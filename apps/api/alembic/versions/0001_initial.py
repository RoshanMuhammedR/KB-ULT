"""initial schema — tenancy, email/password auth, and the ingestion pipeline

Revision ID: 0001_initial
Revises:
Create Date: 2026-08-08

This is a fresh baseline, not an evolution: the previous six revisions were collapsed into
one when domain-based auth was replaced with email + password and the database was reset.
There is therefore no data to preserve, so tenant_id/user_id are NOT NULL from birth rather
than the add-nullable / backfill / tighten dance an in-place migration would have needed.

Layout mirrors `infrastructure/database/models.py`:
  * `tenants` / `users` / `refresh_tokens` are the root of tenancy and are NOT tenant-scoped
    — they are read pre-auth, under `system_scope`.
  * every domain table carries its own `tenant_id` + `user_id` (the `TenantScoped` mixin) so
    both the ORM filter and the RLS policy can key on the row itself, with no join.

The final block enables Row-Level Security as the database-side backstop for the ORM filter.
DDL is not subject to RLS, so this migration runs fine; but any *future data* migration
touching these tables must set `app.current_tenant` (or `app.tenant_bypass`) itself, since
the Alembic connection has no `after_begin` listener.
"""

from alembic import op
import sqlalchemy as sa
from pgvector.sqlalchemy import Vector
from sqlalchemy.dialects import postgresql
from sqlalchemy.dialects.postgresql import JSONB, UUID

revision = "0001_initial"
down_revision = None
branch_labels = None
depends_on = None

# Every table carrying tenant_id/user_id — i.e. everything the RLS policy protects.
DOMAIN_TABLES = [
    "knowledge_bases",
    "knowledge_assets",
    "chunks",
    "embeddings",
    "ingestion_jobs",
    "ingestion_job_events",
]

# Bypass (system_scope) OR the row belongs to the current tenant. An unset GUC makes the
# predicate NULL, which returns zero rows — fail closed.
_RLS_PREDICATE = (
    "current_setting('app.tenant_bypass', true) = 'on' "
    "OR tenant_id = NULLIF(current_setting('app.current_tenant', true), '')::uuid"
)


def _tenant_columns() -> list[sa.Column]:
    """The `TenantScoped` pair, added to every domain table."""
    return [
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
    ]


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")

    # --- Roots of tenancy ------------------------------------------------------------
    op.create_table(
        "tenants",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        # Display label only — deliberately not unique. A tenant has no addressable name.
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False, server_default="active"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
    )

    op.create_table(
        "users",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "tenant_id",
            UUID(as_uuid=True),
            sa.ForeignKey("tenants.id", ondelete="CASCADE"),
            nullable=False,
        ),
        # Globally unique: this is the whole of a login's subject resolution.
        sa.Column("email", sa.String(length=320), nullable=False),
        sa.Column("password_hash", sa.String(length=255), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False, server_default=""),
        sa.Column("status", sa.String(length=16), nullable=False, server_default="active"),
        sa.Column("email_verified_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint("email", name="uq_users_email"),
    )
    op.create_index("ix_users_tenant_id", "users", ["tenant_id"])

    op.create_table(
        "refresh_tokens",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "user_id",
            UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "tenant_id",
            UUID(as_uuid=True),
            sa.ForeignKey("tenants.id", ondelete="CASCADE"),
            nullable=False,
        ),
        # Only the digest is stored, never the token itself.
        sa.Column("token_hash", sa.String(length=128), nullable=False),
        # Rotation lineage: reusing a revoked token revokes its whole family.
        sa.Column("family_id", UUID(as_uuid=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_refresh_tokens_user_id", "refresh_tokens", ["user_id"])
    op.create_index("ix_refresh_tokens_token_hash", "refresh_tokens", ["token_hash"], unique=True)
    op.create_index("ix_refresh_tokens_family_id", "refresh_tokens", ["family_id"])

    # --- Domain tables ---------------------------------------------------------------
    op.create_table(
        "knowledge_bases",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("owner_id", sa.String(length=255), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        *_tenant_columns(),
    )

    op.create_table(
        "knowledge_assets",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("knowledge_base_id", UUID(as_uuid=True), sa.ForeignKey("knowledge_bases.id"), nullable=False),
        sa.Column("lineage_id", UUID(as_uuid=True), nullable=False, index=True),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("filename", sa.String(length=512), nullable=False),
        sa.Column("title", sa.String(length=512), nullable=True),
        sa.Column("source_type", sa.String(length=64), nullable=False),
        sa.Column("storage_key", sa.String(length=1024), nullable=False, server_default=""),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("failed_step", sa.String(length=64), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("text_content", sa.Text(), nullable=True),
        sa.Column("metadata", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("superseded_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        *_tenant_columns(),
        sa.UniqueConstraint("lineage_id", "version", name="uq_asset_lineage_version"),
    )

    op.create_table(
        "chunks",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("knowledge_asset_id", UUID(as_uuid=True), sa.ForeignKey("knowledge_assets.id", ondelete="CASCADE"), nullable=False),
        sa.Column("chunk_index", sa.Integer(), nullable=False),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("metadata", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        *_tenant_columns(),
        sa.UniqueConstraint("knowledge_asset_id", "chunk_index", name="uq_chunk_asset_index"),
    )

    op.create_table(
        "embeddings",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("chunk_id", UUID(as_uuid=True), sa.ForeignKey("chunks.id", ondelete="CASCADE"), nullable=False),
        sa.Column("model", sa.String(length=255), nullable=False),
        sa.Column("dimensions", sa.Integer(), nullable=False),
        sa.Column("vector", Vector(1536), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        *_tenant_columns(),
        sa.UniqueConstraint("chunk_id", "model", name="uq_embedding_chunk_model"),
    )

    op.create_table(
        "ingestion_jobs",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("asset_id", UUID(as_uuid=True), sa.ForeignKey("knowledge_assets.id", ondelete="CASCADE"), nullable=False),
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
        *_tenant_columns(),
    )
    op.create_index("ix_ingestion_jobs_asset_id", "ingestion_jobs", ["asset_id"])
    op.create_index("ix_ingestion_jobs_status", "ingestion_jobs", ["status"])

    op.create_table(
        "ingestion_job_events",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("asset_id", UUID(as_uuid=True), sa.ForeignKey("knowledge_assets.id", ondelete="CASCADE"), nullable=False),
        # Nullable: an event may outlive the job that produced it.
        sa.Column("job_id", UUID(as_uuid=True), sa.ForeignKey("ingestion_jobs.id", ondelete="CASCADE"), nullable=True),
        sa.Column("level", sa.String(length=16), nullable=False, server_default="info"),
        sa.Column("event", sa.String(length=64), nullable=False),
        sa.Column("message", sa.Text(), nullable=True),
        sa.Column("data", JSONB(), nullable=False, server_default="{}"),
        sa.Column("ts", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        *_tenant_columns(),
    )
    op.create_index("ix_ingestion_job_events_asset_id", "ingestion_job_events", ["asset_id"])
    op.create_index("ix_ingestion_job_events_job_id", "ingestion_job_events", ["job_id"])

    # --- Indexes ---------------------------------------------------------------------
    for table in DOMAIN_TABLES:
        op.create_index(f"ix_{table}_tenant_id", table, ["tenant_id"])
        op.create_index(f"ix_{table}_user_id", table, ["user_id"])

    op.create_index("ix_assets_active", "knowledge_assets", ["knowledge_base_id", "superseded_at", "status"])
    op.create_index(
        "ix_embeddings_vector",
        "embeddings",
        ["vector"],
        postgresql_using="ivfflat",
        postgresql_with={"lists": 100},
        postgresql_ops={"vector": "vector_cosine_ops"},
    )

    # --- Row-Level Security ----------------------------------------------------------
    # FORCE makes the policy apply to the table owner too, so the app needs no separate
    # non-owner role for this to bite.
    for table in DOMAIN_TABLES:
        op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
        op.execute(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY")
        op.execute(
            f"CREATE POLICY tenant_isolation ON {table} "
            f"USING ({_RLS_PREDICATE}) WITH CHECK ({_RLS_PREDICATE})"
        )


def downgrade() -> None:
    for table in DOMAIN_TABLES:
        op.execute(f"DROP POLICY IF EXISTS tenant_isolation ON {table}")
        op.execute(f"ALTER TABLE {table} NO FORCE ROW LEVEL SECURITY")
        op.execute(f"ALTER TABLE {table} DISABLE ROW LEVEL SECURITY")

    op.drop_table("ingestion_job_events")
    op.drop_table("ingestion_jobs")
    op.drop_table("embeddings")
    op.drop_table("chunks")
    op.drop_table("knowledge_assets")
    op.drop_table("knowledge_bases")
    op.drop_table("refresh_tokens")
    op.drop_table("users")
    op.drop_table("tenants")
