from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum
from uuid import UUID, uuid4


class JobStatus(StrEnum):
    # Queue-level lifecycle of a unit of work. This is deliberately coarser than
    # AssetStatus: the asset tracks the *pipeline stage* (extracting/chunking/...),
    # while the job tracks *whether the work ran and how many times we tried*.
    QUEUED = "queued"      # created and handed to the queue, not yet picked up
    RUNNING = "running"    # a worker is currently processing it
    SUCCEEDED = "succeeded"
    FAILED = "failed"      # terminal failure after exhausting retries


@dataclass(slots=True)
class IngestionJob:
    """Domain-owned record of an ingestion unit of work.

    This is intentionally decoupled from the queue engine (Procrastinate). The
    queue keeps its own internal bookkeeping; this entity is what the API and
    frontend read, and it survives a future swap of the queue technology.
    """

    id: UUID = field(default_factory=uuid4)
    asset_id: UUID | None = None
    job_type: str = "ingest_asset"
    status: JobStatus = JobStatus.QUEUED
    attempts: int = 0
    max_attempts: int = 3
    last_error: str | None = None
    scheduled_at: datetime | None = None
    started_at: datetime | None = None
    finished_at: datetime | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None
