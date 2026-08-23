"""parent/child chunks, enriched embedding text, and per-chunk modality

Revision ID: 0009_chunk_hierarchy
Revises: 0008_unique_kb_per_tenant
Create Date: 2026-08-20

Three columns on `chunks`, all in service of retrieval quality:

  * `parent_id` — small-to-big. A fixed-size window is the wrong unit twice over: big enough
    to answer from is too big to match precisely, and small enough to match precisely is too
    small to answer from. Splitting those roles means embedding the small child and sending
    the parent section to the model.

  * `embed_text` — what actually gets vectorised: the chunk prefixed with a sentence naming
    the section it came from. A chunk that reads as a fragment on its own ("It expires after
    30 days.") becomes retrievable once it carries "This is from the termination clause of
    the Q3 vendor contract." `text` is untouched, so display and citations are unaffected —
    and `chunks.fts` is `GENERATED ALWAYS AS to_tsvector('english', text)`, so the lexical
    arm keeps matching the document's own words rather than our prose about it.

  * `modality` — text / pdf / asr / ocr. ASR output is noisier than typed prose and scores
    lower on identical relevance, so it needs its own floor. A column rather than a JSONB
    key because the retrieval filter should not have to unpack a blob to apply it.

No backfill is possible: nothing can invent a parent section for a chunk that was split
without one. Existing rows keep `parent_id IS NULL` (so they behave as their own parent) and
`embed_text IS NULL` (so `text_for_embedding` falls back to `text`), which degrades to
exactly today's behaviour. Re-ingest a source to give it the new structure.
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID

revision = "0009_chunk_hierarchy"
down_revision = "0008_unique_kb_per_tenant"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "chunks",
        sa.Column("parent_id", UUID(as_uuid=True), nullable=True),
    )
    # CASCADE, because `replace_for_asset` deletes an asset's chunks in one statement and
    # does not order parents last. Without it that delete would trip the constraint.
    op.create_foreign_key(
        "fk_chunks_parent_id",
        "chunks",
        "chunks",
        ["parent_id"],
        ["id"],
        ondelete="CASCADE",
    )
    op.create_index("ix_chunks_parent_id", "chunks", ["parent_id"])

    op.add_column("chunks", sa.Column("embed_text", sa.Text(), nullable=True))
    op.add_column(
        "chunks",
        sa.Column(
            "modality",
            sa.String(length=16),
            nullable=False,
            server_default="text",
        ),
    )


def downgrade() -> None:
    op.drop_column("chunks", "modality")
    op.drop_column("chunks", "embed_text")
    op.drop_index("ix_chunks_parent_id", table_name="chunks")
    op.drop_constraint("fk_chunks_parent_id", "chunks", type_="foreignkey")
    op.drop_column("chunks", "parent_id")
