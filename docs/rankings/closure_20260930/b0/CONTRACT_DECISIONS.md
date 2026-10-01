# Rankings Bucket 0 contract decisions

Audit baseline: `80ed964161a3600d900624da6155a63b91962d74` on `audit/rankings-closure-b0-local-20260930`. This document freezes contracts; it does not authorize implementation.

## Public access field matrix

| Surface | Public fields | Protected fields | Decision |
|---|---|---|---|
| Era headline | `entityType`, `entityId`, `name`, `canonicalKey`, `modeledSetCount`, Overall `score`, `rank`, `cohortSize`, `tier`, `status`, `statusReason`; `marketDate`; benchmark key/calibration/model/publication identity and reference label/score | Financial, Chase, Collector, histories, component evidence, source lineage | Add a narrow public headline projection over the published Benchmark authority. Do not remove the guard from `/tcgs/pokemon/rankings/scorecards`, whose rows contain all four metrics. |
| Set headline | Era/Set identity, `logoImageUrl`, `symbolImageUrl`, Overall fields listed above, publication/scale context | Financial, Chase, Collector, family scores, simulation and detailed economics | Same narrow public headline projection. Artwork must be joined once in the scorecard identity query, not fetched per row. |
| Set Pack Economics preview | Set identity/artwork, `productFamilyCount`, `productCount`, `averagePackCostPerPack`, opening-economics date/status | EV, modeled return, recovery chance, entertainment cost, family/SKU expansion and Best-Open | Reuse the existing public opening-economics projection: `_BASE_OPENING_BREAKDOWN_FIELDS` already exposes identity/counts/average cost only. Do not publicize the current detailed `/rankings/pack-economics` response. |
| Product catalogue | `sealedProductId`, `productName`, `setId`, `setName`, `setCanonicalKey`, `productType`/normalized family, canonical route identity, optional product and Set artwork | Any rank, score, tier, delta, cohort, price, Best-Open or economics | Add a dedicated catalogue read ordered by normalized product name, Set name and stable ID. It must read the eligible exact-product identity universe directly, not ranked top-N rows. Existing base Product projection leaks `unitPrice`/`marketPrice` and is not this contract. |
| Unavailable state | `status=unavailable`, stable reason code, publication context when known, empty rows | Partial/stale paid data | Fail closed; never render zero as a score. |

Existing `/explore/rankings/lens/sets` has a useful allowlisted public Set projection, but its legacy `setRipV1` source is not the new Benchmark scorecard authority. The clean implementation is a new narrow public Benchmark-headline endpoint (or an explicit `headline` projection in the scorecard service) rather than weakening the paid scorecards endpoint.

## Product metric/reference decision table

| Display | Current authority | Raw scale/meaning | Rank cohort | Valid reference | Decision |
|---|---|---|---|---|---|
| Current Product `overallRipScore` | `budget_product_ranking_rows.overall_rip_v12_score` because the live snapshot has `ranked_under_v12_authority=true` | Absolute composite, 0–100. Live examples: 53.073, 51.2042, 50.7801. | Full Market whole-unit budget cohort; live 138 products, $1,300 ceiling | None on the current response | The current call to `benchmark_presentation(... reference=5.0)` is invalid. Do not divide by ten, clamp, or label 5.0 Overall. |
| Canonical Product Benchmark Overall | `pokemon_rip_benchmark_rows_v1`, key `pokemon_product_family_equal_weight_v1`, calibration `rip_product_benchmark_v1_fin5_overall5_family_mean` | Calibrated 0–10; family mean is exactly 5.0 | Within certified non-singleton product family; Overall rank uses existing family rank | Family-specific mean, score 5.0 | Source contract exists but live published header count was zero. It cannot currently back the page. |
| Product Financial absolute | ranking row Financial V4 on current V12 publication | Absolute model score, 0–100 | No canonical Financial family rank in the benchmark policy | Not generic 5.0 | Present as an absolute metric only with its model identity, or consume a published calibrated Financial benchmark row once available. |
| Product rank | `budget_rank_v12` | Ordinal | Full Market budget-constrained cross-format cohort | No numeric score reference | Label cohort and market date explicitly. |

Current live Product publication identity: snapshot `704a7e5a-2486-430e-9201-a13567ceacf6`, market/pinned date `2026-09-29`, comparison scope `budget_constrained_whole_unit_cross_format_v1`, Overall model `overall_rip_v12_86_financial_v4_04_chase_accessibility_v1_10_collector_appeal_v5`, Financial model `financial_rip_v4_outcome_profile_p95_only_25_20_15_25_10_5`, cohort 138.

Minimal additive contract: either publish the already-defined Product Benchmark authority and serve its per-product Overall rows with family reference identity, or keep the absolute Product score and introduce an explicit 0–100 presentation contract with a separately published reference. The former is preferred because the code and validation model already exist. Until publication exists, remove the false 5.0 comparison rather than inventing a replacement.

## Exact-SKU economics field matrix

| Field | Exact SKU authority | Status |
|---|---|---|
| Product purchase cost | `budget_product_ranking_rows.product_market_price`; pinned by snapshot/market date | Available |
| Unit quantity/committed capital | `quantity`, `actual_committed_capital` | Available; these describe the Full Market whole-unit strategy |
| Pack count | canonical simulation/product-family projection `packCount`, sourced from the exact sealed result | Available in the joined Product contract, not `sealed_products` |
| Expected value | `budget_product_ranking_rows.expected_value` for `quantity` units | Available |
| EV per pack | `expected_value / (quantity * packCount)` | Presentation arithmetic over exact persisted operands |
| Modeled return | `expected_value / actual_committed_capital` (`averageReturn`) | Available |
| Chance to recover | `chance_to_recover_capital` | Available, but semantics are for the published quantity strategy; do not relabel as a one-unit probability without a one-unit authority |
| Entertainment cost | No exact-SKU field in the prepared Product contract | Missing. Do not copy the family mean. Smallest addition: project the exact sealed-result cost-minus-EV value with run/date identity, or explicitly derive it from exact unit cost and exact unit EV under an approved definition. |
| Best-Open | `budget_product_best_open_price_rows` by `sealed_product_id` | Available and exact SKU |
| Best-Open comparison/status | current market price, status, gap dollars/percent | Available |
| Source dates | Product ranking market/pinned date; Best-Open `source_market_date` | Available independently; live Best-Open is `2026-09-08`, older than Product/opening data |

The current Set Pack Economics response has 22 Sets, 128 family rows and 138 exact Product children. Product children contain only identity, market price and Best-Open; all five economics columns render unavailable. Flattening can reuse existing Product prepared data for cost, pack count, EV/pack, modeled return and published recovery semantics without a migration, joined by `sealedProductId`. Exact entertainment cost needs the additive projection above. Family means must never be copied to children.

## Set artwork path

`sets.logo_image_url` and `sets.symbol_image_url` are real authorities. Live coverage is 174 logo / 174 symbol rows among 212 Sets. `SetIdentity` already implements logo -> symbol -> initials. Artwork is dropped in `read_scorecards`: its Set identity select requests only `id,name,canonical_key,era_id`; `scorecardSetTarget` then maps no artwork. The Pack Economics Set projection also emits no artwork. Product-family rows carry only a collapsed `setImage`; Product secondary identity does not render it. Card ranking facets select no Set artwork and Card rows render Set text only.

Fix the shared Set identity projection once: select and expose separate `logoImageUrl` and `symbolImageUrl`, preserve both through adapters, and reuse them in headline, Pack Economics, Product secondary identity and Card Set identity. No per-row fetches.

## MSRP

Repository-wide schema/code search found no stored MSRP, launch-price or retail-price field. The only `MSRP` occurrences explicitly prohibit using it as a fallback. `sealed_products` live shape contains identity, type and images only. Current market prices and retailer/listing prices are not MSRP.

MSRP is therefore unknown. A future additive contract requires exact SKU, currency/amount, manufacturer provenance URL/document, region, effective/launch date, retrieval date and confidence/status. No current asking price may populate it.
