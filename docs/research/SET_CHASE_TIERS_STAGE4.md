# Set Chase Efficiency — Stage IV: Objective, Percentage-Based Chase Tiers

**Tier definition: `PERCENTILE_PLUS_ECONOMIC_FLOOR_SUPPORTED`**
**Depth: `CHASE_DEPTH_VALIDATED_AS_SEPARATE_DIMENSION`**
**Chase EV: `CHASE_EV_SUPPORTED_AS_TIER_SPECIFIC_METRIC`**
**Beat-the-Buy: `BTB_USEFUL_AS_INTERPRETABLE_COMPANION`**

> The single most important finding is a falsification, not a confirmation:
> **the percentile is inert.** Once an economic floor of ≥2× pack cost is
> applied, the percentile stops binding in almost every set, and at ≥5× it never
> binds at all. The rule that passes every stress test is an *economic
> threshold* wearing a percentile costume. The percentile survives only as a
> guardrail cap, and the honest name for what is supported is
> "percentile + economic floor, where the floor does the work."

| | |
|---|---|
| Branch | `fix/public-rankings-entitlement-regression` |
| Market date | 2026-08-28 |
| Cohort | 21 of 22 simulation-supported sets (Destined Rivals excluded, defect unchanged) |
| Packs | 1,000,000 per set, seeded and reproducible |
| Candidates | 65 single-tier rules × 62 two-tier systems |
| Temporal | 8 weekly snapshots, 2026-07-03 → 2026-08-28 |
| Artifact | `docs/research/set_chase_tiers_stage4.json` |
| Production impact | **None.** No Financial RIP, Overall RIP, ranking, API, snapshot, schema or UI changed. |

```
python -m backend.scripts.build_chase_tier_research --packs 1000000
python -m backend.scripts.report_chase_tier_research
python -m pytest backend/tests/unit/research/                     # 179 passed
```

---

## Phase 0–1 — Baseline and authority

Branch confirmed `fix/public-rankings-entitlement-regression`, HEAD `573c1a1` at start,
no merge/rebase/cherry-pick, nothing staged. Stage I–III tests re-run first: **131 passed**.
Cohort re-verified at 21/22; **Destined Rivals still excluded** — its latest run
(`2925570c`, 2026-08-29) still has no `simulation_run_summary` row while
`explore_rip_statistics_latest` points at a different healthy run. Unchanged since Stage II
and left for separate remediation.

Prior conclusions preserved and not revisited: the aggregate Set CE formula degenerates
toward EV; BTB avoids that degeneracy but is closely related to Chase EV Return; HHI is a
depth statistic and is **not** allowed to select a tier anywhere in this stage; the
human-labeling framework is retained intact as optional future validation infrastructure
and was not required here.

---

## Phase 2 — Eligible universe, and a data defect found

| Set | drawable | eligible | excluded | pack $ | median $ | q75 $ | top $ |
|---|---:|---:|---:|---:|---:|---:|---:|
| Ascended Heroes | 468 | 459 | 9 | 13.79 | 0.48 | 1.25 | 1052.30 |
| Prismatic Evolutions | 448 | 447 | 1 | 14.86 | 0.33 | 1.40 | 1472.79 |
| Paradox Rift | 428 | 428 | 0 | 7.56 | 0.20 | 0.43 | 120.02 |
| White Flare | 405 | 405 | 0 | 13.53 | 0.46 | 10.79 | 567.98 |
| Scarlet and Violet 151 | 361 | 361 | 0 | 29.81 | 0.28 | 1.32 | 373.61 |
| Paldean Fates | 326 | 324 | 2 | 23.11 | 0.62 | 4.16 | 964.98 |
| Phantasmal Flames | 214 | 214 | 0 | 11.08 | 0.20 | 0.28 | 703.07 |
| Shrouded Fable | 168 | 162 | 6 | 8.91 | 0.22 | 0.76 | 74.80 |

**A new data defect surfaced.** The Stage-III uniqueness invariant, applied here to the
simulator's own entity universe, failed for three sets: eligible printings exceeded
distinct `(set_id, card_variant_id)` by 1 (Perfect Order), 1 (SV Base Set) and 6
(Shrouded Fable).

Cause: `EVRInputPreparationService` echoes the **base** variant id into
`reverse_variant_id` for cards with no separate reverse printing, and the simulator still
registers a reverse-column sampling entity for some of those rows. Two economically
distinct entities then claim the same tradeable id at different prices — a card that would
appear twice in one tier at two prices.

Handled with an explicit exclusion (`ambiguous_variant_identity_duplicate`): the
base-column entity keeps the id, the reverse-column claimant is dropped and reported.
**8 entities of 7,530.** Deliberately Stage-IV local — repairing it in the shared
`entity_identities` would change Stage-I/II results and leave their published artifacts
inconsistent with the code that produced them. Logged as a follow-up.

Note how low the median price is (\$0.19–\$0.62 in most sets). This is why
median-anchored rules fail later: the median is a bulk common.

---

## Phase 3 — Pure card-count percentile: **falsified**

`*` marks a tier whose cheapest member is worth **less than a single pack**.

| Set | 2.5% | 5% | 7.5% | 10% | 15% | 20% | pack $ |
|---|---|---|---|---|---|---|---:|
| Ascended Heroes | 12/\$83 | 23/\$41 | 35/\$8* | 46/\$6* | 69/\$3* | 92/\$2* | 13.79 |
| Scarlet and Violet 151 | 10/\$68 | 19/\$24* | 28/\$15* | 37/\$8* | 55/\$3* | 73/\$2* | 29.81 |
| Obsidian Flames | 11/\$12 | 21/\$3* | 31/\$1* | 41/\$1* | 61/\$0* | 82/\$0* | 10.16 |
| Shrouded Fable | 5/\$49 | 9/\$32 | 13/\$27 | 17/\$22 | 25/\$13 | 33/\$4* | 8.91 |
| White Flare | 11/\$47 | 21/\$32 | 31/\$24 | 41/\$19 | 61/\$16 | 81/\$13* | 13.53 |

**Sets whose percentile tier dips below one pack price: 0/21 at 2.5%, 6/21 at 5%,
12/21 at 7.5%, 16/21 at 10%, 18/21 at 15%, 21/21 at 20%.**

At 20% *every set in the cohort* declares cards worth less than a single pack to be
chases. Obsidian Flames reaches \$0.xx cards. This is the Case-A pathology measured on
real data, and it is fatal to percentile-only tiers above 2.5%.

**Rounding is not a detail.** Across the 126 (set × percentile) combinations, **floor
differs from ceil in 93.7%** and round differs from ceil in 54.8%. Ceil is used
throughout, clamped to a 1-card minimum; the clamp never actually fired (these sets are
all large enough), but `floor(0.025 × 30) = 0` makes it mandatory for any smaller set.

---

## Phase 4 — Percentile × economic floor: **the percentile is inert**

Median selected K across the 21 sets; `(Ne)` = N sets produced an empty tier:

| percentile | no floor | ≥1×C | ≥2×C | ≥3×C | ≥5×C | ≥10×C |
|---|---:|---:|---:|---:|---:|---:|
| top 2.5% | 10 | 10 | 9 | 7 | 5 | 2 (2e) |
| top 5% | 19 | 17 | 12 | 9 | 5 | 2 (2e) |
| top 7.5% | 28 | 19 | 12 | 10 | 5 | 2 (2e) |
| top 10% | 37 | 19 | 12 | 10 | 5 | 2 (2e) |
| top 15% | 55 | 24 | 12 | 10 | 5 | 2 (2e) |
| top 20% | 73 | 24 | 12 | 10 | 5 | 2 (2e) |

Read down the ≥5×C column: **K is 5 regardless of whether the percentile is 5% or 20%.**

### Why, exactly

Both constraints select a **prefix** of the value-sorted list, so their intersection is
simply the shorter prefix. Which one binds (percentile / floor / tie, out of 21 sets):

| floor | 2.5% | 5% | 7.5% | 10% | 15% | 20% |
|---|---|---|---|---|---|---|
| ≥1×C | **21**/0/0 | 15/6/0 | 8/12/1 | 5/16/0 | 3/18/0 | 0/**21**/0 |
| ≥2×C | 17/3/1 | 7/12/2 | 1/20/0 | 1/20/0 | 0/**21**/0 | 0/**21**/0 |
| ≥3×C | 11/8/2 | 1/19/1 | 0/20/1 | 0/**21**/0 | 0/**21**/0 | 0/**21**/0 |
| ≥5×C | 5/13/3 | 0/**21**/0 | 0/**21**/0 | 0/**21**/0 | 0/**21**/0 | 0/**21**/0 |
| ≥10×C | 0/**21**/0 | 0/**21**/0 | 0/**21**/0 | 0/**21**/0 | 0/**21**/0 | 0/**21**/0 |

**At ≥5×C the percentile never binds for any percentile at or above 5%.** The only regime
where both constraints genuinely participate is a *tight* percentile (2.5%) with a
*modest* floor (1–3×C).

Confirmed structurally: the **62 candidate systems collapse to 39 distinct cohort-wide
outcomes**. Eight systems — `B_pct_floor`, `D_wide`, `S_c5f5_e15f2`, `S_c7.5f5_e15f2`,
`S_c10f5_e20f2` and others — produce *byte-identical* tier membership across all 21 sets.
Eleven more collapse together at ≥10×C.

---

## Phase 6/7 — Price-distribution and relative-to-top families

| Rule | med K | min K | max K | med min value | sets below pack price |
|---|---:|---:|---:|---:|---:|
| log_zscore ≥2 | 57 | 4 | 100 | \$0.91 | **19** |
| log_zscore ≥3 | 40 | 1 | 83 | \$1.68 | **17** |
| ≥10× median | 52 | 21 | 127 | \$2.34 | **21** |
| ≥25× median | 31 | 12 | 96 | \$6.09 | **18** |
| ≥5× q75 | 36 | 8 | 79 | \$1.88 | **18** |
| ≥10% of top card | 10 | 2 | 36 | \$30.51 | 2 |
| ≥25% of top card | 4 | 2 | 20 | \$84.35 | **0** |
| ≥33% of top card | 4 | 1 | 14 | \$135.64 | **0** |
| ≥50% of top card | 2 | 1 | 8 | \$171.51 | **0** |

**Price-distribution rules are falsified.** Anchoring to the median fails because the
median card costs \$0.20 — ten times a bulk common is still a bulk common. Every
median/quartile/z-score variant declares sub-pack cards to be chases in 16–21 of 21 sets,
and selects up to 127 cards.

**Relative-to-top is economically clean but structurally fragile.** It never dips below
pack price at ≥25%, is perfectly scale-invariant, and has the *lowest* size-dependence in
the study (|ρ| = 0.056). But it has the **worst independent-shock stability of any family
(Core Jaccard 0.929 at ±10%, 0.846 at ±20%)** and collapses on hero sets exactly as
predicted: on the synthetic hero case (\$900 hero, \$180 genuine second chase) it selects
1 card at 33%, 1 at 25%, 2 at 20% and 5 at 10% — the answer swings 5× on where a single
outlier happens to sit. On real hero sets it gives Phantasmal Flames a 2-card Core and
Paldean Fates a **1-card** Core.

---

## Phase 9 — Price-shock stability

Mean Core Jaccard:

| System | ind ±2% | ind ±5% | ind ±10% | ind ±20% | joint ±10% | cost ±10% | cost ±20% |
|---|---:|---:|---:|---:|---:|---:|---:|
| A_pct_only | 0.986 | 0.973 | 0.944 | 0.902 | **1.000** | **1.000** | **1.000** |
| B_pct_floor | 0.992 | 0.975 | 0.953 | 0.901 | 0.958 | 0.945 | 0.895 |
| C_tight | 0.994 | 0.981 | **0.962** | 0.910 | 0.968 | 0.959 | 0.923 |
| Z_logz | 0.986 | 0.969 | 0.959 | 0.929 | 1.000 | 1.000 | 1.000 |
| Z_top | 0.988 | 0.962 | **0.929** | **0.846** | 1.000 | 1.000 | 1.000 |

Every family is stable enough under ordinary noise (≥0.93 at ±10%). The interesting column
is **pack-cost shock**: percentile-only and scale-free rules score a perfect 1.000 because
they cannot see pack cost at all. **That immunity is a defect, not a virtue** — if packs
get 20% more expensive, what qualifies as an economically meaningful chase genuinely
should change. Floor rules move (0.945 / 0.895), which is the correct response.

---

## Phase 10 — Temporal stability (8 weekly snapshots, 2026-07-03 → 2026-08-28)

| System | consec. Core Jaccard | endpoint Jaccard | Core K min | Core K max | Core→Ext | Ext→non |
|---|---:|---:|---:|---:|---:|---:|
| A_pct_only | 0.951 | 0.921 | 9 | 23 | 65 | 155 |
| **B_pct_floor** | **0.964** | 0.860 | 1 | 18 | 26 | 42 |
| C_tight | 0.967 | 0.879 | 1 | 12 | 20 | 43 |
| Z_logz | **0.898** | 0.796 | **0** | **85** | 187 | 242 |
| Z_median | 0.942 | 0.907 | 10 | 100 | 129 | 143 |
| Z_top | 0.962 | 0.892 | 1 | 15 | 20 | 23 |

Floor systems hold ~0.96 week to week. `Z_logz` reaches a **Core of zero** at some date
and 85 at another — disqualifying on its own.

Per-set detail for system B shows where churn concentrates: five sets never move at all
(Mega Evolution, Obsidian Flames, Paldean Fates, Phantasmal Flames, Twilight Masquerade —
endpoint Jaccard 1.000), while **Scarlet and Violet 151 has the worst endpoint Jaccard in
the cohort at 0.500**, its Core oscillating between 1 and 2 cards. Surging Sparks is next
at 0.571. Both are cases where the Core is so small that a single card crossing the
threshold halves the tier.

Chase EV Return drifted downward almost everywhere over the window (Ascended Heroes
0.424 → 0.352, Pitch Black 0.402 → 0.296), i.e. the market softened; tier *membership*
stayed far more stable than tier *economics*, which is the desired behaviour.

**Limitation, stated rather than approximated:** any-hit probability and Beat-the-Buy were
not recomputed per date — each distinct membership costs a pass over a million pack draws.
Chase EV Return *is* exact per date, via the linear identity
`Chase EV = Σ E[copies per pack] × price`.

---

## Phase 11 — Set-size robustness, and whether guardrails are needed

| | Spearman(eligible size, Core K) |
|---|---:|
| top 5% only | **+0.992** |
| top 5% AND ≥2×C | +0.706 |
| system B (top 5% AND ≥5×C) | **+0.165** |
| C_tight | +0.225 |
| Z_top | +0.056 |

A pure percentage is pinned to set size *by construction* — ρ = 0.992 is not a finding
about Pokémon, it is arithmetic. The floor is what lets K respond to the set's economics
instead: Phantasmal Flames (214 cards) gets Core 3 while Mega Evolution (310) gets 16.

**Guardrails are not supported by the data.** Core K under system B ranges 1–14 with
**zero empty tiers**; the 1-card minimum never fired. Imposing a minimum Core of, say, 3
would force Scarlet and Violet 151 and Obsidian Flames to admit cards *below* their own
5×-pack floor, destroying the one property that makes the rule defensible. The only place
coverage breaks is ≥10×C, where two sets have no card that expensive at all (SV Base Set
top card \$72.82 < \$82.25; Shrouded Fable \$74.80 < \$89.10) — which argues against
10×C, not for a guardrail.

---

## Phase 12 — Literal chase count vs effective chase depth

System B, Core+Extended:

| Set | literal K | effective EV count | ratio | effective value count | effective prob count |
|---|---:|---:|---:|---:|---:|
| Prismatic Evolutions | 27 | 6.72 | **0.249** | 7.90 | 25.33 |
| Paldean Fates | 7 | 2.57 | 0.367 | 2.58 | 7.00 |
| Ascended Heroes | 26 | 11.50 | 0.442 | 9.38 | 12.70 |
| Phantasmal Flames | 3 | 1.40 | 0.468 | 1.77 | 2.19 |
| Scarlet and Violet 151 | 11 | 7.49 | 0.681 | 7.23 | 10.93 |
| Scarlet and Violet Base Set | 13 | 10.83 | **0.833** | 10.73 | 12.99 |

Exactly the desired behaviour, and the brief's own example is realised almost literally:
**Prismatic Evolutions has 27 qualifying chase cards but an effective chase count of 6.7**,
because Umbreon ex dominates the economics. The ratio spans 0.25 → 0.83, a 3.3× range, so
depth is genuinely informative beyond the count.

Caveat, stated plainly: Spearman(literal K, effective EV count) = **+0.805**. Depth is
substantially correlated with tier size and must always be published *beside* K, never
instead of it. Its value is in the residual — the sets where the ratio is unusual.

---

## Phase 13/14 — Tier-specific economics and Chase EV Share (system B)

| Set | Core K | Ext K | Core p | Total p | Core EVret | Tot EVret | **Core share** | **Tot share** | BTB | med gap | effEV |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| Prismatic Evolutions | 13 | 27 | 0.01083 | 0.02157 | 0.375 | 0.408 | **0.647** | **0.705** | 0.2050 | \$319 | 6.72 |
| Ascended Heroes | 14 | 26 | 0.01254 | 0.02857 | 0.287 | 0.352 | 0.439 | 0.538 | 0.2093 | \$218 | 11.50 |
| Shrouded Fable | 5 | 20 | 0.02347 | 0.08140 | 0.156 | 0.339 | 0.233 | 0.507 | **0.2630** | **\$41** | 13.79 |
| Scarlet and Violet 151 | 1 | 11 | 0.00473 | 0.05403 | 0.059 | 0.210 | 0.138 | 0.488 | 0.1677 | \$277 | 7.49 |
| Paldean Fates | 3 | 7 | 0.00641 | 0.01460 | 0.131 | 0.151 | 0.403 | 0.466 | 0.1223 | **\$877** | 2.57 |
| Journey Together | 4 | 11 | 0.00771 | 0.03940 | 0.074 | 0.160 | 0.139 | **0.302** | 0.1236 | \$91 | 8.58 |

**Chase EV Share is the most immediately useful output of this stage.** It separates sets
whose pack value is essentially all chase (Prismatic Evolutions **70.5%**, Ascended Heroes
53.8%) from sets carried by a long mid-tier tail (Journey Together **30.2%**, Twilight
Masquerade 32.8%, Surging Sparks 32.9%).

The Core-versus-Total split is where the tiering earns its keep: 151 draws only **13.8%**
of pack EV from its Core but **48.8%** once Extended is included — a set whose headline
chase is narrow but whose secondary pool is deep. Prismatic Evolutions is the opposite:
64.7% of all pack EV sits in the Core alone.

---

## Phase 15 — Redundancy

Spearman across sets, system B:

| | totEVret | coreEVret | totShare | BTB | medGap | effEV | fullEVret | packCost | totK |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| **totEVret** | +1.000 | +0.671 | +0.610 | **+0.951** | −0.296 | +0.244 | +0.668 | +0.035 | +0.375 |
| **BTB** | **+0.951** | +0.603 | +0.517 | +1.000 | −0.430 | **+0.210** | +0.734 | −0.052 | +0.235 |
| **effEV** | +0.244 | −0.219 | +0.134 | +0.210 | −0.481 | +1.000 | +0.213 | −0.086 | **+0.805** |
| **totShare** | +0.610 | +0.316 | +1.000 | +0.517 | +0.310 | +0.134 | −0.038 | **+0.730** | +0.358 |

* Chase EV correlates with EV-like measures, exactly as expected — it *is* an EV measure,
  and no independence is claimed.
* **BTB vs Chase EV Return is +0.951**, reconfirming Stage II on a completely different
  tier definition. BTB is not an independent axis.
* **Chase Depth is orthogonal to the economics** (+0.244 with EV return, +0.210 with BTB)
  but correlated with tier size (+0.805). It is a separate *dimension*, not a separate
  *ranking*.
* `totShare` vs `packCost` = **+0.730**: expensive-pack sets concentrate more of their EV
  in chases. Worth remembering before reading Chase EV Share as a quality signal.

---

## Phase 16 — Rule-quality scorecard (not collapsed into one score)

| System | med K | K min | K max | scaleInv | shock ±10% | costShock | temporal | \|sizeRho\| | econSig | coverage | weakFake | heroK | depthOK |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|---:|
| **C_tight** (2.5%+5×C / 10%+2×C) | 5 | 1 | 12 | 0.968 | **0.962** | 0.959 | **0.967** | 0.225 | **1.00** | **1.00** | **0** | 2/3 | 1.00 |
| **B_pct_floor** (5%+5×C / 15%+2×C) | 5 | 1 | 14 | 0.958 | 0.953 | 0.945 | 0.964 | **0.165** | **1.00** | **1.00** | **0** | 2/3 | 1.00 |
| S_c2.5f2_e10f1 | 9 | 3 | 12 | 0.978 | 0.947 | 0.982 | 0.970 | 0.917 | **1.00** | 1.00 | **0** | 3/7 | 1.00 |
| Z_top (33%/10% of top) | 4 | 1 | 14 | 1.000 | **0.929** | 1.000 | 0.962 | **0.056** | **1.00** | 1.00 | **0** | 2/1 | 1.00 |
| A_pct_only (5%/15%) | 19 | 9 | 23 | 1.000 | 0.944 | 1.000 | 0.951 | **0.992** | 0.71 | 1.00 | **6** | 11/17 | 1.00 |
| S_c10f0_e15f0 (10%/15%) | 37 | 17 | 46 | 1.000 | 0.962 | 1.000 | 0.951 | 0.998 | 0.24 | 1.00 | **16** | 22/33 | 1.00 |
| Z_logz | 40 | 1 | 83 | 1.000 | 0.959 | 1.000 | **0.898** | 0.414 | 0.19 | 1.00 | **17** | 34/1 | 1.00 |
| Z_median | 31 | 12 | 96 | 1.000 | 0.960 | 1.000 | 0.942 | 0.631 | 0.14 | 1.00 | **18** | 12/21 | 1.00 |
| S_c*f10_e*f3 (≥10×C) | 2 | **0** | 10 | 0.867 | 0.878 | 0.884 | 0.895 | 0.034 | 1.00 | **0.90** | 0 | 2/2 | 1.00 |

*econSig* = share of sets whose Core floor is at or above one pack price; *weakFake* =
sets where the Core dips below one pack; *heroK* = Core K on Phantasmal Flames / Paldean
Fates; *depthOK* = share of sets where effective EV count < literal K.

**Trade-offs.** `Z_top` wins on scale invariance and size independence but loses on shock
stability and hero-set behaviour. Pure percentiles win on scale invariance for the wrong
reason — they cannot see economics at all — and pay for it with 6–16 sets of fake chases.
`≥10×C` is the only family that fails coverage. `C_tight` and `B_pct_floor` are the only
systems that are simultaneously stable (≥0.95 everywhere), economically significant in
every set, non-empty in every set, and responsive to pack cost.

---

## Phase 17 — Pathological cases

`backend/tests/unit/research/test_chase_tiers.py` — **48 passed**, six controlled
distributions where the right answer is obvious to a human:

| Case | Construction | Behaviour |
|---|---|---|
| **A** | one \$500 card, 99 × \$5 | Top 5% selects **5 cards, four of them \$5 commons**. With a ≥2×C floor: exactly the one real chase. |
| **B** | ten × \$100, ninety × \$5 | Top 5% can only ever name **five** of ten genuine chases. Top 20% + ≥2×C stops at exactly 10. |
| **C** | 20 cards clustered \$81–\$100 | `≥50% of top` admits all 20 — the scale-free family over-selects on flat distributions. |
| **D** | best card 4× pack | A ≥5×C Core is correctly **empty**; ≥2×C gives 3. |
| **E** | \$2 packs, cards \$25–\$60 | ≥10×C admits 8 — cheap packs make modest cards real chases. |
| **F** | \$900 hero + \$180/\$150/\$120/\$90 | `relative_to_top` gives **1, 1, 2, 5** cards at 33/25/20/10% — a 5× swing from one outlier. |

Also asserted: wider percentiles are supersets of narrower ones; higher floors select
fewer cards; `CORE ⊆ EXTENDED` holds for all 62 systems on all six cases; nesting
violations are repaired and counted; scale-free rules are provably immune to a joint price
doubling while floor rules provably are not.

---

## Phase 19 — Ascended Heroes vs Pokémon 151 (system B)

| | Ascended Heroes | Scarlet and Violet 151 |
|---|---|---|
| Pack cost | \$13.79 | **\$29.81** |
| Eligible printings | 459 | 361 |
| 5× pack floor | \$68.95 | **\$149.06** |
| **Core K** | **14** | **1** |
| Core cards | Pikachu ex \$1052, Mega Gengar ex \$993, Mega Dragonite ex \$659, Mega Charizard Y ex \$399, Pikachu ex \$349, Team Rocket's Mewtwo \$315, … | Charizard ex \$374 |
| Extended total K | 26 | 11 |
| Core any-hit p | 0.01254 | 0.00473 |
| Total any-hit p | 0.02857 | **0.05403** |
| Core Chase EV Return | **0.287** | 0.059 |
| Total Chase EV Return | **0.352** | 0.210 |
| Core Chase EV Share | **0.439** | 0.138 |
| Total Chase EV Share | 0.538 | 0.488 |
| BTB | 0.2093 | 0.1677 |
| Median Chase Cost Gap | **\$218** | \$277 |
| 50% chase spend | \$331 (24 packs) | \$388 (13 packs) |
| Effective chase count | **11.50** | 7.49 |

**Why they differ.** The whole gap is generated by the pack price. At \$29.81 a pack, a
"5× pack" Core card must be worth \$149 — and only Charizard ex clears it, so 151 gets a
**one-card Core**. Ascended Heroes' \$13.79 pack sets the same bar at \$68.95, which 14
cards clear.

This directly answers the original hypothesis, and the answer is **both, on different
axes**. 151 has the more *accessible* chase: 13 packs and \$388 for a coin-flip at some
Extended chase, against 24 packs and \$331 for Ascended Heroes — 151 needs roughly half
the packs. Ascended Heroes has the far *richer* chase: 26 qualifying cards against 11,
effective depth 11.50 against 7.49, Core EV Share 0.439 against 0.138, and a median
obtained chase of \$60 against 151's \$93 but reached from a much deeper pool.

The caution: 151's one-card Core is also the **least temporally stable Core in the
cohort** (endpoint Jaccard 0.500, oscillating between 1 and 2 cards). A tier that thin is
economically honest but presentationally fragile.

---

## Research findings

### Observed

1. Pure percentile tiers place sub-pack cards in the chase tier in 6/21 sets at 5% and
   **21/21 at 20%**.
2. Rounding mode changes K in **93.7%** of set × percentile combinations.
3. At a ≥5×C floor the percentile **never** binds for any percentile ≥5%; at ≥10×C it
   never binds at all. 62 systems collapse to 39 distinct outcomes; 8 are identical.
4. Median/quartile/z-score rules declare sub-pack cards chases in 16–21 of 21 sets,
   because the median card costs about \$0.20.
5. Relative-to-top is the most scale-free (|ρ| with set size = 0.056) and the least
   shock-stable (0.929 at ±10%, 0.846 at ±20%); it swings 5× on hero sets.
6. Floor systems: econSig 1.00, weakFake 0, coverage 1.00, shock ±10% ≈ 0.95, temporal
   ≈ 0.96, |sizeRho| 0.165–0.225.
7. ≥10×C leaves two sets with no Core at all.
8. Effective-EV-count / literal-K ratio spans 0.249 → 0.833.
9. BTB vs Chase EV Return = **+0.951**, on a completely different tier definition.
10. Chase EV Share vs pack cost = **+0.730**.

### Interpretation

An objective, transparent, reproducible tier definition **does** exist, but it is not
really a percentile rule. It is an **economic threshold** — "worth at least *m* packs" —
with a percentile acting as a cap that only engages at 2.5%. That is a perfectly good
answer for the stated product philosophy: it needs no cultural claim about what a chase
is, only an internally consistent economic one, and it is legible in one sentence to a
user.

The percentile should be kept for exactly one reason: it bounds the tier on sets whose
prices are compressed, and it makes the rule fail *safe* rather than *large*. It should
not be described as the mechanism.

### Unresolved

* Which floor multiple is canonical. 5×C/2×C behaves well but is not derived from
  anything; 3×C/1×C is nearly as stable with a wider Core. Nothing in this study picks
  between them.
* Whether a one-card Core (151, Obsidian Flames) is acceptable product behaviour, given it
  is the least temporally stable configuration.
* Whether reference-retail (MSRP) rather than market pack cost changes the tiers — still
  untested, and it matters most for exactly the sets whose sealed price has decoupled.
* Whether 8 weekly snapshots over 8 weeks is enough temporal evidence. It is the most that
  currently exists at usable coverage.

---

## Decisions

### `PERCENTILE_PLUS_ECONOMIC_FLOOR_SUPPORTED`

Percentile-only is falsified (weakFake up to 21/21). Price-distribution is falsified
(weakFake 16–21/21, Core K up to 127, a temporally empty Core). Relative-to-top is
economically clean but structurally fragile (worst shock stability, 5× hero swing).
Percentile + economic floor is the only family that is simultaneously stable under price
and pack-cost shocks, temporally steady, economically significant in **every** set, never
empty, and responsive to pack cost. **Adopted with the explicit caveat that the floor
carries the rule and the percentile is a guardrail cap, not the mechanism.**

### `CHASE_DEPTH_VALIDATED_AS_SEPARATE_DIMENSION`

Orthogonal to the economics (+0.244 with Chase EV Return, +0.210 with BTB), with a
literal-K-to-effective-count ratio spanning 0.25–0.83. Validated **on condition** that it
is always published beside literal K, given ρ = +0.805 between them.

### `CHASE_EV_SUPPORTED_AS_TIER_SPECIFIC_METRIC`

Behaves exactly as an EV metric should, splits cleanly by tier, and Chase EV Share
(30.2%–70.5%) is the most immediately interpretable output of the stage. It is an EV
concentration measure and is labelled as one — never as Chase Efficiency.

### `BTB_USEFUL_AS_INTERPRETABLE_COMPANION`

Unchanged from Stage II and reconfirmed here at +0.951 with Chase EV Return under a new
tier definition. It adds interpretation ("about one chase journey in five beats buying"),
not information, and must not be presented as an independent axis.

---

## Next study

**Financial RIP V11 remains locked.** No weight, P95, Jackpot Upside or ranking was
touched.

The gate for the complementarity study is now open, but two things should be settled
first: (1) the canonical floor multiple, via sensitivity of the published tier to
3×/5×/10×C across more market dates; (2) the MSRP-versus-market cost basis, since the
floor is defined in pack costs and 151 and Paldean Fates would move most. Only then does
"is Chase EV Share redundant with P95 / Jackpot Upside / Financial RIP" become a
well-posed question.

The Stage-III human-labeling framework is **preserved intact** and can now serve its
proper role: an independent check on whether an economic-threshold tier matches human
judgement — no longer a gate, but a validation.
