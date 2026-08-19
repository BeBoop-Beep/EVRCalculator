from __future__ import annotations

"""Bounded retries for Supabase writes on the unattended simulation path.

WHY THIS EXISTS
---------------
A scheduled set simulation used to die on its FIRST Supabase hiccup. The
observed failure was a Cloudflare-generated HTML `502 Bad Gateway` surfacing as
``APIError(code=502)`` in the middle of the per-card
``simulation_input_cards`` inserts, roughly 1.8 seconds into the set. The set
was marked failed, the Monte Carlo work that produced the row was thrown away,
and the next set in the queue walked straight into the same 30-second edge
outage.

That failure is INFRASTRUCTURE, not data: the payload was valid and the same
request succeeds moments later. This module retries exactly that class of
failure and nothing else. Classification lives in
:mod:`backend.db.services.data_service_health`, which vetoes a retry whenever
the exception chain carries a real SQLSTATE - so a unique violation, a bad UUID
or an undefined column still fails on the first attempt, loudly.

WHAT THIS MODULE DELIBERATELY DOES NOT DO
-----------------------------------------
It does not make a write idempotent. Retrying is only safe when the caller has
already established that a second attempt cannot duplicate anything - a network
failure can arrive AFTER Postgres committed - so every call site must supply
that guarantee itself (a natural key read-back, an upsert, or a primary key the
client chose). See ``_insert_required_payload`` in
``backend.db.repositories.calculation_runs_repository``.
"""

import logging
import random
import time
from contextlib import contextmanager
from contextvars import ContextVar
from typing import Callable, Iterator, Optional, TypeVar

from supabase import create_client

from backend.db.clients.supabase_client import SUPABASE_KEY, SUPABASE_URL

from backend.db.services.data_service_health import classify_data_service_error


logger = logging.getLogger(__name__)
T = TypeVar("T")

SCRAPER_DB_MAX_ATTEMPTS = 3
_transport_retry_count: ContextVar[int] = ContextVar("supabase_transport_retry_count", default=0)
_persistence_session: ContextVar[Optional["ScraperPersistenceSession"]] = ContextVar(
    "scraper_persistence_session", default=None)


def reset_transport_retry_count() -> None:
    _transport_retry_count.set(0)


def get_transport_retry_count() -> int:
    return _transport_retry_count.get()


class ScraperPersistenceSession:
    """Reuse one healthy client inside one scraper execution context.

    The client is never serialized or stored globally. A transient failure
    invalidates it before the retry backoff, so the next attempt necessarily
    constructs a fresh client. Deterministic failures leave it intact.
    """

    def __init__(self, client_factory: Optional[Callable[[], object]] = None):
        self._client_factory = client_factory or (
            lambda: create_client(SUPABASE_URL, SUPABASE_KEY))
        self._client: Optional[object] = None
        self.client_constructions = 0

    def client(self) -> object:
        if self._client is None:
            self._client = self._client_factory()
            self.client_constructions += 1
        return self._client

    def invalidate(self) -> None:
        self._client = None

    def close(self) -> None:
        # supabase-py does not expose a stable synchronous close contract across
        # supported versions. Dropping the last session reference safely keeps
        # clients scoped to this invocation without depending on private APIs.
        self._client = None


@contextmanager
def scraper_persistence_session(
    session: Optional[ScraperPersistenceSession] = None,
) -> Iterator[ScraperPersistenceSession]:
    """Install a non-shareable persistence session for the current context."""
    owned = session is None
    active = session or ScraperPersistenceSession()
    token = _persistence_session.set(active)
    try:
        yield active
    finally:
        _persistence_session.reset(token)
        if owned:
            active.close()


# One attempt plus four retries. The delays below sum to 15s of sleeping, which
# is the right order of magnitude for a Cloudflare/PostgREST blip and small
# enough that a genuinely down backend still fails the set within a minute
# rather than stalling an overnight batch.
SIMULATION_PERSISTENCE_MAX_ATTEMPTS = 5
SIMULATION_PERSISTENCE_BASE_DELAY_SECONDS = 1.0
SIMULATION_PERSISTENCE_BACKOFF_MULTIPLIER = 2.0
SIMULATION_PERSISTENCE_MAX_DELAY_SECONDS = 8.0
# Jitter is a fraction of the computed delay, not an absolute value, so it stays
# proportionate as the backoff grows. It exists so a batch that hits the same
# outage across many rows does not resynchronise on every retry boundary.
SIMULATION_PERSISTENCE_JITTER_RATIO = 0.1


def compute_backoff_delay_seconds(
    attempt: int,
    *,
    base_delay: float = SIMULATION_PERSISTENCE_BASE_DELAY_SECONDS,
    multiplier: float = SIMULATION_PERSISTENCE_BACKOFF_MULTIPLIER,
    max_delay: float = SIMULATION_PERSISTENCE_MAX_DELAY_SECONDS,
) -> float:
    """Delay BEFORE attempt ``attempt + 1``: 1s, 2s, 4s, 8s, capped."""
    exponent = max(0, int(attempt) - 1)
    return float(min(max_delay, base_delay * (multiplier ** exponent)))


def run_with_transient_retry(
    operation: Callable[[int], T],
    *,
    operation_name: str,
    max_attempts: int = SIMULATION_PERSISTENCE_MAX_ATTEMPTS,
    sleep: Optional[Callable[[float], None]] = None,
    jitter: Optional[Callable[[float, float], float]] = None,
) -> T:
    """Run ``operation(attempt)`` with bounded exponential backoff.

    ``operation`` receives the 1-based attempt number so an idempotency
    reconciliation (did the previous attempt actually land?) can be limited to
    retries and skipped on the first, cheapest pass.

    A non-transient exception is re-raised IMMEDIATELY and unwrapped: the caller
    sees the original error, at the original attempt, with no added latency.
    Exhaustion re-raises the last transient exception rather than converting it
    into a success or a sentinel.
    """
    attempts = max(1, int(max_attempts))
    # Resolved at CALL time, not bound as a default, so a test can replace
    # `time.sleep` on this module and actually make the backoff free.
    sleep_fn = sleep if sleep is not None else time.sleep
    jitter_fn = jitter if jitter is not None else random.uniform

    for attempt in range(1, attempts + 1):
        try:
            result = operation(attempt)
        except Exception as exc:
            failure = classify_data_service_error(exc)
            if not failure.transient:
                raise
            if attempt >= attempts:
                # No sleep after the final attempt.
                logger.error(
                    "Transient Supabase failure exhausted retries operation=%s attempts=%s status=%s code=%s",
                    operation_name,
                    attempts,
                    failure.status_code,
                    failure.code,
                )
                raise
            delay = compute_backoff_delay_seconds(attempt)
            delay += jitter_fn(0.0, delay * SIMULATION_PERSISTENCE_JITTER_RATIO)
            logger.warning(
                "Transient Supabase failure operation=%s attempt=%s/%s status=%s code=%s retry_in=%.1fs",
                operation_name,
                attempt,
                attempts,
                failure.status_code,
                failure.code,
                delay,
            )
            _transport_retry_count.set(_transport_retry_count.get() + 1)
            sleep_fn(delay)
            continue

        if attempt > 1:
            logger.info(
                "Supabase operation recovered operation=%s attempts=%s",
                operation_name,
                attempt,
            )
        return result

    raise AssertionError("unreachable")


def run_supabase_with_transient_retry(
    operation: Callable[[object, int], T],
    *,
    operation_name: str,
    max_attempts: int = SCRAPER_DB_MAX_ATTEMPTS,
    sleep: Optional[Callable[[float], None]] = None,
    jitter: Optional[Callable[[float, float], float]] = None,
) -> T:
    """Run a scraper DB operation using the current healthy session client.

    Callers performing inserts must reconcile their deterministic identity when
    ``attempt > 1`` before issuing another write.  The final transport exception
    is deliberately re-raised unchanged. A transient failure invalidates the
    failed client before backoff, so every retry uses a fresh client.
    """
    active = _persistence_session.get()
    owned = active is None
    session = active or ScraperPersistenceSession()

    def attempt_operation(attempt: int) -> T:
        try:
            return operation(session.client(), attempt)
        except Exception as exc:
            if classify_data_service_error(exc).transient:
                session.invalidate()
            raise

    try:
        return run_with_transient_retry(
            attempt_operation,
            operation_name=operation_name,
            max_attempts=max_attempts,
            sleep=sleep,
            jitter=jitter,
        )
    finally:
        if owned:
            session.close()
