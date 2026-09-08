from __future__ import annotations

from collections.abc import Iterable
from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import delete, desc, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.exceptions import DuplicateAssetVersionError
from src.core.text import sanitize_json_for_storage, sanitize_text_for_storage
from src.domain.entities import KnowledgeAsset
from src.infrastructure.database.models import KnowledgeAssetModel
from src.infrastructure.repositories.mappers import asset_to_domain, documents_to_storage
from src.infrastructure.repositories.unit_of_work import commit_or_flush


class KnowledgeAssetRepository:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def count_by_knowledge_base(self) -> dict[UUID, int]:
        """Current source counts for every base in the tenant, in one query.

        The base switcher shows them, and a per-base round trip would make opening a menu
        cost one query per base. Superseded versions are excluded for the same reason the
        library list excludes them: they are history, not contents.
        """
        rows = (await self.db.execute(
            select(
                KnowledgeAssetModel.knowledge_base_id,
                func.count(KnowledgeAssetModel.id),
            )
            .where(KnowledgeAssetModel.superseded_at.is_(None))
            .group_by(KnowledgeAssetModel.knowledge_base_id)
        )).all()
        return {kb_id: int(count) for kb_id, count in rows}

    async def list_current(self, knowledge_base_id: UUID) -> list[KnowledgeAsset]:
        rows = (await self.db.scalars(
            select(KnowledgeAssetModel)
            .where(KnowledgeAssetModel.knowledge_base_id == knowledge_base_id)
            .where(KnowledgeAssetModel.superseded_at.is_(None))
            .order_by(desc(KnowledgeAssetModel.created_at))
        )).all()
        return [asset_to_domain(row) for row in rows]

    async def get(self, asset_id: UUID) -> KnowledgeAsset | None:
        # select().where(pk) rather than Session.get(): Session.get() can serve from the
        # identity map and bypasses the tenant auto-filter, so a cross-tenant id would leak.
        row = await self.db.scalar(select(KnowledgeAssetModel).where(KnowledgeAssetModel.id == asset_id))
        return asset_to_domain(row) if row else None

    async def get_many(self, asset_ids: Iterable[UUID]) -> dict[UUID, KnowledgeAsset]:
        """Fetch several assets by id in one query, keyed by id.

        For list endpoints that need a field from each row's asset: one `IN (...)` instead
        of one SELECT per row. Missing ids are simply absent from the mapping — the tenant
        filter applies here as everywhere, so another tenant's id looks identical to a
        deleted one.
        """
        ids = list(asset_ids)
        if not ids:
            return {}
        rows = (await self.db.scalars(
            select(KnowledgeAssetModel).where(KnowledgeAssetModel.id.in_(ids))
        )).all()
        return {row.id: asset_to_domain(row) for row in rows}

    async def get_model(self, asset_id: UUID) -> KnowledgeAssetModel | None:
        # Same reason as get(): stay on select() so the tenant filter applies.
        return await self.db.scalar(select(KnowledgeAssetModel).where(KnowledgeAssetModel.id == asset_id))

    async def latest_for_filename(self, knowledge_base_id: UUID, filename: str) -> KnowledgeAsset | None:
        row = await self.db.scalar(
            select(KnowledgeAssetModel)
            .where(KnowledgeAssetModel.knowledge_base_id == knowledge_base_id)
            .where(KnowledgeAssetModel.filename == filename)
            .order_by(desc(KnowledgeAssetModel.version))
            .limit(1)
        )
        return asset_to_domain(row) if row else None

    async def create_pending(self, asset: KnowledgeAsset) -> KnowledgeAsset:
        model = KnowledgeAssetModel(
            id=asset.id,
            knowledge_base_id=asset.knowledge_base_id,
            lineage_id=asset.lineage_id,
            version=asset.version,
            filename=asset.filename,
            title=self._sanitize_optional_text(asset.title),
            source_type=asset.source_type,
            storage_key=asset.storage_key,
            status=asset.status.value,
            failed_step=asset.failed_step,
            error_message=asset.error_message,
            text_content=self._sanitize_optional_text(asset.text_content),
            metadata_=sanitize_json_for_storage(asset.metadata),
            documents=self._documents(asset),
            superseded_at=asset.superseded_at,
        )
        self.db.add(model)
        try:
            await self._commit()
        except IntegrityError as exc:
            # Two concurrent uploads of the same filename both read the same "latest"
            # version and both computed n+1. The constraint keeps the data correct; this
            # turns "the database said no" into something the caller can act on, instead
            # of an opaque 500 for what is really a retryable race.
            if "uq_asset_lineage_version" in str(exc.orig):
                raise DuplicateAssetVersionError(
                    f"version {asset.version} of this source already exists"
                ) from exc
            raise
        await self.db.refresh(model)
        return asset_to_domain(model)

    async def update_from_domain(self, asset: KnowledgeAsset) -> KnowledgeAsset:
        model = await self.get_model(asset.id)
        if model is None:
            raise ValueError(f"KnowledgeAsset not found: {asset.id}")
        model.title = self._sanitize_optional_text(asset.title)
        model.storage_key = asset.storage_key
        model.status = asset.status.value
        model.failed_step = asset.failed_step
        model.error_message = asset.error_message
        model.text_content = self._sanitize_optional_text(asset.text_content)
        model.metadata_ = sanitize_json_for_storage(asset.metadata)
        model.documents = self._documents(asset)
        model.superseded_at = asset.superseded_at
        await self._commit()
        await self.db.refresh(model)
        return asset_to_domain(model)

    async def rename(self, asset_id: UUID, title: str) -> KnowledgeAsset:
        model = await self.get_model(asset_id)
        if model is None:
            raise ValueError(f"KnowledgeAsset not found: {asset_id}")
        model.title = sanitize_text_for_storage(title)
        await self._commit()
        await self.db.refresh(model)
        return asset_to_domain(model)

    async def supersede_previous_versions(self, lineage_id: UUID, active_asset_id: UUID) -> None:
        rows = (await self.db.scalars(
            select(KnowledgeAssetModel)
            .where(KnowledgeAssetModel.lineage_id == lineage_id)
            .where(KnowledgeAssetModel.id != active_asset_id)
            .where(KnowledgeAssetModel.superseded_at.is_(None))
        )).all()
        now = datetime.now(UTC)
        for row in rows:
            row.superseded_at = now
        await self._commit()

    async def delete(self, asset_id: UUID) -> None:
        await self.db.execute(delete(KnowledgeAssetModel).where(KnowledgeAssetModel.id == asset_id))
        await self._commit()

    async def _commit(self) -> None:
        # Commits on its own, unless the caller opened a `unit_of_work` — then this
        # flushes and the enclosing scope owns the single COMMIT. See unit_of_work.py.
        await commit_or_flush(self.db)

    def _sanitize_optional_text(self, value: str | None) -> str | None:
        return sanitize_text_for_storage(value) if value is not None else None

    @staticmethod
    def _documents(asset: KnowledgeAsset) -> list[dict]:
        # Dump to plain JSON first, then NUL-strip: extracted text reaches this column too,
        # and PostgreSQL rejects NUL bytes in JSONB strings.
        return sanitize_json_for_storage(documents_to_storage(asset.documents))
