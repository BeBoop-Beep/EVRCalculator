"""Fail-closed budget contract for optional future Sentinel AI triage.

P8 does not install or call a paid model provider.  The budget layer exists so
any future provider must reserve a conservative worst-case request cost before
making a network request.  The hard monthly ceiling is intentionally encoded
in code and cannot be raised by environment configuration.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from typing import Any, Mapping, Optional, Protocol


AI_HARD_MONTHLY_CAP_CENTS = 1000  # $10.00 absolute ceiling.


@dataclass(frozen=True)
class AiBudgetDecision:
    allowed: bool
    reason_code: str
    estimated_cost_cents: int
    configured_budget_cents: int
    hard_cap_cents: int = AI_HARD_MONTHLY_CAP_CENTS
    ledger_metadata: Mapping[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "allowed": self.allowed,
            "reason_code": self.reason_code,
            "estimated_cost_cents": self.estimated_cost_cents,
            "configured_budget_cents": self.configured_budget_cents,
            "hard_cap_cents": self.hard_cap_cents,
            "ledger_metadata": dict(self.ledger_metadata),
        }


class AiBudgetLedger(Protocol):
    """Atomic reservation boundary required by any future paid provider.

    ``reserve`` must be concurrency-safe and return ``allowed=False`` without
    mutation when the reservation would exceed the persisted monthly budget.
    """

    def reserve(
        self,
        *,
        budget_month: date,
        reservation_cents: int,
        configured_budget_cents: int,
    ) -> Mapping[str, Any]: ...


class DisabledAiBudgetLedger:
    """Default ledger: cannot authorize spend and performs no external I/O."""

    def reserve(
        self,
        *,
        budget_month: date,
        reservation_cents: int,
        configured_budget_cents: int,
    ) -> Mapping[str, Any]:
        return {
            "allowed": False,
            "reason_code": "ai_budget_ledger_disabled",
            "request_made": False,
        }


class AiBudgetGuard:
    """Authorize a future AI request only after a persisted budget reservation."""

    def __init__(
        self,
        *,
        enabled: bool,
        configured_budget_cents: int,
        ledger: Optional[AiBudgetLedger] = None,
    ) -> None:
        self.enabled = bool(enabled)
        self.configured_budget_cents = int(configured_budget_cents)
        self.ledger = ledger or DisabledAiBudgetLedger()
        self.validate_policy()

    def validate_policy(self) -> None:
        if self.configured_budget_cents < 0:
            raise ValueError("AI monthly budget cannot be negative")
        if self.configured_budget_cents > AI_HARD_MONTHLY_CAP_CENTS:
            raise ValueError(
                "AI monthly budget exceeds Sentinel hard cap of "
                f"{AI_HARD_MONTHLY_CAP_CENTS} cents"
            )

    def authorize(
        self,
        *,
        estimated_cost_cents: int,
        budget_month: date,
    ) -> AiBudgetDecision:
        estimate = int(estimated_cost_cents)
        if not self.enabled:
            return AiBudgetDecision(
                False,
                "ai_disabled",
                estimate,
                self.configured_budget_cents,
            )
        if self.configured_budget_cents <= 0:
            return AiBudgetDecision(
                False,
                "ai_monthly_budget_zero",
                estimate,
                self.configured_budget_cents,
            )
        if estimate <= 0:
            return AiBudgetDecision(
                False,
                "ai_cost_estimate_invalid",
                estimate,
                self.configured_budget_cents,
            )
        if estimate > self.configured_budget_cents:
            return AiBudgetDecision(
                False,
                "ai_request_exceeds_monthly_budget",
                estimate,
                self.configured_budget_cents,
            )

        try:
            raw = dict(
                self.ledger.reserve(
                    budget_month=budget_month,
                    reservation_cents=estimate,
                    configured_budget_cents=self.configured_budget_cents,
                )
                or {}
            )
        except Exception as exc:
            # Provider/budget exceptions can contain credentials.  Persist only
            # the class name and fail closed before any paid provider call.
            return AiBudgetDecision(
                False,
                "ai_budget_reservation_error",
                estimate,
                self.configured_budget_cents,
                ledger_metadata={"error_type": exc.__class__.__name__},
            )

        allowed = raw.get("allowed") is True
        metadata = {
            key: value
            for key, value in raw.items()
            if key
            in {
                "budget_month",
                "reserved_cents",
                "configured_budget_cents",
                "remaining_cents",
                "request_count",
                "reason_code",
                "request_made",
            }
        }
        return AiBudgetDecision(
            allowed,
            (
                "ai_budget_reserved"
                if allowed
                else str(raw.get("reason_code") or "ai_budget_reservation_denied")
            ),
            estimate,
            self.configured_budget_cents,
            ledger_metadata=metadata,
        )
