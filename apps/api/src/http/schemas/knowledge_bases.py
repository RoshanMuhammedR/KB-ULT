from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel


class KnowledgeBaseSchema(BaseModel):
    id: UUID
    name: str
    owner_id: str | None
    created_at: datetime | None
    updated_at: datetime | None
