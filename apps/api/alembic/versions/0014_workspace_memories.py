"""facts a workspace has stated about itself, outliving the thread they were said in

Revision ID: 0014_workspace_memories
Revises: 0013_message_feedback
Create Date: 2026-09-07

**This does not replace the four-turn history window, and must not be made to.** That window
is what lets `QueryResolver.resolve` turn "what about its pricing?" into a real query, and it
works because it carries the *literal* previous turn. Distilled facts are lossy by
construction, so substituting them would quietly degrade follow-up resolution — the single
highest-value model call in the pipeline. Memory is for facts that outlive a thread; the
window is for pronouns inside one. They solve different problems and both stay.

Scoped to `knowledge_base_id` as conversations are, so a workspace that grows a second library
inherits the right memories rather than all of them.

**Lexical only, deliberately.** The `fts` generated column reuses exactly the mechanism
`chunks` already has: no new adapter, no embedding cost at write time, and no coupling to
`embedding_dimensions` — which would mean a model change requires re-embedding memories as
well as the corpus. Memories are one-sentence facts phrased in the user's own vocabulary, and
`QueryResolver` already produces `resolved.keywords` for precisely this kind of matching. A
vector column can be added later if eval shows lexical misses matter; adding one now would be
paying for a capability nothing has yet asked for.

`superseded_by` is a self-FK with `ON DELETE SET NULL`, not CASCADE. Deleting the newer memory
must not delete the older one it replaced — the old fact becomes current again, which is the
only sane reading of "forget the correction".
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID

revision = "0014_workspace_memories"
down_revision = "0013_message_feedback"
branch_labels = None
depends_on = None

_RLS_PREDICATE = (
    "current_setting('app.tenant_bypass', true) = 'on' "
    "OR tenant_id = NULLIF(current_setting('app.current_tenant', true), '')::uuid"
)

_FTS_EXPRESSION = "to_tsvector('english', content)"


def upgrade() -> None:
    op.create_table(
        "workspace_memories",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "knowledge_base_id",
            UUID(as_uuid=True),
            sa.ForeignKey("knowledge_bases.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("content", sa.Text(), nullable=False),
        # fact | preference. A fact about the workspace is shared; a stated preference
        # ("answer briefly") is personal, and the read predicate treats them differently.
        sa.Column("kind", sa.String(length=16), nullable=False, server_default="fact"),
        # Where this came from, so a user can go and read the conversation that produced it.
        # SET NULL rather than CASCADE: deleting the thread should not erase what was learned.
        sa.Column(
            "source_conversation_id",
            UUID(as_uuid=True),
            sa.ForeignKey("conversations.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "source_message_id",
            UUID(as_uuid=True),
            sa.ForeignKey("messages.id", ondelete="SET NULL"),
            nullable=True,
        ),
        # A correction points back at what it replaced. The old row is never destroyed, so
        # the history of what the workspace believed stays auditable.
        sa.Column(
            "superseded_by",
            UUID(as_uuid=True),
            sa.ForeignKey("workspace_memories.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("superseded_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_used_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
    )

    op.add_column(
        "workspace_memories",
        sa.Column(
            "tenant_id",
            UUID(as_uuid=True),
            sa.ForeignKey("tenants.id", ondelete="CASCADE"),
            nullable=False,
        ),
    )
    op.add_column(
        "workspace_memories",
        sa.Column(
            "user_id",
            UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
    )

    op.create_index("ix_workspace_memories_tenant_id", "workspace_memories", ["tenant_id"])
    op.create_index("ix_workspace_memories_user_id", "workspace_memories", ["user_id"])
    # The list view is "what this workspace currently believes, newest first".
    op.create_index(
        "ix_workspace_memories_active",
        "workspace_memories",
        ["knowledge_base_id", "superseded_at", "created_at"],
    )

    # Same mechanism as `chunks.fts` (0006), same reasons.
    op.execute(
        f"ALTER TABLE workspace_memories ADD COLUMN fts tsvector "
        f"GENERATED ALWAYS AS ({_FTS_EXPRESSION}) STORED"
    )
    op.execute("CREATE INDEX ix_workspace_memories_fts ON workspace_memories USING GIN (fts)")

    op.execute("ALTER TABLE workspace_memories ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE workspace_memories FORCE ROW LEVEL SECURITY")
    op.execute(
        f"CREATE POLICY tenant_isolation ON workspace_memories "
        f"USING ({_RLS_PREDICATE}) WITH CHECK ({_RLS_PREDICATE})"
    )


def downgrade() -> None:
    op.execute("DROP POLICY IF EXISTS tenant_isolation ON workspace_memories")
    op.execute("ALTER TABLE workspace_memories NO FORCE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE workspace_memories DISABLE ROW LEVEL SECURITY")
    op.execute("DROP INDEX IF EXISTS ix_workspace_memories_fts")
    op.drop_table("workspace_memories")
