"""Re-ingestion actually queues work, and says so honestly when it does not.

`scripts/reingest.py` called `IngestionService.retry` on READY assets. `retry` guards on
`status == FAILED` and returns the asset unchanged for anything else — so the script queued
nothing, four times, and printed "Queued 4 sources. Watch progress with GET /jobs."

Nothing caught it because the guard is correct for `retry` and the script's only automated
exercise was `--dry-run`, which returns before reaching the call. It was found by running the
real thing against a real corpus and watching the job table not grow.

Two lessons are pinned here: `reingest` queues a READY asset, and it returns a bool so that
"nothing to do" cannot be read as "done" — which is precisely the confusion that let a silent
no-op report success.
"""

from contextlib import asynccontextmanager
import sys
from types import SimpleNamespace
import unittest
from unittest.mock import AsyncMock, Mock
from uuid import UUID, uuid4

sys.modules.setdefault("structlog", SimpleNamespace(get_logger=lambda *_: Mock()))

from src.application.ingestion.service import IngestionService
from src.core.tenant_context import reset_tenant_context, set_tenant_context
from src.domain.entities import AssetStatus, IngestionJob, JobStatus, KnowledgeAsset


class _FakeJobQueue:
    def __init__(self) -> None:
        self.enqueued: list[UUID] = []

    async def enqueue_ingestion(self, asset_id: UUID, tenant_id: UUID, user_id: UUID) -> None:
        self.enqueued.append(asset_id)


class _NullAtomicScope:
    @asynccontextmanager
    async def atomic(self):
        yield


def _service(status: AssetStatus):
    asset = KnowledgeAsset(
        id=uuid4(),
        knowledge_base_id=uuid4(),
        filename="notes.md",
        source_type="markdown",
        status=status,
    )
    asset_repo = AsyncMock()
    asset_repo.get.return_value = asset
    asset_repo.update_from_domain.side_effect = lambda a: a

    job_repo = AsyncMock()
    job_repo.create.side_effect = lambda job: job
    job_repo.latest_for_asset.return_value = IngestionJob(id=uuid4())

    job_event_repo = AsyncMock()
    job_event_repo.append.side_effect = lambda event: event

    queue = _FakeJobQueue()
    service = IngestionService(
        kb_repo=AsyncMock(),
        asset_repo=asset_repo,
        chunk_repo=AsyncMock(),
        job_repo=job_repo,
        job_event_repo=job_event_repo,
        source_handler_registry=Mock(),
        chunker=AsyncMock(),
        embedding_provider=AsyncMock(),
        vector_store=AsyncMock(),
        file_storage=AsyncMock(),
        job_queue=queue,
        atomic_scope=_NullAtomicScope(),
        max_audio_upload_bytes=100 * 1024 * 1024,
    )
    return service, asset, queue


class ReingestTest(unittest.IsolatedAsyncioTestCase):
    async def _call(self, service, asset_id):
        tokens = set_tenant_context(uuid4(), uuid4())
        try:
            return await service.reingest(asset_id)
        finally:
            reset_tenant_context(tokens)

    async def test_a_ready_asset_is_queued(self) -> None:
        """The case that was broken: `retry` refused this outright and said nothing."""
        service, asset, queue = _service(AssetStatus.READY)

        queued = await self._call(service, asset.id)

        self.assertTrue(queued)
        self.assertEqual(queue.enqueued, [asset.id])
        self.assertEqual(asset.status, AssetStatus.QUEUED)

    async def test_an_asset_genuinely_in_flight_is_not_queued_again(self) -> None:
        """A second job would re-parse and re-embed the same source alongside the first."""
        for status in (AssetStatus.QUEUED, AssetStatus.EXTRACTING, AssetStatus.EMBEDDING):
            with self.subTest(status=status):
                service, asset, queue = _service(status)
                # A job the queue will still retry: attempts below the budget.
                service.job_repo.latest_for_asset.return_value = IngestionJob(
                    id=uuid4(), status=JobStatus.RUNNING, attempts=1
                )

                queued = await self._call(service, asset.id)

                self.assertFalse(queued)
                self.assertEqual(queue.enqueued, [])

    async def test_a_stranded_asset_is_recovered(self) -> None:
        """Mid-pipeline with no job the queue will retry: reachable by nothing else.

        This is what the un-awaited `handler.acquire` produced on the live stack — the
        pipeline died where its own except-block could not recover, so nothing marked the
        asset FAILED, and its job then exhausted the queue's attempts. `retry` refused it for
        not being FAILED, re-ingestion refused it for not being READY, and the only way out
        was editing the database by hand.
        """
        service, asset, queue = _service(AssetStatus.EXTRACTING)
        # Attempts spent: the queue is done with it.
        service.job_repo.latest_for_asset.return_value = IngestionJob(
            id=uuid4(), status=JobStatus.FAILED, attempts=4
        )

        queued = await self._call(service, asset.id)

        self.assertTrue(queued)
        self.assertEqual(queue.enqueued, [asset.id])
        self.assertEqual(asset.status, AssetStatus.QUEUED)

    async def test_a_running_job_past_its_budget_is_treated_as_abandoned(self) -> None:
        """RUNNING is not to be believed once the attempt budget is spent.

        `mark_failed` runs inside the pipeline's own except-block, so a worker that dies
        where that block cannot run leaves the row on RUNNING with nothing alive to correct
        it. Reading that as "the queue has it" locks the asset out of every recovery path in
        the product — which is exactly what happened on the live stack.
        """
        service, asset, queue = _service(AssetStatus.EXTRACTING)
        service.job_repo.latest_for_asset.return_value = IngestionJob(
            id=uuid4(), status=JobStatus.RUNNING, attempts=4, max_attempts=3
        )

        queued = await self._call(service, asset.id)

        self.assertTrue(queued)
        self.assertEqual(queue.enqueued, [asset.id])

    async def test_a_job_on_its_final_attempt_is_still_live(self) -> None:
        """The boundary the rule above must not cross: attempts == max_attempts is running
        right now, and duplicating it would pay twice for the same work."""
        service, asset, queue = _service(AssetStatus.EXTRACTING)
        service.job_repo.latest_for_asset.return_value = IngestionJob(
            id=uuid4(), status=JobStatus.RUNNING, attempts=3, max_attempts=3
        )

        queued = await self._call(service, asset.id)

        self.assertFalse(queued)
        self.assertEqual(queue.enqueued, [])

    async def test_a_failed_asset_is_left_to_retry(self) -> None:
        """`retry` owns FAILED, including standing down while the queue still has the job.
        Re-ingestion must not step around that."""
        service, asset, queue = _service(AssetStatus.FAILED)

        queued = await self._call(service, asset.id)

        self.assertFalse(queued)
        self.assertEqual(queue.enqueued, [])

    async def test_a_missing_asset_raises_rather_than_returning_false(self) -> None:
        """False means "nothing to do"; a bad id is a caller error and must not read as one."""
        service, _asset, _queue = _service(AssetStatus.READY)
        service.asset_repo.get.return_value = None

        with self.assertRaises(ValueError):
            await self._call(service, uuid4())


if __name__ == "__main__":
    unittest.main()
