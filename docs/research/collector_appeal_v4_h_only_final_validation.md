# Collector Appeal V4 — H-only candidate, final validation

**Status: RESEARCH ONLY.** Collector Appeal V3 remains canonical. Overall RIP V7
remains canonical. No snapshot published, no simulation rerun, no frontend
change, nothing committed, pushed, merged or deployed.

Predecessors:
[`collector_appeal_v4_candidate_study.md`](collector_appeal_v4_candidate_study.md) ·
[`collector_appeal_v4_promotion_validation.md`](collector_appeal_v4_promotion_validation.md)

Reproduce:

```
python -m backend.scripts.audit_collector_appeal_v4_candidates --fetch-financial-rip \
    --json docs/research/collector_appeal_v4_candidate_study.json \
    --csv  docs/research/collector_appeal_tables/collector_appeal_v4_candidate_scores.csv
python -m backend.scripts.audit_collector_appeal_v4_historical_replay \
    --json docs/research/collector_appeal_v4_historical_replay.json
```

---

## 1. H-only candidate frozen

```
key           collector_appeal_v4_candidate_h_only_up4_down2
version       collector_appeal_v4_candidate_h_only_d_baseline_ceil4_floor2_log2_anchors_research_v1
formulaVer    collector_appeal_v4_h_only_centred_asymmetric_modifier_v1
status        research_candidate_frozen_not_canonical
fingerprint   3285067da325679ce92412f240caf70facbf0b7a029ede0594e0ca1befbcb756  (sha256)
```

```
sH = clamp01((log2(H) - log2(1/16)) / (log2(1/4) - log2(1/16)))
   = clamp01((log2(H) + 4) / 2)

     1-in-16 -> 0.0        1-in-8 -> 0.5 (NEUTRAL)        1-in-4 -> 1.0

z  = 2*sH - 1
m  = 4.0*z   if z >= 0        positive ceiling  +4.0
m  = 2.0*z   if z <  0        negative floor    -2.0
CA = clamp(100*D + m, 0, 100)

max pairwise structural advantage = 4.0 - (-2.0) = 6.0 points
```

Inputs are `D` and `H` only. The function signature is
`collector_appeal_v4_candidate_h_only(d, h)` — it does not accept a `p`
argument, so a caller cannot pass dual-path data and believe it was used.

Fingerprint covers: H transform kind, all three H anchors, the blend
(`h_weight=1.0, p_weight=0.0`), neutral point, positive ceiling, downside
damping, negative floor, max pairwise advantage, clamp domain and clamp kind,
monotonicity contract, missing-data policy, and the version identifier. Every
one is verified to move the hash. The version identifier is hashed here (unlike
the canonical fingerprint, which excludes labels) because this study now carries
two frozen models with identical arithmetic — the H-only candidate and the P
ablation twin — and a hash that could not tell them apart would let a stored
score claim the wrong lineage.

**The H70/P30 candidate is not mutated.** Its fingerprint is still
`0f0846a3e0f5bd05…`, pinned by a test, and it remains computable for comparison
and rollback.

**H anchors were not retuned** when P was dropped. Retuning them after seeing
which sets moved would be fitting to a preferred ranking.

### Monotonicity contract

| in | contract |
|---|---|
| **D** | non-decreasing everywhere on [0,1]; **strictly increasing** wherever `100·D + m` lies strictly inside (0,100) |
| **H** | non-decreasing everywhere |
| **P** | not an input |

Saturation regions, named so a future set fails loudly rather than tying:
`D > 0.96` (upper) and `D < 0.02` (lower). **No set in the current cohort is in
either** (max D 0.9548, min D 0.5107) — asserted as a separate data-fact test
that fails the moment one crosses.

---

## 2. Construct validation (published-state cohort, n = 22)

| statistic | H-only candidate |
|---|---|
| Spearman vs D | **0.963** |
| Pearson vs D | **0.987** |
| Spearman vs H | 0.446 |
| Spearman vs current V3 | 0.711 |
| Spearman vs CA7 | 0.980 |
| Spearman vs bounded V2 | 0.976 |
| mean abs rank movement vs D | **1.18** |
| median movement | 1.0 |
| max movement | **5** |
| % moving ≥2 | 0.41 |
| % moving ≥3 | **0.09** |
| % moving ≥5 | 0.045 |
| top-5 overlap vs D | **1.00** |
| bottom-5 overlap vs D | **1.00** |

Reference poles: V2 ρ(D) = 0.991, CA7 0.984, V3 0.589. The candidate sits at
0.963 — desirability-dominant, but with 3.3× V2's practical rank movement.

### Full cohort, sorted by D

| set | D | D rk | H | 1-in-N | sH | mod | CA | CA rk |
|---|---|---|---|---|---|---|---|---|
| Ascended Heroes | 95.48 | 1 | .2338 | 4.3 | .952 | +3.61 | 99.09 | 1 |
| Paldean Fates | 95.33 | 2 | .1791 | 5.6 | .759 | +2.07 | 97.41 | 2 |
| Scarlet and Violet 151 | 93.61 | 3 | .2072 | 4.8 | .864 | +2.91 | 96.53 | 3 |
| Prismatic Evolutions | 93.28 | 4 | .1995 | 5.0 | .837 | +2.70 | 95.98 | 4 |
| Phantasmal Flames | 90.74 | 5 | .2427 | 4.1 | .979 | +3.83 | 94.57 | 5 |
| Paldea Evolved | 90.37 | 6 | .0933 | 10.7 | .289 | −0.84 | 89.53 | 8 |
| Surging Sparks | 88.85 | 7 | .1244 | 8.0 | .496 | −0.01 | 88.84 | 9 |
| Destined Rivals | 87.93 | 8 | .1410 | 7.1 | .587 | +0.70 | 88.62 | 10 |
| Journey Together | 87.46 | 9 | .2117 | 4.7 | .880 | +3.04 | 90.50 | **6** |
| Obsidian Flames | 87.32 | 10 | .1029 | 9.7 | .360 | −0.56 | 86.75 | 12 |
| White Flare | 87.30 | 11 | .0900 | 11.1 | .263 | −0.95 | 86.35 | 13 |
| Mega Evolution | 87.20 | 12 | .1904 | 5.3 | .803 | +2.43 | 89.63 | **7** |
| Paradox Rift | 86.65 | 13 | .1384 | 7.2 | .573 | +0.58 | 87.23 | 11 |
| Stellar Crown | 86.35 | 14 | .1081 | 9.3 | .395 | −0.42 | 85.93 | 14 |
| Temporal Forces | 86.03 | 15 | .0960 | 10.4 | .310 | −0.76 | 85.27 | 16 |
| Black Bolt | 84.01 | 16 | .1254 | 8.0 | .502 | +0.02 | 84.03 | 17 |
| Perfect Order | 81.60 | 17 | .2659 | 3.8 | 1.000 | +4.00 | 85.60 | 15 |
| Twilight Masquerade | 81.18 | 18 | .1384 | 7.2 | .574 | +0.59 | 81.77 | 19 |
| Pitch Black | 79.90 | 19 | .2323 | 4.3 | .947 | +3.58 | 83.48 | 18 |
| Scarlet and Violet Base | 75.60 | 20 | .1029 | 9.7 | .360 | −0.56 | 75.04 | 20 |
| Chaos Rising | 69.89 | 21 | .1803 | 5.5 | .764 | +2.11 | 72.01 | 21 |
| Shrouded Fable | 51.07 | 22 | .0278 | 36.0 | .000 | −2.00 | 49.07 | 22 |

---

## 3. Sets moving ≥3 ranks — both of them

**Mega Evolution: D rank 12 → CA rank 7 (+5)**
D = 87.20, H = 0.1904 (a desirable card about every **5.3 packs**), sH = 0.803,
modifier **+2.43**, CA = 89.63.
Passed: Surging Sparks, Destined Rivals, Obsidian Flames, Paldea Evolved, White
Flare. **Widest D gap crossed: 3.17 points.**
*Why:* D ranks 6–12 are a dense cluster spanning 3.2 points. Mega Evolution has
clearly better desirable-outcome accessibility than the four sets immediately
above it (their sH values are 0.289, 0.360, 0.263, 0.496 — at or below neutral,
so they take small penalties), and a +2.43 bonus against −0.95 to +0.02
penalties clears five places. Five rank places, three D points.

**Journey Together: D rank 9 → CA rank 6 (+3)**
D = 87.46, H = 0.2117 (about every **4.7 packs**), sH = 0.880, modifier
**+3.04**, CA = 90.50. Passed: Surging Sparks, Destined Rivals, Paldea Evolved.
**Widest D gap crossed: 2.91 points.**

**Locality holds.** The widest D gap crossed by any mover is **3.17 points**
against a structural span of 6.0 — every reordering is inside a desirability
neighbourhood, and no low-desirability set travels the leaderboard. Compare V3,
where Pitch Black moves +13 and Paldea Evolved −11. Top-5 and bottom-5 overlap
with the D ordering are both 1.00.

---

## Pairwise case studies

| pair | ΔD | ΔH | modifiers | Δ CA | flips D order? |
|---|---|---|---|---|---|
| Ascended Heroes vs Pitch Black | +15.58 | +0.0015 | +3.61 / +3.58 | +15.61 | no |
| Ascended Heroes vs Perfect Order | +13.88 | −0.0321 | +3.61 / +4.00 | +13.49 | no |
| Ascended Heroes vs Journey Together | +8.02 | +0.0221 | +3.61 / +3.04 | +8.59 | no |
| Mega Evolution vs SV 151 | −6.41 | −0.0168 | +2.43 / +2.91 | −6.90 | no |
| Mega Evolution vs Journey Together | −0.26 | −0.0213 | +2.43 / +3.04 | −0.87 | no |
| Prismatic Evolutions vs SV 151 | −0.34 | −0.0077 | +2.70 / +2.91 | −0.55 | no |
| Phantasmal Flames vs Ascended Heroes | −4.74 | +0.0089 | +3.83 / +3.61 | −4.52 | no |
| Phantasmal Flames vs Prismatic Evolutions | −2.53 | +0.0432 | +3.83 / +2.70 | **−1.40** | no |
| Phantasmal Flames vs Paldean Fates | −4.59 | +0.0636 | +3.83 / +2.07 | **−2.83** | no |

**H flips none of these pairs** — and that is the correct construct behaviour,
not a weakness. In every pair the H advantage runs the *same* way as D or is too
small to overcome the D gap. Where H is doing real work is visible in the gap
*narrowing*: Phantasmal Flames closes 2.53 → 1.40 on Prismatic Evolutions and
4.59 → 2.83 on Paldean Fates, because it delivers a desirable card about every
4.1 packs against their 5.0 and 5.6. Those are live tiebreakers — a slightly
larger accessibility edge would flip them — which is exactly "H settles many
close calls" rather than "H overturns desirability".

Compare V3 on the same pairs: it flips Mega Evolution over SV 151 (a 6.4-point D
gap), Phantasmal Flames over Ascended Heroes (4.7 points) and Phantasmal Flames
over Paldean Fates (4.6 points). The candidate flips none of them.

**Phantasmal Flames is the difficulty check.** Its chase odds are brutal, yet it
receives the cohort's second-largest positive modifier (+3.83). H measures how
often a pack delivers *a* desirable card, not how easy the top card is, so a
jackpot set is not punished for being a jackpot set. No market price was used
anywhere in this section.

---

## 4–6. Historical Overall RIP weight sensitivity

10 compatible snapshots. 5 excluded, all `financial_rip_v2_60_25_15`.
Composition mirrors `weighted_rip.compute_overall_rip_v7` exactly
(`clamp(w_fin·F + w_appeal·A, 0, 100)`, rounded 4dp) with only the weight
varying — a test asserts it reproduces `compute_overall_rip_v7` at 90/10.

Guardrails read from `OVERALL_RIP_PRODUCTION_GUARDRAILS`, never restated.

> **Sample caveat, stated up front.** The 10 dates contain about **6 distinct
> financial configurations**: 08-04/05 are identical, 08-07/08/09 are identical,
> and 08-12/13 are identical. Every aggregate below is really over ~6
> independent states.

### 4. Appeal weight 10% (canonical)

| date | ρ | top-5 | top-7 | top-10 | RBO | mean mv | max | ≥5 | pass | failing |
|---|---|---|---|---|---|---|---|---|---|---|
| 08-04 | 0.9661 | 0.80 | 0.86 | 0.90 | 0.9158 | 0.91 | 5 | 0.05 | YES | |
| 08-05 | 0.9661 | 0.80 | 0.86 | 0.90 | 0.9158 | 0.91 | 5 | 0.05 | YES | |
| 08-06 | **0.9345** | **0.60** | 0.57 | 0.90 | 0.8651 | 1.36 | 6 | **0.14** | NO | ρ, top5, ≥5 |
| 08-07 | **0.9424** | **0.60** | 0.71 | 0.90 | 0.7441 | 1.36 | 7 | 0.05 | NO | ρ, top5 |
| 08-08 | **0.9424** | **0.60** | 0.71 | 0.90 | 0.7441 | 1.36 | 7 | 0.05 | NO | ρ, top5 |
| 08-09 | **0.9424** | **0.60** | 0.71 | 0.90 | 0.7441 | 1.36 | 7 | 0.05 | NO | ρ, top5 |
| 08-10 | 0.9593 | 1.00 | 0.71 | 0.90 | 0.8398 | 1.27 | 5 | 0.05 | YES | |
| 08-11 | 0.9650 | 1.00 | 0.86 | 0.90 | 0.8981 | 1.09 | 5 | 0.05 | YES | |
| 08-12 | 0.9571 | 0.80 | 0.86 | 0.90 | 0.9223 | 1.18 | 5 | 0.05 | YES | |
| 08-13 | 0.9571 | 0.80 | 0.86 | 0.90 | 0.9223 | 1.18 | 5 | 0.05 | YES | |

**6/10 pass (0.60).** ρ min/med/max **0.9345 / 0.9571 / 0.9661**.
Worst date **08-06**, failing ρ by **−0.0155**, top-5 by −0.20, ≥5-share by −0.036.

### 5. Appeal weight 7.5%

| date | ρ | top-5 | top-7 | RBO | mean mv | max | ≥5 | pass | failing |
|---|---|---|---|---|---|---|---|---|---|
| 08-04 | 0.9729 | 0.80 | 0.86 | 0.9268 | 0.82 | 5 | 0.05 | YES | |
| 08-05 | 0.9729 | 0.80 | 0.86 | 0.9268 | 0.82 | 5 | 0.05 | YES | |
| 08-06 | 0.9503 | **0.60** | 0.71 | 0.8910 | 1.09 | 6 | 0.09 | NO | top5 |
| 08-07 | 0.9526 | **0.60** | 0.71 | 0.7836 | 1.09 | 7 | 0.05 | NO | top5 |
| 08-08 | 0.9526 | **0.60** | 0.71 | 0.7836 | 1.09 | 7 | 0.05 | NO | top5 |
| 08-09 | 0.9526 | **0.60** | 0.71 | 0.7836 | 1.09 | 7 | 0.05 | NO | top5 |
| 08-10 | 0.9695 | 1.00 | 0.71 | 0.8507 | 1.09 | 4 | 0.00 | YES | |
| 08-11 | 0.9842 | 1.00 | 0.86 | 0.9471 | 0.64 | 3 | 0.00 | YES | |
| 08-12 | 0.9797 | 0.80 | 0.86 | 0.9397 | 0.64 | 4 | 0.00 | YES | |
| 08-13 | 0.9797 | 0.80 | 0.86 | 0.9397 | 0.64 | 4 | 0.00 | YES | |

**6/10 pass (0.60).** ρ min/med/max **0.9503 / 0.9712 / 0.9842**.
Worst date **08-06**, ρ margin **+0.000311** — passes, but barely.
**Spearman and ≥5-share are cleared on every date. The only failing guardrail is
top-5 overlap.**

### 6. Appeal weight 5%

| date | ρ | top-5 | top-7 | RBO | mean mv | max | ≥5 | pass | failing |
|---|---|---|---|---|---|---|---|---|---|
| 08-04 | 0.9853 | 1.00 | 0.86 | 0.9468 | 0.55 | 4 | 0.00 | YES | |
| 08-05 | 0.9853 | 1.00 | 0.86 | 0.9468 | 0.55 | 4 | 0.00 | YES | |
| 08-06 | 0.9695 | **0.60** | 0.86 | 0.9147 | 0.82 | 5 | 0.05 | NO | top5 |
| 08-07 | 0.9684 | **0.60** | 0.86 | 0.7976 | 0.82 | 6 | 0.05 | NO | top5 |
| 08-08 | 0.9684 | **0.60** | 0.86 | 0.7976 | 0.82 | 6 | 0.05 | NO | top5 |
| 08-09 | 0.9684 | **0.60** | 0.86 | 0.7976 | 0.82 | 6 | 0.05 | NO | top5 |
| 08-10 | 0.9763 | 1.00 | 0.71 | 0.9035 | 0.91 | 4 | 0.00 | YES | |
| 08-11 | 0.9955 | 1.00 | 1.00 | 0.9678 | 0.27 | 2 | 0.00 | YES | |
| 08-12 | 0.9864 | 0.80 | 0.86 | 0.9542 | 0.45 | 3 | 0.00 | YES | |
| 08-13 | 0.9864 | 0.80 | 0.86 | 0.9542 | 0.45 | 3 | 0.00 | YES | |

**6/10 pass (0.60).** ρ min/med/max **0.9684 / 0.9808 / 0.9955**.
Worst date **08-07**, ρ margin **+0.0184**. Only top-5 fails.

### The decisive cross-weight fact

| | 10% | 7.5% | 5% |
|---|---|---|---|
| pass rate | 6/10 | 6/10 | 6/10 |
| ρ guardrail breached? | **yes (2 states)** | no | no |
| ≥5-share breached? | **yes (1 state)** | no | no |
| top-5 breached? | yes (2 states) | yes (2 states) | yes (2 states) |
| worst ρ margin | −0.0155 | +0.0003 | +0.0184 |

**The top-5 failures are weight-invariant.** They do not improve at all between
10% and 5%. Only the Spearman and ≥5-share breaches respond to weight, and both
are cleared at 7.5%.

---

## 7. Guardrail diagnosis

### Who actually leaves the financial top 5

At the canonical 10%, on the subject candidate:

| date | top-5 | top-7 | RBO | mean move within fin. top 5 | leavers |
|---|---|---|---|---|---|
| 08-04 / 05 | 0.80 | 0.86 | 0.9158 | 0.6 | SV Base #4→#7 (still top 7) |
| 08-06 | 0.60 | 0.57 | 0.8651 | 2.2 | SV Base #4→#9, **Shrouded Fable #5→#11** |
| 08-07/08/09 | 0.60 | 0.71 | 0.7441 | 2.8 | **Shrouded Fable #4→#11**, SV Base #5→#9 |
| 08-12 / 13 | 0.80 | 0.86 | 0.9223 | 0.4 | Twilight Masquerade #5→#7 (still top 7) |

**The recurring cause is Shrouded Fable.** D = 51.07 — the lowest in the cohort
by **19 points** (next lowest is Chaos Rising at 69.89) — while being financially
ranked #4–5. Every appeal metric, including plain `D_only`, pushes it out of the
top 5. Even at 5% weight it still lands #10.

That is Collector Appeal doing precisely its job: a set that is financially
efficient and collector-undesirable *should* rank lower on a blended score than
on a purely financial one. It is not distortion.

### Is the gate detecting distortion, or quantization? Both, on different dates.

* **Real distortion (08-07/08/09):** top-5 0.60, top-7 0.71, RBO **0.7441**, mean
  movement inside the financial top 5 = 2.8 places. All three diagnostics agree
  the orderings genuinely differ. The gate is right to fire.
* **Quantization (08-06 at 5% weight):** top-5 **0.60** — a fail — while top-7 is
  0.86 and RBO is **0.9147**. Here the gate fires on a leaderboard the
  rank-weighted diagnostics call highly similar.
* **Sitting on the bar:** on 08-04/05 and 08-12/13 the value is exactly 0.80 —
  the threshold — with a single set moving 2–3 places and staying in the top 7.
  Production V3 sits at exactly 0.80 (margin 0.00) on 4 of the 6 dates it passes.

**The mechanism.** `top5Overlap` over a 22-set cohort takes only the values
0.0/0.2/0.4/0.6/0.8/1.0. The threshold 0.80 therefore means literally "at most
one of five sets may leave the top 5, no matter where it lands". A set moving
#5 → #6 costs the same 0.20 as a set moving #5 → #22. There is no room between
"pass" and "fail" for "moved one place".

Top-7 and top-10 are less quantized (steps of 0.143 and 0.10) and RBO is
continuous. Top-10 in particular is near-flat (0.90–1.00 at every weight),
confirming that nothing is travelling far.

### What each alternative adds

| metric | adds | costs |
|---|---|---|
| top-5 (current) | direct, legible "did the headline five change?" | 0.20 quantization; one set = pass/fail; blind to distance |
| top-7 | finer steps (0.143); distinguishes "left the 5 but stayed near" | still set-membership; still arbitrary k |
| top-10 | very stable; good "nothing travelled far" check | too insensitive to be a gate — 0.90+ on every date and weight |
| **RBO (p=0.9)** | continuous; weights depth; separates near-misses from real demotions; comparable across cohort sizes | research-only implementation, no production history, needs a threshold nobody has calibrated |

RBO definition used (research-only, no repo implementation existed):
`RBO_n = Σ_{d=1..n} p^(d-1)·A_d / Σ_{d=1..n} p^(d-1)` where
`A_d = |top_d(base) ∩ top_d(variant)| / d`. This is the depth-normalized form —
the original Webber/Moffat/Zobel sum is over infinite lists, and truncating it at
n leaves it bounded by `1 − p^n`, so two identical 22-item rankings would score
0.90 instead of 1.0. Dividing by the same partial sum removes that artifact.

---

## 8. Practical influence: 10 vs 7.5 vs 5

Subject candidate, means across the 10 dates:

| weight | pass | ρ med | mean mv | med mv | max mv | n ≥1 | n ≥2 | n ≥3 | n ≥5 | top-5 | RBO |
|---|---|---|---|---|---|---|---|---|---|---|---|
| **10%** | 6/10 | 0.9571 | 1.20 | 0.65 | 5.7 | **12.6** | **6.2** | **3.7** | **1.2** | 0.76 | 0.851 |
| **7.5%** | 6/10 | 0.9712 | 0.90 | 0.30 | 5.2 | 10.1 | 4.7 | 2.5 | 0.7 | 0.76 | 0.877 |
| **5%** | 6/10 | 0.9808 | 0.65 | 0.10 | 4.3 | 7.9 | 3.6 | 1.2 | 0.4 | 0.80 | 0.898 |

Step-by-step loss of differentiation:

| | n ≥1 | n ≥2 | **n ≥3** | n ≥5 |
|---|---|---|---|---|
| 10 → 7.5 | −20% | −24% | **−32%** | −42% |
| 7.5 → 5 | −22% | −23% | **−52%** | −43% |

The `n ≥1` and `n ≥2` costs are roughly linear in the weight, as expected. The
**meaningful** differentiation — sets moving 3 or more places — behaves
differently: going 10 → 7.5 costs a third of it, going 7.5 → 5 costs **half of
what remains**. At 5% the metric moves barely one set 3+ places per date.

Financial dominance is preserved at all three: median ρ against Financial-only is
0.957 / 0.971 / 0.981, and top-10 overlap is 0.90–1.00 throughout.

---

## 9. Collector Appeal verdict

# CA CONSTRUCT PROMOTION READY

Judged only on whether the H-only candidate validly represents Collector Appeal:

* **Desirability dominance holds.** ρ(CA, D) = 0.963, Pearson 0.987. Strictly
  increasing in D off the clamp; non-decreasing everywhere; neutral H returns
  exactly D.
* **Structure is a tiebreaker, not a pillar.** Stated span of 6.0 points,
  verified by exhaustive search. Two sets move ≥3 ranks; the widest D gap any
  mover crosses is 3.17 points against a 6.0 span. Top-5 and bottom-5 overlap
  with D are both 1.00.
* **Anchors, extrema and bounds all verified exactly** (1-in-16 → 0, 1-in-8 →
  0.5, 1-in-4 → 1; −2.0 / 0 / +4.0; [0,100]).
* **No saturation.** No ranked set is within the clamp region, and a data-fact
  test fails loudly if one ever is.
* **Difficulty is not punished.** Phantasmal Flames takes +3.83.
* **No pathological external behaviour.** ρ vs sealed pack price = **+0.3145**,
  against D at +0.4466 — same sign, slightly attenuated, exactly as expected for
  "D plus a non-price term". Production V3's **−0.19** sign reversal does not
  reappear. (Diagnostic only; nothing fitted to price. Current-source state.)
* **No mathematical defect found.** No new family was opened.

The Overall RIP weight question is explicitly *not* a reason to block: it is a
property of the blend, and it is answered separately below.

---

## 10. Overall RIP weighting verdict

# MOVE TO 7.5%

**Provisional — see the re-measurement gate below.**

Why 7.5%:

* It is the **largest** tested weight that clears the Spearman and ≥5-share
  guardrails on **every** compatible date. 10% breaches both (ρ 0.9345 and
  ≥5-share 0.14 on 08-06).
* Dropping further to 5% buys margin but costs disproportionately: the 7.5 → 5
  step removes **52%** of the remaining 3+-rank differentiation, versus 32% for
  10 → 7.5. The lowest weight is not automatically preferred, and here it is
  measurably the worse trade.
* It does not fix the top-5 breach — but **nothing does**. Those failures are
  weight-invariant and are a guardrail problem, not a weight problem (§7).
* Financial dominance is unambiguous: 92.5% financial, median ρ 0.971 against
  Financial-only, top-10 overlap 0.90–1.00.

**The honest weakness.** On the worst state (08-06) the Spearman margin at 7.5%
is **+0.000311**. That is a pass, but it is not robust, and the effective sample
is ~6 distinct financial configurations over ten days.

**Re-measurement gate before this becomes canonical config:** re-run the replay
once ~20 further *distinct* financial states have accumulated. If the 7.5% worst
margin stays positive, adopt 7.5%. If it goes negative on any new state,
**fall back to 5%**, which currently holds a +0.0184 worst margin and still moves
~8 sets a day.

---

## 11. Guardrail verdict

# REVIEW RECOMMENDED

* **Which guardrail:** `min_top5_overlap ≥ 0.80`. The other three are fine —
  Spearman and ≥5-share discriminate usefully between weights, and mean movement
  is never close to its 1.5 bar.
* **Nature of the problem: both metric choice and k-size quantization, and they
  compound.** Over a 22-set cohort `top5Overlap` takes only six values, so the
  0.80 threshold means "at most one of five may leave, regardless of where it
  lands" — #5→#6 and #5→#22 cost the same 0.20. Production V3 sits *exactly* on
  0.80 (margin 0.00) on 4 of the 6 dates it passes, so a single set moving one
  place is a pass/fail event for the shipping model too.
* **Evidence it sometimes fires wrongly:** 08-06 at 5% weight — top-5 = 0.60
  (fail) while top-7 = 0.86 and RBO = 0.9147 (highly similar orderings).
* **Evidence it sometimes fires correctly:** 08-07/08/09 — top-5 = 0.60, top-7 =
  0.71, RBO = 0.7441, mean movement inside the financial top 5 = 2.8 places. Real
  divergence, and the gate is right.
* **More informative alternative:** RBO at p = 0.9 as the hard gate — continuous,
  depth-weighted, cohort-size comparable — with top-7 as a simpler option if a
  set-overlap metric is preferred for legibility. Top-10 is too insensitive to
  gate on.
* **Should top-5 remain?** **Yes, as a secondary warning.** It answers a question
  a reader actually asks ("did the headline five change?") in a form anyone can
  check by eye. What it should stop being is the hard gate, because its
  resolution is coarser than the differences it is being asked to adjudicate.

Nothing was implemented. No canonical guardrail changed.

---

## 12. Minimal cutover plan — NOT EXECUTED

Only the CA construct is promotion-ready; the weight change is provisional and
should be a **separate** cutover after the re-measurement gate.

### Phase A — Collector Appeal V4 canonical (self-contained)

| # | file | change |
|---|---|---|
| A1 | `backend/desirability/collector_appeal.py` | add `COLLECTOR_APPEAL_V4_VERSION`, `COLLECTOR_APPEAL_V4_FORMULA_VERSION`, the anchor/ceiling/floor constants, `compute_collector_appeal_v4(d, h)`, `collector_appeal_v4_decomposition`, `collector_appeal_v4_public_identity`, `COLLECTOR_APPEAL_V4_DIAGNOSTICS_KEY`. **Leave V3, V2, CA7 untouched and computable.** |
| A2 | `backend/desirability/collector_appeal_fingerprint.py` | extend `collect_assumptions()` with the V4 block. This **invalidates every stored fingerprint** — intended, and the reason A6 exists. |
| A3 | `backend/desirability/collector_appeal_rollout.py` | point the rollout gate at V4 |
| A4 | `backend/db/services/collector_appeal_service.py` | compute and store V4 under its own diagnostics key; keep resolving inputs by declared version, never field position |
| A5 | `backend/desirability/public_rip_contract_v7.py`, `backend/db/services/public_rip_publication_contract.py` | accept `collector_appeal_v4_*` as the appeal input version |
| A6 | `backend/db/services/explore_rip_statistics_service.py` | read V4 |
| A7 | `backend/scripts/pokemon_explore_rankings_publisher.py`, `backend/scripts/refresh_stale_public_snapshots.py`, `backend/scripts/run_daily_opening_publication.py` | republish with V4; snapshot rebuild required because A2 marks all rows stale |
| A8 | `frontend/components/explore/collectorAppealBreakdownSelector.mjs` | **two factors, not three** — drop the `dualPathDepth` row (lines ~143, ~213). **Required, not cosmetic:** each factor "carries its OWN availability", so a V4 payload with no P would render a permanently greyed "Dual-Path Depth —" card rather than fail loudly. |
| A9 | `frontend/components/explore/CollectorAppealBreakdown.jsx` | render two factors |

**No production frontend file pins a Collector Appeal version string.**
`canonicalRipV7.mjs`, `rankingsSort.mjs` and `ripDecisionModel.mjs` resolve the
appeal block structurally and pass whatever version the payload declares, so
Phase A needs no frontend version edit — only the structural A8/A9 change. The
`collector_appeal_v3` literals live exclusively in test fixtures.

Tests to add/update: `backend/tests/unit/desirability/test_collector_appeal_v3_and_overall_rip_v7.py`
(add a V4 sibling), `test_collector_appeal_fingerprint.py`,
`test_collector_appeal_service.py`, `test_collector_appeal_rollout.py`,
`test_public_rip_publication_contract.py`, and the three frontend files carrying
`collector_appeal_v3` fixtures:
`CollectorAppealBreakdown.contract.test.mjs:82`,
`canonicalRipV7.contract.test.mjs:56`,
`ripHeroScoreMode.test.mjs:128,136` (`collector_appeal_v3_unavailable`).

**Dual-Path Depth is not deleted.** `compute_dual_path_depth` and
`DUAL_PATH_DEPTH_VERSION` stay; P simply stops being an appeal input.

### Phase B — Overall RIP weight, ONLY after the re-measurement gate

| # | file | change |
|---|---|---|
| B1 | `backend/desirability/scoring_config.py` | add `OVERALL_RIP_V8_VERSION` + `OVERALL_RIP_V8_WEIGHTS = {financial: 0.925, collector_appeal: 0.075}`; repoint `CANONICAL_OVERALL_RIP_VERSION`. **A new identifier, not a repointed V7** — V7's string names its own weights. |
| B2 | `backend/desirability/weighted_rip.py` | `compute_overall_rip_v8`; leave V7/V6/V5 intact |
| B3 | `backend/db/migrations/06X_update_public_rip_rpc_to_v8.sql` | new RPC version, modelled on `061_update_public_rip_rpc_to_v7.sql` |
| B4 | `backend/db/services/public_rip_publication_contract.py`, `explore_rip_statistics_service.py` | serve V8 |
| B5 | `frontend/components/explore/canonicalRipV7.mjs` | naming only — the module is named for V7 but reads the payload's declared version, so this is a rename for honesty, not a functional change |

Tests: `test_public_rip_rpc_v7_migration_sql.py` (V8 sibling),
`canonicalRipV7.contract.test.mjs`, `test_scheduled_publication_contract.py`.

The full backend surface was enumerated by grepping every non-test file for
`COLLECTOR_APPEAL_V3_VERSION|compute_collector_appeal_v3|collector_appeal_v3`;
A1–A7 plus migration 061 (the model for B3) account for every hit.

**Phase B must not be bundled with Phase A.** Phase A changes what Collector
Appeal means; Phase B changes how much it counts. Shipping both at once makes
any post-cutover leaderboard movement unattributable.

---

## 13. Files changed

New:
* `docs/research/collector_appeal_v4_h_only_final_validation.md` (this file)

Modified:
* `backend/research/collector_appeal_v4_candidates.py` — H-only frozen block (key, version, anchors, ceiling/floor, contract, assumptions, fingerprint, identity), registered in `candidate_registry`
* `backend/scripts/audit_collector_appeal_v4_historical_replay.py` — appeal-weight grid, canonical composition helper, RBO, boundary diagnostics, top-7/10, per-weight summaries
* `backend/scripts/audit_collector_appeal_v4_candidates.py` — `significant_movers`, three new case-study pairs, H-only identity in the report
* `backend/tests/unit/research/test_collector_appeal_v4_candidates.py` — 88 tests (was 68)
* `docs/research/collector_appeal_v4_candidate_study.json`, `collector_appeal_v4_historical_replay.json`, `collector_appeal_tables/collector_appeal_v4_candidate_scores.csv` — regenerated

Unchanged: every canonical module.

---

## 14. Test results

* `backend/tests/unit/research/test_collector_appeal_v4_candidates.py` — **88 passed**
* `backend/tests/unit/research` + `backend/tests/unit/desirability` — **1902 passed**
* Wider `backend/tests/unit` — 49 pre-existing failures, unrelated and unchanged
  (identical count with all V4 files removed from the tree)

---

## 15. Explicit non-actions

* **Collector Appeal V3 remains canonical** — version, weights and function unchanged
* **Overall RIP V7 remains canonical** — version, weights and guardrails unchanged
* **No production snapshots published**
* **No simulations rerun** — the only database access was `SELECT`s against
  `explore_rip_statistics_latest` and `pokemon_public_rip_leaderboard_*`
* **No frontend changes**
* **No deploy, no merge, no push, no new commit**
* P was not reintroduced; Universal Set Desirability, Pokémon demand scores,
  pull-rate models and Financial RIP V3 are untouched; nothing was fitted to
  market price or to preferred rankings; H anchors were not retuned; Collector
  Appeal was not weakened to satisfy any Overall RIP correlation
