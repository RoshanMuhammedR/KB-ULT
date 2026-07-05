from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import delete, desc, select
from sqlalchemy.orm import Session

from src.core.text import sanitize_json_for_storage, sanitize_text_for_storage
from src.domain.entities import KnowledgeAsset
from src.infrastructure.database.models import KnowledgeAssetModel
from src.infrastructure.repositories.mappers import asset_to_domain


class KnowledgeAssetRepository:
    def __init__(self, db: Session) -> None:
        self.db = db

    def list_current(self, knowledge_base_id: UUID) -> list[KnowledgeAsset]:
        rows = self.db.scalars(
            select(KnowledgeAssetModel)
            .where(KnowledgeAssetModel.knowledge_base_id == knowledge_base_id)
            .where(KnowledgeAssetModel.superseded_at.is_(None))
            .order_by(desc(KnowledgeAssetModel.created_at))
        ).all()
        return [asset_to_domain(row) for row in rows]

    def get(self, asset_id: UUID) -> KnowledgeAsset | None:
        row = self.db.get(KnowledgeAssetModel, asset_id)
        return asset_to_domain(row) if row else None

    def get_model(self, asset_id: UUID) -> KnowledgeAssetModel | None:
        return self.db.get(KnowledgeAssetModel, asset_id)

    def latest_for_filename(self, knowledge_base_id: UUID, filename: str) -> KnowledgeAsset | None:
        row = self.db.scalar(
            select(KnowledgeAssetModel)
            .where(KnowledgeAssetModel.knowledge_base_id == knowledge_base_id)
            .where(KnowledgeAssetModel.filename == filename)
            .order_by(desc(KnowledgeAssetModel.version))
            .limit(1)
        )
        return asset_to_domain(row) if row else None

    def create_pending(self, asset: KnowledgeAsset) -> KnowledgeAsset:
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
            superseded_at=asset.superseded_at,
        )
        self.db.add(model)
        self._commit()
        self.db.refresh(model)
        return asset_to_domain(model)

    def update_from_domain(self, asset: KnowledgeAsset) -> KnowledgeAsset:
        model = self.get_model(asset.id)
        if model is None:
            raise ValueError(f"KnowledgeAsset not found: {asset.id}")
        model.title = self._sanitize_optional_text(asset.title)
        model.storage_key = asset.storage_key
        model.status = asset.status.value
        model.failed_step = asset.failed_step
        model.error_message = asset.error_message
        model.text_content = self._sanitize_optional_text(asset.text_content)
        model.metadata_ = sanitize_json_for_storage(asset.metadata)
        model.superseded_at = asset.superseded_at
        self._commit()
        self.db.refresh(model)
        return asset_to_domain(model)

    def rename(self, asset_id: UUID, title: str) -> KnowledgeAsset:
        model = self.get_model(asset_id)
        if model is None:
            raise ValueError(f"KnowledgeAsset not found: {asset_id}")
        model.title = sanitize_text_for_storage(title)
        self._commit()
        self.db.refresh(model)
        return asset_to_domain(model)

    def supersede_previous_versions(self, lineage_id: UUID, active_asset_id: UUID) -> None:
        rows = self.db.scalars(
            select(KnowledgeAssetModel)
            .where(KnowledgeAssetModel.lineage_id == lineage_id)
            .where(KnowledgeAssetModel.id != active_asset_id)
            .where(KnowledgeAssetModel.superseded_at.is_(None))
        ).all()
        now = datetime.now(UTC)
        for row in rows:
            row.superseded_at = now
        self._commit()

    def delete(self, asset_id: UUID) -> None:
        self.db.execute(delete(KnowledgeAssetModel).where(KnowledgeAssetModel.id == asset_id))
        self._commit()

    def _commit(self) -> None:
        try:
            self.db.commit()
        except Exception:
            # A failed flush leaves the Session transaction unusable until it is rolled back.
            self.db.rollback()
            raise

    def _sanitize_optional_text(self, value: str | None) -> str | None:
        return sanitize_text_for_storage(value) if value is not None else None
