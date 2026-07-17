"""add ingestion job events table

Revision ID: 0004_add_ingestion_job_events
Revises: 0003_add_ingestion_jobs
Create Date: 2026-07-17
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB, UUID

revision = "0004_add_ingestion_job_events"
down_revision = "0003_add_ingestion_jobs"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "ingestion_job_events",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "asset_id",
            UUID(as_uuid=True),
            sa.ForeignKey("knowledge_assets.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "job_id",
            UUID(as_uuid=True),
            sa.ForeignKey("ingestion_jobs.id", ondelete="CASCADE"),
            nullable=True,
        ),
        sa.Column("level", sa.String(length=16), nullable=False, server_default="info"),
        sa.Column("event", sa.String(length=64), nullable=False),
        sa.Column("message", sa.Text(), nullable=True),
        sa.Column("data", JSONB(), nullable=False, server_default="{}"),
        sa.Column("ts", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_ingestion_job_events_asset_id", "ingestion_job_events", ["asset_id"])
    op.create_index("ix_ingestion_job_events_job_id", "ingestion_job_events", ["job_id"])


def downgrade() -> None:
    op.drop_index("ix_ingestion_job_events_job_id", table_name="ingestion_job_events")
    op.drop_index("ix_ingestion_job_events_asset_id", table_name="ingestion_job_events")
    op.drop_table("ingestion_job_events")
