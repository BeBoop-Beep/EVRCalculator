# Billing Effort 5 Launch Decision

Status: `EFFORT_5_BLOCKED_ON_COMMERCIAL_INPUTS`

This record intentionally contains no invented prices, Stripe object identifiers, secrets,
or assumed legal/commercial policies. No database, Stripe account, deployment environment,
or public offer was mutated during this pass.

## Commercial contract

The project owner has not yet supplied the mandatory approved decision record:

| Decision | Approved value |
| --- | --- |
| Currency | UNRESOLVED |
| Index Plus monthly offered | UNRESOLVED |
| Index Plus monthly price | UNRESOLVED |
| Index Plus annual offered | UNRESOLVED |
| Index Plus annual price | UNRESOLVED |
| Index Premium monthly offered | UNRESOLVED |
| Index Premium monthly price | UNRESOLVED |
| Index Premium annual offered | UNRESOLVED |
| Index Premium annual price | UNRESOLVED |
| Free trial | UNRESOLVED |
| Promotion codes | UNRESOLVED |
| Automatic tax | UNRESOLVED |
| Cancellation timing | UNRESOLVED |
| Plan-change proration | UNRESOLVED |
| Refund policy | UNRESOLVED |
| Legal purchase copy | NOT APPROVED / unavailable |

No selected offer can be created until its offered/not-offered decision and exact amount are
approved. `N/A` is acceptable for an interval explicitly declined by the owner.

## Environment classification

| Target | Identifier | Verified purpose | Safe to mutate? |
| --- | --- | --- | --- |
| Supabase linked | `zwxzxuuawalvwioadhmf` / `TheIndex` | Unknown; production/staging not proven | No |
| Supabase unlinked | `exnwvdwjrjlgkgrdlrcw` / `trial` / inactive | Unknown; name alone is not authority | No |
| Stripe sandbox | No configured test secret/account identifier | Unavailable | No |
| Stripe live | No configured live secret/account identifier | Unavailable | No |
| Backend sandbox/staging | No verifiable deployed hostname/configuration | Unknown | No |
| Backend production | No verifiable deployed hostname/configuration | Unknown | No |
| Frontend sandbox/staging | No verifiable deployed hostname/configuration | Unknown | No |
| Frontend production | No verifiable deployed hostname/configuration | Unknown | No |

Local `FRONTEND_BASE_URL` resolves to localhost. Stripe CLI, Docker, Podman, and local `psql`
are unavailable. The installed Supabase CLI is 2.116.0.

## Supabase deployment

Read-only migration inspection from Effort 4 shows the three billing migrations are absent
from the linked remote history:

1. `20260831184744_billing_effort1_foundation.sql`
2. `20260831190018_billing_effort2_stripe_backend.sql`
3. `20260831212547_billing_effort4_atomic_reliability.sql`

The remote/local histories also diverge beyond billing. `billing_doctor` reports
`schemaReachable: false`. No migration was pushed. Before deployment, the owner must identify a
staging project explicitly, reconcile migration history, deploy chronologically, run real
anon/authenticated/service-role probes, verify constraints/RPC grants, and test transactional
entitlement recomputation. Production must follow only after staging succeeds and backup and
rollback posture are approved.

Current Supabase guidance makes explicit object grants a separate requirement from RLS. The
billing migrations already use explicit service-role grants and browser revocations; these must
still be verified against the deployed database.

## Stripe sandbox catalog

No sandbox Products or Prices were created. No offer keys are active. Configuration remains:

```text
STRIPE_SECRET_KEY: absent
STRIPE_WEBHOOK_SECRET: absent
STRIPE_PRICE_PLUS_MONTHLY: absent
STRIPE_PRICE_PLUS_ANNUAL: absent
STRIPE_PRICE_PREMIUM_MONTHLY: absent
STRIPE_PRICE_PREMIUM_ANNUAL: absent
```

After approval, create at most two sandbox Products (`Index Plus`, `Index Premium`) and only
the approved recurring Prices. Validate currency, interval, tax behavior, and `livemode=false`
before mapping Price IDs to backend-only environment variables.

## Price presentation and public pricing

The browser currently receives only canonical offer keys and shows “Pricing pending” because
zero offers are configured. No price amount is hardcoded. Server-authoritative display amounts
and a public pricing surface must be added only after real approved Stripe Prices exist. The
locked Plus/Premium capability packaging must not change or advertise unfinished capabilities.

## Customer Portal configuration

Not configured. Owner approval is required for payment-method updates, invoice history,
cancellation availability/timing/reasons, Plus/Premium switching, allowed Prices, and proration.
Sandbox and live Portal settings must be configured and verified separately.

## Webhook configuration

No sandbox or production destination was created. The canonical destination remains the direct
backend URL:

```text
https://<verified-environment-backend-domain>/billing/stripe/webhook
```

Required events: `checkout.session.completed`, `customer.subscription.created`,
`customer.subscription.updated`, `customer.subscription.deleted`,
`customer.subscription.paused`, `customer.subscription.resumed`, `invoice.paid`,
`invoice.payment_failed`, and `invoice.payment_action_required`. Each environment needs its own
endpoint signing secret.

## Tax, cancellation, proration, and refunds

All remain unresolved. Stripe Tax was not enabled. No tax behavior, trial, discount, promotion,
cancellation timing, proration, or refund behavior was selected.

## Legal launch state

Blocked. `/terms` and `/privacy` are “Legal page coming soon” placeholders. Approved Terms,
Privacy, recurring/auto-renewal disclosure, cancellation policy, refund policy if applicable,
business/contact identity, and purchase consent copy must exist before checkout activation.

## Sandbox and live lifecycle results

Not executed because no approved contract, safe deployed billing schema, Stripe sandbox
credentials/catalog, webhook destination, legal approval, or authorized test account is
available. This includes Checkout, Portal, upgrade/downgrade, cancellation, test-clock,
failed-payment recovery, replay, reconciliation against real Stripe state, and live smoke tests.

## Billing doctor

Current safe result:

```text
stripeSecretConfigured: false
webhookSecretConfigured: false
configuredOfferCount: 0
schemaReachable: false
```

Webhook/anomaly counts cannot be treated as healthy zeros while the billing schema is
unreachable.

## Application regression

Current non-commercial regression results:

```text
backend billing/entitlement/security: 118 passed
frontend billing/auth/entitlement: 34 passed
backend startup/import: passed
```

The Next.js production source compiled successfully twice and generated all 74 static pages,
but both builds ended with an `.next/export/500.html` rename race. Concurrent `.perf-audit`
fixture/visual-parity processes and three `next start` instances were actively sharing
`frontend/.next`; they were preserved and not interrupted. A clean isolated production build
must be rerun after that workstream exits. This is not reported as a passing final build.

## Monitoring and reconciliation

After launch, use Stripe webhooks for realtime synchronization and run
`python -m backend.scripts.reconcile_stripe_billing --all --repair` daily through an established
reliable scheduler. Run `python -m backend.scripts.billing_doctor` for failed/stale webhooks and
configuration/schema health, plus a reconciliation dry-run for unmapped Prices, multiple active
subscriptions, and entitlement drift. Check these immediately after activation and during the
first day/customer lifecycle.

## Rollback

Stop new sales by removing/disabling every configured offer Price variable. Keep webhooks,
Customer Portal, reconciliation, and entitlement synchronization operating for existing
subscribers. During a provider incident, billing actions may fail closed while core inDex and
local entitlement enforcement continue. Never disable webhook ingestion as the purchase kill
switch and never mass-demote subscribers without authoritative reconciliation.

## Resume requirements

The next execution may proceed only after the owner supplies:

1. every commercial-contract decision above;
2. legal approval and final purchase-flow copy;
3. explicit staging and production Supabase classifications;
4. explicit sandbox/live Stripe account classifications and secured credentials;
5. verified staging/production backend and frontend domains;
6. authorized sandbox users and, later, an authorized owner live-smoke account;
7. production migration backup/change-window approval.

Until then: `PRICING_NOT_CONFIGURED`, `PURCHASABLE_OFFERS=0`, and
`PUBLIC_CHECKOUT_DISABLED`.
