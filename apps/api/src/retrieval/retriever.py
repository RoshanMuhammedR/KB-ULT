from __future__ import annotations

from uuid import UUID

import structlog

from src.domain.entities import RetrievalResult
from src.domain.interfaces import IVectorStore
from src.retrieval.fusion import DEFAULT_RRF_K, reciprocal_rank_fusion

logger = structlog.get_logger(__name__)

# Equal influence per arm. Neither is reliably better than the other — dense wins on
# paraphrase, lexical on exact identifiers — and weighting one up would trade one failure
# mode for the other. Constants rather than settings so there is one fewer knob whose correct
# value nobody can justify.
_DENSE_WEIGHT = 1.0
_LEXICAL_WEIGHT = 1.0


class Retriever:
    """Runs both retrieval arms and fuses them into one ranking.

    Dense search alone misses text it should trivially find: error codes, config keys, rare
    proper nouns — the tokens embeddings represent worst. Lexical search alone misses anything
    phrased differently from the source. Running both and fusing by rank gets most of each,
    and costs one extra query over ~30 rows.
    """

    def __init__(
        self,
        vector_store: IVectorStore,
        candidate_multiplier: int = 6,
        rrf_k: int = DEFAULT_RRF_K,
    ) -> None:
        self.vector_store = vector_store
        self.candidate_multiplier = max(1, candidate_multiplier)
        self.rrf_k = rrf_k

    def retrieve(
        self,
        query_embedding: list[float],
        knowledge_base_id: UUID,
        top_k: int,
        threshold: float,
        query_text: str = "",
    ) -> list[RetrievalResult]:
        # Both arms over-fetch. For the dense arm that is what lets the threshold apply to a
        # pool instead of a truncated list; for fusion it means a chunk ranked 12th by one arm
        # and 3rd by the other is still visible to be promoted.
        limit = top_k * self.candidate_multiplier

        dense = self.vector_store.search_dense(
            query_embedding, knowledge_base_id, limit, threshold
        )
        lexical = (
            self.vector_store.search_lexical(query_embedding, query_text, knowledge_base_id, limit)
            if query_text.strip()
            else []
        )

        # Nothing to fuse: skip the work and keep the dense ordering exactly as it was.
        if not lexical:
            return dense[:top_k]

        by_id: dict[str, RetrievalResult] = {}
        for result in (*dense, *lexical):
            by_id.setdefault(str(result.chunk.id), result)

        fused_ids = reciprocal_rank_fusion(
            [[str(r.chunk.id) for r in dense], [str(r.chunk.id) for r in lexical]],
            k=self.rrf_k,
            weights=[_DENSE_WEIGHT, _LEXICAL_WEIGHT],
        )
        results = [by_id[chunk_id] for chunk_id in fused_ids[:top_k]]

        logger.info(
            "retrieval_fused",
            dense_count=len(dense),
            lexical_count=len(lexical),
            # How many of the winners the lexical arm contributed that dense had not already
            # found. If this is persistently 0, the lexical arm is earning nothing and the
            # AND-semantics tradeoff is worth revisiting.
            lexical_only_promoted=sum(
                1
                for r in results
                if r.chunk.id not in {d.chunk.id for d in dense}
            ),
            returned=len(results),
        )
        return results
