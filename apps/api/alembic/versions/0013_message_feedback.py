"""a reader's verdict on an answer

Revision ID: 0013_message_feedback
Revises: 0012_chunk_signals
Create Date: 2026-09-07

Everything the retrieval loop learns about its own output today is self-graded: the reranker
scores, the grader judges sufficiency, the checker verifies citations — all the same family of
model judging its own work. A thumb is the only signal in the system that comes from outside
it, which makes it worth more per event than anything else recorded here.

Unique on `(message_id, user_id)`: one verdict per person per answer. Two people disagreeing
about the same answer is a real thing to record, not a conflict to resolve.

`rating` is a signed SmallInteger rather than the `String(16)` this codebase uses for every
other state column (`status`, `role`, `kind`). The deviation is deliberate and worth the
inconsistency: this value is summed into a weighted score, not compared against a name, and
storing "up"/"down" would mean mapping strings to numbers at every read. The CHECK constraint
keeps it as closed a set as an enum would.
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID

revision = "0013_message_feedback"
down_revision = "0012_chunk_signals"
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
        "message_feedback",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "message_id",
            UUID(as_uuid=True),
            sa.ForeignKey("messages.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("rating", sa.SmallInteger(), nullable=False),
        # Optional and unused by the prior — it exists so a reader who wants to say *why*
        # has somewhere to put it, and so that reason survives for a human to read later.
        sa.Column("comment", sa.Text(), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        *_tenant_columns(),
        sa.CheckConstraint("rating IN (-1, 1)", name="ck_message_feedback_rating"),
        sa.UniqueConstraint("message_id", "user_id", name="uq_message_feedback_message_user"),
    )

    op.create_index("ix_message_feedback_tenant_id", "message_feedback", ["tenant_id"])
    op.create_index("ix_message_feedback_user_id", "message_feedback", ["user_id"])
    # Loading a thread asks "this user's ratings for these messages" in one statement.
    op.create_index("ix_message_feedback_message_id", "message_feedback", ["message_id"])

    op.execute("ALTER TABLE message_feedback ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE message_feedback FORCE ROW LEVEL SECURITY")
    op.execute(
        f"CREATE POLICY tenant_isolation ON message_feedback "
        f"USING ({_RLS_PREDICATE}) WITH CHECK ({_RLS_PREDICATE})"
    )


def downgrade() -> None:
    op.execute("DROP POLICY IF EXISTS tenant_isolation ON message_feedback")
    op.execute("ALTER TABLE message_feedback NO FORCE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE message_feedback DISABLE ROW LEVEL SECURITY")
    op.drop_table("message_feedback")
