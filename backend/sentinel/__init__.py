"""Deterministic reliability kernel for inDex Sentinel.

Prompt 2 intentionally contains no production checks, automated recovery, or AI.
Those capabilities are attached in later phases through the registry/provider
interfaces defined here.
"""

from backend.sentinel.config import SentinelConfig
from backend.sentinel.models import (
    CheckOutcome,
    CheckResult,
    CheckState,
    CheckStateStatus,
    IncidentRecord,
    IncidentStatus,
    Severity,
)
from backend.sentinel.registry import CheckRegistry

__all__ = [
    "CheckOutcome",
    "CheckRegistry",
    "CheckResult",
    "CheckState",
    "CheckStateStatus",
    "IncidentRecord",
    "IncidentStatus",
    "SentinelConfig",
    "Severity",
]
