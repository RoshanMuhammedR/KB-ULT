from __future__ import annotations

from typing import Protocol
from uuid import UUID


class IJobQueue(Protocol):
    """Port for handing ingestion work off to a background worker.

    Boundary rule: nothing behind this port leaks into the domain — the concrete
    adapter (e.g. Procrastinate) lives in `infrastructure/queue/`. Swapping to a
    different queue engine (Celery/Redis, ...) should only replace that adapter.
    """

    async def enqueue_ingestion(self, asset_id: UUID, tenant_id: UUID, user_id: UUID) -> None:
        """Schedule the ingestion pipeline for an already-persisted asset.

        Only ids travel through the queue — never the file bytes. `tenant_id`/`user_id`
        are carried explicitly so the worker can re-establish tenant context before
        touching any tenant-scoped table (a job with no tenant is refused, never run
        unscoped). The worker re-reads the source from object storage using the asset's
        storage_key (see IFileStorage.download).
        """


class IMemoryQueue(Protocol):
    """Port for handing memory distillation off to a background worker.

    Separate from `IJobQueue` rather than another method on it, because the two have opposite
    transactional requirements and sharing a port would invite sharing an adapter. Ingestion
    needs "the asset exists" and "its job is queued" to be one atomic fact. Distillation needs
    no such guarantee: if the job is lost the user simply has one fewer remembered fact, and
    nothing anywhere is left in a broken state.
    """

    async def enqueue_distillation(
        self,
        knowledge_base_id: UUID,
        tenant_id: UUID,
        user_id: UUID,
        *,
        question: str,
        answer: str,
        conversation_id: UUID | None,
        message_id: UUID | None,
    ) -> None:
        """Schedule distillation for one finished exchange. Best-effort by design."""
        ...
