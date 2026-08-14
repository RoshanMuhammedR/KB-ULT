from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel


class MessageSchema(BaseModel):
    id: UUID
    role: str
    content: str
    citations: list[dict[str, Any]]
    insufficient_context: bool
    created_at: datetime | None


class ConversationSummarySchema(BaseModel):
    """List view — enough to recognise a thread without loading it."""

    id: UUID
    title: str
    message_count: int
    preview: str
    created_at: datetime | None
    updated_at: datetime | None


class ConversationSchema(BaseModel):
    id: UUID
    title: str
    messages: list[MessageSchema]
    created_at: datetime | None
    updated_at: datetime | None


class RenameConversationRequest(BaseModel):
    title: str


class AskRequest(BaseModel):
    question: str
