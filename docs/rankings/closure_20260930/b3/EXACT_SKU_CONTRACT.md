# Bucket 3 exact-SKU Pack Economics contract

## Authority and joins

The paid Pack Economics projection is anchored to the single latest `pokemon_rip_stats_snapshot_latest` row. Its `openingEconomics.sets` and `familyEconomics` remain the authority for Set aggregates and internal family weighting. Bucket 3 does not recalculate either.

Exact products are selected by `budget_product_best_open_price_rows` for the latest `budget_product_best_open_price_latest.snapshot_id`. Identity is joined in one batch from `sealed_products.id = budget_product_best_open_price_rows.sealed_product_id`. Exact economics is joined in one batch on the compound canonical key:

`simulation_sealed_product_results.sealed_product_id = budget_product_best_open_price_rows.sealed_product_id`

and

`simulation_sealed_product_results.calculation_run_id = budget_product_best_open_price_rows.source_calculation_run_id`.

Names, display strings, and family labels are never join keys. `sealed_products.name` supplies `productName`; the Best-Open row supplies the canonical Set and family membership used by the published cohort. `familyKey`/`familyName` are metadata only and create no visible hierarchy.

## Field contract

| API field | Authority | Units / rule |
| --- | --- | --- |
| `sealedProductId` | Best-Open row, joined to `sealed_products.id` | canonical identifier |
| `productName` | `sealed_products.name` | canonical product name |
| `setId`, `familyKey` | Best-Open row | published cohort classification |
| `packCount` | exact simulation row `random_pack_count`, falling back to its `pack_count` | packs per exact SKU |
| `purchaseQuantity` | Best-Open row `current_quantity` | exact units in selected purchase basis |
| `actualCommittedCapital` | Best-Open row `current_actual_committed_capital` | currency amount for that exact basis |
| `unitPrice` | exact simulation row `product_market_cost` | currency per sealed product; if exact economics is absent, the same-SKU Best-Open current market price remains available only as unit price |
| `averagePackCostPerPack` | exact `product_market_cost / packCount` | currency per pack |
| `expectedValuePerPack` | exact `expected_value / packCount` | currency per pack |
| `modeledReturnOnSpend` | exact `expected_value / product_market_cost` | ratio, not percent |
| `chanceToRecoverCost` | exact simulation row | probability ratio |
| `entertainmentCostPerPack` | exact derivation below | currency per pack |
| Best-Open price, market price, gaps, status | same exact Best-Open row | currency, ratio, and publication status |
| economics date | exact simulation row `price_as_of` | ISO date |
| Best-Open date | latest pointer `source_market_date` | ISO date, independently compared with opening-economics date |
| `sourceCalculationRunId` | Best-Open row | exact simulation provenance key |

## Entertainment cost decision

The existing model in `backend/domain/pokemon/opening_economics_v3.py` defines exact product entertainment cost per pack as `(product_market_cost - expected_value) / pack_count`, equivalently `averagePackCostPerPack - expectedValuePerPack`. Bucket 3 applies that established formula only when all exact inputs exist. This is a projection of the existing model, not a scoring/model change.

When the exact simulation row, pack count, price, or expected value is absent, exact economics fields—including entertainment cost—are `null`, and `economicsAvailabilityStatus` is `unavailable`. Family values are never substituted.

## Same-family variants

Every `sealedProductId` produces its own row. Multiple ETBs or other variants in the same family retain independent pack counts, prices, expected values, recovery probabilities, run IDs, Best-Open values, and dates. Sorting is deterministic by canonical product name then ID; it does not collapse variants.

## Access boundary

This projection is returned only by the paid detailed Pack Economics path. The public preview continues to use its explicit allowlist: Set identity/artwork, counts, average pack cost, and date. It neither calls this detailed reader nor includes `products`, family details, EV, return, recovery, entertainment cost, or Best-Open evidence.

Product Rankings scores and references are outside B3 and unchanged: `B4_PENDING_PRODUCT_SCORE_REFERENCE`.
