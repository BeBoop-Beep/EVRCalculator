# Stage IX — Chase Identity from Set Value Concentration

## Decision

### `SET_VALUE_HHI_VALIDATED_AS_DEPTH_NOT_ROSTER`

Raw set-value HHI and its effective count `1/HHI` are validated as a **cross-era
descriptor of chase depth**. No tested rule — HHI-adaptive K, ranked log-share cliffs,
robust log-outlier scoring, or cumulative-mass — produced a defensible Core/Extended
**roster** across eras. Every candidate failed in an era- and shape-correlated way.

Chase Identity is therefore **not yet implementable**. Chase Depth is.

> Nothing was deployed, published, migrated or made canonical. Migration 074 remains
> unapplied. `CANONICAL_OVERALL_RIP_VERSION` remains Overall RIP V10.

---

## 1. Authority audit (Phase 1)

| Existing metric | Formula | Basis | Level | Question answered | Verdict |
|---|---|---|---|---|---|
| `herfindahl` / `effectiveChaseCount` (`set_chase_efficiency/metrics.py:238`) | `Σsᵢ²` over EV shares of a **basket** | EV | basket | how concentrated is the EV of a chosen basket | **keep** — but it is basket-relative, not a set descriptor |
| `chaseDepth` (Stage V-C) | effective count of the chase EV block | EV | product | depth of one product's chase EV | keep |
| `tiers.py` rules — `count_percentile`, `percentile_floor`, `log_zscore`, `multiple_of_quantile`, `relative_to_top` | various | value | set | candidate tier selectors | **reuse** — these are Methods A/C/E already built |
| `chase_core_k_v1_stage5c_3x_pack_equivalent_cost` | `value ≥ 3 × product_market_cost / random_pack_count` | value + sealed price | **product** | which cards clear this product's cost | **retire from Chase Identity** |
| `chase_labeling_v1/` | blind 448-card packet, 10 sets | — | card | human face validity | **preserve, unused** |

**Two prior findings inherited rather than re-derived:**

1. `tiers.py:34` — *"HHI IS NOT ALLOWED TO CHOOSE A TIER. Stage II showed effective chase
   count is circular as a selector: it is computed FROM a basket, so using it to CHOOSE
   the basket moves the answer by up to 17 cards."* That circularity applies to
   **basket-relative EV-HHI**. Whole-set raw-value HHI is *not* circular — its reference
   pool is the entire eligible set, fixed independently of any tier — so it was retested
   here rather than inherited. It still fails as a selector, for a different reason (§5).

2. **No human labels exist.** `chase_labels_template.csv` has 448 rows and **0** populated
   `human_label` values. External validation was unavailable for this stage.

---

## 2. Card universe (Phase 2) — PARTIALLY RESOLVED

Analysis used `pokemon_canonical_card_market_prices_latest`, one row per
`canonical_card_id`. Universe A (every priced row) and Universe B (collapse by canonical
card, max price) were computed and are **identical** — 0 rows dropped on all 11 tested
sets, `1/HHI` delta 0.00 everywhere. That table is already canonical-collapsed.

**Consequence, stated plainly:** the reverse-holo / treatment / illustration-variant
question was therefore **not exercised**. The simulation universe keys on
`card_variant_id` and does carry separate reverse printings (the labeling packet has 448
distinct printings across 10 sets). A variant-level universe is a different and larger
population and could move both HHI and any roster rule. **Phase 2 is not closed.**

## 3. Price basis (Phase 3) — RESOLVED

`pokemon_canonical_card_market_prices_latest` carries `market_price`, `captured_at`,
`source`, `price_selection_reason`. Cohort sets are captured at a single day
(2026-08-31), with per-set completeness ≥ 90% at that date for all but a few vintage
sets. No sealed-product price enters anywhere in this stage.

## 4. Cross-era cohort (Phase 4)

30 sets, 1999–2026, all eras with ≥ 40 priced cards. Detailed analysis on a 16-set
structural subset spanning vintage → current.

---

## 5. Concentration results (Phases 5–7)

`1/HHI` over raw value shares, full set:

| set | era | cards | set value | HHI | **N_eff** | top1 % | shape |
|---|---|---|---|---|---|---|---|
| Phantasmal Flames | SV | 132 | $1,209 | 0.3905 | **2.56** | 58.1 | hero |
| Champion's Path | SWSH | 81 | $585 | 0.3642 | **2.75** | 45.9 | hero |
| Black & White | mid | 115 | $504 | 0.1908 | 5.24 | 30.9 | concentrated |
| Base | vintage | 102 | $2,175 | 0.1850 | 5.40 | 39.9 | concentrated |
| Team Up | SM | 196 | $10,818 | 0.1630 | 6.14 | 35.0 | concentrated |
| Paldean Fates | SV | 247 | $2,645 | 0.1430 | 6.99 | 35.2 | concentrated |
| Neo Destiny | vintage | 113 | $19,354 | 0.1233 | 8.11 | 22.0 | deep |
| Evolving Skies | SWSH | 237 | $8,260 | 0.1203 | 8.31 | 28.0 | deep |
| Prismatic Evolutions | SV | 181 | $5,008 | 0.1195 | 8.37 | 29.1 | deep |
| Fossil | vintage | 62 | $2,075 | 0.1131 | 8.84 | 29.0 | deep |
| Ascended Heroes | SV | 305 | $5,673 | 0.0924 | 10.82 | 18.2 | deep |
| Crown Zenith | SWSH | 161 | $260 | 0.0586 | 17.07 | 19.0 | flat |
| Jungle | vintage | 64 | $1,638 | 0.0479 | 20.89 | 9.5 | flat |
| Shrouded Fable | SV | 107 | $878 | 0.0418 | 23.91 | 8.6 | flat |
| Cosmic Eclipse | SM | 271 | $6,432 | 0.0352 | 28.44 | 8.8 | flat |
| Paradox Rift | SV | 266 | $1,221 | 0.0281 | 35.53 | 9.7 | flat |

**N_eff orders sets by depth in a way that is coherent across 27 years and matches the
independent structural designations in the labeling manifest** — Phantasmal Flames
(`hero_chase`), Paradox Rift (`deep`), Shrouded Fable (`flat/deep`). Champion's Path
landing at 2.75 is a strong external check: it is famously a two-card set.

### N_eff is not literal K

`1/HHI` matched a cliff-derived Core within ±1 in **2 of 16** sets. It over-counts flat
sets catastrophically — Jungle 21, Crown Zenith 17, Paradox Rift 36 against intuitive
rosters of 4–8, 1–3 and 5–10.

**Verdict: continuous depth descriptor only. Never round it into K.**

---

## 6. The user's hypothesis (Phase 6) — SUPPORTED

Raw value share alone is insufficient; **relative separation is the discriminating
signal.** The cleanest evidence:

| set | top1 share | top1 / median card | verdict |
|---|---|---|---|
| Paradox Rift | 9.74 % | **626×** | genuine chase |
| Jungle | 9.51 % | **17×** | genuinely flat |

Near-identical share, utterly different structure. Any fixed-share threshold
(`share ≥ 1%`) would rank these as equivalent. Confirmed at the other extreme: Ascended
Heroes' top card is 18.2 % of set value but **4,304×** the median card, while Fossil's is
29.0 % but only **91×**. The user's vintage intuition is correct — share magnitude and
disproportion are different quantities and disproportion is the one that travels.

---

## 7. Boundary methods (Phase 8) — ALL FAILED

| rule | vintage Core range | modern Core range | failure mode |
|---|---|---|---|
| `1/HHI` rounded | 5–21 | 3–36 | over-counts flat sets |
| largest log-share cliff | 1–3 | 1–3 | **era-stable range** but under-counts (Base 1, Fossil 1, Prismatic 1) and returns *nothing* on flat sets |
| robust log z ≥ 3.5 | **0–1** | **0–29** | catastrophic era split |
| cumulative 60 % of value | 4–10 | 2–19 | over-counts flat sets |

**Method E (robust log z) is the most instructive failure.** It scores 0 Core for Fossil
(top card $601, 91× median), Neo Destiny ($4,250 top card) and Paldean Fates ($930, 35 %
of set value) — all obviously chase-bearing — while scoring 21 Core for Champion's Path
and 29–30 for Cosmic Eclipse, Team Up and Ascended Heroes. The cause is that log-MAD is
set by the *bulk* distribution, which is broad in vintage sets (Fossil 1.55, Jungle 1.55)
and tight in modern ones (Champion's Path 0.34). The statistic measures era, not chase.

No z threshold rescues it — at z ≥ 3.5 the cohort ranges from 0 to 30 Core.

### Why every rule failed

**Flat sets have no boundary to find.** Jungle, Shrouded Fable, Cosmic Eclipse and
Paradox Rift genuinely lack a chase/ordinary separation in value space. A rule obliged to
emit a roster there invents one. This is a property of the sets, not a defect in any
particular formula, and it is the central unsolved problem.

---

## 8. Scale invariance (Phase 12) — PASS

Multiplying every price in a set by 0.5×, 2× and 10× produced **0 tier changes** for
every share-based and log-gap-based rule, and 0 for the robust-z rule once the population
median shifts with it. HHI and `1/HHI` are exactly invariant by construction.

This is a genuine and decisive improvement over `3 × C_product`, which is not
scale-invariant and moves whenever sealed-product prices move.

---

## 9. Comparison with the old 3×C rule (Phase 16)

The old rule produces **a different chase roster per sealed SKU of the same set.** For
Ascended Heroes, one set had four different Core K values simultaneously:

| product | Core floor | Core K (research vintage) | Core K (production vintage) |
|---|---|---|---|
| Booster Bundle | $43.40 | 13 | 22 |
| Booster Pack | $41.37 | 14 | 22 |
| Pokemon Center ETB | $113.31 | 7 | 10 |
| Elite Trainer Box | $54.41 | 10 | 21 |

This directly violates the product-invariance requirement. It also makes chase identity
move when a booster box goes on sale. **Retired from Chase Identity.**

**What survives:** the 3× coupled contract, `pack_equivalent_cost`, and the Stage V-B cost
authority remain valid and useful for **Economic Chase Efficiency** — "is this SKU a good
way to buy access to the chases" — which is a legitimately product-level question.

---

## 10. What was not done

* **Phase 2 variant universe** — canonical-card only; reverse/treatment universe untested.
* **Phase 11 human labels** — none exist; no external face-validity check was possible.
* **Phase 13 longitudinal stability** — not run. Pointless before a roster rule exists.
* **Phase 14/15 EV-HHI and pull scarcity comparison** — not run. EV-HHI is basket-relative
  in the current code and needs a set-level reformulation first.
* **Phase 10 synthetic distribution shapes** — covered by real analogues (hero: Champion's
  Path/Phantasmal Flames; deep: Cosmic Eclipse; flat: Jungle/Shrouded Fable;
  vintage-expensive: Neo Destiny) rather than synthetic vectors.

---

## 11. Architecture conclusions (Phase 17)

| question | answer |
|---|---|
| **A. Set Chase Concentration** | **Raw value HHI**, `Σ(Vᵢ/ΣV)²`. Validated cross-era. |
| **B. Core Chase roster** | **UNRESOLVED.** No tested rule generalises. |
| **C. Extended Chase roster** | **UNRESOLVED.** Blocked on B. |
| **D. Chase Depth** | `1/HHI`, continuous descriptor. **Never** literal K. Distinct name from any future roster count. |
| **E. Product Chase Opportunity** | Input contract only: *one fixed set chase roster + product pull/composition data*. Not calibrated. |
| **F. Economic Chase Efficiency** | Future role only: product price vs probability/value of pursuing the fixed roster. Inherits the 3×C machinery. Not implemented. |

### Invariants status

| invariant | status |
|---|---|
| 1. Product invariance | satisfied by construction (no product input) |
| 2. Scale invariance | **PASS**, 0 changes at 0.5×/2×/10× |
| 3. Era robustness | **PASS for depth**, FAIL for every roster rule |
| 4. Relative significance | supported — disproportion, not share, is the signal |
| 5. Depth awareness | **PASS** — 2.56 vs 35.53 across the cohort |
| 6. Extended-tail preservation | untestable until B is solved |
| 7. No sealed-price floor | satisfied |

---

## 12. Next research step

**One step only:** determine whether a chase/ordinary boundary exists at all in flat sets,
by testing bimodality directly rather than assuming a boundary and locating it.

Concretely: fit 1-component vs 2-component models to the log-value distribution per set
(or a dip-statistic equivalent) and ask *whether the set is separable*, before asking
*where* it separates. Sets that fail the separability test would legitimately report
`chase_depth` with **no Core roster**, rather than being forced to produce one.

That reframing — separability first, boundary second — is the single most likely route
past the failure documented in §7, and it must be answered before any Chase Opportunity
formula, any coefficient calibration, or any resumption of Overall RIP V11.

---

## Forward reference

Stage X (`CHASE_SEPARABILITY_STAGE10.md`) acted on §12's next step and returned
`CHASE_SEPARABILITY_NOT_VALIDATED`. It closed the Phase 2 card-universe gap left open in
§2 (Universe B shifts `1/HHI` by up to 53% but preserves rank order and shape class) and
showed that mixture separability finds the bulk/non-bulk split rather than the chase
boundary. Stage IX's findings below are unchanged.

Stage XI (`CHASE_EXTREME_TAIL_STAGE11.md`) then validated continuous Chase Significance
`HC_i = s_i^2/HHI` and the driver count `N_HC = D4^3/D2^2`, which is universe-invariant where
`1/HHI` moves up to 53%. Discrete rosters remain unresolved and are no longer required.
