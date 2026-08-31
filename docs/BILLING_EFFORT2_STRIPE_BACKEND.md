# Billing Effort 2 — Stripe Backend

Status: `PRICING_NOT_CONFIGURED` · `NO_REAL_STRIPE_PRICE_IDS_CREATED` · `PUBLIC_CHECKOUT_NOT_ENABLED`

## Architecture

Verified application authentication produces an immutable user ID. The billing service resolves a server-owned offer, reuses or creates the uniquely mapped Stripe Customer, and creates Stripe-hosted subscription Checkout. Checkout completion never grants access. A raw-body, signature-verified webhook claims an idempotency ledger entry, retrieves current authoritative Stripe subscription state, persists its normalized audit record, then invokes one transactional database function to merge billing and manual provenance into `users.index_plan`. Existing feature authorization remains Stripe-blind.

## Provider boundary

- `backend/domain/billing/providers/stripe_provider.py`: the only Stripe SDK caller; customer, Checkout, subscription retrieval, and signature verification.
- `backend/domain/billing/catalog.py`: environment-backed offer/Price mapping and reverse Price lookup.
- `backend/db/services/billing_service.py`: customer orchestration, reconciliation, webhook dispatch, and safe status DTO.
- `backend/db/repositories/billing_repository.py`: privileged persistence, retryable event claims, and entitlement RPC invocation.
- `backend/domain/billing/policy.py`: the single status and effective-plan policy used outside the database transaction.

The SDK is pinned to `stripe==15.4.0` (Dahlia API family). Version-sensitive invoice parent subscription references and subscription-item period timestamps are normalized inside the billing boundary; feature code never depends on Stripe object shapes.

## Checkout contract

`POST /billing/checkout-session` requires app authentication and accepts exactly `{ "offerKey": "..." }`; extra fields are rejected. The response is `{ "checkoutUrl": "..." }`. Unknown offers return `BILLING_OFFER_UNKNOWN`; disabled/unpriced offers return `BILLING_OFFER_NOT_CONFIGURED`; provider failures return a controlled 503. Customer, Price, user, plan, success URL, and cancel URL are all server-owned. Checkout uses `mode=subscription`, one recurring Price, trusted metadata, and Stripe-hosted UI.

## Webhook contract

`POST /billing/stripe/webhook` is public but requires `Stripe-Signature`. FastAPI reads `await request.body()` and passes unchanged bytes to `stripe.Webhook.construct_event`. Missing/invalid signatures return 400 before mutation. Processing failures return 503 so Stripe retries. No unsigned bypass exists.

Events reconciled: `checkout.session.completed`; `customer.subscription.created`, `.updated`, `.deleted`, `.paused`, `.resumed`; `invoice.paid`, `.payment_failed`, `.payment_action_required`. Events are signals: the service retrieves the current subscription instead of trusting delivery order or the event snapshot.

## Idempotency and retry

Ledger state is `processing`, `processed`, or `failed` (with Effort 1's `received` retained for compatibility), plus attempt count/start/update timestamps. New events are claimed; processed duplicates succeed; failed events retry; stale processing claims recover after five minutes; active claims return retryable failure. Reconciliation upserts on provider subscription ID and recomputes from all trusted persisted rows, making replay safe. A crash after reconciliation but before ledger completion repeats an idempotent upsert/RPC rather than losing the event.

## Subscription policy

| Stripe status | Entitlement |
|---|---|
| `trialing` | mapped plan |
| `active` | mapped plan |
| `past_due` | mapped plan during Stripe payment recovery |
| `incomplete` | none |
| `incomplete_expired` | none |
| `unpaid` | none |
| `canceled` | none |
| `paused` | none |
| unknown | none |

`cancel_at_period_end=true` does not revoke an otherwise provisionable subscription. Premium outranks Plus across multiple provisionable rows and duplicate-active state is logged.

## Price and identity authority

Price variables are `STRIPE_PRICE_PLUS_MONTHLY`, `STRIPE_PRICE_PLUS_ANNUAL`, `STRIPE_PRICE_PREMIUM_MONTHLY`, and `STRIPE_PRICE_PREMIUM_ANNUAL`. Unset means disabled. Exactly one subscription item must map to exactly one configured offer. Unknown Prices and multi-item subscriptions remain auditable with null plan and cannot grant access. Metadata and email never grant or transfer ownership; inbound ownership resolves only through `billing_customers.provider_customer_id`. Customer creation uses a stable per-user Stripe idempotency key plus database uniqueness.

## Effective entitlement and manual provenance

`billing_manual_entitlements` preserves pre-Stripe Plus/Premium values during migration and supports explicit comp/admin access. The policy is highest valid authorization: Premium beats Plus whether billing- or manually-derived. Removing billing therefore cannot erase an independent manual grant. `public.recompute_effective_index_plan(uuid)` executes the merge and `users.index_plan` update transactionally. Execute is revoked from PUBLIC, anon, and authenticated and granted only to `service_role`.

## Database and browser security

The additive Effort 2 migration makes plan/offer nullable for unmapped audit rows, adds mapping/reconciliation provenance, adds webhook attempt timestamps, creates the RLS-protected manual table, preserves existing paid profiles as manual provenance, and adds the restricted synchronization function. Billing tables remain unavailable to browser roles.

## Configuration and local testing

Backend-only variables: `STRIPE_SECRET_KEY`, `STRIPE_WEBHOOK_SECRET`, the four optional Price variables above, and trusted `FRONTEND_BASE_URL`. Production redirect origin must be HTTPS. Never use `NEXT_PUBLIC_` for these values. Test and live secrets/Prices must be configured together by deployment environment; no values are committed.

For local webhook delivery, run the current Stripe CLI authenticated to the intended sandbox account and forward to `http://localhost:8001/billing/stripe/webhook`. Put the CLI command's temporary `whsec_...` only in local `STRIPE_WEBHOOK_SECRET`. It differs from a Dashboard endpoint secret. Unit tests do not require Stripe CLI or network access.

## Validation limitation

The linked local Supabase stack could not start or apply migrations because neither Docker nor Podman is installed/available. Migration/RLS validation is therefore static and must be followed by `supabase start`, migration application, database tests, and advisors when local infrastructure is available. This is not reported as DB-backed success.

## Effort 3

Effort 3 owns Account Billing UI, Manage Subscription/Customer Portal, success/cancel presentation, frontend upgrade actions, and subscription-state messaging. Core Checkout, signature verification, reconciliation, status policy, provenance, and entitlement synchronization are complete here.
