# Rankings Redesign — Bucket 1 DB/Data Authority Closure

Date: 2026-09-28  
Starting develop: `0019c2bcd8a701cbcdd530fb837d9431963106e7`

## Financial history

The pre-existing `financial_rip_history_db_v1` migration is a query/guard layer over complete Benchmark V1 publications. It cannot legally manufacture older partial Benchmark publications from leaderboard-only evidence.

Bucket 1 therefore adds a separate Financial-only authority over immutable canonical leaderboard snapshots. Semantic `market_date` is the persisted row `source_market_date`, never the leaderboard wrapper date. This yields 12 exact dates:

- 2026-08-22
- 2026-08-24
- 2026-08-25
- 2026-08-26
- 2026-09-08
- 2026-09-12
- 2026-09-13
- 2026-09-14
- 2026-09-15
- 2026-09-25
- 2026-09-27
- 2026-09-28

Every date has 22 Set rows, 2 Era rows and one equal-Set Overall Financial RIP reference. The 2026-09-17 leaderboard wrapper resolves to 2026-09-15 source data and is retained as an exact duplicate candidate, not a second chart point. The 2026-09-26 wrapper resolves to 2026-09-25 and becomes the 2026-09-25 history point.

Published Benchmark overlap at 2026-09-15, 2026-09-25 and 2026-09-27 matches the dedicated Financial reference within 1e-8.

Daily continuation is statement-triggered from canonical leaderboard snapshot/row publication into an idempotent classifier/backfill function. Non-V4, incomplete, ambiguous and insufficient-evidence candidates remain classified but unpublished. Gaps remain gaps.

## Best-Open

No additional schema is required. Current exact authority is `budget_product_best_open_price_latest` + `budget_product_best_open_price_rows`.

Current stored cohort:
- 22 Sets
- 138 unique products
- 138 products with Best-Open thresholds
- 10 Set/family groups contain multiple SKUs (20 products total)

The backend contract must keep exact product rows. A family with one SKU may surface its scalar threshold; a multi-SKU family must expose a `products[]` expansion and must never average or silently select one threshold.

The 138-row current join executes in ~0.57 ms in production. No convenience view/RPC is justified.

Freshness caveat: Best-Open source market date is 2026-09-08 while Opening Economics is 2026-09-28. Consumers must expose/handle this freshness difference rather than presenting the threshold as same-day.

## Card facets

Generation-keyed prepared facets were added for the current ranking authorities.

Collector V7 (2026-09-11):
- 16 Eras
- 155 Sets
- 33 rarities
- 3 subject types

Chase (2026-09-28):
- 2 Eras
- 22 Sets
- 14 rarities

This intentionally exposes separate lens support rather than pretending Chase supports the Collector universe. A Collector Set facet read returns 155 rows in ~0.14 ms and reads only the prepared generation, not all 18,293 card rows.

## Collector cross-domain audit

Production global card ranking literally sorts all scored cards by raw Collector Appeal.

Current distributions show materially different domain scales/ceiling behavior:
- Pokémon: n=15,639, mean 54.6846, median 52.4359, std 14.6675, p95 85.3485, p99 94.1035, max 97.1481, score=100 count 0.
- Trainer: n=811, mean 48.2554, median 47.0158, std 31.8368, p95 95.4155, p99 100, max 100, score=100 count 12.
- neutral_functional: n=1,843, mean 52.0171, median 51.1218, std 2.4939, p95 58.5070, p99 59.5375, max 61.2640.

Current global top composition is Trainer 10/10, 25/25, 38/50 and 40/100.

Model construction:
- Pokémon subject baseline is a 75% fan / 25% Trends composite, then V6 playability can consume 20% of remaining headroom.
- Trainer baseline comes from Trainer subject authority, then the same playability-headroom form is applied where evidence exists.
- V7 Artist can consume 10% of remaining headroom.
- neutral_functional begins from a fixed 50 baseline and receives functional/playability treatment only.

Frozen V7 price validation supports both Pokémon and Trainer subject signals within the controlled 22-Set cohort, but does not establish literal cross-domain raw-scale equivalence.

Decision: `CROSS_DOMAIN_CALIBRATION_CANDIDATE_REQUIRED`.

A monotonic subject-domain cume-dist shadow candidate is frozen at `docs/research/collector_cross_domain_calibration_shadow_v1.json`. It is diagnostic only and is not promotion-ready. No Collector production score/rank was changed.

## Security/performance

New tables have RLS enabled, explicit service-role policies, and no anon/authenticated/public table access. New functions are `SECURITY INVOKER`; public/anon/authenticated execute is revoked. The facets view is `security_invoker=true`.

Advisor review found no new exposed-data/function-security finding attributable to these objects. Project-wide advisor output still contains pre-existing RLS/no-policy, unused-index and duplicate-index findings outside this bucket.

## Verification

Production assertions:
- 15/15 integration/data-authority invariants passed.
- 9/9 classification/contract behavior checks passed.
- Financial refresh rerun inserted 0 new publications: idempotency confirmed.
- Final Financial authority: 12 publications / 288 rows (264 Set + 24 Era).
