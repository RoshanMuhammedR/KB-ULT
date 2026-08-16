from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum
from typing import Any
from uuid import UUID, uuid4

from langchain_core.documents import Document


class AssetStatus(StrEnum):
    PENDING = "pending"
    # Accepted and waiting for a worker to pick up its ingestion job. This is the
    # state an asset is left in by the (fast) upload request, before the (slow)
    # extract/chunk/embed pipeline runs asynchronously in a worker.
    QUEUED = "queued"
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
    # The parsed source, normalized by its handler into LangChain `Document`s: one per
    # natural unit of the source (a PDF page, a Markdown section, a slide, a transcript
    # window), each carrying a typed `metadata["locator"]` saying where it came from.
    #
    # This is the handoff between parsing and chunking, and it is deliberately typed state
    # rather than a key in the untyped `metadata` bag: the chunker splits these to the
    # embedding model's token budget while copying each one's locator onto every piece, so
    # a citation can always point back at a page/timestamp/slide.
    #
    # Persisted (see the `documents` JSONB column) because a retry that resumes at the
    # chunking step re-reads them instead of re-parsing the source.
    documents: list[Document] = field(default_factory=list)
    superseded_at: datetime | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None

    @property
    def is_current(self) -> bool:
        return self.superseded_at is None and self.status == AssetStatus.READY
