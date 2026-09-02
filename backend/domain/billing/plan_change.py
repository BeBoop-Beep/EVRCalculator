# backend/domain/billing/plan_change.py
from enum import Enum

from .catalog import offer_for_price_id
from .errors import PlanChangeNotAllowed
from .policy import PLAN_RANK

_CROSS_TIER_PLANS = {"plus", "premium"}

SCHEDULE_STATE_NONE = "none"
SCHEDULE_STATE_SCHEDULED = "scheduled"
SCHEDULE_STATE_UNKNOWN = "unknown"

IDEMPOTENCY_KEY_PREFIX_UPGRADE = "planchange"
IDEMPOTENCY_KEY_PREFIX_DOWNGRADE = "plandowngrade"


class PlanChangeAction(str, Enum):
    UPGRADE_NOW = "upgrade_now"
    DOWNGRADE_AT_PERIOD_END = "downgrade_at_period_end"


def classify_transition(current_plan, target_plan) -> PlanChangeAction:
    if current_plan not in _CROSS_TIER_PLANS or target_plan not in _CROSS_TIER_PLANS:
        raise PlanChangeNotAllowed(
            f"Plan change not supported for current={current_plan!r} target={target_plan!r}"
        )
    if current_plan == target_plan:
        raise PlanChangeNotAllowed("Same-tier interval changes are not supported in this effort")
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


def build_downgrade_preview_dto(*, from_plan, to_plan, from_offer_key, to_offer_key, current_period_end) -> dict:
    return {
        "action": PlanChangeAction.DOWNGRADE_AT_PERIOD_END.value,
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

    target_offer = offer_for_price_id(phase_two_price, offers)
    if target_offer is None or target_offer.plan != "plus":
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
