# Stage VI — Overall RIP Chase Pillar Feasibility & Integration Study

**Decision: `CHASE_PILLAR_APPROVED_WITH_REVISIONS`**

The revisions are severe. Three of the four Stage V-C survivors are rejected
outright, the multi-factor families are all rejected, and the approved weight is
half the one that looked natural. What survives is a single, narrow, well-behaved
construct — not the "Chase experience" pillar the brief anticipated.

Research only. Nothing in this stage changes production Overall RIP, Financial
RIP, Collector Appeal, weights, ranking snapshots, APIs, UI or publication state.
Production implementation requires a separate explicit instruction.

---

## 1. Phase 0 — workspace baseline

| | |
|---|---|
| Branch | `fix/public-rankings-entitlement-regression` |
| HEAD at start | `00ab4279` |
| Merge/rebase/cherry-pick in progress | none |
| Pre-existing modified | 5 scraper files (`card_helper.py`, `tcgplayer_parser.py`, `tcg_player_orchestrator.py`, 2 scraper tests) |
| Pre-existing untracked | `accept_market_explorer_three_set_swsh_ramp.py`, the two Stage V-C documents |

An isolated Stage-VI worktree was created and then removed at your instruction;
the study ran in the main tree. **A concurrent process is active in this tree**
and moved HEAD from `26ea7f1f` to `00ab4279` during Phase 0, having already
swept the Stage V-C files into `26ea7f1f` in the previous session. No Stage VI
file was lost. No commits were created by this study and no unrelated work was
reverted, stashed or deleted.

---

## 2. Phases 1–3 — pillar authority, read from code

Audited from the source constants, not from notes. Memory that said the appeal
input was CA7 is **stale**; the code says Collector Appeal V5.

| | Canonical version |
|---|---|
| Overall RIP | `overall_rip_v10_90_financial_v4_10_collector_appeal_v5` |
| Financial RIP | `financial_rip_v4_outcome_profile_p95_only_25_20_15_25_10_5` |
| Collector Appeal | `collector_appeal_v5_contextual_roster_h_only_d_baseline_up4_down2` |
| Public RIP contract | `public_rip_contract_v10` |
| Weights | Financial 0.90 / Collector 0.10 |

Financial RIP V4 components (weights unchanged from V3): true_win_frequency
0.25, typical_retention 0.20, loss_resilience 0.15, realistic_upside 0.25,
jackpot_upside 0.10, base_economic_efficiency 0.05. V4's one substantive change
is Realistic Upside becoming the P95 threshold ratio alone. Collector Appeal V5
is D (roster desirability) with an asymmetric H (desirable outcome frequency)
modifier, up4/down2; Dual-Path Depth is explicitly excluded.

### The CONTROL gate, and a real obstacle

`overall_rip_v10_score` is **NULL for all 131 rows** of the Stage V-C cohort's
run, because Collector Appeal was deferred when those rows were finalized. There
is therefore **no stored production value to agree with to a tolerance.**

Rather than reimplement the arithmetic and call the match a validation, CONTROL
is built by calling the production function `compute_overall_rip_v10` on the
production Financial RIP V4 score and the production Collector Appeal V5 score,
with inputs resolved by their **declared version strings** and refused
otherwise. Agreement is exact by construction. What this cannot prove is that
production *would have written* these numbers, and that limit is recorded on the
artifact rather than glossed over.

Two defects found and reported, not fixed (Stage VI does not edit production):

- `compute_overall_rip_v10`'s docstring says "NOT YET CANONICAL … resolves to
  V9". The constant `CANONICAL_OVERALL_RIP_VERSION` is V10. The docstring is stale.
- My Stage V-C write-up said card prices dated 2026-08-26. The artifact's actual
  basis is **2026-08-30** — card prices are 2 days *newer* than product costs,
  not older. The 2-day skew magnitude was right; the direction was wrong.

### The structural fact the whole study turns on

**Collector Appeal is set-level.** Products differ on it in 0 of 21 sets. So
*within a set, CONTROL is a strictly increasing function of Financial RIP
alone.* Chase is the only candidate that can separate two products of one set on
anything other than money.

---

## 3. Phase 4 — dataset

131 products, 21 sets, 8 families, **0 unusable rows**. Chase metrics read
verbatim from the Stage V-C artifact; Financial from the same
`calculation_run_id` Stage V-C simulated; Collector projected from set to
product exactly as production does. Dates: product cost 2026-08-28, card prices
2026-08-30, Financial `price_as_of` 2026-08-28. The Collector Appeal bundle
carries **no `asOf`**, so appeal-side date skew is unverifiable — recorded as a
limitation.

---

## 4. Phase 5 & 13 — direction, transforms, anchors

| metric | direction | transform | anchors |
|---|---|---|---|
| Chase EV Return | higher | linear | ceiling 0.35 |
| Any-Chase per product | higher | log | 0.01 → 0.50 |
| 50% Chase Spend | **lower** | inverted log | $100 → $10,000 |
| Core K | higher, **saturating** | `200K/(K+10)` | saturation 10 |

No cohort min/max anywhere — every transform is a fixed function of one
product's own numbers, so adding a product cannot rescore the others. Anchor
stress: moving anchors wider/tighter preserves rank at ρ ≥ +0.977 in every case,
so the transforms carry information about products, not about anchors.

All four Core K curvatures are monotone (ρ vs raw ≥ +0.9999), so the curvature
choice cannot reorder products on K — it only sets how much a marginal chase is
worth against the other factors. `saturating` is chosen because the brief
requires 30 chases not to be worth twice 15, and it is the only smooth transform
that never reaches 100.

---

## 5. Phases 6–10 — where the candidates actually stand

### Phase 6 overlap (Spearman)

| vs | anyChase/product | 50% spend | Core K | EV Return |
|---|---|---|---|---|
| Financial RIP V4 | +0.356 | −0.644 | +0.517 | +0.423 |
| Collector Appeal V5 | +0.125 | +0.298 | +0.313 | +0.066 |
| Overall CONTROL | +0.378 | −0.624 | +0.568 | +0.445 |
| P95 | +0.641 | +0.208 | −0.072 | −0.096 |
| P99 (jackpot) | +0.614 | +0.319 | +0.067 | +0.042 |
| FIN jackpot_upside | −0.243 | −0.293 | +0.555 | +0.596 |

No **strong** redundancy (|ρ| ≥ 0.85) anywhere. Two moderate flags, both among
the Chase candidates themselves: 50% spend ↔ EV Return −0.673 and
**Core K ↔ EV Return +0.717**.

### Phase 7 reconstruction (cvR2 is leave-one-**set**-out)

| candidate | Fin only | Coll only | Fin+Coll | all components |
|---|---|---|---|---|
| anyChase/product | 0.165 | −0.015 | **0.149** | 0.300 |
| 50% Chase Spend | 0.227 | 0.040 | 0.242 | 0.312 |
| Core K | 0.131 | −0.002 | 0.345 | 0.496 |
| Chase EV Return | 0.079 | −0.125 | 0.101 | **0.500** |

### Phase 8 partial correlation with CONTROL — the decisive phase

| candidate | raw ρ | **partial ρ** | controls |
|---|---|---|---|
| anyChase/product | +0.378 | **−0.106** | Financial, Collector, price, pack count |
| Core K | +0.515 | **+0.300** | Collector, EV Return, price |
| Chase EV Return | +0.445 | **+0.105** | EV/cost, P95, P99 |
| 50% Chase Spend | −0.624 | **−0.038** | price, per-product prob, Financial |

**Three of the four candidates collapse to zero or flip sign once their obvious
confounds are removed. Only Core K survives.**

### Phase 9 — Core K is not a Collector Appeal proxy

Max |ρ| against any Collector construct is **+0.514** (elite scarcity); against
Collector Appeal itself **+0.313**; against roster desirability **+0.263**. All
classified `distinct`. Core K differs across products in **20 of 21 sets**
(median range 3.0) while Collector Appeal differs in **none**.

Disagreements exist in both directions: *151* is CA rank 20/21 but Core-K rank
4/21; *Chaos Rising* is CA rank 2/21 but Core-K rank 13.5/21.

### Phase 10 — the pack-count confound kills accessibility

Any-Chase per product is reconstructed at **cvR2 0.726 from pack count alone**,
ρ(packs) = +0.688 Spearman / **+0.866 Pearson**. (The 0.899 for pack count plus
per-pack probability is the identity `1−(1−p)^n`, arithmetic rather than a
finding.) The three views separate correctly — ρ(packs) is +0.688 per product,
−0.142 per pack, +0.117 for dollar-normalized spend — but the per-product view
is the one that carries the tilt, and it is the one Candidate A is built on.

---

## 6. Phases 11–15 — candidate tournament

29 candidates across 9 families. `build_candidate` **refuses** the three pairs
Stage V-C falsified (Depth+Core K, BTB+EV Return, Cost Gap+50% Spend) — they are
unrepresentable, not merely discouraged.

Headline finalists (cvR2 from Financial+Collector; higher = more redundant):

| finalist | cvR2 | new info | ρ(packs) | box−pack gap | 10% variance share | ρ vs CONTROL |
|---|---|---|---|---|---|---|
| A_100 accessibility | **0.129** | 0.871 | **+0.729** | **+86.3** | 0.231 | 0.9445 |
| C_100 Core K | 0.349 | 0.651 | −0.077 | −4.8 | 0.252 | 0.9522 |
| G_50-50 K + cost | 0.388 | 0.612 | −0.115 | +3.1 | 0.223 | 0.9732 |
| H_33-33-33 three-factor | 0.389 | 0.611 | +0.236 | +32.1 | 0.205 | 0.9766 |
| I_25-25-25-25 four-factor | 0.403 | 0.597 | +0.159 | +23.5 | 0.190 | 0.9789 |

**Candidate A is the most independent candidate in the study and must still be
rejected.** Its independence is pack count. Phase 25 confirms it: it scores
loose booster packs and sleeved packs at exactly **0.0**, booster boxes at 86.3,
and its largest risers at 10% weight are three booster boxes while its largest
fallers are three loose packs. That is the booster-box bonus the brief says to
reject, and no amount of low cvR2 redeems it.

---

## 7. Phases 16–17 — disagreements and counterfactuals

Real quadrant members exist for every quadrant. Examples with Chase = Core K:

- **High Financial / low Chase** — *Shrouded Fable Pokémon Center ETB*, $167.35
  over 11 random packs (C = $15.21). Financial 34.19 (p76), Core K **0**: no card
  in Shrouded Fable is worth three of this box's packs, though 23 clear the
  Extended floor.
- **Low Financial / high Chase** — *Prismatic Evolutions Booster Pack*, Core K
  13, per-unit hit rate 1.07%. A single pack with a genuinely broad Core.

Counterfactual results, expectations stated before running:

| case | expectation | result |
|---|---|---|
| A same F+C, different any-chase probability | higher wins | PASS (+1.53) |
| B same F+C, different Core K | broader wins | PASS (+2.22) |
| C same F+C, different 50% spend | cheaper wins | PASS (+1.96) |
| D same F+C, different EV Return | **no change** | PASS (0.0000) |
| **G 1-pack vs 36-pack, identical per-pack economics** | must not reward size | **A_100 gap +82.28 (FAIL)**, C_100 **0.00**, G_50-50 **0.00**, H +27.43 |
| H hero-only vs broad Core, matched Financial | breadth wins | C_100 +81.82, G +40.91, H +27.27, **A_100 0.00** |

Case G is the cleanest single result in the study: at identical cost per pack
and identical per-pack hit rate, Candidate A scores the 36-pack box 82 points
above the single pack. Core K scores them **identically**, which is correct.

---

## 8. Phases 18–22 — integration, donors, leverage, double counting

**Donor feasibility.** Collector holds only 0.10, so a 15% or 20% Chase pillar
**cannot be funded from Collector at all**. That is structural, not a preference.

**Phase 21 is the most serious problem in the study.** Every candidate's
normalized spread is far wider than Financial RIP's, so nominal weight badly
understates real leverage:

| finalist | nominal 10% → actual variance share |
|---|---|
| A_100 | 0.231 (**2.3×**) |
| C_100 | 0.252 (**2.5×**) |
| G_50-50 | 0.223 (2.2×) |
| H_33-33-33 | 0.205 (2.0×) |
| I_25-25-25-25 | 0.190 (1.9×) |

A "10% Chase pillar" would in fact be a quarter of the score's variance, and
Financial's share would fall from ~1.00 to 0.738. This is precisely the trap the
brief named, and it forces a revision to how the weight is set.

**Phase 22 double counting.** The most valuable Core card in the cohort
(*Prismatic Evolutions Pokémon Center ETB*, P99 $1,609.30 against a $439.46 cost)
is already paid in Financial EV, in P95 via realistic_upside, and in P99 via
jackpot_upside. Correlations with those quantities:

| finalist | P99 | P95 | jackpot_upside | realistic_upside | EV/cost |
|---|---|---|---|---|---|
| A_100 | +0.646 | +0.684 | −0.298 | +0.070 | +0.320 |
| C_100 | **+0.069** | **−0.069** | +0.554 | +0.480 | +0.524 |
| I_25-25-25-25 | +0.169 | +0.125 | +0.356 | +0.501 | +0.607 |

Core K is nearly orthogonal to the two tail quantities that price the chase card
itself, because it pays a card's **existence** once and saturates. Candidates
containing Chase EV Return pay that card a third time.

---

## 9. Phases 23–24 — stability

**Price shocks** (21/21 sets, one simulation per set shared across all
scenarios, so a difference is the shock and nothing else). Core K membership
changes for 15 of 131 products at ±2% and 87–95 at ±20%.

| shock | C_100 chase ρ | mean \|Δ\| | Overall ρ |
|---|---|---|---|
| card ±2% | 0.995 / 0.995 | 0.72 / 0.78 | 0.999 |
| card ±5% | 0.992 / 0.987 | 1.29 / 2.16 | 0.999 |
| card ±10% | 0.973 / 0.970 | 3.35 / 4.59 | 0.998 |
| card ±20% | 0.944 / 0.919 | 6.14 / 10.08 | 0.996 / 0.991 |
| product ±20% | 0.941 / 0.924 | 8.38 / 7.27 | 0.992 / 0.994 |

Degradation is smooth and symmetric. Overall-score rank correlation never falls
below **0.991** even at ±20%, because Chase carries only a tenth of the weight.

**Short-window temporal stability within the available recent regime** — 13
days, 9 dates, one market regime, card prices frozen. Baseline 2026-08-28:

| date | n | chase ρ | mean \|Δ\| | Overall ρ | Core K changed |
|---|---|---|---|---|---|
| 2026-08-17 | 130 | 0.9961 | 0.57 | 0.9997 | 13 |
| 2026-08-22 | 131 | 0.9968 | 0.44 | 0.9997 | 11 |
| 2026-08-25 | 131 | 0.9978 | 0.22 | 0.9998 | 7 |
| 2026-08-27 | 131 | 0.9992 | 0.13 | 0.9999 | 3 |

This is **short-window recent-regime evidence only**. It is not long-term and
not multi-regime, and must never be cited as either.

---

## 10. Phases 25–27 — fairness, complexity, interpretability

**Family fairness** (medians across all 8 families):

| finalist | ρ(packs) | booster box − loose pack | verdict |
|---|---|---|---|
| A_100 | +0.729 | **+86.3** | REJECT — a booster-box bonus |
| C_100 | **−0.077** | **−4.8** | format-neutral |
| G_50-50 | −0.115 | +3.1 | format-neutral |
| H_33-33-33 | +0.236 | +32.1 | inherits a third of the tilt |
| I_25-25-25-25 | +0.159 | +23.5 | inherits a quarter of the tilt |

**Complexity penalty** — adding factors *reduces* independent information:

| architecture | vars | ρ vs CONTROL | median move | new info (1 − cvR2) |
|---|---|---|---|---|
| CONTROL | 0 | 1.0000 | 0.0 | — |
| + Core K | 1 | 0.9522 | 6.0 | **0.651** |
| + accessibility | 1 | 0.9445 | 8.0 | 0.871 (but rejected on fairness) |
| + 2 factors | 2 | 0.9732 | 5.0 | 0.612 |
| + 3 factors | 3 | 0.9766 | 4.0 | 0.611 |
| + 4 factors | 4 | 0.9789 | 4.0 | 0.597 |

Every multi-factor family buys fewer independent bits than the single-factor
one, and moves the ranking less. There is no case for a two-, three- or
four-factor Chase pillar.

**Interpretability.** Core K reads as *"how many economically meaningful chases
does this product actually have, priced at its own cost?"* — and the observed
movers match that sentence exactly. Candidate A reads as *"this box is bigger"*.
Candidate I contains *"another representation of card value"*, the stated reject.

---

## 11. Final decision

### `CHASE_PILLAR_APPROVED_WITH_REVISIONS`

**Approved public definition.** The count of distinct card printings in the set
whose market value is at least three times *this product's own* per-pack cost —
how many economically meaningful chases this product actually puts in front of a
buyer at the price it is sold for.

**Exact component.** `coreK` from the Stage V-C Core basket. **One factor only.**

**Transformation.** `saturating`: `score = 200·K / (K + 10)`, clamped to [0,100],
saturation constant 10, fixed anchors, no cohort normalization. K = 0 scores 0
and is a measured zero, not missing data.

**Chase internal weights.** Not applicable — single factor, weight 1.00.

**Approved Overall pillar weights.** Financial 0.85 / Collector 0.10 / **Chase
0.05**.

**Donor.** Financial. Collector cannot fund more than 0.10 in principle and
would be reduced to 0.05 by a 5% Chase pillar, which is not defensible for the
only roster signal in the model. Financial retains 0.85 and, being the
lowest-variance pillar per unit of weight, is the donor least distorted by the
transfer.

**Why 5% and not 10%.** At a nominal 10%, Core K takes **25.2%** of the
composite's variance. At 5% it takes 12.0% — still 2.4× its nominal weight, but
the absolute leverage is halved, ρ vs CONTROL is 0.985, median rank movement is
3 places and top-5 turnover is 1. **The binding revision is that the weight must
be set from measured variance share, not from the nominal number**, and
re-measured whenever the cohort or the transform changes.

**Public name: Chase Opportunity.** It names what survived — how many
economically meaningful chances the product puts in front of you, at its own
price. *Chase Quality* implies a judgement of how good the cards are; the metric
counts them. *Chase Experience* overclaims for a count. *Chase Appeal* collides
with the live `chaseAppeal` diagnostic already in the Collector Appeal payload.
*Chase RIP* implies a peer of a six-component model. *Chase Profile* is empty.

### Known limitations

1. Core K is **34.5% reconstructable** (cvR2) from the existing two pillars and
   **49.6%** from their components. This is moderate overlap, not independence.
2. Nominal weight ≠ effective weight (2.4× at 5%). Must be monitored.
3. Core K ↔ Chase EV Return ρ = +0.717 — Core K is partly a value signal.
4. Temporal evidence is 13 days, 9 dates, one regime. Not validation for promotion.
5. CONTROL could not be compared to a stored production value, because
   `overall_rip_v10_score` is NULL for the whole cohort.
6. The Collector Appeal bundle exposes no `asOf`, so appeal-side date skew is
   unverified.
7. Cohort is 21 sets / 131 products of one market state.
8. Chase's main contribution is **within-set product differentiation**, which
   exists partly because Collector Appeal is set-level. Projecting Collector
   Appeal to product level is a plausible alternative fix and was out of scope.

### Every rejected candidate, and why

| candidate | why it failed |
|---|---|
| **Any-Chase probability per product** (A) | ρ(packs) +0.729/+0.866; cvR2 0.726 from pack count alone; scores every loose and sleeved pack 0.0 and booster boxes 86.3; partial ρ with CONTROL **flips to −0.106**; counterfactual G gap **+82.28**. A booster-box bonus. |
| **50% Chase Spend** (B) | partial ρ with CONTROL +0.018 / −0.038 once price, per-product probability and Financial RIP are controlled. Adds nothing the pillars do not have. |
| **Chase EV Return** (D) | partial ρ +0.105 / −0.103 after EV/cost, P95 and P99. Pays the same expensive card a third time. Most reconstructable candidate (cvR2 0.500). |
| **E, F, G, H (multi-factor)** | all reduce new information versus C_100 (0.612/0.611 vs 0.651) while adding variables; F and H reimport the pack-count tilt. |
| **I (four-factor)** | lowest new information (0.597), contains EV Return, ρ +0.607 with EV/cost. The double-counting control failed as designed. |
| **Chase Depth** | locked out upstream (Stage V-C ρ +0.984 with Core K); unrepresentable in the module. |
| **Beat-the-Buy, Median Cost Gap** | locked out upstream (ρ +1.00 with EV Return and 50% Spend); unrepresentable in the module. |

**Do not deploy.** This is a research recommendation. The default remains the
current two-pillar Overall RIP V10 until a separate explicit instruction says
otherwise.

---

## 12. Module and artifact inventory

| Path | Classification | Role |
|---|---|---|
| `backend/research/chase_pillar_stage6/stats.py` | deliverable | grouped CV, partials, rank movement, variance decomposition |
| `backend/research/chase_pillar_stage6/transforms.py` | deliverable | directional contract, fixed anchors, anchor stress |
| `backend/research/chase_pillar_stage6/control.py` | deliverable | CONTROL via the production function; donor arithmetic |
| `backend/research/chase_pillar_stage6/candidates.py` | deliverable | candidate families, grids, Phase-12 prohibitions |
| `backend/scripts/build_chase_pillar_stage6.py` | deliverable | Phase 4 dataset build |
| `backend/scripts/build_chase_pillar_stage6_scenarios.py` | deliverable | Phase 23/24 scenario build |
| `backend/scripts/report_chase_pillar_stage6.py` | deliverable | Phases 1–29 |
| `backend/tests/unit/research/test_chase_pillar_stage6.py` | deliverable | 33 tests over the apparatus |
| `docs/research/chase_pillar_stage6_dataset.json` | generated/reproducible | 131 aligned rows |
| `docs/research/chase_pillar_stage6_scenarios.json` | generated/reproducible | 3,204 scenario observations |
| `docs/research/chase_pillar_stage6_analysis.txt` | generated/reproducible | full phase output |

`python -m pytest backend/tests/unit/research/test_chase_pillar_stage6.py` —
**33 passed**.

### Defects found and fixed during Stage VI

- The scenario builder initially pinned the card-price basis to the date stored
  in the Stage V-C artifact. The scrape had moved on, the freshness filter
  excluded the entire eligible universe, and every shock reported a Core K of 0
  and a response of exactly zero. The basis is now read off the prepared data
  each run, and an empty eligible universe raises instead of scoring silently.
- Shocked identities were rebuilt positionally against an 11-field dataclass;
  now `dataclasses.replace`.
- Phase 24 first reported "no complete scenarios" because coverage was
  intersected globally; the early temporal dates cover 7 products. Coverage is
  now intersected pairwise with the baseline and every row prints its own `n`.
- One set (`whiteFlare`) failed the first scenario build with
  `NameError: name 'APIError' is not defined` — an upstream bare `except APIError`
  with no import, in code Stage VI does not own. It did not recur on the rebuild
  (21/21 sets, 0 failures) and was **not** fixed here.
