from __future__ import annotations

from uuid import UUID, uuid4

from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased, joinedload

from src.core.text import sanitize_json_for_storage, sanitize_text_for_storage
from src.domain.entities import AssetStatus, Chunk, Embedding
from src.infrastructure.database.models import ChunkModel, EmbeddingModel, KnowledgeAssetModel
from src.infrastructure.repositories.mappers import chunk_to_domain
from src.infrastructure.repositories.unit_of_work import commit_or_flush


class ChunkRepository:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def replace_for_asset(self, asset_id: UUID, chunks: list[Chunk]) -> list[Chunk]:
        await self.db.execute(delete(ChunkModel).where(ChunkModel.knowledge_asset_id == asset_id))
        models: list[ChunkModel] = []
        # Relies on the chunker emitting each parent before its own children: ids are
        # assigned client-side and the whole batch flushes as one unit, so the self-FK on
        # `parent_id` is satisfied without ordering the INSERTs by hand. A reordering that
        # broke that invariant would surface as a foreign-key violation here.
        for chunk in chunks:
            model = ChunkModel(
                id=chunk.id or uuid4(),
                knowledge_asset_id=asset_id,
                chunk_index=chunk.chunk_index,
                text=sanitize_text_for_storage(chunk.text),
                metadata_=sanitize_json_for_storage(chunk.metadata),
                parent_id=chunk.parent_id,
                # Model-generated, so it needs the same NUL-stripping as `text`. Stored as
                # NULL rather than "" to match the column default; `text_for_embedding`
                # treats both as "embed `text` as-is".
                embed_text=sanitize_text_for_storage(chunk.embed_text) or None,
                modality=chunk.modality,
            )
            self.db.add(model)
            models.append(model)
        await self._commit()
        for model in models:
            await self.db.refresh(model)
        return [chunk_to_domain(model) for model in models]

    @staticmethod
    def _leaves_only(stmt):
        """Restrict a chunk query to leaves — the passages a reader actually sees.

        Parent sections live in the same table but are an internal retrieval artefact: they
        are never embedded, never cited, and counting them would inflate a source's passage
        count by however many sections it has.

        Expressed as "has no children" rather than "parent_id IS NOT NULL" so that chunks
        written before the hierarchy existed still count as leaves — they have no parent and
        no children, and they are exactly what the reader used to see.
        """
        child = aliased(ChunkModel)
        return stmt.where(
            ~select(child.id).where(child.parent_id == ChunkModel.id).exists()
        )

    async def count_by_asset(self, asset_ids: list[UUID]) -> dict[UUID, int]:
        """Passage counts for many assets in one query — the library list needs all of them."""
        if not asset_ids:
            return {}
        rows = (await self.db.execute(
            self._leaves_only(
                select(ChunkModel.knowledge_asset_id, func.count(ChunkModel.id))
                .where(ChunkModel.knowledge_asset_id.in_(asset_ids))
            ).group_by(ChunkModel.knowledge_asset_id)
        )).all()
        return {asset_id: int(count) for asset_id, count in rows}

    async def list_for_asset(self, asset_id: UUID) -> list[Chunk]:
        rows = (await self.db.scalars(
            self._leaves_only(
                select(ChunkModel).where(ChunkModel.knowledge_asset_id == asset_id)
            ).order_by(ChunkModel.chunk_index)
        )).all()
        return [chunk_to_domain(row) for row in rows]

    async def list_parents(self, parent_ids: list[UUID]) -> dict[UUID, Chunk]:
        """The parent sections for a set of matched children, keyed by id.

        Small-to-big retrieval: the child is what matched, the parent is what the model
        reads. Returned as a dict because the caller resolves each document's own parent
        rather than iterating a list.

        An ORM `select`, never `Session.get` — a `get` that hits the identity map returns
        the row without emitting a statement, which means the tenant filter in
        `do_orm_execute` never runs for it.
        """
        if not parent_ids:
            return {}
        rows = (await self.db.scalars(
            select(ChunkModel).where(ChunkModel.id.in_(parent_ids))
        )).all()
        return {row.id: chunk_to_domain(row) for row in rows}

    async def list_all_for_asset(self, asset_id: UUID) -> list[Chunk]:
        """Every chunk including parents — for the pipeline resuming after chunking."""
        rows = (await self.db.scalars(
            select(ChunkModel)
            .where(ChunkModel.knowledge_asset_id == asset_id)
            .order_by(ChunkModel.chunk_index)
        )).all()
        return [chunk_to_domain(row) for row in rows]

    async def _commit(self) -> None:
        # Commits on its own, unless the caller opened a `unit_of_work` — then this
        # flushes and the enclosing scope owns the single COMMIT. See unit_of_work.py.
        await commit_or_flush(self.db)


class EmbeddingRepository:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def replace_for_chunks(self, chunks: list[Chunk], embeddings: list[Embedding]) -> None:
        chunk_ids = [chunk.id for chunk in chunks]
        if chunk_ids:
            await self.db.execute(delete(EmbeddingModel).where(EmbeddingModel.chunk_id.in_(chunk_ids)))
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
        await self._commit()

    async def _commit(self) -> None:
        # Commits on its own, unless the caller opened a `unit_of_work` — then this
        # flushes and the enclosing scope owns the single COMMIT. See unit_of_work.py.
        await commit_or_flush(self.db)

    async def query_ready_chunks(
        self,
        query_embedding: list[float],
        knowledge_base_ids: list[UUID],
        top_k: int,
    ) -> list[tuple[ChunkModel, KnowledgeAssetModel, float]]:
        """Dense arm: nearest neighbours by cosine similarity."""
        distance = EmbeddingModel.vector.cosine_distance(query_embedding)
        rows = (await self.db.execute(
            self._ready_chunks_base(knowledge_base_ids, distance)
            .order_by(distance)
            .limit(top_k)
        )).all()
        return [(chunk, asset, float(score)) for chunk, asset, score in rows]

    async def query_ready_chunks_lexical(
        self,
        query_embedding: list[float],
        query_text: str,
        knowledge_base_ids: list[UUID],
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
        rows = (await self.db.execute(
            self._ready_chunks_base(knowledge_base_ids, distance)
            .where(ChunkModel.fts.op("@@")(tsquery))
            .order_by(func.ts_rank_cd(ChunkModel.fts, tsquery).desc())
            .limit(top_k)
        )).all()
        return [(chunk, asset, float(score)) for chunk, asset, score in rows]

    @staticmethod
    def _ready_chunks_base(knowledge_base_ids: list[UUID], distance):
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
            # `IN`, not `==`: a chat can have several bases attached at once. Postgres
            # plans this as a bitmap over the same `knowledge_base_id` index, so the HNSW
            # scan on `embeddings` is unaffected — the vector index is reached through the
            # join either way.
            .where(KnowledgeAssetModel.knowledge_base_id.in_(knowledge_base_ids))
            .where(KnowledgeAssetModel.superseded_at.is_(None))
            .where(KnowledgeAssetModel.status == AssetStatus.READY.value)
        )
