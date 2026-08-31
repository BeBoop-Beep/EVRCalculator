# Product-Level Chase Economics — Stage V-A: Canonical Economic Floor

**Decision: `ECONOMIC_CHASE_FLOORS_VALIDATED_WITH_REVISIONS`**

> The revision is not a tweak to Stage IV's numbers. Stage IV's tentative 5×C Core
> was validated against the **cheapest** pack route in each set. Applied to the
> actual products people buy, that floor empties the Core tier on 9 of 131
> products and reduces it to a single card on 35 of 131. The floor that survives
> contact with product-native cost is **3×C Core / 1×C Extended**, and the
> percentile is dropped entirely rather than retained as a guardrail.

| | |
|---|---|
| Branch | `fix/public-rankings-entitlement-regression` |
| HEAD at start | `2aa117d` |
| Market date | 2026-08-28 |
| Observation window | 2026-06-28 → 2026-08-28 (**the full extent of NM price history**) |
| Cohort | 21 sets, 131 usable product routes |
| Temporal resolution | **daily**, median 60 dates/set (Stage IV: 8 weekly) |
| Artifact | `docs/research/product_chase_stage5a.json` |
| Production impact | **None.** No Financial RIP, Overall RIP, Collector Appeal, weight, ranking, API, snapshot, schema or UI changed. |

```
python -m backend.scripts.build_product_chase_stage5a
```

---

## Phase 0 — Baseline

Branch confirmed `fix/public-rankings-entitlement-regression`, HEAD `2aa117d`, no
merge/rebase/cherry-pick in progress, nothing staged.

Three files were **already modified before this study began** and were not touched:
`backend/db/services/market_explorer_query_planner.py`,
`backend/scripts/benchmark_market_explorer_query_planner.py`,
`backend/tests/unit/db/services/test_market_explorer_query_planner.py`. They belong to
unrelated Market Explorer work and are classified PRE-EXISTING throughout.

No external commits landed during the session.

---

## Phase 1 — Stage-IV reproduction

Candidate floors were re-derived from `docs/research/set_chase_tiers_stage4.json` and
independently recomputed from live NM prices against the Stage-IV cost basis. The
reproduction is exact: for Ascended Heroes the recomputed Core K is 30 / 26 / 22 / 14 / 9
at 1× / 2× / 3× / 5× / 10×C, matching Stage IV's published `selectedK` at every floor.

**The percentile is confirmed inert.** Across all 21 sets the percentile cap binds in
**0/21** at every floor once the 20% cap is used, and at 5×C the selected K is identical
(14 for Ascended Heroes) under the top-5%, 7.5%, 10%, 15% and 20% caps. Only the 2.5% cap
ever binds. Stage IV's own language — "the floor carries the rule and the percentile is a
guardrail" — is confirmed, and this study goes one step further: since the cap never binds
at any defensible width, it is removed rather than retained.

Set-level Core K by floor (Stage-IV cheapest-route cost basis):

| floor | median K | min | max | K≤1 | K=0 |
|---|---:|---:|---:|---:|---:|
| 1×C | 24.0 | 9 | 76 | 0 | 0 |
| 2×C | 12.0 | 3 | 28 | 0 | 0 |
| 3×C | 10.0 | 2 | 22 | 0 | 0 |
| 5×C | 5.0 | 1 | 14 | **2** | 0 |
| 10×C | 2.0 | 0 | 10 | **8** | **2** |

---

## Phase 2 — Expanded temporal validation

Stage IV sampled weekly over a 91-day lookback and obtained 8 usable dates. That lookback
was longer than the data: `card_variant_price_observations` **begins 2026-06-28**. The
window cannot be extended backwards, and none was fabricated.

What could be improved is density. This study samples **daily** and obtains a median of
**60 dates per set** — roughly 7× Stage IV's resolution over the same real history.

Two methodology corrections:

* **Balanced panel.** Only variants observed on *every* retained date are scored. Stage IV
  retained any date holding 50% of the widest coverage, which allows a card that is merely
  unobserved on a date to read as a card that left the tier. Median panel: 352 variants.
* **Stricter date filter** (90% of widest coverage, vs Stage IV's 50%).

Pack cost is held at its market-date value across the series. Sealed price history is a
Stage V-B question, and varying it here would smuggle an unvalidated cost basis into a
floor decision.

| pair | core J mean | core J **min** | endpoint J | K min | K med | empty-core sets | singleton-core sets |
|---|---:|---:|---:|---:|---:|---:|---:|
| 2×/1× | 0.9885 | 0.7500 | 0.8754 | 3 | 12.0 | 0 | 0 |
| 3×/1× | 0.9891 | 0.6667 | 0.8698 | 2 | 9.0 | 0 | 0 |
| 5×/2× | 0.9913 | 0.5000 | 0.8524 | 1 | 6.0 | 0 | **2** |
| 10×/3× | 0.9946 | **0.0000** | 0.9058 | **0** | 2.0 | **2** | **8** |

**The mean Jaccard column is a trap and is reported only to disarm it.** 10×/3× has the
*best* mean stability (0.9946) and is simultaneously the worst rule in the study: its Core
is so small that it is stable by being nearly empty, and its worst case is a complete
tier turnover (Jaccard 0.000, Scarlet & Violet 151, K oscillating 0↔1). Selecting on mean
stability would have chosen the falsified rule. Worst-case behaviour is the discriminating
statistic.

Legitimate movement vs threshold noise: `coreExits` averages 3.5 cards per set over 60 days
at 3×/1×, against a median Core of 9 — turnover concentrated in a small number of genuinely
moving cards rather than broad oscillation. Endpoint Jaccard (~0.87) being well below
consecutive Jaccard (~0.99) is the signature of *directional drift*, not churn: the tier
walks somewhere over two months rather than vibrating in place.

---

## Phase 3 — Boundary sensitivity

Mean number of panel cards sitting within a band of the Core threshold, per set-date:

| pair | ±2% | ±5% | ±10% | ±20% |
|---|---:|---:|---:|---:|
| 2×/1× | 0.51 | 1.27 | 2.59 | 5.48 |
| 3×/1× | 0.45 | 1.09 | 2.02 | 4.25 |
| 5×/2× | 0.34 | 0.92 | 1.72 | 3.07 |
| 10×/3× | 0.05 | 0.10 | 0.27 | 0.85 |

Absolute occupancy falls with the floor, but so does tier size, and the meaningful quantity
is occupancy *relative* to K. At 3×C, ~1.09 cards sit within ±5% of a median-9 Core (12%);
at 5×C, ~0.92 sit within ±5% of a median-6 Core (15%); at 10×C, 0.10 against a median-2
Core (5%, but on a tier that is frequently empty). No candidate places a large share of the
universe perpetually at the cutoff. This phase does not discriminate strongly and is not
the basis of the decision.

---

## Phase 4 — Structural tests

Spearman correlation of Core K against set characteristics:

| floor | ρ(K, pack cost) | ρ(K, eligible printings) |
|---|---:|---:|
| 2×C | +0.204 | **+0.530** |
| 3×C | **+0.081** | +0.394 |
| 5×C | −0.209 | +0.088 |
| 10×C | −0.058 | −0.066 |

Two findings:

1. **No floor mechanically punishes expensive-pack sets.** ρ(K, pack cost) is near zero at
   3×C. Scarlet & Violet 151 (K=6 at 3×C on a $29.81 pack) is a genuine economic outlier —
   its cards are cheap *relative to its pack* — not a threshold artifact.
2. **Low floors partly measure set size.** At 2×C, ρ(K, eligible) = +0.530: a bigger set
   gets a bigger Core largely for being bigger. This is a real argument against 2×C as a
   *Core* rule, which should be a quality bar rather than a size proxy. It weakens by 3×C
   (+0.394) and vanishes by 5×C (+0.088).

Archetype spot checks (Core K at 2×/3×/5×/10×C): hero-chase 151 → 11/6/1/1; deep Ascended
Heroes → 26/22/14/9; cheap-pack Perfect Order → 10/8/7/5; god-pack Prismatic Evolutions →
27/18/13/10. Every floor separates hero from deep sets in the right direction.

---

## Phase 5 — Economic interpretability, and the decisive test

Each floor states one sentence:

| floor | reading |
|---|---|
| 1×C | "worth at least what a pack costs" — the **breakeven** card: pulling it pays for the pack |
| 2×C | "worth two packs" — a good hit, but not a headline |
| 3×C | "worth three packs" — pulling it pays for the pack **and** a meaningful part of the session |
| 5×C | "worth five packs" |
| 10×C | "worth ten packs" |

1×C is the most defensible Extended boundary in the study because it is not a tuned
constant at all: it is the point where a card repays its own pack. That is an economic
identity, not a choice.

**The decisive test — floor survival under product-native cost.** Stage IV's floors were
calibrated against the *cheapest* route in each set. Stage V must apply them to individual
products, whose pack-equivalent cost differs from the cheapest route by a median of 1.36×
and a maximum of **6.18×** within a single set. Recomputing every floor against each of the
131 usable product routes at its own cost:

| floor | K=0 | K≤1 | K≤2 | median K |
|---|---:|---:|---:|---:|
| 1×C | 0/131 | 1/131 | 2/131 | 17.0 |
| 1.5×C | 0/131 | 3/131 | 4/131 | 12.0 |
| 2×C | 1/131 | 4/131 | 11/131 | 10.0 |
| **3×C** | **3/131** | 9/131 | 21/131 | **7.0** |
| 5×C | **9/131** | **35/131** | 50/131 | 4.0 |
| 10×C | **40/131** | 66/131 | 91/131 | 1.0 |

**Stage IV's tentative 5×C does not survive.** It empties the Core on 9 products and
reduces it to one card on 35 of 131 — over a quarter of the catalogue reduced to a
single-card "chase profile", which is the configuration Stage IV itself flagged as least
temporally stable. The failures are concentrated in exactly the families Stage V exists to
serve: 5/25 Pokémon Center ETBs, 3/26 ETBs, 1/22 booster bundles.

An important interpretive distinction: **an empty Core means different things at set and
product level.** At set level it is a definitional failure — the metric cannot be computed
for that set. At product level it is a legitimate verdict: "no card in this set is worth
three packs *of this product*" is a true and useful statement about an Obsidian Flames PC
ETB at $62.79/pack. The 3/131 empty Cores at 3×C are all of this second kind, and are
retained rather than patched.

---

## Phase 6 — Decision

### `ECONOMIC_CHASE_FLOORS_VALIDATED_WITH_REVISIONS`

**Core multiple: 3×C.** The only floor that is simultaneously a genuine quality bar
(ρ with set size +0.394, falling), non-degenerate at set level (K min 2, no empty or
singleton Core in 21 sets over 60 daily dates), and non-degenerate at product level
(3/131 empty, all economically legitimate). 5×C is rejected on product survival; 10×C is
rejected outright; 2×C is rejected as a Core because it substantially measures set size.

**Extended multiple: 1×C.** The breakeven identity, not a tuned constant. 0/131 empty,
1/131 singleton, median K 17.

**Percentile guardrail: not necessary, and removed.** It binds in 0/21 sets at every
defensible width. Stage IV kept it to make the rule "fail safe rather than large"; the
daily evidence shows nothing to fail safe against, and retaining an inert term invites the
rule to be described by a mechanism that does not operate.

**Temporal stability:** consecutive core Jaccard 0.9891 mean / 0.6667 worst-case over a
median 60 daily dates; ~3.5 core exits per set per 60 days against a median Core of 9;
no empty or singleton Core in any set on any date.

**Boundary sensitivity:** 0.45 / 1.09 / 2.02 / 4.25 cards within ±2 / 5 / 10 / 20% of the
Core threshold per set-date.

### Major limitations

1. **The window is 62 days and one market regime.** Price history begins 2026-06-28.
   Phase 2's request for spike, decline and stable regimes cannot be honoured — there is
   only one regime in the data. The floor is validated as *stable*, not as *stable across
   regimes*, and that claim should not be upgraded without more history.
2. **Pack cost is held constant through the temporal series.** Sealed price history was not
   used, so the temporal result measures card-price movement only. A floor is a ratio, and
   the denominator's own volatility is untested until V-B.
3. **V-A and V-B are not cleanly separable.** This is the study's most consequential
   methodological finding. The gate structure assumes the floor can be settled before the
   cost basis, but the floor's survival *depends* on which cost basis is used — 5×C passes
   at set level on cheapest-route cost and fails at product level on product-native cost.
   The 3×C/1×C recommendation is therefore issued **conditionally**: it is validated
   against both cost bases tested here, and V-B must re-check it against any cost authority
   it selects that is not one of them (notably MSRP/reference retail, still untested).
4. **Chase EV, BTB and accessibility were not recomputed per date.** Membership stability
   only. Those require a pass over pack draws per membership set and belong to V-C.

### Bonus finding — the proof V-C is required

Within-set Core K spread at 3×C, product-native cost:

| set | spread | lowest | highest |
|---|---:|---|---|
| Paradox Rift | 16 | K=1, PC ETB @ $19.69/pack | K=17, Booster Box @ $7.56/pack |
| Temporal Forces | 13 | K=5, PC ETB @ $17.76/pack | K=18, Booster Box @ $8.64/pack |
| Ascended Heroes | 12 | K=10, PC ETB @ $37.77/pack | K=22, Booster Pack @ $13.79/pack |
| Paldea Evolved | 9 | K=1, PC ETB @ $54.67/pack | K=10, Sleeved Booster @ $16.75/pack |

Set-level inheritance would have assigned Paradox Rift's booster-box profile (K=17) to its
Pokémon Center ETB, whose true Core at its own cost is **one card**. This quantifies why
`PRODUCT_LEVEL_CHASE_ECONOMICS_REQUIRED_BEFORE_ANY_RECONSIDERATION` was correct.

---

## Gate status

Stage V-A has a research decision, so **Stage V-B may begin**. Its first obligation is
inherited from limitation 3: whichever cost authority V-B selects, the 3×C/1×C floor must
be re-validated against it before Stage V-C computes anything.

**Nothing was deployed.** No production version, weight, transform, snapshot, ranking, RPC,
API contract or UI was modified.
