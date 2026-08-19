from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from src.domain.entities import JobStatus
from src.http.schemas.jobs import JobSummarySchema
from src.infrastructure.database.session import get_db
from src.infrastructure.repositories import IngestionJobRepository, KnowledgeAssetRepository

router = APIRouter(prefix="/jobs", tags=["jobs"])


@router.get("", response_model=list[JobSummarySchema])
def list_jobs(db: Annotated[Session, Depends(get_db)]) -> list[JobSummarySchema]:
    # Recent ingestion jobs for the monitoring dashboard, each joined to its asset's
    # filename. The filenames come back in ONE query rather than one per job: the row count
    # is bounded by `list_recent`, but an N+1 that is small today is still an N+1.
    jobs = IngestionJobRepository(db).list_recent()
    assets = KnowledgeAssetRepository(db).get_many(job.asset_id for job in jobs if job.asset_id)
    return [
        JobSummarySchema(
            id=job.id,
            asset_id=job.asset_id,
            filename=assets[job.asset_id].filename if job.asset_id in assets else "(deleted)",
            status=job.status.value,
            attempts=job.attempts,
            max_attempts=job.max_attempts,
            # FAILED means "this attempt failed"; the queue keeps re-scheduling until the
            # attempts run out. Only then is the job actually stuck. See the dead_letter
            # event written by IngestionService.process_ingestion.
            exhausted=job.status == JobStatus.FAILED and job.attempts >= job.max_attempts,
            last_error=job.last_error,
            scheduled_at=job.scheduled_at,
            started_at=job.started_at,
            finished_at=job.finished_at,
            created_at=job.created_at,
        )
        for job in jobs
    ]
