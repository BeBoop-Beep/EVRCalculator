# Budget-Normalized Product Ranking V1 — Methodology Validation Appendix

**Date:** 2026-08-22
**Status:** Exploratory, read-only validation. No production writes, no schema changes, no publication.
**Extends (does NOT overwrite):** `BUDGET_NORMALIZED_PRODUCT_RANKING_v1.md`
**Research script:** `backend/scripts/research_budget_ranking_semantics.py` (SELECT-only, rerunnable)

This appendix answers ONE question left open by the committed decision record:

> Should the ranking mean **"best whole-product strategy that fits within a budget ceiling"**
> (Model A / floor-to-budget), or should it require **approximately equal actual committed
> capital** (Model B / matched capital)?

The prior document's claims are preserved verbatim. Where this validation **corrects** a prior
claim, it says so explicitly below rather than editing the original.

---

## 0. Corrections to the prior record

### 0.1 "Zero dominance inversions" was never actually measured

`BUDGET_NORMALIZED_PRODUCT_RANKING_v1.md` states the method behaved with *"zero dominance
inversions"*, inherited from `research_equal_spend_product_rip_v4.py`, whose JSON reports
`multiMetricDominanceCount: 0` across 967 comparisons.

**That zero is a measurement artifact, not a result.**

Root cause: `project_financial_rip_v4_from_v3_payload()` returns a payload whose
`audit.normalizedInputs` is **empty** — the raw distribution metrics survive only on the **V3**
payload it is projected from. Both the prior harness
(`research_equal_spend_product_rip_v4.py:140`) and the first draft of this pass's script read the
raws off the **V4** payload, so `typical_retention_ratio` (→ `medianRetention`) and
`true_win_probability` (→ `chanceToRecoverCapital`) were always `None`.
`multi_metric_dominator()` requires **all four** metrics present, so it could never fire — hence
zero comparable pairs and a reassuring, meaningless "zero inversions".

The corroborating tell is in the same block: `strictExpectedReturnDominanceCount: 943`.
`strict_return_dominator()` filters to whichever downside metrics are non-`None`, so with all of
them absent it silently degraded into "higher RTP wins" instead of vanishing. One counter
collapsing to zero while its neighbour stays large is the signature of missing inputs, not a
clean cohort.

**Consequence:** criterion 2 of *both* approval standards (§26 and §27 of the task) rested on an
untested number. This pass measures dominance properly for the first time. The script now raises
if any dominance metric is `None`, so a vacuous test can never again be reported as a pass.

### 0.2 The engine's own vocabulary contradicts its implementation

`backend/calculations/evr/budget_normalized_product_ranking.py` implements a **budget ceiling**
(`quantity = floor(budget / price)`; unused cash recorded and never scored) but labels itself as
capital-matched:

- module docstring: *"the internal, cross-format **capital-matched** ranking engine"*
- `BUDGET_COMPARISON_SCOPE_VERSION = "equal_committed_capital_cross_format_v1"`
- prior doc: *"**Equal-committed-capital comparison**, using whole purchasable retail units…"*

These are Model B labels on a Model A implementation. The measurements below show the two are
**not** interchangeable, so this is a substantive naming defect, not cosmetics.

---

## 1. Authority

Production wrote to `simulation_sealed_product_results` **during this session** (477 → 614 rows).
By the end there were two *complete* 137-SKU cohorts: `price_as_of` 2026-08-17 and 2026-08-21.
The repo's `load_eligible_products()` correctly fails closed on this ("ambiguous authority").
Taking "latest run wins" would have blended two price dates — exactly the mixed authority the
task forbids — so the analysis pins to a single `price_as_of` and records everything dropped.

| Field | Primary | Replication |
|---|---|---|
| Pinned `price_as_of` | **2026-08-17** | **2026-08-21** |
| SKUs / calculation runs | 137 / 22 | 137 / 22 |
| Family counts | 15 / 23 / 27 / 2 / 7 / 22 / 26 / 15 | identical |
| Min SKU price | $5.65 | $5.47 |
| Max SKU price | **$1,339.19** | **$1,331.19** |
| Financial RIP | `financial_rip_v4_outcome_profile_p95_only_25_20_15_25_10_5` | identical |
| Overall RIP | `overall_rip_v10_90_financial_v4_10_collector_appeal_v5` | identical |
| Collector Appeal | `collector_appeal_v5_contextual_roster_h_only_d_baseline_up4_down2` | identical |

The primary cohort reproduces the task's stated baseline exactly (137 SKUs, max $1,339.19, all
eight family counts). Family counts by family: booster_box 15, booster_bundle 23,
elite_trainer_box 27, enhanced_booster_box 2, half_booster_box 7, loose_booster_pack 22,
pokemon_center_elite_trainer_box 26, sleeved_booster_pack 15.

---

## 2. Methods tested

**FLOOR_BUDGET (Model A).** `quantity = floor(target_budget / unit_price)`. Committed capital is
`quantity × price`; leftover cash is recorded and **never** scored, invested, or folded into the
outcome distribution. Scored on the real Q-unit distribution via
`build_stage1_product_distributions` → `build_financial_rip_v3` →
`project_financial_rip_v4_from_v3_payload` → `compute_overall_rip_v10`.

**MATCHED_CAPITAL (Model B).** The repository's existing `nearest_spend_pair()`, unmodified.
Tolerances verified from source, not assumed: primary **5%**, sensitivity **2%**
(`PRIMARY_TOLERANCE` / `SENSITIVITY_TOLERANCE`), bounded by `MAX_PAIR_SPEND = $1,000` and
`MAX_QUANTITY = 200`. Pairwise winners are aggregated into a global order by Copeland score
(wins − losses). Because the $1,000 bound is load-bearing at Full Market scale, a **relaxed
$2,800 bound** is run alongside it to prove whether findings are parametric or structural.

**RETAINED_CASH (diagnostic only).** `terminalWealth = openingOutcome + unusedCash`, evaluated
against the full budget. Used strictly to detect bias. Financial RIP V4 is deliberately **not**
recomputed over cash-adjusted outcomes: its components are anchored to committed capital, and
injecting a risk-free cash lump would change what every component means.

---

## 3. Full Market at $1,350

Coverage **137 / 137 (100%)**.

| Statistic | Capital utilization | Unused $ | Unused % |
|---|---:|---:|---:|
| Mean | 0.9414 | $79.08 | 5.86% |
| Median | 0.9699 | $40.68 | 3.01% |
| Std dev | 0.0753 | $101.64 | 7.53% |
| Minimum | 0.5217 | $0.12 | 0.009% |
| P10 | 0.8534 | $4.36 | 0.32% |
| P25 | 0.9149 | $6.43 | 0.48% |
| P75 | 0.9952 | $114.93 | 8.51% |
| P90 | 0.9968 | $197.98 | 14.66% |
| Maximum | 0.9999 | $645.77 | 47.83% |

Utilization is high and tight for most of the cohort (median 97%, P25 91%), with a thin
low-utilization tail driven by expensive indivisible SKUs.

### Worst-utilization SKUs

| Product | Family | Price | Qty | Spend | Unused | Util % | Rank |
|---|---|---:|---:|---:|---:|---:|---:|
| Obsidian Flames PC ETB (Exclusive) | pc_etb | $704.23 | 1 | $704.23 | $645.77 | 52.2% | 47 |
| Prismatic Evolutions PC ETB (Exclusive) | pc_etb | $456.54 | 2 | $913.08 | $436.92 | 67.6% | 27 |

*(full 15-row table in `logs/budget_ranking_semantics_20260817.json` →
`fullMarketAt1350.worstUtilization`)*

---

## 4. Capital utilization vs rank — is there budget-divisibility bias?

| Correlation | Value |
|---|---:|
| Spearman(utilization, rank) | **−0.0727** |
| Pearson(utilization, rank) | **−0.0275** |
| Spearman(utilization, Financial RIP V4) | +0.0950 |
| Spearman(utilization, Overall RIP V10) | +0.0727 |
| Spearman(unused %, rank) | +0.0727 |
| Spearman(unit price, rank) | +0.0770 |
| Spearman(quantity, rank) | −0.0786 |

Every coefficient sits inside ±0.10. Rank improves *very* slightly with better utilization
(negative Spearman vs rank = better rank), which is the **opposite** of the feared bias — poorly
utilized strategies are not being flattered by their unspent cash.

### Utilization quartiles

| Quartile | n | Mean util | Median rank | Mean V4 | Mean V10 |
|---|---:|---:|---:|---:|---:|
| Q1 (worst) | 35 | 0.8419 | 62.0 | 24.71 | 30.45 |
| Q2 | 34 | 0.9443 | 80.0 | 21.87 | 27.71 |
| Q3 | 34 | 0.9852 | 65.5 | 25.97 | 31.08 |
| Q4 (best) | 34 | 0.9972 | 58.5 | 26.30 | 31.56 |

Non-monotonic: Q1 (worst utilization) outperforms Q2 on both median rank and mean score. There is
no clean utilization gradient, so no hidden budget-divisibility bias.

---

## 5. Dominance integrity

Measured properly for the first time (see §0.1). A pair is *comparable* when one strategy weakly
dominates the other on all four of RTP, typical retention, chance to recover capital, and loss
resilience; an *inversion* is the dominator ranking below its dominatee.

| Method | Comparable pairs | Inversions | Rate |
|---|---:|---:|---:|
| FLOOR_BUDGET @ $1,350 | 4,508 | 48 | **1.06%** |
| MATCHED_CAPITAL 5% / $1,000 | 4,127 | 24 | **0.58%** |
| MATCHED_CAPITAL 2% / $1,000 | 3,352 | 20 | **0.60%** |
| MATCHED_CAPITAL 5% / $2,800 | 4,631 | 35 | **0.76%** |

Neither method is at zero. **But the inversions are not an allocation defect** — they are Overall
RIP V10 behaving as designed (0.90 Financial + 0.10 Collector Appeal):

- **48 / 48** floor inversions have **higher Collector Appeal on the winner**.
- Only **1 / 48** had a higher Financial RIP V4 (by +0.04 — a numerical tie).
- Mean Financial V4 delta (winner − dominator) = **−1.36**; the winner is financially *worse* and
  wins on appeal, exactly the intended trade.
- Utilization direction is **26 / 48** — a coin flip, confirming this is not capital bias.

A financially-dominated product outranking on desirability is the documented purpose of V10, not
a fault in the budget normalization. The allocation-isolating test is dominance against Financial
RIP V4 alone — reported in §5.1.

### 5.1 Financial-only dominance (allocation isolated from Collector Appeal)

Ranking the same floor-budget strategies by **Financial RIP V4 alone** removes Collector Appeal
from the comparator and tests the allocation rule on its own terms:

| Budget | Inversions | Comparable pairs | Rate |
|---|---:|---:|---:|
| $500 | 2 | 3,990 | 0.050% |
| **$1,350** | **2** | **4,508** | **0.044%** |
| $1,400 | 2 | 4,569 | 0.044% |
| $1,450 | 3 | 4,559 | 0.066% |
| $1,500 | 3 | 4,605 | 0.065% |
| $1,600 | 5 | 4,635 | 0.108% |

**The floor-budget allocation is essentially dominance-clean** — worst case 5 inversions in 4,635
comparable pairs (0.108%), versus 1.06% once Collector Appeal is admitted. So ~96% of the V10
inversions are attributable to Collector Appeal by design.

The sub-0.11% residual is explained and benign: `multi_metric_dominator()` tests **four** metrics
(RTP, typical retention, true-win probability, loss resilience) while Financial RIP V4 scores
**six** components — `realistic_upside` and `jackpot_upside` are outside the dominance set. Weak
dominance on a 4-metric subset therefore does not imply a higher 6-component V4 score. The
observed cases are marginal (largest V4 gap in the winner's favour: **+0.0406**). This is a
property of the dominance test's metric subset, not a defect in budget normalization.

**Replicated on the 2026-08-21 cohort:**

| Cohort / budget | Financial-only inversions | Rate | V10 inversions | Explained by Collector Appeal |
|---|---:|---:|---:|---:|
| 2026-08-17 @ $1,350 | 2 / 4,508 | 0.044% | 48 | **48 / 48** |
| 2026-08-21 @ $1,350 | 3 / 4,645 | 0.065% | 62 | **61 / 62** |
| 2026-08-21 @ $1,600 | 2 / 4,749 | 0.042% | 80 | **79 / 80** |

On the replication cohort the attribution is 61/62 and 79/80 rather than a clean sweep — one
inversion in each is *not* Collector-Appeal-explained, matching the small financial-only residual
described above. The conclusion is unchanged and stated precisely: **the overwhelming majority
(≈98–100%) of V10 dominance inversions are Collector Appeal operating as designed, and the
allocation rule itself inverts on well under 0.1% of comparable pairs.**

---

## 6. Floor-budget vs matched-capital ranking

| Comparison | Common | Spearman | Top-5 | Top-10 | Top-20 | Mean Δ | Median Δ | Max Δ | ≥5 | ≥10 | ≥20 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 5% / $1,000 | 136 | 0.9488 | 2/5 | 6/10 | 14/20 | 9.60 | 8 | 47 | 97 | 52 | 14 |
| 2% / $1,000 | 136 | 0.9451 | 1/5 | 3/10 | 13/20 | 10.21 | 8 | 34 | 93 | 60 | 21 |
| 5% / $2,800 | 137 | 0.9598 | 3/5 | 7/10 | 15/20 | 7.97 | 5 | 42 | 75 | 40 | 11 |

The two methods agree strongly in aggregate (ρ ≈ 0.95–0.96) but **disagree sharply exactly where
a ranking is consumed** — the podium. Top-5 overlap is 1–3 of 5 and Top-10 is 3–7 of 10. A user
reading "the best product for $1,350" would be shown a materially different answer depending on
which semantics we pick. This is the single most important result in this appendix: the choice is
**not** cosmetic.

### 6.1 Matched capital's structural coverage limit

At the **preregistered** $1,000 bound, the most expensive SKU ($1,339.19 "151 Pokemon Center Elite
Trainer Box (Exclusive)") **cannot be matched against anything** — any pairing containing it needs
more than $1,000 of committed capital. It is excluded from the ranking entirely: **136 / 137**.

Only the relaxed $2,800 bound reaches 137 / 137. So Model B either drops the single most
expensive product in the catalogue, or requires abandoning the preregistered bound that the
existing validated research was built on. This directly fails §27 criterion 2 ("expensive
products are not systematically excluded") at the tolerances actually on record.

---

## 7. Retained-cash diagnostic

| Ordering vs floor-budget rank | Spearman | Top-5 | Top-10 | Mean Δ | Max Δ |
|---|---:|---:|---:|---:|---:|
| Terminal RTP on budget | 0.8531 | 2/5 | 5/10 | 14.95 | 79 |
| Terminal median wealth | 0.6669 | 1/5 | 4/10 | 22.85 | 109 |

Unused cash **does** materially change the economic ordering. This is a genuine caveat and must
shape the consumer language — but it is **not** evidence the ranking is broken. Terminal median
wealth mechanically rewards *not spending*: holding $645.77 in cash is a guaranteed, risk-free
retention that no pack-opening distribution can match. Ranked purely on terminal median wealth,
the "best" strategy trends toward buying as little as possible, which does not answer "what should
I open?"

The correct reading: the floor-budget ranking is a ranking **of opening strategies**, not a
ranking of total end-of-period wealth. It must never be described as "the best thing to do with
$X" — only as the best product to open within $X.

---

## 8. Full Market anchor stability

Every anchor holds 137 / 137 coverage.

| Anchor | Coverage | ρ vs $1,350 | Top-5 | Top-10 | Top-20 | Mean move | Max move | Dominance inv. |
|---|---|---:|---:|---:|---:|---:|---:|---|
| $1,350 | 137/137 | — (baseline) | — | — | — | — | — | 48 / 4,508 |
| $1,400 | 137/137 | 0.99776 | 5/5 | 10/10 | 20/20 | 0.93 | 27 | 54 / 4,569 |
| $1,450 | 137/137 | 0.99755 | 5/5 | 10/10 | 20/20 | 1.11 | 26 | 52 / 4,559 |
| $1,500 | 137/137 | 0.99668 | 5/5 | 10/10 | 20/20 | 1.50 | 25 | 61 / 4,605 |
| $1,600 | 137/137 | 0.99345 | 5/5 | 10/10 | 20/20 | 2.00 | 33 | 60 / 4,635 |

Adjacent anchors:

| Step | Spearman | Mean move | Max move | ≥5 movers |
|---|---:|---:|---:|---:|
| $1,350 → $1,400 | 0.99776 | 0.93 | 27 | 2 |
| $1,400 → $1,450 | 0.99970 | 0.42 | 7 | 2 |
| $1,450 → $1,500 | 0.99921 | 0.69 | 11 | 3 |
| $1,500 → $1,600 | 0.99873 | 0.95 | 11 | 7 |

**Top-5, Top-10 and Top-20 are perfectly preserved at every anchor.** Mean movement never exceeds
2 ranks. The $1,350 → $1,600 range (a +18.5% budget change) is highly stable. The extra anchors
($1,750 / $2,000) were not needed — no instability to resolve.

---

## 9. Quantity-threshold events

316 events where `quantity(B₂) > quantity(B₁)` between adjacent anchors. The most unstable SKUs:

| Product | Family | Price | Range | Best | Worst | Max adj. | Quantities $1,350→$1,600 |
|---|---|---:|---:|---:|---:|---:|---|
| Paldean Fates Booster Bundle | bundle | $171.62 | 33 | 67 | 100 | 27 | 7 → 8 → 8 → 8 → 9 |
| Paldean Fates Booster Pack | loose | $23.43 | 22 | 50 | 72 | 11 | 57 → 59 → 61 → 64 → 68 |
| Phantasmal Flames Sleeved Pack | sleeved | $12.78 | 21 | 59 | 80 | 11 | 105 → 109 → 113 → 117 → 125 |
| Phantasmal Flames Booster Pack | loose | $10.94 | 11 | 26 | 37 | 7 | 123 → 127 → 132 → 137 → 146 |
| Paldea Evolved Booster Box | box | $460.67 | 9 | 26 | 35 | 8 | 2 → 3 → 3 → 3 → 3 |

The largest mover (Paldean Fates Booster Bundle, range 33) crosses 7→8 units between $1,350 and
$1,400 — utilization jumps from 89.0% to 98.1%. These movements are **explainable and economic**:
crossing a whole-unit threshold genuinely changes both capital utilization and the shape of the
aggregate outcome distribution (more units → tighter distribution, higher chance to recover). The
behaviour is a real property of buying indivisible goods, not an artifact.

---

## 10. Family stability

| Family | n | Median move | Mean move | Max move | Median util | Median rank | Qty events |
|---|---:|---:|---:|---:|---:|---:|---:|
| booster_box | 15 | 0.75 | 0.78 | 8 | 0.8893 | 33.0 | 13 |
| booster_bundle | 23 | 0.50 | 1.02 | 27 | 0.9726 | 79.0 | 69 |
| elite_trainer_box | 27 | 0.25 | 0.50 | 5 | 0.9522 | 100.0 | 49 |
| enhanced_booster_box | 2 | 0.25 | 0.25 | 1 | 0.9355 | 20.5 | 2 |
| half_booster_box | 7 | 0.50 | 0.57 | 3 | 0.9259 | 113.0 | 9 |
| loose_booster_pack | 22 | 0.50 | 0.84 | 11 | 0.9961 | 40.5 | 88 |
| pokemon_center_elite_trainer_box | 26 | 0.50 | 0.65 | 9 | 0.9152 | 61.5 | 26 |
| sleeved_booster_pack | 15 | 0.50 | 0.92 | 11 | 0.9963 | 85.0 | 60

No family is destabilized: median movement ≤ 0.75 ranks everywhere, mean ≤ 1.02. Cheap divisible
formats (loose/sleeved packs) have the **highest** utilization (≈0.996) and the most threshold
events (88, 60) yet remain stable (median move 0.50) — divisibility does not translate into rank
churn. Median-rank spread across families (box 33 vs half-box 113) reflects genuine product
economics, not a methodological thumb on the scale: it is not correlated with utilization
(booster_box has the *second-lowest* median utilization, 0.889, and the *best* median rank).

---

## 11. Full Market rounding rule

`anchor = ceil(maxEligibleSkuPrice / increment) × increment`, max price $1,339.19.

| Increment | Anchor | Excess over max SKU | Excess % | Distinct anchors across sweep | Anchor churn |
|---|---:|---:|---:|---:|---:|
| $25 | $1,350 | $10.81 | 0.81% | 5 | 4 |
| **$50** | **$1,350** | **$10.81** | **0.81%** | **3** | **2** |
| $100 | $1,400 | $60.81 | 4.54% | 2 | 1 |

Price-sensitivity sweep (1320 / 1330 / 1339.19 / 1345 / 1349 / 1351 / 1375 / 1399 / 1401):

- **$25** → 1325, 1350, 1350, 1350, 1350, 1375, 1375, 1400, 1425 (4 changes)
- **$50** → 1350, 1350, 1350, 1350, 1350, 1400, 1400, 1400, 1450 (2 changes)
- **$100** → 1400 × 8, then 1500 (1 change)

**$50 is confirmed, with evidence.** It yields the identical anchor to $25 on the current cohort
($1,350) while halving anchor churn, and costs only 0.81% excess capital versus $100's 4.54% —
5.6× more inflation for one fewer churn event. Since §8 shows ranks are near-invariant between
$1,350 and $1,600, the stability $100 buys is worth nothing, while its capital inflation is real.

**Real-world confirmation.** During this session the max SKU price actually moved
$1,339.19 → $1,331.19 (a genuine −$8.00 over four days). Under both $25 and $50 the anchor
remained **$1,350**; under $100 it remained $1,400. This is an unplanned natural experiment
showing the rule absorbs real price drift without churn.

---

## 12. $500 band vs Full Market

| Metric | Value |
|---|---|
| $500 coverage | 131 / 137 (95.6%) |
| $500 mean utilization | 0.8629 |
| $500 dominance inversions | 26 / 3,990 (0.65%) |
| Common SKUs vs Full Market | 131 |
| Spearman | 0.9305 |
| Top-5 / Top-10 overlap | 3/5 · 8/10 |
| Mean rank movement | 10.17 |
| Max rank movement | 63 |

$500 and Full Market tell a **broadly similar but not identical** story (ρ = 0.93). The prior
record's "median cross-budget Spearman = 1.0" was computed *within* small per-set cohorts, not
across the full cross-format population — it is not comparable to this figure and should not be
read as contradicted. The 131→137 cohort expansion moves ranks by ~10 on average, which is why
Full Market must be published as its own budget-qualified rank rather than presented as an
extension of $500.

---

## 12.5 Independent replication on the 2026-08-21 cohort

Because production shipped a second complete 137-SKU cohort mid-session, the entire analysis was
re-run against it. This is a genuine independent replication: different prices (min $5.47 vs
$5.65, max $1,331.19 vs $1,339.19), different calculation runs, same 137 SKUs and same model
versions.

| Result | 2026-08-17 (primary) | 2026-08-21 (replication) |
|---|---:|---:|
| Coverage at $1,350 | 137/137 | 137/137 |
| Mean capital utilization | 0.9414 | 0.9412 |
| Median utilization | 0.9699 | 0.9731 |
| Minimum utilization | 0.5217 | 0.5151 |
| Spearman(utilization, rank) | −0.0727 | −0.0730 |
| Pearson(utilization, rank) | −0.0275 | −0.0283 |
| Matched-capital coverage @ preregistered bound | 136/137 | 136/137 |
| Matched-capital coverage @ relaxed $2,800 | 137/137 | 137/137 |
| Floor vs matched Spearman (5%/$1,000) | 0.9488 | 0.9525 |
| Floor vs matched Top-5 overlap | 2/5 | 1/5 |
| ρ($1,600 vs $1,350) | 0.99345 | 0.99516 |
| Retained-cash ρ (terminal RTP) | 0.8531 | 0.8538 |
| Retained-cash ρ (terminal median wealth) | 0.6669 | 0.6715 |
| $500 vs Full Market ρ | 0.9305 | 0.9347 |
| $50 anchor | $1,350 | $1,350 |

Every finding reproduces, including the two that drive the decision: the **1-SKU structural
exclusion** under the preregistered matched-capital bound, and the **podium disagreement** between
the two methods (Top-5 overlap 1–2 of 5). The decision is not an artifact of one price snapshot.

Rounding on the replication cohort: $25 → $1,350 (churn 4), $50 → $1,350 (churn 2), $100 → $1,400
(5.17% excess). Identical ordering of merit, confirming §11.

---

## 13. Consumer semantics

**Candidate A** — *"You have up to $250. We rank the strongest whole-product opening strategies
that fit within that budget."*

- Mathematically accurate? **Yes.** Exactly `floor(budget / price)`.
- Matches implementation? **Yes**, precisely.
- Understandable? **Yes** — "as many as $X buys" needs no explanation.
- Hides a caveat? **One**: leftover cash is not credited. §7 shows this matters, so the wording
  must stay "to open", never "to do with your money".
- Answers "I have $X, what should I open?" — **Yes, directly.**

**Candidate B** — *"We compare products using approximately the same amount of money so different
sealed formats can be evaluated fairly."*

- Mathematically accurate? **Yes**, for pairs that match within tolerance.
- Matches implementation? **No** — today's engine is floor-to-budget while *calling* itself
  equal-committed-capital (§0.2).
- Understandable? **Weaker.** "Approximately the same amount" invites "how approximate?", and the
  honest answer is a 5% tolerance with a $1,000 pairwise bound.
- Hides a caveat? **Yes, a serious one**: it silently drops the most expensive SKU (§6.1), and the
  spend a user is quoted is not a budget they chose.
- Answers "I have $X, what should I open?" — **No.** It answers "which format is fairer at
  comparable spend", a researcher's question, not a shopper's.

Model B is the better *scientific control*. Model A is the only one that answers the product
question, and it is the one already built.

---

## 14. Decision

## `BUDGET_CONSTRAINED_WHOLE_UNIT_RANKING_V1_APPROVED`

Checked against the §26 approval standard:

1. **No material unexplained utilization bias.** All utilization/rank correlations sit within
   ±0.10 (Spearman −0.073, Pearson −0.028), the sign is the *opposite* of the feared bias, and the
   utilization quartiles are non-monotonic (Q1 beats Q2). ✅
2. **Dominance inversions acceptably low.** 0.044% at $1,350 on the allocation-isolating
   financial-only test (worst 0.108%); 0.065% / 0.042% on the replication cohort. The higher
   1.06–1.33% V10 figure is ≈98–100% attributable to Collector Appeal operating as designed. ✅
3. **Stable across nearby full-cohort anchors.** ρ ≥ 0.993 from $1,350 to $1,600 with Top-5,
   Top-10 and Top-20 perfectly preserved at every anchor; mean movement ≤ 2 ranks. ✅
4. **Quantity-threshold movement understandable.** 316 events, all traceable to a whole-unit
   crossing that genuinely changes utilization and distribution shape. ✅
5. **Economically coherent.** Rank tracks the outcome profile of what is actually opened. ✅
6. **"Up to $X" is accurate.** It is literally `floor(budget / price)`. ✅
7. **Deterministic.** Fixed comparator, no tolerance parameter, no search. ✅
8. **More useful than Family Rank alone.** It is the only tested construct that ranks all 137 SKUs
   across all 8 families at one common budget. ✅

Model B is rejected on its own standard (§27): at the **preregistered** 5%/$1,000 tolerance it
cannot represent the most expensive SKU at all (136/137), failing criterion 2. Rescuing coverage
requires abandoning the bound the existing validated research rests on. It also fails criterion 7
— it answers "which format is fairer at comparable spend", not "I have $X, what should I open?"

Two caveats bind this approval and are **not** optional:

- **Naming must change.** The engine currently calls itself `equal_committed_capital_cross_format_v1`
  while implementing a budget ceiling. Since §6 proves the two methods produce materially different
  podiums, that label is actively misleading.
- **Copy must say "to open", never "to do with your money".** §7 shows unspent cash materially
  changes total-wealth ordering (ρ = 0.67 on terminal median wealth). The ranking ranks opening
  strategies, not end-of-period wealth.

---

## 15. Required implementation changes (next pass — none applied here)

Specified only — **nothing below was applied in this pass.**

### 15.1 Rename the comparison scope (blocking)

In `backend/calculations/evr/budget_normalized_product_ranking.py`:

```python
# was: "equal_committed_capital_cross_format_v1"
BUDGET_COMPARISON_SCOPE_VERSION = "budget_constrained_whole_unit_cross_format_v1"
```

Per the module's own versioning convention, add the new constant rather than mutating the meaning
of the published one. Because migration `20260822213027` stores this string on every row, the
follow-up pass must decide between a new method version with a clean republish, or a documented
value migration. Also correct the module docstring ("capital-matched" → "budget-constrained") and
the "Equal-committed-capital comparison" sentence in `BUDGET_NORMALIZED_PRODUCT_RANKING_v1.md`.

### 15.2 Fix the V4 raw-metric extraction defect (blocking)

`research_equal_spend_product_rip_v4.py:140` reads `audit.normalizedInputs` off the **V4**
projection, which is empty. Source it from the **V3** payload instead:

```python
raw = {k: rec.get("raw") for k, rec in ((v3_payload.get("audit") or {}).get("normalizedInputs") or {}).items()}
```

Add a guard that raises when any dominance metric is `None`, so a vacuous test can never again be
reported as "zero inversions". Then re-run that harness and correct any downstream claim that
cites its dominance numbers.

### 15.3 Terminology contract

Adopt **Budget-Constrained Product Ranking** throughout. Definition of record:

> Ranks strategies consisting of the maximum whole units of a single SKU purchasable at or below
> the selected budget ceiling, scored on the real multi-unit outcome distribution. Leftover cash
> is reported, never scored.

### 15.4 Fields to add to the row contract

Present in research, absent from the published rows:

| Field | Why |
|---|---|
| `capital_utilization` | `actualCommittedCapital / targetBudget`; already proven unbiased, needed for auditability |
| `unused_capital_percent` | already computed by `whole_unit_allocation`, currently dropped on write |
| `chance_to_recover_capital` | populate it — production hard-codes `None`, leaving tie-break 3 inert |
| `financial_only_rank` | the allocation-isolating diagnostic from §5.1 |
| `pinned_price_as_of` | required for reproducibility; production carries multiple complete cohorts |

### 15.5 Authority-resolution hardening

`load_eligible_products()` fails closed on multi-run SKUs, which blocks legitimate reruns whenever
production holds two cohorts. Adopt the `--price-as-of` pinning approach from
`research_budget_ranking_semantics.py`: pin to one `price_as_of`, tie-break to the latest date,
and record every excluded run as provenance.

### 15.6 Not required

- Full Market rounding stays at **$50** — confirmed by §11 plus a real-world price move.
- Canonical bands ($25–$500) stay; $500 and Full Market are materially different (ρ = 0.93) and
  both remain meaningful.
- No change to Financial RIP V4, Overall RIP V10, Collector Appeal, or Family Rank.

---

## 16. Reproducing this analysis

```bash
# primary (pinned to the task's baseline cohort)
python -m backend.scripts.research_budget_ranking_semantics \
    --price-as-of 2026-08-17 \
    --json logs/budget_ranking_semantics_20260817.json

# replication on the newer cohort
python -m backend.scripts.research_budget_ranking_semantics \
    --price-as-of 2026-08-21 \
    --json logs/budget_ranking_semantics_20260821.json

# default: most SKUs, ties broken to the LATEST price_as_of
python -m backend.scripts.research_budget_ranking_semantics
```

The script is SELECT-only. It performs no `INSERT`/`UPDATE`/`DELETE`, applies no migration, and
publishes nothing. `--price-as-of` exists because production may hold several complete cohorts at
once; pinning is required for a reproducible number.

**Known deviation from production:** this harness populates the `chanceToRecoverCapital`
tie-break, whereas `build_budget_normalized_product_rankings.py` hard-codes
`chanceToRecoverCost: None`, leaving production's third tie-break inert. It can only bind on an
exact Overall-V10 *and* Financial-V4 float tie. **Verified non-binding:** exact (V10, V4) tie
count is **0** at every budget tested ($500, $1,350, $1,400, $1,450, $1,500, $1,600), so the two
comparators produce identical orderings on this cohort.

### 16.1 Pre-existing test failure (not introduced by this pass)

`backend/tests/unit/scripts/test_research_equal_spend_product_rip.py::test_no_database_or_snapshot_writes_contract_and_import_isolation`
**fails on a pristine tree** with this pass's files removed. Its final assertion forbids any
non-test file under `backend/` from referencing `research_equal_spend_product_rip`, but seven
research harnesses already do:

```
research_financial_rip_final_validation.py        (12c271f, 2026-08-18)
research_product_rip_dominance_utility.py         (b9daf61, 2026-08-18)
research_opponent_adjusted_product_rip.py
research_product_rip_publication_architecture.py
research_realistic_upside_candidate_matrix.py
research_realistic_upside_semantics.py
_run_v4_research_driver.py                        (2f0fc62, 2026-08-22)
```

The earliest dates to 2026-08-18, four days before this session. The contract's *intent* —
production code must not depend on research modules — is still satisfied; the assertion is simply
too broad, because it exempts only one research harness by name while the repo now has several.
`research_budget_ranking_semantics.py` becomes an eighth file in the same category.

**Deliberately not fixed here.** Editing the assertion to whitelist this pass's script would have
turned a red test green without addressing why it is red, and disguised a pre-existing problem as
a passing suite. The correct fix — generalise the exemption to all `backend/scripts/research_*.py`
harnesses, or invert it to assert the absence of research imports in genuinely production modules
only — belongs to the follow-up pass.

All other touched suites pass: `test_budget_normalized_product_ranking.py` **25/25**, and the
remaining 9 tests in the equal-spend file.
