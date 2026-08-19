"""one knowledge base per (tenant, name) — closes the ensure_default race

Revision ID: 0008_unique_kb_per_tenant
Revises: 0007_documents_column
Create Date: 2026-08-19

`KnowledgeBaseRepository.ensure_default()` was read-then-insert: SELECT the tenant's
knowledge base, and create it when there isn't one. Two requests arriving together on a
fresh tenant — an upload and the `/knowledge-bases/default` fetch the app makes on load,
which is exactly the pair a first-time user triggers — both saw nothing and both inserted.
Nothing in the schema said that was wrong, so the tenant quietly ended up with two
knowledge bases and its sources split across them depending on which one each request won.

The index makes the invariant the database's business, so the repository can insert with
`ON CONFLICT DO NOTHING` and let the loser of the race read the winner's row.

Keyed on `(tenant_id, name)` rather than `tenant_id` alone: the product creates exactly one
KB per tenant today, but scoping the constraint to the name closes this race without
foreclosing multiple named knowledge bases later.

Existing duplicates are merged before the index is built — the oldest row per
`(tenant_id, name)` wins, and any assets pointing at the losers are repointed to it.
"""

from alembic import op

revision = "0008_unique_kb_per_tenant"
down_revision = "0007_documents_column"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # This migration writes DATA, not just schema, so RLS applies to it: in production the
    # migration role is the same non-superuser app role, and every domain table carries
    # FORCE ROW LEVEL SECURITY. Without a tenant GUC the predicate is NULL and each
    # statement below would silently match zero rows. `app.tenant_bypass` is the same
    # break-glass switch `system_scope()` uses at runtime; `is_local => true` scopes it to
    # this migration's transaction.
    op.execute("SELECT set_config('app.tenant_bypass', 'on', true)")

    op.execute(
        """
        WITH ranked AS (
            SELECT id,
                   first_value(id) OVER (
                       PARTITION BY tenant_id, name ORDER BY created_at, id
                   ) AS keeper
            FROM knowledge_bases
        )
        UPDATE knowledge_assets AS a
           SET knowledge_base_id = r.keeper
          FROM ranked AS r
         WHERE a.knowledge_base_id = r.id
           AND r.id <> r.keeper
        """
    )

    op.execute(
        """
        DELETE FROM knowledge_bases AS kb
         USING (
            SELECT id,
                   first_value(id) OVER (
                       PARTITION BY tenant_id, name ORDER BY created_at, id
                   ) AS keeper
            FROM knowledge_bases
         ) AS r
         WHERE kb.id = r.id
           AND r.id <> r.keeper
        """
    )

    op.execute(
        "CREATE UNIQUE INDEX uq_knowledge_base_tenant_name "
        "ON knowledge_bases (tenant_id, name)"
    )


def downgrade() -> None:
    # The merge is not reversible (the duplicate rows are gone and their assets have been
    # repointed), so this only drops the constraint.
    op.execute("DROP INDEX IF EXISTS uq_knowledge_base_tenant_name")
