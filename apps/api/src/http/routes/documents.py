from __future__ import annotations

from pathlib import Path
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from sqlalchemy.orm import Session

from src.domain.entities import IngestionJob
from src.domain.interfaces import IFileStorage
from src.http.dependencies import get_file_storage, get_ingestion_service
from src.infrastructure.repositories import (
    IngestionJobEventRepository,
    IngestionJobRepository,
    KnowledgeAssetRepository,
    KnowledgeBaseRepository,
)
from src.infrastructure.database.session import get_db
from src.application.ingestion.service import IngestionService
from src.http.schemas.documents import (
    IngestionJobSchema,
    KnowledgeAssetSchema,
    RenameKnowledgeAssetRequest,
)
from src.http.schemas.jobs import JobEventSchema

router = APIRouter(prefix="/documents", tags=["documents"])


def _to_schema(
    asset,
    file_storage: IFileStorage | None = None,
    job: IngestionJob | None = None,
) -> KnowledgeAssetSchema:
    download_url = None
    if file_storage is not None and asset.storage_key:
        download_url = file_storage.get_presigned_url(asset.storage_key)
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
        status=asset.status.value,
        failed_step=asset.failed_step,
        error_message=asset.error_message,
        metadata=asset.metadata,
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
    file_storage: Annotated[IFileStorage, Depends(get_file_storage)],
) -> list[KnowledgeAssetSchema]:
    kb = KnowledgeBaseRepository(db).ensure_default()
    assets = KnowledgeAssetRepository(db).list_current(kb.id)
    return [_to_schema(asset, file_storage) for asset in assets]


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
    return _to_schema(asset, file_storage, job)


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

    try:
        asset = ingestion_service.enqueue_ingestion(
            file_data,
            Path(file.filename).name,
            file.content_type,
        )
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
