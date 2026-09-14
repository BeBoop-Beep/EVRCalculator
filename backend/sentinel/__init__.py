"""Deterministic reliability kernel for inDex Sentinel.

Observation adapters, independent monitoring, and P6's allowlisted recovery
layer attach to the same typed kernel. Recovery remains fail-closed unless its
separate persistence/schema/execution gates are explicitly enabled.
"""

from backend.sentinel.config import SentinelConfig
from backend.sentinel.models import (
    CheckOutcome,
    CheckResult,
    CheckState,
    CheckStateStatus,
    IncidentRecord,
    IncidentStatus,
    RecoveryAttemptRecord,
    RecoveryAttemptStatus,
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
    "RecoveryAttemptRecord",
    "RecoveryAttemptStatus",
    "SentinelConfig",
    "Severity",
]
