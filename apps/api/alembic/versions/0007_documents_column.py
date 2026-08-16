"""move parsed source documents out of metadata and into their own column

Revision ID: 0007_documents_column
Revises: 0006_hybrid_retrieval
Create Date: 2026-08-16

Handlers used to normalize every source into an untyped dict convention parked inside the
`metadata` JSONB blob (`metadata["segments"] = [{"text", "locator"}]`). That is now a typed
`list[Document]` (LangChain) living in its own column.

Two reasons the column is separate rather than a renamed key:

  * `metadata` is returned verbatim to the browser by `KnowledgeAssetSchema`, and this data
    is the ENTIRE TEXT of the source. Every 2-second ingestion status poll was shipping it,
    and the web app merely hid it behind a `HIDDEN_METADATA` set. It now never leaves the
    server.
  * It is pipeline state with a real type, not free-form annotation, so it reads better as
    a column than as a key in a bag of miscellany.

No backfill. Old rows get `[]`, and the extraction guard in `IngestionService._run_pipeline`
treats an asset with no documents as needing re-extraction — so an asset that failed at the
chunking step before this migration re-parses its source on the next retry instead of
resuming into an empty chunk list. Re-parsing is idempotent, so that costs time, not
correctness.

The stale `metadata->'segments'` key is dropped from existing rows so nothing reads it by
accident and the payload shrinks immediately.
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

revision = "0007_documents_column"
down_revision = "0006_hybrid_retrieval"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "knowledge_assets",
        sa.Column(
            "documents",
            JSONB,
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
    )
    # DDL is not subject to RLS, so this runs fine without setting `app.current_tenant`.
    op.execute("UPDATE knowledge_assets SET metadata = metadata - 'segments'")


def downgrade() -> None:
    # The old shape cannot be reconstructed from the new one without re-parsing (page
    # numbers survive, but the pre-split boundaries are the handler's, not ours), so this
    # only removes the column. Assets then re-extract on their next retry, exactly as they
    # do on upgrade.
    op.drop_column("knowledge_assets", "documents")
