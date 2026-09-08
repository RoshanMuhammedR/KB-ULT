"""a conversation can be attached to several knowledge bases

Revision ID: 0015_conversation_kbs
Revises: 0014_workspace_memories
Create Date: 2026-09-08

Chat is one interface you attach bases to, so a thread spans a *set* of them rather than one.
`conversations.knowledge_base_id` stays and keeps meaning "the base this thread was started
in": it is NOT NULL, it is what every existing row already has, and dropping it would mean a
data migration to invent an answer for threads that predate the choice. This table is the
attachment set on top of it.

Backfilled with one row per existing conversation, so a thread created before this migration
behaves exactly as it did — attached to the base it was started in, and to nothing else.

`ON DELETE CASCADE` on both sides. Deleting a base detaches it from every thread rather than
deleting the threads: a conversation that also had two other bases attached is still worth
reading, and one that had only this base becomes a thread with no corpus — which is honest,
and which the read path treats as "nothing to retrieve from" rather than as an error.
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID

revision = "0015_conversation_kbs"
down_revision = "0014_workspace_memories"
branch_labels = None
depends_on = None

_RLS_PREDICATE = (
    "current_setting('app.tenant_bypass', true) = 'on' "
    "OR tenant_id = NULLIF(current_setting('app.current_tenant', true), '')::uuid"
)


def upgrade() -> None:
    op.create_table(
        "conversation_knowledge_bases",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "conversation_id",
            UUID(as_uuid=True),
            sa.ForeignKey("conversations.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "knowledge_base_id",
            UUID(as_uuid=True),
            sa.ForeignKey("knowledge_bases.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
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
        # Attaching the same base twice is a no-op, not a second row.
        sa.UniqueConstraint(
            "conversation_id", "knowledge_base_id", name="uq_conversation_knowledge_base"
        ),
    )

    op.create_index(
        "ix_conversation_kbs_conversation", "conversation_knowledge_bases", ["conversation_id"]
    )
    op.create_index("ix_conversation_kbs_tenant_id", "conversation_knowledge_bases", ["tenant_id"])
    op.create_index("ix_conversation_kbs_user_id", "conversation_knowledge_bases", ["user_id"])

    # Backfill: every existing thread stays attached to the base it was started in. Runs as
    # plain SQL over `conversations`, which already carries tenant_id/user_id — copying them
    # keeps the new rows inside the same RLS policy without this migration needing to know
    # who any of them belong to.
    #
    # `gen_random_uuid()` is pgcrypto, available in Postgres 13+ as a core function.
    op.execute(
        """
        INSERT INTO conversation_knowledge_bases
            (id, conversation_id, knowledge_base_id, tenant_id, user_id)
        SELECT gen_random_uuid(), c.id, c.knowledge_base_id, c.tenant_id, c.user_id
        FROM conversations c
        """
    )

    op.execute("ALTER TABLE conversation_knowledge_bases ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE conversation_knowledge_bases FORCE ROW LEVEL SECURITY")
    op.execute(
        f"CREATE POLICY tenant_isolation ON conversation_knowledge_bases "
        f"USING ({_RLS_PREDICATE}) WITH CHECK ({_RLS_PREDICATE})"
    )


def downgrade() -> None:
    op.execute("DROP POLICY IF EXISTS tenant_isolation ON conversation_knowledge_bases")
    op.execute("ALTER TABLE conversation_knowledge_bases NO FORCE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE conversation_knowledge_bases DISABLE ROW LEVEL SECURITY")
    op.drop_table("conversation_knowledge_bases")
