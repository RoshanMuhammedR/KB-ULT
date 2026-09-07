from __future__ import annotations

from uuid import UUID

import structlog
from procrastinate import RetryStrategy

from src.core.config import get_settings
from src.infrastructure.database.session import session_scope
from src.infrastructure.queue.app import app
from src.infrastructure.queue.tenant_task import tenant_task

logger = structlog.get_logger(__name__)

# Retry policy owned by the queue engine. process_ingestion re-raises IngestionError
# on failure, and Procrastinate re-schedules with exponential backoff up to
# max_attempts. The domain job row records attempts/last_error alongside this.
_RETRY = RetryStrategy(max_attempts=3, exponential_wait=5)


@app.task(name="ingest_asset", retry=_RETRY)
@tenant_task
async def ingest_asset(asset_id: str) -> None:
    """Worker entrypoint: run the ingestion pipeline for one asset.

    Procrastinate awaits coroutine tasks natively, so this is a plain `async def` — no
    bridging layer, and the ingestion pipeline's own awaits reach the driver directly.

    `@tenant_task` (outer of the body) rebuilds tenant context from the job's
    tenant_id/user_id before this runs, so the worker-scoped session filters exactly
    like the HTTP path. Kept deliberately thin — it opens a session, rebuilds the shared
    object graph, and hands off. Anything raised propagates to Procrastinate for retry.

    The import of the composition root is deferred to call time to avoid an import
    cycle (composition -> queue adapter -> this module).
    """
    from src.composition import build_ingestion_service

    logger.info("ingest_task_received", asset_id=asset_id)
    async with session_scope() as db:
        service = build_ingestion_service(db, get_settings())
        await service.process_ingestion(UUID(asset_id))


@app.task(name="distill_memory", retry=RetryStrategy(max_attempts=2, exponential_wait=5))
@tenant_task
async def distill_memory(
    knowledge_base_id: str,
    question: str,
    answer: str,
    conversation_id: str | None = None,
    message_id: str | None = None,
) -> None:
    """Extract durable facts from a finished exchange, in the background.

    `max_attempts=2` rather than ingestion's 3, because the failure modes differ in kind.
    A failed ingestion leaves an asset stuck in `queued` — a visible broken state a user
    reports. A failed distillation leaves nothing at all: the answer was delivered, and the
    only cost is a fact nobody learned. A third model call to chase that is not worth paying
    for, and a distillation that has already failed twice is unlikely to succeed on a third.

    Text travels through the queue here, unlike `ingest_asset` which carries only ids. It has
    to: the answer is not addressable — nothing has written it to a row this task could read
    at the time it is deferred — and re-reading the message would race the very transaction
    that is writing it.
    """
    from src.composition import build_memory_service

    async with session_scope() as db:
        service = build_memory_service(db, get_settings())
        if service is None:
            return
        await service.distil(
            UUID(knowledge_base_id),
            question=question,
            answer=answer,
            conversation_id=UUID(conversation_id) if conversation_id else None,
            message_id=UUID(message_id) if message_id else None,
        )
