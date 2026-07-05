"""add storage key to knowledge assets

Revision ID: 0002_add_storage_key
Revises: 0001_initial
Create Date: 2026-07-05
"""

from alembic import op
import sqlalchemy as sa

revision = "0002_add_storage_key"
down_revision = "0001_initial"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "knowledge_assets",
        sa.Column("storage_key", sa.String(length=1024), nullable=False, server_default=""),
    )


def downgrade() -> None:
    op.drop_column("knowledge_assets", "storage_key")
