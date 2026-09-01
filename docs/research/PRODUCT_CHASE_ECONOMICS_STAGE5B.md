# Product-Level Chase Economics — Stage V-B: Cost Basis Contract

**Decision: `PRODUCT_CHASE_COST_BASIS_VALIDATED_WITH_REVISIONS`**

> The headline result is that there was never a cost *conflict* to resolve. Financial
> RIP and Stage-IV Chase Economics do not disagree about what a product costs — they
> divide by different things because they answer different questions. Financial RIP
> divides by the exact product's own market price; Stage IV divided by the cheapest pack
> route anywhere in the set. Once Chase Economics is asked a product-level question, the
> correct denominator is Financial RIP's own cost re-expressed per random pack. One
> authority, two units.
>
> The revision is that one of the three requested authorities **cannot be built at all**:
> there is no MSRP or reference-retail data in this system, and the codebase forbids
> inventing one.

| | |
|---|---|
| Branch | `fix/public-rankings-entitlement-regression` |
| Market date | 2026-08-28 |
| Cohort | 145 scored products; 131 with a usable verified pack-equivalent route |
| Gate | Stage V-A returned `ECONOMIC_CHASE_FLOORS_VALIDATED_WITH_REVISIONS` |
| Production impact | **None.** |

---

## Phase 7 — Cost authority inventory

| authority | source | product-specific | history | status |
|---|---|---|---|---|
| **Product market price** | `simulation_sealed_product_results.product_market_cost`, dated by `price_as_of` | yes | `sealed_product_price_observations`, 2026-06-28 → 2026-08-28 | **exists, authoritative** |
| **Product-native pack-equivalent** | `product_market_cost / random_pack_count` | yes | derived | **exists, derivable** |
| **Cheapest-route pack cost** | `min(packEquivalentCost)` over verified routes in the set | **no — set constant** | derived | exists |
| **Financial RIP simulation cost** | the product's own `product_market_cost` | yes | as above | **exists — same field as row 1** |
| **MSRP / reference retail** | — | — | — | **DOES NOT EXIST** |

Taxes and shipping are excluded from every authority. Source is TCGPLAYER throughout.

**On MSRP.** This is not a gap to be filled later; it is a deliberate and enforced design
rule. Three independent places in the codebase state it:

* `sealed_product_rip_service.py` — "There is no fallback for (3). Not `pack_price *
  pack_count`, not MSRP, not an average of history, not a sibling SKU's price — a product
  with no current market price simply has no Stage 1 cost, and a score computed against an
  invented cost would look like a measurement while being a guess."
* `guaranteed_component_pricing_service.py` — "Not a sibling printing, not MSRP, not eBay…"
* migration `064_create_simulation_sealed_product_results.sql` — "pack count and never MSRP."

**Data quality note.** `sealed_product_price_observations` contains at least one row with a
NULL `captured_date`. Logged as a follow-up; it does not affect this stage, which addresses
prices through `simulation_sealed_product_results.price_as_of`.

---

## Phase 8 — Which question each basis answers

| question | correct denominator |
|---|---|
| **Exact Product Chase Economics** — "if I buy *this* product today, what are its chase economics?" | that product's `product_market_cost / random_pack_count` |
| **Cheapest Set Chase Route** — "what is the cheapest way to pursue this set's chases?" | cheapest verified pack-equivalent route in the set |
| **Reference-Retail Chase Economics** — "what would this look like at intended retail?" | **unanswerable — no data** |
| **Financial RIP** | the product's own `product_market_cost` (whole product, not per pack) |

The first two are genuinely different questions and both are worth publishing. They must
never be labelled the same thing, which is precisely the error set-level inheritance makes.

---

## Phase 9 — Reconciliation with Financial RIP

Taking the five sub-questions in order:

1. **Is Financial RIP's cost basis appropriate for exact-product opening economics?**
   Yes. It is the product's own current market price with no fallback of any kind. For
   "what happens if I buy this box", no better denominator exists.
2. **Should Chase Economics share it?** Yes, re-expressed per random pack. A chase floor is
   a statement about one pack ("this card is worth three packs *of this product*"), so the
   denominator must be per-pack, but it must be *this product's* per-pack cost.
   `product_market_cost / random_pack_count` is Financial RIP's cost in per-pack units, not
   a second opinion about it.
3. **Does the prior disagreement reflect a contract bug?** **No.** This study set out
   expecting one and did not find one. The ~66% divergence reported previously is fully
   explained by Stage IV dividing by a set-wide cheapest route while Financial RIP divides
   by the specific SKU. Both were correct for their own question. The bug would have been
   *inheriting* one onto the other — which is exactly what Stage V exists to prevent.
4. **Does cheapest-route pricing belong only at set level?** Yes. It is a set constant by
   construction and cannot express within-set variation, so it can never be the authority
   for a product-level metric. Retained for the Cheapest Set Chase Route question only.
5. **Should MSRP remain a secondary scenario?** It cannot be a scenario at all. There is no
   such data, and fabricating it is explicitly forbidden.

---

## Phase 10 — Cost-basis stress test

Core K at the V-A canonical 3×C floor, computed under both bases for all 131 products:

| statistic | Core (3×C) | Extended (1×C) |
|---|---:|---:|
| mean Δ (product − set) | **−2.95** | **−6.46** |
| median Δ | −1.0 | −4.0 |
| range | −16 … 0 | −42 … 0 |
| exact agreement | 48/131 (37%) | — |
| product-native gives a *smaller* Core | **83/131** | — |
| \|Δ\| ≥ 5 cards | 35/131 | 60/131 |

The maximum is 0 in both rows, and that is structural rather than incidental: the cheapest
route is by definition the lowest per-pack cost in the set, so no product can ever qualify
*more* cards than the set-level basis. **Set-level inheritance is therefore not merely
noisy — it is a systematic, one-directional overstatement of chase depth for 63% of
products.**

The bias is cleanly ordered by cost premium, which is the signature of a real mechanism
rather than an artifact:

| family | n | mean ΔK (3×C) | mean cost premium over cheapest route |
|---|---:|---:|---:|
| Pokémon Center ETB | 25 | **−6.48** | 2.69× |
| Elite Trainer Box | 26 | −4.19 | 1.75× |
| booster bundle | 22 | −2.36 | 1.36× |
| half booster box | 7 | −2.29 | 1.57× |
| sleeved booster pack | 14 | −1.79 | 1.34× |
| loose booster pack | 21 | −0.95 | 1.11× |
| booster box | 14 | −0.14 | 1.03× |
| enhanced booster box | 2 | 0.00 | 1.04× |

Worst single case: the Paradox Rift Pokémon Center ETB at $19.69/pack has a true Core of
**1 card**; set-level inheritance would have given it the booster box's **17**.

**Re-validation of the V-A floor against the selected basis** (the obligation V-A left
open): the 3×C/1×C floor was already evaluated against product-native cost in V-A Phase 5
— 3/131 empty Cores, 9/131 singletons, median K 7. It holds. Had 5×C been adopted, the
selected basis would have emptied 9 and reduced 35 to one card.

---

## Phase 11 — Decision

### `PRODUCT_CHASE_COST_BASIS_VALIDATED_WITH_REVISIONS`

**Live exact-product Chase Economics:** `product_market_cost / random_pack_count`, from
`simulation_sealed_product_results` at the run's `price_as_of`. No fallback. A product
without its own current market price has no chase economics and must be reported
unavailable with a reason code, never estimated from a sibling SKU or from
`pack_price × pack_count`.

**Set-level cheapest-route Chase Economics:** unchanged from Stage IV — cheapest verified
pack-equivalent route in the set. Retained as a separate published question ("cheapest way
into this set's chases"), never as a product attribute.

**Reference-retail Chase Economics:** `CANNOT_BE_BUILT`. No MSRP or reference-retail
authority exists, and three independent code sites forbid substituting one. This is the
revision in the decision code. It should be removed from the Stage V scope rather than
carried forward as pending work, unless an MSRP source is separately acquired and
validated.

**Interaction with Financial RIP:** one shared authority, two units. Financial RIP uses the
product's market price; Chase Economics uses the same price divided by that product's
random pack count. No contract bug was found, and none should be filed.

### Limitations

1. Sealed price history spans the same shallow window as card history (2026-06-28 →
   2026-08-28). Cost-basis *temporal* stability is therefore untested across regimes.
2. 14 of 145 scored products lack a usable verified route (no price, or unverified
   composition) and are excluded here; V-C must enumerate them with explicit reason codes
   rather than dropping them silently.
3. `random_pack_count` is the divisor, so guaranteed/promotional components are correctly
   excluded from the pack count — but this makes the floor sensitive to the accuracy of
   that field, which this stage did not independently audit.

---

## Gate status

Stage V-B has a research decision, so **Stage V-C may begin** — with one scope change
(reference-retail is removed) and one blocker discovered in advance, recorded below.

### Blocker discovered for V-C Phase 14

Phase 14 asks whether product chase probability may be derived from pack probability via
`P(≥1 chase) = 1 − (1−p_pack)^n`, to be "validated against native product simulation" with
non-IID families routed to native simulation instead.

**That validation cannot be performed.** Every one of the 145 scored products on the market
date carries `pack_independence_assumption = True`. The production simulator assumes IID
for *every* family; there is no non-IID native product simulation anywhere in the system to
validate the closed form against.

The closed form is therefore not an approximation of the production model — it *is* the
production model's assumption, restated. V-C may use it, but must report it as an
**inherited, unvalidated assumption of the whole pipeline**, not as something Stage V
tested and confirmed. Genuinely validating it would require collation data this system does
not hold, and is a separate study.

**Nothing was deployed.**
