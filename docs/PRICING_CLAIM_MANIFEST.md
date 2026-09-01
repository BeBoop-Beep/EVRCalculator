# Pricing Claim Manifest

Audit scope: the nine Index Plus and seven Index Premium capability claims rendered on
`/pricing`. A capability constant by itself was not accepted as implementation evidence.
Each row below traces the claim through a rendered customer surface and, where the surface
loads protected data, its production API and entitlement path.

Status vocabulary: `IMPLEMENTED_AND_CUSTOMER_ACCESSIBLE`,
`IMPLEMENTED_BUT_NOT_READY_FOR_PUBLIC_CLAIM`, `COMING_SOON`, and `NOT_IMPLEMENTED`.

## PRICING_CLAIM_MANIFEST

| Display label | Capability constant | Tier | Actual customer surface | Backend/API available? | Current implementation status | Pricing-page presentation |
| --- | --- | --- | --- | --- | --- | --- |
| Product RIP rankings | `FEATURE_PRODUCT_RIP` | Plus | `/Rankings` ProductFamilyRankingsClient and sealed-product ProductRipSection | YES — RIP targets/product-detail projections; server enforces Product RIP | `IMPLEMENTED_AND_CUSTOMER_ACCESSIBLE` | ✓ Product RIP rankings |
| Detailed EV, recovery, and opening economics | `FEATURE_DETAILED_OPENING_ECONOMICS` | Plus | `/Rankings` RipDecisionPage, RipStoryEvidence, RipDistributionChart, and SimulationFullReport | YES — `/explore/opening-economics` and protected RIP projections | `IMPLEMENTED_AND_CUSTOMER_ACCESSIBLE` | ✓ Detailed EV, recovery, and opening economics |
| Set pack economics | `FEATURE_SET_PACK_ECONOMICS` | Plus | `/Rankings` SetPackMetrics | YES — set RIP/bootstrap, advanced, and rank-context projections enforce the set analytics entitlement | `IMPLEMENTED_AND_CUSTOMER_ACCESSIBLE` | ✓ Set pack economics |
| Era pack economics | `FEATURE_ERA_PACK_ECONOMICS` | Plus | `/Rankings` OpeningEconomicsEras | YES — `/explore/opening-economics` supplies the protected era comparison | `IMPLEMENTED_AND_CUSTOMER_ACCESSIBLE` | ✓ Era pack economics |
| Market breadth | `FEATURE_MARKET_BREADTH` | Plus | Set Market, SetMarketSignals and desktop/mobile market overview | YES — set market dashboard/bootstrap/signals routes enforce Market Breadth | `IMPLEMENTED_AND_CUSTOMER_ACCESSIBLE` | ✓ Market breadth |
| Card pull odds | `FEATURE_CARD_PULL_ODDS` | Plus | Card detail “Choose How You Open It” and Probability Journey | YES — card detail and set pull-rate/simulation projections provide modeled exact-printing odds | `IMPLEMENTED_AND_CUSTOMER_ACCESSIBLE` | ✓ Card pull odds |
| Acquisition milestones | `FEATURE_ACQUISITION_MILESTONES` | Plus | Card detail probability milestone rail and opening-choice acquisition costs | YES — protected card/RIP projections provide milestone pack and spend values | `IMPLEMENTED_AND_CUSTOMER_ACCESSIBLE` | ✓ Acquisition milestones |
| Prepared Market Explorer intelligence | `FEATURE_PREPARED_MARKET_INTELLIGENCE` | Plus | `/Market/Explorer` prepared filters, benchmarks, and series | YES — `/market/explorer/snapshot` provides the prepared paid layer | `IMPLEMENTED_AND_CUSTOMER_ACCESSIBLE` | ✓ Prepared Market Explorer intelligence |
| Single-axis custom markets | `FEATURE_MARKET_EXPLORER_SINGLE_AXIS` | Plus | `/Market/Explorer` MarketExplorerQueryBuilder | YES — query options plus `POST /market/explorer/query`; server evaluates the active axis and Plus entitlement | `IMPLEMENTED_AND_CUSTOMER_ACCESSIBLE` | ✓ Single-axis custom markets |
| Chase Efficiency ranking | `FEATURE_CARD_CHASE_EFFICIENCY` | Premium | `/Rankings` CardChaseEfficiencyRankings and card-detail Chase Efficiency section | YES — `/explore/card-chase-efficiency` and `/tcgs/pokemon/sets/{set_id}/cards/{card_id}/chase-efficiency`; both enforce Premium | `IMPLEMENTED_AND_CUSTOMER_ACCESSIBLE` | ✓ Chase Efficiency ranking |
| Best chase opening route | `FEATURE_CHASE_OPENING_ROUTE` | Premium | Card-detail Chase Efficiency economics matrix renders “Best Verified Opening Route” with product, pack count, and price | YES — the protected exact-card Chase Efficiency response carries verified route economics | `IMPLEMENTED_AND_CUSTOMER_ACCESSIBLE` | ✓ Best chase opening route |
| Chase-vs-buy economics | `FEATURE_CHASE_VS_BUY` | Premium | Rankings “Cost vs Buy” column and card-detail chance-at-buy-price / 50% cost multiple | YES — protected Chase Efficiency ranking and exact-card responses carry buy-price comparison fields | `IMPLEMENTED_AND_CUSTOMER_ACCESSIBLE` | ✓ Chase-vs-buy economics |
| Global, era, set, and rarity chase rankings | `FEATURE_CHASE_RANKINGS` | Premium | Card-detail Rank Context rail (Overall, Era, Set, Rarity) plus sortable `/Rankings` card lens | YES — protected Chase Efficiency responses include all four rank cohorts | `IMPLEMENTED_AND_CUSTOMER_ACCESSIBLE` | ✓ Global, era, set, and rarity chase rankings |
| Multi-axis compound markets | `FEATURE_MARKET_EXPLORER_COMPOUND` | Premium | `/Market/Explorer` builder combines scope, segment, price, release-age, and other axes | YES — `POST /market/explorer/query` and the query service accept compound specs; server requires Premium when more than one axis is active | `IMPLEMENTED_AND_CUSTOMER_ACCESSIBLE` | ✓ Multi-axis compound markets |
| Pokémon-specific market construction | `FEATURE_MARKET_EXPLORER_POKEMON` | Premium | `/Market/Explorer` Pokémon filter in the custom-market builder | YES — query DTO/service accept `pokemonIds`; server independently requires Premium for Pokémon-filtered queries | `IMPLEMENTED_AND_CUSTOMER_ACCESSIBLE` | ✓ Pokémon-specific market construction |
| Custom ranked market composition | `FEATURE_MARKET_EXPLORER_CUSTOM_RANKED` | Premium | `/Market/Explorer` ranked “Top 10 in Selected Set” screen and chase-mode builder result | YES — query DTO/service accept `mode: chase` and `topN`; server independently requires Premium for ranked mode | `IMPLEMENTED_AND_CUSTOMER_ACCESSIBLE` | ✓ Custom ranked market composition |

## Audit result

- `IMPLEMENTED_AND_CUSTOMER_ACCESSIBLE`: 16
- `IMPLEMENTED_BUT_NOT_READY_FOR_PUBLIC_CLAIM`: 0
- `COMING_SOON`: 0
- `NOT_IMPLEMENTED`: 0
- Unclassified pricing claims: 0

All current Plus and Premium feature rows may retain their standard checkmark. “Coming Soon”
continues to describe subscription purchasing while checkout is disabled; it does not describe
the availability of the implemented product surfaces to already-entitled accounts.
