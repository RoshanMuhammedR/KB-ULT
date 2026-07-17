from __future__ import annotations

from uuid import UUID

from src.domain.interfaces import IJobQueue
from src.infrastructure.queue.tasks import ingest_asset


class ProcrastinateJobQueue(IJobQueue):
    """The one place the app talks to Procrastinate for enqueuing.

    Implements the IJobQueue port, so the rest of the codebase depends only on the
    domain interface. Swapping to another engine (Celery/Redis, ...) means replacing
    this file plus app.py/tasks.py and nothing else.
    """

    def enqueue_ingestion(self, asset_id: UUID) -> None:
        # `.defer()` inserts a row into Procrastinate's Postgres queue; a running
        # worker is woken via LISTEN/NOTIFY. Only the id crosses the boundary.
        #
        # Called synchronously from the FastAPI request. Because the app is never
        # opened in the web process, the async PsycopgConnector derives a one-off
        # sync connection for this defer under the hood — no `app.open()` needed.
        ingest_asset.defer(asset_id=str(asset_id))
