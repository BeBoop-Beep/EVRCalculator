"""Low-overhead structured telemetry for public Market read endpoints."""

from __future__ import annotations

import json
import logging
import os
import time
from typing import Any, Optional
from uuid import uuid4

logger = logging.getLogger("market.performance")

MARKET_PATHS = {"/explore/card-market-movers", "/explore/set-value-market"}
MARKET_PATH_FRAGMENTS = ("/market/",)


def _rss_bytes() -> Optional[int]:
    try:
        import psutil  # type: ignore[reportMissingImports]
        return int(psutil.Process(os.getpid()).memory_info().rss)
    except Exception:
        return None


def is_market_path(path: str) -> bool:
    return path in MARKET_PATHS or any(fragment in path for fragment in MARKET_PATH_FRAGMENTS)


async def market_request_metrics_middleware(request: Any, call_next: Any):
    """Log one compact record without copying or re-encoding the response."""
    path = request.url.path
    if not is_market_path(path):
        return await call_next(request)
    request_id = request.headers.get("x-request-id") or uuid4().hex
    started = time.perf_counter()
    rss_before = _rss_bytes()
    status = 500
    exception_category = None
    try:
        response = await call_next(request)
        status = response.status_code
        return response
    except Exception as exc:
        exception_category = type(exc).__name__
        raise
    finally:
        rss_after = _rss_bytes()
        response_bytes = None
        if "response" in locals():
            response.headers["x-request-id"] = request_id
            response.headers["x-index-build"] = build_identity()
            try:
                response_bytes = int(response.headers.get("content-length", ""))
            except (TypeError, ValueError):
                pass
        record = {
            "event": "market_request", "route": path, "requestId": request_id,
            "durationMs": round((time.perf_counter() - started) * 1000, 2),
            "status": status, "responseBytes": response_bytes,
            "rssBefore": rss_before, "rssAfter": rss_after,
            "rssDelta": (rss_after - rss_before) if rss_after is not None and rss_before is not None else None,
            "cache": "endpoint_or_upstream",
            "params": {key: request.query_params.get(key) for key in ("window", "set", "set_id", "asset", "days", "scope", "limit") if request.query_params.get(key) is not None},
            "exceptionCategory": exception_category,
        }
        logger.info(json.dumps(record, separators=(",", ":"), default=str))


def build_identity() -> str:
    return (os.getenv("RENDER_GIT_COMMIT") or os.getenv("GIT_SHA") or os.getenv("SOURCE_VERSION") or "development")[:40]
