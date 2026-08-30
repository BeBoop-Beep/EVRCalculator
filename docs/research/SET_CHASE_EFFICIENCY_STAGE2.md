# Set-Level Chase Efficiency — Stage II: Chase Universe & Beat-the-Buy

**Chase-universe decision: `NO_CANONICAL_CHASE_UNIVERSE_YET`**
**Beat-the-Buy decision: `BEAT_THE_BUY_SUPPORTED_WITH_REVISIONS`**

| | |
|---|---|
| Market date | 2026-08-28 |
| Cohort | 21 of 22 simulation-supported sets (Destined Rivals still excluded) |
| Packs simulated | 1,000,000 per set (21,000,000 total), seeded, reproducible |
| Stage identity | `stage2-chase-universe-and-beat-the-buy-v1` |
| Artifact | `docs/research/set_chase_efficiency_stage2.json` (4.3 MB, all raw components) |
| Production impact | **None.** No score, ranking, snapshot, migration, endpoint or UI changed. |

```
python -m backend.scripts.build_set_chase_efficiency_stage2 --packs 1000000
python -m backend.scripts.report_set_chase_efficiency_stage2
python -m pytest backend/tests/unit/research/                       # 95 passed
```

---

## Part 1 — Prior-research verification

| Check | Result |
|---|---|
| Stage-I scripts and modules present | Yes — `backend/research/set_chase_efficiency/{metrics,baskets,runner,version}.py`, `backend/scripts/build_set_chase_efficiency_research.py`, `report_set_chase_efficiency_research.py` |
| Stage-I artifact present | `docs/research/set_chase_efficiency_stage1.json` — marketDate 2026-08-28, 1M packs, 21 sets, code `6c345f6b` |
| Degeneracy proof preserved | Yes — `test_conditional_mean_chase_efficiency_is_monotone_under_basket_expansion` and its supporting `test_hazard_over_probability_is_increasing`, both passing |
| Stage-I suite | **58 passed** |
| Simulator / input path changed since Stage I? | **No.** `git log 0c90927..HEAD` over `backend/simulations`, `backend/calculations`, `evr_input_preparation_service.py`, `evr_runner.py`, `backend/research/ev_representativeness`, and the set-config packages returns empty. The only diffs in my own modules are cosmetic (unused-import removal). |
| Market date | 2026-08-28 — still the latest promoted complete scrape batch |
| Cohort | 22 supported sets, **21 current** |
| Destined Rivals | **Still excluded; defect NOT fixed.** `evaluate_opening_simulation_freshness` selects its latest simulation (2026-08-29, run `2925570c-…`) which still has no `simulation_run_summary` row. Note `explore_rip_statistics_latest` points at a *different, older, healthy* run (`7607569c-…`), so the two authorities disagree for this set — a second symptom of the same persistence defect. |
| Repository state | Clean enough. No merge in progress, no conflicted paths (`git diff --diff-filter=U` empty). The Stage-I conflict in `RankingsLazyClient.jsx` was resolved externally. Unrelated in-flight work by others (market-explorer, treatment-prestige v3 round 14, set-lifecycle) was left untouched. |

No implementation error was found in the Stage-I proof. It stands.

---

## Part 2 — Chase EV (Question 1: **yes, validly measurable**)

`Chase_EV_S` = mean over all 1,000,000 packs of the total market value of qualifying chase cards, with every non-qualifying card credited at exactly $0. `Chase_EV_Return_S = Chase_EV_S / C`.

At the `≥2×C` universe:

| Set | pack $ | K | Chase EV | EV return | chase share of full EV | non-chase share |
|---|---:|---:|---:|---:|---:|---:|
| Prismatic Evolutions | 14.86 | 27 | 6.070 | **0.408** | 0.705 | 0.295 |
| Ascended Heroes | 13.79 | 26 | 4.858 | 0.352 | 0.538 | 0.462 |
| Shrouded Fable | 8.91 | 20 | 3.024 | 0.339 | 0.507 | 0.493 |
| Pitch Black | 4.75 | 10 | 1.408 | 0.296 | 0.391 | 0.609 |
| Scarlet and Violet 151 | 29.81 | 11 | 6.256 | 0.210 | 0.488 | 0.512 |
| Paldean Fates | 23.11 | 7 | 3.500 | 0.151 | 0.466 | 0.534 |
| Journey Together | 6.58 | 11 | 1.054 | 0.160 | 0.302 | 0.698 |

**Chase EV behaves exactly as an EV metric should, including degenerating.** Across the sweep to the full eligible set, chase share of total EV rises to 0.99–1.00 in every set — by construction, since the "chase universe" eventually contains every card. This is recorded as an *expectation* in `test_chase_ev_rises_monotonically_as_the_universe_widens`, so nobody later mistakes it for a defect or for evidence of efficiency.

The chase/non-chase split is genuinely informative: Prismatic Evolutions draws **70.5 %** of its pack EV from cards worth ≥2 packs, while Journey Together draws only **30.2 %** — that set's value is carried by a long mid-tier tail.

---

## Part 3–4 — Beat-the-Buy (Question 2: **yes, and it is the strongest candidate**)

`BTB = P(C·T ≤ Y)` where `T` = packs to the first qualifying chase and `Y` = value obtained.

### The independence assumption was validated, not assumed

The closed form `E_Y[1 − (1−p_S)^⌊Y/C⌋]` requires `T ⊥ Y`. That holds under the pipeline's documented `packIndependenceAssumption`, but the study computes **both** the closed form and a direct walk of the recorded pack sequence into actual journeys (`chase_journeys`), which assumes nothing.

**356 paired comparisons across 21 sets × 18 universes:**

* max |closed − direct| = **0.01853**
* median |closed − direct| = **0.00163**
* comparisons exceeding 4 standard errors of the direct estimate: **0**

The worst case (Prismatic Evolutions `largest_log_gap`, K=1) is 2.2σ on 1,359 journeys. The closed form is safe to use; the direct estimate is retained anyway and reported beside it.

### Definition A vs B (Part 4)

* **A** = highest-value qualifying card in the successful pack.
* **B** = total qualifying value from that pack.
* **C** was *not* built: the recorder preserves no within-pack draw ordering and no "selected chase" identity, so any ordering would have been invented. This is reported as unavailable rather than fabricated.

**Spearman(A, B) = 0.9987.** Max divergence +0.0071 (Prismatic Evolutions, 0.2050 → 0.2121), then Ascended Heroes +0.0031 and Black Bolt +0.0024. These are exactly the three sets with god-pack/multi-hit structure (`maxInPack` = 9, 9, 7). Eleven sets show *zero* divergence because `maxInPack = 1`.

**Prismatic Evolutions specifically:** `P(≥2 chases) = 0.001548`, up to 9 Top-10 members in one pack. Even there the A/B difference is 0.7 percentage points. **Multi-hit mechanics do not materially change Beat-the-Buy**, and Definition A (the semantically preferred one) can be used without loss.

### The anti-degeneration result (Part 15's core)

| Set | argmax K | BTB@peak | BTB@K=3 | BTB@full set | decline from peak | EV share @peak | EV share @full |
|---|---:|---:|---:|---:|---:|---:|---:|
| Prismatic Evolutions | 15 | 0.2159 | 0.1618 | 0.0315 | **85.4 %** | 0.660 | 0.998 |
| Ascended Heroes | 20 | 0.2116 | 0.1322 | 0.0389 | 81.6 % | 0.497 | 0.993 |
| Phantasmal Flames | 2 | 0.1622 | 0.1519 | 0.0355 | 78.1 % | 0.430 | 1.000 |
| Shrouded Fable | 30 | 0.2699 | 0.0821 | 0.1114 | 58.7 % | 0.616 | 1.000 |
| Scarlet and Violet 151 | 15 | 0.1819 | 0.0887 | 0.0818 | 55.0 % | 0.571 | 1.000 |
| White Flare | 75 | 0.1437 | 0.0663 | 0.0781 | 45.7 % | 0.567 | 1.000 |

**All 21 sets show an interior peak.** Decline from peak to the full set ranges 45.7 %–85.4 %. Chase EV share rises to ~1.0 over the same sweep.

The mechanism is explicit in the formula: `⌊Y/C⌋ = 0` for any card worth less than one pack, so a cheap card raises `p_S` while contributing **exactly zero** to beating the buy. The two effects fight rather than compound. This is the property Stage I's metric provably lacked, and it is asserted as a live regression test (`test_padding_with_a_cheap_frequent_card_can_reduce_beat_the_buy`).

### Against production financial measures

Spearman(BTB, existing measure), by chase universe:

| Universe | Financial RIP v3 | Realistic Upside | Jackpot Upside | P95/cost | P99/cost |
|---|---:|---:|---:|---:|---:|
| top_3 | −0.316 | −0.468 | **+0.632** | −0.453 | +0.258 |
| top_5 | −0.143 | −0.318 | +0.551 | −0.305 | +0.368 |
| top_10 | +0.232 | +0.109 | +0.282 | +0.035 | +0.582 |
| ≥2×C | +0.387 | +0.334 | +0.160 | +0.239 | +0.540 |
| ≥5×C | +0.032 | −0.313 | **+0.721** | −0.362 | +0.475 |

Correlations wobble and change sign; nothing converges monotonically the way Stage I's CE converged on EV/cost (+0.045 → +0.703). BTB's strongest affinity is with **Jackpot Upside** at narrow universes (+0.63 to +0.72), which is intuitive — both concern rare, large hits — and is a specific input to the later complementarity study.

### THE REVISION: Beat-the-Buy is near-collinear with Chase EV Return at a fixed universe

This is the finding that downgrades the verdict from "supported" to "supported with revisions".

Spearman(BTB, Chase EV Return) across sets:

| Universe | top_3 | top_5 | top_10 | ≥2×C | ≥5×C | 2-means | ev_hhi@20 |
|---|---:|---:|---:|---:|---:|---:|---:|
| ρ | **0.997** | 0.975 | 0.792 | 0.951 | **0.997** | 0.684 | 0.977 |

There is an analytic reason. For small `p·Y/C`, `1 − (1−p)^⌊Y/C⌋ ≈ p·Y/C`, so

```
BTB  ≈  p_S · E[Y | hit] / C  =  Chase EV Return (on the best-card valuation)
```

Measured ratio `BTB / (p·E[Y]/C)`:

| Universe | observed ratio range |
|---|---|
| top_3 | 0.87 – 0.97 (near-identity) |
| ≥2×C | 0.64 – 0.83 |
| log_price_2means | 0.51 – 0.82 |

**Beat-the-Buy is a bounded, saturating shrinkage of Chase EV Return, with the shrinkage growing as the universe widens.** That shrinkage is precisely what produces the interior peak — so the anti-degeneration property and the redundancy have the *same* cause and cannot be separated.

Consequences:

1. BTB is a legitimate, well-behaved, interpretable measure. It does not degenerate. It passes every sanity test.
2. BTB is **not an independent ranking dimension** alongside Chase EV Return. Publishing both as separate "chase" axes would present one statistic twice.
3. BTB's advantages over Chase EV Return are real but are about *interpretability and boundedness*, not information: it is a probability in [0,1] that a person can act on ("about 1 chase journey in 4 beats buying"), it cannot run away with an outlier, and it has a defensible maximum.

---

## Part 5 — Chase Cost Gap (Question 3: **yes**)

`Gap = C·T − Y` over walked journeys. At `≥2×C`, most favourable first:

| Set | median gap | mean gap | P(gap≤0) | P(gap ≤ 0.25Y) | P(gap > Y) | median spend | median Y | p25 | p90 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| Shrouded Fable | **$41** | $72 | 0.2629 | 0.3163 | 0.5311 | $80 | $31 | −$1 | $210 |
| Temporal Forces | $60 | $99 | 0.2284 | 0.2762 | 0.5899 | $95 | $32 | $5 | $275 |
| Paradox Rift | $67 | $107 | 0.1861 | 0.2223 | 0.6593 | $98 | $27 | $12 | $286 |
| Pitch Black | $67 | $102 | 0.2025 | 0.2430 | 0.6670 | $100 | $16 | $8 | $296 |
| Ascended Heroes | $218 | $325 | 0.2098 | 0.2458 | 0.6673 | $331 | $60 | $25 | $990 |
| Scarlet and Violet 151 | $277 | $437 | 0.1687 | 0.1930 | 0.6901 | $388 | $93 | $59 | $1,146 |
| Prismatic Evolutions | $319 | $470 | 0.2029 | 0.2332 | 0.6804 | $476 | $79 | $44 | $1,409 |
| Phantasmal Flames | $726 | $1,097 | 0.1540 | 0.1852 | 0.7442 | $953 | $27 | $161 | $2,854 |
| Paldean Fates | **$877** | $1,343 | 0.1235 | 0.1466 | 0.7868 | $1,109 | $78 | $250 | $3,392 |

`P(gap ≤ 0)` is identically `BTB direct` — asserted in `test_gap_and_beat_the_buy_agree_on_the_same_journeys` — so the gap distribution is the dollar-denominated view of the same event, and the two must never be presented as independent evidence.

**Only Shrouded Fable has a p25 gap at or below zero.** In every set, buying the chase outright beats ripping for it more than half the time (`P(gap > Y)` = 0.53–0.79). The metric is deliberately *not* called profit or loss: all non-chase pulls are credited at $0, so this overstates the true cost to someone who sells the remainder.

---

## Part 6 — Chase EV vs Beat-the-Buy

Correlation matrix at `≥2×C` (Spearman, 21 sets):

| | chaseEV | EVreturn | EVshare | BTB | medGap | p_S | medY | effEV | packCost | fullEVret |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| **chaseEV** | +1.000 | +0.410 | +0.921 | +0.340 | +0.442 | +0.134 | +0.738 | +0.155 | +0.888 | −0.203 |
| **EVreturn** | +0.410 | +1.000 | +0.610 | **+0.951** | −0.296 | +0.327 | +0.044 | +0.244 | +0.035 | +0.668 |
| **BTB** | +0.340 | +0.951 | +0.517 | +1.000 | −0.430 | +0.434 | +0.000 | +0.210 | −0.052 | +0.734 |
| **medGap** | +0.442 | −0.296 | +0.310 | −0.430 | +1.000 | −0.690 | +0.656 | −0.481 | +0.719 | −0.652 |
| **effEV** | +0.155 | +0.244 | +0.134 | +0.210 | −0.481 | +0.648 | −0.226 | +1.000 | −0.086 | +0.213 |

Absolute Chase EV and BTB are only ρ=+0.34 — because absolute Chase EV is dominated by pack price (ρ=+0.888 with `packCost`). The quadrants requested:

* **High Chase EV / low BTB — Paldean Fates.** chase EV rank 4, BTB rank 19. Its Mew ex is worth $965 but sits at 1-in-470 packs; median journey costs $1,109 to obtain a median $78 card. Expensive expected chase contribution, terrible chase economics.
* **Moderate Chase EV / high BTB — Perfect Order and Pitch Black.** chase EV ranks 19 and 17, BTB ranks 7 and 5. Cheap packs ($4.74, $4.75) and modest but reachable chases: 50 % of journeys cost under $104 and $100.
* **High both — Prismatic Evolutions, Ascended Heroes, Shrouded Fable.** EV return 0.408 / 0.352 / 0.339 with BTB 0.205 / 0.209 / 0.263.
* **Low both — White Flare, Surging Sparks, Journey Together.** BTB 0.118–0.124 with EV return 0.149–0.161.

**Depth is the genuinely orthogonal dimension.** `effEV` correlates only +0.210 with BTB and +0.155 with absolute Chase EV, but +0.919 with the production `effective_chase_count` at `≥2×C` — strong convergent validity for a measure that carries information neither EV nor BTB does.

---

## Part 7 — Chase Depth (Question 4: **yes**)

All three concentration concepts are computed and they demonstrably differ (`test_the_three_depth_measures_can_disagree`). At `≥2×C`:

| Set | K | effective **value** count | effective **EV** count | effective **probability** count |
|---|---:|---:|---:|---:|
| Phantasmal Flames | 3 | 1.77 | **1.40** | 2.19 |
| Paldean Fates | 7 | 2.58 | 2.57 | 7.00 |
| Stellar Crown | 8 | 3.41 | 3.41 | — |
| Prismatic Evolutions | 27 | 7.90 | 6.72 | **25.33** |
| Scarlet and Violet 151 | 11 | 7.23 | 7.49 | 10.93 |
| Ascended Heroes | 26 | 9.38 | 11.50 | 12.70 |
| Shrouded Fable | 20 | 16.93 | 13.79 | 16.99 |
| Paradox Rift | 27 | 18.97 | **17.55** | 26.02 |

The value/probability divergence is the interesting one. **Prismatic Evolutions** has effective *value* count 7.90 but effective *probability* count 25.33 — its chase value is concentrated in Umbreon ex while chase *access* is spread across 27 cards. That is the quantitative signature of a set that feels deep to open and is actually shallow to profit from.

Depth cleanly separates the three archetypes: single-hero (Phantasmal Flames 1.40, Paldean Fates 2.57), moderate (Prismatic 6.72, 151 7.49), deep (Paradox Rift 17.55, Shrouded Fable 13.79).

---

## Part 8 — Can HHI determine adaptive K? (Question 5: **NO**)

Adaptive K from `round(effective count)`, by weighting × reference pool:

| Set | val@20 | ev@20 | val@25 | ev@25 | val@1×C | ev@1×C | val@2×C | ev@2×C | **spread** |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| White Flare | 7 | 10 | 8 | 12 | 16 | 24 | 8 | 12 | **17** |
| Black Bolt | 7 | 9 | 8 | 11 | 14 | 20 | 8 | 12 | **13** |
| Paradox Rift | 15 | 14 | 18 | 16 | 26 | 24 | 19 | 18 | 12 |
| Temporal Forces | 17 | 14 | 20 | 17 | 25 | 22 | 18 | 15 | 11 |
| Scarlet and Violet 151 | 11 | 12 | 12 | 13 | 10 | 10 | 7 | 7 | 6 |
| Paldean Fates | 4 | 4 | 4 | 4 | 3 | 4 | 3 | 3 | **1** |

**K spread across reference pools: min 1, max 17, mean 6.9.**

This is the circularity made concrete. Effective chase count is computed *from* a basket, so using it to *choose* the basket requires a reference pool, and the choice of pool moves the answer by up to 17 cards. Nothing in the data privileges one pool: White Flare's chase universe is "8 cards" or "24 cards" depending entirely on whether the pool was Top-20 or everything above one pack's price.

There is also a semantic failure independent of the spread. **Phantasmal Flames** has effective value count 1.77 → K=2, which happens to be right. But **Scarlet and Violet 151** has effective value count 7.23 → K=7, cutting at $87.80 with the next card at $80.82 — a **boundary ratio of 1.09**. HHI has no knowledge of where the price discontinuities are; it slices through a flat run because the arithmetic said 7.23.

**Conclusion: effective chase count is a good Chase Depth statistic and a bad chase-definition engine.** It should be reported as depth, never used to pick K.

---

## Part 9 — Price-boundary / elbow methods (**no reliable elbow exists**)

| Set | largest-log-gap K | gap **ratio** | robust-z K | 2-means K | 2-means price | top-5 prices |
|---|---:|---:|---:|---:|---:|---|
| Phantasmal Flames | 2 | **10.16** | 2 | 2 | $40.91 | 703 275 27 22 21 |
| Paldea Evolved | 1 | 3.83 | — | 55 | $7.62 | 382 100 98 74 61 |
| Paldean Fates | 1 | 3.43 | 3 | 42 | $8.76 | 965 282 176 78 51 |
| Scarlet and Violet 151 | 1 | 2.75 | 1 | 35 | $8.26 | 374 136 119 95 95 |
| Prismatic Evolutions | 1 | 2.71 | — | 41 | $13.91 | 1473 543 343 320 296 |
| Ascended Heroes | 3 | 1.65 | 6 | 29 | $15.37 | 1052 993 659 399 349 |
| Shrouded Fable | **26** | **1.46** | — | 26 | $10.26 | 75 59 58 54 49 |
| Temporal Forces | 1 | 1.45 | — | 41 | $7.36 | 96 66 63 60 60 |
| SV Base Set | 2 | 1.36 | — | 25 | $7.88 | 73 59 43 43 39 |

Three independent failures:

1. **Only one set has a real cliff.** Phantasmal Flames' ratio of 10.16 ($275 → $27) is the sole unambiguous elbow. Every other set's largest gap is a ratio of 1.36–3.83, and eight of them fire at K=1, which is not a chase universe — it is the hero card.
2. **The method always returns an answer.** `test_largest_log_gap_still_returns_a_cut_on_a_smooth_curve` shows a perfectly geometric price curve still produces a K, with ratio < 1.2. A K on its own is therefore not evidence a boundary exists; only the ratio is, and the ratios say it usually does not. Shrouded Fable's "largest gap" at K=26 with ratio 1.46 is a rounding artefact of a flat curve.
3. **The robust z-score fires for only 8 of 21 sets** and is the least stable rule in the study (mean Jaccard 0.768, minimum 0.000 — on Mega Evolution and Surging Sparks a ±10 % price shock changes the selection completely). Two-means is stable but selects absurd universes: 112 cards for Black Bolt, 123 for White Flare, down to ~$7–8 cards.

---

## Part 10 — Value-to-pack-cost thresholds

| Set | ≥2×C | ≥5×C | ≥10×C | ≥20×C |
|---|---:|---:|---:|---:|
| Ascended Heroes | 26 | 14 | 9 | 6 |
| Black Bolt | 28 | 5 | 4 | 2 |
| Prismatic Evolutions | 27 | 13 | 10 | 4 |
| Scarlet and Violet 151 | 11 | **1** | **1** | — |
| Obsidian Flames | 7 | 1 | 1 | — |
| Paradox Rift | 27 | 7 | 1 | — |
| Shrouded Fable | 20 | 5 | — | — |
| Phantasmal Flames | 3 | 2 | 2 | 2 |

`≥2×C` is the **only rule in the entire study supported by all 21 sets**, and it is the most stable non-trivial rule (mean Jaccard 0.952 under ±10 % shocks, minimum 0.870, mean K swing 1.95).

Its weakness is exposed by 151: at $29.81 a pack, `≥5×C` is a $149 floor, so the "chase universe" collapses to the single Charizard ex while Obsidian Flames at $10.16 keeps a card at $51. **The multiplier is not scale-free once pack prices span 6×** ($4.74 to $29.81), which is precisely the cross-set comparability the family was chosen to deliver. Four sets have no `≥10×C` universe at all and seven have no `≥20×C`.

---

## Part 11–12 — Chase-universe comparison and robustness

Per-set mean pairwise Jaccard across seven defensible methods (`top_5`, `≥2×C`, `≥5×C`, largest-log-gap, 2-means, value-HHI@20, EV-HHI@20):

| Class | Count | Sets |
|---|---:|---|
| **Stable** (≥0.60) | 4 | Pitch Black 0.760, Phantasmal Flames 0.721, Chaos Rising 0.628, Surging Sparks 0.613 |
| **Boundary-sensitive** (0.35–0.60) | 12 | Mega Evolution 0.583 … Temporal Forces 0.352 |
| **Unstable** (<0.35) | 5 | SV 151 0.346, White Flare 0.338, Prismatic Evolutions 0.333, Paradox Rift 0.327, Paldea Evolved 0.324 |

Cross-method agreement on *which cards are chases* (mean Jaccard over sets):

| | top_5 | ≥2×C | ≥5×C | log-gap | 2-means | val-HHI | ev-HHI |
|---|---:|---:|---:|---:|---:|---:|---:|
| **top_5** | 1.000 | 0.400 | 0.660 | 0.424 | 0.286 | 0.598 | 0.517 |
| **≥2×C** | 0.400 | 1.000 | 0.406 | 0.242 | 0.638 | 0.622 | 0.692 |
| **log-gap** | 0.424 | 0.242 | 0.473 | 1.000 | 0.237 | 0.352 | 0.289 |
| **val-HHI** | 0.598 | 0.622 | 0.625 | 0.352 | 0.484 | 1.000 | **0.791** |

The only pair that agrees strongly is value-HHI vs EV-HHI (0.791) — two variants of the same statistic. Every genuinely different method disagrees with every other: the highest cross-family agreement is 0.692 and the lowest is 0.237. **K ranges within a single set from 1 to 123** (White Flare), 1 to 55 (Paldea Evolved), 1 to 45 (Paradox Rift).

Rule-level stability under ±10 % price shocks:

| Rule | mean Jaccard | min Jaccard | mean K swing |
|---|---:|---:|---:|
| log_price_2means | 0.965 | 0.893 | 3.57 |
| **≥2×C** | **0.952** | **0.870** | 1.95 |
| ≥5×C | 0.952 | 0.833 | 1.19 |
| value_hhi_top_20 | 0.951 | 0.855 | 1.00 |
| ev_hhi_top_20 | 0.945 | 0.855 | 1.05 |
| top_5 | 0.929 | 0.754 | 0.00 |
| largest_log_gap | 0.922 | **0.513** | 4.05 |
| robust_zscore | **0.768** | **0.000** | 1.09 |

Every rule is individually reasonably stable to price noise. **The instability is not within methods, it is between them.** No amount of shock-robustness helps when two defensible rules disagree about whether a set has 1 chase or 55.

---

## Part 13 — Core + Extended chase model (**not adopted**)

A vote across the economic, price-boundary and HHI families (fixed-K excluded, since Stage I already rejected it):

| Set | voters | core | extended | core cards |
|---|---:|---:|---:|---|
| Phantasmal Flames | 15 | 2 | 1 | Mega Charizard X ex $703, Mega Charizard X ex $275 |
| Prismatic Evolutions | 14 | 7 | 34 | Umbreon ex $1473, Sylveon ex $543, Leafeon ex $343, Espeon ex $320 … |
| Ascended Heroes | 15 | 9 | 20 | Pikachu ex $1052, Mega Gengar ex $993, Mega Dragonite ex $659 … |
| **Scarlet and Violet 151** | 14 | **1** | **34** | Charizard ex $374 |
| **White Flare** | 15 | **3** | **120** | Victini, Reshiram ex, Reshiram ex |
| **Shrouded Fable** | 12 | **17** | 9 | Persian $75, Basic Darkness Energy $59, Houndoom $58 … |
| **Paradox Rift** | 13 | **14** | 31 | Groudon $120, Morpeko $57, Altaria ex $56, Plusle $50 … |

It works beautifully where the answer was never in doubt — Phantasmal Flames (2 core, 1 extended), Prismatic Evolutions, Ascended Heroes — and fails exactly where it was needed. 151 gets a core of one and an extended set of 34; White Flare gets 3 core and **120** extended, which is not a chase distinction but a restatement of the disagreement.

*(The unusual-looking Shrouded Fable and Paradox Rift core cards were checked against the source data and are legitimate: all carry card numbers above the set size — `078/064`, `199/182` — i.e. secret/illustration rares, not a pricing artefact.)*

**Core+Extended is a promising presentation format but it is not a chase-universe method.** It inherits whatever the voter methods disagree about; it cannot manufacture agreement they do not have.

---

## Part 14 — Sanity-test results

`backend/tests/unit/research/test_beat_the_buy.py` — **37 passed**. Full research suite (Stage I + II) — **95 passed**.

| Required property | Result |
|---|---|
| 1. Lower pack price must not reduce BTB | **PASS** (4 price levels) |
| 2. Higher chase value must not reduce BTB | **PASS** (3 value levels) |
| 3. Higher hit probability must not reduce BTB | **PASS** (3 rate levels) |
| 4. Adding a low-value frequent card **can** decrease BTB | **PASS** — the anti-degeneration property, asserted directly |
| 5. An extremely valuable rare card behaves sensibly | **PASS** — a $5,000 card at 1-in-20,000 yields BTB < 0.10 and loses to a $60 card at 1-in-30 |
| 6. Missing prices never become zero-value chases | **PASS** — `None` cost, `None` probability and zero cost all return `None` |
| 7. Empty baskets handled explicitly | **PASS** — reason string, no score; exercised for real by `≥20×C` on 7 sets |
| 8. Multi-hit packs not double-counted | **PASS** — journeys partition the sequence; `Σ T` equals the index of the final success + 1 |
| 9. BTB bounded in [0,1] | **PASS** across four extreme parameter corners |
| 10. Closed form agrees with direct simulation | **PASS** — 4σ tolerance in tests; 0/356 real comparisons exceeded 4σ |

Supporting checks: `P(gap ≤ 0)` is identically `BTB direct`; a card worth less than one pack contributes exactly zero; the three depth measures are shown to disagree; price perturbation is bounded, seeded and identity-preserving; the elbow selectors report reasons when they cannot fire.

---

## Part 16 — Case studies

### Ascended Heroes vs Pokémon 151

| | Ascended Heroes | Pokémon 151 |
|---|---|---|
| Pack cost | $13.79 (loose pack) | $29.81 (bundle) |
| Top prices | 1052, 993, 659, 399, 349, 315, 235… | 374, 136, 119, 95, 95, 93, 88… |
| `≥2×C` universe | **K=26** down to $32.19 | **K=11** down to $60.09 |
| `≥5×C` universe | K=14 down to $71.60 | **K=1** — Charizard ex only |
| largest-log-gap | K=3, ratio 1.65 | K=1, ratio 2.75 |
| EV-HHI@20 | K=10 | K=12 |
| **Core / extended** | **9 / 20** | **1 / 34** |
| p_S at ≥2×C | 0.02857 | 0.05403 |
| Chase EV / return | $4.858 / **0.352** | $6.256 / 0.210 |
| Chase EV share of pack EV | 0.538 | 0.488 |
| **BTB** | **0.2093** (rank 3) | 0.1677 (rank 8) |
| Median gap / spend / Y | $218 / $331 / $60 | $277 / $388 / $93 |
| Effective EV count | 11.50 | 7.49 |
| Universe stability class | boundary-sensitive (0.429) | **unstable (0.346)** |

**Why they differ.** Ascended Heroes wins on BTB for three compounding reasons: its pack is 2.2× cheaper, its chase pool is genuinely deeper (26 cards clear 2× pack cost against 151's 11; effective EV count 11.50 vs 7.49), and its chase cards are individually worth far more relative to a pack (six cards over $300). 151's higher `p_S` does not save it, because a $29.81 pack means `⌊Y/C⌋` is small for most of its chase pool — its median obtained chase of $93 covers only three packs.

The deeper point is about the *universe*, not the ranking. **151 is one of the five unstable sets**: its methods produce K from 1 to 35, and its core is a single card. Ascended Heroes has a 9-card core that nine of fifteen voters agree on. Any published comparison of these two sets would be reporting a real difference for AH and an artefact of method choice for 151.

### Prismatic Evolutions — the god-pack case

The only set where Definition A and B diverge materially (BTB 0.2050 → 0.2121; `P(≥2)` = 0.001548; up to 9 qualifying cards in one pack). It ranks **#1 on Chase EV Return (0.408)** and **#4 on BTB**, and has the sharpest anti-degeneration profile in the cohort (peak 0.2159 at K=15, collapsing 85.4 % to 0.0315 at the full set). Its `largest_log_gap` fires at K=1 on a ratio of 2.71, selecting only Umbreon ex — BTB 0.126 — while `≥2×C` selects 27 cards and yields BTB 0.205. **A 63 % swing in the headline number from two defensible universe definitions on the same set.** Its effective *value* count (7.90) versus effective *probability* count (25.33) is the widest divergence in the study.

### Phantasmal Flames — the hero-chase set, and the only real elbow

$703 → $275 → $27 is a genuine cliff (ratio 10.16). Every method except `top_5` and `top_10` agrees on 2–3 cards, giving it the second-highest stability (0.721) and a clean core of 2. Effective EV count 1.40 — the most concentrated set in the cohort. Its BTB peaks at **K=2**, the smallest argmax observed, and its median gap of $726 against a median obtained chase of $27 shows what a hero-chase set costs: you pay for many packs and usually get the cheap tail of the basket.

### Paradox Rift — the deep-chase set

Effective EV count **17.55**, effective probability count 26.02, 27 cards above 2× pack cost, top card only $120. `largest_log_gap` gives K=1 (BTB 0.033) while `≥2×C` gives K=27 (BTB 0.188) — a **5.7× swing**. Classified unstable (0.327). It ranks 6th on BTB and 3rd-best on median gap ($67), i.e. a set where opening for *some* chase is comparatively cheap but no individual chase is worth much.

### Shrouded Fable — highest BTB, and the flattest curve

Highest BTB in the cohort (0.2630 at `≥2×C`, peaking at 0.2699 at K=30) and the most favourable Chase Cost Gap (median $41, p25 −$1 — the **only set where the lower quartile of journeys beats buying**). Its top price is just $74.80 and its price curve is nearly flat (75, 59, 58, 54, 49), so `largest_log_gap` fires at K=26 on a ratio of 1.46 — a meaningless cut that nonetheless produces the study's single highest BTB (0.2802). This set is the clearest demonstration that **BTB is only as meaningful as the universe it is evaluated on.**

### Paldean Fates — the largest Chase EV / BTB disagreement

Chase EV rank **4**, BTB rank **19**. Mew ex at $965 drives a high expected chase contribution, but at 1-in-470 packs with a $23.11 pack, the median journey costs $1,109 and delivers a median $78 card. `P(gap > Y)` = 0.787 — the worst in the cohort. This is exactly the "large expected chase contribution driven by rare expensive cards" quadrant the brief anticipated, and it is the strongest single argument that Chase EV must never be presented as evidence of chase efficiency.

### Largest adaptive-K disagreement — White Flare

K = 7 (value-HHI@Top-20) to 24 (EV-HHI@≥1×C) — a spread of 17 on the same set with the same data, purely from the reference pool. Its 2-means universe is 123 cards. Core 3 / extended 120. Unstable (0.338).

---

## Research findings

### Observed

1. Beat-the-Buy shows an interior maximum in **21/21 sets**, declining 45.7–85.4 % from peak to the full eligible set, while Chase EV share rises to ~1.0 over the same sweep.
2. Closed-form and direct-simulation BTB agree: 356 comparisons, median |Δ| 0.0016, **0 exceeding 4 standard errors**.
3. BTB Definition A vs B: ρ = 0.9987, max Δ 0.0071 even on god-pack sets.
4. BTB correlates ρ = 0.68–0.997 with Chase EV Return, and `BTB / (p·E[Y]/C)` measures 0.87–0.97 at narrow universes.
5. HHI-adaptive K varies by up to 17 cards with the reference pool (mean spread 6.9).
6. Only 1 of 21 sets has a price gap ratio above 3.9; the robust z-score fires for 8/21 and has minimum Jaccard 0.000.
7. `≥2×C` is the only rule supported by all 21 sets; mean Jaccard 0.952 under ±10 % shocks.
8. Cross-method agreement on chase membership: 0.237–0.692 between families; K within a single set ranges 1–123.
9. Only 4/21 sets are stable, 12 boundary-sensitive, 5 unstable.
10. Study effective-EV-count correlates +0.919 with production `effective_chase_count`; BTB correlates only +0.210 with it.

### Interpretation

Beat-the-Buy is the right *shape* for a Chase Efficiency metric: bounded, interpretable, non-degenerating, validated two independent ways, and passing every sanity property. But it is, to first order, a shrunk Chase EV Return — and the shrinkage that saves it from degeneracy is the same thing that makes it near-collinear at any fixed universe. It should be positioned as **the interpretable, bounded expression of chase economics**, not as an additional independent dimension beside Chase EV.

The blocking problem is upstream of every metric: **there is no defensible way to say which cards are a set's chases.** Every candidate rule fails somewhere. Fixed K was already rejected. HHI is circular. Price boundaries do not exist in 20 of 21 sets. Economic multiples are the best available but are not scale-free across a 6× pack-price range. Because BTB, Chase EV and Chase Cost Gap are all functions of the universe — and swing by 63 % (Prismatic) to 470 % (Paradox Rift) across defensible universes — **no chase metric can be published before the universe question is settled.**

### Hypotheses for Stage III

* **H1.** The chase universe should be defined by the *metric's own optimum*: the K that maximises BTB. It is interior in all 21 sets, so it exists and is unique-ish. Risk: peak K ranges 2–75 with the lowest selected card ranging $4.98–$275.30, so it may encode "where the economics turn" rather than "what people chase". This must be tested, not assumed.
* **H2.** A two-sided economic rule (value ≥ m×C **and** value ≥ some absolute floor) may repair `≥2×C`'s scale failure on expensive-pack sets.
* **H3.** Depth and BTB are the two publishable dimensions; Chase EV is a diagnostic, and Chase Cost Gap is a presentation of BTB in dollars.
* **H4.** Sets should be labelled by universe-stability class, and unstable sets may warrant no published chase metric at all.

### Unresolved

* Whether any chase-universe rule can be justified without a human-labelled ground truth. Nothing in this study establishes what a chase *is*, only what several rules do.
* Whether BTB's rankings are stable across market dates — this remains a single-day snapshot.
* Whether BTB survives a reference-retail (MSRP) cost basis, which was again not tested.
* Whether the BTB/Chase-EV-Return collinearity persists once the universe is fixed by a principled rule.

---

## Next research gate

**Stage III — Chase Universe Resolution (blocking).** Nothing downstream may proceed until one of these succeeds:

1. **Human-labelled ground truth.** Label the chase universe for 8–10 sets by hand; score every candidate rule against it. This is the only way to break the circularity, and its absence is why Stage II cannot conclude.
2. **BTB-optimal K.** Test H1 against the labels: does the argmax basket look like a chase universe, and is peak K stable under ±10 % price shocks and across market dates?
3. **Two-sided economic rule.** Test H2 for cross-set comparability at fixed pack-price spread.

**Stage IV — Temporal robustness.** Replay across ≥30 market dates: rank stability of BTB and depth, stability of the chosen universe, sensitivity to single-card price shocks.

**Stage V — Market vs reference-retail cost.** Re-derive `C` from MSRP; measure rank displacement. 151 ($29.81/pack) and Paldean Fates ($23.11) should move most.

**Only then** the Chase Efficiency vs P95 vs Jackpot / Financial RIP complementarity study, for which this study contributes: BTB's affinity with Jackpot Upside (+0.63 to +0.72 at narrow universes), its sign-changing relationship with Realistic Upside (−0.47 to +0.47), and the finding that it does not converge on any production measure as the universe widens.

**Financial RIP V11 remains out of scope and is not begun.**

---

## Decisions

### `NO_CANONICAL_CHASE_UNIVERSE_YET`

Four families were tested against agreement, semantic plausibility and shock-stability. Fixed K was already rejected in Stage I. HHI-adaptive is circular and moves K by up to 17 cards with the reference pool. Price boundaries are real in exactly one set of 21. Economic multiples are the strongest candidate — `≥2×C` is universally supported and the most stable non-trivial rule — but are not scale-free across a 6× pack-price range, collapsing to K=1 on expensive-pack sets. Core+Extended is a good presentation of disagreement, not a resolution of it. Cross-family agreement peaks at 0.692 and only 4 of 21 sets are stable.

### `BEAT_THE_BUY_SUPPORTED_WITH_REVISIONS`

**Supported:** interior peak in 21/21 sets; closed form validated against direct simulation with 0/356 comparisons beyond 4σ; bounded in [0,1]; all ten required sanity properties pass; robust to the multi-hit definition choice (ρ=0.9987); no convergence toward any production financial measure as the universe widens.

**Revisions required before it can be treated as *the* Chase Efficiency metric:**

1. **It is not an independent dimension.** ρ = 0.68–0.997 with Chase EV Return, analytically explained. It must not be published beside Chase EV Return as a second axis.
2. **It is undefined without a chase universe.** BTB swings 0.126 → 0.205 (Prismatic) and 0.033 → 0.188 (Paradox Rift) across defensible universes on the same set. Stage III blocks it.
3. **Definition A should be canonical**, and Definition C should stay unbuilt — the simulator provides no ordering to support it.
4. **`P(gap ≤ 0)` is BTB.** The Chase Cost Gap is BTB's dollar view, not corroborating evidence.

This is a Stage-II foundation decision. **Nothing here is production validated.**
