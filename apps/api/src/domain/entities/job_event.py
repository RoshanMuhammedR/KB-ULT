from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any
from uuid import UUID, uuid4


@dataclass(slots=True)
class JobEvent:
    """One persisted line in the ingestion worker log for an asset/job.

    The worker's structlog output is stdout-only and ephemeral. This is the durable,
    queryable counterpart: one row per pipeline transition or terminal state, written
    explicitly at each step (not scraped from the logger). It is what the `/jobs`
    dashboard reads to show what a worker did and when.

    `job_id` is nullable because an event can predate/outlive a specific job row, but
    `asset_id` is always present so the trail is retrievable per asset. `data` holds
    small structured extras (e.g. chunk_count) that don't deserve their own columns.
    """

    id: UUID = field(default_factory=uuid4)
    asset_id: UUID | None = None
    job_id: UUID | None = None
    level: str = "info"
    event: str = ""
    message: str | None = None
    data: dict[str, Any] = field(default_factory=dict)
    ts: datetime | None = None
