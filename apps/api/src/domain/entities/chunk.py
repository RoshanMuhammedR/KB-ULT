from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum
from uuid import UUID, uuid4

from src.domain.entities.knowledge_asset import KnowledgeAsset


class ChunkModality(StrEnum):
    """How the text was produced, which is what decides how much to trust it.

    Coarser than `SourceType` on purpose: retrieval does not care whether a transcript came
    from an uploaded file or from YouTube, it cares that ASR output is noisier than typed
    prose and should clear a higher bar before it is cited.
    """

    TEXT = "text"      # authored prose: markdown, pptx notes
    PDF = "pdf"        # extracted from a page layout - mostly faithful
    ASR = "asr"        # speech recognition - misspells names, drops punctuation
    OCR = "ocr"        # character recognition - reserved; nothing emits it yet


@dataclass(slots=True)
class Chunk:
    id: UUID = field(default_factory=uuid4)
    knowledge_asset_id: UUID | None = None
    chunk_index: int = 0
    text: str = ""
    metadata: dict = field(default_factory=dict)
    created_at: datetime | None = None

    #: The section this chunk was split out of. Retrieval matches the small child (precise),
    #: then expands to the parent before generation (enough context to answer from). A
    #: parent row has `parent_id is None` and is never itself embedded.
    parent_id: UUID | None = None

    #: What gets embedded: the chunk text prefixed with a short description of the section
    #: it belongs to, so a chunk that reads as a fragment on its own still retrieves.
    #: `text` stays exactly what the user sees and what gets cited. Empty means "embed
    #: `text` as-is" - true for parents and for anything ingested before enrichment.
    embed_text: str = ""

    #: See `ChunkModality`. Stored per chunk rather than derived from the asset so the
    #: retrieval filter needs no join.
    modality: str = ChunkModality.TEXT.value

    @property
    def is_parent(self) -> bool:
        return self.parent_id is None

    @property
    def text_for_embedding(self) -> str:
        return self.embed_text or self.text


@dataclass(slots=True)
class Embedding:
    id: UUID = field(default_factory=uuid4)
    chunk_id: UUID | None = None
    vector: list[float] = field(default_factory=list)
    model: str = ""
    dimensions: int = 0
    created_at: datetime | None = None


@dataclass(slots=True)
class RetrievalResult:
    chunk: Chunk
    asset: KnowledgeAsset
    score: float
