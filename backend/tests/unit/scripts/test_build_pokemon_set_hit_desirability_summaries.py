from backend.scripts.build_pokemon_card_desirability_links import DEFAULT_HIT_POLICY_VERSION
from backend.scripts.build_pokemon_set_hit_desirability_summaries import (
    DEFAULT_AGGREGATION_VERSION,
    build_set_summary_row,
    select_latest_complete_composite_score_group,
)


SET_ROW = {
    "id": "00000000-0000-0000-0000-000000000001",
    "name": "Test Set",
    "canonical_key": "testSet",
}

COMPOSITE_METADATA = {
    "fan_popularity_snapshot_id": 9,
    "current_trend_snapshot_ids": [3, 4],
    "score_row_count": 3,
    "coverage_ratio": 1.0,
}


def test_weighted_average_and_missing_scores_are_handled():
    summary = _build_summary()

    assert summary["hit_eligible_card_count"] == 4
    assert summary["scored_hit_eligible_card_count"] == 3
    assert summary["linked_pokemon_count"] == 5
    assert summary["unique_linked_pokemon_count"] == 4
    assert summary["scored_link_count"] == 4
    assert summary["missing_score_count"] == 1
    assert summary["missing_score_reference_ids_json"] == [999]
    assert summary["average_hit_desirability_score"] == 80.0
    assert summary["weighted_average_hit_desirability_score"] == 86.6667


def test_multi_pokemon_card_scores_are_card_based():
    summary = _build_summary()
    top_cards = summary["top_desirable_cards_json"]
    tag_card = next(card for card in top_cards if card["pokemon_canonical_card_id"] == "card-tag")

    assert tag_card["card_desirability_score"] == 60.0
    assert [pokemon["contribution_weight"] for pokemon in tag_card["linked_pokemon"]] == [0.5, 0.5]
    assert summary["multi_pokemon_card_count"] == 1
    assert summary["max_hit_desirability_score"] == 100.0
    assert summary["top_3_hit_desirability_score"] == 86.6667
    assert summary["top_5_hit_desirability_score"] == 86.6667


def test_concentration_depth_and_effective_count():
    summary = _build_summary()

    assert summary["desirability_concentration_top_1_share"] == 0.38461538
    assert summary["desirability_concentration_top_3_share"] == 1.0
    assert summary["desirability_depth_score"] == 26.0
    assert summary["effective_desirable_card_count"] == 2.8644


def test_fallback_links_are_included_and_reported():
    summary = _build_summary()

    assert summary["fallback_link_count"] == 1
    assert summary["diagnostics_json"]["fallback_average_match_confidence"] == 0.85
    fallback_card = next(
        card for card in summary["top_desirable_cards_json"]
        if card["pokemon_canonical_card_id"] == "card-charizard-2"
    )
    assert fallback_card["has_fallback_link"] is True


def test_duplicate_pokemon_appearances_count_per_card():
    summary = _build_summary()
    top_pokemon = summary["top_desirable_pokemon_json"]
    charizard = next(row for row in top_pokemon if row["pokemon_reference_id"] == 6)

    assert charizard["appearance_weight"] == 2.0
    assert charizard["hit_card_count"] == 2
    assert charizard["weighted_score_total"] == 200.0
    assert top_pokemon[0]["pokemon_reference_id"] == 6


def test_select_latest_complete_composite_group_without_mixing_fan_snapshots():
    rows = [
        _score(1, 70, fan_snapshot_id=1, updated_at="2026-06-09T00:00:00+00:00"),
        _score(2, 60, fan_snapshot_id=1, updated_at="2026-06-09T00:00:00+00:00"),
        _score(1, 80, fan_snapshot_id=2, updated_at="2026-06-10T00:00:00+00:00"),
        _score(2, 90, fan_snapshot_id=2, updated_at="2026-06-10T00:00:00+00:00"),
    ]

    selected = select_latest_complete_composite_score_group(
        composite_rows=rows,
        reference_count=2,
        scoring_version="pokemon_desirability_composite_v1",
        min_coverage=1.0,
    )

    assert selected["metadata"]["fan_popularity_snapshot_id"] == 2
    assert {row["pokemon_reference_id"] for row in selected["rows"]} == {1, 2}
    assert {row["fan_popularity_snapshot_id"] for row in selected["rows"]} == {2}


def _build_summary():
    return build_set_summary_row(
        set_row=SET_ROW,
        links=[
            _link("card-charizard", 6, 1.0),
            _link("card-tag", 1, 0.5, link_count=2),
            _link("card-tag", 4, 0.5, link_count=2),
            _link("card-charizard-2", 6, 1.0, match_method="normalized_name_fallback", match_confidence=0.85),
            _link("card-missing", 999, 1.0),
        ],
        cards_by_id=_cards_by_id(),
        scores_by_reference={
            1: _score(1, 80, name="Bulbasaur"),
            4: _score(4, 40, name="Charmander"),
            6: _score(6, 100, name="Charizard"),
        },
        aggregation_version=DEFAULT_AGGREGATION_VERSION,
        hit_policy_version=DEFAULT_HIT_POLICY_VERSION,
        composite_scoring_version="pokemon_desirability_composite_v1",
        composite_metadata=COMPOSITE_METADATA,
        built_at="2026-06-11T00:00:00+00:00",
    )


def _card(card_id, name, number, rarity):
    return {
        "id": card_id,
        "set_id": SET_ROW["id"],
        "name": name,
        "number": number,
        "printed_number": number,
        "rarity": rarity,
        "image_small_url": f"https://example.test/{card_id}.png",
        "image_large_url": f"https://example.test/{card_id}_large.png",
    }


def _cards_by_id():
    return {
        "card-charizard": _card("card-charizard", "Charizard ex", "199", "Special Illustration Rare"),
        "card-tag": _card("card-tag", "Bulbasaur & Charmander-GX", "200", "Rare Holo GX"),
        "card-charizard-2": _card("card-charizard-2", "Charizard VMAX", "201", "Rare Holo VMAX"),
        "card-missing": _card("card-missing", "Missingmon ex", "202", "Double Rare"),
    }


def _link(
    card_id,
    reference_id,
    contribution_weight,
    *,
    link_count=1,
    match_method="national_pokedex_numbers",
    match_confidence=1.0,
):
    return {
        "pokemon_canonical_card_id": card_id,
        "pokemon_reference_id": reference_id,
        "pokedex_number": reference_id,
        "link_count": link_count,
        "contribution_weight": contribution_weight,
        "match_method": match_method,
        "match_confidence": match_confidence,
        "is_hit_eligible": True,
        "hit_policy_version": DEFAULT_HIT_POLICY_VERSION,
    }


def _score(
    reference_id,
    score,
    *,
    name=None,
    fan_snapshot_id=9,
    trend_snapshot_id=3,
    updated_at="2026-06-11T00:00:00+00:00",
):
    return {
        "pokemon_reference_id": reference_id,
        "pokedex_number": reference_id,
        "pokemon_name": name or f"Pokemon {reference_id}",
        "fan_popularity_snapshot_id": fan_snapshot_id,
        "current_trend_snapshot_id": trend_snapshot_id,
        "desirability_score": score,
        "scoring_version": "pokemon_desirability_composite_v1",
        "updated_at": updated_at,
    }
