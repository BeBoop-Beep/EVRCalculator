import pytest

from backend.domain.billing.catalog import CommercialOffer
from backend.domain.billing.errors import PlanChangeNotAllowed
from backend.domain.billing.plan_change import (
    PlanChangeAction,
    build_downgrade_preview_dto,
    build_upgrade_preview_dto,
    classify_schedule,
    classify_transition,
    downgrade_idempotency_key,
    upgrade_idempotency_key,
)

PREMIUM_MONTHLY_OFFER = CommercialOffer(
    offer_key="premium_monthly",
    plan="premium",
    billing_interval="month",
    enabled=True,
    provider_price_id="price_premium_monthly",
    unit_amount_minor=2499,
    currency="usd",
)
PLUS_MONTHLY_OFFER = CommercialOffer(
    offer_key="plus_monthly",
    plan="plus",
    billing_interval="month",
    enabled=True,
    provider_price_id="price_plus_monthly",
    unit_amount_minor=999,
    currency="usd",
)
OFFERS = {"premium_monthly": PREMIUM_MONTHLY_OFFER, "plus_monthly": PLUS_MONTHLY_OFFER}


@pytest.mark.parametrize(
    "current_plan,target_plan,expected",
    [
        ("plus", "premium", PlanChangeAction.UPGRADE_NOW),
        ("premium", "plus", PlanChangeAction.DOWNGRADE_AT_PERIOD_END),
    ],
)
def test_classify_transition_valid_cross_tier(current_plan, target_plan, expected):
    assert classify_transition(current_plan, target_plan) == expected


@pytest.mark.parametrize(
    "current_plan,target_plan",
    [
        ("plus", "plus"),
        ("premium", "premium"),
        (None, "plus"),
        ("plus", None),
        ("plus", "basic"),
        (None, None),
    ],
)
def test_classify_transition_rejects_invalid(current_plan, target_plan):
    with pytest.raises(PlanChangeNotAllowed):
        classify_transition(current_plan, target_plan)


def test_build_upgrade_preview_dto_shape():
    dto = build_upgrade_preview_dto(
        from_plan="plus",
        to_plan="premium",
        from_offer_key="plus_monthly",
        to_offer_key="premium_monthly",
        currency="usd",
        amount_due_now=1500,
        effective_at=1735689600,
        next_renewal_at=1738368000,
    )
    assert dto == {
        "action": "upgrade_now",
        "fromPlan": "plus",
        "toPlan": "premium",
        "fromOfferKey": "plus_monthly",
        "toOfferKey": "premium_monthly",
        "currency": "usd",
        "amountDueNow": 1500,
        "effectiveAt": 1735689600,
        "nextRenewalAt": 1738368000,
    }


def test_build_downgrade_preview_dto_shape():
    dto = build_downgrade_preview_dto(
        from_plan="premium",
        to_plan="plus",
        from_offer_key="premium_monthly",
        to_offer_key="plus_monthly",
        current_period_end=1738368000,
    )
    assert dto == {
        "action": "downgrade_at_period_end",
        "fromPlan": "premium",
        "toPlan": "plus",
        "fromOfferKey": "premium_monthly",
        "toOfferKey": "plus_monthly",
        "amountDueNow": 0,
        "effectiveAt": 1738368000,
        "currentPlanUntil": 1738368000,
    }


def test_classify_schedule_none():
    result = classify_schedule(
        None, current_price_id="price_premium_monthly", current_period_end=1738368000, offers=OFFERS
    )
    assert result == {
        "state": "none",
        "pendingPlan": None,
        "pendingOfferKey": None,
        "pendingChangeEffectiveAt": None,
    }


def test_classify_schedule_recognized_downgrade():
    schedule = {
        "phases": [
            {
                "items": [{"price": "price_premium_monthly"}],
                "end_date": 1738368000,
            },
            {
                "items": [{"price": "price_plus_monthly"}],
                "start_date": 1738368000,
            },
        ]
    }
    result = classify_schedule(
        schedule, current_price_id="price_premium_monthly", current_period_end=1738368000, offers=OFFERS
    )
    assert result == {
        "state": "scheduled",
        "pendingPlan": "plus",
        "pendingOfferKey": "plus_monthly",
        "pendingChangeEffectiveAt": 1738368000,
    }


@pytest.mark.parametrize(
    "schedule",
    [
        {"phases": [{"items": [{"price": "price_premium_monthly"}], "end_date": 1738368000}]},  # 1 phase
        {
            "phases": [
                {"items": [{"price": "price_premium_monthly"}], "end_date": 1738368000},
                {"items": [{"price": "price_unknown"}], "start_date": 1738368000},
            ]
        },  # unmapped phase-2 price
        {
            "phases": [
                {"items": [{"price": "price_different"}], "end_date": 1738368000},
                {"items": [{"price": "price_plus_monthly"}], "start_date": 1738368000},
            ]
        },  # phase-1 price mismatch
        {
            "phases": [
                {"items": [{"price": "price_premium_monthly"}], "end_date": 999},
                {"items": [{"price": "price_plus_monthly"}], "start_date": 1738368000},
            ]
        },  # date mismatch between phase boundaries
    ],
)
def test_classify_schedule_unknown_shapes(schedule):
    result = classify_schedule(
        schedule, current_price_id="price_premium_monthly", current_period_end=1738368000, offers=OFFERS
    )
    assert result["state"] == "unknown"
    assert result["pendingPlan"] is None


def test_upgrade_idempotency_key_format():
    key = upgrade_idempotency_key("sub_1", "price_a", "price_b", 1735689600)
    assert key == "planchange:sub_1:price_a:price_b:1735689600"


def test_downgrade_idempotency_key_format():
    key = downgrade_idempotency_key("sub_1", "price_a", "price_b", 1738368000)
    assert key == "plandowngrade:sub_1:price_a:price_b:1738368000"
