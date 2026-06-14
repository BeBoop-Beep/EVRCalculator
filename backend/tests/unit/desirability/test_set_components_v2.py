import pytest

from backend.desirability.rarity_buckets import ACCESSIBLE_HIT, PREMIUM_CHASE, classify_rarity
from backend.desirability.set_components import (
    compute_component_scores,
    build_card_facts,
    collapse_subject_rollups,
    compute_hit_link_category_counts,
    EXPECTED_NON_POKEMON_HIT,
    TRUE_MISSING_LINK,
    UNMATCHED_POKEMON_HIT,
)


def test_duplicate_charizard_rows_collapse_and_sir_represents_subject():
    facts, warnings = build_card_facts(
        cards=_cards(),
        links=_links(),
        scores_by_reference=_scores_by_reference(),
    )
    rollups = collapse_subject_rollups(facts)
    charizard = next(row for row in rollups if row["subject_name"] == "Charizard")

    assert warnings == []
    assert len([row for row in rollups if row["subject_name"] == "Charizard"]) == 1
    assert charizard["card_count"] == 3
    assert charizard["representative_card_name"] == "Charizard ex"
    assert charizard["representative_printed_number"] == "199/165"
    assert charizard["representative_rarity"] == "Special Illustration Rare"
    assert charizard["best_rarity_bucket"] == PREMIUM_CHASE


def test_rarity_bucket_policy_classifies_premium_and_accessible():
    assert classify_rarity("Special Illustration Rare").bucket == PREMIUM_CHASE
    assert classify_rarity("SIR").bucket == PREMIUM_CHASE
    assert classify_rarity("Double Rare").bucket == ACCESSIBLE_HIT


def test_older_chase_rarity_labels_classify_deterministically():
    premium_labels = ["Rare Holo Star", "Gold Star", "Rare Shining", "Shining", "Secret Rare", "Rare Secret"]
    for label in premium_labels:
        assert classify_rarity(label).bucket == PREMIUM_CHASE

    assert classify_rarity("Classic Collection").bucket == ACCESSIBLE_HIT
    assert classify_rarity("Rare Holo").bucket == ACCESSIBLE_HIT
    assert classify_rarity("Rare Holo").bucket != PREMIUM_CHASE


def test_non_pokemon_hit_rows_without_links_are_diagnostic_not_scary_warnings():
    cards = [
        _card("trainer", "set", "Boss's Orders", "001/100", "Rare Holo", supertype="Trainer", subtypes=["Supporter"]),
        _card("item", "set", "Rare Candy", "002/100", "Double Rare", supertype="Trainer", subtypes=["Item"]),
        _card("energy", "set", "Basic Fire Energy", "003/100", "Rare Holo", supertype="Energy", subtypes=["Basic Energy"]),
    ]

    facts, warnings = build_card_facts(cards=cards, links=[], scores_by_reference={})
    counts = compute_hit_link_category_counts(facts)

    assert warnings == []
    assert {fact["hit_link_category"] for fact in facts} == {EXPECTED_NON_POKEMON_HIT}
    assert counts["expected_non_pokemon_hit_count"] == 3
    assert counts["unmatched_pokemon_hit_count"] == 0
    assert counts["true_missing_link_count"] == 0


def test_pokemon_hit_row_without_link_is_actionable_missing_link():
    cards = [
        _card("pokemon-no-pokedex", "set", "Mysterymon ex", "001/100", "Special Illustration Rare", subtypes=["ex"]),
        _card(
            "pokemon-with-pokedex",
            "set",
            "Charizard",
            "002/100",
            "Rare Holo",
            pokedex_numbers=[6],
        ),
    ]

    facts, warnings = build_card_facts(cards=cards, links=[], scores_by_reference={})
    counts = compute_hit_link_category_counts(facts)

    assert len(warnings) == 2
    categories = {fact["card_name"]: fact["hit_link_category"] for fact in facts}
    assert categories["Mysterymon ex"] == UNMATCHED_POKEMON_HIT
    assert categories["Charizard"] == TRUE_MISSING_LINK
    assert counts["unmatched_pokemon_hit_count"] == 1
    assert counts["true_missing_link_count"] == 1


def test_v2_pokedex_fallback_links_legacy_hit_when_link_table_skipped_it():
    cards = [_card("classic-zard", "set", "Charizard", "4/102", "Rare Holo", pokedex_numbers=[6])]

    facts, warnings = build_card_facts(
        cards=cards,
        links=[],
        scores_by_reference=_scores_by_reference(),
        references_by_pokedex={6: {"id": 6, "pokedex_number": 6, "display_name": "Charizard"}},
    )

    assert warnings == []
    assert facts[0]["subject_name"] == "Charizard"
    assert facts[0]["subject_key"] == "ref:6"


def test_component_outputs_are_bounded_and_weighted_formula_matches():
    facts, _ = build_card_facts(
        cards=_cards(),
        links=_links(),
        scores_by_reference=_scores_by_reference(),
    )
    rollups = collapse_subject_rollups(facts)

    result = compute_component_scores(
        subject_rollups=rollups,
        card_facts=facts,
        set_config={"GOD_PACK_CONFIG": {"enabled": False}, "DEMI_GOD_PACK_CONFIG": {"enabled": False}},
    )

    components = [
        result["chase_subject_strength"],
        result["chase_subject_depth"],
        result["accessible_favorite_hits"],
        result["special_pack_chase_appeal"],
        result["set_desirability_score"],
    ]
    assert all(0 <= value <= 100 for value in components)
    expected = (
        0.40 * result["chase_subject_strength"]
        + 0.25 * result["chase_subject_depth"]
        + 0.20 * result["accessible_favorite_hits"]
        + 0.15 * result["special_pack_chase_appeal"]
    )
    assert result["set_desirability_score"] == pytest.approx(round(expected, 4))


def test_no_data_returns_safe_values_and_warnings():
    result = compute_component_scores(subject_rollups=[], card_facts=[], set_config=None)

    assert result["set_desirability_score"] == 0.0
    assert result["chase_subject_strength"] == 0.0
    assert result["warnings_json"]


def test_god_and_demi_detection_is_deterministic_from_config():
    facts, _ = build_card_facts(
        cards=_cards(),
        links=_links(),
        scores_by_reference=_scores_by_reference(),
    )
    rollups = collapse_subject_rollups(facts)
    config = {
        "GOD_PACK_CONFIG": {
            "enabled": True,
            "pull_rate": 1 / 2000,
            "strategy": {
                "type": "fixed",
                "cards": [{"name": "Charizard ex", "number": "199/165", "rarity": "Special Illustration Rare"}],
            },
        },
        "DEMI_GOD_PACK_CONFIG": {
            "enabled": True,
            "pull_rate": 3 / 2000,
            "strategy": {"type": "random", "rules": {"rarities": {"Double Rare": {"count": 3}}}},
        },
    }

    result = compute_component_scores(subject_rollups=rollups, card_facts=facts, set_config=config)
    mechanics = result["special_pack_summary_json"]["mechanics"]

    assert result["special_pack_chase_appeal"] > 0
    assert [row["enabled"] for row in mechanics] == [True, True]
    assert mechanics[0]["subject_quality_source"] == "direct_special_pack_composition"
    assert mechanics[1]["subject_quality_source"] == "direct_special_pack_composition"


def test_specialty_status_alone_does_not_score_special_pack_appeal():
    facts, _ = build_card_facts(
        cards=_cards(),
        links=_links(),
        scores_by_reference=_scores_by_reference(),
    )
    rollups = collapse_subject_rollups(facts)
    result = compute_component_scores(
        subject_rollups=rollups,
        card_facts=facts,
        set_config={"set_type": "specialty", "PRICE_ENDPOINTS": {"Booster Box Price": None}},
    )

    assert result["special_pack_chase_appeal"] == 0.0


def _cards():
    set_id = "00000000-0000-0000-0000-000000000001"
    return [
        _card("sir-zard", set_id, "Charizard ex", "199/165", "Special Illustration Rare"),
        _card("ur-zard", set_id, "Charizard ex", "183/165", "Ultra Rare"),
        _card("dr-zard", set_id, "Charizard ex", "006/165", "Double Rare"),
        _card("blast", set_id, "Blastoise ex", "200/165", "Special Illustration Rare"),
        _card("psyduck", set_id, "Psyduck", "175/165", "Illustration Rare"),
    ]


def _card(card_id, set_id, name, printed_number, rarity, supertype="Pokemon", subtypes=None, pokedex_numbers=None):
    return {
        "id": card_id,
        "set_id": set_id,
        "name": name,
        "supertype": supertype,
        "subtypes": subtypes if subtypes is not None else (["ex"] if name.endswith("ex") else []),
        "rarity": rarity,
        "number": printed_number.split("/")[0],
        "printed_number": printed_number,
        "national_pokedex_numbers": pokedex_numbers or [],
    }


def _links():
    return [
        _link("sir-zard", 6),
        _link("ur-zard", 6),
        _link("dr-zard", 6),
        _link("blast", 9),
        _link("psyduck", 54),
    ]


def _link(card_id, reference_id):
    return {
        "pokemon_canonical_card_id": card_id,
        "pokemon_reference_id": reference_id,
        "pokedex_number": reference_id,
    }


def _scores_by_reference():
    return {
        6: _score(6, "Charizard", 98, 99, 95),
        9: _score(9, "Blastoise", 80, 78, 85),
        54: _score(54, "Psyduck", 63, 66, 55),
    }


def _score(reference_id, name, desirability, fan, trend):
    return {
        "pokemon_reference_id": reference_id,
        "pokedex_number": reference_id,
        "pokemon_name": name,
        "desirability_score": desirability,
        "fan_popularity_score": fan,
        "current_trend_score": trend,
    }
