"""The only module that talks directly to the Stripe Python SDK."""

from __future__ import annotations

import os
import uuid
import stripe

from backend.domain.billing.errors import BillingNotConfigured, BillingProviderError, InvalidWebhookSignature, PlanChangeNotAllowed, StripeCustomerMissing


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
            params = {"expand": expand} if expand else None
            return self._client().v1.subscriptions.retrieve(subscription_id, params)
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
                    # Without this, Stripe returns `latest_invoice` as a bare
                    # invoice-ID string, not the expanded object. Confirmed
                    # against a real Stripe sandbox upgrade during the full
                    # application E2E test: `_normalize_payment_result` then
                    # reads `.status`/`.payment_intent` off that string (both
                    # silently None via `_field`'s getattr fallback) and
                    # misreports "requires_action" even when the invoice was
                    # paid synchronously and successfully.
                    "expand": ["latest_invoice.payment_intent"],
                },
                options={"idempotency_key": idempotency_key},
            )
            return {"payment_result": _normalize_payment_result(subscription), "subscription": subscription}
        except BillingNotConfigured: raise
        except Exception as exc: raise BillingProviderError("Stripe subscription item update failed") from exc

    def create_downgrade_schedule(self, *, subscription_id: str, target_price_id: str, current_period_end: int, idempotency_key: str) -> dict:
        try:
            # A purely input-derived idempotency_key (subscription/prices/
            # period_end -- see plan_change.downgrade_idempotency_key) is
            # stable for an entire billing period. Confirmed against a real
            # Stripe sandbox: Stripe caches the FIRST response for a given
            # idempotency key on this create endpoint for its full retention
            # window, so a legitimate second scheduling attempt within the
            # same period (e.g. schedule -> cancel -> schedule again) would
            # replay the first, now-released/stale schedule and fail on the
            # phase-2 update rather than creating a fresh one. A per-call
            # nonce keeps genuine network-level duplicate submissions from
            # a single attempt safe (Stripe still dedupes those, since a
            # true duplicate request is retried by application/HTTP-layer
            # logic within the same call, not by regenerating this method's
            # arguments), while a real subsequent user action always gets a
            # fresh key. Cross-schedule double-submission (e.g. a double
            # click) is independently guarded by Stripe itself: `create`
            # with `from_subscription` on a subscription that already has an
            # active schedule attached is rejected by Stripe regardless of
            # idempotency key.
            schedule = self._client().v1.subscription_schedules.create(
                {"from_subscription": subscription_id},
                options={"idempotency_key": f"{idempotency_key}:{uuid.uuid4().hex}"},
            )
        except BillingNotConfigured: raise
        except Exception as exc: raise BillingProviderError("Stripe downgrade schedule creation failed") from exc

        schedule_id = _field(schedule, "id")
        try:
            phases = _field(schedule, "phases")
            current_phase = phases[0]
            updated_phases = [
                _writable_phase_payload(current_phase, end_date=current_period_end),
                {"items": [{"price": target_price_id}], "start_date": current_period_end},
            ]
            return self._client().v1.subscription_schedules.update(
                schedule_id,
                {"end_behavior": "release", "phases": updated_phases},
                # Stripe scopes idempotency keys per endpoint -- the same key
                # cannot be reused across the `create` call above (POST
                # /v1/subscription_schedules) and this `update` call (POST
                # /v1/subscription_schedules/{id}); Stripe rejects that with
                # IdempotencyError. Scoped to this specific schedule's own id
                # (globally unique per successful create), so it's naturally
                # collision-free across schedules while still stable for a
                # retry of this exact schedule's phase-2 update.
                options={"idempotency_key": f"{schedule_id}:phase2"},
            )
        except BillingNotConfigured:
            raise
        except PlanChangeNotAllowed:
            # The current phase carries billing-affecting state (e.g. a
            # discount) that _writable_phase_payload could not confidently
            # and losslessly represent through the writable phase schema.
            # Fail closed: release the schedule the `create` call above
            # already attached, so the subscription is left exactly as it
            # was found, and let the caller see this as a rejected plan
            # change rather than a generic provider error.
            try:
                self._client().v1.subscription_schedules.release(schedule_id)
            except Exception:
                pass
            raise
        except Exception as exc:
            # The schedule from the `create` call above already exists on the
            # subscription. If the phase-2 `update` fails, release it so we
            # don't leave an orphaned single-phase schedule behind -- that
            # shape blocks all future plan-change retries and cannot be
            # cancelled through cancel_scheduled_plan_change (which only
            # recognizes the full 2-phase shape).
            try:
                self._client().v1.subscription_schedules.release(schedule_id)
            except Exception:
                pass
            raise BillingProviderError("Stripe downgrade schedule creation failed") from exc

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


def _resource_id(value):
    """Extract a resource id from a plain id string, a dict-shaped expanded
    resource, or a StripeObject-shaped expanded resource. Returns None if the
    value cannot be confidently reduced to an id."""
    if value is None:
        return None
    if isinstance(value, str):
        return value
    resolved = _field(value, "id")
    return resolved if isinstance(resolved, str) else None


def _writable_phase_payload(phase, *, end_date) -> dict:
    """Project a schedule phase read back from `create` down to the
    documented-writable subset (stripe-python 15.4.0
    `SubscriptionScheduleUpdateParamsPhase`) before resubmitting it to
    `update`.

    The `create` response phase carries read-only/expanded fields (e.g. a
    fully expanded price object, computed proration fields) that a real
    `subscription_schedules.update` call rejects if resubmitted verbatim.
    Every field below is deliberately narrowed to what that write schema
    actually accepts. Billing-affecting state that IS present on the read
    phase but cannot be confidently and losslessly reduced to a valid write
    value raises `PlanChangeNotAllowed` -- the caller must fail the plan
    change closed rather than silently drop it.
    """
    items = _field(phase, "items") or []
    projected_items = []
    for item in items:
        price_id = _resource_id(_field(item, "price"))
        if price_id is None:
            raise PlanChangeNotAllowed(
                "Unable to safely represent the current subscription phase's price for a scheduled downgrade"
            )
        quantity = _field(item, "quantity", 1) or 1
        projected_items.append({"price": price_id, "quantity": quantity})

    payload = {
        "items": projected_items,
        "start_date": _field(phase, "start_date"),
        "end_date": end_date,
    }

    collection_method = _field(phase, "collection_method")
    if collection_method:
        if collection_method not in ("charge_automatically", "send_invoice"):
            raise PlanChangeNotAllowed(
                "Unsupported billing collection method on the current subscription phase"
            )
        payload["collection_method"] = collection_method

    application_fee_percent = _field(phase, "application_fee_percent")
    if application_fee_percent is not None:
        payload["application_fee_percent"] = application_fee_percent

    on_behalf_of_id = _resource_id(_field(phase, "on_behalf_of"))
    if _field(phase, "on_behalf_of") is not None and on_behalf_of_id is None:
        raise PlanChangeNotAllowed(
            "Unable to safely represent connected-account billing state for a scheduled downgrade"
        )
    if on_behalf_of_id:
        payload["on_behalf_of"] = on_behalf_of_id

    if _field(phase, "trial"):
        payload["trial"] = True
    trial_end = _field(phase, "trial_end")
    if trial_end:
        payload["trial_end"] = trial_end

    default_tax_rates = _field(phase, "default_tax_rates")
    if default_tax_rates:
        rate_ids = [_resource_id(rate) for rate in default_tax_rates]
        if any(rate_id is None for rate_id in rate_ids):
            raise PlanChangeNotAllowed(
                "Unable to safely represent the current subscription's tax rates for a scheduled downgrade"
            )
        payload["default_tax_rates"] = rate_ids

    discounts = _field(phase, "discounts")
    if discounts:
        discount_refs = []
        for discount in discounts:
            discount_id = _resource_id(discount)
            if discount_id is None:
                raise PlanChangeNotAllowed(
                    "Unable to safely represent an active discount for a scheduled downgrade"
                )
            discount_refs.append({"discount": discount_id})
        payload["discounts"] = discount_refs

    billing_thresholds = _field(phase, "billing_thresholds")
    if billing_thresholds:
        amount_gte = _field(billing_thresholds, "amount_gte")
        reset_anchor = _field(billing_thresholds, "reset_billing_cycle_anchor")
        if amount_gte is None and reset_anchor is None:
            raise PlanChangeNotAllowed(
                "Unable to safely represent billing thresholds on the current subscription phase for a scheduled downgrade"
            )
        projected_thresholds = {}
        if amount_gte is not None:
            projected_thresholds["amount_gte"] = amount_gte
        if reset_anchor is not None:
            projected_thresholds["reset_billing_cycle_anchor"] = reset_anchor
        payload["billing_thresholds"] = projected_thresholds

    automatic_tax = _field(phase, "automatic_tax")
    if automatic_tax:
        enabled = _field(automatic_tax, "enabled")
        if enabled is None:
            raise PlanChangeNotAllowed(
                "Unable to safely represent automatic tax settings on the current subscription phase for a scheduled downgrade"
            )
        projected_automatic_tax = {"enabled": bool(enabled)}
        liability = _field(automatic_tax, "liability")
        if liability:
            liability_type = _field(liability, "type")
            # `liability` is an optional override ("If set, ..." per the SDK's
            # own docs) -- Stripe applies its own default liability when it's
            # omitted. The read-side `type` can be "stripe" (confirmed against
            # a real Managed Payments subscription during the application E2E
            # test), which is Stripe's own computed default for that account,
            # not a merchant-settable value -- the write-side schema only
            # accepts "self"/"account" and real Stripe rejects "stripe" with
            # `Invalid phases[0][automatic_tax][liability][type]`. Only
            # resubmit `liability` when it's a genuine override value; a
            # non-writable type (like "stripe") is safely omitted rather than
            # failing the whole downgrade closed, since omitting it preserves
            # exactly the same effective behavior (Stripe's own default).
            if liability_type in ("self", "account"):
                projected_liability = {"type": liability_type}
                liability_id = _resource_id(_field(liability, "account"))
                if liability_id:
                    projected_liability["account"] = liability_id
                projected_automatic_tax["liability"] = projected_liability
        payload["automatic_tax"] = projected_automatic_tax

    invoice_settings = _field(phase, "invoice_settings")
    if invoice_settings:
        projected_invoice_settings = {}
        days_until_due = _field(invoice_settings, "days_until_due")
        if days_until_due is not None:
            projected_invoice_settings["days_until_due"] = days_until_due
        description = _field(invoice_settings, "description")
        if description:
            projected_invoice_settings["description"] = description
        footer = _field(invoice_settings, "footer")
        if footer:
            projected_invoice_settings["footer"] = footer
        account_tax_ids = _field(invoice_settings, "account_tax_ids")
        if account_tax_ids:
            tax_id_ids = [_resource_id(tax_id) for tax_id in account_tax_ids]
            if any(tax_id is None for tax_id in tax_id_ids):
                raise PlanChangeNotAllowed(
                    "Unable to safely represent invoice tax id settings for a scheduled downgrade"
                )
            projected_invoice_settings["account_tax_ids"] = tax_id_ids
        custom_fields = _field(invoice_settings, "custom_fields")
        if custom_fields:
            projected_custom_fields = []
            for custom_field in custom_fields:
                name = _field(custom_field, "name")
                value = _field(custom_field, "value")
                if not isinstance(name, str) or not isinstance(value, str):
                    raise PlanChangeNotAllowed(
                        "Unable to safely represent invoice custom fields for a scheduled downgrade"
                    )
                projected_custom_fields.append({"name": name, "value": value})
            projected_invoice_settings["custom_fields"] = projected_custom_fields
        issuer = _field(invoice_settings, "issuer")
        if issuer:
            issuer_type = _field(issuer, "type")
            # Same "stripe" read-only default as automatic_tax.liability above
            # (confirmed against the same real Managed Payments subscription:
            # `Invalid phases[0][invoice_settings][issuer][type]: must be one
            # of self or account`) -- `issuer` is itself an optional override
            # (NotRequired) within invoice_settings, so a non-writable type is
            # safely omitted rather than failing the downgrade closed.
            if issuer_type in ("self", "account"):
                projected_issuer = {"type": issuer_type}
                issuer_account_id = _resource_id(_field(issuer, "account"))
                if issuer_account_id:
                    projected_issuer["account"] = issuer_account_id
                projected_invoice_settings["issuer"] = projected_issuer
        if projected_invoice_settings:
            payload["invoice_settings"] = projected_invoice_settings

    return payload


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
