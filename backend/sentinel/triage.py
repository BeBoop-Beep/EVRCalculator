"""Provider boundary for optional future Sentinel AI triage.

P8 intentionally installs no paid AI provider.  Deterministic Sentinel behavior
is complete without AI; this module makes that zero-request state explicit and
provides the only factory through which a future provider may be introduced.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Protocol

from backend.sentinel.ai_budget import AI_HARD_MONTHLY_CAP_CENTS


@dataclass(frozen=True)
class TriageDecision:
    status: str
    summary: str
    metadata: Dict[str, Any]


class TriageProvider(Protocol):
    def triage(self, evidence: Dict[str, Any]) -> TriageDecision: ...


class DisabledTriageProvider:
    """Zero-I/O provider used by the supported P8 production configuration."""

    def __init__(self, *, configured_budget_cents: int = 0) -> None:
        self.configured_budget_cents = int(configured_budget_cents)

    def triage(self, evidence: Dict[str, Any]) -> TriageDecision:
        return TriageDecision(
            status="disabled",
            summary="AI triage is disabled; deterministic Sentinel handling remains active.",
            metadata={
                "provider": "disabled",
                "request_made": False,
                "configured_budget_cents": self.configured_budget_cents,
                "hard_monthly_cap_cents": AI_HARD_MONTHLY_CAP_CENTS,
            },
        )


def build_triage_provider(config: Any) -> TriageProvider:
    """Return the only provider available in P8.

    ``SentinelConfig.validate_kernel_v1`` already rejects ``ai_enabled=True``.
    Keep the factory independently fail-closed so callers that bypass config
    validation still cannot manufacture a paid request path.
    """
    if bool(getattr(config, "ai_enabled", False)):
        raise RuntimeError(
            "No paid Sentinel AI triage provider adapter is installed in P8"
        )
    return DisabledTriageProvider(
        configured_budget_cents=int(getattr(config, "ai_monthly_budget_cents", 0) or 0)
    )


def triage_runtime_summary(config: Any) -> Dict[str, Any]:
    """Safe runtime metadata proving whether AI could have made a request."""
    provider = build_triage_provider(config)
    decision = provider.triage({})
    return {
        "status": decision.status,
        "summary": decision.summary,
        **dict(decision.metadata),
    }
