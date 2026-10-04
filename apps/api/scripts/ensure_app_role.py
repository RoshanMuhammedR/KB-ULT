"""Create (or re-sync) the non-superuser role the app's ORM sessions connect as.

Superusers — and Supabase's `postgres`, which has BYPASSRLS — skip Row-Level Security
entirely, so the ORM has to connect as a role that does not. This script makes that role
exist with the password in APP_DB_PASSWORD and the grants the app needs. It connects with
DATABASE_URL, the owner role that runs migrations.

Idempotent: the entrypoint runs it on every boot right after `alembic upgrade head`, so the
grants always cover tables a new migration just created, and rotating APP_DB_PASSWORD on the
host is all a password change takes.

    python scripts/ensure_app_role.py
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import psycopg  # noqa: E402
from psycopg import sql  # noqa: E402

from src.core.config import APP_DB_ROLE, get_settings  # noqa: E402

# Roles PostgREST serves requests as on Supabase. The app never uses the Data API, but
# Supabase grants these roles access to every table in `public` by default — and tables
# like `users` and the queue's are not tenant-scoped, so RLS would not stand in the way.
# Revoking is a no-op wherever the roles do not exist (local Postgres).
_DATA_API_ROLES = ("anon", "authenticated")


def main() -> None:
    settings = get_settings()
    if not settings.app_db_password:
        print("APP_DB_PASSWORD is unset; skipping app role setup")
        return

    role = sql.Identifier(APP_DB_ROLE)
    # Procrastinate's connector wants the same plain libpq DSN.
    with psycopg.connect(settings.database_url.replace("+psycopg", "", 1), autocommit=True) as conn:
        exists = conn.execute(
            "SELECT 1 FROM pg_roles WHERE rolname = %s", (APP_DB_ROLE,)
        ).fetchone()
        if not exists:
            conn.execute(
                sql.SQL("CREATE ROLE {} LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE").format(role)
            )
        # DDL takes no bind parameters, so the password goes in as a quoted literal.
        conn.execute(
            sql.SQL("ALTER ROLE {} PASSWORD {}").format(
                role, sql.Literal(settings.app_db_password)
            )
        )

        database = conn.execute("SELECT current_database()").fetchone()[0]
        for statement in (
            "GRANT CONNECT ON DATABASE {db} TO {role}",
            "GRANT USAGE ON SCHEMA public TO {role}",
            # DML only; RLS still scopes which rows the role can see or write.
            "GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO {role}",
            "GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO {role}",
            "ALTER DEFAULT PRIVILEGES IN SCHEMA public "
            "GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO {role}",
            "ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT USAGE, SELECT ON SEQUENCES TO {role}",
        ):
            conn.execute(sql.SQL(statement).format(db=sql.Identifier(database), role=role))

        present = {
            row[0]
            for row in conn.execute(
                "SELECT rolname FROM pg_roles WHERE rolname = ANY(%s)", (list(_DATA_API_ROLES),)
            )
        }
        for name in sorted(present):
            conn.execute(
                sql.SQL("REVOKE ALL ON ALL TABLES IN SCHEMA public FROM {}").format(
                    sql.Identifier(name)
                )
            )
            conn.execute(
                sql.SQL("REVOKE ALL ON ALL SEQUENCES IN SCHEMA public FROM {}").format(
                    sql.Identifier(name)
                )
            )

    print(f"app role '{APP_DB_ROLE}' ready on database '{database}'")


if __name__ == "__main__":
    main()
