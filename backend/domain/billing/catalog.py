"""Server-owned, pricing-neutral commercial offer catalog."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping

BILLING_OFFER_NOT_CONFIGURED = "BILLING_OFFER_NOT_CONFIGURED"


@dataclass(frozen=True)
class CommercialOffer:
    offer_key: str
    plan: str
    billing_interval: str
    enabled: bool = False
    provider_price_id: str | None = None

    @property
    def purchasable(self) -> bool:
        return self.enabled and bool((self.provider_price_id or "").strip())


OFFERS: Mapping[str, CommercialOffer] = {
    key: CommercialOffer(key, plan, interval)
    for key, plan, interval in (
        ("plus_monthly", "plus", "month"),
        ("plus_annual", "plus", "year"),
        ("premium_monthly", "premium", "month"),
        ("premium_annual", "premium", "year"),
    )
}


def require_purchasable_offer(offer_key: str) -> CommercialOffer:
    offer = OFFERS.get(offer_key)
    if offer is None or not offer.purchasable:
        raise BillingOfferNotConfigured(BILLING_OFFER_NOT_CONFIGURED)
    return offer


class BillingOfferNotConfigured(ValueError):
    code = BILLING_OFFER_NOT_CONFIGURED
