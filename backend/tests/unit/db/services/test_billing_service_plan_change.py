import os
import time

import pytest

from backend.domain.billing.catalog import CommercialOffer
from backend.domain.billing.errors import (
    BillingOwnershipError,
    PlanChangeNotAllowed,
    PlanChangePreviewStale,
    UnmappedStripePrice,
    UnsupportedSubscriptionShape,
)
from backend.db.services.billing_service import BillingService

PLUS_MONTHLY = CommercialOffer("plus_monthly", "plus", "month", True, "price_plus_monthly", 999, "usd")
PLUS_ANNUAL = CommercialOffer("plus_annual", "plus", "year", True, "price_plus_annual", 7900, "usd")
PREMIUM_MONTHLY = CommercialOffer("premium_monthly", "premium", "month", True, "price_premium_monthly", 2499, "usd")
PREMIUM_ANNUAL = CommercialOffer("premium_annual", "premium", "year", True, "price_premium_annual", 21900, "usd")
OFFERS = {o.offer_key: o for o in (PLUS_MONTHLY, PLUS_ANNUAL, PREMIUM_MONTHLY, PREMIUM_ANNUAL)}


@pytest.fixture(autouse=True)
def _signing_secret(monkeypatch):
    monkeypatch.setenv("BILLING_PLAN_CHANGE_SIGNING_SECRET", "test-secret")


class _FakeRepository:
    def __init__(self, customer=None, subscriptions=None):
        self.customer = customer
        self.subscriptions = subscriptions or []

    def find_customer(self, user_id, provider="stripe"):
        return self.customer

    def find_subscriptions(self, user_id):
        return self.subscriptions

    def manual_plan(self, user_id):
        return None


class _FakeProvider:
    def __init__(self, subscription, preview_response=None, update_response=None, schedule_response=None):
        self.subscription = subscription
        self.preview_response = preview_response or {"amount_due": 1500, "currency": "usd"}
        self.update_response = update_response or {"payment_result": "succeeded", "subscription": subscription}
        self.schedule_response = schedule_response or {"id": "sub_sched_1"}
        self.preview_calls = []
        self.update_calls = []
        self.schedule_calls = []
        self.release_calls = []

    def retrieve_subscription(self, subscription_id, expand=None):
        return self.subscription

    def preview_subscription_update(self, **kwargs):
        self.preview_calls.append(kwargs)
        return self.preview_response

    def update_subscription_item(self, **kwargs):
        self.update_calls.append(kwargs)
        return self.update_response

    def create_downgrade_schedule(self, **kwargs):
        self.schedule_calls.append(kwargs)
        return self.schedule_response

    def release_schedule(self, **kwargs):
        self.release_calls.append(kwargs)


def _plus_subscription(period_end=1738368000, schedule=None):
    return {
        "id": "sub_1",
        "status": "active",
        "current_period_end": period_end,
        "schedule": schedule,
        "items": {"data": [{"id": "si_1", "price": {"id": "price_plus_monthly"}}]},
        "latest_invoice": {"payment_intent": {"status": "succeeded"}},
    }


def _premium_subscription(period_end=1738368000, schedule=None):
    return {
        "id": "sub_1",
        "status": "active",
        "current_period_end": period_end,
        "schedule": schedule,
        "items": {"data": [{"id": "si_1", "price": {"id": "price_premium_monthly"}}]},
        "latest_invoice": {"payment_intent": {"status": "succeeded"}},
    }


def _service(subscription, **provider_kwargs):
    repository = _FakeRepository(
        customer={"provider_customer_id": "cus_1"},
        subscriptions=[{"provider_subscription_id": "sub_1", "status": "active", "commercial_mapping_status": "mapped"}],
    )
    provider = _FakeProvider(subscription, **provider_kwargs)
    return BillingService(repository=repository, provider=provider, offers=OFFERS), provider


def test_preview_plan_change_upgrade_returns_dto_and_token():
    service, provider = _service(_plus_subscription())
    dto = service.preview_plan_change(user_id="user-1", offer_key="premium_monthly")
    assert dto["action"] == "upgrade_now"
    assert dto["fromPlan"] == "plus"
    assert dto["toPlan"] == "premium"
    assert dto["amountDueNow"] == 1500
    assert "previewToken" in dto
    assert provider.preview_calls  # non-mutating provider call only


def test_preview_plan_change_downgrade_returns_zero_due_now():
    service, _ = _service(_premium_subscription())
    dto = service.preview_plan_change(user_id="user-1", offer_key="plus_monthly")
    assert dto["action"] == "downgrade_at_period_end"
    assert dto["amountDueNow"] == 0
    assert dto["effectiveAt"] == 1738368000


def test_preview_same_tier_rejected():
    service, _ = _service(_plus_subscription())
    with pytest.raises(PlanChangeNotAllowed):
        service.preview_plan_change(user_id="user-1", offer_key="plus_annual")


def test_preview_unmapped_current_price_rejected():
    subscription = _plus_subscription()
    subscription["items"]["data"][0]["price"]["id"] = "price_unrecognized"
    service, _ = _service(subscription)
    with pytest.raises(UnmappedStripePrice):
        service.preview_plan_change(user_id="user-1", offer_key="premium_monthly")


def test_preview_multi_item_subscription_rejected():
    subscription = _plus_subscription()
    subscription["items"]["data"].append({"id": "si_2", "price": {"id": "price_plus_annual"}})
    service, _ = _service(subscription)
    with pytest.raises(UnsupportedSubscriptionShape):
        service.preview_plan_change(user_id="user-1", offer_key="premium_monthly")


def test_preview_no_customer_rejected():
    repository = _FakeRepository(customer=None)
    provider = _FakeProvider(_plus_subscription())
    service = BillingService(repository=repository, provider=provider, offers=OFFERS)
    with pytest.raises(BillingOwnershipError):
        service.preview_plan_change(user_id="user-1", offer_key="premium_monthly")


def test_confirm_upgrade_reuses_proration_date_and_succeeds():
    service, provider = _service(_plus_subscription())
    preview = service.preview_plan_change(user_id="user-1", offer_key="premium_monthly")
    result = service.confirm_plan_change(
        user_id="user-1", offer_key="premium_monthly", preview_token=preview["previewToken"]
    )
    assert result["paymentResult"] == "succeeded"
    preview_proration = provider.preview_calls[0]["proration_date"]
    update_proration = provider.update_calls[0]["proration_date"]
    assert preview_proration == update_proration


def test_confirm_upgrade_stale_amount_blocks_mutation():
    service, provider = _service(_plus_subscription())
    preview = service.preview_plan_change(user_id="user-1", offer_key="premium_monthly")
    provider.preview_response = {"amount_due": 999999, "currency": "usd"}  # price changed server-side
    with pytest.raises(PlanChangePreviewStale):
        service.confirm_plan_change(
            user_id="user-1", offer_key="premium_monthly", preview_token=preview["previewToken"]
        )
    assert not provider.update_calls


def test_confirm_upgrade_expired_token_rejected():
    service, provider = _service(_plus_subscription())
    preview = service.preview_plan_change(user_id="user-1", offer_key="premium_monthly")
    tampered = preview["previewToken"][:-4] + "0000"
    with pytest.raises(PlanChangeNotAllowed):
        service.confirm_plan_change(user_id="user-1", offer_key="premium_monthly", preview_token=tampered)
    assert not provider.update_calls


def test_confirm_upgrade_token_for_different_subscription_rejected():
    service, provider = _service(_plus_subscription())
    preview = service.preview_plan_change(user_id="user-1", offer_key="premium_monthly")
    other_service, _ = _service(_plus_subscription())
    other_service.repository.customer = {"provider_customer_id": "cus_2"}
    other_service.provider.subscription["id"] = "sub_2"
    with pytest.raises(PlanChangeNotAllowed):
        other_service.confirm_plan_change(
            user_id="user-1", offer_key="premium_monthly", preview_token=preview["previewToken"]
        )


def test_confirm_downgrade_creates_schedule_from_subscription():
    service, provider = _service(_premium_subscription())
    preview = service.preview_plan_change(user_id="user-1", offer_key="plus_monthly")
    result = service.confirm_plan_change(user_id="user-1", offer_key="plus_monthly", preview_token=None)
    assert result["action"] == "downgrade_at_period_end"
    assert result["pendingChangeEffectiveAt"] == 1738368000
    assert provider.schedule_calls[0]["subscription_id"] == "sub_1"
    assert provider.schedule_calls[0]["target_price_id"] == "price_plus_monthly"


def test_billing_status_pending_none_when_no_schedule():
    service, _ = _service(_premium_subscription(schedule=None))
    status = service.billing_status("user-1")
    assert status["pendingChangeState"] == "none"


def test_billing_status_pending_scheduled_when_recognized_schedule():
    schedule = {
        "phases": [
            {"items": [{"price": "price_premium_monthly"}], "end_date": 1738368000},
            {"items": [{"price": "price_plus_monthly"}], "start_date": 1738368000},
        ]
    }
    service, _ = _service(_premium_subscription(schedule=schedule))
    status = service.billing_status("user-1")
    assert status["pendingChangeState"] == "scheduled"
    assert status["pendingPlan"] == "plus"
    assert status["pendingOfferKey"] == "plus_monthly"
    assert status["pendingChangeEffectiveAt"] == 1738368000


def test_billing_status_pending_unknown_when_provider_raises():
    class _RaisingProvider(_FakeProvider):
        def retrieve_subscription(self, subscription_id, expand=None):
            raise RuntimeError("stripe outage")

    repository = _FakeRepository(
        customer={"provider_customer_id": "cus_1"},
        subscriptions=[{"provider_subscription_id": "sub_1", "status": "active", "commercial_mapping_status": "mapped", "plan": "premium"}],
    )
    service = BillingService(repository=repository, provider=_RaisingProvider(_premium_subscription()), offers=OFFERS)
    status = service.billing_status("user-1")
    assert status["pendingChangeState"] == "unknown"
    assert status["effectivePlan"] == "premium"  # unaffected by Stripe outage


def test_cancel_scheduled_releases_recognized_schedule():
    schedule = {
        "phases": [
            {"items": [{"price": "price_premium_monthly"}], "end_date": 1738368000},
            {"items": [{"price": "price_plus_monthly"}], "start_date": 1738368000},
        ],
        "id": "sub_sched_1",
    }
    service, provider = _service(_premium_subscription(schedule=schedule))
    result = service.cancel_scheduled_plan_change(user_id="user-1")
    assert result == {"cancelled": True}
    assert provider.release_calls[0]["schedule_id"] == "sub_sched_1"


def test_cancel_scheduled_rejects_unknown_schedule():
    schedule = {"phases": [{"items": [{"price": "price_premium_monthly"}], "end_date": 1738368000}]}
    service, provider = _service(_premium_subscription(schedule=schedule))
    with pytest.raises(PlanChangeNotAllowed):
        service.cancel_scheduled_plan_change(user_id="user-1")
    assert not provider.release_calls


def test_cancel_scheduled_rejects_when_no_schedule():
    service, provider = _service(_premium_subscription(schedule=None))
    with pytest.raises(PlanChangeNotAllowed):
        service.cancel_scheduled_plan_change(user_id="user-1")
    assert not provider.release_calls


def test_repeated_confirm_upgrade_reuses_same_idempotency_key():
    service, provider = _service(_plus_subscription())
    preview = service.preview_plan_change(user_id="user-1", offer_key="premium_monthly")
    service.confirm_plan_change(user_id="user-1", offer_key="premium_monthly", preview_token=preview["previewToken"])
    service.confirm_plan_change(user_id="user-1", offer_key="premium_monthly", preview_token=preview["previewToken"])
    keys = {call["idempotency_key"] for call in provider.update_calls}
    assert len(keys) == 1
