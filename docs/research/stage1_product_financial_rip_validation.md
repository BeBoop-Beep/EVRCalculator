# Stage 1: is Financial RIP V3 valid for 6- and 36-pack sealed products?

**Assessment date:** 2026-08-15
**Financial RIP version:** `financial_rip_v3` (normalization unchanged)
**Verdict:** `NOT_VALIDATED_FOR_CROSS_FORMAT_RANKING`

Companion artifacts:

- `stage1_product_financial_rip_validation_data.md` — full generated tables (raw inputs, normalized scores, clipping, components) by family
- `stage1_product_financial_rip_validation.json` — the same, machine-readable
- `stage1_pack_count_control.json` — the controlled pack-count experiment below

Nothing in this study changed a formula, a weight, an anchor or a pack count.

---

## 1. What was asked

Financial RIP V3's normalization anchors are **absolute and fixed**, and the
config documents them against **pack-level** quantities: P(pack value ≥ pack
cost), P50/cost, Q95/cost, the 95th–99th pack tail, the top-1% pack tail. Stage 1
feeds those same anchors a 6-pack and a 36-pack distribution.

The question is not "do booster boxes score lower". It is:

> Does the same normalization scale still meaningfully distinguish good from bad
> products within and across these opening sizes, or is pack count itself
> overwhelming the intended economic signal?

## 2. Evidence base

53 Stage 1 product rows across 22 simulation-supported sets, each from a real
1,000,000-outcome pack simulation and each scored against its own real sealed
market price:

| family | packs | products | sets |
|---|---|---|---|
| `sleeved_booster_pack` | 1 | 15 | 15 |
| `booster_bundle` | 6 | 23 | 22 |
| `booster_box` | 36 | 15 | 15 |

> **Provenance, stated plainly.** `simulation_sealed_product_results` is **empty
> in production** — Stage 1 has never run there. These rows were produced by
> `backend/scripts/collect_stage1_product_dry_run.py`, which runs the real pack
> simulation and the real Stage 1 scoring path in memory and persists nothing.
> They are the same payloads the runner would write, not a substitute model, but
> they are **not** persisted production rows.

## 3. Within-family behaviour: healthy

**No input is clipped anywhere.** Across all 53 products and all nine raw V3
inputs, the lower-bound and upper-bound clip rates are **0.0%**. There is no
floor saturation, no ceiling saturation, and no metric pinned at a knot. The
concern that multi-pack distributions would push inputs off the end of their
fixed transforms did not materialise.

Scores stay in a usable band and keep separating products:

| family | score min | median | max | IQR | range |
|---|---|---|---|---|---|
| `sleeved_booster_pack` | 19.53 | 29.94 | 38.40 | 3.21 | 18.86 |
| `booster_bundle` | — | 27.14 | — | 11.02 | 37.29 |
| `booster_box` | 21.70 | 31.64 | 51.14 | 13.48 | 29.44 |

Note the direction: **the 36-pack family is the least compressed, not the most.**
Booster boxes have the widest interquartile spread of the three. The predicted
"large products all collapse to the same score" failure did **not** occur.

Every component still contributes non-trivial separation within each family, with
one exception (below), and no single component's contribution spread exceeds ~42%
of the total in any family. Within-format ranking is intact.

## 4. The one mechanical distortion that is real

Concentration does exactly what the mathematics predicts, and it moves the tail
metrics hard:

| raw input (median) | 1 pack | 6 packs | 36 packs |
|---|---|---|---|
| `jackpot_tail_mean_ratio` | 10.23 | 4.27 | **1.63** |
| `p99_threshold_ratio` | 4.17 | 3.23 | **1.39** |
| `realistic_tail_mean_ratio` | 2.11 | 1.70 | 1.21 |
| `typical_retention_ratio` | 0.17 | 0.22 | **0.39** |
| `base_rtp_excluding_top_1pct` | 0.31 | 0.34 | 0.45 |
| `true_win_probability` | 0.060 | 0.050 | 0.046 |

Upside ratios fall by ~6× and retention ratios roughly double, purely from
aggregation. The consequence for Jackpot Upside is severe: its within-family
score IQR falls from **12.85 (1 pack) → 14.46 (6) → 2.72 (36)**, and its median
normalized score from 15.70 → 6.33. **At 36 packs, Jackpot Upside has stopped
distinguishing products.** It still carries its 10% weight; it just carries it
almost identically for every box.

What orders products therefore changes by format:

- **1 pack**: realistic_upside (33.6%), true_win_frequency (23.8%)
- **6 packs**: realistic_upside (29.4%), true_win_frequency (27.7%)
- **36 packs**: **true_win_frequency (41.7%)**, typical_retention (20.0%)

## 5. The controlled experiment

Observational data confounds economics with format. This isolates them: for one
set, score `Y1`, `Y6` and `Y36` at costs `1×C`, `6×C`, `36×C`. Every one has
**identical economics by construction** — same pack model, same RTP, same value
per dollar. A unit-agnostic scale would return the same score three times.

| set | RTP | 1 pack | 6 packs | 36 packs | Δ(6) | Δ(36) |
|---|---|---|---|---|---|---|
| Surging Sparks | 0.445 | 31.72 | 30.60 | 30.74 | −1.12 | −0.97 |
| Destined Rivals | 0.490 | 33.55 | 35.11 | 35.77 | +1.56 | +2.22 |
| **Prismatic Evolutions** | 0.581 | 24.39 | 37.26 | **43.55** | **+12.87** | **+19.16** |

This is the finding. The pack-count effect is **not a constant offset that could
be disclosed once and mentally subtracted — it is set-dependent and ranges from
≈0 to ≈19 points.** Its size tracks how chase-concentrated the set is: Prismatic
Evolutions is dominated by rare high-value hits, so a single pack usually returns
almost nothing while 36 packs average out and look dramatically better on the
same anchors.

The score is not "wrong" — variance reduction is genuine economic value, and V3
is honestly measuring it. But it means a cross-format leaderboard would order
products substantially by **format and set variance**, not by product quality.
Two products with the same value-per-dollar can differ by 19 points.

## 6. Classification

Within a format, V3 is behaving well: no clipping, healthy separation, sensible
component structure. Across formats, the fixed pack-calibrated anchors introduce
a set-dependent bias of up to ~19 points at identical economics, and one
component (Jackpot Upside) stops discriminating entirely at 36 packs.

That is precisely a structural distortion of multi-pack products large enough
that they should not share one public Financial RIP label or leaderboard without
an explicit scoring-contract decision.

**`NOT_VALIDATED_FOR_CROSS_FORMAT_RANKING`**

Cleared for: ranking products **within** a family ("best booster box", "best
bundle", "best sleeved pack").
Not cleared for: one mixed Financial RIP leaderboard across 1/6/36-pack formats.

No new score is proposed here, and none was implemented. That is a contract
decision, not an implementation detail.

## 7. Reproducibility limitation

The Stage 1 seed makes `Y` a deterministic function of `X`: same `X`, same
identity, same `Y`. It does **not** make `Y` recoverable from the database. The
million-outcome pack vector `X` is not persisted, so **historical product
distributions cannot currently be reconstructed from Postgres alone** — only
re-derived by re-running the pack simulation, which is bit-identical only if
every simulation input and the simulator itself are unchanged.

Migration 064's header states this too loosely; the correction is recorded in
migration 065 and in `sealed_product_distribution.stage1_distribution_seed`.
Closing the gap is future outcome-artifact work and is out of scope here.
