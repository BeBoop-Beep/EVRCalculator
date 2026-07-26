from __future__ import annotations

"""Bounded retries and circuit breaking for live public PostgREST reads."""

import logging
import random
import threading
import time
from dataclasses import dataclass, field
from typing import Any, Callable, TypeVar

from backend.db.clients.supabase_client import create_public_read_client
from backend.db.services.data_service_health import classify_data_service_error


logger = logging.getLogger(__name__)
T = TypeVar("T")

_CIRCUIT_OPEN_SECONDS = 4.0
_MAX_ELAPSED_BEFORE_RETRY_SECONDS = 1.0


class PublicReadCircuitOpenError(RuntimeError):
    """Raised when a recent transient outage suppresses duplicate requests."""

    code = "PUBLIC_READ_CIRCUIT_OPEN"
    status_code = 503


@dataclass
class _CircuitState:
    state: str = "closed"
    open_until: float = 0.0
    lock: threading.Lock = field(default_factory=threading.Lock)


_CIRCUIT = _CircuitState()


def _claim_request_slot(now: float) -> bool:
    """Return whether this request owns the single half-open probe."""

    with _CIRCUIT.lock:
        if _CIRCUIT.state == "closed":
            return False
        if _CIRCUIT.state == "open" and now >= _CIRCUIT.open_until:
            _CIRCUIT.state = "half_open"
            return True
        raise PublicReadCircuitOpenError("Public data service circuit is open")


def _open_circuit(now: float) -> None:
    with _CIRCUIT.lock:
        _CIRCUIT.state = "open"
        _CIRCUIT.open_until = now + _CIRCUIT_OPEN_SECONDS


def _close_circuit() -> None:
    with _CIRCUIT.lock:
        _CIRCUIT.state = "closed"
        _CIRCUIT.open_until = 0.0


def _reset_public_read_circuit_breaker_for_tests() -> None:
    """Reset process-local state so unit tests do not influence one another."""

    _close_circuit()


def run_batch_read_with_retry(
    operation: Callable[[], T],
    *,
    operation_name: str,
    max_attempts: int = 4,
    sleep: Callable[[float], None] = time.sleep,
    jitter: Callable[[float, float], float] = random.uniform,
) -> T:
    """Retry a read on the BATCH path with bounded exponential backoff + jitter.

    Distinct from :func:`run_public_read_with_retry`, which serves a
    latency-sensitive HTTP request and therefore abandons the retry once ~1s has
    elapsed and trips a shared circuit breaker. Neither behaviour suits batch
    work: the reads here legitimately take seconds (a cold TOAST read or the
    ~6s `explore_rip_statistics_latest` view against an 8s statement_timeout),
    so the elapsed-time budget would forbid the retry precisely when it is the
    thing that would succeed, and one snapshot build's slow read must not open a
    circuit against live traffic.

    Transience is decided by the shared classifier, never by matching text here.
    A non-transient error raises on the first attempt: a schema or permission
    fault does not improve by being asked again.
    """
    attempts = max(1, int(max_attempts))
    for attempt in range(1, attempts + 1):
        try:
            return operation()
        except Exception as exc:
            failure = classify_data_service_error(exc)
            final = attempt >= attempts or not failure.transient
            logger.log(
                logging.ERROR if final else logging.WARNING,
                "batch read failed operation=%s attempt=%s/%s error_type=%s "
                "error_code=%s status=%s transient=%s final=%s",
                operation_name, attempt, attempts, failure.error_type, failure.code,
                failure.status_code, failure.transient, str(final).lower(),
            )
            if final:
                raise
            base_delay = min(4.0, 0.5 * (2 ** (attempt - 1)))
            sleep(max(0.0, base_delay + jitter(0.0, base_delay * 0.5)))
    raise AssertionError("unreachable")


def run_public_read_with_retry(
    operation: Callable[[Any], T],
    *,
    operation_name: str,
    initial_client: Any = None,
    max_attempts: int = 2,
    client_factory: Callable[[], Any] = create_public_read_client,
    sleep: Callable[[float], None] = time.sleep,
    jitter: Callable[[float, float], float] = random.uniform,
    monotonic: Callable[[], float] = time.monotonic,
) -> T:
    """Run a live public read with one fresh-client retry when it is safe.

    A retry is only started when the first transient failure returned quickly.
    This prevents a full PostgREST timeout from being followed by another full
    timeout on a latency-sensitive HTTP request path.
    """

    started = monotonic()
    try:
        half_open_probe = _claim_request_slot(started)
    except PublicReadCircuitOpenError as exc:
        failure = classify_data_service_error(exc)
        logger.warning(
            "public read blocked operation=%s attempt=0/0 error_type=%s "
            "error_code=%s status=%s circuit=open",
            operation_name,
            failure.error_type,
            failure.code,
            failure.status_code,
        )
        raise

    attempts = 1 if half_open_probe else max(1, min(int(max_attempts), 2))
    for attempt in range(1, attempts + 1):
        client = client_factory() if half_open_probe or attempt > 1 or initial_client is None else initial_client
        try:
            result = operation(client)
        except Exception as exc:
            failure = classify_data_service_error(exc)
            elapsed = monotonic() - started
            retry_budget_exhausted = elapsed >= _MAX_ELAPSED_BEFORE_RETRY_SECONDS
            final = (
                half_open_probe
                or attempt >= attempts
                or not failure.transient
                or retry_budget_exhausted
            )
            logger.log(
                logging.ERROR if final else logging.WARNING,
                "public read failed operation=%s attempt=%s/%s error_type=%s "
                "error_code=%s status=%s transient=%s final=%s",
                operation_name,
                attempt,
                attempts,
                failure.error_type,
                failure.code,
                failure.status_code,
                failure.transient,
                str(final).lower(),
            )
            if final:
                if failure.transient:
                    _open_circuit(monotonic())
                elif half_open_probe:
                    # A semantic/application error proves PostgREST is reachable.
                    _close_circuit()
                raise

            delay = max(0.0, jitter(0.25, 0.5))
            logger.warning(
                "public read retry operation=%s attempt=%s/%s error_type=%s "
                "error_code=%s status=%s delay=%.3fs",
                operation_name,
                attempt,
                attempts,
                failure.error_type,
                failure.code,
                failure.status_code,
                delay,
            )
            sleep(delay)
            continue

        _close_circuit()
        return result

    raise AssertionError("unreachable")
