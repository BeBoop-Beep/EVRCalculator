"""Stage V-C Phase 16/17 apparatus, and the central proof's two halves.

These tests guard the FALSIFIER, not the framework. If ``temporal_replay`` or
``equivalence_classes`` were subtly permissive, Stage V-C would pass its own
gate for the wrong reason - so each test below is written against a construction
whose verdict is known, including several that a lenient implementation passes
and a correct one fails.
"""

from __future__ import annotations

import pytest

from backend.research.product_chase_economics import validation


# --------------------------------------------------------------------------
# Primitives
# --------------------------------------------------------------------------

def test_membership_floor_is_inclusive():
    prices = [30.0, 29.999, 10.0]
    assert validation.membership(prices, 10.0, 3.0) == {0}


def test_jaccard_treats_two_empty_baskets_as_agreement():
    """Two no-Core products have not disagreed about anything."""
    assert validation.jaccard([], []) == 1.0
    assert validation.jaccard([1], []) == 0.0


def test_spearman_uses_average_ranks_for_ties():
    """Competition ranks would report perfect agreement here; average ranks do not.

    ``y`` is constant, so there is no ordering information in it at all and the
    honest answer is "undefined", not "+1.0".
    """
    assert validation.spearman([1, 2, 3, 4], [7, 7, 7, 7]) is None


def test_spearman_still_finds_a_real_monotone_relation():
    assert validation.spearman([1, 2, 3, 4], [10, 20, 30, 40]) == pytest.approx(1.0)


# --------------------------------------------------------------------------
# Phase 16 - temporal replay
# --------------------------------------------------------------------------

VECTORS = {"S": [100.0, 60.0, 31.0, 29.0, 5.0]}


def _observation(day, cost, packs=10, key="p1", set_key="S"):
    return {"setKey": set_key, "productKey": key, "date": day,
            "productMarketCost": cost, "randomPackCount": packs}


def test_temporal_replay_reports_a_stable_product_as_stable():
    result = validation.temporal_replay(
        price_vectors=VECTORS,
        observations=[_observation("2026-08-01", 100.0), _observation("2026-08-02", 100.0)])
    assert result["supported"] is True
    assert result["totalCoreExistenceFlips"] == 0
    assert all(day["meanCoreJaccard"] == 1.0 for day in result["perDate"])


def test_temporal_replay_catches_a_membership_change():
    """C moves $10.00 -> $10.34, so the 31.0 card drops below the 3x floor."""
    result = validation.temporal_replay(
        price_vectors=VECTORS, baseline_date="2026-08-01",
        observations=[_observation("2026-08-01", 100.0), _observation("2026-08-02", 103.4)])
    later = [day for day in result["perDate"] if day["date"] == "2026-08-02"][0]
    assert later["meanCoreCountDelta"] == pytest.approx(-1.0)
    assert later["meanCoreJaccard"] < 1.0


def test_temporal_replay_counts_a_core_existence_flip():
    """Losing the LAST Core member is a change of verdict, not of magnitude."""
    result = validation.temporal_replay(
        price_vectors={"S": [30.0]}, baseline_date="2026-08-01",
        observations=[_observation("2026-08-01", 100.0), _observation("2026-08-02", 200.0)])
    assert result["totalCoreExistenceFlips"] == 1


def test_temporal_replay_reports_the_real_window_not_a_nominal_one():
    result = validation.temporal_replay(
        price_vectors=VECTORS,
        observations=[_observation("2026-08-01", 100.0), _observation("2026-08-14", 100.0)])
    assert result["windowDays"] == 13
    assert result["regime"] == "single_regime_only"
    assert result["cardPrices"] == "frozen_at_build_basis"


def test_temporal_replay_skips_rows_it_cannot_price():
    result = validation.temporal_replay(
        price_vectors=VECTORS,
        observations=[_observation("2026-08-01", 100.0),
                      _observation("2026-08-02", None),
                      _observation("2026-08-03", 100.0, packs=0)])
    assert result["dates"] == ["2026-08-01"]


def test_temporal_replay_is_unsupported_rather_than_empty_when_there_is_no_history():
    result = validation.temporal_replay(price_vectors=VECTORS, observations=[])
    assert result["supported"] is False
    assert result["reason"]


# --------------------------------------------------------------------------
# Phase 17 - the pathological catalogue
# --------------------------------------------------------------------------

def test_every_pathological_case_passes():
    results = validation.run_catalogue()
    failures = [(r["key"], r["failure"]) for r in results if not r["passed"]]
    assert failures == []


def test_the_catalogue_covers_every_required_case():
    """The brief names these; a silently dropped case would be a coverage hole."""
    keys = {r["key"] for r in validation.run_catalogue()}
    assert {"A_same_packs_cheap", "A_same_packs_dear"} <= keys   # same packs, different price
    assert {"B_single_pack", "B_thirty_six_packs"} <= keys       # same C, 1 vs 36 packs
    assert "C_expensive_large" in keys
    assert "D_cheap_small" in keys
    assert "E_exactly_on_the_floor" in keys
    assert "F_hero_only_core" in keys
    assert "G_no_core" in keys
    assert "H_guaranteed_promo" in keys


def test_the_catalogue_actually_fails_a_broken_case():
    """The apparatus must be able to report FAIL, or its PASSes mean nothing."""
    broken = validation.PathologicalCase(
        key="broken", description="deliberately wrong expectation",
        prices=(100.0,), product_market_cost=10.0, random_pack_count=1,
        expectation=validation._expect(coreCount=99))
    result = validation.run_catalogue([broken])[0]
    assert result["passed"] is False
    assert "coreCount" in result["failure"]


def test_size_contrast_case_would_fail_if_the_denominator_used_pack_count():
    """H is the guaranteed-promo guard, restated as a falsification.

    Dividing $110 by 12 packs instead of 11 gives $9.17 and a $27.50 Core floor
    rather than $30.00, which quietly qualifies a $28 card that should not
    qualify. The price vector carries a card in exactly that gap, because a
    ladder with nothing between the two floors would hide the bug.
    """
    prices = (400.0, 120.0, 60.0, 30.0, 28.0, 12.0, 1.0)
    honest = validation.evaluate_case(validation.PathologicalCase(
        key="honest", description="11 random packs plus a guaranteed promo",
        prices=prices, product_market_cost=110.0, random_pack_count=11,
        expectation=lambda o: None))
    leaked = validation.evaluate_case(validation.PathologicalCase(
        key="leaked", description="promo counted as a random pack",
        prices=prices, product_market_cost=110.0, random_pack_count=12,
        expectation=lambda o: None))
    assert honest["packEquivalentCost"] == pytest.approx(10.0)
    assert leaked["packEquivalentCost"] == pytest.approx(110.0 / 12)
    assert len(leaked["core"]) == len(honest["core"]) + 1
    assert leaked["core"] > honest["core"]


# --------------------------------------------------------------------------
# The central proof
# --------------------------------------------------------------------------

def _row(name, set_name="S", C=10.0, packs=36, coreK=4, depth=2.0, pPack=0.05,
         evReturn=0.4, evShare=0.3, btb=0.2, extK=6, pProduct=0.84):
    return {"set": set_name, "name": name, "C": C, "packs": packs, "coreK": coreK,
            "extK": extK, "depth": depth, "pPack": pPack, "evReturn": evReturn,
            "evShare": evShare, "btb": btb, "pProduct": pProduct}


def test_equivalence_holds_for_two_products_at_the_same_cost_per_pack():
    rows = [_row("box", packs=36, pProduct=0.84), _row("pack", packs=1, pProduct=0.05)]
    result = validation.equivalence_classes(rows)
    assert result["equivalencePairsFound"] == 1
    assert result["sizeContrastPairs"] == 1
    assert result["violations"] == []
    assert result["holds"] is True


def test_equivalence_fails_when_a_per_sku_number_leaks_in():
    """The per-SKU Monte Carlo signature: same C, different per-pack probability."""
    rows = [_row("box", packs=36), _row("pack", packs=1, pPack=0.0503, pProduct=0.0503)]
    result = validation.equivalence_classes(rows)
    assert result["holds"] is False
    assert any(v["field"] == "pPack" for v in result["violations"])


def test_equivalence_fails_when_two_sizes_share_a_per_unit_probability():
    """A 36-pack box and a single pack must NOT have the same per-unit hit rate."""
    rows = [_row("box", packs=36, pProduct=0.05), _row("pack", packs=1, pProduct=0.05)]
    result = validation.equivalence_classes(rows)
    assert result["holds"] is False
    assert any("pProduct" in v["field"] for v in result["violations"])


def test_equivalence_on_an_empty_cohort_is_vacuous_not_passing():
    """The exact vacuous pass this stage exists to refuse."""
    result = validation.equivalence_classes([_row("only", C=10.0)])
    assert result["equivalencePairsFound"] == 0
    assert result["vacuous"] is True
    assert result["holds"] is False


def test_products_in_different_sets_are_never_equivalence_partners():
    """Different sets have different pack paths; equal C proves nothing across them."""
    rows = [_row("a", set_name="S1"), _row("b", set_name="S2", coreK=9)]
    result = validation.equivalence_classes(rows)
    assert result["equivalencePairsFound"] == 0


def test_differentiation_holds_when_every_set_has_distinct_product_costs():
    rows = [_row("box", C=8.0, coreK=5), _row("etb", C=14.0, coreK=3)]
    result = validation.differentiation_report(rows)
    assert result["setsExamined"] == 1
    assert result["setsWithDistinctProductCosts"] == 1
    assert result["maxCostSpreadRatio"] == pytest.approx(1.75)
    assert result["holds"] is True


def test_differentiation_fails_when_a_set_inherits_one_constant():
    """The Stage-IV error, restated: identical C for every product of a set."""
    rows = [_row("box", C=10.0), _row("etb", C=10.0)]
    result = validation.differentiation_report(rows)
    assert result["setsWithDistinctProductCosts"] == 0
    assert result["holds"] is False


def test_differentiation_flags_a_difference_with_no_cost_reason():
    """Same C, different Core K, is not a legitimate difference."""
    rows = [_row("box", C=10.0, coreK=4), _row("etb", C=10.0, coreK=7)]
    result = validation.differentiation_report(rows)
    assert result["setsWithIllegitimateDifference"] == 1
    assert result["holds"] is False


def test_near_equivalence_finds_close_pairs_and_measures_their_divergence():
    rows = [_row("box", C=10.0, packs=36, pProduct=0.84),
            _row("pack", C=10.05, packs=1, evReturn=0.402, pProduct=0.05)]
    result = validation.near_equivalence(rows, cost_tolerance=0.01)
    assert result["pairsFound"] == 1
    assert result["sizeContrastPairs"] == 1
    assert result["sizeContrastsThatDifferPerUnit"] == 1
    assert result["maxRelativeDivergence"] < 0.02


def test_near_equivalence_ignores_pairs_outside_the_tolerance():
    rows = [_row("box", C=10.0), _row("etb", C=20.0)]
    assert validation.near_equivalence(rows, cost_tolerance=0.01)["vacuous"] is True
