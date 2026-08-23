"""Langfuse tracing, wired through LangChain's callback mechanism.

Because the query pipeline is LangChain-native, most of the trace tree comes for free: every
`ainvoke` on a model or a retriever reports itself, so the spans for query resolution,
reranking, sufficiency and grounding appear without any instrumentation at their call sites.
What this module adds is the frame around them — one trace per question, carrying the tenant
and conversation so a trace can be found from a support request rather than by timestamp.

Disabled by default. With no keys configured `handler()` returns None, every call site
degrades to an empty callback list, and nothing about the pipeline changes — which is what
makes it safe to leave the calls in place unconditionally.
"""

from __future__ import annotations

from functools import lru_cache
from typing import Any

import structlog

from src.core.config import Settings, get_settings
from src.core.tenant_context import try_current_tenant_id

logger = structlog.get_logger(__name__)


@lru_cache
def _client(public_key: str, secret_key: str, host: str) -> Any | None:
    """One Langfuse client per process. Cached on the credentials so a settings change in a
    test creates a new one rather than silently reusing the old."""
    try:
        from langfuse import Langfuse
    except ImportError:  # pragma: no cover - the package is a declared dependency
        logger.warning("langfuse_not_installed")
        return None

    try:
        return Langfuse(public_key=public_key, secret_key=secret_key, host=host)
    except Exception:  # noqa: BLE001 - tracing must never break the thing it observes
        logger.warning("langfuse_init_failed", host=host)
        return None


def is_enabled(settings: Settings | None = None) -> bool:
    settings = settings or get_settings()
    return bool(settings.langfuse_public_key and settings.langfuse_secret_key)


def handler(
    *,
    trace_name: str = "agentic_query",
    conversation_id: str | None = None,
    settings: Settings | None = None,
) -> Any | None:
    """A LangChain callback handler that reports into Langfuse, or None when disabled.

    Tagged with the tenant so traces can be filtered to one workspace — the id only, never
    anything the user wrote, because a trace store is not somewhere a document's contents
    should end up by accident.
    """
    settings = settings or get_settings()
    if not is_enabled(settings):
        return None

    if _client(settings.langfuse_public_key, settings.langfuse_secret_key, settings.langfuse_host) is None:
        return None

    try:
        from langfuse.langchain import CallbackHandler
    except ImportError:  # pragma: no cover
        logger.warning("langfuse_langchain_handler_unavailable")
        return None

    tenant_id = try_current_tenant_id()
    metadata = {
        "langfuse_session_id": conversation_id,
        "langfuse_user_id": str(tenant_id) if tenant_id else None,
        "langfuse_tags": [trace_name],
    }
    try:
        return CallbackHandler(metadata={k: v for k, v in metadata.items() if v is not None})
    except Exception:  # noqa: BLE001
        logger.warning("langfuse_handler_failed")
        return None


def callbacks(**kwargs) -> list[Any]:
    """The `callbacks` value for a `RunnableConfig`. Empty list when tracing is off."""
    active = handler(**kwargs)
    return [active] if active is not None else []


def flush() -> None:
    """Push buffered spans. Called on shutdown so a short-lived process still reports."""
    settings = get_settings()
    if not is_enabled(settings):
        return
    client = _client(settings.langfuse_public_key, settings.langfuse_secret_key, settings.langfuse_host)
    if client is None:
        return
    try:
        client.flush()
    except Exception:  # noqa: BLE001
        logger.warning("langfuse_flush_failed")
