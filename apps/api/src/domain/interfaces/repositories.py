from __future__ import annotations

from typing import Protocol
from uuid import UUID

from src.domain.entities import (
    Chunk,
    ChunkSignal,
    ChunkSignalEvent,
    Embedding,
    KnowledgeAsset,
    KnowledgeBase,
)
from src.domain.entities.ingestion_job import IngestionJob
from src.domain.entities.job_event import JobEvent
from src.domain.entities.refresh_token import RefreshToken
from src.domain.entities.tenant import Tenant
from src.domain.entities.user import User


class ITenantRepository(Protocol):
    async def get(self, tenant_id: UUID) -> Tenant | None:
        ...

    async def create(self, tenant: Tenant) -> Tenant:
        ...


class IUserRepository(Protocol):
    async def get(self, user_id: UUID) -> User | None:
        ...

    async def get_by_email(self, email: str) -> User | None:
        """Resolve a login's subject. Email is globally unique, so this needs no tenant."""
        ...

    async def create(self, user: User) -> User:
        ...


class IRefreshTokenRepository(Protocol):
    async def create(self, token: RefreshToken) -> RefreshToken:
        ...

    async def get_by_hash(self, token_hash: str) -> RefreshToken | None:
        ...

    async def revoke(self, token_id: UUID) -> None:
        ...

    async def revoke_family(self, family_id: UUID) -> None:
        """Revoke every token in a family — used on logout and on refresh-reuse detection."""
        ...


class IKnowledgeBaseRepository(Protocol):
    async def get_default(self) -> KnowledgeBase | None:
        ...

    async def ensure_default(self) -> KnowledgeBase:
        ...


class IDocumentRepository(Protocol):
    async def list_current(self, knowledge_base_id: UUID) -> list[KnowledgeAsset]:
        ...

    async def get(self, asset_id: UUID) -> KnowledgeAsset | None:
        ...

    async def latest_for_filename(self, knowledge_base_id: UUID, filename: str) -> KnowledgeAsset | None:
        ...

    async def create_pending(self, asset: KnowledgeAsset) -> KnowledgeAsset:
        ...

    async def update_from_domain(self, asset: KnowledgeAsset) -> KnowledgeAsset:
        ...

    async def rename(self, asset_id: UUID, title: str) -> KnowledgeAsset:
        ...

    async def supersede_previous_versions(self, lineage_id: UUID, active_asset_id: UUID) -> None:
        ...

    async def delete(self, asset_id: UUID) -> None:
        ...


class IIngestionJobRepository(Protocol):
    """Persistence for the domain-level ingestion job record."""

    async def create(self, job: IngestionJob) -> IngestionJob:
        ...

    async def get(self, job_id: UUID) -> IngestionJob | None:
        ...

    async def latest_for_asset(self, asset_id: UUID) -> IngestionJob | None:
        ...

    async def list_recent(self, limit: int = 50) -> list[IngestionJob]:
        """Most-recent jobs across all assets, for the monitoring dashboard."""
        ...

    async def mark_running(self, job_id: UUID) -> IngestionJob:
        """Flip to RUNNING, stamp started_at, and increment the attempt counter."""
        ...

    async def mark_succeeded(self, job_id: UUID) -> IngestionJob:
        ...

    async def mark_failed(self, job_id: UUID, error: str) -> IngestionJob:
        """Record a terminal failure with its error message."""
        ...

    async def reset_for_retry(self, job_id: UUID) -> IngestionJob:
        """Return a failed job to QUEUED so it can be deferred again."""
        ...


class IIngestionJobEventRepository(Protocol):
    """Append-only worker log: the durable per-asset ingestion event trail."""

    async def append(self, event: JobEvent) -> JobEvent:
        """Persist one event. Best-effort — callers treat logging as non-fatal."""
        ...

    async def list_for_asset(self, asset_id: UUID, limit: int = 200) -> list[JobEvent]:
        """Chronological events for an asset (what the dashboard expands)."""
        ...

    async def list_for_job(self, job_id: UUID) -> list[JobEvent]:
        ...


class IChunkRepository(Protocol):
    async def replace_for_asset(self, asset_id: UUID, chunks: list[Chunk]) -> list[Chunk]:
        ...

    async def list_for_asset(self, asset_id: UUID) -> list[Chunk]:
        """Leaves only — the passages a reader sees and a citation points at."""
        ...

    async def list_all_for_asset(self, asset_id: UUID) -> list[Chunk]:
        """Every chunk including parent sections — for a pipeline resuming after chunking."""
        ...

    async def list_parents(self, parent_ids: list[UUID]) -> dict[UUID, Chunk]:
        """Parent sections keyed by id, for expanding matched children before generation."""
        ...

    async def count_by_asset(self, asset_ids: list[UUID]) -> dict[UUID, int]:
        """Leaf counts per asset, for the library list."""
        ...


class IEmbeddingRepository(Protocol):
    async def replace_for_chunks(self, chunks: list[Chunk], embeddings: list[Embedding]) -> None:
        ...


class IChunkSignalRepository(Protocol):
    """Accumulated per-passage outcomes, behind the learned relevance prior."""

    async def record(self, events: list[ChunkSignalEvent]) -> None:
        """Fold one answer's outcomes into the counters. Increments, not absolute values."""
        ...

    async def apply_feedback(
        self, chunk_ids: list[UUID], *, previous: int | None, current: int | None
    ) -> None:
        """Move vote counters by the difference between two verdicts, so a change of mind
        is exactly reversible."""
        ...

    async def priors(self, chunk_ids: list[UUID]) -> dict[str, ChunkSignal]:
        """Signals for a retrieval pool, keyed by `str(chunk_id)` to match Document metadata."""
        ...
