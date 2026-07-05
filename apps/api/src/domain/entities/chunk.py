from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from uuid import UUID, uuid4

from src.domain.entities.knowledge_asset import KnowledgeAsset


@dataclass(slots=True)
class Chunk:
    id: UUID = field(default_factory=uuid4)
    knowledge_asset_id: UUID | None = None
    chunk_index: int = 0
    text: str = ""
    metadata: dict = field(default_factory=dict)
    created_at: datetime | None = None


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
