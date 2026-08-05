# Historical evidence vs. the revised formula — what transfers and what does not

**Purpose.** The July 2026 studies are frequently cited as validation for
Collector Appeal. This document states precisely what they established, what they
did not, and which of their conclusions can legitimately be carried over to the
revised D/H/P formula now shipping on `feature/financial-rip-v3`.

Sources, read in full and **not modified by this work**:

* `docs/research/collector_appeal_market_prediction_results.md` (2026-07-15, n=21)
* `docs/research/collector_appeal_product_rollout.md` (2026-07-15/16, n=21–22)

---

## 1. What the prior research established

The July market study evaluated several **separate constructs**:

| Construct | Definition |
|---|---|
| `D` | Universal Roster Desirability |
| `A` | Favorite-Hit Accessibility |
| `M` | Chase Intensity (elite scarcity among desirable subjects) |
| Chase Appeal | `D × M` |
| `P` | Dual-Path Depth |
| CA6 | `D × (0.50 + 0.50·P)` |
| CA7 | `D + 0.50·P·(1 − D)` |

### Findings that are established and still stand

1. **`A` and `M` are approximately one axis, not two.** `access(p) = 1 −
   scarcity(p)` at shared anchors; mean `A* + M* − 1 = +0.040`. So "balancing"
   them is not a real design choice, and `CA4_50_50` collapses to a rescaled `D`.

2. **The strongest raw market-price relationship belonged to Chase Appeal
   (`D × M`), not to CA6 or CA7.** ρ = **0.865** with top-10 card value, CI
   [0.660, 0.948], LOSO [0.844, 0.899], zero sign flips, and it **survived** the
   set-size correction (partial 0.784, attenuation only 0.081). CA6 reached 0.420.

3. **Dual-Path Depth has no value-level signal** (−0.052, CI includes zero) but
   the strongest **concentration** relationship measured (HHI 0.468). It is a
   concentration construct, and a larger concentration relationship is not
   automatically better.

4. **`D` is the least robust construct measured.** It correlates 0.9887 with a
   static third-party fan-popularity scrape; the only time-varying input is 0.0
   for 49.7% of subjects. A 10% error in `D` drops rank correlation to 0.56.

5. **`P` is structurally compressed.** `P ≤ access(easiest hit-eligible card)`,
   and no modern hit ladder approaches the 1-in-10 EASY anchor. Observed
   P ∈ [0.135, 0.447], mean 0.293. **P structurally cannot approach 1.0.**

6. **Accessibility works against price by construction.** `axis_position` vs set
   value = **−0.690**. Any appeal metric leaning accessible will look worse
   against price for reasons unrelated to collectors.

### Why CA7 was selected — and why not

CA7 was chosen over CA6 on **construct grounds**, explicitly not on price:

* it stays bounded in [0,1] and monotone in both inputs;
* it preserves roster desirability as the **baseline** (at P=0, CA7 = D, whereas
  CA6 = 0.5·D);
* missing or compressed dual-path structure therefore does not severely penalize
  a set — which matters because P's compression is a known measurement artifact;
* CA6's observed range was [31.5, 65.2], so nothing could ever score near 100;
* CA6 let the artifact overrule desirability — it ranked Mega Evolution above
  Ascended Heroes despite 8 fewer desirability points, purely because Ascended
  Heroes has the cohort's lowest hit-access ceiling;
* `λ = 0.50` was a **reasoned symmetric prior**, never a price-fitted value.

> **CA7 was not selected because it predicted price.** It predicted price less
> well than Chase Appeal. Any summary claiming otherwise misstates the record.

### What the prior research did *not* establish

* That CA6 or CA7 measures **appeal**. §19 of the market study is explicit: every
  construct representing opening *experience* is unmeasurable against price by
  construction.
* That collectors value dual-path structure at all, or that λ=0.50 matches any
  real preference. Listed as limitation 8 and open question 19.
* That a Collector Appeal weight above ~15% is defensible. The study recommended
  **10%**, called 15% defensible, and stated **"25–30% is not"**. It further
  noted Collector Appeal becomes the **second-largest pillar above 18.18%**.
* Anything about Desirable Outcome Frequency (`H`/`F`) — **the construct did not
  exist**.

---

## 2. What transfers to the revised formula

The revised formula is a **different construct**:

```text
legacy CA7  =  D + 0.50 · P · (1 − D)
revised CA  =  D + 0.50 · (0.60·H + 0.40·P) · (1 − D)
```

| Prior finding | Transfers? | Why |
|---|---|---|
| A and M are one axis | **Yes** | Structural algebra, formula-independent |
| P is compressed, P ≤ 0.45 | **Yes** | Property of P and the pull model |
| D is rank-fragile | **Yes** | Property of D; the revision does not touch D |
| Accessibility fights price | **Yes** | Structural |
| Chase Appeal is the strongest price construct | **Yes** | Unchanged; it is a separate metric |
| CA7's bounded-bonus shape is safer than CA6's discount | **Yes** | Applies to any `D + λ·S·(1−D)` form |
| CA6/CA7 market relationships | **No** | Measured on formulas containing no `H` |
| CA6/CA7 rank-robustness results | **No** | Different score, different ranking |
| "CA6 at 10–15%" weight guidance | **Partially** | Reasoning transfers; the numbers were measured on a different formula **and against Financial RIP V2** |

> **The July study cannot be cited as empirical validation of the revised
> formula.** It validated formulas that do not contain `H`. What it supplies is
> construct reasoning and structural facts, both of which remain useful.

---

## 3. Old vs revised, side by side

Empirical columns are from this validation run (n = 22 sets with complete D/H/P;
see [validation_summary.md](validation_summary.md)). Financial and Overall-RIP
columns are **blocked** — no set has Financial RIP V3 data.

| Property | Legacy CA7 | Revised CA (`CA8_D_H60_P40_L50`) |
|---|---|---|
| Inputs | D, P | D, H, P |
| Formula | `D + 0.50·P·(1−D)` | `D + 0.50·(0.60H + 0.40P)·(1−D)` |
| Bounds | [0, 1] | [0, 1] |
| Monotonic in every input | Yes | Yes (verified on a dense grid) |
| `structure = 0` → | D | D |
| `D = 1` → | 1 | 1 |
| Observed score range (0–100) | 56.79 – 96.09 | 53.77 – 96.04 |
| Observed SD | 8.24 | 8.86 |
| ρ vs `D` | 0.984 | **0.991** |
| ρ vs `H` | — | 0.334 |
| ρ vs `P` | — | −0.112 |
| ρ vs CA6 | — | 0.756 |
| ρ vs Chase Appeal | — | 0.536 |
| ρ vs legacy CA7 | — | **0.9966** |
| ρ vs Financial RIP V3 | **blocked** | **blocked** |
| Raw market relationships | 0.420 (CA6 proxy, July) | **not re-run — blocked** |
| Size-adjusted relationships | July values | **not re-run — blocked** |
| Rank robustness under uncertainty | July values | **framework built, not run** |
| Effective Overall influence @10/15/20/25% | **blocked** | **blocked** |

### λ = 0.75 carries a defect the July study understated

The July doc rejected λ=0.75 as "over-weighting a quantity we measure with known
compression". This validation found a harder objection, now pinned as a test
(`test_lambda_050_preserves_desirability_ordering_where_lambda_075_does_not`):

At λ=0.75 a set at D=0.30 with perfect structure **outscores** a set at D=0.80
with none. The formula stops being a bounded bonus on desirability and becomes
capable of reordering sets against it. The exact boundary is algebraic and
independent of α: structure overturns a desirability gap whenever
`D_strong − D_weak < λ·(1 − D_weak)`.

At the pre-registered λ=0.50 this inversion does not occur in that region — a
genuine point in the primary candidate's favour, and one the historical record
did not state.
