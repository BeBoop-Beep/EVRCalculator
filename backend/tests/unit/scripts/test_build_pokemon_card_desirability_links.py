from backend.scripts.build_pokemon_card_desirability_links import (
    DEFAULT_HIT_POLICY_VERSION,
    build_link_rows,
    find_fallback_reference_match,
    is_hit_eligible_card,
)


class FakeConfig:
    RARITY_MAPPING = {
        "common": "common",
        "rare": "rare",
        "double rare": "hits",
        "illustration rare": "hits",
        "special illustration rare": "hits",
        "hyper rare": "hits",
        "ace spec rare": "hits",
    }
    CHASE_METRICS_EXCLUDED_RARITIES = frozenset()


REFERENCES = [
    {"id": 1, "pokedex_number": 1, "canonical_name": "bulbasaur", "display_name": "Bulbasaur"},
    {"id": 4, "pokedex_number": 4, "canonical_name": "charmander", "display_name": "Charmander"},
    {"id": 1017, "pokedex_number": 1017, "canonical_name": "ogerpon", "display_name": "Ogerpon"},
]


def test_primary_pokedex_number_linking():
    result = build_link_rows(
        cards=[_card("card-1", "Bulbasaur", [1], "Double Rare")],
        references=REFERENCES,
        config_map={"testSet": FakeConfig},
        hit_policy_version=DEFAULT_HIT_POLICY_VERSION,
    )

    assert len(result["rows"]) == 1
    row = result["rows"][0]
    assert row["pokemon_canonical_card_id"] == "card-1"
    assert row["pokemon_reference_id"] == 1
    assert row["pokedex_number"] == 1
    assert row["link_position"] == 1
    assert row["link_count"] == 1
    assert row["contribution_weight"] == 1.0
    assert row["match_method"] == "national_pokedex_numbers"
    assert row["match_confidence"] == 1.0
    assert row["is_hit_eligible"] is True
    assert result["diagnostics"]["cards_linked_by_pokedex_number"] == 1


def test_multi_pokemon_cards_get_equal_contribution_weights():
    result = build_link_rows(
        cards=[_card("card-tag", "Bulbasaur & Charmander-GX", [1, 4], "Double Rare")],
        references=REFERENCES,
        config_map={"testSet": FakeConfig},
        hit_policy_version=DEFAULT_HIT_POLICY_VERSION,
    )

    assert len(result["rows"]) == 2
    assert [row["link_position"] for row in result["rows"]] == [1, 2]
    assert [row["link_count"] for row in result["rows"]] == [2, 2]
    assert [row["contribution_weight"] for row in result["rows"]] == [0.5, 0.5]
    assert result["diagnostics"]["multi_pokemon_cards_linked"] == 1


def test_non_pokemon_rows_are_excluded_even_when_rarity_is_hit_like():
    result = build_link_rows(
        cards=[
            _card(
                "trainer-1",
                "Master Ball",
                [],
                "ACE SPEC Rare",
                supertype="Trainer",
                subtypes=["Item", "ACE SPEC"],
            )
        ],
        references=REFERENCES,
        config_map={"testSet": FakeConfig},
        hit_policy_version=DEFAULT_HIT_POLICY_VERSION,
    )

    assert result["rows"] == []
    assert result["diagnostics"]["total_non_pokemon_cards_skipped"] == 1
    assert result["diagnostics"]["total_hit_rarity_cards"] == 1
    assert result["diagnostics"]["excluded_non_pokemon_hit_rarity_rows"] == 1


def test_hit_eligibility_requires_pokemon_supertype_and_hit_rarity():
    assert is_hit_eligible_card(_card("hit", "Bulbasaur", [1], "Double Rare"), {"testSet": FakeConfig}) is True
    assert is_hit_eligible_card(_card("common", "Bulbasaur", [1], "Common"), {"testSet": FakeConfig}) is False
    assert (
        is_hit_eligible_card(
            _card("trainer", "Boss's Orders", [], "Special Illustration Rare", supertype="Trainer"),
            {"testSet": FakeConfig},
        )
        is False
    )


def test_safe_fallback_name_matching_for_missing_pokedex_number():
    result = build_link_rows(
        cards=[_card("ogerpon-1", "Teal Mask Ogerpon ex", [], "Special Illustration Rare")],
        references=REFERENCES,
        config_map={"testSet": FakeConfig},
        hit_policy_version=DEFAULT_HIT_POLICY_VERSION,
    )

    assert len(result["rows"]) == 1
    row = result["rows"][0]
    assert row["pokemon_reference_id"] == 1017
    assert row["match_method"] == "normalized_name_fallback"
    assert row["match_confidence"] == 0.85
    assert result["diagnostics"]["cards_linked_by_fallback_name"] == 1


def test_ambiguous_fallback_does_not_create_link():
    ambiguous_references = [
        {"id": 10, "pokedex_number": 10, "canonical_name": "alpha", "display_name": "Alpha"},
        {"id": 11, "pokedex_number": 11, "canonical_name": "gamma", "display_name": "Gamma"},
    ]
    result = build_link_rows(
        cards=[_card("ambiguous", "Alpha Gamma ex", [], "Double Rare")],
        references=ambiguous_references,
        config_map={"testSet": FakeConfig},
        hit_policy_version=DEFAULT_HIT_POLICY_VERSION,
    )

    assert result["rows"] == []
    assert result["diagnostics"]["ambiguous_fallback_candidates"] == 1
    assert result["diagnostics"]["unmatched_pokemon_cards_missing_pokedex_numbers"] == 0


def test_duplicate_pokedex_numbers_do_not_generate_duplicate_upsert_keys():
    result = build_link_rows(
        cards=[_card("dupe", "Bulbasaur", [1, 1], "Double Rare")],
        references=REFERENCES,
        config_map={"testSet": FakeConfig},
        hit_policy_version=DEFAULT_HIT_POLICY_VERSION,
    )

    keys = {
        (row["pokemon_canonical_card_id"], row["pokemon_reference_id"])
        for row in result["rows"]
    }
    assert len(result["rows"]) == 1
    assert len(keys) == len(result["rows"])


def test_find_fallback_reference_match_prefers_single_longest_candidate():
    references = [
        {
            "id": 1,
            "pokedex_number": 1,
            "canonical_name": "iron",
            "display_name": "Iron",
            "match_keys": ["iron"],
        },
        {
            "id": 992,
            "pokedex_number": 992,
            "canonical_name": "iron-hands",
            "display_name": "Iron Hands",
            "match_keys": ["iron hands"],
        },
    ]

    match = find_fallback_reference_match(_card("iron-hands", "Iron Hands ex", [], "Double Rare"), references)

    assert match["status"] == "matched"
    assert match["reference"]["id"] == 992


def _card(
    card_id,
    name,
    pokedex_numbers,
    rarity,
    *,
    supertype="Pokémon",
    subtypes=None,
):
    return {
        "id": card_id,
        "set_id": "set-1",
        "set_name": "Test Set",
        "set_canonical_key": "testSet",
        "name": name,
        "supertype": supertype,
        "subtypes": subtypes or ["Basic"],
        "rarity": rarity,
        "number": "1",
        "national_pokedex_numbers": pokedex_numbers,
    }
