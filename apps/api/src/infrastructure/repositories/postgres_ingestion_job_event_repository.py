from __future__ import annotations

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from src.core.text import sanitize_text_for_storage
from src.domain.entities import JobEvent
from src.infrastructure.database.models import IngestionJobEventModel
from src.infrastructure.repositories.mappers import event_to_domain


class IngestionJobEventRepository:
    """Append-only persistence for the ingestion worker log.

    Same commit/rollback discipline as the other repositories so a failed insert never
    leaves the Session unusable. Callers treat logging as best-effort — a failure to
    persist an event must not break ingestion — so they wrap `append` in try/except.
    """

    def __init__(self, db: Session) -> None:
        self.db = db

    def append(self, event: JobEvent) -> JobEvent:
        model = IngestionJobEventModel(
            id=event.id,
            asset_id=event.asset_id,
            job_id=event.job_id,
            level=event.level,
            event=event.event,
            # Messages can carry arbitrary parser/error text; sanitize before the DB.
            message=sanitize_text_for_storage(event.message) if event.message else None,
            data_=event.data or {},
        )
        self.db.add(model)
        self._commit()
        self.db.refresh(model)
        return event_to_domain(model)

    def list_for_asset(self, asset_id: UUID, limit: int = 200) -> list[JobEvent]:
        models = self.db.scalars(
            select(IngestionJobEventModel)
            .where(IngestionJobEventModel.asset_id == asset_id)
            .order_by(IngestionJobEventModel.ts.asc())
            .limit(limit)
        ).all()
        return [event_to_domain(model) for model in models]

    def list_for_job(self, job_id: UUID) -> list[JobEvent]:
        models = self.db.scalars(
            select(IngestionJobEventModel)
            .where(IngestionJobEventModel.job_id == job_id)
            .order_by(IngestionJobEventModel.ts.asc())
        ).all()
        return [event_to_domain(model) for model in models]

    def _commit(self) -> None:
        try:
            self.db.commit()
        except Exception:
            self.db.rollback()
            raise
