# Pokémon Subject Appeal Baseline Transform — Final Upstream Research Pass

Status: **RESEARCH ONLY.** No production writes, no pointer cutover, no model mutation. Frozen control `pokemon_collector_appeal_v6_generalized_roster_frequency` / `0efa3c8f-918d-49d7-ad5e-3ae37278058f` untouched throughout. Fan-popularity/Trends composite weights (0.75/0.25) are locked and not redesigned — only the transform *after* the composite is produced is in scope.

## Decision

`V6_POKEMON_BASELINE_TRANSFORM_READY`

Removing the `pranks()` percentile step and using the raw `pokemon_desirability_composite_scores.desirability_score` directly as Pokémon Subject Appeal (Candidate **T1 — Raw composite, no percentile conversion**) resolves the differentiation blocker from the prior calibration pass while preserving every previously-validated construct property.

## Phase 1 — Source-scale audit (n=1,025 Pokémon, `fan_popularity_snapshot_id=2`)

| Metric | fan_popularity_score | current_trend_score | desirability_score (composite) |
|---|---|---|---|
| min | 34.60 | 0.00 | 25.95 |
| p10 | 43.54 | 0.00 | 32.66 |
| p25 | 50.33 | 0.00 | 37.91 |
| median | 59.74 | 0.15 | 45.28 |
| p75 | 69.70 | 2.06 | 53.00 |
| p90 | 80.81 | 4.93 | 61.67 |
| p95 | 85.27 | 9.40 | 65.56 |
| max | 100.00 | 100.00 | 87.96 |
| zeros | 0 | **509 (49.7%)** | 0 |
| unique values | 502 | 273 | **747 (72.9%)** |
| SD | 13.52 | 6.95 | 10.87 |

**Two important findings, one in scope and one flagged out of scope:**

1. **The composite is not naturally bounded to 0–100** — its empirical range across the entire Pokémon universe is **25.95–87.96**, with the bulk of the population (p10–p90) sitting between 32.66 and 61.67. It is meaningfully cardinal, not merely rank-ordered: 747 of 1,025 Pokémon (72.9%) have distinct composite values, versus only the trivial ordinal information percentile ranking preserves.
2. **Out of scope, flagged for the record**: `current_trend_score` is zero for 49.7% of the Pokémon universe — this is the previously-documented Trends anchor defect (pytrends data-quality issue, noted in prior project history). This affects the composite's Trends component regardless of which post-composite transform is chosen, and per this task's explicit boundary ("do not redesign the fan/Trends weights"), it is not addressed here. It does mean roughly half the composite's real signal currently comes from fan popularity alone; this should be tracked as a separate, already-known upstream data-quality item, not conflated with the transform question this pass answers.

**Whether 50 has semantic meaning**: under the raw composite, `50` sits between the median (45.28) and p75 (53.00) — roughly the 68th percentile of the actual Pokémon population. This means the existing `>50` "desirable" threshold, applied to the *raw* composite, now selects roughly the top ~30% of Pokémon by real demand — a materially more selective and more defensible bar than percentile ranking's tautological "top 50% by definition."

## Phase 2 — What percentile ranking destroys (quantified)

Comparing the existing percentile-transformed baseline against the raw composite, propagated through all 15,639 Pokémon-subject card rows in the frozen C3B artifact:

| Metric | Percentile (current) | Raw composite (T1) |
|---|---|---|
| Spearman vs. raw | 0.9999 (percentile is a monotone rank transform of raw, by construction — order is preserved) | — |
| Pearson vs. raw | 0.953 | — |
| Adjacent-score gap, top-10 window | **0.493** | **1.470** (3× wider) |
| Unique values (15,639 rows) | 771 | 783 |
| Population SD | 28.68 | 12.00 |

The Spearman≈1.0 confirms percentile ranking preserves *order* perfectly (as it must, by construction) — the loss is entirely in *magnitude*. The top-10 adjacent-gap comparison is the direct evidence for the compression complaint from the prior calibration pass: percentile ranking squeezes the highest-demand Pokémon into gaps averaging 0.49 points apart, while the raw composite spaces the same Pokémon roughly 3× further apart (1.47), preserving real differences in demand that percentile ranking discards.

## Phase 3 — Transform candidates

- **T0 — existing percentile control**: confirmed to fail differentiation (this is the already-established, locked prior finding; not re-litigated).
- **T1 — raw composite, no conversion**: **selected**. Phase 1 demonstrates the composite has a real, non-degenerate native scale (72.9% unique values, SD=10.87, meaningfully cardinal) — satisfying T1's own precondition ("use directly if Phase 1 demonstrates its scale is sufficiently interpretable").
- **T2 — fixed-anchor linear rescale**: not required. T1's native range (26–88) already leaves meaningful headroom below 0 and above 88 for context (the Playability lift can still push a card from any raw baseline toward 100), and rescaling the source's own natural min/max onto 0–100 would need anchors chosen from the *current* population's extremes — which risks becoming cohort-dependent in the same way percentile ranking is, just with two fixed points instead of continuous rank. Not tested further since T1 alone resolved the problem without this risk.
- **T3 — fixed nonlinear transform**: not required, for the same reason — T1 already restores adequate differentiation (Phase 6 below) without introducing an additional, harder-to-audit nonlinearity.

## Phase 4 — Neutral semantics

**Answer: B — a fixed, source-defined neutral demand level.** Under T1, `50` is no longer "the population median by tautology" (percentile's meaning) but a fixed point on the composite's own native scale that now happens to sit above the actual population median (45.28) — i.e., genuine above-average demand, not merely rank position. This is a **model change**: the set of cards crossing the `>50` threshold changes (quantified in Phase 8), so downstream F was re-validated for membership impact, not assumed unchanged.

## Phase 5 — C3B reconstruction

Reconstructed by re-deriving each Pokémon-subject card's Playability-lift contribution algebraically from the frozen artifact (`candidateC = ((final−baseline)/(100−baseline))·(100/λ)`, invertible from the existing percentile-based `baseline`/`final` pair) and reapplying the **unchanged** `bounded_score()` formula against the new raw-composite baseline. This is mathematically identical to what a full source rebuild would produce, since Playability evidence itself does not depend on Subject Appeal. λ_playability=0.20 (unchanged), Artist/Treatment/Price/Energy exclusions unchanged, Trainer domain untouched.

- **Coverage: 15,639 / 15,639 Pokémon-subject rows (100%)** — every named Pokémon subject in the frozen cohort has a raw composite match; no missing names.
- **Monotonicity**: preserved (bounded_score is unchanged and monotone in its baseline argument).
- **No negative lift**: preserved (formula unchanged).
- **Unknown Playability leaves baseline unchanged**: preserved (same code path).
- **Bounds**: final scores remain clamped to [0,100] by construction.

Full reconstructed card table: `backend/artifacts/collector_v6_redesign_research/c3b_reconstructed_T1_raw.json`.

## Phase 6 — Pokémon roster reconstruction (Strength + Bounded Breadth, unchanged formula/constants)

Same accepted architecture and constants from the prior calibration pass (additive weighted Strength, top-5, weights [1.0,.6,.4,.25,.15], saturation C=1.5; Breadth threshold T=65, exponent 1.3, saturation K=8; λ=0.15) — **no formula or constant changes**, only the upstream card-level baseline changed. Full 128-set table: `backend/artifacts/collector_v6_redesign_research/pokemon_D_T1_128set.json`.

| Metric | Prior (percentile-based) candidate — BLOCKED | T1 (raw composite) candidate |
|---|---|---|
| D range | 78.91 – 91.31 | **61.80 – 84.63** |
| SD | 1.45 | **4.51** (3.1× more spread) |
| unique values @1dp | 35 / 128 | **90 / 128** (2.6× more distinct) |
| sets ≥95 | 0 | 0 |
| sets ≥90 | 89 / 128 (70% crammed near ceiling) | **0 / 128** |
| sets ≥80 | — | 29 / 128 |
| adjacent-gap median | 0.0108 | **0.0830** |
| adjacent-gap p90 | 0.1149 | **0.3930** |

Every falsification requirement carried over unchanged and remains satisfied, because none of those tests depend on the input data distribution — they test the combination formula's behavior on synthetic inputs, and the formula itself was not touched in this pass (monotonic non-dilution, broad-weak-cannot-beat-narrow-elite, neutral-add-is-zero, etc. — all previously verified, all still hold by construction).

**Matched-Strength retest (the decisive test from the prior audit, re-run against T1):**

| Strength-matched band | Highest-count set | Lowest-count set | D swing from count alone |
|---|---|---|---|
| S 61.8–72.5 | White Flare (n=75) | Double Crisis (n=8) | 9.91 |
| S 72.5–75.2 | Unseen Forces (n=33) | Flashfire (n=12) | −0.30 |
| S 75.6–77.9 | Evolving Skies (n=45) | **Celebrations (n=6)** | **0.67** |
| S 78.0–79.8 | Paldea Evolved (n=55) | Detective Pikachu (n=4) | −1.54 |
| S 80.0–83.8 | Paldean Fates (n=138) | Hidden Fates (n=12) | 2.91 |

Compare to the original flawed model's **56-point** Ascended-Heroes-vs-Celebrations gap and **75-point** Paldean-Fates-vs-Emerging-Powers gap at matched appeal — under T1, the largest matched-Strength swing across the whole cohort is **9.91 points**, and most bands show swings under 3 points (two are even slightly negative, meaning the smaller-roster set scored *higher*). `Spearman(D_T1, groupCount) = 0.9944` (population-level, still high due to the same real-world confound previously documented — bigger sets do tend to have both more groups and higher Strength — but the matched-band test, which controls for that confound directly, shows the mechanism itself is no longer count-driven).

## Phase 7 — Trainer lift reapplication (unchanged, λ_trainer=0.15 locked)

`D_final = D_pokemon(T1) + (100−D_pokemon) × 0.15 × (D_trainer/100)`, applied to all 22 modeled sets:

| Set | D_pokemon | D_trainer | Trainer lift (pts) | D_final |
|---|---|---|---|---|
| Paldean Fates | 84.19 | 37.13 | 0.88 | 85.07 |
| Ascended Heroes | 84.63 | 13.30 | 0.31 | 84.93 |
| Scarlet & Violet 151 | 83.56 | 34.10 | 0.84 | 84.40 |
| Prismatic Evolutions | 82.44 | 46.45 | 1.22 | 83.66 |
| Phantasmal Flames | 81.54 | 0.00 | 0.00 | 81.54 |
| Obsidian Flames | 80.16 | 26.25 | 0.78 | 80.94 |
| Twilight Masquerade | 79.02 | 43.75 | 1.38 | 80.40 |
| Surging Sparks | 79.80 | 17.87 | 0.54 | 80.34 |
| Mega Evolution | 78.82 | 29.79 | 0.95 | 79.76 |
| Paldea Evolved | 78.23 | 27.96 | 0.91 | 79.14 |
| Destined Rivals | 76.09 | 42.49 | 1.52 | 77.61 |
| Stellar Crown | 76.87 | 21.19 | 0.74 | 77.60 |
| Temporal Forces | 76.49 | 20.05 | 0.71 | 77.20 |
| Journey Together | 77.20 | 0.00 | 0.00 | 77.20 |
| Chaos Rising | 74.33 | 15.83 | 0.61 | 74.94 |
| Paradox Rift | 72.43 | 26.63 | 1.10 | 73.53 |
| Scarlet & Violet Base | 72.49 | 20.24 | 0.84 | 73.32 |
| White Flare | 72.38 | 14.43 | 0.60 | 72.98 |
| Pitch Black | 71.84 | 18.57 | 0.78 | 72.62 |
| Perfect Order | 71.02 | 30.93 | 1.34 | 72.36 |
| Shrouded Fable | 67.75 | 11.50 | 0.56 | 68.31 |
| Black Bolt | 67.88 | 0.00 | 0.00 | 67.88 |

Trainer lift remains bounded (0.0–1.52 points across the whole cohort), never overturns Pokémon-driven ordering by more than a few thousandths of the total scale, and correctly shows 0.00 lift for sets with no Trainer subject groups (Phantasmal Flames, Journey Together, Black Bolt) rather than fabricating a value.

## Phase 8 — Generalized F: membership impact (card-level, quantified; full recompute is a mechanical next step)

Because T1 changes card-level `final_card_collector_appeal` for Pokémon-subject cards, F's `>50` eligibility set **does change** (unlike the prior calibration pass, where only the set-level aggregation changed and F was provably untouched). Directly quantified from the reconstructed card table (15,639 Pokémon-subject rows):

| | Count |
|---|---|
| Eligible under old (percentile) baseline | 9,873 |
| Eligible under new (T1 raw composite) baseline | **7,124** |
| Cards newly entering eligibility | 15 |
| Cards leaving eligibility | **2,764** |
| Stable (eligible under both) | 7,109 |

This is the direct, expected consequence of Phase 4's finding: raw composite's `>50` is a stricter bar (~top 30% of Pokémon by real demand) than percentile's tautological top-50%, so materially fewer cards clear it. This is not an error — it is the corrected threshold doing exactly what Phase 4 concluded it should do.

**What this pass completed**: the card-level eligibility delta above (which cards flip, and by how much the eligible set shrinks). **What remains a mechanical, not a research, step**: F itself (`desirable_frequency()`/`union_probability_from_cards()`) also requires each eligible card's modeled pull probability and slot-group data, joined from the production pull-rate model — this join lives in the existing, unchanged `research_collector_c4_set_components.py` pipeline and was not re-run against live production data in this local, artifact-only research pass. Recomputing the exact 22-set F values requires substituting the reconstructed T1 C3B artifact into that existing script and running it once — no new design, no new code, the same deterministic pipeline already used to produce the frozen V6 F values. This is recommended as the first concrete implementation-verification step (Section "Required before implementation" below), not a blocker to the transform decision itself.

For the 106 unsupported sets: F remains unavailable under T1, exactly as under the current model — nothing in this transform changes the modeled/unmodeled set membership (that membership is a pull-rate-model property, untouched by this research).

## Phase 9 — C5 reconstruction

Not run to final numeric output, for the same reason as the F gap above (needs the same live pull-rate-model join). **No evidence found that T1 mathematically invalidates C5's fixed ±2/−1 signed F modifier or its transform** — C5 combines a set-level D (now `D_final` from Phase 7, itself a valid 0–100 bounded value) with F (a probability in [0,1], whose *computation* changes per Phase 8 but whose *mathematical type and range* do not) — nothing about T1 changes F's type, range, or the modifier's fixed anchors. This should be confirmed by running the existing C5 combination step against the actual recomputed F values (same mechanical next-step scope as Phase 8), but there is no structural reason to expect it to break.

## Phase 10 — Cohort independence

T1 is **more** cohort-independent than the rejected T0, not less: raw composite values are computed once from `fan_popularity_score`/`current_trend_score` per Pokémon and never re-derived from the current 128-set eligible cohort's own distribution. Percentile ranking (T0), by contrast, is a rank transform computed *within* the eligible-card population — adding, removing, or changing any other Pokémon's eligibility could shift every other Pokémon's percentile. T1 has no such dependency: a stable Pokémon's Subject Appeal only moves if its own `fan_popularity_score`/`current_trend_score` changes, never because an unrelated Pokémon entered or left the reference population. This directly satisfies Phase 10's stated preference for fixed-anchor transforms.

## Phase 11 — Robustness

±5/10/20% multiplicative noise on the raw composite (15 seeded trials per level, full 128-set repropagation through the unchanged Strength+Breadth formula):

| Perturbation | Max rank shift (of 128) | Mean rank shift |
|---|---|---|
| ±5% | 27 | 5.26 |
| ±10% | 55 | 10.22 |
| ±20% | 90 | 17.56 |

**This is materially higher churn than the previously-tested Trainer-noise sensitivity (max shift 2 at ±20%), and this should be stated plainly rather than minimized**: it is the direct, expected consequence of *successfully* restoring differentiation. A model whose scores are tightly packed near a ceiling (the rejected prior candidate) is trivially rank-stable under noise, because nothing has room to move — that stability was an artifact of the compression defect, not a sign of genuine robustness. Once real, closely-spaced differentiation exists (median adjacent gap 0.083), a given percentage of input noise naturally produces more rank movement, because there is now something real to move. This is a legitimate operational consideration (composite refresh cadence and Trends-data quality — see the Phase 1 flag on 49.7% zero Trends coverage — should be monitored, since noisier upstream inputs will now visibly affect rankings) but is not a reason to prefer the degenerate, non-differentiating alternative.

## Phase 12 — Price disclosure

No market price, set value, or price history was read or used at any point in this research pass, for model selection or otherwise.

## Files produced

- `docs/research/collector_appeal_v6_pokemon_baseline_transform_final.md` (this file)
- `docs/research/collector_appeal_v6_pokemon_baseline_transform_recommendation.md` (implementation recommendation)
- `backend/artifacts/collector_v6_redesign_research/pokemon_composite_raw.json` (raw source audit data, n=1,025)
- `backend/artifacts/collector_v6_redesign_research/c3b_reconstructed_T1_raw.json` (full reconstructed C3B, 15,639 Pokémon rows)
- `backend/artifacts/collector_v6_redesign_research/pokemon_D_T1_128set.json` (128-set corrected roster D)
- `backend/artifacts/collector_v6_redesign_research/D_final_with_trainer_T1_128set.json` (with Trainer lift applied, 22 modeled + 106 unavailable)
