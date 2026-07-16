# Factorized Opening Appeal — Case Study Results

**Status: research only. Nothing committed to RIP, no frontend change, no
database writes.** Canonical RIP is unchanged.

- Run date: 2026-07-15. Database: Supabase `TheIndex` (`zwxzxuuawalvwioadhmf`).
- Reproduce: `backend/scripts/build_factorized_opening_appeal_study.py`.
  Raw output: `docs/research/factorized_opening_appeal_study.json`.
- Constructs: `backend/desirability/factorized_opening_appeal.py`.
  Tests: `backend/tests/unit/desirability/test_factorized_opening_appeal.py`.
- Dependencies: no new package required. `numpy==2.4.3` was added to
  `backend/requirements.txt` — it was already imported directly by both study
  scripts but was **undeclared** (and `pandas`, its assumed transitive source,
  is not installed in `backend/.venv` at all), so a clean environment was not
  reproducible before this change.
- Seeds (also in the JSON): bootstrap `20260716`, uncertainty `20260717`,
  500 bootstrap draws, 200 uncertainty draws per scenario.

> Price is used **only** as an external validation outcome. It never entered the
> construction, normalization, internal weighting, or selection of any factor or
> candidate. No weight, anchor, or alpha is fitted to price. The F3 alphas were
> pre-registered (0.25 / 0.50 / 0.75) and there is no alpha search loop — this is
> asserted by a unit test that walks the module AST.

---

# RECOMMENDATION (up front)

## Do NOT merge a factorized Opening Appeal into RIP. Keep the 10% Universal Roster Appeal pillar as-is. But this study did **not** reproduce the previous "nothing works" verdict: `D × M*` is a strong, robust **Market Chase Strength** metric that deserves to ship as its own visible metric — under that name, not as "Opening Appeal".

The factorization hypothesis is **half right, and right about the wrong half.**

1. **Desirability was never double-counted in Accessibility.** The audit found
   `compute_accessible_appeal` weights by `appeal_excess / total_excess` — a
   *normalized share* whose absolute magnitude cancels. Accessible Appeal was
   **already factor-free**. The rebuilt `A*` is not merely rank-identical to it
   (ρ = 1.000) — it is **numerically identical**: `A* × 100` reproduces the
   shipping Accessible Appeal on all 21 sets to within **4.9e-5**, which is
   exactly the rounding incurred by storing `A*` at 6 dp and rescaling.
   Factorizing accessibility was a **literal no-op**.
2. **Desirability *was* genuinely double-counted in Magnetism**
   (`appeal_excess × scarcity`), which is why Magnetism correlated 0.75 with
   Roster Appeal while Accessibility sat at −0.15. This is the one real defect
   the factorization fixes.
3. **Fixing it worked, and the effect is large.** Stripping desirability out of
   Magnetism *improved* its market association (top-10 ρ **0.646 → 0.811**), and
   re-applying desirability exactly once on top gives `F4 = D × M*` at
   ρ = **0.865** — the strongest, most stable external association found in
   either study.
4. **But `D × M*` is not Opening Appeal.** It correlates **0.93 with `M*`** and
   **−0.50 with `A*`**: it carries essentially none of the accessibility
   information, and it beats Roster Appeal only on the six *value-level*
   outcomes while **losing on all three value-concentration outcomes**. Calling
   it Opening Appeal would rename a scarcity metric to preserve the original
   proposal.
5. **The formulas that genuinely represent opening experience fail.** `F1 =
   D·√(A*·M*)` scores ρ = 0.294 with a bootstrap CI **including zero**
   ([−0.252, 0.723]), held-out R² = **−0.70**, and 14 of 21 leave-one-set-out
   removals drop it below 0.30. `F5 = D × A*` scores −0.261, CI also including
   zero.

So the study succeeds on its stated terms — **factorization still does not
justify a merged Opening Appeal pillar** — but it does so for a different and
more interesting reason than the previous study, and it surfaces a genuine
positive result the previous study missed.

**Recommended action** (matching §22's stated fallback):

- Keep `RIP = 0.58 Profit + 0.20 Safety + 0.12 Stability + 0.10 UniversalRosterAppeal`.
- Ship **Market Chase Strength** (`D × M*`) as its own visible metric.
- Keep **Accessible Opening Appeal** (`A*`) visible and separate, reported as
  probabilities rather than a score (see §17).
- Do **not** ship a blended Opening Appeal under any of the tested formulas.

---

## 1. Was the algebraic factorization valid?

**No symbolic factorization of the final scores was performed, because it is not
mathematically valid.** The shipped 0–100 scores cannot be algebraically
factored: Universal Roster Appeal contains top-k slot selection, an HHI depth
term, and a saturating exponential; Accessible Appeal contains normalized subject
weights and slot-aware probability unions; Elite Chase Magnetism contains a
per-subject `max`. None of these commute with a scalar factorization.

The factorized model is therefore **constructed from the shared lower-level
subject/card inputs**, not derived from the final scores. This is the only
defensible route and it is what the code does.

**The audit's substantive finding** (the reason the whole premise needed
re-examining):

| Construct | Uses desirability as | Double-counted? |
|---|---|---|
| Universal Roster Appeal | absolute magnitude (the score itself) | — it *is* D |
| Accessible Appeal | **normalized share** `u_s / Σu_s` | **No — magnitude already cancels** |
| Elite Chase Magnetism | **absolute** `appeal_excess × scarcity` | **Yes** |

The merged `0.60·Roster + 0.20·Accessible + 0.20·Magnetism` therefore contained
desirability **twice** (Roster + Magnetism), never three times. The accessibility
path was innocent all along.

## 2. Exact definitions

```
u_s   = max((subject_demand_s - 50) / 50, 0)          # per DISTINCT subject
q_s   = u_s / sum(u_s)                                # normalized share

D1    = universal_roster_appeal / 100
D2    = 1 - exp(-sum(sqrt(u_s)) / K_D)                # K_D fixed, default 3.0

broad_access_structure = sum(q_s * access_transform(p_subject_s))
top3_access_structure  = P(>=1 card from the 3 highest-demand subjects)
A*    = 0.60 * broad + 0.40 * top3

subject_elite_scarcity_s = max(scarcity_transform(p_card) over s's cards)
M1    = 0.50*scarcity_top1 + 0.30*scarcity_top2 + 0.20*scarcity_top3   (ranked BY DEMAND)
M2    = sum(q_s * subject_elite_scarcity_s)
```

Desirability enters **once**, in `D`. `A*` and `M*` use desirability only to
*select* subjects (`u_s > 0`) and *prioritize* them (shares, demand ranking) —
never to scale magnitude again. A unit test proves this: **doubling every
subject's demand excess leaves `A*`, `M1`, and `M2` bit-identical while `D`
rises.** The old Magnetism could not pass that test.

`p_subject` is slot-aware: probabilities **add** within a mutually exclusive
slot and combine multiplicatively **only across independent slots**. All 21 sets
used **exact** slot calculations — no approximations were required
(`exact_slot_calculation: true`).

### D1 vs D2 — D2 is not an independent alternative

**D2 at `K_D = 3.0` is algebraically identical to Universal Roster Appeal's own
`favorite_hit_coverage` component ÷ 100** (asserted in a unit test against the
shipping function). D2 is not a new construct; it is **one of D1's three
components promoted to stand alone**, discarding Chase Subject Strength and
Chase Subject Depth.

| | ρ(D1, D2) | max rank Δ | mean rank Δ | D2 vs checklist size | D1 vs checklist size |
|---|---|---|---|---|---|
| K_D = 2.0 / 3.0 / 4.5 / 6.0 | **0.882** | 6 | 1.91 | 0.400 | 0.451 |

**Every saturation constant gives an identical rank correlation** — necessarily
so: `1 − exp(−raw/K)` is monotone in `raw`, so K_D changes only the scale, never
the ordering. Testing three constants was required and was done, but the answer
is analytically trivial. Largest movers: Obsidian Flames (−6), Surging Sparks
(−6), White Flare (+6).

Notably **D2 outperforms D1 on the primary outcome** (0.707 vs 0.551). That is
*not* a reason to adopt it: D2 is a strict subset of D1's information, and
preferring it would mean deleting Chase Strength and Depth because a
price correlation improved — exactly the price-driven construct selection this
project forbids (`scoring_config.py` documents why that gate was removed).

## 3. Do A* and M* remain complements?

**Not exactly — but they are strongly opposed, and the exactness depends on set
structure.**

| Pair | mean \|A+M−1\| | median | min | max | % sets < 0.01 | ρ(A*, M*) |
|---|---|---|---|---|---|---|
| A* vs M1 | 0.114 | 0.110 | 0.003 | 0.291 | 9.5% | **−0.523** |
| A* vs M2 | **0.069** | 0.060 | 0.004 | 0.164 | 9.5% | **−0.684** |
| broad vs M2 | 0.179 | 0.187 | 0.000 | 0.360 | 4.8% | −0.674 |

**Why they are not independent (algebra, not correlation):** at shared anchors
`access_transform(p) = 1 − scarcity_transform(p)` exactly. With **one card per
subject**, `subject_probability == p_card`, so
`broad = Σ q·access(p)` and `M2 = Σ q·(1−access(p)) = 1 − broad` **exactly** —
proved in a unit test. Complementarity is broken only by (a) multi-card
subjects, where the union probability exceeds the rarest card's probability
while `M*` takes the max scarcity, (b) A*'s top-3 term, and (c) M1's top-3
truncation vs M2's all-subject aggregation. **Independence is not claimed merely
because the observed ρ is not exactly −1.**

**F3 degeneracy.** Under exact complementarity
`F3 = D·((2α−1)·A* + (1−α))`, so at **α = 0.50 the A\* term vanishes entirely
and F3 = 0.5·D** — a rescaled roster baseline with zero structural content.
Empirically A*+M* are not *exactly* complementary, so `F3_alpha_0.50` is not
fully degenerate — but it retains almost no accessibility information
(ρ = **−0.166** with A*), confirming the prediction directionally.

## 4. Synthetic archetype behaviour

All 40 unit tests pass. Documented behaviour:

| Property | Result |
|---|---|
| Increasing D lowers any candidate? | **Never** (all 8 formulas) |
| Increasing A* lowers an A*-bearing candidate? | **Never**; F4/F6 correctly unmoved |
| Increasing M* lowers an M*-bearing candidate? | **Never**; F5/F6 correctly unmoved |
| One zero component | F1, F4 collapse to 0; F2 survives via the other path; F5 unaffected by M* |
| D = 0 | **All** candidates collapse to 0 — structure without desirability is never appeal |
| Lopsided sets | F1 punishes them; `F3_alpha_0.50` **cannot distinguish them at all** |
| low D / extreme M* | M* = 1.000 but F4 < 0.10 — scarcity alone earns no appeal |
| Unintuitive ties | `F3_alpha_0.50` ties even/lopsided pairs; F5/F6 tie across M* variation (by design) |

Also asserted: an accessible secondary printing cannot erase an elite chase
(`max`, not union); duplicate cards of one species cannot occupy multiple slots
or shares; M1 ranks **by demand**, so a rare-but-unloved subject cannot displace
a beloved one from slot 1; missing pull data returns unavailable, never 0; fixed
normalization is cohort-independent.

## 5. Candidate rankings (primary outcome: top-10 card value)

| Candidate | ρ | Bootstrap 95% CI | CI includes 0? |
|---|---|---|---|
| `D2_M1_F3_alpha_0.25` | **0.866** | [0.647, 0.941] | no |
| **`D1_M1_F4_market_chase`** | **0.865** | [0.660, 0.948] | no |
| `D1_M1_F2_either_path_union` | 0.861 | [0.649, 0.941] | no |
| `M1_star` *(structure alone)* | 0.811 | [0.494, 0.944] | no |
| `D2` | 0.707 | [0.375, 0.871] | no |
| `prior_elite_chase_magnetism` | 0.646 | [0.245, 0.893] | no |
| **`roster_appeal` = `D1` = F6 baseline** | **0.551** | [0.098, 0.823] | no |
| `D1_M1_F1_balanced_multiplicative` | **0.294** | **[−0.252, 0.723]** | **yes** |
| `D1_M1_F5_accessible_roster` | **−0.261** | **[−0.679, 0.204]** | **yes** |
| `A_star` = `prior_accessible_appeal` | −0.452 | [−0.740, −0.035] | no |

`F3_alpha_0.25` edges out F4 by 0.001 — a meaningless difference, and it is
0.90-redundant with `M*` anyway. F4 is preferred on interpretability.

## 6. Correlation with each market outcome

| Outcome | roster | D2 | A* | M1* | prior Magnetism | **F4 = D×M\*** | F1 balanced | F5 accessible |
|---|---|---|---|---|---|---|---|---|
| Top-10 card value | 0.551 | 0.707 | −0.452 | 0.811 | 0.646 | **0.865** | 0.294 | −0.261 |
| Top-3 card value | 0.592 | 0.695 | −0.353 | 0.750 | 0.658 | **0.830** | 0.320 | −0.151 |
| Median hit value | −0.117 | 0.191 | −0.716 | 0.357 | −0.075 | **0.278** | −0.379 | −0.677 |
| Mean hit value | 0.442 | 0.564 | −0.368 | 0.617 | 0.535 | **0.665** | 0.278 | −0.177 |
| Total hit value | 0.562 | 0.752 | −0.614 | 0.811 | 0.627 | **0.868** | 0.213 | −0.421 |
| Total set value | 0.551 | 0.747 | −0.617 | 0.815 | 0.614 | **0.871** | 0.208 | −0.423 |
| Top-1 value share | 0.416 | 0.221 | 0.338 | 0.029 | 0.455 | **0.140** | 0.355 | 0.392 |
| Top-3 value share | 0.244 | 0.056 | 0.378 | 0.058 | 0.310 | **0.099** | 0.269 | 0.386 |
| Value HHI | 0.297 | 0.121 | 0.401 | 0.117 | 0.392 | **0.157** | 0.356 | 0.433 |

**The split is structural, not noise.** F4 beats Roster on **6 of 9** outcomes —
every *value-level* outcome — and **loses on all 3 *concentration* outcomes**.
Concentration asks how value is *distributed*; A* is the only construct
positively associated with it (0.34–0.43). So F4 answers "how much value is
locked behind this set's chases", not "how concentrated is it".

## 7. Comparison with Roster Appeal

| | Roster | F4 = D×M* | Δ |
|---|---|---|---|
| Top-10 ρ | 0.551 | **0.865** | **+0.314** |
| Top-3 ρ | 0.592 | 0.830 | +0.238 |
| Total set value ρ | 0.551 | 0.871 | +0.321 |
| Bootstrap CI (top-10) | [0.098, 0.823] | [0.660, 0.948] | far tighter |
| LOSO range (top-10) | [0.480, 0.648] | [0.844, 0.899] | far tighter |
| Most influential set | **Black Bolt** (shift 0.098) | Paradox Rift (shift **0.034**) | more robust |

F4 beats Roster Appeal materially and consistently on value level, with a
tighter interval and less single-set dependence. **This is a real result and it
contradicts the prior study's blanket "merging makes external validity worse".**

## 8. Comparison with Elite Chase Magnetism

| | prior Magnetism | M* (factor-free) | F4 = D × M* |
|---|---|---|---|
| Top-10 ρ | 0.646 | **0.811** | **0.865** |
| Held-out R² | — | **+0.389** | **+0.641** |

**Removing desirability from Magnetism improved it by ρ +0.165.** The
double-counted desirability was *diluting* a scarcity signal, not strengthening
it. Re-applying D once on top adds a further +0.054 and, more importantly, a
large jump in held-out R² (0.389 → 0.641) — so D contributes genuine
information beyond M* alone rather than merely reordering it.

F4 vs Magnetism is **+0.219** on the primary outcome.

## 9. Bootstrap uncertainty

See §5. The decisive contrast: **F4's CI excludes zero and is tight
([0.660, 0.948]); F1's and F5's CIs both include zero.** The candidates that
claim to represent *opening experience* are the ones that cannot be
distinguished from no association at all.

## 10. Leave-one-set-out sensitivity

| Predictor | full | LOSO min | median | max | most influential | sign flips | drops < 0.30 |
|---|---|---|---|---|---|---|---|
| **F4 = D×M\*** | 0.865 | **0.844** | 0.866 | 0.899 | Paradox Rift (+0.034) | 0 | **0** |
| M1* | 0.811 | 0.781 | 0.805 | 0.858 | S&V Base Set (+0.047) | 0 | 0 |
| D2 | 0.707 | 0.665 | 0.702 | 0.774 | Journey Together (+0.068) | 0 | 0 |
| roster / D1 | 0.551 | 0.480 | 0.541 | 0.648 | **Black Bolt** (+0.098) | 0 | 0 |
| **F1 balanced** | 0.294 | **0.187** | 0.286 | 0.421 | **Black Bolt** (+0.128) | 0 | **14** |
| F5 accessible | −0.261 | −0.364 | −0.265 | −0.174 | Prismatic Evolutions (−0.103) | 0 | **17** |

No predictor's sign reverses under any removal. **F4 is the most stable
construct in the study.** F1 and F5 fall below 0.30 under 14 and 17 of 21
removals respectively — they are not robust by any reading.

## 11. Black Bolt influence

**Black Bolt drives the *old* constructs, not the factorized market-chase one.**
It is the most influential set for Roster Appeal (+0.098), prior Magnetism
(+0.114), and F1 (+0.128) — but for F4 it is not the most influential set at all
(Paradox Rift is, at a mere +0.034). Removing any single set leaves F4 within
[0.844, 0.899]. The prior study's warning that "no single-set finding is safe"
applies to Roster and F1; F4 escapes it.

## 12. Set-size and subject-count bias

| Construct | checklist size | eligible cards | distinct subjects |
|---|---|---|---|
| A* | −0.310 | **−0.772** | −0.756 |
| F5 = D×A* | −0.235 | −0.644 | −0.635 |
| D1 | 0.451 | 0.435 | 0.442 |
| M1* | 0.263 | 0.718 | 0.674 |
| **F4 = D×M\*** | 0.362 | **0.777** | 0.739 |
| **F1 balanced** | 0.292 | **0.016** | **−0.012** |

**This is F4's most serious defect.** ρ = **0.777** with eligible-card count —
just under the 0.80 flag but directionally unambiguous: bigger sets have more
elite chases, and part of F4's market win is "this set is large". Since two of
its strongest outcomes (total hit value, total set value) are themselves
size-sensitive, some of that association is mechanical.

A* carries the mirror-image defect (−0.772), exactly as the prior study found.
F1 is the only candidate that is genuinely size-neutral (0.016) — and it is the
one with no market signal.

## 13. Relative pull-rate uncertainty

Seeded log-normal multiplicative shocks on each set×rarity odds (200 draws per
scenario, seed `20260717`). These are **uncertainty scenarios, not empirically
estimated confidence bounds** — the modeled pull rates carry no source sample
counts to propagate.

| Scenario | | F1 | **F4** | A* | M1* |
|---|---|---|---|---|---|
| ±10% independent | median ρ | 0.994 | **0.995** | 0.983 | 0.993 |
| | p05 ρ | 0.984 | 0.988 | 0.969 | 0.985 |
| | within ±3 ranks | 100% | 99.9% | 98.9% | 100% |
| ±20% independent | median ρ | 0.981 | **0.986** | 0.959 | 0.979 |
| | within ±3 ranks | 98.0% | 98.9% | 93.0% | 98.6% |
| ±30% independent | median ρ | 0.965 | **0.974** | 0.923 | 0.959 |
| | p05 ρ | 0.926 | 0.952 | 0.855 | 0.924 |
| | within ±3 ranks | 95.0% | 96.6% | **85.5%** | 94.1% |

**Every construct survives relative error well; F4 is the most stable and A* the
least.** The uniform calibration scenarios (±15%, ±25%) are near-meaningless by
construction (all ρ ≥ 0.983) — a uniform multiplier shifts every set together —
which is precisely why the relative test above was the one that mattered.

## 14. Sparse incremental models — held-out R² shown prominently

Outcome `Y = log(top_10_card_value)`, leave-whole-set-out validation, n = 21.

| Model | Held-out **R²** | MAE | Spearman | Beats the mean? | Sets improved vs B0 |
|---|---|---|---|---|---|
| B0: controls only | **−0.309** | 0.705 | −0.096 | **No** | — |
| B1: + D | **−0.940** | 0.737 | 0.164 | **No** | 11/21 |
| B2: + M* | **+0.389** | 0.474 | 0.710 | **Yes** | 16/21 |
| **B3: + D × M\*** | **+0.641** | **0.355** | **0.858** | **Yes** | **16/21** |
| B4: + best opening-experience (F1) | **−0.704** | 0.796 | −0.309 | **No** | 6/21 |

**This is the sharpest break from the prior study.** There, *every* set-level
model had negative held-out R², so no incremental comparison meant anything.
Here B2 and B3 are solidly **positive** — they genuinely beat predicting the
mean — and B3 halves B0's error. The `D × M*` result therefore does **not** fall
to the objection that sank the previous one.

The reverse also holds and is reported plainly: **B1 (+D) and B4 (+F1) remain
negative.** Roster Appeal alone and the balanced opening-experience candidate
still fail to beat the mean. B4 is *worse* than the controls.

B4's predictor was chosen **by construct** (F1 is the formula that claims to
represent both A* and M*), never by scanning outcomes for the best correlation.

## 15. Internal redundancy matrix

Flagged at |ρ| > 0.80.

| Construct | roster | D1 | D2 | A* | M1* | Profit | Safety | Stability | eligible cards |
|---|---|---|---|---|---|---|---|---|---|
| D1 | **1.000** ⚑ | — | **0.882** ⚑ | −0.151 | 0.283 | −0.324 | −0.364 | −0.547 | 0.435 |
| D2 | **0.882** ⚑ | **0.882** ⚑ | — | — | — | — | — | — | — |
| A* | −0.151 | −0.151 | — | — | −0.523 | 0.281 | 0.581 | 0.139 | **−0.772** |
| M1* | 0.283 | 0.283 | — | −0.523 | — | −0.304 | −0.183 | −0.495 | 0.718 |
| **F4 = D×M\*** | 0.565 | 0.565 | — | **−0.501** | **0.930** ⚑ | −0.393 | −0.283 | −0.553 | **0.777** |
| F1 balanced | 0.520 | 0.520 | — | 0.392 | 0.328 | −0.023 | 0.235 | −0.275 | 0.016 |
| F5 = D×A* | 0.158 | 0.158 | — | **0.916** ⚑ | −0.444 | 0.201 | 0.429 | 0.031 | −0.644 |

Per-candidate reading:

- **F4** — *mostly Magnetism restated* (ρ 0.930 with M*). Retains **no**
  accessibility information (−0.501). **Not** redundant with any financial
  pillar (max |ρ| = 0.553 with Stability), so it is a genuinely distinct axis
  from Profit/Safety/Stability. Materially size-driven (0.777).
- **F1** — the only candidate retaining meaningful information from *both* A*
  (0.392) and M* (0.328), and the only size-neutral one (0.016). It is the
  honest opening-experience construct — and it has no market signal.
- **F5** — essentially A* restated (0.916).
- **F6/D1** — trivially identical to Roster Appeal (1.000).
- **A\*** — **ρ = 1.000 with the prior Accessible Appeal, and numerically
  identical to it** (`A* × 100` matches the shipping score on all 21 sets to
  within 4.9e-5 = display rounding). The factorization was a literal no-op here,
  as the audit predicted.

**No candidate that includes A* and claims to balance accessibility survives:**
F4 correlates −0.50 with A*, so describing it as balancing accessibility would
be false.

## 16. RIP influence

Baseline = current shipping RIP (10% Universal Roster Appeal).

| Candidate @ weight | max rank Δ | mean rank Δ | max score Δ | ρ vs current RIP | Top-10 changes |
|---|---|---|---|---|---|
| F4 @ 5% | 2 | 0.76 | 5.21 | 0.984 | Shrouded Fable in / Stellar Crown out |
| **F4 @ 10%** | **5** | **1.62** | 4.41 | 0.946 | Destined Rivals in / Stellar Crown out |
| F4 @ 15% | **7** | **2.76** | 4.01 | 0.855 | Destined Rivals in / Stellar Crown out |
| F1 @ 10% | 3 | 0.86 | 6.18 | 0.978 | Destined Rivals, Shrouded Fable in / Ascended Heroes, Stellar Crown out |
| F5 @ 10% | 3 | 0.67 | 7.96 | 0.981 | Shrouded Fable in / Ascended Heroes out |
| F6 (roster) @ 10% | **0** | **0.00** | 0.00 | 1.000 | none — identical to today |

**Unlike the prior study, the fourth pillar would no longer be
non-load-bearing.** F4 at 10% moves sets up to 5 places (mean 1.62), and at 15%
up to 7. So "it wouldn't change anything anyway" is **not** available as an
argument here — swapping in F4 *would* materially change user-facing rankings.

That cuts both ways, and it is why the recommendation is still no: a change this
material must be justified by construct validity, and F4's construct is *market
chase strength*, not desirability. Replacing the desirability pillar with a
scarcity-driven, size-correlated (0.78) price proxy would quietly convert 10% of
RIP into a second financial term — while RIP already spends 90% on
Profit/Safety/Stability. The pillar's purpose is to represent what collectors
*want*, which is exactly the thing F4 does not measure.

## 17. Product interpretation of each candidate

| Candidate | Label | Reading |
|---|---|---|
| `F6 = D` | `universal_roster_appeal` | The shipping pillar. Simplicity benchmark. |
| **`F4 = D × M*`** | **`market_chase_strength`** | Popular subjects behind modeled scarcity. Strong, robust market association. **Not** a complete Opening Appeal measure. |
| `F5 = D × A*` | `accessible_opening_appeal` | Desirable roster you can realistically reach. Valid construct; negatively associated with value **because accessibility reduces scarcity** — that is expected, not a defect. |
| `F1 = D·√(A*·M*)` | `balanced_opening_experience` | The only candidate that honestly represents both axes and is size-neutral. No market signal (CI includes zero). |
| `F2`, `F3_*` | `not_recommended` | `F2`/`F3_0.25` are ≥0.88 redundant with M*; `F3_0.50` retains almost no A* information (−0.166); `F3_0.75` is weak on every outcome. |

Construct validity and market validity are kept separate throughout:
**`D × M*` is not called Opening Appeal despite winning market validation, and
`D × A*` is not called invalid despite its negative price association.**

### The user-facing form Accessibility should take

A 0–1 score is not actionable; probabilities are. For the most accessible sets:

| Set | P(top-3 subject)/pack | median packs | P per ETB (9) | P per box (36) |
|---|---|---|---|---|
| Phantasmal Flames | 0.0576 (1-in-17.4) | 11.7 | 41.4% | 88.2% |
| Journey Together | 0.0481 (1-in-20.8) | 14.1 | 35.8% | 83.0% |
| Chaos Rising | 0.0469 (1-in-21.3) | 14.4 | 35.1% | 82.3% |
| Perfect Order | 0.0432 (1-in-23.2) | 15.7 | 32.8% | 79.6% |

(Per-opening figures assume independent packs, which overstates certainty for
products with anti-duplicate or guaranteed-slot rules.)

## 18. Recommended formula

**None for RIP.** Retain:

```
RIP = 0.58·Profit + 0.20·Safety + 0.12·Stability + 0.10·UniversalRosterAppeal
```

Ship `D × M*` as **Market Chase Strength**, a separate visible metric, using D1
(the existing Roster Appeal) — not D2, which would mean deleting Chase Strength
and Depth on the basis of a price correlation.

Against the §22 standard, F4 satisfies 1, 2, 3, 4, 5, 6, and 8, but **fails 7**
(size proxy, ρ = 0.78), **fails 9** (claims no accessibility content — it has
none, ρ = −0.50), and fails the spirit of 10 as an *Opening Appeal* replacement:
its product value is real but it is a different product.

**Priority follow-up:** the deferred **collector-preference validation**
(financially-matched pairwise "which would you rather open?") is now the
decisive missing evidence. Every construct here that plausibly represents
opening *experience* (F1, A*) is unmeasurable against price by construction —
accessibility *lowers* scarcity and therefore price. Another price regression
cannot resolve this; a preference-elicitation mechanism can.

## 19. Known limitations

1. **n = 21 sets.** Every set-level result rests on 21 points. F4's stability is
   reassuring but 21 clusters is thin for any inference.
2. **F4's win is partly mechanical.** Scarcity→price is close to the definition
   of a chase market, and two of F4's strongest outcomes (total hit value, total
   set value) are size-sensitive while F4 itself is size-correlated at 0.78.
   Some of the +0.31 over Roster is "large sets have more expensive rare cards".
3. **The scale-mixing caveat in A\*.** The pre-registered `A*` mixes a
   log-scaled `broad` term with a **linear** raw-probability `top3` term. Real
   top-3 per-pack probabilities are tiny, so the raw term averages **0.033**
   against `broad`'s scale, dragging mean A* to 0.275. The pre-registered
   definition was followed literally; the same-axis variant
   (`top3_mode=access_transform`, mean top3 = 0.715, mean A* = 0.547) is
   reported as a sensitivity and changes A*'s ranking only slightly (ρ = 0.981).
   This is a defect in the specification, not in the data.
4. **Only 2 eras** have a pull model (S&V 16 sets, Mega Evolution 5). **Lost
   Origin is excluded entirely** this time — it has no hit-eligible card with
   both an appeal link and a modeled pull rate — so there is **no external
   holdout** in this study.
5. **Modeled, not observed, pull rates**, constant within set×rarity. The
   relative-error scenarios are transparent assumptions, not estimated bounds.
6. **D2's K_D sensitivity is vacuous by construction** (monotone transform ⇒
   rank-invariant). Reported for completeness only.
7. **Contemporaneous only.** Nothing here predicts future prices, and no such
   claim is made.
8. **Blocked:** collector-preference validation; per-rarity pull-rate
   uncertainty bounds; pull models for pre-S&V eras.

## 20. Exact test results

| Suite | Result |
|---|---|
| `test_factorized_opening_appeal.py` (new) | **40 passed, 0 failed** |
| `backend/tests/unit/desirability` (full) | **168 passed, 0 failed** (128 pre-existing, unchanged) |
| Frontend contract tests | **not run — no payload/frontend code was touched** |

No service tests were affected: the new module is imported only by the study
script and its own tests (verified by search); nothing in production references
it. A unit test asserts the module contains no database access, and a
grep for `insert/upsert/update/delete` against both new files returns nothing.

## 21. Exact files changed

| File | Status | Purpose |
|---|---|---|
| `backend/desirability/factorized_opening_appeal.py` | **added** | D / A* / M* factors and F1–F6 candidates (research only) |
| `backend/scripts/build_factorized_opening_appeal_study.py` | **added** | The study; reuses `build_opening_appeal_study.py`'s IO layer |
| `backend/tests/unit/desirability/test_factorized_opening_appeal.py` | **added** | 40 archetype / monotonicity / purity / algebra tests |
| `docs/research/factorized_opening_appeal_study.json` | **added** | Raw output backing every table above |
| `docs/research/factorized-opening-appeal-results.md` | **added** | This document |
| `backend/requirements.txt` | **modified** | Declared `numpy==2.4.3` (direct import, previously undeclared) |

No production module, payload, frontend file, or database object was touched.

---

## Final decision table

| Decision question | Evidence | Verdict |
|---|---|---|
| Factorization mathematically valid? | Final scores contain top-k, HHI, max, saturation ⇒ not factorable; model rebuilt from lower-level inputs instead. Desirability-applied-once proved by test. | **Yes, as constructed — but the premise was half wrong: Accessibility was already factor-free (A* ρ=1.000 with the old score); only Magnetism double-counted.** |
| Beats Roster Appeal? | F4: +0.314 top-10, +0.321 set value, 6/9 outcomes; CI [0.660, 0.948] vs [0.098, 0.823] | **Yes for F4 (value outcomes only; loses all 3 concentration outcomes). No for F1 (+ −0.257) or F5.** |
| Beats Magnetism? | F4 0.865 vs 0.646 (+0.219); held-out R² 0.641 vs M*-alone 0.389 | **Yes — and factor-free M* alone (0.811) already beats the old Magnetism by +0.165.** |
| Retains Accessibility information? | F4 ρ = **−0.501** with A*; F1 ρ = 0.392 | **No for F4. Yes only for F1 — the candidate with no market signal.** |
| Stable without influential sets? | F4 LOSO [0.844, 0.899], 0 sign flips, 0 drops <0.30, Black Bolt not influential; F1 14/21 drops <0.30 | **Yes for F4. No for F1/F5.** |
| Stable to relative pull error? | ±30% independent: F4 median ρ 0.974, 96.6% within ±3 ranks; A* weakest at 0.923 / 85.5% | **Yes, all constructs.** |
| Nonredundant with RIP pillars? | F4 vs Profit/Safety/Stability max \|ρ\| = 0.553; but ρ = 0.930 with M* and **0.777 with eligible-card count** | **Yes vs financial pillars; No vs M*; materially size-driven.** |
| Changes user decisions meaningfully? | F4 @10%: max rank Δ **5**, mean 1.62, ρ 0.946 vs current RIP | **Yes — materially, unlike the previous study's ≤3 / <0.6.** |
| Suitable as Opening Appeal? | Carries none of the accessibility axis (−0.50); the formulas that do (F1, F5) have CIs including zero and negative held-out R² | **No.** |
| Suitable as Market Chase Strength? | ρ 0.865, CI excludes zero, LOSO [0.844, 0.899], held-out R² **+0.641**, distinct from financial pillars | **Yes — ship it under that name, at 0% RIP weight.** |
