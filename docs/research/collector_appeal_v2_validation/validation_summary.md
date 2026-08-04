# Collector Appeal revision + Financial RIP V3 — validation summary

**Status: research only. Read-only run. No database write, no snapshot, no SQL,
no simulation launched, no canonical version changed, no frontend touched.**

* Run date: 2026-08-04 · Branch `feature/financial-rip-v3` · Commit `7dc82f2`
* Instrument: `backend/scripts/build_rip_v3_collector_appeal_validation.py`
* Manifest: [`manifest.json`](manifest.json) — every seed, draw count, formula
  version and the literal CLI invocation
* Companion documents:
  [historical_evidence_comparison.md](historical_evidence_comparison.md) ·
  [behavioral_validation_plan.md](behavioral_validation_plan.md) ·
  [three_bucket_architecture.md](three_bucket_architecture.md)

---

# HEADLINE

## 1. The revision already shipped. This is a retrospective validation, not a pre-cutover one.

Commit `7dc82f2` made the revised D/H/P formula and Overall RIP V6 (80/20)
**canonical**. `scoring_config.CANONICAL_OVERALL_RIP_VERSION` is
`overall_rip_v6_80_financial_v3_20_collector_appeal_v2`, and
`collector_appeal_service` serves the revised formula. Legacy CA7 and Overall RIP
V5 are retained for comparison and rollback only.

## 2. The empirical half of the study is BLOCKED. Zero sets have Financial RIP V3 data.

Migration 060's columns exist; no simulation has run since. **0 of 1,757**
`simulation_derived_metrics` rows carry `financial_rip_v3_score`. Everything
depending on it — component redundancy, leave-one-component-out, Overall weight
sensitivity, variance decomposition, financial uncertainty, market re-analysis —
cannot produce a single real number.

## 3. On the half that CAN be measured, the revision reorders almost nothing.

Across the 22 sets with complete `D`, `H` and `P`:

| Question | Statistic | Reading |
|---|---|---|
| Does the revised CA collapse into `D`? | **ρ = 0.991** (CI [0.940, 1.0]) | **Yes, very nearly** |
| Does it differ from legacy CA7? | **ρ = 0.9966** (CI [0.972, 1.0]) | **Barely** |
| Does `H` add information beyond `D`? | ρ = 0.303 (CI [−0.179, 0.682]) | **Yes** |
| Does `H` add information beyond `P`? | ρ = 0.565 (CI [0.228, 0.808]) | **Yes, partly** |
| Is `H` a scarcity/price proxy? | ρ = 0.163 vs Chase Appeal | **No** |
| Is the revised CA a chase proxy? | ρ = 0.536 vs Chase Appeal | **No** |

**The paradox, and the central finding of this phase:** `H` is a genuinely new
signal — nearly uncorrelated with `D` (0.30), essentially unrelated to scarcity
(0.16) — and the formula then compresses it into near-irrelevance.

---

# WHY THE SIGNAL DISAPPEARS

The bounded-headroom term multiplies the structural signal by **two** small
numbers:

```text
bonus = λ · (0.60·H + 0.40·P) · (1 − D)
      = 0.50 · S · (1 − D)
```

Measured across the 22-set cohort:

| Quantity | min | median | max | SD |
|---|---|---|---|---|
| `D` | 0.5107 | 0.8725 | 0.9548 | 0.0952 |
| `H` | 0.0278 | 0.1397 | 0.2659 | 0.0605 |
| `P` | 0.1351 | 0.2987 | 0.4502 | 0.0838 |
| `S = 0.60H + 0.40P` | 0.1080 | **0.2132** | 0.3195 | 0.0612 |
| headroom `1 − D` | 0.0452 | **0.1275** | 0.4893 | — |
| **bonus (CA − D), points on 0–100** | **0.437** | **1.254** | **3.868** | 0.896 |

**The entire structural term — H and P together — is worth a median of 1.25
points out of 100, and never more than 3.87.** Meanwhile `D` itself has an SD of
9.5 points. The structural signal is roughly an order of magnitude smaller than
the variation it is competing with, so it cannot meaningfully reorder anything.

Three multiplicative causes, all structural rather than incidental:

1. **`H` is small.** The best set in the cohort delivers a desirable card in only
   **26.6%** of packs; the median is 14.0%. This is a real property of modern hit
   ladders, not a modelling error.
2. **`P` is compressed** — the July study's finding, reconfirmed: P ∈ [0.135,
   0.450], structurally bounded by the accessibility of the easiest hit-eligible
   card, which never approaches the 1-in-10 EASY anchor.
3. **`D` is high, so headroom is small.** Median `D` = 0.87 leaves only **0.128**
   of headroom for structure to claim, and λ=0.50 halves that again.

The revised formula changes what "structure" *means* (adding H to P) but not how
much structure is allowed to *matter*. Against legacy CA7 the per-set difference
is a median of **−0.59 points**, at most **−3.02**.

> Adding `H` was a construct improvement. It was not, on this evidence, a
> ranking improvement — and the 80/20 weight was raised as if it were.

---

# DATA READINESS

| | Count |
|---|---|
| Sets in the published RIP cohort | **34** |
| With Financial RIP V3 | **0** |
| With complete Collector Appeal inputs (D, H, P) | **22** |
| **Fully ready for the complete study** | **0** |

## Sets missing Collector Appeal inputs (12)

11 have **no pull model**: Astral Radiance, Battle Styles, Brilliant Stars,
Chilling Reign, Darkness Ablaze, Evolving Skies, Fusion Strike, Rebel Clash,
Silver Tempest, Sword & Shield, Vivid Voltage.
1 has **no modeled subject**: Lost Origin.

This reproduces the July rollout's finding exactly (11 + 1) and is unchanged.

## Sets missing Financial RIP V3: all 34

**No backfill is possible.** Realistic Upside and Jackpot Upside require
conditional means over exact empirical rank buckets. A percentile is a threshold,
and no arithmetic over stored P50/P95/P99 recovers the mean of the mass above
one. The framework refuses to approximate rather than publishing a number that
looks like a measurement.

### Exact commands to unblock

```bash
# Whole cohort (writes to simulation_derived_metrics — a production job)
backend/.venv/Scripts/python.exe -m backend.scripts.run_all_v2_sets

# One set
backend/.venv/Scripts/python.exe -m backend.scripts.run_all_v2_sets --set ascendedHeroes

# Preview only, writes nothing
backend/.venv/Scripts/python.exe -m backend.scripts.run_all_v2_sets --dry-run
```

Then re-run:

```bash
backend/.venv/Scripts/python.exe -m backend.scripts.build_rip_v3_collector_appeal_validation --strict
```

**None of these were launched by this work.**

---

# WHAT THE HISTORICAL RESEARCH DOES AND DOES NOT SUPPORT

Full treatment in
[historical_evidence_comparison.md](historical_evidence_comparison.md). The three
points that matter most here:

1. **CA7 was never selected for predicting price.** The strongest raw market
   relationship belonged to **Chase Appeal (`D × M`), ρ = 0.865**, which also
   survived size correction (0.784). CA7 was chosen on construct grounds:
   bounded, D-as-baseline, degrading to `D` rather than `0.5·D` under
   mis-measured P. `λ = 0.50` was a reasoned prior, never fitted.

2. **The July study cannot validate the revised formula.** It evaluated formulas
   containing no `H`. Its structural findings (A≈1−M, P's compression, D's
   fragility, accessibility-vs-price) transfer; its market and robustness results
   do not.

3. **The July study recommended 10%, called 15% defensible, and stated 25–30% is
   not.** It also established that Collector Appeal becomes the **second-largest
   pillar above 18.18%**, and recommended deferring any weight increase until the
   collector-preference study landed. **The shipped weight is 20%. That study has
   not been run.**

---

# NEW FINDING: λ = 0.75 permits structural inversion

Pinned as a test
(`test_lambda_050_preserves_desirability_ordering_where_lambda_075_does_not`).

At λ = 0.75, a set at `D = 0.30` with perfect structure **outscores** a set at
`D = 0.80` with none. The boundary is algebraic and independent of α: structure
overturns a desirability gap whenever

```text
D_strong − D_weak  <  λ · (1 − D_weak)
```

At λ = 0.75 the formula stops being a bounded *bonus* on desirability and becomes
capable of reordering sets against it. At the pre-registered λ = 0.50 it does
not. This is a stronger objection to λ=0.75 than the July study's "over-weights a
poorly-measured quantity", and it is a genuine point in favour of the primary
candidate.

---

# SECTIONS THAT COULD NOT BE RUN

All implemented, tested, and blocked on Financial RIP V3 data:

| Section | Status |
|---|---|
| Financial component redundancy matrix (6×6) | **blocked** — n = 0 |
| Leave-one-component-out (both methods) | **blocked** — needs ≥3 sets with all six components |
| Overall RIP weight sensitivity (0/10/15/20/25%) | **blocked** — needs V3 + appeal |
| Variance decomposition `Var(O) = a²Var(F) + b²Var(C) + 2abCov` | **blocked** |
| Effective vs nominal appeal influence | **blocked** |
| Financial uncertainty (bootstrap over outcome vectors) | **blocked** — vectors not retained |
| Rank indistinguishability / pairwise dominance | **framework ready**, needs V3 |
| Market re-analysis, size-adjusted + partial | **not re-run** |

The uncertainty machinery for the **appeal** side (pull-rate shocks grouped by
(slot, rarity), missing-card removal, combined draws) is implemented and unit
tested, but reporting appeal-only uncertainty intervals without the financial
half would invite reading them as Overall RIP intervals, so they are deferred to
the unblocked run.

---

# DECISION TABLE

Practical influence cannot be filled in without Financial RIP V3. What *is*
known constrains it:

| Weight | Nominal appeal share | Practical influence | Ranking stability | Evidence status |
|---|---|---|---|---|
| 90/10 | 10% | July (vs V2): max 1 rank, 0% move ≥3 | Very stable | July-supported |
| 85/15 | 15% | **unmeasured vs V3** | unmeasured | July: "defensible" |
| **80/20 (shipped)** | 20% | **unmeasured vs V3** | unmeasured | **Above the 18.18% second-pillar crossover; July advised against >15% pending behavioral data** |
| 75/25 | 25% | **unmeasured vs V3** | unmeasured | July: "not defensible" |

A key caveat on carrying the July influence numbers forward: they were measured
against **Financial RIP V2**. Financial RIP V3 has a different score distribution
and fixed absolute anchors, so the appeal term's *relative* dispersion share
under V3 is genuinely unknown and could be larger or smaller.

---

# RECOMMENDATION

**Classification: `insufficient data` — with one qualified sub-finding.**

The complete question ("is the revised formula at 20% justified?") **cannot be
answered today**, because the financial half of every comparison is missing.

On the appeal half, which *can* be measured, the evidence is specific:

**Evidence for the revision**
* `H` is a real, distinct signal: ρ = 0.30 with `D`, ρ = 0.16 with Chase Appeal.
  It is not desirability restated and not a scarcity proxy.
* It is not redundant with `P` (ρ = 0.565) — the 0.60/0.40 blend is not measuring
  one axis twice.
* Bounds, monotonicity and missing-data behaviour verified exhaustively.
* λ = 0.50 avoids the structural inversion λ = 0.75 permits.

**Evidence against — and it is the more consequential**
* The revised score correlates **ρ = 0.991 with pure `D`** and **ρ = 0.9966 with
  legacy CA7**. Whatever `H` contributes, the formula does not let it through.
* The structural term is worth a **median 1.25 points on a 0–100 scale**, against
  a `D` spread of 9.5 points.
* The shipped 80/20 weight **exceeds** what the historical research supported,
  and the study that was named as its prerequisite has not been run.
* `D` — which the revised score is ρ=0.99 with — remains the least robust
  construct measured (98.9% a static popularity scrape; ρ 0.56 at σ=0.10). **A
  20% weight on a metric that is essentially `D` amplifies exactly the fragility
  the July study warned about.**

## Recommended sequence

1. **Do not treat this as validation of the 80/20 cutover.** It is not.
2. **Rerun simulations** to populate Financial RIP V3, then re-run this
   validation unmodified. It is built and tested; it needs only data.
3. **Consider whether the formula should let structure matter more.** If `H` is
   worth adding, a median 1.25-point contribution is arguably too small to
   justify the added complexity — the honest options are to raise λ (carefully:
   see the inversion boundary), rescale `H` against its achievable range rather
   than [0,1], or accept that Collector Appeal is a **presentational axis** and
   return the Overall weight to 10–15%.
4. **Run the behavioral study.** It has been the named blocker since July and
   remains the only thing that can validate an appeal metric against appeal.

**A defensible outcome of the unblocked run is "revert to 90/10 and keep the
revised formula", and the framework is built to be able to say so.**

---

# LIMITATIONS

1. **n = 22** for every appeal statistic; **n = 0** for every financial one.
2. Cohort-limited to S&V and Mega Evolution; no external holdout.
3. Modeled, not observed, pull rates.
4. Bootstrap CIs at n=22 are wide — several straddle zero and are labelled so
   per-row rather than in a footnote.
5. No market re-analysis was run, so nothing here speaks to price.
6. `D`'s uncertainty is assumed, not measured — unchanged since July.
7. The appeal-side uncertainty machinery is unit-tested but has not been run
   against the full cohort.
