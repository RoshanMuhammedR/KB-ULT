from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field


class KnowledgeBaseSchema(BaseModel):
    id: UUID
    name: str
    created_at: datetime | None = None
    #: How much is in it. Shown on the switcher so a base is recognisable by its contents
    #: rather than only by a name someone typed once.
    source_count: int = 0


class CreateKnowledgeBaseRequest(BaseModel):
    name: str = Field(min_length=1, max_length=120)


class RenameKnowledgeBaseRequest(BaseModel):
    name: str = Field(min_length=1, max_length=120)
