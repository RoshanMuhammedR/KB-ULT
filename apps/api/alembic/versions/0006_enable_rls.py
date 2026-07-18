"""enable Row-Level Security on tenant-scoped tables (DB backstop for the ORM filter)

Revision ID: 0006_enable_rls
Revises: 0005_add_tenancy
Create Date: 2026-07-18

Second enforcement layer: even a query that forgets the ORM filter, raw SQL, or a bulk op
cannot cross tenants. Policies read the transaction-local GUC `app.current_tenant`, set by
the SQLAlchemy `after_begin` listener from the same tenant context the ORM filter uses.

`FORCE ROW LEVEL SECURITY` makes the policies apply even to the table owner, so the app can
keep using its existing role (no separate non-owner role required for this setup). Genuinely
cross-tenant/pre-auth work sets `app.tenant_bypass = 'on'` (the DB counterpart of
`system_scope`). Unset GUC → predicate is NULL → zero rows (fail closed).

Note: DDL is not subject to RLS, so this migration runs fine; but any *future data*
migration touching these tables must set `app.current_tenant` (or `app.tenant_bypass`)
itself, since the Alembic connection has no `after_begin` listener.
"""

from alembic import op

revision = "0006_enable_rls"
down_revision = "0005_add_tenancy"
branch_labels = None
depends_on = None

DOMAIN_TABLES = [
    "knowledge_bases",
    "knowledge_assets",
    "chunks",
    "embeddings",
    "ingestion_jobs",
    "ingestion_job_events",
]

_PREDICATE = (
    "current_setting('app.tenant_bypass', true) = 'on' "
    "OR tenant_id = NULLIF(current_setting('app.current_tenant', true), '')::uuid"
)


def upgrade() -> None:
    for table in DOMAIN_TABLES:
        op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
        op.execute(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY")
        op.execute(
            f"CREATE POLICY tenant_isolation ON {table} "
            f"USING ({_PREDICATE}) WITH CHECK ({_PREDICATE})"
        )


def downgrade() -> None:
    for table in DOMAIN_TABLES:
        op.execute(f"DROP POLICY IF EXISTS tenant_isolation ON {table}")
        op.execute(f"ALTER TABLE {table} NO FORCE ROW LEVEL SECURITY")
        op.execute(f"ALTER TABLE {table} DISABLE ROW LEVEL SECURITY")
