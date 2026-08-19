from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

from src.core.tenant_context import current_tenant_id, current_user_id
from src.domain.entities import KnowledgeBase
from src.infrastructure.database.models import KnowledgeBaseModel
from src.infrastructure.repositories.mappers import kb_to_domain
from src.infrastructure.repositories.unit_of_work import commit_or_flush

_DEFAULT_NAME = "Default Knowledge Base"


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

        # Read-then-insert is a race: on a brand-new tenant the first upload and the app's
        # `/knowledge-bases/default` fetch arrive together, both see nothing, and both
        # insert. `uq_knowledge_base_tenant_name` (migration 0008) makes the second insert a
        # no-op instead of a duplicate, and the re-read below returns the winner's row — so
        # both callers get the same knowledge base rather than one each.
        #
        # This is a Core INSERT, which the `before_flush` tenant stamper does not see, so
        # tenant_id/user_id are set explicitly here. `current_tenant_id()` fails closed if
        # no tenant is bound, exactly as the listener would.
        self.db.execute(
            pg_insert(KnowledgeBaseModel)
            .values(
                name=_DEFAULT_NAME,
                owner_id=None,
                tenant_id=current_tenant_id(),
                user_id=current_user_id(),
            )
            .on_conflict_do_nothing(constraint="uq_knowledge_base_tenant_name")
        )
        self._commit()

        created = self.get_default()
        if created is None:  # pragma: no cover - the row was just inserted or already there
            raise RuntimeError("Default knowledge base could not be created")
        return created

    def _commit(self) -> None:
        # Commits on its own, unless the caller opened a `unit_of_work` — then this
        # flushes and the enclosing scope owns the single COMMIT. See unit_of_work.py.
        commit_or_flush(self.db)
