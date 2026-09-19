# Best-Open Price V2 - Monotonicity Certification (Bucket 1)

Date: 2026-09-19
Branch: `develop` (research only; no production behaviour changed)

## Decision

`PARTIAL_CERTIFIED_SEARCH_SPACE_REDUCTION_SUPPORTED`

- The Best-Open winner predicate is **not monotone** in acquisition price, so an unrestricted binary search is **not certified**.
  Genuine counterexamples exist both synthetically (real scorer, tiny controlled distributions) and in the frozen Sep-14 data.
- Within one fixed physical quantity `q` the predicate **was** down-closed in all 6,083 swept intervals for both authorities, and a proof
  (Theorem A) explains why it must be in the half-win region where every one of the 276 real thresholds lives.
- A **conservative branch-and-bound** upper bound is sound (0 false prunes, 0 bound violations, 9,461/9,461 replays reproduce the exact
  highest winning cent) and removes 98.8% of the cent scores the exact engine performs.
- That reduction is worth **at most about 2.9% of the exact engine's wall time**, because physical-`q` construction is 97.1% of it.
  Cent pruning is a real but small win; quantity-level pruning has **no** supporting theorem.

No snapshot was published, no migration ran, no pointer moved, and no Supabase write occurred. `best_open_price_v2_fused.py` is unchanged.

## 1. Provenance

| Item | Value |
|---|---|
| Frozen source | Budget Ranking snapshot `0e65fb6d-ff33-4331-99d5-d6a214ecc712`, market date 2026-09-14 |
| Authority fingerprint | `faad453f7d29eff1831fb2e212a13dad7d9d553536dc283af90c9bfbd53e48b0` (verified before any sweep) |
| Full Market budget | $1,300 (130,000 cents), 138 eligible products |
| Threshold oracle | `docs/research/financial_rip_v5_best_open_v2_control.json` (fused V2 engine, `complete`, 138 rows). Its four Phase-10B rows equal the frozen constants in `run_best_open_price_v2_phase10b.py` (1395/1386, 66243/60974, 407/409, 22417/23053). |
| Scorer | `PreparedCanonicalCandidate.score_candidate` and `.compare` unchanged; physical distributions built with the same `build_single_q_parity_distributions([q])` call the fused engine uses |
| Auditor | `backend/scripts/research_best_open_price_v2_monotonicity.py` (read-only) |
| Regression tests | `backend/tests/unit/calculations/test_best_open_price_v2_monotonicity.py` (24 tests) |
| Machine-readable summary | `docs/research/best_open_price_v2_monotonicity_certification.json` |

The older `BEST_OPEN_PRICE_BUCKET1_PREPARED_SCORER_AND_EXACT_SEARCH.md` (2026-09-13, prepared Financial scoring) is a different report and is untouched.

**Independent verification of the oracle.** The sweeps found the highest winning legal cent for **276/276** thresholds (138 RIP, 138 Financial) equal to the
frozen control, and the number of cents the exact descending search must scan per axis reproduces the control's
`ripComparatorEvaluations` / `financialComparatorEvaluations` for **138/138** products (2,312,118 scans plus one current-market evaluation per axis = the control's
`naiveScoreCount` of 2,312,394). So the audit scope is exactly the engine's own scan domain.

## 2. What "monotone" means here

Ascending price at fixed `q`, the verdict sequence must look like `W* L*` (a win at price `p` implies a win at every lower price). That is what a binary
search for the highest winning cent needs. A single `L` followed (at a higher price) by a `W` is a violation. The auditor reports run patterns such as
`W L W L`, one-cent islands (`L W L`), upward score steps (score rises when price rises), plateaus, and verdict changes at unchanged scores.

## 3. Static analysis (Buckets 1A-1C): what the code proves

Traced from source: `PreparedFinancialRipDistribution.score` -> `build_financial_rip` -> `_prepared_raw_blocks` (`financial_rip_v3.py`),
`project_financial_rip_v4_from_v3_payload` (`financial_rip_v4.py`), `compute_overall_rip_v12` (`weighted_rip.py`),
`PreparedCanonicalCandidate.score_candidate` / `.compare` (`best_open_price.py`), and `_tier_sort_key_v12` / `financial_only_comparator_key`
(`budget_normalized_product_ranking.py`).

**Fixed-q setting.** The outcome multiset `X` (n draws plus a uniform value offset) is fixed. Price `p` (cents) only changes the cost
`C = q * (p / 100.0)` (the exact float expression `score_candidate` uses) and the capital used by the comparator tie-break.

### 3.1 Component monotonicity table (Financial V4, fixed q, cost C rising)

V4 weights: True Win 0.25, Typical Retention 0.20, Loss Resilience 0.15, Realistic Upside 0.25, Jackpot Upside 0.10, Base Economic Efficiency 0.05.
All rounding (raw 6-8 dp, component 4 dp, final 4 dp) is monotone non-decreasing: it can create ties and plateaus but never reverse an order.

| Input | Formula (engine) | Behaviour as C rises | Discontinuities | Clip / rounding | Verdict |
|---|---|---|---|---|---|
| True Win Frequency `P(X>=C)` | `(n - count_below(C)) / n`; knots reach 100 at 0.50 | steps DOWN each time C passes an outcome value | every outcome value (a tie at exactly C still counts as a win) | flat at 100 once P >= 0.5; 8 dp | **non-increasing, stepwise** (0 increases in any real or synthetic sweep) |
| Typical Retention `median(X)/C` | median fixed | strictly decreasing | none | clips at 1.0; 6 dp | **non-increasing** |
| Realistic Upside (V4) `P95/C` | P95 fixed | strictly decreasing | none | clips at 8.0 | **non-increasing** |
| Jackpot Upside `P99/C`, `top1%mean/C` | fixed numerators, saturating-exp transform | strictly decreasing | none | rounds to 100.0000 for huge ratios | **non-increasing** |
| Base Economic Efficiency `mean(X excl. top 1%)/C` | fixed numerator | strictly decreasing | none | clips at 1.0 | **non-increasing** |
| LR `average_retention_given_loss` `E[X/C \| X<C]` | `S_k/(kC)`, `k = count_below(C)` | decreasing between outcomes, **jumps UP** at an outcome crossing (the newly lost value is the largest loser so far: mean rises by `m(v-mean)/((k+m)C)`) | every outcome value | bounded [0,1) | **potentially locally increasing** (shown possible in section 4, observed 619 times in section 5) |
| LR `soft_loss_share_given_loss` `(k-h)/k`, `h = count_below(C/2)` | conditional share | jumps UP at a crossing of C (by `m h/(k(k+m))`), jumps DOWN when C/2 crosses an outcome (a loss becomes hard) | outcomes (at C) and 2x outcomes (at C) | [0,1] | **non-monotone** |
| LR `hard_loss_probability` (disclosed, unweighted) | `h/n` | non-decreasing (0 decreases measured) | 2x outcomes | 8 dp | monotone, no weight |
| LR no-losing-runs transition | `k = 0` gives LR = 100 exactly | drops from 100 once C exceeds the minimum outcome | min outcome | none | downward step only |
| LR component | `0.7*avg + 0.3*soft`, linear 0-100 | union of the above | union | cannot clip | **non-monotone** |
| Financial V4 total | weighted sum, 4 dp | non-increasing wherever LR cannot out-jump the rest (Theorem A) | union | 4 dp | **not monotone in general** |
| Overall V12 | `round(0.86 F + 0.04 A + 0.10 CA, 4)`; A, CA product constants | non-decreasing function of F alone | those of F | 4 dp (adjacent F may collapse) | inherits F |

### 3.2 Theorems

**T1 (gap monotonicity).** If no outcome lies in `[C1, C2)` then `k` is unchanged, the average-retention term decreases, `h` can only grow (soft share cannot rise) and every other
component is non-increasing, so Financial V4 is non-increasing on that cost interval. Exact but weak on dense distributions: 34.2% of adjacent-cent pairs cross an outcome
(978,162 crossing vs 1,878,004 outcome-free pairs), so T1 alone cannot certify long intervals.

**T2 (Theorem A, the half-win region).** If `P(X >= C) <= 1/2` at the lower cost, the real-valued Financial V4 score at the next cost is strictly lower.
At a crossing of `m` outcomes with `k` prior losers the True Win term falls by at least `0.25 * (100/0.15) * m/n = 33.3 m/n` points (its slope is at least 133.3 per unit probability
below 0.5) while Loss Resilience gains at most `0.15*100*(0.7 + 0.3) * m/(k+m) = 15 m/(k+m)`. `P <= 1/2` gives `k + m >= n/2`, so the gain is at most `30 m/n < 33.3 m/n`.
Every other component only falls, and the `k = 0 -> k > 0` crossing lowers LR from 100. Rounding is monotone; the only rounding risk is the sum of independently rounded components
(about 1e-4), which is below the margin `3.3 m/n` whenever `n <= ~30,000 m`. The exhaustive audit found 0 rises in the region regardless of n.
The theorem cannot be widened: the synthetic fixture with `P(win) = 0.97` rises by 0.5268 points.

**T3 (Overall V12 predicate).** V12 is a monotone function of F. The comparator is lexicographic
`(Overall desc, Financial desc, chanceToRecover desc, |capital - target| asc, id)`. The winning set is therefore `{F >= tau'}` **except on the exact tie band**
`{Overall == benchmark Overall and Financial == benchmark Financial}`, where lower keys decide. `chanceToRecover` is non-increasing in price but `|capital - target|` **decreases**
with price (committed capital `q*p/100` rises toward the budget), so on a full headline tie a HIGHER price wins where a lower price loses. A tie band needs a score plateau.

**T4 (Financial predicate).** The comparator is `(-F, id)` and `id` is price-independent, so the predicate is exactly `F(p) >= tau` (or `> tau`); it is monotone iff F has no rebound across `tau`.

**T5 (bound soundness).** For cents `[a, b]` at fixed q the five non-LR component scores at `a` bound every cent in the interval, and Loss Resilience is bounded by the left end of every
outcome gap inside the interval (within a gap LR falls), computed in one vectorised pass plus a 1e-3-point slack. Rounding, the weighted sum, the 0-100 clamp,
`compute_overall_rip_v12` and both comparators are monotone in the score, so an upper-bound score that loses proves every cent in the interval loses. Overall pruning uses only strict inequality on
the first two lexicographic keys and never prunes ties.

### 3.3 Winner predicate versus score (1C)

- Financial: the predicate is a pure threshold on F, so a score rebound across `tau` is exactly a predicate rebound.
- Overall V12: a threshold on F plus the capital-closeness tie-break on the tie band. A higher price can win where a lower price with an identical headline does not; the reverse cannot happen at fixed q.
- Across `q -> q+1` the whole distribution is replaced. `build_single_q_parity_distributions` starts each q at the same seed and groups the same flat stream into q-sized rows, so the distributions are
  correlated but not nested or ordered. Nothing above implies any ordering of scores across q.

## 4. Synthetic evidence (1D)

Real scorer, real comparators; only the outcome vectors are synthetic. All numbers are asserted in `test_best_open_price_v2_monotonicity.py`.
`REBOUND` = 100 outcomes {1,2,3,4 once each, 10 x95, 12 x1}, q=1. `PLATEAU` = 100 outcomes all 10.0, q=1. Target budget 100.

| Pattern | Fixture and result (exact) | Found |
|---|---|---|
| Score increases with price | REBOUND 200->201: F 85.8908 -> 86.1992; 300->301: 80.489 -> 82.9319; 400->401: 78.676 -> 79.2028 (V12 76.5075 -> 76.9606; LR 55.0 -> 58.6409; P(win) 0.97 -> 0.96; avg retention 0.5 -> 0.6234414) | yes |
| Outcome-value crossing | A tie at exactly C is a win (P(win) 0.97 at C=4.00, 0.96 at 4.01); soft share 0.666667 -> 0.5; C/2 crossing at 2.01 turns soft share 1.0 -> 0.5 and hard loss 0 -> 0.01; no-losing-runs boundary LR 100.0 -> 99.3069 (downward only) | yes |
| WIN-WIN-LOSS-LOSS (control) | REBOUND, benchmark F 76.0, cents 401-519: `W L` | yes (monotone control) |
| WIN-LOSS-WIN rebound | benchmark F 82.7, cents 250-305: `W L W` | yes |
| WIN-LOSS-WIN-LOSS | benchmark F 82.9319, cents 250-400: `W L W L` | yes |
| One-cent winning island (Financial) | benchmark F 82.9319, cents 260-400: winners == [301] (300 scores 80.489, 302 scores 82.8752): `L W L` | yes |
| Tie-break driven higher-price win (V12) | PLATEAU cents 1-3 share the identical headline (F 100.0, V12 94.8462, P(win) 1.0); benchmark capital 0.025: V12 verdicts `[L, L, W, L]`, Financial `[W, W, W, L]` | yes |
| Financial monotone but V12 not | same PLATEAU: Financial `W L`, V12 `L W L` (one-cent island at 3) | yes |
| V12 monotone but Financial not | REBOUND cents 260-400: Financial `L W L`, V12 (low benchmark) `W` | yes (benchmark-dependent) |
| Verdict changes while every score is unchanged | PLATEAU: `winnerChangesWithUnchangedScore == 1` at the 2 -> 3 step | yes |
| Score rise that does NOT flip the predicate | REBOUND benchmark F 70.0: `W` despite the rise | yes (caution: a rise is necessary, not sufficient) |
| Quantity-boundary reversal | budget 1000: q=3 cents 251-333 all lose, q=2 cents 334-500 all win: `L W` at 333 -> 334 | yes |
| Theorem A region | 12 random distributions, 900 cents each: 0 rises where P(win) <= 0.5; rises exist outside the region | confirmed |
| Bound soundness / branch and bound | 8 random distributions x 12 random intervals: bound >= exact F and V12 every time; B&B equals the exhaustive top with 0 false prunes on both authorities | confirmed |

Nothing in the requested pattern list failed to reproduce with the real scorer. The q-level `L W L W` fixture is a *construction* (independent distributions per q), not a discovery, and is labelled as such in the test.

## 5. Real-data evidence (1E): frozen Sep-14 authority

Scope: **138 products, 6,083 fixed-q intervals, 2,862,249 integer cents scored** (each physical distribution prepared once per q; each cent scored by the canonical
scorer and both canonical comparators). Per product the sweep covers every q the exact search touches (leaders from q=1, non-leaders from the current q) through
`q* + 1`, deduped across the two authorities; the four Phase-10B products (`c29f8489`, `dbfd9f2d`, `9f17422e`, `2c4b1825`) plus a 10-product evenly spaced sample (13 distinct products in total) additionally get
a q window of `q* + 25` (up to 400 quantities). Raw cent-by-cent dumps stay in gitignored `logs/`.

| Measure | Financial V4 | Overall V12 |
|---|---|---|
| Thresholds reproduced | 138/138 | 138/138 |
| Upward score steps (all swept cents) | 2,382 | 2,373 |
| ... inside a q interval (score rebounds) | 619 | 610 |
| ... at a q -> q+1 boundary | 1,763 | 1,763 |
| Products with an upward step | 112 | 112 |
| Loss-to-win transitions (breaks `W* L*`), inside a q interval | **0** | **0** |
| Loss-to-win transitions at a q boundary | 7 (7 products) | 15 (15 products) |
| Products with separated winning ranges | 7 | 15 |
| One-cent winning islands | 1 (`e6b942ff` at 2281 cents, q=56) | 0 |
| Verdict changes at unchanged scores | 0 | 0 |
| Adjacent equal-score plateau pairs (all swept / legal domain) | 656,074 / 87,709 | 704,587 / 91,246 |
| Score equals benchmark score band | 1 interval, 1 cent (`4e9d90e0`, q=12) | 0 |

- **Within a fixed q the predicate was always down-closed**, despite 619 score rebounds (all Loss Resilience up-jumps that out-run the rest, all at `P(win) > 0.5`, none flipping a verdict).
  In the legal search domain the counts are identical.
- **Every one of the 22 separated-range cases sits on the bottom edge of the threshold's own quantity interval** (boundary q == threshold q in 22/22): the lowest cent of `q*` wins while the top cent of `q*+1` (one cent cheaper) loses.
  Example: `1072db0c` Financial threshold 18,581 cents at q=6; 18,572 (q=6) wins, 18,571 (q=7) loses, pattern `W L W L`.
  Example: `dbfd9f2d` Overall threshold 66,243 at q=1; 65,001 (q=1) wins, 65,000 (q=2) loses. Financial for the same product is `W L`.
  Example: `e6b942ff` Financial threshold **is** the one-cent island: 2,281 (q=56, F 48.5774 vs benchmark 48.5557) wins while 2,280 (q=57) and 2,282 (q=56, F 48.5367) lose.
  This affects 20 distinct products (14.5%) and 22/276 threshold axes (8.0%). A binary search over price that assumes everything below a winning price wins would mis-locate these.
- Theorem A region: **2,757,011** cents (96.3%) have `P(win) <= 0.5`; **0** upward steps there. **105,238** cents are outside it and hold all **619** rebounds.
  All 276 thresholds have `P(win) <= 0.2232` (median 0.0646), far inside the region.
- Score-rebound rate is tiny: 619 of 2,862,249 cents (0.02%), yet they exist, so monotonicity cannot be assumed.
- Reproducing cases for every anomaly (product, axis, threshold, boundary prices and quantities, benchmark values) are in `reproducingRealCases` of the JSON summary.

### Quantity-boundary reversals (q -> q+1)

Upward score steps at a boundary: 1,763 in the swept set (1,466 in the legal domain). Boundary loss-to-win transitions: 7 Financial, 15 Overall (identical inside and outside the legal domain).
A `q` change replaces the distribution, so these are unconstrained by fixed-q theory and unavoidable.

## 6. Certified monotone subregions (1F)

Discontinuity points partition the price domain: outcome crossings of `C` (LR up-jumps), crossings of `C/2` (LR soft-share down-jumps), the minimum outcome (no-losing-runs), and `q` boundaries (distribution swap).

| Class | Definition | Intervals | Exact-engine scans | Notes |
|---|---|---:|---:|---|
| **A** (provably monotone) | fixed q, `P(win)` at the interval's lowest scanned cent `<= 0.5` (Theorem A), and for Overall no exact tie band | 9,458 | 2,301,343 (99.5%) | Financial predicate is `F >= tau`; binary search locates the boundary, then an exact scan of the equal-score band. Requires a rounding guard (section 3.2, T2). |
| **B** (not provable, but prunable) | `P(win) > 0.5` somewhere, yet the bound prunes cents | 3 | 10,775 | Loss Resilience can rebound here; only the bound is sound. |
| **C** (exact enumeration) | neither of the above | 0 | 0 | No interval on this authority needed full enumeration. |

Across q there is no certified region at all: every `q -> q+1` boundary must be treated as a potential reversal.

## 7. Branch-and-bound feasibility (1G)

Bound: score at the interval's lowest price for the five non-LR components, plus a vectorised gap-left-end maximum for Loss Resilience, plus 1e-3 points; prune only when the canonical
comparator (Financial) or the first two strict lexicographic keys (Overall) already lose. Algorithm: score the top cent first (the exact engine does too), then bisect and prune.

Replay against the exhaustive sweeps over exactly the cents the exact descending search scans (per axis and q):

| Measure | Value |
|---|---|
| Replays (axis x q intervals) | 9,461 |
| Highest winning cent equals exhaustive | 9,461 / 9,461 |
| False prunes (a pruned node containing a winning cent) | **0** |
| Bound violations (bound < true Financial score) | **0** |
| Exact-engine scans (per axis, naive) | 2,312,118 |
| Branch-and-bound scores (6,288 bound evaluations + 20,480 leaf scores) | 26,768 |
| Cents pruned | 2,291,638 (99.1%) |
| Score reduction | **98.8%** |

Under-pruning is allowed and happens: an interval that straddles the benchmark keeps subdividing. Small intervals (a handful of cents, where the top cent wins) are not improved.
Financial rows: 1,150,888 scans; Overall rows: 1,161,230 scans.

## 8. The q-level question (1H)

If the candidate fails at `q1` and wins at a later `q2`, does that imply anything about `q` between? **No theorem holds.**
The distributions come from one seed stream regrouped per q, with no ordering between q values, and no fixed-q result crosses a boundary.
Evidence: the exact search's own outcome shows every `q < q*` loses at every cent (threshold reproduced 276/276), and in the 47 axes (34 products) whose swept range runs at least 4 quantities
past the first winnable q (the 13 extended-window products plus products whose two authority thresholds differ by 4+ quantities) **no hole appeared** after the first winnable q. That is an observation, not a licence to skip quantities:
skipping a q would require knowing its distribution, which is the expensive part. The synthetic `L W L W` fixture (independent distributions per q) shows nothing prevents holes.

## 9. Opportunity-size estimate

| Quantity | Value |
|---|---|
| Cent scores the exact engine performs (per axis, naive) | 2,312,118 (fused unique: 1,167,908) |
| Binary-searchable (Class A) | 2,301,343 scans, 9,458 intervals (99.5%), conditional on the rounding guard |
| Prunable with a sound bound | 2,291,638 cents; 26,768 scores remain |
| Must remain exact (leaf scores after pruning) | 20,480 cent scores, plus 6,288 bound evaluations |
| Cent scoring + comparator time in the frozen control | 109.1 s |
| Physical-q construction time in the frozen control | 3,616.7 s (5,383 constructions) |
| Cent scoring share of runtime | **2.93%** |
| Best-case wall-time saving from cent pruning | **about 2.9%**, less the vectorised bound cost |

Cent pruning cannot remove a physical-q construction, and none of the certificates above bounds a distribution that has not been built. Do not read 98.8% fewer cent scores as a 98.8% speed-up.

## 10. Recommended Bucket 2 direction

1. Do **not** ship an unrestricted binary search: 20 of 138 products (22 of 276 axes) have separated winning ranges at a q boundary, including a real one-cent island at a threshold.
2. If cents ever matter, use the **branch-and-bound** layer (sound with no monotonicity assumption; 0 false prunes; 9,461 replays) as an optional filter inside a fixed-q interval, keeping the
   top-cent probe and the exact scan fallback. Treat Theorem A as an explanation, not a dependency.
3. The runtime prize is in **physical-q construction** (97.1%). Any Bucket 2 engine work should target construction or a distribution-free interval bound across q, which this bucket found no support for.

## 11. Limitations (what was not proven)

- One frozen snapshot (Sep-14) and one benchmark structure; other dates were not swept.
- The sweep covers every q the exact search touches plus `q*+1`; only 13 products got a wider window (34 products have a swept range at least 4 quantities past an axis's first winnable q), so q-level claims past `q*+1` are empirical and limited to those.
- Theorem A is a real-valued proof; the rounded-score guarantee relies on a margin argument plus 2,757,011 clean audited cents. The bound (T5) is analytic and verified on 9,461 replays, not machine-checked.
- Class A means "monotone under Theorem A and no Overall tie band", assessed at the interval's lowest scanned cent.
- The B&B replay counts per-axis scores; the fused engine shares scores between axes, so its absolute savings would be smaller than the per-axis count in the naive case.
- Two leader axes exist in the cohort (`c29f8489` on both); leader behaviour is thinly sampled.

## 12. Reproduce

```powershell
$env:PYTHONPATH = "D:\EVRCalculator"
py -3.11 -m backend.scripts.research_best_open_price_v2_monotonicity --checkpoint logs/mono_raw_0.jsonl --output logs/mono_raw_0.json   # full run; --product X restricts, repeat over chunks for parallelism
py -3.11 -m backend.scripts.research_best_open_price_v2_monotonicity --summarize logs/mono_raw_*.jsonl
py -3.11 -m pytest backend/tests/unit/calculations/test_best_open_price_v2_monotonicity.py -q
```

The full run scored 2,862,249 cents across 138 products in about 50 minutes on six parallel processes (dominated by physical-q construction).
