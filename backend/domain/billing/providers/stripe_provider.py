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
                "allow_promotion_codes": False,
                "automatic_tax": {"enabled": False},
                "success_url": success_url, "cancel_url": cancel_url,
                "client_reference_id": user_id,
                "metadata": {"index_user_id": user_id, "offer_key": offer_key, "intended_plan": plan},
                # No trial fields: launch subscriptions begin billing immediately.
                "subscription_data": {"metadata": {"index_user_id": user_id, "offer_key": offer_key}},
            })
        except BillingNotConfigured: raise
        except Exception as exc: raise BillingProviderError("Stripe Checkout creation failed") from exc

    def retrieve_subscription(self, subscription_id: str):
        try: return self._client().v1.subscriptions.retrieve(subscription_id)
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
