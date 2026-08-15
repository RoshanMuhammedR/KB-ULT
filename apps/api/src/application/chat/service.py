from __future__ import annotations

from typing import Iterator
from uuid import UUID

import structlog

from src.application.chat.citations import build_citations
from src.application.chat.prompt_builder import PromptBuilder
from src.application.chat.titles import title_from_question
from src.domain.entities import Conversation, Message, MessageRole, RetrievalResult
from src.infrastructure.ai_providers import AICreditsEmbeddingProvider, AICreditsLLMProvider
from src.infrastructure.repositories import ConversationRepository, KnowledgeBaseRepository
from src.retrieval.retriever import Retriever

logger = structlog.get_logger(__name__)

# How much of a thread is replayed to the model on a follow-up. Four turns is two
# exchanges — enough for "what about the second one?" without paying for the whole history.
_HISTORY_TURNS = 4


class ChatService:
    def __init__(
        self,
        kb_repo: KnowledgeBaseRepository,
        embedding_provider: AICreditsEmbeddingProvider,
        retriever: Retriever,
        llm_provider: AICreditsLLMProvider,
        prompt_builder: PromptBuilder,
        top_k: int,
        threshold: float,
        min_context_chunks: int,
        conversation_repo: ConversationRepository | None = None,
    ) -> None:
        self.kb_repo = kb_repo
        self.embedding_provider = embedding_provider
        self.retriever = retriever
        self.llm_provider = llm_provider
        self.prompt_builder = prompt_builder
        self.top_k = top_k
        self.threshold = threshold
        self.min_context_chunks = min_context_chunks
        self.conversation_repo = conversation_repo

    # --- One-shot (kept for POST /chat/ask and the smoke path) ---------------------

    def ask(self, question: str) -> dict:
        knowledge_base = self.kb_repo.ensure_default()
        results = self._retrieve(question, knowledge_base.id)

        if len(results) < self.min_context_chunks:
            answer = self.prompt_builder.insufficient_context_answer()
            logger.info("chat_insufficient_context", query=question, result_count=len(results))
            return self._response(answer, results, insufficient=True)

        messages = self.prompt_builder.build(question, results)
        logger.info("chat_prompt_created", query=question, context_count=len(results))
        answer = self.llm_provider.generate(messages)
        logger.info("chat_llm_response", query=question, answer_length=len(answer))
        return self._response(answer, results, insufficient=False)

    # --- Streaming, conversation-aware --------------------------------------------

    def ask_stream(self, conversation_id: UUID | None, question: str) -> Iterator[tuple[str, object]]:
        """Yield `("conversation", id)`, `("delta", str)`, `("citations", list)`, `("done", ids)`.

        The user's message is persisted immediately, but the assistant's only after the
        stream finishes. A failure mid-stream therefore persists nothing, which is exactly
        what the client promises the user ("nothing was saved, so you can ask it again
        as-is") — a half-written answer never survives a reload.
        """
        if self.conversation_repo is None:
            raise RuntimeError("ChatService was built without a conversation repository")

        knowledge_base = self.kb_repo.ensure_default()
        conversation = self._resolve_conversation(conversation_id, knowledge_base.id, question)
        yield ("conversation", {"id": str(conversation.id), "title": conversation.title})

        history = self.conversation_repo.recent_messages(conversation.id, _HISTORY_TURNS)

        user_message = self.conversation_repo.append_message(
            Message(conversation_id=conversation.id, role=MessageRole.USER, content=question)
        )

        results = self._retrieve(question, knowledge_base.id, history=history)
        citations = build_citations(results)

        if len(results) < self.min_context_chunks:
            answer = self.prompt_builder.insufficient_context_answer()
            logger.info("chat_insufficient_context", query=question, result_count=len(results))
            yield ("delta", answer)
            yield ("citations", citations)
            assistant = self._persist_answer(conversation.id, answer, citations, insufficient=True)
            yield ("done", self._done(user_message, assistant, insufficient=True))
            return

        messages = self.prompt_builder.build(question, results, history=self._as_turns(history))
        logger.info("chat_prompt_created", query=question, context_count=len(results))

        pieces: list[str] = []
        for delta in self.llm_provider.stream(messages):
            pieces.append(delta)
            yield ("delta", delta)

        answer = "".join(pieces).strip()
        if not answer:
            # An empty completion is a provider failure, not an answer — persist nothing.
            raise RuntimeError("The model returned an empty answer")

        logger.info("chat_llm_response", query=question, answer_length=len(answer))
        yield ("citations", citations)
        assistant = self._persist_answer(conversation.id, answer, citations, insufficient=False)
        yield ("done", self._done(user_message, assistant, insufficient=False))

    # --- Internals ----------------------------------------------------------------

    def _retrieve(
        self,
        question: str,
        knowledge_base_id: UUID,
        history: list[Message] | None = None,
    ) -> list[RetrievalResult]:
        # An elliptical follow-up ("what about the second one?") embeds to almost nothing on
        # its own, so the previous question is prepended to give it something to match on.
        # Deliberately cheap; an LLM query-rewrite is the later upgrade.
        query = question
        previous = self._previous_question(history or [])
        if previous:
            query = f"{previous}\n{question}"

        query_embedding = self.embedding_provider.embed_query(query)
        results = self.retriever.retrieve(
            query_embedding=query_embedding,
            knowledge_base_id=knowledge_base_id,
            top_k=self.top_k,
            threshold=self.threshold,
            # The raw text drives the lexical arm. It gets the same follow-up expansion as the
            # embedding, so "what about the second one?" carries the previous question's terms
            # into the keyword search too.
            query_text=query,
        )
        logger.info(
            "chat_retrieval",
            query=question,
            followup=bool(previous),
            top_k=self.top_k,
            threshold=self.threshold,
            scores=[round(result.score, 4) for result in results],
        )
        return results

    @staticmethod
    def _previous_question(history: list[Message]) -> str | None:
        for message in reversed(history):
            if message.role is MessageRole.USER:
                return message.content
        return None

    @staticmethod
    def _as_turns(history: list[Message]) -> list[dict[str, str]]:
        return [{"role": message.role.value, "content": message.content} for message in history]

    def _resolve_conversation(
        self, conversation_id: UUID | None, knowledge_base_id: UUID, question: str
    ) -> Conversation:
        assert self.conversation_repo is not None
        if conversation_id is not None:
            existing = self.conversation_repo.get(conversation_id)
            if existing is None:
                raise ValueError("Conversation not found")
            return existing
        # First question in a new thread also names it — no extra model call.
        return self.conversation_repo.create(
            Conversation(knowledge_base_id=knowledge_base_id, title=title_from_question(question))
        )

    def _persist_answer(
        self, conversation_id: UUID, answer: str, citations: list[dict], insufficient: bool
    ) -> Message:
        assert self.conversation_repo is not None
        return self.conversation_repo.append_message(
            Message(
                conversation_id=conversation_id,
                role=MessageRole.ASSISTANT,
                content=answer,
                citations=citations,
                insufficient_context=insufficient,
            )
        )

    @staticmethod
    def _done(user_message: Message, assistant: Message, insufficient: bool) -> dict:
        return {
            "user_message_id": str(user_message.id),
            "message_id": str(assistant.id),
            "insufficient_context": insufficient,
            "created_at": assistant.created_at.isoformat() if assistant.created_at else None,
        }

    def _response(self, answer: str, results: list[RetrievalResult], insufficient: bool) -> dict:
        return {
            "answer": answer,
            "insufficient_context": insufficient,
            "citations": build_citations(results),
        }
