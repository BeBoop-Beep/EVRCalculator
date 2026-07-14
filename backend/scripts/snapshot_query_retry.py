from __future__ import annotations

"""Bounded retries for offline snapshot work.

Every attempt receives a newly-created service-role client so a failed HTTP/2
connection pool is never reused.
"""

import logging
import random
import time
from typing import Any, Callable, Optional, TypeVar

from backend.db.clients.supabase_client import create_service_role_client
from backend.db.services.data_service_health import classify_data_service_error


logger = logging.getLogger(__name__)
T = TypeVar("T")


def run_snapshot_operation_with_retry(
    operation: Callable[[Any], T],
    *,
    operation_name: str,
    set_id: Optional[str] = None,
    max_attempts: int = 3,
    client_factory: Callable[[], Any] = create_service_role_client,
    sleep: Callable[[float], None] = time.sleep,
    jitter: Callable[[float, float], float] = random.uniform,
) -> T:
    attempts = max(1, min(int(max_attempts), 3))
    for attempt in range(1, attempts + 1):
        client = client_factory()
        try:
            return operation(client)
        except Exception as exc:
            failure = classify_data_service_error(exc)
            final = attempt >= attempts or not failure.transient
            if final:
                logger.error(
                    "snapshot operation failed operation=%s set_id=%s attempt=%s/%s "
                    "error_type=%s error_code=%s status=%s transient=%s final=true",
                    operation_name,
                    set_id,
                    attempt,
                    attempts,
                    failure.error_type,
                    failure.code,
                    failure.status_code,
                    failure.transient,
                )
                raise
            base_delay = min(2.0, 0.25 * (2 ** (attempt - 1)))
            delay = max(0.0, base_delay + jitter(0.0, base_delay * 0.25))
            logger.warning(
                "snapshot operation retry operation=%s set_id=%s attempt=%s/%s "
                "error_type=%s error_code=%s status=%s delay=%.3fs",
                operation_name,
                set_id,
                attempt,
                attempts,
                failure.error_type,
                failure.code,
                failure.status_code,
                delay,
            )
            sleep(delay)
    raise AssertionError("unreachable")

