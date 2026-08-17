# Entertainment Cost + Target-Card Chase Economics Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Publish, for every sealed product we model, what a buyer is paying for the entertainment of opening rather than buying — and for the top 25 chase cards per set, what acquiring one copy by ripping costs versus buying the single.

**Architecture:** Two pure calculation modules under `backend/domain/pokemon/` (no database, no policy, fully unit-testable), one impure service that applies selection and publication policy, and additive wiring into the existing `ripDecision` contract plus one new non-critical snapshot table. All production math is analytical closed form; Monte Carlo exists only as a validation test.

**Tech Stack:** Python 3.13, NumPy (already a dependency), pytest, Supabase/PostgREST, raw SQL migrations applied manually.

**Spec:** `docs/superpowers/specs/2026-08-16-entertainment-cost-chase-economics-design.md` — read it before Task 1. The plan argues from the spec; where they appear to disagree, the spec wins and you should stop and flag it.

## Global Constraints

Copied verbatim from the spec. These apply to **every** task.

- **No RIP formula, weight, threshold, tier or score changes.** No file under `backend/calculations/evr/financial_rip_v3*`, `backend/desirability/weighted_rip.py` or `backend/desirability/collector_appeal*` may be modified.
- **No promo, composition or classifier research.** Consume `guaranteed_component_market_value`, `random_pack_count` and composition rows exactly as they are. Do not backfill, scrape, infer or hand-add Mega Evolution promos or any other mapping. A SKU lacking canonical inputs stays explicitly unavailable.
- **No frontend files.** Not one.
- **Recovery basis is `recoveryModel: "gross_market_value"`.** No haircut, no fee deduction, no liquidation estimate is introduced anywhere.
- **Nothing is clamped.** `entertainmentCost`, `ripAcquisitionCost` and `entertainmentPremium` may be negative and negatives are published as-is.
- **Missing inputs stay missing.** Return `None` rather than a fabricated `0.0`. A fabricated zero is indistinguishable from a measured zero on a page.
- **No `NaN` or `Infinity` may reach any contract.** Every public return must survive `json.dumps(..., allow_nan=False)`.
- **`guaranteed_target_copies` is removed from V1.** Do not add the parameter back. A product guaranteeing the target implies `p_prod = 1`, which collapses the chase into a different model.
- **`targetPriceBasisDelta = currentTargetMarketPrice - targetValueUsedInEV`** — current minus EV-basis. Positive means the card appreciated since the run was priced.
- **The recovery term is named `incidentalRecovery`**, never `nonTargetRecovery`. It includes duplicate copies of the target.
- **Exactness language is qualified.** Write "exact under the model assumptions" in docstrings and comments, never bare "exact".
- **Test command:** `./backend/.venv/Scripts/python.exe -m pytest <path> -q`, run from the repository root `d:\EVRCalculator`. The root `.venv-1` has no pytest installed — do not use it.

---

## File Structure

| File | Responsibility |
|---|---|
| `backend/domain/pokemon/entertainment_cost.py` | **Create.** Pure. Price − EV, per-pack equivalent, ratio, disclosure block. |
| `backend/domain/pokemon/target_chase_economics.py` | **Create.** Pure. `PackGroup`, product-level chase math, threshold contracts. |
| `backend/db/services/chase_economics_service.py` | **Create.** Impure. Card selection, top-N publication policy, contract assembly. |
| `backend/db/migrations/<NNN>_create_pokemon_set_chase_economics_snapshot.sql` | **Create.** Non-critical snapshot table + backend-only RLS. |
| `backend/db/services/rip_decision_service.py` | **Modify.** Shared run-population load; attach `entertainmentCost`; add `unsupportedProducts`. |
| `backend/db/services/pokemon_public_snapshot_service.py` | **Modify.** Add the chase snapshot reader. |
| `backend/scripts/pokemon_snapshot_builders.py` | **Modify.** Build and persist the chase snapshot row. |
| `backend/scripts/audit_entertainment_cost_chase.py` | **Create.** Read-only real-data validation. |
| `backend/tests/unit/domain/test_entertainment_cost.py` | **Create.** |
| `backend/tests/unit/domain/test_target_chase_economics.py` | **Create.** |
| `backend/tests/unit/domain/test_target_chase_monte_carlo.py` | **Create.** Statistical validation, test-only. |
| `backend/tests/unit/db/services/test_chase_economics_service.py` | **Create.** |

Files 5–7 carry uncommitted changes from the in-flight RIP-decision-layer work. Every edit to them is **additive** — new functions plus their assembly points. Do not reformat, reorder or refactor surrounding code. Commit them separately (Tasks 6 and 7) so those commits can be dropped independently.

---

## Task 1: Pure Entertainment Cost module

**Files:**
- Create: `backend/domain/pokemon/entertainment_cost.py`
- Test: `backend/tests/unit/domain/test_entertainment_cost.py`

**Interfaces:**
- Consumes: nothing from earlier tasks.
- Produces:
  - `ENTERTAINMENT_COST_CONTRACT_VERSION: str = "entertainment-cost-v1"`
  - `RECOVERY_MODEL_GROSS_MARKET_VALUE: str = "gross_market_value"`
  - `REASON_EXPECTED_VALUE_UNAVAILABLE: str = "expected_value_unavailable"`
  - `REASON_MARKET_PRICE_UNAVAILABLE: str = "market_price_unavailable"`
  - `entertainment_cost_contract(*, purchase_price, expected_value, pack_count, guaranteed_component_included=False) -> Dict[str, Any]`
  - `unsupported_entertainment_cost(reason, *, purchase_price=None, pack_count=None) -> Dict[str, Any]`

- [ ] **Step 1: Write the failing tests**

Create `backend/tests/unit/domain/test_entertainment_cost.py`:

```python
"""Contract tests for the Entertainment Cost display math.

Entertainment Cost is purchase price minus the modeled gross market value of
what is inside. It is not a score, not a recommendation, and not a liquidation
estimate: `recoveryModel` states the basis on every block.
"""

import json

import pytest

from backend.domain.pokemon.entertainment_cost import (
    ENTERTAINMENT_COST_CONTRACT_VERSION,
    REASON_EXPECTED_VALUE_UNAVAILABLE,
    REASON_MARKET_PRICE_UNAVAILABLE,
    RECOVERY_MODEL_GROSS_MARKET_VALUE,
    entertainment_cost_contract,
    unsupported_entertainment_cost,
)


def test_entertainment_cost_is_price_minus_expected_value():
    block = entertainment_cost_contract(
        purchase_price=149.99, expected_value=107.89, pack_count=36
    )
    assert block["entertainmentCost"] == pytest.approx(42.10)
    assert block["available"] is True
    assert block["reason"] is None


def test_per_pack_equivalent_divides_by_pack_count():
    block = entertainment_cost_contract(
        purchase_price=149.99, expected_value=107.89, pack_count=36
    )
    assert block["entertainmentCostPerPackEquivalent"] == pytest.approx(42.10 / 36)


def test_ratio_is_entertainment_cost_over_purchase_price():
    block = entertainment_cost_contract(
        purchase_price=100.0, expected_value=72.0, pack_count=10
    )
    assert block["entertainmentCostRatio"] == pytest.approx(0.28)


def test_negative_entertainment_cost_is_preserved_not_clamped():
    # The model prices the contents above what the SKU sells for. A real state.
    block = entertainment_cost_contract(
        purchase_price=100.0, expected_value=130.0, pack_count=36
    )
    assert block["entertainmentCost"] == pytest.approx(-30.0)
    assert block["entertainmentCostRatio"] == pytest.approx(-0.30)
    assert block["entertainmentCostPerPackEquivalent"] == pytest.approx(-30.0 / 36)


def test_zero_entertainment_cost_is_a_real_measurement():
    block = entertainment_cost_contract(
        purchase_price=100.0, expected_value=100.0, pack_count=1
    )
    assert block["entertainmentCost"] == 0.0
    assert block["available"] is True


@pytest.mark.parametrize("bad_price", [None, 0.0, -5.0, "abc", float("nan"), float("inf"), True])
def test_ratio_is_none_for_unusable_purchase_price(bad_price):
    block = entertainment_cost_contract(
        purchase_price=bad_price, expected_value=50.0, pack_count=36
    )
    assert block["entertainmentCostRatio"] is None
    assert block["entertainmentCost"] is None
    assert block["available"] is False
    assert block["reason"] == REASON_MARKET_PRICE_UNAVAILABLE


def test_missing_expected_value_reports_its_own_reason():
    block = entertainment_cost_contract(
        purchase_price=149.99, expected_value=None, pack_count=36
    )
    assert block["entertainmentCost"] is None
    assert block["available"] is False
    assert block["reason"] == REASON_EXPECTED_VALUE_UNAVAILABLE


@pytest.mark.parametrize("bad_count", [None, 0, -3, "x"])
def test_per_pack_equivalent_is_none_without_a_usable_pack_count(bad_count):
    block = entertainment_cost_contract(
        purchase_price=149.99, expected_value=107.89, pack_count=bad_count
    )
    # The total cost and ratio do not depend on pack count and survive.
    assert block["entertainmentCost"] == pytest.approx(42.10)
    assert block["entertainmentCostPerPackEquivalent"] is None


def test_disclosure_keys_are_present_on_an_available_block():
    block = entertainment_cost_contract(
        purchase_price=149.99, expected_value=107.89, pack_count=36,
        guaranteed_component_included=True,
    )
    assert block["recoveryModel"] == RECOVERY_MODEL_GROSS_MARKET_VALUE
    assert block["accessoryValueIncluded"] is False
    assert block["guaranteedComponentIncluded"] is True
    assert block["contractVersion"] == ENTERTAINMENT_COST_CONTRACT_VERSION


def test_disclosure_keys_are_present_on_an_unavailable_block():
    # A reader must be able to see the basis even when there is no number.
    block = unsupported_entertainment_cost("unsupported_product_family")
    assert block["recoveryModel"] == RECOVERY_MODEL_GROSS_MARKET_VALUE
    assert block["accessoryValueIncluded"] is False
    assert block["available"] is False
    assert block["reason"] == "unsupported_product_family"
    assert block["entertainmentCost"] is None


def test_unsupported_block_keeps_a_known_price():
    block = unsupported_entertainment_cost(
        "unsupported_product_family", purchase_price=14.99
    )
    assert block["purchasePrice"] == 14.99
    assert block["entertainmentCost"] is None


def test_every_block_shape_is_json_safe():
    blocks = [
        entertainment_cost_contract(purchase_price=149.99, expected_value=107.89, pack_count=36),
        entertainment_cost_contract(purchase_price=float("inf"), expected_value=1.0, pack_count=1),
        unsupported_entertainment_cost("unsupported_product_family"),
    ]
    for block in blocks:
        json.dumps(block, allow_nan=False)


def test_available_and_unavailable_blocks_have_identical_key_sets():
    # One contract, not two shapes a consumer has to branch on.
    available = entertainment_cost_contract(
        purchase_price=149.99, expected_value=107.89, pack_count=36
    )
    unavailable = unsupported_entertainment_cost("unsupported_product_family")
    assert set(available) == set(unavailable)


def test_reason_strings_match_the_decision_service_vocabulary():
    # Two spellings of the same reason is one too many. The domain module may
    # not import the service, so equality is asserted here instead.
    from backend.db.services import rip_decision_service

    assert REASON_EXPECTED_VALUE_UNAVAILABLE == rip_decision_service.REASON_EXPECTED_VALUE_UNAVAILABLE
    assert REASON_MARKET_PRICE_UNAVAILABLE == rip_decision_service.REASON_MARKET_PRICE_UNAVAILABLE
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `./backend/.venv/Scripts/python.exe -m pytest backend/tests/unit/domain/test_entertainment_cost.py -q`

Expected: collection error — `ModuleNotFoundError: No module named 'backend.domain.pokemon.entertainment_cost'`.

- [ ] **Step 3: Write the implementation**

Create `backend/domain/pokemon/entertainment_cost.py`:

```python
"""Entertainment Cost: what you pay for the experience of opening.

WHAT THIS IS
------------
    Entertainment Cost = purchase price - modeled gross market value of contents

A direct, reversible transformation of two numbers that already exist on
``simulation_sealed_product_results``: ``product_market_cost`` and
``expected_value``. Pure: no database, no policy, no run resolution.

WHAT THIS DELIBERATELY IS NOT
-----------------------------
* NOT a score. Nothing here is fitted, weighted, calibrated or normalized, and
  nothing here may be ranked.
* NOT a judgement. A high entertainment cost is not "a bad buy" - buying
  entertainment is a legitimate purchase, and this module only prices it.
* NOT a liquidation estimate. See RECOVERY MODEL below.

RECOVERY MODEL
--------------
``gross_market_value``. Expected value is the raw mean of modeled Near Mint
market prices with NO deduction for marketplace fees, shipping, grading,
bid/ask spread or the practical impossibility of selling every card. The real
cash a seller nets is therefore LOWER than the value credited here, which makes
the entertainment cost published here a LOWER BOUND. This is disclosed on every
block rather than assumed, and no haircut is invented: the repository has no
empirically grounded one, and a made-up multiplier would look like a
measurement while being a guess.

Accessories - sleeves, dice, boxes, binders, code cards - carry ZERO value,
matching the existing ``ACCESSORY_VALUE_INCLUDED = False`` contract in the
Stage 2 composition module. This is inherited, not a new assumption.

MISSING INPUTS STAY MISSING
---------------------------
Every field is ``None`` rather than a placeholder when its input is absent,
non-numeric, non-finite or out of domain. A fabricated ``0.0`` is
indistinguishable on a page from a measured one, which makes it the more
dangerous of the two failure modes.
"""

from __future__ import annotations

import math
from typing import Any, Dict, Optional

ENTERTAINMENT_COST_CONTRACT_VERSION = "entertainment-cost-v1"

#: The only recovery basis this module implements. Published on every block.
RECOVERY_MODEL_GROSS_MARKET_VALUE = "gross_market_value"

#: Inherited from the Stage 2 composition contract, not decided here.
ACCESSORY_VALUE_INCLUDED = False

# Reason vocabulary. These strings MUST equal the identically-named constants in
# ``backend.db.services.rip_decision_service``; a test asserts it. They are
# duplicated rather than imported because a domain module importing a database
# service would invert the dependency direction for two string literals.
REASON_EXPECTED_VALUE_UNAVAILABLE = "expected_value_unavailable"
REASON_MARKET_PRICE_UNAVAILABLE = "market_price_unavailable"

#: Rounding strips IEEE-754 representation noise only (``0.1 + 0.2``). The
#: precision is far beyond any display need, so this never changes a value.
_PRECISION = 12


def _finite_float(value: Any) -> Optional[float]:
    """``value`` as a finite float, or ``None``. Booleans are not numbers here."""
    if value is None or isinstance(value, bool):
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(number):
        return None
    return number


def _positive(value: Any) -> Optional[float]:
    number = _finite_float(value)
    if number is None or number <= 0.0:
        return None
    return number


def _positive_int(value: Any) -> Optional[int]:
    number = _finite_float(value)
    if number is None or number <= 0.0:
        return None
    return int(number)


def _block(
    *,
    entertainment_cost: Optional[float],
    per_pack_equivalent: Optional[float],
    ratio: Optional[float],
    purchase_price: Optional[float],
    expected_value: Optional[float],
    pack_count: Optional[int],
    guaranteed_component_included: bool,
    available: bool,
    reason: Optional[str],
) -> Dict[str, Any]:
    """The ONE block shape. Available and unavailable results share it exactly.

    Two shapes would force every consumer to branch before reading a field, and
    a consumer that forgets to branch reads a missing key as a missing value.
    """
    return {
        "entertainmentCost": entertainment_cost,
        "entertainmentCostPerPackEquivalent": per_pack_equivalent,
        "entertainmentCostRatio": ratio,
        "purchasePrice": purchase_price,
        "expectedValue": expected_value,
        "packCount": pack_count,
        "recoveryModel": RECOVERY_MODEL_GROSS_MARKET_VALUE,
        "accessoryValueIncluded": ACCESSORY_VALUE_INCLUDED,
        "guaranteedComponentIncluded": bool(guaranteed_component_included),
        "available": available,
        "reason": reason,
        "contractVersion": ENTERTAINMENT_COST_CONTRACT_VERSION,
    }


def entertainment_cost_contract(
    *,
    purchase_price: Any,
    expected_value: Any,
    pack_count: Any,
    guaranteed_component_included: bool = False,
) -> Dict[str, Any]:
    """Entertainment Cost for ONE sealed product.

    ``expected_value`` is the stored ``expected_value`` for the SKU. For a
    Stage 2 product it ALREADY includes the guaranteed component's exact market
    value, so nothing is added here - adding it again would double-count the
    promo.

    Negative results are returned unchanged. A product whose modeled contents
    are worth more than its price has a negative entertainment cost, and
    clamping it to zero would erase the most interesting rows in the table.
    """
    price = _positive(purchase_price)
    value = _finite_float(expected_value)
    packs = _positive_int(pack_count)

    if value is None:
        return _block(
            entertainment_cost=None,
            per_pack_equivalent=None,
            ratio=None,
            purchase_price=price,
            expected_value=None,
            pack_count=packs,
            guaranteed_component_included=guaranteed_component_included,
            available=False,
            reason=REASON_EXPECTED_VALUE_UNAVAILABLE,
        )

    if price is None:
        return _block(
            entertainment_cost=None,
            per_pack_equivalent=None,
            ratio=None,
            purchase_price=None,
            expected_value=value,
            pack_count=packs,
            guaranteed_component_included=guaranteed_component_included,
            available=False,
            reason=REASON_MARKET_PRICE_UNAVAILABLE,
        )

    cost = round(price - value, _PRECISION)
    return _block(
        entertainment_cost=cost,
        # Survives independently: a missing pack count does not invalidate the
        # total, only the per-pack normalization used to compare formats.
        per_pack_equivalent=None if packs is None else round(cost / packs, _PRECISION),
        ratio=round(cost / price, _PRECISION),
        purchase_price=price,
        expected_value=value,
        pack_count=packs,
        guaranteed_component_included=guaranteed_component_included,
        available=True,
        reason=None,
    )


def unsupported_entertainment_cost(
    reason: str, *, purchase_price: Any = None, pack_count: Any = None
) -> Dict[str, Any]:
    """An explicitly unavailable block for a product we do not model.

    Emitted rather than omitted. A blister that vanishes from the table is
    indistinguishable from a blister that does not exist, and a reader
    comparing formats needs to know the difference.

    ``reason`` must come from the existing closed vocabulary in the Stage 1/2
    composition and decision modules. No reason string is invented here.
    """
    return _block(
        entertainment_cost=None,
        per_pack_equivalent=None,
        ratio=None,
        purchase_price=_positive(purchase_price),
        expected_value=None,
        pack_count=_positive_int(pack_count),
        guaranteed_component_included=False,
        available=False,
        reason=reason,
    )
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `./backend/.venv/Scripts/python.exe -m pytest backend/tests/unit/domain/test_entertainment_cost.py -q`

Expected: PASS, all tests.

- [ ] **Step 5: Commit**

```bash
git add backend/domain/pokemon/entertainment_cost.py backend/tests/unit/domain/test_entertainment_cost.py
git commit -m "Add pure Entertainment Cost contract module

Price minus modeled gross market value, per-pack equivalent and ratio, with
the recovery basis and accessory treatment disclosed on every block. Negative
costs are preserved; missing inputs stay missing.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

---

## Task 2: Pure target-chase economics module

**Files:**
- Create: `backend/domain/pokemon/target_chase_economics.py`
- Test: `backend/tests/unit/domain/test_target_chase_economics.py`

**Interfaces:**
- Consumes: `backend.domain.pokemon.rip_decision_metrics.packs_for_cumulative_probability` (existing, unmodified).
- Produces:
  - `TARGET_CHASE_CONTRACT_VERSION: str = "target-chase-economics-v1"`
  - `CHASE_THRESHOLDS: tuple = (0.50, 0.75, 0.90, 0.95)`
  - `PackGroup` frozen dataclass with fields `pack_count: int`, `target_probability_per_pack: float`, `expected_target_copies_per_pack: float`, `expected_pack_value: float`
  - `REASON_PROBABILITY_UNAVAILABLE`, `REASON_PRODUCT_PRICE_UNAVAILABLE`, `REASON_NO_PACK_GROUPS`
  - `loose_pack_odds_contract(*, target_probability_per_pack) -> Dict[str, Any]`
  - `target_chase_for_product(*, product_price, pack_groups, target_value_used_in_ev, current_target_market_price, guaranteed_component_market_value=0.0) -> Dict[str, Any]`
  - `model_assumptions_contract() -> Dict[str, Any]`

- [ ] **Step 1: Write the failing tests**

Create `backend/tests/unit/domain/test_target_chase_economics.py`:

```python
"""Contract tests for target-card chase economics.

Everything here is exact UNDER THE MODEL ASSUMPTIONS (i.i.d. packs, the whole
successful product opened). It is not a claim about physical collation.
"""

import json

import pytest

from backend.domain.pokemon.target_chase_economics import (
    CHASE_THRESHOLDS,
    REASON_PRODUCT_PRICE_UNAVAILABLE,
    REASON_PROBABILITY_UNAVAILABLE,
    PackGroup,
    loose_pack_odds_contract,
    model_assumptions_contract,
    target_chase_for_product,
)


def _group(pack_count=36, p=0.0021, copies=None, ev=2.997):
    return PackGroup(
        pack_count=pack_count,
        target_probability_per_pack=p,
        expected_target_copies_per_pack=p if copies is None else copies,
        expected_pack_value=ev,
    )


def _box(**overrides):
    kwargs = {
        "product_price": 149.99,
        "pack_groups": [_group()],
        "target_value_used_in_ev": 280.0,
        "current_target_market_price": 310.0,
    }
    kwargs.update(overrides)
    return target_chase_for_product(**kwargs)


# ---------------------------------------------------------------------------
# Core identities
# ---------------------------------------------------------------------------

def test_product_probability_reduces_to_pack_probability_for_a_single_pack():
    block = target_chase_for_product(
        product_price=4.99,
        pack_groups=[_group(pack_count=1, p=0.0021)],
        target_value_used_in_ev=280.0,
        current_target_market_price=310.0,
    )
    assert block["targetProbabilityPerProduct"] == pytest.approx(0.0021)


def test_expected_products_to_hit_is_the_reciprocal_of_product_probability():
    block = _box()
    assert block["expectedProductsToHit"] == pytest.approx(
        1.0 / block["targetProbabilityPerProduct"]
    )


def test_gross_spend_is_price_times_expected_products():
    block = _box()
    assert block["grossSpend"] == pytest.approx(
        149.99 * block["expectedProductsToHit"]
    )


def test_thresholds_are_monotonic_for_products_and_purchased_packs():
    block = _box()
    products = [block[f"productsFor{int(q * 100)}PercentChance"] for q in CHASE_THRESHOLDS]
    purchased = [block[f"packsPurchasedFor{int(q * 100)}PercentChance"] for q in CHASE_THRESHOLDS]
    assert products == sorted(products)
    assert purchased == sorted(purchased)


def test_loose_pack_thresholds_are_monotonic():
    odds = loose_pack_odds_contract(target_probability_per_pack=0.0021)
    packs = [odds[f"packsFor{int(q * 100)}PercentChance"] for q in CHASE_THRESHOLDS]
    assert packs == sorted(packs)


def test_purchased_pack_thresholds_are_exact_multiples_of_pack_count():
    block = _box()
    for q in CHASE_THRESHOLDS:
        products = block[f"productsFor{int(q * 100)}PercentChance"]
        purchased = block[f"packsPurchasedFor{int(q * 100)}PercentChance"]
        assert purchased == products * 36


def test_loose_pack_and_purchased_pack_thresholds_differ_for_multipack_products():
    # Naming exists precisely because these are different questions.
    odds = loose_pack_odds_contract(target_probability_per_pack=0.0021)
    block = _box()
    assert odds["packsFor50PercentChance"] != block["packsPurchasedFor50PercentChance"]


# ---------------------------------------------------------------------------
# One retained copy
# ---------------------------------------------------------------------------

def test_exactly_one_target_value_is_removed_from_recovery():
    block = _box()
    assert block["retainedTargetCopies"] == 1
    assert block["incidentalRecovery"] == pytest.approx(
        block["grossPullValue"] - 280.0
    )


def test_duplicate_copies_stay_inside_incidental_recovery():
    # Doubling expected copies must NOT increase the amount removed. The user
    # keeps one copy and sells the rest.
    single = _box()
    double = _box(pack_groups=[_group(copies=0.0042)])
    assert double["expectedTargetCopies"] > single["expectedTargetCopies"]
    assert double["retainedTargetCopies"] == 1
    assert double["incidentalRecovery"] == pytest.approx(double["grossPullValue"] - 280.0)


def test_rip_acquisition_cost_is_spend_minus_incidental_recovery():
    block = _box()
    assert block["ripAcquisitionCost"] == pytest.approx(
        block["grossSpend"] - block["incidentalRecovery"]
    )


def test_entertainment_premium_compares_against_the_current_single_price():
    block = _box()
    assert block["entertainmentPremium"] == pytest.approx(
        block["ripAcquisitionCost"] - 310.0
    )


def test_expected_target_copies_is_at_least_one():
    block = _box()
    assert block["expectedTargetCopies"] >= 1.0


def test_negative_entertainment_premium_is_preserved_not_clamped():
    # A cheap product whose packs are unusually rich in value.
    block = target_chase_for_product(
        product_price=1.0,
        pack_groups=[_group(pack_count=36, p=0.20, ev=50.0)],
        target_value_used_in_ev=5.0,
        current_target_market_price=5.0,
    )
    assert block["entertainmentPremium"] < 0


# ---------------------------------------------------------------------------
# Price basis separation
# ---------------------------------------------------------------------------

def test_recovery_uses_the_ev_basis_and_premium_uses_the_current_price():
    block = _box(target_value_used_in_ev=280.0, current_target_market_price=310.0)
    swapped = _box(target_value_used_in_ev=310.0, current_target_market_price=280.0)
    # Both bases move, so both derived numbers must move.
    assert block["incidentalRecovery"] != swapped["incidentalRecovery"]
    assert block["entertainmentPremium"] != swapped["entertainmentPremium"]


def test_price_basis_delta_is_current_minus_ev_basis():
    appreciated = _box(target_value_used_in_ev=280.0, current_target_market_price=310.0)
    depreciated = _box(target_value_used_in_ev=310.0, current_target_market_price=280.0)
    assert appreciated["targetPriceBasisDelta"] == pytest.approx(30.0)
    assert depreciated["targetPriceBasisDelta"] == pytest.approx(-30.0)


def test_missing_current_price_nulls_the_premium_but_keeps_the_spend():
    block = _box(current_target_market_price=None)
    assert block["entertainmentPremium"] is None
    assert block["targetPriceBasisDelta"] is None
    assert block["grossSpend"] is not None
    assert block["ripAcquisitionCost"] is not None
    assert block["available"] is True


def test_missing_ev_basis_price_nulls_recovery_and_acquisition():
    block = _box(target_value_used_in_ev=None)
    assert block["incidentalRecovery"] is None
    assert block["ripAcquisitionCost"] is None
    assert block["entertainmentPremium"] is None
    assert block["grossSpend"] is not None


# ---------------------------------------------------------------------------
# Probability and copies are separate inputs
# ---------------------------------------------------------------------------

def test_copies_can_differ_from_probability_without_error():
    # Today they are equal, but a future pack model with two target-capable
    # slots must not require a contract rewrite.
    block = _box(pack_groups=[_group(p=0.0021, copies=0.0035)])
    assert block["targetProbabilityPerProduct"] == pytest.approx(
        1.0 - (1.0 - 0.0021) ** 36
    )
    assert block["expectedTargetCopies"] == pytest.approx(
        (36 * 0.0035) / block["targetProbabilityPerProduct"]
    )


def test_changing_copies_alone_does_not_change_probability_fields():
    base = _box(pack_groups=[_group(copies=0.0021)])
    more = _box(pack_groups=[_group(copies=0.0084)])
    assert base["targetProbabilityPerProduct"] == more["targetProbabilityPerProduct"]
    assert base["expectedProductsToHit"] == more["expectedProductsToHit"]
    assert base["grossSpend"] == more["grossSpend"]
    assert more["expectedTargetCopies"] > base["expectedTargetCopies"]


def test_guaranteed_target_copies_parameter_is_not_accepted():
    # Deferred from V1 on purpose: a guaranteed target implies p_prod == 1,
    # which is a different model, not a parameter of this one.
    with pytest.raises(TypeError):
        target_chase_for_product(
            product_price=149.99,
            pack_groups=[_group()],
            target_value_used_in_ev=280.0,
            current_target_market_price=310.0,
            guaranteed_target_copies=1.0,
        )


# ---------------------------------------------------------------------------
# Guaranteed components and heterogeneous groups
# ---------------------------------------------------------------------------

def test_guaranteed_component_enters_once_per_product_not_once_per_pack():
    without = target_chase_for_product(
        product_price=49.99,
        pack_groups=[_group(pack_count=9, p=0.0021, ev=3.0)],
        target_value_used_in_ev=280.0,
        current_target_market_price=310.0,
    )
    with_promo = target_chase_for_product(
        product_price=49.99,
        pack_groups=[_group(pack_count=9, p=0.0021, ev=3.0)],
        target_value_used_in_ev=280.0,
        current_target_market_price=310.0,
        guaranteed_component_market_value=5.0,
    )
    delta = with_promo["grossPullValue"] - without["grossPullValue"]
    # One promo per product opened, not nine.
    assert delta == pytest.approx(5.0 * with_promo["expectedProductsToHit"])


def test_heterogeneous_groups_reduce_to_the_single_group_form():
    single = target_chase_for_product(
        product_price=149.99,
        pack_groups=[_group(pack_count=36, p=0.0021, ev=2.997)],
        target_value_used_in_ev=280.0,
        current_target_market_price=310.0,
    )
    split = target_chase_for_product(
        product_price=149.99,
        pack_groups=[
            _group(pack_count=20, p=0.0021, ev=2.997),
            _group(pack_count=16, p=0.0021, ev=2.997),
        ],
        target_value_used_in_ev=280.0,
        current_target_market_price=310.0,
    )
    assert split["targetProbabilityPerProduct"] == pytest.approx(
        single["targetProbabilityPerProduct"]
    )
    assert split["grossPullValue"] == pytest.approx(single["grossPullValue"])
    assert split["packCount"] == 36


def test_heterogeneous_groups_with_different_rates_combine_independently():
    block = target_chase_for_product(
        product_price=100.0,
        pack_groups=[
            PackGroup(pack_count=2, target_probability_per_pack=0.10,
                      expected_target_copies_per_pack=0.10, expected_pack_value=1.0),
            PackGroup(pack_count=3, target_probability_per_pack=0.05,
                      expected_target_copies_per_pack=0.05, expected_pack_value=2.0),
        ],
        target_value_used_in_ev=10.0,
        current_target_market_price=10.0,
    )
    expected = 1.0 - (0.90 ** 2) * (0.95 ** 3)
    assert block["targetProbabilityPerProduct"] == pytest.approx(expected)
    assert block["packCount"] == 5


# ---------------------------------------------------------------------------
# Boundaries
# ---------------------------------------------------------------------------

def test_certain_pull_needs_one_product():
    block = _box(pack_groups=[_group(pack_count=1, p=1.0, copies=1.0)])
    assert block["targetProbabilityPerProduct"] == pytest.approx(1.0)
    assert block["expectedProductsToHit"] == pytest.approx(1.0)
    for q in CHASE_THRESHOLDS:
        assert block[f"productsFor{int(q * 100)}PercentChance"] == 1


@pytest.mark.parametrize("bad_p", [0.0, -0.5, None, float("nan"), float("inf")])
def test_impossible_pull_is_unavailable_never_infinite(bad_p):
    block = _box(pack_groups=[_group(p=bad_p, copies=0.0)])
    assert block["available"] is False
    assert block["reason"] == REASON_PROBABILITY_UNAVAILABLE
    assert block["expectedProductsToHit"] is None
    assert block["grossSpend"] is None


@pytest.mark.parametrize("bad_price", [None, 0.0, -1.0, "x", float("inf")])
def test_missing_product_price_is_unavailable(bad_price):
    block = _box(product_price=bad_price)
    assert block["available"] is False
    assert block["reason"] == REASON_PRODUCT_PRICE_UNAVAILABLE
    assert block["grossSpend"] is None


def test_empty_pack_groups_is_unavailable():
    block = _box(pack_groups=[])
    assert block["available"] is False


def test_loose_pack_odds_are_unavailable_for_a_non_positive_rate():
    odds = loose_pack_odds_contract(target_probability_per_pack=0.0)
    assert odds["modeledProbability"] is None
    assert odds["impliedOddsOneInN"] is None
    assert odds["expectedPacksToHit"] is None
    for q in CHASE_THRESHOLDS:
        assert odds[f"packsFor{int(q * 100)}PercentChance"] is None


# ---------------------------------------------------------------------------
# Disclosure and JSON safety
# ---------------------------------------------------------------------------

def test_model_assumptions_are_published():
    assumptions = model_assumptions_contract()
    assert assumptions["successfulProductFullyOpened"] is True
    assert assumptions["packIndependenceAssumption"] is True
    assert assumptions["retainedTargetCopies"] == 1
    assert assumptions["exactnessScope"] == "exact_under_model_assumptions"


def test_available_and_unavailable_product_blocks_share_a_key_set():
    assert set(_box()) == set(_box(product_price=None))


def test_every_shape_is_json_safe():
    for block in (
        _box(),
        _box(product_price=None),
        _box(current_target_market_price=None),
        _box(pack_groups=[_group(p=0.0)]),
        loose_pack_odds_contract(target_probability_per_pack=0.0021),
        loose_pack_odds_contract(target_probability_per_pack=None),
        model_assumptions_contract(),
    ):
        json.dumps(block, allow_nan=False)


def test_spend_distribution_tracks_the_product_thresholds():
    block = _box()
    assert block["medianChaseSpend"] == pytest.approx(
        block["productsFor50PercentChance"] * 149.99
    )
    assert block["p90ChaseSpend"] == pytest.approx(
        block["productsFor90PercentChance"] * 149.99
    )
    assert block["p95ChaseSpend"] == pytest.approx(
        block["productsFor95PercentChance"] * 149.99
    )
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `./backend/.venv/Scripts/python.exe -m pytest backend/tests/unit/domain/test_target_chase_economics.py -q`

Expected: collection error — `ModuleNotFoundError: No module named 'backend.domain.pokemon.target_chase_economics'`.

- [ ] **Step 3: Write the implementation**

Create `backend/domain/pokemon/target_chase_economics.py`:

```python
"""Target-card chase economics: what chasing ONE card actually costs.

THE QUESTION
------------
    If I want this specific card and choose to rip products until I pull it,
    what does that journey cost me compared with buying the single?

The point is NOT that opening packs is bad. The point is to price the
entertainment honestly, so someone who wants to open products can see what the
experience costs them relative to the alternative.

THE MODEL, AND ITS LIMITS
-------------------------
Three assumptions, all published on the contract via
``model_assumptions_contract`` so no reader has to infer them:

1. ``successfulProductFullyOpened`` - every product bought is opened in full,
   INCLUDING the one containing the target. This matches the sealed-product RIP
   use case ("buy a box, open the box"). It is NOT the same as opening packs
   until the target appears and reselling the remainder sealed, which is a
   different and un-modeled journey.
2. ``packIndependenceAssumption`` - packs are i.i.d. draws, inherited from the
   existing Stage 1/2 pipeline. Real collation is not perfectly independent.
3. ``retainedTargetCopies = 1`` - the chaser keeps ONE copy and sells
   everything else, duplicate targets included.

Every result here is EXACT UNDER THESE ASSUMPTIONS - the closed forms are not
approximations of a simulation, they are the model's answer. That is a
different and weaker claim than being exact about physical products, and the
``exactnessScope`` field says so.

WHY CLOSED FORM RATHER THAN MONTE CARLO
---------------------------------------
Products are i.i.d. draws and "open until the first product containing the
target" is a stopping time adapted to the sequence, so Wald's identity gives
``E[sum over the journey] = E[products] * E[value per product]`` exactly within
the model. Simulating would reproduce these numbers with added sampling noise
and minutes of runtime per set. A Monte Carlo agreement test exists
(``test_target_chase_monte_carlo.py``) and is test-only.

WHY ``incidentalRecovery`` AND NOT ``nonTargetRecovery``
--------------------------------------------------------
Because it legitimately includes DUPLICATE COPIES OF THE TARGET. The chaser
keeps one and sells the rest, so extra copies are recoverable exactly like any
other incidental pull. Calling the term "non-target" would misdescribe its
contents.

TWO PRICES, NOT ONE
-------------------
``target_value_used_in_ev`` is the price the stored EV was actually built from
(``simulation_input_cards.price_used``). ``current_target_market_price`` is what
buying the single costs today. They drift apart between runs. The retained copy
is removed from the journey value at the EV basis - removing it at today's
price would manufacture phantom recovery equal to the drift - while the
buy-versus-rip comparison uses today's price, because that is what the reader
would actually pay.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any, Dict, Optional, Sequence

from backend.domain.pokemon.rip_decision_metrics import (
    packs_for_cumulative_probability,
)

TARGET_CHASE_CONTRACT_VERSION = "target-chase-economics-v1"

#: The published cumulative-probability thresholds. Ordered ascending; the
#: contract's monotonicity guarantee depends on that order.
CHASE_THRESHOLDS = (0.50, 0.75, 0.90, 0.95)

REASON_PROBABILITY_UNAVAILABLE = "modeled_probability_unavailable"
REASON_PRODUCT_PRICE_UNAVAILABLE = "product_price_unavailable"
REASON_NO_PACK_GROUPS = "no_pack_groups"

_PRECISION = 12


@dataclass(frozen=True)
class PackGroup:
    """One homogeneous block of random packs inside a product.

    ``target_probability_per_pack`` and ``expected_target_copies_per_pack`` are
    SEPARATE inputs on purpose. Under today's Pokemon model a specific card
    occupies at most one slot per pack, so they are numerically equal and the
    service populates the second from the first - but they are different
    quantities, and a future pack model with two target-capable slots must not
    require a contract rewrite to express.

    ``expected_pack_value`` is the gross market value of ONE RANDOM pack. For a
    Stage 2 product this must EXCLUDE the guaranteed component: the stored
    ``expected_value`` already contains the promo, and dividing the whole figure
    by the pack count would smear a certain component across random packs. The
    promo is passed separately to ``target_chase_for_product``.

    A product is a SEQUENCE of these. Every product modeled today has exactly
    one group; the sequence exists so a future collection product with packs
    from two sets is expressible without reshaping anything.
    """

    pack_count: int
    target_probability_per_pack: float
    expected_target_copies_per_pack: float
    expected_pack_value: float


def _finite_float(value: Any) -> Optional[float]:
    if value is None or isinstance(value, bool):
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(number):
        return None
    return number


def _positive(value: Any) -> Optional[float]:
    number = _finite_float(value)
    if number is None or number <= 0.0:
        return None
    return number


def _non_negative(value: Any) -> Optional[float]:
    number = _finite_float(value)
    if number is None or number < 0.0:
        return None
    return number


def _threshold_key(prefix: str, threshold: float) -> str:
    return f"{prefix}For{int(round(threshold * 100))}PercentChance"


def model_assumptions_contract() -> Dict[str, Any]:
    """The assumptions every number in this module rests on.

    Attached to published contracts rather than documented only here: a reader
    holding the payload cannot open this docstring.
    """
    return {
        "successfulProductFullyOpened": True,
        "packIndependenceAssumption": True,
        "retainedTargetCopies": 1,
        "exactnessScope": "exact_under_model_assumptions",
        "recoveryModel": "gross_market_value",
        "contractVersion": TARGET_CHASE_CONTRACT_VERSION,
    }


def loose_pack_odds_contract(*, target_probability_per_pack: Any) -> Dict[str, Any]:
    """Per-pack odds and LOOSE-PACK thresholds for one card.

    These answer "if I could buy individual packs". They are NOT the number of
    packs a buyer ends up with after purchasing whole products - see
    ``packsPurchasedFor...`` on the product block, which is generally larger
    because products are bought whole.
    """
    p = _positive(target_probability_per_pack)
    block: Dict[str, Any] = {
        "modeledProbability": p,
        "impliedOddsOneInN": None if p is None else round(1.0 / p, _PRECISION),
        "expectedPacksToHit": None if p is None else round(1.0 / p, _PRECISION),
    }
    for threshold in CHASE_THRESHOLDS:
        block[_threshold_key("packs", threshold)] = packs_for_cumulative_probability(
            p, threshold
        )
    return block


def _product_block(
    *,
    pack_count: Optional[int],
    probability: Optional[float],
    expected_products: Optional[float],
    gross_spend: Optional[float],
    gross_pull_value: Optional[float],
    expected_target_copies: Optional[float],
    incidental_recovery: Optional[float],
    rip_acquisition_cost: Optional[float],
    target_value_used_in_ev: Optional[float],
    current_target_market_price: Optional[float],
    price_basis_delta: Optional[float],
    entertainment_premium: Optional[float],
    thresholds: Dict[str, Any],
    spend_distribution: Dict[str, Any],
    available: bool,
    reason: Optional[str],
) -> Dict[str, Any]:
    """The ONE product block shape, shared by available and unavailable results."""
    block: Dict[str, Any] = {
        "packCount": pack_count,
        "targetProbabilityPerProduct": probability,
        "expectedProductsToHit": expected_products,
        "grossSpend": gross_spend,
        "grossPullValue": gross_pull_value,
        "expectedTargetCopies": expected_target_copies,
        # Always 1 under the V1 model, published so a reader never has to guess
        # how many copies were treated as kept.
        "retainedTargetCopies": 1,
        "incidentalRecovery": incidental_recovery,
        "ripAcquisitionCost": rip_acquisition_cost,
        "targetValueUsedInEV": target_value_used_in_ev,
        "currentTargetMarketPrice": current_target_market_price,
        "targetPriceBasisDelta": price_basis_delta,
        "entertainmentPremium": entertainment_premium,
        "available": available,
        "reason": reason,
        "contractVersion": TARGET_CHASE_CONTRACT_VERSION,
    }
    block.update(thresholds)
    block.update(spend_distribution)
    return block


def _empty_thresholds() -> Dict[str, Any]:
    thresholds: Dict[str, Any] = {}
    for threshold in CHASE_THRESHOLDS:
        thresholds[_threshold_key("products", threshold)] = None
        thresholds[_threshold_key("packsPurchased", threshold)] = None
    return thresholds


def _empty_spend_distribution() -> Dict[str, Any]:
    return {"medianChaseSpend": None, "p90ChaseSpend": None, "p95ChaseSpend": None}


def _unavailable(reason: str, **known: Any) -> Dict[str, Any]:
    defaults: Dict[str, Any] = {
        "pack_count": None,
        "probability": None,
        "expected_products": None,
        "gross_spend": None,
        "gross_pull_value": None,
        "expected_target_copies": None,
        "incidental_recovery": None,
        "rip_acquisition_cost": None,
        "target_value_used_in_ev": None,
        "current_target_market_price": None,
        "price_basis_delta": None,
        "entertainment_premium": None,
        "thresholds": _empty_thresholds(),
        "spend_distribution": _empty_spend_distribution(),
        "available": False,
        "reason": reason,
    }
    defaults.update(known)
    return _product_block(**defaults)


def target_chase_for_product(
    *,
    product_price: Any,
    pack_groups: Sequence[PackGroup],
    target_value_used_in_ev: Any,
    current_target_market_price: Any,
    guaranteed_component_market_value: Any = 0.0,
) -> Dict[str, Any]:
    """The full chase journey for ONE target card through ONE sealed product.

    There is deliberately no ``guaranteed_target_copies`` parameter. A product
    whose composition guarantees the target has ``p_prod == 1``: the journey is
    one product with no thresholds and no accumulation, which is a different
    model rather than a parameter of this one. Passing the keyword raises
    ``TypeError``, which is the intended behaviour.
    """
    groups = [g for g in (pack_groups or []) if isinstance(g, PackGroup)]
    if not groups:
        return _unavailable(REASON_NO_PACK_GROUPS)

    price = _positive(product_price)
    if price is None:
        return _unavailable(REASON_PRODUCT_PRICE_UNAVAILABLE)

    # ---- Combine the groups -------------------------------------------------
    # p_prod = 1 - PROD_g (1 - p_g)^{k_g}: the chance that at least one pack in
    # the whole product carries the target. Accumulated as a product of misses
    # rather than a sum, because the groups are independent, not exclusive.
    miss = 1.0
    pack_count = 0
    product_value = 0.0
    expected_copies_per_product = 0.0
    for group in groups:
        k = _positive(group.pack_count)
        p = _finite_float(group.target_probability_per_pack)
        copies = _non_negative(group.expected_target_copies_per_pack)
        ev = _finite_float(group.expected_pack_value)
        if k is None or p is None or copies is None or ev is None:
            return _unavailable(REASON_PROBABILITY_UNAVAILABLE)
        if not 0.0 < p <= 1.0:
            return _unavailable(REASON_PROBABILITY_UNAVAILABLE)
        k_int = int(k)
        miss *= (1.0 - p) ** k_int
        pack_count += k_int
        product_value += k_int * ev
        expected_copies_per_product += k_int * copies

    promo_value = _non_negative(guaranteed_component_market_value) or 0.0
    # The guaranteed component is certain, so it is added ONCE PER PRODUCT, not
    # once per pack. Adding it per pack would multiply one promo by 36.
    product_value += promo_value

    p_prod = 1.0 - miss
    if p_prod <= 0.0:
        return _unavailable(REASON_PROBABILITY_UNAVAILABLE, pack_count=pack_count)

    # ---- Journey expectations (Wald, exact under the model) ------------------
    expected_products = 1.0 / p_prod
    gross_spend = price * expected_products
    gross_pull_value = product_value * expected_products
    expected_target_copies = expected_copies_per_product * expected_products

    # ---- One retained copy --------------------------------------------------
    # Removed at the EV BASIS, the same basis gross_pull_value was built on.
    # Removing it at today's price would invent recovery equal to the drift.
    ev_basis = _positive(target_value_used_in_ev)
    if ev_basis is None:
        incidental_recovery = None
        rip_acquisition_cost = None
    else:
        incidental_recovery = gross_pull_value - ev_basis
        rip_acquisition_cost = gross_spend - incidental_recovery

    current_price = _positive(current_target_market_price)
    if rip_acquisition_cost is None or current_price is None:
        entertainment_premium = None
    else:
        entertainment_premium = rip_acquisition_cost - current_price

    if ev_basis is None or current_price is None:
        price_basis_delta = None
    else:
        # Current MINUS EV basis: positive means the card appreciated since the
        # run was priced, so buying the single today costs more than the EV
        # credited it. The opposite ordering reads every drift backwards.
        price_basis_delta = current_price - ev_basis

    # ---- Thresholds ---------------------------------------------------------
    thresholds: Dict[str, Any] = {}
    spend_distribution: Dict[str, Any] = {}
    products_by_threshold: Dict[float, Optional[int]] = {}
    for threshold in CHASE_THRESHOLDS:
        products = packs_for_cumulative_probability(p_prod, threshold)
        products_by_threshold[threshold] = products
        thresholds[_threshold_key("products", threshold)] = products
        thresholds[_threshold_key("packsPurchased", threshold)] = (
            None if products is None else products * pack_count
        )

    for key, threshold in (("medianChaseSpend", 0.50), ("p90ChaseSpend", 0.90), ("p95ChaseSpend", 0.95)):
        products = products_by_threshold.get(threshold)
        spend_distribution[key] = None if products is None else round(products * price, _PRECISION)

    def _round(value: Optional[float]) -> Optional[float]:
        return None if value is None else round(value, _PRECISION)

    return _product_block(
        pack_count=pack_count,
        probability=_round(p_prod),
        expected_products=_round(expected_products),
        gross_spend=_round(gross_spend),
        gross_pull_value=_round(gross_pull_value),
        expected_target_copies=_round(expected_target_copies),
        incidental_recovery=_round(incidental_recovery),
        rip_acquisition_cost=_round(rip_acquisition_cost),
        target_value_used_in_ev=ev_basis,
        current_target_market_price=current_price,
        price_basis_delta=_round(price_basis_delta),
        entertainment_premium=_round(entertainment_premium),
        thresholds=thresholds,
        spend_distribution=spend_distribution,
        available=True,
        reason=None,
    )
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `./backend/.venv/Scripts/python.exe -m pytest backend/tests/unit/domain/test_target_chase_economics.py -q`

Expected: PASS, all tests. If `test_impossible_pull_is_unavailable_never_infinite` fails for `bad_p=float("inf")`, check that `_finite_float` rejects infinity before the `0.0 < p <= 1.0` guard.

- [ ] **Step 5: Commit**

```bash
git add backend/domain/pokemon/target_chase_economics.py backend/tests/unit/domain/test_target_chase_economics.py
git commit -m "Add pure target-card chase economics module

Closed-form journey model: product hit probability, expected products, gross
spend, incidental recovery with exactly one retained target copy, rip
acquisition cost and entertainment premium. Separates the EV price basis from
today's single price. Thresholds at 50/75/90/95 for loose packs, products and
packs actually purchased.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

---

## Task 3: Monte Carlo validation of the closed forms

**Files:**
- Test: `backend/tests/unit/domain/test_target_chase_monte_carlo.py`

**Interfaces:**
- Consumes: `PackGroup`, `target_chase_for_product` from Task 2.
- Produces: nothing. This task adds no production code — it exists to prove the analytical model is what a simulation would have said.

- [ ] **Step 1: Write the simulation test**

Create `backend/tests/unit/domain/test_target_chase_monte_carlo.py`:

```python
"""Monte Carlo agreement check for the analytical chase model.

TEST-ONLY. There is no production Monte Carlo path and there must not be one:
these numbers are exact under the model assumptions, so simulating in
production would buy sampling noise and minutes of runtime per set.

What this proves: the closed forms in ``target_chase_economics`` are what a
literal open-until-hit simulation of the SAME model produces. It proves nothing
about real collation, which the model does not claim to capture.
"""

import numpy as np
import pytest

from backend.domain.pokemon.target_chase_economics import (
    PackGroup,
    target_chase_for_product,
)

TRIALS = 50_000
SEED = 20260816

# A moderate rate keeps the journey short enough to simulate 50k times quickly
# while still exercising the multi-product path.
P_PER_PACK = 0.02
PACKS_PER_PRODUCT = 6
PRODUCT_PRICE = 25.0
EV_PER_PACK = 3.5
TARGET_PRICE = 40.0


def _simulate():
    """Literal open-until-hit journeys under the module's own assumptions.

    The whole product is opened every time, including the successful one -
    matching ``successfulProductFullyOpened``. Products are drawn i.i.d.
    """
    rng = np.random.default_rng(SEED)
    products_used = np.empty(TRIALS, dtype=np.int64)
    value_pulled = np.empty(TRIALS, dtype=np.float64)
    target_copies = np.empty(TRIALS, dtype=np.int64)

    for trial in range(TRIALS):
        products = 0
        copies = 0
        while True:
            products += 1
            hits = int(rng.binomial(PACKS_PER_PRODUCT, P_PER_PACK))
            copies += hits
            if hits > 0:
                break
        products_used[trial] = products
        target_copies[trial] = copies
        # Every pack opened contributes its expected value; the variance of the
        # per-pack value is irrelevant to the expectations under test.
        value_pulled[trial] = products * PACKS_PER_PRODUCT * EV_PER_PACK

    return products_used, value_pulled, target_copies


@pytest.fixture(scope="module")
def simulated():
    return _simulate()


@pytest.fixture(scope="module")
def analytical():
    return target_chase_for_product(
        product_price=PRODUCT_PRICE,
        pack_groups=[
            PackGroup(
                pack_count=PACKS_PER_PRODUCT,
                target_probability_per_pack=P_PER_PACK,
                expected_target_copies_per_pack=P_PER_PACK,
                expected_pack_value=EV_PER_PACK,
            )
        ],
        target_value_used_in_ev=TARGET_PRICE,
        current_target_market_price=TARGET_PRICE,
    )


def test_expected_products_matches_simulation(simulated, analytical):
    products_used, _, _ = simulated
    assert analytical["expectedProductsToHit"] == pytest.approx(
        products_used.mean(), rel=0.02
    )


def test_gross_spend_matches_simulation(simulated, analytical):
    products_used, _, _ = simulated
    assert analytical["grossSpend"] == pytest.approx(
        (products_used * PRODUCT_PRICE).mean(), rel=0.02
    )


def test_gross_pull_value_matches_simulation(simulated, analytical):
    _, value_pulled, _ = simulated
    assert analytical["grossPullValue"] == pytest.approx(value_pulled.mean(), rel=0.02)


def test_expected_target_copies_matches_simulation(simulated, analytical):
    _, _, target_copies = simulated
    assert analytical["expectedTargetCopies"] == pytest.approx(
        target_copies.mean(), rel=0.02
    )


def test_incidental_recovery_matches_simulation(simulated, analytical):
    _, value_pulled, _ = simulated
    # One retained copy is removed at the EV basis, regardless of how many
    # copies the stopping product happened to contain.
    expected = value_pulled.mean() - TARGET_PRICE
    assert analytical["incidentalRecovery"] == pytest.approx(expected, rel=0.02)


def test_rip_acquisition_cost_matches_simulation(simulated, analytical):
    products_used, value_pulled, _ = simulated
    expected = (products_used * PRODUCT_PRICE).mean() - (value_pulled.mean() - TARGET_PRICE)
    assert analytical["ripAcquisitionCost"] == pytest.approx(expected, rel=0.02)


def test_probability_thresholds_match_empirical_hit_frequency(simulated, analytical):
    """``ceil(log(1-q)/log(1-p))`` really is the q-th cumulative threshold."""
    products_used, _, _ = simulated
    for threshold in (0.50, 0.75, 0.90, 0.95):
        n = analytical[f"productsFor{int(threshold * 100)}PercentChance"]
        empirical = float((products_used <= n).mean())
        assert empirical >= threshold - 0.02
        # The ceiling means the threshold is met, not wildly overshot.
        assert empirical <= threshold + 0.08
```

- [ ] **Step 2: Run the test**

Run: `./backend/.venv/Scripts/python.exe -m pytest backend/tests/unit/domain/test_target_chase_monte_carlo.py -q`

Expected: PASS. Runtime should be a few seconds. If it exceeds ~30s, lower `TRIALS` to 20000 and widen `rel` to 0.03 — the point is agreement, not precision.

If any assertion fails by more than the tolerance, **stop and investigate the analytical module** — that is the failure this task exists to catch. Do not widen the tolerance to make a real disagreement pass.

- [ ] **Step 3: Commit**

```bash
git add backend/tests/unit/domain/test_target_chase_monte_carlo.py
git commit -m "Validate closed-form chase economics against Monte Carlo

Test-only simulation of literal open-until-hit journeys under the same i.i.d.
assumptions, confirming the analytical expectations and cumulative thresholds.
No production simulation path is added.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

---

## Task 4: Non-critical chase-economics snapshot table

**Files:**
- Create: `backend/db/migrations/<NNN>_create_pokemon_set_chase_economics_snapshot.sql`

**Interfaces:**
- Consumes: nothing.
- Produces: table `public.pokemon_set_chase_economics_snapshot_latest` with columns `set_id UUID PRIMARY KEY`, `calculation_run_id UUID`, `payload_json JSONB NOT NULL`, `card_count INTEGER`, `as_of TIMESTAMPTZ`, `updated_at TIMESTAMPTZ`. Read in Task 7, written in Task 7.

- [ ] **Step 1: Determine the next free migration number**

Run: `ls backend/db/migrations/ | sort -V | tail -5`

Use the next integer after the highest, zero-padded to three digits. **Do not assume `067`** — the Stage 2 composition work running in parallel may have taken it. Record the number you chose; every later reference in this task means that number.

- [ ] **Step 2: Write the migration**

Create `backend/db/migrations/<NNN>_create_pokemon_set_chase_economics_snapshot.sql`:

```sql
-- Migration <NNN>: target-card chase economics snapshot.
--
-- WHAT THIS ADDS
-- --------------
-- One row per set holding the published chase-economics contract: for the top
-- N highest-priced pullable cards, what chasing each one costs through each
-- modeled sealed product. Built by the snapshot builder, read by a dedicated
-- service function.
--
-- WHY A SEPARATE TABLE RATHER THAN A KEY IN THE SET PAGE PAYLOAD
-- --------------------------------------------------------------
-- The contract is roughly 60-90 KB per set: 25 cards x up to 6 products x ~22
-- numeric fields. `pokemon_set_page_snapshot_latest` is on the critical set
-- page path and is fetched on every set view; adding a block that nothing on
-- that path reads would make every set page slower to serve a payload no
-- current consumer wants.
--
-- It is also NOT appended to `pokemon_set_cards_snapshot_latest`, even though
-- that table is the established home for heavy per-card data. That row is
-- already multi-MB and IS read by the live cards page, so appending an
-- unrelated block there would grow a request users actually make. A separate
-- row is delivered only when something asks for it.
--
-- WHY STORED AT ALL RATHER THAN COMPUTED ON READ
-- ----------------------------------------------
-- A future frontend must be able to retrieve the canonical contract without
-- recomputing it. Computing on demand would require two whole-run population
-- reads (`simulation_input_cards` and the Near Mint price view) per request,
-- and would let two readers disagree about the same set.
--
-- RUN IDENTITY
-- ------------
-- `calculation_run_id` is stored because the payload's probabilities and EV
-- basis belong to exactly one run. A reader comparing this against the set
-- page's `ripDecision` must be able to see whether they describe the same run.
--
-- PRIVACY POSTURE
-- ---------------
-- Backend-only, matching migration 065's posture: RLS enabled, no read policy,
-- no grants to `anon` or `authenticated`, full DML to `service_role`. Nothing
-- consumes this publicly yet, and publishing an internal shape before deciding
-- it is the shape to publish makes every future column public by default.
-- When a frontend needs it, that is a deliberate grant or a projected view,
-- and it is not made here.
--
-- MANUAL APPLICATION
-- ------------------
-- Follows this repository's manually-applied convention: idempotent, safe to
-- re-run, and NOT applied to production by any automated process.

BEGIN;

CREATE TABLE IF NOT EXISTS public.pokemon_set_chase_economics_snapshot_latest (
    set_id UUID PRIMARY KEY
        REFERENCES public.sets(id) ON DELETE CASCADE,

    -- The run the payload's pull probabilities and EV price basis belong to.
    -- Nullable: a set with no scored run publishes an explicitly empty payload
    -- rather than no row, so a reader can tell "built and empty" from "never
    -- built".
    calculation_run_id UUID
        REFERENCES public.calculation_runs(id) ON DELETE SET NULL,

    payload_json JSONB NOT NULL,

    -- Projection of the payload for cheap diagnostics. Never a second source
    -- of truth: the payload is authoritative.
    card_count INTEGER NOT NULL DEFAULT 0 CHECK (card_count >= 0),

    as_of TIMESTAMPTZ,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Freshness sweeps read by recency across all sets; the primary key does not
-- serve that access path.
CREATE INDEX IF NOT EXISTS pokemon_set_chase_economics_snapshot_latest_updated_at_idx
    ON public.pokemon_set_chase_economics_snapshot_latest (updated_at DESC);

ALTER TABLE public.pokemon_set_chase_economics_snapshot_latest
    ENABLE ROW LEVEL SECURITY;

-- Stated explicitly so re-running leaves the intended state even if something
-- created a policy out of band.
DROP POLICY IF EXISTS pokemon_set_chase_economics_snapshot_latest_read_policy
    ON public.pokemon_set_chase_economics_snapshot_latest;

REVOKE ALL ON public.pokemon_set_chase_economics_snapshot_latest FROM anon;
REVOKE ALL ON public.pokemon_set_chase_economics_snapshot_latest FROM authenticated;
REVOKE ALL ON public.pokemon_set_chase_economics_snapshot_latest FROM PUBLIC;

GRANT SELECT, INSERT, UPDATE, DELETE
    ON public.pokemon_set_chase_economics_snapshot_latest TO service_role;

COMMIT;
```

- [ ] **Step 3: Verify the SQL parses**

There is no automated migration runner in this repository — migrations are applied manually. Verify by inspection that:
- every statement is idempotent (`IF NOT EXISTS`, `DROP ... IF EXISTS`),
- the file opens with `BEGIN;` and closes with `COMMIT;`,
- no `GRANT` to `anon` or `authenticated` exists anywhere in the file.

**Do not apply this migration to production.** It is committed as a file only.

- [ ] **Step 4: Commit**

```bash
git add backend/db/migrations/
git commit -m "Add chase-economics snapshot table migration

Backend-only, RLS-enabled, one row per set. Kept out of both the critical set
page payload and the already-large cards snapshot so the contract costs nothing
until something asks for it.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

---

## Task 5: Chase economics service

**Files:**
- Create: `backend/db/services/chase_economics_service.py`
- Test: `backend/tests/unit/db/services/test_chase_economics_service.py`

**Interfaces:**
- Consumes: `PackGroup`, `target_chase_for_product`, `loose_pack_odds_contract`, `model_assumptions_contract` (Task 2).
- Produces:
  - `DEFAULT_PUBLISHED_CARD_LIMIT: int = 25`
  - `CHASE_ECONOMICS_CONTRACT_VERSION: str = "target-chase-economics-v1"`
  - `select_chase_cards(price_rows, pull_denominators, price_used_by_variant_id, *, limit) -> List[Dict]`
  - `pack_groups_for_product(product_row, *, target_probability_per_pack) -> List[PackGroup]`
  - `build_chase_economics_contract(*, cards, product_rows, run_id, limit=DEFAULT_PUBLISHED_CARD_LIMIT) -> Dict`

  All three are **pure functions over already-loaded rows** — the service does no database work of its own. Task 7 supplies the rows.

- [ ] **Step 1: Write the failing tests**

Create `backend/tests/unit/db/services/test_chase_economics_service.py`:

```python
"""Selection and assembly tests for the chase-economics publication contract.

The top-25 cap is a PUBLICATION policy. Every test that touches it also checks
that the underlying calculator is not restricted by it.
"""

import json

import pytest

from backend.db.services.chase_economics_service import (
    DEFAULT_PUBLISHED_CARD_LIMIT,
    build_chase_economics_contract,
    pack_groups_for_product,
    select_chase_cards,
)
from backend.domain.pokemon.target_chase_economics import (
    PackGroup,
    target_chase_for_product,
)


def _price_row(variant_id, price, name=None):
    return {
        "card_id": f"card-{variant_id}",
        "card_variant_id": variant_id,
        "card_name": name or f"Card {variant_id}",
        "rarity_bucket": "ultra",
        "current_near_mint_price": price,
    }


def _stage1_product(pack_count=36, price=149.99, ev=107.89):
    return {
        "sealed_product_id": "prod-box",
        "product_name": "Booster Box",
        "product_family": "booster_box",
        "pack_count": pack_count,
        "product_market_cost": price,
        "expected_value": ev,
        "random_pack_count": None,
        "guaranteed_component_market_value": None,
    }


def _stage2_product():
    return {
        "sealed_product_id": "prod-etb",
        "product_name": "Elite Trainer Box",
        "product_family": "elite_trainer_box",
        "pack_count": 9,
        "product_market_cost": 49.99,
        "expected_value": 32.0,
        "random_pack_count": 9,
        "guaranteed_component_market_value": 5.0,
    }


# ---------------------------------------------------------------------------
# Card selection
# ---------------------------------------------------------------------------

def test_cards_are_selected_by_descending_market_price():
    rows = [_price_row("a", 10.0), _price_row("b", 300.0), _price_row("c", 55.0)]
    denominators = {"a": 100.0, "b": 500.0, "c": 250.0}
    used = {"a": 9.0, "b": 280.0, "c": 50.0}
    selected = select_chase_cards(rows, denominators, used, limit=10)
    assert [c["cardVariantId"] for c in selected] == ["b", "c", "a"]


def test_cards_without_a_modeled_pull_rate_are_excluded():
    # However expensive, a card the model cannot produce is not a chase this
    # contract can honestly describe.
    rows = [_price_row("a", 999.0), _price_row("b", 10.0)]
    selected = select_chase_cards(rows, {"b": 100.0}, {"b": 9.0}, limit=10)
    assert [c["cardVariantId"] for c in selected] == ["b"]


def test_cards_without_a_price_are_excluded():
    rows = [_price_row("a", None), _price_row("b", 10.0)]
    selected = select_chase_cards(rows, {"a": 100.0, "b": 100.0}, {"a": 1.0, "b": 9.0}, limit=10)
    assert [c["cardVariantId"] for c in selected] == ["b"]


def test_selection_is_capped_at_the_limit():
    rows = [_price_row(str(i), float(100 - i)) for i in range(50)]
    denominators = {str(i): 100.0 for i in range(50)}
    used = {str(i): 90.0 for i in range(50)}
    selected = select_chase_cards(rows, denominators, used, limit=25)
    assert len(selected) == 25
    assert selected[0]["cardVariantId"] == "0"


def test_selection_ties_break_deterministically():
    rows = [_price_row("b", 50.0), _price_row("a", 50.0)]
    denominators = {"a": 100.0, "b": 100.0}
    used = {"a": 45.0, "b": 45.0}
    first = select_chase_cards(rows, denominators, used, limit=10)
    second = select_chase_cards(list(reversed(rows)), denominators, used, limit=10)
    assert [c["cardVariantId"] for c in first] == [c["cardVariantId"] for c in second]


def test_selected_card_carries_both_price_bases_and_probability():
    rows = [_price_row("a", 310.0)]
    selected = select_chase_cards(rows, {"a": 476.19}, {"a": 280.0}, limit=10)[0]
    assert selected["currentTargetMarketPrice"] == 310.0
    assert selected["targetValueUsedInEV"] == 280.0
    assert selected["modeledProbability"] == pytest.approx(1.0 / 476.19)


def test_missing_price_used_leaves_the_ev_basis_none_rather_than_borrowing_current():
    # Borrowing today's price as the EV basis would silently zero the drift.
    rows = [_price_row("a", 310.0)]
    selected = select_chase_cards(rows, {"a": 476.19}, {}, limit=10)[0]
    assert selected["targetValueUsedInEV"] is None
    assert selected["currentTargetMarketPrice"] == 310.0


# ---------------------------------------------------------------------------
# Pack group construction
# ---------------------------------------------------------------------------

def test_stage1_pack_group_uses_expected_value_over_pack_count():
    groups = pack_groups_for_product(_stage1_product(), target_probability_per_pack=0.002)
    assert len(groups) == 1
    assert groups[0].pack_count == 36
    assert groups[0].expected_pack_value == pytest.approx(107.89 / 36)


def test_stage2_pack_group_excludes_the_guaranteed_component():
    # 32.0 total minus a 5.0 promo, over 9 random packs.
    groups = pack_groups_for_product(_stage2_product(), target_probability_per_pack=0.002)
    assert groups[0].pack_count == 9
    assert groups[0].expected_pack_value == pytest.approx((32.0 - 5.0) / 9)


def test_pack_group_copies_default_to_the_probability():
    # Today's Pokemon model: at most one copy of a given card per pack.
    groups = pack_groups_for_product(_stage1_product(), target_probability_per_pack=0.002)
    assert groups[0].expected_target_copies_per_pack == pytest.approx(0.002)


def test_unusable_product_row_yields_no_groups():
    broken = _stage1_product(ev=None)
    assert pack_groups_for_product(broken, target_probability_per_pack=0.002) == []


# ---------------------------------------------------------------------------
# Contract assembly
# ---------------------------------------------------------------------------

def _contract(limit=DEFAULT_PUBLISHED_CARD_LIMIT):
    cards = select_chase_cards(
        [_price_row("a", 310.0), _price_row("b", 40.0)],
        {"a": 476.19, "b": 20.0},
        {"a": 280.0, "b": 38.0},
        limit=limit,
    )
    return build_chase_economics_contract(
        cards=cards,
        product_rows=[_stage1_product(), _stage2_product()],
        run_id="run-1",
        limit=limit,
    )


def test_contract_publishes_model_assumptions():
    contract = _contract()
    assert contract["modelAssumptions"]["successfulProductFullyOpened"] is True
    assert contract["modelAssumptions"]["retainedTargetCopies"] == 1
    assert contract["recoveryModel"] == "gross_market_value"


def test_contract_carries_run_identity_and_selection_policy():
    contract = _contract()
    assert contract["sourceCalculationRunId"] == "run-1"
    assert contract["selectionPolicy"] == "top_market_price_pullable"
    assert contract["publishedCardLimit"] == DEFAULT_PUBLISHED_CARD_LIMIT


def test_each_card_carries_loose_pack_thresholds_and_a_product_row_per_sku():
    contract = _contract()
    card = contract["cards"][0]
    assert card["packsFor50PercentChance"] is not None
    assert card["packsFor95PercentChance"] is not None
    assert {p["sealedProductId"] for p in card["products"]} == {"prod-box", "prod-etb"}


def test_price_basis_delta_is_published_per_card():
    contract = _contract()
    card = next(c for c in contract["cards"] if c["cardVariantId"] == "a")
    assert card["targetPriceBasisDelta"] == pytest.approx(30.0)


def test_provenance_nulls_are_not_defaulted_to_read_time():
    cards = select_chase_cards([_price_row("a", 310.0)], {"a": 476.19}, {"a": 280.0}, limit=5)
    contract = build_chase_economics_contract(
        cards=cards, product_rows=[_stage1_product()], run_id="run-1"
    )
    card = contract["cards"][0]
    # No timestamp was supplied by the rows, so none may be asserted.
    assert card["evPriceBasisAsOf"] is None
    assert card["currentPriceAsOf"] is None
    assert card["evPriceBasisRunId"] == "run-1"


def test_eligible_card_count_reports_the_full_population_not_the_cap():
    rows = [_price_row(str(i), float(100 - i)) for i in range(40)]
    denominators = {str(i): 100.0 for i in range(40)}
    used = {str(i): 90.0 for i in range(40)}
    cards = select_chase_cards(rows, denominators, used, limit=5)
    contract = build_chase_economics_contract(
        cards=cards, product_rows=[_stage1_product()], run_id="run-1",
        limit=5, eligible_card_count=len(rows),
    )
    assert contract["publishedCardLimit"] == 5
    assert len(contract["cards"]) == 5
    assert contract["eligibleCardCount"] == 40


def test_the_publication_cap_does_not_restrict_the_calculator():
    # A card ranked far outside the published 25 computes identically through
    # the pure function. The cap is policy, not a property of the math.
    block = target_chase_for_product(
        product_price=149.99,
        pack_groups=pack_groups_for_product(
            _stage1_product(), target_probability_per_pack=0.0001
        ),
        target_value_used_in_ev=1.5,
        current_target_market_price=1.75,
    )
    assert block["available"] is True
    assert block["entertainmentPremium"] is not None


def test_contract_is_json_safe():
    json.dumps(_contract(), allow_nan=False)


def test_empty_population_publishes_an_explicit_empty_contract():
    contract = build_chase_economics_contract(cards=[], product_rows=[], run_id=None)
    assert contract["cards"] == []
    assert contract["eligibleCardCount"] == 0
    assert contract["sourceCalculationRunId"] is None
    json.dumps(contract, allow_nan=False)
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `./backend/.venv/Scripts/python.exe -m pytest backend/tests/unit/db/services/test_chase_economics_service.py -q`

Expected: collection error — `ModuleNotFoundError: No module named 'backend.db.services.chase_economics_service'`.

- [ ] **Step 3: Write the implementation**

Create `backend/db/services/chase_economics_service.py`:

```python
"""Chase-economics selection and publication policy.

WHERE THIS SITS
---------------
    already-loaded run populations
      -> select_chase_cards      (which cards are worth publishing)
      -> pack_groups_for_product (how each SKU decomposes for the chase)
      -> target_chase_for_product (the pure math, unchanged)
      -> build_chase_economics_contract (the published shape)

Every function here is PURE over rows the caller already holds. The service
issues no queries of its own: the two whole-run populations it needs are the
same two ``rip_decision_service`` already reads for Top Chase, and loading them
twice would double a set-sized read to produce identical rows.

TOP 25 IS A PUBLICATION POLICY
------------------------------
``DEFAULT_PUBLISHED_CARD_LIMIT`` caps what gets STORED, because 25 cards covers
every card anyone would realistically chase while keeping the payload bounded.
It does not cap what can be COMPUTED: ``target_chase_for_product`` accepts any
card, and a future on-demand endpoint for an arbitrary card calls exactly the
same function with the same arguments. ``eligibleCardCount`` is published beside
the capped list so a reader can see how much was left out.

WHAT THIS DELIBERATELY IS NOT
-----------------------------
* NOT a ranking of products. Rows are emitted per SKU in the order given; the
  repository's comparison scope is ``within_product_family_only`` and nothing
  here declares a best way to chase a card.
* NOT a recommendation. No field labels a chase wise or foolish.
"""

from __future__ import annotations

import math
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence

from backend.domain.pokemon.target_chase_economics import (
    TARGET_CHASE_CONTRACT_VERSION,
    PackGroup,
    loose_pack_odds_contract,
    model_assumptions_contract,
    target_chase_for_product,
)

CHASE_ECONOMICS_CONTRACT_VERSION = TARGET_CHASE_CONTRACT_VERSION

#: How many cards are STORED per set. Policy, not a limit on the calculator.
DEFAULT_PUBLISHED_CARD_LIMIT = 25

#: Published so a reader knows which question the card list answers.
SELECTION_POLICY = "top_market_price_pullable"

RECOVERY_MODEL_GROSS_MARKET_VALUE = "gross_market_value"


def _optional_float(value: Any) -> Optional[float]:
    if value is None or isinstance(value, bool):
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def _positive(value: Any) -> Optional[float]:
    number = _optional_float(value)
    if number is None or number <= 0.0:
        return None
    return number


def _optional_str(value: Any) -> Optional[str]:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def select_chase_cards(
    price_rows: Iterable[Mapping[str, Any]],
    pull_denominators_by_variant_id: Mapping[str, Any],
    price_used_by_variant_id: Mapping[str, Any],
    *,
    limit: int = DEFAULT_PUBLISHED_CARD_LIMIT,
) -> List[Dict[str, Any]]:
    """The N priciest cards the model can actually produce.

    Two filters, in this order: the card must have a current Near Mint price,
    and it must have a positive modeled pull rate in the SAME run. A card the
    packs cannot produce is not a chase this contract can describe, however
    expensive it is - and a set's most expensive cards frequently ARE such
    cards, which is why the modeled population is the gate rather than an
    afterthought.

    ``price_used_by_variant_id`` may be missing an entry. That leaves
    ``targetValueUsedInEV`` as ``None`` rather than borrowing today's price,
    which would silently report zero drift between two bases we never compared.
    """
    eligible: List[Dict[str, Any]] = []
    for row in price_rows or []:
        if not isinstance(row, Mapping):
            continue
        variant_id = _optional_str(row.get("card_variant_id"))
        if variant_id is None:
            continue
        price = _positive(row.get("current_near_mint_price"))
        if price is None:
            continue
        denominator = _positive(pull_denominators_by_variant_id.get(variant_id))
        if denominator is None:
            continue

        eligible.append(
            {
                "cardId": _optional_str(row.get("card_id")),
                "cardVariantId": variant_id,
                "cardName": _optional_str(row.get("card_name")),
                "rarity": _optional_str(row.get("rarity_bucket")),
                "currentTargetMarketPrice": price,
                "currentPriceAsOf": _optional_str(row.get("price_as_of")),
                "targetValueUsedInEV": _positive(
                    price_used_by_variant_id.get(variant_id)
                ),
                "evPriceBasisAsOf": _optional_str(row.get("price_used_as_of")),
                "modeledProbability": 1.0 / denominator,
            }
        )

    # Price descending, then variant id ascending. The id tiebreak makes the
    # same run publish the same list regardless of row arrival order.
    eligible.sort(key=lambda c: (-c["currentTargetMarketPrice"], c["cardVariantId"]))
    return eligible[: max(0, int(limit))]


def pack_groups_for_product(
    product_row: Mapping[str, Any], *, target_probability_per_pack: Any
) -> List[PackGroup]:
    """How one scored SKU decomposes into random-pack groups for the chase.

    Every product modeled today produces exactly ONE group; the list shape
    exists so a future heterogeneous product needs no contract change.

    STAGE 2 EXCLUDES THE GUARANTEED COMPONENT from the per-pack value. The
    stored ``expected_value`` already contains the promo at its exact market
    price, so ``expected_value / pack_count`` would smear a certain component
    across random packs and overstate what each pack contributes to a chase.
    The promo is handed to ``target_chase_for_product`` separately, where it is
    added once per product opened.
    """
    p = _positive(target_probability_per_pack)
    if p is None:
        return []

    expected_value = _optional_float(product_row.get("expected_value"))
    if expected_value is None:
        return []

    promo_value = _positive(product_row.get("guaranteed_component_market_value"))
    random_pack_count = _positive(product_row.get("random_pack_count"))

    if promo_value is not None and random_pack_count is not None:
        pack_count = int(random_pack_count)
        random_value = expected_value - promo_value
    else:
        total_pack_count = _positive(product_row.get("pack_count"))
        if total_pack_count is None:
            return []
        pack_count = int(total_pack_count)
        random_value = expected_value

    if pack_count <= 0:
        return []

    return [
        PackGroup(
            pack_count=pack_count,
            target_probability_per_pack=p,
            # Today's Pokemon model puts a given card in at most one slot per
            # pack, so copies equal probability. The pure calculator does not
            # assume this; the equality is asserted HERE, where the model that
            # justifies it lives.
            expected_target_copies_per_pack=p,
            expected_pack_value=random_value / pack_count,
        )
    ]


def _card_block(
    card: Mapping[str, Any],
    product_rows: Sequence[Mapping[str, Any]],
    *,
    run_id: Optional[str],
) -> Dict[str, Any]:
    probability = _positive(card.get("modeledProbability"))
    ev_basis = _positive(card.get("targetValueUsedInEV"))
    current_price = _positive(card.get("currentTargetMarketPrice"))

    products: List[Dict[str, Any]] = []
    for row in product_rows:
        groups = pack_groups_for_product(row, target_probability_per_pack=probability)
        block = target_chase_for_product(
            product_price=row.get("product_market_cost"),
            pack_groups=groups,
            target_value_used_in_ev=ev_basis,
            current_target_market_price=current_price,
            guaranteed_component_market_value=(
                _positive(row.get("guaranteed_component_market_value")) or 0.0
            ),
        )
        products.append(
            {
                "sealedProductId": _optional_str(row.get("sealed_product_id")),
                "productName": _optional_str(row.get("product_name")),
                "productFamily": _optional_str(row.get("product_family")),
                "productPrice": _positive(row.get("product_market_cost")),
                **block,
            }
        )

    if ev_basis is None or current_price is None:
        delta = None
    else:
        delta = round(current_price - ev_basis, 12)

    return {
        "cardId": card.get("cardId"),
        "cardVariantId": card.get("cardVariantId"),
        "cardName": card.get("cardName"),
        "rarity": card.get("rarity"),
        "currentTargetMarketPrice": current_price,
        "currentPriceAsOf": card.get("currentPriceAsOf"),
        "currentPriceSource": "simulation_input_cards_with_near_mint_price",
        "targetValueUsedInEV": ev_basis,
        "evPriceBasisRunId": run_id,
        "evPriceBasisAsOf": card.get("evPriceBasisAsOf"),
        # Current MINUS EV basis. Positive means the card appreciated since the
        # run was priced.
        "targetPriceBasisDelta": delta,
        **loose_pack_odds_contract(target_probability_per_pack=probability),
        "products": products,
    }


def build_chase_economics_contract(
    *,
    cards: Sequence[Mapping[str, Any]],
    product_rows: Sequence[Mapping[str, Any]],
    run_id: Any,
    limit: int = DEFAULT_PUBLISHED_CARD_LIMIT,
    eligible_card_count: Optional[int] = None,
) -> Dict[str, Any]:
    """The published chase-economics contract for ONE set.

    ``eligible_card_count`` is the size of the population BEFORE the cap, so a
    reader can see that 25 of 187 chaseable cards were published rather than
    inferring that the set has 25.
    """
    resolved_run_id = _optional_str(run_id)
    card_list = [c for c in (cards or []) if isinstance(c, Mapping)]
    rows = [r for r in (product_rows or []) if isinstance(r, Mapping)]

    return {
        "contractVersion": CHASE_ECONOMICS_CONTRACT_VERSION,
        "recoveryModel": RECOVERY_MODEL_GROSS_MARKET_VALUE,
        "sourceCalculationRunId": resolved_run_id,
        "selectionPolicy": SELECTION_POLICY,
        "publishedCardLimit": int(limit),
        "eligibleCardCount": (
            len(card_list) if eligible_card_count is None else int(eligible_card_count)
        ),
        "modelAssumptions": model_assumptions_contract(),
        "cards": [
            _card_block(card, rows, run_id=resolved_run_id) for card in card_list
        ],
    }
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `./backend/.venv/Scripts/python.exe -m pytest backend/tests/unit/db/services/test_chase_economics_service.py -q`

Expected: PASS, all tests.

- [ ] **Step 5: Run the full domain suite to confirm nothing regressed**

Run: `./backend/.venv/Scripts/python.exe -m pytest backend/tests/unit/domain/ -q`

Expected: PASS, including the pre-existing `test_rip_decision_metrics.py` (35 tests).

- [ ] **Step 6: Commit**

```bash
git add backend/db/services/chase_economics_service.py backend/tests/unit/db/services/test_chase_economics_service.py
git commit -m "Add chase economics selection and publication service

Pure over already-loaded run populations: selects the priciest pullable cards,
decomposes each SKU into pack groups (Stage 2 excluding the guaranteed
component), and assembles the published contract. The top-25 cap is publication
policy only and does not restrict the calculator.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

---

## Task 6: Wire Entertainment Cost into the RIP decision contract

**Files:**
- Modify: `backend/db/services/rip_decision_service.py`
- Test: `backend/tests/unit/db/services/test_rip_decision_service.py` (existing — append; do not rewrite)

**Interfaces:**
- Consumes: `entertainment_cost_contract`, `unsupported_entertainment_cost` (Task 1).
- Produces:
  - `build_unsupported_products_contract(snapshot_payload, scored_product_ids) -> Dict`
  - `_product_decision_row` gains an `"entertainmentCost"` key.
  - `build_rip_decision_contract` gains an `"unsupportedProducts"` key and accepts a new optional `sealed_snapshot_fn` keyword for injection in tests.

**This file has uncommitted changes from the in-flight RIP-decision-layer work.** Read it before editing. Add only; do not reformat, reorder or refactor anything you did not add.

- [ ] **Step 1: Read the current state of the file**

Run: `git diff backend/db/services/rip_decision_service.py`

Confirm you understand what the in-flight work changed, so your additions do not collide with it.

- [ ] **Step 2: Write the failing tests**

Append to `backend/tests/unit/db/services/test_rip_decision_service.py`:

```python
# ---------------------------------------------------------------------------
# Entertainment Cost (additive to the existing product decision contract)
# ---------------------------------------------------------------------------

import json as _json

from backend.db.services.rip_decision_service import (
    build_sealed_product_decision_contract,
    build_unsupported_products_contract,
)


def _scored_row(**overrides):
    row = {
        "calculation_run_id": "run-1",
        "sealed_product_id": "prod-box",
        "product_name": "Booster Box",
        "product_family": "booster_box",
        "pack_count": 36,
        "product_market_cost": 149.99,
        "expected_value": 107.89,
        "median_value": 95.0,
        "chance_to_recover_cost": 0.21,
    }
    row.update(overrides)
    return row


def test_each_product_row_carries_an_entertainment_cost_block():
    contract = build_sealed_product_decision_contract([_scored_row()])
    block = contract["products"][0]["entertainmentCost"]
    assert block["entertainmentCost"] == pytest.approx(42.10)
    assert block["entertainmentCostPerPackEquivalent"] == pytest.approx(42.10 / 36)
    assert block["recoveryModel"] == "gross_market_value"


def test_entertainment_cost_marks_stage2_products_as_including_the_promo():
    contract = build_sealed_product_decision_contract(
        [_scored_row(guaranteed_component_market_value=5.0, random_pack_count=9)]
    )
    assert contract["products"][0]["entertainmentCost"]["guaranteedComponentIncluded"] is True


def test_entertainment_cost_is_unavailable_without_a_price():
    contract = build_sealed_product_decision_contract(
        [_scored_row(product_market_cost=None)]
    )
    block = contract["products"][0]["entertainmentCost"]
    assert block["available"] is False
    assert block["entertainmentCost"] is None


def test_negative_entertainment_cost_reaches_the_contract_unclamped():
    contract = build_sealed_product_decision_contract(
        [_scored_row(product_market_cost=100.0, expected_value=130.0)]
    )
    assert contract["products"][0]["entertainmentCost"]["entertainmentCost"] == pytest.approx(-30.0)


# ---------------------------------------------------------------------------
# Unsupported products
# ---------------------------------------------------------------------------

_SNAPSHOT = {
    "products": [
        {"sealedProductId": "prod-box", "name": "Booster Box",
         "productFamily": "booster_box", "currentPrice": 149.99},
        {"sealedProductId": "prod-blister", "name": "3-Pack Blister",
         "productFamily": "three_pack_blister", "currentPrice": 14.99},
        {"sealedProductId": "prod-halfbox", "name": "Half Booster Box",
         "productFamily": "booster_box", "currentPrice": 79.99},
    ]
}


def test_unmodeled_families_are_published_explicitly_not_omitted():
    contract = build_unsupported_products_contract(_SNAPSHOT, {"prod-box"})
    ids = {p["sealedProductId"] for p in contract["products"]}
    assert "prod-blister" in ids
    assert "prod-box" not in ids


def test_unsupported_products_carry_a_machine_readable_reason():
    contract = build_unsupported_products_contract(_SNAPSHOT, {"prod-box"})
    reasons = {p["sealedProductId"]: p["entertainmentCost"]["reason"] for p in contract["products"]}
    assert reasons["prod-blister"] == "unsupported_product_family"
    # Right family, wrong pack count: the more specific existing reason wins.
    assert reasons["prod-halfbox"] == "non_default_pack_count_variant"


def test_unsupported_products_keep_their_market_price():
    contract = build_unsupported_products_contract(_SNAPSHOT, {"prod-box"})
    blister = next(p for p in contract["products"] if p["sealedProductId"] == "prod-blister")
    assert blister["marketPrice"] == 14.99
    assert blister["entertainmentCost"]["entertainmentCost"] is None


def test_unsupported_contract_is_empty_without_a_snapshot():
    contract = build_unsupported_products_contract(None, set())
    assert contract["products"] == []
    assert contract["productCount"] == 0


def test_decision_contract_stays_json_safe_with_the_new_blocks():
    contract = build_sealed_product_decision_contract([_scored_row()])
    _json.dumps(contract, allow_nan=False)
    _json.dumps(build_unsupported_products_contract(_SNAPSHOT, {"prod-box"}), allow_nan=False)


def test_the_large_chase_table_is_not_in_the_decision_contract():
    # Chase economics lives in its own snapshot precisely so the critical set
    # page payload does not grow by 60-90 KB per set.
    contract = build_sealed_product_decision_contract([_scored_row()])
    assert "chaseEconomics" not in contract
    assert "chaseEconomics" not in contract["products"][0]
```

- [ ] **Step 3: Run the tests to verify they fail**

Run: `./backend/.venv/Scripts/python.exe -m pytest backend/tests/unit/db/services/test_rip_decision_service.py -q`

Expected: `ImportError: cannot import name 'build_unsupported_products_contract'`.

- [ ] **Step 4: Add the imports**

In `backend/db/services/rip_decision_service.py`, add to the existing import block (alongside the `rip_decision_metrics` import):

```python
from backend.domain.pokemon.entertainment_cost import (
    entertainment_cost_contract,
    unsupported_entertainment_cost,
)
from backend.domain.pokemon.sealed_product_composition import (
    is_stage1_supported_family,
    stage1_composition_disqualifier,
)
from backend.domain.pokemon.sealed_product_classifier import classify_sealed_product
from backend.domain.pokemon.sealed_product_stage2_composition import (
    REASON_NO_VERIFIED_COMPOSITION,
    is_stage2_family,
)
```

- [ ] **Step 5: Add the entertainment-cost block to the product row**

In `_product_decision_row`, immediately before the `return` statement, add:

```python
    # Entertainment Cost is derived here rather than persisted, for the same
    # reason the ratio metrics above are: it is arithmetic on two authoritative
    # columns, and deriving it at publication time makes drift impossible.
    entertainment = entertainment_cost_contract(
        purchase_price=row.get("product_market_cost"),
        expected_value=row.get("expected_value"),
        pack_count=row.get("pack_count"),
        # A Stage 2 row's stored expected_value already contains the promo at
        # its exact market value; the flag tells a reader that, it does not
        # change the arithmetic.
        guaranteed_component_included=row.get("guaranteed_component_market_value") is not None,
    )
```

and add this key to the returned dict, immediately after `"availability": _product_availability(row, metrics),`:

```python
        "entertainmentCost": entertainment,
```

- [ ] **Step 6: Add the unsupported-products contract**

Append to `backend/db/services/rip_decision_service.py`, after `build_sealed_product_decision_contract`:

```python
# ---------------------------------------------------------------------------
# Unsupported products
# ---------------------------------------------------------------------------

#: Local aliases for the two composition-module reason strings used below, so
#: this module never spells a reason a second way.
REASON_UNSUPPORTED_FAMILY = "unsupported_product_family"
REASON_INVALID_PRICE_FALLBACK = "invalid_or_missing_market_price"


def _unsupported_reason(product: Mapping[str, Any], family: str) -> str:
    """Why this SKU has no modeled opening value.

    The reasons come from the EXISTING closed vocabulary in the composition
    modules; none is invented here. The order matters: a "Half Booster Box" is
    a supported family with an unsupported pack count, and reporting it as
    `unsupported_product_family` would send someone looking for a family we
    already model.
    """
    if is_stage1_supported_family(family):
        disqualifier = stage1_composition_disqualifier(
            product.get("name"), product_family=family
        )
        if disqualifier is not None:
            return disqualifier
        return REASON_INVALID_PRICE_FALLBACK
    if is_stage2_family(family):
        # Stage 2 eligibility is a verified composition row keyed on
        # sealed_product_id. Absent that, this SKU was never scorable - and
        # finding the missing composition is deliberately NOT this layer's job.
        return REASON_NO_VERIFIED_COMPOSITION
    return REASON_UNSUPPORTED_FAMILY


def build_unsupported_products_contract(
    snapshot_payload: Optional[Mapping[str, Any]],
    scored_product_ids: Any,
) -> Dict[str, Any]:
    """Every sealed SKU in the market snapshot that carries NO modeled value.

    Published rather than omitted. A blister that simply vanishes from the
    table is indistinguishable from a blister that does not exist, and a reader
    comparing "what are my options for this set" needs to see that the format
    exists and why we cannot price its opening.

    This function does NOT research compositions, classify promos or widen
    coverage. It reports the current state of the modeled/unmodeled boundary.
    """
    scored = {str(pid) for pid in (scored_product_ids or set())}
    products = (snapshot_payload or {}).get("products") or []

    rows: List[Dict[str, Any]] = []
    for product in products:
        if not isinstance(product, Mapping):
            continue
        product_id = _optional_str(product.get("sealedProductId"))
        if product_id is None or product_id in scored:
            continue

        family = _optional_str(product.get("productFamily")) or str(
            classify_sealed_product(product.get("name")).get("productFamily")
        )
        price = _optional_float(product.get("currentPrice"))
        if price is not None and price <= 0.0:
            price = None

        rows.append(
            {
                "sealedProductId": product_id,
                "productName": _optional_str(product.get("name")),
                "productFamily": family,
                "marketPrice": price,
                "entertainmentCost": unsupported_entertainment_cost(
                    _unsupported_reason(product, family), purchase_price=price
                ),
            }
        )

    return {
        "contractVersion": RIP_DECISION_CONTRACT_VERSION,
        "productCount": len(rows),
        "products": rows,
    }
```

- [ ] **Step 7: Wire it into the combined contract**

In `build_rip_decision_contract`, add a `sealed_snapshot_fn=None` keyword parameter. In the no-run branch add `"unsupportedProducts": build_unsupported_products_contract(None, set()),`. In the main branch, replace the body with:

```python
    product_rows = _load_current_run_product_rows(
        run_id=resolved_run_id, set_id=set_id, client=client
    )
    scored_ids = {
        _optional_str(row.get("sealed_product_id"))
        for row in product_rows
        if _optional_str(row.get("sealed_product_id")) is not None
    }

    if sealed_snapshot_fn is None:
        from backend.db.services.pokemon_set_sealed_market_snapshot_service import (
            read_snapshot,
        )

        def sealed_snapshot_fn(target_set_id):  # type: ignore[misc]
            return read_snapshot(client, target_set_id)

    try:
        snapshot = sealed_snapshot_fn(str(set_id)) if set_id is not None else None
    except Exception as exc:
        if is_transient_data_service_error(exc):
            raise
        # A missing snapshot costs the unsupported list, not the whole contract:
        # the scored products are already loaded and are the primary payload.
        logger.warning("unsupported product read failed set_id=%s", set_id, exc_info=True)
        snapshot = None

    return {
        "contractVersion": RIP_DECISION_CONTRACT_VERSION,
        "sourceCalculationRunId": resolved_run_id,
        "currentRunAvailable": True,
        "sealedProducts": build_sealed_product_decision_contract(
            product_rows, run_status=RUN_STATUS_CURRENT
        ),
        "unsupportedProducts": build_unsupported_products_contract(snapshot, scored_ids),
        "topChase": build_top_chase_contract(run_id=resolved_run_id, client=client),
        **sealed_product_comparison_scope_contract(),
    }
```

- [ ] **Step 8: Run the tests to verify they pass**

Run: `./backend/.venv/Scripts/python.exe -m pytest backend/tests/unit/db/services/test_rip_decision_service.py -q`

Expected: PASS — both the new tests and every pre-existing test in the file. If a pre-existing test fails, your change was not additive; revert and narrow it.

- [ ] **Step 9: Run the broader regression suite**

Run: `./backend/.venv/Scripts/python.exe -m pytest backend/tests/unit/db/services/ backend/tests/unit/domain/ backend/tests/unit/scripts/test_rip_decision_snapshot_merge.py -q`

Expected: PASS. In particular `test_rip_decision_snapshot_merge.py` must be unchanged and green — the `ripDecision` merge path is the in-flight work's surface.

- [ ] **Step 10: Commit**

```bash
git add backend/db/services/rip_decision_service.py backend/tests/unit/db/services/test_rip_decision_service.py
git commit -m "Publish Entertainment Cost and unsupported products in the RIP decision contract

Each scored product row gains a small entertainmentCost block; unmodeled SKUs
from the sealed market snapshot are published explicitly with their existing
machine-readable reason rather than silently omitted. Additive only: topChase
keys and all existing product keys are unchanged.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

---

## Task 7: Build, persist and read the chase-economics snapshot

**Files:**
- Modify: `backend/db/services/pokemon_public_snapshot_service.py`
- Modify: `backend/scripts/pokemon_snapshot_builders.py`
- Test: `backend/tests/unit/scripts/test_chase_economics_snapshot_build.py` (create)

**Interfaces:**
- Consumes: `select_chase_cards`, `build_chase_economics_contract` (Task 5); the table from Task 4.
- Produces:
  - `pokemon_public_snapshot_service.get_pokemon_set_chase_economics_snapshot_payload(set_id) -> Dict`
  - `pokemon_snapshot_builders.build_chase_economics_snapshot_payload(*, set_id, run_id, client) -> Dict`
  - `CHASE_ECONOMICS_SNAPSHOT_TABLE: str = "pokemon_set_chase_economics_snapshot_latest"`

- [ ] **Step 1: Write the failing tests**

Create `backend/tests/unit/scripts/test_chase_economics_snapshot_build.py`:

```python
"""The chase-economics snapshot is built from ONE run and stays off the
critical set-page payload."""

import json

import pytest

from backend.scripts.pokemon_snapshot_builders import (
    build_chase_economics_snapshot_payload,
)


class _FakeResult:
    def __init__(self, data):
        self.data = data


class _FakeQuery:
    def __init__(self, rows):
        self._rows = rows

    def select(self, *_a, **_k):
        return self

    def eq(self, *_a, **_k):
        return self

    def range(self, start, end):
        self._slice = (start, end)
        return self

    def execute(self):
        start, end = getattr(self, "_slice", (0, len(self._rows) - 1))
        return _FakeResult(self._rows[start : end + 1])


class _FakeClient:
    """Serves the two whole-run populations the builder needs."""

    def __init__(self, input_cards, priced_cards):
        self._tables = {
            "simulation_input_cards": input_cards,
            "simulation_input_cards_with_near_mint_price": priced_cards,
        }

    def table(self, name):
        return _FakeQuery(self._tables.get(name, []))


_INPUT_CARDS = [
    {"card_variant_id": "a", "effective_pull_rate": 476.19, "price_used": 280.0},
    {"card_variant_id": "b", "effective_pull_rate": 20.0, "price_used": 38.0},
]

_PRICED_CARDS = [
    {"card_id": "c-a", "card_variant_id": "a", "card_name": "Chase",
     "rarity_bucket": "ultra", "current_near_mint_price": 310.0},
    {"card_id": "c-b", "card_variant_id": "b", "card_name": "Minor",
     "rarity_bucket": "rare", "current_near_mint_price": 40.0},
]

_PRODUCTS = [
    {
        "sealed_product_id": "prod-box", "product_name": "Booster Box",
        "product_family": "booster_box", "pack_count": 36,
        "product_market_cost": 149.99, "expected_value": 107.89,
        "random_pack_count": None, "guaranteed_component_market_value": None,
    }
]


def test_payload_is_built_from_the_supplied_run():
    payload = build_chase_economics_snapshot_payload(
        set_id="set-1", run_id="run-1",
        client=_FakeClient(_INPUT_CARDS, _PRICED_CARDS),
        product_rows_fn=lambda **_k: _PRODUCTS,
    )
    assert payload["sourceCalculationRunId"] == "run-1"
    assert [c["cardVariantId"] for c in payload["cards"]] == ["a", "b"]


def test_price_used_is_carried_through_as_the_ev_basis():
    payload = build_chase_economics_snapshot_payload(
        set_id="set-1", run_id="run-1",
        client=_FakeClient(_INPUT_CARDS, _PRICED_CARDS),
        product_rows_fn=lambda **_k: _PRODUCTS,
    )
    card = payload["cards"][0]
    assert card["targetValueUsedInEV"] == 280.0
    assert card["currentTargetMarketPrice"] == 310.0
    assert card["targetPriceBasisDelta"] == pytest.approx(30.0)


def test_no_current_run_publishes_an_explicitly_empty_payload():
    payload = build_chase_economics_snapshot_payload(
        set_id="set-1", run_id=None, client=_FakeClient([], []),
        product_rows_fn=lambda **_k: [],
    )
    assert payload["cards"] == []
    assert payload["sourceCalculationRunId"] is None
    json.dumps(payload, allow_nan=False)


def test_payload_is_json_safe():
    payload = build_chase_economics_snapshot_payload(
        set_id="set-1", run_id="run-1",
        client=_FakeClient(_INPUT_CARDS, _PRICED_CARDS),
        product_rows_fn=lambda **_k: _PRODUCTS,
    )
    json.dumps(payload, allow_nan=False)


def test_eligible_count_reports_the_population_before_the_cap():
    payload = build_chase_economics_snapshot_payload(
        set_id="set-1", run_id="run-1",
        client=_FakeClient(_INPUT_CARDS, _PRICED_CARDS),
        product_rows_fn=lambda **_k: _PRODUCTS,
        limit=1,
    )
    assert len(payload["cards"]) == 1
    assert payload["eligibleCardCount"] == 2
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `./backend/.venv/Scripts/python.exe -m pytest backend/tests/unit/scripts/test_chase_economics_snapshot_build.py -q`

Expected: `ImportError: cannot import name 'build_chase_economics_snapshot_payload'`.

- [ ] **Step 3: Add the builder**

Append to `backend/scripts/pokemon_snapshot_builders.py`:

```python
CHASE_ECONOMICS_SNAPSHOT_TABLE = "pokemon_set_chase_economics_snapshot_latest"


def build_chase_economics_snapshot_payload(
    *, set_id, run_id, client, product_rows_fn=None, limit=None
):
    """The chase-economics contract for ONE set, from ONE calculation run.

    Reads the SAME two whole-run populations the Top Chase contract reads -
    `simulation_input_cards` (pull rate plus the price the EV was built on) and
    the Near Mint price view - and reuses the existing paged loader so a set
    larger than one PostgREST page cannot be silently truncated. Truncation here
    would not fail loudly; it would publish a DIFFERENT set of chase cards.

    Without a current run this publishes an explicitly empty payload rather than
    falling back to the newest historical run. Real economics from a run the
    rest of the page is not describing is worse than nothing, because it looks
    right.
    """
    from backend.db.services import rip_decision_service
    from backend.db.services.chase_economics_service import (
        DEFAULT_PUBLISHED_CARD_LIMIT,
        build_chase_economics_contract,
        select_chase_cards,
    )

    resolved_limit = DEFAULT_PUBLISHED_CARD_LIMIT if limit is None else int(limit)
    resolved_run_id = None if run_id is None else str(run_id).strip() or None

    if resolved_run_id is None:
        return build_chase_economics_contract(
            cards=[], product_rows=[], run_id=None, limit=resolved_limit,
            eligible_card_count=0,
        )

    input_rows = rip_decision_service._load_run_population(
        client,
        table=rip_decision_service.INPUT_CARDS_TABLE,
        # `price_used` rides along on the existing select rather than costing a
        # second query. It is the price the stored EV was actually built from,
        # which is NOT today's price - see the EV-basis split in the contract.
        select="card_variant_id,effective_pull_rate,price_used",
        run_id=resolved_run_id,
    )
    denominators = {}
    price_used = {}
    for row in input_rows:
        variant_id = row.get("card_variant_id")
        if not variant_id:
            continue
        denominators[str(variant_id)] = row.get("effective_pull_rate")
        price_used[str(variant_id)] = row.get("price_used")

    priced_rows = rip_decision_service._load_run_population(
        client,
        table=rip_decision_service.NEAR_MINT_PRICE_VIEW,
        select="card_id,card_variant_id,card_name,rarity_bucket,current_near_mint_price",
        run_id=resolved_run_id,
    )

    # The eligible population is measured before the cap so the payload can say
    # "25 of 187" rather than implying the set has 25 chaseable cards.
    eligible = select_chase_cards(priced_rows, denominators, price_used, limit=10**9)
    cards = eligible[:resolved_limit]

    if product_rows_fn is None:
        def product_rows_fn(**_kwargs):
            return rip_decision_service._load_current_run_product_rows(
                run_id=resolved_run_id, set_id=set_id, client=client
            )

    return build_chase_economics_contract(
        cards=cards,
        product_rows=product_rows_fn(run_id=resolved_run_id, set_id=set_id),
        run_id=resolved_run_id,
        limit=resolved_limit,
        eligible_card_count=len(eligible),
    )


def persist_chase_economics_snapshot(*, set_id, run_id, payload, client):
    """Upsert ONE set's chase-economics snapshot row.

    Separate from the set-page snapshot write on purpose: this row is not on
    the critical path and a failure here must not fail the page build.
    """
    row = {
        "set_id": str(set_id),
        "calculation_run_id": None if run_id is None else str(run_id),
        "payload_json": payload,
        "card_count": len(payload.get("cards") or []),
        "as_of": _utc_now_iso() if "_utc_now_iso" in globals() else None,
    }
    return (
        client.table(CHASE_ECONOMICS_SNAPSHOT_TABLE)
        .upsert(row, on_conflict="set_id")
        .execute()
    )
```

**Before writing `persist_chase_economics_snapshot`,** grep the file for an existing timestamp helper (`rg "def _utc_now|datetime.now\(" backend/scripts/pokemon_snapshot_builders.py`) and use the established one rather than the conditional shown. If none exists, use `datetime.now(timezone.utc).isoformat()` and add the import.

- [ ] **Step 4: Run the tests to verify they pass**

Run: `./backend/.venv/Scripts/python.exe -m pytest backend/tests/unit/scripts/test_chase_economics_snapshot_build.py -q`

Expected: PASS.

- [ ] **Step 5: Add the reader**

Append to `backend/db/services/pokemon_public_snapshot_service.py`, modeled on `get_pokemon_set_cards_snapshot_payload` (:2013) — read that function first and match its error handling, meta merging and return shape:

```python
CHASE_ECONOMICS_SNAPSHOT_TABLE = "pokemon_set_chase_economics_snapshot_latest"


def get_pokemon_set_chase_economics_snapshot_payload(set_id: str) -> Dict[str, Any]:
    """One set's published chase-economics contract.

    A DELIBERATELY SEPARATE REQUEST from the set page. The payload is roughly
    60-90 KB per set and nothing on the critical path reads it, so it is served
    only when something asks for it rather than riding along on every set view.

    A missing row is a real answer - the set has not been built yet - and is
    reported as such rather than as an error.
    """
    started = time.perf_counter()
    try:
        result = (
            _service_client()
            .table(CHASE_ECONOMICS_SNAPSHOT_TABLE)
            .select("set_id,calculation_run_id,payload_json,card_count,as_of,updated_at")
            .eq("set_id", str(set_id))
            .limit(1)
            .execute()
        )
        row = (result.data or [None])[0]
    except Exception as exc:
        if _is_missing_snapshot_relation_error(exc):
            row = None
        else:
            raise

    elapsed_ms = round((time.perf_counter() - started) * 1000.0, 3)
    if not row or not isinstance(row.get("payload_json"), dict):
        return {
            "available": False,
            "setId": str(set_id),
            "payload": None,
            "source": f"{CHASE_ECONOMICS_SNAPSHOT_TABLE}.payload_json",
            "elapsedMs": elapsed_ms,
        }

    return {
        "available": True,
        "setId": str(set_id),
        "sourceCalculationRunId": row.get("calculation_run_id"),
        "cardCount": row.get("card_count"),
        "asOf": row.get("as_of"),
        "updatedAt": row.get("updated_at"),
        "payload": row["payload_json"],
        "source": f"{CHASE_ECONOMICS_SNAPSHOT_TABLE}.payload_json",
        "elapsedMs": elapsed_ms,
    }
```

Adjust `_service_client()` and `time` to whatever the surrounding module already uses — match the neighbouring function exactly rather than introducing a new client accessor.

- [ ] **Step 6: Run the snapshot service regression suite**

Run: `./backend/.venv/Scripts/python.exe -m pytest backend/tests/unit/db/services/test_pokemon_public_snapshot_service.py backend/tests/unit/scripts/ -q`

Expected: PASS, all pre-existing tests unchanged.

- [ ] **Step 7: Commit**

```bash
git add backend/scripts/pokemon_snapshot_builders.py backend/db/services/pokemon_public_snapshot_service.py backend/tests/unit/scripts/test_chase_economics_snapshot_build.py
git commit -m "Build, persist and read the chase-economics snapshot

Built from the same two whole-run populations Top Chase already loads, with
price_used riding along on the existing select as the EV price basis. Served
from its own table by its own reader so the critical set page payload does not
grow.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

---

## Task 8: Real-data validation script

**Files:**
- Create: `backend/scripts/audit_entertainment_cost_chase.py`

**Interfaces:**
- Consumes: everything from Tasks 1–7.
- Produces: console output only. **No `--commit` path, no writes.**

- [ ] **Step 1: Write the script**

Create `backend/scripts/audit_entertainment_cost_chase.py`:

```python
"""Read-only validation of Entertainment Cost and chase economics on real sets.

DRY RUN ONLY. There is deliberately no `--commit` flag and no write path: this
script exists to let a human check the numbers against reality before anything
is published, and a script that can also write is a script someone will
eventually run with the wrong flag.

Usage:
    python -m backend.scripts.audit_entertainment_cost_chase --set-slug <slug> [...]
"""

from __future__ import annotations

import argparse
import json
import sys
from typing import Any, Dict, List


def _print_products(contract: Dict[str, Any]) -> None:
    print("\n  SCORED PRODUCTS")
    print(f"  {'Product':<38} {'Price':>9} {'EV':>9} {'EntCost':>9} {'/pack':>8} {'ratio':>7}")
    for product in contract.get("sealedProducts", {}).get("products", []):
        block = product.get("entertainmentCost") or {}
        def _fmt(value, width=9, places=2):
            return f"{value:>{width}.{places}f}" if isinstance(value, (int, float)) else f"{'--':>{width}}"
        print(
            f"  {str(product.get('productName'))[:38]:<38}"
            f"{_fmt(block.get('purchasePrice'))}"
            f"{_fmt(block.get('expectedValue'))}"
            f"{_fmt(block.get('entertainmentCost'))}"
            f"{_fmt(block.get('entertainmentCostPerPackEquivalent'), 8)}"
            f"{_fmt(block.get('entertainmentCostRatio'), 7, 3)}"
        )

    unsupported = contract.get("unsupportedProducts", {}).get("products", [])
    print(f"\n  UNSUPPORTED PRODUCTS ({len(unsupported)})")
    for product in unsupported:
        reason = (product.get("entertainmentCost") or {}).get("reason")
        print(f"  {str(product.get('productName'))[:48]:<48} {reason}")


def _print_chase(payload: Dict[str, Any], top_n: int) -> None:
    cards = payload.get("cards") or []
    print(
        f"\n  CHASE ECONOMICS  ({len(cards)} published of "
        f"{payload.get('eligibleCardCount')} eligible)"
    )
    deltas: List[float] = []
    for card in cards[:top_n]:
        delta = card.get("targetPriceBasisDelta")
        if isinstance(delta, (int, float)):
            deltas.append(delta)
        print(
            f"\n  {card.get('cardName')}  "
            f"current=${card.get('currentTargetMarketPrice')}  "
            f"evBasis=${card.get('targetValueUsedInEV')}  "
            f"delta={delta}"
        )
        print(
            f"    1 in {card.get('impliedOddsOneInN')} packs | "
            f"50%: {card.get('packsFor50PercentChance')} packs | "
            f"90%: {card.get('packsFor90PercentChance')} packs"
        )
        for product in card.get("products") or []:
            if not product.get("available"):
                print(f"    {product.get('productFamily'):<32} unavailable: {product.get('reason')}")
                continue
            print(
                f"    {str(product.get('productFamily')):<32}"
                f" spend=${product.get('grossSpend'):.0f}"
                f" recovery=${product.get('incidentalRecovery'):.0f}"
                f" acquire=${product.get('ripAcquisitionCost'):.0f}"
                f" premium=${product.get('entertainmentPremium'):.0f}"
            )

    if deltas:
        print(
            f"\n  PRICE BASIS DRIFT across {len(deltas)} cards: "
            f"min={min(deltas):.2f} max={max(deltas):.2f} "
            f"mean={sum(deltas) / len(deltas):.2f}"
        )
        print("  (current minus EV basis; positive = card appreciated since the run)")


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--set-slug", action="append", required=True,
                        help="canonical set key; repeatable")
    parser.add_argument("--top", type=int, default=3,
                        help="how many chase cards to print per set")
    parser.add_argument("--json", action="store_true",
                        help="dump raw contracts instead of tables")
    args = parser.parse_args(argv)

    from backend.db.clients.supabase_client import supabase
    from backend.db.services.rip_decision_service import build_rip_decision_contract
    from backend.scripts.pokemon_snapshot_builders import (
        build_chase_economics_snapshot_payload,
    )
    from backend.db.services.pokemon_sets_catalog_service import (  # noqa: F401
        # Imported for its side-effect-free set lookup; adjust to whatever the
        # repository's canonical slug->set_id resolver turns out to be.
    )

    for slug in args.set_slug:
        print(f"\n{'=' * 78}\nSET: {slug}\n{'=' * 78}")
        set_id, run_id = _resolve_set_and_run(supabase, slug)
        if set_id is None:
            print("  set not found")
            continue
        print(f"  set_id={set_id}  calculation_run_id={run_id}")

        contract = build_rip_decision_contract(set_id=set_id, run_id=run_id, client=supabase)
        payload = build_chase_economics_snapshot_payload(
            set_id=set_id, run_id=run_id, client=supabase
        )

        if args.json:
            print(json.dumps({"ripDecision": contract, "chaseEconomics": payload},
                             indent=2, allow_nan=False))
            continue

        _print_products(contract)
        _print_chase(payload, args.top)

        # The contract must be publishable as JSON, on real data, not just in
        # fixtures. This is the check that catches a real NaN.
        json.dumps(contract, allow_nan=False)
        json.dumps(payload, allow_nan=False)
        print("\n  JSON safety: OK")

    return 0


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 2: Implement `_resolve_set_and_run`**

The plan cannot specify this without knowing the repository's canonical resolver. Before writing it, run:

```bash
rg "def .*resolve.*set|canonical_set_key.*set_id" backend/db/services/pokemon_sets_catalog_service.py backend/scripts/pokemon_snapshot_builders.py | head -20
```

Use the existing resolver the snapshot builders already use to turn a slug into `(set_id, current calculation_run_id)`. **Do not write a new query** if one exists — a second resolution is a chance to disagree with the builder about which run is current, which is precisely the failure mode the decision layer is built to avoid. Remove the placeholder import block once the real resolver is identified.

- [ ] **Step 3: Run it against three real sets**

Pick, from the live catalogue: one modern high-chase set, one set with Stage 2 ETB coverage, one set with unsupported blister SKUs present.

```bash
./backend/.venv/Scripts/python.exe -m backend.scripts.audit_entertainment_cost_chase \
  --set-slug <modernSet> --set-slug <etbSet> --set-slug <blisterSet> --top 3
```

Check, and report back rather than silently accepting:
- Entertainment cost is positive for typical sealed products. A whole set of negatives means the EV or price column is being misread.
- `entertainmentCostRatio` is plausible (roughly 0.1–0.5 for most sealed products).
- The price-basis drift summary is non-zero for at least some cards — if every delta is exactly 0.00, `price_used` is probably not being read and the two bases have silently collapsed into one.
- Unsupported products appear with sensible reasons.
- `JSON safety: OK` prints for every set.

- [ ] **Step 4: Commit**

```bash
git add backend/scripts/audit_entertainment_cost_chase.py
git commit -m "Add read-only validation script for entertainment cost and chase economics

Dry-run only, no commit path. Prints the product table, the unsupported list,
the top chase journeys and the observed price-basis drift, and asserts JSON
safety against real data.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

---

## Final verification

- [ ] **Run the whole backend unit suite**

Run: `./backend/.venv/Scripts/python.exe -m pytest backend/tests/unit -q`

Expected: PASS. Any pre-existing failure unrelated to this work should be reported, not fixed silently.

- [ ] **Run the frontend contract suites**

Run: `cd frontend && npm test -- ripDecisionContract` (or the repository's established runner for `.test.mjs` files — check `frontend/package.json` first).

Expected: PASS unchanged. The frontend normalizes `ripDecision` as a pass-through `toNullablePlainObject`, so additive keys must not break it. If they do, something non-additive was added.

- [ ] **Confirm the scope boundaries held**

```bash
git diff --stat main...HEAD
```

Verify the diff contains **no** frontend files, **no** file under `backend/calculations/evr/financial_rip_v3*`, `backend/desirability/weighted_rip.py` or `backend/desirability/collector_appeal*`, and **no** composition, promo or classifier data changes.

---

## Notes for the executor

- **Do not apply the migration to production.** It is committed as a file. Application is manual and is the repository owner's decision.
- **If a pre-existing test breaks**, your change was not additive. Revert and narrow rather than editing the existing test to match new behaviour.
- **If the Monte Carlo test disagrees** with the analytical module beyond tolerance, that is a real finding — stop and investigate the math. Do not widen the tolerance.
- **If `price_used` turns out to be absent or null** on real rows for a set, report it. Do not fall back to the current price: the whole point of the two-basis split is that substituting one for the other silently manufactures recovery.
- Tasks 6 and 7 touch files with in-flight uncommitted work from a parallel task. Commit them separately, as the plan specifies, so they can be dropped independently.
