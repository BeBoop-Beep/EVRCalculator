"""Canonical checkout, reconciliation, and entitlement synchronization."""
from __future__ import annotations
import logging
import os
import time
from datetime import datetime, timezone
from backend.db.repositories.billing_repository import BillingRepository
from backend.domain.billing.catalog import OFFERS, BillingOfferNotConfigured, offer_for_price_id
from backend.domain.billing.errors import (
    BillingNotConfigured,
    BillingOwnershipError,
    BillingPortalUnavailable,
    BillingSubscriptionAlreadyManaged,
    PlanChangeNotAllowed,
    PlanChangePreviewStale,
    UnmappedStripePrice,
    UnsupportedSubscriptionShape,
)
from backend.domain.billing.plan_change import (
    PlanChangeAction,
    build_downgrade_preview_dto,
    build_upgrade_preview_dto,
    classify_schedule,
    classify_transition,
    downgrade_idempotency_key,
    upgrade_idempotency_key,
)
from backend.domain.billing.policy import effective_plan, has_duplicate_active_subscriptions, subscription_grants_access, PLAN_RANK
from backend.domain.billing.preview_token import sign_preview_token, verify_preview_token
from backend.domain.billing.providers.stripe_provider import StripeProvider

logger = logging.getLogger(__name__)
RECONCILING_EVENTS = frozenset({
    "checkout.session.completed", "customer.subscription.created", "customer.subscription.updated",
    "customer.subscription.deleted", "customer.subscription.paused", "customer.subscription.resumed",
    "invoice.paid", "invoice.payment_failed", "invoice.payment_action_required",
})

def _plain(value):
    # stripe-python 15.4.0's StripeObject has no `to_dict_recursive` (that
    # method name does not exist on this SDK version -- confirmed via a real
    # Stripe sandbox call during the plan-change smoke test); `to_dict()` is
    # the real method, and it DOES recursively convert nested StripeObjects
    # (list items, nested resources) into plain dicts despite the
    # non-"recursive" name. `dict(value)` is kept only as the fallback for
    # already-dict test doubles, which have neither method.
    return value.to_dict() if hasattr(value, "to_dict") else dict(value)
def _iso(epoch): return datetime.fromtimestamp(epoch, timezone.utc).isoformat() if epoch else None
def _period_end(subscription, item):
    """Some Stripe API versions report the period on the subscription item, not
    the subscription itself. Mirrors `subscription_row`'s existing fallback."""
    return subscription.get("current_period_end") or (item or {}).get("current_period_end")
def _cancels_at_period_end(subscription, item):
    """Normalize Stripe's two equivalent end-of-paid-period cancellation shapes.

    Standard Billing commonly reports ``cancel_at_period_end=true``. Managed
    Payments can instead leave that boolean false while setting ``cancel_at``
    to the exact current-period end. Treat only that exact timestamp match as
    an end-of-period cancellation; an arbitrary future ``cancel_at`` date must
    not be mislabeled as period-end cancellation.
    """
    if subscription.get("cancel_at_period_end"):
        return True
    cancel_at = subscription.get("cancel_at")
    period_end = _period_end(subscription, item)
    if cancel_at is None or period_end is None:
        return False
    try:
        return int(cancel_at) == int(period_end)
    except (TypeError, ValueError):
        return cancel_at == period_end
def _subscription_id_from_event_object(obj):
    """Normalize Checkout and Dahlia-era Invoice subscription references."""
    reference = obj.get("subscription")
    if not reference:
        reference = (((obj.get("parent") or {}).get("subscription_details") or {}).get("subscription"))
    if isinstance(reference, dict): reference = reference.get("id")
    return reference

class BillingService:
    _PLAN_CHANGE_TOKEN_TTL_SECONDS = 300

    def __init__(self, repository=None, provider=None, offers=None):
        self.repository = repository or BillingRepository()
        self.provider = provider or StripeProvider()
        self.offers = offers or OFFERS

    def _signing_secret(self):
        secret = os.environ.get("BILLING_PLAN_CHANGE_SIGNING_SECRET")
        if not secret:
            raise BillingNotConfigured("BILLING_PLAN_CHANGE_SIGNING_SECRET is not configured")
        return secret

    def _resolve_current_subscription(self, user_id):
        """Stripe is the sole authority for current price/item/period/schedule.

        Local `billing_subscriptions` rows are consulted only to establish
        ownership (which Stripe subscription belongs to this user) and to
        fail closed on duplicate active local rows; every other field is
        read fresh from Stripe on each call.
        """
        customer = self.repository.find_customer(user_id)
        if not customer:
            raise BillingOwnershipError("No trusted Stripe customer mapping for this user")

        local_rows = self.repository.find_subscriptions(user_id)
        if has_duplicate_active_subscriptions(local_rows):
            raise UnsupportedSubscriptionShape("User has multiple active subscriptions")

        owned_row = next(
            (row for row in local_rows if row.get("status") in ("trialing", "active", "past_due")), None
        )
        if not owned_row:
            raise BillingOwnershipError("No active subscription ownership found for this user")
        subscription_id = owned_row["provider_subscription_id"]

        # `_plain(...)` mirrors reconcile_subscription's existing convention: real
        # stripe-python 15.4.0 responses are StripeObject instances that support
        # attribute access but not `.get(...)`/subscripting, so every fresh Stripe
        # response must be flattened to a plain dict before this module touches it.
        subscription = _plain(self.provider.retrieve_subscription(
            subscription_id, expand=["items.data.price", "schedule", "latest_invoice.payment_intent"]
        ))

        subscription_customer_id = subscription.get("customer")
        if isinstance(subscription_customer_id, dict):
            subscription_customer_id = subscription_customer_id.get("id")
        if subscription_customer_id and subscription_customer_id != customer.get("provider_customer_id"):
            raise BillingOwnershipError("Stripe subscription customer does not match trusted customer mapping")

        items = (subscription.get("items") or {}).get("data") or []
        recurring = [entry for entry in items if (entry.get("price") or {}).get("id")]
        if len(recurring) != 1:
            raise UnsupportedSubscriptionShape("Subscription must have exactly one recurring item")
        item = recurring[0]
        current_price_id = item["price"]["id"]

        current_offer = offer_for_price_id(current_price_id, self.offers)
        if current_offer is None:
            raise UnmappedStripePrice(f"Current Stripe Price {current_price_id} is not mapped")

        return customer, subscription, item, current_offer

    def preview_plan_change(self, *, user_id, offer_key):
        customer, subscription, item, current_offer = self._resolve_current_subscription(user_id)

        target_offer = self.offers.get(offer_key)
        # Plan-change is decoupled from BILLING_CHECKOUT_ENABLED: an existing
        # subscriber changing their already-active subscription's plan is a
        # different action from a new Checkout purchase, so this checks the
        # offer is real and priced (`is_priced`), not whether new-purchase
        # checkout is currently enabled (`purchasable`).
        if target_offer is None or not target_offer.is_priced:
            raise PlanChangeNotAllowed(f"Offer {offer_key} is not available")

        action = classify_transition(
            current_offer.plan,
            target_offer.plan,
            current_interval=current_offer.billing_interval,
            target_interval=target_offer.billing_interval,
        )
        subscription_id = subscription["id"]
        current_period_end = _period_end(subscription, item)

        if action == PlanChangeAction.UPGRADE_NOW:
            proration_date = int(time.time())
            preview = self.provider.preview_subscription_update(
                subscription_id=subscription_id,
                subscription_item_id=item["id"],
                target_price_id=target_offer.provider_price_id,
                proration_date=proration_date,
            )
            dto = build_upgrade_preview_dto(
                from_plan=current_offer.plan,
                to_plan=target_offer.plan,
                from_offer_key=current_offer.offer_key,
                to_offer_key=target_offer.offer_key,
                currency=preview["currency"],
                amount_due_now=preview["amount_due"],
                effective_at=proration_date,
                next_renewal_at=current_period_end,
            )
            expires_at = proration_date + self._PLAN_CHANGE_TOKEN_TTL_SECONDS
            visible = {
                "version": 1,
                "action": dto["action"],
                "prorationDate": proration_date,
                "amountDueNow": dto["amountDueNow"],
                "currency": dto["currency"],
                "expiresAt": expires_at,
            }
            hidden = {
                "userId": user_id,
                "subscriptionId": subscription_id,
                "subscriptionItemId": item["id"],
                "currentPriceId": item["price"]["id"],
                "targetPriceId": target_offer.provider_price_id,
                "currentPeriodEnd": current_period_end,
                "offerKey": target_offer.offer_key,
            }
            token = sign_preview_token(secret=self._signing_secret(), visible=visible, hidden=hidden)
            dto["previewToken"] = token
            return dto

        return build_downgrade_preview_dto(
            from_plan=current_offer.plan,
            to_plan=target_offer.plan,
            from_offer_key=current_offer.offer_key,
            to_offer_key=target_offer.offer_key,
            current_period_end=current_period_end,
            action=action,
        )

    def confirm_plan_change(self, *, user_id, offer_key, preview_token):
        customer, subscription, item, current_offer = self._resolve_current_subscription(user_id)

        target_offer = self.offers.get(offer_key)
        # Plan-change is decoupled from BILLING_CHECKOUT_ENABLED: see the
        # matching comment in preview_plan_change above.
        if target_offer is None or not target_offer.is_priced:
            raise PlanChangeNotAllowed(f"Offer {offer_key} is not available")

        action = classify_transition(
            current_offer.plan,
            target_offer.plan,
            current_interval=current_offer.billing_interval,
            target_interval=target_offer.billing_interval,
        )
        subscription_id = subscription["id"]
        current_period_end = _period_end(subscription, item)

        if action == PlanChangeAction.UPGRADE_NOW:
            if not preview_token:
                raise PlanChangeNotAllowed("previewToken is required to confirm an upgrade")

            hidden = {
                "userId": user_id,
                "subscriptionId": subscription_id,
                "subscriptionItemId": item["id"],
                "currentPriceId": item["price"]["id"],
                "targetPriceId": target_offer.provider_price_id,
                "currentPeriodEnd": current_period_end,
                "offerKey": target_offer.offer_key,
            }
            visible = verify_preview_token(preview_token, secret=self._signing_secret(), hidden=hidden)
            proration_date = visible["prorationDate"]

            fresh_preview = self.provider.preview_subscription_update(
                subscription_id=subscription_id,
                subscription_item_id=item["id"],
                target_price_id=target_offer.provider_price_id,
                proration_date=proration_date,
            )
            if fresh_preview["amount_due"] != visible["amountDueNow"] or fresh_preview["currency"] != visible["currency"]:
                raise PlanChangePreviewStale("Price changed since preview; please re-preview")

            idempotency_key = upgrade_idempotency_key(
                subscription_id, current_offer.provider_price_id, target_offer.provider_price_id, proration_date
            )
            result = self.provider.update_subscription_item(
                subscription_id=subscription_id,
                subscription_item_id=item["id"],
                target_price_id=target_offer.provider_price_id,
                proration_date=proration_date,
                idempotency_key=idempotency_key,
            )
            return {"action": PlanChangeAction.UPGRADE_NOW.value, "paymentResult": result["payment_result"]}

        idempotency_key = downgrade_idempotency_key(
            subscription_id, current_offer.provider_price_id, target_offer.provider_price_id, current_period_end
        )
        self.provider.create_downgrade_schedule(
            subscription_id=subscription_id,
            target_price_id=target_offer.provider_price_id,
            current_period_end=current_period_end,
            idempotency_key=idempotency_key,
        )
        return {
            "action": action.value,
            "pendingChangeEffectiveAt": current_period_end,
        }

    def cancel_scheduled_plan_change(self, *, user_id):
        customer, subscription, item, current_offer = self._resolve_current_subscription(user_id)
        schedule = subscription.get("schedule")
        classification = classify_schedule(
            schedule,
            current_price_id=current_offer.provider_price_id,
            current_period_end=_period_end(subscription, item),
            offers=self.offers,
        )
        if classification["state"] != "scheduled":
            raise PlanChangeNotAllowed("No recognized scheduled plan change to cancel")

        self.provider.release_schedule(schedule_id=schedule["id"])
        return {"cancelled": True}

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
        item = recurring[0] if len(recurring) == 1 else None
        product_id = price.get("product")
        if isinstance(product_id, dict): product_id = product_id.get("id")
        return {"user_id": customer["user_id"], "billing_customer_id": customer["id"], "provider": "stripe",
            "provider_subscription_id": subscription["id"], "provider_product_id": product_id,
            "provider_price_id": price.get("id"), "offer_key": offer.offer_key if offer else None,
            "plan": offer.plan if offer else None, "status": subscription.get("status") or "unknown",
            "current_period_start": _iso(subscription.get("current_period_start") or (item.get("current_period_start") if item else None)),
            "current_period_end": _iso(_period_end(subscription, item)),
            "cancel_at_period_end": _cancels_at_period_end(subscription, item),
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
        public_offers = [{"offerKey": offer.offer_key, "plan": offer.plan,
                          "billingInterval": offer.billing_interval,
                          "unitAmount": offer.unit_amount_minor, "currency": offer.currency,
                          "purchasable": offer.purchasable}
                         for offer in self.offers.values()]
        base = {"effectivePlan": plan, "billingPlan": billing.get("plan") if billing else None,
            "billingManaged": bool(customer and billing), "accessManagedByIndex": bool(manual),
            "subscriptionStatus": billing.get("status") if billing else None,
            "offerKey": billing.get("offer_key") if billing else None,
            "cancelAtPeriodEnd": bool(billing and billing.get("cancel_at_period_end")),
            "currentPeriodEnd": billing.get("current_period_end") if billing else None,
            "billingConfigured": bool(purchasable), "purchasableOfferKeys": purchasable,
            "offers": public_offers}

        pending = {"pendingChangeState": "none", "pendingPlan": None, "pendingOfferKey": None, "pendingChangeEffectiveAt": None}
        if base.get("billingManaged"):
            try:
                _, subscription, item, current_offer = self._resolve_current_subscription(user_id)
                # This best-effort Stripe lookup already exists for pending plan
                # changes. Reuse the same authoritative snapshot for billing
                # presentation fields that do not grant or revoke entitlement,
                # so a delayed/stale webhook projection cannot tell a customer
                # their subscription will renew after Stripe has scheduled it
                # to end at the paid-period boundary.
                live_period_end = _period_end(subscription, item)
                base["cancelAtPeriodEnd"] = _cancels_at_period_end(subscription, item)
                if live_period_end:
                    base["currentPeriodEnd"] = _iso(live_period_end)
                schedule = subscription.get("schedule")
                classification = classify_schedule(
                    schedule,
                    current_price_id=current_offer.provider_price_id,
                    current_period_end=live_period_end,
                    offers=self.offers,
                )
                pending = {
                    "pendingChangeState": classification["state"],
                    "pendingPlan": classification["pendingPlan"],
                    "pendingOfferKey": classification["pendingOfferKey"],
                    "pendingChangeEffectiveAt": classification["pendingChangeEffectiveAt"],
                }
            except Exception:
                logger.warning("billing.pending_change.lookup_failed user_id=%s", user_id, exc_info=True)
                pending = {"pendingChangeState": "unknown", "pendingPlan": None, "pendingOfferKey": None, "pendingChangeEffectiveAt": None}

        return {**base, **pending}

    def public_catalog(self):
        return {"offers": [{"offerKey": offer.offer_key, "plan": offer.plan,
            "billingInterval": offer.billing_interval, "unitAmount": offer.unit_amount_minor,
            "currency": offer.currency, "purchasable": offer.purchasable}
            for offer in self.offers.values()],
            "billingConfigured": any(offer.purchasable for offer in self.offers.values())}

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
