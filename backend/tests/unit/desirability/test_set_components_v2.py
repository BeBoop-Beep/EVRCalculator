import pytest

from backend.desirability.rarity_buckets import ACCESSIBLE_HIT, PREMIUM_CHASE, classify_rarity
from backend.desirability.set_components import (
    compute_component_scores,
    build_card_facts,
    build_set_coverage_audit,
    collapse_subject_rollups,
    compute_hit_link_category_counts,
    compute_counts,
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


def test_energy_hit_rows_without_links_are_expected_non_pokemon_diagnostics():
    cards = [
        _card(
            "energy",
            "set",
            "Basic Psychic Energy",
            "207/198",
            "Secret Rare",
            supertype="Energy",
            subtypes=["Basic"],
        )
    ]

    facts, warnings = build_card_facts(cards=cards, links=[], scores_by_reference={})
    counts = compute_hit_link_category_counts(facts)

    assert warnings == []
    assert facts[0]["hit_link_category"] == EXPECTED_NON_POKEMON_HIT
    assert counts["expected_non_pokemon_hit_count"] == 1
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


def test_evolving_skies_alt_art_override_promotes_only_exact_card_to_premium_chase():
    set_id = "00000000-0000-0000-0000-000000000002"
    cards = [
        _card(
            "umbreon-full-art",
            set_id,
            "Umbreon V",
            "188/203",
            "Rare Ultra",
            api_id="swsh7-188",
            set_canonical_key="evolvingSkies",
        ),
        _card(
            "umbreon-alt",
            set_id,
            "Umbreon V",
            "189/203",
            "Rare Ultra",
            api_id="swsh7-189",
            set_canonical_key="evolvingSkies",
        ),
    ]
    facts, warnings = build_card_facts(
        cards=cards,
        links=[_link("umbreon-full-art", 197), _link("umbreon-alt", 197)],
        scores_by_reference={197: _score(197, "Umbreon", 75, 80, 70)},
    )
    rollups = collapse_subject_rollups(facts)
    counts = compute_counts(card_facts=facts, subject_rollups=rollups)
    coverage = build_set_coverage_audit(
        set_row={"name": "Evolving Skies", "canonical_key": "evolvingSkies"},
        cards=cards,
        card_facts=facts,
    )

    by_card_id = {fact["pokemon_canonical_card_id"]: fact for fact in facts}
    assert warnings == []
    assert by_card_id["umbreon-full-art"]["rarity_bucket"] == "major_hit"
    assert by_card_id["umbreon-full-art"].get("rarity_override_source") is None
    assert by_card_id["umbreon-alt"]["rarity_bucket"] == PREMIUM_CHASE
    assert by_card_id["umbreon-alt"]["base_rarity_bucket"] == "major_hit"
    assert by_card_id["umbreon-alt"]["rarity_override_source"] == "evolving_skies_alt_art_card_list"
    assert "alternate-art chase card" in by_card_id["umbreon-alt"]["classification_override_reason"]
    assert rollups[0]["best_rarity_bucket"] == PREMIUM_CHASE
    assert counts["rarity_bucket_counts_json"] == {"major_hit": 1, "premium_chase": 1}
    assert coverage["premium_chase_count"] == 1
    assert coverage["major_hit_count"] == 1
    assert coverage["rarity_override_count"] == 1
    assert coverage["top_hit_like_rows"][0]["rarity_override_source"] == "evolving_skies_alt_art_card_list"


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


def _card(
    card_id,
    set_id,
    name,
    printed_number,
    rarity,
    supertype="Pokemon",
    subtypes=None,
    pokedex_numbers=None,
    api_id=None,
    set_canonical_key=None,
):
    return {
        "id": card_id,
        "set_id": set_id,
        "set_canonical_key": set_canonical_key,
        "pokemon_tcg_api_card_id": api_id,
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
