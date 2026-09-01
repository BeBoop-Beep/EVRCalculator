# Stage V-C — Native Product-Level Chase Economics

**Verdict: `PRODUCT_LEVEL_CHASE_ECONOMICS_VALIDATED_WITH_REVISIONS`**

**Gate: `OVERALL_RIP_CHASE_PILLAR_RESEARCH_UNLOCKED`**

Research only. Nothing in this stage changes Overall RIP, Financial RIP, Collector
Appeal, production weights, ranking UI, APIs, or any published snapshot.

---

## 1. What was run

| | |
|---|---|
| Artifact | `docs/research/product_chase_stage5c.json` |
| Temporal artifact | `docs/research/product_chase_stage5c_temporal.json` |
| Full analysis output | `docs/research/product_chase_stage5c_analysis.txt` |
| Research version | `product-chase-economics-stage5c-v1` |
| Market date | 2026-08-28 (card prices 2026-08-26, skew 2 days, uniform across all 21 sets) |
| Simulation | 250,000 packs per set, one run per set, `PackDecompositionRecorder` attached |
| Cohort | 21 sets, **131 products, 0 unsupported, 0 failures** |
| Families | 8 (booster_box, enhanced_booster_box, half_booster_box, booster_bundle, elite_trainer_box, pokemon_center_elite_trainer_box, loose_booster_pack, sleeved_booster_pack) |

### Upstream contract, reproduced not re-litigated

Stage V-A and V-B were treated as a closed, **coupled** contract and re-derived
from their own inputs before any V-C work:

```
C_product = product_market_cost / random_pack_count      (V-B live authority)
CORE      : card_market_value >= 3 x C_product           (V-A)
EXTENDED  : card_market_value >= 1 x C_product           (V-A, breakeven identity)
no percentile term
```

`contract.pack_equivalent_cost` has no entry point that accepts a set-level cost,
so the specific error Stage V exists to prevent — applying 3x/1x to Stage IV's
set-wide cheapest route — is unrepresentable rather than merely discouraged.

Observed cohort spread: `C` ranges **$4.74 to $120.08**. Core K ranges 0–14
(median 4); Extended K ranges 1–77 (median 17).

### Architecture

Each set is simulated **once**. Every product of that set is scored against
those same recorded pack paths. No SKU is independently simulated. Consequently
two products of one set can differ only through `C` — their acquisition cost,
their tier membership, and their whole-product aggregation — and never through
Monte Carlo noise. That is what makes both halves of the central proof testable
simultaneously, and it is why Phase 17 case B can be stated as an exact identity
rather than a tolerance.

---

## 2. The central proof

> Products from the same set produce different Chase profiles for legitimate
> economic reasons, while economically equivalent products behave equivalently.

### Half 1 — differentiation. **HOLDS.**

- 21 / 21 sets with ≥2 products have **distinct** per-pack costs.
- 0 sets show a difference **without** a cost reason.
- Within-set `C` spread: median **×2.40**, max **×6.18** (Obsidian Flames).
- Core K range within a set reaches 4 (Scarlet & Violet Base Set).
- Phase 12 tournament: the four criteria (cheapest pack, deepest Core, best EV
  return, best per-unit probability) **disagree in 11 of 21 sets**. Products of
  one set are genuinely not interchangeable.

### Half 2 — equivalence. **Structurally established; VACUOUS on the live cohort.**

This is the honest result and it is reported as such rather than as a pass.

- **Exact equivalence: 0 pairs found.** No two same-set products share a cost per
  pack in this cohort, so exact equivalence has nothing to test empirically. The
  reporter prints `VACUOUS`, not `HOLDS`; `equivalence_classes(...)["holds"]` is
  `False` on zero pairs by construction, and a test pins that.
- **Constructed equivalence: verified.** Phase 17 `B_single_pack` vs
  `B_thirty_six_packs` — one pack at $10 and a 36-pack box at $360 — produce
  identical `C`, identical Core membership, identical per-pack economics and
  identical Chase EV Return, while differing on per-unit probability exactly as
  they must.
- **Near-equivalence (continuous form): evidence present.** 5 same-set pairs sit
  within 1% on `C`; 4 are size contrasts and **all 4 differ per unit**. Worst
  relative divergence on any cost-determined metric is **1.13%** (Beat-the-Buy,
  Chaos Rising box vs pack) against a 0.82% cost separation — i.e. the metric
  moved slightly *less* than the cost that drove it. Median divergence 0.57%.

A per-SKU re-simulation architecture would have produced non-zero divergence
here uncorrelated with cost separation. It did not.

**Central proof: HOLDS**, on the understanding that Half 2 rests on the
architecture plus constructed and near-equivalent evidence, not on exact
in-cohort pairs that do not exist.

---

## 3. Findings by phase

### Phase 13 — the cost of inheriting Stage IV's set-level basket

Set-level inheritance is **strictly and materially wrong**, and the bias is
one-directional (the cheapest route has the lowest `C` in the set by
construction, so inheritance can only over-issue).

| | mean | median | P90 worst | worst | over-issued |
|---|---|---|---|---|---|
| Core K error | **−6.27** | −5.0 | −14.0 | −17 | 125 / 131 |
| Extended K error | **−6.65** | −4.0 | −18.0 | −43 | 98 / 131 |

Worst-hit families are exactly the ones with the highest `C`: Pokémon Center ETB
(−8.44 mean), ETB (−7.65). Booster boxes suffer least (−3.79) because they *are*
usually the cheapest route. Inheritance therefore does not merely add noise; it
systematically flatters the formats that are worst value per pack.

### Phase 14 — product-family fairness

| metric | ρ(pack count) | ρ(product cost) |
|---|---|---|
| per-product hit rate | **+0.677** | +0.502 |
| per-pack hit rate | −0.126 | −0.330 |
| 50% spend, pack-granular | **+0.100** | +0.396 |
| 50% spend, whole unit | +0.146 | +0.442 |
| Core K | −0.087 | −0.247 |
| Chase Depth | −0.036 | −0.156 |
| Chase EV Return | −0.128 | −0.233 |

Per-unit probability is strongly pack-count-driven **by construction and
correctly so** — a 36-pack box really does hit more often than a pack. The test
that matters is that dollar-normalised accessibility is *not*: ρ falls from
+0.677 to +0.100. The three accessibility views are correctly separated, and
collapsing them would rebuild the pack-count artifact.

### Phase 15 — price shocks (closed form)

Mean Core Jaccard against the unshocked basket:

| shock | card + | card − | product + | product − |
|---|---|---|---|---|
| 2% | 0.983 | 0.980 | 0.980 | 0.983 |
| 5% | 0.965 | 0.943 | 0.946 | 0.959 |
| 10% | 0.915 | 0.886 | 0.894 | 0.900 |
| 20% | 0.833 | 0.770 | 0.800 | 0.800 |

Thin-basket flips (products with ≤2 Core members changing count) are **0 at ±2%**
and rise to 6–10 of 131 at ±20%. Degradation is smooth and symmetric between the
card and product sides, as the algebra requires (a +x% card shock is exactly a
threshold divided by 1+x). Stability is good at realistic daily movement and
merely acceptable at ±20%.

### Phase 16 — temporal validation

**The brief's "~62-day recent regime" does not exist for product costs.** The
real history in `simulation_sealed_product_results` is **13 days, 9 observed
dates** (2026-08-15 → 2026-08-28). This is reported as found rather than
inherited as a nominal window.

Card prices are deliberately **frozen** at the build basis so that any churn is
attributable to `product_market_cost` movement and nothing else; card-price
movement is covered instead, and more widely, by the Phase-15 shock grid.

| date | n | mean Core Jaccard | min | mean ΔK | flips | rank ρ |
|---|---|---|---|---|---|---|
| 2026-08-15 | 7 | 0.976 | 0.833 | +0.14 | 0 | +1.000 |
| 2026-08-17 | 130 | 0.986 | 0.750 | −0.05 | 0 | +0.997 |
| 2026-08-22 | 131 | 0.989 | 0.750 | −0.01 | 0 | +0.998 |
| 2026-08-25 | 131 | 0.994 | 0.833 | +0.02 | 0 | +0.999 |
| 2026-08-27 | 131 | 0.997 | 0.833 | +0.01 | 0 | +0.999 |
| 2026-08-28 | 131 | 1.000 | 1.000 | +0.00 | 0 | — (baseline) |

- **0 Core-existence flips across the entire window.** No product gained or lost
  a Core basket outright.
- Core count moved at all for **18 / 131** products.
- Pack-equivalent cost CV: median 0.0081, P90 0.0207, max 0.0782.
- Cross-product rank stability never falls below **ρ = +0.995**.

**This is single-regime evidence over a fortnight.** It is not evidence across a
release, a reprint, a restock or a crash, and it is not multi-regime validation.

### Phase 17 — synthetic and pathological cases: **10 / 10 pass**

| case | C | Core K | Ext K | what it proves |
|---|---|---|---|---|
| A_same_packs_cheap / A_same_packs_dear | 4.00 / 10.00 | 5 / 4 | 6 / 5 | same packs, different price ⇒ strictly narrower Core for the dearer SKU |
| B_single_pack / B_thirty_six_packs | 10.00 / 10.00 | 4 / 4 | 5 / 5 | same cost per pack, 1 vs 36 packs ⇒ **identical** per-pack economics |
| C_expensive_large | 40.00 | 2 | 3 | expensive large product: size buys no basket |
| D_cheap_small | 2.00 | 6 | 7 | cheap small product: smallness is not punished; strictly contains C's Core |
| E_exactly_on_the_floor | 20.00 | 1 | 2 | the 3× floor is inclusive at exactly the threshold |
| F_hero_only_core | 10.00 | 1 | 1 | a one-member Core is a valid verdict |
| G_no_core | 100.00 | 0 | 0 | no-Core is a measured zero, never missing data |
| H_guaranteed_promo | 10.00 | 4 | 5 | denominator is random packs (11), not pack_count (12) |

The catalogue is data-driven and its ability to *fail* is itself under test: a
deliberately-wrong expectation is asserted to be reported as FAIL, and the promo
leak is asserted to widen the Core on a price vector carrying a card in the
$27.50–$30.00 gap.

### Phase 18 — redundancy (n = 131, tie-aware Spearman)

|  | Core K | Depth | p/pack | p/product | spend50 | EV Ret | EV Share | BTB | Gap |
|---|---|---|---|---|---|---|---|---|---|
| **Core K** | +1.00 | **+0.98** | +0.70 | +0.41 | −0.60 | +0.72 | +0.59 | +0.71 | −0.63 |
| **Chase Depth** | **+0.98** | +1.00 | +0.61 | +0.29 | −0.59 | +0.65 | +0.53 | +0.65 | −0.61 |
| **Any-chase / pack** | +0.70 | +0.61 | +1.00 | +0.46 | **−0.91** | +0.70 | +0.47 | +0.69 | **−0.91** |
| **Any-chase / product** | +0.41 | +0.29 | +0.46 | +1.00 | −0.27 | +0.23 | +0.21 | +0.22 | −0.27 |
| **50% Chase Spend** | −0.60 | −0.59 | −0.91 | −0.27 | +1.00 | −0.67 | −0.34 | −0.67 | **+1.00** |
| **Chase EV Return** | +0.72 | +0.65 | +0.70 | +0.23 | −0.67 | +1.00 | +0.86 | **+1.00** | −0.71 |
| **Chase EV Share** | +0.59 | +0.53 | +0.47 | +0.21 | −0.34 | +0.86 | +1.00 | +0.86 | −0.39 |
| **Beat-the-Buy** | +0.71 | +0.65 | +0.69 | +0.22 | −0.67 | **+1.00** | +0.86 | +1.00 | −0.71 |
| **median Cost Gap** | −0.63 | −0.61 | −0.91 | −0.27 | **+1.00** | −0.71 | −0.39 | −0.71 | +1.00 |

Three exact or near-exact collinearities, all of which force revisions:

1. **Beat-the-Buy ≡ Chase EV Return** (ρ = +1.00). At product level BTB is a
   monotone restatement of EV Return, not an independent view.
2. **median Cost Gap ≡ 50% Chase Spend** (ρ = +1.00), both ≈ −0.91 against
   per-pack hit rate. The pack-granular gap and the 50% spend horizon are one
   axis expressed twice.
3. **Chase Depth ≈ Core K** (ρ = +0.98). See Phase 19.

Only **Any-chase per product** is genuinely orthogonal to the value cluster
(ρ ≤ +0.46 with everything), because it is the one metric carrying pack count.

> **Defect found and fixed during this stage.** The Phase-18 matrix previously
> printed `-` for the entire Cost Gap row: the reporter read `median` from
> `chase_cost_gap`, which emits `medianGap`. Cost Gap was silently absent from
> every redundancy result until now, and its ρ = +1.00 with 50% Chase Spend was
> therefore never visible. The reporter's local Spearman also used competition
> ranks, which inflate agreement between the heavily-tied vectors this stage
> produces; it now delegates to the tie-aware implementation in `validation.py`.

### Phase 19 — product-level Chase Depth, retested

The Financial RIP study found Depth statistically promising and rejected it
**solely** because product-level delivery did not exist. Delivery now exists, so
the question was reopened rather than inherited.

- n = 122 (9 products have no Core and therefore no Depth); min 1.00, median
  2.98, max 8.09.
- Within-set Depth spread: median 1.55, max 5.21 (Temporal Forces). Depth is
  **constant across products in only 3 of 21 sets** — so it does differentiate.
- But **ρ(Depth, Core K) = +0.984**.

**Depth is genuine but not independent.** It differentiates products for the
right reason (a dearer SKU has a shallower, more top-heavy Core), yet at product
level it is very nearly a smooth restatement of the literal Core count. The
earlier rejection is *not* overturned by delivery alone.

### Phase 20 — coverage

- 21 sets, **131 / 131 products scored, 0 unsupported**, 0 failures.
- All 8 product families represented. No exclusion reason was triggered:
  `no_product_market_cost`, `no_random_pack_count`, `unverified_composition` and
  `not_pack_independent` each fired 0 times.
- Card-price vs product-cost skew is a uniform 2 days on every set.
- **9 products legitimately have no Core** (5 Pokémon Center ETB, 3 ETB, 1
  bundle), e.g. the 151 Pokémon Center ETB at `C` = $120.08 — no card in 151 is
  worth three of its packs. All 9 still carry a non-empty Extended basket
  (1–23 members) and are reported as measured zeroes with full statistics, never
  as missing data.

---

## 4. Answers to the critical validation questions

1. **Does product-native cost materially alter Chase Tier membership?**
   **Yes, decisively.** Mean Core K error from inheritance is −6.27 with a worst
   case of −17, in the same direction for 125 of 131 products, and concentrated
   on the highest-`C` families.

2. **Do same-set products genuinely receive different Chase profiles?**
   **Yes.** All 21 multi-product sets have distinct `C` (median spread ×2.40,
   max ×6.18), and the four tournament criteria disagree in 11 of them.

3. **Does common-set-path evaluation work without inheriting set constants?**
   **Yes.** One decomposition per set, no set-level cost is reachable from any
   scoring path, and the only per-set constant carried (`setCheapestRoute`)
   exists purely as the Phase-13 comparison baseline and is never a product
   attribute.

4. **Are product-unit and dollar-normalised accessibility correctly separated?**
   **Yes.** Three views are kept distinct. ρ(pack count) is +0.677 for per-unit
   probability and +0.100 for dollar-normalised 50% spend. Whole-product spend is
   asserted never cheaper than pack-granular spend.

5. **Are no-Core products handled as valid economic outcomes?**
   **Yes.** 9 real cases plus pathological case G; reported as measured zeroes
   with `empty: true` and `supported: true`, distinct from the four exclusion
   reasons (none of which fired).

6. **Is product-level Chase Depth meaningful?**
   **Meaningful but not independent.** It varies within 18 of 21 sets, but
   ρ = +0.984 with Core K. Not admitted as a distinct metric.

7. **Is product-level Chase EV Return valid?**
   **Yes.** It reconciles exactly between its two formulations
   (`ev_pack·n / cost` ≡ `ev_pack / C`), is near-neutral to pack count
   (ρ = −0.128), and is the strongest non-degenerate value metric available.

8. **Does BTB remain primarily explanatory?**
   **Yes, and more strongly than before.** ρ(BTB, Chase EV Return) = **+1.00**
   at product level. It is retained for explanation and formally barred from any
   composite.

9. **Are results acceptably stable within the limited historical regime?**
   **Yes, within a fortnight of one regime.** 0 Core-existence flips, mean
   Jaccard ≥ 0.976 on every date, rank stability ρ ≥ +0.995. This is *not*
   multi-regime evidence and must not be cited as such.

10. **Is coverage broad enough to support the future pillar tournament?**
    **Yes.** 131/131 products, 8 families, 21 sets, zero exclusions, uniform
    2-day price skew.

---

## 5. Revisions required (why not a clean `VALIDATED`)

| # | Revision |
|---|---|
| R1 | **Chase Depth is not admitted** as an independent product-level metric. ρ = +0.984 with Core K. Delivery existing does not overturn the earlier rejection; retain Depth as a descriptive companion only. |
| R2 | **Beat-the-Buy is formally explanatory-only** and barred from any composite. ρ = +1.00 with Chase EV Return over all 131 products. |
| R3 | **Median Cost Gap is not admitted** as a distinct metric. ρ = +1.00 with 50% Chase Spend. Publish one of the two, not both, as an axis. |
| R4 | **The temporal claim is downgraded** to a 13-day, 9-date, single-regime, product-cost-only stability check. The "~62-day regime" assumed by the brief does not exist in `simulation_sealed_product_results`. |
| R5 | **Equivalence is structural, not empirical-exact.** Zero exact same-`C` pairs exist in the cohort; the claim rests on the shared-path architecture, Phase-17 case B, and a 1% near-equivalence band (max divergence 1.13%). Any future restatement must not upgrade this to "observed". |
| R6 | **Product aggregation remains model-consistent IID, never validated IID.** `1 − (1 − p)^n` is the production model's own `pack_independence_assumption` restated at product scale, with no non-IID simulation anywhere to check it against. `aggregate_to_product` refuses rather than forces when a product's contract does not assert independence. |

---

## 6. Gate decision

**`OVERALL_RIP_CHASE_PILLAR_RESEARCH_UNLOCKED`**

Grounds:

- Native product-level delivery exists, is complete (131/131, 0 exclusions) and
  spans all 8 families and 21 sets.
- The set-inheritance shortcut is quantified and refuted, so the pillar cannot
  be built on Stage IV baskets by accident.
- The central proof holds, with its weaker half stated honestly.
- A **non-redundant** metric family survives the redundancy purge and is
  sufficient for a pillar tournament: **Chase EV Return** (value),
  **Any-chase per product** (the one pack-count-carrying, orthogonal axis,
  ρ ≤ +0.46 with everything else), **50% Chase Spend** (dollar-normalised
  accessibility), and **Core K** (structure). Depth, BTB and Cost Gap are
  companions, not candidates.
- The pathological catalogue passes 10/10 including every case the brief named,
  and the apparatus is proven able to report failure.

Conditions carried into the pillar work — these unlock *research*, not
production:

1. No production weight, snapshot, endpoint or UI may consume Stage V-C output
   until the pillar tournament itself concludes.
2. The pillar tournament must not treat Depth, BTB or median Cost Gap as
   independent inputs (R1–R3).
3. Temporal robustness must be re-run once a genuinely multi-regime product-cost
   history exists. Thirteen days is enough to unlock research and nowhere near
   enough to promote a pillar.
4. Any published aggregation figure must carry the model-consistent-IID wording.

---

## 7. Module and test inventory

| Path | Role |
|---|---|
| `backend/research/product_chase_economics/contract.py` | the coupled 3×/1× tier contract; no set-level entry point |
| `backend/research/product_chase_economics/metrics.py` | product aggregation, three accessibility views, whole-product gap/BTB, product Chase EV |
| `backend/research/product_chase_economics/runner.py` | one decomposition per set, many products scored against it |
| `backend/research/product_chase_economics/validation.py` | **new** — Phase 16 temporal replay, Phase 17 catalogue, differentiation/equivalence/near-equivalence |
| `backend/scripts/build_product_chase_stage5c.py` | main build (250k packs/set) |
| `backend/scripts/build_product_chase_stage5c_temporal.py` | **new** — dated product costs for Phase 16 |
| `backend/scripts/report_product_chase_stage5c.py` | Phases 12–20 plus the central proof |
| `backend/tests/unit/research/test_product_chase_economics.py` | 27 tests — contract, aggregation, pack-count invariance, EV, whole-product journey |
| `backend/tests/unit/research/test_product_chase_economics_validation.py` | **new** — 24 tests over the falsification apparatus itself |

`python -m pytest backend/tests/unit/research/test_product_chase_economics.py backend/tests/unit/research/test_product_chase_economics_validation.py` — **51 passed**.
