from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from src.core.config import get_settings
from src.core.logging import configure_logging
from src.http.routes.chat import router as chat_router
from src.http.routes.documents import router as documents_router
from src.http.routes.health import router as health_router
from src.http.routes.knowledge_bases import router as knowledge_bases_router

configure_logging()
settings = get_settings()

app = FastAPI(title="AI Knowledge Base PDF MVP")

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(health_router)
app.include_router(documents_router)
app.include_router(chat_router)
app.include_router(knowledge_bases_router)
