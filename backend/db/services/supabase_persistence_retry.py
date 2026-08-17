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
from typing import Callable, Optional, TypeVar

from backend.db.services.data_service_health import classify_data_service_error


logger = logging.getLogger(__name__)
T = TypeVar("T")


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
