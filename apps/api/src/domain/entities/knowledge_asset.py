from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum
from typing import Any
from uuid import UUID, uuid4


class AssetStatus(StrEnum):
    PENDING = "pending"
    EXTRACTING = "extracting"
    CHUNKING = "chunking"
    EMBEDDING = "embedding"
    READY = "ready"
    FAILED = "failed"


@dataclass(slots=True)
class KnowledgeAsset:
    id: UUID = field(default_factory=uuid4)
    knowledge_base_id: UUID | None = None
    lineage_id: UUID = field(default_factory=uuid4)
    version: int = 1
    filename: str = ""
    title: str | None = None
    source_type: str = "pdf"
    storage_key: str = ""
    status: AssetStatus = AssetStatus.PENDING
    failed_step: str | None = None
    error_message: str | None = None
    text_content: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)
    superseded_at: datetime | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None

    @property
    def is_current(self) -> bool:
        return self.superseded_at is None and self.status == AssetStatus.READY
