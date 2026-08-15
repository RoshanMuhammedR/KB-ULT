from __future__ import annotations

from pathlib import Path
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, File, HTTPException, Response, UploadFile, status
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session

from src.core.config import get_settings
from src.domain.entities import IngestionJob
from src.domain.interfaces import IFileStorage
from src.ingestion.source_types import AUDIO_EXTENSIONS
from src.http.dependencies import get_file_storage, get_ingestion_service
from src.infrastructure.repositories import (
    ChunkRepository,
    ConversationRepository,
    IngestionJobEventRepository,
    IngestionJobRepository,
    KnowledgeAssetRepository,
    KnowledgeBaseRepository,
)
from src.infrastructure.database.session import get_db
from src.application.ingestion.service import IngestionService
from src.http.schemas.documents import (
    AssetCitationSchema,
    IngestUrlRequest,
    IngestionJobSchema,
    KnowledgeAssetSchema,
    PassageSchema,
    RenameKnowledgeAssetRequest,
)
from src.http.schemas.jobs import JobEventSchema

router = APIRouter(prefix="/documents", tags=["documents"])


def _megabytes(size_bytes: int) -> int:
    return round(size_bytes / (1024 * 1024))


# Signed URLs embedded in a detail response are rendered straight into the DOM — an <a href>
# the user clicks minutes later, or an <audio src> whose playback starts long after load.
# Those cannot carry an Authorization header, so they must be pre-signed and must outlive the
# render. 15 minutes is the window the UI needs; it is deliberately far longer than the 60s
# default, and is why these are issued only for a single asset the caller already fetched
# rather than for every row of a list.
_DETAIL_URL_TTL_SECONDS = 900


def _to_schema(
    asset,
    file_storage: IFileStorage | None = None,
    job: IngestionJob | None = None,
    passage_count: int = 0,
) -> KnowledgeAssetSchema:
    """Map an asset row to its wire schema.

    Pass `file_storage` only when the caller actually needs signed URLs. Signing is cheap
    (a local HMAC, no network call) but the URLs are bearer credentials with a 60s life, so
    minting one per row on every list read hands out dozens of short-lived grants nobody
    asked for. List endpoints therefore omit it and the client calls
    `GET /documents/{id}/download` when the user actually clicks something.
    """
    download_url = None
    transcript_url = None
    if file_storage is not None:
        if asset.storage_key:
            download_url = file_storage.get_presigned_url(
                asset.storage_key, _DETAIL_URL_TTL_SECONDS
            )
        # Audio sources store a readable transcript.md beside the original; the viewer
        # shows it alongside the player.
        transcript_key = (asset.metadata or {}).get("transcript_key")
        if transcript_key:
            transcript_url = file_storage.get_presigned_url(
                transcript_key, _DETAIL_URL_TTL_SECONDS
            )
    return KnowledgeAssetSchema(
        id=asset.id,
        knowledge_base_id=asset.knowledge_base_id,
        lineage_id=asset.lineage_id,
        version=asset.version,
        filename=asset.filename,
        title=asset.title,
        source_type=asset.source_type,
        storage_key=asset.storage_key,
        download_url=download_url,
        transcript_url=transcript_url,
        status=asset.status.value,
        failed_step=asset.failed_step,
        error_message=asset.error_message,
        metadata=asset.metadata,
        passage_count=passage_count,
        job=(
            IngestionJobSchema(
                status=job.status.value,
                attempts=job.attempts,
                max_attempts=job.max_attempts,
                last_error=job.last_error,
            )
            if job is not None
            else None
        ),
        superseded_at=asset.superseded_at,
        created_at=asset.created_at,
        updated_at=asset.updated_at,
    )


@router.get("", response_model=list[KnowledgeAssetSchema])
def list_assets(
    db: Annotated[Session, Depends(get_db)],
) -> list[KnowledgeAssetSchema]:
    kb = KnowledgeBaseRepository(db).ensure_default()
    assets = KnowledgeAssetRepository(db).list_current(kb.id)
    # One grouped count for the whole list, rather than a query per row.
    counts = ChunkRepository(db).count_by_asset([asset.id for asset in assets])
    # No `file_storage`: the library list renders names and statuses, not file contents, so
    # it needs no signed URLs. Clicking through to a source calls /download for one.
    return [_to_schema(asset, passage_count=counts.get(asset.id, 0)) for asset in assets]


@router.get("/{asset_id}", response_model=KnowledgeAssetSchema)
def get_asset(
    asset_id: UUID,
    db: Annotated[Session, Depends(get_db)],
    file_storage: Annotated[IFileStorage, Depends(get_file_storage)],
) -> KnowledgeAssetSchema:
    # Single-asset read used by the frontend to poll ingestion progress. Includes the
    # latest job so the UI can render attempt count and the last error.
    asset = KnowledgeAssetRepository(db).get(asset_id)
    if asset is None:
        raise HTTPException(status_code=404, detail="KnowledgeAsset not found")
    job = IngestionJobRepository(db).latest_for_asset(asset_id)
    counts = ChunkRepository(db).count_by_asset([asset.id])
    return _to_schema(asset, file_storage, job, passage_count=counts.get(asset.id, 0))


@router.get("/{asset_id}/download")
def download_asset(
    asset_id: UUID,
    db: Annotated[Session, Depends(get_db)],
    file_storage: Annotated[IFileStorage, Depends(get_file_storage)],
    transcript: bool = False,
) -> Response:
    """Mint a short-lived signed URL for one asset's file and redirect to it.

    The signed URL is a bearer credential — anyone holding it reads the object without
    presenting a token — so it is issued here, per click, behind the tenant guard, rather
    than embedded in every list response. `Cache-Control: private, max-age=45` sits just
    inside the 60s signature so a reload within a session reuses the redirect instead of
    re-signing, while never outliving the URL it points at.

    `?transcript=true` returns the readable transcript.md that audio sources write beside
    the original, rather than the media file.
    """
    # Repository reads run under the tenant guard, so another tenant's id 404s here rather
    # than reaching the signing call.
    asset = KnowledgeAssetRepository(db).get(asset_id)
    if asset is None:
        raise HTTPException(status_code=404, detail="KnowledgeAsset not found")

    if transcript:
        key = (asset.metadata or {}).get("transcript_key")
        if not key:
            raise HTTPException(status_code=404, detail="This source has no transcript file")
    else:
        key = asset.storage_key
        if not key:
            # URL sources (YouTube) store no file — there is nothing to download.
            raise HTTPException(status_code=404, detail="This source has no downloadable file")

    return RedirectResponse(
        url=file_storage.get_presigned_url(key),
        status_code=status.HTTP_307_TEMPORARY_REDIRECT,
        headers={"Cache-Control": "private, max-age=45"},
    )


@router.get("/{asset_id}/events", response_model=list[JobEventSchema])
def list_asset_events(
    asset_id: UUID,
    db: Annotated[Session, Depends(get_db)],
) -> list[JobEventSchema]:
    # The persisted worker log for one asset (all attempts), expanded in the /jobs
    # dashboard. Ordered oldest-first by the repository.
    events = IngestionJobEventRepository(db).list_for_asset(asset_id)
    return [
        JobEventSchema(
            id=event.id,
            event=event.event,
            level=event.level,
            message=event.message,
            data=event.data,
            ts=event.ts,
        )
        for event in events
    ]


@router.get("/{asset_id}/passages", response_model=list[PassageSchema])
def list_passages(
    asset_id: UUID,
    db: Annotated[Session, Depends(get_db)],
    around: int | None = None,
    window: int = 2,
) -> list[PassageSchema]:
    """The passages of a source, optionally narrowed to a neighbourhood of one chunk.

    This is what makes a citation openable: the viewer shows the cited passage with the
    text either side of it, so a quote can be read in context rather than in isolation.
    Omit `around` to get the whole source.
    """
    chunks = ChunkRepository(db).list_for_asset(asset_id)
    if around is not None:
        low = around - max(0, window)
        high = around + max(0, window)
        chunks = [chunk for chunk in chunks if low <= chunk.chunk_index <= high]

    return [
        PassageSchema(
            chunk_index=chunk.chunk_index,
            text=chunk.text,
            locator=chunk.metadata.get("locator"),
        )
        for chunk in chunks
    ]


@router.get("/{asset_id}/citations", response_model=list[AssetCitationSchema])
def list_asset_citations(
    asset_id: UUID,
    db: Annotated[Session, Depends(get_db)],
) -> list[AssetCitationSchema]:
    """Every persisted answer that cited this source — the "answers that cited this" panel.

    A JSONB containment query against the GIN index on `messages.citations`, so it stays
    cheap as the thread history grows.
    """
    rows = ConversationRepository(db).find_by_cited_asset(asset_id)
    return [
        AssetCitationSchema(
            conversation_id=conversation_id,
            conversation_title=title,
            locator=citation.get("locator"),
            chunk_index=citation.get("chunk_index"),
            score=citation.get("score"),
            excerpt=citation.get("excerpt"),
        )
        for conversation_id, title, citation in rows
    ]


@router.post("/upload", response_model=KnowledgeAssetSchema, status_code=status.HTTP_202_ACCEPTED)
async def upload_document(
    ingestion_service: Annotated[IngestionService, Depends(get_ingestion_service)],
    file_storage: Annotated[IFileStorage, Depends(get_file_storage)],
    file: UploadFile = File(...),
) -> KnowledgeAssetSchema:
    # Accepts the upload, stores it, and enqueues the ingestion job — then returns
    # 202 immediately with a `queued` asset. The heavy pipeline runs in the worker;
    # the client polls GET /documents/{id} for progress.
    if not file.filename:
        raise HTTPException(status_code=400, detail="Uploaded file must include a filename")

    file_data = await file.read()

    # Audio is transcribed by a paid hosted model, so it alone carries a size cap.
    if Path(file.filename).suffix.lower() in AUDIO_EXTENSIONS:
        limit = get_settings().max_audio_upload_bytes
        if len(file_data) > limit:
            raise HTTPException(
                status_code=400,
                detail=(
                    f"This audio file is {_megabytes(len(file_data))} MB. "
                    f"The limit is {_megabytes(limit)} MB — try a shorter recording."
                ),
            )

    try:
        asset = ingestion_service.enqueue_ingestion(
            file_data,
            Path(file.filename).name,
            file.content_type,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return _to_schema(asset, file_storage)


@router.post("/ingest-url", response_model=KnowledgeAssetSchema, status_code=status.HTTP_202_ACCEPTED)
def ingest_url(
    request: IngestUrlRequest,
    ingestion_service: Annotated[IngestionService, Depends(get_ingestion_service)],
    file_storage: Annotated[IFileStorage, Depends(get_file_storage)],
) -> KnowledgeAssetSchema:
    # URL sources (YouTube today) have no upload: resolve + queue, then return 202. The
    # worker fetches the transcript. Client polls GET /documents/{id} like an upload.
    try:
        asset = ingestion_service.enqueue_url(request.url)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return _to_schema(asset, file_storage)


@router.post("/{asset_id}/retry", response_model=KnowledgeAssetSchema, status_code=status.HTTP_202_ACCEPTED)
def retry_asset(
    asset_id: UUID,
    ingestion_service: Annotated[IngestionService, Depends(get_ingestion_service)],
    file_storage: Annotated[IFileStorage, Depends(get_file_storage)],
) -> KnowledgeAssetSchema:
    # Re-enqueue a failed asset. No re-upload: the worker re-downloads the source and
    # resumes from the step that failed.
    try:
        asset = ingestion_service.retry(asset_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return _to_schema(asset, file_storage)



@router.patch("/{asset_id}", response_model=KnowledgeAssetSchema)
def rename_asset(
    asset_id: UUID,
    request: RenameKnowledgeAssetRequest,
    db: Annotated[Session, Depends(get_db)],
    file_storage: Annotated[IFileStorage, Depends(get_file_storage)],
) -> KnowledgeAssetSchema:
    try:
        asset = KnowledgeAssetRepository(db).rename(asset_id, request.title)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return _to_schema(asset, file_storage)


@router.delete("/{asset_id}", status_code=204)
def delete_asset(
    asset_id: UUID,
    db: Annotated[Session, Depends(get_db)],
    file_storage: Annotated[IFileStorage, Depends(get_file_storage)],
) -> None:
    repo = KnowledgeAssetRepository(db)
    asset = repo.get(asset_id)
    if asset is None:
        raise HTTPException(status_code=404, detail="KnowledgeAsset not found")
    if asset.storage_key:
        file_storage.delete(asset.storage_key)
    repo.delete(asset_id)
