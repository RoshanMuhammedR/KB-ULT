from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from uuid import UUID, uuid4


@dataclass(slots=True)
class KnowledgeBase:
    id: UUID = field(default_factory=uuid4)
    name: str = "Default Knowledge Base"
    #: What this library is for, in the owner's own words. A list of bases with nothing but
    #: names is a list you have to read rather than recognise.
    description: str | None = None
    #: A colour *token* — "amber", "slate" — never a hex value. What it renders as is the
    #: client's business and differs between light and dark.
    colour: str | None = None
    owner_id: str | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None
