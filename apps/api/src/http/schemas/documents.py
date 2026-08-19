from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field


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


class UploadUrlRequest(BaseModel):
    """Ask for somewhere to PUT a file, before sending any of it."""

    filename: str = Field(min_length=1, max_length=512)
    content_type: str | None = Field(default=None, max_length=255)
    # What the client says it is about to send, so a file over the limit is refused before
    # it is uploaded rather than after. Verified against the stored object on completion.
    size_bytes: int | None = Field(default=None, ge=0)


class UploadUrlResponse(BaseModel):
    """Where to PUT the file, and the id to report back with once it is there."""

    asset_id: UUID
    upload_url: str
    storage_key: str
    expires_in_seconds: int
    # Echoed back because the signature covers it: the PUT must send this exact header or
    # object storage rejects it.
    content_type: str


class CompleteUploadRequest(BaseModel):
    """Tell the API the direct upload finished, so it can record and queue the source."""

    filename: str = Field(min_length=1, max_length=512)
    content_type: str | None = Field(default=None, max_length=255)
