import pytest

from backend.domain.billing.catalog import (
    BILLING_OFFER_NOT_CONFIGURED, OFFERS, BillingOfferNotConfigured,
    require_purchasable_offer,
)


def test_all_declared_offers_are_disabled_and_price_neutral():
    assert set(OFFERS) == {"plus_monthly", "plus_annual", "premium_monthly", "premium_annual"}
    assert all(not offer.enabled for offer in OFFERS.values())
    assert all(offer.provider_price_id is None for offer in OFFERS.values())


@pytest.mark.parametrize("key", [*OFFERS, "unknown_offer"])
def test_unconfigured_and_unknown_offers_fail_closed(key):
    with pytest.raises(BillingOfferNotConfigured) as error:
        require_purchasable_offer(key)
    assert error.value.code == BILLING_OFFER_NOT_CONFIGURED
