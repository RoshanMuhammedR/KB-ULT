from __future__ import annotations

from typing import Protocol
from uuid import UUID

from src.domain.entities import Chunk, Embedding, KnowledgeAsset, RetrievalResult


class IVectorStore(Protocol):
    def upsert_embeddings(
        self,
        asset: KnowledgeAsset,
        chunks: list[Chunk],
        embeddings: list[Embedding],
    ) -> None:
        """Persist embeddings for an asset version."""

    def search(
        self,
        query_embedding: list[float],
        knowledge_base_id: UUID,
        top_k: int,
        threshold: float,
    ) -> list[RetrievalResult]:
        """Search current, ready asset versions by vector similarity."""
