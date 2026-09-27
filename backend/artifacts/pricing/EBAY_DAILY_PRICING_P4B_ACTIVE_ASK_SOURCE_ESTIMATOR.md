# P4B: active-ask source-estimator development

Market date: 2026-09-19. Source semantic name: `eBayActiveAsk`. All figures are **active fixed-price asks**, not sold transactions. No TCGplayer/eBay blending or inDex Fair Value was implemented.

## Development data and provenance

The 30-card, 15-era P4A cohort and targeted seller-depth extension used 195 Browse calls. The [analysis artifact](ebay_p4b_97cff77b2a1c4b3e9c5d9cfc862d1c8c.json) has fingerprint `804992a0eb9dc3912bbb0124f55ff87d1bbfb4a73e9cad1ae56c8dd1f056d8de`. It records per card the pricing run, canonical/variant IDs, eligible item IDs, seller keys, landed asks, eligibility-policy fingerprint, candidate estimators, depth, benchmark comparisons, and a calculation fingerprint. The [candidate implementation](../../scripts/evaluate_ebay_p4b_active_ask.py) reads only local development artifacts and writes only this analysis artifact.

There were 58 English/NM/fixed/landed eligible listings after the extension, on 18 cards. The other twelve cards had zero eligible asks. Ten cards reached at least three distinct eligible sellers; eight reached five, of which six had a resolved variant ID. The five-seller cards span seven eras: five low-price, one mid-price, and two missing-TCGplayer cards. No high-value card reached five sellers; one high-value card reached three. Depth states under the candidate rule: **8 SUFFICIENT, 2 THIN, 20 INSUFFICIENT**. A source estimate is null for thin/insufficient cards and for cards lacking a variant ID.

## Estimator candidates and depth

The analysis compares lowest landed ask, median of the lowest three seller-distinct asks, median of the lowest five, seller lower quartile, median of the lower half, all-listing median, and all-seller median. One cheapest ask per seller is retained before seller-based estimators; this prevents repeat listings by one seller from occupying several competitive slots. The candidate source estimator is **median of the lowest three seller-distinct landed asks**, version `ebay_active_ask_lowest_three_seller_median_candidate_v1`. It reflects executable competitive offers without the single-listing fragility of the minimum or the aspirational high-tail influence of the overall median. No global dollar-value outlier cutoff is used. The three-ask median resists one extreme low or high observation, and the input list remains auditable.

| Seller depth | Candidate outcome |
| ---: | --- |
| 1 or 2 | INSUFFICIENT; no estimate |
| 3 or 4 | THIN; diagnostic candidate only |
| At least 5 | SUFFICIENT only when removing any one seller changes the lowest-three median by at most 25%; a resolved variant is also required for a source row |

For the eight five-seller cards, maximum leave-one-seller-out changes ranged from 0% to 22.0% (mean 8.9%). The highest ask did not control the lowest-three statistic. A seller with many listings did not dominate the estimator by construction. In this live cohort, all-listing and all-seller medians happened to coincide per card because no seller contributed multiple **eligible** rows for the same card; synthetic tests show the two can diverge. Thus live seller-concentration sensitivity is limited.

The six five-seller cards with TCGplayer benchmarks had eBay/TCGplayer ratios of **0.87, 1.09, 1.31, 1.47, 5.82, and 9.40**; median ratio **1.39**, median signed bias **+39%**, and median absolute percentage difference **39%**. Per-card max/min eligible-ask dispersion ranged from 1.19× to 3.42×. The two extreme ratios occur on very low TCGplayer prices where fixed shipping and minimum viable eBay asks matter. The benchmark is a comparison, not label truth and not an optimization target. The six benchmarked sufficient-depth cards span Base/WOTC, EX, XY, Sun and Moon, Sword and Shield, and Mega Evolution eras, but are concentrated in low and mid price bands. The missing-price cards lack resolved variants, and the high-value band remains too thin. The source signal is therefore a bounded development candidate, not a general daily source authority.

## Price Storage V2 publication gate

**No `eBayActiveAsk` observation, event, or current row was written.** Inspection of the live `get_pokemon_canonical_card_market_prices_latest_for_set_v2_shadow(uuid)` definition (MD5 `cc4e5d8db648ae92772e65f42ee6f934`) found its lateral `card_variant_price_current_v2` selection filters Near Mint, USD, variant, and positive price, but **does not filter `source='TCGPlayer'`**. A direct function-text check found no `current_row.source =` predicate (position 0) and found the latest-observed-date ordering (position 6159). Adding a same-day `eBayActiveAsk` current row could therefore change canonical selected prices and public downstream values. The user explicitly forbids altering the canonical resolver and public price authority in P4. Writing only a raw observation would also risk a later V2 rebuild creating a current row through the existing source-dimensional path. This is a concrete fail-closed blocker, independent of the estimator's local numerical stability.

P4 source-level publication additionally lacks high-value five-seller validation, live IMAGE-v2/OCR-v3 veto coverage for this new cohort, and P3 DB ingestion of the new item-detail capture. The next safe step is an explicit source-isolation migration and validation plan, authorized in a later scope, that preserves TCGplayer canonical selection before any eBay V2 write. At that point the estimator needs an atomic provenance record keyed by `(card_variant_id, condition_id, source, currency, effective_date)` with its run ID, eligible item IDs, policy/estimator versions, seller/listing counts, landed inputs, and calculation fingerprint. Replay must return the same row for the same fingerprint and reject a changed fingerprint rather than rewriting the day. No such publication machinery or source row was introduced here.

Focused P1–P4 regression tests: **41 passed**. They cover request allocation and stopping, the shared daily ledger, English and NM evidence, seller deduplication, minimum depth, deterministic calculation, outlier behavior, disappearing-seller sensitivity, and provenance. The P4 source code contains no canonical pricing-table write path. Because the source-isolation gate failed, no live shadow write was attempted and TCGplayer, Set Value, simulations, and Market Explorer were left untouched by this task.

EBAY_ACTIVE_ASK_SOURCE_ESTIMATOR_NOT_READY_CANONICAL_RESOLVER_SOURCE_ISOLATION
