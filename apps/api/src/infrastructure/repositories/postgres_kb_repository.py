from sqlalchemy import select
from sqlalchemy.orm import Session

from src.domain.entities import KnowledgeBase
from src.infrastructure.database.models import KnowledgeBaseModel
from src.infrastructure.repositories.mappers import kb_to_domain


class KnowledgeBaseRepository:
    def __init__(self, db: Session) -> None:
        self.db = db

    def get_default(self) -> KnowledgeBase | None:
        model = self.db.scalar(select(KnowledgeBaseModel).order_by(KnowledgeBaseModel.created_at).limit(1))
        return kb_to_domain(model) if model else None

    def ensure_default(self) -> KnowledgeBase:
        existing = self.get_default()
        if existing:
            return existing
        model = KnowledgeBaseModel(name="Default Knowledge Base", owner_id=None)
        self.db.add(model)
        self._commit()
        self.db.refresh(model)
        return kb_to_domain(model)

    def _commit(self) -> None:
        try:
            self.db.commit()
        except Exception:
            self.db.rollback()
            raise
