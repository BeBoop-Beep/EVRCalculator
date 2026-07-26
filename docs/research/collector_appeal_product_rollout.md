# Collector Appeal product rollout — Dual-Path audit, formula selection, RIP integration

**Status:** analysis complete, read-only. **No production write has occurred.**
**Date:** 2026-07-15 · **Branch:** `research/desirability-card-study`
**Selected formula:** CA7 bounded bonus, λ = 0.50 — pending owner approval.

---

## Phase 8.2 update (2026-07-16)

- **Chaos Rising exact component gap: RESOLVED.** Its `v2_coverage_cleanup`
  component row was built and committed (`6e4cf65f-6846-4e7a-91dd-346550d31dca`).
  The historical v1 row is retained and remains ignored by the version-exact
  contract.
- **Exact component coverage: 171 of 171** (0 missing, 0 duplicates), from 512
  historical rows across three hit policies.
- **CA7 RIP coverage: 21 of 33** (was 20). The remaining **12** are upstream pull
  data gaps: **11 `no pull model`** + **1 `no modeled subject` (Lost Origin)**.
  **Zero** are missing component-source rows.
- **Formula fingerprint unchanged:**
  `a98b948c693b87afdb1e4b0d19df03aa3ae650d35ca62b38eea41c126240b774`. Source and
  payload hashes changed, correctly — a new input row is not a new rule.
- **Public reader repaired.** Consumer #1 below selected by `built_at DESC` and
  was serving `hit_policy_v1` rows for **170 of 171 sets**. It now uses the same
  version-exact contract as CA7. **0 public scores and 0 ranks changed**; 170
  sets changed which row backs the identical value. See
  `universal_desirability_reader_source_repair.md`.
- **Independent cross-run determinism executed and passed** (Phase 8.1 ran only
  the in-process check). See `collector_appeal_cross_run_determinism.md`.
- CA7 remains `internal_candidate`; **0 CA7 writes**, no migration, no RIP or
  naming change. RIP still consumes Universal Desirability v3 at 10%.

---

## 0. Headline

Three findings drive everything below.

1. **The Phase-1 premise was false.** No consumer ranks the 36 unscoreable sets as
   zero. They have no simulation rows, so they never enter Explore's ranked
   cohort, and both RIP paths already null-guard. The stored `0.0` is a **latent
   trap**, not a live bug. The availability work was rescoped accordingly.

2. **The 36 sets are not broken — they are out of model.** All 36 have full rarity
   data and resolved subject links. Every one is a non-booster product. The
   previous `unavailable_missing_rarity` label was a misdiagnosis.

3. **Dual-Path Depth is real but structurally compressed.** Dragonite and Gengar
   both receive Dual-Path credit at exactly the maximum their set allows. But no
   set can score P above ~0.45, because P is capped by the accessibility of the
   *easiest hit-eligible card*, and no hit card is anywhere near the 1-in-10
   "easy" anchor. This compression is what decides CA6 vs CA7.

---

## 1. Consumer inventory

Every reader of `pokemon_set_desirability_component_scores` and of the score
columns, traced end to end.

| # | Consumer | Reads | Ranks unavailable as zero? |
|---|---|---|---|
| 1 | `universal_set_desirability_service._load_current_component_rows` | `subject_rollups_json`, `set_desirability_score` | **No** — computes v3 at read time, gates on `coverage.status` |
| 2 | `explore_rip_statistics_service` (L929-933) | v3 payload | **No** — `desirability_v3_score = None` unless coverage `full` |
| 3 | `weighted_rip.compute_weighted_rip` | pillar value | **No** — dropped missing pillar (now: canonical RIP unavailable) |
| 4 | `rip_desirability_comparison.build_rip_desirability_comparison_payload` | `desirability_score` → `pack_score`, `pack_rank`, `pack_tier` | **No** — sources from `pokemon_set_opening_desirability_latest`, where all 36 are `NULL`; `_weighted_score` returns `None` if any input is missing |
| 5 | `explore_rip_statistics_service._calculate_score_ranks_and_tiers` (L799) | `desirability_score` → `desirability_rank`, `desirability_tier` | **No** — same `NULL` source |
| 6 | Frontend `exploreRankingConfig.js` "Best Opening Desirability" | `relative_desirability_score`, `desirability_rank`, `desirability_tier` | **No** — consumes #5 |
| 7 | `set_desirability_service` | `pokemon_set_opening_desirability_latest` | **No** |
| 8 | Research scripts (`build_opening_appeal_study`, `build_universal_set_desirability_v3`, …) | `set_desirability_score` | Read-only, not user-facing |

**Answer to final question 1 — which consumers previously ranked unavailable sets
as zero?** *None.* Verified three ways against production:

- `explore_rip_statistics_latest` has **33 rows**; overlap with the 36 unavailable
  sets is **0**.
- `pokemon_set_opening_desirability_latest` has 171 rows but only **33 ranked** —
  exactly the simulated cohort. All 36 carry `NULL` score and `NULL` rank.
- All 33 simulated sets have `desirabilityCoverage = full`, so the missing-pillar
  path is not exercised today at all.

The `0.0` lives only in `pokemon_set_desirability_component_scores.set_desirability_score`
and reaches no ranking. It is a trap for the *next* consumer, which is why the
guard was still built.

### The second finding: the availability contract was never in production

`metric_status`, `availability_reason` and `rankable` are absent from **all 511
production rows** (0 rows contain the keys). The previous phase's builder writes
them, but that code has never been committed to production data. So there was
nothing for a consumer to filter on even if one had tried.

---

## 2. Availability / rankability fix (collapsed scope)

Two new modules replace what would have been a repeated JSON-parsing convention.

**`backend/desirability/product_support.py`** — classifies product support from
**set metadata only** (canonical key, name, series). It never reads scores, hit
counts, or card counts: inferring "unsupported" from a zero score would make the
classifier agree with the scorer by construction and would silently reclassify a
genuinely broken booster set as "out of model" the moment its data regressed.
Unknown sets default to **supported**, so a set the classifier has never heard of
surfaces real defects loudly instead of vanishing from the model.

**`backend/desirability/rankability.py`** — the single accessor. `rankable_score()`
returns `None`, never `0.0`, for a row that must not be ranked; `None` propagates
as "unavailable" while `0.0` propagates as "worst in catalogue".
`rank_rankable_rows()` **raises** rather than rank an unrankable row, so a future
consumer that forgets to filter fails in tests instead of quietly shipping.

Crucially, `availability()` falls back to **product classification** when
`diagnostics_json` carries no status. Since that describes every production row
today, **the trap is closed against current data without requiring a rebuild
first**.

Genuine zeroes are preserved: the contract keys on *status*, never on *value*.
Filtering on `score == 0` would discard exactly the honest zeroes we must keep.

---

## 3. Before / after for the 36 unavailable sets

**Before:** rank `—` (never ranked; no simulation rows), status
`unavailable_missing_rarity` (**wrong** — blames rarity data that is correct).
**After:** rank `—` (unchanged), status `unsupported_product_type` with an
accurate subtype.

| Product family | Sets | New `product_support_type` | Prev. rank | New rank | Visible | RIP |
|---|---|---|---|---|---|---|
| Black Star Promos (BW, DP, HGSS, Nintendo, SM, SWSH, Wizards, XY) | 8 | `unsupported_promo_product` | — | — | Yes, labelled | Unavailable |
| McDonald's Collections 2011–2022 | 10 | `unsupported_mcdonalds_collection` | — | — | Yes, labelled | Unavailable |
| POP Series 1–9 | 9 | `unsupported_pop_series` | — | — | Yes, labelled | Unavailable |
| EX Trainer Kits (Latias, Latios, Plusle, Minun) | 4 | `unsupported_trainer_kit` | — | — | Yes, labelled | Unavailable |
| Best of Game, Kalos Starter Set, Futsal, Rumble, Southern Islands | 5 | `unsupported_fixed_product` | — | — | Yes, labelled | Unavailable |

Full detail: `docs/research/collector_appeal_tables/unavailable_sets_before_after.csv`.

**No ranking changes**, because none of these sets was ever ranked. The change is
in what the system *says* about them and what it *cannot do* to them in future.

User-facing explanation per family, e.g. Trainer Kits: *"Trainer Kits ship two
fixed preconstructed decks. Contents are identical in every copy, so there is
nothing to pull and no chase structure."*

### Classification validation

The rules partition the catalogue **exactly**, with zero overlap, without
consulting any score:

| Family | Sets | Score > 0 | Score = 0 |
|---|---|---|---|
| booster (supported) | 135 | **135** | 0 |
| promo | 8 | 0 | **8** |
| mcdonalds | 10 | 0 | **10** |
| pop_series | 9 | 0 | **9** |
| trainer_kit | 4 | 0 | **4** |
| fixed_product | 5 | 0 | **5** |

Every unsupported set scores 0.0; every supported set scores above 0.0. The
classifier reproduces the affected cohort exactly from metadata alone — that is
the evidence that **product type, not data quality, is the cause**.

---

## 4. Product-type classification (Phase 2)

Reason codes now separate two families that must never blur:

| Code | Meaning | Actionable? |
|---|---|---|
| `unsupported_product_type` | Outside the RIP model. Permanent. | **No** — not a defect |
| `unavailable_missing_rarity_mapping` | Supported set, rarity unmapped | Yes |
| `unavailable_missing_subject_links` | Supported set, hits unlinked | Yes |
| `unavailable_no_eligible_hit_structure` | Supported booster set with no hit ladder | Yes |
| `partial` | Supported, thin coverage, **still rankable** | Warning only |
| `valid` | Fully covered | — |

`build_metric_status` now decides **product support first**, before any data check
(`METRIC_STATUS_VERSION` → `set_metric_status_v2`). The old code checked data
first, which is why all 36 hit the `hit_eligible == 0 → unavailable_missing_rarity`
branch. That branch now means what it says: a *supported* booster set with no hit
ladder is a real defect (`unavailable_no_eligible_hit_structure`).

**Per your instruction, no rarity-mapping investigation was performed** — the data
shows these are product-type exclusions, and the classifier confirms it without
touching rarity.

---

## 5. RIP missing-pillar policy — decided explicitly

**Previously (option C, by accident):** a missing desirability pillar was dropped
and Profit/Safety/Stability renormalized to 100%. This was never a decision — it
fell out of the generic renormalization rule, which cannot distinguish "this
pillar is switched off" from "we could not measure this pillar".

The result *looked* like a canonical RIP and sorted against real four-pillar RIPs
while not being comparable to them. A product missing its fourth pillar could
out-rank a fully-measured booster set purely because the missing pillar was scored
out of existence — the absence of evidence rendered as a competitive score.

**Now (option B):**

| Option | Verdict |
|---|---|
| A. Exclude unsupported products from RIP entirely | Rejected — hides products users search for |
| **B. Financial RIP only, Collector Appeal marked unavailable** | **Selected** |
| C. Reweight financial pillars to 100% | Rejected — produces a non-comparable score that ranks anyway |
| D. Preserve RIP, show lower-confidence badge | Rejected — a badge does not stop a bad number from sorting |

Behaviour: `score = None`, `status = "incomplete_missing_desirability"`,
`rankable = False`, `effectiveWeights = {}`. Financial numbers remain available
under the distinct `financial_rip_v2` label in a `financialOnly` sub-payload,
explicitly marked *"not comparable to canonical RIP"*, and never ranked in the
canonical cohort.

Two paths legitimately exclude desirability and are **not** missing pillars:
`include_desirability=False` (explicit caller request) and a configured weight of
0. Both still renormalize and produce a valid financial RIP.

**Blast radius: zero.** All 33 simulated sets have `coverage = full`, so no set
loses a rank today. This purely closes the trap.

**Required future-case test** (`test_unsupported_promo_with_simulation_data_cannot_get_a_canonical_rip`):
a promo with a strong simulated financial profile (95/90/88) receives
`score = None`, not a renormalized 92.6 that would place it near the top of the
leaderboard.

---

## 6. Real-data Dual-Path audit

Script: `backend/scripts/build_dual_path_audit.py` (read-only).
Cohort: **22 sets with a modeled pack**, 21 with computable Dual-Path Depth.

### 6.1 Ascended Heroes — Gengar

D(set) = 95.4809 · P(set) = 0.27143 · **set hit-access ceiling = 0.3595**

| Card | # | Rarity | Treatment | Modeled pull | access | scarcity | Selected |
|---|---|---|---|---|---|---|---|
| Mega Gengar ex | 125 | Double Rare | 0.62 | 1-in-191 | 0.3595 | 0.6405 | **easiest** |
| Mega Gengar ex | 269 | MEGA_ATTACK_RARE | 0.36 | 1-in-202 | 0.3473 | 0.6527 | — |
| Mega Gengar ex | 284 | Special Illustration Rare | 0.96 | 1-in-1,533 | 0.0000 | 1.0000 | **rarest** |

- Accessible path: **Mega Gengar ex #125 (Double Rare)**, access 0.3595
- Elite path: **Mega Gengar ex #284 (SIR)**, scarcity 1.0000
- `dual_path = 0.3595 × 1.0 = 0.359483` · `q_s = 0.066533` · **contribution = 0.023917**

### 6.2 Ascended Heroes — Dragonite

| Card | # | Rarity | Treatment | Modeled pull | access | scarcity | Selected |
|---|---|---|---|---|---|---|---|
| Mega Dragonite ex | 152 | Double Rare | 0.62 | 1-in-191 | 0.3595 | 0.6405 | **easiest** |
| Mega Dragonite ex | 271 | MEGA_ATTACK_RARE | 0.36 | 1-in-202 | 0.3473 | 0.6527 | — |
| Mega Dragonite ex | 290 | Special Illustration Rare | 0.96 | 1-in-1,533 | 0.0000 | 1.0000 | **rarest** |
| Mega Dragonite ex | 295 | Mega Hyper Rare | 0.82 | 1-in-1,080 | 0.0000 | 1.0000 | tied |

- `dual_path = 0.3595 × 1.0 = 0.359483` · `q_s = 0.048648` · **contribution = 0.017488**

**Answer to final questions 6 & 7 — do Dragonite and Gengar receive meaningful
Dual-Path credit?** **Yes — both receive the maximum credit their set permits.**
Each has a perfect elite path (SIR, scarcity 1.0) and the most reachable hit the
set offers (Double Rare, access 0.3595). Both clear the single-card ceiling of
0.25, confirming the metric recognises them as genuine dual-path subjects rather
than one-card artefacts.

**Two defects surfaced by the audit (neither affects the value):**

1. **Elite-anchor tie.** Dragonite's SIR (1-in-1,533) and Mega Hyper Rare
   (1-in-1,080) both clamp to access 0.0 and become indistinguishable. Which is
   reported as "rarest" is decided by iteration order, not scarcity. The
   `dual_path` value is unaffected (tied cards share an access); only the label
   is ambiguous.
2. **`subject_dual_path` returns only `card_name`.** All four Dragonite printings
   are named "Mega Dragonite ex", so the returned pick cannot identify *which*
   printing won. The audit works around this by selecting on position and
   cross-checking against the production function. Worth fixing before any
   card-level Dual-Path UI ships.

### 6.3 The structural finding — P is capped by the easiest hit

`dual_path ≤ access(p_easiest)`. The easiest **hit-eligible** card in a modern set
is nowhere near the 1-in-10 EASY anchor. Ascended Heroes' entire hit ladder:

| Rarity | Odds | access |
|---|---|---|
| Double Rare | 1-in-191 | **0.3595** ← set ceiling |
| MEGA_ATTACK_RARE | 1-in-202 | 0.3473 |
| Ultra Rare | 1-in-291 | 0.2681 |
| Illustration Rare | 1-in-293 | 0.2666 |
| Mega Hyper Rare | 1-in-1,080 | 0.0000 |
| Special Illustration Rare | 1-in-1,533 | 0.0000 |

**No subject in Ascended Heroes can exceed 0.3595, so P ≤ 0.3595 for the whole
set.** Ascended Heroes has the **lowest ceiling of all 21 covered sets**.

Cohort-wide: P ∈ **[0.135, 0.447]**, mean 0.293, sd 0.079. Ceilings: mean 0.554,
max 0.722. **P never approaches 1.0 and structurally cannot.**

**Cause attribution** (per the brief's checklist): not card links (resolve
correctly), not rarity mapping (complete), not pull-rate mapping (present and
sane), not subject weighting (shares normalize to 1), not the formula's algebraic
form. The cause is the **hit-eligibility policy meeting the anchor calibration**:
the 1-in-10 EASY anchor is calibrated for a scale that hit-eligible cards never
occupy. P must therefore be read as a *relative* structural measure, **not** as a
0-1 utilisation.

### 6.4 Comparison sets

| Archetype | Set | Rank | D | P | Ceiling | Subjects | Multi | Single |
|---|---|---|---|---|---|---|---|---|
| **Strong Dual-Path** | Mega Evolution | 1 | 87.20 | 0.4466 | 0.659 | 15 | 6 | 9 |
| **Strong (deepest structure)** | Prismatic Evolutions | 2 | 93.28 | 0.3988 | 0.487 | 19 | **12** | 7 |
| **Broad attainable, few elite** | Paldean Fates | 19 | 95.33 | 0.1988 | 0.688 | **46** | 5 | **41** |
| **Weak Dual-Path** | White Flare | 21 | 87.30 | 0.1351 | 0.622 | 24 | 3 | 21 |
| **Single-elite / narrow** | Shrouded Fable | 17 | 51.07 | 0.2337 | 0.722 | 5 | **0** | 5 |
| **Anchor** | Ascended Heroes | 14 | 95.48 | 0.2714 | **0.359** | 44 | 18 | 26 |

This matches real product interpretation. **Prismatic Evolutions** (12 of 19
desirable subjects have multiple printings) ranks 2nd — it genuinely offers both
reachable and elite versions of its favourites. **Paldean Fates** has the second-
highest desirability and the *most* subjects (46), but only 5 have multiple
printings — broad attainable favourites with few elite chases — and correctly
lands at rank 19. **Shrouded Fable** has **zero** multi-printing subjects, so
every subject is capped at the single-card bound of 0.25.

**Answer to final question 8 — does the Dual-Path ranking match real product
interpretation?** Yes, with one caveat: Ascended Heroes ranks only 14th despite
having 18 multi-printing subjects, because its ceiling (0.359) is the lowest in
the cohort. That is the compression artifact, not a product judgment.

### 6.5 Safeguards verified on real data

| Case | Claim | Result |
|---|---|---|
| 3 | Duplicates cannot inflate | ✅ Only the two ends are read; padding with mid-rarity cards changes nothing. `q_s` is per distinct subject. |
| 4 | One elite, no obtainable alternate → weak | ✅ `access=0, dual_path=0` |
| 5 | Attainable cards, no elite chase → weak | ✅ `scarcity=0, dual_path=0` |
| 6 | Same card cannot fake a dual path | ✅ **253 single-printing subjects in production, max `dual_path` exactly 0.2500, zero above the bound.** Algebraic ceiling `a(1-a) ≤ 0.25` confirmed empirically. |
| 7 | Multi-subject breadth preserved | ✅ |
| 8 | Weights normalized | ✅ shares sum to 1.0; unmodeled subjects renormalize rather than contribute zero |

128 multi-printing subjects reach up to 0.6833 — comfortably separated from the
0.25 single-card ceiling.

---

## 7. CA6 vs CA7 — formula selection

**CA6** = `D × (0.50 + 0.50·P)` — discount model.
**CA7** = `D + λ·P·(1 − D)` — bounded bonus, λ ∈ {0.25, 0.50, 0.75} (pre-registered).

| Criterion | CA6 | CA7 |
|---|---|---|
| Bounds | ✅ [0,1] | ✅ [0,1] for all λ (proved on a 21×21 grid) |
| Monotone in D | ✅ | ✅ strictly; `dCA7/dD = 1−λP ≥ 1−λ > 0` |
| Monotone in P | ✅ | ✅ `dCA7/dP = λ(1−D) ≥ 0` |
| At P=0 | `0.50·D` — halves desirability | `D` — costs nothing |
| At P=1 | `D` | `D + λ(1−D)` |
| Structure without desirability (D=0) | ✅ → 0 | ❌ → `λ·P` (see below) |
| Observed score range | **[31.5, 65.2]** | [53.9, 95.8] (λ=.25) … [59.7, 96.4] (λ=.75) |
| Rank moves vs pure-D | max **10**, mean 3.33, 19/21 sets | max 3-4, mean 0.29–0.95 |

### Why CA7 wins

**1. CA6's scale is not readable as Collector Appeal.** Because P is capped at
~0.45, CA6's multiplier spans only **[0.567, 0.723]**. The most appealing set in
the catalogue scores **65/100**, and nothing ever approaches 100. CA6 does not
produce a 0-100 appeal score; it produces D scaled by a factor that can never
reach 1. Telling a viewer "Ascended Heroes — the most desirable roster in the
catalogue — has Collector Appeal 61/100" would be misleading.

**2. CA6 lets a measurement artifact overrule desirability.** The decisive case:

| Set | D | P | CA6 |
|---|---|---|---|
| Ascended Heroes | **95.48** | 0.2714 (ceiling **0.359**) | **60.70** |
| Mega Evolution | 87.20 | 0.4466 (ceiling 0.659) | **63.07** |
| Prismatic Evolutions | 93.28 | 0.3988 | **65.24** |

CA6 ranks Mega Evolution **above** Ascended Heroes on Collector Appeal despite 8
fewer desirability points. The reason is not that Mega Evolution is better to
open — it is that **Ascended Heroes has the lowest hit-access ceiling in the
cohort**, so the artifact penalises it hardest. CA6 converts a pull-rate
calibration artifact into a product verdict. Under CA7 (λ=0.50) Ascended Heroes
correctly stays first at 96.09.

**3. The failure modes are asymmetric — and this is the strongest argument.** P is
measured with a known, quantified artifact. A formula whose degradation under
mis-measured P falls back to **D** (a well-validated construct) is safe. A formula
that degrades toward **0.5·D** — a systematically wrong number applied to every
set — is not. Under-measurement of P should cost a set nothing, not a third of
its score.

**4. Product semantics.** "A set of beloved Pokémon with one printing each is
still appealing to open" is true. CA6 charges that set 50% of its desirability
for a structural property most collectors would not describe as a flaw. The
brief's own framing of CA7 — *"Roster Desirability is the baseline; Dual-Path
Depth adds a bounded bonus"* — matches how the construct actually behaves.

**Answer to final question 19/20 — penalty or bonus?** **Bonus.** Lack of
Dual-Path Depth is largely an artifact of hit-eligibility and anchor calibration,
not a property of the product. It must not be charged as a penalty.

### CA7's honest defect

At D=0, CA7 = λ·P — a set whose Pokémon nobody cares about would score up to 0.75
on structure alone. This **genuinely violates** the pre-registered principle
*"structure without desirability is never appeal"*, and it is a real point in
CA6's favour.

It is **latent, not active**: P is computed only over subjects with demand above
the baseline and returns `None` — not 0 — when none exists. So P cannot be a
number unless some subject is desirable, and any such subject forces D > 0. The
D=0/P>0 quadrant is unreachable *by construction*, not merely unobserved.
Recorded in `test_ca7_violates_the_zero_desirability_principle_but_only_where_data_cannot_reach`,
which fails if P's eligibility rule is ever loosened — surfacing the blemish
before it becomes a bug. Empirically min D = 51.07 (Shrouded Fable).

### Selected λ = 0.50

Chosen on construct grounds, **not** on rank movement or price agreement.

- **λ=0.25** makes P nearly inert (only 4 of 21 sets move at all), defeating the
  purpose of adding the dimension.
- **λ=0.75** lets structure claim three-quarters of a set's headroom — over-
  weighting a quantity we measure with known compression.
- **λ=0.50** is the neutral, symmetric prior: dual-path structure at its maximum
  may claim half the remaining headroom. Absent collector-preference data,
  splitting headroom evenly between "already desirable" and "structurally
  rewarding to open" is the defensible default, and it keeps `dCA7/dD = 1−0.5P ≥
  0.78 > 0` — desirability always dominates.

At λ=0.50 and the observed mean P≈0.29, the typical bonus is ≈2.2 points on
0-100. Small and honest.

**No market outcome was consulted in this selection.** Tests walk the module AST
to assert no optimizer surface and no price imports exist; `bounded_bonus_appeal`
takes exactly `(d, p, lam)`.

---

## 8. Effective RIP influence at 10%

Weights unchanged: `0.58 Profit + 0.20 Safety + 0.12 Stability + 0.10 Collector Appeal`.

| Candidate | pillar sd | 1-SD marginal RIP pts | share of weighted dispersion | max rank move | mean | % ≥1 | % ≥3 | mean abs score Δ |
|---|---|---|---|---|---|---|---|---|
| CA6 | 7.04 | 0.704 | 10.05% | **1** | 0.38 | 38.1% | **0.0%** | 3.009 |
| CA7 λ=0.25 | 9.04 | 0.904 | 12.54% | **1** | 0.10 | 9.5% | **0.0%** | 0.109 |
| **CA7 λ=0.50** | 8.41 | 0.841 | **11.78%** | **1** | 0.19 | 19.1% | **0.0%** | 0.218 |
| CA7 λ=0.75 | 7.80 | 0.780 | 11.01% | **1** | 0.29 | 28.6% | **0.0%** | 0.327 |

Weighted contribution SD by pillar (CA7 λ=0.50): Profit **2.781**, Stability
**2.371**, Safety **1.148**, Collector Appeal **0.841**.

**Answer to final questions 12 & 13 — how much does Collector Appeal change RIP,
and is it meaningful or decorative?**

**Modest but meaningful — at the low end, and honestly closer to decorative than
the 10% label suggests.** A nominal 10% weight is not 10% practical influence.
The pillar's weighted dispersion share (11.8%) roughly matches its nominal weight
— it is not being crushed — but **maximum rank movement is 1 position and nothing
moves 3+ ranks**, because Profit and Stability carry 3.3× and 2.8× more weighted
dispersion. Switching from the current Universal Roster Appeal to CA7 λ=0.50
changes RIP by 0.22 points on average and reorders almost nothing.

CA6's much larger score delta (3.009) is **a uniform level shift**, not added
discrimination — it lowers every set by roughly a third while still moving max 1
rank. That is the clearest evidence CA6 changes the *scale* rather than the
*information*.

Honest framing for the video: Collector Appeal is a **tie-breaker and an
explanatory axis**, not a driver of the leaderboard. It should be presented as
"what kind of set this is to open", alongside RIP rather than as the thing moving
it.

---

## 9. Metric definitions productionized (Phase 6 — status)

| Metric | Definition | Status |
|---|---|---|
| **D** Roster Desirability | How strongly collectors care about the Pokémon in the set | ✅ shipped (`universal_set_desirability_v3`) |
| **A** Favorite-Hit Accessibility | How realistically collectors can pull cards featuring desirable Pokémon | ✅ research module |
| **M** Chase Intensity | How difficult the elite cards are to pull among desirable Pokémon | ✅ available separately (`elite_chase_magnetism_v1_card_level`) |
| **P** Dual-Path Depth | Whether desirable Pokémon offer both attainable cards and elite chases | ✅ audited, `dual_path_depth_v1` |
| **Chase Appeal** = D × M | How desirability and elite scarcity combine into a chase structure | ✅ separate, **not a RIP pillar** |
| **Collector Appeal** | How appealing the set is to open beyond financial return | ⏳ CA7 λ=0.50 selected, **not yet written** |

**Answer to final questions 14 & 15:** Chase Intensity and Chase Appeal are
available independently, and **Chase Appeal remains outside RIP**. RIP has exactly
four pillars — pinned by `test_rip_has_exactly_four_pillars_and_chase_appeal_is_not_one`.
Adding Chase Appeal as a fifth would apply desirability to RIP twice. The failed
card-level `Subject Desirability × Card Scarcity` formula was not reused.

---

## 10. Tests run

```
backend/tests/unit/desirability                              (all)
backend/tests/unit/db/services/test_explore_rip_statistics_service.py
backend/tests/unit/db/services/test_rip_desirability_comparison.py
backend/tests/unit/scripts                                   (all)
--------------------------------------------------------------------
537 passed
```

New files: `test_product_support_availability.py` (53), `test_collector_appeal_ca7.py`,
`test_dual_path_safeguards.py`.

**Two deliberate contract reversals**, updated explicitly rather than left to drift:

1. `test_missing_desirability_data_renormalizes_instead_of_scoring_zero` →
   `test_missing_desirability_data_makes_canonical_rip_unavailable`. The old test
   asserted exactly the silent-renormalization behaviour being removed.
2. `unavailable_missing_rarity` → `unavailable_missing_rarity_mapping`, and the
   `hit_eligible == 0` branch → `unavailable_no_eligible_hit_structure`.

**Pre-existing failures, unrelated and not touched** (confirmed failing on a clean
tree via `git stash`): `test_collection_portfolio_service.py` (2),
`test_pokemon_set_cards_service.py` (1), plus 4 collection errors from a missing
`jwt` module.

**No frontend code was changed, so no frontend claim is made.** Frontend contract
tests were not run because no payload consumed by the frontend was modified.

---

## 11. Files changed

**New**
- `backend/desirability/product_support.py`
- `backend/desirability/rankability.py`
- `backend/scripts/build_dual_path_audit.py`
- `backend/tests/unit/desirability/test_product_support_availability.py`
- `backend/tests/unit/desirability/test_collector_appeal_ca7.py`
- `backend/tests/unit/desirability/test_dual_path_safeguards.py`
- `docs/research/collector_appeal_product_rollout.md`, `docs/research/dual_path_audit.json`

**Modified**
- `backend/desirability/collector_appeal.py` — CA7 + `CA7_LAMBDA_GRID`
- `backend/desirability/weighted_rip.py` — missing-pillar policy
- `backend/scripts/build_pokemon_set_desirability_component_scores.py` — classifier wiring, `set_metric_status_v2`
- `backend/tests/unit/desirability/test_collector_appeal.py`, `test_set_rebuild_staleness.py`, `test_universal_set_desirability.py`

**CSVs** (`docs/research/collector_appeal_tables/`): `dual_path_set_rankings.csv`,
`dual_path_subject_contributions.csv`, `ascended_heroes_anchor_card_trace.csv`,
`collector_appeal_ca6_ca7_comparison.csv`, `pillar_effective_influence.csv`,
`unavailable_sets_before_after.csv`

---

## 12. Proposed production write plan — NOT EXECUTED

**Nothing has been written.** All analysis above is read-only.

| Field | Value |
|---|---|
| Target table | `pokemon_set_desirability_component_scores` |
| Rows to update | **171** (all latest-per-set rows gain `product_support_type` / corrected `metric_status`) |
| Rows to insert | 0 |
| Unavailable rows | 36 → `unsupported_product_type` + subtype |
| Rankable rows | 135 unchanged |
| Score column changes | **None** — no score value changes; `diagnostics_json` only |
| Version change | `set_metric_status_v1` → `set_metric_status_v2` |
| Rollback | Diagnostics-only; prior rows retained by `built_at` history (511 rows across 3 builds/set) |

Because `METRIC_STATUS_VERSION` changed, `--rebuild-changed` will select all 171
rows anyway — a `--rebuild-all` is **not** justified and is not proposed.

**Validation queries after any write:**

```sql
-- expect 36, all unsupported_*
select diagnostics_json->>'product_support_type', count(*)
from pokemon_set_desirability_component_scores
where built_at = (select max(built_at) from pokemon_set_desirability_component_scores)
  and (diagnostics_json->>'rankable')::bool = false
group by 1;

-- expect 0: no rankable row may be an unsupported product
select count(*) from pokemon_set_desirability_component_scores
where (diagnostics_json->>'rankable')::bool = true
  and diagnostics_json->>'product_support_type' like 'unsupported%';
```

### Deferred to a follow-up (deliberately not done here)

- **Phase 7** full source fingerprinting — staleness still keys on
  `set_id` + `config_fingerprint` + `current_trend_snapshot_ids`. It does **not**
  yet include the Dual-Path / Chase Intensity / Collector Appeal formula versions.
  Must land **before** Collector Appeal is persisted, or a formula change will not
  invalidate rows.
- **Phase 8** dry-run preview fix — the builder still reads existing rows only when
  `not dry_run`, so dry-run cannot yet report accurate update counts.
- Persisting `collector_appeal` / `dual_path_depth` and their formula-version
  columns.

**Answer to final question 17 — can dry-run accurately preview writes?** **Not
yet.** This is why no write is proposed in this phase beyond the diagnostics
correction, and why even that should wait for the dry-run fix.

---

## 13. Remaining limitations

1. **P is compressed by an artifact** (§6.3). Fixing it means re-calibrating
   EASY_PROBABILITY for hit-eligible cards, or admitting hit-adjacent cards to the
   accessible path. Either changes P's meaning and must be a deliberate decision.
2. **Dual-Path covers 21 of 171 sets** — only sets with a modeled pack.
3. **No collector-preference data.** Whether collectors actually value dual-path
   structure, and how much, is unvalidated. λ=0.50 is a reasoned prior, not a
   measurement. This is the single largest open question.
4. **The elite-anchor tie and name-only card identity** (§6.2) should be fixed
   before any card-level Dual-Path UI.
5. **CA7's D=0 blemish** is unreachable but real (§7).
6. **P's P=0 case is never exercised** — observed P ∈ [0.135, 0.447], so CA7's
   "costs nothing at P=0" property is never actually tested by production data.

---

## 14. Answers to the final questions

1. **Which consumers ranked unavailable sets as zero?** None. Verified three ways.
2. **Are all 36 excluded from rankings?** Yes — and they always were. Now they are
   also correctly *labelled*, and the trap is closed at the accessor.
3. **Genuine zeroes?** Retained and rankable. The contract keys on status, never value.
4. **Partial sets?** `rankable = true`, coverage warning preserved.
5. **Trainer Kits classified as unsupported products?** Yes — `unsupported_trainer_kit`, not a rarity defect.
6. **Do Dragonite and Gengar receive meaningful Dual-Path credit?** Yes — both at their set's maximum (0.3595), both clearing the 0.25 single-card ceiling.
7. **Which cards form each path?** Gengar: #125 Double Rare (accessible) / #284 SIR (elite). Dragonite: #152 Double Rare / #290 SIR.
8. **Does the ranking match real product interpretation?** Yes, except Ascended Heroes is depressed by the ceiling artifact.
9. **CA6 or CA7?** **CA7.**
10. **Which λ?** **0.50** — neutral symmetric prior; 0.25 inert, 0.75 over-weights a poorly-measured quantity.
11. **Bounded and monotone?** Yes, proved on a 21×21 grid for every λ.
12. **How much does it change RIP at 10%?** 0.22 points mean; max 1 rank; 0% move 3+.
13. **Meaningful or decorative?** Modest but meaningful — a tie-breaker, not a driver.
14. **Chase Intensity / Chase Appeal available separately?** Yes.
15. **Chase Appeal outside RIP?** Yes — four pillars, test-pinned.
16. **All formula/source versions in staleness detection?** **No** — Phase 7 deferred; must land before persisting Collector Appeal.
17. **Can dry-run accurately preview writes?** **No** — Phase 8 deferred.
18. **What exact DB changes are proposed?** 171 diagnostics-only updates; no score changes.
19. **What remains unvalidated without collector-preference data?** Whether dual-path structure is valued at all, and λ's magnitude.
20. **What single command requires approval next?** See below.

---

## 15. The one command requiring approval

**Not yet.** Two prerequisites should land first: the Phase 7 fingerprint and the
Phase 8 dry-run fix. When they do, the sequence is:

```bash
# 1. Preview only — writes nothing (requires the Phase 8 dry-run fix to be accurate)
python backend/scripts/build_pokemon_set_desirability_component_scores.py --rebuild-changed --dry-run
```

and only after that preview is reviewed and matches the plan in §12:

```bash
# 2. REQUIRES OWNER APPROVAL — 171 diagnostics-only row updates, no score changes
python backend/scripts/build_pokemon_set_desirability_component_scores.py --rebuild-changed --commit
```

`--rebuild-all` is **not** requested and is not justified.
