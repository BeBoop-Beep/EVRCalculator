"""Stage V-C product-level Chase Economics invariants.

These tests are the falsification apparatus for Stage V-C, not a smoke screen.
Several of them are written so that the OBVIOUS wrong implementation passes the
happy path and fails here: the pack-count invariance test would pass for a
metric that silently rewards big boxes, and the cost-normalisation test is the
one that catches it.
"""

from __future__ import annotations

import math

import numpy as np
import pytest

from backend.research.product_chase_economics import contract
from backend.research.product_chase_economics.metrics import (
    accessibility,
    aggregate_to_product,
    product_chase_ev,
    products_for_horizon,
    whole_product_journey,
)
from backend.research.product_chase_economics.runner import evaluate_product_basket


class Entity:
    """Minimal stand-in for an eligible chase entity."""

    def __init__(self, entity_id, card_variant_id, price):
        self.entity_id = entity_id
        self.card_variant_id = card_variant_id
        self.price = price


class FakeDecomposition:
    """A deterministic recorded pack sequence.

    ``draws`` is (packs x entities) copy counts, so every statistic derived from
    it is exact and hand-checkable rather than sampled.
    """

    def __init__(self, draws, prices):
        self.draws = np.asarray(draws, dtype=np.float64)
        self.prices = np.asarray(prices, dtype=np.float64)
        self.entity_count = self.draws.shape[1]

    def price_vector(self):
        return self.prices.copy()

    def pull_counts(self):
        return self.draws.sum(axis=0)

    def pack_values(self, vector):
        return self.draws @ np.asarray(vector, dtype=np.float64)

    def pack_max_entity_value(self, vector):
        vec = np.asarray(vector, dtype=np.float64)
        present = (self.draws > 0).astype(np.float64)
        return (present * vec).max(axis=1)


def make_case():
    """Four entities priced 60 / 30 / 12 / 1, over eight recorded packs."""
    prices = [60.0, 30.0, 12.0, 1.0]
    draws = [
        [1, 0, 0, 1],
        [0, 1, 0, 1],
        [0, 0, 1, 1],
        [0, 0, 0, 1],
        [0, 0, 0, 1],
        [1, 1, 0, 1],
        [0, 0, 0, 1],
        [0, 0, 1, 1],
    ]
    entities = [Entity(i, "cv-%d" % i, p) for i, p in enumerate(prices)]
    return FakeDecomposition(draws, prices), np.asarray(prices), entities


# --------------------------------------------------------------------------
# Tier contract
# --------------------------------------------------------------------------

def test_pack_equivalent_cost_is_product_native():
    assert contract.pack_equivalent_cost(
        product_market_cost=86.80, random_pack_count=6) == pytest.approx(14.4666667)


def test_pack_equivalent_cost_refuses_to_invent_a_number():
    assert contract.pack_equivalent_cost(product_market_cost=None, random_pack_count=6) is None
    assert contract.pack_equivalent_cost(product_market_cost=50.0, random_pack_count=0) is None
    assert contract.pack_equivalent_cost(product_market_cost=-5.0, random_pack_count=6) is None


def test_tier_membership_uses_three_and_one_times_cost():
    _, _, entities = make_case()
    basket = contract.product_basket(entities, 10.0)
    # thresholds: core 30, extended 10 -> core {60,30}, extended {60,30,12}
    assert basket["coreCount"] == 2
    assert basket["extendedCount"] == 3
    assert basket["coreThreshold"] == 30.0
    assert basket["extendedThreshold"] == 10.0


def test_core_is_a_subset_of_extended():
    _, _, entities = make_case()
    for cost in (0.5, 1.0, 4.0, 10.0, 19.9, 20.0, 50.0):
        basket = contract.product_basket(entities, cost)
        assert set(basket["coreEntityIds"]) <= set(basket["extendedEntityIds"])
        assert basket["coreCount"] <= basket["extendedCount"]


def test_boundary_is_inclusive_at_exactly_the_threshold():
    entities = [Entity(0, "cv-0", 30.0)]
    assert contract.product_basket(entities, 10.0)["coreCount"] == 1
    # a hair above the cost pushes the same card out of Core
    assert contract.product_basket(entities, 10.0001)["coreCount"] == 0


def test_identical_cost_gives_identical_membership():
    _, _, entities = make_case()
    a = contract.product_basket(entities, 7.25)
    b = contract.product_basket(entities, 7.25)
    assert a["coreEntityIds"] == b["coreEntityIds"]
    assert a["extendedEntityIds"] == b["extendedEntityIds"]


def test_cheaper_product_never_has_a_narrower_chase_universe():
    """Monotonicity. The central fairness property of the whole contract."""
    _, _, entities = make_case()
    costs = [0.5, 1.0, 2.0, 4.0, 8.0, 12.0, 20.0, 40.0, 100.0]
    previous_core, previous_ext = None, None
    for cost in costs:
        basket = contract.product_basket(entities, cost)
        if previous_core is not None:
            assert basket["coreCount"] <= previous_core
            assert basket["extendedCount"] <= previous_ext
        previous_core, previous_ext = basket["coreCount"], basket["extendedCount"]


def test_empty_core_is_legal_and_is_not_missing_data():
    _, _, entities = make_case()
    basket = contract.product_basket(entities, 1000.0)
    assert basket["coreCount"] == 0
    assert basket["coreEntityIds"] == []


def test_zero_and_negative_prices_never_qualify():
    entities = [Entity(0, "cv-0", 0.0), Entity(1, "cv-1", -3.0), Entity(2, "cv-2", None)]
    basket = contract.product_basket(entities, 1.0)
    assert basket["extendedCount"] == 0


def test_distinct_variant_identities_are_preserved_not_deduplicated():
    """Two real printings at the same price must both be counted."""
    entities = [Entity(0, "cv-base", 40.0), Entity(1, "cv-reverse", 40.0)]
    basket = contract.product_basket(entities, 10.0)
    assert basket["coreCount"] == 2
    assert sorted(basket["coreCardVariantIds"]) == ["cv-base", "cv-reverse"]


# --------------------------------------------------------------------------
# Probability contract
# --------------------------------------------------------------------------

def test_probability_at_least_one_identity_holds():
    decomposition, prices, entities = make_case()
    basket = contract.product_basket(entities, 10.0)
    result = evaluate_product_basket(
        decomposition=decomposition, prices=prices,
        entities=[e for e in entities if e.entity_id in basket["coreEntityIds"]],
        entity_ids=basket["coreEntityIds"], pack_cost=10.0, product_cost=360.0,
        random_pack_count=36, full_pack_values=decomposition.pack_values(prices),
        pack_independent=True)
    dist = result["hitCountDistribution"]
    assert dist["pAtLeastOne"] == pytest.approx(1.0 - dist["pZero"])
    # packs 0,1,5 contain a core card -> 3/8
    assert dist["pAtLeastOne"] == pytest.approx(3 / 8)


def test_product_probability_closed_form():
    out = aggregate_to_product(pack_probability=0.10, random_pack_count=36)
    assert out["supported"] is True
    assert out["probabilityAtLeastOne"] == pytest.approx(1 - 0.9 ** 36)
    assert out["expectedChaseContainingPacks"] == pytest.approx(3.6)


def test_product_probability_increases_with_pack_count():
    previous = 0.0
    for n in (1, 2, 6, 12, 24, 36):
        p = aggregate_to_product(pack_probability=0.05, random_pack_count=n)["probabilityAtLeastOne"]
        assert p > previous
        previous = p


def test_single_pack_product_probability_equals_pack_probability():
    out = aggregate_to_product(pack_probability=0.037, random_pack_count=1)
    assert out["probabilityAtLeastOne"] == pytest.approx(0.037)


def test_non_iid_product_is_refused_not_forced():
    out = aggregate_to_product(pack_probability=0.1, random_pack_count=36,
                               pack_independent=False)
    assert out["supported"] is False
    assert out["reason"] == "not_pack_independent"
    assert out["assumption"] == "model_consistent_iid"


def test_products_for_horizon_is_consistent_with_probability():
    p = 1 - 0.9 ** 36
    units = products_for_horizon(p, 0.50)
    assert 1 - (1 - p) ** units == pytest.approx(0.50)


# --------------------------------------------------------------------------
# Pack-count invariance and the cost-normalisation guard
# --------------------------------------------------------------------------

def test_same_pack_cost_gives_identical_per_pack_economics_regardless_of_size():
    """Phase 17 case B. One pack vs 36 packs at the same cost per pack."""
    decomposition, prices, entities = make_case()
    basket = contract.product_basket(entities, 10.0)
    members = [e for e in entities if e.entity_id in basket["coreEntityIds"]]
    common = dict(decomposition=decomposition, prices=prices, entities=members,
                  entity_ids=basket["coreEntityIds"], pack_cost=10.0,
                  full_pack_values=decomposition.pack_values(prices),
                  pack_independent=True)
    single = evaluate_product_basket(product_cost=10.0, random_pack_count=1, **common)
    box = evaluate_product_basket(product_cost=360.0, random_pack_count=36, **common)

    # Identical per-pack economics.
    assert single["packProbability"] == box["packProbability"]
    assert single["literalChaseCount"] == box["literalChaseCount"]
    assert single["chaseDepth"] == box["chaseDepth"]
    assert single["chaseEv"]["chaseEv"] == box["chaseEv"]["chaseEv"]
    assert (single["productChaseEv"]["chaseEvReturn"]
            == pytest.approx(box["productChaseEv"]["chaseEvReturn"]))
    # Different per-UNIT accessibility.
    assert (box["productProbability"]["probabilityAtLeastOne"]
            > single["productProbability"]["probabilityAtLeastOne"])


def test_cost_normalised_spend_does_not_reward_a_bigger_box():
    """The guard against the pack-count artifact.

    A 36-pack box and a 1-pack product at the SAME cost per pack must require
    the same DOLLARS for a 50% chance, even though the box wins on per-unit
    probability. A metric that collapsed the two views would fail this.
    """
    single = accessibility(pack_probability=0.05, product_probability=0.05,
                           pack_cost=10.0, product_cost=10.0, random_pack_count=1)
    box_p = 1 - 0.95 ** 36
    box = accessibility(pack_probability=0.05, product_probability=box_p,
                        pack_cost=10.0, product_cost=360.0, random_pack_count=36)
    assert (single["costNormalised"]["50"]["spendPackGranular"]
            == pytest.approx(box["costNormalised"]["50"]["spendPackGranular"]))
    assert (box["perProduct"]["anyChaseRatePerProduct"]
            > single["perProduct"]["anyChaseRatePerProduct"])


def test_whole_product_spend_is_never_cheaper_than_pack_granular():
    box = accessibility(pack_probability=0.05, product_probability=1 - 0.95 ** 36,
                        pack_cost=10.0, product_cost=360.0, random_pack_count=36)
    for horizon in ("50", "75", "90"):
        block = box["costNormalised"][horizon]
        assert block["spendWholeProduct"] >= block["spendPackGranular"] - 1e-9


# --------------------------------------------------------------------------
# Chase EV reconciliation
# --------------------------------------------------------------------------

def test_chase_ev_return_reconciles_between_formulations():
    out = product_chase_ev(pack_chase_ev=2.5, random_pack_count=36,
                           product_cost=360.0, full_pack_ev=9.0)
    assert out["chaseEvReturn"] == pytest.approx(90.0 / 360.0)
    assert out["chaseEvReturn"] == pytest.approx(out["chaseEvReturnPackNormalised"])
    assert out["chaseEvShareOfFullEv"] == pytest.approx(2.5 / 9.0)


def test_chase_ev_scales_linearly_with_pack_count():
    small = product_chase_ev(pack_chase_ev=2.0, random_pack_count=6,
                             product_cost=60.0, full_pack_ev=9.0)
    large = product_chase_ev(pack_chase_ev=2.0, random_pack_count=36,
                             product_cost=360.0, full_pack_ev=9.0)
    assert large["chaseEvPerProduct"] == pytest.approx(6 * small["chaseEvPerProduct"])
    assert large["chaseEvReturn"] == pytest.approx(small["chaseEvReturn"])


# --------------------------------------------------------------------------
# Whole-product discretisation
# --------------------------------------------------------------------------

def test_whole_product_journey_costs_at_least_the_pack_granular_journey():
    qualifying = np.array([False, False, True, False, True, False, False, True])
    values = np.array([0.0, 0.0, 40.0, 0.0, 25.0, 0.0, 0.0, 90.0])
    out = whole_product_journey(qualifying=qualifying, chase_values=values,
                                product_cost=60.0, random_pack_count=6)
    assert out["journeys"] == 3
    # every journey ends inside the first product, so each costs exactly one unit
    assert out["productUnitsMean"] == pytest.approx(1.0)


def test_whole_product_journey_refuses_fractional_products():
    qualifying = np.array([False, False, False, True])
    values = np.array([0.0, 0.0, 0.0, 100.0])
    out = whole_product_journey(qualifying=qualifying, chase_values=values,
                                product_cost=30.0, random_pack_count=2)
    # the chase arrives on pack 4 -> ceil(4/2) = 2 whole products, never 1.5
    assert out["productUnitsMean"] == pytest.approx(2.0)


def test_whole_product_journey_reports_missing_inputs():
    out = whole_product_journey(qualifying=np.array([True]), chase_values=np.array([5.0]),
                                product_cost=None, random_pack_count=6)
    assert out["journeys"] == 0


# --------------------------------------------------------------------------
# Empty core, and guaranteed-content leakage
# --------------------------------------------------------------------------

def test_empty_core_evaluates_to_a_measured_zero():
    decomposition, prices, entities = make_case()
    result = evaluate_product_basket(
        decomposition=decomposition, prices=prices, entities=[], entity_ids=[],
        pack_cost=1000.0, product_cost=36000.0, random_pack_count=36,
        full_pack_values=decomposition.pack_values(prices), pack_independent=True)
    assert result["supported"] is True
    assert result["empty"] is True
    assert result["literalChaseCount"] == 0
    assert result["packProbability"] == 0.0
    assert result["productProbability"]["probabilityAtLeastOne"] == 0.0


def test_random_pack_count_excludes_guaranteed_components():
    """No guaranteed-promo leakage.

    The denominator and the aggregation exponent are both ``random_pack_count``,
    never ``pack_count``. A product with 11 random packs plus a guaranteed promo
    must price and aggregate on 11.
    """
    cost = contract.pack_equivalent_cost(product_market_cost=110.0, random_pack_count=11)
    assert cost == pytest.approx(10.0)
    out = aggregate_to_product(pack_probability=0.05, random_pack_count=11)
    assert out["randomPackCount"] == 11
    assert out["probabilityAtLeastOne"] == pytest.approx(1 - 0.95 ** 11)


# --------------------------------------------------------------------------
# Set-inheritance comparison
# --------------------------------------------------------------------------

def test_product_native_cost_cannot_exceed_the_set_cheapest_route_basket():
    """The formal statement of the Phase-13 bias.

    The cheapest route has the lowest per-pack cost in the set by construction,
    so no product can ever qualify MORE cards than set-level inheritance would
    have given it. The bias is one-directional, and this pins it.
    """
    _, _, entities = make_case()
    cheapest = 5.0
    inherited = contract.product_basket(entities, cheapest)
    for premium in (1.0, 1.2, 2.0, 3.5, 6.2):
        native = contract.product_basket(entities, cheapest * premium)
        assert native["coreCount"] <= inherited["coreCount"]
        assert native["extendedCount"] <= inherited["extendedCount"]
        assert set(native["coreEntityIds"]) <= set(inherited["coreEntityIds"])
