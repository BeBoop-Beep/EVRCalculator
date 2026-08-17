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
