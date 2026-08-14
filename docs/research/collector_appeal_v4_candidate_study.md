# Collector Appeal V4 — candidate architecture study

**Status: RESEARCH ONLY. Nothing here is canonical.**
Collector Appeal V3 (`collector_appeal_v3_balanced_d40_h35_p25`) remains the
shipping metric. Overall RIP V7 is unchanged. No snapshot was published, no
simulation was rerun, nothing was committed, pushed, merged or deployed.

* Cohort state: **published-state**, `docs/research/collector_appeal_tables/collector_appeal_v3_decomposition.csv` (n = 22)
* Financial RIP V3 and sealed pack price: **current-source-state**, read live and read-only from `explore_rip_statistics_latest`
* Reproduce with: `python -m backend.scripts.audit_collector_appeal_v4_candidates --fetch-financial-rip --json docs/research/collector_appeal_v4_candidate_study.json --csv docs/research/collector_appeal_tables/collector_appeal_v4_candidate_scores.csv`

The published V3 and CA7 numbers in the frozen table reproduce **exactly** from
today's canonical functions given the stored D/H/P, so the published state and
the code have not drifted. (The frozen table's `collectorAppealV2` column is
mislabelled — it duplicates `ca_v3_public` digit for digit because the audit
that wrote it copied the then-current `collectorAppeal` field after V3 had
already landed. V2 is recomputed from the canonical V2 function here and that
column is ignored.)

---

## 1. Why V3 no longer matches the construct

V3 is `CA = 0.40D + 0.35H + 0.25P`. Three peer addends, each on its own [0, 1]
scale, is not a "D-dominant" model — it is a model in which **D contributes 40%
of the score and 100% of nothing in particular.** What actually orders a
weighted sum is not the nominal coefficient but the *dispersion of the weighted
contribution*, and on this cohort:

| | raw range | weight | contribution range |
|---|---|---|---|
| D | 0.511 → 0.955 (0.444) | 0.40 | 0.178 |
| H | 0.028 → 0.266 (0.238) | 0.35 | 0.083 |
| P | 0.135 → 0.450 (0.315) | 0.25 | 0.079 |

D's contribution range is only slightly larger than H's and P's *combined*
(0.178 vs 0.162), and D's dispersion is concentrated in a single outlier
(Shrouded Fable at 0.511) — strip it and the remaining 21 sets span D 0.699 to
0.955, a contribution range of 0.102, which H and P jointly beat outright.

The measured consequence, on the published cohort:

* Spearman(V3, D) = **0.589**, Spearman(V3, H) = **0.832**
* Mean absolute rank movement from a D-only ranking: **4.45** places out of 22
* **41%** of the cohort moves 5+ places, max movement **13** places
* Bottom-5 overlap with D-only: **0.60**

A metric named for how desirable a set's content is, whose ranking correlates
0.83 with hit *frequency* and 0.59 with desirability, and which moves the median
set three places off the desirability order, is measuring the opening cadence and
calling it appeal. Pitch Black (D = 79.90) sitting above Ascended Heroes
(D = 95.48) is a symptom, not the disease; the disease is that structure has no
budget at all in V3 — it has an unbounded share.

---

## 2. Historical lineage

| model | formula | ρ(model, D) | practical structural influence |
|---|---|---|---|
| CA7 (legacy) | `D + 0.50·P·(1−D)` | **0.984** | observed swing **2.36 pts**; mean rank move vs D-only **0.64**; 0% move 5+ |
| V2 (bounded D/H/P) | `D + 0.50·(0.60H + 0.40P)·(1−D)` | **0.991** | observed swing **2.02 pts**; mean rank move **0.36**; 0% move 5+ |
| V3 (additive, current) | `0.40D + 0.35H + 0.25P` | **0.589** | observed swing **16.21 pts**; mean rank move **4.45**; 41% move 5+ |

CA7 and V2 both bound the structural bonus by `(1 − D)`. For the sets anyone
argues about, `(1 − D)` is 0.05–0.13, so the entire structural term is scaled
down by an order of magnitude precisely where it was supposed to break ties.
That is the mechanism behind the "median bonus ≈ 1.25 pts" finding, and it is
why V2 was three inputs reproducing one input's ordering.

V3 fixed that by deleting the bound entirely. The lineage is a bang-bang
control: a structural budget of ~2 points, then a structural budget of ~16.
Nothing in between was tried.

---

## 3. Candidate models tested

All candidates score on the public 0–100 scale and take D, H, P unchanged. **D
is never normalized, rescaled or ranked.** H and P are mapped onto a structural
index through *fixed, pre-registered anchors stated in collector language*, so a
set's score cannot move because another set was added or removed:

```
sH = clamp( (log2(H) − log2(1/16)) / (log2(1/4) − log2(1/16)) )
        0.0 = a desirable card ~every 16 packs or worse
        0.5 = ~every 8 packs         (NEUTRAL)
        1.0 = ~every 4 packs or better
sP = clamp( (P − 0.10) / (0.50 − 0.10) )
        0.0 = desirable subjects essentially single-path
        0.5 = P = 0.30               (NEUTRAL)
        1.0 = desirable subjects broadly dual-path
S  = 0.70·sH + 0.30·sP
```

H is anchored on a **log2 wait-time** scale because frequency is perceived
multiplicatively — the felt gap between "every 4 packs" and "every 8" is the
same as between "every 8" and "every 16".

The architecture's one substantive move is that the modifier is **centred at
neutral structure, not floored at zero**:

| key | family | formula |
|---|---|---|
| `D_only` | reference | `100·D` |
| `baseline_A_v3` | existing | `100·(0.40D + 0.35H + 0.25P)` |
| `baseline_B_ca7` | existing | `100·(D + 0.50·P·(1−D))` |
| `baseline_C_v2` | existing | `100·(D + 0.50·(0.60H + 0.40P)·(1−D))` |
| `cand_D_additive_c{2,4,6,8}` | candidate | `100·D + c·(2S−1)` |
| `cand_D_additive_c{…}_damp50` | candidate | as above, downside halved |
| `cand_E_h_dominant_c4` | candidate | `100·D + 4·(2S−1)`, `S = 0.85·sH + 0.15·sP` |
| `cand_F_d_plus_h_c4` | candidate | `100·D + 4·(2·sH − 1)` |
| `cand_P_only_control_c4` | P audit | `100·D + 4·(2·sP − 1)` |
| `cand_G_multiplicative_g{4,8}` | candidate | `100·D·(1 + g·(2S−1))` |

Why centring matters: a *floored* bonus can only add, so the only way to make
structure matter is to make the bonus large — and a large one-sided bonus is
exactly the thing that lets a mediocre roster climb. A centred modifier lets
excellent structure add and poor structure subtract while the **total span**
stays small. That is what "tiebreaker" means arithmetically.

Behavioural properties, all asserted in tests:

* `∂CA/∂D = 100 > 0` independent of H and P — strict monotonicity in D
* neutral structure (`S = 0.5`) gives `CA = 100·D` **exactly**
* non-decreasing in H and in P
* any missing input → `None`, never 0, never D
* deterministic, cohort-independent, no search loop over any constant
* no price / EV / cost / profit / set value anywhere in the module

---

## 4. Inversion boundaries

For the additive family the maximum overturnable D gap is **derived, not
discovered**:

```
max_flip_gap = ceiling × (1 + penalty_damping)
```

because the widest possible swing is `+ceiling` for the challenger against
`−ceiling·damping` for the incumbent. Exhaustive search over the admissible
(D, H, P) space confirms nothing exceeds it.

| model | derived max flip gap | observed structural swing | gap 2 | gap 5 | gap 10 | gap 15 | gap 20 |
|---|---|---|---|---|---|---|---|
| `D_only` | 0 | 0.00 | hold | hold | hold | hold | hold |
| `baseline_A_v3` | unbounded | 16.21 | **FLIP\*** | **FLIP\*** | **FLIP\*** | **FLIP\*** | **FLIP\*** |
| `baseline_B_ca7` | ~7.5 | 2.36 | FLIP\* | FLIP | hold | hold | hold |
| `baseline_C_v2` | ~5.25 | 2.02 | FLIP | FLIP | hold | hold | hold |
| `cand_D_additive_c2` | 4 | 3.75 | FLIP\* | hold | hold | hold | hold |
| `cand_D_additive_c2_damp50` | 3 | 2.80 | FLIP\* | hold | hold | hold | hold |
| `cand_D_additive_c4` | 8 | 7.49 | FLIP\* | FLIP\* | hold | hold | hold |
| **`cand_D_additive_c4_damp50`** | **6** | **5.60** | **FLIP\*** | **FLIP\*** | **hold** | **hold** | **hold** |
| `cand_D_additive_c6` | 12 | 11.24 | FLIP\* | FLIP\* | FLIP\* | hold | hold |
| `cand_D_additive_c6_damp50` | 9 | 8.39 | FLIP\* | FLIP\* | hold | hold | hold |
| `cand_D_additive_c8` | 16 | 14.98 | FLIP\* | FLIP\* | FLIP\* | FLIP | hold |
| `cand_D_additive_c8_damp50` | 12 | 11.19 | FLIP\* | FLIP\* | FLIP\* | hold | hold |
| `cand_E_h_dominant_c4` | 8 | 7.75 | FLIP\* | FLIP\* | hold | hold | hold |
| `cand_F_d_plus_h_c4` | 8 | 8.00 | FLIP\* | FLIP\* | hold | hold | hold |
| `cand_G_multiplicative_g4` | ~6.8 (D-dependent) | 6.37 | FLIP\* | FLIP\* | hold | hold | hold |
| `cand_G_multiplicative_g8` | ~13.6 (D-dependent) | 12.73 | FLIP\* | FLIP\* | FLIP\* | hold | hold |

**FLIP** = the lower-D set wins at that gap under the most extreme admissible
structure; **\*** = it also wins under the best-vs-worst structure *actually
observed in the cohort*. That distinction matters: CA7 and V2 can nominally flip
a 5-point gap but never do so on real data, because their observed swing is only
~2 points.

The transition is legible. Ceiling ±2 is **too weak to matter** (observed swing
3.75 pts, but only 14% of the cohort moves 2+ ranks, mean movement 0.55 — this
is CA7 with extra steps). Ceiling ±4 is a **useful tiebreaker**. Ceiling ±6 and
±8 begin to **hijack desirability**: they overturn 10-point D gaps, and they also
**clamp real sets at 100** (2 sets at ±6, 4 sets at ±8), which is the one place
the additive family loses strict monotonicity in D. That is a structural
disqualification independent of where anyone lands.

The multiplicative family (G) is well-behaved and never manufactures appeal from
nothing (`D = 0 → CA = 0` at any structure), but its inversion boundary is
D-dependent — the same structural advantage is worth 4.8 points at D = 95 and
2.6 points at D = 51 — so the boundary cannot be stated in the spec, only
measured per-set. It is not disqualified; it is simply less explainable for the
same behaviour.

---

## 5. Full cohort comparison

Sorted by D. `mod` is the structural adjustment under the recommended candidate.

| set | D | H | P | S | mod | D-only rk | V3 | V3 rk | CA7 rk | **V4c4d50** | **rk** |
|---|---|---|---|---|---|---|---|---|---|---|---|
| Ascended Heroes | 95.48 | .234 | .271 | .795 | +2.36 | 1 | 53.16 | 3 | 1 | 97.84 | 1 |
| Paldean Fates | 95.33 | .179 | .199 | .606 | +0.85 | 2 | 49.37 | 9 | 2 | 96.18 | 2 |
| Scarlet and Violet 151 | 93.61 | .207 | .290 | .747 | +1.98 | 3 | 51.94 | 5 | 4 | 95.59 | 4 |
| Prismatic Evolutions | 93.28 | .199 | .399 | .810 | +2.48 | 4 | 54.26 | 1 | 3 | 95.76 | 3 |
| Phantasmal Flames | 90.74 | .243 | .371 | .889 | +3.11 | 5 | 54.08 | 2 | 5 | 93.85 | 5 |
| Paldea Evolved | 90.37 | .093 | .209 | .284 | −0.86 | 6 | 44.65 | 17 | 6 | 89.51 | 8 |
| Surging Sparks | 88.85 | .124 | .362 | .544 | +0.35 | 7 | 48.94 | 10 | 7 | 89.21 | 9 |
| Destined Rivals | 87.93 | .141 | .321 | .577 | +0.61 | 8 | 48.13 | 11 | 9 | 88.54 | 10 |
| Journey Together | 87.46 | .212 | .299 | .765 | +2.12 | 9 | 49.87 | 8 | 10 | 89.58 | 7 |
| Obsidian Flames | 87.32 | .103 | .248 | .363 | −0.55 | 10 | 44.74 | 16 | 11 | 86.77 | 12 |
| White Flare | 87.30 | .090 | .135 | .210 | −1.16 | 11 | 41.45 | 20 | 13 | 86.14 | 13 |
| Mega Evolution | 87.20 | .190 | .447 | .822 | +2.58 | 12 | 52.71 | 4 | 8 | 89.78 | **6** |
| Paradox Rift | 86.65 | .138 | .298 | .550 | +0.40 | 13 | 46.96 | 12 | 12 | 87.05 | 11 |
| Stellar Crown | 86.35 | .108 | .259 | .396 | −0.42 | 14 | 44.80 | 15 | 14 | 85.94 | 14 |
| Temporal Forces | 86.03 | .096 | .290 | .360 | −0.56 | 15 | 45.03 | 14 | 15 | 85.47 | 15 |
| Black Bolt | 84.01 | .125 | .136 | .379 | −0.48 | 16 | 41.40 | 21 | 16 | 83.53 | 17 |
| Perfect Order | 81.60 | .266 | .347 | .885 | +3.08 | 17 | 50.63 | 7 | 17 | 84.69 | 16 |
| Twilight Masquerade | 81.18 | .138 | .326 | .571 | +0.56 | 18 | 45.46 | 13 | 19 | 81.75 | 19 |
| Pitch Black | 79.90 | .232 | .450 | .926 | +3.40 | 19 | 51.35 | 6 | 18 | 83.31 | 18 |
| Scarlet and Violet Base | 75.60 | .103 | .334 | .427 | −0.29 | 20 | 42.19 | 19 | 20 | 75.31 | 20 |
| Chaos Rising | 69.89 | .180 | .372 | .739 | +1.91 | 21 | 43.57 | 18 | 21 | 71.81 | 21 |
| Shrouded Fable | 51.07 | .028 | .234 | .100 | −1.60 | 22 | 27.24 | 22 | 22 | 49.48 | 22 |

### Rank movement vs a D-only ranking

| model | mean | median | max | ≥2 | ≥3 | ≥5 | top-5 overlap | bottom-5 overlap |
|---|---|---|---|---|---|---|---|---|
| `baseline_A_v3` | 4.45 | 3.0 | **13** | 0.73 | 0.64 | **0.41** | 0.80 | 0.60 |
| `baseline_B_ca7` | 0.64 | 0.0 | 4 | 0.09 | 0.05 | 0.00 | 1.00 | 1.00 |
| `baseline_C_v2` | 0.36 | 0.0 | 3 | 0.09 | 0.05 | 0.00 | 1.00 | 1.00 |
| `cand_D_additive_c2` | 0.64 | 0.0 | 3 | 0.23 | 0.05 | 0.00 | 1.00 | 1.00 |
| `cand_D_additive_c4` | 1.36 | 1.0 | 6 | 0.41 | 0.14 | 0.05 | 1.00 | 0.80 |
| **`cand_D_additive_c4_damp50`** | **1.18** | **1.0** | **6** | **0.36** | **0.05** | **0.05** | **1.00** | **1.00** |
| `cand_D_additive_c6_damp50` | 1.64 | 1.5 | 6 | 0.50 | 0.18 | 0.05 | 1.00 | 0.80 |
| `cand_D_additive_c8` | 2.27 | 1.5 | 7 | 0.50 | 0.32 | 0.23 | 1.00 | 0.80 |
| `cand_E_h_dominant_c4` | 1.27 | 1.0 | 5 | 0.36 | 0.18 | 0.05 | 1.00 | 1.00 |
| `cand_F_d_plus_h_c4` | 1.36 | 1.0 | 5 | 0.36 | 0.23 | 0.05 | 1.00 | 1.00 |
| `cand_G_multiplicative_g4` | 1.27 | 1.0 | 6 | 0.32 | 0.14 | 0.05 | 1.00 | 1.00 |

### Correlations

| model | ρ vs D | r vs D | ρ vs H | ρ vs P | ρ vs V3 | ρ vs CA7 | ρ vs V2 |
|---|---|---|---|---|---|---|---|
| `baseline_A_v3` | 0.589 | 0.790 | **0.832** | 0.563 | 1.000 | 0.654 | 0.634 |
| `baseline_B_ca7` | 0.984 | 0.996 | 0.345 | −0.082 | 0.654 | 1.000 | 0.997 |
| `baseline_C_v2` | 0.991 | 0.998 | 0.334 | −0.112 | 0.634 | 0.997 | 1.000 |
| `cand_D_additive_c2` | 0.984 | 0.996 | 0.361 | −0.100 | 0.653 | 0.994 | 0.993 |
| `cand_D_additive_c4` | 0.953 | 0.986 | 0.443 | 0.010 | 0.743 | 0.981 | 0.973 |
| **`cand_D_additive_c4_damp50`** | **0.961** | **0.990** | **0.421** | −0.034 | 0.712 | 0.985 | 0.979 |
| `cand_D_additive_c6_damp50` | 0.938 | 0.978 | 0.506 | 0.063 | 0.783 | 0.970 | 0.961 |
| `cand_D_additive_c8` | 0.866 | 0.952 | 0.651 | 0.214 | 0.889 | 0.905 | 0.895 |
| `cand_E_h_dominant_c4` | 0.958 | 0.985 | 0.457 | −0.029 | 0.724 | 0.977 | 0.974 |
| `cand_F_d_plus_h_c4` | 0.948 | 0.983 | 0.496 | −0.002 | 0.748 | 0.970 | 0.966 |
| `cand_G_multiplicative_g4` | 0.956 | 0.990 | 0.432 | −0.013 | 0.726 | 0.983 | 0.976 |

### Largest movers under the recommended candidate, with the reason

**Up**

* **Mega Evolution 12 → 6 (+6).** The single largest move in the cohort, and the
  only 5+ move. D = 87.20 sits in a dense cluster (six sets within 3.2 points),
  and Mega Evolution has the cohort's **best dual-path structure** (P = 0.447,
  sP = 0.867) with above-neutral frequency (sH = 0.803) → S = 0.822, mod +2.58.
  Its immediate D-neighbours (Obsidian Flames, White Flare, Paldea Evolved) all
  carry *negative* modifiers, so a 2.6-point bonus against 0.5–1.2-point
  penalties clears five places inside one desirability neighbourhood. This is
  the intended behaviour: reshuffling within a neighbourhood, not travelling the
  leaderboard. Under V3 the same set moves +8, and Pitch Black moves +13.
* **Journey Together 9 → 7, Paradox Rift 13 → 11 (+2 each).** Above-neutral
  structure in tight D clusters.

**Down**

* **Surging Sparks 7 → 9, Destined Rivals 8 → 10, Obsidian Flames 10 → 12,
  Paldea Evolved 6 → 8, White Flare 11 → 13 (−2 each).** All displaced by
  neighbours, not demoted: Paldea Evolved and White Flare carry genuine
  penalties (−0.86, −1.16) for below-neutral obtainability, while Surging Sparks
  and Destined Rivals move purely because Mega Evolution and Journey Together
  passed them.

No set changes desirability neighbourhood. Top-5 and bottom-5 overlap with the
D-only ordering are both 1.00.

### Case studies (interpretability, not selection criteria)

| pair | ΔD | ΔH | ΔP | ΔS | V3 gap / flips? | CA7 gap | **V4 c4d50 gap / flips?** |
|---|---|---|---|---|---|---|---|
| Ascended Heroes vs Pitch Black | **+15.58** | +0.002 | −0.179 | .795 vs .926 | +1.81, follows D but ranks #3 vs #6 | +11.67 | **+14.53, follows D** |
| Ascended Heroes vs Perfect Order | +13.88 | −0.032 | −0.076 | .795 vs .885 | +2.53 | +11.30 | **+13.15, follows D** |
| Ascended Heroes vs Journey Together | +8.02 | +0.022 | −0.028 | .795 vs .765 | +3.29 | +6.76 | **+8.26, follows D** |
| Mega Evolution vs SV 151 | −6.41 | −0.017 | **+0.157** | .822 vs .747 | +0.77, **FLIPS** | −4.48 | **−5.81, follows D** |
| Phantasmal Flames vs Ascended Heroes | −4.74 | +0.009 | +0.100 | .889 vs .795 | +0.92, **FLIPS** | −3.63 | **−3.99, follows D** |
| Phantasmal Flames vs Prismatic Evolutions | −2.53 | +0.043 | −0.027 | .889 vs .810 | −0.19 | −2.15 | **−1.91, follows D** |

Read this as calibration, not as a scoreboard. The recommended candidate
narrows every one of these gaps relative to D-only where the lower-D set has
better structure (Phantasmal Flames closes 2.53 → 1.91 on Prismatic Evolutions;
Pitch Black closes 15.58 → 14.53 on Ascended Heroes) without overturning any of
them. A 2.53-point gap closing to 1.91 is a live tiebreaker: a slightly larger
structural edge on Phantasmal Flames' side would flip it, which is exactly the
behaviour the brief asks for at small gaps.

**Phantasmal Flames is the requirement-5 check.** Its H = 0.243 (about one
desirable card per 4.1 packs) gives sH = 0.979 — the model reads it as an
excellent opening experience, and its high P adds on top, for a +3.11 modifier.
Difficulty of the *individual chase* never enters as a penalty, because H
measures how often a desirable card of any kind arrives, not how easy the top
card is. The model does not punish jackpot sets.

---

## 6. P verdict

Four variants at an identical ±4-point budget, so the comparison is of *inputs*,
not of leverage:

| variant | ρ vs D | ρ vs H | ρ vs P | mean rank move | max move |
|---|---|---|---|---|---|
| `D_only` | 1.000 | 0.303 | −0.173 | 0.00 | 0 |
| `cand_F_d_plus_h_c4` (D + H) | 0.948 | 0.496 | −0.002 | 1.36 | 5 |
| `cand_P_only_control_c4` (D + P) | 0.942 | 0.409 | 0.081 | 1.45 | 6 |
| `cand_D_additive_c4` (D + H + P) | 0.953 | 0.443 | 0.010 | 1.36 | 6 |

> **SUPERSEDED.** The verdict below was reached from a shared-budget comparison
> of *different* variants (D+H at ±4 symmetric vs D+H+P at ±4 symmetric). The
> pre-promotion pass ran the proper ablation — the frozen candidate against its
> otherwise-identical H-only twin — and found ρ(with P, without P) = 0.9966, six
> sets moving one rank each, and 3 changed pairwise orderings out of 231, one of
> which is a weight-dilution artifact rather than a P signal. Against the stated
> bar (*useful construct-relevant discrimination beyond H; non-redundancy is not
> sufficient*), **P does not clear it, and the recommendation is now to remove
> it.** See
> [`collector_appeal_v4_promotion_validation.md`](collector_appeal_v4_promotion_validation.md)
> section 2. The reasoning below is retained as the record of what was
> originally concluded and why it was wrong: it rested on non-redundancy, which
> is exactly the insufficient ground.

**Verdict (SUPERSEDED): keep P, but reduced to a minority share of a small structural budget
— not as a peer pillar, and not removed.**

Three findings support that:

1. **P is not redundant with H.** Adding P to D+H changes the ranking (both move
   the cohort ~1.4 places on average but not the same sets), and P's own
   contribution is what produces the study's single most defensible move —
   Mega Evolution, whose case is entirely "the desirable Pokémon here have both
   a reachable printing and a real chase".
2. **P does not manufacture desirability under this architecture, because the
   architecture forbids it.** The requirement-6 worry — "a well-designed rarity
   ladder around less-desirable Pokémon should not create the same appeal as
   elite Pokémon demand" — is not addressed by weighting P down; it is addressed
   by capping *all* structure. Under a ±4/damped budget, perfect dual-path
   architecture around a mediocre roster is worth at most 4 points, which cannot
   reach an elite roster more than 6 points away. Under V3, P alone had a
   0.079 contribution range against D's post-outlier 0.102 — there, a rarity
   ladder genuinely could substitute for demand.
3. **P's raw correlation with D is slightly negative (−0.173)**, so P is the
   input most capable of pulling the ranking away from desirability. That is an
   argument for the 0.30 minority share it holds inside S, not for expulsion.

**Naming.** "Dual-Path Depth" describes the measurement accurately and should
stay. What it is *not* is an appeal pillar. If the product later wants a visible
structural diagnostic, P belongs in an **Opening Experience / Chase Structure**
card alongside H, shown next to Collector Appeal rather than inside it — the
public surface can then show "why" without the score being hostage to it. That
is a product decision, not part of this study.

---

## 7. Recommended candidate

**`cand_D_additive_c4_damp50`**

```
S  = 0.70·sH + 0.30·sP                     (fixed anchors, cohort-independent)
m  = 4·(2S − 1)          if S ≥ 0.5
m  = 4·(2S − 1)·0.5      if S <  0.5
CA = clamp(100·D + m, 0, 100)
```

Why this one, on construct grounds:

* **It is the only ceiling where structure is a tiebreaker rather than either
  noise or a second ranking.** ±2 moves 14% of the cohort 2+ places (too weak);
  ±6 and ±8 overturn 10-point D gaps (too strong) *and* clamp real sets at 100,
  which is where the additive family loses strict monotonicity in D.
* **Its inversion boundary is a stated design parameter, not an emergent
  property.** `max_flip_gap = 4 × 1.5 = 6 points`, verified by exhaustive
  search. Small gaps (1–5 points) are live; 10, 15 and 20-point gaps are
  unreachable by any admissible structure. That is precisely "D = 92 vs D = 90
  may flip; D = 95 vs D = 80 must not".
* **ρ(CA, D) = 0.961 sits in the defensible middle** — meaningfully below CA7's
  0.984 and V2's 0.991, far above V3's 0.589 — while delivering **3.3× V2's
  practical rank movement** (1.18 vs 0.36 mean places) and a **2.8× larger
  observed structural swing** (5.60 vs 2.02 points). It is not "V2 with a bigger
  number"; the centring is what buys the movement, not the budget.
* **The asymmetry is the right one.** Damping the downside to 0.5 encodes
  "a difficult chase is still a chase" without pretending difficulty is a
  virtue: excellent obtainability earns up to +4, poor obtainability costs at
  most −2. It also improves bottom-5 stability against D (1.00 vs 0.80 for the
  symmetric ±4) — the sets that were being penalized hardest were low-D sets
  being penalized twice.
* **Neutral structure returns D exactly**, so the sentence "Collector Appeal is
  this set's desirability, adjusted for how well the pack delivers it" is
  literally true of the arithmetic rather than a gloss on it.

Runners-up, and why they lose:

* `cand_E_h_dominant_c4` (0.85H/0.15P) is nearly identical in every statistic;
  it loses only because the P audit shows P carrying non-redundant signal, and
  reducing it to 0.15 discards that for no measured gain.
* `cand_G_multiplicative_g4` behaves well (ρ = 0.956, mean move 1.27) and has the
  attractive property that structure can never create appeal from zero
  desirability. It loses because its inversion boundary is D-dependent and
  therefore cannot be *specified* — only measured per set — which forfeits the
  main advantage of this whole architecture.
* `cand_F_d_plus_h_c4` is the honest simplification if the product decides to
  move P out of Collector Appeal entirely. It is a defensible fallback, not the
  recommendation.

**None of these were selected by where they put any set.** The selection
criteria in order were: (1) strict D-monotonicity with no clamp saturation on
real data, (2) a *stateable* inversion boundary in the 5–8-point range, (3)
ρ(CA, D) strictly between the V2 and V3 poles, (4) mean rank movement from
D-only in the 1–2 place range with no set crossing a desirability neighbourhood.
Ascended Heroes finishing #1 is a consequence of having the highest D; it was
not a target, and the recommended model would rank it #1 even with the cohort's
worst structure.

### External sanity check (diagnostic only — never fitted)

| model | ρ vs sealed pack price |
|---|---|
| D alone | +0.468 |
| CA7 | +0.418 |
| V2 | +0.435 |
| **V4 c4d50** | **+0.350** |
| **V3 (current production)** | **−0.189** |

Reported, not optimized. The striking number is V3's: the shipping Collector
Appeal is *mildly negatively* related to what a sealed pack costs. That is not
by itself disqualifying — a correct appeal model may disagree with the market,
and pack price is heavily driven by print run and age — but a sign flip relative
to D, CA7 and V2 is a face-validity signal worth recording. The recommended
candidate's +0.350 is lower than D's +0.468, which is expected: it is D plus a
non-price structural term.

---

## 8. Overall RIP impact

Read-only sensitivity at the **canonical** `overall_rip_v7` weights
(0.90 Financial RIP V3 + 0.10 Collector Appeal), against a Financial-only
baseline, n = 22 (current-source state; all 22 sets `financial_rip_v3_rankable`).

Guardrails read from `backend/desirability/scoring_config.OVERALL_RIP_PRODUCTION_GUARDRAILS`,
not restated in the audit script:

```
min_spearman_vs_financial_only    >= 0.95
min_top5_overlap                  >= 0.80
max_mean_absolute_rank_movement   <= 1.5
max_share_moving_5_plus_ranks     <= 0.10
```

| appeal input | ρ vs Fin-only | top-5 | mean move | max move | ≥5 | passes |
|---|---|---|---|---|---|---|
| none (Financial only) | 1.000 | 1.00 | 0.00 | 0 | 0.00 | — |
| **V3 (current production V7)** | 0.9842 | 0.80 | 0.64 | 3 | 0.00 | **YES** |
| CA7 | 0.9673 | 0.80 | 1.09 | 4 | 0.00 | YES |
| V2 | 0.9571 | 0.80 | 1.27 | 4 | 0.00 | YES |
| D only | 0.9571 | 0.80 | 1.27 | 4 | 0.00 | YES |
| `cand_D_additive_c4` | 0.9560 | 0.80 | 1.18 | 5 | 0.05 | YES |
| **`cand_D_additive_c4_damp50`** | **0.9548** | **0.80** | **1.27** | **5** | **0.05** | **YES** |
| `cand_E_h_dominant_c4` | 0.9571 | 0.80 | 1.18 | 5 | 0.05 | YES |
| `cand_G_multiplicative_g4` | 0.9548 | 0.80 | 1.27 | 5 | 0.05 | YES |

**Every candidate passes all four guardrails**, including the recommendation.
Two honest caveats:

1. The recommended candidate's Spearman (0.9548) clears the 0.95 bar by
   0.005 — a thinner margin than V3's 0.9842. That is inherent, not a defect:
   V3 is *further from D*, and D is what disagrees with Financial RIP. Any
   desirability-dominant appeal metric will move Overall RIP more than a
   frequency-dominant one does. Note that plain `D_only` scores 0.9571 on the
   same test, so the candidate is not more disruptive than the construct it is
   built on.
2. Max movement rises from 3 to 5 ranks and the ≥5 share from 0.00 to 0.05
   (one set). Still inside the 0.10 guardrail, but it should be re-measured
   against fresh Financial RIP data before any promotion decision, since the
   Financial half here is current-source state while the appeal half is
   published state.

**No Overall RIP version is proposed, and V7 is unchanged.**

---

## 9. Files changed / artifacts

New, all research-only:

* `backend/research/collector_appeal_v4_candidates.py` — the candidate combination architecture
* `backend/scripts/audit_collector_appeal_v4_candidates.py` — read-only comparative study
* `backend/tests/unit/research/test_collector_appeal_v4_candidates.py` — 55 behavioural tests
* `docs/research/collector_appeal_v4_candidate_study.md` — this document
* `docs/research/collector_appeal_v4_candidate_study.json` — full machine-readable report
* `docs/research/collector_appeal_tables/collector_appeal_v4_candidate_scores.csv` — per-set scores and ranks for every model

Modified: none.

---

## 10. Explicit non-actions

* Collector Appeal **V3 remains canonical** — `COLLECTOR_APPEAL_V3_VERSION`,
  `COLLECTOR_APPEAL_V3_WEIGHTS` and `compute_collector_appeal_v3` are byte-for-byte unchanged
* **Overall RIP V7 unchanged** — `CANONICAL_OVERALL_RIP_VERSION`, `OVERALL_RIP_V7_WEIGHTS`, guardrails all untouched
* CA7 and V2 remain computable and identifiable for rollback diagnostics
* **No snapshots published**; no publication, snapshot-builder or service path imports the candidate module (asserted by test)
* **No simulations rerun** — the only live reads were `SELECT`s against `explore_rip_statistics_latest`
* **No Universal Set Desirability, Pokémon demand score, pull rate, Financial RIP V3 or public frontend label changed**
* **No commit, push, merge or deploy**
* No formula fitted to Ascended Heroes or to market price; no internal weight exposed on any public surface
