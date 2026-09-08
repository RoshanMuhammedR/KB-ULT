from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel


class MemorySchema(BaseModel):
    id: UUID
    content: str
    kind: str
    #: Where it was learned, so the UI can link to the conversation. Null when the source
    #: thread has been deleted (the FK is SET NULL — losing the thread must not erase the
    #: fact) or when the user added the memory by hand.
    source_conversation_id: UUID | None = None
    #: Set on a memory that has been corrected. Kept rather than deleted, so "why did it
    #: think that?" has an answer.
    superseded_at: datetime | None = None
    last_used_at: datetime | None = None
    created_at: datetime | None = None


class MemoryStatusSchema(BaseModel):
    """Whether stored memories actually reach an answer.

    Exists because they did not, for the entire life of the feature so far, while every other
    endpoint here behaved normally. The page needs one honest bit to render against.
    """

    enabled: bool
