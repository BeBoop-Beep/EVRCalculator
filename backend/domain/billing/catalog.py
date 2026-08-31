"""Server-owned, pricing-neutral commercial offer catalog."""

from __future__ import annotations

from dataclasses import dataclass
import os
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


_OFFER_DEFINITIONS = (
    ("plus_monthly", "plus", "month", "STRIPE_PRICE_PLUS_MONTHLY"),
    ("plus_annual", "plus", "year", "STRIPE_PRICE_PLUS_ANNUAL"),
    ("premium_monthly", "premium", "month", "STRIPE_PRICE_PREMIUM_MONTHLY"),
    ("premium_annual", "premium", "year", "STRIPE_PRICE_PREMIUM_ANNUAL"),
)


def build_offer_catalog(environ: Mapping[str, str] | None = None) -> Mapping[str, CommercialOffer]:
    source = os.environ if environ is None else environ
    offers = {}
    for key, plan, interval, variable in _OFFER_DEFINITIONS:
        price_id = (source.get(variable) or "").strip() or None
        offers[key] = CommercialOffer(key, plan, interval, bool(price_id), price_id)
    return offers


OFFERS: Mapping[str, CommercialOffer] = build_offer_catalog()


def offer_for_price_id(price_id: str, offers: Mapping[str, CommercialOffer] | None = None) -> CommercialOffer | None:
    matches = [offer for offer in (offers or OFFERS).values() if offer.provider_price_id == price_id]
    return matches[0] if len(matches) == 1 else None


def require_purchasable_offer(offer_key: str) -> CommercialOffer:
    offer = OFFERS.get(offer_key)
    if offer is None or not offer.purchasable:
        raise BillingOfferNotConfigured(BILLING_OFFER_NOT_CONFIGURED)
    return offer


class BillingOfferNotConfigured(ValueError):
    code = BILLING_OFFER_NOT_CONFIGURED
