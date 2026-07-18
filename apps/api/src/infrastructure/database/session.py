from collections.abc import Generator
from contextlib import contextmanager

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from src.core.config import get_settings
from src.infrastructure.database.tenancy import register_tenant_guards

# ORM sessions connect as the non-superuser app role when configured, so Postgres RLS
# applies (see app_database_url). Falls back to the superuser URL when unset.
_settings = get_settings()
engine = create_engine(
    _settings.app_database_url or _settings.database_url, pool_pre_ping=True
)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)

# Attach the tenant auto-filter + stamping listeners to every session this factory makes
# (request-scoped and worker-scoped alike). Queries on tenant-scoped tables are filtered
# by the current tenant and fail closed if none is set; see database/tenancy.py.
register_tenant_guards(SessionLocal)


def get_db() -> Generator[Session, None, None]:
    # FastAPI request-scoped session. Commit/rollback is owned by the repositories;
    # this dependency only guarantees the session is closed when the request ends.
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


@contextmanager
def session_scope() -> Generator[Session, None, None]:
    # Worker-scoped session for code running outside the FastAPI request lifecycle
    # (i.e. the ingestion worker). Unlike get_db(), it owns the transaction: commit
    # on clean exit, roll back on any exception, always close.
    db = SessionLocal()
    try:
        yield db
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()
