"""add ingestion jobs table

Revision ID: 0003_add_ingestion_jobs
Revises: 0002_add_storage_key
Create Date: 2026-07-17
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID

revision = "0003_add_ingestion_jobs"
down_revision = "0002_add_storage_key"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "ingestion_jobs",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "asset_id",
            UUID(as_uuid=True),
            sa.ForeignKey("knowledge_assets.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("job_type", sa.String(length=64), nullable=False, server_default="ingest_asset"),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("attempts", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("max_attempts", sa.Integer(), nullable=False, server_default="3"),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column("scheduled_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_ingestion_jobs_asset_id", "ingestion_jobs", ["asset_id"])
    op.create_index("ix_ingestion_jobs_status", "ingestion_jobs", ["status"])


def downgrade() -> None:
    op.drop_index("ix_ingestion_jobs_status", table_name="ingestion_jobs")
    op.drop_index("ix_ingestion_jobs_asset_id", table_name="ingestion_jobs")
    op.drop_table("ingestion_jobs")
