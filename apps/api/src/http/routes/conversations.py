from __future__ import annotations

import asyncio
import json
from contextlib import suppress
from collections.abc import AsyncIterator
from typing import Annotated
from uuid import UUID

import structlog
from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from src.composition import build_agentic_chat_service
from src.core.config import Settings, get_settings
from src.core.identity import Identity
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
# Sent when the answer has produced nothing for this long. Comfortably under the 30-60s
# idle timeout typical of proxies and load balancers, and long enough that a normally
# responsive model never triggers it.
_HEARTBEAT_SECONDS = 15.0
_HEARTBEAT_FRAME = ": ping\n\n"
# Sentinel: the producer thread is finished (successfully or not).
_STREAM_DONE = object()

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
        trace=message.trace,
        grounding=message.grounding,
        insufficient_context=message.insufficient_context,
        created_at=message.created_at,
    )


@router.get("", response_model=list[ConversationSummarySchema])
async def list_conversations(
    db: Annotated[AsyncSession, Depends(get_db)],
) -> list[ConversationSummarySchema]:
    kb = await KnowledgeBaseRepository(db).ensure_default()
    rows = await ConversationRepository(db).list_for_knowledge_base(kb.id)
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
async def get_conversation(
    conversation_id: UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> ConversationSchema:
    conversation = await ConversationRepository(db).get_with_messages(conversation_id)
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
async def rename_conversation(
    conversation_id: UUID,
    request: RenameConversationRequest,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> ConversationSchema:
    repo = ConversationRepository(db)
    try:
        await repo.rename(conversation_id, request.title)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return await get_conversation(conversation_id, db)


@router.delete("/{conversation_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_conversation(
    conversation_id: UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> None:
    try:
        await ConversationRepository(db).delete(conversation_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.delete(
    "/{conversation_id}/messages/{message_id}", status_code=status.HTTP_204_NO_CONTENT
)
async def delete_message(
    conversation_id: UUID,
    message_id: UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> None:
    try:
        await ConversationRepository(db).delete_message(conversation_id, message_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/{conversation_id}/messages")
async def ask_in_conversation(
    conversation_id: str,
    request: AskRequest,
    identity: Annotated[Identity, Depends(get_current_identity)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> StreamingResponse:
    """Ask a question and stream the answer back as Server-Sent Events.

    Deliberately does **not** take the request-scoped `get_db` session. A yield-dependency's
    lifetime and a streaming response body are exactly the case where the session can be
    closed out from under the generator, so the generator opens its own `session_scope()`
    instead — the same pattern the ingestion worker uses.

    `identity` is unused in the body, but it is not dead: it keeps this route's
    authentication assertion at the route itself rather than relying solely on the
    middleware's exempt-path list. Leave it.

    Historical note worth keeping. This body used to be a *sync* generator, which Starlette
    drove through `iterate_in_threadpool` — one fresh `copy_context()` per frame. Binding a
    contextvar inside it therefore could not be unbound (`ContextVar.reset` raises across
    contexts), and the failure surfaced as a dead connection after a fully successful
    answer. An async generator runs in one task and one context, so that entire class of
    bug is gone rather than merely avoided.
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

    async def events() -> AsyncIterator[str]:
        async with session_scope() as db:
            chat_service = build_agentic_chat_service(db, settings)
            frames: asyncio.Queue[str | object] = asyncio.Queue()

            async def produce() -> None:
                """Drive the answer, pushing each frame to the consumer below."""
                try:
                    async for event, payload in chat_service.ask_stream(target, question):
                        await frames.put(_frame(event, payload))
                except ValueError as exc:
                    # A bad conversation id — the only client-caused failure down here.
                    await frames.put(_frame("error", {"message": str(exc)}))
                except asyncio.CancelledError:
                    # The client hung up. Nothing to report to a socket that is gone.
                    raise
                except Exception as exc:  # noqa: BLE001 - the stream is the only channel left
                    # Headers are long gone by now, so an error can only be delivered as an
                    # event. The turn is persisted only once the answer is complete, so a
                    # failure here really does leave nothing behind — which is what we
                    # promise the client.
                    logger.exception("chat_stream_failed", error=str(exc))
                    await frames.put(
                        _frame(
                            "error",
                            {
                                "message": (
                                    "The answer stopped partway through. Nothing was "
                                    "saved, so you can ask it again as-is."
                                )
                            },
                        )
                    )
                finally:
                    await frames.put(_STREAM_DONE)

            # The answer runs as its own task so this generator can keep yielding while it
            # works. Nothing is sent between the request and the first token — retrieval, a
            # query embedding, and the model's time-to-first-token — which is long enough
            # for an idle proxy to decide the connection is dead and cut it. A comment frame
            # on a timer keeps bytes flowing through that silent window.
            producer = asyncio.create_task(produce())
            try:
                while True:
                    try:
                        item = await asyncio.wait_for(frames.get(), _HEARTBEAT_SECONDS)
                    except TimeoutError:
                        # An SSE comment: the browser's parser ignores it, and so does the
                        # hand-rolled reader in the web app (a frame with no `data:` line is
                        # dropped). Its only job is to be bytes on the wire.
                        yield _HEARTBEAT_FRAME
                        continue
                    if item is _STREAM_DONE:
                        break
                    yield item  # type: ignore[misc]
            finally:
                # Cancel on client disconnect, then let the task settle before
                # `session_scope` commits — the producer owns the session, and the two must
                # never touch it at the same time.
                producer.cancel()
                with suppress(asyncio.CancelledError):
                    await producer

    return StreamingResponse(events(), media_type="text/event-stream", headers=_SSE_HEADERS)


def _frame(event: str, payload: object) -> str:
    return f"event: {event}\ndata: {json.dumps(payload)}\n\n"
