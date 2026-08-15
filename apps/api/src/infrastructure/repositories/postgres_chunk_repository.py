from __future__ import annotations

from uuid import UUID, uuid4

from sqlalchemy import delete, func, select
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

    def count_by_asset(self, asset_ids: list[UUID]) -> dict[UUID, int]:
        """Passage counts for many assets in one query — the library list needs all of them."""
        if not asset_ids:
            return {}
        rows = self.db.execute(
            select(ChunkModel.knowledge_asset_id, func.count(ChunkModel.id))
            .where(ChunkModel.knowledge_asset_id.in_(asset_ids))
            .group_by(ChunkModel.knowledge_asset_id)
        ).all()
        return {asset_id: int(count) for asset_id, count in rows}

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
            # A failed flush leaves the Session transaction unusable until it is rolled back.
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
            # A failed flush leaves the Session transaction unusable until it is rolled back.
            self.db.rollback()
            raise

    def query_ready_chunks(
        self,
        query_embedding: list[float],
        knowledge_base_id: UUID,
        top_k: int,
    ) -> list[tuple[ChunkModel, KnowledgeAssetModel, float]]:
        """Dense arm: nearest neighbours by cosine similarity."""
        distance = EmbeddingModel.vector.cosine_distance(query_embedding)
        rows = self.db.execute(
            self._ready_chunks_base(knowledge_base_id, distance)
            .order_by(distance)
            .limit(top_k)
        ).all()
        return [(chunk, asset, float(score)) for chunk, asset, score in rows]

    def query_ready_chunks_lexical(
        self,
        query_embedding: list[float],
        query_text: str,
        knowledge_base_id: UUID,
        top_k: int,
    ) -> list[tuple[ChunkModel, KnowledgeAssetModel, float]]:
        """Lexical arm: chunks containing the query's terms, ranked by `ts_rank_cd`.

        Returns the *same tuple shape* as the dense arm, cosine score included, so everything
        downstream — the score threshold, the prompt's `score=` label, the citation relevance
        percentage — works identically whichever arm surfaced a chunk. The similarity is
        computed as a selected column rather than an ordering, so it is an exact calculation
        over at most `top_k` rows and never touches the vector index.

        `websearch_to_tsquery` is used over `plainto_tsquery` because it understands quoted
        phrases and never raises on punctuation a user happens to type. It ANDs the terms, so
        a long conversational question often matches nothing here — that is intended. This arm
        exists to catch the exact identifier, error code or proper noun that embeddings miss;
        when it has nothing to say it stays silent and the dense arm carries the query alone.
        """
        if not query_text.strip():
            return []

        distance = EmbeddingModel.vector.cosine_distance(query_embedding)
        tsquery = func.websearch_to_tsquery("english", query_text)
        rows = self.db.execute(
            self._ready_chunks_base(knowledge_base_id, distance)
            .where(ChunkModel.fts.op("@@")(tsquery))
            .order_by(func.ts_rank_cd(ChunkModel.fts, tsquery).desc())
            .limit(top_k)
        ).all()
        return [(chunk, asset, float(score)) for chunk, asset, score in rows]

    @staticmethod
    def _ready_chunks_base(knowledge_base_id: UUID, distance):
        """Shared skeleton of both arms: same joins, same visibility rules, same columns.

        Built with ORM `select()` constructs rather than raw SQL on purpose. The tenant filter
        is injected by the `do_orm_execute` listener, which only fires for ORM statements — a
        raw-SQL or CTE query would silently escape it and leave only RLS, which is dormant
        whenever `APP_DATABASE_URL` is unset. Keeping both arms as plain ORM selects means
        they inherit exactly the isolation the existing search already had.
        """
        return (
            select(ChunkModel, KnowledgeAssetModel, (1 - distance).label("score"))
            .join(EmbeddingModel, EmbeddingModel.chunk_id == ChunkModel.id)
            .join(KnowledgeAssetModel, KnowledgeAssetModel.id == ChunkModel.knowledge_asset_id)
            .options(joinedload(ChunkModel.asset))
            .where(KnowledgeAssetModel.knowledge_base_id == knowledge_base_id)
            .where(KnowledgeAssetModel.superseded_at.is_(None))
            .where(KnowledgeAssetModel.status == AssetStatus.READY.value)
        )
