"""google sign-in — link a Google subject to a user, and allow password-less accounts

Revision ID: 0003_google_identity
Revises: 0002_conversations
Create Date: 2026-08-15

`users` is the root of the tenant chain and is NOT tenant-scoped (it is read pre-auth under
`system_scope`), so unlike 0002 there is no RLS policy to add here — only two column changes:

  * `google_sub` — Google's stable subject id, unique so one Google account maps to exactly
    one user. Nullable: password-only accounts never have one.
  * `password_hash` becomes nullable — an account created through Google has no password at
    all. `AuthService.login` treats a NULL hash as a normal credential failure, so it stays
    indistinguishable from a wrong password and leaks nothing.
"""

from alembic import op
import sqlalchemy as sa

revision = "0003_google_identity"
down_revision = "0002_conversations"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("users", sa.Column("google_sub", sa.String(length=255), nullable=True))
    op.create_unique_constraint("uq_users_google_sub", "users", ["google_sub"])
    op.alter_column("users", "password_hash", existing_type=sa.String(length=255), nullable=True)


def downgrade() -> None:
    # Password-less accounts cannot survive the column going back to NOT NULL; they are
    # deleted rather than silently given an unusable hash that would look like a real one.
    op.execute("DELETE FROM users WHERE password_hash IS NULL")
    op.alter_column("users", "password_hash", existing_type=sa.String(length=255), nullable=False)
    op.drop_constraint("uq_users_google_sub", "users", type_="unique")
    op.drop_column("users", "google_sub")
