from __future__ import annotations

from uuid import UUID

from src.domain.entities import RetrievalResult
from src.domain.interfaces import IVectorStore


class Retriever:
    def __init__(self, vector_store: IVectorStore) -> None:
        self.vector_store = vector_store

    def retrieve(
        self,
        query_embedding: list[float],
        knowledge_base_id: UUID,
        top_k: int,
        threshold: float,
    ) -> list[RetrievalResult]:
        return self.vector_store.search(query_embedding, knowledge_base_id, top_k, threshold)
