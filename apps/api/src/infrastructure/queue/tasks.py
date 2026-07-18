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
def ingest_asset(asset_id: str) -> None:
    """Worker entrypoint: run the ingestion pipeline for one asset.

    `@tenant_task` (outer of the body) rebuilds tenant context from the job's
    tenant_id/user_id before this runs, so the worker-scoped session filters exactly
    like the HTTP path. Kept deliberately thin — it opens a session, rebuilds the shared
    object graph, and hands off. Anything raised propagates to Procrastinate for retry.

    The import of the composition root is deferred to call time to avoid an import
    cycle (composition -> queue adapter -> this module).
    """
    from src.composition import build_ingestion_service

    logger.info("ingest_task_received", asset_id=asset_id)
    with session_scope() as db:
        service = build_ingestion_service(db, get_settings())
        service.process_ingestion(UUID(asset_id))
