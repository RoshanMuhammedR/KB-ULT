from __future__ import annotations

import structlog

from src.application.chat.citations import build_citations
from src.application.chat.prompt_builder import PromptBuilder
from src.domain.entities import RetrievalResult
from src.infrastructure.ai_providers import AICreditsEmbeddingProvider, AICreditsLLMProvider
from src.infrastructure.repositories import KnowledgeBaseRepository
from src.retrieval.retriever import Retriever

logger = structlog.get_logger(__name__)


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
    ) -> None:
        self.kb_repo = kb_repo
        self.embedding_provider = embedding_provider
        self.retriever = retriever
        self.llm_provider = llm_provider
        self.prompt_builder = prompt_builder
        self.top_k = top_k
        self.threshold = threshold
        self.min_context_chunks = min_context_chunks

    def ask(self, question: str) -> dict:
        knowledge_base = self.kb_repo.ensure_default()
        query_embedding = self.embedding_provider.embed_query(question)
        results = self.retriever.retrieve(
            query_embedding=query_embedding,
            knowledge_base_id=knowledge_base.id,
            top_k=self.top_k,
            threshold=self.threshold,
        )
        logger.info(
            "chat_retrieval",
            query=question,
            top_k=self.top_k,
            threshold=self.threshold,
            scores=[round(result.score, 4) for result in results],
        )

        if len(results) < self.min_context_chunks:
            answer = self.prompt_builder.insufficient_context_answer()
            logger.info("chat_insufficient_context", query=question, result_count=len(results))
            return self._response(answer, results, insufficient=True)

        messages = self.prompt_builder.build(question, results)
        logger.info("chat_prompt_created", query=question, context_count=len(results))
        answer = self.llm_provider.generate(messages)
        logger.info("chat_llm_response", query=question, answer_length=len(answer))
        return self._response(answer, results, insufficient=False)

    def _response(self, answer: str, results: list[RetrievalResult], insufficient: bool) -> dict:
        return {
            "answer": answer,
            "insufficient_context": insufficient,
            "citations": build_citations(results),
        }
