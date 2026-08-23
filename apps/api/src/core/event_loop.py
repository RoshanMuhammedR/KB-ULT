"""Event-loop policy, which on Windows is a correctness requirement rather than a tuning knob.

psycopg's async mode cannot run on the `ProactorEventLoop` that Python selects by default on
Windows — it raises `InterfaceError` on the first connection attempt. Linux, where this
actually deploys, uses an epoll loop and never sees the problem, so the failure only appears
in local development and only once something touches the database.

Calling this before any loop is created switches Windows to the selector policy. It is a
no-op everywhere else, and it must run at import time in every entrypoint — the API, the
Procrastinate worker, and anything driving the async engine from a script — because uvicorn
and the worker each create the loop themselves.
"""

from __future__ import annotations

import asyncio
import sys


def configure_event_loop() -> None:
    if sys.platform != "win32":
        return
    policy = getattr(asyncio, "WindowsSelectorEventLoopPolicy", None)
    if policy is not None and not isinstance(asyncio.get_event_loop_policy(), policy):
        asyncio.set_event_loop_policy(policy())
