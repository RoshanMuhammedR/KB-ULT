from __future__ import annotations

from uuid import UUID, uuid4

from sqlalchemy import delete, select
from sqlalchemy.orm import Session, joinedload

from src.core.text import sanitize_json_for_storage, sanitize_text_for_storage
from src.domain.entities import AssetStatus, Chunk, Embedding
from src.infrastructure.database.models import ChunkModel, EmbeddingModel, KnowledgeAssetModel
from src.infrastructure.repositories.mappers import chunk_to_domain


class ChunkRepository:
    def __init__(self, db: Session) -> None:
        self.db = db

    def replace_for_asset(self, asset_id: UUID, chunks: list[Chunk]) -> list[Chunk]:
        self.db.execute(delete(ChunkModel).where(ChunkModel.knowledge_asset_id == asset_id))
        models: list[ChunkModel] = []
        for chunk in chunks:
            model = ChunkModel(
                id=chunk.id or uuid4(),
                knowledge_asset_id=asset_id,
                chunk_index=chunk.chunk_index,
                text=sanitize_text_for_storage(chunk.text),
                metadata_=sanitize_json_for_storage(chunk.metadata),
            )
            self.db.add(model)
            models.append(model)
        self._commit()
        for model in models:
            self.db.refresh(model)
        return [chunk_to_domain(model) for model in models]

    def list_for_asset(self, asset_id: UUID) -> list[Chunk]:
        rows = self.db.scalars(
            select(ChunkModel)
            .where(ChunkModel.knowledge_asset_id == asset_id)
            .order_by(ChunkModel.chunk_index)
        ).all()
        return [chunk_to_domain(row) for row in rows]

    def _commit(self) -> None:
        try:
            self.db.commit()
        except Exception:
            self.db.rollback()
            raise


class EmbeddingRepository:
    def __init__(self, db: Session) -> None:
        self.db = db

    def replace_for_chunks(self, chunks: list[Chunk], embeddings: list[Embedding]) -> None:
        chunk_ids = [chunk.id for chunk in chunks]
        if chunk_ids:
            self.db.execute(delete(EmbeddingModel).where(EmbeddingModel.chunk_id.in_(chunk_ids)))
        for chunk, embedding in zip(chunks, embeddings, strict=True):
            self.db.add(
                EmbeddingModel(
                    id=embedding.id,
                    chunk_id=chunk.id,
                    model=embedding.model,
                    dimensions=embedding.dimensions,
                    vector=embedding.vector,
                )
            )
        self._commit()

    def _commit(self) -> None:
        try:
            self.db.commit()
        except Exception:
            self.db.rollback()
            raise

    def query_ready_chunks(
        self,
        query_embedding: list[float],
        knowledge_base_id: UUID,
        top_k: int,
    ) -> list[tuple[ChunkModel, KnowledgeAssetModel, float]]:
        distance = EmbeddingModel.vector.cosine_distance(query_embedding)
        rows = self.db.execute(
            select(ChunkModel, KnowledgeAssetModel, (1 - distance).label("score"))
            .join(EmbeddingModel, EmbeddingModel.chunk_id == ChunkModel.id)
            .join(KnowledgeAssetModel, KnowledgeAssetModel.id == ChunkModel.knowledge_asset_id)
            .options(joinedload(ChunkModel.asset))
            .where(KnowledgeAssetModel.knowledge_base_id == knowledge_base_id)
            .where(KnowledgeAssetModel.superseded_at.is_(None))
            .where(KnowledgeAssetModel.status == AssetStatus.READY.value)
            .order_by(distance)
            .limit(top_k)
        ).all()
        return [(chunk, asset, float(score)) for chunk, asset, score in rows]
