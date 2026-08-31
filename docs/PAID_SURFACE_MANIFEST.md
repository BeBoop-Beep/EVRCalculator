# Paid Surface Manifest

Scope authority for the global inDex upgrade funnel. Every customer-visible paid capability uses
`PlanLock`/`PlanUpgradeLink`, or reaches the same canonical route through the Rankings callback.
Authorization remains in `indexPlanAccess.mjs` and the backend response projections.

| Route | Component / surface | Capability | Tier | Previous mechanism | Global lock | Destination | Disposition |
| --- | --- | --- | --- | --- | --- | --- | --- |
| `/Rankings` | ProductFamilyRankingsClient, ExploreTableClient, RankedProductTablePrimitives, SetRipFamilyBreakdown | `FEATURE_PRODUCT_RIP` | Plus | compact locks + callback | Rankings callback | `/pricing?plan=plus&source=rankings` | UPDATED_TO_GLOBAL_UPGRADE_FUNNEL |
| `/Rankings` | OpeningEconomicsEras, RipDecisionPage, RipStoryEvidence, RipDistributionChart, SimulationFullReport | `FEATURE_DETAILED_OPENING_ECONOMICS` | Plus | compact/section locks + callback | Rankings callback | `/pricing?plan=plus&source=rankings` | UPDATED_TO_GLOBAL_UPGRADE_FUNNEL |
| `/Rankings` | SetPackMetrics | `FEATURE_SET_PACK_ECONOMICS` | Plus | passive Plus copy + callback | Rankings callback | `/pricing?plan=plus&source=rankings` | UPDATED_TO_GLOBAL_UPGRADE_FUNNEL |
| `/Rankings` | OpeningEconomicsEras | `FEATURE_ERA_PACK_ECONOMICS` | Plus | passive Plus copy + callback | Rankings callback | `/pricing?plan=plus&source=rankings` | UPDATED_TO_GLOBAL_UPGRADE_FUNNEL |
| `/Rankings` | CardChaseEfficiencyRankings | `FEATURE_CARD_CHASE_EFFICIENCY`, `FEATURE_CHASE_RANKINGS` | Premium | bespoke non-clickable panel | PlanUpgradeLink | `/pricing?plan=premium&source=chase-efficiency` | UPDATED_TO_GLOBAL_UPGRADE_FUNNEL |
| `/Market/Explorer` | MarketExplorerFilters, MarketExplorerQueryBuilder, MarketExplorerSeriesCard, ExplorerMarketOption | `FEATURE_PREPARED_MARKET_INTELLIGENCE` | Plus | Explorer lock with dead route | PlanLock | `/pricing?plan=plus&source=market-explorer` | UPDATED_TO_GLOBAL_UPGRADE_FUNNEL |
| `/Market/Explorer` | MarketExplorerQueryBuilder | `FEATURE_MARKET_EXPLORER_CUSTOM_MARKETS` | Plus | Explorer lock with dead route | PlanLock | `/pricing?plan=plus&source=market-explorer` | UPDATED_TO_GLOBAL_UPGRADE_FUNNEL |
| `/Market/Explorer` | MarketExplorerQueryBuilder | `FEATURE_MARKET_EXPLORER_SINGLE_AXIS` | Plus | Explorer lock with dead route | PlanLock | `/pricing?plan=plus&source=market-explorer` | UPDATED_TO_GLOBAL_UPGRADE_FUNNEL |
| `/Market/Explorer` | MarketExplorerQueryBuilder | `FEATURE_MARKET_EXPLORER_COMPOUND` | Premium | Explorer lock with dead route | PlanLock | `/pricing?plan=premium&source=market-explorer` | UPDATED_TO_GLOBAL_UPGRADE_FUNNEL |
| `/Market/Explorer` | Market Explorer Pokémon filters | `FEATURE_MARKET_EXPLORER_POKEMON` | Premium | query-level plan lock | PlanLock | `/pricing?plan=premium&source=market-explorer` | UPDATED_TO_GLOBAL_UPGRADE_FUNNEL |
| `/Market/Explorer` | Market Explorer ranked screen | `FEATURE_MARKET_EXPLORER_CUSTOM_RANKED` | Premium | screen lock | PlanLock | `/pricing?plan=premium&source=market-explorer` | UPDATED_TO_GLOBAL_UPGRADE_FUNNEL |
| Set Market | SetMarketSignals — Market Breadth and Chase Concentration | `FEATURE_MARKET_BREADTH` | Plus | duplicated Explorer descriptor | canonical descriptor/link | `/pricing?plan=plus` | UPDATED_TO_GLOBAL_UPGRADE_FUNNEL |
| Card detail | PlusLock — opening choice / collector intelligence | `FEATURE_CARD_PULL_ODDS`, `FEATURE_ACQUISITION_MILESTONES` | Plus | bespoke `/pricing` link | PlanUpgradeLink | `/pricing?plan=plus&source=card-detail` | UPDATED_TO_GLOBAL_UPGRADE_FUNNEL |
| Card detail | Chase Efficiency section | `FEATURE_CARD_CHASE_EFFICIENCY`, `FEATURE_CHASE_OPENING_ROUTE`, `FEATURE_CHASE_VS_BUY` | Premium | bespoke `/pricing` link | PlanUpgradeLink | `/pricing?plan=premium&source=card-detail` | UPDATED_TO_GLOBAL_UPGRADE_FUNNEL |
| Sealed product detail | ProductRipSection | `FEATURE_PRODUCT_RIP` | Plus | bespoke `/pricing` link | PlanUpgradeLink | `/pricing?plan=plus&source=sealed-product` | UPDATED_TO_GLOBAL_UPGRADE_FUNNEL |
| Global desktop header | Membership discovery | plan identity | Basic/Plus/Premium | absent | MembershipNavLink | pricing or billing management | UPDATED_TO_GLOBAL_UPGRADE_FUNNEL |
| Global mobile header / bottom nav | Membership discovery | plan identity | Basic/Plus/Premium | absent | MembershipNavLink / Upgrade profile slot | pricing or billing management | UPDATED_TO_GLOBAL_UPGRADE_FUNNEL |

## Audited, intentionally not converted

| Location | Classification | Reason |
| --- | --- | --- |
| Pokémon overview, Sets overview, main Market page | ALREADY_ENTITLED_CONTENT_NO_LOCK | Public discovery/market content; no paid lock found. |
| `ChaseEfficiencyFigures.jsx` and Chase Efficiency article | NON_GATED_INFORMATIONAL_MENTION | Editorial explanation, not an interactive paid capability. |
| AuthContext / AuthPopover | INTENTIONALLY_UNCHANGED_WITH_REASON | Authentication and canonical `user.index_plan` delivery only; not pricing authority. |
| Footer | INTENTIONALLY_UNCHANGED_WITH_REASON | No paid lock or primary purchase-control requirement. |
| Backend capability/projection code | BACKEND_ONLY | Security authority remains unchanged. |
| Contract/unit tests mentioning locks | TEST_ONLY | Regression coverage, not customer UI. |
| Billing and entitlement documentation | DOCS_ONLY | Operational records, not customer UI. |

## Capability completeness

All 17 canonical paid capability identities are represented above. None is classified
`NOT_CURRENTLY_RENDERED`: each currently has an implemented customer-facing surface or builder
path. Future paid surfaces must add a row here and use the canonical funnel.

`ZERO_UNCLASSIFIED_CUSTOMER_VISIBLE_PAID_SURFACES = true`

## Post-edit audit totals

| Classification | Count |
| --- | ---: |
| Customer-visible paid/membership surfaces | 17 |
| Plus capability surfaces | 10 |
| Premium capability surfaces | 5 |
| Global mixed-tier membership surfaces | 2 |
| Updated to the global funnel | 17 |
| Already-correct customer paid surfaces | 0 |
| Informational/editorial groups | 1 |
| Test-only groups | 1 |
| Docs-only groups | 1 |
| Backend-only groups | 1 |
| Unclassified customer-visible paid surfaces | 0 |

The repeated repository scan matched 91 frontend files across UI, entitlement helpers, tests,
and editorial code. Stale purchase-route language remained only inside a test asserting that
`Sign in to unlock` is absent. No customer-visible stale match remains.
