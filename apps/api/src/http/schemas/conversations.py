from __future__ import annotations

from datetime import datetime
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel


class MessageSchema(BaseModel):
    id: UUID
    role: str
    content: str
    citations: list[dict[str, Any]]
    trace: dict[str, Any] | None = None
    grounding: dict[str, Any] | None = None
    feedback: int | None = None
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
    #: The knowledge bases to answer from. Omitted means "whatever this thread is already
    #: attached to", and for a new thread the workspace default — so a client that predates
    #: the switcher keeps working unchanged.
    knowledge_base_ids: list[UUID] | None = None


class FeedbackRequest(BaseModel):
    """`Literal[-1, 1]` so anything else is a 422 from validation, before the handler runs."""

    rating: Literal[-1, 1]


class FeedbackSchema(BaseModel):
    rating: int | None = None
