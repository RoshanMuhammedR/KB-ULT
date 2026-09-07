"""whether an answer's citations checked out, stored alongside the answer

Revision ID: 0011_message_grounding
Revises: 0010_message_trace
Create Date: 2026-09-07

The grounding checker verifies each cited claim against the passage it cites, and the result
reaches the client as a `verified` SSE frame. Until now that frame was the only place it
existed — so the badge was there while the answer streamed and gone the moment the page
reloaded. Same failure `trace` had in 0010, same fix.

`grounding` is nullable and there is no backfill, for a reason stronger than "we have no old
data": re-running the checker over historical answers would judge their claims against
whatever passages exist *now*. Re-ingestion deletes and re-creates chunks with fresh ids and
different boundaries, so a backfill would be scoring old answers against passages they were
never written from. An unverified old answer is honest; a retroactively "verified" one is not.

JSONB verbatim, following `citations` (0002) and `trace` (0010) on this same table: the shape
is the client's to render. No index — the column is read only as part of loading the message
it belongs to, never filtered or aggregated on.
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

revision = "0011_message_grounding"
down_revision = "0010_message_trace"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("messages", sa.Column("grounding", JSONB(), nullable=True))


def downgrade() -> None:
    op.drop_column("messages", "grounding")
