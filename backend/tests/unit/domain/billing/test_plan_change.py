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
PREMIUM_ANNUAL_OFFER = CommercialOffer(
    offer_key="premium_annual",
    plan="premium",
    billing_interval="year",
    enabled=True,
    provider_price_id="price_premium_annual",
    unit_amount_minor=21900,
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
PLUS_ANNUAL_OFFER = CommercialOffer(
    offer_key="plus_annual",
    plan="plus",
    billing_interval="year",
    enabled=True,
    provider_price_id="price_plus_annual",
    unit_amount_minor=7900,
    currency="usd",
)
OFFERS = {
    offer.offer_key: offer
    for offer in (
        PREMIUM_MONTHLY_OFFER,
        PREMIUM_ANNUAL_OFFER,
        PLUS_MONTHLY_OFFER,
        PLUS_ANNUAL_OFFER,
    )
}


@pytest.mark.parametrize(
    "current_plan,target_plan,expected",
    [
        ("plus", "premium", PlanChangeAction.UPGRADE_NOW),
        ("premium", "plus", PlanChangeAction.DOWNGRADE_AT_PERIOD_END),
    ],
)
def test_classify_transition_valid_cross_tier(current_plan, target_plan, expected):
    assert classify_transition(current_plan, target_plan) == expected


@pytest.mark.parametrize("plan", ["plus", "premium"])
def test_classify_transition_same_tier_interval_change_is_scheduled(plan):
    assert classify_transition(
        plan,
        plan,
        current_interval="month",
        target_interval="year",
    ) == PlanChangeAction.INTERVAL_CHANGE_AT_PERIOD_END
    assert classify_transition(
        plan,
        plan,
        current_interval="year",
        target_interval="month",
    ) == PlanChangeAction.INTERVAL_CHANGE_AT_PERIOD_END


@pytest.mark.parametrize(
    "current_plan,target_plan,current_interval,target_interval",
    [
        ("plus", "plus", None, None),
        ("plus", "plus", "month", "month"),
        ("premium", "premium", "year", "year"),
        (None, "plus", None, None),
        ("plus", None, None, None),
        ("plus", "basic", None, None),
        (None, None, None, None),
    ],
)
def test_classify_transition_rejects_invalid(current_plan, target_plan, current_interval, target_interval):
    with pytest.raises(PlanChangeNotAllowed):
        classify_transition(
            current_plan,
            target_plan,
            current_interval=current_interval,
            target_interval=target_interval,
        )


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


def test_build_interval_change_preview_dto_shape():
    dto = build_downgrade_preview_dto(
        from_plan="plus",
        to_plan="plus",
        from_offer_key="plus_monthly",
        to_offer_key="plus_annual",
        current_period_end=1738368000,
        action=PlanChangeAction.INTERVAL_CHANGE_AT_PERIOD_END,
    )
    assert dto["action"] == "interval_change_at_period_end"
    assert dto["amountDueNow"] == 0
    assert dto["currentPlanUntil"] == 1738368000


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


def test_classify_schedule_recognized_interval_change():
    schedule = {
        "phases": [
            {
                "items": [{"price": "price_plus_monthly"}],
                "end_date": 1738368000,
            },
            {
                "items": [{"price": "price_plus_annual"}],
                "start_date": 1738368000,
            },
        ]
    }
    result = classify_schedule(
        schedule, current_price_id="price_plus_monthly", current_period_end=1738368000, offers=OFFERS
    )
    assert result == {
        "state": "scheduled",
        "pendingPlan": "plus",
        "pendingOfferKey": "plus_annual",
        "pendingChangeEffectiveAt": 1738368000,
    }


def test_classify_schedule_rejects_scheduled_upgrade_shape():
    schedule = {
        "phases": [
            {"items": [{"price": "price_plus_monthly"}], "end_date": 1738368000},
            {"items": [{"price": "price_premium_monthly"}], "start_date": 1738368000},
        ]
    }
    result = classify_schedule(
        schedule, current_price_id="price_plus_monthly", current_period_end=1738368000, offers=OFFERS
    )
    assert result["state"] == "unknown"


@pytest.mark.parametrize(
    "schedule",
    [
        {"phases": [{"items": [{"price": "price_premium_monthly"}], "end_date": 1738368000}]},
        {
            "phases": [
                {"items": [{"price": "price_premium_monthly"}], "end_date": 1738368000},
                {"items": [{"price": "price_unknown"}], "start_date": 1738368000},
            ]
        },
        {
            "phases": [
                {"items": [{"price": "price_different"}], "end_date": 1738368000},
                {"items": [{"price": "price_plus_monthly"}], "start_date": 1738368000},
            ]
        },
        {
            "phases": [
                {"items": [{"price": "price_premium_monthly"}], "end_date": 999},
                {"items": [{"price": "price_plus_monthly"}], "start_date": 1738368000},
            ]
        },
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
