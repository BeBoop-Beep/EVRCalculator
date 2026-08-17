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
