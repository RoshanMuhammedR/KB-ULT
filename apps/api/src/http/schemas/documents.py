from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel


class IngestionJobSchema(BaseModel):
    """Latest ingestion job for an asset — what the frontend polls for retry state."""

    status: str
    attempts: int
    max_attempts: int
    last_error: str | None = None


class KnowledgeAssetSchema(BaseModel):
    id: UUID
    knowledge_base_id: UUID
    lineage_id: UUID
    version: int
    filename: str
    title: str | None
    source_type: str
    storage_key: str
    download_url: str | None = None
    status: str
    failed_step: str | None
    error_message: str | None
    metadata: dict[str, Any]
    # Present on single-asset reads so the UI can show attempt count / queue state.
    job: IngestionJobSchema | None = None
    superseded_at: datetime | None
    created_at: datetime | None
    updated_at: datetime | None


class RenameKnowledgeAssetRequest(BaseModel):
    title: str
