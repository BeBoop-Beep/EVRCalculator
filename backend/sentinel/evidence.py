"""Bound and sanitize Sentinel incident evidence before persistence or triage."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping, Sequence
from typing import Any


_REDACTED = "[REDACTED]"
_TRUNCATED = "[TRUNCATED]"
_SENSITIVE_FRAGMENTS = (
    "password",
    "passwd",
    "secret",
    "authorization",
    "cookie",
    "webhook",
    "service_role",
)
_SENSITIVE_EXACT = {
    "token",
    "access_token",
    "refresh_token",
    "api_key",
    "apikey",
    "supabase_key",
    "slack_alert_webhook_url",
}


def _sensitive_key(key: str) -> bool:
    normalized = key.strip().lower().replace("-", "_")
    return normalized in _SENSITIVE_EXACT or any(
        fragment in normalized for fragment in _SENSITIVE_FRAGMENTS
    )


def sanitize_evidence(
    value: Any,
    *,
    max_depth: int = 5,
    max_items: int = 50,
    max_string: int = 500,
    _depth: int = 0,
) -> Any:
    if _depth >= max_depth:
        return _TRUNCATED

    if value is None or isinstance(value, (bool, int, float)):
        return value

    if isinstance(value, str):
        if len(value) <= max_string:
            return value
        return value[:max_string] + _TRUNCATED

    if isinstance(value, Mapping):
        result = {}
        items = list(value.items())
        for key, child in items[:max_items]:
            rendered_key = str(key)
            if _sensitive_key(rendered_key):
                result[rendered_key] = _REDACTED
            else:
                result[rendered_key] = sanitize_evidence(
                    child,
                    max_depth=max_depth,
                    max_items=max_items,
                    max_string=max_string,
                    _depth=_depth + 1,
                )
        if len(items) > max_items:
            result["_truncated_items"] = len(items) - max_items
        return result

    if isinstance(value, Sequence) and not isinstance(value, (bytes, bytearray)):
        rendered = [
            sanitize_evidence(
                child,
                max_depth=max_depth,
                max_items=max_items,
                max_string=max_string,
                _depth=_depth + 1,
            )
            for child in list(value)[:max_items]
        ]
        if len(value) > max_items:
            rendered.append({"_truncated_items": len(value) - max_items})
        return rendered

    return sanitize_evidence(
        str(value),
        max_depth=max_depth,
        max_items=max_items,
        max_string=max_string,
        _depth=_depth + 1,
    )


def bounded_evidence(value: Any, *, max_bytes: int = 32_000) -> Any:
    sanitized = sanitize_evidence(value)
    encoded = json.dumps(
        sanitized, sort_keys=True, separators=(",", ":"), default=str
    ).encode("utf-8")
    if len(encoded) <= max_bytes:
        return sanitized
    digest = hashlib.sha256(encoded).hexdigest()
    preview_budget = max(256, min(max_bytes // 2, 4_000))
    preview = encoded[:preview_budget].decode("utf-8", errors="replace")
    return {
        "_truncated": True,
        "original_bytes": len(encoded),
        "sha256": digest,
        "preview": preview,
    }
