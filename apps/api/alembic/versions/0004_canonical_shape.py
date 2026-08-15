"""canonical shape — tombstone for a revision that shipped and was then withdrawn

Revision ID: 0004_canonical_shape
Revises: 0003_google_identity
Create Date: 2026-08-15

**This migration intentionally does nothing.** It exists only so Alembic can resolve its own
history.

The original `0004_canonical_shape` added three columns to `knowledge_assets`
(`canonical_shape`, `render_version`, `page_manifest`) for the citation viewer. It was
deployed and applied to production. The viewer was then reverted, and that revert deleted
this file — but a deleted migration does not un-apply itself. Production's `alembic_version`
table still read `0004_canonical_shape`, so every subsequent `alembic upgrade head` failed
with:

    Can't locate revision identified by '0004_canonical_shape'

which killed the api container at startup (the entrypoint runs migrations under `set -e`), so
no deploy could reach a healthy state.

Restoring the revision *id* is what repairs the chain. Restoring its *effects* would be wrong
— the feature is gone — so `upgrade()` is empty and the columns it used to add are dropped by
`0005_drop_canonical_shape` instead. That split is deliberate: databases already stamped at
this revision skip straight past it to 0005 (which does the cleanup), while a fresh database
runs this as a no-op and 0005 finds nothing to drop. Both paths converge on the same schema.

The lesson, recorded here because the file is otherwise inexplicable: once a migration has
been applied anywhere, revert it with a *new* migration. Never by deleting the old one.
"""

revision = "0004_canonical_shape"
down_revision = "0003_google_identity"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """No-op. See the module docstring — this revision exists purely to link history."""


def downgrade() -> None:
    """No-op, symmetrically."""
