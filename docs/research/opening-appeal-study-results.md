# Opening Appeal Pillar — Follow-Up Study Results

**Status: research only. Nothing committed, nothing wired into RIP, no database
writes.** Opening Appeal is **not** in the canonical RIP score.

- Run date: 2026-07-16. Database: Supabase `TheIndex` (`zwxzxuuawalvwioadhmf`).
- Reproduce: `backend/scripts/build_opening_appeal_study.py` and
  `backend/scripts/build_repeated_species_correction.py`.
  Raw output: `docs/research/opening_appeal_study.json`,
  `docs/research/repeated_species_correction.json`.
- Constructs: `backend/desirability/opening_appeal.py`. Tests:
  `backend/tests/unit/desirability/test_opening_appeal.py`.
- Dev-environment note: `statsmodels` was installed into `backend/.venv` for the
  crossed mixed-effects model. No repo dependency file was changed.

> Price is used **only** as an external outcome. It never entered the
> construction, normalization, internal weighting, or selection of any Opening
> Appeal candidate. No weight in this study is fitted to price. The pull input is
> **modeledPullScarcity** (config-derived pack model), never observed scarcity.

---

# RECOMMENDATION (up front)

## Do NOT merge the three submetrics into a single Opening Appeal pillar. Keep RIP's fourth component as-is (10% Universal Roster Appeal), and surface Accessible Appeal and Elite Chase Magnetism as separate, visible simulation-only metrics.

Five independent reasons, any one of which would be sufficient:

1. **Opening Appeal is largely Universal Roster Appeal restated.** Every
   candidate correlates **ρ = 0.88–0.94** with Roster Appeal — over the 0.80
   redundancy flag. The prompt's own rule applies: *"If Opening Appeal is nearly
   identical to Universal Roster Appeal, recommend retaining the simpler
   Desirability pillar."*
2. **Merging makes external validity worse, not better.** On the primary outcome
   (top-10 card value) Roster Appeal alone scores ρ = **0.551**; the best
   candidate scores **0.508**, and every candidate is *worse* than Roster alone
   on 5 of 7 market outcomes. Opening Appeal's bootstrap CI on the primary
   outcome **includes zero** ([−0.005, 0.845] for OA_60_20_20) while Roster's
   does not.
3. **The one result that favours merging is not trustworthy.** The sparse
   incremental models appear to show OA beating Roster (−6.1% MAE, +0.065
   Spearman, gate=True), but **every one of those models has negative held-out
   R²** (B0 −0.31, B1 −0.94, B2 −0.52): none of them beats predicting the mean.
   With n = 21 sets, "OA is 6% better" compares two models that both fail. It
   would be dishonest to cite it as support. Details in §7.
4. **Accessible Appeal is close to an inverse set-size proxy.** ρ = **−0.77**
   with eligible-card count and −0.76 with distinct-subject count, and it is
   *negatively* associated with every value outcome (top-10 ρ = **−0.45**, CI
   excluding zero). Folding it into a scored pillar imports "small sets score
   higher" into RIP.
5. **It would not change RIP anyway.** Across all candidates at 5/10/15%, the
   maximum rank movement is **3 places** and the mean is **< 0.6**. The fourth
   pillar remains non-load-bearing; the added surface area buys nothing.

**The genuine find is Elite Chase Magnetism**, which deserves to be visible:
it is the **strongest single external predictor in the study** (top-10 ρ =
**0.646**, CI [0.245, 0.893] — *better than Roster Appeal's 0.551*), it is
distinct from every financial pillar (max |ρ| = 0.59), and it is near-immune to
pull-rate error. It should ship as its own metric — not blended into a score
where its signal is diluted by Roster and cancelled by Accessibility.

This matches the stated acceptance standard: *"The study is successful if it
concludes that the three submetrics should remain visible and unmerged."*

---

## 1. Is a single Opening Appeal pillar conceptually defensible?

**Partly — but not as a merged score.** The three submetrics answer genuinely
different questions, and the data confirms they are not interchangeable:

| Pair | Spearman | Reading |
|---|---|---|
| Accessible ↔ Magnetism | **−0.099** | essentially unrelated (mildly opposed) |
| Accessible ↔ Roster | −0.151 | unrelated |
| Magnetism ↔ Roster | 0.751 | related but distinct |

Conceptually the pillar is coherent ("how appealing is this to *open*"). The
problem is arithmetic: averaging three axes where two are near-orthogonal and
one is dominant produces a number that mostly tracks the dominant one (Roster,
ρ = 0.93) while cancelling the other two against each other. The merged score is
harder to explain *and* weaker than its own best component.

**There is also an unavoidable structural tradeoff, documented rather than hidden:**
at shared anchors, `access_transform(p) = 1 − scarcity_transform(p)` exactly.
Accessibility and Magnetism read the same probability axis from opposite ends, so
**making a set's chase cards easier necessarily raises Accessibility and lowers
Magnetism.** They are not independent design dials; a single blended score
partially cancels them (this is asserted in the archetype tests).

## 2. Do the candidate formulas rank sets similarly?

**Yes — near-identically, so the internal weighting choice is immaterial.**

| | OA_60_20_20 | OA_50_25_25 | OA_70_15_15 | OA_balanced |
|---|---|---|---|---|
| OA_60_20_20 | — | 0.978 | **0.999** | 0.992 |
| OA_50_25_25 | 0.978 | — | 0.978 | 0.987 |
| OA_70_15_15 | 0.999 | 0.978 | — | 0.991 |
| OA_balanced | 0.992 | 0.987 | 0.991 | — |

All pairwise rank correlations are **0.978–0.999**. Debating 60/20/20 vs
70/15/15 is not a real decision. Distributions (n=21): means 59.3–69.6, SD ≈ 8.

The balance-sensitive candidate is *not* recommended: it ranks the same as the
others (0.987–0.992) while being the **only candidate to fail the directional
gate** (+0.12% MAE, **−0.14** Spearman). Its distinctive behaviour — punishing
lopsided sets — is real (proved in unit tests) but does not survive contact with
this cohort.

## 3. Are Accessibility and Magnetism meaningfully distinct?

**Yes, strongly (ρ = −0.099) — and this is the argument for keeping them separate
rather than merging them.** They are distinct from the financial pillars too:

| | Roster | Accessible | Magnetism | Profit | Safety | Stability | Checklist size | Eligible cards |
|---|---|---|---|---|---|---|---|---|
| **Accessible Appeal** | −0.151 | — | −0.099 | 0.281 | 0.581 | 0.139 | −0.310 | **−0.772** |
| **Elite Chase Magnetism** | 0.751 | −0.099 | — | −0.307 | −0.242 | **−0.587** | 0.431 | 0.432 |

- **No redundancy flags** for either submetric against any pillar.
- **Accessibility ↔ Safety = 0.581** and **Accessibility ↔ eligible cards = −0.772**:
  accessible sets are small and low-variance. Accessibility does *not* duplicate
  Safety outright, but it leans the same way and is heavily size-driven.
- **Magnetism ↔ Stability = −0.587**: magnetic sets concentrate value in few
  chases. It does **not** duplicate Profit (−0.307) or Roster's role.

**Verdict:** Magnetism does not duplicate Profit or Desirability; Accessibility
does not duplicate Safety or Stability outright, but its size dependence is a
real defect (§11).

## 4. Corrected Elite Chase Magnetism

Now reproduces the construct the market study validated — **card-level** appeal ×
**card-level** modeled scarcity — instead of a subject's any-card probability:

```
card_magnetism    = appeal_excess(subject) · scarcity_transform(p_card)
subject_magnetism = max(card_magnetism over that subject's cards)
EliteChaseMagnetism = 0.50·top1 + 0.30·top2 + 0.20·top3   (distinct subjects)
```

Taking **max** (not a union probability) is what stops an accessible secondary
printing from erasing an elite chase; collapsing to distinct subjects stops one
Pokémon occupying several chase slots. Both are asserted in unit tests. The
top sets show it working as intended:

| Set | Magnetism | Top chase |
|---|---|---|
| Ascended Heroes | 73.3 | Charizard — Mega Charizard Y ex, **1-in-1080** |
| Prismatic Evolutions | 64.8 | Pikachu — Pikachu ex, 1-in-900 |
| Paldean Fates | 60.3 | Charizard — Charizard ex, 1-in-465 |
| S&V 151 | 49.0 | Charizard — Charizard ex, 1-in-248 |

**Sensitivity (rank Spearman vs default):** top-1 only **0.943**, top-5 **0.990**;
anchors 1-in-5→1-in-500 **0.978**, 1-in-20→1-in-2000 **0.983**. The construct is
robust to every structural choice tested.

## 5. Corrected slot-aware Accessible Appeal

Subject encounter probability now respects pack structure: probabilities **add**
within a mutually-exclusive slot (`slot_label` from the pack model) and combine
multiplicatively **only across independent slots**. The independence formula is
never applied to cards sharing a slot (asserted in tests). `top3_accessibility`
unions the top-three subjects' **cards** through the slot logic, never their
subject-level probabilities.

`broad_accessibility` is appeal-weighted, so it asks "of the appeal this set
has, how much can you actually reach?" rather than rewarding roster size.

**Result: Accessible Appeal is the study's problem child.** ρ = −0.77 with
eligible-card count; ρ = **−0.45** with top-10 value (CI [−0.74, −0.035],
excludes zero). It is measuring, to a large degree, "this set is small, so its
few desirable cards are easy to hit" — which is why it drags every merged
candidate's market association down. Rank ordering is perfectly stable across
anchors (ρ = 1.000).

## 6. Repeated-species-adjusted market study

The original study clustered only by **set**, but Appeal is a **species-level**
variable repeated across cards and sets (every Charizard shares one appeal
value). Three specifications on the pooled modern cohort (3,608 cards / 21 sets /
933 species):

| Term | A: set FE, cluster by set | B: two-way cluster (set × species) | C: crossed mixed effects |
|---|---|---|---|
| `appeal` | **+0.02273** (se 0.00155, t=14.68) | se **0.00203**, t=**11.22** | **+0.02204**, t=16.79 |
| `pull_scarcity` | +1.9287 (t=9.89) | se 0.20469, t=9.42 | +1.8897, t=36.75 |
| `appeal × scarcity` | **+0.02400** (t=9.67) | se 0.00274, t=**8.76** | **+0.02265**, t=17.18 |
| `treatment_prestige` | +2.4247 (t=5.49) | se 0.44233, t=5.48 | +2.5784, t=24.05 |

**The Appeal finding survives the correction.** Two-way clustering inflates the
Appeal standard error by ~31% (0.00155 → 0.00203) — a real, material correction —
but t = 11.2 remains overwhelming, and the coefficient is unchanged in direction
and practical magnitude across all three specs.

**Spec C variance decomposition — the correction was warranted:**

| Component | Variance share |
|---|---|
| **Species** | **19.9%** |
| Set | 12.6% |
| Residual | 67.5% |

**Species carries *more* variance than set.** Clustering only by set was
genuinely understating dependence, exactly as suspected. Spec C converged (REML,
crossed variance components; species is a **random** intercept — as a fixed
effect it would absorb the species-level Appeal variable entirely). Note Spec C's
t-statistics are the largest of the three: random-intercept SEs are not
cluster-robust, so **prefer Spec B / the wild bootstrap for inference.**

**Wild cluster bootstrap by set** (Rademacher, 400 draws — preferred with only
~21 clusters):

| Term | Point | 95% CI | Share positive |
|---|---|---|---|
| `appeal` | +0.02273 | **[+0.01981, +0.02551]** | 100% |
| `appeal × scarcity` | +0.02400 | **[+0.01921, +0.02854]** | 100% |
| `pull_scarcity` | +1.92866 | [+1.57191, +2.28390] | 100% |
| `treatment_prestige` | +2.42465 | [+1.68910, +3.21687] | 100% |

**Finite-cluster limitation, stated plainly:** cluster-robust inference is
asymptotic in the *number of clusters*, and ~21 sets is few. Species clusters are
plentiful (~933) but sets are not, so the set dimension binds. The two-way
estimator is also not guaranteed positive semi-definite in finite samples (no
negative variances occurred here). This is why the wild bootstrap is the
preferred inference, not the analytic SEs.

## 7. Card-weighted vs equal-set validation

**Card-level model (appeal added to controls + scarcity), pooled modern:**

| Validation | Card-weighted MAE lift | Set-balanced MAE lift | Spearman gain | Sets improved |
|---|---|---|---|---|
| Leave-whole-set-out | **+6.49%** | **+5.90%** | +0.031 | **17/21** |
| Grouped species, 10-fold | +6.89% | +6.24% | +0.031 | 17/21 |
| Grouped species, 20-fold | +6.95% | +6.32% | +0.032 | 17/21 |

**Appeal's card-level lift is not an artifact of repeated species.** Grouped
species CV — where every card of a species is held out together, so a species can
never leak into its own test fold — reproduces the lift almost exactly (+6.9% vs
+6.5%). Set-balanced metrics agree with card-weighted ones, so this is not
large-set dominance. It clears both directional gates on every validation scheme.

**Set-level Opening Appeal models (n=21) — do NOT rely on these:**

| Model (outcome: top-10 card value) | Held-out MAE | Spearman | **Held-out R²** |
|---|---|---|---|
| B0: controls only | 0.7045 | −0.096 | **−0.31** |
| B1: + Roster Appeal | 0.7371 | 0.164 | **−0.94** |
| B2: + OA_60_20_20 | 0.6925 | 0.229 | **−0.52** |
| B2: + OA_50_25_25 | 0.6806 | 0.239 | **−0.40** |
| B2: + OA_balanced | 0.7363 | 0.022 | **−0.69** |

Every held-out R² is **negative** — each model predicts worse than the sample
mean. B1 (Roster) is *worse than B0* (controls only) by 4.6% MAE. The
much-quoted "OA beats Roster by 6.1% MAE, gate=True" is therefore a comparison
between two failing models on 21 points, and **is not evidence for merging.**
Reported because it is the one pro-merge signal in the study, and suppressing it
would be dishonest — but it does not survive scrutiny.

## 8. Pooled modern results with era diagnostics

Pooled cohort: **Scarlet & Violet (16 sets, 80.8% of cards) + Mega Evolution
(5 sets, 19.2%)**. A single pooled model is retained; no per-era production
formula was built. Era is included as a control. Diagnostic interactions (wild
bootstrap, 400 draws):

| Interaction | Coefficient | 95% CI | Share positive | Reading |
|---|---|---|---|---|
| `era × scarcity` | **+1.357** | [+0.376, +2.410] | 100% | Mega Evolution's scarcity slope is materially **steeper** |
| `era × prestige` | **−3.001** | [−4.899, −1.016] | **0%** | Prestige's effect is **cancelled** in Mega Evolution (2.42 − 3.00 ≈ −0.58) |
| `appeal` | +0.02261 | [+0.01957, +0.02533] | 100% | unchanged by era controls |
| `appeal × scarcity` | +0.02260 | [+0.01823, +0.02691] | 100% | unchanged by era controls |

**Both era interactions are material and both CIs exclude zero.** So the pooled
headline for *scarcity* and *prestige* over-generalizes from Scarlet & Violet,
which supplies four-fifths of the cards. **Appeal and appeal×scarcity are the
only terms stable enough to state pooled** — which is convenient, because they
are the terms the product actually relies on. This rigorously confirms the
earlier era-specific prestige instability.

## 9. Lost Origin external holdout (directional only)

Trained on pooled modern (S&V + Mega Evolution), scored the single Sword & Shield
set:

| Metric | Value |
|---|---|
| n cards | 108 |
| MAE (log price) | **0.471** |
| Spearman | **0.516** |
| Mean bias | **+0.341** (model *under*-predicts Lost Origin prices) |

Ordering transfers moderately (ρ = 0.52) but levels do not: the model
systematically under-prices Lost Origin by ~0.34 log points (≈ 41%), consistent
with an older set whose prices have appreciated beyond what the modern
release-age control anticipates. **Directional only. One set is not an era model,
and this must not be generalized to the Sword & Shield era.**

## 10. Pull-rate uncertainty

`modeledPullScarcity` is a config-derived model, not observed data. No source
sample counts or confidence bounds exist, so transparent scenarios were run
(rank Spearman vs base):

| Scenario | Accessible | Magnetism | OA_60_20_20 |
|---|---|---|---|
| Base | 1.000 | 1.000 | 1.000 |
| 15% easier | 0.998 | 0.997 | 0.999 |
| 15% harder | 1.000 | 0.996 | 1.000 |
| 25% easier | 0.996 | 0.995 | 0.999 |
| 25% harder | 1.000 | 0.996 | 1.000 |

**Every construct is essentially immune to ±25% pull-rate error** (ρ ≥ 0.995).
A uniform multiplier shifts all sets together, so rank ordering barely moves;
this tests *calibration* error, not *relative* error between sets, which would be
the harsher test and is not currently estimable. Card-level coefficients under
the same scenarios are in the JSON.

## 11. Size and duplicate-species bias

- **Accessible Appeal is substantially an inverse size proxy:** ρ = −0.772
  (eligible cards), −0.756 (distinct subjects), −0.310 (checklist size). Just
  under the 0.80 flag, but directionally unambiguous.
- **Magnetism is mildly size-positive** (ρ = 0.43): bigger sets have more elite
  chases, which is partly real.
- **Merged candidates inherit both:** ρ ≈ 0.41–0.45 with checklist size.
- **Duplicate species cannot inflate anything:** subjects are collapsed by
  `pokemon_reference_id`; one Pokémon occupies exactly one Magnetism slot
  (asserted in tests), and Accessibility's appeal weights normalize across
  distinct subjects.

## 12. Redundancy with RIP pillars

| Candidate | Roster | Magnetism | Accessible | Profit | Safety | Stability |
|---|---|---|---|---|---|---|
| OA_60_20_20 | **0.933** ⚑ | **0.857** ⚑ | 0.012 | −0.282 | −0.240 | −0.492 |
| OA_50_25_25 | **0.882** ⚑ | **0.861** ⚑ | 0.134 | −0.205 | −0.118 | −0.475 |
| OA_70_15_15 | **0.942** ⚑ | **0.851** ⚑ | 0.000 | −0.294 | −0.256 | −0.494 |
| OA_balanced | **0.917** ⚑ | **0.849** ⚑ | 0.082 | −0.277 | −0.221 | −0.481 |

⚑ = |ρ| > 0.80. **Every candidate is flagged redundant against Roster Appeal and
against Magnetism.** None is flagged against any financial pillar — Opening
Appeal's problem is not that it duplicates Profit/Safety/Stability, it is that it
duplicates *the thing it would replace*. Note the striking ρ ≈ 0.01 with
Accessible Appeal: the merged score carries almost **none** of Accessibility's
information, so including Accessibility in the formula is nearly cosmetic while
still importing its size bias.

## 13. RIP rank influence

Baseline = current shipping RIP (10% Universal Roster Appeal):

| Candidate @ weight | Max abs rank Δ | Mean abs rank Δ | Top-10 changes |
|---|---|---|---|
| OA_60_20_20 @ 5% | 3 | 0.48 | Shrouded Fable in / Ascended Heroes out |
| OA_60_20_20 @ 10% | 2 | 0.19 | Shrouded Fable in / Stellar Crown out |
| OA_60_20_20 @ 15% | 1 | 0.29 | Destined Rivals in / Stellar Crown out |
| OA_70_15_15 @ 10% | **0** | **0.00** | none |
| OA_balanced @ 15% | 1 | 0.29 | none |

**The fourth pillar remains non-load-bearing under every candidate and weight.**
OA_70_15_15 at 10% changes *nothing at all*. This cuts both ways: merging is
low-risk, but it is also pointless — there is no benefit to buy with the added
complexity, redundancy, and size bias.

## 14. Recommended formula

**None. Do not merge.** Retain:

```
RIP = 0.58·Profit + 0.20·Safety + 0.12·Stability + 0.10·UniversalRosterAppeal
```

unchanged, and expose **Accessible Appeal** and **Elite Chase Magnetism** as
separate visible simulation-only metrics alongside it, with Universal Set
Desirability remaining the all-set score (available without simulation, with
scarcity and accessibility **never** merged into it).

**Priority follow-up:** Elite Chase Magnetism is the strongest external signal
found (top-10 ρ = 0.646, CI excluding zero, beating Roster's 0.551, distinct from
all pillars, robust to ±25% pull error). It is the best future pillar candidate —
but it correlates 0.75 with Roster, so a straight swap needs its own study, and
the right next test is the deferred **collector-preference validation** (which
would open faster: financially-matched pairwise choices), not another price
regression.

## 15. Known limitations and blocked work

1. **n = 21 sets.** Every set-level result rests on 21 points. Bootstrap CIs are
   wide (Roster's top-10 CI spans 0.098–0.823); set-level incremental models have
   negative held-out R² and cannot decide anything. Leave-one-set-out sensitivity
   shows **Black Bolt** is the most influential set for nearly every predictor —
   no single-set finding is safe.
2. **Only 2 eras** have a pull model (S&V 16 sets, Mega Evolution 5). All
   pre-Sword-and-Shield eras have none and are entirely outside this study.
3. **Modeled, not observed, pull rates**, rarity-keyed (constant within
   set×rarity). No source sample counts or confidence bounds exist to propagate,
   so only uniform scenarios were testable — relative per-rarity error is not
   estimable.
4. **Accessibility/Magnetism are exact complements at shared anchors** — an
   unavoidable structural tradeoff, not a tunable one.
5. **Spec C SEs are not cluster-robust**; prefer Spec B / the wild bootstrap.
   Two-way clustering with ~21 set clusters is asymptotically thin.
6. **Contemporaneous only.** Nothing here predicts future prices, and no such
   claim is made.
7. **Blocked:** collector-preference validation (needs a preference-elicitation
   mechanism); era-relative Treatment Prestige ontology; historical pull rates
   for older eras; per-rarity pull-rate uncertainty bounds.

## 16. Phase 9 — Treatment Prestige (kept outside Opening Appeal)

Retained outside Opening Appeal for this pass, as instructed.

| Relationship | Spearman | Flag |
|---|---|---|
| Prestige ↔ Elite Chase Magnetism | −0.266 | no |
| Prestige ↔ Accessible Appeal | −0.351 | no |
| Prestige ↔ Roster Appeal | −0.375 | no |

- **Correlation with modeled scarcity / incremental price value:** prestige
  remains a significant card-level price term after actual pull odds (+2.42,
  wild-bootstrap CI [+1.69, +3.22], 100% positive) — it is **not** redundant with
  odds.
- **Era interaction:** `era × prestige` = **−3.00**, CI [−4.90, −1.02], 0%
  positive — prestige's effect is **cancelled in Mega Evolution**.
- **Redundancy with Magnetism:** none (−0.27).

**Conclusion: keep it out.** The Mega Evolution instability is exactly the
condition the prompt named as blocking, and it is now confirmed rigorously rather
than suspected. An era-relative treatment ontology is required first.

---

## Tests and exact results

| Suite | Result |
|---|---|
| `test_opening_appeal.py` (Phase 7 archetypes + monotonicity) | **14 passed** |
| `backend/tests/unit/desirability` (full) | **128 passed, 0 failed** |
| Frontend contract + alignment suites | **196 passed, 0 failed** (unchanged) |

Phase 7 assertions all hold:

- increasing demand at fixed probability cannot lower Magnetism or Accessibility ✅
- making a desirable card easier raises Accessibility ✅
- making an elite desirable card harder raises Magnetism ✅
- an accessible secondary printing cannot erase a distinct elite chase's
  Magnetism (max, not union) ✅
- duplicate cards of one species cannot occupy multiple Magnetism slots ✅
- probabilities add within a slot; independence applies only across slots ✅
- missing pull data yields **unavailable, never zero** ✅
- no candidate Opening Appeal formula reads price (injecting price/EV/profit
  fields changes nothing) ✅
- low-roster/extreme-scarcity earns no Magnetism — scarcity alone is never
  appeal ✅
- the balanced candidate punishes lopsided sets that the additive candidates
  cannot distinguish at all ✅
