from __future__ import annotations

from pathlib import Path
from uuid import UUID, uuid4

import structlog

from src.core.exceptions import IngestionError
from src.domain.entities import (
    AssetStatus,
    IngestionJob,
    JobEvent,
    KnowledgeAsset,
    RawContent,
    SourceType,
)
from src.domain.interfaces import (
    Chunker,
    EmbeddingProvider,
    IChunkRepository,
    IDocumentRepository,
    IFileStorage,
    IIngestionJobEventRepository,
    IIngestionJobRepository,
    IJobQueue,
    IKnowledgeBaseRepository,
    ISourceHandler,
    VectorStore,
)
from src.ingestion.registry import SourceHandlerRegistry
from src.ingestion.source_types import source_type_for_filename

logger = structlog.get_logger(__name__)


class IngestionService:
    """Orchestrates ingestion across two entrypoints.

    The work is split so the slow, CPU-bound pipeline never runs inside an HTTP
    request:

      * `enqueue_ingestion` runs in the **request** — it does only the fast part
        (store the file, create the asset + job records, hand the job to the queue)
        and returns immediately.
      * `process_ingestion` runs in the **worker** — it resolves the source handler,
        acquires the raw content, and runs the parse -> chunk -> embed -> persist
        pipeline, driving the asset/job status as it goes.

    Source specifics live entirely behind `SourceHandlerRegistry`/`ISourceHandler`, so
    this class is source-agnostic: adding websites/YouTube is a new handler, not a
    change here.
    """

    def __init__(
        self,
        kb_repo: IKnowledgeBaseRepository,
        asset_repo: IDocumentRepository,
        chunk_repo: IChunkRepository,
        job_repo: IIngestionJobRepository,
        job_event_repo: IIngestionJobEventRepository,
        source_handler_registry: SourceHandlerRegistry,
        chunker: Chunker,
        embedding_provider: EmbeddingProvider,
        vector_store: VectorStore,
        file_storage: IFileStorage,
        job_queue: IJobQueue,
    ) -> None:
        self.kb_repo = kb_repo
        self.asset_repo = asset_repo
        self.chunk_repo = chunk_repo
        self.job_repo = job_repo
        self.job_event_repo = job_event_repo
        self.source_handler_registry = source_handler_registry
        self.chunker = chunker
        self.embedding_provider = embedding_provider
        self.vector_store = vector_store
        self.file_storage = file_storage
        self.job_queue = job_queue

    # ------------------------------------------------------------------ request path

    def enqueue_ingestion(
        self,
        file_data: bytes,
        filename: str,
        content_type: str | None = None,
        user_id: str = "anonymous",
    ) -> KnowledgeAsset:
        """Fast path (HTTP): persist the source + job, then return without processing.

        Everything here is cheap: resolve the source type, compute lineage/version,
        push bytes to object storage, create the asset (status QUEUED) and its job,
        then hand the job id to the queue. The heavy pipeline happens later in
        `process_ingestion`.
        """
        # Sanitize first, then resolve the source type from the clean name so quirks
        # like a trailing space (".pdf " vs ".pdf") don't spuriously reject the upload.
        safe_filename = self._sanitize_filename(filename)
        # Fail fast in the request if we can't handle this source type at all.
        source_type = source_type_for_filename(safe_filename)
        self.source_handler_registry.get(source_type)
        knowledge_base = self.kb_repo.ensure_default()
        previous = self.asset_repo.latest_for_filename(knowledge_base.id, safe_filename)
        lineage_id = previous.lineage_id if previous else uuid4()
        version = previous.version + 1 if previous else 1
        asset_id = uuid4()
        storage_key = f"{user_id}/{asset_id}/{safe_filename}"
        stored_key = self.file_storage.upload(
            key=storage_key,
            file_data=file_data,
            content_type=content_type or "application/octet-stream",
        )

        asset = self.asset_repo.create_pending(
            KnowledgeAsset(
                id=asset_id,
                knowledge_base_id=knowledge_base.id,
                lineage_id=lineage_id,
                version=version,
                filename=safe_filename,
                title=safe_filename,
                source_type=source_type.value,
                storage_key=stored_key,
                status=AssetStatus.QUEUED,
                metadata={
                    "filename": safe_filename,
                    "source_type": source_type.value,
                    "content_type": content_type,
                },
            )
        )

        # Create the domain job record, then hand it to the queue. Defer happens after
        # the records are committed so a worker can never pick up an asset that isn't
        # persisted yet.
        job = self.job_repo.create(IngestionJob(asset_id=asset.id))
        self.job_queue.enqueue_ingestion(asset.id)
        self._record(asset, "queued", "Ingestion queued", job_id=job.id)
        logger.info("ingestion_enqueued", knowledge_asset_id=str(asset.id), filename=safe_filename)
        return asset

    def retry(self, asset_id: UUID) -> KnowledgeAsset:
        """Re-enqueue a failed asset. No re-upload needed — the worker re-acquires the
        source from storage, resuming from the step that failed."""
        asset = self.asset_repo.get(asset_id)
        if asset is None:
            raise ValueError(f"KnowledgeAsset not found: {asset_id}")
        if asset.status != AssetStatus.FAILED:
            return asset

        job = self.job_repo.latest_for_asset(asset_id)
        if job is not None:
            self.job_repo.reset_for_retry(job.id)
        else:
            # Older asset predating the jobs table: create a fresh job for it.
            job = self.job_repo.create(IngestionJob(asset_id=asset_id))

        asset.status = AssetStatus.QUEUED
        asset.error_message = None
        self.asset_repo.update_from_domain(asset)
        self.job_queue.enqueue_ingestion(asset_id)
        self._record(asset, "retry", "Retry re-enqueued", job_id=job.id if job else None)
        logger.info("ingestion_retry_enqueued", knowledge_asset_id=str(asset_id))
        return asset

    # ------------------------------------------------------------------- worker path

    def process_ingestion(self, asset_id: UUID) -> KnowledgeAsset:
        """Slow path (worker): run the full pipeline for one asset.

        Marks the job running, acquires the source via its handler, runs the state
        machine, then records the terminal job outcome. On failure it re-raises
        `IngestionError` so the queue engine can retry — the asset keeps its
        `failed_step` so the retry resumes rather than starting over.
        """
        asset = self.asset_repo.get(asset_id)
        if asset is None:
            raise ValueError(f"KnowledgeAsset not found: {asset_id}")

        job = self.job_repo.latest_for_asset(asset_id)
        job_id = job.id if job is not None else None
        if job is not None:
            self.job_repo.mark_running(job.id)
        self._record(asset, "running", f"Attempt {job.attempts + 1 if job else 1} started", job_id=job_id)

        handler = self.source_handler_registry.get(SourceType(asset.source_type))

        # Only (re-)acquire the source when extraction actually needs it. A retry that
        # already got past extraction resumes from chunks stored in the DB.
        raw: RawContent | None = None
        if asset.failed_step in (None, "extracting"):
            raw = handler.acquire(asset)

        result = self._run_pipeline(asset, raw, handler, job_id)

        if result.status == AssetStatus.FAILED:
            error = result.error_message or "ingestion failed"
            if job is not None:
                self.job_repo.mark_failed(job.id, error)
            # Re-raise so Procrastinate re-schedules per its RetryStrategy.
            raise IngestionError(error)

        if job is not None:
            self.job_repo.mark_succeeded(job.id)
        return result

    def _run_pipeline(
        self,
        asset: KnowledgeAsset,
        raw: RawContent | None,
        handler: ISourceHandler,
        job_id: UUID | None,
    ) -> KnowledgeAsset:
        step = "extracting"
        try:
            if asset.failed_step in (None, "extracting"):
                asset.status = AssetStatus.EXTRACTING
                asset.failed_step = None
                asset.error_message = None
                self.asset_repo.update_from_domain(asset)
                self._record(asset, step, "Extracting source content", job_id=job_id)
                logger.info("ingestion_step", step=step, knowledge_asset_id=str(asset.id), status=asset.status)
                if raw is None:
                    raise ValueError("Cannot extract without acquired source content")
                asset = handler.parse(asset, raw)
                self.asset_repo.update_from_domain(asset)

            step = "chunking"
            if asset.failed_step in (None, "chunking"):
                asset.status = AssetStatus.CHUNKING
                asset.failed_step = None
                asset.error_message = None
                self.asset_repo.update_from_domain(asset)
                self._record(asset, step, "Splitting into chunks", job_id=job_id)
                logger.info("ingestion_step", step=step, knowledge_asset_id=str(asset.id), status=asset.status)
                chunks = self.chunker.chunk(asset)
                if not chunks:
                    raise ValueError("Source produced no indexable text chunks")
                chunks = self.chunk_repo.replace_for_asset(asset.id, chunks)
            else:
                chunks = self.chunk_repo.list_for_asset(asset.id)

            step = "embedding"
            asset.status = AssetStatus.EMBEDDING
            self.asset_repo.update_from_domain(asset)
            self._record(asset, step, "Embedding chunks", job_id=job_id, data={"chunk_count": len(chunks)})
            logger.info("ingestion_step", step=step, knowledge_asset_id=str(asset.id), status=asset.status, chunk_count=len(chunks))
            embeddings = self.embedding_provider.embed_texts([chunk.text for chunk in chunks])
            self.vector_store.upsert_embeddings(asset, chunks, embeddings)

            step = "persisting"
            asset.status = AssetStatus.READY
            asset.failed_step = None
            asset.error_message = None
            ready = self.asset_repo.update_from_domain(asset)
            self.asset_repo.supersede_previous_versions(asset.lineage_id, asset.id)
            self._record(ready, "ready", "Ingestion complete", job_id=job_id)
            logger.info("ingestion_step", step=step, knowledge_asset_id=str(asset.id), status=ready.status)
            return ready
        except Exception as exc:
            # Record where it broke so a retry resumes from this step, then return the
            # failed asset. process_ingestion turns this into a raised IngestionError.
            asset.status = AssetStatus.FAILED
            asset.failed_step = step
            asset.error_message = str(exc)
            failed = self.asset_repo.update_from_domain(asset)
            self._record(failed, "failed", str(exc), level="error", job_id=job_id, data={"step": step})
            logger.exception("ingestion_failed", step=step, knowledge_asset_id=str(asset.id), error=str(exc))
            return failed

    def _record(
        self,
        asset: KnowledgeAsset,
        event: str,
        message: str | None = None,
        *,
        level: str = "info",
        job_id: UUID | None = None,
        data: dict | None = None,
    ) -> None:
        # Persist one worker-log line. Best-effort: a logging failure must never break
        # ingestion, so any error here is swallowed (the structlog trail still fires).
        try:
            self.job_event_repo.append(
                JobEvent(
                    asset_id=asset.id,
                    job_id=job_id,
                    level=level,
                    event=event,
                    message=message,
                    data=data or {},
                )
            )
        except Exception:  # noqa: BLE001 - logging is non-fatal by design
            logger.warning("job_event_record_failed", knowledge_asset_id=str(asset.id), event=event)

    def _sanitize_filename(self, filename: str) -> str:
        sanitized = Path(filename).name.strip().replace("/", "").replace("\\", "")
        if not sanitized:
            raise ValueError("Uploaded file must include a valid filename")
        return sanitized
