"""how an answer was reached, stored alongside the answer

Revision ID: 0010_message_trace
Revises: 0009_chunk_hierarchy
Create Date: 2026-08-23

The agentic loop already records every hop it takes — the query it ran, whether it was a
rewrite and which strategy produced it, how many candidates came back, how many survived
reranking, and what the grader judged missing. Until now that lived only in the log and in a
Langfuse trace, so the UI could show progress *while* an answer streamed and then lost it
the moment the page reloaded — a panel that exists on some messages and not others reads as
a bug rather than a feature.

`trace` is nullable and there is no backfill: answers written before this migration genuinely
have no trace, and the client omits the panel for them rather than inventing one.

JSONB verbatim, following `citations` on this same table for the same reason — the shape is
the client's to render, not something to normalise into columns that would then have to be
migrated every time a hop learns to record one more thing. The passages themselves are
deliberately *not* included; `citations` already carries them, and duplicating them would
double the size of a row written on every answer.
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

revision = "0010_message_trace"
down_revision = "0009_chunk_hierarchy"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("messages", sa.Column("trace", JSONB(), nullable=True))


def downgrade() -> None:
    op.drop_column("messages", "trace")
