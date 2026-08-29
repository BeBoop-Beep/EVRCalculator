"""Process-local abuse controls for authenticated paid analytics.

Authorization must run before this module. Counters never contain tokens,
cookies, request bodies, or raw query strings.
"""

from __future__ import annotations

from collections import defaultdict, deque
from dataclasses import dataclass
import hashlib
import json
import logging
import os
import threading
import time
from typing import Any, Callable, Deque, Mapping, Optional


logger = logging.getLogger("security.paid_analytics")

POLICY_INTERACTIVE_DETAIL = "interactive_detail"
POLICY_RANKED_INTELLIGENCE = "ranked_intelligence"
POLICY_CUSTOM_QUERY = "custom_query"


@dataclass(frozen=True)
class PaidRoutePolicy:
    name: str
    burst_limit: int
    burst_seconds: int
    sustained_limit: int
    sustained_seconds: int


POLICIES = {
    POLICY_INTERACTIVE_DETAIL: PaidRoutePolicy(POLICY_INTERACTIVE_DETAIL, 30, 10, 300, 3600),
    POLICY_RANKED_INTELLIGENCE: PaidRoutePolicy(POLICY_RANKED_INTELLIGENCE, 12, 10, 120, 3600),
    POLICY_CUSTOM_QUERY: PaidRoutePolicy(POLICY_CUSTOM_QUERY, 5, 10, 30, 3600),
}


@dataclass(frozen=True)
class LimitDecision:
    allowed: bool
    retry_after_seconds: int = 0
    reason: Optional[str] = None


def _pseudonym(value: str) -> str:
    secret = os.getenv("ABUSE_TELEMETRY_HASH_KEY", "local-process-only")
    return hashlib.sha256(f"{secret}:{value}".encode("utf-8")).hexdigest()[:20]


def _network_identity(headers: Mapping[str, str], client_host: Optional[str]) -> str:
    forwarded = str(headers.get("x-forwarded-for") or "").split(",", 1)[0].strip()
    return forwarded or str(client_host or "unknown")


class PaidAnalyticsLimiter:
    def __init__(self, *, clock: Callable[[], float] = time.monotonic):
        self._clock = clock
        self._events: dict[tuple[str, str, str], Deque[float]] = defaultdict(deque)
        self._lock = threading.Lock()

    def clear(self) -> None:
        with self._lock:
            self._events.clear()

    def check(
        self, *, policy_name: str, user_id: str, route: str,
        headers: Mapping[str, str], client_host: Optional[str], request_id: str,
    ) -> LimitDecision:
        policy = POLICIES[policy_name]
        now = self._clock()
        network = _network_identity(headers, client_host)
        # Query strings are deliberately absent: all variations share these buckets.
        keys = (
            ("user", user_id, policy.name, policy.burst_limit, policy.burst_seconds),
            ("user", user_id, policy.name, policy.sustained_limit, policy.sustained_seconds),
            # Network limits supplement account limits and are deliberately looser.
            ("network", network, policy.name, policy.burst_limit * 3, policy.burst_seconds),
        )
        with self._lock:
            for identity_type, identity, bucket, limit, window in keys:
                events = self._events[(identity_type, identity, f"{bucket}:{window}")]
                cutoff = now - window
                while events and events[0] <= cutoff:
                    events.popleft()
                if len(events) >= limit:
                    retry = max(1, int(events[0] + window - now + 0.999))
                    reason = "network_burst" if identity_type == "network" else (
                        "user_burst" if window == policy.burst_seconds else "user_sustained"
                    )
                    emit_security_event("paid_rate_limited", route=route, policy_class=policy.name,
                                        user_id=user_id, request_id=request_id,
                                        retry_after_seconds=retry, reason=reason)
                    return LimitDecision(False, retry, reason)
            for identity_type, identity, bucket, _limit, window in keys:
                self._events[(identity_type, identity, f"{bucket}:{window}")].append(now)

        emit_security_event("paid_request", route=route, policy_class=policy.name,
                            user_id=user_id, request_id=request_id)
        return LimitDecision(True)


def emit_security_event(event: str, **fields: Any) -> None:
    safe = {"event": event, "timestamp": int(time.time())}
    for key, value in fields.items():
        if key == "user_id" and value:
            safe["accountPseudonym"] = _pseudonym(str(value))
        elif key not in {"authorization", "cookie", "token", "body", "headers"}:
            safe[key] = value
    logger.info(json.dumps(safe, separators=(",", ":"), default=str))


paid_analytics_limiter = PaidAnalyticsLimiter()
