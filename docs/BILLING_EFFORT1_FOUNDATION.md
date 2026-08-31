# Billing Effort 1 Foundation

Status: `PRICING_NOT_CONFIGURED` · `STRIPE_NOT_IMPLEMENTED` · `CHECKOUT_DISABLED`

## Commercial contract

| Capability | Tier | Enforcement / implementation status |
|---|---|---|
| Product RIP rankings | Plus | Central capability; backend positive projections; frontend locks |
| Detailed EV, recovery, opening economics | Plus | Central capability; detailed API projections |
| Set and era pack economics | Plus | Central capabilities; detailed API projections |
| Market breadth | Plus | Central capability; sealed-market projection |
| Card pull odds | Plus | Contract encoded; existing pull-rate surfaces require boundary audit when expanded |
| Acquisition milestones (50/75/90/95) | Plus | 50/90 fields gated; 75/95 are not implemented and were not fabricated |
| Prepared Market Explorer intelligence | Plus | Central capability and authenticated API gate |
| Single-axis custom markets | Plus | Mirrored query evaluator in both runtimes and backend enforcement |
| Chase Efficiency | Premium | Central capability; frontend and backend API gates |
| Best chase opening route | Premium | Contract encoded; no complete standalone feature yet |
| Chase-vs-buy economics | Premium | Contract encoded; existing chase economics remain Premium-gated |
| Global/era/set/rarity chase rankings | Premium | Contract encoded; not all ranking scopes exist yet |
| Compound markets | Premium | Mirrored query evaluator and backend enforcement |
| Pokémon-specific markets | Premium | Mirrored query evaluator and backend enforcement |
| Custom ranked composition | Premium | Mirrored query evaluator and backend enforcement |

Unknown plans and unknown capabilities fail closed. Authentication remains identity only; `users.index_plan` remains the effective application entitlement. Premium satisfies every Plus capability. The Python authority additionally retains server-only projection aliases (`pack_economics`, `set_rip_analytics`) because API payload projection has no browser equivalent.

## Removed legacy commerce

Removed `/cart`, `/checkout`, `/products`, `/products/details`, `/merchandise`, `/ripAndShip`, the Cart provider/state/local-storage implementation, cart UI, physical Products/Merchandise/Rip-and-Ship component trees, sales-tax utility, obsolete navigation comments, raw payment/shipping UI, unused legal-commerce modal, and `@stripe/stripe-js`. No replacement checkout route was created. Merchandise remains a legitimate collection asset type; only its abandoned storefront was removed.

## Preserved sealed-product analytics

The canonical sealed-product detail route, `frontend/components/pokemon/sealed-product-detail`, `frontend/lib/pokemon/sealedProductRoutes.mjs`, backend sealed-product services/domain models, RIP analytics, market data, and detail links were intentionally retained. They represent analytics entities, not inventory.

## Billing schema and architecture

`billing_customers` uniquely maps a user/provider and provider customer ID. `billing_subscriptions` retains provider IDs, offer, paid plan, lifecycle dates/status, and indexed user/status lookup. `billing_webhook_events` uniquely keys `(provider, provider_event_id)` for future idempotency without storing raw payloads. All three tables have RLS enabled and revoke browser roles; only trusted server code may access them.

Authentication identifies the account. Billing records describe commercial state. A future billing synchronizer will derive `users.index_plan`. The existing access authority authorizes features and projects API responses. Feature code never interprets provider status.

The server-owned catalog declares monthly/annual identities for Plus/Premium as disabled possibilities, not promised products. Every price ID is unset and every offer fails with `BILLING_OFFER_NOT_CONFIGURED`. There is no public checkout endpoint.

## Legal cleanup status

The obsolete Shiny Finds physical-goods terms modal was removed. `/terms` remains an explicit coming-soon legal placeholder and must be replaced before billing launch. Effort 5 must supply reviewed subscription terms, privacy disclosures, cancellation/refund policy, billing contact identity, renewal language, and provider disclosures. Signup/auth has no dependency on the removed modal.

## Validation

See the final Effort 1 handoff for exact command totals. Validation covers mirrored entitlement contracts, paid API response boundaries, billing catalog failure behavior, frontend build, backend imports, migration SQL structure, and the legacy-commerce dead-code scan.

## Effort 2 readiness

Remaining provider work: configure real offers only after pricing is approved; implement server-side Stripe client/configuration, Checkout Sessions, verified idempotent webhooks using the ledger, subscription-to-effective-plan synchronization, Customer Portal, reconciliation/observability, and provider integration tests. None of that is implemented here.
