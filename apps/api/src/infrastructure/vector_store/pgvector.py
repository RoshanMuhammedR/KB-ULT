from __future__ import annotations

from uuid import UUID

from sqlalchemy.orm import Session

from src.domain.entities import Chunk, Embedding, KnowledgeAsset, RetrievalResult
from src.infrastructure.repositories.mappers import asset_to_domain, chunk_to_domain
from src.infrastructure.repositories.postgres_chunk_repository import EmbeddingRepository


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

    def search(
        self,
        query_embedding: list[float],
        knowledge_base_id: UUID,
        top_k: int,
        threshold: float,
    ) -> list[RetrievalResult]:
        rows = self.embedding_repo.query_ready_chunks(query_embedding, knowledge_base_id, top_k)
        results: list[RetrievalResult] = []
        for chunk_model, asset_model, score in rows:
            if score >= threshold:
                results.append(
                    RetrievalResult(
                        chunk=chunk_to_domain(chunk_model),
                        asset=asset_to_domain(asset_model),
                        score=score,
                    )
                )
        return results
