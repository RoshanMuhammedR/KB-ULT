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
    FeedbackRequest,
    FeedbackSchema,
    MessageSchema,
    RenameConversationRequest,
)
from src.infrastructure.database.session import get_db, session_scope
from src.domain.entities import MessageRole
from src.infrastructure.repositories import (
    ChunkSignalRepository,
    ConversationRepository,
    MessageFeedbackRepository,
)

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
        feedback=message.feedback,
        insufficient_context=message.insufficient_context,
        created_at=message.created_at,
    )


@router.get("", response_model=list[ConversationSummarySchema])
async def list_conversations(
    db: Annotated[AsyncSession, Depends(get_db)],
    knowledge_base_id: UUID | None = None,
) -> list[ConversationSummarySchema]:
    """Threads started in one base, or every thread in the workspace when none is named.

    Scoped by the base a thread was *started* in rather than by its attachment set: a thread
    should appear in one place in the list, and "started in" is the only answer that stays
    stable when bases are attached and detached later.

    Unnamed means the whole workspace. It used to mean the default base, which quietly hid
    every thread started anywhere else from a client that had not chosen a base yet.
    """
    rows = await ConversationRepository(db).list_for_knowledge_base(knowledge_base_id)
    return [
        ConversationSummarySchema(
            id=conversation.id,
            knowledge_base_id=conversation.knowledge_base_id,
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


async def _assistant_message(db: AsyncSession, conversation_id: UUID, message_id: UUID):
    """The assistant message this feedback is about, or the right HTTP error.

    Filters on *both* ids, like `delete_message`, so a message id from another conversation
    is a 404 rather than a successful write to someone else's thread. A message in another
    tenant is also a 404 and never a 403: the tenant filter makes it invisible, and saying
    "forbidden" would confirm that an id exists.
    """
    conversation = await ConversationRepository(db).get_with_messages(conversation_id)
    if conversation is None:
        raise HTTPException(status_code=404, detail="Conversation not found")

    message = next((m for m in conversation.messages if m.id == message_id), None)
    if message is None:
        raise HTTPException(status_code=404, detail="Message not found")
    if message.role != MessageRole.ASSISTANT:
        # Rating your own question is meaningless, and letting it through would record a
        # verdict against no citations at all.
        raise HTTPException(
            status_code=422, detail="Only an assistant message can be rated"
        )
    return message


def _cited_chunk_ids(message) -> list[UUID]:
    """The passages an answer was built from — what a thumb is really a verdict on.

    A fallback answer cites nothing and therefore moves no counters, which is correct: the
    reader is rating the absence of an answer, not any passage's contribution to one.
    """
    ids = []
    for citation in message.citations or []:
        raw = citation.get("chunk_id")
        if not raw:
            continue
        with suppress(ValueError, AttributeError):
            ids.append(UUID(raw))
    return ids


@router.put("/{conversation_id}/messages/{message_id}/feedback")
async def set_feedback(
    conversation_id: UUID,
    message_id: UUID,
    request: FeedbackRequest,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> FeedbackSchema:
    """Record this reader's verdict on an answer.

    PUT rather than POST because the operation is "this user's verdict is now X", which is
    idempotent by definition — changing your mind is the same call with a different body,
    not a second resource. `rating` is a `Literal[-1, 1]`, so an out-of-range value is a 422
    from validation before this handler runs.
    """
    message = await _assistant_message(db, conversation_id, message_id)

    # The reader's click is the durable thing. It is committed first and on its own, so a
    # failure in the derived counters below can never cost the user their vote.
    previous = await MessageFeedbackRepository(db).set(message_id, request.rating)

    try:
        await ChunkSignalRepository(db).apply_feedback(
            _cited_chunk_ids(message), previous=previous, current=request.rating
        )
    except Exception:  # noqa: BLE001 - a counter that did not move must not fail a 200
        logger.warning("signal_write_failed", message_id=str(message_id))

    return FeedbackSchema(rating=request.rating)


@router.delete(
    "/{conversation_id}/messages/{message_id}/feedback",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def clear_feedback(
    conversation_id: UUID,
    message_id: UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> None:
    """Retract a verdict, returning the counters to exactly where they were before it."""
    message = await _assistant_message(db, conversation_id, message_id)
    previous = await MessageFeedbackRepository(db).clear(message_id)

    try:
        await ChunkSignalRepository(db).apply_feedback(
            _cited_chunk_ids(message), previous=previous, current=None
        )
    except Exception:  # noqa: BLE001
        logger.warning("signal_write_failed", message_id=str(message_id))


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
                    async for event, payload in chat_service.ask_stream(
                        target, question, request.knowledge_base_ids
                    ):
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
