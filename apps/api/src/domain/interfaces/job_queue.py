from __future__ import annotations

from typing import Protocol
from uuid import UUID


class IJobQueue(Protocol):
    """Port for handing ingestion work off to a background worker.

    Boundary rule: nothing behind this port leaks into the domain — the concrete
    adapter (e.g. Procrastinate) lives in `infrastructure/queue/`. Swapping to a
    different queue engine (Celery/Redis, ...) should only replace that adapter.
    """

    def enqueue_ingestion(self, asset_id: UUID, tenant_id: UUID, user_id: UUID) -> None:
        """Schedule the ingestion pipeline for an already-persisted asset.

        Only ids travel through the queue — never the file bytes. `tenant_id`/`user_id`
        are carried explicitly so the worker can re-establish tenant context before
        touching any tenant-scoped table (a job with no tenant is refused, never run
        unscoped). The worker re-reads the source from object storage using the asset's
        storage_key (see IFileStorage.download).
        """
