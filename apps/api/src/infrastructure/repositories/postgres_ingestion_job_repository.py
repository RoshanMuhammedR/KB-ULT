from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.text import sanitize_text_for_storage
from src.domain.entities import IngestionJob, JobStatus
from src.infrastructure.database.models import IngestionJobModel
from src.infrastructure.repositories.mappers import job_to_domain
from src.infrastructure.repositories.unit_of_work import commit_or_flush


class IngestionJobRepository:
    """Postgres persistence for the domain-level ingestion job record.

    Mirrors the commit/rollback discipline used by KnowledgeAssetRepository so a
    failed flush never leaves the session in an unusable state.
    """

    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def create(self, job: IngestionJob) -> IngestionJob:
        model = IngestionJobModel(
            id=job.id,
            asset_id=job.asset_id,
            job_type=job.job_type,
            status=job.status.value,
            attempts=job.attempts,
            max_attempts=job.max_attempts,
            last_error=job.last_error,
            scheduled_at=job.scheduled_at,
        )
        self.db.add(model)
        await self._commit()
        await self.db.refresh(model)
        return job_to_domain(model)

    async def get(self, job_id: UUID) -> IngestionJob | None:
        # select().where(pk), not Session.get(): Session.get() bypasses the tenant filter.
        model = await self.db.scalar(select(IngestionJobModel).where(IngestionJobModel.id == job_id))
        return job_to_domain(model) if model else None

    async def latest_for_asset(self, asset_id: UUID) -> IngestionJob | None:
        model = await self.db.scalar(
            select(IngestionJobModel)
            .where(IngestionJobModel.asset_id == asset_id)
            .order_by(desc(IngestionJobModel.created_at))
            .limit(1)
        )
        return job_to_domain(model) if model else None

    async def list_recent(self, limit: int = 50) -> list[IngestionJob]:
        # Newest jobs for the current tenant — powers the /jobs dashboard. The tenant
        # auto-filter scopes this select (IngestionJobModel is TenantScoped), so it no
        # longer spans all tenants.
        models = (await self.db.scalars(
            select(IngestionJobModel).order_by(desc(IngestionJobModel.created_at)).limit(limit)
        )).all()
        return [job_to_domain(model) for model in models]

    async def mark_running(self, job_id: UUID) -> IngestionJob:
        # A new attempt begins: bump the counter and stamp the start time.
        model = await self._require(job_id)
        model.status = JobStatus.RUNNING.value
        model.attempts += 1
        model.started_at = datetime.now(UTC)
        model.finished_at = None
        model.last_error = None
        await self._commit()
        await self.db.refresh(model)
        return job_to_domain(model)

    async def mark_succeeded(self, job_id: UUID) -> IngestionJob:
        model = await self._require(job_id)
        model.status = JobStatus.SUCCEEDED.value
        model.finished_at = datetime.now(UTC)
        model.last_error = None
        await self._commit()
        await self.db.refresh(model)
        return job_to_domain(model)

    async def mark_failed(self, job_id: UUID, error: str) -> IngestionJob:
        model = await self._require(job_id)
        model.status = JobStatus.FAILED.value
        model.finished_at = datetime.now(UTC)
        # Error text can contain arbitrary parser output; sanitize before it hits the DB.
        model.last_error = sanitize_text_for_storage(error)
        await self._commit()
        await self.db.refresh(model)
        return job_to_domain(model)

    async def reset_for_retry(self, job_id: UUID) -> IngestionJob:
        # Return a failed job to the queue-ready state; attempts are preserved so
        # the retry budget keeps accumulating across manual retries.
        model = await self._require(job_id)
        model.status = JobStatus.QUEUED.value
        model.started_at = None
        model.finished_at = None
        model.last_error = None
        model.scheduled_at = datetime.now(UTC)
        await self._commit()
        await self.db.refresh(model)
        return job_to_domain(model)

    async def _require(self, job_id: UUID) -> IngestionJobModel:
        # select().where(pk), not Session.get(): keep the tenant filter in force.
        model = await self.db.scalar(select(IngestionJobModel).where(IngestionJobModel.id == job_id))
        if model is None:
            raise ValueError(f"IngestionJob not found: {job_id}")
        return model

    async def _commit(self) -> None:
        # Commits on its own, unless the caller opened a `unit_of_work` — then this
        # flushes and the enclosing scope owns the single COMMIT. See unit_of_work.py.
        await commit_or_flush(self.db)
