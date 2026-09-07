"""The agentic chat service: one question in, a stream of typed events out.

This replaces the single-pass `ChatService.ask_stream`. The event protocol is a superset of
the old one — `conversation`, `delta`, `citations`, `done` are unchanged, so an older client
keeps working — plus `status` frames that say what the pipeline is doing during the seconds
before the first token, and a `verified` frame that resolves after the answer is complete.

Two promises the old service made and this one keeps:

* **Nothing is persisted until the answer is complete.** The question and the answer are
  written together, at the end. That is what makes the client's "nothing was saved, so you
  can ask it again" literally true, and it keeps a failed attempt out of the history that
  the next prompt is built from.
* **The whole thing degrades to a template rather than a 500.** Any unhandled failure in
  the loop produces the deterministic fallback, streamed through the same channel, so the
  client needs no separate error path.
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from contextlib import suppress
from uuid import UUID

import structlog

from src.application.chat.agentic import fallback
from src.application.chat.agentic.context import ContextAssembler
from src.application.chat.agentic.grounding import GroundingChecker
from src.application.chat.agentic.loop import LoopState, RetrievalLoop
from src.application.chat.agentic.prompts import (
    INSUFFICIENT_CONTEXT_ANSWER,
    build_messages,
)
from src.application.chat.titles import title_from_question
from src.domain.entities import ChunkSignalEvent, Conversation, MessageRole
from src.retrieval.langchain.query import QueryResolver, needs_retrieval

logger = structlog.get_logger(__name__)

# Two exchanges. Enough for "what about its pricing?" to resolve, short enough that the
# prompt does not fill with transcript.
_HISTORY_TURNS = 4

_NO_RETRIEVAL_ANSWER = (
    "I answer questions about the sources in your knowledge base. Ask me something about "
    "them and I'll cite where the answer came from."
)


class AgenticChatService:
    """Orchestration only. Every step it calls is a component that can be tested alone."""

    def __init__(
        self,
        *,
        kb_repo,
        conversation_repo,
        chunk_repo,
        loop: RetrievalLoop,
        resolver: QueryResolver,
        assembler: ContextAssembler,
        grounding: GroundingChecker,
        llm_provider,
        grounding_blocking: bool = False,
        signal_repo=None,
        memory_service=None,
        memory_queue=None,
        memory_distill_every_n_turns: int = 3,
    ) -> None:
        self.kb_repo = kb_repo
        self.conversation_repo = conversation_repo
        self.chunk_repo = chunk_repo
        self.loop = loop
        self.resolver = resolver
        self.assembler = assembler
        self.grounding = grounding
        self.llm_provider = llm_provider
        self.grounding_blocking = grounding_blocking
        self.signal_repo = signal_repo
        # Both None disables memory entirely, which is how `memory_enabled = False` is
        # expressed — at the composition seam, not as a flag checked in here.
        self.memory_service = memory_service
        self.memory_queue = memory_queue
        self.memory_distill_every_n_turns = memory_distill_every_n_turns

    async def ask_stream(
        self, conversation_id: UUID | None, question: str
    ) -> AsyncIterator[tuple[str, object]]:
        try:
            async for event in self._ask(conversation_id, question):
                yield event
        except asyncio.CancelledError:
            raise
        except Exception as exc:  # noqa: BLE001 - the stream is the only channel left
            # The unconditional backstop. Anything that escapes the pipeline degrades to a
            # template rather than tearing down the response, so a code failure mid-loop is
            # a legible message instead of a dead connection.
            logger.exception("agentic_stream_failed", error=str(exc))
            yield ("delta", fallback.FAILED)
            yield ("citations", [])
            yield ("done", {"insufficient_context": True, "message_id": None, "user_message_id": None})

    async def _ask(
        self, conversation_id: UUID | None, question: str
    ) -> AsyncIterator[tuple[str, object]]:
        knowledge_base = await self.kb_repo.ensure_default()
        conversation = await self._resolve_conversation(conversation_id, knowledge_base.id, question)
        # Bound once; every log line this question produces carries it from here on, including
        # lines written inside the retrieval and rerank steps that know nothing about requests.
        structlog.contextvars.bind_contextvars(conversation_id=str(conversation.id))
        yield ("conversation", {"id": str(conversation.id), "title": conversation.title})

        # Costs microseconds and saves a full retrieval round-trip on "hi" and "thanks".
        if not needs_retrieval(question):
            async for event in self._answer_without_retrieval(conversation):
                yield event
            return

        history = await self.conversation_repo.recent_messages(conversation.id, _HISTORY_TURNS)
        turns = [{"role": m.role.value, "content": m.content} for m in history]

        yield ("status", {"stage": "resolving"})
        resolved = await self.resolver.resolve(question, turns)

        # Right after resolution, where `resolved.keywords` is the distinctive terms this
        # question is actually about — the same input the lexical retrieval arm gets.
        memories = []
        if self.memory_service is not None:
            memories = await self.memory_service.recall(knowledge_base.id, resolved.keywords)

        state = LoopState(
            question=question,
            resolved_query=resolved.query,
            memories_used=len(memories),
        )
        async for event in self.loop.stream(state, knowledge_base.id, keywords=resolved.keywords):
            yield event

        if not state.found_anything:
            async for event in self._answer_not_found(conversation, question, state):
                yield event
            return

        assembled = await self.assembler.assemble(state.documents)
        if not assembled.citations:
            async for event in self._answer_not_found(conversation, question, state):
                yield event
            return

        yield ("status", {"stage": "reading", "sources": len(assembled.citations)})
        yield ("citations", assembled.wire_citations)

        messages = build_messages(
            resolved.query,
            assembled.blocks,
            history=turns,
            # `max_hops` means the loop ran out of attempts with context it never judged
            # sufficient — the answer should say so rather than imply completeness.
            complete=state.exit_reason == "sufficient",
            memories=[memory.content for memory in memories] or None,
        )

        # The answering model's own time-to-first-token is the last silent stretch. Without
        # this the UI sits on "Reading N passages" while it waits, which reads as a stall.
        yield ("status", {"stage": "generating"})

        pieces: list[str] = []
        async for delta in self.llm_provider.stream(messages):
            pieces.append(delta)
            yield ("delta", delta)

        answer = "".join(pieces).strip()
        if not answer:
            # An empty completion is a provider failure, not an answer. Persist nothing.
            raise RuntimeError("The model returned an empty answer")

        report = None
        if self.grounding_blocking:
            report = await self.grounding.check(answer, assembled.citations)

        user_message, assistant = await self._persist_turn(
            conversation.id,
            question,
            answer,
            assembled.wire_citations,
            insufficient=False,
            trace=state.to_wire(),
            # Blocking mode already has the verdict, so it goes in on the INSERT and needs
            # no second write. The streaming path below fills it in afterwards.
            grounding=report.to_wire() if report else None,
        )
        yield ("done", self._done(user_message, assistant, insufficient=False, state=state))

        # After `done`, so it cannot delay the answer. The client resolves the badge in
        # place when this arrives, and simply never shows one if the connection ended first.
        if report is None:
            report = await self.grounding.check(answer, assembled.citations)
            # Persist before yielding: the check has already been paid for, and a client
            # that hangs up between these two lines should still keep the result. The
            # reverse order would lose it exactly when the user is most likely to reload.
            try:
                await self.conversation_repo.set_grounding(assistant.id, report.to_wire())
            except Exception:  # noqa: BLE001 - a badge that failed to save is not a failed answer
                logger.warning("grounding_persist_failed", message_id=str(assistant.id))

        await self._record_signals(report, assembled.citations)
        await self._maybe_distil(
            knowledge_base.id, question, answer, conversation.id, assistant.id, len(history)
        )
        yield ("verified", report.to_wire())

    # --- terminal paths -------------------------------------------------------------

    async def _answer_without_retrieval(self, conversation) -> AsyncIterator[tuple[str, object]]:
        yield ("delta", _NO_RETRIEVAL_ANSWER)
        yield ("citations", [])
        yield ("done", {"message_id": None, "user_message_id": None, "insufficient_context": False})

    async def _answer_not_found(
        self, conversation, question: str, state: LoopState
    ) -> AsyncIterator[tuple[str, object]]:
        near_misses = fallback.rank_near_misses(state.documents)
        answer = fallback.not_found_answer(
            searched_sources=fallback.searched_source_names(state.documents),
            near_misses=near_misses,
        )
        if not state.documents:
            answer = INSUFFICIENT_CONTEXT_ANSWER + " " + fallback.NOT_FOUND

        logger.info(
            "fallback_triggered",
            reason=state.exit_reason,
            hops=state.hop_count,
            question=question,
        )
        yield ("delta", answer)
        yield ("citations", [])
        user_message, assistant = await self._persist_turn(
            conversation.id, question, answer, [], insufficient=True, trace=state.to_wire()
        )
        yield ("done", self._done(user_message, assistant, insufficient=True, state=state))

    # --- persistence ----------------------------------------------------------------

    async def _resolve_conversation(self, conversation_id, knowledge_base_id, question):
        if conversation_id is None:
            return await self.conversation_repo.create(
                Conversation(
                    knowledge_base_id=knowledge_base_id,
                    title=title_from_question(question),
                )
            )
        conversation = await self.conversation_repo.get(conversation_id)
        if conversation is None:
            raise ValueError("Conversation not found")
        return conversation

    async def _persist_turn(
        self, conversation_id, question, answer, citations, *, insufficient, trace=None,
        grounding=None,
    ):
        from src.domain.entities import Message

        user_message = await self.conversation_repo.append_message(
            Message(conversation_id=conversation_id, role=MessageRole.USER, content=question)
        )
        assistant = await self.conversation_repo.append_message(
            Message(
                conversation_id=conversation_id,
                role=MessageRole.ASSISTANT,
                content=answer,
                citations=citations,
                trace=trace,
                grounding=grounding,
                insufficient_context=insufficient,
            )
        )
        return user_message, assistant

    async def _maybe_distil(
        self, knowledge_base_id, question, answer, conversation_id, message_id, history_length
    ) -> None:
        """Hand this exchange to the background distiller, if it is worth the model call.

        Two of the three gates are structural rather than checked here: this is only reached
        on the successful path, so a fallback and an `insufficient_context` answer have both
        already returned above and can never be distilled. Neither contains anything the
        workspace said about itself. The gate that is checked is the turn counter, which
        keeps this to one call per few exchanges — a table that gains a row a week does not
        deserve a model call per question.

        Deferred, never awaited inline: it is a second model call, and the answer is already
        finished. Nothing here can fail the stream.
        """
        if self.memory_queue is None or not self.memory_distill_every_n_turns:
            return
        if history_length % self.memory_distill_every_n_turns:
            return

        try:
            from src.core.tenant_context import current_tenant_id, current_user_id

            await self.memory_queue.enqueue_distillation(
                knowledge_base_id,
                current_tenant_id(),
                current_user_id(),
                question=question,
                answer=answer,
                conversation_id=conversation_id,
                message_id=message_id,
            )
        except Exception:  # noqa: BLE001 - a worker that is down must not break answering
            logger.warning("memory_distill_enqueue_failed")

    async def _record_signals(self, report, citations) -> None:
        """Attribute the answer's outcome back to the passages it was written from.

        Here rather than in the retrieval loop, for two reasons that both matter. It needs
        the grounding verdict, which does not exist until after the answer. And it must
        record the citations that *reached the answer*, not the retrieval pool — rewarding
        everything retrieved would reward being retrieved, which is the thing the prior
        influences, closing the loop with no signal from outside it.

        Ordinal N is `citations[N-1]`. Invalid ordinals resolve to no citation and are
        skipped; a fallback answer cites nothing and so produces no signal at all, which is
        correct — the reader is looking at the absence of an answer.
        """
        if self.signal_repo is None or not report.cited_ordinals:
            return

        unsupported = set(report.unsupported_ordinals)
        events = []
        for ordinal in report.cited_ordinals:
            if not 1 <= ordinal <= len(citations):
                continue
            chunk_id = citations[ordinal - 1].chunk_id
            if not chunk_id:
                continue
            with suppress(ValueError, AttributeError):
                events.append(
                    ChunkSignalEvent(
                        chunk_id=UUID(chunk_id),
                        cited=1,
                        supported=0 if ordinal in unsupported else 1,
                        unsupported=1 if ordinal in unsupported else 0,
                    )
                )

        try:
            await self.signal_repo.record(events)
        except Exception:  # noqa: BLE001 - the answer is already written, streamed and stored
            logger.warning("signal_record_failed", events=len(events))

    @staticmethod
    def _done(user_message, assistant, *, insufficient: bool, state: LoopState) -> dict:
        return {
            "user_message_id": str(user_message.id) if user_message else None,
            "message_id": str(assistant.id) if assistant else None,
            "insufficient_context": insufficient,
            "created_at": assistant.created_at.isoformat() if assistant and assistant.created_at else None,
            # Surfaced so the UI (and the eval harness) can see how the answer was reached
            # without re-deriving it from a trace.
            "hops": state.hop_count,
            "exit_reason": state.exit_reason,
            # The full hop-by-hop record, so the client can show how the answer was reached
            # without a second request and without re-deriving it from a Langfuse trace.
            "trace": state.to_wire(),
        }
