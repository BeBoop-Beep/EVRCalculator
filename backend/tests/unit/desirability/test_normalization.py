import math

from backend.desirability.normalization import (
    assign_desirability_tier,
    match_source_row_to_reference,
    normalize_from_ranks,
    normalize_from_vote_counts,
    normalize_pokemon_name_key,
)


def test_normalize_from_vote_counts_uses_log_scale():
    rows = [
        {"pokemon_name": "Pikachu", "raw_vote_count": 99, "source_name": "favoritepokemon"},
        {"pokemon_name": "Bulbasaur", "raw_vote_count": 9, "source_name": "favoritepokemon"},
    ]

    scores = normalize_from_vote_counts(rows)

    assert scores[0]["pokemon_name"] == "Pikachu"
    assert scores[0]["normalized_score"] == 100.0
    expected = 100 * math.log1p(9) / math.log1p(99)
    assert scores[1]["normalized_score"] == round(expected, 4)
    assert scores[1]["confidence"] == "high"


def test_normalize_from_ranks_spreads_scores_across_ranked_rows():
    rows = [
        {"pokemon_name": "Bulbasaur", "raw_rank": 1},
        {"pokemon_name": "Charmander", "raw_rank": 2},
        {"pokemon_name": "Squirtle", "raw_rank": 3},
    ]

    scores = normalize_from_ranks(rows)

    assert [score["normalized_score"] for score in scores] == [100.0, 50.0, 0.0]
    assert [score["normalized_rank"] for score in scores] == [1, 2, 3]
    assert all(score["confidence"] == "medium" for score in scores)


def test_assign_desirability_tier_boundaries():
    assert assign_desirability_tier(100) == "S"
    assert assign_desirability_tier(90) == "S"
    assert assign_desirability_tier(89) == "A"
    assert assign_desirability_tier(75) == "A"
    assert assign_desirability_tier(74) == "B"
    assert assign_desirability_tier(55) == "B"
    assert assign_desirability_tier(54) == "C"
    assert assign_desirability_tier(35) == "C"
    assert assign_desirability_tier(34) == "D"
    assert assign_desirability_tier(15) == "D"
    assert assign_desirability_tier(14) == "F"


def test_name_matching_normalizes_accents_punctuation_and_symbols():
    references = [
        {"id": 1, "pokedex_number": 29, "canonical_name": "nidoran-f", "display_name": "Nidoran F"},
        {"id": 2, "pokedex_number": 83, "canonical_name": "farfetchd", "display_name": "Farfetch'd"},
        {"id": 3, "pokedex_number": 122, "canonical_name": "mr-mime", "display_name": "Mr. Mime"},
        {"id": 4, "pokedex_number": 865, "canonical_name": "sirfetchd", "display_name": "Sirfetchd"},
    ]

    assert normalize_pokemon_name_key("Pokémon") == "pokemon"
    assert match_source_row_to_reference({"pokemon_name": "Nidoran♀"}, references)["id"] == 1
    assert match_source_row_to_reference({"pokemon_name": "Farfetch’d"}, references)["id"] == 2
    assert match_source_row_to_reference({"pokemon_name": "Mr Mime"}, references)["id"] == 3
    assert match_source_row_to_reference({"pokemon_name": "Sirfetch’d"}, references)["id"] == 4


def test_name_matching_prefers_pokedex_number():
    references = [
        {"id": 25, "pokedex_number": 25, "canonical_name": "pikachu", "display_name": "Pikachu"},
    ]

    match = match_source_row_to_reference({"pokedex_number": 25, "pokemon_name": "Wrong Name"}, references)

    assert match["id"] == 25


def test_name_matching_handles_pokeapi_default_form_suffixes():
    references = [
        {"id": 778, "pokedex_number": 778, "canonical_name": "mimikyu-disguised", "display_name": "Mimikyu Disguised"},
        {"id": 875, "pokedex_number": 875, "canonical_name": "eiscue-ice", "display_name": "Eiscue Ice"},
        {"id": 876, "pokedex_number": 876, "canonical_name": "indeedee-male", "display_name": "Indeedee Male"},
        {"id": 902, "pokedex_number": 902, "canonical_name": "basculegion-male", "display_name": "Basculegion Male"},
        {"id": 678, "pokedex_number": 678, "canonical_name": "meowstic-male", "display_name": "Meowstic Male"},
        {"id": 916, "pokedex_number": 916, "canonical_name": "oinkologne-male", "display_name": "Oinkologne Male"},
    ]

    assert match_source_row_to_reference({"pokemon_name": "Mimikyu"}, references)["id"] == 778
    assert match_source_row_to_reference({"pokemon_name": "Eiscue"}, references)["id"] == 875
    assert match_source_row_to_reference({"pokemon_name": "Indeedee"}, references)["id"] == 876
    assert match_source_row_to_reference({"pokemon_name": "Basculegion"}, references)["id"] == 902
    assert match_source_row_to_reference({"pokemon_name": "Meowstic"}, references)["id"] == 678
    assert match_source_row_to_reference({"pokemon_name": "Oinkologne"}, references)["id"] == 916


def test_name_matching_handles_type_null_and_nidoran_gender_words():
    references = [
        {"id": 772, "pokedex_number": 772, "canonical_name": "type-null", "display_name": "Type Null"},
        {"id": 29, "pokedex_number": 29, "canonical_name": "nidoran-f", "display_name": "Nidoran F"},
        {"id": 32, "pokedex_number": 32, "canonical_name": "nidoran-m", "display_name": "Nidoran M"},
    ]

    assert match_source_row_to_reference({"pokemon_name": "Type: Null"}, references)["id"] == 772
    assert match_source_row_to_reference({"pokemon_name": "Nidoran female"}, references)["id"] == 29
    assert match_source_row_to_reference({"pokemon_name": "Nidoran male"}, references)["id"] == 32
