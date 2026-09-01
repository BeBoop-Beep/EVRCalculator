# Stage X — Chase Separability Before Boundary

## Decision

### `CHASE_SEPARABILITY_NOT_VALIDATED`

Mixture-based separability does not answer the chase question. It reliably finds the
**bulk vs non-bulk** split in a set's price distribution, which is a real statistical
boundary but is not the chase boundary. The results are inverted from the goal: the sets
with the most obvious chase structure return *no* separable core, while flat and deep sets
return "Core" rosters of 37–164 cards.

> Nothing was deployed, published or migrated. Migration 074 remains unapplied.
> `CANONICAL_OVERALL_RIP_VERSION` remains Overall RIP V10. Overall RIP V11 was not resumed.

---

## 1. Card universe (Phase 1) — CLOSED

Stage IX's gap is closed. Universe B (drawable `card_variant` rows reachable in
simulation, `pull_count > 0`) compared against Universe A (canonical card market price):

| set | A rows | B rows | N_eff A | N_eff B | Δ | Δ% |
|---|---|---|---|---|---|---|
| Black Bolt | 175 | 407 | 13.30 | 20.36 | +7.06 | **+53.0** |
| White Flare | 173 | 405 | 14.98 | 22.66 | +7.68 | **+51.3** |
| Prismatic Evolutions | 181 | 448 | 8.37 | 10.81 | +2.44 | +29.2 |
| Obsidian Flames | 230 | 406 | 11.96 | 14.66 | +2.70 | +22.6 |
| Ascended Heroes | 305 | 464 | 10.82 | 11.41 | +0.59 | +5.5 |
| Paradox Rift | 266 | 428 | 35.53 | 37.58 | +2.05 | +5.8 |
| Shrouded Fable | 107 | 162 | 23.91 | 24.84 | +0.93 | +3.9 |
| Phantasmal Flames | 132 | 214 | 2.56 | 2.63 | +0.07 | +2.6 |
| Paldean Fates | 247 | 326 | 6.99 | 7.09 | +0.10 | +1.4 |

**Verdict — not `CHASE_SEPARABILITY_BLOCKED_CARD_UNIVERSE`.** The universe choice moves
`N_eff` magnitude materially (up to +53%) but preserves rank ordering and shape class
throughout: Phantasmal Flames stays the most concentrated set in both universes,
Paradox Rift stays the flattest. Structural conclusions survive.

**Authoritative universe: B, where it exists.** It is what is actually drawable. But
`simulation_card_variant_pull_rates` is populated only for the **22 simulated modern
sets** — vintage sets have no Universe B at all. Cross-era work is therefore forced onto
Universe A, and absolute `N_eff` values must always be reported with the universe that
produced them. The two are not magnitude-comparable.

## 2. Methodology (Phases 2–6)

Implemented in `backend/research/chase_separability_stage10.py`:

* 1-D Gaussian mixtures on **log value** (scale invariance by construction), fitted by EM
  with deterministic quantile initialisation, k = 1, 2, 3;
* BIC model selection with a **ΔBIC ≥ 10** toll on each extra component;
* separation gates: Ashman **D ≥ 2.0**, upper-component **posterior ≥ 0.80**, membership
  **≥ 3 cards and ≥ 2%** of the set, variance floor against single-point collapse;
* Silverman critical-bandwidth bootstrap test as **independent** modality evidence;
* bootstrap resampling and independent per-card price shocks for stability.

No sealed-product economic variable is read anywhere (Phase 15 satisfied).

## 3. Synthetic truth set (Phase 7) — 3 / 5

| case | expected | result | verdict |
|---|---|---|---|
| A — one hero (`1000, 80, 70, 65`, bulk 1–20) | separable small Core | `UPPER_TAIL_PRESENT_BUT_CONTINUOUS` | **FAIL** |
| B — multi-Core (`500,450,400,360`, then 70,60) | Core cluster | `CORE_SEPARABLE`, Core = 4 | PASS |
| C — Core + Extended + bulk | 3 components | `CORE_AND_EXTENDED_SEPARABLE` | PASS |
| D — power-law decline | no forced Core | `UPPER_TAIL_PRESENT_BUT_CONTINUOUS`, Silverman p = 0.825 | PASS |
| E — flat expensive tail | weak/no Core | `CORE_SEPARABLE`, Core = 10 | inconclusive¹ |
| F — ×10, ×100 on all cases | identical classification | **0 changes** | PASS |

¹ Case E as constructed has a genuine gap between the tail (68) and the bulk (1–20), so
finding a component there is arguably correct. The synthetic was mis-specified, not the
method.

**Case A is the important failure.** Diagnostics: the k=2 fit *does* locate the upper
component (μ = 4.24 ≈ log 70, weight 3.5%, 4 members) but ΔBIC = **2.36** against a
required 10, and Ashman D = **1.96** against a required 2.0. A 4-card tier inside a
124-card set produces too little likelihood gain to pay the BIC toll for three extra
parameters. **Mixture selection is structurally underpowered exactly where chase tiers
live.**

## 4. Cross-era results (Phase 8) — INVERTED

Universe A, 2026-08-31 basis.

| set | era | n | state | Core | Silverman p |
|---|---|---|---|---|---|
| Champion's Path | SWSH | 81 | `UPPER_TAIL_PRESENT_BUT_CONTINUOUS` | — | 0.033 |
| Phantasmal Flames | SV | 132 | `UPPER_TAIL_PRESENT_BUT_CONTINUOUS` | — | 0.200 |
| Base | vintage | 102 | `UPPER_TAIL_PRESENT_BUT_CONTINUOUS` | — | 0.427 |
| Fossil | vintage | 62 | `UPPER_TAIL_PRESENT_BUT_CONTINUOUS` | — | 0.700 |
| Neo Destiny | vintage | 113 | `UPPER_TAIL_PRESENT_BUT_CONTINUOUS` | — | 0.373 |
| Jungle | vintage | 64 | `DISTRIBUTED_VALUE` | — | 0.213 |
| Crown Zenith | SWSH | 161 | `CORE_SEPARABLE` | **50** | 0.107 |
| Shrouded Fable | SV | 107 | `CORE_SEPARABLE` | **37** | 0.007 |
| Paradox Rift | SV | 266 | `CORE_SEPARABLE` | **104** | 0.000 |
| Evolving Skies | SWSH | 237 | `CORE_SEPARABLE` | **107** | 0.020 |
| Cosmic Eclipse | SM | 271 | `CORE_SEPARABLE` | **130** | 0.153 |
| Paldean Fates | SV | 247 | `CORE_SEPARABLE` | **164** | 0.007 |

**Hero sets:** Champion's Path (a famously two-card set) and Phantasmal Flames both return
no core. Their k=2 fits post large ΔBIC (83.14 and 46.34) but Ashman D of **1.98** and
**1.95** — both fractionally under threshold — and in each case the fitted "upper
component" holds 28–48 cards, i.e. 35% of the set. Even when it fits, it is not finding
the hero pair.

**Deep/flat sets:** the returned rosters of 104–164 cards are not chase rosters. They are
the non-bulk half of the set.

**Vintage sets:** Base, Fossil and Neo Destiny all return continuous. Stage IX's worry —
that wide vintage dispersion erases top-value structure — is confirmed under this method
too, via a different mechanism (ΔBIC of −6.44 for Fossil, −4.52 for Neo Destiny: the
one-component model is *preferred*).

### Root cause

In a 100–300 card set the dominant modal split in log price is between ~150 bulk commons
at $0.10–0.30 and ~100 non-bulk cards at $1–100. That is a real bimodality, and it is what
BIC selects every time. The chase tier — 2 to 6 cards — is a rounding error in the
likelihood by comparison. **The method answers "where does bulk end", not "where does
chase begin".**

## 5. Stability (Phases 9–10)

| set | state | Core | bootstrap Jaccard | ±2% | ±5% | ±10% |
|---|---|---|---|---|---|---|
| Crown Zenith | CORE_SEPARABLE | 50 | **0.181** | 1.000 | 0.998 | 0.994 |
| Shrouded Fable | CORE_SEPARABLE | 37 | **0.199** | 1.000 | 1.000 | 0.999 |
| Paradox Rift | CORE_SEPARABLE | 104 | **0.235** | 1.000 | 1.000 | 1.000 |
| Cosmic Eclipse | CORE_SEPARABLE | 130 | **0.261** | 0.995 | 0.991 | 0.974 |
| Evolving Skies | CORE_SEPARABLE | 107 | **0.285** | 1.000 | 1.000 | 1.000 |
| Paldean Fates | CORE_SEPARABLE | 164 | **0.302** | 1.000 | 1.000 | 1.000 |

**Bootstrap Jaccard of 0.18–0.30 disqualifies every roster this method produced.** A
boundary that retains under a third of its membership under resampling is not a boundary.

The contrast is diagnostic: per-card price noise leaves membership essentially untouched
(Jaccard ≈ 1.0) because the boundary sits deep inside the bulk where ±10% moves nothing,
while *resampling the population* destroys it. That pattern is the signature of a boundary
determined by the bulk's shape rather than by any real structural feature.

**Uniform scale invariance: 12 / 12 sets exactly invariant** at 0.5×, 2× and 10×. This is
the one unambiguous success, and it confirms the log-value formulation is the correct frame
for any future rule.

## 6. EV-HHI (Phase 14) — NOT RUN

Deferred honestly rather than rushed. It is only meaningful on Universe B (pull rates
exist only there), which covers 22 modern sets and no vintage set, so the cross-era
comparison this phase asks for cannot currently be made. Recommend running it as a
modern-only comparison in a later stage, clearly scoped as such.

## 7. Human labels (Phase 16) — UNCHANGED

`docs/research/chase_labeling_v1/chase_labels_template.csv` remains **0 / 448** populated.
No new packet was generated: Phase 16 conditions it on the methodology producing plausible
candidates, and it did not.

## 8. Architecture consequence

Stage IX's split stands and is reinforced:

| concept | status |
|---|---|
| **Chase concentration / depth** — `HHI_value`, `1/HHI` | **validated**, continuous, always measurable, scale-invariant, universe-sensitive in magnitude |
| **Chase roster** — discrete Core/Extended | **still unresolved.** Two independent method families have now failed: Stage IX's threshold/cliff/outlier rules, and Stage X's mixture separability |
| **Product Chase Opportunity** | still blocked — it consumes a fixed set roster that does not yet exist |
| **Economic Chase Efficiency** | unaffected; inherits the retired 3×C machinery |

## 9. Next research step

**Treat the chase tier as an extreme-value problem, not a mixture problem.**

Every method tried so far — thresholds, cliffs, robust outliers, finite mixtures — asks
where one population ends and another begins, and is therefore dominated by the largest
population in the set. The chase tier is not a second population; it is the **tail** of
one, and the question is where the tail's behaviour changes.

The appropriate tooling is threshold selection from extreme value theory: peaks-over-
threshold with a generalised Pareto fit, Hill-estimator stability plots, or the
mean-excess plot's departure from linearity. These are designed for exactly the regime
that defeated BIC — locating a tail boundary from a handful of extreme observations,
with the bulk explicitly excluded rather than competing for likelihood.

That test should be run before any Chase Opportunity formula, any coefficient calibration,
or any resumption of Overall RIP V11.

---

## Forward reference

Stage XI (`CHASE_EXTREME_TAIL_STAGE11.md`) acted on §9's next step. It **rejected** EVT on
the synthetic gate (tail K of 23/35/30/37 for true counts of 1/2/5/3) and instead validated
a continuous HHI-derived Chase Significance, returning
`CHASE_SIGNIFICANCE_VALIDATED__DISCRETE_TIERS_UNRESOLVED`. Stage X's findings below are
unchanged.
