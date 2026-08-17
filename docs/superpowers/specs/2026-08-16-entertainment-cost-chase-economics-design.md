# Entertainment Cost + Target-Card Chase Economics — Design

Date: 2026-08-16
Status: awaiting review (revision 2)
Branch context: `feature/rip-decision-layer`

## Purpose

Make the cost of *entertainment* explicit across every sealed product we model,
and quantify what it costs to open products specifically to obtain one target
card, versus simply buying that card.

This extends the quantitative information around RIP decisions. It does not
change any RIP formula, weight, threshold, tier or score. No file under
`backend/calculations/evr/financial_rip_v3*`, `backend/desirability/weighted_rip.py`
or `backend/desirability/collector_appeal*` is modified.

### Scope boundary: no promo or composition research

This task consumes existing guaranteed-component and composition data **only**.
It does not research, backfill, scrape, infer or manually add Mega Evolution
promos or any other promo mapping; it does not expand blister or
special-collection composition coverage; and it is not blocked by missing promo
data. A SKU lacking canonical inputs is published as explicitly unavailable
with its existing machine-readable reason. That work is tracked separately.

---

## 1. Audit of existing implementation

### Entertainment Cost

**Does not exist.** The only occurrence of the word "entertainment" in the
repository is marketing copy in `frontend/components/Footer.jsx`. There is no
calculation, no column, no snapshot field, and nothing computed-but-hidden.
There are therefore **no duplicate or conflicting implementations** to
reconcile.

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

- `backend/domain/pokemon/rip_decision_metrics.py` — `implied_odds_one_in_n`,
  `packs_for_cumulative_probability` (already exactly
  `ceil(log(1-q)/log(1-p))`), `exact_card_probability_contract` (50% and 90%
  thresholds only).
- `backend/db/services/rip_decision_service.py` — `build_top_chase_contract()`
  publishes the single highest-priced pullable card.

Missing: 75%/95% thresholds, everything product-specific, all spend and
recovery quantities, rip acquisition cost, entertainment premium, and coverage
beyond one card per set.

### Simulation engine

`extract_pack_outcome_vector` (`backend/calculations/evr/sealed_product_distribution.py:136`)
returns a **scalar** vector `X` of per-pack total values; card identity is
discarded before storage. Consequently a target-aware Monte Carlo over stored
artifacts is impossible without re-instrumenting the simulator. See §7.

---

## 2. Existing fields and data sources reused

| Input | Source | Notes |
|---|---|---|
| `expected_value`, `product_market_cost`, `pack_count` | `simulation_sealed_product_results` | per scored SKU, per run |
| `random_pack_count`, `guaranteed_component_market_value` | same (Stage 2 rows) | consumed as-is; never researched or backfilled here |
| `accessory_value_included` | same | **always `false`** |
| Per-card pull odds | `simulation_input_cards.effective_pull_rate` | stores **N** in "1 in N", *not* a probability, despite the column name |
| **Run-time card price** | **`simulation_input_cards.price_used`** | **the price the EV was actually built from — see §5** |
| Current card price | view `simulation_input_cards_with_near_mint_price.current_near_mint_price` | today's price |
| Composition | `sealed_product_composition.py`, `sealed_product_stage2_composition.py` | consumed as-is |
| Sealed market snapshot | `pokemon_set_sealed_market_snapshot_service.read_snapshot` | the only place unsupported SKUs appear |
| Threshold math | `rip_decision_metrics.packs_for_cumulative_probability` | reused, not reimplemented |

### Modeled formats

`sleeved_booster_pack` (1), `booster_bundle` (6), `booster_box` (36) at Stage 1;
`elite_trainer_box`, `pokemon_center_elite_trainer_box`, `enhanced_booster_box`
at Stage 2 with per-SKU composition rows.

**Three-pack blisters and special collection products are not modeled** and
their coverage is not expanded by this task. They are surfaced explicitly as
unsupported (§6.2).

---

## 3. Definition conflicts found

1. **Realizable value has no canonical definition.** Resolved:
   `recoveryModel: "gross_market_value"`, disclosed on every emitted block.
2. **The request's format list exceeds what is modeled.** Resolved by emitting
   explicit unsupported rows rather than silently omitting them.
3. **Per-pack thresholds are not product thresholds.** Resolved by §8's binding
   naming rules.
4. **Target-aware Monte Carlo is not possible on stored data.** Resolved by the
   analytical model (§7).
5. **The chase dataset is too large for the critical set-page payload.**
   Resolved by §6.3's separate snapshot surface.
6. **Two different card-price bases were being mixed.** Resolved by §5.

---

## 4. Modeling assumptions (binding, and stated in the contract)

These are published as a `modelAssumptions` block on every chase-economics
contract so no reader has to infer them.

### 4.1 Full-product opening — `successfulProductFullyOpened: true`

Every sealed product purchased during the chase is **opened in full**,
including the product in which the target first appears. This matches the
sealed-product RIP use case: the model prices "buy a booster box and open the
box", not "open packs until the target appears, then resell the remainder
sealed". Those are different economics, and V1 commits to the first.

A partial-product stopping model is **not** implemented in this task.

### 4.2 Independent packs — `packIndependenceAssumption: true`

Packs are modeled as i.i.d. draws, inheriting the existing
`PACK_INDEPENDENCE_ASSUMPTION` already published by the Stage 1/2 pipeline.
Real collation is not perfectly independent. Everything below is **exact under
this model**, not exact about physical products. See §7.

### 4.3 At most one target copy per random pack — today

Under the current Pokémon pack model a specific card occupies at most one slot
per pack, so `expectedTargetCopiesPerPack == targetProbabilityPerPack`. The
pure calculator does **not** assume this; see §6.4.

---

## 5. Target-price basis audit (data integrity)

**Result: the two prices can differ, and the repository retains both. No
approximation is needed.**

Lineage traced:

- `evr_input_repository` resolves Near Mint prices via
  `get_latest_prices_for_variants(...)` **at run time**.
- `calculation_run_persistence_service` (line ~973, 1020) persists that value
  into `simulation_input_cards.price_used`, via
  `_require_float(row.get("price_used"), "price_used")` in
  `calculation_runs_repository:987` — so it is **non-null and validated** for
  every input card of every run.
- `expected_value` on `simulation_sealed_product_results` is derived from that
  same run's pack simulation, i.e. from `price_used`.
- `simulation_input_cards_with_near_mint_price.current_near_mint_price` is
  **today's** price, joined at read time. `rip_decision_service` already
  documents this split deliberately: "the price should be today's, the
  probability MUST be the one the opening model actually ran with."

A run is refreshed daily but is not re-priced continuously, so on any given
read `price_used` and `current_near_mint_price` are frequently different
numbers for the same card. Subtracting a current $310 target price from an EV
aggregate that only contained $280 of target value would silently manufacture
$30 of phantom recovery per copy.

**Therefore two distinct concepts are carried:**

| Field | Source | Used for |
|---|---|---|
| `targetValueUsedInEV` | `simulation_input_cards.price_used` | separating the retained target from `grossPullValue` |
| `currentTargetMarketPrice` | `current_near_mint_price` | the buy-the-single comparison and Entertainment Premium |

Both are published, alongside `targetPriceBasisDelta =
currentTargetMarketPrice - targetValueUsedInEV`, so a reader can see the drift
rather than having it silently absorbed.

**Query cost: zero.** `_load_modeled_pull_denominators` already reads
`simulation_input_cards` for the whole run; `price_used` is an additional
column on that existing select, not an additional query.

---

## 6. Canonical formulas and data contract

### 6.1 Entertainment Cost

```
entertainmentCost                  = purchasePrice - expectedValue
entertainmentCostPerPackEquivalent = entertainmentCost / packCount
entertainmentCostRatio             = entertainmentCost / purchasePrice
```

`expectedValue` is the stored `expected_value` for the SKU; for Stage 2 rows it
already includes the guaranteed component, so no term is added here.

`entertainmentCostRatio` is the fraction of purchase price attributable to
entertainment cost under the gross-market-value recovery model. It is the only
ratio defined in this document. It is `null` when `purchasePrice` is missing,
non-numeric, non-finite, or `<= 0`.

**Nothing is clamped.** A negative `entertainmentCost` means the model prices
contents above market price — a real state, published as a negative number.

Every block discloses `recoveryModel: "gross_market_value"`,
`accessoryValueIncluded: false` (sleeves, dice, boxes, binders and code cards
carry zero value, mirroring the existing `ACCESSORY_VALUE_INCLUDED` contract),
and `guaranteedComponentIncluded`.

**This small block stays in the critical payload** — see §6.3.

### 6.2 Unsupported products

Sourced from the sealed market snapshot, the only place unmodeled SKUs appear.
Each carries `available: false` plus exactly one reason from the existing
closed vocabulary (`unsupported_product_family`,
`non_default_pack_count_variant`, `composite_multi_product_sku`,
`unresolved_composition`, `guaranteed_component_market_price_unavailable`,
`missing_product_market_price`, `invalid_or_missing_market_price`). No new
reason string is invented, and no SKU is silently omitted.

### 6.3 Where each contract is published

**The large chase dataset does not enter the critical set-page payload.**

The repository already separates critical from heavy per-card data:

| Surface | Table | Reader | Weight |
|---|---|---|---|
| Shell | — | `get_pokemon_set_shell_snapshot_payload` (:1702) | explicitly "never `payload_json`" |
| Critical set page | `pokemon_set_page_snapshot_latest` | `get_pokemon_set_page_snapshot_payload` (:1483) | carries `ripDecision` |
| **Heavy per-card** | **`pokemon_set_cards_snapshot_latest`** | **`get_pokemon_set_cards_snapshot_payload` (:2013)** | **separate row, separate request** |

The third row is the established precedent, and chase economics is the same
shape of problem: a large per-card table nothing on the critical path needs.

**Decision:**

- **Entertainment Cost (small)** → stays in `ripDecision`, as a per-product
  `entertainmentCost` block plus an `unsupportedProducts` list. This is a few
  hundred bytes per set and is decision-relevant beside the numbers it derives
  from.
- **Chase economics (large, ~60-90 KB)** → a **new dedicated snapshot table
  `pokemon_set_chase_economics_snapshot_latest`** (migration `067_`), mirroring
  the cards-snapshot pattern: `set_id` primary key, `payload_json`,
  `calculation_run_id`, `card_count`, `updated_at`, backend-only RLS matching
  migration `065`'s posture on `simulation_sealed_product_results`. Read by a
  new `get_pokemon_set_chase_economics_snapshot_payload(set_id)`.

Why a new table rather than joining `pokemon_set_cards_snapshot_latest`: that
row is already multi-MB and is read by the live cards page; appending an
unrelated 60-90 KB block would grow a payload that *is* on a user path, to no
benefit. A separate row is not delivered until something asks for it.

Why not compute on demand: the future frontend must retrieve the canonical
contract without recalculating it, and on-demand computation would require the
two whole-run population reads per request.

The frontend is not wired to the new surface in this task.

### 6.4 Chase economics — the pure model

Inputs, per pack group (forward-compatible with heterogeneous products):

```python
@dataclass(frozen=True)
class PackGroup:
    pack_count: int
    target_probability_per_pack: float        # P(pack contains >= 1 target)
    expected_target_copies_per_pack: float    # E[copies | one pack]
    expected_pack_value: float                # gross market value of one random pack
```

`target_probability_per_pack` and `expected_target_copies_per_pack` are
**separate inputs**. They are numerically equal under today's Pokémon model
(§4.3) and the service populates the second from the first, but the calculator
never assumes it — a future pack model with multiple target-capable slots needs
no contract rewrite.

Derived, over groups `g`:

```
p_prod        = 1 - Π_g (1 - p_g)^{k_g}
k_total       = Σ_g k_g
productValue  = Σ_g k_g · ev_g  +  guaranteedComponentMarketValue
expectedProductsToHit = 1 / p_prod
grossSpend            = productPrice / p_prod
grossPullValue        = productValue / p_prod
expectedTargetCopies  = (Σ_g k_g · c_g) / p_prod        (+ guaranteed_target_copies)
```

`expected_pack_value` is the value of one **random** pack:

```
Stage 1: expected_value / pack_count
Stage 2: (expected_value - guaranteed_component_market_value) / random_pack_count
```

Stage 2 must not use `expected_value / pack_count` — `expected_value` already
includes the promo, and dividing the whole figure by pack count would smear a
certain component across random packs. The guaranteed component instead enters
`productValue` once per product, as shown.

### 6.5 The acquisition metric — ONE retained copy

The question being answered is: *if I want one copy, what does acquiring that
one copy by ripping cost me versus buying it?* The user keeps **one** copy.
Any duplicate copies pulled along the way are as recoverable as any other
incidental pull.

```
retainedTargetCopies = 1

incidentalRecovery   = grossPullValue - targetValueUsedInEV
ripAcquisitionCost   = grossSpend - incidentalRecovery
entertainmentPremium = ripAcquisitionCost - currentTargetMarketPrice
```

Exactly **one** target value is removed, and it is removed at
`targetValueUsedInEV` — the same basis `grossPullValue` was built on (§5).
Expected duplicate copies remain inside `incidentalRecovery`, which is correct:
the user sells them.

The field is named `incidentalRecovery`, **not** `nonTargetRecovery`, because
it legitimately includes duplicate copies of the target card. Calling it
"non-target" would misdescribe its contents.

`expectedTargetCopies` is retained as an **informational statistic** — it
characterises the stopping product and validates the model — but it does *not*
enter the acquisition formula.

**Nothing is clamped.** `entertainmentCost`, `ripAcquisitionCost` and
`entertainmentPremium` may all be negative, and negatives are published.

**Why `expectedTargetCopies` can exceed 1.** Under the stopping rule, every
product before the stopping product contains **zero** target copies — if one
had contained the target it would itself have been the stopping product. The
excess comes entirely from the stopping product, which is opened in full
(§4.1) and may contain more than one copy. (The earlier draft of this spec
attributed extra copies to earlier products; that was wrong and is corrected
here. The formula was unaffected.)

### 6.6 Thresholds and spend distribution

```
packsForQPercentChance          = ceil(log(1-q) / log(1-p))        loose packs
productsForQPercentChance       = ceil(log(1-q) / log(1-p_prod))
packsPurchasedForQPercentChance = productsForQPercentChance * k_total
```

for `q ∈ {0.50, 0.75, 0.90, 0.95}`. Both pack quantities are preserved and
named unambiguously (§8); they coincide only when `k_total = 1`.

Spend distribution is free, spend being a deterministic function of product
count:

```
medianChaseSpend = productsFor50PercentChance * productPrice
p90ChaseSpend    = productsFor90PercentChance * productPrice
p95ChaseSpend    = productsFor95PercentChance * productPrice
```

### 6.7 Published shapes

Inside `ripDecision` (critical, small) — each `sealedProducts.products[]` entry
gains:

```jsonc
"entertainmentCost": {
  "entertainmentCost": 42.10,
  "entertainmentCostPerPackEquivalent": 1.17,
  "entertainmentCostRatio": 0.281,
  "purchasePrice": 149.99, "expectedValue": 107.89, "packCount": 36,
  "recoveryModel": "gross_market_value",
  "accessoryValueIncluded": false,
  "guaranteedComponentIncluded": false,
  "available": true, "reason": null,
  "contractVersion": "entertainment-cost-v1"
}
```

plus a sibling `unsupportedProducts` list of the same block shape with
`available: false` and a reason.

In `pokemon_set_chase_economics_snapshot_latest.payload_json` (non-critical,
large):

```jsonc
{
  "contractVersion": "target-chase-economics-v1",
  "recoveryModel": "gross_market_value",
  "sourceCalculationRunId": "…",
  "selectionPolicy": "top_market_price_pullable",
  "publishedCardLimit": 25,
  "eligibleCardCount": 187,
  "modelAssumptions": {
    "successfulProductFullyOpened": true,
    "packIndependenceAssumption": true,
    "retainedTargetCopies": 1,
    "exactnessScope": "exact_under_model_assumptions"
  },
  "cards": [{
    "cardId": "…", "cardVariantId": "…", "cardName": "…", "rarity": "…",
    "imageUrl": "…",
    "currentTargetMarketPrice": 310.00,
    "targetValueUsedInEV": 280.00,
    "targetPriceBasisDelta": 30.00,
    "modeledProbability": 0.0021, "impliedOddsOneInN": 476.2,
    "expectedPacksToHit": 476.2,
    "packsFor50PercentChance": 330, "packsFor75PercentChance": 660,
    "packsFor90PercentChance": 1096, "packsFor95PercentChance": 1425,
    "products": [{
      "sealedProductId": "…", "productFamily": "booster_box",
      "productPrice": 149.99, "packCount": 36,
      "targetProbabilityPerProduct": 0.0729,
      "expectedProductsToHit": 13.72,
      "productsFor50PercentChance": 10, "productsFor75PercentChance": 19,
      "productsFor90PercentChance": 31, "productsFor95PercentChance": 40,
      "packsPurchasedFor50PercentChance": 360,
      "packsPurchasedFor75PercentChance": 684,
      "packsPurchasedFor90PercentChance": 1116,
      "packsPurchasedFor95PercentChance": 1440,
      "grossSpend": 2057.9,
      "grossPullValue": 1480.2,
      "expectedTargetCopies": 1.037,
      "retainedTargetCopies": 1,
      "incidentalRecovery": 1200.2,
      "ripAcquisitionCost": 857.7,
      "entertainmentPremium": 547.7,
      "medianChaseSpend": 1499.9, "p90ChaseSpend": 4649.7,
      "p95ChaseSpend": 5999.6,
      "available": true, "reason": null
    }]
  }]
}
```

The 25-card cap is a **publication policy of the service only**. The pure
calculator accepts any eligible card and any product list; a future on-demand
endpoint calls the identical function.

---

## 7. Performance and the Monte Carlo question

**Decision: analytical in production, Monte Carlo as a test only.**

1. **Target-aware Monte Carlo is not possible on stored artifacts** — the pack
   vector is scalar and card identity is gone (§1). It would require
   instrumenting the simulator, which this task does not touch.
2. **The analytical results are exact under the model assumptions of §4** —
   not unconditionally exact about physical products. Products are i.i.d. draws
   under `packIndependenceAssumption`, and "open until the first product
   containing the target" is a stopping time adapted to the sequence, so Wald's
   identity gives `E[Σ value] = E[T]·E[value per product]` exactly *within the
   model*. Real collation is not perfectly independent; the analytical solution
   being exact relative to the model does not make the model exact.
   `exactnessScope: "exact_under_model_assumptions"` states this in the
   contract, and code comments must use the same qualified language.
3. **Cost.** Analytical: 25 cards × ≤6 products × ~30 flops ≈ 4,500 operations
   per set — sub-millisecond, immeasurable against the snapshot build. An
   open-until-hit Monte Carlo for a 1-in-500 card needs ~500 pack draws per
   trial; 10k trials × 25 cards × 6 products ≈ 750M draws per set, i.e. minutes
   per set across the catalogue, buying nothing but sampling noise.
4. **Query cost is zero.** `build_top_chase_contract` already loads the full
   per-run pull-denominator and Near-Mint-price populations and keeps one card.
   The population load is extracted so Top Chase, entertainment cost and chase
   economics share it; `price_used` rides along on the existing select (§5).
   Round trips do not increase.
5. **Payload cost is contained** by §6.3 — the large contract never enters a
   user-path request.

---

## 8. Naming rules (binding)

| Name | Meaning |
|---|---|
| `packsForQPercentChance` | loose packs, independent trials at `p`. Existing semantics unchanged. |
| `productsForQPercentChance` | whole sealed products, independent trials at `p_prod` |
| `packsPurchasedForQPercentChance` | `productsForQPercentChance × k_total` — packs actually owned after buying whole products |
| `expectedPacksToHit` / `expectedProductsToHit` | `1/p` / `1/p_prod` |
| `incidentalRecovery` | recoverable value of everything kept for resale, **including duplicate target copies** |
| `targetValueUsedInEV` | the target price the stored EV was built from |
| `currentTargetMarketPrice` | today's cost to buy the single |

A per-pack threshold is never labelled as a product-specific pack requirement.
The recovery term is never called `nonTargetRecovery`.

---

## 9. Implementation plan

### New files

1. `backend/domain/pokemon/entertainment_cost.py` — pure.
2. `backend/domain/pokemon/target_chase_economics.py` — pure. `PackGroup`,
   `target_chase_for_product`, `target_chase_for_card`. Reuses
   `packs_for_cumulative_probability`; the threshold formula is not
   reimplemented.
3. `backend/db/services/chase_economics_service.py` — impure; selection,
   joining, and the top-`limit` publication policy.
4. `backend/db/migrations/067_create_pokemon_set_chase_economics_snapshot.sql`
   — table + backend-only RLS, following `064`/`065`.
5. `backend/scripts/audit_entertainment_cost_chase.py` — read-only validation.

### Modified files

6. `backend/db/services/rip_decision_service.py` — additive: extract the shared
   run-population load (adding `price_used` to the existing select), attach
   `entertainmentCost` per product, add `unsupportedProducts`.
   `build_top_chase_contract`'s existing output keys are unchanged, so the
   `explore_rip_statistics_service` consumer (`ripDecision.topChase`, :1468)
   and the frontend contract tests are unaffected.
7. `backend/db/services/pokemon_public_snapshot_service.py` — add
   `get_pokemon_set_chase_economics_snapshot_payload(set_id)`, mirroring
   `get_pokemon_set_cards_snapshot_payload`.
8. `backend/scripts/pokemon_snapshot_builders.py` — build and persist the chase
   snapshot row alongside the existing merge.

Files 6-8 have uncommitted changes from the in-flight RIP-decision-layer work.
All edits are additive and confined to new functions plus their assembly
points, delivered as their own commit so it can be dropped independently.

### Not modified

No frontend file. No RIP scoring module. No promo, composition or classifier
data.

---

## 10. Tests

### `entertainment_cost.py`
- positive, zero and **negative** cost preserved unclamped
- ratio `null` for missing / non-numeric / non-finite / zero / negative price
- per-pack-equivalent `null` when `packCount <= 0`
- disclosure keys present on every block, including unavailable ones
- unsupported block carries a reason from the existing closed vocabulary

### `target_chase_economics.py`
- **`p_prod == p` when `k == 1`**
- **`expectedProductsToHit == 1 / p_prod`**
- **threshold monotonicity P50 ≤ P75 ≤ P90 ≤ P95**, packs and products
- **`packsPurchasedForQ` is an exact multiple of `k_total`**
- **exactly one target copy is removed**: doubling
  `expected_target_copies_per_pack` raises `expectedTargetCopies` and
  `incidentalRecovery` but leaves `retainedTargetCopies == 1`
- **basis separation**: with `targetValueUsedInEV != currentTargetMarketPrice`,
  `incidentalRecovery` uses the former and `entertainmentPremium` the latter;
  a fixture where they are swapped produces a detectably different premium
- **probability and copies are independent inputs**: a group with
  `expected_target_copies_per_pack != target_probability_per_pack` computes
  without error and changes only the copy-derived fields
- `expectedTargetCopies >= 1`; negative premium preserved unclamped
- boundaries: `p >= 1` → one product; `p <= 0` → unavailable, never `Infinity`;
  missing `currentTargetMarketPrice` → premium `null`, spend fields survive
- Stage 2 per-pack value excludes the guaranteed component; the promo appears
  once per product in `productValue`, not once per pack
- heterogeneous `pack_groups` reduce identically to the single-group form

### Statistical
- **analytical vs Monte Carlo** under the *same* i.i.d. assumptions: ~50k
  seeded open-until-hit trials at `p ≈ 1/50`, asserting
  `expectedProductsToHit`, `grossSpend`, `incidentalRecovery` and
  `ripAcquisitionCost` agree within tolerance. Test-only.
- empirical check of `ceil(log(1-q)/log(1-p))` against simulated hit frequency.

### Contract
- **no `NaN`/`Infinity` reaches JSON** — `json.dumps(..., allow_nan=False)`
  round-trip over both built contracts
- **unsupported products present and explicit**, never silently omitted
- **the top-25 cap does not constrain the calculator** — a direct pure call for
  a card outside the published 25 returns a full result
- **the critical payload does not grow by the chase table** — assert
  `chaseEconomics` is absent from `ripDecision` and present in the new snapshot
- existing `topChase` keys byte-identical to today's output
- the single-run invariant still raises on mixed `calculation_run_id`

### Regression
`test_rip_decision_service.py`, `test_rip_decision_metrics.py`,
`test_rip_decision_snapshot_merge.py`, `test_pokemon_public_snapshot_service.py`,
and the frontend `ripDecisionContract.test.mjs` / normalization suites must pass
unchanged.

---

## 11. Validation against real data

`backend/scripts/audit_entertainment_cost_chase.py`, dry-run only, no
`--commit` path, over three real sets (one modern high-chase set, one with
Stage 2 ETB coverage, one with unsupported blister SKUs present):

- every scored SKU: price, EV, entertainment cost, per-pack equivalent, ratio
- every unsupported SKU with its reason
- the top-25 chase table, including `targetValueUsedInEV` beside
  `currentTargetMarketPrice` and the observed basis delta across the set
- analytical thresholds beside a small Monte Carlo cross-check

Reported for review before anything is considered done.

---

## 12. Deliberately deferred

| Deferred | Why |
|---|---|
| All frontend/UI work, including reading the new snapshot | Owned by the in-flight RIP-decision-layer task |
| Mega Evolution promo research, promo mapping changes, composition backfill | Handled separately by instruction; consumed as-is here |
| Blister / special-collection composition coverage | No researched rows exist; inventing pack counts would publish confident wrong numbers |
| Realizable-value haircut | No empirical basis; `recoveryModel` marks the seam |
| Target-aware simulator instrumentation | Not needed — analytical is exact under model assumptions |
| Partial-product stopping model | §4.1 commits V1 to full-product opening |
| Heterogeneous multi-set products | Contract accommodates them (§6.4); no implementation |
| Cross-family "best way to chase" ranking | Repository policy is `within_product_family_only`; the contract enables it, this task does not rank |
| Any RIP formula, weight, tier or score change | Out of scope; no bug found requiring it |
