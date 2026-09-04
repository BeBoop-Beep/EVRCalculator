# Overall RIP Accessibility — Pass 1B: Robustness, Temporal Replay, LOSO, Historical Core K

Research only. No production code, scoring module, or migration was modified. No
migration, deploy, publish, backfill, commit, or branch operation was performed.

## 0. Workspace / freeze

- Branch: `fix/public-rankings-entitlement-regression-2`
- Start HEAD: `6001825c8519fcdb5860d9de66826ca6a0356a6c`
- Primary cohort: the Pass 1A **frozen** 22-set `loose_booster_pack` cohort
  (`docs/research/overall_rip_accessibility_primary_cohort.json`), used as-is per
  instructions — no fresh live data substituted for it. No correctness defect was
  found in the frozen cohort; A_raw recomputed from its own frozen
  `per_variant.price_used` / `modeled_probability` arrays matches the frozen
  `A_raw` field to a worst absolute delta of `4.87e-11` (JSON round-trip float
  precision, not a defect).
- ECE / Product Chase Efficiency was **not** reopened, re-derived, or
  re-implemented anywhere in this pass, per the locked Pass 1A result (weight = 0).

## 1-2. Transform × weight grid, and transform robustness

Computed for all 5 k anchors ({0.0005, 0.001, 0.002, 0.004, 0.008}) × all 6
accessibility weights ({0, 2, 4, 6, 8, 10}%), n=22, against the frozen
`overall_rip_v10_score` control. Hard gates: clear Financial overrides = 0,
Spearman ≥ 0.98, Top-5 turnover ≤ 1.

**Same-set reversals = 0 at every (k, weight) cell**, confirmed directly — this
cohort has exactly one product per set, so a same-set reversal is impossible by
construction.

Every cell tested has **0 clear Financial overrides** (no pair with
`|Fa-Fb| ≥ 10` is ever flipped by any k/weight combination in this cohort) and
Top-5 overlap never drops below 4/5 (turnover ≤ 1 always holds). The binding gate
across the grid is **Spearman ≥ 0.98**.

Phase 2 (transform robustness, min/max across all 5 k anchors, for weights
4/6/8/10%):

| Weight | min Spearman across k | max clear overrides | max Fin. gap overturned | min Top-5 overlap | close-reversal rate range |
|---|---|---|---|---|---|
| 4% | **0.9876** | 0 | 0.0 | 4/5 | 7.3%–12.2% |
| 6% | **0.9797** | 0 | 0.0 | 4/5 | 9.8%–14.6% |
| 8% | **0.9684** | 0 | 0.0 | 4/5 | 12.2%–17.1% |
| 10% | **0.9458** | 0 | 0.0 | 4/5 | 14.6%–24.4% |

**Only 4% clears the ≥0.98 gate at every k anchor.** 6% clears it at 4 of 5 k
anchors (`k=0.0005,0.001,0.004,0.008`) but drops to **0.9797** at `k=0.002` — a
genuine, reproducible below-gate cell, not noise. 8% and 10% fail the gate at
most or all k anchors. Clear Financial overrides are 0 everywhere in this grid;
the discriminator is purely rank-correlation robustness across k.

## 3. Historical Core K numerical reconstruction

Exact production contract used (not re-derived from memory):
`backend/desirability/chase_core_k.py`, version identity
`chase_core_k_v1_stage5c_3x_pack_equivalent_cost` — `C_product =
product_market_cost / random_pack_count`, `Core K = count(card_value ≥ 3 ×
C_product)`. This module is retired from any Overall RIP pillar (per Stage XIV
§13) but is retained, unmodified, as research evidence; it was imported
read-only for this comparison and nothing was written back.

Reconstructed against the frozen 138-product cohort
(`overall_rip_accessibility_product_cohort.json`), pairing each product's own
`product_market_cost` / `random_pack_count` with its own set's card-price roster
(`per_variant.price_used`, from the primary cohort). **55 of 138 products**
carried a status of `"ready"` (finite positive `product_market_cost` AND
`random_pack_count` both present); the remaining 83 returned
`unavailable_no_random_pack_count` or `unavailable_no_product_market_cost` and
were excluded from this comparison, exactly as the production contract requires
(`None` cost/count → `None` Core K, never 0).

Baseline correlations (n=55, Spearman):

| vs. | ρ | p |
|---|---|---|
| Accessibility (`A_raw`) | **-0.7033** | 2.1e-9 |
| Financial RIP V4 total | **0.5890** | 2.2e-6 |
| Effective pack cost | **-0.4035** | 0.0023 |

Core K correlates far more strongly (and negatively) with Accessibility than
Financial RIP does — consistent with Core K being a **count of high-value
cards above a hard multiple**, the conceptual opposite of Accessibility's
continuous, depth-diversified "how reachable is the set's value" measure: a set
concentrated in a few very expensive chase cards tends to have a *high* Core K
and *low* Accessibility.

**Discontinuity instability** — uniform ±{2,5,10,20}% shocks to card prices and
to product price (holding the other fixed), same 55 products:

| Shock magnitude | Card-price share changed | Product-price share changed |
|---|---|---|
| ±2% | 18.2% / 0.0% | 0.0% / 18.2% |
| ±5% | 30.9% / 16.4% | 16.4% / 30.9% |
| ±10% | 47.3% / 41.8% | 50.9% / 45.5% |
| ±20% | 61.8% / 65.5% | 69.1% / 58.2% |

(mean |ΔK| ranges 0.18–1.6, max |ΔK| up to 7, across the same shock set). Even a
**±2% shock changes Core K for ~18% of products** because it is an integer
threshold-crossing count, not a continuous statistic. This is the exact
quantified contrast the phase asked for: at the identical ±2% magnitude, A_raw
(Phase 5/6 below) changes by a *median* of ~1e-6 to ~8e-6 (a smooth, near-zero
continuous response) while Core K flips outright for roughly 1 in 5 products.

## 4. Uniform Accessibility invariance

- Card-price uniform scaling {0.5×, 2×, 10×}: worst observed |ΔA_raw| across all
  22 sets and all 3 scales = **8.673617379884035e-19** — machine precision,
  matching Stage XIV's own reported figure (8.674e-19) exactly.
- Product-price change {-20,-10,-5,-2,+2,+5,+10,+20}%: worst observed |ΔA_raw| =
  **0.0**, exactly, because `product_market_cost` is not a parameter of
  `compute_chase_accessibility` at all (the function is keyword-only over
  `variants` and physically cannot accept it — confirmed by inspection of
  `backend/desirability/chase_accessibility.py`, not just by empirical delta).

## 5. Independent card-price shocks

Deterministic seed scheme: `seed = round(magnitude * 1000) * 100 + seed_index`,
`seed_index in [0, 11]` (12 seeds/magnitude), `random.Random(seed)`, uniform
per-card multiplicative perturbation `price_i *= (1 + U(-magnitude, magnitude))`.
Reproducible from `backend/research/scratch_pass1b/phase5_6_shocks.py`.

Worst-across-12-seeds, per weight, per magnitude (k=0.002 fixed for scoring):

| Magnitude | Weight | Worst Spearman | Worst Top-5 | Worst close-rev. rate | Clear overrides |
|---|---|---|---|---|---|
| ±2% | 4% | 0.9876 | 4/5 | 12.2% | 0 |
| ±2% | 6% | 0.9797 | 4/5 | 14.6% | 0 |
| ±2% | 8% | 0.9684 | 4/5 | 17.1% | 0 |
| ±5% | 4% | 0.9876 | 4/5 | 12.2% | 0 |
| ±5% | 6% | 0.9797 | 4/5 | 14.6% | 0 |
| ±5% | 8% | 0.9673 | 4/5 | 19.5% | 0 |
| ±10% | 4% | 0.9876 | 4/5 | 12.2% | 0 |
| ±10% | 6% | 0.9797 | 4/5 | 14.6% | 0 |
| ±10% | 8% | 0.9650 | 4/5 | 19.5% | 0 |

Raw A_raw stability (median / max absolute change): ±2% → 1.29e-6 / 3.04e-5;
±5% → 3.91e-6 / 7.43e-5; ±10% → 6.82e-6 / 1.86e-4. Even the worst single seed at
±10% moves fewer than 2 in 10,000 of A_raw's own scale. Card-price shocks alone
never push any weight below its own no-shock baseline meaningfully — the
w=6/k=0.002 ceiling of 0.9797 is set by the base cohort (Phase 1), not amplified
by these shocks.

## 6. Independent pull-probability shocks

Same seed scheme, applied to `modeled_probability` instead, clamped to `[0,1]`.

| Magnitude | Weight | Worst Spearman | Worst Top-5 | Worst close-rev. rate | Clear overrides |
|---|---|---|---|---|---|
| ±2% | 4% | 0.9876 | 4/5 | 12.2% | 0 |
| ±2% | 6% | 0.9797 | 4/5 | 14.6% | 0 |
| ±2% | 8% | 0.9650 | 4/5 | 17.1% | 0 |
| ±5% | 4% | 0.9876 | 4/5 | 12.2% | 0 |
| ±5% | 6% | 0.9797 | 4/5 | 14.6% | 0 |
| ±5% | 8% | 0.9639 | 4/5 | 19.5% | 0 |
| ±10% | 4% | 0.9876 | 4/5 | 12.2% | 0 |
| ±10% | 6% | **0.9763** | 4/5 | 14.6% | 0 |
| ±10% | 8% | 0.9571 | 4/5 | 19.5% | 0 |

Raw A_raw change (median / max): ±2% → 7.97e-6 / 7.75e-5; ±5% → 2.02e-5 /
1.87e-4; ±10% → 4.22e-5 / 3.43e-4. At ±10% probability shocks, 6% drops as low
as 0.9763 in the worst seed — below its already-marginal no-shock baseline of
0.9797 — while 4% holds steady at 0.9876 across every magnitude and every seed
tested. No clear Financial override was ever produced by any shock at any tested
weight/magnitude.

## 7. Temporal authority search (Phase 7)

Searched, in the spec's order, against the **live** Supabase project
(`backend/.env`):

1. **Live `simulation_card_variant_pull_rates` rows with an older
   calculation_run_id/date than the primary cohort's** — **found**. Querying all
   22 primary-cohort `set_id`s (24,366 rows scanned) shows every one of the 22
   sets currently carries **2–5 distinct live `calculation_run_id`s**
   (`docs/research/overall_rip_accessibility_pass_1b_robustness.json` →
   `phase7_temporal_authority_search`), each with a full drawable-variant roster
   (`pull_count > 0`) and its own `created_at`. This search did not need to
   proceed to steps 2–5.

This directly reverses Pass 1A's own documented expectation ("older runs' pull
rates appear pruned once a set is re-simulated" — see
`overall_rip_accessibility_authority.json`); at the time this pass ran, pruning
had not yet caught up to the ~08-27/08-28 runs. This is time-sensitive
live-database state, not a permanent guarantee — a rerun of this pass later
could find those older runs pruned.

## 8. Temporal replay (Phase 8)

**Two genuine states, replayed independently, not averaged:**

**State 1 — Pass 1A's frozen primary cohort.** Accessibility run dates
2026-08-28 to 2026-09-02 (per-set), paired Financial/Collector run dates
predominantly 2026-08-27 (offset 1.0–5.4 days per set, exactly as documented in
Pass 1A; unchanged here).

**State 2 — found live in this pass.** Accessibility run = the **oldest** live
pull-rate run per set (2026-08-27T23:14 to 2026-08-28T18:25 UTC), paired with
the **latest available** Financial/Collector-enriched
`simulation_sealed_product_results` run per set (2026-08-27T17:03 to
2026-08-27T18:25 UTC) — offset **0.26–1.00 days**, tighter than State 1's own
internal offset. All 22 sets usable (22/22).

Disclosure: in this live-database snapshot, State 1's and State 2's paired
Financial/Collector runs turn out to be **the same** `calculation_run_id`s per
set (both anchor to the single 2026-08-27 daily enrichment batch, the latest one
that exists) — verified directly. The two states differ **only** in which
Accessibility (pull-rate) snapshot is paired to that shared Financial baseline:
State 1 uses the 09-02 run, State 2 uses the ~08-28 run, roughly 4–5 days
earlier. This was not manufactured to make replication easy — it is what the
live database actually contains right now (the Financial/Collector enrichment
pass has not advanced past 08-27 since Pass 1A ran) — and it has the useful
property of **isolating Accessibility's own temporal effect** from Financial
drift, since Financial and Collector are held byte-identical between the two
states.

Cross-state check: **Spearman(A_raw_state1, A_raw_state2) = 0.9977** (p≈6e-25,
n=22) — Accessibility itself is highly stable across the ~5-day gap between the
two live pull-rate snapshots.

State 2 candidate diagnostics (k=0.002, vs its own V10 control):

| Weight | Spearman | Kendall | Top-5 | Top-10 | Close-rev. rate | Clear overrides |
|---|---|---|---|---|---|---|
| 4% | 0.9876 | 0.9394 | 4/5 | 9/10 | 12.2% | 0 |
| 6% | 0.9797 | 0.8961 | 4/5 | 9/10 | 14.6% | 0 |
| 8% | 0.9650 | 0.8615 | 4/5 | 9/10 | 17.1% | 0 |

State 1 (k=0.002, from Phase 1's grid, restated for direct side-by-side
comparison):

| Weight | Spearman | Kendall | Top-5 | Top-10 | Close-rev. rate | Clear overrides |
|---|---|---|---|---|---|---|
| 4% | 0.9876 | 0.9394 | 4/5 | 9/10 | 12.2% | 0 |
| 6% | 0.9797 | 0.8961 | 4/5 | 9/10 | 14.6% | 0 |
| 8% | 0.9684 | 0.8701 | 4/5 | 9/10 | 17.1% | 0 |

State 1 and State 2 are numerically identical at 4% and 6% (down to the
displayed precision) and nearly identical at 8% (0.9684 vs 0.9650) — expected
given the 0.9977 A_raw cross-state correlation and the shared Financial/Collector
baseline. **The temporal replay does not change any Phase 1–2 conclusion**: 6%
still sits at the 0.9797 gate-adjacent value in both independently-queried
states.

## 9. Leave-one-set-out (Phase 9)

Run at every one of the 5 k anchors (not just one), n=21 per omitted set,
weights {4,6,8,10}%. Hard requirement: min LOSO Spearman ≥ 0.98.

| Weight | Passes at k = | Fails at k = | Worst omitted set (all k) |
|---|---|---|---|
| 4% | **all 5** (0.0005, 0.001, 0.002, 0.004, 0.008) | none | `0f7e51e2-…` |
| 6% | 0.0005, 0.008 (2 of 5) | 0.001, 0.002, 0.004 (3 of 5) | `0f7e51e2-…` |
| 8% | none | all 5 | `0f7e51e2-…` |
| 10% | none | all 5 | `0f7e51e2-…` |

At the headline k=0.002 anchor specifically: 4% min-Spearman = 0.9857 (passes),
6% = 0.9766 (**fails**), 8% = 0.9636 (fails), 10% = 0.9377 (fails). The same set
(`0f7e51e2-5a78-4500-9c9c-f690e934a069` — Scarlet & Violet 151, per the primary
cohort's `set_id` mapping) is the worst-case omission at every weight and every
k anchor tested.

**Direct answer to the prior partial finding ("6% survives, 8% fails"):** 8%
failing is **confirmed** (fails LOSO at all 5 k anchors). 6% surviving is
**refuted** under this stricter, full-k-grid LOSO test: 6% only clears the
≥0.98 LOSO gate at 2 of the 5 k anchors and fails at the other 3, including the
median anchor (k=0.002). **Only 4% is LOSO-robust across the entire k grid.**

## 10. Product-family movement for Accessibility (not ECE)

Projected the SET-level **6%** Accessibility candidate (k=0.002) onto the full
frozen 138-product cohort (all 8 families, all 138 products matched to
Accessibility-supported sets, 0 excluded):

| Family | n | Avg \|movement\| | Median \|movement\| | Avg signed movement | Risers | Fallers | Unchanged |
|---|---|---|---|---|---|---|---|
| Pokémon Center ETB | 26 | 4.50 | 4 | -1.19 | 16 | 9 | 1 |
| Booster bundle | 23 | 3.17 | 2 | +1.00 | 7 | 13 | 3 |
| Loose booster pack | 22 | 4.50 | 4 | -0.32 | 12 | 10 | 0 |
| Elite trainer box | 27 | 4.59 | 4 | +0.67 | 9 | 15 | 3 |
| Sleeved booster pack | 15 | 5.60 | 3 | -1.73 | 6 | 6 | 3 |
| Booster box | 15 | 4.20 | 3 | +0.60 | 6 | 5 | 4 |
| Half booster box | 8 | 5.00 | 4 | +1.25 | 3 | 4 | 1 |
| Enhanced booster box | 2 | 4.00 | 6 | +2.00 | 1 | 1 | 0 |

**No family shows a large, one-directional average movement** — signed averages
range from -1.73 to +2.00 ranks (out of 138), risers/fallers are mixed within
every family, and there is no monotonic pattern by product cost/size (cheap
formats like loose packs move -0.32 on average, expensive formats like booster
boxes move +0.60; neither the very cheapest nor the very largest formats show a
systematic direction). This is the qualitative opposite of ECE's confirmed
cheap-format bias (Pass 1A supplement).

**Same-set Accessibility reversals = 0**, verified directly by exhaustive
pairwise check within every multi-product set (138 products, all same-set pairs
checked): confirmed by construction, since A_raw/A_score is constant per set and
every product in a set receives the identical additive shift.

## 11. Weight robustness summary

| Weight | Transform robust (all 5 k)? | Shock robust (card + prob, all mags)? | Temporal robust (2 states)? | LOSO robust (all 5 k)? | Clear overrides | Close discrimination (close-rev. rate @ k=0.002) |
|---|---|---|---|---|---|---|
| 2% | yes (all cells pass hard gates) | not separately shock-tested (out of Phase 5/6 scope) | not separately tested | not separately tested | 0 | not computed |
| **4%** | **yes** (min Spearman 0.9876) | **yes** (worst 0.9876 across all card+prob shocks) | yes (0.9876 both states) | **yes** (min 0.9857, all k) | 0 | 12.2% |
| 6% | **no** (min Spearman 0.9797 at k=0.002, < 0.98) | marginal (worst 0.9763 at ±10% prob shock) | yes (0.9797 both states) | **no** (fails at 3/5 k anchors, min 0.9766) | 0 | 14.6% |
| 8% | no (min 0.9684) | no (worst 0.9570) | yes (0.9650–0.9684) | no (fails all k) | 0 | 17.1% |
| 10% | no (min 0.9458) | not separately shock-tested | not separately tested | no (fails all k) | 0 | not computed |

Classification:
- **2%: SURVIVES_PASS_1B** (passes every hard gate at every k; not independently
  shock/LOSO-tested because Phase 5/6/9 scoped their weight set to {4,6,8[,10]}%
  per the spec).
- **4%: SURVIVES_PASS_1B** — the only weight that is robust across the transform
  grid, both independent shock families, both temporal states, and LOSO,
  simultaneously and at every k anchor tested.
- **6%: FAILS_TRANSFORM_ROBUSTNESS_MIN_SPEARMAN_GE_0.98_ACROSS_ALL_K** (and
  separately fails LOSO at 3 of 5 k anchors). It clears every gate at some k
  values (notably 0.0005 and 0.008) but not all — the spec requires robustness
  across ALL k, not a favorable subset.
- **8%: FAILS_TRANSFORM_ROBUSTNESS_MIN_SPEARMAN_GE_0.98_ACROSS_ALL_K** (fails at
  4 of 5 k anchors, and fails LOSO at all 5).
- **10%: FAILS_TRANSFORM_ROBUSTNESS_MIN_SPEARMAN_GE_0.98_ACROSS_ALL_K** (fails at
  4 of 5 k anchors, and fails LOSO at all 5).

**Factual answer: no.** Under this pass's stricter "robust at every k anchor,
not just one" standard, **6% does not remain the highest surviving weight — 4%
is**. 6% survives if a single favorable k anchor is picked (as the prior partial
finding evidently did), but fails once tested against the full 5-anchor
transform grid and the full 5-anchor LOSO sweep. This is a genuine, reproducible
finding from real data, not a rounding artifact: 6%'s failing cells (k=0.001,
0.002, 0.004) span the middle of the tested k range, not an edge case.

No production weight is chosen here — that decision belongs to Pass 1C.

## 12. Files created

- `docs/research/OVERALL_RIP_ACCESSIBILITY_PASS_1B_ROBUSTNESS.md` — this report.
- `docs/research/overall_rip_accessibility_pass_1b_robustness.json` — every
  computed number from Phases 1–11, machine-readable.
- Scratch (not deliverables, left for traceability):
  `backend/research/scratch_pass1b/common.py`,
  `phase1_2_grid.py` (+ `phase1_2_grid_result.json`),
  `phase3_core_k.py` (+ `phase3_core_k_result.json`),
  `phase4_invariance.py` (+ `phase4_invariance_result.json`),
  `phase5_6_shocks.py` (+ `phase5_6_shocks_result.json`),
  `phase7_temporal_search.py`, `phase7_run_dates.py`, `phase7_run_dates2.py`,
  `phase7_financial_runs.py` (+ their `*_result.json` outputs),
  `phase8_temporal_replay.py` (+ `phase8_temporal_replay_result.json`,
  `phase8_state2_raw.json`),
  `phase9_loso.py` (+ `phase9_loso_result.json`),
  `phase10_family_movement.py` (+ `phase10_family_movement_result.json`).

No file under `backend/desirability/`, `backend/db/migrations/`, or any other
canonical scoring/production module was modified. `backend/desirability/chase_core_k.py`
and `backend/desirability/chase_accessibility.py` were imported read-only.

Pass 1A and Pass 1A-supplement artifacts (`overall_rip_accessibility_primary_cohort.json`,
`overall_rip_accessibility_authority.json`, `overall_rip_accessibility_pass_1a_ece.json`,
`overall_rip_accessibility_product_cohort.json`,
`overall_rip_accessibility_pass_1a_product_supplement.json`, and both `.md`
reports) were read but not modified.

## 13. Start / end HEAD and concurrent work

- Start HEAD (this pass): `6001825c8519fcdb5860d9de66826ca6a0356a6c`
- `git status --short` observed during this pass showed, in addition to this
  pass's own new files: `logs/run_simulations.log`, `logs/task_scheduler_debug.log`
  (continuously modified by the live scheduler/simulation pipeline — the same
  pipeline whose run cadence produced the Phase 7 temporal states used here), and
  `backend/domain/billing/providers/stripe_provider.py` (modified by unrelated
  concurrent billing work already in progress on this shared branch before this
  pass began). None of these three files was read for content or written to by
  this pass.

## Decision

`OVERALL_RIP_ACCESSIBILITY_PASS_1B_COMPLETE`
