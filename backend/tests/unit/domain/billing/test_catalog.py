import pytest

from backend.domain.billing.catalog import (
    BILLING_OFFER_NOT_CONFIGURED, OFFERS, BillingOfferNotConfigured, build_offer_catalog,
    require_purchasable_offer,
)


def test_all_declared_offers_are_disabled_and_price_neutral():
    assert set(OFFERS) == {"plus_monthly", "plus_annual", "premium_monthly", "premium_annual"}
    assert all(not offer.enabled for offer in OFFERS.values())
    assert all(offer.provider_price_id is None for offer in OFFERS.values())
    assert {key: offer.unit_amount_minor for key, offer in OFFERS.items()} == {
        "plus_monthly": 999, "plus_annual": 7900,
        "premium_monthly": 2499, "premium_annual": 21900,
    }
    assert all(offer.currency is None for offer in OFFERS.values())


def test_price_ids_without_approved_currency_cannot_activate_checkout():
    offers = build_offer_catalog({"STRIPE_PRICE_PLUS_MONTHLY": "price_test"})
    assert offers["plus_monthly"].purchasable is False


def test_currency_and_server_price_mapping_activate_only_configured_offers():
    offers = build_offer_catalog({"BILLING_CURRENCY": "USD", "BILLING_CHECKOUT_ENABLED": "true", "STRIPE_PRICE_PLUS_MONTHLY": "price_test"})
    assert offers["plus_monthly"].purchasable is True
    assert offers["plus_monthly"].currency == "usd"
    assert offers["plus_annual"].purchasable is False


def test_purchase_kill_switch_preserves_existing_subscription_price_mapping():
    offers = build_offer_catalog({"BILLING_CURRENCY": "USD", "STRIPE_PRICE_PLUS_MONTHLY": "price_test"})
    from backend.domain.billing.catalog import offer_for_price_id
    assert offers["plus_monthly"].purchasable is False
    assert offer_for_price_id("price_test", offers).plan == "plus"


@pytest.mark.parametrize("key", [*OFFERS, "unknown_offer"])
def test_unconfigured_and_unknown_offers_fail_closed(key):
    with pytest.raises(BillingOfferNotConfigured) as error:
        require_purchasable_offer(key)
    assert error.value.code == BILLING_OFFER_NOT_CONFIGURED
