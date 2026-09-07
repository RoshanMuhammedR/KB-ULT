from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from uuid import UUID, uuid4


class MemoryKind(StrEnum):
    """What a memory is, which decides who it applies to.

    A `FACT` describes the workspace and is shared with everyone in it. A `PREFERENCE` is one
    person's stated way of being answered ("keep it short"), and forcing it on a teammate
    would be wrong — so the read path filters preferences to their author. That distinction
    changes nothing today, with one user per tenant, and is correct the moment there are two.
    """

    FACT = "fact"
    PREFERENCE = "preference"


@dataclass(slots=True)
class Memory:
    knowledge_base_id: UUID | None = None
    content: str = ""
    kind: MemoryKind = MemoryKind.FACT
    id: UUID = None  # type: ignore[assignment]
    source_conversation_id: UUID | None = None
    source_message_id: UUID | None = None
    superseded_by: UUID | None = None
    superseded_at: datetime | None = None
    last_used_at: datetime | None = None
    created_at: datetime | None = None

    def __post_init__(self) -> None:
        if self.id is None:
            self.id = uuid4()

    @property
    def active(self) -> bool:
        """Currently believed. A superseded memory is kept for the record, never injected."""
        return self.superseded_at is None
