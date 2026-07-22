from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from src.composition import build_authenticators
from src.core.config import get_settings
from src.core.logging import configure_logging
from src.http.middleware import AuthenticationMiddleware, TenantContextMiddleware
from src.http.routes.auth import router as auth_router
from src.http.routes.chat import router as chat_router
from src.http.routes.documents import router as documents_router
from src.http.routes.health import router as health_router
from src.http.routes.jobs import router as jobs_router
from src.http.routes.knowledge_bases import router as knowledge_bases_router
from src.infrastructure.queue.app import app as queue_app

configure_logging()
settings = get_settings()


@asynccontextmanager
async def lifespan(_: FastAPI):
    # Open the Procrastinate connector for the lifetime of the web process so the
    # synchronous `.defer()` in request handlers has a live connection pool. Without
    # this, deferring raises AppNotOpen. The worker process opens the app on its own.
    with queue_app.open():
        yield


app = FastAPI(title="AI Knowledge Base PDF MVP", lifespan=lifespan)

# Middleware runs outermost-first in reverse of add order, so the request flows:
#   CORS → Authentication (resolve Identity) → TenantContext (bind it) → routes.
# Auth and tenant binding are separate concerns: authentication owns credentials (bearer
# now, API keys/OAuth later) and only produces an Identity; the tenant layer binds that
# Identity to the contextvars without caring how it was proven. Both sit inside CORS so
# preflight OPTIONS and 401s still carry CORS headers.
app.add_middleware(TenantContextMiddleware)
app.add_middleware(
    AuthenticationMiddleware,
    authenticators=build_authenticators(settings),
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    # Plus any origin matching the regex (default: mapped `.test` tenant domains + localhost
    # on any port), so the two-app domain-handoff flow works without editing the exact list.
    allow_origin_regex=settings.cors_allowed_origin_regex or None,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(health_router)
app.include_router(auth_router)
app.include_router(documents_router)
app.include_router(jobs_router)
app.include_router(chat_router)
app.include_router(knowledge_bases_router)
