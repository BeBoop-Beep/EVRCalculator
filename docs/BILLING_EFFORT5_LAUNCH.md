# Billing Effort 5 Launch Decision

Status: `EFFORT_5_BLOCKED_ON_TAX_LEGAL_AND_SAFE_ENVIRONMENT_CLASSIFICATION`

This record intentionally contains no invented prices, Stripe object identifiers, secrets,
or assumed legal/commercial policies. No database, Stripe account, deployment environment,
or public offer was mutated during this pass.

## Commercial contract

The project owner approved all four recurring offer amounts and intervals plus the launch
operating policies below:

| Decision | Approved value |
| --- | --- |
| Currency | USD |
| Index Plus monthly offered | YES |
| Index Plus monthly price | 999 minor units / $9.99 USD |
| Index Plus annual offered | YES |
| Index Plus annual price | 7900 minor units / $79.00 USD |
| Index Premium monthly offered | YES |
| Index Premium monthly price | 2499 minor units / $24.99 USD |
| Index Premium annual offered | YES |
| Index Premium annual price | 21900 minor units / $219.00 USD |
| Free trial | NONE |
| Promotion codes | DISABLED |
| Automatic tax | `AUTOMATIC_TAX_DECISION_PENDING` |
| Cancellation timing | END OF CURRENT BILLING PERIOD |
| Cancellation reasons | ENABLED |
| Upgrade | IMMEDIATE + STRIPE PRORATION |
| Downgrade | END OF CURRENT BILLING PERIOD |
| Normal cancellation refund | NO AUTOMATIC PRORATED CASH REFUND |
| Exceptional refunds | MANUAL / CASE-BY-CASE UNDER FINAL LEGAL POLICY |
| Legal purchase copy | NOT APPROVED / unavailable |

Approved annual presentation: Plus saves 4088 minor units (`34%`, effective 658 minor units per
month); Premium saves 8088 minor units (`27%`, effective 1825 minor units per month). These are
normal annual prices, not temporary promotions. All amounts are USD.

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
BILLING_CURRENCY: optional; canonical default is usd and any other value fails closed
BILLING_CHECKOUT_ENABLED: false
```

The approved sandbox model is exactly one Product named `inDex Membership` with four recurring
USD Prices: `plus_monthly`, `plus_annual`, `premium_monthly`, and `premium_annual`. Application
display names remain `Index Plus` and `Index Premium`. Product identity is audit data only;
canonical Price-ID-to-offer mapping remains the sole commercial and entitlement authority.
Validate amount, currency, interval, labels, and `livemode=false` before mapping Price IDs to
backend-only environment variables. Do not create live objects.

## Price presentation and public pricing

The server catalog now owns the approved minor-unit amounts. A safe DTO exposes amount, currency,
interval, plan, and purchasability only for fully configured offers. Central frontend helpers
derive annual savings, rounded discount, effective monthly annual rate, and localized display.
The browser still shows “Pricing pending” because real Price IDs and checkout activation
are absent. A public pricing surface must be added only after real approved Stripe Prices exist. The
locked Plus/Premium capability packaging must not change or advertise unfinished capabilities.

## Customer Portal configuration

Not configured. In sandbox, configure the shared Product's four allowed Prices; cancellation at
period end; cancellation reasons on; retention coupons off; promotion codes off; immediate
prorated upgrades; and end-of-period downgrades. Visually verify that Portal labels clearly
distinguish Plus/Premium and monthly/annual. If they do not, stop: do not change the Product model
or build custom plan-changing infrastructure without approval. Sandbox and live Portal settings
must be configured and verified separately.

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

Checkout explicitly disables promotion-code entry and automatic tax, and supplies no trial
fields. Automatic tax stays off until tax-registration obligations and an approved collection
mechanism are determined. Normal cancellation is scheduled for period end with access retained
through that paid period and no automatic prorated cash refund. Upgrades are immediate with
Stripe proration; downgrades are scheduled for period end. Exceptional refunds are manual and
subject to the final approved legal policy.

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
billingCurrencyApproved: true
checkoutEnabled: false
```

Webhook/anomaly counts cannot be treated as healthy zeros while the billing schema is
unreachable.

## Application regression

Current non-commercial regression results:

```text
backend focused billing/domain/service/migration: 56 passed
frontend focused billing/account: 19 passed
billing doctor: fail-closed, zero configured offers
```

The clean Next.js production build passed after the concurrent `.next` workstream exited. The
billing API test module is presently blocked during collection by an unrelated missing
`backend.desirability.scoring_config` module; it fails before billing API tests load.

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

1. automatic-tax/tax-registration decision;
2. legal approval and final purchase-flow copy;
3. explicit staging and production Supabase classifications;
4. explicit sandbox/live Stripe account classifications and secured credentials;
5. verified staging/production backend and frontend domains;
6. authorized sandbox users and, later, an authorized owner live-smoke account;
7. production migration backup/change-window approval.

Until then: `PRICING_NOT_CONFIGURED`, `PURCHASABLE_OFFERS=0`, and
`PUBLIC_CHECKOUT_DISABLED`.
