from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field


class KnowledgeBaseSchema(BaseModel):
    id: UUID
    name: str
    #: What this library is for. A list of bases with only names is one you have to read
    #: rather than recognise.
    description: str | None = None
    #: A colour *token* — "amber", "slate" — never a hex value. What it renders as belongs to
    #: the client and differs between light and dark.
    colour: str | None = None
    created_at: datetime | None = None
    #: How much is in it. Shown on the switcher so a base is recognisable by its contents
    #: rather than only by a name someone typed once.
    source_count: int = 0


class CreateKnowledgeBaseRequest(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    description: str | None = Field(default=None, max_length=500)
    colour: str | None = Field(default=None, max_length=32)


class UpdateKnowledgeBaseRequest(BaseModel):
    """Every field optional: `None` means "leave it alone".

    An empty string is how a description is cleared — otherwise the only way to remove one
    would be a separate route, or overloading `None` to mean two different things.
    """

    name: str | None = Field(default=None, min_length=1, max_length=120)
    description: str | None = Field(default=None, max_length=500)
    colour: str | None = Field(default=None, max_length=32)
