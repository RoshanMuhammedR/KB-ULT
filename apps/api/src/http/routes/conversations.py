from __future__ import annotations

import json
from typing import Annotated, Iterator
from uuid import UUID

import structlog
from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from src.composition import build_chat_service
from src.core.config import Settings, get_settings
from src.core.identity import Identity
from src.core.tenant_context import reset_tenant_context, set_tenant_context
from src.http.dependencies import get_current_identity
from src.http.schemas.conversations import (
    AskRequest,
    ConversationSchema,
    ConversationSummarySchema,
    MessageSchema,
    RenameConversationRequest,
)
from src.infrastructure.database.session import get_db, session_scope
from src.infrastructure.repositories import ConversationRepository, KnowledgeBaseRepository

logger = structlog.get_logger(__name__)

router = APIRouter(prefix="/conversations", tags=["conversations"])

# `POST /conversations/new/messages` starts a thread, so the client needs no separate
# "create conversation" call before it can ask its first question.
NEW_CONVERSATION = "new"

# Streaming responses must not be buffered anywhere between the model and the browser,
# or the whole point (a visibly progressing answer) is lost. Caddy's reverse_proxy does
# not buffer by default; X-Accel-Buffering covers an nginx sitting in front.
_SSE_HEADERS = {
    "Cache-Control": "no-cache",
    "Connection": "keep-alive",
    "X-Accel-Buffering": "no",
}


def _message_schema(message) -> MessageSchema:
    return MessageSchema(
        id=message.id,
        role=message.role.value,
        content=message.content,
        citations=message.citations,
        insufficient_context=message.insufficient_context,
        created_at=message.created_at,
    )


@router.get("", response_model=list[ConversationSummarySchema])
def list_conversations(
    db: Annotated[Session, Depends(get_db)],
) -> list[ConversationSummarySchema]:
    kb = KnowledgeBaseRepository(db).ensure_default()
    rows = ConversationRepository(db).list_for_knowledge_base(kb.id)
    return [
        ConversationSummarySchema(
            id=conversation.id,
            title=conversation.title,
            message_count=message_count,
            preview=preview,
            created_at=conversation.created_at,
            updated_at=conversation.updated_at,
        )
        for conversation, message_count, preview in rows
    ]


@router.get("/{conversation_id}", response_model=ConversationSchema)
def get_conversation(
    conversation_id: UUID,
    db: Annotated[Session, Depends(get_db)],
) -> ConversationSchema:
    conversation = ConversationRepository(db).get_with_messages(conversation_id)
    if conversation is None:
        raise HTTPException(status_code=404, detail="Conversation not found")
    return ConversationSchema(
        id=conversation.id,
        title=conversation.title,
        messages=[_message_schema(message) for message in conversation.messages],
        created_at=conversation.created_at,
        updated_at=conversation.updated_at,
    )


@router.patch("/{conversation_id}", response_model=ConversationSchema)
def rename_conversation(
    conversation_id: UUID,
    request: RenameConversationRequest,
    db: Annotated[Session, Depends(get_db)],
) -> ConversationSchema:
    repo = ConversationRepository(db)
    try:
        repo.rename(conversation_id, request.title)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return get_conversation(conversation_id, db)


@router.delete("/{conversation_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_conversation(
    conversation_id: UUID,
    db: Annotated[Session, Depends(get_db)],
) -> None:
    try:
        ConversationRepository(db).delete(conversation_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.delete(
    "/{conversation_id}/messages/{message_id}", status_code=status.HTTP_204_NO_CONTENT
)
def delete_message(
    conversation_id: UUID,
    message_id: UUID,
    db: Annotated[Session, Depends(get_db)],
) -> None:
    try:
        ConversationRepository(db).delete_message(conversation_id, message_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/{conversation_id}/messages")
def ask_in_conversation(
    conversation_id: str,
    request: AskRequest,
    identity: Annotated[Identity, Depends(get_current_identity)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> StreamingResponse:
    """Ask a question and stream the answer back as Server-Sent Events.

    Deliberately does **not** take the request-scoped `get_db` session. A yield-dependency's
    lifetime and a streaming response body are exactly the case where the session can be
    closed out from under the generator, so the generator opens its own `session_scope()`
    instead — the same pattern the ingestion worker uses — and rebinds the tenant context
    inside the thread Starlette runs it on.
    """
    question = request.question.strip()
    if not question:
        raise HTTPException(status_code=422, detail="A question is required")

    if conversation_id == NEW_CONVERSATION:
        target: UUID | None = None
    else:
        try:
            target = UUID(conversation_id)
        except ValueError as exc:
            raise HTTPException(status_code=404, detail="Conversation not found") from exc

    tenant_id = identity.tenant_id
    user_id = identity.user_id

    def events() -> Iterator[str]:
        token = set_tenant_context(tenant_id, user_id)
        try:
            with session_scope() as db:
                chat_service = build_chat_service(db, settings)
                try:
                    for event, payload in chat_service.ask_stream(target, question):
                        yield _frame(event, payload)
                except ValueError as exc:
                    # A bad conversation id — the only client-caused failure down here.
                    yield _frame("error", {"message": str(exc)})
                except Exception as exc:  # noqa: BLE001 - the stream is the only channel left
                    # Headers are long gone by now, so an error can only be delivered as an
                    # event. Nothing was persisted, which is what the client tells the user.
                    logger.exception("chat_stream_failed", error=str(exc))
                    yield _frame(
                        "error",
                        {
                            "message": (
                                "The answer stopped partway through. Nothing was saved, so "
                                "you can ask it again as-is."
                            )
                        },
                    )
        finally:
            reset_tenant_context(token)

    return StreamingResponse(events(), media_type="text/event-stream", headers=_SSE_HEADERS)


def _frame(event: str, payload: object) -> str:
    return f"event: {event}\ndata: {json.dumps(payload)}\n\n"
