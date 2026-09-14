from datetime import date

import pytest

from backend.sentinel.ai_budget import (
    AI_HARD_MONTHLY_CAP_CENTS,
    AiBudgetGuard,
)
from backend.sentinel.config import SentinelConfig
from backend.sentinel.triage import (
    DisabledTriageProvider,
    build_triage_provider,
)


MONTH = date(2026, 9, 1)


class CountingLedger:
    def __init__(self, result=None):
        self.calls = []
        self.result = result or {"allowed": True, "reserved_cents": 25}

    def reserve(self, **kwargs):
        self.calls.append(dict(kwargs))
        return dict(self.result)


def test_ai_hard_cap_is_exactly_ten_dollars():
    assert AI_HARD_MONTHLY_CAP_CENTS == 1000


def test_disabled_budget_guard_never_touches_ledger():
    ledger = CountingLedger()
    decision = AiBudgetGuard(
        enabled=False,
        configured_budget_cents=500,
        ledger=ledger,
    ).authorize(estimated_cost_cents=25, budget_month=MONTH)
    assert decision.allowed is False
    assert decision.reason_code == "ai_disabled"
    assert ledger.calls == []


def test_budget_policy_rejects_negative_or_above_hard_cap():
    with pytest.raises(ValueError, match="negative"):
        AiBudgetGuard(enabled=True, configured_budget_cents=-1)
    with pytest.raises(ValueError, match="hard cap"):
        AiBudgetGuard(
            enabled=True,
            configured_budget_cents=AI_HARD_MONTHLY_CAP_CENTS + 1,
        )


def test_enabled_guard_with_zero_monthly_budget_fails_before_ledger():
    ledger = CountingLedger()
    decision = AiBudgetGuard(
        enabled=True,
        configured_budget_cents=0,
        ledger=ledger,
    ).authorize(estimated_cost_cents=1, budget_month=MONTH)
    assert decision.reason_code == "ai_monthly_budget_zero"
    assert ledger.calls == []


def test_invalid_request_estimate_fails_before_ledger():
    ledger = CountingLedger()
    decision = AiBudgetGuard(
        enabled=True,
        configured_budget_cents=500,
        ledger=ledger,
    ).authorize(estimated_cost_cents=0, budget_month=MONTH)
    assert decision.reason_code == "ai_cost_estimate_invalid"
    assert ledger.calls == []


def test_request_larger_than_monthly_budget_fails_before_ledger():
    ledger = CountingLedger()
    decision = AiBudgetGuard(
        enabled=True,
        configured_budget_cents=500,
        ledger=ledger,
    ).authorize(estimated_cost_cents=501, budget_month=MONTH)
    assert decision.reason_code == "ai_request_exceeds_monthly_budget"
    assert ledger.calls == []


def test_default_disabled_ledger_cannot_authorize_spend():
    decision = AiBudgetGuard(
        enabled=True,
        configured_budget_cents=500,
    ).authorize(estimated_cost_cents=25, budget_month=MONTH)
    assert decision.allowed is False
    assert decision.reason_code == "ai_budget_ledger_disabled"
    assert decision.ledger_metadata["request_made"] is False


def test_successful_reservation_passes_exact_budget_envelope_to_ledger():
    ledger = CountingLedger(
        {
            "allowed": True,
            "budget_month": "2026-09-01",
            "reserved_cents": 125,
            "configured_budget_cents": 500,
            "remaining_cents": 375,
            "request_count": 2,
        }
    )
    decision = AiBudgetGuard(
        enabled=True,
        configured_budget_cents=500,
        ledger=ledger,
    ).authorize(estimated_cost_cents=25, budget_month=MONTH)
    assert decision.allowed is True
    assert decision.reason_code == "ai_budget_reserved"
    assert ledger.calls == [
        {
            "budget_month": MONTH,
            "reservation_cents": 25,
            "configured_budget_cents": 500,
        }
    ]
    assert decision.ledger_metadata["remaining_cents"] == 375


def test_budget_ledger_exception_is_redacted_to_exception_class():
    class ExplodingLedger:
        def reserve(self, **_kwargs):
            raise RuntimeError("secret-provider-capability-token")

    decision = AiBudgetGuard(
        enabled=True,
        configured_budget_cents=500,
        ledger=ExplodingLedger(),
    ).authorize(estimated_cost_cents=25, budget_month=MONTH)
    assert decision.allowed is False
    assert decision.reason_code == "ai_budget_reservation_error"
    assert decision.ledger_metadata == {"error_type": "RuntimeError"}
    assert "secret-provider-capability-token" not in str(decision.to_dict())


def test_disabled_triage_provider_is_zero_io_and_reports_budget_metadata():
    decision = DisabledTriageProvider(configured_budget_cents=0).triage(
        {"incident": "unknown"}
    )
    assert decision.status == "disabled"
    assert decision.metadata["provider"] == "disabled"
    assert decision.metadata["request_made"] is False
    assert decision.metadata["hard_monthly_cap_cents"] == 1000


def test_triage_factory_independently_refuses_enabled_ai_path():
    config = SentinelConfig(ai_enabled=True)
    with pytest.raises(RuntimeError, match="No paid Sentinel AI"):
        build_triage_provider(config)


def test_config_defaults_to_zero_ai_spend_and_rejects_unsafe_enablement():
    default = SentinelConfig()
    default.validate_kernel_v1()
    assert default.ai_enabled is False
    assert default.ai_provider == "disabled"
    assert default.ai_monthly_budget_cents == 0

    with pytest.raises(RuntimeError, match="hard Sentinel AI ceiling"):
        SentinelConfig(ai_monthly_budget_cents=1001).validate_kernel_v1()

    with pytest.raises(RuntimeError, match="explicit AI gates"):
        SentinelConfig(ai_enabled=True).validate_kernel_v1()

    with pytest.raises(RuntimeError, match="no paid AI triage provider"):
        SentinelConfig(
            state_writes_enabled=True,
            persistence_schema_ready=True,
            ai_enabled=True,
            ai_execution_ready=True,
            ai_budget_ledger_ready=True,
            ai_provider="future-provider",
            ai_monthly_budget_cents=500,
        ).validate_kernel_v1()
