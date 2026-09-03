"""Full plan-change matrix across Plus/Premium and month/year offers."""
import pytest

from backend.domain.billing.catalog import CommercialOffer
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
        self.preview_response = preview_response or {"amount_due": 1234, "currency": "usd"}
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


def _subscription(price_id, period_end=1738368000):
    return {
        "id": "sub_1",
        "status": "active",
        "current_period_end": period_end,
        "schedule": None,
        "items": {"data": [{"id": "si_1", "price": {"id": price_id}}]},
        "latest_invoice": {"payment_intent": {"status": "succeeded"}},
    }


def _service(current_offer):
    repository = _FakeRepository(
        customer={"provider_customer_id": "cus_1"},
        subscriptions=[{"provider_subscription_id": "sub_1", "status": "active", "commercial_mapping_status": "mapped"}],
    )
    provider = _FakeProvider(_subscription(current_offer.provider_price_id))
    return BillingService(repository=repository, provider=provider, offers=OFFERS), provider


UPGRADE_CASES = [
    (PLUS_MONTHLY, PREMIUM_MONTHLY),
    (PLUS_MONTHLY, PREMIUM_ANNUAL),
    (PLUS_ANNUAL, PREMIUM_MONTHLY),
    (PLUS_ANNUAL, PREMIUM_ANNUAL),
]

DOWNGRADE_CASES = [
    (PREMIUM_MONTHLY, PLUS_MONTHLY),
    (PREMIUM_MONTHLY, PLUS_ANNUAL),
    (PREMIUM_ANNUAL, PLUS_MONTHLY),
    (PREMIUM_ANNUAL, PLUS_ANNUAL),
]

SAME_TIER_CASES = [
    (PLUS_MONTHLY, PLUS_ANNUAL),
    (PLUS_ANNUAL, PLUS_MONTHLY),
    (PREMIUM_MONTHLY, PREMIUM_ANNUAL),
    (PREMIUM_ANNUAL, PREMIUM_MONTHLY),
]


@pytest.mark.parametrize("current_offer,target_offer", UPGRADE_CASES)
def test_upgrade_transition(current_offer, target_offer):
    service, provider = _service(current_offer)
    preview = service.preview_plan_change(user_id="user-1", offer_key=target_offer.offer_key)
    assert preview["action"] == "upgrade_now"
    assert preview["fromPlan"] == "plus"
    assert preview["toPlan"] == "premium"

    result = service.confirm_plan_change(
        user_id="user-1", offer_key=target_offer.offer_key, preview_token=preview["previewToken"]
    )
    assert result["paymentResult"] == "succeeded"
    assert provider.update_calls[0]["target_price_id"] == target_offer.provider_price_id


@pytest.mark.parametrize("current_offer,target_offer", DOWNGRADE_CASES)
def test_downgrade_transition(current_offer, target_offer):
    service, provider = _service(current_offer)
    preview = service.preview_plan_change(user_id="user-1", offer_key=target_offer.offer_key)
    assert preview["action"] == "downgrade_at_period_end"
    assert preview["amountDueNow"] == 0

    result = service.confirm_plan_change(user_id="user-1", offer_key=target_offer.offer_key, preview_token=None)
    assert result["action"] == "downgrade_at_period_end"
    assert provider.schedule_calls[0]["target_price_id"] == target_offer.provider_price_id


@pytest.mark.parametrize("current_offer,target_offer", SAME_TIER_CASES)
def test_same_tier_interval_change_schedules_at_period_end(current_offer, target_offer):
    service, provider = _service(current_offer)
    preview = service.preview_plan_change(user_id="user-1", offer_key=target_offer.offer_key)
    assert preview["action"] == "interval_change_at_period_end"
    assert preview["fromPlan"] == preview["toPlan"] == current_offer.plan
    assert preview["fromOfferKey"] == current_offer.offer_key
    assert preview["toOfferKey"] == target_offer.offer_key
    assert preview["amountDueNow"] == 0
    assert not provider.preview_calls

    result = service.confirm_plan_change(user_id="user-1", offer_key=target_offer.offer_key, preview_token=None)
    assert result["action"] == "interval_change_at_period_end"
    assert result["pendingChangeEffectiveAt"] == 1738368000
    assert provider.schedule_calls[0]["target_price_id"] == target_offer.provider_price_id
    assert not provider.update_calls
