"""Seed the default tenant's default KnowledgeBase.

Multi-tenant note: KnowledgeBases are now tenant-scoped, so this seeds the KB for the
**default tenant** (created by migration 0005). The tenant/user are resolved under
`system_scope`, then the KB is created inside that tenant's context so it is stamped and
passes RLS. Each real tenant gets its own default KB lazily on first use.
"""

from sqlalchemy import select

from src.core.tenant_context import reset_tenant_context, set_tenant_context, system_scope
from src.infrastructure.database.models import TenantModel, UserModel
from src.infrastructure.database.session import SessionLocal
from src.infrastructure.repositories import KnowledgeBaseRepository


def main() -> None:
    # 1. Resolve the seeded default tenant + its user (pre-context work).
    with SessionLocal() as db, system_scope():
        tenant = db.scalar(select(TenantModel).where(TenantModel.domain == "default"))
        user = (
            db.scalar(select(UserModel).where(UserModel.tenant_id == tenant.id))
            if tenant is not None
            else None
        )
    if tenant is None or user is None:
        raise SystemExit("Default tenant/user missing — run `alembic upgrade head` first.")

    # 2. Create that tenant's default KB inside its tenant context (fresh transaction).
    with SessionLocal() as db:
        tokens = set_tenant_context(tenant.id, user.id)
        try:
            kb = KnowledgeBaseRepository(db).ensure_default()
            print(f"Default KnowledgeBase ready: {kb.id}")
        finally:
            reset_tenant_context(tokens)


if __name__ == "__main__":
    main()
