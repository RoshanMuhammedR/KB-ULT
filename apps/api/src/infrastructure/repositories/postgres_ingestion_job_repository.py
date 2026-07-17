from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import desc, select
from sqlalchemy.orm import Session

from src.core.text import sanitize_text_for_storage
from src.domain.entities import IngestionJob, JobStatus
from src.infrastructure.database.models import IngestionJobModel
from src.infrastructure.repositories.mappers import job_to_domain


class IngestionJobRepository:
    """Postgres persistence for the domain-level ingestion job record.

    Mirrors the commit/rollback discipline used by KnowledgeAssetRepository so a
    failed flush never leaves the session in an unusable state.
    """

    def __init__(self, db: Session) -> None:
        self.db = db

    def create(self, job: IngestionJob) -> IngestionJob:
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
        self._commit()
        self.db.refresh(model)
        return job_to_domain(model)

    def get(self, job_id: UUID) -> IngestionJob | None:
        model = self.db.get(IngestionJobModel, job_id)
        return job_to_domain(model) if model else None

    def latest_for_asset(self, asset_id: UUID) -> IngestionJob | None:
        model = self.db.scalar(
            select(IngestionJobModel)
            .where(IngestionJobModel.asset_id == asset_id)
            .order_by(desc(IngestionJobModel.created_at))
            .limit(1)
        )
        return job_to_domain(model) if model else None

    def list_recent(self, limit: int = 50) -> list[IngestionJob]:
        # Newest jobs across all assets — powers the /jobs monitoring dashboard.
        models = self.db.scalars(
            select(IngestionJobModel).order_by(desc(IngestionJobModel.created_at)).limit(limit)
        ).all()
        return [job_to_domain(model) for model in models]

    def mark_running(self, job_id: UUID) -> IngestionJob:
        # A new attempt begins: bump the counter and stamp the start time.
        model = self._require(job_id)
        model.status = JobStatus.RUNNING.value
        model.attempts += 1
        model.started_at = datetime.now(UTC)
        model.finished_at = None
        model.last_error = None
        self._commit()
        self.db.refresh(model)
        return job_to_domain(model)

    def mark_succeeded(self, job_id: UUID) -> IngestionJob:
        model = self._require(job_id)
        model.status = JobStatus.SUCCEEDED.value
        model.finished_at = datetime.now(UTC)
        model.last_error = None
        self._commit()
        self.db.refresh(model)
        return job_to_domain(model)

    def mark_failed(self, job_id: UUID, error: str) -> IngestionJob:
        model = self._require(job_id)
        model.status = JobStatus.FAILED.value
        model.finished_at = datetime.now(UTC)
        # Error text can contain arbitrary parser output; sanitize before it hits the DB.
        model.last_error = sanitize_text_for_storage(error)
        self._commit()
        self.db.refresh(model)
        return job_to_domain(model)

    def reset_for_retry(self, job_id: UUID) -> IngestionJob:
        # Return a failed job to the queue-ready state; attempts are preserved so
        # the retry budget keeps accumulating across manual retries.
        model = self._require(job_id)
        model.status = JobStatus.QUEUED.value
        model.started_at = None
        model.finished_at = None
        model.last_error = None
        model.scheduled_at = datetime.now(UTC)
        self._commit()
        self.db.refresh(model)
        return job_to_domain(model)

    def _require(self, job_id: UUID) -> IngestionJobModel:
        model = self.db.get(IngestionJobModel, job_id)
        if model is None:
            raise ValueError(f"IngestionJob not found: {job_id}")
        return model

    def _commit(self) -> None:
        try:
            self.db.commit()
        except Exception:
            # A failed flush leaves the Session transaction unusable until rolled back.
            self.db.rollback()
            raise
