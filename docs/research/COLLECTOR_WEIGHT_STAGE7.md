# Stage VII — Collector Appeal Weight Re-Stress Test

## Decision

### `COLLECTOR_WEIGHT_11_VALIDATED__PRODUCT_LEVEL_SIGNAL_STRUCTURALLY_ABSENT`

$$
\textbf{Overall RIP} = 0.83\,F_{\text{V4}} + 0.11\,C_{\text{V5}} + 0.06\left(\frac{100K}{K+10}\right)
$$

Chase unchanged at 0.06, unclamped. Collector's extra point funded entirely from
Financial. Research recommendation only — **not implemented, no production change,
no Collector Appeal V6.**

**Preregistration:** `docs/research/COLLECTOR_WEIGHT_STAGE7_PREREGISTRATION.json`
· `sha256 73190a86ab0a4c9d21dc3414d1f7b457d67561592ce141014a5248e713745274`
· locked before any candidate outcome existed; never edited.

---

## 1. Historical finding — the recollection is not supported

**The ~13% recollection has no documentary basis as a validated weight.** It has
exactly one origin, and it is not a study result:

```python
# backend/desirability/scoring_config.py
OVERALL_RIP_COLLECTOR_APPEAL_SENSITIVITY_WEIGHTS: tuple = (
    0.00, 0.05, 0.075, 0.10, 0.13, 0.14, 0.15, 0.20,
)
# "...so 0.13 has a declared home as a research candidate rather than
#  drifting toward production by sitting in the same dict as the shipping weight."
```

0.13 is a **declared slot in a research sensitivity grid**, placed there so it
could not drift into production. Nothing reads it on a canonical path. No study
ever evaluated it.

**The documented evidence runs the other way.**
`collector_appeal_v4_h_only_final_validation.md` tested 10%, 7.5% and 5% over 10
snapshots (~6 distinct financial states) and found:

| | 10% (canonical) | 7.5% | 5% |
|---|---|---|---|
| pass rate | 6/10 | 6/10 | 6/10 |
| Spearman guardrail breached | **yes (2 states)** | no | no |
| ≥5-share breached | **yes (1 state)** | no | no |
| top-5 breached | yes (2 states) | yes (2 states) | yes (2 states) |
| worst ρ margin | **−0.0155** | **+0.000311** | +0.0184 |

Its verdict: 7.5% "is the **largest** tested weight that clears the Spearman and
≥5-share guardrails on **every** compatible date", proposed as Overall RIP V8
(`0.925 / 0.075`), and gated on re-measuring the replay once ~20 further distinct
Financial states exist.

### Answering the historical questions directly

- **Why was Collector originally placed at 10%?** Not because higher was
  rejected — because 10% was the *conservative cutover* weight already shipping,
  and the study that examined it recommended **reducing** it. The reduction was
  never adopted because its own margin at 7.5% was +0.000311, which the study
  called "the honest weakness" and gated on more data.
- **Exact study / weights / formula / cohort:** `collector_appeal_v4_h_only_final_validation.md`;
  weights 10/7.5/5%; formula `collector_appeal_v4_h_only_centred_asymmetric_modifier_v1`
  (`CA = clamp(100·D + m)`, m ∈ [−2, +4]); Financial RIP **V3/V2** (5 snapshots
  excluded as `financial_rip_v2_60_25_15`); ~21-set cohort; dates 08-04 → 08-13.
- **Guardrails:** `OVERALL_RIP_PRODUCTION_GUARDRAILS`, read not restated.
- **Was 13% supported?** **No.** It was never tested, under any formula, on any cohort.

Because that work used Collector V4-candidate, Financial V3/V2, a set-level
cohort and a Financial-only baseline, **none of it transfers**. Stage VII
reproduces rather than inherits.

---

## 2. CONTROL reproduction

| | |
|---|---|
| Cohort | 131 products / 21 sets / 8 families |
| V10 inputs re-derived via `compute_overall_rip_v10` | **0 / 131 mismatches**, worst \|Δ\| 0.00e+00 |
| Stage VI-B `84/10/6` reproduced independently | worst \|Δ\| **0.00e+00** |

Gate passed; the study proceeds.

---

## 3. Collector signal diagnosis

| series | min | P25 | med | P75 | max | **sd** | IQR | **distinct** |
|---|---|---|---|---|---|---|---|---|
| Financial RIP V4 | 10.31 | 21.63 | 28.97 | 34.17 | 57.07 | **8.48** | 12.54 | **131** |
| Collector Appeal V5 | 49.07 | 71.93 | 80.82 | 88.25 | 99.09 | **10.91** | 16.32 | **21** |
| Chase 100K/(K+10) | 0.00 | 9.09 | 28.57 | 33.33 | 58.33 | **14.56** | 24.24 | **14** |

**Collector is not compressed.** Its sd is 1.29× Financial's — the *widest*
spread relative to weight of any pillar. It has 21 distinct values across 131
products: exactly one per set.

### Why Stage VI-A found ≈ zero variance contribution

Four candidate explanations; the data selects one.

| | weighted dispersion `w·SD` |
|---|---|
| Financial (w 0.84) | **7.1237** |
| Collector (w 0.10) | 1.0912 |
| Chase (w 0.06) | 0.8734 |

| pair | Pearson | Spearman |
|---|---|---|
| **F vs C** | **−0.2025** | **−0.1254** |
| F vs K | +0.4940 | +0.5169 |
| C vs K | +0.3391 | +0.3133 |

Covariance-aware contribution at 84/10/6: Financial **+0.9272**, Collector
**−0.0011**, Chase **+0.0738** (sum 1.000000).

**It is covariance, not compression and not redundancy.** Collector's own
weighted variance is real, but it is *negatively* correlated with the dominant
Financial term, so its positive own-variance and its negative covariance with the
total very nearly cancel. Collectible sets are, if anything, slightly worse
financial value — so Collector pulls against Financial rather than echoing it.

Not redundancy: reconstructing Collector from Financial + Chase gives R² 0.2961,
**cvR² 0.1477**, residual **83.9%** of its own sd. Partial correlation with
Financial controlling for Chase is **−0.4524** — strongly negative, i.e.
complementary.

Not duplication either: the set-balanced scheme (each set weighted 1/n) barely
moves it, −0.0011 → **−0.0058**.

Leave-one-out (identical under coefficient deletion and budget reallocation):
ρ vs CONTROL is 0.9868 without Collector, 0.9930 without Chase, **0.3521**
without Financial.

---

## 4. Product versus set behaviour — the architectural finding

**Collector Appeal V5 is exactly constant within every set: 0 of 21
multi-product sets show any within-set variation.**

For comparison: Financial RIP V4 is genuinely product-specific; Chase varies in
20 of 21 sets.

> **Collector Appeal cannot directly change the ordering of products within a
> set at any fixed Financial/Chase weighting ratio.** Every same-set product
> carries the identical set score, so the Collector term cancels exactly in a
> same-set comparison. Any within-set movement observed when Collector weight is
> raised is reallocation, not Collector differentiation.

Pair census over 8,515 pairs:

| | count | share | C differs |
|---|---|---|---|
| same-set | 377 | 4.4% | **0** |
| cross-set | 8,138 | 95.6% | **8,138** |
| same-family cross-set | 1,260 | — | — |

Collector carries information on **95.6%** of pairs and is structurally silent on
the other 4.4%. **Its entire contribution is between sets.** This is the accurate
description of the construct, not a failure — but it is a permanent architectural
limit and it is why the decision carries the `PRODUCT_LEVEL_SIGNAL_STRUCTURALLY_ABSENT`
qualifier.

---

## 5. Inherited guardrails

Baseline = `0.94F + 0.06K` (the three-pillar analogue of the historical
Financial-only baseline). Thresholds read from `OVERALL_RIP_PRODUCTION_GUARDRAILS`.

| F/C/K | Spearman | top-5 | top-7 | top-10 | RBO | mean mv | share≥5 | max mv |
|---|---|---|---|---|---|---|---|---|
| 94/0/6 *(diag)* | 1.0000 | 1.00 | 1.00 | 1.00 | 1.0000 | 0.000 | 0.0000 | 0 |
| 86.5/7.5/6 *(diag)* | 0.9917 | 0.80 | 0.86 | 0.90 | 0.9373 | 3.527 | 0.2824 | 19 |
| **84/10/6** | 0.9859 | 0.80 | 0.86 | 0.80 | 0.9311 | 4.611 | 0.4198 | 23 |
| **83/11/6** | 0.9839 | 0.80 | 0.71 | 0.80 | 0.8971 | 5.099 | 0.4733 | 23 |
| **82/12/6** | 0.9815 | 0.80 | 0.71 | 0.80 | 0.8950 | 5.527 | 0.5115 | 24 |
| **81/13/6** | 0.9787 | 0.80 | 0.71 | 0.80 | 0.8913 | 5.924 | 0.5496 | 28 |
| 79/15/6 *(diag)* | 0.9688 | **0.60** | 0.57 | 0.80 | 0.7928 | 7.206 | 0.6031 | 33 |

**The two movement gates are not scale-free**, and that is why they "fail" even
at the shipping 10% weight. They are absolute rank counts calibrated on the V4
study's ~21-set cohort; this cohort is 131 products. *5 ranks of 21* is a quarter
of the field; *5 ranks of 131* is under 4% of it.

Cohort-normalised (mean-move budget 1.5/21 = **0.0714** of cohort; step scaled
5 → 31 ranks):

| F/C/K | mean mv / cohort | share ≥ 31 ranks | scaled gates |
|---|---|---|---|
| 84/10/6 | 0.0352 | 0.0000 | **pass** |
| 83/11/6 | 0.0389 | 0.0000 | **pass** |
| 82/12/6 | 0.0422 | 0.0000 | **pass** |
| 81/13/6 | 0.0452 | 0.0000 | **pass** |
| 79/15/6 *(diag)* | 0.0550 | 0.0229 | pass |

### Guardrail classification

| Guardrail | Class | Reason |
|---|---|---|
| `min_spearman_vs_financial_only` | **inherited hard gate** | Same question; only the baseline changes. All candidates ≥ 0.9787. |
| `max_mean_absolute_rank_movement` | **inherited hard gate, cohort-normalised** | Meaning unchanged, threshold is not scale-free; gated on the 0.0714-of-cohort budget. |
| `max_share_moving_5_plus_ranks` | **inherited hard gate, cohort-normalised** | Same; "5 ranks" rescaled to 31. |
| `min_top5_overlap` | **inherited diagnostic only** | The V4 study itself found the top-5 failures **weight-invariant** (identical at 10%, 7.5% and 5%), driven by one set — Shrouded Fable, D = 51.07 — and recommended RBO or top-7 instead. Reported, not gated. Not silently discarded. |

---

## 6. Weight sweep — what each extra point actually buys

### Reversals, attributed by cause

A reversal counts as Collector-caused **only** when the direct term `δ·dC`
exceeds the reallocation term `−δ·dF` in magnitude.

| step | reversals | **Collector-caused** | realloc-dominant | same-set | cross-set | max F gap crossed |
|---|---|---|---|---|---|---|
| 10 → 11% | 38 | **38** | 0 | **0** | 38 | 6.49 |
| 11 → 12% | 39 | **39** | 0 | **0** | 39 | 6.54 |
| 12 → 13% | 35 | **35** | 0 | **0** | 35 | **9.59** |
| 10 → 13% | 112 | **112** | 0 | **0** | 112 | **9.59** |
| 13 → 14% *(diag)* | 47 | 47 | 0 | 0 | 47 | 9.67 |
| 14 → 15% *(diag)* | 65 | 65 | 0 | 0 | 65 | **12.68** |

**Every reversal is genuinely Collector-driven**, and by a wide margin — the
direct term runs 4–5× the reallocation term:

| winner | beats | F gap | C gap | direct | realloc |
|---|---|---|---|---|---|
| Mega Evolution Booster Bundle | Shrouded Fable PC ETB | 9.59 | 40.01 | **+1.2004** | +0.2876 |
| Mega Evolution ETB [Mega Gardevoir] | Shrouded Fable PC ETB | 8.78 | 40.01 | **+1.2004** | +0.2634 |
| Prismatic Evolutions Booster Pack | Temporal Forces ETB [Iron Leaves ex] | 7.45 | 24.91 | **+0.7472** | +0.2236 |
| Ascended Heroes Booster Pack | Chaos Rising Booster Pack | 7.10 | 33.80 | **+1.0140** | +0.2129 |

Shrouded Fable (D = 51.07, lowest by 19 points) is the recurring loser — the
*same set* the V4 study identified. Continuity of behaviour across two formulas
and two cohorts.

**Same-set reversals are 0 at every step**, exactly as the set-constant structure
requires. Zero movement is credited to Collector that Collector did not cause.

### Marginal movement vs the 84/10/6 CONTROL

| F/C/K | Spearman | Kendall | mean mv | max mv | changed | top-10 | tiers |
|---|---|---|---|---|---|---|---|
| 83/11/6 | 0.9997 | 0.9911 | 0.53 | 3 | 54 | 0 | 6 |
| 82/12/6 | 0.9993 | 0.9819 | 1.08 | 4 | 94 | 0 | 11 |
| 81/13/6 | 0.9986 | 0.9737 | 1.50 | 8 | 103 | 0 | 16 |

Returns are close to linear, not plateauing — the signal is real at every step.

---

## 7. Financial dominance

Baseline `B = 0.94F + 0.06K`; candidate `O_c = (0.94−c)F + cC + 0.06K`.

| F/C/K | close override | **clear overrides** | **max F gap overturned** |
|---|---|---|---|
| 86.5/7.5/6 *(diag)* | 0.1670 | 0 | 7.06 |
| **84/10/6** | 0.2029 | **0** | **7.34** |
| **83/11/6** | 0.2163 | **0** | **7.34** |
| **82/12/6** | 0.2316 | **0** | **7.34** |
| **81/13/6** | 0.2370 | **0** | **9.59** |
| 80/14/6 *(diag)* | 0.2469 | 0 | 9.67 |
| 79/15/6 *(diag)* | 0.2567 | **1** | **12.68** |

No selectable candidate ever overturns a clearly superior Financial profile
(gap ≥ 10). The first breach is at 15%, outside the selectable range.

---

## 8. Chase contract preservation

Each candidate measured against **its own** Chase-free control `(1−c)F + cC` —
the Stage VI-B construction transplanted to that Collector weight, so C1–C5 keep
the meaning they were validated with.

| F/C/K | Shapley C | Shapley K | close ovr | clear ovr | max gap | Spearman | same-set | **C1–C5** |
|---|---|---|---|---|---|---|---|---|
| **84/10/6** | −0.0011 | 0.0738 | 0.1346 | 0 | **7.34** | 0.9926 | 6 | **YYYYY** |
| **83/11/6** | +0.0016 | 0.0754 | 0.1293 | 0 | **7.34** | 0.9927 | 6 | **YYYYY** |
| **82/12/6** | +0.0048 | 0.0770 | 0.1122 | 0 | **7.34** | 0.9930 | 6 | **YYYYY** |
| **81/13/6** | +0.0087 | 0.0786 | 0.1113 | 0 | **9.59** | 0.9930 | 6 | **YYYYY** |

All four preserve the validated tertiary Chase behaviour. **But C1's margin
collapses at 13%**: 10.00 − 7.34 = **2.66** at 10/11/12%, versus 10.00 − 9.59 =
**0.41** at 13%.

---

## 9. Robustness — the deciding evidence

**Dates + price shocks** (worst case over all 12 shocks and all dates):

| F/C/K | clear overrides | max F gap overturned |
|---|---|---|
| 84/10/6 | **0** | 7.06 |
| 83/11/6 | **0** | 7.06 |
| 82/12/6 | **0** | 7.34 |
| 81/13/6 | **0** | 7.34 |

**Collector measurement shocks** (pre-registered, symmetric, ±10%):

| F/C/K | C × 0.90 | **C × 1.10** | margin under C×1.10 |
|---|---|---|---|
| **84/10/6** | 7.34 | **7.34** | **2.66** |
| **83/11/6** | 7.34 | **7.34** | **2.66** |
| 82/12/6 | 7.34 | **9.59** | **0.41** |
| 81/13/6 | 7.34 | **9.67** | **0.33** |

Clear overrides remain 0 everywhere. **This is the discriminator:** a plausible
+10% Collector measurement error collapses the Financial-dominance margin at 12%
and 13% from 2.66 points to under half a point. 11% absorbs the same error with
the margin completely intact.

---

## 10. Why 11%, and not 10, 12 or 13

Applying the pre-registered selection rule in order:

- **Gate 1 — all hard gates.** 10, 11, 12, 13 all pass (Spearman, cohort-normalised
  movement gates, zero clear overrides, C1–C5).
- **Gate 2 — real Collector-specific information.** 10 → 11 buys **38 reversals,
  100% Collector-dominant, 0 reallocation-dominant, 0 same-set**. Not an artifact
  of lowering Financial. **Passes.**
- **Gate 3 — survives dates, shocks, both population schemes.** 11% holds under
  all 12 price shocks, all dates, both Collector shocks, and the set-balanced
  scheme. **Passes.**
- **Gate 4 — comfortable margin.** 11% keeps the full **2.66**-point Financial-
  dominance margin and the full **2.66**-point Chase C1 margin under every
  pre-registered perturbation. **12% and 13% fail this gate** — not on the base
  cohort, but under the pre-registered ±10% Collector shock, where their margins
  fall to 0.41 and 0.33.
- **Gate 5 — lowest sufficient weight.** This is why 11% rather than 12%: the
  rule says take the strongest *justified* candidate, and 12/13% are not
  justified once Gate 4 is applied. It is *not* a reason to stay at 10%, because
  11%'s added information is demonstrably real and costs nothing measurable.

**10% is safe but leaves free information on the table. 12–13% buy more
information at a real cost in safety margin. 11% is the only weight that gains
genuine Collector signal at zero measurable cost.**

### Nominal versus effective hierarchy

| | nominal | effective (covariance share at 83/11/6) |
|---|---|---|
| Financial | 0.83 | ~0.925 |
| Collector | 0.11 | **+0.0016** |
| Chase | 0.06 | ~0.075 |

Nominally `Financial ≫ Collector > Chase` — as intended. Effectively
`Financial ≫ Chase > Collector`, because Collector's negative covariance with
Financial nets its variance share to ~0. **Per the brief, this is not treated as
a hierarchy violation:** it is a covariance artifact, and Collector's behavioural
scope (8,138 cross-set pairs) is far wider than Chase's. Financial remains
dominant; Chase remains a tertiary close-call modifier; Collector governs
cross-set judgement.

---

## 11. Decision table

| F/C/K | Hard gates | Historical | Chase C1–C5 | Clear F ovr | Collector-specific rev | Realloc-only rev | Max F gap | Effective C | Dates | Shocks | Verdict |
|---|---|---|---|---|---|---|---|---|---|---|---|
| **84/10/6** | pass | pass | YYYYY | 0 | — (control) | 0 | 7.34 | −0.0011 | pass | pass | safe, but leaves signal unused |
| **83/11/6** | pass | pass | YYYYY | 0 | **38** | **0** | **7.34** | +0.0016 | pass | **pass (2.66)** | **SELECTED** |
| **82/12/6** | pass | pass | YYYYY | 0 | 77 | 0 | 7.34 | +0.0048 | pass | **fails Gate 4 (0.41)** | rejected on margin |
| **81/13/6** | pass | pass | YYYYY | 0 | 112 | 0 | **9.59** | +0.0087 | pass | **fails Gate 4 (0.33)** | rejected on margin |
| 94/0/6 *(diag)* | pass | — | — | 0 | 0 | 0 | 0.00 | 0 | — | — | ablation reference |
| 89/5/6 *(diag)* | pass | — | — | 0 | — | 0 | 4.88 | — | — | — | below production |
| 86.5/7.5/6 *(diag)* | pass | historical rec. | — | 0 | — | 0 | 7.06 | — | — | — | the V4 provisional |
| 80/14/6 *(diag)* | pass | — | — | 0 | 159 | 0 | 9.67 | — | — | — | above ceiling |
| 79/15/6 *(diag)* | top-5 fails | — | — | **1** | 224 | 0 | **12.68** | — | — | — | **behaviour breaks here** |

---

## 12. The fifteen questions, answered

1. **Why 10% originally?** Conservative cutover; the only study that examined it
   recommended *reducing* to 7.5%, gated on more Financial states.
2. **Was ~13% supported?** **No.** It is a slot in a research sensitivity tuple,
   never tested by any study.
3. **Dispersion today?** sd 10.91, 1.29× Financial. Not compressed.
4. **Why ≈ zero variance contribution?** Negative covariance with Financial
   (Pearson −0.2025) cancels its own variance.
5. **Compression, covariance, redundancy or duplication?** **Covariance.** Not
   compression (sd is widest per unit weight), not redundancy (cvR² 0.148,
   residual 84%), not duplication (set-balanced gives −0.0058).
6. **Does Collector vary within a set?** **No — 0 of 21.**
7. **Can it alter same-set rankings?** **No, structurally impossible.**
8. **Distinct information beyond F and K?** Yes — 83.9% residual sd; partial
   correlation with Financial −0.4524.
9. **What changes 10 → 13?** 112 cross-set reversals, 103 products move, 16 tier
   changes, mean movement 1.50 ranks.
10. **Genuinely Collector-caused?** **100%** — 0 reallocation-dominant, 0 same-set.
11. **Chase contract preserved?** Yes at all four; C1 margin intact at 10/11/12%,
    degraded at 13%.
12. **Ever overturn clearly superior Financial?** No selectable candidate; first
    breach at 15%.
13. **Survives dates and shocks?** 10% and 11% fully; 12% and 13% only until the
    ±10% Collector shock.
14. **More useful at set level?** **Yes, exclusively** — 95.6% of its pairs are
    cross-set; the remaining 4.4% are structurally inaccessible to it.
15. **What weight going forward?** **11%** → `0.83 / 0.11 / 0.06`.

---

## 13. Tests

```
python -m pytest backend/tests/unit/research/test_collector_weight_stage7.py -q
  52 passed

python -m pytest backend/tests/unit/research/test_product_chase_economics.py \
  backend/tests/unit/research/test_product_chase_economics_validation.py \
  backend/tests/unit/research/test_chase_pillar_stage6.py \
  backend/tests/unit/research/test_chase_weight_stage6a.py \
  backend/tests/unit/research/test_chase_weight_stage6b.py \
  backend/tests/unit/research/test_collector_weight_stage7.py -q
  210 passed

python -m pytest backend/tests/unit/desirability/ \
  backend/tests/unit/calculations/test_sealed_product_canonical_version_alignment.py \
  backend/tests/unit/research/test_validation_framework.py -q
  1904 passed, 13 failed
```

**Total: 2,114 passed, 13 failed, 0 skipped.**

The 13 failures are **pre-existing and unrelated**, in
`test_pull_model_live_fallback.py` (6) and `test_public_rip_cohort_integration.py`
(7). Neither file references any Stage V-C/VI/VI-A/VI-B/VII module (grep: 0
matches), and the only modified service in the tree is the external
`billing_service.py`. Stage VII modified no production or shared code.

**Two defects were found by the new tests and fixed in Stage VII code:**

1. **RBO lacked truncation normalisation.** The textbook infinite-list form
   scored two *identical* five-item rankings at 0.4095 instead of 1.0. Now divided
   by the achievable maximum `(1−p^k)/(1−p)`. At the 131-product depth used in the
   report the correction is ~1e-6, so no reported value changes materially — but a
   measure wrong on short lists cannot be trusted on long ones.
2. **Reversal attribution was too generous.** It initially credited any reversal
   between products with differing Collector scores to Collector. Now a reversal
   is Collector-caused only when `|δ·dC| > |δ·dF|`. On this cohort the conclusion
   survives the stricter rule — all 112 remain Collector-dominant — but the loose
   version would have been unfalsifiable.

Two methodological errors in my own Stage VII phases were also caught and
corrected before any conclusion was drawn: the movement guardrails were applied
as absolute rank counts across cohorts of different size, and the Chase contract
was initially measured against the 84/10/6 CONTROL rather than each candidate's
own Chase-free control.

---

## 14. Workspace

| | |
|---|---|
| Branch | `fix/public-rankings-entitlement-regression` |
| HEAD at start | `22274477` (Stage VI-B reported `2f17ff59`; **+2 external commits** since) |
| HEAD at finish | `b64939cf` (**+2 further external commits during the study**) |
| Stage VI-B deliverables | verified present, no drift vs HEAD at start |

The external process committed mid-study and swept in the Stage VII
preregistration, module and report script; they subsequently show as tracked
modifications because this study kept editing them after that commit. The
preregistration hash is unchanged (`73190a86...`), confirming it was never
edited after being locked.

All pre-existing modified/untracked files belong to the concurrent **billing
effort** (`billing_repository.py`, `billing_service.py`, `domain/billing/`,
`backend/api/main.py`, `requirements.txt`, migrations, docs) plus two scheduler
logs. **None was touched.** No stash, reset, clean or commit.

**Created by Stage VII:**

| Path | Classification |
|---|---|
| `docs/research/COLLECTOR_WEIGHT_STAGE7_PREREGISTRATION.json` | required deliverable (hashed, immutable) |
| `docs/research/COLLECTOR_WEIGHT_STAGE7.md` | required deliverable |
| `docs/research/collector_weight_stage7_analysis.txt` | generated / reproducible |
| `backend/research/collector_weight_stage7/__init__.py` | required deliverable |
| `backend/research/collector_weight_stage7/sweep.py` | required deliverable |
| `backend/scripts/report_collector_weight_stage7.py` | required deliverable |
| `backend/tests/unit/research/test_collector_weight_stage7.py` | required deliverable (52 tests) |

**Not implemented. No production change. No Collector Appeal V6.**
