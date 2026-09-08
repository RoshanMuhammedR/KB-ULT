"""knowledge bases get an identity, and a source can live in several of them

Revision ID: 0016_kb_identity
Revises: 0015_conversation_kbs
Create Date: 2026-09-08

Two changes, together because both exist to make a base something a person recognises rather
than a row they have to remember the name of.

**Identity.** `description` and `colour` on `knowledge_bases`. A list of bases with nothing but
names is a list you have to read; the point of a base is to be picked out at a glance.

**Membership.** A source could belong to exactly one base, because `knowledge_assets` carries
a non-null `knowledge_base_id`. That column stays and keeps meaning "the base this was
uploaded into" — it is what the library groups by, it is NOT NULL, and every existing row has
one. This table is membership on top of it, so the same contract can sit in Legal and in
Onboarding without being ingested, chunked and embedded twice.

Backfilled with one row per current asset, so nothing already there changes what it is a
member of.

`ON DELETE CASCADE` on both sides. Deleting a base removes the memberships, not the sources:
a source that was also in two other bases is still wanted, and one that was only here becomes
a source in no base — which the library still shows, because it is still the user's file.
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID

revision = "0016_kb_identity"
down_revision = "0015_conversation_kbs"
branch_labels = None
depends_on = None

_RLS_PREDICATE = (
    "current_setting('app.tenant_bypass', true) = 'on' "
    "OR tenant_id = NULLIF(current_setting('app.current_tenant', true), '')::uuid"
)


def upgrade() -> None:
    # --- Identity -------------------------------------------------------------------
    op.add_column("knowledge_bases", sa.Column("description", sa.Text(), nullable=True))
    # A token name, not a hex value: the client owns what "amber" looks like in each theme,
    # and storing `#f6552c` would freeze one theme's palette into the database.
    op.add_column(
        "knowledge_bases", sa.Column("colour", sa.String(length=32), nullable=True)
    )

    # --- Membership -----------------------------------------------------------------
    op.create_table(
        "knowledge_asset_bases",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "knowledge_asset_id",
            UUID(as_uuid=True),
            sa.ForeignKey("knowledge_assets.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "knowledge_base_id",
            UUID(as_uuid=True),
            sa.ForeignKey("knowledge_bases.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "tenant_id",
            UUID(as_uuid=True),
            sa.ForeignKey("tenants.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "user_id",
            UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        # Adding the same source to the same base twice is a no-op, not a second row.
        sa.UniqueConstraint(
            "knowledge_asset_id", "knowledge_base_id", name="uq_asset_base_membership"
        ),
    )

    # Retrieval joins from a base to its assets on every query, so that direction is the one
    # that needs the index. The unique constraint already covers the other.
    op.create_index("ix_asset_bases_base", "knowledge_asset_bases", ["knowledge_base_id"])
    op.create_index("ix_asset_bases_tenant_id", "knowledge_asset_bases", ["tenant_id"])
    op.create_index("ix_asset_bases_user_id", "knowledge_asset_bases", ["user_id"])

    # Backfill from the column every asset already has. Copying tenant_id/user_id from the
    # asset keeps the new rows inside the same RLS policy without this migration needing to
    # know who any of them belong to.
    op.execute(
        """
        INSERT INTO knowledge_asset_bases
            (id, knowledge_asset_id, knowledge_base_id, tenant_id, user_id)
        SELECT gen_random_uuid(), a.id, a.knowledge_base_id, a.tenant_id, a.user_id
        FROM knowledge_assets a
        """
    )

    op.execute("ALTER TABLE knowledge_asset_bases ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE knowledge_asset_bases FORCE ROW LEVEL SECURITY")
    op.execute(
        f"CREATE POLICY tenant_isolation ON knowledge_asset_bases "
        f"USING ({_RLS_PREDICATE}) WITH CHECK ({_RLS_PREDICATE})"
    )


def downgrade() -> None:
    op.execute("DROP POLICY IF EXISTS tenant_isolation ON knowledge_asset_bases")
    op.execute("ALTER TABLE knowledge_asset_bases NO FORCE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE knowledge_asset_bases DISABLE ROW LEVEL SECURITY")
    op.drop_table("knowledge_asset_bases")
    op.drop_column("knowledge_bases", "colour")
    op.drop_column("knowledge_bases", "description")
