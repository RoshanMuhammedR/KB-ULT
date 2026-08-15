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

    def search_dense(
        self,
        query_embedding: list[float],
        knowledge_base_id: UUID,
        limit: int,
        threshold: float,
    ) -> list[RetrievalResult]:
        """Nearest neighbours by cosine similarity, over current + ready asset versions.

        `threshold` is applied here, to the whole candidate pool, so the caller can
        over-fetch and still end up with a full set of results that all clear the bar.
        """

    def search_lexical(
        self,
        query_embedding: list[float],
        query_text: str,
        knowledge_base_id: UUID,
        limit: int,
    ) -> list[RetrievalResult]:
        """Chunks containing the query's literal terms, best keyword match first.

        Deliberately *not* thresholded on similarity: a chunk holding the exact error code
        someone searched for may score poorly on cosine and still be the right answer, and
        filtering it out on a semantic score would defeat the purpose of searching lexically
        at all. Requiring the terms to be present is itself the relevance criterion.
        """
