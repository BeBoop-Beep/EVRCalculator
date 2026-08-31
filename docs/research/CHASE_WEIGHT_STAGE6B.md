# Stage VI-B — Chase Weight Closure and Formula Equivalence Audit

## 1. Executive decision

### `CHASE_WEIGHT_84_10_06_VALIDATED`

$$
\textbf{Overall RIP} = 0.84\,(\text{Financial RIP V4}) + 0.10\,(\text{Collector Appeal V5}) + 0.06\,(\text{Chase Opportunity})
$$

$$
\textbf{Chase Opportunity} = \frac{100K}{K+10} \qquad \textbf{NO CLAMP}
$$

Candidate A was **recomputed directly** from its own formula and passed all five
pre-registered Stage VI-A criteria on CONTROL, on all 12 shocks and on all 7
full-cohort dates. No result below is inferred from Candidate B.

> **`0.87 / 0.10 / 0.03` with the old 200-scale transform has equivalent Chase
> contribution strength but is NOT an equivalent Overall RIP formula, and is NOT
> the selected production specification.**

The user's diagnosis was correct on both counts: the wording was imprecise, *and*
every Stage VI-A behavioral table had in fact been generated from the wrong
weighting system. The recommendation survives, but it had not been earned until
now.

---

## 2. Scope

Closure only. Financial RIP V4, Collector Appeal V5, chase-floor construction,
Core chase definitions, K, and the transform family are all untouched. No new
transform, no percentile normalization, no clamp, no weights outside the Stage
VI-A neighbourhood, no frontend, no production change, no commits, no
stash/reset/clean.

---

## 3. Reconstructed Stage VI-A methodology

Read from the artifacts and the code, not from prose.

| | |
|---|---|
| Cohort | **131 products**, **21 sets**, 8 families |
| CONTROL | `compute_overall_rip_v10(financial_rip_v4_score, collector_appeal_v5_score)` — `overall_rip_v10_90_financial_v4_10_collector_appeal_v5`, 0.90 F + 0.10 C, appeal projected set→product |
| Dates tested | 2026-08-16 (n=54), 08-17 (n=130), 08-22, 08-24, 08-25, 08-26, 08-27, 08-28 (n=131) |
| Shocks tested | card ±2/5/10/20%, product ±2/5/10/20% (headline table uses ±5/10/20%) |
| Weights tested | Chase 0, 1, 2, 3, 4, 5, 6, 7.5, 10% with Collector fixed at 10% |

**Exact definitions, transcribed unchanged:**

- **CLOSE Financial profile** — pairwise `|F_a − F_b| ≤ 2.0` (`pairs.CLOSE_MAX`).
- **CLEARLY SUPERIOR Financial profile** — pairwise `|F_a − F_b| ≥ 10.0`
  (`pairs.CLEAR_MIN`). Bands: `≤2, 2-5, 5-10, 10-15, 15-20, >20`.
- **Override/reversal** — CONTROL ranks *a* above *b*, the candidate ranks *b*
  above *a*, with a 1e-9 tie tolerance. A **clear** override additionally
  requires that Financial and CONTROL already **agree** on the ordering, so a
  pair Collector had already inverted is not counted against Chase.
- **Same-set winner** — `argmax` of the score among products sharing a set; a
  change is counted when CONTROL's winner and the candidate's winner differ.
- **Shock** — Core K recomputed from `chase_pillar_stage6_scenarios.json`, one
  simulation per set shared across scenarios, pillar scores held fixed.

**The five pre-registered criteria** (from `phase19_finalists`):

| | Threshold |
|---|---|
| **C1** | clear overrides == 0 **and** max overturned gap < 10, on base **and** all ±10% shocks |
| **C2** | close-pair override rate ≥ 0.10 |
| **C3** | Financial variance share > 0.80 **and** Chase < 0.20 |
| **C4** | Spearman ≥ 0.98 vs CONTROL **and** Top-5 turnover ≤ 1 |
| **C5** | same-set pairwise reversals > 0 |

**Generated vs inferred:** every Stage VI-A table was *generated* by
`report_chase_weight_stage6a.py` — except the `100K/(K+10) @ 5%/6%/…`
comparison in the Phase-13 section, which came from a one-off base-cohort
command with **no shocks, no dates and no criteria applied**. That single
inferred row is what the 84/10/6 recommendation rested on.

---

## 4. What the Stage VI-A `0.03` row actually tested

Traced in `backend/scripts/report_chase_weight_stage6a.py`:

```python
line 34:  TRANSFORM = scale.approved_unclamped            # = 200K/(K+10)

def _chase_column(rows, transform=TRANSFORM):
    return [transform(r["coreK"]) for r in rows]

# phase19_finalists, phase16_shocks, phase17_temporal, _scenario_block:
weight_set = {"financial_rip": 0.90 - share,
              "collector_appeal": 0.10,
              "chase": share}

# weights.chase_grid():
"financial_rip": financial - share
```

Financial was **always** auto-assigned `1 − 0.10 − chase`, and the Chase column
was **always** the 200-scale transform. Therefore:

$$
\text{the reported }0.03\text{ row} = 0.87F + 0.10C + 0.03T = \textbf{Candidate B}
$$

**Candidate A was never run through `phase16`, `phase17` or `phase19`.** Every
C1–C5 verdict printed in the Stage VI-A report is a verdict on Candidate B.

---

## 5. Algebraic equivalence audit

With $S=\frac{100K}{K+10}$ and $T=\frac{200K}{K+10}=2S$:

$$
B = 0.87F + 0.10C + 0.03T = 0.87F + 0.10C + 0.06S
$$
$$
A = 0.84F + 0.10C + 0.06S
$$
$$
\boxed{B - A = 0.03F}
$$

Verified programmatically over all 131 products:

| statistic | observed `B − A` |
|---|---|
| min | 0.309402 |
| median | 0.868986 |
| mean | 0.861705 |
| max | 1.712205 |
| sd | 0.254416 |

**Max |observed − 0.03·F| = 9.548 × 10⁻¹⁵** — machine precision.

B flatters **every** product, by 0.31 to 1.71 Overall points, in proportion to
its Financial RIP. "Equivalent" was true of the Chase **term** only.

---

## 6. A vs B ranking comparison

| | |
|---|---|
| Spearman | **0.999915** |
| Kendall tau | **0.996242** |
| Products whose ordinal position changes | **32 / 131** |
| Rank movement | median 0.0, mean 0.24, **max 1** |
| Total pairwise ordering disagreements | **16** |
| Same-set pairwise disagreements | **1** |
| Products participating in a disagreement | 32 |
| **Same-set winners differing** | **0 / 21** |

**Top/bottom sensitivity**

| window | membership changes | ordering identical |
|---|---|---|
| top 10 | 1 | no |
| top 25 | 0 | no |
| bottom 10 | 0 | yes |
| bottom 25 | 0 | no |

**Tier effects** — Stage VI-A did assign RIP tiers via the production leader
curve (`compute_leader_normalized_scores` → `public_leader_rip_tier`), so this is
in scope. **3 products change tier between A and B:**

| product | A → B |
|---|---|
| Mega Evolution Pokémon Center ETB (Exclusive) | B → C |
| Mega Evolution Booster Pack | C → D |
| Prismatic Evolutions Pokémon Center ETB | C → D |

So the distinction is small but **real and publicly visible**: 16 pairwise
inversions, 1 top-10 membership change and 3 tier changes are not nothing.

---

## 7. Candidate A five-gate validation

Recomputed from `0.84F + 0.10C + 0.06·100K/(K+10)`, unclamped.

| gate | threshold | observed | margin | verdict |
|---|---|---|---|---|
| **C1** | clear overrides == 0, max gap < 10, base + all ±10% shocks | clear = **0**; max gap base **7.34**, worst shock **7.06** | **+2.66** | **PASS** |
| **C2** | close-pair override rate ≥ 0.10 | **0.13465** | **+0.0346** | **PASS** |
| **C3** | Financial share > 0.80, Chase < 0.20 | Financial **0.9272**, Chase **0.0805** | **+0.1262** | **PASS** |
| **C4** | Spearman ≥ 0.98, Top-5 turnover ≤ 1 | Spearman **0.9926**, T5 turnover **0** | **+0.0126** | **PASS** |
| **C5** | same-set reversals > 0 | **6** | +6 | **PASS** |

**Flags `YYYYY` → ALL PASS.**

Side by side with what Stage VI-A actually measured:

| gate | A (84/10/6 × S) | B (87/10/3 × T) |
|---|---|---|
| C1 margin | +2.66 | +2.66 |
| C2 | 0.13465 (+0.0346) | 0.12926 (+0.0293) |
| C3 | Fin 0.9272 / Chase 0.0805 | Fin 0.9309 / Chase 0.0710 |
| C4 | 0.9926 / T5 0 | 0.9930 / T5 0 |
| C5 | **6** reversals | 5 reversals |
| Leverage | **1.34×** | 2.59× |

**A passes with margins at least as good as B on C1, C2 and C5**, marginally
tighter on C3/C4, and with less than half B's leverage ratio. The safety margin
that motivated choosing the `0.03` row over `0.05` is fully retained: max gap
**7.34** against a threshold of 10.

---

## 8. Date and shock robustness

Candidate A, recomputed under every scenario:

| scenario | n | Chase share | leverage | close ovr | clear ovr | max gap | Spearman |
|---|---|---|---|---|---|---|---|
| base | 131 | 0.0805 | 1.34 | 0.1409 | **0** | **7.06** | 0.9933 |
| card ±5% | 131 | 0.0825 / 0.0819 | 1.37 | 0.1436 / 0.1427 | **0** | **7.06** | 0.9930 / 0.9933 |
| card ±10% | 131 | 0.0808 / 0.0817 | 1.35 / 1.36 | 0.1472 / 0.1454 | **0** | **7.06** | 0.9932 / 0.9927 |
| card ±20% | 131 | 0.0789 / 0.0837 | 1.32 / 1.40 | 0.1526 / 0.1355 | **0** | **7.06** | 0.9933 / 0.9929 |
| prod ±5% | 131 | 0.0818 / 0.0823 | 1.36 / 1.37 | 0.1427 / 0.1436 | **0** | **7.06** | 0.9933 |
| prod ±10% | 131 | 0.0820 / 0.0796 | 1.37 / 1.33 | 0.1490 / 0.1499 | **0** | **7.06** | 0.9927 / 0.9931 |
| prod ±20% | 131 | 0.0825 / 0.0780 | 1.37 / 1.30 | 0.1382 / 0.1598 | **0** | **7.06** | 0.9930 |
| 2026-08-17 | 130 | 0.0804 | 1.34 | 0.1400 | **0** | **7.06** | 0.9930 |
| 2026-08-22 → 08-28 | 131 | 0.0803–0.0810 | 1.34–1.35 | 0.1409–0.1445 | **0** | **7.06** | 0.9932–0.9933 |
| 2026-08-16 | **54** | 0.0572 | 0.95 | **0.0994** | **0** | 4.43 | 0.9963 |

**Clear overrides are 0 in every one of the 19 conditions. The maximum
overturned Financial gap is flat at 7.06 across all 12 shocks** (margin 2.94)
and across every full-cohort date.

**One honest exception:** on 2026-08-16 the close-pair override rate is
**0.0994**, fractionally below C2's 0.10. That date covers only **54 of 131
products** — Stage VI-A's C2 was defined on the base cohort and never evaluated
per-date, so this is a partial-cohort observation, not a criterion failure. It is
recorded rather than smoothed over. Candidate B shows the identical 0.0994 on
that date, so it is a property of the date, not of the candidate.

---

## 9. Chase score semantic verification

| requirement | result |
|---|---|
| K = 0 → 0 | 0.0000 ✓ |
| K = 1 → ≈ 9.09 | 9.0909 ✓ |
| K = 10 → 50 | 50.0000 ✓ |
| finite K always < 100 | K = 10⁶ → 99.999000 ✓ |
| monotonic increasing | true over K = 0…400 ✓ |
| saturating (shrinking increments) | true ✓ |
| no clamp needed | none applied anywhere ✓ |

**Cohort:** K min 0, max 14, **14 distinct values**; S min 0.0000, max 58.3333,
**14 distinct values**. Distinct S == distinct K.

**The five products the old clamp collapsed are now separately representable:**

| K | old clamped T | new S | product |
|---|---|---|---|
| 14 | 100.00 | **58.3333** | Ascended Heroes Booster Pack |
| 13 | 100.00 | **56.5217** | Ascended Heroes Booster Bundle |
| 13 | 100.00 | 56.5217 | Prismatic Evolutions Booster Bundle |
| 13 | 100.00 | 56.5217 | Prismatic Evolutions Booster Pack |
| 12 | 100.00 | **54.5455** | Prismatic Evolutions Elite Trainer Box |

Three distinct K values above 10 now map to three distinct S values. The three
products at K = 13 remain tied — that is a **legitimate equal-K tie**, not a
clamp-induced one, and the distinction is asserted in the test suite.

---

## 10. Corrections to the Stage VI-A record

Applied to `docs/research/CHASE_WEIGHT_STAGE6A.md` as an explicitly marked
**Stage VI-B clarification**; no historical finding was silently rewritten.

**Corrected:**

> `0.03 × 200K/(K+10)` and `0.06 × 100K/(K+10)` provide equivalent Chase
> contribution strength. However, `87/10/3` and `84/10/6` are **not** equivalent
> Overall RIP formulas, because the Financial coefficient differs by 0.03 and
> therefore `B − A = 0.03F`.

**Also corrected:** the Stage VI-A statement that its C1–C5 verdicts applied to
the recommended candidate. They applied to Candidate B. Candidate A's own
verdicts are those in §7 above.

**Preserved unchanged** (Stage VI-B found no evidence against any of these):

1. Chase's apparent excess leverage was primarily a **dispersion/scaling** issue.
2. `200K/(K+10)` exceeds 100 and should not be used as a 0–100 pillar score.
3. Clamping the old transform destroys top-end differentiation.
4. Collector Appeal contributes ≈ 0 marginal Overall RIP variance; the
   product-level Collector study remains **deferred**.
5. Chase can cause meaningful same-set reorderings — **6** under Candidate A.
6. The narrowed claim stands: Chase changes **0 / 21** same-set winners.

---

## 11. Final locked recommendation

$$
\boxed{\;\text{Overall RIP} = 0.84F_{\text{V4}} + 0.10C_{\text{V5}} + 0.06\left(\frac{100K}{K+10}\right)\;}
$$

**NO CLAMP.** Expected effective Chase contribution **8.05%** of Overall RIP
variance (Shapley), leverage **1.34×** nominal. Behavioural role: **tertiary
modifier** — settles ~13.5% of near-tied pairs, overturns **0%** of pairs where
Financial leads by ≥ 10, under every tested shock and date.

Research recommendation only. **Not implemented.** Production Overall RIP V10
(90/10) remains the default.

---

## 12. Workspace state

| | Stage VI-A baseline | Stage VI-B start | Deviation |
|---|---|---|---|
| Branch | `fix/public-rankings-entitlement-regression` | same | none |
| HEAD | `7b7f9974` | **`389a61b3`** | **+1 commit** by an external process |
| Stage VI-A untracked deliverables | 10 files | **0** | **committed in `389a61b3`** |
| Unrelated modified | 4 files | 11 entries | different set; all external |

All 11 Stage VI-A/VI artifacts verified present and byte-identical to HEAD
(`git diff --stat` empty). The external commit `389a61b3` ("updates") absorbed
the ten Stage VI-A deliverables. **I created no commits and modified no
unrelated file.** Current unrelated changes — six deleted
`frontend/.perf-audit/.../received/*.png`, `RipStatisticsPageClient.jsx`, two
frontend contract tests and two logs — are all external and were left untouched.

**Files created by Stage VI-B:**

| Path | Classification |
|---|---|
| `backend/research/chase_weight_stage6a/closure.py` | required deliverable |
| `backend/scripts/report_chase_weight_stage6b.py` | required deliverable |
| `backend/tests/unit/research/test_chase_weight_stage6b.py` | required deliverable |
| `docs/research/CHASE_WEIGHT_STAGE6B.md` | required deliverable |
| `docs/research/chase_weight_stage6b_analysis.txt` | generated / reproducible |
| `docs/research/CHASE_WEIGHT_STAGE6A.md` | **modified** — §10 correction |

---

## 13. Test results

```
python -m pytest backend/tests/unit/research/test_chase_weight_stage6b.py -q
  31 passed

python -m pytest backend/tests/unit/research/test_product_chase_economics.py \
                 backend/tests/unit/research/test_product_chase_economics_validation.py \
                 backend/tests/unit/research/test_chase_pillar_stage6.py \
                 backend/tests/unit/research/test_chase_weight_stage6a.py \
                 backend/tests/unit/research/test_chase_weight_stage6b.py -q
  158 passed

python -m pytest backend/tests/unit/desirability/test_scoring_config_canonical_selection.py \
                 backend/tests/unit/calculations/test_sealed_product_canonical_version_alignment.py -q
  6 passed
```

**164 tests, 0 failures, 0 skips.** The Stage VI-B suite includes an end-to-end
test that runs Candidate A through all five gates against the real cohort and
the four ±10% shocks, and a test asserting `B − A = 0.03F` to machine precision
on real data.
