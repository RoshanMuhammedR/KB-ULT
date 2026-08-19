"""A small circuit breaker for calls to the AI gateway.

The failure this exists for: when the provider is down, every ingestion job still walks its
full retry budget — three attempts, ~35 seconds of exponential backoff — before failing, and
every queued job after it does the same. A hundred queued sources become a hundred pointless
round-trips against a host that is not answering, each holding a worker slot and a database
session while it waits out its timeout.

A breaker turns that into one round-trip per cooldown window. After `failure_threshold`
consecutive failures it opens and fails calls immediately for `reset_after_seconds`; the
first call after that is a trial. If the trial succeeds the breaker closes and normal
service resumes; if it fails the window starts again.

Deliberately not a library: this is ~50 lines of state machine, it needs no configuration
surface, and it stays in `infrastructure/` where every other third-party concern lives —
`application/` never learns that provider calls can be short-circuited.
"""

from __future__ import annotations

import threading
import time
from typing import Callable, TypeVar

import structlog

from src.core.exceptions import ProviderUnavailableError

logger = structlog.get_logger(__name__)

T = TypeVar("T")

# Five consecutive failures is comfortably past "one unlucky request" and well short of the
# volume of dead calls this is meant to prevent. Thirty seconds is long enough that a
# restarting provider gets time to come back, short enough that recovery is not noticeable
# to someone who uploads a source right after the outage ends.
_FAILURE_THRESHOLD = 5
_RESET_AFTER_SECONDS = 30.0


class CircuitBreaker:
    """Trips after consecutive failures; lets one call through per cooldown to test."""

    def __init__(
        self,
        name: str,
        *,
        failure_threshold: int = _FAILURE_THRESHOLD,
        reset_after_seconds: float = _RESET_AFTER_SECONDS,
    ) -> None:
        self.name = name
        self.failure_threshold = failure_threshold
        self.reset_after_seconds = reset_after_seconds
        # Guarded by a lock because the same breaker is shared by every anyio worker thread
        # in the API and every task thread in the worker process.
        self._lock = threading.Lock()
        self._consecutive_failures = 0
        self._opened_at: float | None = None

    def call(self, fn: Callable[..., T], *args, **kwargs) -> T:
        self._check_open()
        try:
            result = fn(*args, **kwargs)
        except Exception:
            self._record_failure()
            raise
        self._record_success()
        return result

    def _check_open(self) -> None:
        with self._lock:
            if self._opened_at is None:
                return
            elapsed = time.monotonic() - self._opened_at
            if elapsed < self.reset_after_seconds:
                raise ProviderUnavailableError(
                    f"The {self.name} service is not responding. It will be retried "
                    f"automatically in about {round(self.reset_after_seconds - elapsed)}s."
                )
            # Cooldown elapsed: let this one call through as the trial. `_opened_at` is
            # cleared here rather than on success so concurrent callers don't all queue up
            # as trials — they simply resume, and a still-broken provider re-opens the
            # breaker on the next failure.
            self._opened_at = None
            logger.info("circuit_half_open", provider=self.name)

    def _record_failure(self) -> None:
        with self._lock:
            self._consecutive_failures += 1
            if self._consecutive_failures < self.failure_threshold:
                return
            if self._opened_at is None:
                logger.error(
                    "circuit_opened",
                    provider=self.name,
                    consecutive_failures=self._consecutive_failures,
                    cooldown_seconds=self.reset_after_seconds,
                )
            self._opened_at = time.monotonic()

    def _record_success(self) -> None:
        with self._lock:
            if self._consecutive_failures:
                logger.info("circuit_closed", provider=self.name)
            self._consecutive_failures = 0
            self._opened_at = None


# Adapters are built per request/job, so breaker state has to outlive them: it belongs to
# the provider, not to whoever happens to be calling it right now.
_breakers: dict[str, CircuitBreaker] = {}
_registry_lock = threading.Lock()


def get_breaker(name: str) -> CircuitBreaker:
    with _registry_lock:
        breaker = _breakers.get(name)
        if breaker is None:
            breaker = CircuitBreaker(name)
            _breakers[name] = breaker
        return breaker
