# Stage VI-A — Overall RIP Chase Weight Semantics & Calibration

**Decision: `CHASE_WEIGHT_SEMANTICS_VALIDATED_WITH_REVISIONS`**

> ### ⚠ Stage VI-B clarification (correction)
>
> Two statements below are corrected by
> [`CHASE_WEIGHT_STAGE6B.md`](CHASE_WEIGHT_STAGE6B.md). Nothing else in this
> report is retracted.
>
> **1. "Equivalent" was imprecise.** With `S = 100K/(K+10)` and
> `T = 200K/(K+10) = 2S`, the terms `0.03 × T` and `0.06 × S` are identical, so
> the two candidates carry **equivalent Chase contribution strength**. But
> `87/10/3` and `84/10/6` are **not equivalent Overall RIP formulas**, because
> the Financial coefficient differs by 0.03:
>
> ```
> B = 0.87F + 0.10C + 0.03T = 0.87F + 0.10C + 0.06S
> A = 0.84F + 0.10C + 0.06S
> B - A = 0.03F        (verified to 9.5e-15 over all 131 products)
> ```
>
> B scores every product 0.31–1.71 points higher than A. Ranking impact is small
> but real: Spearman 0.999915, 16 pairwise inversions, 1 top-10 membership
> change, 3 tier changes, 0/21 same-set winner changes.
>
> **2. The C1–C5 verdicts in this report describe Candidate B, not the
> recommendation.** `report_chase_weight_stage6a.py` binds
> `TRANSFORM = scale.approved_unclamped` (= T) and assigns
> `financial = 0.90 - chase` in every phase, so the `0.02 / 0.03 / 0.05` rows,
> the shock grid and the date grid are all `0.90-w / 0.10 / w × T`. Candidate A
> was evaluated only once, on the base cohort, with no shocks, dates or criteria.
>
> Stage VI-B recomputed Candidate A directly: **it passes all five gates**
> (C1 margin +2.66, C2 0.13465, C3 Financial 0.9272 / Chase 0.0805, C4 0.9926,
> C5 six same-set reversals), with 0 clear overrides across all 12 shocks and all
> 7 full-cohort dates. The recommendation stands — but it was not established
> until Stage VI-B.
>
> Every other Stage VI-A finding is unchanged, including: the leverage was a
> dispersion/scaling issue; `200K/(K+10)` exceeds 100 and is unsuitable as a
> 0–100 pillar; clamping destroys top-end differentiation; Collector Appeal
> contributes ≈0 marginal variance and its product-level study stays deferred;
> Chase produces real same-set reorderings but changes 0/21 same-set winners.


**Recommended nominal weights: Financial 0.84 / Collector 0.10 / Chase 0.06**,
with Chase Opportunity re-expressed on a true 0–100 scale as `100K/(K+10)`.

The comparison point `0.87 / 0.10 / 0.03` with `200K/(K+10)` unclamped carries
the **same Chase contribution strength** but is a **different Overall RIP
formula** (`B - A = 0.03F`); see the Stage VI-B clarification above. It is not
the selected specification.

Stage VI's provisional 85/10/5 is **not** endorsed. It passes every acceptance
criterion, but with 0.41 points of margin on the binding one.

Research only. No production score, weight, snapshot, API or UI was modified.
The product-level Collector Appeal alternative was **not** touched, per instruction.

---

## Phase 0 — workspace baseline

| | |
|---|---|
| Branch | `fix/public-rankings-entitlement-regression` ✓ |
| HEAD at start | `7b7f9974` |
| Staged | none |
| Modified | `logs/run_simulations.log`, `logs/task_scheduler_debug.log` (pre-existing, scheduler-written) |
| Untracked | none |
| Merge/rebase/cherry-pick | none |

No worktree was created or entered. Nothing was reverted, stashed, deleted or
committed.

---

## Phase 1 — CONTROL reproduced

CONTROL was re-derived for all 131 products by calling the production function
`compute_overall_rip_v10` on each product's declared-version inputs:

> **0 mismatches, worst |Δ| = 0.00e+00.**

Canonical authority re-audited from code: Overall RIP **V10** (0.90 Financial /
0.10 Collector), Financial RIP **V4**, Collector Appeal **V5**, public contract
**v10**. Cohort: 131 products / 21 sets / 8 families.

The approved transform `200K/(K+10)` was verified exactly at
K = 0, 1, 2, 3, 5, 10, 15, 20, 30.

---

## Phase 2 — the Chase scale audit, and the answer to "A or B"

### The transform is (B) — and its implementation was (A)

`200K/(K+10)` **crosses 100 at exactly K = 10** and reaches **116.67** at the
cohort maximum K = 14. So the approved construct is a saturating index that
exceeds 100.

But Stage VI's *implementation* clamped it to [0, 100], and its docstring
described the curve as never reaching 100 — which is true of `100K/(K+10)` and
false of the formula that was approved. **The approved construct is ambiguous
between two different pillars**, and the clamp is not cosmetic: **5 of 131
products have K > 10** (K = 12, 13, 13, 13, 14) and are collapsed onto a single
score of 100, destroying differentiation exactly at the top of the range that a
breadth metric exists to provide.

| K | `200K/(K+10)` | clamped | `100K/(K+10)` |
|---|---|---|---|
| 0 | 0.000 | 0.000 | 0.000 |
| 1 | 18.182 | 18.182 | 9.091 |
| 2 | 33.333 | 33.333 | 16.667 |
| 3 | 46.154 | 46.154 | 23.077 |
| 5 | 66.667 | 66.667 | 33.333 |
| 10 | **100.000** | 100.000 | 50.000 |
| 15 | 120.000 | **100.000** | 60.000 |
| 20 | 133.333 | **100.000** | 66.667 |
| 30 | 150.000 | **100.000** | 75.000 |

### Distribution across the live cohort

Core K: min 0, P25 1, median 4, P75 5, P90 8, max 14.

| variant | min | P5 | P10 | P25 | med | P75 | P90 | P95 | max | sd |
|---|---|---|---|---|---|---|---|---|---|---|
| `200K/(K+10)` | 0.00 | 0.00 | 18.18 | 18.18 | 57.14 | 66.67 | 88.89 | 97.37 | **116.67** | **29.11** |
| clamped | 0.00 | 0.00 | 18.18 | 18.18 | 57.14 | 66.67 | 88.89 | 97.37 | 100.00 | 28.12 |
| `100K/(K+10)` | 0.00 | 0.00 | 9.09 | 9.09 | 28.57 | 33.33 | 44.44 | 48.68 | 58.33 | **14.56** |

### Why "leverage" exists — it is dispersion, not magic

| series | min | max | sd | sd ÷ Financial |
|---|---|---|---|---|
| Financial RIP V4 | 10.31 | 57.07 | 8.48 | **1.00×** |
| Collector Appeal V5 | 49.07 | 99.09 | 10.91 | 1.29× |
| Overall CONTROL | 18.11 | 58.71 | 7.49 | 0.88× |
| Chase `200K/(K+10)` | 0.00 | 116.67 | 29.11 | **3.43×** |
| Chase `100K/(K+10)` | 0.00 | 58.33 | 14.56 | 1.72× |

A weighted sum responds to `w · sd`, not to a pillar's nominal range. Financial
RIP occupies only 47 of its 0–100 range in this cohort; the approved Chase
transform occupies 117. **That ratio is the entire leverage story.** Stage VI's
unexplained "2.4×" is `3.43² ` renormalized against the correlated total.

> A nominal 5% on `200K/(K+10)` behaves like **17.2%** of a Financial-dispersion
> pillar. On `100K/(K+10)` the same 5% behaves like **8.6%**.

---

## Phases 3–4 — the grid and what a coefficient literally means

Collector held at 10%; Chase funded **entirely** from Financial (enforced in
code and pinned by tests).

| F/C/Chase | +10 Chase pts = Overall | Chase pts worth 1 Financial pt |
|---|---|---|
| 90/10/0 | +0.000 | — |
| 89/10/1 | +0.100 | 89.0 |
| 88/10/2 | +0.200 | 44.0 |
| **87/10/3** | **+0.300** | **29.0** |
| 86/10/4 | +0.400 | 21.5 |
| 85/10/5 | +0.500 | 17.0 |
| 84/10/6 | +0.600 | 14.0 |
| 82.5/10/7.5 | +0.750 | 11.0 |
| 80/10/10 | +1.000 | 8.0 |

**What one more Core K actually buys**, at 5% on the approved transform:

| K step | Chase pts | Overall pts | = Financial pts |
|---|---|---|---|
| 0 → 1 | +18.18 | +0.9091 | **1.070** |
| 1 → 2 | +15.15 | +0.7576 | 0.891 |
| 2 → 3 | +12.82 | +0.6410 | 0.754 |
| 4 → 5 | +9.52 | +0.4762 | 0.560 |
| 9 → 10 | +5.26 | +0.2632 | 0.310 |
| 13 → 14 | +3.62 | +0.1812 | 0.213 |

At 5%, a product's **first** chase card is worth about one full Financial RIP
point; its fourteenth is worth a fifth of one. That front-loading is the
intended saturating behaviour and is the clearest available statement of what
the coefficient means to a reader.

---

## Phase 5 — variance attribution, four methods, no winner declared

| chase w | direct | covariance | drop-one | Shapley | leverage (Shapley) |
|---|---|---|---|---|---|
| 0.01 | 0.0015 | 0.0223 | 0.0237 | 0.0223 | 2.23× |
| 0.02 | 0.0058 | 0.0461 | 0.0487 | 0.0461 | 2.30× |
| **0.03** | 0.0127 | 0.0710 | 0.0746 | **0.0710** | **2.37×** |
| 0.04 | 0.0220 | 0.0969 | 0.1013 | 0.0969 | 2.42× |
| 0.05 | 0.0334 | 0.1234 | 0.1285 | 0.1234 | 2.47× |
| 0.06 | 0.0466 | 0.1505 | 0.1561 | 0.1505 | 2.51× |
| 0.075 | 0.0696 | 0.1915 | 0.1976 | 0.1915 | 2.55× |
| 0.10 | 0.1140 | 0.2597 | 0.2659 | 0.2597 | 2.60× |

Stage VI's ~2.4× is confirmed and **persists across the whole grid**, rising
gently from 2.23× to 2.60×. Covariance and Shapley coincide exactly — for the
variance of a weighted *sum* these are the same decomposition, so they are one
piece of evidence, not two, and the report says so rather than presenting them
as agreement. Direct own-variance is far smaller because it discards covariance
and deliberately does not sum to one. Drop-one runs slightly above Shapley.

### The hierarchy problem

| chase w | Financial | Collector | Chase |
|---|---|---|---|
| 0.00 (CONTROL) | **1.0088** | **−0.0088** | 0.0000 |
| 0.03 | 0.9309 | −0.0019 | 0.0710 |
| 0.05 | 0.8744 | 0.0022 | 0.1234 |

**Collector Appeal contributes approximately zero variance to the *current*
production Overall RIP — very slightly negative.** It is set-level, so it is
constant within a set, and its 0.10 × sd 10.91 is dwarfed by Financial's
0.90 × sd 8.48.

Consequently the intended hierarchy *Financial ≫ Collector > Chase* **cannot be
satisfied in variance terms at any non-zero Chase weight**. At even 1%, Chase
already contributes more than Collector does at 10%. That is a property of
Collector, not a fault of Chase, and it forces the hierarchy to be judged
behaviourally rather than by variance share.

---

## Phase 6 — marginal rank influence

| chase w | Spearman | Kendall | med move | max move | inversions | ≥3 | ≥5 | ≥10 | T5 out | tier changes |
|---|---|---|---|---|---|---|---|---|---|---|
| 0.01 | 0.9989 | 0.9782 | 1.0 | 7 | 93 | 21 | 2 | 0 | 0 | 3 |
| 0.02 | 0.9963 | 0.9551 | 2.0 | 11 | 191 | 42 | 18 | 2 | 0 | 7 |
| **0.03** | **0.9930** | 0.9371 | 2.0 | 15 | 268 | 55 | 33 | 9 | **0** | 12 |
| 0.05 | 0.9844 | 0.8990 | 3.0 | 20 | 430 | 79 | 55 | 23 | 1 | 17 |
| 0.075 | 0.9698 | 0.8584 | 4.0 | 33 | 603 | 96 | 61 | 34 | 2 | 24 |
| 0.10 | 0.9502 | 0.8161 | 6.0 | 44 | 783 | 98 | 75 | 45 | 2 | 34 |

---

## Phases 7–8 — Financial gap bands and pairwise overrides

Financial RIP: min 10.31, median 28.97, max 57.07, sd 8.48. Pairwise |gap|:
median 8.15, P75 13.86, P90 19.34, max 46.76.

Band population (8,515 pairs): ≤2 → 1,114 · 2–5 → 1,653 · 5–10 → 2,267 ·
10–15 → 1,705 · 15–20 → 1,018 · >20 → 758.

**An override counts only where CONTROL and Financial already agree on the
ordering.** A pair Collector Appeal had already inverted inside CONTROL is not
Chase overturning a superior financial profile, and counting it would inflate
the rate with pairs Chase had nothing to do with.

### Override rate by band

| chase w | ≤2 | 2–5 | 5–10 | 10–15 | 15–20 | >20 | clear overrides | max gap overturned |
|---|---|---|---|---|---|---|---|---|
| 0.01 | 0.0467 | 0.0236 | 0.0009 | 0 | 0 | 0 | **0** | 6.28 |
| 0.02 | 0.0996 | 0.0430 | 0.0040 | 0 | 0 | 0 | **0** | 7.06 |
| **0.03** | **0.1293** | 0.0641 | 0.0079 | 0 | 0 | 0 | **0** | **7.34** |
| 0.04 | 0.1688 | 0.0817 | 0.0106 | 0 | 0 | 0 | **0** | 7.34 |
| 0.05 | 0.1885 | 0.1089 | 0.0176 | 0 | 0 | 0 | **0** | **9.59** |
| 0.06 | 0.2092 | 0.1283 | 0.0282 | 0.0006 | 0 | 0 | **1** | 12.68 |
| 0.075 | 0.2253 | 0.1549 | 0.0410 | 0.0018 | 0 | 0 | **3** | 12.68 |
| 0.10 | 0.2469 | 0.2033 | 0.0693 | 0.0082 | 0.0010 | 0 | **15** | 15.01 |

This is the cleanest result in the study. **The clear-override rate is exactly
zero from 1% through 5%, and first breaches at 6%.** The largest Financial gap
Chase can overturn rises smoothly — 6.28 → 7.06 → 7.34 → 9.59 at 5% → 12.68 at
6%.

At 5% the margin to the 10-point CLEAR line is **0.41 points**. At 3% it is
**2.66 points**.

---

## Phases 9–10 — within-set and cross-set decisions

| chase w | sets examined | winner changes | helpful (gap ≤2) | excessive (gap ≥10) |
|---|---|---|---|---|
| 0.01 – 0.075 | 21 | **0** | 0 | 0 |
| 0.10 | 21 | 1 | 0 | 0 |

**A significant negative result.** Chase changes which product wins its own set
in **0 of 21 sets at every defensible weight**, and in only 1 of 21 at 10%. This
qualifies Stage VI's headline claim that within-set differentiation is Chase's
strongest use case: Chase *does* reorder same-set products (9 same-set pairwise
overrides at 5%, 5 at 3%), but it reorders the **middle** of a set, never the
top. Set winners are robust to Chase at any weight worth shipping.

---

## Phase 12 — controlled counterfactuals

Expectations were stated before the numbers were produced.

**A — identical Financial (40) and Collector (70), K=0 vs K=14:**

| chase w | K=0 | K=14 | gap |
|---|---|---|---|
| 0.01 | 42.600 | 43.767 | 1.167 |
| 0.03 | 41.800 | 45.300 | 3.500 |
| 0.05 | 41.000 | 46.833 | 5.833 |
| 0.10 | 39.000 | 50.667 | 11.667 |

**B–E — can the maximum possible Chase advantage overturn a Financial lead?**

| chase w | 2 pts | 5 pts | 10 pts | 20 pts |
|---|---|---|---|---|
| 0.01 | held | held | held | held |
| 0.02 | **overturned** | held | held | held |
| 0.03 | **overturned** | held | held | held |
| 0.05 | **overturned** | **overturned** | held | held |
| 0.10 | **overturned** | **overturned** | **overturned** | held |

Expectation D ("a 10-point lead should essentially never be overturned") holds at
every weight up to 7.5% and fails at 10%. Expectation E holds everywhere. Note
that at 5% the *extreme* synthetic case overturns a 5-point lead, consistent
with the empirical maximum of 9.59.

**F/G** — with Chase equal, +10 Financial moves Overall by +8.50 and +10
Collector by +1.00 at 5%. Financial still dominates by 8.5:1.

**H/I/J** — saturation confirmed: K 0→1 buys +0.909 Overall points, K 1→5 buys
+2.424 across four steps, K 10→20 buys +1.667 across ten.

---

## Phase 13 — weight problem or scaling problem?

| variant | chase w | Shapley | leverage | Spearman | med move |
|---|---|---|---|---|---|
| `200K/(K+10)` | 0.05 | 0.1234 | **2.47×** | 0.9844 | 3.0 |
| `200K/(K+10)` clamped | 0.05 | 0.1199 | 2.40× | 0.9852 | 3.0 |
| `100K/(K+10)` | 0.05 | 0.0603 | **1.21×** | 0.9943 | 2.0 |

Product **rank order is identical across all three** (ρ = 1.000000 for the
rescale; 0.999931 for the clamp, which loses order only among the five K > 10
products it collapses).

> **Halving the scale halves the leverage while changing no product's position.
> The Stage VI "leverage" is unambiguously a scaling artifact, not a weight
> problem.**

Behavioural equivalence, measured directly:

| construct | Shapley | close override | clear override | max gap | Spearman | leverage |
|---|---|---|---|---|---|---|
| `0.87F + 0.10C + 0.03T` | 0.0710 | 12.93% | 0 | 7.34 | 0.9930 | 2.37× |
| `0.84F + 0.10C + 0.06S` | 0.0738 | 13.46% | 0 | 7.34 | 0.9926 | **1.23×** |

Closely comparable behaviour, honestly priced — but **not the same formula**:
these two rows differ by `0.03F` as well as by scale. Stage VI-B separates the
two effects and gates the second row on its own. (`100K/(K+10)` at 10%
breaks the binding constraint: 1 clear override, max gap 12.68.)

---

## Phase 14 — outlier leverage

Highest Chase products: *Ascended Heroes Booster Pack* (K=14, 116.67),
*Ascended Heroes Booster Bundle* / *Prismatic Evolutions Booster Bundle* /
*Prismatic Evolutions Booster Pack* (K=13, 113.04), *Prismatic Evolutions ETB*
(K=12, 109.09).

| cohort | n | Shapley @5% | leverage |
|---|---|---|---|
| full | 131 | 0.1234 | 2.47× |
| drop top 1 | 130 | 0.1215 | 2.43× |
| drop top 5% | 125 | 0.1122 | 2.24× |
| drop top 10% | 118 | 0.1031 | 2.06× |

The leverage **survives dropping the top decile**. It is broad structural
dispersion, not a handful of extreme products.

---

## Phase 15 — family leverage

| family | n | med K | Chase median | Chase sd | mean Overall shift @5% |
|---|---|---|---|---|---|
| enhanced_booster_box | 2 | 6.5 | 75.94 | 26.58 | **+1.910** |
| loose_booster_pack | 21 | 5.0 | 66.67 | 28.79 | +1.502 |
| half_booster_box | 7 | 4.0 | 57.14 | 19.64 | +1.383 |
| booster_box | 14 | 4.5 | 61.90 | 22.29 | +1.380 |
| booster_bundle | 22 | 4.0 | 57.14 | 31.15 | +1.268 |
| sleeved_booster_pack | 14 | 3.5 | 51.65 | 21.95 | +1.178 |
| elite_trainer_box | 26 | 2.0 | 33.33 | 32.17 | +0.923 |
| pokemon_center_elite_trainer_box | 25 | 2.0 | 33.33 | 25.48 | **+0.259** |

A 7× spread across families, but **not** a booster-box bonus: loose packs
(+1.50) benefit more than booster boxes (+1.38). The families that gain least
are the ETBs, whose per-pack cost is highest and whose Core K is therefore
smallest — which is the Stage V-B contract working as designed, not a format
artifact.

---

## Phases 16–17 — shock and short-window temporal calibration

**Price shocks** (21/21 sets, one simulation per set shared across scenarios;
Core K recomputed under each shock). Clear-override count is **0 for every
finalist under every shock**.

Largest Financial gap overturned:

| chase w | base | card ±5% | card ±10% | card ±20% | prod ±10% | prod ±20% |
|---|---|---|---|---|---|---|
| 0.02 | 7.06 | 7.06 | 7.06 | 6.77 / 7.06 | 7.06 | 7.06 / **5.05** |
| **0.03** | **7.06** | **7.06** | **7.06** | **7.06** | **7.06** | **7.06** |
| 0.05 | 7.12 | 7.12 / 8.47 | 8.31 / 8.47 | 8.31 / 8.47 | 8.47 / 8.31 | 8.47 |

3% is **completely flat at 7.06 under every one of the twelve shocks**. 5% moves
between 7.12 and 8.47.

**Short-window temporal** — 13 days, 9 dates, one regime, card prices frozen.
**Not long-term validation.** Effective Chase share is essentially static:

| chase w | min Shapley | max Shapley | spread |
|---|---|---|---|
| 0.02 | 0.0354 | 0.0508 | 0.0154 |
| 0.03 | 0.0551 | 0.0780 | 0.0230 |
| 0.05 | 0.0976 | 0.1347 | 0.0370 |

Clear overrides remain 0 and max gap remains 7.06 (3%) / 7.12 (5%) on every
date.

---

## Phase 18 — behavioral acceptance criteria

Derived from the stated philosophy **before** checking which weight passes.

| | Criterion | Target |
|---|---|---|
| **C1** | Clear-Financial override *(binding)* | Rate 0, and the largest overturnable Financial gap stays below 10 **with margin** under ±10% shocks |
| **C2** | Close-pair influence *(binding)* | Reorders ≥10% of pairs with Financial gap ≤2 — below that it is decoration |
| **C3** | Not co-primary *(binding)* | Financial variance share > 0.80 and Chase < 0.20 on every method |
| **C4** | Rank continuity *(advisory)* | Spearman ≥ 0.98 vs CONTROL, Top-5 turnover ≤ 1 |
| **C5** | Within-set differentiation *(advisory)* | Reorders some same-set pairs — Chase is the only pillar that can |

**On the intended hierarchy:** *Financial ≫ Collector > Chase* is unachievable in
variance terms at any non-zero weight (Phase 5). The hierarchy is therefore
judged behaviourally, via C1 and C2.

---

## Phase 19 — finalist tournament

| chase w | Shapley | leverage | close override | clear override | max gap | Spearman | T5 out | tiers | C1–C5 |
|---|---|---|---|---|---|---|---|---|---|
| 0.02 | 0.0461 | 2.30× | 9.96% | 0 | 7.06 | 0.9963 | 0 | 7 | **Y n Y Y Y** |
| **0.03** | **0.0710** | **2.37×** | **12.93%** | **0** | **7.34** | **0.9930** | **0** | **12** | **Y Y Y Y Y** |
| 0.05 | 0.1234 | 2.47× | 18.85% | 0 | 9.59 | 0.9844 | 1 | 17 | **Y Y Y Y Y** |

- **2% fails C2** by four hundredths of a percentage point (9.96% vs 10%). It is
  close enough that the failure should be read as "marginal", not "decisive" —
  but it is the wrong side of a criterion fixed in advance.
- **3% and 5% both pass all five.** The separator is margin on the binding
  criterion: 3% holds 2.66 points of headroom and is *flat under every shock*;
  5% holds 0.41 points and drifts to 8.47 under shocks.

**3% wins on margin, not on preference.**

---

## Phase 20 — decision

### `CHASE_WEIGHT_SEMANTICS_VALIDATED_WITH_REVISIONS`

**Recommended nominal Overall weights**

> **Financial 0.84 / Collector 0.10 / Chase 0.06**, with Chase Opportunity =
> `100K/(K+10)`.

The `0.87 / 0.10 / 0.03` form with `200K/(K+10)` unclamped has the same Chase
contribution strength but is **not the same formula** — it differs by `0.03F` and
is not the selected specification. The 0–100 form is preferred because its
coefficient means what it says. See the Stage VI-B clarification above.

**Expected effective Chase contribution:** 7.1–7.4% of Overall RIP variance
(Shapley and covariance), 7.5–7.7% by drop-one. Leverage **1.23×** nominal on
the 0–100 form (2.37× on the ×200 form). Temporal spread over the observed
window: 0.055–0.078.

**Direct score-point interpretation**

- On the recommended 0–100 form at 6%: **+10 Chase points = +0.60 Overall
  points**; one Financial point is worth 14 Chase points.
- In the units a reader can check: **a product's first Core chase is worth about
  one full Financial RIP point**; its fourteenth is worth about a fifth of one.

**Behavioral role: a tertiary modifier.** It settles close calls and never
overturns clear ones — it reorders ~13% of near-tied pairs (Financial gap ≤ 2)
and 0% of pairs where Financial leads by ≥10, holding at 0% under every ±20%
shock and on every date in the window.

One honest caveat on that label: **Chase is the second-largest source of variance
in the resulting model**, because Collector Appeal currently contributes
approximately none. Chase is tertiary by design, by nominal coefficient and by
behaviour — but not by variance rank.

**Clear-Financial override behavior:** zero overrides of any pair with a ≥10-point
Financial gap. The largest gap Chase can overturn is **7.34 points**, and that
figure is **invariant across all twelve price shocks and all nine dates**.

**Within-set differentiation behavior:** Chase reorders same-set products in the
middle of a set (5 same-set pair reversals at 3%) but changes the set *winner* in
**0 of 21 sets**. Stage VI's claim that within-set differentiation is Chase's
strongest use case is confirmed as *reordering* and refuted as *winner selection*.

**Is the approved transform unchanged?** The *shape*, the *saturation constant*
(10) and the *product ordering* are unchanged — ρ = 1.000000. What changes is the
scale constant and, necessarily, the coefficient that pairs with it. This is a
**revision, not a replacement**: the approved formula proved ambiguous (formula
exceeds 100, implementation clamped at 100, docstring described a third thing)
and that ambiguity had to be resolved before a coefficient could mean anything.
The clamp must be removed in either resolution.

### Known evidence limitations

1. One cohort, one market state: 131 products, 21 sets, 8 families.
2. Temporal evidence is 13 days / 9 dates / one regime. **Not** long-term or
   multi-regime.
3. C2's 10% threshold is a judgement call fixed in advance, not an empirical
   constant. 2% fails it by 0.04 points; a defensible reading could admit 2%.
4. The Phase-16 base scenario re-simulates on fresher card prices than the
   Phase-8 dataset, so its base max-gap (7.06–7.12) differs slightly from the
   dataset's (7.34 at 3%, 9.59 at 5%). Both are reported; the larger is used.
5. Collector Appeal's ≈0 variance share is a finding about **Collector**, and it
   makes the intended three-tier hierarchy unmeasurable by variance. It is the
   strongest argument for running the deferred product-level Collector Appeal
   study — which was **not** touched here, per instruction.
6. Core K's cohort maximum is 14, so behaviour above K ≈ 15 is extrapolation.
7. Chase remains ~35% reconstructable from the existing pillars (Stage VI). This
   stage calibrated a coefficient; it did not revisit that overlap.

**Do not deploy.** Production Overall RIP V10 (90/10) remains the default until a
separate explicit instruction says otherwise.

---

## Deliverables and workspace

| Path | Classification |
|---|---|
| `backend/research/chase_weight_stage6a/scale.py` | required deliverable |
| `backend/research/chase_weight_stage6a/weights.py` | required deliverable |
| `backend/research/chase_weight_stage6a/attribution.py` | required deliverable |
| `backend/research/chase_weight_stage6a/pairs.py` | required deliverable |
| `backend/research/chase_weight_stage6a/decisions.py` | required deliverable |
| `backend/scripts/report_chase_weight_stage6a.py` | required deliverable |
| `backend/tests/unit/research/test_chase_weight_stage6a.py` | required deliverable (43 tests) |
| `docs/research/CHASE_WEIGHT_STAGE6A.md` | required deliverable |
| `docs/research/chase_weight_stage6a_analysis.txt` | generated / reproducible |
| `docs/research/chase_pillar_stage6_dataset.json` | pre-existing (Stage VI) |
| `docs/research/chase_pillar_stage6_scenarios.json` | pre-existing (Stage VI) |
| `logs/*.log` | pre-existing / unrelated |

`python -m pytest backend/tests/unit/research/test_chase_weight_stage6a.py` —
**43 passed**, including a directional guard asserting that shock scenarios
actually move Core K (a card-price rise can only widen a fixed-floor basket; a
product-cost rise can only narrow it). That test exists because the Stage VI
shock build once reported an exactly-zero response that read as a finding and
was a bug.
