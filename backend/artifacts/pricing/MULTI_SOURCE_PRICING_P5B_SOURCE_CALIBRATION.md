# P5B source calibration: TCGplayer vs eBayActiveAsk

Market date 2026-09-20 (P4 rows 2026-09-19). This is development evidence. Neither source is treated as ground truth: TCGplayer Market Price is a sales-based statistic, and eBayActiveAsk (frozen `ebay_active_ask_lower3_seller_median_v1`) is a landed active-ask quote. The P4C estimator, its eligibility policy and its source semantics were not modified; the frozen `estimate()` was called unchanged. Its replay fingerprint still matches the P4C freeze (`c1f8d167…`, asserted in a test).

Reproduce with `backend/scripts/p5b_cohort_builder.py`, `p5b_capture_batch.py`, `p5b_dataset.py`, `p5b_analysis.py` and `p5b_policy_evaluation.py`. Datasets: `p5b_paired_dataset.json` (150 rows), `p5b_analysis_summary.json`, `p5b_policy_evaluation.json`, `p5b_universe_2026-09-20.json.gz`.

## 1. Cohort composition (P5B.1)

150 targets: 30 from P4 (2026-09-19) plus 120 new in three batches of 40. The new batches used 836 Browse calls (270 + 289 + 277) with 0 failures and 0 retries, under the 1,000-call budget. P4 spent 195 calls on an earlier day. The batches used the P4A adaptive capture unchanged (shallow search, selective getItem), with the seller stop raised from 3 to 5 so SUFFICIENT depth is reachable.

The cohort is stratified but **not random**, and it was tilted after batch 1. Batch 1 (15% SUFFICIENT) showed that supply exists mostly in cheap bands, so batches 2–3 moved toward fresh cheap and mid-price cards. Pooled statistics therefore over-represent cheap cards; the segment tables below are the honest view.

| TCG status | Targets | | Price band (TCG) | Targets | SUFFICIENT |
|---|---:|---|---|---:|---:|
| fresh (≤1 day) | 105 | | < $5 | 34 | 10 |
| stale (≥2 days) | 23 | | $5–20 | 35 | 8 |
| missing | 22 | | $20–50 | 21 | 3 |
| | | | $50–100 | 11 | 1 |
| | | | $100–250 | 15 | 1 |
| | | | $250+ | 12 | 2 |
| | | | missing | 22 | 2 |

Structure: 75 rare/holo, 24 hit/special (illustration, secret, ultra, rainbow), 51 other. Era: 17 eras; 61 targets are pre-2007 vintage (E-Card 24, Gym 12, EX 11, Base/WOTC 8, NP 3, POP 2, Neo 1). Promos: only 4 of 150 targets (main 146), because most promo identities do not resolve to a variant. eBay depth over all 150 targets: 27 SUFFICIENT, 27 THIN, 96 INSUFFICIENT (18% sufficient).

Not achieved: balanced high-value coverage (4 of 38 cards ≥ $50 reached SUFFICIENT), promos (identity gaps, see policy freeze §6), and any thin-market vintage evidence beyond a handful of rows. Supply, not sampling, limited these.

Eligibility funnel across the 682 hydrated P5B listings: 233 eligible (34%), 354 CONDITION_EXCLUDED (52%), 81 LANGUAGE_UNRESOLVED (12%), 8 BUYING_FORMAT_EXCLUDED, 3 NON_ENGLISH_EXCLUDED, 3 CONDITION_UNRESOLVED. The frozen NM-compatible gate is the main sufficiency limiter. It was not retuned.

## 2. Paired sample (P5B.2)

**25 resolved cards have a TCGplayer price and a SUFFICIENT eBay estimate for the same variant** (6 from P4, 19 from P5B). The target was ≥ 40 and the hard gate was 30; **the sample is below both**. Consequences: no calibrated arithmetic blend and no calibrated conversion factor was fit or is justified. Six of the 25 cards have multiple NM-priced variants (e.g. holo and reverse); eBay evidence is card-level, not finish-level, so it is attached to the resolver-selected variant. Each paired row carries variant, condition (Near Mint), both prices and dates, ages, listing and seller counts, depth, difference and ratio (`p5b_paired_dataset.json`).

## 3. Source relationship (P5B.3)

| Segment | n | Median eBay/TCG | 95% bootstrap CI (median) | Median abs % diff |
|---|---:|---:|---|---:|
| **All paired** | 25 | 1.165 | 1.07–1.34 | 19.6% |
| < $5 | 10 | 1.50 | 1.23–3.67 | 50.0% |
| $5–20 | 8 | 1.11 | 0.87–1.20 | 14.9% |
| $20+ | 7 | 1.08 | 1.06–1.23 | 7.6% |
| Pre-2007 vintage | 4 | 0.98 | n/a (too small) | 13.0% |
| Modern | 21 | 1.23 | 1.08–1.46 | 23.5% |
| Hit/special | 14 | 1.13 | 1.06–1.34 | 13.1% |
| Rare/holo | 9 | 1.31 | 0.87–5.82 | 31.4% |
| TCG fresh | 21 | 1.13 | 1.06–1.29 | 16.5% |
| TCG stale | 4 | 1.47 | n/a | 46.9% |

Overall: mean ratio 1.70 (driven by two sub-$1 outliers at 5.8× and 9.4×), geometric mean 1.35, value-weighted ratio 1.10. Absolute percentage disagreement: P25 ≈ 8%, P50 ≈ 20%, P75 ≈ 46%, P90 ≈ 70%. Three rows were exact or near-exact (within 2%).

Findings:

- **Active-ask premium is not constant; it shrinks with value.** Median ratio 1.50 below $5, 1.11 at $5–20, 1.08 at $20+. Much of the sub-$5 premium is shipping: the landed ask includes shipping while TCGplayer Market Price excludes it. Subtracting each card's median shipping from the ask lowers the sub-$5 median from 1.50 to 1.10 and the ≥ $5 median from 1.09 to 1.03 (diagnostic only, not part of the estimator).
- **No stable conversion factor.** The interquartile ranges do not overlap across bands (< $5: 1.31–1.70; ≥ $5: 1.06–1.16), so a single factor would misprice one side.
- **Thin markets are not visibly noisier.** The low-three-median log-ratio SD was 0.54 for THIN rows (n=26) and 0.54 for SUFFICIENT rows (n=25). This rests on small groups and a shipping-dominated cheap-card tail, so it says nothing about thin markets in general.
- **Stale TCG prices disagree more** (median |Δ| 47% vs 16.5%), but 3 of the 4 stale pairs are under $5, so freshness is confounded with the shipping effect. It is not established.
- **High-value cards:** the four paired cards ≥ $50 agreed to +5.8%, +7.3%, +9.3% and +34.2% (Evolving Skies Rare Rainbow, $312.61 vs $419.43). No severe disagreement occurred at ≥ $20, but n=7.
- **Vintage** (n=4) looked closer to 1.0, but four rows support no claim.

No segment-specific factor was created from any cell.

## 4. Estimator stability (P5B.4)

Run on the 25 paired SUFFICIENT rows by re-calling the frozen estimator on perturbed inputs.

- **All 25 have exactly 5 sellers.** Removing any single listing or seller downgrades every card to THIN. SUFFICIENT sits at the depth cliff, so eBay availability is fragile day to day.
- Dropping the lowest seller moves the estimate by a median of 4.4% (max 34.8%). Dropping any one seller: median of per-card maxima 4.4%, P75 8.4%, P90 17.4%, max 34.8%. Dropping one of the three contributing asks: max 34.8%.
- Alternative tie ordering leaves the price unchanged in 25 of 25.
- Sensitivity here is a source-confidence input, not a retune: the per-card leave-one-seller-out shifts anchor the agreement bands in the policy freeze.

## 5. TCGplayer freshness (P5B.5)

Age = market date minus last observed date, over 19,813 priced canonical cards on 2026-09-20.

| Age (days) | Cards | | Age (days) | Cards |
|---|---:|---|---|---:|
| 0 | 3,767 | | 8–14 | 5 |
| 1 | 15,852 | | 15–30 | 18 |
| 2–4 | 4 | | 31–60 | 88 |
| 5–7 | 9 | | 61–120 | 51 |
| | | | > 120 | 19 |

Median, P75, P90, P95 and P99 are all 1 day; maximum 162 days. 99.02% are ≤ 1 day, consistent with a daily scrape whose newest observation is at most one day behind. A 13-card shoulder covers 2–7 days, and a 181-card long tail runs ≥ 8 days, most beyond 30. Freshness follows `last_observed_date`, which advances on unchanged-price heartbeats (P5A closure), so it measures observation age, not price-change age. The 8-day boundary is a judgment: there is a real gap after day 1 but the tail is continuous, so ≥ 8 vs 2–7 is a calendar-week choice rather than a natural break.

## 6. Disagreement distribution (P5B.6)

Bands are frozen in the policy freeze. Distribution over the 25 pairs: 13 AGREE, 9 MODERATE, 3 SEVERE. All three SEVERE are under $5 (two fresh, one stale); the moderate cases include the $312.61 Evolving Skies card. The agreement bands come from the eBay estimator's leave-one-seller-out noise and a shipping tolerance, not from where the pairs happen to fall.

## 7. Limits

25 pairs; non-random, cheap-tilted; six multi-variant cards; two sub-$1 outliers dominate the mean; no completed-sale ground truth. The analysis characterizes disagreement; it does not show either source is more accurate.
