from __future__ import annotations

from typing import Protocol
from uuid import UUID

from src.domain.entities import Chunk, Embedding, KnowledgeAsset, KnowledgeBase
from src.domain.entities.ingestion_job import IngestionJob
from src.domain.entities.job_event import JobEvent


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


class IIngestionJobRepository(Protocol):
    """Persistence for the domain-level ingestion job record."""

    def create(self, job: IngestionJob) -> IngestionJob:
        ...

    def get(self, job_id: UUID) -> IngestionJob | None:
        ...

    def latest_for_asset(self, asset_id: UUID) -> IngestionJob | None:
        ...

    def list_recent(self, limit: int = 50) -> list[IngestionJob]:
        """Most-recent jobs across all assets, for the monitoring dashboard."""
        ...

    def mark_running(self, job_id: UUID) -> IngestionJob:
        """Flip to RUNNING, stamp started_at, and increment the attempt counter."""
        ...

    def mark_succeeded(self, job_id: UUID) -> IngestionJob:
        ...

    def mark_failed(self, job_id: UUID, error: str) -> IngestionJob:
        """Record a terminal failure with its error message."""
        ...

    def reset_for_retry(self, job_id: UUID) -> IngestionJob:
        """Return a failed job to QUEUED so it can be deferred again."""
        ...


class IIngestionJobEventRepository(Protocol):
    """Append-only worker log: the durable per-asset ingestion event trail."""

    def append(self, event: JobEvent) -> JobEvent:
        """Persist one event. Best-effort — callers treat logging as non-fatal."""
        ...

    def list_for_asset(self, asset_id: UUID, limit: int = 200) -> list[JobEvent]:
        """Chronological events for an asset (what the dashboard expands)."""
        ...

    def list_for_job(self, job_id: UUID) -> list[JobEvent]:
        ...


class IChunkRepository(Protocol):
    def replace_for_asset(self, asset_id: UUID, chunks: list[Chunk]) -> list[Chunk]:
        ...

    def list_for_asset(self, asset_id: UUID) -> list[Chunk]:
        ...


class IEmbeddingRepository(Protocol):
    def replace_for_chunks(self, chunks: list[Chunk], embeddings: list[Embedding]) -> None:
        ...
