from __future__ import annotations

import json
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.orm import Session

from src.domain.interfaces import IJobQueue
from src.infrastructure.queue.tasks import ingest_asset


class ProcrastinateJobQueue(IJobQueue):
    """The one place the app talks to Procrastinate for enqueuing.

    Implements the IJobQueue port, so the rest of the codebase depends only on the
    domain interface. Swapping to another engine (Celery/Redis, ...) means replacing
    this file plus app.py/tasks.py and nothing else.
    """

    def enqueue_ingestion(self, asset_id: UUID, tenant_id: UUID, user_id: UUID) -> None:
        # `.defer()` inserts a row into Procrastinate's Postgres queue; a running
        # worker is woken via LISTEN/NOTIFY. Only ids cross the boundary — including
        # tenant_id/user_id, so the worker's @tenant_task wrapper can rebuild context.
        #
        # Called synchronously from the FastAPI request. Because the app is never
        # opened in the web process, the async PsycopgConnector derives a one-off
        # sync connection for this defer under the hood — no `app.open()` needed.
        ingest_asset.defer(
            asset_id=str(asset_id), tenant_id=str(tenant_id), user_id=str(user_id)
        )


# Procrastinate's own `defer_jobs` query, run through OUR connection instead of the
# connector's. `procrastinate_defer_jobs_v1` is the same function `.defer()` calls, and the
# INSERT it performs fires the `procrastinate_jobs_notify_queue_job_inserted_v1` trigger, so
# a listening worker still wakes immediately — but only once this transaction commits, which
# is exactly the semantics we want. Postgres holds NOTIFY until commit; a rolled-back upload
# therefore wakes nobody, because the job row never existed.
_DEFER_SQL = text(
    """
    SELECT procrastinate_defer_jobs_v1(
        ARRAY[
            ROW(
                CAST(:queue_name AS character varying),
                CAST(:task_name AS character varying),
                CAST(:priority AS integer),
                NULL::text,
                NULL::text,
                CAST(:args AS jsonb),
                NULL::timestamptz
            )::procrastinate_job_to_defer_v1
        ]
    )
    """
)

# Mirrors the task registration in tasks.py: `@app.task(name="ingest_asset")` with no queue
# override, so Procrastinate's defaults apply. If either is ever changed there, change it
# here — the coupling is the price of bypassing the connector, and it is why this adapter
# lives next to the task definition rather than in the repositories package.
_QUEUE_NAME = "default"
_TASK_NAME = "ingest_asset"
_PRIORITY = 0


class TransactionalProcrastinateJobQueue(IJobQueue):
    """Enqueues through the caller's SQLAlchemy transaction rather than its own connection.

    `ProcrastinateJobQueue` above is correct but *separate*: `.defer()` opens its own
    connection and commits independently of whatever the request has been writing. That is
    the dual-write gap — asset committed, process dies, job never queued, asset stuck in
    `queued` forever.

    Because the queue table is in the same database, the fix is to write the queue row with
    the same connection and let one COMMIT cover both. Used with `unit_of_work(db)` (see
    repositories/unit_of_work.py), "the asset exists" and "its job is queued" become a
    single atomic fact, and neither can be observed without the other.
    """

    def __init__(self, db: Session) -> None:
        self.db = db

    def enqueue_ingestion(self, asset_id: UUID, tenant_id: UUID, user_id: UUID) -> None:
        # Same payload as `.defer()` — ids only, with tenant_id/user_id carried explicitly
        # so @tenant_task can rebuild context in a worker that has no HTTP request.
        args = {
            "asset_id": str(asset_id),
            "tenant_id": str(tenant_id),
            "user_id": str(user_id),
        }
        self.db.execute(
            _DEFER_SQL,
            {
                "queue_name": _QUEUE_NAME,
                "task_name": _TASK_NAME,
                "priority": _PRIORITY,
                "args": json.dumps(args),
            },
        )
