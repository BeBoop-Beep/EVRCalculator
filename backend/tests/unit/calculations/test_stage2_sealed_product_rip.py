"""Stage 2 sealed-product contract tests.

The claims under test are the ones that would be expensive to discover in
production: that composition comes from the SKU and not its name, that a
guaranteed promo is a constant rather than a draw, that the shared random
distribution is never mutated by the SKU that borrows it, and that a missing
promo price produces a refusal rather than a cheap-looking product.
"""

from __future__ import annotations

import numpy as np
import pytest

from backend.calculations.evr.guaranteed_component_value import (
    GuaranteedComponentError,
    add_guaranteed_components,
    compose_stage2_distribution,
    total_guaranteed_value,
)
from backend.db.services import sealed_product_stage2_rip_service as stage2
from backend.db.services.sealed_product_rip_service import (
    deferred_collector_appeal,
    score_stage1_sealed_products,
    select_stage1_products,
)
from backend.domain.pokemon import sealed_product_comparison_scope as scope
from backend.domain.pokemon.sealed_product_stage2_composition import (
    CompositionContractError,
    REASON_MISSING_PRODUCT_PRICE,
    REASON_MISSING_PROMO_PRICE,
    REASON_NO_VERIFIED_COMPOSITION,
    parse_composition_row,
)

SET_ID = "set-1"


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

def _composition_row(
    *,
    product_id,
    pack_count,
    cards,
    composition_id="comp-1",
    version="stage2-v1",
    family="elite_trainer_box",
):
    return {
        "id": composition_id,
        "sealed_product_id": product_id,
        "composition_version": version,
        "product_family": family,
        "status": "verified",
        "source_type": "pokemon_com_product_page",
        "source_reference": "https://example.invalid/product",
        "verified_at": "2026-08-15",
        "notes": None,
        "packComponents": [{"set_id": SET_ID, "pack_count": pack_count}],
        "guaranteedCardComponents": cards,
    }


def _card(variant_id, role, quantity=1, canonical=None):
    return {
        "card_variant_id": variant_id,
        "canonical_card_id": canonical,
        "quantity": quantity,
        "component_role": role,
    }


def _snapshot(products):
    return {"products": products}


def _product(product_id, name, family, price=100.0):
    return {
        "sealedProductId": product_id,
        "name": name,
        "productFamily": family,
        "currentPrice": price,
        "priceAsOf": "2026-08-15",
        "source": "TCGPlayer",
    }


def _pack_vector(size=20_000, seed=7):
    rng = np.random.default_rng(seed)
    return rng.gamma(shape=1.4, scale=3.0, size=size)


def _prices(mapping):
    """A price lookup that knows only the variants it is given."""

    def _lookup(components, client=None):
        priced, missing = [], []
        for component in components:
            price = mapping.get(component.card_variant_id)
            if price is None:
                missing.append(
                    {
                        "cardVariantId": component.card_variant_id,
                        "componentRole": component.component_role,
                        "reason": "no_near_mint_usd_market_price_observation",
                    }
                )
                continue
            priced.append(
                {
                    "card_variant_id": component.card_variant_id,
                    "canonical_card_id": component.canonical_card_id,
                    "component_role": component.component_role,
                    "quantity": component.quantity,
                    "display_name": component.display_name,
                    "market_price": price,
                    "captured_at": "2026-08-15",
                    "source": "TCGPlayer",
                }
            )
        total = (
            sum(e["market_price"] * e["quantity"] for e in priced) if priced and not missing else None
        )
        return {"priced": priced, "missing": missing, "totalGuaranteedValue": total}

    return _lookup


# ---------------------------------------------------------------------------
# Composition retrieval
# ---------------------------------------------------------------------------

def test_standard_etb_composition_resolves_by_sealed_product_id():
    composition = parse_composition_row(
        _composition_row(product_id="etb-1", pack_count=9, cards=[_card("v-promo", "standard_etb_promo")])
    )
    assert composition.total_pack_count == 9
    assert composition.guaranteed_card_count == 1
    assert composition.random_pack_set_id == SET_ID


def test_pokemon_center_etb_composition_carries_both_promos():
    composition = parse_composition_row(
        _composition_row(
            product_id="pc-1",
            pack_count=11,
            family="pokemon_center_elite_trainer_box",
            cards=[
                _card("v-standard", "pokemon_center_standard_promo"),
                _card("v-stamped", "pokemon_center_stamped_promo"),
            ],
        )
    )
    assert composition.total_pack_count == 11
    assert composition.guaranteed_card_count == 2
    roles = {c.component_role for c in composition.guaranteed_card_components}
    assert roles == {"pokemon_center_standard_promo", "pokemon_center_stamped_promo"}


def test_enhanced_booster_box_composition_is_36_plus_one():
    composition = parse_composition_row(
        _composition_row(
            product_id="ebb-1",
            pack_count=36,
            family="enhanced_booster_box",
            cards=[_card("v-enhanced", "enhanced_display_promo")],
        )
    )
    assert composition.total_pack_count == 36
    assert composition.guaranteed_card_count == 1


def test_composition_version_and_provenance_are_retained():
    composition = parse_composition_row(
        _composition_row(
            product_id="etb-1",
            pack_count=9,
            version="stage2-etb-v3",
            cards=[_card("v-promo", "standard_etb_promo")],
        )
    )
    payload = composition.as_payload()
    assert payload["compositionVersion"] == "stage2-etb-v3"
    assert payload["sourceType"] == "pokemon_com_product_page"
    assert payload["sourceReference"] == "https://example.invalid/product"
    assert payload["verifiedAt"] == "2026-08-15"


def test_two_artwork_variants_can_map_to_different_promos():
    left = parse_composition_row(
        _composition_row(
            product_id="etb-a", composition_id="c-a", pack_count=9, cards=[_card("v-a", "standard_etb_promo")]
        )
    )
    right = parse_composition_row(
        _composition_row(
            product_id="etb-b", composition_id="c-b", pack_count=9, cards=[_card("v-b", "standard_etb_promo")]
        )
    )
    assert left.total_pack_count == right.total_pack_count
    assert left.guaranteed_card_components[0].card_variant_id != (
        right.guaranteed_card_components[0].card_variant_id
    )


def test_duplicate_printing_in_one_composition_is_refused():
    with pytest.raises(CompositionContractError):
        parse_composition_row(
            _composition_row(
                product_id="etb-1",
                pack_count=9,
                cards=[_card("v-same", "role_a"), _card("v-same", "role_b")],
            )
        )


def test_mixed_set_composition_is_refused_in_stage2():
    row = _composition_row(product_id="etb-1", pack_count=9, cards=[_card("v", "r")])
    row["packComponents"] = [
        {"set_id": SET_ID, "pack_count": 9},
        {"set_id": "set-2", "pack_count": 2},
    ]
    with pytest.raises(CompositionContractError):
        parse_composition_row(row)


@pytest.mark.parametrize(
    "name",
    [
        "Paradox Rift Elite Trainer Box Case",
        "Paradox Rift Elite Trainer Boxes [Set of 2]",
        "Prismatic Evolutions Elite Trainer Box (Dollar General Exclusive)",
    ],
)
def test_unresearched_skus_are_never_stage2_eligible(name):
    """Cases, multi-box listings and unverified retailer variants.

    None of these need an exclusion rule: no composition was researched for
    them, so composition-gated eligibility rejects them by construction.
    """
    family = "case" if "Case" in name else "elite_trainer_box"
    selection = stage2.select_stage2_products(
        _snapshot([_product("x-1", name, family)]),
        compositions_fn=lambda ids: [],
    )
    assert selection["candidates"] == []
    if family in ("elite_trainer_box",):
        assert selection["skipped"][0]["reason"] == REASON_NO_VERIFIED_COMPOSITION


def test_unknown_sku_is_unsupported_even_inside_a_stage2_family():
    selection = stage2.select_stage2_products(
        _snapshot([_product("etb-unknown", "Some Set Elite Trainer Box", "elite_trainer_box")]),
        compositions_fn=lambda ids: [],
    )
    assert selection["candidates"] == []
    assert selection["skipped"][0]["reason"] == REASON_NO_VERIFIED_COMPOSITION


def test_product_without_its_own_price_is_skipped_not_estimated():
    selection = stage2.select_stage2_products(
        _snapshot([_product("etb-1", "ETB", "elite_trainer_box", price=None)]),
        compositions_fn=lambda ids: [
            _composition_row(product_id="etb-1", pack_count=9, cards=[_card("v", "r")])
        ],
    )
    assert selection["candidates"] == []
    assert selection["skipped"][0]["reason"] == REASON_MISSING_PRODUCT_PRICE


# ---------------------------------------------------------------------------
# Guaranteed components
# ---------------------------------------------------------------------------

def test_composed_vector_is_random_plus_constant_for_every_element():
    random_y = np.array([1.0, 5.5, 100.0, 0.25])
    composed = add_guaranteed_components(random_y, 12.5)
    assert np.allclose(composed, random_y + 12.5)


def test_original_random_distribution_is_not_mutated():
    random_y = np.array([1.0, 2.0, 3.0])
    before = random_y.copy()
    add_guaranteed_components(random_y, 10.0)
    assert np.array_equal(random_y, before)


def test_read_only_shared_distribution_can_be_composed():
    """The shared bootstrap output is write-protected; composing must still work."""
    random_y = np.array([1.0, 2.0, 3.0])
    random_y.setflags(write=False)
    composed = add_guaranteed_components(random_y, 4.0)
    assert np.allclose(composed, [5.0, 6.0, 7.0])


def test_total_guaranteed_value_is_exact_sum_of_components():
    components = [
        {"card_variant_id": "a", "quantity": 1, "market_price": 12.34},
        {"card_variant_id": "b", "quantity": 1, "market_price": 7.66},
    ]
    assert total_guaranteed_value(components) == pytest.approx(20.0)


def test_quantity_greater_than_one_multiplies():
    components = [{"card_variant_id": "a", "quantity": 3, "market_price": 5.0}]
    assert total_guaranteed_value(components) == pytest.approx(15.0)


def test_zero_promo_price_is_refused_not_silently_accepted():
    with pytest.raises(GuaranteedComponentError):
        total_guaranteed_value([{"card_variant_id": "a", "quantity": 1, "market_price": 0.0}])


@pytest.mark.parametrize("bad", [None, float("nan"), float("inf"), -1.0])
def test_invalid_promo_prices_are_refused(bad):
    with pytest.raises(GuaranteedComponentError):
        total_guaranteed_value([{"card_variant_id": "a", "quantity": 1, "market_price": bad}])


def test_missing_promo_price_makes_the_whole_product_unscorable():
    candidate = {
        "sealed_product_id": "pc-1",
        "name": "PC ETB",
        "product_family": "pokemon_center_elite_trainer_box",
        "product_market_cost": 120.0,
        "composition": parse_composition_row(
            _composition_row(
                product_id="pc-1",
                pack_count=11,
                family="pokemon_center_elite_trainer_box",
                cards=[
                    _card("v-standard", "pokemon_center_standard_promo"),
                    _card("v-stamped", "pokemon_center_stamped_promo"),
                ],
            )
        ),
    }
    # The ordinary promo is priced; the stamped one is not. A partial valuation
    # would understate the product, so the product is refused entirely.
    result = stage2.price_stage2_candidates(
        [candidate], pricing_fn=_prices({"v-standard": 4.0})
    )
    assert result["candidates"] == []
    assert result["skipped"][0]["reason"] == REASON_MISSING_PROMO_PRICE


def test_wrong_printing_cannot_substitute_for_the_guaranteed_one():
    """Pricing the ordinary promo must not rescue a product needing the stamp."""
    candidate = {
        "sealed_product_id": "pc-1",
        "name": "PC ETB",
        "product_family": "pokemon_center_elite_trainer_box",
        "product_market_cost": 120.0,
        "composition": parse_composition_row(
            _composition_row(
                product_id="pc-1",
                pack_count=11,
                family="pokemon_center_elite_trainer_box",
                cards=[_card("v-stamped", "pokemon_center_stamped_promo")],
            )
        ),
    }
    result = stage2.price_stage2_candidates(
        [candidate], pricing_fn=_prices({"v-ordinary": 4.0, "v-some-other-promo": 900.0})
    )
    assert result["candidates"] == []
    assert result["skipped"][0]["reason"] == REASON_MISSING_PROMO_PRICE


def test_composition_meta_separates_random_ev_from_guaranteed_value():
    random_y = np.full(1000, 10.0)
    composed = compose_stage2_distribution(
        random_y, [{"card_variant_id": "a", "quantity": 1, "market_price": 40.0}]
    )
    meta = composed["meta"]
    assert meta["randomPackExpectedValue"] == pytest.approx(10.0)
    assert meta["totalGuaranteedValue"] == pytest.approx(40.0)
    assert meta["expectedValue"] == pytest.approx(50.0)
    assert meta["guaranteedValueShareOfExpectedValue"] == pytest.approx(0.8)


# ---------------------------------------------------------------------------
# Distributions
# ---------------------------------------------------------------------------

def _stage2_candidate(product_id, pack_count, cards, cost, family="elite_trainer_box", prices=None):
    composition = parse_composition_row(
        _composition_row(
            product_id=product_id,
            composition_id=f"comp-{product_id}",
            pack_count=pack_count,
            family=family,
            cards=cards,
        )
    )
    priced = _prices(prices or {})(composition.guaranteed_card_components)
    assert not priced["missing"]
    return {
        "sealed_product_id": product_id,
        "name": product_id,
        "product_family": family,
        "composition": composition,
        "product_market_cost": cost,
        "priced_components": priced["priced"],
    }


def test_pack_count_comes_from_the_composition_not_the_family():
    """A composition saying 10 wins over the family's baseline of 9."""
    candidate = _stage2_candidate(
        "etb-odd", 10, [_card("v", "standard_etb_promo")], 60.0, prices={"v": 5.0}
    )
    scored = score_stage1_sealed_products(
        pack_values=_pack_vector(),
        candidates=[],
        canonical_set_key="setA",
        collector_appeal=deferred_collector_appeal(),
        stage2_candidates=[candidate],
    )
    assert scored["products"][0]["pack_count"] == 10
    assert scored["distributionMeta"]["packCounts"] == [10]


def test_etb_pc_etb_and_enhanced_use_9_11_and_36():
    candidates = [
        _stage2_candidate("etb", 9, [_card("v1", "standard_etb_promo")], 50.0, prices={"v1": 5.0}),
        _stage2_candidate(
            "pc",
            11,
            [_card("v1", "pokemon_center_standard_promo"), _card("v2", "pokemon_center_stamped_promo")],
            120.0,
            family="pokemon_center_elite_trainer_box",
            prices={"v1": 5.0, "v2": 40.0},
        ),
        _stage2_candidate(
            "ebb",
            36,
            [_card("v3", "enhanced_display_promo")],
            200.0,
            family="enhanced_booster_box",
            prices={"v3": 15.0},
        ),
    ]
    scored = score_stage1_sealed_products(
        pack_values=_pack_vector(),
        candidates=[],
        canonical_set_key="setA",
        collector_appeal=deferred_collector_appeal(),
        stage2_candidates=candidates,
    )
    assert scored["distributionMeta"]["packCounts"] == [9, 11, 36]
    assert {p["sealed_product_id"]: p["pack_count"] for p in scored["products"]} == {
        "etb": 9,
        "pc": 11,
        "ebb": 36,
    }


def test_variants_sharing_a_pack_count_share_one_random_distribution():
    """Same K, different promos: the random half must be identical."""
    candidates = [
        _stage2_candidate("etb-a", 9, [_card("va", "standard_etb_promo")], 50.0, prices={"va": 5.0}),
        _stage2_candidate("etb-b", 9, [_card("vb", "standard_etb_promo")], 50.0, prices={"vb": 25.0}),
    ]
    scored = score_stage1_sealed_products(
        pack_values=_pack_vector(),
        candidates=[],
        canonical_set_key="setA",
        collector_appeal=deferred_collector_appeal(),
        stage2_candidates=candidates,
    )
    # One distribution generated, not two.
    assert scored["distributionMeta"]["packCounts"] == [9]
    by_id = {p["sealed_product_id"]: p for p in scored["products"]}
    assert by_id["etb-a"]["random_pack_expected_value"] == pytest.approx(
        by_id["etb-b"]["random_pack_expected_value"]
    )
    # The promo, and only the promo, separates their expected values.
    assert by_id["etb-b"]["expected_value"] - by_id["etb-a"]["expected_value"] == pytest.approx(20.0)


def test_enhanced_booster_box_reuses_the_stage1_booster_box_distribution():
    """Y36 is generated once and serves both stages."""
    pack_values = _pack_vector()
    stage1 = select_stage1_products(
        _snapshot([_product("bb-1", "Set Booster Box", "booster_box", price=150.0)])
    )
    enhanced = _stage2_candidate(
        "ebb-1",
        36,
        [_card("v", "enhanced_display_promo")],
        220.0,
        family="enhanced_booster_box",
        prices={"v": 30.0},
    )
    scored = score_stage1_sealed_products(
        pack_values=pack_values,
        candidates=stage1["candidates"],
        canonical_set_key="setA",
        collector_appeal=deferred_collector_appeal(),
        stage2_candidates=[enhanced],
    )
    assert scored["distributionMeta"]["packCounts"] == [36]
    by_id = {p["sealed_product_id"]: p for p in scored["products"]}
    assert by_id["ebb-1"]["random_pack_expected_value"] == pytest.approx(
        by_id["bb-1"]["expected_value"]
    )
    assert by_id["ebb-1"]["expected_value"] - by_id["bb-1"]["expected_value"] == pytest.approx(30.0)


def test_stage2_scoring_is_deterministic():
    def _run():
        return score_stage1_sealed_products(
            pack_values=_pack_vector(),
            candidates=[],
            canonical_set_key="setA",
            collector_appeal=deferred_collector_appeal(),
            stage2_candidates=[
                _stage2_candidate("etb", 9, [_card("v", "standard_etb_promo")], 50.0, prices={"v": 5.0})
            ],
        )["products"][0]

    first, second = _run(), _run()
    assert first["expected_value"] == second["expected_value"]
    assert first["financial_rip_v3_score"] == second["financial_rip_v3_score"]


# ---------------------------------------------------------------------------
# Financial
# ---------------------------------------------------------------------------

def test_expected_value_is_k_times_pack_mean_plus_guaranteed_value():
    pack_values = _pack_vector(size=200_000)
    candidate = _stage2_candidate(
        "etb", 9, [_card("v", "standard_etb_promo")], 50.0, prices={"v": 12.0}
    )
    scored = score_stage1_sealed_products(
        pack_values=pack_values,
        candidates=[],
        canonical_set_key="setA",
        collector_appeal=deferred_collector_appeal(),
        stage2_candidates=[candidate],
    )
    product = scored["products"][0]
    expected = 9 * float(np.mean(pack_values)) + 12.0
    # Bootstrap noise only; the relationship itself is exact in expectation.
    assert product["expected_value"] == pytest.approx(expected, rel=0.02)


def test_financial_rip_is_computed_on_the_composed_vector_not_the_random_one():
    from backend.calculations.evr.financial_rip_v3 import build_financial_rip_v3

    pack_values = _pack_vector()
    candidate = _stage2_candidate(
        "etb", 9, [_card("v", "standard_etb_promo")], 50.0, prices={"v": 40.0}
    )
    scored = score_stage1_sealed_products(
        pack_values=pack_values,
        candidates=[],
        canonical_set_key="setA",
        collector_appeal=deferred_collector_appeal(),
        stage2_candidates=[candidate],
    )
    product = scored["products"][0]

    # Rebuild the shared random vector the scorer used, then both scores.
    from backend.calculations.evr.sealed_product_distribution import (
        build_stage1_product_distributions,
    )

    random_y = build_stage1_product_distributions(
        pack_values, pack_counts=[9], canonical_set_key="setA"
    )["distributions"][9]

    composed_score = build_financial_rip_v3(random_y + 40.0, 50.0)["score"]
    random_only_score = build_financial_rip_v3(random_y, 50.0)["score"]

    assert product["financial_rip_v3_score"] == pytest.approx(composed_score)
    assert product["financial_rip_v3_score"] != pytest.approx(random_only_score)


def test_promo_value_changes_final_y_without_changing_random_y():
    pack_values = _pack_vector()
    cheap = _stage2_candidate("a", 9, [_card("v", "r")], 50.0, prices={"v": 1.0})
    rich = _stage2_candidate("b", 9, [_card("w", "r")], 50.0, prices={"w": 500.0})
    scored = score_stage1_sealed_products(
        pack_values=pack_values,
        candidates=[],
        canonical_set_key="setA",
        collector_appeal=deferred_collector_appeal(),
        stage2_candidates=[cheap, rich],
    )
    by_id = {p["sealed_product_id"]: p for p in scored["products"]}
    assert by_id["a"]["random_pack_expected_value"] == pytest.approx(
        by_id["b"]["random_pack_expected_value"]
    )
    assert by_id["a"]["chance_to_recover_cost"] < by_id["b"]["chance_to_recover_cost"]


# ---------------------------------------------------------------------------
# Row shape / disclosure
# ---------------------------------------------------------------------------

def test_stage2_rows_record_composition_identity_and_economics():
    scored = score_stage1_sealed_products(
        pack_values=_pack_vector(),
        candidates=[],
        canonical_set_key="setA",
        collector_appeal=deferred_collector_appeal(),
        stage2_candidates=[
            _stage2_candidate("etb", 9, [_card("v", "standard_etb_promo")], 50.0, prices={"v": 12.0})
        ],
    )
    product = scored["products"][0]
    assert product["composition_id"] == "comp-etb"
    assert product["composition_version"] == "stage2-v1"
    assert product["random_pack_count"] == 9
    assert product["guaranteed_component_count"] == 1
    assert product["guaranteed_component_market_value"] == pytest.approx(12.0)
    assert product["accessory_value_included"] is False


def test_accessory_value_is_never_included():
    scored = score_stage1_sealed_products(
        pack_values=_pack_vector(),
        candidates=[],
        canonical_set_key="setA",
        collector_appeal=deferred_collector_appeal(),
        stage2_candidates=[
            _stage2_candidate("etb", 9, [_card("v", "r")], 50.0, prices={"v": 12.0})
        ],
    )
    assert all(p["accessory_value_included"] is False for p in scored["products"])


def test_collector_appeal_stays_set_level_inherited_and_says_so():
    contract = stage2.stage2_scope_contract()
    assert contract["collectorAppealScope"] == (
        "set_level_inherited_guaranteed_promos_not_included"
    )
    assert contract["accessoryValueIncluded"] is False
    assert contract["compositionAuthority"] == "sealed_product_id"


# ---------------------------------------------------------------------------
# Comparison contract
# ---------------------------------------------------------------------------

@pytest.mark.parametrize(
    "family",
    ["elite_trainer_box", "pokemon_center_elite_trainer_box", "enhanced_booster_box"],
)
def test_stage2_within_family_comparison_is_allowed(family):
    assert scope.may_compare_products(family, family) is True


@pytest.mark.parametrize(
    "left,right",
    [
        ("elite_trainer_box", "pokemon_center_elite_trainer_box"),
        ("elite_trainer_box", "booster_box"),
        ("elite_trainer_box", "booster_bundle"),
        ("pokemon_center_elite_trainer_box", "enhanced_booster_box"),
        ("enhanced_booster_box", "booster_box"),
    ],
)
def test_stage2_cross_format_comparison_is_not_allowed(left, right):
    assert scope.may_compare_products(left, right) is False


def test_cross_format_flag_is_still_false_after_stage2():
    assert scope.SEALED_PRODUCT_CROSS_FORMAT_COMPARABLE is False
    assert scope.sealed_product_comparison_scope_contract()["crossFormatComparable"] is False


def test_no_cross_format_ranking_entry_point_exists():
    """A global 'best sealed product' reader must not appear anywhere."""
    from backend.db.repositories import sealed_product_results_repository as repo

    assert not hasattr(repo, "get_best_sealed_product")
    for name in dir(repo):
        if name.startswith("get_") and "best" in name:
            assert "family" in name, f"{name} returns a ranking without family scope"
