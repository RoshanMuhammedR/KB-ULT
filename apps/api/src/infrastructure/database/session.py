from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import Session

from src.core.config import get_settings
from src.infrastructure.database.tenancy import register_tenant_guards


class TenantScopedSession(Session):
    """The sync `Session` class that backs every `AsyncSession` this app creates.

    SQLAlchemy's ORM events are defined on the sync Session, not on `AsyncSession` — under
    asyncio the async layer drives a real sync Session inside a greenlet. Listening on a
    dedicated subclass rather than on `Session` itself keeps the tenant guards attached to
    *our* sessions only, instead of every Session in the process (Alembic's included).
    """


# ORM sessions connect as the non-superuser app role when configured, so Postgres RLS
# applies (see app_database_url). Falls back to the superuser URL when unset.
_settings = get_settings()
engine = create_async_engine(
    _settings.app_database_url or _settings.database_url,
    pool_pre_ping=True,
    # Sized explicitly rather than left on SQLAlchemy's 5+10 default: this pool is what
    # actually caps concurrency. See the arithmetic on `db_pool_size` in core/config.py.
    pool_size=_settings.db_pool_size,
    max_overflow=_settings.db_max_overflow,
    pool_timeout=_settings.db_pool_timeout,
)

SessionLocal = async_sessionmaker(
    bind=engine,
    sync_session_class=TenantScopedSession,
    autoflush=False,
    # Async sessions must not expire attributes on commit: a refresh after the transaction
    # closes would be a lazy IO load, which raises under asyncio rather than silently
    # emitting SQL. Entities are mapped to domain objects before the scope ends anyway.
    expire_on_commit=False,
)

# Attach the tenant auto-filter + stamping + RLS listeners to every session this factory
# makes (request-scoped and worker-scoped alike). Queries on tenant-scoped tables are
# filtered by the current tenant and fail closed if none is set; see database/tenancy.py.
register_tenant_guards(TenantScopedSession)


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    # FastAPI request-scoped session. Commit/rollback is owned by the repositories;
    # this dependency only guarantees the session is closed when the request ends.
    async with SessionLocal() as db:
        yield db


@asynccontextmanager
async def session_scope() -> AsyncGenerator[AsyncSession, None]:
    # Session for code running outside the FastAPI request lifecycle (the ingestion
    # worker, and the streaming chat route whose generator outlives its dependencies).
    # Unlike get_db(), it owns the transaction: commit on clean exit, roll back on any
    # exception, always close.
    async with SessionLocal() as db:
        try:
            yield db
            await db.commit()
        except Exception:
            await db.rollback()
            raise
