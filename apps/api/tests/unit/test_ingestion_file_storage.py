import sys
from types import SimpleNamespace
from unittest import TestCase
from unittest.mock import Mock
from uuid import UUID, uuid4

sys.modules.setdefault("structlog", SimpleNamespace(get_logger=lambda *_: Mock()))

from src.application.ingestion.service import IngestionService
from src.core.tenant_context import reset_tenant_context, set_tenant_context
from src.domain.entities import (
    AssetStatus,
    Chunk,
    Embedding,
    IngestionJob,
    KnowledgeAsset,
    KnowledgeBase,
    RawContent,
)


class FakeJobQueue:
    """Records enqueued asset ids instead of talking to Procrastinate."""

    def __init__(self) -> None:
        self.enqueued: list[UUID] = []
        self.tenant_ids: list[UUID] = []

    def enqueue_ingestion(self, asset_id: UUID, tenant_id: UUID, user_id: UUID) -> None:
        self.enqueued.append(asset_id)
        self.tenant_ids.append(tenant_id)


def _build_service(**overrides):
    """Assemble an IngestionService with mocks, overridable per test."""
    kb_repo = Mock()
    kb_repo.ensure_default.return_value = KnowledgeBase(id=uuid4())
    asset_repo = Mock()
    asset_repo.latest_for_filename.return_value = None
    asset_repo.create_pending.side_effect = lambda asset: asset
    asset_repo.update_from_domain.side_effect = lambda asset: asset

    job_repo = Mock()
    job_repo.create.side_effect = lambda job: job
    job_repo.latest_for_asset.return_value = IngestionJob(id=uuid4())

    job_event_repo = Mock()
    job_event_repo.append.side_effect = lambda event: event

    chunk_repo = Mock()
    chunk_repo.replace_for_asset.side_effect = lambda _, chunks: chunks

    # The source handler owns acquire (download) + parse (extract -> segments).
    handler = Mock()
    handler.acquire.return_value = RawContent(data=b"pdf", mime="application/pdf")
    handler.parse.side_effect = lambda asset, raw: KnowledgeAsset(
        id=asset.id,
        knowledge_base_id=asset.knowledge_base_id,
        lineage_id=asset.lineage_id,
        version=asset.version,
        filename=asset.filename,
        source_type="pdf",
        storage_key=asset.storage_key,
        status=AssetStatus.EXTRACTING,
        metadata={"segments": [{"text": "hello", "locator": {"type": "page", "value": 1}}]},
    )
    source_handler_registry = Mock()
    source_handler_registry.get.return_value = handler

    chunker = Mock()
    chunker.chunk.return_value = [Chunk(text="hello")]
    embedder = Mock()
    embedder.embed_texts.return_value = [Embedding(vector=[0.1], model="m", dimensions=1)]
    vector_store = Mock()
    file_storage = Mock()
    file_storage.upload.side_effect = lambda key, file_data, content_type: key
    file_storage.download.return_value = b"pdf"

    kwargs = dict(
        kb_repo=kb_repo,
        asset_repo=asset_repo,
        chunk_repo=chunk_repo,
        job_repo=job_repo,
        job_event_repo=job_event_repo,
        source_handler_registry=source_handler_registry,
        chunker=chunker,
        embedding_provider=embedder,
        vector_store=vector_store,
        file_storage=file_storage,
        job_queue=FakeJobQueue(),
    )
    kwargs.update(overrides)
    return IngestionService(**kwargs), kwargs


class EnqueueIngestionTest(TestCase):
    def test_uploads_and_enqueues_without_running_pipeline(self) -> None:
        service, deps = _build_service()

        # Enqueue reads the current tenant/user (set by the HTTP middleware in prod) to
        # carry into the job payload, so a tenant context must be present.
        tenant_id, user_id = uuid4(), uuid4()
        tokens = set_tenant_context(tenant_id, user_id)
        try:
            asset = service.enqueue_ingestion(
                b"pdf", "../ My File.pdf ", "application/pdf", user_id="user-1"
            )
        finally:
            reset_tenant_context(tokens)

        # The request path only stores + queues; it must NOT acquire/parse.
        self.assertEqual(asset.status, AssetStatus.QUEUED)
        self.assertTrue(asset.storage_key.startswith("user-1/"))
        self.assertTrue(asset.storage_key.endswith("/My File.pdf"))
        self.assertEqual(asset.source_type, "pdf")
        deps["file_storage"].upload.assert_called_once()
        deps["source_handler_registry"].get.return_value.acquire.assert_not_called()
        deps["source_handler_registry"].get.return_value.parse.assert_not_called()
        deps["job_repo"].create.assert_called_once()
        deps["job_event_repo"].append.assert_called()  # "queued" worker-log line
        self.assertEqual(deps["job_queue"].enqueued, [asset.id])
        # The current tenant is threaded into the job payload.
        self.assertEqual(deps["job_queue"].tenant_ids, [tenant_id])


class ProcessIngestionTest(TestCase):
    def test_acquires_source_and_runs_pipeline_to_ready(self) -> None:
        asset_id = uuid4()
        queued = KnowledgeAsset(
            id=asset_id,
            knowledge_base_id=uuid4(),
            filename="My File.pdf",
            source_type="pdf",
            storage_key="user-1/x/My File.pdf",
            status=AssetStatus.QUEUED,
            metadata={"content_type": "application/pdf"},
        )
        asset_repo = Mock()
        asset_repo.get.return_value = queued
        asset_repo.create_pending.side_effect = lambda asset: asset
        asset_repo.update_from_domain.side_effect = lambda asset: asset
        service, deps = _build_service(asset_repo=asset_repo)

        result = service.process_ingestion(asset_id)

        self.assertEqual(result.status, AssetStatus.READY)
        # Worker sources content via the handler (never from the queue payload).
        deps["source_handler_registry"].get.return_value.acquire.assert_called_once()
        deps["source_handler_registry"].get.return_value.parse.assert_called_once()
        deps["job_repo"].mark_running.assert_called_once()
        deps["job_repo"].mark_succeeded.assert_called_once()
