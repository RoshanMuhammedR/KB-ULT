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

from dataclasses import dataclass, field
from uuid import UUID

import structlog
from langchain_core.documents import Document

from src.infrastructure.observability import tracing
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

    async def run(
        self,
        state: LoopState,
        knowledge_base_id: UUID,
        *,
        keywords: str = "",
    ) -> LoopState:
        query = state.resolved_query
        # The lexical arm wants distinctive terms, not a sentence: `websearch_to_tsquery`
        # ANDs what it is given, so a full conversational question usually matches nothing.
        lexical_query = keywords or query
        strategy = "initial"
        consecutive_empty = 0

        while state.hop_count < self.max_hops:
            hop = state.hop_count + 1
            documents, degraded = await self._retrieve(query, lexical_query, knowledge_base_id)
            state.degraded = state.degraded or degraded

            self._merge(state, documents)

            if not documents:
                consecutive_empty += 1
            else:
                consecutive_empty = 0

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
        return state

    async def _retrieve(
        self, query: str, lexical_query: str, knowledge_base_id: UUID
    ) -> tuple[list[Document], bool]:
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
        candidates = await retriever.ainvoke(lexical_query, config={"callbacks": tracing.callbacks()})
        return await self.reranker.compress(candidates, query)

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
