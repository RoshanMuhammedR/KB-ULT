from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel


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
    superseded_at: datetime | None
    created_at: datetime | None
    updated_at: datetime | None


class RenameKnowledgeAssetRequest(BaseModel):
    title: str
