"""Provider-neutral billing service. No Stripe calls belong in Effort 1."""

from backend.domain.billing.catalog import require_purchasable_offer


class BillingService:
    def resolve_checkout_offer(self, offer_key: str):
        """Fail closed until a later effort explicitly configures an offer."""
        return require_purchasable_offer(offer_key)

