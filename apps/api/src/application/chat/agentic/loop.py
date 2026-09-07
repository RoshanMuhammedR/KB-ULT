"""The bounded retrieval loop: retrieve, judge, rewrite, retrieve again, stop.

**Two hops, not three.** A question that survives two well-formed hybrid retrievals is
usually a question the corpus cannot answer. A third hop buys latency and a more elaborate
wrong answer, and the honest response to "it isn't in here" is to say so. The cap is
business logic and lives here; the queue's retry policy is infrastructure resilience and
lives in the queue — conflating them would make each one's behaviour depend on the other's.

**The hop counter is per request.** It lives on `LoopState`, never at module scope: a
counter shared between concurrent questions is a bug that only appears under load.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import suppress
from dataclasses import dataclass, field
from uuid import UUID

import structlog
from langchain_core.documents import Document

from src.infrastructure.observability import tracing
from src.retrieval.langchain.prior import apply_prior
from src.retrieval.langchain.query import QueryRewriter, SufficiencyChecker
from src.retrieval.langchain.rerank import ScoringReranker
from src.retrieval.langchain.retrievers import CHUNK_ID, build_hybrid_retriever

logger = structlog.get_logger(__name__)


@dataclass(slots=True)
class HopRecord:
    """What one hop did, for the trace and for the eval harness."""

    hop: int
    query: str
    strategy: str
    candidates: int
    kept: int
    rerank_degraded: bool
    sufficient: bool
    missing: str = ""

    def to_wire(self) -> dict:
        """The shape the client renders and the message row stores."""
        return {
            "hop": self.hop,
            "query": self.query,
            "strategy": self.strategy,
            "candidates": self.candidates,
            "kept": self.kept,
            "rerank_degraded": self.rerank_degraded,
            "sufficient": self.sufficient,
            "missing": self.missing,
        }


@dataclass(slots=True)
class LoopState:
    """Everything one question accumulates. Never shared between requests."""

    question: str
    resolved_query: str
    documents: list[Document] = field(default_factory=list)
    hops: list[HopRecord] = field(default_factory=list)
    exit_reason: str = ""
    degraded: bool = False

    @property
    def hop_count(self) -> int:
        return len(self.hops)

    @property
    def found_anything(self) -> bool:
        return bool(self.documents)

    def to_wire(self) -> dict:
        """How the answer was reached, for the trace panel and the eval harness.

        Carries the resolved query and every hop, but never the passages themselves - the
        citations already ship those, and duplicating them would double the size of a row
        that is written on every single answer.
        """
        return {
            "resolved_query": self.resolved_query,
            "hops": [hop.to_wire() for hop in self.hops],
            "exit_reason": self.exit_reason,
            "degraded": self.degraded,
        }


class RetrievalLoop:
    """Runs hops until the context is sufficient, the cap is reached, or nothing is found.

    Exit reasons, all recorded on the state so a trace can be read without re-deriving them:

    * `sufficient`   — the grader says the passages answer the question. The common case.
    * `max_hops`     — the cap was reached with context that is usable but incomplete. The
                       answer is generated *with* a caveat rather than withheld; partial
                       information plus an honest hedge beats a refusal the user can see is
                       wrong.
    * `nothing_found`— two consecutive empty hops. Nothing to answer from, so the caller
                       falls back to a deterministic template rather than inventing prose.
    """

    def __init__(
        self,
        *,
        vector_store,
        embedding_provider,
        reranker: ScoringReranker,
        rewriter: QueryRewriter,
        sufficiency: SufficiencyChecker,
        max_hops: int,
        candidate_limit: int,
        threshold: float,
        rrf_k: int,
        signal_repo=None,
        prior_settings=None,
    ) -> None:
        self.vector_store = vector_store
        self.embedding_provider = embedding_provider
        self.reranker = reranker
        self.rewriter = rewriter
        self.sufficiency = sufficiency
        self.max_hops = max_hops
        self.candidate_limit = candidate_limit
        self.threshold = threshold
        self.rrf_k = rrf_k
        # `None` disables the prior entirely — which is how `retrieval_prior_enabled = False`
        # is implemented, at the composition seam rather than as a flag threaded through
        # here. A loop with no signal repository cannot accidentally consult one.
        self.signal_repo = signal_repo
        self.prior_settings = prior_settings

    async def stream(
        self,
        state: LoopState,
        knowledge_base_id: UUID,
        *,
        keywords: str = "",
    ) -> AsyncIterator[tuple[str, dict]]:
        """Run the hops, yielding a status frame at each phase boundary.

        A generator rather than a coroutine because this is the longest part of answering a
        question - two retrievals, two rerank calls and two grading calls - and reporting it
        as one opaque "searching" left the user watching a spinner for seconds with no idea
        whether anything was happening. `state` is mutated in place, so the caller still has
        the finished LoopState once this is drained.
        """
        query = state.resolved_query
        # The lexical arm wants distinctive terms, not a sentence: `websearch_to_tsquery`
        # ANDs what it is given, so a full conversational question usually matches nothing.
        lexical_query = keywords or query
        strategy = "initial"
        consecutive_empty = 0

        while state.hop_count < self.max_hops:
            hop = state.hop_count + 1
            yield (
                "status",
                {"stage": "searching", "hop": hop, "of": self.max_hops, "strategy": strategy},
            )
            candidates = await self._fetch(query, lexical_query, knowledge_base_id)

            yield (
                "status",
                {"stage": "ranking", "hop": hop, "of": self.max_hops, "candidates": len(candidates)},
            )
            documents, degraded = await self.reranker.compress(candidates, query)
            state.degraded = state.degraded or degraded

            self._merge(state, documents)

            if not documents:
                consecutive_empty += 1
            else:
                consecutive_empty = 0

            yield (
                "status",
                {"stage": "grading", "hop": hop, "of": self.max_hops, "kept": len(state.documents)},
            )
            verdict = await self.sufficiency.check(
                state.question, [d.page_content for d in state.documents]
            )
            state.hops.append(
                HopRecord(
                    hop=hop,
                    query=query,
                    strategy=strategy,
                    candidates=len(documents),
                    kept=len(state.documents),
                    rerank_degraded=degraded,
                    sufficient=verdict.sufficient,
                    missing=verdict.missing,
                )
            )

            if verdict.sufficient:
                state.exit_reason = "sufficient"
                break

            # Two hops that both found nothing means the corpus does not contain this, not
            # that the query was phrased badly. Rewriting again would be a third search for
            # something that is not there.
            if consecutive_empty >= 2:
                state.exit_reason = "nothing_found"
                break

            if state.hop_count >= self.max_hops:
                state.exit_reason = "max_hops"
                break

            query, strategy = await self.rewriter.rewrite(query)
            lexical_query = query
            logger.info("retrieval_rewrite", hop=hop, strategy=strategy, query=query)
            yield (
                "status",
                {"stage": "rewriting", "hop": hop + 1, "of": self.max_hops, "strategy": strategy},
            )

        if not state.exit_reason:
            state.exit_reason = "max_hops"
        if not state.found_anything:
            state.exit_reason = "nothing_found"

        logger.info(
            "retrieval_loop_complete",
            hops=state.hop_count,
            exit_reason=state.exit_reason,
            documents=len(state.documents),
            degraded=state.degraded,
        )

    async def _fetch(
        self, query: str, lexical_query: str, knowledge_base_id: UUID
    ) -> list[Document]:
        embedding = await self.embedding_provider.embed_query(query)
        retriever = build_hybrid_retriever(
            self.vector_store,
            embedding,
            knowledge_base_id,
            limit=self.candidate_limit,
            threshold=self.threshold,
            rrf_k=self.rrf_k,
        )
        # The ensemble passes one query string to both arms, but the arms want different
        # things — a sentence for the embedding, keywords for `websearch_to_tsquery`. The
        # dense arm already has its vector, so the string it receives is unused.
        # Reranking is deliberately *not* done here: the caller yields a status frame
        # between retrieval and ranking, which it cannot do if the two are one await.
        documents = await retriever.ainvoke(
            lexical_query, config={"callbacks": tracing.callbacks()}
        )
        return await self._apply_prior(documents)

    async def _apply_prior(self, documents: list[Document]) -> list[Document]:
        """Nudge fusion order by what these passages have done before, if that is enabled.

        Between retrieval and reranking, not inside either. Not in the reranker, because it
        judges text and giving it a database dependency would make a scoring call into an
        I/O call. Not in the retrievers, because a prior is only defined over documents some
        arm has already found.

        Every failure here is silent and total: an unavailable signal store leaves the fused
        order untouched, which is exactly what the answer would have been anyway.
        """
        if self.signal_repo is None or not documents:
            return documents

        chunk_ids = []
        for document in documents:
            raw = document.metadata.get(CHUNK_ID)
            if raw:
                with suppress(ValueError, AttributeError):
                    chunk_ids.append(UUID(raw))

        try:
            priors = await self.signal_repo.priors(chunk_ids)
        except Exception:  # noqa: BLE001 - the answer was already correct without the prior
            logger.warning("prior_unavailable", candidates=len(documents))
            return documents

        return apply_prior(
            documents,
            priors,
            max_shift=self.prior_settings.retrieval_prior_max_rank_shift,
            saturation=self.prior_settings.retrieval_prior_saturation,
            half_life_days=self.prior_settings.retrieval_prior_half_life_days,
            upvote_weight=self.prior_settings.feedback_upvote_weight,
            downvote_weight=self.prior_settings.feedback_downvote_weight,
        )

    @staticmethod
    def _merge(state: LoopState, documents: list[Document]) -> None:
        """Accumulate across hops, keeping the best-judged copy of each chunk.

        A chunk found by both hops is one chunk. Deduplicating by id (rather than by text)
        also means the ordinal citation map can be built once, from a list that cannot
        contain the same passage twice under two different numbers.
        """
        by_id = {d.metadata.get(CHUNK_ID): d for d in state.documents}
        for document in documents:
            key = document.metadata.get(CHUNK_ID)
            existing = by_id.get(key)
            if existing is None or document.metadata.get("rerank_score", 0.0) > existing.metadata.get(
                "rerank_score", 0.0
            ):
                by_id[key] = document
        state.documents = sorted(
            by_id.values(),
            key=lambda d: d.metadata.get("rerank_score", d.metadata.get("score", 0.0)),
            reverse=True,
        )
