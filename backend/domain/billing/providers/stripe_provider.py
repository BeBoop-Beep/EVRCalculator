"""The only module that talks directly to the Stripe Python SDK."""

from __future__ import annotations

import os
import stripe

from backend.domain.billing.errors import BillingNotConfigured, BillingProviderError, InvalidWebhookSignature, StripeCustomerMissing


class StripeProvider:
    def __init__(self, secret_key: str | None = None, webhook_secret: str | None = None):
        self.secret_key = (secret_key if secret_key is not None else os.getenv("STRIPE_SECRET_KEY", "")).strip()
        self.webhook_secret = (webhook_secret if webhook_secret is not None else os.getenv("STRIPE_WEBHOOK_SECRET", "")).strip()
        self.client = stripe.StripeClient(self.secret_key) if self.secret_key else None

    def _client(self):
        if self.client is None:
            raise BillingNotConfigured("STRIPE_SECRET_KEY is not configured")
        return self.client

    def create_customer(self, *, user_id: str, email: str | None, idempotency_key: str):
        try:
            params = {"metadata": {"index_user_id": user_id}}
            if email: params["email"] = email
            return self._client().v1.customers.create(params, options={"idempotency_key": idempotency_key})
        except BillingNotConfigured: raise
        except Exception as exc: raise BillingProviderError("Stripe customer creation failed") from exc

    def create_checkout_session(self, *, customer_id: str, price_id: str, user_id: str,
                                offer_key: str, plan: str, success_url: str, cancel_url: str):
        try:
            return self._client().v1.checkout.sessions.create({
                "mode": "subscription", "customer": customer_id,
                "line_items": [{"price": price_id, "quantity": 1}],
                "managed_payments": {"enabled": True},
                "allow_promotion_codes": False,
                "success_url": success_url, "cancel_url": cancel_url,
                "client_reference_id": user_id,
                "metadata": {"index_user_id": user_id, "offer_key": offer_key, "intended_plan": plan},
                # No trial fields: launch subscriptions begin billing immediately.
                "subscription_data": {"metadata": {"index_user_id": user_id, "offer_key": offer_key}},
            })
        except BillingNotConfigured: raise
        except Exception as exc: raise BillingProviderError("Stripe Checkout creation failed") from exc

    def retrieve_subscription(self, subscription_id: str, expand=None):
        try:
            kwargs = {}
            if expand:
                kwargs["expand"] = expand
            return self._client().v1.subscriptions.retrieve(subscription_id, **kwargs)
        except BillingNotConfigured: raise
        except Exception as exc: raise BillingProviderError("Stripe subscription retrieval failed") from exc

    def retrieve_customer(self, customer_id: str):
        try:
            return self._client().v1.customers.retrieve(customer_id)
        except BillingNotConfigured:
            raise
        except stripe.InvalidRequestError as exc:
            if getattr(exc, "code", None) == "resource_missing":
                raise StripeCustomerMissing("Persisted Stripe customer does not exist") from exc
            raise BillingProviderError("Stripe customer retrieval failed") from exc
        except Exception as exc:
            raise BillingProviderError("Stripe customer retrieval failed") from exc

    def list_customer_subscriptions(self, customer_id: str):
        try:
            result = self._client().v1.subscriptions.list({"customer": customer_id, "status": "all", "limit": 100})
            return list(getattr(result, "data", None) or _mapping_data(result))
        except BillingNotConfigured:
            raise
        except Exception as exc:
            raise BillingProviderError("Stripe subscription listing failed") from exc

    def create_customer_portal_session(self, *, customer_id: str, return_url: str):
        try:
            return self._client().v1.billing_portal.sessions.create({
                "customer": customer_id,
                "return_url": return_url,
            })
        except BillingNotConfigured: raise
        except Exception as exc: raise BillingProviderError("Stripe Customer Portal creation failed") from exc

    def preview_subscription_update(self, *, subscription_id: str, subscription_item_id: str, target_price_id: str, proration_date: int) -> dict:
        try:
            response = self._client().v1.invoices.create_preview({
                "subscription": subscription_id,
                "subscription_details": {
                    "items": [{"id": subscription_item_id, "price": target_price_id}],
                    "proration_behavior": "always_invoice",
                    "proration_date": proration_date,
                },
            })
            return {"amount_due": _field(response, "amount_due"), "currency": _field(response, "currency")}
        except BillingNotConfigured: raise
        except Exception as exc: raise BillingProviderError("Stripe invoice preview failed") from exc

    def update_subscription_item(self, *, subscription_id: str, subscription_item_id: str, target_price_id: str, proration_date: int, idempotency_key: str) -> dict:
        try:
            subscription = self._client().v1.subscriptions.update(
                subscription_id,
                {
                    "items": [{"id": subscription_item_id, "price": target_price_id}],
                    "proration_behavior": "always_invoice",
                    "proration_date": proration_date,
                    "payment_behavior": "pending_if_incomplete",
                },
                options={"idempotency_key": idempotency_key},
            )
            return {"payment_result": _normalize_payment_result(subscription), "subscription": subscription}
        except BillingNotConfigured: raise
        except Exception as exc: raise BillingProviderError("Stripe subscription item update failed") from exc

    def create_downgrade_schedule(self, *, subscription_id: str, target_price_id: str, current_period_end: int, idempotency_key: str) -> dict:
        try:
            schedule = self._client().v1.subscription_schedules.create(
                {"from_subscription": subscription_id},
                options={"idempotency_key": idempotency_key},
            )
            phases = _field(schedule, "phases")
            current_phase = phases[0]
            updated_phases = [
                current_phase,
                {"items": [{"price": target_price_id}], "start_date": current_period_end},
            ]
            return self._client().v1.subscription_schedules.update(
                _field(schedule, "id"),
                {"end_behavior": "release", "phases": updated_phases},
            )
        except BillingNotConfigured: raise
        except Exception as exc: raise BillingProviderError("Stripe downgrade schedule creation failed") from exc

    def release_schedule(self, *, schedule_id: str) -> None:
        try:
            self._client().v1.subscription_schedules.release(schedule_id)
        except BillingNotConfigured: raise
        except Exception as exc: raise BillingProviderError("Stripe schedule release failed") from exc

    def construct_event(self, raw_body: bytes, signature: str):
        if not self.webhook_secret:
            raise BillingNotConfigured("STRIPE_WEBHOOK_SECRET is not configured")
        try: return stripe.Webhook.construct_event(raw_body, signature, self.webhook_secret)
        except (ValueError, stripe.SignatureVerificationError) as exc:
            raise InvalidWebhookSignature("Invalid Stripe webhook signature") from exc


def _mapping_data(value):
    if hasattr(value, "to_dict_recursive"):
        return value.to_dict_recursive().get("data", [])
    if isinstance(value, dict):
        return value.get("data", [])
    return []


def _field(value, name, default=None):
    """Read `name` from either a dict-shaped or attribute-shaped (StripeObject) value.

    Real stripe-python 15.4.0 responses are StripeObject instances, which support
    attribute access (with AttributeError, not None, for a missing field) but do not
    implement `.get(...)`. Test doubles and webhook payloads are plain dicts. This
    helper works uniformly across both.
    """
    if value is None:
        return default
    if isinstance(value, dict):
        return value.get(name, default)
    return getattr(value, name, default)


def _normalize_payment_result(subscription) -> str:
    latest_invoice = _field(subscription, "latest_invoice")
    if not latest_invoice:
        return "succeeded"
    payment_intent = _field(latest_invoice, "payment_intent")
    if not payment_intent:
        invoice_status = _field(latest_invoice, "status")
        return "succeeded" if invoice_status == "paid" else "requires_action"
    status = _field(payment_intent, "status")
    if status == "succeeded":
        return "succeeded"
    if status in ("requires_action", "requires_source_action"):
        return "requires_action"
    return "failed"
