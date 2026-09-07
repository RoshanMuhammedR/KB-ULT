"""what each passage has actually done for this workspace

Revision ID: 0012_chunk_signals
Revises: 0011_message_grounding
Create Date: 2026-09-07

Retrieval currently has no memory. Every query is scored as if the corpus had never been used
before, so a passage that has answered the same question correctly forty times starts from
scratch on the forty-first, and one that keeps getting cited for claims it does not support
never sinks.

**A separate table, not counters on `chunks`.** `replace_for_asset` DELETEs every chunk for an
asset and re-inserts with fresh UUIDs on every re-ingest, so counters living on `chunks` would
be destroyed anyway. Putting them here makes that loss explicit rather than incidental — and
the loss is *correct*, not a bug to be fixed later by anyone reading this. Re-ingestion moves
chunk boundaries; carrying "this passage was useful" onto a differently-bounded passage that
merely inherited its position would be inventing evidence. A future migration that tries to
preserve these across re-ingest is making the system confidently wrong.

**Read per tenant, never per user.** Whether a passage answers a question well is a property
of the workspace's corpus, not of whoever asked. `user_id` is stamped because `TenantScoped`
stamps it, and is deliberately never filtered on — it is not attribution, and reading it as
attribution would turn a shared corpus signal into a per-person filter bubble.

The unique constraint is on `(tenant_id, chunk_id)` rather than `chunk_id` alone because it is
the `ON CONFLICT` target for the upsert in `postgres_chunk_signal_repository`. Including
`tenant_id` makes a cross-tenant conflict structurally impossible: the one write path in this
codebase that must set `tenant_id` by hand (Core `insert()` bypasses the `before_flush` stamp)
cannot silently merge two tenants' counters even if that hand-written value were wrong.
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID

revision = "0012_chunk_signals"
down_revision = "0011_message_grounding"
branch_labels = None
depends_on = None

_RLS_PREDICATE = (
    "current_setting('app.tenant_bypass', true) = 'on' "
    "OR tenant_id = NULLIF(current_setting('app.current_tenant', true), '')::uuid"
)


def _tenant_columns() -> list[sa.Column]:
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
        "chunk_signals",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "chunk_id",
            UUID(as_uuid=True),
            sa.ForeignKey("chunks.id", ondelete="CASCADE"),
            nullable=False,
        ),
        # Cited is recorded but deliberately does NOT feed the prior — see prior.py. It is
        # the denominator that makes the other counters interpretable.
        sa.Column("cited", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("supported", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("unsupported", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("upvoted", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("downvoted", sa.Integer(), nullable=False, server_default="0"),
        # Read at query time to decay the prior. An exponent computed in Python, not a
        # scheduled job rewriting rows.
        sa.Column("last_cited_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        *_tenant_columns(),
        sa.UniqueConstraint("tenant_id", "chunk_id", name="uq_chunk_signal_tenant_chunk"),
    )

    op.create_index("ix_chunk_signals_tenant_id", "chunk_signals", ["tenant_id"])
    op.create_index("ix_chunk_signals_user_id", "chunk_signals", ["user_id"])

    op.execute("ALTER TABLE chunk_signals ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE chunk_signals FORCE ROW LEVEL SECURITY")
    op.execute(
        f"CREATE POLICY tenant_isolation ON chunk_signals "
        f"USING ({_RLS_PREDICATE}) WITH CHECK ({_RLS_PREDICATE})"
    )


def downgrade() -> None:
    op.execute("DROP POLICY IF EXISTS tenant_isolation ON chunk_signals")
    op.execute("ALTER TABLE chunk_signals NO FORCE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE chunk_signals DISABLE ROW LEVEL SECURITY")
    op.drop_table("chunk_signals")
