# Financial RIP — Chase Complementarity / V11 Candidate Study

**Primary decision: `CHASE_METRICS_SHOULD_REMAIN_SEPARATE_FROM_FINANCIAL_RIP`**

> No chase metric earned a place in Financial RIP. Two of them failed on evidence
> (Core Chase EV Return and Chase EV Share are double-counted against Jackpot
> Upside; Beat-the-Buy is a restatement of Chase EV Return). One — Chase Depth —
> is genuinely orthogonal to the CONTROL and was not falsified as *information*,
> but it was never shown to be *financial*, and it cannot currently be delivered
> at the level Financial RIP scores. The default outcome stands.

| | |
|---|---|
| Branch | `fix/public-rankings-entitlement-regression` |
| Baseline HEAD | `6882da0` |
| CONTROL | Financial RIP **V4**, `25/20/15/25/10/5`, P95-only Realistic Upside |
| Cohort | 21 simulation-supported sets, market date **2026-08-28**, 1,000,000 packs each |
| Chase contract | Stage IV system **`B_pct_floor`** — Core = top 5% ∧ ≥5×C, Extended = top 15% ∧ ≥2×C |
| Candidates tested | 31 chase metrics × 2 universes, 62 scoring architectures |
| Artifact | `docs/research/financial_rip_v11_chase_complementarity.json` |
| Production impact | **None.** No version, weight, snapshot, ranking, RPC, API or UI changed. |

---

## Phase 0 — Workspace baseline

Branch confirmed `fix/public-rankings-entitlement-regression`, HEAD `6882da0`, no
merge/rebase/cherry-pick in progress, nothing staged. Two pre-existing changes were present
at start and were not touched: modified `frontend/components/explore/RipStatisticsPageClient.jsx`
(−246/+31) and untracked `frontend/components/pokemon/set-page/rich/RichCardsSetTab.jsx`.
Both are unrelated to this study and remain exactly as found.

---

## Phase 1 — CONTROL contract audit, and three discrepancies

The current production contract was read from code and database, not from prior notes.

| Property | Verified value | Source |
|---|---|---|
| Canonical version | `financial_rip_v4_outcome_profile_p95_only_25_20_15_25_10_5` | `backend/desirability/scoring_config.py:425` |
| Weights | win .25 / retention .20 / loss .15 / realistic .25 / jackpot .10 / econ .05 | `financial_rip_v4_config.py` |
| Realistic Upside | `1.00 × p95_threshold_ratio` (the P95–P99 conditional mean is disclosed, unweighted) | `REALISTIC_UPSIDE_SUBWEIGHTS_V4` |
| Normalization | `financial_rip_v3_fixed_absolute_piecewise_v1` — **fixed absolute anchors, not cohort-relative** | shared with V3 by value |
| Tail contract | `empirical_rank_exact_mass_v1` | shared with V3 |
| Storage | `simulation_derived_metrics.financial_rip_v3_payload`; **V4 is projected at read time** by `project_financial_rip_v4_from_v3_payload` — no V4 row is stored | `explore_rip_statistics_service.py:775` |

### Discrepancy 1 — V4 *is* canonical

The standing research note records "V4/V10 built but NOT canonical; promotion needs snapshot
rebuild." That is **out of date**. `CANONICAL_FINANCIAL_RIP_VERSION = FINANCIAL_RIP_V4_VERSION`
today, and `test_financial_rip_canonical_ownership.py` asserts it. The snapshot caveat survives
in a different form: no V4 score is persisted anywhere, so every V4 number in production —
and in this study — is a read-time projection of a stored V3 payload.

### Discrepancy 2 — the Stage-IV decision code in the brief is not the recorded one

The brief states `ECONOMIC_THRESHOLD_CHASE_TIERS_SUPPORTED`. The artifact records
**`PERCENTILE_PLUS_ECONOMIC_FLOOR_SUPPORTED`**, adopted with the explicit caveat that
"the floor carries the rule and the percentile is a guardrail cap." The 5×/2× floors in the
brief are correct; the percentile caps (5% / 15%) are part of the winning specification and
were reused verbatim from the artifact rather than reconstructed from the prompt. As Stage IV
required, the inert percentile received no credit anywhere in this study.

### Discrepancy 3 — the two cost bases disagree, on the same market date

This is the single most consequential input finding. Financial RIP's pack cost and the
Stage-IV chase pack-equivalent cost are **different numbers for the same set on the same day**:

| Set | Financial RIP cost | Chase pack-equiv cost | Δ | chase cost route |
|---|---:|---:|---:|---|
| Shrouded Fable | $14.81 | $8.91 | **+66.2%** | booster bundle |
| Temporal Forces | $11.25 | $8.64 | +30.2% | booster box |
| Obsidian Flames | $12.98 | $10.16 | +27.8% | booster box |
| Paldea Evolved | $16.09 | $13.07 | +23.1% | booster box |
| Pitch Black | $5.76 | $4.75 | +21.3% | booster box |

Stage IV prices a chase against the **cheapest usable acquisition route**; Financial RIP scores
against the cost the simulation ran at. So `p95_threshold_ratio` and `chaseEvReturn` are ratios
to *different denominators*. Every correlation in Phases 4–6 is therefore partly a correlation
between two different deflators. This is quantified rather than corrected, because correcting it
means re-running the chase simulation on the Financial RIP cost basis — which is exactly the
Phase-22 question, and is unresolved.

---

## Phase 11 — CONTROL reconstruction (gate: passed)

The CONTROL was rebuilt from the six stored raw components using the production engine, for all
21 sets, before any candidate was scored.

```
max | manual Σ w·component − published V4 score |  =  5.0e-05
score versions                                     =  1 (V4 only)
statuses                                           =  all "ready"
```

The residual is 4-decimal storage rounding. **The baseline is exact and comparisons against it
are valid.**

---

## Phase 2–3 — Candidate set and direction

31 chase metrics computed for both universes (Core, Core+Extended): Chase EV Return, Chase EV
Share, Any-Chase probability, Expected Packs per Chase, 50% Chase Spend, Beat-the-Buy, median and
mean Chase Cost Gap, literal Chase Count, effective EV count and effective value count, EV-HHI and
value-HHI, plus five Core-vs-Extended structural differentials.

Direction was **not** assumed. The unadjusted relationships to CONTROL (n=21):

| metric | ρ vs CONTROL | p | reading |
|---|---:|---:|---|
| Core 50% Chase Spend | −0.674 | 0.001 | cheaper chase → better RIP |
| Total 50% Chase Spend | −0.668 | 0.001 | " |
| Total median Cost Gap | −0.662 | 0.001 | " |
| Core Any-Chase p | +0.526 | 0.014 | more accessible → better RIP |
| Total Chase Depth (effective EV count) | +0.417 | 0.060 | weak |
| Total Chase EV Return | **+0.225** | 0.328 | **not significant** |
| Core Chase EV Return | **−0.031** | 0.893 | **no relationship at all** |

The hypothesis that "deeper chase pools imply better Financial RIP" is **not supported**:
ρ = +0.417 (p = 0.06) for total depth, +0.320 (p = 0.16) for core depth. Depth is a description,
not a direction. The metrics that *do* track CONTROL are the accessibility/cost ones — and they
track it with the sign that says *cheap and frequent beats rich and rare*, which is precisely what
True Win Frequency and Typical Retention already say.

---

## Phase 4–5 — Redundancy

Strong redundancy flags (|ρ| ≥ 0.85) against the CONTROL space:

```
coreShareOfChaseEv   vs jackpot_tail_mean_ratio   +0.887
coreMedianCostGap    vs full EV/cost              −0.873
coreEvShare          vs jackpot_tail_mean_ratio   +0.871
coreMeanCostGap      vs full EV/cost              −0.861
```

93 further pairs fall in the 0.65–0.85 moderate-overlap band.

Redundancy regression — each chase metric regressed on the six CONTROL components, reported at
**LOOCV R²** because n=21 with 6 predictors makes in-sample R² meaningless:

| metric | R² | adj R² | **LOOCV R²** | verdict |
|---|---:|---:|---:|---|
| Core Chase EV Share | 0.898 | 0.854 | **0.781** | already encoded |
| Core Chase EV Return | 0.841 | 0.773 | **0.662** | already encoded |
| Total Chase EV Share | 0.828 | 0.755 | **0.643** | already encoded |
| Total Any-Chase p | 0.791 | 0.702 | 0.552 | partly encoded |
| Total 50% Spend | 0.718 | 0.597 | 0.342 | partly encoded |
| Total Chase Depth | 0.672 | 0.531 | 0.318 | partly encoded |
| Total Chase EV Return | 0.655 | 0.507 | 0.271 | largely independent |
| Beat-the-Buy (total) | 0.520 | 0.315 | **−0.009** | independent |
| Core Chase Depth | 0.505 | 0.293 | **−0.036** | independent |
| Core 50% Spend | 0.404 | 0.149 | **−0.315** | independent |

**Core economics are the redundant half.** Core Chase EV Share is 78% reconstructable from the
CONTROL alone. That is the first of two independent routes to the same conclusion; Phase 23 is the
second, and it is mechanical rather than statistical.

---

## Phase 6 — Partial correlation

After controlling for full EV/cost, P95 ratio, jackpot tail mean and pack price:

| metric | controls | partial r | p |
|---|---|---:|---:|
| Total Chase EV Return | EV, P95, Jackpot, price | **−0.829** | 0.000 |
| Beat-the-Buy | EV, P95, Jackpot, price | **−0.860** | 0.000 |
| Total Chase EV Share | EV, P95, Jackpot, price | **−0.831** | 0.000 |
| Core Chase EV Return | EV, P95, Jackpot, price | −0.802 | 0.000 |
| **Total Chase Depth** | EV, P95, Jackpot, price | **−0.108** | 0.680 |
| **Core Chase Depth** | EV, P95, Jackpot, price | +0.141 | 0.590 |
| Total Chase Count | EV, P95, Jackpot, price | −0.181 | 0.487 |

Two clean, opposite results.

**Chase EV Return does contain independent information — with the wrong sign.** Conditional on EV,
P95 and Jackpot, a set whose EV is *more* concentrated in its chase pool scores *lower* on Financial
RIP (r = −0.83). That is not a discovery; it is the CONTROL working as designed. EV parked in a
1-in-35 card is EV that is absent from the median pack, so Typical Retention and True Win Frequency
fall. Adding Chase EV Return as a positively-weighted component would **partially cancel** the
concentration penalty the model already applies deliberately.

**Chase Depth is orthogonal, in the strict sense.** Partial r ≈ 0.0 with p ≈ 0.7. It is neither
redundant with the CONTROL nor informative about it. Orthogonality is a necessary condition for
inclusion, not a sufficient one: a set's card count is also orthogonal to Financial RIP.

---

## Phase 7 — Multicollinearity, and an incumbent problem

| architecture | condition number | worst VIFs |
|---|---:|---|
| **CONTROL (six components)** | **17.0** | cLoss 48.0, cRetention 45.4, cEcon 28.0, cRealistic 16.1, cWin 12.4 |
| CONTROL + Chase EV Return | 18.0 | *chase term 2.90* — the lowest VIF in the model |
| CONTROL + Chase Depth | 22.8 | *chase term 3.05* |
| CONTROL + both | 23.2 | *chase terms 3.01 / 3.17* |
| CONTROL + Core EV Return + Core Depth | 19.0 | core EV return 6.77, jackpot rises 1.76 → 6.27 |

An honest reading, in the CONTROL's disfavour: **the incumbent six components are far more
collinear with each other than any chase candidate is with them.** Loss Resilience, Typical
Retention and Base Economic Efficiency (VIF 48/45/28) are close to a single latent "how much value
comes back" factor already. This is a real finding about the CONTROL and is recorded as such — it
is not an argument for adding a seventh component, and it is out of scope here, but it belongs in
whatever study next revisits the CONTROL's own structure.

One caution for any Core-based architecture: adding **Core** Chase EV Return raises Jackpot
Upside's VIF from 1.76 to 6.27. Core chase economics and the Jackpot component compete for the same
variance. Total-universe metrics do not do this.

---

## Phase 9 — Latent structure of the chase suite

PCA over 11 total-universe chase metrics (standardized): PC1 48.6%, PC2 28.8%, PC3 10.1%
(cumulative 87.5%).

| axis | share | dominant loadings | honest name |
|---|---:|---|---|
| PC1 | 48.6% | expected packs +0.38, EV-HHI +0.38, depth −0.36, median gap +0.36, 50% spend +0.35, any-P −0.35 | **Chase accessibility** — how expensive and how concentrated the journey is |
| PC2 | 28.8% | EV share −0.50, core EV return −0.49, EV return −0.46, BTB −0.34 | **Chase economic strength** |
| PC3 | 10.1% | count −0.57, depth −0.40, BTB +0.35 | **Chase breadth** |

The empirical structure declines to separate "breadth" from "accessibility": depth and HHI load on
PC1 alongside expected packs and spend. Chase Depth is not its own axis in the data — it is the
breadth end of the accessibility axis, which is why it correlates ρ = +0.805 with literal K (Stage IV)
while being orthogonal to the score.

---

## Phase 10 — Classification

**SCORE CANDIDATES** (carried into architecture testing): Total Chase EV Return, Core Chase EV
Return, Total Chase Depth (effective EV count), Core Chase Depth, Total Chase EV Share, Beat-the-Buy.

**EXPLANATORY METRICS** (retained for display, never for weighting): Expected Packs per Chase and
50% Chase Spend (invertible transforms of Any-Chase probability and price — AccessCluster VIF 4.3/2.7/2.4,
condition number 4.0); mean and median Chase Cost Gap and the gap distribution; literal Chase Count;
value-HHI and EV-HHI; the five Core-vs-Extended differentials; median chase value obtained.

Nothing is removed from the product. Beat-the-Buy in particular remains the most legible sentence
in the whole suite ("about one chase journey in five beats buying the card outright") and should
keep its place in the UI — it simply carries no score information: ρ = +0.951 with Chase EV Return
under two different tier definitions, and LOOCV R² = −0.009 against the CONTROL.

---

## Phase 12–14 — Ablation families

62 architectures were scored. All use **fixed absolute** piecewise transforms in the same family
and shape as the CONTROL's own `p95_threshold_ratio` anchor set, because the CONTROL's normalization
is absolute and a cohort-relative chase term would change the model's character, not just its inputs.
Anchor choice is researcher-made and its sensitivity is reported in Phase 26b.

**Family A — one-for-one replacement (diagnostic only).** Which incumbent does each chase metric
most resemble?

| replacement | ρ vs CONTROL | max rank move |
|---|---:|---:|
| Base Economic Efficiency → any chase metric | 0.978 – 0.992 | 2–4 |
| Jackpot Upside → Chase EV Return | 0.973 | 3 |
| Jackpot Upside → Chase Depth | 0.940 | 6 |
| **Realistic Upside (P95) → Core Chase EV Return** | **0.440** | **15** |
| Realistic Upside (P95) → Chase Depth (core) | 0.608 | 14 |
| Realistic Upside (P95) → Chase EV Return (total) | 0.692 | 13 |

Chase metrics substitute almost perfectly for Base Economic Efficiency and well for Jackpot Upside;
they substitute *terribly* for P95. Read correctly, that says the chase suite lives in the model's
**EV and jackpot** space, not in its realistic-upside space — the opposite of the intuition that
motivated the study.

**Family B — weight splits.** Donating up to a third of Jackpot Upside or Base Economic Efficiency
to a chase metric leaves ρ ≥ 0.986 and zero Top-10 turnover — that is, it does nothing. Donating
half or more of P95 breaks the model (ρ 0.69–0.93, up to 13 rank places moved). There is no
allocation that both matters and is safe.

**Family C — Chase EV + Depth architectures.**

| arch | composition | ρ vs CONTROL | τ | changed | max move | Top-5 | Top-10 |
|---|---|---:|---:|---:|---:|---:|---:|
| C1_Tot | P95 + halved Jackpot + Chase EV Return | 0.990 | 0.943 | 10 | 2 | 1 | 0 |
| C2_Tot | P95 + halved Jackpot + Chase Depth | 0.962 | 0.857 | 16 | 5 | 1 | 0 |
| C3_Tot | P95 + Jackpot + EV Return + Depth | 0.984 | 0.933 | 10 | 3 | 1 | 0 |
| C4_Tot | P95 + reduced Jackpot + EV Return + Depth | 0.973 | 0.895 | 15 | 4 | 1 | 0 |
| C5_Tot | P95 + EV Return + Depth, Jackpot removed | 0.961 | 0.867 | 15 | 5 | 2 | 0 |
| C1_Core | Core universe variant of C1 | 0.992 | 0.952 | 6 | 2 | 1 | 0 |
| **C6** | **CONTROL unchanged** | 1.000 | 1.000 | 0 | 0 | 0 | 0 |

Every movement was traced. The recurring faller is **Chaos Rising** (rank 5 → 7…11), a $5.22/pack
box-route set whose chase pool is small (Core K = 5, total K = 8) and whose depth is low; it is
penalized by every chase-bearing architecture. The recurring riser is **Shrouded Fable** (6 → 4)
under EV-return architectures — and Shrouded Fable is precisely the set with the **+66% cost-basis
mismatch**, so its rise is at least partly an artifact of being scored on a $8.91 chase denominator
while its Financial RIP is computed on $14.81. No unexplained movement remains, but one of the two
largest explained movements is explained by a data defect.

---

## Phase 15 — Core vs Extended

| question | Core | Core+Extended |
|---|---|---|
| Redundancy (LOOCV R² vs CONTROL) | EV Share **0.781**, EV Return **0.662** | EV Share 0.643, EV Return **0.271** |
| Double counting with Jackpot (Phase 23) | **median ratio 0.94, ~1:1** | 0.30–0.71 of the band |
| VIF impact on Jackpot Upside | 1.76 → **6.27** | 1.76 → 3.15 |
| Temporal stability | Core K churns 0–50%; 151 oscillates 1↔2 cards (endpoint Jaccard 0.500) | Extended Jaccard ≈ 0.99 |
| Product-level K spread within a set | median **3 cards** | median **8 cards** |

**Answer: neither, but Core is clearly the worse of the two.** Core metrics are the more redundant,
the more double-counted, the more collinear with the incumbent Jackpot component, and the least
temporally stable. If any chase metric were ever to enter Financial RIP, it would have to be a
Core+Extended one. Stage IV's warning about thin Core universes is confirmed and sharpened: on 151
the Core is one card, it oscillates between one and two cards across eight weekly dates, and its
Chase EV Return swings 16.1%.

---

## Phase 16 — Incremental information (test is degenerate, and that matters)

The nested-model test as specified cannot work here, and this is a property of the CONTROL, not of
the implementation: **Financial RIP is an exact linear function of its six components**, so
`CONTROL ~ components` has R² = 1.000 and every candidate's ΔR², Δadj-R² and ΔLOOCV are exactly
0.00000. There is no residual for a chase metric to explain.

Recorded, not worked around. The valid form of the question is the **reverse** regression — can the
CONTROL reconstruct the chase metric? — which is Phase 5, and which was run. As the brief itself
notes, neither direction validates a V11 in the absence of an external target; both are redundancy
tests, and Phase 5 is the one that is well-posed.

---

## Phase 17–18 — Rank and uncertainty stability

Cohort bootstrap (4,000 resamples of the 21 sets) and simulation-noise resampling (1,000 draws,
chase EV perturbed by the measured binomial SE of any-chase probability, mean relative SE 0.58%):

| arch | bootstrap ρ | 95% CI | mean rank SD | max rank SD |
|---|---:|---|---:|---:|
| C6_CONTROL | 1.000 | [1.000, 1.000] | 0.000 | 0.000 |
| C1_Core | 0.987 | [0.950, 1.000] | 0.003 | 0.032 |
| C1_Tot | 0.984 | [0.943, 1.000] | 0.008 | 0.055 |
| C3_Tot | 0.978 | [0.922, 1.000] | 0.041 | 0.360 |
| C5_Tot | 0.950 | [0.858, 0.993] | 0.015 | 0.153 |
| C2_Tot | 0.949 | [0.858, 0.991] | 0.000 | 0.000 |

No candidate is *unstable*. At 1,000,000 packs the chase inputs are measured precisely enough that
simulation noise moves no rank by as much as half a place. Stability is not what disqualifies these
architectures.

---

## Phase 19–20 — Price and temporal sensitivity

Price sensitivity is inherited from Stage IV's exhaustive shock work rather than re-derived: system
B holds Jaccard ≈ 0.953 at ±10% independent price shock, 0.945 under pack-cost shock, and — the
property that matters for an economic floor — tier membership *does* respond to pack cost, which is
the intended behaviour. Sets do move cards across the 5× and 2× floors under shock, and any
integrated architecture would correctly inherit that churn.

Temporal, over 8 weekly dates (2026-07-03 → 2026-08-28), system B:

| set | Core K range | endpoint Jaccard | Chase EV Return swing |
|---|---|---:|---:|
| Chaos Rising | 5–6 | 0.833 | **44.7%** |
| Pitch Black | 7–8 | 0.875 | 30.2% |
| Phantasmal Flames | 2–2 | 1.000 | 28.1% |
| SV Base Set | 4–5 | 0.800 | 23.4% |
| Ascended Heroes | 14–18 | 0.778 | 18.4% |
| **Scarlet & Violet 151** | **1–2** | **0.500** | 16.1% |
| Prismatic Evolutions | 13–14 | 1.000 | 6.0% |

Median Chase EV Return swing across the cohort is **~12% over eight weeks**, against a CONTROL whose
components move far less. Chaos Rising — already the architecture's most-moved set — swings 44.7%.
A 5%-weighted component that swings 12–45% quarter-on-quarter injects rank noise into a public
leaderboard for information the Phase-24 tests show is not decision-relevant.

---

## Phase 21–22 — Set level vs product level (a structural blocker)

Financial RIP is published **per product**. Stage IV's chase tiers are computed **per set**, against
one chosen pack-equivalent cost — the cheapest usable route. The economic floor is *defined in pack
costs*, so chase membership is a function of the acquisition price. Within a single set, the usable
routes' pack-equivalent costs differ enormously:

| set | cost spread across products | set-level Core/Ext K | Core K spread | Ext K spread |
|---|---:|---|---:|---:|
| Obsidian Flames | **518.1%** ($10.16 → $62.79) | 1 / 7 | 1 | 7 |
| Paldea Evolved | 318.2% ($13.07 → $54.67) | 4 / 19 | 3 | **18** |
| Scarlet & Violet 151 | 302.8% ($29.81 → $120.08) | 1 / 11 | 1 | 10 |
| SV Base Set | 248.8% ($8.22 → $28.69) | 4 / 13 | 4 | 11 |
| Journey Together | 181.4% ($6.58 → $18.52) | 4 / 11 | 3 | 7 |
| White Flare | 65.2% ($13.53 → $22.35) | 8 / 25 | 5 | 12 |

*(K counts are censored at the top-25 price list, so Extended spreads are lower bounds.)*

Median within-set spread: **3 cards of Core, 8 cards of Extended**, purely from which product you buy.

This forces a choice with no good branch:

- **Set-level inheritance** gives every product in a set the identical chase term. An overpriced ETB
  and a cheap booster box would receive the same "chase quality" credit despite the ETB's floor being
  3–5× higher and its true Core being a fraction of the size. This directly contradicts the model's
  purpose — Financial RIP exists to distinguish products by their economics — and would inject a
  duplicated set-level constant into a product-level score.
- **Product-level recomputation** is the correct answer and **does not exist**. Chase EV requires
  per-card expected copies per pack from the simulator; it cannot be derived from the published
  artifact. Producing it means re-running Stage IV per product across every product family, which is
  a separate build, not an analysis.

Combined with the Phase-1 cost-basis mismatch (up to +66% on the same day, same set), the chase suite
is currently **not denominated in the units Financial RIP is denominated in**. That alone is
sufficient to withhold integration regardless of every statistical result above.

---

## Phase 23 — Double counting (the decisive test)

The question: does the chase pool occupy the same *outcomes* the CONTROL's upside components already
price? It does.

- **The Core chase floor (5×C) sits at or above the P99 pack-value threshold in 11 of 21 sets.**
  Where it does, *every* Core chase hit is by construction a top-1% outcome — the exact band Jackpot
  Upside is computed over.
- **The Extended floor (2×C) sits at or above the P95 threshold in 17 of 21 sets.** Most Extended
  chase hits are inside the band Realistic Upside is computed over.
- **Core any-chase probability averages 0.0103 (median 0.0092).** The Jackpot band is the top 1.00%.
  The Core chase pool is, to within a rounding error, *the jackpot tail itself, re-derived from prices
  instead of from outcomes*.
- **Core Chase EV Share ÷ Jackpot Value Share has a median of 0.94** across the cohort, and lands at
  exactly 1.00 for Ascended Heroes and Prismatic Evolutions. The two metrics are measuring the same
  dollars.

Total any-chase probability averages 0.0346 against a 5% P95 band — the same coincidence one tier out.

So a single high-value SIR improves total EV (Base Economic Efficiency), lifts the P95 threshold
(Realistic Upside), dominates the top-1% conditional mean (Jackpot Upside), *and* constitutes the
Core chase pool (Chase EV Return, Chase EV Share, Beat-the-Buy). Adding a chase component would make
that card count a **fifth** time. This is the specific failure the study was told to avoid, and it
is present in the data rather than hypothetical.

Chase Depth is the one metric that escapes: it is a property of *how many* cards share the tail, not
of the tail's magnitude, and its partial correlation with the CONTROL is ≈ 0.

---

## Phase 24 — Synthetic counterfactuals

Twelve controlled outcome distributions, scored through the **production V4 engine** (`build_financial_rip`
with `FINANCIAL_RIP_V4_SPEC`, 400,000 packs each). Expected direction was written before each run.

| case | P95 score | Jackpot | chase K | depth | chase EVR | CONTROL | C1_Tot | C2_Tot |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| A huge jackpot, terrible chase | 2.3 | 8.9 | 1 | 1.00 | 0.04 | 2.56 | 2.91 | 2.11 |
| B moderate upside, great chase | 95.1 | 47.0 | 4 | 3.88 | 0.66 | 42.43 | 45.08 | 42.51 |
| C1 same EV, one hero | 2.3 | 46.1 | 1 | 1.00 | 0.30 | 6.89 | 8.75 | 4.59 |
| C2 same EV, five chases | 2.4 | 32.5 | 5 | 5.00 | 0.30 | 10.72 | 13.26 | 12.10 |
| D1 P95 matched, low chase EVR | 80.1 | 30.1 | 2 | 1.69 | 0.21 | 29.70 | 31.76 | 28.88 |
| D2 P95 matched, high chase EVR | 80.3 | 59.0 | 2 | 1.80 | 0.45 | 35.01 | 36.76 | 32.86 |
| E1 chase EVR matched, low P95 | 2.3 | 45.9 | 1 | 1.00 | 0.30 | 7.02 | 8.89 | 4.72 |
| E2 chase EVR matched, high P95 | 90.1 | 23.6 | 1 | 1.00 | 0.30 | 34.36 | 37.34 | 33.18 |
| F1 chase matched, weak resilience | 0.4 | 46.4 | 1 | 1.00 | 0.30 | 8.57 | 10.41 | 6.25 |
| F2 chase matched, strong resilience | 35.7 | 48.7 | 1 | 1.00 | 0.30 | 48.67 | 50.40 | 46.23 |

Paired verdicts:

| pair | CONTROL Δ | chase-arch Δ | verdict |
|---|---:|---:|---|
| B accessible vs A lottery | **+39.87** | +42.17 | CONTROL already answers correctly; chase adds 5% |
| F2 vs F1 (chase held constant, resilience differs) | **+40.10** | +39.98 | chase metrics correctly do **not** mask resilience |
| E2 vs E1 (chase EVR held constant, P95 differs) | **+27.34** | +28.45 | correctly driven by P95 alone |
| **D2 vs D1 (P95 held constant, chase EVR differs)** | **+5.31** | **+5.00** | **failure** — the chase-bearing score *shrinks* the separation it was introduced to create |
| **C2 vs C1 (chase EV held constant, depth differs)** | +3.83 | **+7.51** (depth arch) | **the one genuine win** — depth roughly doubles a separation the CONTROL only partly makes |

Case D is the falsification. Chase EV Return was hypothesized to separate two products with identical
realistic upside but different chase economics. The CONTROL separates them by 5.31 points on its own
(through Jackpot Upside, 30.1 vs 59.0). The Chase-EV-Return architecture separates them by 5.00 — it
made the discrimination *worse*, because the weight it took from Jackpot Upside was already doing that
job better.

Case C is the one place a chase metric earns its keep: with chase EV held identical and only depth
varying, the depth-bearing architecture nearly doubles the CONTROL's separation. Chase Depth measures
something the CONTROL genuinely under-weights.

One construction caveat, recorded rather than hidden: the G1/G2 pair (matched literal count, different
effective depth) is confounded — G2's deep pool also raised its P95 score to 98.9 against G1's 2.4, so
its +26.97 CONTROL delta is a P95 effect, not a depth effect. That pair proves nothing and is excluded
from the verdicts. Case C is the clean depth test.

---

## Phase 25–27 — Dominance, weight sensitivity, complexity

**Variance dominance.** The CONTROL is already a two-component model in practice: Realistic Upside
supplies **50.3%** of score variance and True Win Frequency **27.9%**; Jackpot Upside contributes
**−3.9%** (it moves *against* the score across this cohort). Adding chase terms at 5%:

| architecture | chase term's share of score variance |
|---|---:|
| C1_Tot (Chase EV Return, 5%) | **+1.6%** |
| C1_Core (Core Chase EV Return, 5%) | **−1.9%** |
| C2_Tot (Chase Depth, 5%) | **+11.1%** |
| C3_Tot (both) | +1.6% EVR, +5.7% depth |

Chase EV Return at 5% weight accounts for 1.6% of the variance in the published number. It is, to a
first approximation, **a component that does nothing** — and in the Core variant it does slightly less
than nothing, actively opposing the score. Chase Depth at the same weight moves 11.1%, which is the
quantitative form of "depth is the only one carrying real signal."

**Weight sensitivity.** All finalists are robust: perturbing any weight by ±10/20/30% and
renormalizing leaves ρ ≥ 0.982 vs the unperturbed architecture, zero Top-10 turnover, max 3 rank
places. Notably the **CONTROL itself is the least robust** of the set (worst ρ 0.9831) — none of these
models depends on a knife-edge weight.

**Anchor sensitivity.** Swapping the researcher-chosen Chase EV Return anchors for tighter, looser or
purely linear ones changes C1_Tot's ranking by at most one place (ρ ≥ 0.9987). The result is not an
artifact of the transform — but it is also further evidence that the term barely participates.

**Complexity.** Under the required simplicity preference: CONTROL (6 components) and CONTROL + Chase
EV Return (7 components) produce ρ = 0.990, τ = 0.943, zero Top-10 turnover and one Top-5 change. A
seventh component that changes essentially no ranking, contributes 1.6% of variance, and requires a
new set-to-product projection layer, a new cost basis reconciliation and a new transform anchor set is
not justified. Complexity loses.

---

## Phase 29 — Finalist tournament

| | **C6 CONTROL** | C1_Tot (EV Return) | C2_Tot (Depth) | C3_Tot (both) | C1_Core |
|---|---|---|---|---|---|
| Incremental information | n/a | LOOCV R² 0.271 — some | 0.318 — some | some | 0.662 — little |
| Redundancy / double counting | n/a | **severe (Ph 23)** | **low** | severe via EVR | **severe, ~1:1 with Jackpot** |
| VIF / conditioning | cond 17.0 | 18.0, chase VIF 2.9 | 22.8, VIF 3.1 | 23.2 | 19.0, **Jackpot VIF → 6.27** |
| Rank stability vs CONTROL | — | ρ 0.990 | ρ 0.962 | ρ 0.984 | ρ 0.992 |
| Bootstrap 95% CI | — | [0.943, 1.000] | [0.858, 0.991] | [0.922, 1.000] | [0.950, 1.000] |
| Price stability | good | inherits Stage IV (J≈0.95) | same | same | same |
| Temporal stability | good | **input swings 6–45%/8wk** | same input risk | same | **worse (Core 1↔2 cards)** |
| Variance contribution of chase term | — | **+1.6%** | +11.1% | +1.6/+5.7% | **−1.9%** |
| Product-family behaviour | correct by construction | **blocked (Ph 22)** | **blocked** | **blocked** | **blocked** |
| Interpretability | high | moderate (double-counted story) | **high** | low (two new terms) | low |
| Complexity | 6 components | 7 | 7 | 8 | 7 |
| Largest rank change | — | 2 places | 5 places | 3 places | 2 places |
| Strongest case **for** | already correct in every Phase-24 pair; zero new failure modes | none survived | Phase-24 case C: doubles a separation the CONTROL under-makes; orthogonal; low VIF | combines both | most stable |
| Strongest case **against** | leaves depth unpriced | **Phase-24 case D: worsens the discrimination it exists to make**; double-counted; 1.6% variance | set-level only; input swings 12% median over 8 weeks; not shown to be *financial* | inherits C1's failure | double-counts Jackpot ~1:1; raises Jackpot VIF to 6.3 |

---

## Findings

### Observed

1. The CONTROL is Financial RIP **V4** and is reproduced from stored components to **5e-05**.
2. Financial RIP's pack cost and Stage IV's chase pack-equivalent cost differ by up to **+66.2%** on the same set, same day.
3. **Core Chase EV Share ÷ Jackpot Value Share has median 0.94**; the Core floor is at or above P99 in **11/21** sets; Core any-chase probability averages **0.0103** against a 1% jackpot band.
4. Core Chase EV Share is **78.1%** reconstructable (LOOCV) from the six CONTROL components; Core Chase EV Return **66.2%**.
5. Total Chase EV Return's partial correlation with CONTROL, controlling for EV, P95, Jackpot and price, is **−0.829** — independent, with the sign opposed to the proposed weighting.
6. Chase Depth's partial correlation under the same controls is **−0.108 (p = 0.68)** — genuinely orthogonal.
7. Beat-the-Buy vs Chase EV Return: **ρ = +0.951**, third independent confirmation.
8. Chase EV Return at 5% weight supplies **1.6%** of score variance; the Core variant supplies **−1.9%**.
9. In Phase-24 case D (P95 matched), the chase-bearing architecture **reduced** separation from **+5.31 to +5.00**.
10. In Phase-24 case C (chase EV matched, depth differs), the depth architecture **increased** separation from **+3.83 to +7.51**.
11. Within-set product cost spreads run **65%–518%**, moving Core K by a median of 3 cards and Extended K by 8.
12. Chase EV Return swings a median **~12%** over 8 weekly dates, up to **44.7%** (Chaos Rising).
13. The CONTROL's own components are badly conditioned among themselves (VIF 48/45/28/16/12; condition number 17.0) — worse than any chase candidate's addition.

### Interpretation

The chase suite is not a missing dimension of Financial RIP. It is a **re-derivation of the model's
existing upside dimension from prices instead of from outcomes.** Stage IV set the economic floor at
5× and 2× pack cost; the CONTROL sets its upside bands at the top 1% and top 5% of outcomes; on real
sets those two rules select nearly the same cards. That is why Core Chase EV Share and Jackpot Value
Share come out at a 0.94 median ratio, and why the one-for-one ablations show chase metrics
substituting cleanly for Jackpot Upside and Base Economic Efficiency but catastrophically for P95.

Chase Depth is the honest exception. It is orthogonal, it is not double-counted, it has the lowest
VIF in any candidate architecture, and it is the only metric that won its controlled counterfactual.
It still fails, for two reasons that are not statistical: it has not been shown to be a *financial*
quantity (orthogonality is not relevance — Phase 3's ρ = +0.417, p = 0.06 does not establish that
deeper is financially better), and it is a **set-level** measurement that cannot be honestly attached
to a **product-level** score while the same set's products differ in acquisition cost by up to 518%.

### Unresolved

* Whether a product-level chase recomputation would change any of this. It is the one experiment that
  could reopen the question, and it requires re-running the Stage-IV simulation per product.
* Stage IV's own two prerequisites — the canonical floor multiple (5×/2× vs 3×/1×) and the MSRP-vs-market
  cost basis — remain unsettled. Stage IV said they should be settled *before* this study; they were not,
  and the cost-basis finding in Phase 1 is the direct consequence.
* Whether Chase Depth belongs in some *other* published score. It is a real, clean, orthogonal signal.
  It just is not a Financial RIP component.
* The CONTROL's internal collinearity (VIF 48/45/28). Out of scope here, worth its own study.

---

## Decisions

### `CHASE_METRICS_SHOULD_REMAIN_SEPARATE_FROM_FINANCIAL_RIP`

Financial RIP V4 remains unchanged. The chase suite remains separate intelligence, fully retained and
published in its own right.

Every tested metric is explicitly rejected, with cause:

| metric | verdict | reason |
|---|---|---|
| `CORE_CHASE_EV_RETURN` | **REJECTED** | Double-counted with Jackpot Upside (median share ratio 0.94; floor above P99 in 11/21 sets). LOOCV R² 0.662. Raises Jackpot VIF 1.76 → 6.27. Contributes −1.9% of score variance. |
| `TOTAL_CHASE_EV_RETURN` | **REJECTED** | Contributes 1.6% of score variance; partial correlation −0.829 (opposed sign); failed its own controlled test (Phase 24 case D: separation fell 5.31 → 5.00). |
| `CORE_CHASE_EV_SHARE` | **REJECTED** | 78.1% reconstructable from the CONTROL; ρ +0.871 with jackpot tail mean. |
| `TOTAL_CHASE_EV_SHARE` | **REJECTED** | 64.3% reconstructable; ρ +0.730 with pack cost — it substantially describes how expensive the pack is, not how good it is. |
| `BEAT_THE_BUY` | **REJECTED as a score input** | ρ +0.951 with Chase EV Return. Retained and recommended as the suite's best *explanatory* statistic. |
| `ANY_CHASE_PROBABILITY`, `EXPECTED_PACKS_PER_CHASE`, `50%_CHASE_SPEND` | **REJECTED** | Mutually invertible (AccessCluster condition number 4.0); 34–55% reconstructable; the accessibility signal they carry is already carried by True Win Frequency and Typical Retention with the same sign. |
| `CHASE_COUNT`, `VALUE_HHI`, `CHASE_EV_HHI` | **REJECTED** | Descriptive; ρ +0.805 between count and depth (Stage IV); no independent financial content. |
| `CORE_VS_EXTENDED_DIFFERENTIALS` | **REJECTED** | Best of them (`dEffEv`) is 67.2% reconstructable; novelty is not evidence. |
| **`CHASE_DEPTH`** (effective EV count) | **REJECTED, with the strongest dissent on the record** | Passes redundancy (partial r −0.108), passes double-counting, passes VIF (3.05), and **won** its controlled counterfactual (+3.83 → +7.51). Rejected on delivery, not on statistics: it is set-level, it cannot be projected onto products whose costs differ by up to 518%, its input swings a median 12% over 8 weeks, and it has not been shown to be a financial quantity rather than an interesting set characteristic. |

### `PRODUCT_LEVEL_CHASE_ECONOMICS_REQUIRED_BEFORE_ANY_RECONSIDERATION`

No chase metric may be reconsidered for Financial RIP until chase tiers are computed **per product**,
on the **same cost basis** Financial RIP scores against. Set-level inheritance is rejected outright:
it would attach one constant to every product in a set whose real chase economics differ by a median
of 3 Core cards and 8 Extended cards.

---

## Phase 31 — Deployment

**Nothing was deployed.** No production Financial RIP version, weight, transform, snapshot, public
ranking, RPC, API contract or UI was modified. This study is a research recommendation only, and its
only outputs are this report and its data artifact.

## Next study

If the question is reopened, the order is fixed by what this study found:

1. Settle Stage IV's two prerequisites — canonical floor multiple, and MSRP vs market cost basis.
2. Reconcile the Financial RIP and chase cost bases, or accept that the two suites are not comparable.
3. Build product-level chase economics. Until that exists, the Phase-22 blocker stands regardless of
   any statistical result.
4. Only then re-ask the depth question — and ask it as "is chase depth financial?", which this study
   could not answer, rather than "is chase depth orthogonal?", which it answered yes.
