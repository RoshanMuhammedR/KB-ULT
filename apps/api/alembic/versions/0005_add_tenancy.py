"""add tenancy: tenants, users, refresh_tokens + tenant_id/user_id on domain tables

Revision ID: 0005_add_tenancy
Revises: 0004_add_ingestion_job_events
Create Date: 2026-07-18

Additive & non-breaking: domain columns are added NULLABLE, existing rows are backfilled
to a seeded default tenant/user, then set NOT NULL. Runs on the migration connection
(not SessionLocal), so the tenant auto-filter is not attached here.
"""

import uuid

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID

revision = "0005_add_tenancy"
down_revision = "0004_add_ingestion_job_events"
branch_labels = None
depends_on = None

# Every table that gains tenant_id/user_id (mirrors the TenantScoped mixin).
DOMAIN_TABLES = [
    "knowledge_bases",
    "knowledge_assets",
    "chunks",
    "embeddings",
    "ingestion_jobs",
    "ingestion_job_events",
]

# Stable ids for the seeded default tenant/user that existing single-tenant data is
# attributed to. Generated at migration authoring time so upgrade is deterministic.
DEFAULT_TENANT_ID = "00000000-0000-0000-0000-000000000001"
DEFAULT_USER_ID = "00000000-0000-0000-0000-000000000002"


def upgrade() -> None:
    # 1. Root tables ---------------------------------------------------------------
    op.create_table(
        "tenants",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("domain", sa.String(length=255), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False, server_default="active"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_tenants_domain", "tenants", ["domain"], unique=True)

    op.create_table(
        "users",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "tenant_id",
            UUID(as_uuid=True),
            sa.ForeignKey("tenants.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("email", sa.String(length=320), nullable=False),
        sa.Column("password_hash", sa.String(length=255), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False, server_default="active"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint("tenant_id", name="uq_users_one_per_tenant"),
        sa.UniqueConstraint("tenant_id", "email", name="uq_users_tenant_email"),
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
        sa.Column("token_hash", sa.String(length=128), nullable=False),
        sa.Column("family_id", UUID(as_uuid=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_refresh_tokens_user_id", "refresh_tokens", ["user_id"])
    op.create_index("ix_refresh_tokens_token_hash", "refresh_tokens", ["token_hash"], unique=True)
    op.create_index("ix_refresh_tokens_family_id", "refresh_tokens", ["family_id"])

    # 2. Add tenant_id/user_id (nullable first) to every domain table --------------
    for table in DOMAIN_TABLES:
        op.add_column(table, sa.Column("tenant_id", UUID(as_uuid=True), nullable=True))
        op.add_column(table, sa.Column("user_id", UUID(as_uuid=True), nullable=True))

    # 3. Seed the default tenant + user (the seeded user has an unusable password) --
    op.execute(
        f"INSERT INTO tenants (id, name, domain, status) "
        f"VALUES ('{DEFAULT_TENANT_ID}', 'Default Tenant', 'default', 'active')"
    )
    op.execute(
        f"INSERT INTO users (id, tenant_id, email, password_hash, status) "
        f"VALUES ('{DEFAULT_USER_ID}', '{DEFAULT_TENANT_ID}', 'default@localhost', '!disabled', 'active')"
    )

    # 4. Backfill existing rows to the default tenant/user -------------------------
    for table in DOMAIN_TABLES:
        op.execute(
            f"UPDATE {table} SET tenant_id = '{DEFAULT_TENANT_ID}'::uuid, "
            f"user_id = '{DEFAULT_USER_ID}'::uuid"
        )

    # 5. Enforce NOT NULL + FKs + indexes now that no NULLs remain -----------------
    for table in DOMAIN_TABLES:
        op.alter_column(table, "tenant_id", nullable=False)
        op.alter_column(table, "user_id", nullable=False)
        op.create_foreign_key(
            f"fk_{table}_tenant_id", table, "tenants", ["tenant_id"], ["id"], ondelete="CASCADE"
        )
        op.create_foreign_key(
            f"fk_{table}_user_id", table, "users", ["user_id"], ["id"], ondelete="CASCADE"
        )
        op.create_index(f"ix_{table}_tenant_id", table, ["tenant_id"])
        op.create_index(f"ix_{table}_user_id", table, ["user_id"])


def downgrade() -> None:
    for table in DOMAIN_TABLES:
        op.drop_index(f"ix_{table}_user_id", table_name=table)
        op.drop_index(f"ix_{table}_tenant_id", table_name=table)
        op.drop_constraint(f"fk_{table}_user_id", table, type_="foreignkey")
        op.drop_constraint(f"fk_{table}_tenant_id", table, type_="foreignkey")
        op.drop_column(table, "user_id")
        op.drop_column(table, "tenant_id")

    op.drop_index("ix_refresh_tokens_family_id", table_name="refresh_tokens")
    op.drop_index("ix_refresh_tokens_token_hash", table_name="refresh_tokens")
    op.drop_index("ix_refresh_tokens_user_id", table_name="refresh_tokens")
    op.drop_table("refresh_tokens")

    op.drop_index("ix_users_tenant_id", table_name="users")
    op.drop_table("users")

    op.drop_index("ix_tenants_domain", table_name="tenants")
    op.drop_table("tenants")
