# First-Party Plan-Change (Plus ↔ Premium) — Design Spec

Status: approved (locked commercial contract + implementation contract from user)
Scope: existing-subscriber Plus ↔ Premium plan changes only. No checkout activation, no Stripe object creation, no Supabase mutation, no migrations.

## 1. Problem

Billing-managed subscribers today are routed to Stripe Customer Portal for any plan
change. That worked when Plus/Premium were price variants; it no longer works now
that Plus and Premium are **separate Stripe Products**, and Portal is not being used
for cross-tier switching. There is no first-party path for:

- Plus → Premium (should be immediate, prorated)
- Premium → Plus (should be deferred to period end, no refund)

## 2. Commercial contract (locked)

Hierarchy: `Basic < Plus < Premium`. Premium inherits Plus.

| offer_key | price | Stripe Price ID |
|---|---|---|
| plus_monthly | $9.99/mo | price_1UAjde7OgvEwKwH3KX9aBgkn |
| plus_annual | $79/yr | price_1UAje17OgvEwKwH3o1YXilS6 |
| premium_monthly | $24.99/mo | price_1UAjeB7OgvEwKwH3XPMtbxLr |
| premium_annual | $219/yr | price_1UAjeG7OgvEwKwH34utXH4ae |

Products: `prod_VB512R4VQEsqSs` (Plus), `prod_VB51m44RkfWC21` (Premium). Product ID
never determines entitlement — Price ID → `offer_key` → plan is the only chain, via
the existing `catalog.offer_for_price_id()`.

Stripe IDs stay server-side only (env-var backed catalog, as today). Never in browser code.

**In scope:** the 8 cross-tier transitions (Plus{monthly,annual} → Premium{monthly,annual}
and the reverse). **Out of scope:** same-tier interval changes (Plus monthly ↔ Plus
annual, Premium monthly ↔ Premium annual) — rejected by this feature, `PLAN_RANK`
must not accidentally treat them as valid cross-tier moves.

## 3. Module boundary

```
frontend PricingPageClient.jsx / billingPresentation.mjs / billingClient.mjs
        │ POST /billing/change-plan/{preview,confirm,cancel-scheduled}
        ▼
backend/api/main.py  (auth, request parsing, error→HTTP mapping — matches existing /billing/* routes)
        ▼
BillingService (I/O orchestrator — existing class, gains 3 methods)
        │                                   │
        ▼                                   ▼
StripeProvider (existing, gains methods)   plan_change.py (NEW, pure domain)
        │
        ▼
   Stripe API (sole SDK boundary)
```

- **`plan_change.py`** (new) — pure functions only: direction classification
  (`PlanChangeAction.UPGRADE_NOW` / `DOWNGRADE_AT_PERIOD_END`), schedule-shape
  classification (`none`/`scheduled`/`unknown`), DTO shaping, validation, error
  selection. No Stripe/Supabase/HTTP calls, no subscription retrieval, no
  persistence. Pure in the same sense `policy.py`/`catalog.py` already are.
- **`BillingService`** (existing, extended) — `preview_plan_change()`,
  `confirm_plan_change()`, `cancel_scheduled_plan_change()`. Does all I/O: fresh
  Stripe retrieval, calls into `StripeProvider`, calls into `plan_change.py` for
  decisions, shapes final response.
- **`StripeProvider`** — remains the only Stripe SDK touchpoint. New methods only;
  existing methods (`create_checkout_session`, `create_customer_portal_session`,
  etc.) untouched.
- **`BillingRepository`** — remains the only Supabase boundary. Not modified — this
  feature persists nothing new.

## 4. Stripe is authoritative for current state

Every preview/confirm/cancel call starts with a **fresh**
`stripe.Subscription.retrieve(subscription_id, expand=["items.data.price", "schedule", "latest_invoice.payment_intent"])`.
Local `billing_subscriptions` rows establish trusted *ownership* (which
subscription belongs to this user) and reconciliation history only — never current
Price/item/period/schedule state.

Authority chain: authenticated user → trusted local Stripe customer/subscription
relationship (ownership only) → fresh Stripe retrieve → exactly one recurring
item → current Price ID → `offer_for_price_id()` → current plan.

Fail closed (raise typed errors, no mutation) on: zero recurring items, multiple
recurring items, unmapped current Price, unknown customer ownership, duplicate
active local subscriptions (reuse existing `has_duplicate_active_subscriptions`),
unsupported subscription shape.

## 5. Errors

New: `PlanChangeNotAllowed` (wrong direction / same-tier-only / Basic user /
unmapped price / unrecognized existing schedule), `PlanChangePreviewStale` (amount
or currency changed between preview and confirm). Reused as-is, unmodified:
`BillingOwnershipError`, `UnsupportedSubscriptionShape`, `UnmappedStripePrice`.
`BillingSubscriptionAlreadyManaged` stays scoped to the original Checkout path —
not touched, not reused here.

## 6. API

```
POST /billing/change-plan/preview
  body: { "offerKey": "premium_monthly" }
POST /billing/change-plan/confirm
  body: { "offerKey": "premium_monthly", "previewToken": "..." }
POST /billing/change-plan/cancel-scheduled
  body: {}
```

Auth matches existing `/billing/*` routes exactly (same session/auth dependency as
`/billing/checkout-session`). Browser never supplies: user ID, Stripe customer ID,
subscription ID, subscription-item ID, Product ID, Price ID, current plan, amount,
currency, period end, effective date, or proration amount. All resolved
server-side from the authenticated session + fresh Stripe state.

## 7. Upgrade flow (Plus → Premium)

1. Fresh Stripe subscription retrieval.
2. Verify current mapped plan is Plus (else `PlanChangeNotAllowed`).
3. Resolve requested `offerKey` via server catalog.
4. Verify target mapped plan is Premium (else `PlanChangeNotAllowed` — this also
   rejects same-tier interval-only requests).
5. Take the subscription's one recurring item ID.
6. Generate one server-side `proration_date` (unix ts, `int(time.time())`).
7. Call Stripe's invoice-preview API (`stripe.Invoice.create_preview`, current
   SDK/API shape — verify exact method name against pinned `stripe==15.4.0`
   during implementation, do not assume the old `upcoming_invoice`/deprecated
   shape) with the proposed item price swap and that `proration_date`.
8. Return DTO with the previewed amount + a signed `previewToken`.
9. On confirm: verify token, **re-run the same invoice-preview call** with the
   token's committed `proration_date`, require amount/currency still match
   (else `PlanChangePreviewStale`, no mutation).
10. Perform `stripe.Subscription.modify(...)` with the item's price swapped,
    `proration_behavior="always_invoice"`, `proration_date` = the committed
    value, `payment_behavior="pending_if_incomplete"` (investigate exact
    stripe-python 15.4.0 response shape rather than assuming legacy
    `latest_invoice.payment_intent.status` structure — normalize whatever the
    SDK returns into the 3-state result below).
11. Entitlement change is never inferred from this call's return value —
    `users.index_plan` only changes via the existing webhook/reconciliation
    path (`customer.subscription.updated`), exactly as today.

Same-tier interval changes (Plus↔Plus, Premium↔Premium) are rejected at step 4 by
construction — target plan must differ from current plan, not just target offer
differ from current offer.

## 8. Normalized payment result

`preview_plan_change`/`confirm_plan_change` responses carry `paymentResult` (upgrade
confirm only): `"succeeded" | "requires_action" | "failed"`, derived by inspecting
the actual `stripe-python==15.4.0` invoice/payment-intent shape at implementation
time (no assumptions carried over from older API versions). On `requires_action` or
`failed`: Premium is never granted by this call; frontend copy directs the user to
Manage Billing → Customer Portal to fix their payment method. No custom
card-authentication (3DS) flow is built in this effort.

## 9. Preview token

Signed, short-lived (~5 min TTL), versioned HMAC token, env `BILLING_PLAN_CHANGE_SIGNING_SECRET`
(new, separate from `STRIPE_WEBHOOK_SECRET`/`STRIPE_SECRET_KEY`/any JWT secret).

Visible/committed payload: `version, action, prorationDate, amountDueNow, currency, expiresAt`.
Signature additionally binds hidden authoritative state: `userId, subscriptionId,
subscriptionItemId, currentPriceId, targetPriceId, currentPeriodEnd, offerKey`.
Constant-time comparison (`hmac.compare_digest`) for verification.

Confirm flow: authenticate → fresh Stripe retrieve → re-resolve current
item/Price/target Price → verify signature against **freshly-derived** hidden
fields (not the token's own claims) → verify expiry → re-run invoice preview with
the committed `proration_date` → require amount/currency match → only then mutate.
Any mismatch (tampered token, different user, stale Price, changed item, changed
period end, expired) fails closed with no mutation.

## 10. Idempotency

Upgrade: `f"planchange:{subscription_id}:{current_price_id}:{target_price_id}:{proration_date}"`.
Downgrade: `f"plandowngrade:{subscription_id}:{current_price_id}:{target_price_id}:{current_period_end}"`.
Passed as Stripe idempotency key using the same convention `StripeProvider`
already uses elsewhere. Repeated confirm of the same transition must not create
duplicate invoices/subscriptions/schedules — verified by test.

## 11. Downgrade flow (Premium → Plus)

Preview DTO: `{action: "downgrade_at_period_end", fromPlan: "premium", toPlan: "plus", fromOfferKey, toOfferKey, amountDueNow: 0, effectiveAt: currentPeriodEnd, currentPlanUntil: currentPeriodEnd}`.
No manual proration/refund math. No early entitlement change.

Confirm: **`stripe.SubscriptionSchedule.create(from_subscription=subscription_id)`**
— Stripe generates phase 1 (current Premium configuration) from live state; phase
1 is never hand-reconstructed from the Price ID, preserving whatever else Stripe
carries (discounts, billing/payment settings). Append phase 2:
`{price: target_plus_price_id, start_date: current_period_end}` (target resolved
via server catalog from the confirmed `offerKey`). The subscription must remain
active/renewing after the Plus phase — no cancel-after phase, no end_behavior that
terminates the membership. Exactly one subscription relationship exists throughout;
no new Checkout, no local timer/cron.

## 12. Pending-change state classification

`pendingChangeState`: `"none" | "scheduled" | "unknown"`, computed live on every
`billing_status()` call (no persistence):

- No `subscription.schedule` present → `none`.
- Schedule present and its phase shape exactly matches the known 2-phase
  index-owned downgrade pattern (phase 1 = current Price through `currentPeriodEnd`,
  phase 2 = a canonical Plus offer starting at that boundary) → `scheduled`;
  include `pendingPlan`, `pendingOfferKey`, `pendingChangeEffectiveAt`.
- Schedule present but shape doesn't match (foreign/manual schedule, wrong phase
  count, unmapped phase-2 price, already transitioned) → `unknown`; omit the
  `pending*` fields. Confirm/cancel must never touch an `unknown` schedule.
- Live Stripe enrichment unavailable (retrieval error) → `pendingChangeState =
  "unknown"`, but `effectivePlan`/`billingPlan`/existing fields still come from
  local reconciliation, unaffected. A Stripe outage must never downgrade a user's
  effective entitlement.

## 13. Cancel scheduled downgrade

`POST /billing/change-plan/cancel-scheduled` — browser supplies nothing. Server:
fresh Stripe retrieve → locate schedule → verify current Price is still Premium,
future phase is the expected canonical Plus offer, shape is exactly the
known-good 2-phase downgrade pattern, future phase hasn't started yet → release
the schedule (`stripe.SubscriptionSchedule.release`, reverting to a plain
subscription) → Premium continues normally. Any deviation (already transitioned,
unknown shape, multi-phase, manually modified, unmapped) fails closed, no
mutation, underlying subscription is never canceled.

## 14. Billing status DTO extension

Additive only: `pendingChangeState`, `pendingPlan`, `pendingOfferKey`,
`pendingChangeEffectiveAt`. All existing fields (`effectivePlan`, `billingPlan`,
`billingManaged`, `accessManagedByIndex`, `subscriptionStatus`, `offerKey`,
`cancelAtPeriodEnd`, `currentPeriodEnd`, `billingConfigured`,
`purchasableOfferKeys`, `offers`) unchanged. If Stripe enrichment fails, the
existing fields remain usable from local reconciliation; only `pendingChangeState`
becomes `"unknown"`.

## 15. No migration

Nothing new is persisted in Supabase. Pending-schedule state is Stripe-owned and
derived live. `users.index_plan` is never written early — only via existing
reconciliation once Stripe actually transitions the subscription
(`customer.subscription.updated` → new Price maps to Plus → existing reconciler
updates `index_plan` exactly as it does today for any other Price change).

## 16. Webhooks

No new webhook events. The existing `customer.subscription.updated` handler
already re-derives `offer_key`/plan from `items.data[0].price.id` on every
reconcile with no special-casing — so when a schedule's phase 2 actually fires,
Stripe's `subscription.updated` event flows through the existing path unchanged
and grants Plus correctly. Schedule-specific events are not needed for
correctness, only (optionally) for faster pending-state UX — and live schedule
inspection in `billing_status()` already covers that, so none are added.

## 17. Frontend UX

`PricingPageClient.jsx` `PaidCard`: for a billing-managed subscriber, a card whose
plan differs from `effectivePlan` (and isn't Basic) no longer routes to Portal.
Instead:
- Plus user, Premium card → "Upgrade to Index Premium" → in-page preview step →
  "Due now: $X.XX / begins immediately after successful payment / Next renewal:
  \<date> / Confirm upgrade".
- Premium user, Plus card → "Change to Index Plus" → in-page preview step →
  "You'll keep Index Premium until \<date> / Index Plus begins after that / No
  charge today / Confirm change".
- Premium user with `pendingChangeState === "scheduled"`: Plus card shows
  "Changes to Index Plus on \<date>" + "Keep Index Premium" button (calls
  cancel-scheduled).
- Same-plan card always shows "Current Plan", unchanged.

Reuses existing gold(Plus)/purple(Premium) presentation primitives already in
`PricingPageClient.jsx` — no new styling system. `billingPresentation.mjs` gets
additive pure-function formatting helpers for the new DTO fields; no existing
exports change. `MembershipBillingSection.jsx`'s "Manage Billing → Portal" link is
untouched — Portal remains scoped to payment methods, invoices, billing details,
cancellation.

## 18. Testing

Backend: `plan_change.py` pure-domain unit tests, `StripeProvider` new-method
tests (mocked Stripe client), `BillingService` orchestration tests, API tests,
security tests (§ below), reconciliation tests confirming schedule-transition
Price change flows through unchanged. Frontend: pricing page interaction tests,
`billingPresentation.mjs` formatting tests.

Security cases to prove: anonymous blocked on all 3 endpoints; cross-user
subscription mutation blocked; every browser-controllable Stripe identifier
ignored/rejected; target offer must exist in server catalog; current Price must
map canonically; unsupported/duplicate subscription shapes fail closed; Basic
blocked from this flow entirely; Plus can only reach Premium; Premium can only
reach Plus; same-tier-interval-only requests rejected; unknown schedule fails
closed on confirm/cancel; expired/tampered/cross-user/stale-Price/changed-item
tokens all rejected; amount drift between preview and confirm → `PREVIEW_STALE`,
no mutation; repeated confirm is idempotent (no duplicate Stripe objects).

Test matrix: all 8 valid cross-tier transitions, both directions, monthly/annual
crossed both ways.

Validation commands: focused backend billing test suite, Stripe provider tests,
plan-change domain tests, billing service tests, billing API tests,
webhook/reconciliation tests, billing security tests, frontend pricing/billing
tests, entitlement tests, `python -m compileall`/import check, `git diff --check`,
isolated frontend production build to a separate dist directory (must not disturb
any running dev server). Do not fix unrelated pre-existing failures.

## 19. Non-negotiable safety

`BILLING_CHECKOUT_ENABLED` stays `false` throughout and at completion. No Stripe
object creation/mutation (sandbox Price IDs are read-only references). No
Supabase mutation, no migrations. No Stripe Price IDs in browser code. No new
webhook endpoint. No live Stripe config. No committed secrets. No changes outside
this feature's files.
