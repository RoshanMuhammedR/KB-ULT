from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from src.http.schemas.jobs import JobSummarySchema
from src.infrastructure.database.session import get_db
from src.infrastructure.repositories import IngestionJobRepository, KnowledgeAssetRepository

router = APIRouter(prefix="/jobs", tags=["jobs"])


@router.get("", response_model=list[JobSummarySchema])
def list_jobs(db: Annotated[Session, Depends(get_db)]) -> list[JobSummarySchema]:
    # Recent ingestion jobs for the monitoring dashboard, each joined to its asset's
    # filename. The N asset lookups are bounded by the small `list_recent` limit.
    jobs = IngestionJobRepository(db).list_recent()
    asset_repo = KnowledgeAssetRepository(db)
    summaries: list[JobSummarySchema] = []
    for job in jobs:
        asset = asset_repo.get(job.asset_id)
        summaries.append(
            JobSummarySchema(
                id=job.id,
                asset_id=job.asset_id,
                filename=asset.filename if asset else "(deleted)",
                status=job.status.value,
                attempts=job.attempts,
                max_attempts=job.max_attempts,
                last_error=job.last_error,
                scheduled_at=job.scheduled_at,
                started_at=job.started_at,
                finished_at=job.finished_at,
                created_at=job.created_at,
            )
        )
    return summaries
