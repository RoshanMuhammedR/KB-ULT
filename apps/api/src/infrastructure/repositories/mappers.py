from src.domain.entities import AssetStatus, Chunk, KnowledgeAsset, KnowledgeBase
from src.infrastructure.database.models import ChunkModel, KnowledgeAssetModel, KnowledgeBaseModel


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


def chunk_to_domain(model: ChunkModel) -> Chunk:
    return Chunk(
        id=model.id,
        knowledge_asset_id=model.knowledge_asset_id,
        chunk_index=model.chunk_index,
        text=model.text,
        metadata=model.metadata_ or {},
        created_at=model.created_at,
    )
