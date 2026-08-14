"""conversations and messages — persisted, resumable chat threads

Revision ID: 0002_conversations
Revises: 0001_initial
Create Date: 2026-08-14

Before this, every question was a one-shot and the history died on refresh. These two tables
give the product memory: a named thread a user can leave and come back to, with each
assistant message keeping the citations that grounded it.

Both tables are `TenantScoped`, so they follow 0001's pattern exactly — the same tenant/user
columns, the same index naming, and the same `tenant_isolation` RLS policy. As in 0001, any
future *data* migration touching them must set `app.current_tenant` (or `app.tenant_bypass`)
itself, since the Alembic connection has no `after_begin` listener.
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB, UUID

revision = "0002_conversations"
down_revision = "0001_initial"
branch_labels = None
depends_on = None

NEW_TABLES = ["conversations", "messages"]

# Identical to 0001's predicate: bypass (system_scope) OR the row belongs to the current
# tenant. An unset GUC makes the predicate NULL, which returns zero rows — fail closed.
_RLS_PREDICATE = (
    "current_setting('app.tenant_bypass', true) = 'on' "
    "OR tenant_id = NULLIF(current_setting('app.current_tenant', true), '')::uuid"
)


def _tenant_columns() -> list[sa.Column]:
    """The `TenantScoped` pair, matching 0001."""
    return [
        sa.Column(
            "tenant_id",
            UUID(as_uuid=True),
            sa.ForeignKey("tenants.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "user_id",
            UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
    ]


def upgrade() -> None:
    op.create_table(
        "conversations",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "knowledge_base_id",
            UUID(as_uuid=True),
            sa.ForeignKey("knowledge_bases.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        *_tenant_columns(),
    )
    # The list view is "my threads, most recently touched first".
    op.create_index("ix_conversations_updated_at", "conversations", ["updated_at"])

    op.create_table(
        "messages",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "conversation_id",
            UUID(as_uuid=True),
            sa.ForeignKey("conversations.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("role", sa.String(length=16), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("citations", JSONB(), nullable=False, server_default="[]"),
        sa.Column(
            "insufficient_context", sa.Boolean(), nullable=False, server_default=sa.false()
        ),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        *_tenant_columns(),
    )
    # Reading a thread is always "this conversation, in order".
    op.create_index("ix_messages_conversation_created", "messages", ["conversation_id", "created_at"])
    # Backs "which answers cited this source?" — a containment query
    # (`citations @> '[{"asset_id": "..."}]'`), which is what jsonb_path_ops indexes best.
    op.create_index(
        "ix_messages_citations",
        "messages",
        ["citations"],
        postgresql_using="gin",
        postgresql_ops={"citations": "jsonb_path_ops"},
    )

    for table in NEW_TABLES:
        op.create_index(f"ix_{table}_tenant_id", table, ["tenant_id"])
        op.create_index(f"ix_{table}_user_id", table, ["user_id"])

    # --- Row-Level Security ----------------------------------------------------------
    # FORCE makes the policy apply to the table owner too, so the app needs no separate
    # non-owner role for this to bite.
    for table in NEW_TABLES:
        op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
        op.execute(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY")
        op.execute(
            f"CREATE POLICY tenant_isolation ON {table} "
            f"USING ({_RLS_PREDICATE}) WITH CHECK ({_RLS_PREDICATE})"
        )


def downgrade() -> None:
    for table in NEW_TABLES:
        op.execute(f"DROP POLICY IF EXISTS tenant_isolation ON {table}")
        op.execute(f"ALTER TABLE {table} NO FORCE ROW LEVEL SECURITY")
        op.execute(f"ALTER TABLE {table} DISABLE ROW LEVEL SECURITY")

    op.drop_table("messages")
    op.drop_table("conversations")
