-- Creates the non-superuser role the app's ORM sessions connect as, so Postgres
-- Row-Level Security actually applies (superusers, incl. the default POSTGRES_USER,
-- bypass RLS entirely). Migrations and the Procrastinate connector keep using the
-- superuser role for DDL and queue internals.
--
-- Run as a superuser, e.g. via `pnpm run db:app-role`:
--   psql "$SUPERUSER_URL" -v app_password="$APP_DB_PASSWORD" -v db="$POSTGRES_DB" \
--        -f apps/api/scripts/create_app_role.sql
--
-- Idempotent: safe to re-run (it also re-syncs the password and grants).

-- Create the role only if missing (password set separately below to avoid quoting it
-- inside a dynamically-built statement).
SELECT 'CREATE ROLE kb_app LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE'
WHERE NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'kb_app')
\gexec

ALTER ROLE kb_app PASSWORD :'app_password';

GRANT CONNECT ON DATABASE :"db" TO kb_app;
GRANT USAGE ON SCHEMA public TO kb_app;

-- DML on current tables (RLS still scopes what the role can actually see/write).
GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO kb_app;
GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO kb_app;

-- And on any tables/sequences created later (by the superuser) — e.g. future migrations.
ALTER DEFAULT PRIVILEGES IN SCHEMA public
    GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO kb_app;
ALTER DEFAULT PRIVILEGES IN SCHEMA public
    GRANT USAGE, SELECT ON SEQUENCES TO kb_app;
