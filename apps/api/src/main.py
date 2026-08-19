from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from src.composition import build_authenticators
from src.core.config import get_settings
from src.core.logging import configure_logging
from src.http.error_handlers import register_error_handlers
from src.http.middleware import (
    AuthenticationMiddleware,
    TenantContextMiddleware,
    UploadSizeLimitMiddleware,
)
from src.http.routes.auth import router as auth_router
from src.http.routes.chat import router as chat_router
from src.http.routes.conversations import router as conversations_router
from src.http.routes.documents import router as documents_router
from src.http.routes.health import router as health_router
from src.http.routes.jobs import router as jobs_router
from src.http.routes.knowledge_bases import router as knowledge_bases_router
from src.infrastructure.database.session import engine
from src.infrastructure.database.tenancy import assert_rls_enforced
from src.infrastructure.queue.app import app as queue_app

configure_logging()
settings = get_settings()


@asynccontextmanager
async def lifespan(_: FastAPI):
    # Verify the database backstop before serving a single request: if the ORM role
    # bypasses RLS, tenant isolation is running on one layer instead of two and nothing
    # about the running system would ever show it. Raises here (killing the boot) when
    # REQUIRE_RLS is set; warns loudly otherwise.
    assert_rls_enforced(engine, required=settings.require_rls)

    # Open the Procrastinate connector for the lifetime of the web process so the
    # synchronous `.defer()` in request handlers has a live connection pool. Without
    # this, deferring raises AppNotOpen. The worker process opens the app on its own.
    with queue_app.open():
        yield


app = FastAPI(title="AI Knowledge Base PDF MVP", lifespan=lifespan)

# Middleware runs outermost-first in reverse of add order, so the request flows:
#   CORS → Authentication (resolve Identity) → UploadSizeLimit → TenantContext → routes.
# Auth and tenant binding are separate concerns: authentication owns credentials (bearer
# now, API keys/OAuth later) and only produces an Identity; the tenant layer binds that
# Identity to the contextvars without caring how it was proven. Both sit inside CORS so
# preflight OPTIONS and 401s still carry CORS headers.
app.add_middleware(TenantContextMiddleware)
# Added before Authentication, so it ends up INSIDE it: an oversized body should still be
# rejected as 413 rather than 401, but only for a caller who proved who they are — an
# anonymous request has no business getting a size-limit reading of our configuration.
app.add_middleware(UploadSizeLimitMiddleware, max_bytes=settings.max_upload_bytes)
app.add_middleware(
    AuthenticationMiddleware,
    authenticators=build_authenticators(settings),
)

app.add_middleware(
    CORSMiddleware,
    # Only relevant in local dev: in production Caddy serves the apps and the API from one
    # origin, so browser requests to /api/* are same-origin and never preflight.
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Backstop only — routes still translate their own exceptions. This catches the ones that
# escape, so a domain error never reaches the client as an unshaped 500.
register_error_handlers(app)

app.include_router(health_router)
app.include_router(auth_router)
app.include_router(documents_router)
app.include_router(jobs_router)
app.include_router(chat_router)
app.include_router(conversations_router)
app.include_router(knowledge_bases_router)
