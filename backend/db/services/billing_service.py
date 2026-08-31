"""Canonical checkout, reconciliation, and entitlement synchronization."""
from __future__ import annotations
import logging
from datetime import datetime, timezone
from backend.db.repositories.billing_repository import BillingRepository
from backend.domain.billing.catalog import OFFERS, BillingOfferNotConfigured, offer_for_price_id
from backend.domain.billing.errors import BillingOwnershipError, BillingPortalUnavailable, BillingSubscriptionAlreadyManaged
from backend.domain.billing.policy import effective_plan, has_duplicate_active_subscriptions, subscription_grants_access, PLAN_RANK
from backend.domain.billing.providers.stripe_provider import StripeProvider

logger = logging.getLogger(__name__)
RECONCILING_EVENTS = frozenset({
    "checkout.session.completed", "customer.subscription.created", "customer.subscription.updated",
    "customer.subscription.deleted", "customer.subscription.paused", "customer.subscription.resumed",
    "invoice.paid", "invoice.payment_failed", "invoice.payment_action_required",
})

def _plain(value): return value.to_dict_recursive() if hasattr(value, "to_dict_recursive") else dict(value)
def _iso(epoch): return datetime.fromtimestamp(epoch, timezone.utc).isoformat() if epoch else None
def _subscription_id_from_event_object(obj):
    """Normalize Checkout and Dahlia-era Invoice subscription references."""
    reference = obj.get("subscription")
    if not reference:
        reference = (((obj.get("parent") or {}).get("subscription_details") or {}).get("subscription"))
    if isinstance(reference, dict): reference = reference.get("id")
    return reference

class BillingService:
    def __init__(self, repository=None, provider=None, offers=None):
        self.repository = repository or BillingRepository()
        self.provider = provider or StripeProvider()
        self.offers = offers or OFFERS

    def resolve_checkout_offer(self, offer_key):
        offer = self.offers.get(offer_key)
        if offer is None: raise KeyError("unknown offer")
        if not offer.purchasable: raise BillingOfferNotConfigured("BILLING_OFFER_NOT_CONFIGURED")
        return offer

    def ensure_customer(self, *, user_id, email=None):
        existing = self.repository.find_customer(user_id)
        if existing: return existing
        customer = _plain(self.provider.create_customer(user_id=user_id, email=email,
                          idempotency_key=f"index-customer:{user_id}"))
        return self.repository.create_customer_mapping(user_id=user_id, provider_customer_id=customer["id"])

    def create_checkout(self, *, user_id, offer_key, success_url, cancel_url):
        offer = self.resolve_checkout_offer(offer_key)
        if any(subscription_grants_access(row.get("status")) for row in self.repository.find_subscriptions(user_id)):
            raise BillingSubscriptionAlreadyManaged("Use Customer Portal for an existing subscription")
        profile = self.repository.get_profile(user_id) or {"id": user_id}
        customer = self.ensure_customer(user_id=user_id, email=profile.get("email"))
        session = _plain(self.provider.create_checkout_session(
            customer_id=customer["provider_customer_id"], price_id=offer.provider_price_id,
            user_id=user_id, offer_key=offer.offer_key, plan=offer.plan,
            success_url=success_url, cancel_url=cancel_url))
        logger.info("billing.checkout.created user_id=%s customer_id=%s", user_id, customer["provider_customer_id"])
        return session["url"]

    def create_customer_portal(self, *, user_id, return_url):
        customer = self.repository.find_customer(user_id)
        if not customer:
            raise BillingPortalUnavailable("No Stripe billing relationship exists")
        session = _plain(self.provider.create_customer_portal_session(
            customer_id=customer["provider_customer_id"], return_url=return_url))
        logger.info("billing.portal.created user_id=%s", user_id)
        return session["url"]

    def reconcile_subscription(self, subscription_id):
        subscription = _plain(self.provider.retrieve_subscription(subscription_id))
        customer_id = subscription.get("customer")
        if isinstance(customer_id, dict): customer_id = customer_id.get("id")
        customer = self.repository.find_customer_by_provider_id(customer_id)
        if not customer: raise BillingOwnershipError("Stripe customer has no trusted inDex mapping")
        return self.reconcile_subscription_snapshot(customer, subscription)

    def subscription_row(self, customer, subscription):
        subscription = _plain(subscription)
        items = ((subscription.get("items") or {}).get("data") or [])
        recurring = [item for item in items if (item.get("price") or {}).get("id")]
        recognized = [(item, offer_for_price_id((item.get("price") or {}).get("id"), self.offers)) for item in recurring]
        recognized = [(item, offer) for item, offer in recognized if offer]
        if len(recurring) != 1: mapping, offer = "unsupported_shape", None
        elif len(recognized) != 1: mapping, offer = "unmapped_price", None
        else: mapping, offer = "mapped", recognized[0][1]
        price = (recurring[0].get("price") or {}) if len(recurring) == 1 else {}
        product_id = price.get("product")
        if isinstance(product_id, dict): product_id = product_id.get("id")
        return {"user_id": customer["user_id"], "billing_customer_id": customer["id"], "provider": "stripe",
            "provider_subscription_id": subscription["id"], "provider_product_id": product_id,
            "provider_price_id": price.get("id"), "offer_key": offer.offer_key if offer else None,
            "plan": offer.plan if offer else None, "status": subscription.get("status") or "unknown",
            "current_period_start": _iso(subscription.get("current_period_start") or (recurring[0].get("current_period_start") if len(recurring) == 1 else None)),
            "current_period_end": _iso(subscription.get("current_period_end") or (recurring[0].get("current_period_end") if len(recurring) == 1 else None)),
            "cancel_at_period_end": bool(subscription.get("cancel_at_period_end")),
            "canceled_at": _iso(subscription.get("canceled_at")), "ended_at": _iso(subscription.get("ended_at")),
            "commercial_mapping_status": mapping, "last_reconciled_at": datetime.now(timezone.utc).isoformat(),
            "reconciliation_error_code": None if mapping == "mapped" else mapping.upper()}

    def reconcile_subscription_snapshot(self, customer, subscription):
        row = self.subscription_row(customer, subscription)
        if hasattr(self.repository, "persist_subscription_and_recompute"):
            persisted = self.repository.persist_subscription_and_recompute(row)
            resolved = self.repository.get_profile(customer["user_id"]).get("index_plan") if hasattr(self.repository, "get_profile") else None
        else:  # Lightweight repository fakes retain the same domain contract.
            persisted = self.repository.upsert_subscription(row)
            resolved = self.repository.recompute_effective_plan(customer["user_id"])
        mapping = row["commercial_mapping_status"]
        subscription = _plain(subscription)
        if mapping != "mapped": logger.warning("billing.price.unmapped user_id=%s subscription_id=%s", customer["user_id"], subscription["id"])
        logger.info("billing.subscription.reconciled user_id=%s subscription_id=%s plan=%s mapping=%s",
                    customer["user_id"], subscription["id"], resolved, mapping)
        return persisted

    def billing_status(self, user_id):
        rows, manual = self.repository.find_subscriptions(user_id), self.repository.manual_plan(user_id)
        plan = effective_plan(rows, manual)
        if has_duplicate_active_subscriptions(rows): logger.warning("billing.multiple_active_subscriptions user_id=%s", user_id)
        mapped = [row for row in rows if row.get("commercial_mapping_status", "mapped") == "mapped"]
        mapped.sort(key=lambda row: (subscription_grants_access(row.get("status")), PLAN_RANK.get(row.get("plan"), 0), row.get("updated_at") or ""), reverse=True)
        billing = mapped[0] if mapped else None
        customer = self.repository.find_customer(user_id)
        purchasable = sorted(key for key, offer in self.offers.items() if offer.purchasable)
        return {"effectivePlan": plan, "billingPlan": billing.get("plan") if billing else None,
            "billingManaged": bool(customer and billing), "accessManagedByIndex": bool(manual),
            "subscriptionStatus": billing.get("status") if billing else None,
            "offerKey": billing.get("offer_key") if billing else None,
            "cancelAtPeriodEnd": bool(billing and billing.get("cancel_at_period_end")),
            "currentPeriodEnd": billing.get("current_period_end") if billing else None,
            "billingConfigured": bool(purchasable), "purchasableOfferKeys": purchasable}

    def handle_event(self, event):
        event = _plain(event); event_id, event_type = event["id"], event["type"]
        claim = self.repository.claim_webhook_event(event_id=event_id, event_type=event_type)
        if claim == "duplicate": return "duplicate"
        if claim == "busy": raise RuntimeError("event already processing")
        try:
            if event_type in RECONCILING_EVENTS:
                obj = ((event.get("data") or {}).get("object") or {})
                subscription_id = _subscription_id_from_event_object(obj)
                if event_type.startswith("customer.subscription."): subscription_id = obj.get("id")
                if subscription_id: self.reconcile_subscription(subscription_id)
            self.repository.finish_webhook_event(event_id)
            return "processed"
        except Exception as exc:
            self.repository.fail_webhook_event(event_id, getattr(exc, "code", "PROCESSING_FAILED"), type(exc).__name__)
            raise
