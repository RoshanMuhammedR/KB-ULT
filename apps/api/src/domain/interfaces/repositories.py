from __future__ import annotations

from typing import Protocol
from uuid import UUID

from src.domain.entities import Chunk, Embedding, KnowledgeAsset, KnowledgeBase


class IKnowledgeBaseRepository(Protocol):
    def get_default(self) -> KnowledgeBase | None:
        ...

    def ensure_default(self) -> KnowledgeBase:
        ...


class IDocumentRepository(Protocol):
    def list_current(self, knowledge_base_id: UUID) -> list[KnowledgeAsset]:
        ...

    def get(self, asset_id: UUID) -> KnowledgeAsset | None:
        ...

    def latest_for_filename(self, knowledge_base_id: UUID, filename: str) -> KnowledgeAsset | None:
        ...

    def create_pending(self, asset: KnowledgeAsset) -> KnowledgeAsset:
        ...

    def update_from_domain(self, asset: KnowledgeAsset) -> KnowledgeAsset:
        ...

    def rename(self, asset_id: UUID, title: str) -> KnowledgeAsset:
        ...

    def supersede_previous_versions(self, lineage_id: UUID, active_asset_id: UUID) -> None:
        ...

    def delete(self, asset_id: UUID) -> None:
        ...


class IChunkRepository(Protocol):
    def replace_for_asset(self, asset_id: UUID, chunks: list[Chunk]) -> list[Chunk]:
        ...

    def list_for_asset(self, asset_id: UUID) -> list[Chunk]:
        ...


class IEmbeddingRepository(Protocol):
    def replace_for_chunks(self, chunks: list[Chunk], embeddings: list[Embedding]) -> None:
        ...
