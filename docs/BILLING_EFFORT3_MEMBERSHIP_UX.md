# Billing Effort 3 — Membership UX

Status: `PRICING_NOT_CONFIGURED` · `PURCHASABLE_OFFERS=0` · `PUBLIC_CHECKOUT_DISABLED`

## Account architecture

Membership & Billing is an extracted section within `/account-settings`, below the existing independent Profile and Privacy/Preferences form. Billing loading or provider errors do not disable profile editing. Components live under `frontend/components/account`; transactional confirmation UI lives under `frontend/components/billing`.

## Frontend billing client and proxies

`billingClient.mjs` owns `getBillingStatus()`, `createCheckoutSession(offerKey)`, and `createCustomerPortalSession()`. The Checkout request serializes only `offerKey`. Components never submit plan, amount, Price, customer, user, or redirect authority.

Next proxy routes are:

- `GET /api/billing/me`
- `POST /api/billing/checkout-session`
- `POST /api/billing/customer-portal`

They forward only the canonical Cookie/Authorization context to the Python backend, use `cache: no-store`, and return `Cache-Control: no-store` with `Vary: Cookie, Authorization`. Safe backend status codes and error codes are preserved; service credentials are never present in the browser.

## Billing status DTO

```text
effectivePlan           actual feature access: null/basic, plus, premium
billingPlan             mapped Stripe subscription plan, if any
billingManaged          mapped Stripe customer/subscription relationship exists
accessManagedByIndex    independent inDex-managed access exists (boolean only)
subscriptionStatus      normalized provider lifecycle state or null
offerKey                canonical billed offer or null
cancelAtPeriodEnd       scheduled end flag
currentPeriodEnd        ISO timestamp for presentation or null
billingConfigured       at least one offer is purchasable
purchasableOfferKeys    canonical configured offer identities
```

No Stripe IDs, metadata, payment details, manual reasons, event history, or provider payloads are exposed.

## Membership presentation

- Basic: Basic access, Plus/Premium descriptions, no Manage Subscription, configuration-driven unavailable CTAs.
- Manual Plus/Premium: effective paid plan plus “Access managed by inDex”; no renewal or Stripe-subscription claim.
- Active Stripe: effective plan, Active, readable renewal date, Manage Subscription.
- Scheduled cancellation: remains entitled and says scheduled to end/active through the period date.
- Trialing: Trial with the available end date.
- Past due: membership remains active during recovery with payment-update guidance.
- Unpaid/canceled/paused/incomplete: no false active-paid claim; current effective access remains separately authoritative.
- Mixed provenance: current effective plan and the lower Stripe billing plan are distinguished so billing language is not misleading.
- Unknown status: neutral “Billing status unavailable.”

The plan language remains Basic, Index Plus, and Index Premium. Plus describes deeper numerical intelligence; Premium describes the additional decision layer. No capability packaging changed.

## Customer Portal

`POST /billing/customer-portal` authenticates the app user, loads the persisted customer mapping, derives `FRONTEND_BASE_URL/account-settings?section=billing`, and calls the Stripe adapter. It accepts no customer, user, subscription, or return URL input and returns only `{ "portalUrl": "..." }`. Sessions are created only after an intentional button click, are never cached, and are never persisted.

Before launch, Stripe Dashboard Portal configuration still requires approved branding, payment-method behavior, invoice history, cancellation timing, allowed Products/Prices, plan switching, and proration policy. This effort chooses none of those commercial policies.

## Checkout orchestration

Only non-Stripe-managed accounts can receive selectable configured offers. Existing managed subscribers see Customer Portal management instead, preventing a second Checkout subscription. A click makes one guarded request, disables actions, and top-level navigates to the returned Stripe-hosted URL. Zero configured offers means no functional checkout button and no render-time Checkout request.

## Success and cancel

`/billing/success` is noindex and ignores query strings. It polls `/api/billing/me` a bounded five times, stops on verified provisionable billing state, refreshes canonical AuthContext from `/api/auth/me`, and otherwise presents neutral pending confirmation. Status-fetch failure is never called payment failure.

`/billing/cancel` is noindex and states only that Checkout was canceled and membership was unchanged. Neither route mutates entitlement.

## Auth entitlement refresh

Account billing load and confirmed Checkout call the existing `AuthContext.refreshUser()`. That function fetches the verified current profile, replaces shared user state, increments the auth revision, and refreshes entitlement-aware Server Components. No local optimistic plan mutation or logout/login is required.

## Database verification

No Effort 3 schema change was required. Effort 1/2 migrations remain unapplied locally because Docker and Podman are unavailable. Applying migrations, testing RLS/grants/function execution, and running database-backed lifecycle tests remains an explicit Effort 4 launch blocker.

## Effort 4 readiness

Effort 4 should own database-backed migration/RLS validation, webhook/ledger concurrency hardening, reconciliation/drift jobs, provider-mode/configuration validation, operational telemetry and alerting, rate limits/abuse review for billing endpoints, deployment runbooks, and production failure recovery. Pricing, Portal switching/proration policy, and public launch remain deferred to Effort 5.
