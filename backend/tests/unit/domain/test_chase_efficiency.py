import math

from backend.domain.pokemon.chase_efficiency import (
    calculate_row, chase_efficiency, probability_from_effective_pull_rate, rank_rows,
)


def product(product_id, price, packs):
    return {
        "sealed_product_id": product_id, "product_name": product_id,
        "product_family": "booster_box", "product_price": price,
        "random_pack_count": packs, "composition_verified": True,
        "price_source": "market", "price_as_of": "2026-08-27",
    }


def card(variant="00000000-0000-0000-0000-000000000001", value=100, p=0.01):
    return {
        "card_variant_id": variant, "canonical_card_id": "canonical", "set_id": "set",
        "era_id": "era", "canonical_rarity": "Special Illustration Rare",
        "card_name": "Card", "current_market_price": value, "probability": p,
        "price_is_fresh": True, "card_price_as_of": "2026-08-27",
    }


def test_formula_is_raw_hazard_value_over_best_pack_cost():
    actual = chase_efficiency(target_value=120, pack_cost=4, probability=0.01)
    assert actual == round((120 / 4) * -math.log(0.99), 12)
    assert probability_from_effective_pull_rate(100) == 0.01


def test_whole_product_milestones_choose_actual_minimum_spend():
    row, reason = calculate_row(card(), [product("box", 100, 36), product("pack", 4, 1)])
    assert reason is None
    assert row["chosen_sealed_product_id"] == "box"  # lowest pack-equivalent cost
    assert row["milestones"]["50"]["spend"] == min(
        route["thresholds"]["50"]["spend"] for route in row["verified_routes"]
    )
    assert row["milestones"]["50"]["productsNeeded"] >= 1


def test_exclusions_are_explicit():
    bad = card(); bad["price_is_fresh"] = False
    assert calculate_row(bad, [product("box", 100, 36)])[1] == "stale_near_mint_price"
    assert calculate_row(card(), [dict(product("box", 100, 36), composition_verified=False)])[1] == "no_verified_current_opening_route"


def test_deterministic_global_era_set_and_rarity_ranks():
    rows = []
    for variant, value in (("b", 100), ("a", 100), ("c", 50)):
        row, _ = calculate_row(card(variant, value), [product("box", 100, 36)])
        rows.append(row)
    ranked = rank_rows(rows)
    assert [r["card_variant_id"] for r in ranked] == ["a", "b", "c"]
    assert [r["overall_rank"] for r in ranked] == [1, 2, 3]
    assert all(r["set_cohort_size"] == 3 and r["rarity_cohort_size"] == 3 for r in ranked)


def test_formula_monotonicity():
    base = chase_efficiency(target_value=100, pack_cost=5, probability=.01)
    assert chase_efficiency(target_value=101, pack_cost=5, probability=.01) > base
    assert chase_efficiency(target_value=100, pack_cost=5, probability=.011) > base
    assert chase_efficiency(target_value=100, pack_cost=6, probability=.01) < base
