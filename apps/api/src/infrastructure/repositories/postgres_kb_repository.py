from uuid import UUID

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.tenant_context import current_tenant_id, current_user_id
from src.domain.entities import KnowledgeBase
from src.infrastructure.database.models import KnowledgeBaseModel
from src.infrastructure.repositories.mappers import kb_to_domain
from src.infrastructure.repositories.unit_of_work import commit_or_flush

_DEFAULT_NAME = "Default Knowledge Base"


class KnowledgeBaseRepository:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def get_default(self) -> KnowledgeBase | None:
        """The oldest base in the tenant — first-run bootstrap only.

        **Not a way to resolve which base a request means.** It used to be exactly that, for
        all fourteen call sites in the product, none of which accepted a base id. The moment a
        tenant had a second base every read and every write silently kept using the first, and
        the new one was unreachable through the entire API. Anything that acts on a base takes
        its id now; this survives to answer "what should a brand-new tenant see".
        """
        model = await self.db.scalar(
            select(KnowledgeBaseModel).order_by(KnowledgeBaseModel.created_at).limit(1)
        )
        return kb_to_domain(model) if model else None

    async def get(self, knowledge_base_id: UUID) -> KnowledgeBase | None:
        """One base by id, or None.

        An ORM `select`, never `Session.get` — a `get` that hits the identity map returns the
        row without emitting a statement, so the tenant filter in `do_orm_execute` never runs
        for it. That matters more here than anywhere: this is the function that decides
        whether a caller may act on a base at all.
        """
        model = (await self.db.scalars(
            select(KnowledgeBaseModel).where(KnowledgeBaseModel.id == knowledge_base_id)
        )).first()
        return kb_to_domain(model) if model else None

    async def list_all(self) -> list[KnowledgeBase]:
        """Every base in this tenant, oldest first, so the order is stable across reloads."""
        rows = (await self.db.scalars(
            select(KnowledgeBaseModel).order_by(KnowledgeBaseModel.created_at)
        )).all()
        return [kb_to_domain(row) for row in rows]

    async def create(
        self, name: str, description: str | None = None, colour: str | None = None
    ) -> KnowledgeBase:
        """Add a base. Raises `ValueError` when the name is already taken in this tenant.

        `uq_knowledge_base_tenant_name` is scoped to `(tenant_id, name)` rather than to
        `tenant_id` — migration 0008 chose that deliberately so multiple named bases would be
        legal later without another migration. This is that later.
        """
        clean = name.strip()
        if not clean:
            raise ValueError("A knowledge base needs a name")

        existing = (await self.db.scalars(
            select(KnowledgeBaseModel).where(KnowledgeBaseModel.name == clean)
        )).first()
        if existing is not None:
            raise ValueError(f"A knowledge base called {clean!r} already exists")

        model = KnowledgeBaseModel(
            name=clean,
            description=(description or "").strip() or None,
            colour=(colour or "").strip() or None,
            owner_id=None,
        )
        self.db.add(model)
        await self._commit()
        await self.db.refresh(model)
        return kb_to_domain(model)

    async def update(
        self,
        knowledge_base_id: UUID,
        *,
        name: str | None = None,
        description: str | None = None,
        colour: str | None = None,
    ) -> KnowledgeBase:
        """Change a base's name, description or colour. Omitted fields are left alone.

        `None` means "not supplied" and empty-string means "clear it", which is the only way
        a client can remove a description it no longer wants without a separate route.
        """
        clean = name.strip() if name is not None else None
        if name is not None and not clean:
            raise ValueError("A knowledge base needs a name")

        model = (await self.db.scalars(
            select(KnowledgeBaseModel).where(KnowledgeBaseModel.id == knowledge_base_id)
        )).first()
        if model is None:
            raise ValueError("Knowledge base not found")

        if clean is not None:
            clash = (await self.db.scalars(
                select(KnowledgeBaseModel).where(
                    KnowledgeBaseModel.name == clean,
                    KnowledgeBaseModel.id != knowledge_base_id,
                )
            )).first()
            if clash is not None:
                raise ValueError(f"A knowledge base called {clean!r} already exists")
            model.name = clean

        if description is not None:
            model.description = description.strip() or None
        if colour is not None:
            model.colour = colour.strip() or None
        await self._commit()
        await self.db.refresh(model)
        return kb_to_domain(model)

    async def delete(self, knowledge_base_id: UUID) -> None:
        """Delete a base and, by FK cascade, its sources, conversations and memories.

        The caller is responsible for telling the user what that means before calling. The
        last base in a tenant is refused: an account with nowhere to put a source is a state
        the product has no screen for.
        """
        model = (await self.db.scalars(
            select(KnowledgeBaseModel).where(KnowledgeBaseModel.id == knowledge_base_id)
        )).first()
        if model is None:
            raise ValueError("Knowledge base not found")

        remaining = len(await self.list_all())
        if remaining <= 1:
            raise ValueError("This is the only knowledge base — create another one first")

        await self.db.delete(model)
        await self._commit()

    async def ensure_default(self) -> KnowledgeBase:
        existing = await self.get_default()
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
        await self.db.execute(
            pg_insert(KnowledgeBaseModel)
            .values(
                name=_DEFAULT_NAME,
                owner_id=None,
                tenant_id=current_tenant_id(),
                user_id=current_user_id(),
            )
            .on_conflict_do_nothing(constraint="uq_knowledge_base_tenant_name")
        )
        await self._commit()

        created = await self.get_default()
        if created is None:  # pragma: no cover - the row was just inserted or already there
            raise RuntimeError("Default knowledge base could not be created")
        return created

    async def _commit(self) -> None:
        # Commits on its own, unless the caller opened a `unit_of_work` — then this
        # flushes and the enclosing scope owns the single COMMIT. See unit_of_work.py.
        await commit_or_flush(self.db)
