# Set-Level Chase Efficiency — Stage I Foundation Study

**Research decision: `SET_CHASE_EFFICIENCY_FOUNDATION_SUPPORTED_WITH_REVISIONS`**

| | |
|---|---|
| Market date | 2026-08-28 |
| Cohort | 21 of 22 simulation-supported Pokémon sets |
| Packs simulated | 1,000,000 per set (21,000,000 total), seeded and reproducible |
| Research version | `set-chase-efficiency-stage1-v1` |
| Calculation version | `basket-conditional-value-times-any-hit-hazard-over-pack-cost-v1` |
| Probability source | `monte_carlo_v2_pack_decomposition` |
| Artifact | `docs/research/set_chase_efficiency_stage1.json` (3.4 MB, all raw components) |
| Production impact | **None.** No score, ranking, snapshot, migration or endpoint was changed. |

Reproduce with:

```
python -m backend.scripts.build_set_chase_efficiency_research --packs 1000000
python -m backend.scripts.report_set_chase_efficiency_research
python -m pytest backend/tests/unit/research/test_set_chase_efficiency.py    # 58 passed
```

---

## 1. Existing-system audit

### 1.1 Individual-card Chase Efficiency (exists, published, canonical)

| Concern | Location |
|---|---|
| Pure mathematics | `backend/domain/pokemon/chase_efficiency.py` |
| Authority resolution + publication | `backend/db/services/chase_efficiency_service.py` |
| Read path | `backend/db/services/chase_efficiency_query_service.py` |
| CLI | `backend/scripts/publish_chase_efficiency.py`, `backend/scripts/audit_chase_efficiency_publication.py` |
| Storage | `pokemon_card_chase_efficiency_snapshots` / `_rows` / `_latest` |
| API | `frontend/app/api/tcgs/pokemon/sets/[setId]/cards/[cardId]/chase-efficiency/route.js` |
| Gate | `backend/tests/unit/api/test_chase_efficiency_premium_gate.py` |

The formula in `chase_efficiency()` is exactly

```
CE_card = (target_value / best_verified_pack_equivalent_cost) × [−ln(1 − p)]
```

with `p = 1 / effective_pull_rate`, `-log1p(-p)` for numerical stability, and `p = 1` refused rather than stored as infinity. **The candidate set-level form in the brief is the same hazard functional**, which is what makes card-level and set-level CE commensurable.

Contract versions in force: `pokemon-chase-efficiency-v1`, `value-times-hit-hazard-over-best-pack-cost-v1`, `best-verified-pack-equivalent-cost-v1`.

### 1.2 Authority chain (verified against code and DB, not notes)

| Input | Authority | Notes |
|---|---|---|
| Supported cohort | `sets.supports_opening_simulation = true` (22 rows) | |
| Current authoritative run | `evaluate_opening_simulation_freshness` → `explore_rip_statistics_latest.calculation_run_id` | the card-CE service uses the view; the research cohort resolver uses the freshness evaluator, which is stricter |
| Card pull probability (analytic) | `simulation_input_cards.effective_pull_rate` (one-in-N) | derived in `PackEVCalculator.calculate_effective_pull_rate` |
| Card pull probability (empirical) | `simulation_card_variant_pull_rates.modeled_probability` = `pack_presence_count / simulation_count` | added 2026-08-27; **a second authority** |
| Pack-state / collation model | `backend/simulations/utils/packStateModels/*`, consumed by `make_simulate_pack_fn_v2` | |
| Simulator | `backend/simulations/monteCarloSimV2.py` (`make_simulate_pack_fn_v2`, `run_simulation_v2`) | |
| Card market price | `EVRInputPreparationService.prepare_for_set` → `card_market_usd_latest_by_condition` (NM) | supplies **current** prices, with `captured_at` per row |
| Product price / pack-equivalent cost | `simulation_sealed_product_results.product_market_cost / random_pack_count`, composition-verified | |
| Existing chase ranking work | `backend/db/services/chase_economics_service.py`, `backend/domain/pokemon/target_chase_economics.py`, `pokemon_set_chase_economics_snapshot_latest`, `pokemon_set_top_chase_card_daily_history` | single-card journey economics; `DEFAULT_PUBLISHED_CARD_LIMIT = 25`, `SELECTION_POLICY = "top_market_price_pullable"` |

### 1.3 Reusable components this study consumed rather than duplicated

* `backend/research/ev_representativeness/recorder.py` — `PackDecompositionRecorder` / `PackDecomposition`. Strictly observational sampling observer; `pack_values`, `pack_max_entity_value`, `pack_entity_presence` re-value the recorded draw sequence under any price vector. **This is the component that makes exact basket probability possible.**
* `backend/research/ev_representativeness/tier_b.py` — the pattern for a seeded, instrumented re-simulation, including the completeness gate.
* `backend/db/services/ev_representativeness_service.resolve_research_cohort` — cohort + freshness authority.
* `backend/db/services/evr_input_preparation_service.EVRInputPreparationService` and `backend/jobs/evr_runner._resolve_set_config` — the same input assembly production uses.
* `backend/simulations/variant_pull_summary.py` — the entity → `card_variant_id` mapping rule (base price column ⇒ `card_variant_id`, reverse column ⇒ `reverse_variant_id`), replicated in `runner.entity_identities`.

### 1.4 Discrepancies found (code/DB authoritative, notes not)

1. **Two probability authorities disagree on 130 of 4,879 card-variants (2.7 %)** by more than 25 %. Aggregate agreement is good (median ratio `sim/analytic` = 0.985). **Every disagreement is on a card priced ≤ \$12.92**; there are **zero** disagreements above \$20, so no meaningful chase card is affected. The empirical figure is higher in 97 of the 130 cases.
2. **The published card-level CE snapshot is one market day stale.** `pokemon_card_chase_efficiency_snapshots` latest = `2026-08-27` (published, 4,862 eligible / 17 excluded / 22 sets) while the current promoted market date and the authoritative simulation cohort are `2026-08-28`.
3. **Destined Rivals is broken, not merely stale.** Its latest run (`2925570c-…`, dated 2026-08-29 — *ahead* of the promoted market date) **has no `simulation_run_summary` row**, so the freshness evaluator marks it `invalid`. This is a persistence defect independent of this study; it costs the cohort one set.
4. **`simulation_pack_outcome_artifacts` stores per-pack totals only** (a numeric value array), not card composition. Combined with (1) storing only marginals, **no stored table can answer a basket question** — which is why this study re-simulates.
5. `chase_efficiency_service.load_candidate` derives freshness by string-comparing `captured_at[:10]` to the market date. Correct, but it means a set whose prices are all stale would silently produce an empty cohort rather than a flagged one.

---

## 2. Data coverage report

**Cohort: 21 analysed / 22 supported.** Excluded: **Destined Rivals** — reason `no_simulation_run_summary_row_for_latest_calculation_run` (see 1.4.3).

All 21 analysed sets had a complete authoritative run at 1,000,000 simulations, a usable verified pack-equivalent cost, and NM prices captured on 2026-08-28.

| Set | Drawable | Eligible | Excluded | ≥\$20 | ≥\$50 | Max \$ | Pack \$ |
|---|---:|---:|---:|---:|---:|---:|---:|
| Ascended Heroes | 468 | 459 | 9 | 27 | 21 | 1052.30 | 13.79 |
| Black Bolt | 407 | 403 | 4 | 45 | 12 | 616.70 | 14.81 |
| Chaos Rising | 198 | 196 | 2 | 7 | 3 | 184.57 | 5.22 |
| Journey Together | 333 | 331 | 2 | 5 | 2 | 104.73 | 6.58 |
| Mega Evolution | 310 | 310 | 0 | 15 | 9 | 267.34 | 8.07 |
| Obsidian Flames | 406 | 406 | 0 | 7 | 1 | 109.07 | 10.16 |
| Paldea Evolved | 455 | 455 | 0 | 25 | 10 | 382.18 | 13.07 |
| Paldean Fates | 326 | 324 | 2 | 15 | 6 | 964.98 | 23.11 |
| Paradox Rift | 428 | 428 | 0 | 19 | 4 | 120.02 | 7.56 |
| Perfect Order | 203 | 203 | 0 | 7 | 4 | 130.45 | 4.74 |
| Phantasmal Flames | 214 | 214 | 0 | 5 | 2 | 703.07 | 11.08 |
| Pitch Black | 194 | 194 | 0 | 7 | 4 | 212.90 | 4.75 |
| Prismatic Evolutions | 448 | 447 | 1 | 34 | 17 | 1472.79 | 14.86 |
| Scarlet and Violet 151 | 361 | 361 | 0 | 20 | 13 | 373.61 | 29.81 |
| SV Base Set | 446 | 442 | 4 | 12 | 2 | 72.82 | 8.22 |
| Shrouded Fable | 168 | 168 | 0 | 18 | 4 | 74.80 | 8.91 |
| Stellar Crown | 300 | 300 | 0 | 5 | 3 | 112.88 | 8.72 |
| Surging Sparks | 417 | 417 | 0 | 12 | 4 | 290.59 | 7.75 |
| Temporal Forces | 358 | 358 | 0 | 20 | 8 | 95.89 | 8.64 |
| Twilight Masquerade | 373 | 373 | 0 | 12 | 5 | 373.17 | 8.75 |
| White Flare | 405 | 405 | 0 | 39 | 10 | 567.98 | 13.53 |

**Card exclusions: 24 of 7,530 drawable entities (0.32 %)**, all one reason code:

* `price_basis_not_current_market_date` — 24. Capture dates range 2026-06-09 to 2026-08-17. **Highest excluded price is \$2.79**, so no exclusion touches any chase basket at any tested definition. Most are `Professor's Research` printings (a known stale-price cluster) plus a handful of AH commons.
* `missing_card_variant_identity` — 0.
* `non_positive_market_price` — 0.
* `unreachable_in_simulation` — 0. Every drawable entity was drawn at least once in 1,000,000 packs.

**Variant / printing ambiguity: none, structurally.** The unit of analysis is the sampling entity `(source_row, price_column)`, which *is* the exact printing: base column ⇒ `card_variant_id`, reverse column ⇒ `reverse_variant_id`, each with its own price. The chase universe is therefore exactly the set of things the simulator can produce, so a card cannot be priced as one printing and pulled as another.

**Market-date alignment.** All eligible prices captured 2026-08-28; all product prices `price_as_of = 2026-08-28`; all runs dated 2026-08-28. Destined Rivals' run at 2026-08-29 is *ahead* of the promoted date and is excluded anyway.

**Acquisition cost.** `C` = cheapest **verified** pack-equivalent cost across all sealed products for the run, the same rule the published card-level CE applies. This is frequently **not** the loose pack: Phantasmal Flames \$11.08 (booster box) vs \$11.61 loose; Obsidian Flames \$10.16 vs \$12.98; 151 \$29.81 (bundle) vs \$29.90. Every candidate route is retained in the artifact.

---

## 3. Basket probability: the method, and why it was necessary

`p_S` is measured, never assembled. For each basket the mask over sampling entities is applied to the recorded draw sequence and three per-pack vectors are re-derived from the *same* paths: qualifying copies, qualifying total value, best qualifying value. Mutually exclusive pack states, the without-replacement rule across variable slots, pattern overlays, and both special-pack entry paths are honoured exactly because they were *observed*.

Validation, all 21 sets, every basket: **`P(≥1) = 1 − P(0)` holds with zero failures**, and the recorder reproduced every simulated pack value to ≤ 1.4e-14.

**Necessity is quantified.** Comparing the observed joint against the two wrong shortcuts:

| Set | K | observed `p_S` | naive Σ card odds | independence | Σ/observed |
|---|---:|---:|---:|---:|---:|
| Prismatic Evolutions | 5 | 0.00459 | 0.00669 | 0.00667 | **1.456** |
| Prismatic Evolutions | 20 | 0.01630 | 0.02135 | 0.02114 | **1.310** |
| Ascended Heroes | 20 | 0.02053 | 0.02263 | 0.02240 | 1.102 |
| Phantasmal Flames | 20 | 0.14397 | 0.14879 | 0.13895 | 1.033 |
| SV 151 | 20 | 0.10217 | 0.10439 | 0.09938 | 1.022 |
| Paldea Evolved | 20 | 0.04243 | 0.04243 | 0.04159 | 1.000 |

Summation overstates `p_S` by up to **45.6 %**. The error is *not* uniform: it is largest exactly in the sets with multi-hit mechanics (Prismatic's god packs put up to **9** Top-10 members in one pack; Ascended Heroes up to 6), i.e. the sets whose chase economics anyone would most want to compare. A closed-form approximation would have biased the interesting cases hardest.

Multi-chase openings are real but rare: `P(≥2 | Top-10)` ranges 0 (7 sets, `maxInPack = 1`) to 0.00086 (Prismatic).

---

## 4. Initial Set Chase Efficiency rankings

`V_S` = conditional arithmetic mean of **total** qualifying value. Full tables with every raw component are in the artifact; the report script prints Top-1/3/5/10.

### Top-1

| # | Set | CE | pack\$ | `p_S` | `V_mean` | packs/hit | 50 % packs | 50 % spend |
|--:|---|---:|---:|---:|---:|---:|---:|---:|
| 1 | Phantasmal Flames | 0.1606 | 11.08 | 0.00253 | 703.07 | 396 | 274 | \$3,036 |
| 2 | Prismatic Evolutions | 0.1348 | 14.86 | 0.00136 | 1472.79 | 736 | 510 | \$7,579 |
| 3 | Pitch Black | 0.0958 | 4.75 | 0.00214 | 212.90 | 468 | 325 | \$1,544 |
| 4 | Paldean Fates | 0.0889 | 23.11 | 0.00213 | 964.98 | 470 | 326 | \$7,534 |
| 5 | Stellar Crown | 0.0767 | 8.72 | 0.00590 | 112.88 | 169 | 118 | \$1,029 |
| 8 | **Scarlet and Violet 151** | 0.0594 | 29.81 | 0.00473 | 373.61 | 212 | 147 | \$4,382 |
| 9 | **Ascended Heroes** | 0.0565 | 13.79 | 0.00074 | 1052.30 | 1351 | 937 | \$12,921 |
| 20 | Perfect Order | 0.0166 | 4.74 | 0.00060 | 130.45 | 1658 | 1150 | \$5,446 |
| 21 | Mega Evolution | 0.0138 | 8.07 | 0.00042 | 267.34 | 2398 | 1662 | \$13,412 |

### Top-10

| # | Set | CE | pack\$ | `p_S` | `V_mean` | `V_med` | packs/hit | 50 % packs | 50 % spend | top-1 share |
|--:|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 1 | Prismatic Evolutions | 0.3606 | 14.86 | 0.00855 | 623.83 | 296.46 | 117 | 81 | \$1,204 | 0.375 |
| 2 | Pitch Black | 0.3013 | 4.75 | 0.03273 | 43.00 | 15.90 | 31 | 21 | \$100 | 0.323 |
| 3 | **Ascended Heroes** | 0.2574 | 13.79 | 0.00737 | 479.70 | 349.37 | 136 | 94 | \$1,296 | 0.220 |
| 4 | Phantasmal Flames | 0.2469 | 11.08 | 0.04389 | 60.95 | 19.01 | 23 | 16 | \$177 | 0.664 |
| 5 | Shrouded Fable | 0.2319 | 8.91 | 0.04174 | 48.46 | 49.08 | 24 | 17 | \$151 | 0.204 |
| 6 | Perfect Order | 0.2314 | 4.74 | 0.03207 | 33.62 | 19.46 | 31 | 22 | \$104 | 0.225 |
| 9 | **Scarlet and Violet 151** | 0.2043 | 29.81 | 0.04893 | 121.38 | 93.19 | 20 | 14 | \$417 | 0.297 |
| 21 | White Flare | 0.1118 | 13.53 | 0.00999 | 150.64 | 78.27 | 100 | 70 | \$947 | 0.266 |

Monte Carlo error is reported per basket. It is material only for Top-1: `SE(p_S)` on Mega Evolution's Top-1 is 2.0e-5 on `p_S` = 4.2e-4, a **4.8 % relative error**. Top-1 rankings must not be read as exact.

---

## 5. Chase Frontier and diminishing returns

**`CE(K)` rises monotonically in 20 of 21 sets** and reaches a mere plateau (final marginal gain < 5 %) in exactly one (Prismatic Evolutions). **No set produces an interior peak.**

| Set | K=1 | K=3 | K=5 | K=10 | K=15 | K=20 |
|---|---:|---:|---:|---:|---:|---:|
| Pitch Black | 0.0958 | 0.1693 | 0.2159 | 0.3013 | 0.3568 | **0.3983** |
| Prismatic Evolutions | 0.1348 | 0.2131 | 0.2692 | 0.3606 | 0.3846 | 0.3996 |
| Shrouded Fable | 0.0465 | 0.0919 | 0.1574 | 0.2319 | 0.3170 | 0.3539 |
| Ascended Heroes | 0.0565 | 0.1509 | 0.1976 | 0.2574 | 0.2929 | 0.3289 |
| SV 151 | 0.0594 | 0.0994 | 0.1341 | 0.2043 | 0.2552 | 0.2876 |
| Mega Evolution | 0.0138 | 0.0489 | 0.0903 | 0.1273 | 0.1803 | 0.2097 |
| White Flare | 0.0296 | 0.0698 | 0.0840 | 0.1118 | 0.1328 | 0.1500 |

### 5.1 This is provable, not empirical accident

With `V_S` = conditional **mean** of total qualifying value, the identity `V_S · p_S = E_S` holds, where `E_S` is the *unconditional* expected qualifying value per pack. Substituting into the candidate form:

```
CE = (V_S / C) · h(p_S)  =  (E_S / C) · [ h(p_S) / p_S ] ,    h(p) = −ln(1−p)
```

`h(p)/p ≥ 1` and is strictly increasing in `p` (verified: 1.00005 at p=1e-4, 1.0536 at p=0.1, 4.652 at p=0.99). Adding **any** card with a positive price strictly increases `E_S` and weakly increases `p_S`. **Therefore CE strictly increases under every basket expansion, without exception.**

The limit is the degenerate one: take the basket to the whole set and `CE → (pack EV / C) · (h/p)`, i.e. a monotone transform of expected value over cost — precisely the quantity Set Chase Efficiency was defined to be distinct from. This is encoded as a deliberately-passing regression test, `test_conditional_mean_chase_efficiency_is_monotone_under_basket_expansion`.

The convergence is visible in the data. Spearman correlation of `CE_K` against the set's mean pack value / pack cost:

| K | 1 | 3 | 5 | 10 | 15 | 20 |
|---|---:|---:|---:|---:|---:|---:|
| ρ(CE, EV/C) | **+0.045** | +0.105 | +0.365 | +0.548 | +0.636 | **+0.703** |

At K=1 the metric is essentially orthogonal to EV/cost. By K=20 it is most of the way to being the same statistic. **The metric's independence from existing financial measures is a function of the arbitrary K, not of the construct.**

### 5.2 The ranking is not K-stable

Spearman between Top-K rankings (mean-based):

| | K=1 | K=3 | K=5 | K=10 | K=15 | K=20 |
|---|---:|---:|---:|---:|---:|---:|
| **K=1** | 1.000 | 0.871 | 0.805 | 0.706 | 0.594 | **0.516** |
| **K=5** | 0.805 | 0.910 | 1.000 | 0.936 | 0.853 | 0.800 |
| **K=10** | 0.706 | 0.804 | 0.936 | 1.000 | 0.962 | 0.931 |
| **K=20** | 0.516 | 0.583 | 0.800 | 0.931 | 0.991 | 1.000 |

ρ(K=1, K=20) = 0.516. Choosing K choooses the answer. Rankings do stabilise for K ≥ 10 (ρ ≥ 0.93 among K=10/15/20), which is the one encouraging note here.

### 5.3 `V_S` choice moves rankings materially

Spearman against the mean-based ranking:

| Basket | median | winsorized mean | trimmed mean | mean(best) | median(best) |
|---|---:|---:|---:|---:|---:|
| Top-1 | 1.000 | 1.000 | 1.000 | 1.000 | 1.000 |
| Top-3 | **0.478** | 1.000 | 0.986 | 0.999 | 0.478 |
| Top-5 | **0.623** | 1.000 | 0.948 | 0.999 | 0.623 |
| Top-10 | **0.453** | 0.996 | **0.621** | 0.996 | 0.453 |

The mean, winsorized mean and best-card mean are near-interchangeable. The **median is a different metric** (ρ ≈ 0.45–0.62) — and it is the only family that produces interior optima (3 interior peaks, 13 "inconsistent" at Top-K). But its `CE(K)` curves are erratic rather than economically shaped: Phantasmal Flames runs 0.1606 → 0.0200 → 0.0379 → 0.0770 → 0.0486 → 0.0682. That is the median jumping between a \$703 card and a \$21 card, not a chase optimum. **The median breaks the degeneracy without supplying a defensible cutoff.**

### 5.4 Threshold baskets do not rescue it

Basket sizes at fixed dollar floors span an order of magnitude across sets (at ≥\$10: Chaos Rising 8 vs White Flare 110; at ≥\$100: five sets have zero). Cost-multiple baskets are better behaved but still range 3–28 members at 2×C and leave 5 sets empty at 10×C. **No threshold produces a comparably-sized chase universe across sets**, so an absolute floor trades K-arbitrariness for threshold-arbitrariness.

---

## 6. Chase concentration

Concentration is measured on **value actually delivered** per member across the run (pull count × price), so it carries both reachability and worth.

| Set | top-1 | top-3 | top-5 | rest | HHI | effective N |
|---|---:|---:|---:|---:|---:|---:|
| Phantasmal Flames | 0.664 | 0.813 | 0.909 | 0.091 | 0.459 | **2.18** |
| Paldean Fates | 0.530 | 0.783 | 0.883 | 0.117 | 0.322 | 3.10 |
| Stellar Crown | 0.354 | 0.746 | 0.848 | 0.152 | 0.248 | 4.03 |
| Prismatic Evolutions | 0.375 | 0.592 | 0.748 | 0.252 | 0.191 | 5.23 |
| Ascended Heroes | 0.220 | 0.588 | 0.769 | 0.231 | 0.147 | 6.81 |
| SV 151 | 0.297 | 0.495 | 0.665 | 0.335 | 0.145 | 6.88 |
| SV Base Set | 0.182 | 0.447 | 0.662 | 0.338 | 0.115 | **8.67** |

Effective chase count spans 2.18 → 8.67 on an identical Top-10 basket, cleanly separating single-hero sets (Phantasmal Flames, Paldean Fates), moderately concentrated sets (Prismatic, Stellar Crown) and deep-chase sets (SV Base Set, Journey Together, Mega Evolution). **Concentration is the most immediately usable output of this study** and, unlike CE, it is stable and needs no arbitrary cutoff beyond the basket it is measured on.

---

## 7. Sanity-test results

`backend/tests/unit/research/test_set_chase_efficiency.py` — **58 passed**.

| Brief's requirement | Result |
|---|---|
| 1. Higher `p_S` must not reduce CE | **PASS** (7 magnitudes, 1e-6 → 0.9) |
| 2. Higher `V_S` must not reduce CE | **PASS** |
| 3. Lower `C` must not reduce CE | **PASS** |
| 4. Adding a valuable reachable chase behaves sensibly | **PASS** |
| 5. Adding a near-worthless card must not create an absurd advantage | **FAIL — see §5.1.** Padding a \$200/p=0.01 chase with a \$0.10 common at p=0.9 raises mean-based CE from 0.2010 to 0.5364. Proven monotone, not a tuning artefact. The median variant does not have this defect (0.2010 → 0.0231). |
| 6. Finite and correct near probability boundaries | **PASS.** `p=1` refused (infinite hazard not stored); `p=1e-12` finite and correctly ordered; `p ≤ 0` and `p > 1` refused. |
| 7. Empty baskets receive no artificial score | **PASS.** Unsupported baskets carry `supported=False`, a reason string, and no CE. Top-15/20 on small sets and \$100 floors on 5 sets exercise this in the real run. |
| 8. Missing data must not silently become zero | **PASS.** Every missing/NaN/non-positive input returns `None`. Every excluded card carries one of four reason codes. |

Empirical checks on the real cohort: `P(≥1) = 1 − P(0)` — 0 failures across 21 sets × 19 baskets; decomposition reproduces simulated pack values to ≤ 1.4e-14 in all 21 sets; 0 cards unreachable; 0 sets with a non-finite CE.

---

## 8. Case studies

**1. Ascended Heroes vs Pokémon 151 — the headline disagreement.** Both have complete data. At Top-1, 151 edges AH (0.0594 vs 0.0565): AH's Pikachu ex is worth more (\$1,052 vs \$374) but is 6.4× harder to hit (1-in-1351 vs 1-in-212), and the hazard term punishes that harder than the value term rewards it. At Top-10 the order reverses decisively (AH 0.2574, rank 3; 151 0.2043, rank 9). AH's advantage is **depth and cheapness**: 27 cards ≥\$20 against 151's 20, and a \$13.79 pack against \$29.81. AH's Top-10 median qualifying haul is \$349 against 151's \$93. Reaching a 50 % chance of *some* Top-10 chase costs \$1,296 in AH and \$417 in 151 — 151 is far cheaper to *reach*, AH far richer to *hit*. Both intuitions were partly right; which one the metric endorses depends entirely on K.

**2. Prismatic Evolutions — an outlier-dominated ranking, demonstrated.** Ranks #1 at Top-5/10/15 on the mean and #14 on the median at Top-5 (0.1062 vs a mean-based 0.2692). Its Top-10 conditional value has mean \$624 against median \$296, `p95 = max = \$3,863`, and up to **9** Top-10 members in a single pack — god packs. The 5 % winsorized mean is *identical* to the raw mean (0.3606) because the extreme tail is thicker than 5 %; only the 10 % trimmed mean moves it (CE 0.3606 → 0.2288, on V_S \$396 vs \$624). **Winsorizing at 5 % does not defend against this set**, which falsifies the assumption that a light robust statistic suffices.

**3. Phantasmal Flames — Top-K manufactures a fake chase.** Ranks #1 at Top-1 on a single \$703 Mega Charizard X ex. Its Top-5 basket is `$703, $275, $27, $22 (Dawn), $21 (Meowth)` — the fourth and fifth members are cards nobody chases. Conditional median collapses from \$703 to \$21.54 and median-based CE falls 0.1606 → 0.0379 while mean-based CE *rises* 0.1606 → 0.2152. Top-1 share stays at 0.664 even at K=10 (effective N = 2.18). **The set has ~3 chase cards; Top-K insists it has 10.**

**4. Perfect Order — the largest rank mover, for a legible reason.** Top-1 rank **20 → Top-10 rank 6** (+14). Its hero (Mega Zygarde ex, \$130) is both cheap and rare (1-in-1,658), which is the worst possible Top-1 profile. But packs cost \$4.74 and the set has ten cards ≥\$42, so a 50 % chance at *some* Top-10 chase costs \$104 — the cheapest in the cohort alongside Chaos Rising. The metric is behaving correctly; the disagreement is between two different questions, not between right and wrong answers.

**5. Mega Evolution — lowest-ranked, and correctly so.** Top-1 CE 0.0138. A \$267 card at 1-in-2,398 from a \$8.07 pack: 1,662 packs and \$13,412 for a coin-flip. It stays last at Top-3/5 and rises only to 19th at Top-10 on the strength of a genuinely deep roster (effective N = 7.77, `maxInPack = 1` — no multi-hit mechanic at all). This is the metric working: an expensive, unreachable hero in a deep but modest set.

**6. Paldean Fates — the hero-tax case.** Ranks 4th at Top-1 (Mew ex, \$965) but 11th at Top-10. Its basket falls off a cliff — \$965, \$282, \$176, \$78, \$51, \$50 — so top-1 share stays 0.53 and effective N is 3.10. Median-based CE *falls* monotonically from 0.0889 (K=1) to 0.0549 (K=10). It is the clearest instance of the mean and median variants disagreeing about direction, not just magnitude.

---

## 9. Research findings

### Observed

1. Exact-under-model basket probabilities are obtainable for the whole supported cohort at ~40 s per set, and validate cleanly (`P(≥1) = 1 − P(0)`, zero failures; decomposition error ≤ 1.4e-14).
2. Naive summation of card odds overstates `p_S` by up to 45.6 %, worst in god-pack sets.
3. Data coverage is essentially complete: 24 exclusions in 7,530 entities (0.32 %), none above \$2.79, one reason code.
4. Mean-based `CE(K)` rises monotonically in 20/21 sets; no interior peak anywhere.
5. ρ(CE_K, EV/cost) climbs +0.045 → +0.703 from K=1 to K=20.
6. ρ(rank K=1, rank K=20) = 0.516; ρ ≥ 0.93 for K ∈ {10,15,20}.
7. Median-based CE ranks differently (ρ ≈ 0.45–0.62) and is erratic in K.
8. Concentration cleanly separates set archetypes (effective N 2.18 → 8.67).

### Interpretation

The **measurement machinery is sound and is the durable contribution of this study**. The *estimator* is not yet a metric: with the conditional mean, `CE_set` is a provably monotone function of basket size whose ranking converges on expected-value-over-cost. It therefore cannot be published against an arbitrary K, because K, not the set, would be doing the ranking.

Top-K is arbitrary in a way that is worse than aesthetic: it forces \$21 cards into Phantasmal Flames' chase basket while excluding 24 qualifying cards from Prismatic's. Absolute thresholds swap one arbitrariness for another. Cost-multiple baskets are the most defensible of the three families but still leave sets empty.

### Hypotheses (for Stage II)

* **H1.** A `V_S` that breaks the `V·p = E` identity is *necessary* for non-degeneracy. Candidates: conditional median, a high conditional quantile, or an explicitly bounded statistic such as mean-of-best-qualifying capped at the basket's own p95.
* **H2.** The natural chase universe is defined by a break in each set's own price distribution (a within-set structural cutoff), not by a global K or a global dollar floor.
* **H3.** Concentration (effective chase count) is publishable on its own merits far sooner than CE is, and may be the more useful of the two constructs.
* **H4.** Set Chase Efficiency is genuinely distinct from Financial RIP only in the small-basket regime; the distinctness must be *designed in* by the basket rule rather than assumed.

### Unresolved

* No principled, cross-set-comparable chase definition has been identified.
* Whether a non-degenerate `V_S` exists that is also *stable* (the median is non-degenerate but erratic).
* Whether reference retail (MSRP) rather than market pack cost changes the ordering — untested here.
* Whether these rankings are stable across market dates — this is a single-day snapshot.
* Whether the 2.7 % probability-authority disagreement matters at all outside the ≤\$13 band (currently: no evidence that it does).

---

## 10. Notes for the later Financial RIP complementarity study

**No Financial RIP change is proposed, tested, or implied. V11 remains ungated.** Recorded only because the measurements exist:

* `CE_K` and mean-pack-value-over-cost are near-orthogonal at K=1 (ρ = +0.045) and substantially redundant at K=20 (ρ = +0.703). Any complementarity claim must state its K.
* ρ(CE_K, 1/pack cost) runs −0.334 (K=1) to +0.094 (K=20): CE is *not* merely an inverse-price proxy.
* The `h(p)/p` term is the mechanism by which basket expansion pulls CE toward an EV-like quantity. A redundancy study that ignores it will attribute the convergence to the wrong cause.
* The published card-level CE snapshot is a day stale relative to the simulation cohort; any cross-metric comparison must align dates first.

---

## 11. Decision and next study

### `SET_CHASE_EFFICIENCY_FOUNDATION_SUPPORTED_WITH_REVISIONS`

**Supported:** the data is sufficient and clean; exact basket probabilities are computable, validated and reproducible from the authoritative model; conditional value, horizons and concentration all behave correctly; the whole pipeline is rerunnable from explicit inputs. The question the brief posed *can* be answered.

**Revisions required before Stage II can produce a candidate metric:**

1. **Reject the conditional arithmetic mean as `V_S`.** Proven degenerate.
2. **Reject fixed Top-K as the canonical basket.** ρ(K=1, K=20) = 0.516.
3. **Reject the 5 % winsorized mean as the robustness answer.** It is identical to the raw mean on Prismatic Evolutions.
4. **Retain and reuse** the decomposition-based probability method, the exclusion-reason discipline, the horizon mathematics and the concentration statistics unchanged.

This is a Stage-I foundation decision only. **Nothing here is production validated.**

### Recommended Stage II

**Study A — canonical basket rule (blocking).** Test within-set structural cutoffs (largest log-price gap; value share reaching a fixed fraction of the set's total pullable value; cards clearing the pack cost by a factor) against fixed-K and fixed-threshold baselines. Success criterion: basket size varies with the set's actual economics, and ρ between adjacent rule parameterisations exceeds 0.9.

**Study B — canonical `V_S` (blocking, runs after A).** Only statistics that break `V·p = E` are admissible. Measure both non-degeneracy (does `CE(K)` admit an interior optimum?) and stability (is the `CE(K)` curve smooth, unlike the median's?).

**Study C — robustness.** Multi-date replay across ≥ 30 market dates: rank stability, sensitivity to single-card price shocks, and behaviour when a god-pack set's tail moves.

**Study D — market vs reference-retail cost.** Re-derive `C` from MSRP and measure rank displacement. Sets whose sealed price has decoupled from retail (151 at \$29.81/pack) will move most.

**Study E — validation.** Only once A–D settle: does the resulting metric predict anything observable, and is it distinct from Financial RIP under its own final basket rule?

Financial RIP V11 is **not** to be started on the strength of this document.
