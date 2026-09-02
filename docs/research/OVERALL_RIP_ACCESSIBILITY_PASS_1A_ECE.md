# Overall RIP Accessibility — Pass 1A: Product Chase Efficiency (ECE)

Status: **OVERALL_RIP_ACCESSIBILITY_PASS_1A_COMPLETE**

Research only. No production code, scoring config, or canonical Overall RIP / Chase
Accessibility file was modified. No migration, deploy, publish, backfill, commit, or
branch operation was performed.

## 1. Workspace / authority

- Branch: `fix/public-rankings-entitlement-regression-2`
- Start HEAD: `26bec1c5183164f5d8bde0be9571836183b1f455`
- HEAD at artifact-write time: `8affebfb587a6b8e207dca42b627a168528dc619` — HEAD moved
  during this pass because of the unrelated concurrent billing / market-explorer /
  infra-scheduler workstreams noted in the task brief (see `git log` on this branch:
  billing test/feature commits, plus continuous simulation runs writing
  `logs/run_simulations.log` and `logs/task_scheduler_debug.log`, both showing as
  modified in `git status --short` throughout this pass). None of those files were
  read for content or touched.
- `git status --short` at write time: only `logs/run_simulations.log`,
  `logs/task_scheduler_debug.log` (modified by the concurrent scheduler) and the new
  `backend/research/scratch_pass1a/` scratch directory and the `docs/research/*`
  artifacts this pass created.

**Authority reconstructed from live code + live DB (Supabase project in
`backend/.env`):**

| Authority | Live identity |
|---|---|
| Financial RIP V4 | `financial_rip_v4_outcome_profile_p95_only_25_20_15_25_10_5` (from `financial_rip_v4_version` column; matches `backend/calculations/evr/financial_rip_v4_config.py::FINANCIAL_RIP_V4_VERSION`). Weights 25/20/15/25/10/5 across true_win_frequency, typical_retention, loss_resilience, realistic_upside, jackpot_upside, base_economic_efficiency. |
| Collector Appeal V5 | `collector_appeal_v5_contextual_roster_h_only_d_baseline_up4_down2` (from `collector_appeal_version` column) |
| Overall RIP V10 control | `overall_rip_v10_90_financial_v4_10_collector_appeal_v5` (from `overall_rip_v10_version` column) |
| Chase Accessibility V1 | Formula confirmed in `backend/desirability/chase_accessibility.py` / `backend/db/services/chase_accessibility_service.py`: `HC_i = V_i^2 / sum(V_j^2)`, `A_raw = sum(HC_i * modeled_probability_i)`. **The persistence table `pokemon_set_chase_accessibility_snapshot_latest` (migration 077) does NOT exist on the live Supabase project** — a live `select *` returns PostgREST `PGRST205` ("table not found in schema cache"). See §2 for how this was worked around. |
| Probability authority | `modeled_probability` from `simulation_card_variant_pull_rates`, exclusively. `effective_pull_rate` was pulled for reference only and never treated as a probability. |
| price_used / product market price | `simulation_card_variant_pull_rates.price_used` (per variant) and `simulation_sealed_product_results.product_market_cost` (per product). |
| pack-equivalent authority | `simulation_sealed_product_results.pack_count` (loose_booster_pack is uniformly `1`) and `.random_pack_count` (used by box-format families, out of scope for this pass — see exclusions). |
| calculation_run_id | `simulation_sealed_product_results.calculation_run_id` / `simulation_card_variant_pull_rates.calculation_run_id`, UUIDs, one per simulation run. |
| Supported set cohort | 1,558 `simulation_sealed_product_results` rows across 261 distinct `calculation_run_id`s, 8 product families. `loose_booster_pack` = 239 rows. 63 of those runs (22 distinct `set_id`s) have matching rows in `simulation_card_variant_pull_rates` (22,245 rows total, 64 distinct runs live). |

## 2. Cohort

### Critical finding: Chase Accessibility persistence is not live

`docs/research/CHASE_ACCESSIBILITY_V1_IMPLEMENTATION.md` describes Chase
Accessibility V1 as fully implemented with a live read path. On the current Supabase
project, the table it reads/writes
(`pokemon_set_chase_accessibility_snapshot_latest`, migration 077) is **not present**
in the schema cache. This means the currently-published Accessibility surface (if
any environment has it) could not be queried directly in this pass.

Workaround used (read-only, math-identical): `A_raw` was reconstructed directly
from `simulation_card_variant_pull_rates` (`pull_count > 0` filter — the same filter
`load_drawable_variants()` uses), applying the exact published formula. This is not
a new metric; it reproduces the documented one from its own upstream inputs. It does
mean the persisted/published Accessibility value itself was not independently
cross-checked in this pass.

### Coherence limitation (documented, not manufactured)

No single `calculation_run_id` carries both (a) `simulation_card_variant_pull_rates`
rows and (b) a `simulation_sealed_product_results` row with **both**
`collector_appeal_score` and `overall_rip_v10_score` populated, for the same
product. The live pipeline continuously re-simulates (fresh pull-rate runs land
every few hours per set — consistent with the concurrent infra/scheduler work
noted in project memory), while Collector Appeal / Overall RIP V10 enrichment is a
separate, slower finalization pass that last completed around 2026-08-27 for this
cohort.

For all 22 sets available, pairing the **latest run with pull-rate rows** (Track A,
Accessibility) to the **latest run with full enrichment** (Track B, Financial +
Collector + Overall) gives an offset of 1.0–5.4 days (median 5.40), with
`product_market_cost` differing by under 2% between the two runs for every set —
i.e. materially the same market state despite different `calculation_run_id`s. This
is the same class and similar magnitude of mismatch as the prior
`OVERALL_RIP_ACCESSIBILITY_ARCHITECTURE_CLOSURE` pass (4-day offset, 123/138
products, 20 sets), which reconfirms it is a structural cadence property of the
pipeline rather than a one-off gap. The primary cohort below is built on that
pairing.

### Primary cohort

- 22 sets, `loose_booster_pack` family only (`pack_count == 1` uniformly, so
  `effective_pack_cost == product_market_cost`, avoiding pack-equivalent
  conversions for box formats in this pass).
- Frozen to `docs/research/overall_rip_accessibility_primary_cohort.json`: per set,
  both run IDs and dates, both product-market-cost readings, `A_raw`, chase depth
  (`N_HC`), all 6 Financial RIP V4 components + total, Collector Appeal V5,
  Overall RIP V10, EV/P95/P99, `effective_pack_cost`, `ECE_raw`, and the full
  per-variant `price_used` / `modeled_probability` / `HC_i` arrays used to compute
  `A_raw` — sufficient to reproduce every downstream number without another DB
  query.
- Full authority/exclusions text: `docs/research/overall_rip_accessibility_authority.json`.

### Temporal replication cohort (identified, not analyzed here)

The 2026-08-27 17:00–18:30 UTC batch of `simulation_sealed_product_results` rows
(Track B above, same 22 sets) has its own complete Financial/Collector/Overall
authority and is a usable temporal replication cohort for Pass 1B. It was not
independently re-analyzed for Accessibility because the corresponding pull-rate
rows from that window are no longer queryable — only 64 distinct
`calculation_run_id`s remain live in `simulation_card_variant_pull_rates` against
261 distinct runs in `simulation_sealed_product_results`, meaning older runs' pull
rates appear pruned once a set is re-simulated. Recommendation for Pass 1B: snapshot
pull rates immediately at run completion.

## 3. Redundancy matrix (Accessibility `A_raw`, n=22)

| vs. | Spearman ρ (p) | Pearson r (p) |
|---|---|---|
| Financial RIP V4 total | 0.1146 (0.612) | 0.0494 (0.827) |
| True Win Frequency | 0.1925 (0.391) | 0.2084 (0.352) |
| Typical Retention | -0.2151 (0.336) | -0.2828 (0.202) |
| Loss Resilience | -0.1293 (0.566) | -0.2295 (0.304) |
| Realistic Upside | 0.2468 (0.268) | 0.3074 (0.164) |
| Jackpot Upside | **-0.5867 (0.004)** | **-0.5543 (0.007)** |
| Base Economic Efficiency | 0.0277 (0.903) | -0.0239 (0.916) |
| EV/cost | **-0.4545 (0.034)** | **-0.4943 (0.019)** |
| P95/cost | 0.2468 (0.268) | 0.3313 (0.132) |
| P99/cost | -0.1033 (0.647) | 0.0185 (0.935) |
| Collector Appeal V5 | -0.3755 (0.085) | -0.3981 (0.067) |
| Chase Depth (N_HC) | 0.1508 (0.503) | 0.2959 (0.181) |
| Pack count | undefined (constant = 1 in this cohort) | undefined |
| Product price / effective pack cost | 0.1733 (0.440) | 0.3391 (0.123) |

**Explicit answers:**
1. **Is Accessibility EV in disguise?** No. ρ(A_raw, EV/cost) = -0.45 (p=0.034) —
   moderate and *negative*, the opposite of a duplicate.
2. **P95/P99 in disguise?** No. ρ with P95/cost = 0.25 (n.s.), with P99/cost =
   -0.10 (n.s.). Neither is significant nor strong.
3. **A Financial component duplicate?** No single component reaches significance
   except Jackpot Upside, which is significantly *negatively* correlated
   (-0.59) — Accessibility is highest when Jackpot Upside is lowest, i.e. it
   favors flatter, more evenly-spread value distributions, the conceptual
   opposite of a jackpot-chasing metric.
4. **Collector Appeal in disguise?** No, and trending the wrong way: ρ = -0.38
   (p=0.085, marginal, negative).
5. **Chase Depth in disguise?** No. ρ = 0.15 (n.s.) — weak.
6. **Pack quantity in disguise?** Not testable in this cohort (`pack_count` is
   constant at 1 for every `loose_booster_pack` row), so no variation exists to
   correlate against. Price/cost itself is weak and non-significant (ρ=0.17).

Conclusion: `A_raw` is not a disguised restatement of any of the above — its
strongest relationships are a moderate negative correlation with EV/cost and a
significant negative correlation with Jackpot Upside, both distinct signals.

## 4. ECE correlation matrix + partials

`ECE_raw = A_raw / effective_pack_cost` (`effective_pack_cost = product_market_cost
/ pack_count`, which equals `product_market_cost` for this cohort).

| vs. ECE_raw | Spearman ρ (p) |
|---|---|
| Financial RIP V4 total | 0.3473 (0.113) |
| Overall RIP V10 control | 0.3055 (0.167) |
| EV/cost | -0.0198 (0.930) |
| P95/cost | 0.2005 (0.371) |
| P99/cost | 0.1745 (0.437) |
| Product cost / effective pack cost | **-0.4545 (0.034)** |
| Pack count | undefined (constant) |
| Accessibility (A_raw) | **0.7617 (<0.001)** |
| Collector Appeal V5 | **-0.5494 (0.008)** |
| True Win Frequency | 0.1801 (0.423) |
| Typical Retention | 0.3665 (0.094) |
| Loss Resilience | 0.4037 (0.062) |
| Realistic Upside | 0.2005 (0.371) |
| Jackpot Upside | -0.3235 (0.142) |
| Base Economic Efficiency | 0.4399 (0.041) |

Partial correlations (Spearman-ranked, controlling for `effective_pack_cost`):
- **ρ(Financial, ECE | effective_pack_cost) = 0.1746**
- **ρ(EV/cost, ECE | effective_pack_cost) = -0.3511**

ECE correlates strongly with the Accessibility numerator it is built from (0.76,
mechanical) and moderately-negatively with cost (mechanical, since cost is the
denominator). Once cost is partialed out, ECE's relationship to Financial RIP V4
collapses to weak (0.17), and its relationship to EV/cost actually goes negative
(-0.35) — ECE is not a proxy for either once price is controlled for.

## 5. Price-only placebo

`PriceEfficiency = 1 / effective_pack_cost`.

| Pair | Spearman ρ (p) |
|---|---|
| ECE vs PriceEfficiency | **0.4545 (0.034)** |
| ECE vs Accessibility | 0.7617 (<0.001) |
| PriceEfficiency vs Financial RIP V4 | **0.4602 (0.031)** |
| PriceEfficiency vs Accessibility | -0.1733 (0.440) |

`PriceEfficiency` alone correlates with ECE about as strongly as Accessibility's
own denominator-adjusted signal does with Financial RIP V4 — a first sign the ECE
signal is not distinguishable from a bare price effect at this sample size.

### Candidate Overall scores vs V10 control (n=22, 231 pairs)

Transform: percentile rank 0–100 for `ECE_raw` and `PriceEfficiency` (no natural
0–100 scale exists for either); Financial and Collector Appeal used on their native
0–100 scale.

- `Overall_ECE = 0.84·Financial + 0.06·pctrank(ECE) + 0.10·Collector`
- `Overall_Price = 0.84·Financial + 0.06·pctrank(PriceEfficiency) + 0.10·Collector`

| | vs. V10 control |
|---|---|
| Total reversals, `Overall_ECE` | 21 / 231 |
| Total reversals, `Overall_Price` | 16 / 231 |
| Shared reversals (both candidates flip the same pair) | 9 |

The ECE-weighted candidate reverses *more* pairs relative to V10 than the
price-only candidate does, and 9 of ECE's 21 reversals (43%) are pairs the
price-only candidate reverses identically — consistent with ECE's movement
against V10 being substantially explainable by price alone.

### Controlled pair tests (tolerance = 5%)

- **Test A** — near-equal effective-cost pairs (13 qualifying pairs at n=22):
  ECE ordering followed Accessibility ordering in **13/13** pairs.
- **Test B** — near-equal-Accessibility pairs (10 qualifying pairs):
  ECE ordering followed cheaper effective cost in **10/10** pairs.

Both are expected/near-tautological given `ECE = A_raw / cost` — they confirm ECE
mechanically encodes both signals when the other is held flat, but do not by
themselves establish independent value; see §6 for the test that isolates the
non-mechanical remainder.

## 6. ECE residual test

Rank-regression of `rank(ECE_raw)` on `[rank(Financial), rank(A_raw)]`:

- **R² = 0.6487**
- Spearman(predicted rank, actual rank) = 0.7877
- Residual dispersion (std of rank residuals) = 3.76 (out of a 22-unit rank range)
- Residual correlation with `rank(PriceEfficiency)` = 0.7911

**Key test** — partial correlation between ECE and PriceEfficiency, controlling for
Financial + Accessibility jointly (regress both on `[Financial, Accessibility]`,
correlate the residuals):

**ρ_partial(ECE, PriceEfficiency | Financial, Accessibility) = 0.8814**

The previously lost run reported 0.9264 on a similar (but not identical —
different date offset, 20 vs 22 sets) cohort. This run's 0.8814 confirms the same
finding at the same order of magnitude: roughly 35% of ECE's rank variance is left
unexplained by Financial + Accessibility together (1 - R² = 0.35), and that
unexplained remainder is overwhelmingly (ρ=0.88) just price. Product Chase
Efficiency, as currently defined, is not adding a genuinely new orthogonal signal
beyond price once Financial and Accessibility are accounted for.

## 7. Negative control

`sum(HC_i · V_i · p_i) / effective_pack_cost` — the rejected value-heavy variant,
computed per product from the same per-variant `HC_i`/`V_i`(`price_used`)/`p_i`
(`modeled_probability`) arrays frozen in the primary cohort file.

| vs. | Spearman ρ (p) |
|---|---|
| P99/cost | 0.0796 (0.725) |
| Jackpot Upside | **0.6488 (0.001)** |
| Financial RIP V4 total | **-0.4670 (0.028)** |

As expected for a value-heavy (not depth-diversified) construction, this negative
control correlates strongly and positively with Jackpot Upside (opposite sign from
`A_raw`'s Jackpot Upside correlation in §3) and negatively with Financial RIP V4
overall — consistent with the reason it was rejected in favor of the
value-squared/HC-weighted Accessibility formula. Reported for completeness only;
not promoted regardless of result, per instructions.

## 8. Equal-spend / budget validation

Per product, per budget: `q = floor(budget / product_price)`, `packs = q ·
pack_count`, `O_budget = sum_i(HC_i · (1 - (1-p_i)^packs))`. Compared against ECE's
product ranking.

| Budget | Comparable products | Pairs total | Agree | Disagree |
|---|---|---|---|---|
| $25 | 21 (1 set unaffordable at any qty) | 210 | 191 | 19 |
| $50 | 22 | 231 | 220 | 11 |
| $100 | 22 | 231 | 228 | 3 |
| $200 | 22 | 231 | **231** | **0** |
| $500 | 22 | 231 | 228 | 3 |

Disagreement causes seen in the sampled examples:
- **Low-budget indivisibility** ($25, $50): products with similar ECE but very
  different unit prices land at very different `q` (e.g. `q_A=3` vs `q_B=4`,
  or `q_A=7` vs `q_B=5`), so leftover unspent capital changes `O_budget`'s
  ordering relative to ECE's continuous-quantity assumption.
- **Probability-saturation reappearance at $500**: at very large `q` (e.g.
  `q=76` vs `q=54`), per-variant hit probabilities `1-(1-p)^packs` begin
  saturating toward 1 for the highest-`p` variants, compressing `O_budget`
  differently than the ECE ratio assumes, reintroducing a handful of
  disagreements after they vanished at $200.
- At $200 every comparable pair agrees — the budget window where `q` is large
  enough to smooth over indivisibility but not yet large enough to saturate
  probabilities.

**Conclusions:**
- **(A) Is ECE valid as a Premium full-market efficiency metric?** Yes as a
  continuous-capital idealization — it agrees with discrete-budget-optimal
  ordering in the great majority of pairs at every budget tested (min 87.6%
  agreement at $25, up to 100% at $200), and its disagreements are explained by
  concrete, named mechanisms (indivisibility, saturation) rather than an
  unexplained divergence.
- **(B) When a budget is explicitly selected, should ranking use O_budget
  instead of ECE?** Yes. ECE is a reasonable full-market default, but at any
  specific selected budget, `O_budget` is the more correct ranking because it
  captures indivisibility and saturation effects that ECE's continuous ratio
  cannot; the disagreement counts above (up to 19/210 pairs, 9%, at $25) show
  this is not a negligible difference at low budgets.

## 9. ECE Overall-pillar decision

**Weight = 0.** Reasoning: §6's key test shows ECE's rank variance is explained
0.6487 (R²) by Financial + Accessibility jointly, and the unexplained remainder
correlates at 0.8814 with bare price efficiency — i.e. the large majority of what
ECE would newly contribute to an Overall RIP blend is a price signal already
implicitly present through Financial RIP's own cost-normalized components (EV/cost,
P95/cost, etc. are already inputs to Financial RIP's sub-scores). §5's controlled
pair tests and Overall-score reversal comparison reinforce this: an ECE-weighted
candidate reverses *more* pairs against the V10 control than an equally-weighted
price-only placebo does, and nearly half of ECE's reversals are shared with the
placebo. Product Chase Efficiency remains a legitimate, informative **standalone
product-level metric** (its budget-window behavior in §8 is sound), but it should
not receive a nonzero weight inside Overall RIP.

## 10. Files created

- `docs/research/overall_rip_accessibility_primary_cohort.json` — raw/frozen
  22-set cohort (both run IDs/dates, all Financial V4 components, Collector
  Appeal V5, Overall RIP V10, EV/P95/P99, effective pack cost, ECE_raw, and full
  per-variant `price_used`/`modeled_probability`/`HC_i` arrays).
- `docs/research/overall_rip_accessibility_authority.json` — authority/coherence
  narrative (market dates, calculation runs, version identities, row counts, set
  counts, exclusions, exact coherence limitation).
- `docs/research/overall_rip_accessibility_pass_1a_ece.json` — machine-readable
  version of every number in this report (sections 3–8).
- `docs/research/OVERALL_RIP_ACCESSIBILITY_PASS_1A_ECE.md` — this report.
- Scratch/working files (not part of the deliverable, left for traceability):
  `backend/research/scratch_pass1a/*.py`, `*.json`.

No production code file was modified. No file under `backend/desirability/`,
`backend/db/migrations/`, or any canonical scoring module was written to.

## 11. Start / end HEAD

- Start HEAD: `26bec1c5183164f5d8bde0be9571836183b1f455`
- HEAD at artifact-write time: `8affebfb587a6b8e207dca42b627a168528dc619`
- HEAD moved due to unrelated concurrent commits/log writes on this shared branch
  (billing test/feature commits per `git log`, plus scheduler-driven log file
  updates). No file from those workstreams (billing, market explorer, infra/
  scheduler, `logs/`) was read for content or modified by this pass.

## 12. Concurrent work observed and preserved

- `logs/run_simulations.log`, `logs/task_scheduler_debug.log` — modified
  throughout this pass by the live, continuously-running simulation/task
  scheduler (the same pipeline whose cadence produced the coherence limitation in
  §2). Left untouched.
- Billing commits visible in `git log` on this branch (Stripe Price/Portal work)
  — untouched, not read beyond the initial `git log` used to confirm branch
  state.
- No market-explorer or infra/scheduler source files were opened or edited.
