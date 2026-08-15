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
    # Display shape ("paged" | "timeline" | "text") — the viewer switches on this and never
    # branches on `source_type`, so a new format needs no frontend change.
    canonical_shape: str = "text"
    # 0 means no rendition has been built; page images live under this version in the object
    # key, so coordinates and images can never fall out of sync.
    render_version: int = 0
    # {"pages": [{"n", "w", "h", "ext"}]} once a rendition exists, else null.
    page_manifest: dict[str, Any] | None = None
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
    # Optional geometry, present only when the pipeline recovered it for this passage.
    # `regions` is [{page, rects[[x0,y0,x1,y1]]}] when paged, [{start, end}] when timeline;
    # both in normalized units so the client multiplies by whatever size it rendered at.
    shape: str | None = None
    regions: list[dict[str, Any]] | None = None


class RenderedPageSchema(BaseModel):
    """A signed URL for one rendered page, with the page's own size in points.

    Size travels with the URL so the viewer can lay out and position highlights before the
    image has loaded — no layout shift when it arrives.
    """

    page: int
    url: str
    width: float
    height: float


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
