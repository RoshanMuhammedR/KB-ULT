from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from uuid import UUID, uuid4

import structlog

from src.core.exceptions import DuplicateAssetVersionError, IngestionError
from src.core.tenant_context import current_tenant_id, current_user_id
from src.domain.entities import (
    AssetStatus,
    IngestionJob,
    JobEvent,
    JobStatus,
    KnowledgeAsset,
    SourceType,
)
from src.domain.interfaces import (
    Chunker,
    EmbeddingProvider,
    IAtomicScope,
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
from src.ingestion.source_types import (
    identity_for_url,
    source_type_for_filename,
    source_type_for_url,
)

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
        atomic_scope: IAtomicScope,
        max_audio_upload_bytes: int,
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
        self.atomic_scope = atomic_scope
        self.max_audio_upload_bytes = max_audio_upload_bytes

    # ------------------------------------------------------------------ request path

    def enqueue_ingestion(
        self,
        file_data: bytes,
        filename: str,
        content_type: str | None = None,
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
        asset_id = uuid4()
        # Tenant-prefixed so the bucket layout mirrors the isolation boundary the database
        # already enforces. This used to be a `user_id: str = "anonymous"` default parameter
        # that no caller ever passed, so every object in the bucket landed under the literal
        # prefix `anonymous/`. Reading the tenant from the ambient context instead of a
        # parameter means a caller cannot silently forget it: `current_tenant_id()` fails
        # closed when no tenant is bound.
        storage_key = f"{current_tenant_id()}/{asset_id}/{safe_filename}"
        stored_key = self.file_storage.upload(
            key=storage_key,
            file_data=file_data,
            content_type=content_type or "application/octet-stream",
        )

        # The object is uploaded before any of this, deliberately: an S3 round-trip inside
        # an open transaction would hold a database connection for its duration, and an
        # orphaned object is harmless (nothing references it) where an orphaned row is not.
        asset = self._persist_queued_asset(
            knowledge_base_id=knowledge_base.id,
            filename=safe_filename,
            build=lambda lineage_id, version: KnowledgeAsset(
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
            ),
            event_message="Ingestion queued",
        )
        logger.info("ingestion_enqueued", knowledge_asset_id=str(asset.id), filename=safe_filename)
        return asset

    def prepare_direct_upload(
        self,
        filename: str,
        content_type: str | None = None,
        size_bytes: int | None = None,
    ) -> tuple[UUID, str, str]:
        """Reserve an asset id and hand back a URL the client can PUT the file to.

        The first half of the direct-upload flow: no bytes reach this process at all, which
        is the whole point — `enqueue_ingestion` reads the entire upload into memory, so a
        large file is a hard memory ceiling per concurrent request. Here the browser talks
        to object storage and the API only learns that it happened.

        Nothing is persisted yet. Validation that would otherwise happen too late is done
        now (a source type we cannot parse fails here, before the client wastes an upload),
        and the key is built from the ambient tenant, so a client cannot choose where its
        file lands.

        Returns `(asset_id, storage_key, upload_url)`; the client sends the first back to
        `complete_direct_upload` once the PUT succeeds.
        """
        safe_filename = self._sanitize_filename(filename)
        source_type = source_type_for_filename(safe_filename)
        self.source_handler_registry.get(source_type)
        # The client tells us how big the file is before sending it, so an over-limit
        # upload is refused before the bytes move rather than after. It is a claim, not a
        # measurement — `complete_direct_upload` checks the object itself — but believing
        # it here saves an honest client a pointless upload.
        if size_bytes is not None:
            self._check_size_limit(source_type, size_bytes)

        asset_id = uuid4()
        storage_key = f"{current_tenant_id()}/{asset_id}/{safe_filename}"
        upload_url = self.file_storage.get_presigned_put_url(
            storage_key, content_type or "application/octet-stream"
        )
        logger.info(
            "direct_upload_prepared", knowledge_asset_id=str(asset_id), filename=safe_filename
        )
        return asset_id, storage_key, upload_url

    def complete_direct_upload(
        self,
        asset_id: UUID,
        filename: str,
        content_type: str | None = None,
    ) -> KnowledgeAsset:
        """Record and queue a source the client uploaded straight to object storage.

        The second half of the flow. The storage key is rebuilt here from the tenant context
        rather than accepted from the caller, so the only objects a client can claim are the
        ones under its own tenant prefix — the same boundary the database enforces.

        The object is checked before anything is written: without that, a client could
        register an asset for a PUT that never happened and the worker would fail on a 404
        several seconds later, with a job row and a failure event to explain away.
        """
        safe_filename = self._sanitize_filename(filename)
        source_type = source_type_for_filename(safe_filename)
        self.source_handler_registry.get(source_type)

        storage_key = f"{current_tenant_id()}/{asset_id}/{safe_filename}"
        size_bytes = self.file_storage.object_size(storage_key)
        if size_bytes is None:
            raise ValueError("The uploaded file was not found in storage. Please try again.")

        # Measured, not claimed. A multipart upload gets its size checked in the request;
        # bytes that went straight to storage can only be checked here, and this is the
        # last point before a paid transcription is queued for them.
        try:
            self._check_size_limit(source_type, size_bytes)
        except ValueError:
            # Nothing references the object yet, so it is pure garbage — drop it rather
            # than leave the tenant paying for storage on a file we refused.
            self.file_storage.delete(storage_key)
            raise

        knowledge_base = self.kb_repo.ensure_default()
        asset = self._persist_queued_asset(
            knowledge_base_id=knowledge_base.id,
            filename=safe_filename,
            build=lambda lineage_id, version: KnowledgeAsset(
                id=asset_id,
                knowledge_base_id=knowledge_base.id,
                lineage_id=lineage_id,
                version=version,
                filename=safe_filename,
                title=safe_filename,
                source_type=source_type.value,
                storage_key=storage_key,
                status=AssetStatus.QUEUED,
                metadata={
                    "filename": safe_filename,
                    "source_type": source_type.value,
                    "content_type": content_type,
                },
            ),
            event_message="Ingestion queued",
        )
        logger.info(
            "ingestion_enqueued",
            knowledge_asset_id=str(asset.id),
            filename=safe_filename,
            direct_upload=True,
        )
        return asset

    def enqueue_url(self, url: str) -> KnowledgeAsset:
        """Fast path (HTTP) for URL sources like YouTube — the file-less sibling of
        `enqueue_ingestion`.

        There are no bytes to store: we resolve the source type, derive a stable identity
        (dedup/display filename + canonical uri + handler hints) *without fetching*, then
        persist a QUEUED asset with an empty `storage_key`. The worker's handler fetches
        the real content in `acquire`. The record/job/enqueue tail is identical to the
        file path.
        """
        source_type = source_type_for_url(url)
        # Fail fast in the request if we can't handle this source type at all.
        self.source_handler_registry.get(source_type)
        filename, source_uri, extra = identity_for_url(source_type, url)
        knowledge_base = self.kb_repo.ensure_default()
        asset_id = uuid4()

        asset = self._persist_queued_asset(
            knowledge_base_id=knowledge_base.id,
            filename=filename,
            build=lambda lineage_id, version: KnowledgeAsset(
                id=asset_id,
                knowledge_base_id=knowledge_base.id,
                lineage_id=lineage_id,
                version=version,
                filename=filename,
                title=filename,
                source_type=source_type.value,
                storage_key="",  # URL sources keep no object-storage file
                status=AssetStatus.QUEUED,
                metadata={
                    "filename": filename,
                    "source_type": source_type.value,
                    "source_uri": source_uri,
                    **extra,
                },
            ),
            event_message=f"Queued from URL: {source_uri}",
        )
        logger.info("ingestion_url_enqueued", knowledge_asset_id=str(asset.id), source_uri=source_uri)
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
        # The asset's FAILED status alone is not enough to say nothing is running. The
        # pipeline marks the asset FAILED *before* re-raising, and the queue's own
        # RetryStrategy only re-schedules after that — so between those two moments a
        # user clicking Retry would enqueue a second job for work already coming back.
        # Both runs are idempotent (chunks and embeddings are replaced, not appended), so
        # the result stayed correct, but the duplicate re-parses and re-embeds the source:
        # real money for nothing. Defer to the queue whenever it still owns the work.
        if job is not None and self._queue_will_retry(job):
            logger.info(
                "ingestion_retry_skipped",
                knowledge_asset_id=str(asset_id),
                reason="queue_retry_pending",
                job_status=str(job.status),
                attempts=job.attempts,
            )
            return asset

        with self.atomic_scope.atomic():
            if job is not None:
                self.job_repo.reset_for_retry(job.id)
            else:
                # Older asset predating the jobs table: create a fresh job for it.
                job = self.job_repo.create(IngestionJob(asset_id=asset_id))

            asset.status = AssetStatus.QUEUED
            asset.error_message = None
            self.asset_repo.update_from_domain(asset)
            self._enqueue(asset_id)
            self._record(asset, "retry", "Retry re-enqueued", job_id=job.id if job else None)
        logger.info("ingestion_retry_enqueued", knowledge_asset_id=str(asset_id))
        return asset

    @staticmethod
    def _queue_will_retry(job: IngestionJob) -> bool:
        """True while the queue still owns this job — a worker has it, or will take it again.

        Note that `JobStatus.FAILED` does **not** mean terminal here: `process_ingestion`
        calls `mark_failed` on *every* failed attempt, and only then re-raises so
        Procrastinate can re-schedule. So a FAILED job is still the queue's until its
        attempt budget is spent — which is why this reads `attempts`, not just `status`.
        `max_attempts` mirrors `RetryStrategy(max_attempts=3)` in queue/tasks.py; the two
        have to be changed together.
        """
        if job.status in (JobStatus.RUNNING, JobStatus.QUEUED):
            return True
        if job.status == JobStatus.SUCCEEDED:
            return False
        return job.attempts < job.max_attempts

    def _check_size_limit(self, source_type: SourceType, size_bytes: int) -> None:
        """Apply the per-source-type size limit, with the same wording as the upload route.

        Only audio has one: it is transcribed by a paid hosted model, so its cost scales
        with length in a way parsing a PDF does not.
        """
        if source_type is not SourceType.AUDIO:
            return
        limit = self.max_audio_upload_bytes
        if size_bytes <= limit:
            return
        raise ValueError(
            f"This audio file is {round(size_bytes / (1024 * 1024))} MB. The limit is "
            f"{round(limit / (1024 * 1024))} MB — try a shorter recording."
        )

    def _persist_queued_asset(
        self,
        *,
        knowledge_base_id: UUID,
        filename: str,
        build: Callable[[UUID, int], KnowledgeAsset],
        event_message: str,
    ) -> KnowledgeAsset:
        """Persist a QUEUED asset with its job and queue row, as one transaction.

        Shared by the file and URL paths, which differ only in how the asset is built.

        Two things here are deliberate. **All three writes are one transaction:** the asset
        row, the job row and the queue row commit together or not at all, so there is no
        window where an asset exists with nothing scheduled to process it. They used to
        commit separately, with the queue row going out on its own connection entirely — a
        crash in either gap left an asset stuck in `queued` forever. The queue table living
        in the same database is what makes the single commit possible.

        **Version conflicts retry once.** Lineage and version are computed *inside* the
        transaction, so a retry recomputes them against whatever the winner committed. Two
        simultaneous uploads of one filename used to both read version n and both write
        n+1, and the constraint failed the loser with a 500; now the loser becomes n+2.
        """
        for attempts_left in (1, 0):
            try:
                with self.atomic_scope.atomic():
                    previous = self.asset_repo.latest_for_filename(knowledge_base_id, filename)
                    lineage_id = previous.lineage_id if previous else uuid4()
                    version = previous.version + 1 if previous else 1

                    asset = self.asset_repo.create_pending(build(lineage_id, version))
                    job = self.job_repo.create(IngestionJob(asset_id=asset.id))
                    self._enqueue(asset.id)
                    self._record(asset, "queued", event_message, job_id=job.id)
                    return asset
            except DuplicateAssetVersionError:
                # One retry, not a loop: a second conflict means something other than a
                # concurrent upload of the same name, and spinning would hide it.
                if not attempts_left:
                    raise
                logger.info("ingestion_version_conflict_retrying", filename=filename)
        raise AssertionError("unreachable")  # pragma: no cover

    def _enqueue(self, asset_id: UUID) -> None:
        # Enqueue carries the current tenant/user so the worker can rebuild context.
        # Runs inside a tenant-scoped request, so the contextvars are set.
        self.job_queue.enqueue_ingestion(
            asset_id, tenant_id=current_tenant_id(), user_id=current_user_id()
        )

    # ------------------------------------------------------------------- worker path

    def process_ingestion(self, asset_id: UUID) -> KnowledgeAsset:
        """Slow path (worker): run the full pipeline for one asset.

        Marks the job running, then runs the state machine (which acquires the source via
        its handler as its first step) and records the terminal job outcome. On failure it
        re-raises `IngestionError` so the queue engine can retry — the asset keeps its
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
        result = self._run_pipeline(asset, handler, job_id)

        if result.status == AssetStatus.FAILED:
            error = result.error_message or "ingestion failed"
            if job is not None:
                failed = self.job_repo.mark_failed(job.id, error)
                # Retries are automatic and quiet; running out of them is not. There is no
                # dead-letter queue to move the job to — Procrastinate leaves an exhausted
                # job sitting in `failed` — so the terminal attempt gets its own error-level
                # row in the durable worker log, and a distinctly-named structlog event an
                # aggregator can alert on. Without this, the only signal that a source will
                # never become ready is a user noticing it never became ready.
                if failed.attempts >= failed.max_attempts:
                    self._record(
                        result,
                        "dead_letter",
                        f"Ingestion failed permanently after {failed.attempts} attempts",
                        level="error",
                        job_id=job.id,
                        data={"attempts": failed.attempts, "failed_step": result.failed_step},
                    )
                    logger.error(
                        "ingestion_attempts_exhausted",
                        knowledge_asset_id=str(result.id),
                        job_id=str(job.id),
                        attempts=failed.attempts,
                        failed_step=result.failed_step,
                        error=error,
                    )
            # Re-raise so Procrastinate re-schedules per its RetryStrategy.
            raise IngestionError(error)

        if job is not None:
            self.job_repo.mark_succeeded(job.id)
        return result

    def _run_pipeline(
        self,
        asset: KnowledgeAsset,
        handler: ISourceHandler,
        job_id: UUID | None,
    ) -> KnowledgeAsset:
        step = "extracting"
        try:
            # `not asset.documents` also forces re-extraction for an asset that failed at a
            # later step but carries nothing to chunk — which is every row ingested before
            # the `documents` column existed (migration 0007 leaves those at `[]`). Without
            # it they would resume straight into "Source produced no indexable text chunks"
            # forever. Re-parsing is idempotent, so this costs time, not correctness.
            if asset.failed_step in (None, "extracting") or not asset.documents:
                asset.status = AssetStatus.EXTRACTING
                asset.failed_step = None
                asset.error_message = None
                self.asset_repo.update_from_domain(asset)
                self._record(asset, step, "Extracting source content", job_id=job_id)
                logger.info("ingestion_step", step=step, knowledge_asset_id=str(asset.id), status=asset.status)
                # Acquire happens here (inside the try) so a fetch failure — e.g. a
                # YouTube video with no captions — routes through the FAILED path below
                # instead of escaping uncaught. Only fetched when extraction is needed,
                # so a retry past extraction skips re-acquiring.
                raw = handler.acquire(asset)
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
