"""finish the citation-viewer revert — drop the columns it left behind

Revision ID: 0005_drop_canonical_shape
Revises: 0004_canonical_shape
Create Date: 2026-08-15

The citation viewer was reverted in code, but its schema change had already been applied to
production and stayed there: `knowledge_assets` kept `canonical_shape`, `render_version` and
`page_manifest` long after the last line that read them was deleted.

They were harmless — the two NOT NULL columns carry server defaults, so inserts kept working —
which is exactly why the drift went unnoticed. This completes the revert.

`IF EXISTS` because this runs against two different starting points: a production database
that applied the original 0004 and therefore *has* the columns, and a fresh database that
went through the 0004 tombstone and therefore does not. Both end up in the same shape.
"""

from alembic import op

revision = "0005_drop_canonical_shape"
down_revision = "0004_canonical_shape"
branch_labels = None
depends_on = None

_COLUMNS = ("canonical_shape", "render_version", "page_manifest")


def upgrade() -> None:
    for column in _COLUMNS:
        op.execute(f"ALTER TABLE knowledge_assets DROP COLUMN IF EXISTS {column}")


def downgrade() -> None:
    # Deliberately not restored. The feature that needed these columns no longer exists, so
    # recreating them on downgrade would resurrect dead schema and nothing would populate it.
    pass
