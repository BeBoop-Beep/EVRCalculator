"""Stable hashes used for Sentinel incident deduplication and observations."""

from __future__ import annotations

import hashlib
import json
from typing import Any

from backend.sentinel.models import CheckResult


def _digest(value: Any) -> str:
    payload = json.dumps(
        value, sort_keys=True, separators=(",", ":"), default=str
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def incident_fingerprint(
    check_key: str,
    failure_code: str,
    authority_identity: str | None,
) -> str:
    """Fingerprint one active failure authority, not an incident's whole history."""
    return _digest(
        {
            "check_key": check_key,
            "failure_code": failure_code,
            "authority_identity": authority_identity or "",
        }
    )


def observation_hash(result: CheckResult) -> str:
    return _digest(
        {
            "check_key": result.check_key,
            "outcome": result.outcome.value,
            "failure_code": result.failure_code,
            "authority_identity": result.authority_identity,
            "expected": dict(result.expected),
            "observed": dict(result.observed),
            "evidence": dict(result.evidence),
        }
    )
