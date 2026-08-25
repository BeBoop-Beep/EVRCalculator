"""Sealed Market product-family submarkets.

Every assertion here guards one of the ways a submarket index could lie:
classifying the wrong SKUs into a family, letting a product entering the
universe manufacture a return, deriving a child index from the parent instead
of from its own constituents, double-counting Pokémon Center ETBs inside the
standard ETB segment, or quietly moving the parent by adding children.
"""

from __future__ import annotations

import pytest

from backend.db.services.pokemon_global_sealed_market_service import (
    build_global_sealed_market,
    build_global_sealed_segments,
    collect_global_sealed_products,
)
from backend.db.services.pokemon_market_index_service import build_market_overview
from backend.domain.pokemon.sealed_market_segments import (
    RESIDUAL_PRODUCT_FAMILIES,
    RESIDUAL_SEGMENT_KEY,
    SEALED_SEGMENT_DEFINITIONS,
    partition_products_by_segment,
    segment_definition_metadata,
    segment_key_for_family,
)
from backend.domain.pokemon.sealed_product_classifier import (
    OVERVIEW_FAMILIES,
    classify_sealed_product,
)

DAYS = ["2026-01-01", "2026-01-02", "2026-01-03", "2026-01-04"]


def product(product_id, family, prices, *, start=0):
    """One sealed SKU with a daily observed history."""
    return {
        "sealedProductId": product_id,
        "name": product_id,
        "productFamily": family,
        "productFamilyLabel": family,
        "variantLabel": None,
        "history": [
            {"date": DAYS[start + offset], "marketPrice": price, "source": "test", "isObserved": True}
            for offset, price in enumerate(prices)
        ],
    }


def payload(products):
    return {"products": products}


# Two of every published family so each segment has a real common cohort, plus
# a residual family (half booster box) that no segment claims.
def universe():
    return [
        product("bb-1", "booster_box", [100.0, 110.0, 121.0, 121.0]),
        product("bb-2", "booster_box", [200.0, 220.0, 242.0, 242.0]),
        product("etb-1", "elite_trainer_box", [50.0, 50.0, 45.0, 45.0]),
        product("etb-2", "elite_trainer_box", [60.0, 60.0, 54.0, 54.0]),
        product("pc-1", "pokemon_center_elite_trainer_box", [90.0, 99.0, 99.0, 99.0]),
        product("pc-2", "pokemon_center_elite_trainer_box", [110.0, 121.0, 121.0, 121.0]),
        product("bun-1", "booster_bundle", [25.0, 25.0, 25.0, 25.0]),
        product("bun-2", "booster_bundle", [35.0, 35.0, 35.0, 35.0]),
        product("loose-1", "loose_booster_pack", [5.0, 5.5, 5.5, 5.5]),
        product("sleeved-1", "sleeved_booster_pack", [7.0, 7.7, 7.7, 7.7]),
        product("half-1", "half_booster_box", [80.0, 80.0, 80.0, 80.0]),
    ]


def build(products=None, *, market_date="2026-01-04"):
    products = universe() if products is None else products
    payloads = [payload(products)]
    total = build_global_sealed_market(payloads, market_date=market_date)
    return total, build_global_sealed_segments(payloads, market_date=market_date, total=total)


# --- classification -------------------------------------------------------

def test_segment_membership_comes_from_the_canonical_classifier():
    # The classifier decides the family; this module only groups families.
    assert classify_sealed_product("Scarlet & Violet Booster Box")["productFamily"] == "booster_box"
    assert classify_sealed_product("Obsidian Flames Elite Trainer Box")["productFamily"] == "elite_trainer_box"
    assert (classify_sealed_product("Pokemon Center Elite Trainer Box")["productFamily"]
            == "pokemon_center_elite_trainer_box")

    assert segment_key_for_family("booster_box") == "boosterBox"
    assert segment_key_for_family("elite_trainer_box") == "eliteTrainerBox"
    assert segment_key_for_family("pokemon_center_elite_trainer_box") == "pokemonCenterEliteTrainerBox"
    assert segment_key_for_family("booster_bundle") == "boosterBundle"
    assert segment_key_for_family("loose_booster_pack") == "packs"
    assert segment_key_for_family("sleeved_booster_pack") == "packs"
    # Residual families belong to the parent but to no published segment.
    assert segment_key_for_family("half_booster_box") is None
    assert segment_key_for_family("enhanced_booster_box") is None


def test_published_segments_are_disjoint_and_cover_every_eligible_family_once():
    seen: dict[str, str] = {}
    for definition in SEALED_SEGMENT_DEFINITIONS:
        for family in definition["productFamilies"]:
            assert family not in seen, f"{family} claimed by two segments"
            assert family in OVERVIEW_FAMILIES, f"{family} is not overview-eligible"
            seen[family] = str(definition["key"])
    # Everything eligible is either published or an explicit residual — never
    # silently dropped.
    assert set(seen) | set(RESIDUAL_PRODUCT_FAMILIES) == set(OVERVIEW_FAMILIES)
    assert set(seen) & set(RESIDUAL_PRODUCT_FAMILIES) == set()


def test_partition_always_reports_every_segment_even_when_empty():
    grouped = partition_products_by_segment([product("bb-1", "booster_box", [10.0])])
    assert set(grouped) == {str(d["key"]) for d in SEALED_SEGMENT_DEFINITIONS} | {RESIDUAL_SEGMENT_KEY}
    assert [p["sealedProductId"] for p in grouped["boosterBox"]] == ["bb-1"]
    assert grouped["eliteTrainerBox"] == []


# --- Booster Box segment (spec 23) ---------------------------------------

def test_booster_box_segment_contains_only_booster_box_skus():
    _total, published = build()
    segment = published["segments"]["boosterBox"]
    assert segment["available"] is True
    # 2 Booster Boxes, and nothing else — ETBs are 50+60, PC ETBs 90+110.
    assert segment["metadata"]["eligibleProductCount"] == 2
    # Day-1 basket is exactly the two Booster Boxes.
    assert segment["trackedValueHistory"][0]["value"] == pytest.approx(300.0)
    assert segment["basketValue"] == pytest.approx(363.0)
    assert segment["productFamilies"] == ["booster_box"]


def test_booster_box_index_tracks_its_own_common_cohort_price_movement():
    _total, published = build()
    segment = published["segments"]["boosterBox"]
    # 300 -> 330 -> 363 -> 363 is +10%, +10%, flat against base 100.
    levels = [round(point["indexValue"], 4) for point in segment["history"]]
    assert levels == [100.0, 110.0, 121.0, 121.0]
    assert segment["indexValue"] == pytest.approx(121.0)


def test_a_product_entering_moves_tracked_value_but_not_the_index():
    # A third Booster Box appears on day 3 at $500. Tracked Value must jump;
    # the index must not, because entry is neutralized at the transition.
    products = [p for p in universe() if p["productFamily"] == "booster_box"]
    products.append(product("bb-3", "booster_box", [500.0, 500.0], start=2))
    _total, published = build(products)
    segment = published["segments"]["boosterBox"]

    tracked = {point["date"]: point["value"] for point in segment["trackedValueHistory"]}
    assert tracked["2026-01-02"] == pytest.approx(330.0)
    assert tracked["2026-01-03"] == pytest.approx(863.0)  # 121 + 242 + 500
    # The index still reports only the common cohort's real +10% move, so the
    # $500 arrival adds nothing to price performance on the day it enters.
    index_by_date = {point["date"]: point["indexValue"] for point in segment["history"]}
    assert round(index_by_date["2026-01-02"], 4) == 110.0
    assert round(index_by_date["2026-01-03"], 4) == 121.0


# --- ETB / PC ETB separation (spec 24) -----------------------------------

def test_pokemon_center_etbs_are_their_own_segment_and_never_counted_in_standard_etbs():
    _total, published = build()
    etb = published["segments"]["eliteTrainerBox"]
    pc = published["segments"]["pokemonCenterEliteTrainerBox"]

    assert etb["metadata"]["eligibleProductCount"] == 2
    assert pc["metadata"]["eligibleProductCount"] == 2
    # Standard ETBs fell 50+60 -> 45+54; PC ETBs rose 90+110 -> 99+121. If PC
    # ETBs leaked into the ETB segment its index could not be below base.
    assert etb["indexValue"] == pytest.approx(90.0)
    assert pc["indexValue"] == pytest.approx(110.0)
    assert etb["basketValue"] == pytest.approx(99.0)
    assert pc["basketValue"] == pytest.approx(220.0)
    # No published segment claims both families.
    assert etb["productFamilies"] == ["elite_trainer_box"]
    assert pc["productFamilies"] == ["pokemon_center_elite_trainer_box"]


# --- Packs composite (spec 25) -------------------------------------------

def test_packs_is_an_explicitly_declared_loose_plus_sleeved_composite():
    definition = next(d for d in SEALED_SEGMENT_DEFINITIONS if d["key"] == "packs")
    assert definition["isComposite"] is True
    assert set(definition["productFamilies"]) == {"loose_booster_pack", "sleeved_booster_pack"}
    assert "loose" in definition["definition"].lower()
    assert "sleeved" in definition["definition"].lower()

    _total, published = build()
    packs = published["segments"]["packs"]
    assert packs["metadata"]["eligibleProductCount"] == 2
    assert packs["basketValue"] == pytest.approx(13.2)  # 5.5 + 7.7
    # Both constituents rose 10% on day 2 and held.
    assert packs["indexValue"] == pytest.approx(110.0)
    assert packs["isComposite"] is True


def test_every_non_composite_segment_declares_exactly_one_family():
    for definition in SEALED_SEGMENT_DEFINITIONS:
        if not definition["isComposite"]:
            assert len(definition["productFamilies"]) == 1, definition["key"]


# --- Total Sealed reconciliation (spec 26) -------------------------------

def test_published_segments_plus_residual_reconcile_to_the_parent():
    total, published = build()
    reconciliation = published["reconciliation"]
    published_value = reconciliation["publishedSegmentBasketValue"]
    residual_value = reconciliation["residual"]["basketValue"]
    assert reconciliation["parentBasketValue"] == pytest.approx(total["basketValue"])
    assert published_value + residual_value == pytest.approx(total["basketValue"], abs=0.02)
    # Every eligible product lands in exactly one bucket.
    assert (reconciliation["segmentedProductCount"] + reconciliation["residual"]["productCount"]
            == reconciliation["eligibleProductCount"] == 11)


def test_the_residual_is_reported_rather_than_folded_into_a_published_segment():
    _total, published = build()
    residual = published["reconciliation"]["residual"]
    assert residual["productFamilies"] == ["half_booster_box"]
    assert residual["basketValue"] == pytest.approx(80.0)
    # And it is NOT a selectable market.
    assert RESIDUAL_SEGMENT_KEY not in published["segments"]
    assert segment_definition_metadata()["residual"]["key"] == RESIDUAL_SEGMENT_KEY


def test_segments_are_built_from_their_own_skus_not_sliced_from_the_parent():
    total, published = build()
    # The parent rose overall; standard ETBs fell. A child derived by filtering
    # or scaling the parent index could not disagree with it in direction.
    assert total["indexValue"] > 100.0
    assert published["segments"]["eliteTrainerBox"]["indexValue"] < 100.0
    # And each child is reproducible from its own constituents alone.
    products = [p for p in universe() if p["productFamily"] == "elite_trainer_box"]
    standalone = build_global_sealed_market([payload(products)], market_date="2026-01-04")
    assert standalone["indexValue"] == pytest.approx(
        published["segments"]["eliteTrainerBox"]["indexValue"]
    )
    assert standalone["basketValue"] == pytest.approx(
        published["segments"]["eliteTrainerBox"]["basketValue"]
    )


# --- parent regression (spec 28) -----------------------------------------

def test_publishing_segments_does_not_move_the_parent_by_a_cent():
    payloads = [payload(universe())]
    before = build_global_sealed_market(payloads, market_date="2026-01-04")
    published = build_global_sealed_segments(payloads, market_date="2026-01-04", total=before)
    after = build_global_sealed_market(payloads, market_date="2026-01-04")
    assert before == after
    for key in ("basketValue", "indexValue", "historyStartDate", "trend", "history"):
        assert published["segments"]["total"][key] == before[key]
    assert published["segments"]["total"]["metadata"] == before["metadata"]


def test_the_parent_universe_and_the_segment_universe_are_the_same_collection():
    payloads = [payload(universe())]
    products, _sets = collect_global_sealed_products(payloads, market_date="2026-01-04")
    grouped = partition_products_by_segment(products)
    assert sum(len(value) for value in grouped.values()) == len(products)


# --- an unavailable segment ----------------------------------------------

def test_a_family_with_no_constituents_is_published_unavailable_not_as_a_zero():
    products = [p for p in universe() if p["productFamily"] == "booster_box"]
    _total, published = build(products)
    empty = published["segments"]["eliteTrainerBox"]
    assert empty["available"] is False
    assert empty["unavailableReason"]
    assert "basketValue" not in empty
    assert "indexValue" not in empty
    assert published["segments"]["boosterBox"]["available"] is True


# --- serialization / contract --------------------------------------------

def test_the_segmentation_publishes_its_own_definition():
    metadata = segment_definition_metadata()
    assert metadata["contractVersion"] == "pokemon-sealed-segments-v1"
    assert metadata["disjoint"] is True
    assert [entry["key"] for entry in metadata["segments"]] == [
        "boosterBox", "eliteTrainerBox", "pokemonCenterEliteTrainerBox", "boosterBundle", "packs",
    ]
    assert [entry["label"] for entry in metadata["segments"]] == [
        "Booster Boxes", "Elite Trainer Boxes", "Pokémon Center ETBs", "Booster Bundles", "Packs",
    ]
    assert all(entry["definition"] for entry in metadata["segments"])


def test_the_segment_payload_is_json_serializable_and_carries_the_required_fields():
    import json

    _total, published = build()
    json.dumps(published)  # must not raise
    for definition in SEALED_SEGMENT_DEFINITIONS:
        segment = published["segments"][str(definition["key"])]
        for field in ("key", "label", "available", "basketValue", "indexValue",
                      "historyStartDate", "familyChanges", "basketChanges",
                      "trackedValueHistory", "trend", "metadata"):
            assert field in segment, f"{definition['key']} is missing {field}"
        assert segment["metadata"]["eligibleProductCount"] is not None
        assert segment["metadata"]["trackingStart"]
