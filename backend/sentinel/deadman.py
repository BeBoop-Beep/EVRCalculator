"""Provider-agnostic external dead-man heartbeat for Sentinel.

The ping URL is treated like a secret capability URL: it is never returned,
logged, or included in an exception message. The external monitor's job is to
notice when successful Sentinel cycles stop reaching it.
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any, Callable, Dict, Optional

import requests


@dataclass(frozen=True)
class DeadmanPingResult:
    configured: bool
    delivered: bool
    status_code: Optional[int] = None
    elapsed_ms: Optional[float] = None
    error_type: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "configured": self.configured,
            "delivered": self.delivered,
            "status_code": self.status_code,
            "elapsed_ms": self.elapsed_ms,
            "error_type": self.error_type,
        }


def ping_deadman(
    url: str,
    *,
    timeout_seconds: float = 5.0,
    http_get: Optional[Callable[..., Any]] = None,
) -> DeadmanPingResult:
    """Send one completion ping without ever exposing the capability URL."""
    resolved_url = str(url or "").strip()
    if not resolved_url:
        return DeadmanPingResult(configured=False, delivered=False)
    if not resolved_url.lower().startswith("https://"):
        return DeadmanPingResult(
            configured=True,
            delivered=False,
            error_type="invalid_deadman_url",
        )

    getter = http_get or requests.get
    started = time.perf_counter()
    try:
        response = getter(
            resolved_url,
            timeout=max(0.1, float(timeout_seconds)),
            headers={"User-Agent": "inDex-Sentinel/1"},
        )
        elapsed_ms = round((time.perf_counter() - started) * 1000.0, 2)
        status_code = int(getattr(response, "status_code", 0) or 0)
        return DeadmanPingResult(
            configured=True,
            delivered=200 <= status_code < 300,
            status_code=status_code or None,
            elapsed_ms=elapsed_ms,
            error_type=None if 200 <= status_code < 300 else "deadman_http_error",
        )
    except Exception as exc:
        # Never persist/render str(exc): HTTP client errors frequently embed URLs.
        elapsed_ms = round((time.perf_counter() - started) * 1000.0, 2)
        return DeadmanPingResult(
            configured=True,
            delivered=False,
            elapsed_ms=elapsed_ms,
            error_type=exc.__class__.__name__,
        )
