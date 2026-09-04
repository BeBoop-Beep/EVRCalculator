# Overall RIP Accessibility — Pass 1A Product Supplement (multi-product ECE test)

Status: **OVERALL_RIP_ACCESSIBILITY_PASS_1A_PRODUCT_SUPPLEMENT_COMPLETE**

Research only. No production code, scoring config, or canonical Overall RIP / Chase
Accessibility file was modified. No migration, deploy, publish, backfill, commit, or
branch operation was performed. Builds directly on
`docs/research/OVERALL_RIP_ACCESSIBILITY_PASS_1A_ECE.md` ("Pass 1A") — that report's
methodology, authority table, and coherence-limitation writeup are not re-derived
here; only what changes on a multi-product cohort is presented.

## 0. Workspace

- Branch: `fix/public-rankings-entitlement-regression-2`
- Start HEAD: `6001825c8519fcdb5860d9de66826ca6a0356a6c`
- `git status --short` before this pass: clean. After this pass: only the new
  `backend/research/scratch_pass1a_supplement/` scratch directory and the three
  `docs/research/*` deliverables below. No billing, market-explorer, or infra/log
  file was read or touched.

## 1. Multi-product cohort

Pass 1A's frozen `A_raw` per set (from
`docs/research/overall_rip_accessibility_primary_cohort.json`, same 22 `set_id`s) was
broadcast onto every eligible sealed product in that set, pulled fresh from
`simulation_sealed_product_results` (all 8 product families, same table/columns Pass
1A used, no restriction to `loose_booster_pack`).

Pairing rule (same approach as Pass 1A's Track B): for each `sealed_product_id`,
take the **latest row** (by `created_at`) that has **both**
`collector_appeal_score` and `overall_rip_v10_score` non-null. `effective_pack_cost
= product_market_cost / pack_equivalent`, where `pack_equivalent` prefers
`pack_count` when populated and > 0, else falls back to `random_pack_count`.

**Result: 138 products, 22 sets, 8 families, 0 exclusions.** This lands inside the
~130–145 range the task anticipated from prior observation — no artificial
shrinkage was needed; every product in the 22-set target scope that had ever
received full Financial+Collector+Overall enrichment was included, and every one
of those also resolved a usable `pack_equivalent` and `product_market_cost`.

| Family | n |
|---|---|
| elite_trainer_box | 27 |
| pokemon_center_elite_trainer_box | 26 |
| booster_bundle | 23 |
| loose_booster_pack | 22 |
| sleeved_booster_pack | 15 |
| booster_box | 15 |
| half_booster_box | 8 |
| enhanced_booster_box | 2 |

Products per set: min 4, max 10, mean 6.27.

Exclusions: **none.** All 138 distinct `sealed_product_id`s found across the 22
target sets (all families, all runs) had at least one row with full
Financial+Collector+Overall enrichment and a resolvable `pack_count`/
`random_pack_count` and `product_market_cost` — so the "never enriched" and
"unresolvable pack/cost" exclusion buckets built for this pass are both empty.

Frozen to `docs/research/overall_rip_accessibility_product_cohort.json`: per
product — `sealed_product_id`, `set_id`, `product_family`, `product_name`,
`calculation_run_id` + `run_created_at`, `product_market_cost`, `pack_count`,
`random_pack_count`, `pack_equivalent_used`, `effective_pack_cost`, broadcast
`A_raw`, `ECE_raw`, all 6 Financial RIP V4 components + total, Collector Appeal
V5, Overall RIP V10, EV/P95/P99 (+ each `/cost`), `total_value_to_cost_ratio`, and
both the accessibility-run and financial/collector-run ids/dates.

## 2. Set-level invariance

Every product's `A_raw` was assigned directly from the single per-set value in the
frozen Pass 1A cohort dict (a Python dict keyed by `set_id`, one broadcast per
product row), so identical-by-construction is expected. Verified anyway by
grouping the 138-row cohort by `set_id` and counting distinct `A_raw` values per
group.

**Sets checked: 22. Products checked: 138. Mismatches: 0.** No join bug.

## 3. ECE matrix on full product cohort

`ECE_raw = A_raw / effective_pack_cost`, n=138 (all Spearman, scipy):

| vs. ECE_raw | ρ | p |
|---|---|---|
| Accessibility (A_raw) | 0.6812 | <0.001 |
| PriceEfficiency (1/effective_pack_cost) | 0.5983 | <0.001 |
| Effective pack cost | -0.5983 | <0.001 |
| Collector Appeal V5 | -0.5953 | <0.001 |
| Product market cost | -0.3265 | <0.001 |
| Financial RIP V4 total | 0.3583 | <0.001 |
| Realistic Upside | 0.3656 | <0.001 |
| Overall RIP V10 | 0.2843 | <0.001 |
| Base Economic Efficiency | 0.2843 | <0.001 |
| True Win Frequency | 0.2818 | <0.001 |
| Loss Resilience | 0.1788 | 0.036 |
| P99/cost | -0.1681 | 0.049 |
| Pack-equivalent count | -0.1087 | 0.204 |
| Typical Retention | 0.1167 | 0.173 |
| Jackpot Upside | -0.0665 | 0.438 |
| EV/cost | -0.0496 | 0.564 |
| P95/cost | 0.0173 | 0.840 |

Everything against ECE is now significant except EV/cost, P95/cost, pack-equivalent
count, Typical Retention, and Jackpot Upside — a marked change from Pass 1A's
n=22 single-product cohort, where almost nothing but A_raw itself and Collector
Appeal cleared significance. This is the expected consequence of adding 116 more
products whose `effective_pack_cost` spans a much wider range (loose packs at ~$11
up to Pokémon Center ETBs at ~$330), which mechanically inflates correlation with
anything price-linked.

Partials controlling for `effective_pack_cost`:
- **ρ(Financial, ECE | effective_pack_cost) = 0.0576** (p=0.502) — collapses to
  essentially zero (Pass 1A: 0.1746, also weak).
- **ρ(EV/cost, ECE | effective_pack_cost) = -0.0230** (p=0.789) — collapses to
  essentially zero (Pass 1A: -0.3511).

### Residual regression

`rank(ECE) ~ rank(Financial) + rank(A_raw)`, n=138:
- **R² = 0.6411** (Pass 1A: 0.6487 — nearly identical)
- Spearman(predicted rank, actual rank) = 0.8085 (Pass 1A: 0.7877)
- Residual-vs-`rank(PriceEfficiency)` ρ = 0.7397 (p<0.001)

### Key residual test — direct comparison to Pass 1A's 0.8814

Residualizing both ECE and PriceEfficiency against `[Financial, Accessibility]`
(rank regression) and correlating the residuals:

**ρ_partial(ECE, PriceEfficiency | Financial, Accessibility) = 0.9152 (p = 1.5e-55, n=138)**

This is *higher* than Pass 1A's 0.8814, not lower. **The conclusion reproduces —
and strengthens — on the multi-product cohort.** Roughly 36% of ECE's rank
variance (1-R²=0.359) is unexplained by Financial+Accessibility jointly, and that
unexplained remainder is now even more overwhelmingly (ρ=0.92 vs 0.88) just price.

## 4. Same-set price placebo (the test Pass 1A could not run)

Within each of the 22 sets, `A_raw` is a shared constant (by construction, per §2),
so `ECE_raw = A_raw / effective_pack_cost` reduces mathematically to a monotone
transform of `1/effective_pack_cost` for every product in that set. This predicts
ECE's within-set product ranking should be **identical** to ranking by
`PriceEfficiency` alone.

**Confirmed empirically, exactly: for all 22 sets, the within-set rank order by
`ECE_raw` equals the within-set rank order by `PriceEfficiency` — zero
exceptions.**

Same-set pairwise comparison (398 same-set product pairs across the 22 sets, each
pair's ECE-vs-V10 ordering and PriceEfficiency-vs-V10 ordering compared):

| Metric | Count |
|---|---|
| Same-set product pairs | 398 |
| ECE-vs-V10 reversals | 102 |
| PriceEfficiency-vs-V10 reversals | 102 |
| Shared reversals (both flip the identical pair) | **102 / 102 (100%)** |
| ECE-only reversals | **0** |
| PriceEfficiency-only reversals | **0** |
| Agreement rate (ECE ranking vs V10 control, same-set pairs) | 74.4% |
| Reversals where the cheaper-effective-cost product won | **102 / 102 (100%)** |

**All same-set ECE differentiation is mechanically identical to price-only
ranking — stated explicitly and prominently, per the task instruction.** Every
single same-set reversal ECE produces relative to the V10 control is also produced,
identically, by ranking on `1/effective_pack_cost` alone, and in every one of those
102 reversals the cheaper-effective-cost product is the one ECE promotes. There is
no same-set case in this 138-product cohort where ECE's within-set behavior
diverges from bare price ranking.

### Representative same-set ECE-induced reversals

| Set (first 8 chars) | Product A (family) | Product B (family) | Financial A / B | Gap | Eff. cost A / B | ECE A / B | Winner | Cheaper won? |
|---|---|---|---|---|---|---|---|---|
| 0f7e51e2 | sleeved_booster_pack | pokemon_center_elite_trainer_box | 17.52 / 19.38 | 1.86 | $13.54 / $26.19 | 1.65e-4 / 0.85e-4 | A (sleeved pack) | Yes |
| 0f7e51e2 | booster_bundle | pokemon_center_elite_trainer_box | 17.47 / 19.38 | 1.91 | $13.66 / $26.19 | 1.64e-4 / 0.85e-4 | A (bundle) | Yes |
| 0f7e51e2 | elite_trainer_box | pokemon_center_elite_trainer_box | 15.50 / 19.38 | 3.88 | $16.97 / $26.19 | 1.32e-4 / 0.85e-4 | A (ETB) | Yes |

(Full 102-row list: `backend/research/scratch_pass1a_supplement/ece_reversal_examples.json`,
not a formal deliverable but left for traceability.) The pattern is consistent
across all 102 rows: the lower-Financial, lower-effective-cost product wins the
ECE comparison every time, purely because it is cheaper per effective pack — this
is the price-placebo effect stated above, not a genuinely orthogonal chase-value
judgment.

## 5. Large-Financial-gap protection (diagnostic only)

`Overall_ECE = 0.84·Financial + 0.10·Collector + 0.06·pctrank(ECE)`, same
transform family as Pass 1A, evaluated against the V10 control across all
same-set pairs.

| Metric | Value |
|---|---|
| Clear Financial overrides, `|ΔFinancial| ≥ 10` between a reversed pair | 16 |
| Max Financial gap overturned | 19.81 |
| Max **same-set** Financial gap overturned | 19.81 (same figure — the largest overturn observed is itself same-set) |
| Close-pair (`|ΔFinancial| < 5`) reversal rate | 39.5% (157 close same-set pairs, ~62 reversed) |

A ~19.8-point Financial gap being overturned by a 6%-weighted price-derived
percentile term is a large override for a small weight, and it recurs (16 pairs
at ≥10-point gaps). This reinforces §4: at product granularity, a small ECE
weight is disproportionately capable of reordering large Financial gaps because
ECE's product-level variance is dominated by price, and price varies far more
sharply across formats (ETB vs booster box vs loose pack, ~30x cost spread) than
Financial RIP does.

## 6. Product family bias

| Family | n | Avg price | Avg eff. pack cost | Avg ECE | Avg rank movement (diag blend vs V10) | Risers | Fallers | Same-set reversal wins | Same-set reversal losses |
|---|---|---|---|---|---|---|---|---|---|
| enhanced_booster_box | 2 | $275.07 | $7.64 | 2.11e-4 | +0.50 | 1 | 1 | 1 | 2 |
| booster_box | 15 | $306.99 | $8.53 | 2.80e-4 | +3.00 | 9 | 4 | 11 | 0 |
| sleeved_booster_pack | 15 | $10.69 | $10.69 | 2.17e-4 | +5.93 | 9 | 5 | 14 | 3 |
| loose_booster_pack | 22 | $11.87 | $11.87 | 2.09e-4 | +1.55 | 13 | 8 | 17 | 5 |
| half_booster_box | 8 | $244.55 | $13.59 | 1.53e-4 | +0.88 | 4 | 3 | 8 | 1 |
| booster_bundle | 23 | $84.44 | $14.07 | 1.72e-4 | -1.00 | 12 | 9 | 22 | 8 |
| elite_trainer_box | 27 | $168.41 | $18.71 | 1.33e-4 | +0.26 | 14 | 12 | 28 | 13 |
| pokemon_center_elite_trainer_box | 26 | $331.57 | $30.14 | 0.97e-4 | **-6.15** | 5 | 20 | 1 | 70 |

Sorted by effective pack cost, the pattern is monotone: the three cheapest
effective-pack-cost formats (booster_box, sleeved_booster_pack, loose_booster_pack
— note booster_box's low *effective* cost despite a high sticker price, because it
divides by a large pack-equivalent count) have the highest avg ECE and net-positive
rank movement, while `pokemon_center_elite_trainer_box` — the highest effective
cost by a wide margin ($30.14, ~2.5x the next family) — has by far the worst
outcome: -6.15 average rank movement, 20 fallers vs 5 risers, and 70 same-set
reversal *losses* against only 1 win.

**Does ECE systematically reward low-effective-pack-cost formats? Yes,
unambiguously**, and this is exactly the same mechanism identified in §3/§4, now
visible as a family-level effect: format choice (which changes `effective_pack_cost`
via the pack-equivalent divisor) drives ECE far more than anything about the
Financial or Accessibility content of the product.

Distinguishing (A) vs (B) per the task instruction:
- **(A) Legitimate Product Chase Efficiency behavior**: as a *standalone* metric
  answering "which SKU gives me the most set-completion probability per dollar of
  effective pack cost," rewarding cheap-per-pack formats is exactly the intended
  signal, and is not wrong on its own terms.
- **(B) Reason not to give it a second implicit price vote inside Overall RIP**:
  this same family bias, inside a *composite* rank, means giving ECE nonzero
  Overall RIP weight double-counts price purely because certain formats
  mechanically produce a cheaper effective-pack-cost, on top of whatever cost
  signal Financial RIP V4 already contributes through EV/cost, P95/cost, etc.
  This is the multi-product cohort's version of Pass 1A's §9 finding, now backed
  by a mechanism (family-level cost divisor) rather than only a residual
  correlation number.

## 7. Product-level budget validation

Pass 1A's §8 method, applied to the full 138-product cohort:
`q = floor(budget/product_price)`, `packs = q · pack_equivalent`,
`O_budget = Σ_i HC_i·(1-(1-p_i)^packs)`, using each set's frozen per-variant
`HC_i`/`p_i` arrays from the primary cohort file. Products unaffordable at a given
budget (`q < 1`) are excluded from that budget's comparable set.

| Budget | Comparable pairs | Agree | Disagree | Agreement rate |
|---|---|---|---|---|
| $25 | 15 | 10 | 5 | 66.7% |
| $50 | 23 | 19 | 4 | 82.6% |
| $100 | 56 | 48 | 8 | 85.7% |
| $200 | 185 | 171 | 14 | 92.4% |
| $500 | 379 | 323 | 56 | 85.2% |

This is materially **lower and noisier** than Pass 1A's single-family cohort
(87.6%–100%, monotonically rising to a clean 100% at $200). Once cross-format
(cross-family) pairs dominate the comparable set — which happens immediately here,
since almost every same-set pair by construction compares different-family
products at low-to-mid product counts per set — agreement never reaches 100% at
any tested budget, and it *degrades again* at $500 (85.2%, down from 92.4% at
$200), the same probability-saturation effect Pass 1A saw, now compounded by
format-driven divisibility differences (e.g. a $330 Pokémon Center ETB is
unaffordable in useful quantity at low budgets regardless of its ECE ranking).

**Cross-format, same-set comparisons specifically** (the critical addition this
supplement was built to test): almost the entire comparable set at every budget
*is* cross-format (e.g. 185/185 at $200 broken out as 167 cross-family + only 4
within the identical shared family, mostly booster_box/booster_bundle
sub-variants). This means the agreement-rate table above already IS predominantly
the cross-format-within-set test: 66.7%–92.4%, never fully agreeing, confirming
that ECE and O_budget diverge specifically at product-format boundaries (loose
pack vs ETB vs booster box for the same set) — exactly where indivisibility
(a $330 product vs an $11 product at the same $25–$100 budget) and per-format
pack-equivalent size interact with the discrete floor(budget/price) step that
ECE's continuous ratio ignores.

Representative disagreement causes (from `budget_disagree_*.json`, not a formal
deliverable, left for traceability):
- **Format-driven unaffordability**: at $25–$100, a Pokémon Center ETB (~$330) or
  booster box (~$307) is either unaffordable (`q=0`, excluded) or affordable only
  at `q=1`, while a loose pack at the same budget buys `q=2-9`; ECE's continuous
  ratio treats both formats identically, but O_budget correctly collapses the
  expensive format's contribution at low budgets.
- **Pack-equivalent indivisibility**: a booster box with a large `random_pack_count`
  jumps in large discrete steps in `packs = q·pack_equivalent`, producing
  saturation-like jumps in `O_budget` that ECE's ratio does not anticipate.
- **Saturation at $500**: as in Pass 1A, very large `packs` values push some
  variants' `1-(1-p)^packs` toward 1, compressing `O_budget` non-linearly and
  reintroducing disagreements after the $200 peak.

**Conclusions (same structure as Pass 1A §8):**
- **For full-market / no-explicit-budget ranking**: ECE remains a reasonable
  continuous-capital idealization for ranking *within* a single format, but the
  multi-product/cross-format evidence here is weaker than Pass 1A's single-family
  result — agreement never reaches 100% at any budget once cross-format pairs
  dominate, so ECE's full-market ranking should be understood as reliable
  primarily *within* a product family, not as a universal cross-format ranking.
- **For an explicitly selected budget, especially across formats within a set
  (loose pack vs ETB vs booster box for the same set)**: `O_budget` should rank
  products, not ECE. The gap between the two orderings is larger and more
  persistent here than in Pass 1A, driven specifically by cross-format
  indivisibility and pack-equivalent step size — the exact scenario this
  supplement was commissioned to test.

## 8. Cross-check of Pass 1A's conclusion

Pass 1A concluded: *"Product Chase Efficiency = valid standalone Premium metric,
Overall RIP weight = 0."*

Evidence gathered here:
- §3's key residual test reproduces and strengthens Pass 1A's finding (0.9152 vs
  0.8814) — the Overall-RIP-weight-zero conclusion is *confirmed*, more strongly,
  at product level.
- §4's same-set placebo shows something Pass 1A could not test and that changes
  the standalone-metric characterization: **100% of same-set ECE differentiation
  is mechanically identical to bare price ranking** (0 ECE-only reversals out of
  102 same-set reversals; every one of them also flips under `PriceEfficiency`
  alone, and the cheaper product wins in all 102). This is expected given
  `A_raw` is a set-level constant (§2), but it is a materially stronger and more
  concrete statement than Pass 1A's set-level "Accessibility is not price in
  disguise" finding (§3 of Pass 1A) — that finding is about `A_raw` itself across
  *sets*, and it still holds; this finding is about `ECE`'s behavior *within* a
  set, across *products*, which is a different and previously untested claim.
- §6 shows this manifests as a systematic family/format bias (cheap-effective-cost
  formats rise, expensive ones — especially Pokémon Center ETBs — fall sharply),
  reinforcing that ECE's product-level ranking power inside a set is,
  concretely, a price ranking with an extra step.

**Classification: REVISED_SAME_SET_ECE_IS_MECHANICALLY_PRICE_ONLY**

The Overall-RIP-weight-zero decision itself is *confirmed*, not revised — if
anything the multi-product evidence makes the case stronger (0.9152 > 0.8814).
What is revised is Pass 1A's characterization of ECE as an unqualified "legitimate
standalone Premium metric." That status now needs an explicit qualification:
**ECE is a legitimate, well-behaved standalone metric for ranking products *within
a single product family/format* (its budget-window behavior there is sound, per
§7), but for ranking *across formats within the same set* — the loose-pack vs ETB
vs booster-box comparison a Premium accessibility surface would plausibly want to
support — its product-level differentiation is mathematically indistinguishable
from ranking by raw price-per-effective-pack alone, once the shared set-level
Accessibility term is held constant.** This does not contradict Pass 1A's
set-level finding that Accessibility (`A_raw`) is not redundant with price (§3 of
Pass 1A still stands — that was tested across sets, at the level where Accessibility
varies). It is a new, narrower, and now-established fact about ECE specifically,
established only because this supplement could run the same-set cross-format
test Pass 1A's one-product-per-set design structurally could not.

## 9. Files created

- `docs/research/overall_rip_accessibility_product_cohort.json` — frozen 138-product
  cohort (§1).
- `docs/research/overall_rip_accessibility_pass_1a_product_supplement.json` —
  machine-readable version of every number in this report.
- `docs/research/OVERALL_RIP_ACCESSIBILITY_PASS_1A_PRODUCT_SUPPLEMENT.md` — this
  report.
- Scratch/working files (not deliverables, left for traceability):
  `backend/research/scratch_pass1a_supplement/*.py`, `*.json`.

No production code file was modified. No file under `backend/desirability/`,
`backend/db/migrations/`, or any canonical scoring module was written to. No
billing, market-explorer, or infra/scheduler file was read or modified; `logs/*`
was not touched.

## 10. Start / end HEAD

- Start HEAD: `6001825c8519fcdb5860d9de66826ca6a0356a6c`
- End HEAD: unchanged (no commit was made as part of this pass; see git status
  evidence in the final report to the calling agent).

OVERALL_RIP_ACCESSIBILITY_PASS_1A_PRODUCT_SUPPLEMENT_COMPLETE
