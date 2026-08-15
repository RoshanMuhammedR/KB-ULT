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
    # Audio sources only: a presigned URL for the readable transcript.md written beside
    # the original during ingestion.
    transcript_url: str | None = None
    status: str
    failed_step: str | None
    error_message: str | None
    metadata: dict[str, Any]
    # How many indexed passages this source contributes — i.e. how much of it is usable.
    passage_count: int = 0
    # Present on single-asset reads so the UI can show attempt count / queue state.
    job: IngestionJobSchema | None = None
    superseded_at: datetime | None
    created_at: datetime | None
    updated_at: datetime | None


class PassageSchema(BaseModel):
    """One indexed passage — the unit of both retrieval and citation."""

    chunk_index: int
    text: str
    locator: dict[str, Any] | None = None


class AssetCitationSchema(BaseModel):
    """An answer that cited this source, for the "answers that cited this" panel."""

    conversation_id: UUID
    conversation_title: str
    locator: dict[str, Any] | None = None
    chunk_index: int | None = None
    score: float | None = None
    excerpt: str | None = None


class RenameKnowledgeAssetRequest(BaseModel):
    title: str


class IngestUrlRequest(BaseModel):
    """Ingest a URL-based source (e.g. a YouTube video) — no file upload."""

    url: str
