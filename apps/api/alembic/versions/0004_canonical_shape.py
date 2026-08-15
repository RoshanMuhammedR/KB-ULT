"""canonical shape + render version + page manifest on knowledge_assets

Revision ID: 0004_canonical_shape
Revises: 0003_google_identity
Create Date: 2026-08-15

Three columns that let the viewer render a source without knowing its file format.

  * `canonical_shape` — how this source is *displayed*, not what it is: "paged" (PDF, PPTX),
    "timeline" (audio, YouTube), or "text" (Markdown, and anything whose rendition failed).
    The client switches on these three values and never learns about formats, so adding a
    format later is a server-side change only.
  * `render_version` — bumped whenever the rendition pipeline changes. It is part of the
    object key for page images, so v2 coordinates can never be paired with v1 images: the
    viewer reads the current version off this row, and old versions are simply orphaned.
  * `page_manifest` — per-page geometry `{"pages": [{"n", "w", "h", "ext"}]}` so the viewer
    can size its canvas before an image loads, and knows whether a page is a raster (jpg) or
    a vector reconstruction (svg).

Backfill maps existing `source_type` onto a shape so already-ingested sources keep working
without a reprocess. `render_version` starts at 0, meaning "no rendition built yet".
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0004_canonical_shape"
down_revision = "0003_google_identity"
branch_labels = None
depends_on = None

# source_type -> canonical_shape. PPTX starts as "text" and flips to "paged" once the slide
# renderer exists; that flip is exactly the "new format is a server-side change" claim.
_SHAPE_BY_SOURCE_TYPE = {
    "pdf": "paged",
    "pptx": "paged",
    "audio": "timeline",
    "youtube": "timeline",
    "markdown": "text",
}


def upgrade() -> None:
    op.add_column(
        "knowledge_assets",
        sa.Column("canonical_shape", sa.String(length=16), nullable=False, server_default="text"),
    )
    op.add_column(
        "knowledge_assets",
        sa.Column("render_version", sa.Integer(), nullable=False, server_default="0"),
    )
    op.add_column(
        "knowledge_assets",
        sa.Column("page_manifest", postgresql.JSONB(), nullable=True),
    )

    for source_type, shape in _SHAPE_BY_SOURCE_TYPE.items():
        op.execute(
            sa.text(
                "UPDATE knowledge_assets SET canonical_shape = :shape WHERE source_type = :source_type"
            ).bindparams(shape=shape, source_type=source_type)
        )


def downgrade() -> None:
    op.drop_column("knowledge_assets", "page_manifest")
    op.drop_column("knowledge_assets", "render_version")
    op.drop_column("knowledge_assets", "canonical_shape")
