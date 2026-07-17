from src.domain.entities import (
    AssetStatus,
    Chunk,
    IngestionJob,
    JobEvent,
    JobStatus,
    KnowledgeAsset,
    KnowledgeBase,
)
from src.infrastructure.database.models import (
    ChunkModel,
    IngestionJobEventModel,
    IngestionJobModel,
    KnowledgeAssetModel,
    KnowledgeBaseModel,
)


def kb_to_domain(model: KnowledgeBaseModel) -> KnowledgeBase:
    return KnowledgeBase(
        id=model.id,
        name=model.name,
        owner_id=model.owner_id,
        created_at=model.created_at,
        updated_at=model.updated_at,
    )


def asset_to_domain(model: KnowledgeAssetModel) -> KnowledgeAsset:
    return KnowledgeAsset(
        id=model.id,
        knowledge_base_id=model.knowledge_base_id,
        lineage_id=model.lineage_id,
        version=model.version,
        filename=model.filename,
        title=model.title,
        source_type=model.source_type,
        storage_key=model.storage_key,
        status=AssetStatus(model.status),
        failed_step=model.failed_step,
        error_message=model.error_message,
        text_content=model.text_content,
        metadata=model.metadata_ or {},
        superseded_at=model.superseded_at,
        created_at=model.created_at,
        updated_at=model.updated_at,
    )


def job_to_domain(model: IngestionJobModel) -> IngestionJob:
    return IngestionJob(
        id=model.id,
        asset_id=model.asset_id,
        job_type=model.job_type,
        status=JobStatus(model.status),
        attempts=model.attempts,
        max_attempts=model.max_attempts,
        last_error=model.last_error,
        scheduled_at=model.scheduled_at,
        started_at=model.started_at,
        finished_at=model.finished_at,
        created_at=model.created_at,
        updated_at=model.updated_at,
    )


def event_to_domain(model: IngestionJobEventModel) -> JobEvent:
    return JobEvent(
        id=model.id,
        asset_id=model.asset_id,
        job_id=model.job_id,
        level=model.level,
        event=model.event,
        message=model.message,
        data=model.data_ or {},
        ts=model.ts,
    )


def chunk_to_domain(model: ChunkModel) -> Chunk:
    return Chunk(
        id=model.id,
        knowledge_asset_id=model.knowledge_asset_id,
        chunk_index=model.chunk_index,
        text=model.text,
        metadata=model.metadata_ or {},
        created_at=model.created_at,
    )
