from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from uuid import UUID, uuid4


@dataclass(slots=True)
class KnowledgeBase:
    id: UUID = field(default_factory=uuid4)
    name: str = "Default Knowledge Base"
    owner_id: str | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None
