"""The single subscription-state to effective-entitlement policy."""

from __future__ import annotations

PLAN_RANK = {None: 0, "plus": 1, "premium": 2}
ENTITLED_STATUSES = frozenset({"trialing", "active", "past_due"})
DENIED_STATUSES = frozenset({"incomplete", "incomplete_expired", "unpaid", "canceled", "paused"})


def subscription_grants_access(status: object) -> bool:
    return isinstance(status, str) and status.strip().lower() in ENTITLED_STATUSES


def effective_plan(subscriptions, manual_plan=None):
    plans = [manual_plan if manual_plan in PLAN_RANK else None]
    plans.extend(
        row.get("plan") for row in subscriptions
        if subscription_grants_access(row.get("status")) and row.get("plan") in PLAN_RANK
        and row.get("commercial_mapping_status", "mapped") == "mapped"
    )
    return max(plans, key=lambda plan: PLAN_RANK[plan])


def has_duplicate_active_subscriptions(subscriptions) -> bool:
    return sum(subscription_grants_access(row.get("status")) for row in subscriptions) > 1

