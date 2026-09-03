# backend/domain/billing/plan_change.py
from enum import Enum

from .catalog import offer_for_price_id
from .errors import PlanChangeNotAllowed
from .policy import PLAN_RANK

_CROSS_TIER_PLANS = {"plus", "premium"}
_SUPPORTED_INTERVALS = {"month", "year"}

SCHEDULE_STATE_NONE = "none"
SCHEDULE_STATE_SCHEDULED = "scheduled"
SCHEDULE_STATE_UNKNOWN = "unknown"

IDEMPOTENCY_KEY_PREFIX_UPGRADE = "planchange"
IDEMPOTENCY_KEY_PREFIX_DOWNGRADE = "plandowngrade"


class PlanChangeAction(str, Enum):
    UPGRADE_NOW = "upgrade_now"
    DOWNGRADE_AT_PERIOD_END = "downgrade_at_period_end"
    INTERVAL_CHANGE_AT_PERIOD_END = "interval_change_at_period_end"


def classify_transition(
    current_plan,
    target_plan,
    *,
    current_interval=None,
    target_interval=None,
) -> PlanChangeAction:
    if current_plan not in _CROSS_TIER_PLANS or target_plan not in _CROSS_TIER_PLANS:
        raise PlanChangeNotAllowed(
            f"Plan change not supported for current={current_plan!r} target={target_plan!r}"
        )
    if current_plan == target_plan:
        if current_interval not in _SUPPORTED_INTERVALS or target_interval not in _SUPPORTED_INTERVALS:
            raise PlanChangeNotAllowed("Same-tier interval change requires known billing intervals")
        if current_interval == target_interval:
            raise PlanChangeNotAllowed("Current and target offers are the same billing interval")
        return PlanChangeAction.INTERVAL_CHANGE_AT_PERIOD_END
    if PLAN_RANK[target_plan] > PLAN_RANK[current_plan]:
        return PlanChangeAction.UPGRADE_NOW
    return PlanChangeAction.DOWNGRADE_AT_PERIOD_END


def build_upgrade_preview_dto(
    *, from_plan, to_plan, from_offer_key, to_offer_key, currency, amount_due_now, effective_at, next_renewal_at
) -> dict:
    return {
        "action": PlanChangeAction.UPGRADE_NOW.value,
        "fromPlan": from_plan,
        "toPlan": to_plan,
        "fromOfferKey": from_offer_key,
        "toOfferKey": to_offer_key,
        "currency": currency,
        "amountDueNow": amount_due_now,
        "effectiveAt": effective_at,
        "nextRenewalAt": next_renewal_at,
    }


def build_downgrade_preview_dto(
    *,
    from_plan,
    to_plan,
    from_offer_key,
    to_offer_key,
    current_period_end,
    action=PlanChangeAction.DOWNGRADE_AT_PERIOD_END,
) -> dict:
    """Build a no-charge-now change scheduled at the paid-period boundary.

    The historical function name is retained because cross-tier Premium→Plus
    downgrades remain its primary caller. Same-tier monthly↔annual changes use
    the same safe schedule shape with a distinct action value.
    """
    return {
        "action": action.value,
        "fromPlan": from_plan,
        "toPlan": to_plan,
        "fromOfferKey": from_offer_key,
        "toOfferKey": to_offer_key,
        "amountDueNow": 0,
        "effectiveAt": current_period_end,
        "currentPlanUntil": current_period_end,
    }


def classify_schedule(schedule, *, current_price_id, current_period_end, offers) -> dict:
    empty = {"state": SCHEDULE_STATE_NONE, "pendingPlan": None, "pendingOfferKey": None, "pendingChangeEffectiveAt": None}
    if not schedule:
        return empty

    phases = schedule.get("phases") or []
    if len(phases) != 2:
        return {**empty, "state": SCHEDULE_STATE_UNKNOWN}

    phase_one, phase_two = phases
    phase_one_price = _phase_price(phase_one)
    phase_two_price = _phase_price(phase_two)

    if phase_one_price != current_price_id:
        return {**empty, "state": SCHEDULE_STATE_UNKNOWN}
    if phase_one.get("end_date") != current_period_end:
        return {**empty, "state": SCHEDULE_STATE_UNKNOWN}
    if phase_two.get("start_date") != current_period_end:
        return {**empty, "state": SCHEDULE_STATE_UNKNOWN}

    current_offer = offer_for_price_id(current_price_id, offers)
    target_offer = offer_for_price_id(phase_two_price, offers)
    if current_offer is None or target_offer is None:
        return {**empty, "state": SCHEDULE_STATE_UNKNOWN}

    try:
        action = classify_transition(
            current_offer.plan,
            target_offer.plan,
            current_interval=current_offer.billing_interval,
            target_interval=target_offer.billing_interval,
        )
    except PlanChangeNotAllowed:
        return {**empty, "state": SCHEDULE_STATE_UNKNOWN}

    if action not in {
        PlanChangeAction.DOWNGRADE_AT_PERIOD_END,
        PlanChangeAction.INTERVAL_CHANGE_AT_PERIOD_END,
    }:
        return {**empty, "state": SCHEDULE_STATE_UNKNOWN}

    return {
        "state": SCHEDULE_STATE_SCHEDULED,
        "pendingPlan": target_offer.plan,
        "pendingOfferKey": target_offer.offer_key,
        "pendingChangeEffectiveAt": current_period_end,
    }


def _phase_price(phase: dict):
    items = phase.get("items") or []
    if len(items) != 1:
        return None
    return items[0].get("price")


def upgrade_idempotency_key(subscription_id, current_price_id, target_price_id, proration_date) -> str:
    return f"{IDEMPOTENCY_KEY_PREFIX_UPGRADE}:{subscription_id}:{current_price_id}:{target_price_id}:{proration_date}"


def downgrade_idempotency_key(subscription_id, current_price_id, target_price_id, current_period_end) -> str:
    return f"{IDEMPOTENCY_KEY_PREFIX_DOWNGRADE}:{subscription_id}:{current_price_id}:{target_price_id}:{current_period_end}"
