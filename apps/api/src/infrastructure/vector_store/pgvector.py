from __future__ import annotations

from uuid import UUID

import structlog
from sqlalchemy.exc import ProgrammingError
from sqlalchemy.orm import Session

from src.domain.entities import Chunk, Embedding, KnowledgeAsset, RetrievalResult
from src.infrastructure.repositories.mappers import asset_to_domain, chunk_to_domain
from src.infrastructure.repositories.postgres_chunk_repository import EmbeddingRepository

logger = structlog.get_logger(__name__)


class PgVectorStore:
    def __init__(self, db: Session) -> None:
        self.embedding_repo = EmbeddingRepository(db)

    def upsert_embeddings(
        self,
        asset: KnowledgeAsset,
        chunks: list[Chunk],
        embeddings: list[Embedding],
    ) -> None:
        self.embedding_repo.replace_for_chunks(chunks, embeddings)

    def search_dense(
        self,
        query_embedding: list[float],
        knowledge_base_id: UUID,
        limit: int,
        threshold: float,
    ) -> list[RetrievalResult]:
        rows = self.embedding_repo.query_ready_chunks(query_embedding, knowledge_base_id, limit)
        # The threshold now filters a candidate pool rather than an already-truncated list, so
        # a marginal match no longer costs a result slot — it is simply replaced by the next
        # candidate down.
        return [self._to_result(row) for row in rows if row[2] >= threshold]

    def search_lexical(
        self,
        query_embedding: list[float],
        query_text: str,
        knowledge_base_id: UUID,
        limit: int,
    ) -> list[RetrievalResult]:
        try:
            rows = self.embedding_repo.query_ready_chunks_lexical(
                query_embedding, query_text, knowledge_base_id, limit
            )
        except ProgrammingError:
            # `chunks.fts` is added by migration 0004. If the code is deployed ahead of the
            # migration, degrade to dense-only rather than 500-ing every question — the same
            # honest-degradation rule the ingestion handlers follow.
            logger.warning("lexical_search_unavailable", reason="chunks.fts missing; run 0004")
            return []
        return [self._to_result(row) for row in rows]

    @staticmethod
    def _to_result(row: tuple) -> RetrievalResult:
        chunk_model, asset_model, score = row
        return RetrievalResult(
            chunk=chunk_to_domain(chunk_model),
            asset=asset_to_domain(asset_model),
            score=float(score),
        )
