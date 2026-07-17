from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel


class JobSummarySchema(BaseModel):
    """A row in the /jobs dashboard: one ingestion job plus its asset's filename."""

    id: UUID
    asset_id: UUID
    filename: str
    status: str
    attempts: int
    max_attempts: int
    last_error: str | None = None
    scheduled_at: datetime | None = None
    started_at: datetime | None = None
    finished_at: datetime | None = None
    created_at: datetime | None = None


class JobEventSchema(BaseModel):
    """One line of the persisted worker log (see JobEvent entity)."""

    id: UUID
    event: str
    level: str
    message: str | None = None
    data: dict[str, Any]
    ts: datetime | None = None
