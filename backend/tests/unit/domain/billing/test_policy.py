import pytest
from backend.domain.billing.policy import effective_plan, subscription_grants_access, has_duplicate_active_subscriptions

@pytest.mark.parametrize("status,grants", [("trialing", True), ("active", True), ("past_due", True),
    ("incomplete", False), ("incomplete_expired", False), ("unpaid", False), ("canceled", False),
    ("paused", False), ("future_status", False), (None, False)])
def test_status_policy(status, grants):
    assert subscription_grants_access(status) is grants

def row(plan, status, mapping="mapped"): return {"plan": plan, "status": status, "commercial_mapping_status": mapping}

def test_effective_plan_is_highest_provisionable_or_manual():
    assert effective_plan([row("plus", "active")]) == "plus"
    assert effective_plan([row("premium", "past_due")]) == "premium"
    assert effective_plan([row("plus", "active"), row("premium", "active")]) == "premium"
    assert effective_plan([row("premium", "canceled")]) is None
    assert effective_plan([row("premium", "active", "unmapped_price")]) is None
    assert effective_plan([], "premium") == "premium"
    assert effective_plan([row("premium", "active")], "plus") == "premium"
    assert effective_plan([row("plus", "active")], "premium") == "premium"

def test_duplicate_anomaly_counts_only_provisionable_rows():
    assert has_duplicate_active_subscriptions([row("plus", "active"), row("premium", "past_due")])
    assert not has_duplicate_active_subscriptions([row("plus", "active"), row("premium", "canceled")])

