# Billing Effort 4: Production Hardening

## 1. Architecture closure

```text
Browser -> no-store Next billing proxy -> authenticated Python API
        -> BillingService -> StripeProvider / BillingRepository
        -> server-owned billing tables -> recompute_effective_index_plan
        -> users.index_plan -> existing backend feature gates
```

The offer catalog is `backend/domain/billing/catalog.py`; subscription policy is
`backend/domain/billing/policy.py`. Stripe schema assumptions remain isolated in
`StripeProvider` and `BillingService.subscription_row`. Ordinary authorization and
`GET /billing/me` use local synchronized records and never call Stripe.

## 2. Migration verification

The two foundation migrations and the Effort 4 forward-only migration were statically
audited. Customer/provider IDs, provider subscription IDs, and provider event IDs are
unique. Billing FKs target `public.users(id)`. Existing paid users are copied to explicit
manual provenance before effective-plan recomputation is used.

Effort 4 adds atomic service-only RPCs for webhook claiming, subscription persistence plus
entitlement recomputation, and missing-subscription demotion plus recomputation. Their
`SECURITY DEFINER` search paths are pinned to `pg_catalog, public`.

Read-only `supabase migration list` confirmed all three billing migrations are local-only on
the linked project, and `billing_doctor` received an API error because the billing schema is
not deployed there. `UNEXECUTED_DB_BACKED_VALIDATION`: Docker, Podman, local PostgreSQL, and a safely identified
development Supabase database are unavailable. The linked project is named `TheIndex` and
cannot safely be classified as non-production. It was deliberately not mutated. Effort 5
must execute the migrations in chronological order against a proven staging database,
run the role probes below, then deploy through the approved production migration workflow.

## 3. RLS and grant verification

Static result: all billing tables enable RLS; `anon` and `authenticated` have all table
access revoked; `service_role` receives explicit table privileges. Every billing RPC revokes
`PUBLIC`, `anon`, and `authenticated`, then grants only `service_role`. No browser policy can
mutate billing or manual entitlement state.

Required DB-backed probes remain unexecuted: anon insert, authenticated insert/update,
authenticated `users.index_plan` update, browser RPC execution, service-role success,
uniqueness, and transactional rollback. This is a hard launch gate, not a passing result.

Account deletion currently cascades customer, subscription, and manual-entitlement rows.
Webhook ledger rows are independent. Before shipping account deletion for subscribed users,
the product must cancel/resolve Stripe billing first and define audit-retention requirements.

## 4. Webhook reliability

The HTTP boundary reads exact bytes and verifies `Stripe-Signature` before any ledger write.
Tests cover a valid HMAC signature, missing/invalid signatures, one-byte mutation, and JSON
reserialization. Invalid requests cause no billing mutation.

After verification, `claim_billing_webhook_event` atomically inserts or reclaims a failed or
five-minute-stale event. Processed duplicates are no-ops; an actively processing duplicate
returns a retryable failure. Reconciliation is idempotent, and persistence plus entitlement
recompute is one DB transaction. Failure records retain event ID/type, attempts, error code,
summary, and last attempt. Rows are retained indefinitely; no cleanup window can undercut
Stripe retry/replay behavior.

Events never supply entitlement state directly. Each relevant delivery retrieves current
Stripe subscription state, so delayed create/update/invoice events cannot resurrect stale
access. The consumed event set is:

- `checkout.session.completed`
- `customer.subscription.created|updated|deleted|paused|resumed`
- `invoice.paid|payment_failed|payment_action_required`

Acknowledgement remains synchronous: verify, atomically claim, authoritative Stripe retrieve,
atomic persistence/recompute, mark processed, then HTTP 200. Local fake-boundary processing is
fast, but no real Stripe/DB latency measurement was possible. A failure returns 503 so Stripe
retries. Do not replace this with in-process background work. If production telemetry shows
timeout risk, move post-claim work to a real durable queue while keeping durable receipt before
acknowledgement.

## 5. Reconciliation

Dry-run is the default:

```bash
python -m backend.scripts.reconcile_stripe_billing --user-id <uuid>
python -m backend.scripts.reconcile_stripe_billing --customer-id <cus_id>
python -m backend.scripts.reconcile_stripe_billing --all
```

Mutation requires explicit `--repair`. A single provider subscription can be repaired with
`--subscription-id <sub_id> --repair`. Bulk runs continue past individual failures and return
concise totals. Schedule `--all --repair` daily only through an existing reliable production
scheduler; no scheduler framework was added here.

Drift categories: `MATCH`, `LOCAL_SUBSCRIPTION_MISSING`, `LOCAL_SUBSCRIPTION_STALE`,
`LOCAL_STATUS_MISMATCH`, `LOCAL_PLAN_MISMATCH`, `INDEX_PLAN_MISMATCH`,
`STRIPE_CUSTOMER_MISSING`, `UNMAPPED_PRICE`, `MULTIPLE_ACTIVE_SUBSCRIPTIONS`,
`UNSUPPORTED_SUBSCRIPTION_SHAPE`, `MANUAL_ENTITLEMENT_ONLY`, and `PROVIDER_ERROR`.

Unknown prices and unsupported multi-item shapes fail closed. Missing Stripe customers are
reported and never silently replaced. Manual access is merged only through the canonical
policy and is never erased by Stripe repair.

## 6. Failure-mode matrix

| Failure | Result | Recovery |
| --- | --- | --- |
| Stripe down during checkout/portal | Stable 503; no entitlement | Retry action |
| Stripe down during webhook | Event failed/retryable; no grant | Stripe retry + reconciliation |
| DB down before ledger claim | 503; no acknowledgement | Stripe retry |
| DB down after Stripe customer creation | Stable customer idempotency key | Retry maps same customer |
| Atomic subscription RPC fails | No partial entitlement commit | Webhook retry/reconciliation |
| Duplicate delivery | Atomic duplicate/busy decision | No duplicate state |
| Worker dies while processing | Five-minute stale reclaim | Provider retry/operator repair |
| Webhook missed/misconfigured | Local drift remains visible | Fix endpoint + bulk reconciliation |
| Customer missing at Stripe | No replacement/ownership guess | `STRIPE_CUSTOMER_MISSING` intervention |

## 7. Security matrix

- Authentication identity alone chooses customer, subscription status, and portal state.
- Checkout accepts only `offerKey`; extra authority fields are rejected.
- Portal accepts no customer or return URL authority.
- Cross-site browser POSTs are rejected using `Origin`/`Sec-Fetch-Site`; bearer/non-browser
  calls without browser origin metadata retain API compatibility.
- Redirect origins are server-owned and production requires HTTPS.
- Private billing proxies use `cache: no-store`, `Cache-Control: no-store`, and
  `Vary: Cookie, Authorization`.
- Paid APIs continue to enforce current server `users.index_plan`; stale UI cannot retain access.
- Logs contain operational IDs and stable codes, not secrets, signatures, raw events,
  checkout/portal URLs, emails, or payment data.
- Billing pages redirect to hosted Stripe surfaces; they do not iframe Stripe or weaken CSP.
- Checkout and portal lack infrastructure-level quotas. Authentication, duplicate-subscription
  prevention, stable customer idempotency, and UI action locks bound common abuse. Add shared
  rate limiting later only through the platform's canonical middleware; never throttle webhooks.

## 8. Observability

Run `python -m backend.scripts.billing_doctor`. It is read-only and prints only configuration
booleans/counts, schema reachability, failed-event summaries, and stale-processing counts.
It never prints secrets. Reconciliation reports accounts scanned, matches, repairs, drift
categories, errors, and entitlement changes. Structured application logs cover checkout,
reconciliation, anomalies, and effective-plan transitions without storing raw Stripe objects.

## 9. Stripe Dashboard checklist

- Create a Workbench event destination directly to the canonical backend HTTPS endpoint:
  `https://<canonical-backend-domain>/billing/stripe/webhook`.
- Subscribe only to the nine event types listed above.
- Store that endpoint's unique signing secret as `STRIPE_WEBHOOK_SECRET`.
- Keep Stripe CLI listener secrets separate from deployed endpoint secrets.
- Configure Portal decisions: payment-method updates, invoices, cancellation timing/reasons,
  plan switching, allowed products/prices, and proration.
- Do not route signed webhooks through Next.js unless deployment topology makes it unavoidable;
  the direct backend path minimizes raw-body transformation risk.

The installed Stripe SDK is pinned to `stripe==15.4.0`. The adapter relies on subscription
`customer`, `status`, `items.data[].price.id/product`, period timestamps, cancellation fields,
Checkout `subscription`, and Dahlia-era invoice `parent.subscription_details.subscription`.
Confirm the Workbench endpoint API version against these fixtures during Effort 5.

## 10. Environment checklist

Required for synchronization: `STRIPE_SECRET_KEY`, `STRIPE_WEBHOOK_SECRET`, `SUPABASE_URL`,
`SUPABASE_SERVICE_ROLE_KEY`, and the existing JWT/auth configuration. `FRONTEND_BASE_URL` is
required for trusted production redirects. Offer variables remain unset until activation:
`STRIPE_PRICE_PLUS_MONTHLY`, `STRIPE_PRICE_PLUS_ANNUAL`,
`STRIPE_PRICE_PREMIUM_MONTHLY`, and `STRIPE_PRICE_PREMIUM_ANNUAL`.

Missing Stripe configuration does not break ordinary analytics startup. Billing actions fail
closed. Before activation, verify every key and Price belongs to the same Stripe test/live mode;
then validate each Price's `livemode`, product, currency, recurrence, and tax behavior.

## 11. Legal blockers

Separately review Terms of Service, Privacy Policy, auto-renewal disclosure, cancellation policy,
refund policy if applicable, billing/contact identity, and business/contact information. Search
and remove any surviving Shiny Finds or physical-commerce language from purchase-linked pages.
Legal wording is not authored by this effort.

## 12. Rollback strategy

The purchase kill switch is to unset/disable all offer Price variables. That produces zero
purchasable offers and prevents new Checkout sessions. Keep webhook processing enabled so
existing subscribers remain synchronized, and keep Customer Portal available when appropriate.
Do not remove the webhook endpoint/secret as the first response to a sales incident.

## 13. Validation status

The combined backend billing/entitlement/abuse suite passed 118 tests. The combined frontend
billing/auth/entitlement suite passed 34 tests. Backend compile/import passed, and the Next.js
production build compiled successfully (with unrelated existing lint warnings). DB-backed migration,
RLS, and real Stripe sandbox delivery are explicitly `UNEXECUTED_DB_BACKED_VALIDATION` until
safe infrastructure and a sandbox catalog are available.

## 14. Effort 5 launch checklist

Decide prices, intervals, discounts/trials, cancellation/proration/refunds, and tax posture.
Create sandbox Products/Prices, configure matching server variables and Portal choices, finish
legal purchase copy, apply/verify migrations on staging then production, run a complete sandbox
lifecycle, configure production keys/webhook, create live catalog objects, activate offers, and
perform a live smoke test. Stripe Tax remains off until registration posture, address collection,
product tax code, Price tax behavior, and Portal switching compatibility are approved.

Current commercial state remains: `PRICING_NOT_CONFIGURED`, `PURCHASABLE_OFFERS=0`, and
`PUBLIC_CHECKOUT_DISABLED`.
