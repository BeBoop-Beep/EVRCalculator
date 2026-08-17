# Entertainment Cost + Target-Card Chase Economics — Design

Date: 2026-08-16
Status: awaiting review
Branch context: `feature/rip-decision-layer`

## Purpose

Make the cost of *entertainment* explicit across every sealed product we model,
and quantify what it costs to open products specifically to obtain one target
card, versus simply buying that card.

This extends the quantitative information around RIP decisions. It does not
change any RIP formula, weight, threshold or score. No file under
`backend/calculations/evr/financial_rip_v3*`, `backend/desirability/weighted_rip.py`
or `backend/desirability/collector_appeal*` is modified.

---

## 1. Audit of existing implementation

### Entertainment Cost

**Does not exist.** The only occurrence of the word "entertainment" in the
repository is marketing copy in `frontend/components/Footer.jsx`. There is no
calculation, no column, no snapshot field, and nothing computed-but-hidden.

There are therefore **no duplicate or conflicting implementations** to reconcile.

### Realizable value

**Does not exist.** Searches for `realizable`, `haircut`, `fee`, `net_of`,
`sell_through`, `liquid`, `discount_factor`, `recovery_rate` across the backend
return no modeling code. `simulation_sealed_product_results.expected_value` is
the raw arithmetic mean of the composed opening distribution, built from Near
Mint market prices with **no** deduction for marketplace fees, shipping,
grading, bid/ask spread or liquidation friction.

This contradicts the premise of the original request, which asked to "use the
existing canonical realizable-value assumptions already used elsewhere in the
RIP system." No such assumptions exist. **Resolution (approved):** define
Entertainment Cost on raw expected value and disclose the basis explicitly as
`recoveryModel: "gross_market_value"`. No haircut is invented. The contract is
shaped so a future haircut is a multiplier applied to one term, not a reshape.

### Target-chase economics

**Partially exists**, in the RIP decision layer this task follows:

- `backend/domain/pokemon/rip_decision_metrics.py`
  - `implied_odds_one_in_n(p)` → 1/p
  - `packs_for_cumulative_probability(p, q)` → `ceil(log(1-q)/log(1-p))`,
    already exactly the relationship the request asked us to validate against
  - `exact_card_probability_contract(p)` → `modeledProbability`,
    `impliedOddsOneInN`, `packsFor50PercentChance`, `packsFor90PercentChance`
- `backend/db/services/rip_decision_service.py`
  - `build_top_chase_contract()` publishes the single highest-priced pullable
    card with its current market price and the four fields above.

What is missing: 75% and 95% thresholds, everything product-specific, all spend
and recovery quantities, rip acquisition cost, entertainment premium, and
coverage beyond one card per set.

### Simulation engine

`extract_pack_outcome_vector` (`backend/calculations/evr/sealed_product_distribution.py:136`)
returns a **scalar** vector `X` of per-pack total values. Card identity is
discarded before storage. `build_stage1_product_distributions` bootstraps `X`
into K-pack sums `Y_K`.

Consequence: a target-aware Monte Carlo over the stored artifacts is
**impossible** — the data needed to know which pull was the target is not
retained. It would require re-instrumenting the simulator. See §6.

---

## 2. Existing fields and data sources reused

| Input | Source | Notes |
|---|---|---|
| `expected_value`, `product_market_cost`, `pack_count` | `simulation_sealed_product_results` | per scored SKU, per run |
| `median_value`, `p95_value`, `chance_to_recover_cost` | same | already published by the decision contract |
| `random_pack_count`, `guaranteed_component_market_value` | same (Stage 2 rows) | promo valued at exact market price |
| `accessory_value_included` | same | **always `false`** — see §4 |
| Per-card pull odds | `simulation_input_cards.effective_pull_rate` | stores **N** in "1 in N", *not* a probability, despite the column name |
| Current card price | view `simulation_input_cards_with_near_mint_price` | `current_near_mint_price` |
| Product family / composition | `sealed_product_composition.py`, `sealed_product_stage2_composition.py` | see §3 |
| Sealed market snapshot | `pokemon_set_sealed_market_snapshot_service.read_snapshot` | the only place unsupported SKUs appear |
| Threshold math | `rip_decision_metrics.packs_for_cumulative_probability` | reused, not reimplemented |

### Modeled formats

| Family | Packs | Stage |
|---|---|---|
| `sleeved_booster_pack` | 1 | 1 |
| `booster_bundle` | 6 | 1 |
| `booster_box` | 36 | 1 |
| `elite_trainer_box` | per composition row | 2 |
| `pokemon_center_elite_trainer_box` | per composition row | 2 |
| `enhanced_booster_box` | per composition row | 2 |

**Three-pack blisters and special collection products are not modeled.** They
have no composition row and are skipped as `unsupported_product_family`. This
task does not research those compositions; it surfaces them explicitly (§5).

---

## 3. Definition conflicts found

1. **Realizable value has no canonical definition.** Resolved as above:
   `recoveryModel: "gross_market_value"`, disclosed on every emitted block.
2. **The request's format list exceeds what is modeled.** Blisters and special
   collections cannot be computed. Resolved by emitting explicit unsupported
   rows rather than silently omitting them.
3. **Per-pack thresholds are not product thresholds.** The existing
   `packsFor50PercentChance` is a loose-pack quantity. Applying that label to a
   product-specific requirement would misstate what a buyer purchases. Resolved
   by §7's naming rules.
4. **Target-aware Monte Carlo is not possible on stored data.** Resolved by the
   analytical model, which is exact rather than approximate. See §6.

---

## 4. Canonical formulas

### 4.1 Entertainment Cost

```
entertainmentCost              = purchasePrice - expectedValue
entertainmentCostPerPackEquivalent = entertainmentCost / packCount
entertainmentCostRatio         = entertainmentCost / purchasePrice
```

`expectedValue` is the stored `expected_value` for the SKU. For Stage 2 rows it
already includes the guaranteed component's exact market value, so no term is
added here — doing so would double-count.

`entertainmentCostRatio` is the fraction of purchase price attributable to
entertainment cost under the gross-market-value recovery model. It is the only
ratio defined in this document; no second ratio definition is introduced.

`entertainmentCostRatio` is `null` when `purchasePrice` is missing,
non-numeric, non-finite, or `<= 0`. `entertainmentCost` is `null` when either
term is unavailable.

**Nothing is clamped.** A negative `entertainmentCost` means the model prices
the contents above the SKU's market price. That is a real, meaningful state and
is published as a negative number.

**Component treatment, stated explicitly on every block:**

- `recoveryModel: "gross_market_value"` — no fees, shipping, spread or grading
  deducted; not a liquidation estimate.
- `accessoryValueIncluded: false` — sleeves, dice, boxes, binders and code
  cards contribute **zero** recoverable value. This mirrors the existing
  `ACCESSORY_VALUE_INCLUDED = False` contract and is not a new assumption.
- `guaranteedComponentIncluded` — `true` for Stage 2 rows, `false` for Stage 1.
  Promos are valued at exact market price by the existing
  `guaranteed_component_value` module.

### 4.2 Target-Card Chase Economics

Let `p` be the per-pack probability of pulling at least one copy of the target
(`p = 1/N` from `effective_pull_rate`), and `k` the pack count of a product.

```
p_prod              = 1 - (1 - p)^k
expectedPacksToHit  = 1 / p
expectedProductsToHit = 1 / p_prod
grossSpend          = productPrice / p_prod
grossPullValue      = (k / p_prod) * expectedPackValue
expectedTargetCopies= (k / p_prod) * p
nonTargetRecovery   = grossPullValue - expectedTargetCopies * targetPrice
ripAcquisitionCost  = grossSpend - nonTargetRecovery
entertainmentPremium= ripAcquisitionCost - targetPrice
```

`expectedPackValue` is the modeled value of one **random** pack:

```
Stage 1: expectedPackValue = expected_value / pack_count
Stage 2: expectedPackValue = (expected_value - guaranteed_component_market_value)
                             / random_pack_count
```

Stage 2 must not use `expected_value / pack_count`. `expected_value` already
includes the guaranteed promo's exact market value, so dividing the whole
figure by the pack count would smear a certain component across random packs
and overstate what each pack contributes to the chase.

Correspondingly, for a Stage 2 product the guaranteed component is a certain
addition to every purchase, so it enters the journey once per product opened:

```
grossPullValue = (k_random / p_prod) * expectedPackValue
               + (1 / p_prod) * guaranteedComponentMarketValue
```

The guaranteed promo is never the target card in the products we model today
(promos are not in the pack pull table), so it contributes wholly to
`nonTargetRecovery`. If a future composition guarantees the target itself, that
is the `guaranteed_target_copies` parameter in §5.4, which shifts the copy into
`expectedTargetCopies` instead. It is `0.0` for every product modeled today.

For Stage 1, `k_random = k` and the guaranteed term is zero, reducing to the
simple form.

**Why `expectedTargetCopies` and not `1`.** The stopping product can contain
more than one copy of the target, and packs opened before the stopping product
can also contain copies. Subtracting exactly one target price would credit
those extra copies to non-target recovery, understating the true cost of the
chase. `expectedTargetCopies >= 1` always.

**Why these are exact, not approximations.** Products are i.i.d. draws and
"open until the first product containing the target" is a stopping time adapted
to the sequence, so Wald's identity gives
`E[Σ value] = E[T] · E[value per product]` exactly. The correlation between an
individual product's value and whether it contains the target does not break
this. The same argument gives `expectedTargetCopies`.

**Nothing is clamped.** `ripAcquisitionCost` and `entertainmentPremium` may be
negative — a chase whose incidental pulls are worth more than the sealed spend
produces a negative premium, which is analytically meaningful and published as
such.

### 4.3 Thresholds and distribution

Loose packs (existing function, extended to four thresholds):

```
packsForQPercentChance = ceil(log(1 - q) / log(1 - p))       q ∈ {.50,.75,.90,.95}
```

Products, and the packs a buyer actually purchases:

```
productsForQPercentChance   = ceil(log(1 - q) / log(1 - p_prod))
packsPurchasedForQPercentChance = productsForQPercentChance * k
```

The two pack quantities are named unambiguously and both are preserved.
`packsForQPercentChance` answers "if I could buy loose packs"; the `Purchased`
variant answers "how many packs do I end up owning after buying whole
products". They coincide only when `k = 1`.

Chase spend distribution is free — spend is a deterministic function of product
count:

```
medianChaseSpend = productsFor50PercentChance * productPrice
p90ChaseSpend    = productsFor90PercentChance * productPrice
p95ChaseSpend    = productsFor95PercentChance * productPrice
```

---

## 5. Data contract

All additions are **additive keys** inside the existing
`build_rip_decision_contract()` output, which is merged into
`payload_json.ripDecision`. The frontend normalizes `ripDecision` as a
pass-through `toNullablePlainObject`, so no existing consumer or contract test
breaks.

### 5.1 Per-product entertainment cost

Each entry of `sealedProducts.products` gains:

```jsonc
"entertainmentCost": {
  "entertainmentCost": 42.10,
  "entertainmentCostPerPackEquivalent": 1.17,
  "entertainmentCostRatio": 0.281,
  "purchasePrice": 149.99,
  "expectedValue": 107.89,
  "packCount": 36,
  "recoveryModel": "gross_market_value",
  "accessoryValueIncluded": false,
  "guaranteedComponentIncluded": false,
  "available": true,
  "reason": null,
  "contractVersion": "entertainment-cost-v1"
}
```

### 5.2 Unsupported products

A new sibling list, sourced from the sealed market snapshot (the only place
unmodeled SKUs appear — they are never written to
`simulation_sealed_product_results`):

```jsonc
"unsupportedProducts": {
  "productCount": 4,
  "products": [
    {
      "sealedProductId": "…",
      "productName": "… 3-Pack Blister",
      "productFamily": "three_pack_blister",
      "marketPrice": 14.99,
      "entertainmentCost": { "available": false, "reason": "unsupported_product_family", … }
    }
  ]
}
```

Reasons reuse the existing closed vocabulary (`unsupported_product_family`,
`non_default_pack_count_variant`, `composite_multi_product_sku`,
`unresolved_composition`, `guaranteed_component_market_price_unavailable`,
`missing_product_market_price`, `invalid_or_missing_market_price`). No new
reason string is invented.

### 5.3 Chase economics

```jsonc
"chaseEconomics": {
  "contractVersion": "target-chase-economics-v1",
  "recoveryModel": "gross_market_value",
  "sourceCalculationRunId": "…",
  "selectionPolicy": "top_market_price_pullable",
  "publishedCardLimit": 25,
  "eligibleCardCount": 187,
  "cards": [
    {
      "cardId": "…", "cardVariantId": "…", "cardName": "…", "rarity": "…",
      "imageUrl": "…", "imageSmallUrl": "…", "imageLargeUrl": "…",
      "currentMarketPrice": 310.00,
      "modeledProbability": 0.0021, "impliedOddsOneInN": 476.2,
      "expectedPacksToHit": 476.2,
      "packsFor50PercentChance": 330, "packsFor75PercentChance": 660,
      "packsFor90PercentChance": 1096, "packsFor95PercentChance": 1425,
      "products": [
        {
          "sealedProductId": "…", "productFamily": "booster_box",
          "productPrice": 149.99, "packCount": 36,
          "targetProbabilityPerProduct": 0.0729,
          "expectedProductsToHit": 13.72,
          "productsFor50PercentChance": 10,
          "productsFor75PercentChance": 19,
          "productsFor90PercentChance": 31,
          "productsFor95PercentChance": 40,
          "packsPurchasedFor50PercentChance": 360,
          "packsPurchasedFor75PercentChance": 684,
          "packsPurchasedFor90PercentChance": 1116,
          "packsPurchasedFor95PercentChance": 1440,
          "grossSpend": 2057.9,
          "grossPullValue": 1480.2,
          "expectedTargetCopies": 1.037,
          "nonTargetRecovery": 1158.7,
          "ripAcquisitionCost": 899.2,
          "targetPrice": 310.00,
          "entertainmentPremium": 589.2,
          "medianChaseSpend": 1499.9,
          "p90ChaseSpend": 4649.7,
          "p95ChaseSpend": 5999.6,
          "available": true, "reason": null
        }
      ]
    }
  ]
}
```

`chaseEconomics.cards` is capped at 25 by the **publication** layer only. The
pure calculator accepts any card and any product list; the cap is a parameter
of the service, not a property of the calculation. A future on-demand endpoint
for an arbitrary card calls the identical function.

### 5.4 Heterogeneous-composition forward compatibility

The pure chase function does **not** take `(k, price)`. It takes a sequence of
pack groups plus a price:

```python
target_chase_for_product(
    product_price=149.99,
    pack_groups=[PackGroup(pack_count=36,
                           target_probability_per_pack=0.0021,
                           expected_pack_value=2.997)],
    target_price=310.00,
    guaranteed_target_copies=0.0,
)
```

`p_prod = 1 - Π_g (1 - p_g)^{k_g}`, `k_total = Σ k_g`,
`expected product value = Σ k_g · ev_g (+ guaranteed component value)`. For
every product we model today there is exactly one group and this reduces
identically to the `k`-pack formulas in §4.2. A future collection product with
packs from two sets, or a guaranteed target slot, is expressible without
reshaping the contract.

This is a shape decision only. **No unsupported composition is researched or
implemented in this task.**

---

## 6. Performance and the Monte Carlo question

**Decision: analytical, with Monte Carlo retained only as a test.**

Rationale:

1. **Target-aware Monte Carlo is not possible on stored artifacts.** The pack
   outcome vector is scalar; card identity is gone. It would require
   instrumenting the simulator to retain per-pull card identity across ~1M
   simulated packs per set, a large change to the engine this task was told not
   to touch.
2. **The analytical results are exact, not approximate.** Wald's identity makes
   the expectation terms exact; the threshold terms are exact by construction.
   Monte Carlo would reproduce the same numbers with added sampling noise.
3. **Cost.** Analytical: 25 cards × ~6 products × ~30 floating-point operations
   ≈ 4,500 operations per set — sub-millisecond, and immeasurable against the
   existing snapshot build. An open-until-hit Monte Carlo for a 1-in-500 card
   needs ~500 pack draws per trial; 10k trials × 25 cards × 6 products ≈ 750M
   draws per set, i.e. minutes per set added to a per-set daily refresh across
   the whole catalogue. That is the tradeoff, and it buys nothing.
4. **Query cost is zero.** `build_top_chase_contract` already reads the full
   per-run pull-denominator and Near-Mint-price populations and keeps one card.
   Chase economics consumes those same two reads. The refactor extracts the
   population load so both consumers share it — the number of database round
   trips does not increase.

**Payload size.** 25 cards × up to 6 products × ~22 numeric fields ≈ 3,300
values, roughly 60-90 KB of JSON per set snapshot. This is the one real cost.
If measurement shows it materially affects snapshot read latency, the
mitigation is lowering `publishedCardLimit`, which is a constant, not a code
change.

---

## 7. Naming rules (binding)

| Name | Meaning |
|---|---|
| `packsForQPercentChance` | loose packs, independent trials at `p`. Unchanged existing semantics. |
| `productsForQPercentChance` | whole sealed products, independent trials at `p_prod` |
| `packsPurchasedForQPercentChance` | `productsForQPercentChance × packCount` — packs actually owned after buying whole products |
| `expectedPacksToHit` | `1/p`, loose-pack expectation |
| `expectedProductsToHit` | `1/p_prod` |

A per-pack threshold is never labelled as a product-specific pack requirement.

---

## 8. Implementation plan

### New files

1. **`backend/domain/pokemon/entertainment_cost.py`** — pure. No database, no
   policy. `entertainment_cost_contract(...)` and
   `unsupported_entertainment_cost(reason)`. Follows the existing
   `rip_decision_metrics.py` discipline: missing inputs return `None`, never a
   fabricated `0.0`; no `NaN`/`Infinity` ever leaves the module.

2. **`backend/domain/pokemon/target_chase_economics.py`** — pure.
   `PackGroup` dataclass, `target_chase_for_product(...)`,
   `target_chase_for_card(...)`, `chase_threshold_contract(...)`. Reuses
   `packs_for_cumulative_probability` from `rip_decision_metrics`; the
   threshold formula is not reimplemented.

3. **`backend/db/services/chase_economics_service.py`** — impure. Selects the
   top-`limit` pullable cards by current market price from an already-loaded
   run population, joins the scored product rows, and calls the pure layer.

### Modified files

4. **`backend/db/services/rip_decision_service.py`** — additive:
   - extract the run-population load so Top Chase and chase economics share it
     (no new queries),
   - attach `entertainmentCost` to each product row,
   - add `unsupportedProducts` from the sealed market snapshot,
   - add `chaseEconomics`.

   `build_top_chase_contract` keeps its current output keys unchanged so the
   in-flight `explore_rip_statistics_service` consumer
   (`ripDecision.topChase`, line 1468) and the frontend contract tests are
   unaffected.

This file currently has uncommitted changes from the RIP-decision-layer work.
Edits will be additive and confined to new functions plus the assembly points
in `build_rip_decision_contract`, delivered as their own commit so it can be
dropped independently.

### Explicitly not modified

`pokemon_snapshot_builders.py` and `pokemon_public_snapshot_service.py` need no
change: they merge whatever `build_rip_decision_contract` returns. No frontend
file is touched.

---

## 9. Tests

### Unit — `entertainment_cost.py`
- positive, zero and **negative** entertainment cost preserved unclamped
- ratio `null` for missing / non-numeric / non-finite / zero / negative price
- per-pack-equivalent `null` when `packCount <= 0`
- `recoveryModel`, `accessoryValueIncluded`, `guaranteedComponentIncluded`
  present on every block including unavailable ones
- unsupported block carries a reason from the existing closed vocabulary

### Unit — `target_chase_economics.py`
- **`p_prod == p` when `k == 1`** (invariant)
- **`expectedProductsToHit == 1 / p_prod`** (invariant)
- **threshold monotonicity: P50 ≤ P75 ≤ P90 ≤ P95** for both packs and products
- **`packsPurchasedForQ` is an exact multiple of `packCount`** (invariant)
- `expectedTargetCopies >= 1` for all valid inputs
- negative `entertainmentPremium` preserved unclamped
- boundaries: `p >= 1` → one pack/one product; `p <= 0` → unavailable, not
  `Infinity`; missing target price → premium `null` while spend fields survive
- heterogeneous `pack_groups` reduce identically to the single-group `k` form
- **Stage 2 per-pack value excludes the guaranteed component**: a fixture whose
  `expected_value` is inflated by a promo must not raise `expectedPackValue`;
  the promo must appear once per product in `grossPullValue`, not once per pack
- `guaranteed_target_copies > 0` moves the copy into `expectedTargetCopies` and
  out of `nonTargetRecovery` (forward-compatibility path, no live product uses it)

### Property/statistical
- **analytical vs Monte Carlo agreement**: simulate open-until-hit for a
  moderate `p` (~1/50) over ~50k trials against a fixed seed; assert
  `expectedProductsToHit`, `grossSpend`, `nonTargetRecovery` and
  `ripAcquisitionCost` agree within Monte Carlo tolerance. Test-only; no
  production Monte Carlo path.
- direct check of `ceil(log(1-q)/log(1-p))` against empirical hit frequency.

### Contract — `rip_decision_service.py`
- **no `NaN` or `Infinity` reaches the payload** — `json.dumps` round-trip with
  `allow_nan=False` over a full built contract
- **unsupported products are present and explicit**, never silently omitted
- **the top-25 cap does not constrain the calculator**: a direct call to the
  pure function for a card outside the published 25 returns a full result
- existing `topChase` keys are byte-identical to today's output
- the single-run invariant still raises on mixed `calculation_run_id`

### Regression
- existing suites must pass unchanged: `test_rip_decision_service.py`,
  `test_rip_decision_metrics.py`, `test_rip_decision_snapshot_merge.py`,
  `test_pokemon_public_snapshot_service.py`, and the frontend
  `ripDecisionContract.test.mjs` / normalization tests.

---

## 10. Validation against real data

A read-only script, `backend/scripts/audit_entertainment_cost_chase.py`,
dry-run by default with no `--commit` path, printing for three real sets
(one modern high-chase set, one set with Stage 2 ETB coverage, one set with
unsupported blister SKUs present):

- every scored SKU with price, EV, entertainment cost, per-pack equivalent and
  ratio
- every unsupported SKU with its reason
- the top-25 chase table for the highest-priced card across all products
- an independence cross-check: analytical thresholds beside a small Monte Carlo

Results reported back for review before anything is considered done.

---

## 11. Deliberately deferred

| Deferred | Why |
|---|---|
| All frontend/UI work | Owned by the in-flight RIP-decision-layer task |
| Blister and special-collection compositions | No researched composition rows exist; inventing pack counts would publish confident wrong numbers |
| Realizable-value haircut | No empirical basis in this repository; `recoveryModel` field marks the seam |
| Target-aware simulator instrumentation | Not needed — analytical results are exact (§6) |
| Heterogeneous multi-set products | Contract shape accommodates them (§5.4); no implementation |
| Cross-family "best way to chase" ranking | Repository policy is `within_product_family_only`; the data contract enables it, this task does not rank |
| Any change to RIP formulas, weights or scores | Out of scope by instruction; no bug found requiring it |
