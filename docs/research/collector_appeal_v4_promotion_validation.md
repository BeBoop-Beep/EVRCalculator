# Collector Appeal V4 candidate — pre-promotion validation

**Status: RESEARCH ONLY. Verdict at the bottom: BLOCKED.**
Collector Appeal V3 remains canonical. Overall RIP V7 is unchanged. No snapshot
published, no simulation rerun, nothing committed, pushed, merged or deployed.

Companion to [`collector_appeal_v4_candidate_study.md`](collector_appeal_v4_candidate_study.md),
whose **section 6 (P verdict) is superseded by section 2 below.**

Reproduce:

```
python -m backend.scripts.audit_collector_appeal_v4_candidates --fetch-financial-rip \
    --json docs/research/collector_appeal_v4_candidate_study.json \
    --csv  docs/research/collector_appeal_tables/collector_appeal_v4_candidate_scores.csv
python -m backend.scripts.audit_collector_appeal_v4_historical_replay \
    --json docs/research/collector_appeal_v4_historical_replay.json
```

---

## 0. The frozen candidate

```
key          collector_appeal_v4_candidate_asymmetric_h70p30_up4_down2
version      collector_appeal_v4_candidate_asym_d_plus_h70p30_ceil4_floor2_research_v1
formula ver  collector_appeal_v4_centred_asymmetric_modifier_v1
status       research_candidate_frozen_not_canonical
fingerprint  0f0846a3e0f5bd05ae8b0efb5de245fcf9e2f538c3a37e973f045aa11ec723c5  (sha256)
```

No new candidate families were invented. Section 2's H-only model is the
**ablation twin of this same model**, required by the ablation itself — not a
new family.

---

## 1. Historical Overall RIP replay

**Data.** 15 public RIP snapshots exist. 10 are compatible; 5 are excluded and
listed, all for the same reason — they were built on `financial_rip_v2_60_25_15`,
and the guardrails are defined against the *canonical* financial ranking.
Converting them would report a number describing neither model.

**Limitation, stated up front.** The published RIP history stores the financial
half per date but no per-date D/H/P. Collector Appeal is therefore held fixed at
the published-state cohort while the financial side varies. This answers "does a
90/10 blend sit safely inside the guardrails as the financial ranking moves?" It
does **not** answer "did Collector Appeal itself drift?" — that needs an appeal
history that does not exist yet.

### Frozen candidate, by date

| date | ρ vs Fin-only | top-5 | mean move | max | ≥5 | pass | failing |
|---|---|---|---|---|---|---|---|
| 2026-08-04 | 0.9661 | 0.80 | 0.91 | 5 | 0.05 | YES | |
| 2026-08-05 | 0.9661 | 0.80 | 0.91 | 5 | 0.05 | YES | |
| 2026-08-06 | **0.9390** | **0.60** | 1.27 | 6 | **0.14** | **NO** | spearman, top5, ≥5 share |
| 2026-08-07 | **0.9424** | **0.60** | 1.36 | 7 | 0.05 | **NO** | spearman, top5 |
| 2026-08-08 | **0.9424** | **0.60** | 1.36 | 7 | 0.05 | **NO** | spearman, top5 |
| 2026-08-09 | **0.9424** | **0.60** | 1.36 | 7 | 0.05 | **NO** | spearman, top5 |
| 2026-08-10 | 0.9593 | 1.00 | 1.27 | 5 | 0.05 | YES | |
| 2026-08-11 | 0.9684 | 1.00 | 1.00 | 5 | 0.05 | YES | |
| 2026-08-12 | 0.9548 | 0.80 | 1.27 | 5 | 0.05 | YES | |
| 2026-08-13 | 0.9548 | 0.80 | 1.27 | 5 | 0.05 | YES | |

* Spearman **min 0.9390 / median 0.9548 / max 0.9684**
* Top-5 overlap **0.60 – 1.00**
* Mean absolute movement **0.91 – 1.36** (never breaches the 1.5 bar)
* ≥5-rank share **0.045 – 0.136**
* **6 / 10 dates pass all four guardrails.** Tightest Spearman margin: **−0.011**.

**Answer to the question that prompted this: today's ρ = 0.9548 is NOT robust.**
The median sits within 0.005 of the bar, and the metric spends 4 of 10 days
below it. A single-date measurement of 0.9548 was measuring the median day.

### The same replay, for every model

| appeal input | ρ min | ρ median | ρ max | top-5 min | dates passing |
|---|---|---|---|---|---|
| **V3 (current production)** | 0.9684 | 0.9785 | 0.9898 | **0.60** | **6 / 10** |
| Frozen candidate | 0.9390 | 0.9548 | 0.9684 | 0.60 | 6 / 10 |
| Ablation twin (H only) | 0.9345 | 0.9571 | 0.9661 | 0.60 | 6 / 10 |
| D only | 0.9424 | 0.9571 | 0.9729 | 0.60 | 6 / 10 |

**The single most important finding in this section: the same four dates
(Aug 6–9) fail for every model — including production V3 and including pure D.**
On those dates every appeal input breaches `min_top5_overlap` at 0.60. V3's
top-5 margin is exactly **0.00** on four of the six dates it passes, i.e. it sits
precisely on the bar.

The cause is visible in the financial data: on Aug 6 Pitch Black enters the
financial top 5 (38.72, rank 2) displacing Journey Together, and the top-5
guardrail — a 5-element set-overlap measure over a 22-set cohort — moves in 0.20
steps. One set entering or leaving the financial top 5 is a guardrail
pass/fail event regardless of which appeal metric is applied.

**Separating the two questions, as instructed:**

1. **Is the candidate construct stable?** Yes. Its guardrail behaviour tracks
   `D_only` almost exactly (ρ min 0.9390 vs 0.9424, identical top-5 and movement
   profiles). Nothing about the candidate's *architecture* is unstable; it
   inherits D's disagreement with the financial ranking, which is what a
   desirability-dominant metric is supposed to do.
2. **Does 90/10 regularly cross the boundary?** Yes — and this is an **Overall
   RIP weighting/guardrail decision, not a Collector Appeal decision.** Two
   distinct issues:
   * `min_top5_overlap ≥ 0.80` is not a stable criterion at n = 22. It is a
     5-element overlap that quantizes to 0.20, so it cannot express "one set
     moved" as anything smaller than a 20-point swing. Production V3 fails it on
     40% of days.
   * `min_spearman ≥ 0.95` is where the candidate and V3 genuinely differ. V3
     never goes below 0.9684; the candidate goes to 0.9390.

**No change was made to the candidate to improve any of these numbers.**

---

## 2. P ablation — supersedes section 6 of the study document

Frozen candidate versus its twin. Identical D input, identical H transform and
anchors, identical neutral point, identical +4.0 ceiling, identical −2.0 floor,
identical clamp, identical missing-data policy, identical inversion boundary
(6.0 points). The **only** difference:

```
with P:     S = 0.70·sH + 0.30·sP
without P:  S = sH
```

### Aggregate

| measure | with P | without P (H only) | difference |
|---|---|---|---|
| ρ vs D | 0.9605 | 0.9627 | −0.002 |
| ρ vs H | 0.4207 | 0.4455 | — |
| ρ vs P | −0.0344 | −0.0503 | — |
| mean rank move vs D-only | 1.18 | 1.18 | **0.00** |
| max rank move vs D-only | 6 | 5 | +1 |
| 2+ movers | 0.36 | **0.41** | −0.05 (P moves *fewer*) |
| 3+ movers | 0.045 | **0.091** | −0.045 (P moves *fewer*) |
| 5+ movers | 0.045 | 0.045 | 0.00 |
| top-5 overlap with D | 1.00 | 1.00 | 0.00 |
| bottom-5 overlap with D | 1.00 | 1.00 | 0.00 |
| inversion boundary | 6.0 pts | 6.0 pts | **identical by construction** |
| Overall RIP ρ (today) | 0.9548 | **0.9571** | P is *worse* |
| Overall RIP ρ (historical min) | 0.9390 | 0.9345 | P is better |
| ρ vs sealed pack price | 0.3495 | 0.3405 | +0.009 |
| **ρ(with P, without P)** | **0.9966** | | |

Six sets change rank, **every one of them by exactly 1 place**:

| set | D | P | rank without P | rank with P |
|---|---|---|---|---|
| Prismatic Evolutions | 93.28 | 0.399 | 4 | **3** |
| Scarlet and Violet 151 | 93.61 | 0.290 | 3 | **4** |
| Mega Evolution | 87.20 | 0.447 | 7 | **6** |
| Journey Together | 87.46 | 0.299 | 6 | **7** |
| Temporal Forces | 86.03 | 0.290 | 16 | **15** |
| Perfect Order | 81.60 | 0.347 | 15 | **16** |

### Every pairwise ordering P changes — all 3 of 231 pairs (1.3%)

**Flip 1 — Mega Evolution > Journey Together.** ΔD = **−0.26 pts** (a virtual
tie). P: 0.447 vs 0.299. H slightly favours Journey Together (0.212 vs 0.190).
Gap without P: −0.87. Gap with P: +0.20.
*What P measured:* Mega Evolution's desirable subjects are the cohort's most
dual-path — the Pokémon collectors want here mostly offer both a printing you can
realistically pull and a genuine elite chase.
*Does that count as Collector Appeal?* **Yes.** Two sets are tied on desirability
and near-tied on how often a pack delivers something desirable; the one where
that desirable content has both a reachable and a chase printing is the more
appealing box to open. This is the tiebreaker working exactly as specified.

**Flip 2 — Prismatic Evolutions > Scarlet and Violet 151.** ΔD = **−0.34 pts**
(again a virtual tie). P: 0.399 vs 0.290. H near-identical (0.199 vs 0.207).
Gap without P: −0.55. Gap with P: +0.17.
*Same character as flip 1, same justification.* Two elite rosters separated by a
third of a point; dual-path structure decides.

**Flip 3 — Temporal Forces > Perfect Order.** ΔD = **+4.43 pts**. P: 0.290 vs
**0.347** — the winner has the *lower* P. Gap without P: −0.33. Gap with P: +0.79.
*What P measured: nothing.* Perfect Order has the cohort's best frequency
(H = 0.266, sH = 1.000) against Temporal Forces' sH = 0.310. In the H-only model
that 0.69 sH gap earns Perfect Order enough modifier to overturn 4.43 points of
D. Adding P at 30% weight **dilutes H's leverage by 30%**, and Temporal Forces'
higher D reasserts itself. P did not contribute a signal here; it acted as an
attenuator on H. The identical effect would be achieved by lowering the ceiling
for an H-only model, with no second input.

### Verdict on P

The stated bar was: *retain P only if it provides useful construct-relevant
discrimination beyond H; non-redundancy alone is not sufficient.*

Measured against that bar:

* **Discrimination is 2 construct-relevant flips out of 231 pairs**, each worth
  exactly one rank, in cases where D is separated by less than 0.35 points.
* ρ(with P, without P) = **0.9966**. Mean rank difference between the two models
  is **0.27 places**; maximum is **1**.
* On every summary statistic the two are indistinguishable, and on three of them
  (2+ movers, 3+ movers, today's Overall RIP Spearman) the H-only twin is
  **marginally better**.
* The study document's showcase for P — Mega Evolution moving 12 → 6 — is
  **85% H**: the H-only model already moves it 12 → 7. P adds one place.
* The third of P's three flips is a weight-dilution artifact, not a P signal.

**Recommendation: REMOVE P from Collector Appeal.** This reverses section 6 of
the study document, which recommended retention on non-redundancy grounds — the
grounds the brief explicitly rules insufficient. The frozen candidate should
become its own H-only twin:

```
S = sH        (P weight 0.00, H weight 1.00)
```

Honest counter-argument, recorded so the owner can override: n = 22 is small,
2 flips is not zero, and both genuine flips are *construct-correct* — they are
precisely the behaviour P was included to produce. A larger cohort would give P
more opportunities to act. If the owner values that option, the defensible
position is to retain P and accept that it is currently doing almost nothing.
What is **not** defensible is the study document's original claim that P earns
its place; the ablation does not support it.

If P leaves Collector Appeal, "Dual-Path Depth" should be kept as a measurement
and surfaced in an Opening Experience / Chase Structure diagnostic, not deleted.

---

## 3. Formula contract

The exact model, both branches, no summary. Encoded in
`backend/research/collector_appeal_v4_candidates.py` as
`FROZEN_FORMULA_EXPRESSION` and asserted by
`test_frozen_formula_string_states_both_branches`.

### Inputs

`D`, `H`, `P` on [0, 1], produced by the existing canonical modules. **D is
passed through unchanged** — not min-maxed, not rescaled, not ranked, not
cohort-normalized.

### Transformed H — log2 wait-time

```
sH = clamp01( (log2(H) − log2(1/16)) / (log2(1/4) − log2(1/16)) )
   = clamp01( (log2(H) + 4) / 2 )
```

| anchor | H | one-in-N | sH |
|---|---|---|---|
| zero | 0.0625 | 1 in 16 | 0.0 |
| **neutral** | **0.125** | **1 in 8** | **0.5** |
| one | 0.25 | 1 in 4 | 1.0 |

`H ≤ 0` returns `None`, never 0.0. Frequency is anchored multiplicatively
because the felt difference between "every 4 packs" and "every 8" equals that
between "every 8" and "every 16".

### Transformed P — linear dual-path

```
sP = clamp01( (P − 0.10) / (0.50 − 0.10) )
```

| anchor | P | sP |
|---|---|---|
| zero | 0.10 | 0.0 |
| **neutral** | **0.30** | **0.5** |
| one | 0.50 | 1.0 |

### Structural blend and neutral point

```
S  = 0.70·sH + 0.30·sP          S ∈ [0, 1]
S₀ = 0.50                        NEUTRAL — the modifier is exactly 0 here
z  = 2S − 1                      z ∈ [−1, +1], neutral z = 0
```

At `S = S₀`, `CA = 100·D` **exactly** (asserted by
`test_neutral_structure_returns_exactly_d`).

### The asymmetric modifier

```
m = +4.0 · z        if z ≥ 0        (positive ceiling  = +4.0 points)
m = +2.0 · z        if z <  0        (negative floor    = −2.0 points)
```

Equivalently `m = ceiling · z · (1 if z ≥ 0 else damping)` with
`ceiling = 4.0`, `damping = 0.50`, `floor = −ceiling · damping = −2.0`.

> **The floor is −2.0, not −4.0.** This model must never be written as
> `D + 4·(2S − 1)`. That summary overstates the downside by a factor of two and
> misstates the inversion boundary by 2 points. The version string carries
> `ceil4_floor2` and the key carries `up4_down2` so the asymmetry survives being
> quoted out of context. A test forbids the misleading shorthand appearing in the
> formula string, and the fingerprint hashes `downside_damping` and
> `negative_floor_points` separately so a symmetric variant cannot masquerade as
> this one.

### Output and clamping

```
CA = clamp( 100·D + m, 0, 100 )
```

### Maximum pairwise structural advantage

```
span = ceiling − floor = 4.0 − (−2.0) = 6.0 points
```

The widest D gap structure can overturn is **6.00 public points**: challenger at
`+4.0`, incumbent at `−2.0`. Derived, then verified by exhaustive search over
the admissible space (`test_frozen_max_pairwise_structural_advantage_...`). At a
gap of 5.99 the best structure flips it; at 6.01 nothing can.

### Monotonicity contract — the explicit statement requested

| in | contract |
|---|---|
| **D** | **NON-DECREASING everywhere on [0, 1]; STRICTLY INCREASING wherever `100·D + m` lies strictly inside (0, 100)** |
| H | non-decreasing everywhere |
| P | non-decreasing everywhere |

Ties in D can arise **only** inside the saturation region, and the region is
named rather than left implicit:

```
upper saturation   D > (100 − 4.0)/100 = 0.96
lower saturation   D <  2.0/100        = 0.02
```

* **Formula fact:** the model is not *strictly* increasing in D on all of [0, 1].
  Above D = 0.96 two sets with different D and maximal structure both score 100.
* **Data fact, asserted separately:** no eligible cohort set is in either region
  (max D = 0.9548, min D = 0.5107), so on real data the function *is* strictly
  increasing in D throughout. `test_no_eligible_cohort_set_is_inside_the_saturation_region`
  fails the moment a future set crosses D = 0.96, forcing a review rather than
  producing a silent tie.

The clamp was retained deliberately. The alternatives were (a) tapering the bonus
into the last points of headroom — which reintroduces exactly the `(1 − D)`
shrinkage that made V2 a restatement of D, and does so precisely for the elite
sets the tiebreaker exists to separate; or (b) letting the score exceed 100 —
which breaks the published "out of 100" claim. Clamping, with the region named
and monitored, is the least dishonest of the three.

### Missing data

Any of D, H, P missing or malformed → `None`. Never 0.0, never 0.5, never D,
never the previous version's score.

### Fingerprint

SHA-256 over the canonicalized assumption set, computed with the *existing*
canonical fingerprint machinery (`collector_appeal_fingerprint.fingerprint_assumptions`)
rather than a second hashing implementation. Version identifiers and the status
label are recorded but excluded from the hash — relabelling changes no computed
number. All six score-changing constants are covered, each verified to move the
hash.

---

## 4. Verdict

# BLOCKED

Two blockers, both requiring an owner decision rather than more code.

**Blocker 1 — the candidate introduces a new Overall RIP guardrail breach that
production V3 does not have.**
The frozen candidate falls below `min_spearman_vs_financial_only = 0.95` on
**4 of 10 compatible historical dates** (min 0.9390, median 0.9548, tightest
margin −0.011). Production V3 never goes below 0.9684 on the same dates. Per the
standing rule — *"a new Collector Appeal candidate that breaks Overall RIP
guardrails should not be promoted without a separate product decision"* — this
blocks promotion until one of the following is decided:
* accept a lower Spearman bar for a desirability-dominant appeal input (note
  `D_only` scores 0.9424 minimum, so the bar penalizes desirability itself); or
* lower the Overall RIP collector-appeal weight below 0.10; or
* explicitly accept the breach.

The candidate was **not** modified to improve this. It is stable in the sense
that matters — its guardrail profile tracks `D_only` almost exactly — and the
breach is the arithmetic consequence of being desirability-dominant.

**Blocker 2 — the frozen spec fails its own P-retention test.**
P changes 3 of 231 pairwise orderings, moves 6 sets by exactly 1 rank each, and
leaves ρ(with P, without P) = 0.9966. One of its 3 flips is a weight-dilution
artifact rather than a P signal. Against the stated bar — *useful
construct-relevant discrimination beyond H, non-redundancy insufficient* — P
does not clear it. The model that should be promoted is therefore the H-only
twin, which is **not the model that was frozen**. Promoting the frozen spec
as-is would ship an input the validation says is not earning its place.

**Adjacent finding, not a blocker for this work but a live production issue:**
`min_top5_overlap ≥ 0.80` is failed on the same 4 dates by *every* model
including production V3, and V3 sits exactly on the bar (margin 0.00) on 4 of
the 6 dates it passes. A 5-element overlap over a 22-set cohort quantizes to
0.20, so one set entering the financial top 5 is a pass/fail event. **Overall
RIP V7 in production would not pass its own promotion guardrails on 40% of the
last ten days.** That deserves a separate ticket regardless of what happens to
Collector Appeal.

---

## 5. Files

New this pass:

* `backend/scripts/audit_collector_appeal_v4_historical_replay.py`
* `docs/research/collector_appeal_v4_historical_replay.json`
* `docs/research/collector_appeal_v4_promotion_validation.md` (this file)

Modified this pass:

* `backend/research/collector_appeal_v4_candidates.py` — frozen contract block, explicit asymmetry constants, monotonicity contract, fingerprint, ablation twin, both registered
* `backend/scripts/audit_collector_appeal_v4_candidates.py` — `p_ablation` section, frozen identity in the report
* `backend/tests/unit/research/test_collector_appeal_v4_candidates.py` — 68 tests (was 55)
* `docs/research/collector_appeal_v4_candidate_study.json`, `collector_appeal_tables/collector_appeal_v4_candidate_scores.csv` — regenerated

Unchanged: every canonical module. V3, Financial RIP V3, Overall RIP V7,
simulations, snapshots, frontend, publication paths.
