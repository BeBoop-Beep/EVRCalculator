from backend.desirability.favoritepokemon_scraper import (
    _parse_table_row_text,
    extract_rows_from_candidates,
)


def test_extract_rows_from_visible_ranked_candidate_text():
    candidates = [
        {"selector": "li", "text": "#1 Pikachu 1,234 votes"},
        {"selector": "li", "text": "About this project"},
    ]

    rows = extract_rows_from_candidates(candidates, "https://favoritepokemon.vercel.app/#/stats")

    assert len(rows) == 1
    assert rows[0]["pokemon_name"] == "Pikachu"
    assert rows[0]["raw_rank"] == 1
    assert rows[0]["raw_vote_count"] == 1234
    assert rows[0]["extraction_confidence"] == "medium"


def test_extract_rows_from_public_rank_vote_block():
    candidates = [
        {
            "selector": "section div",
            "text": "RANK POKÉMON VOTES #1 Mimikyu 4244 #2 Gengar 2986 #3 Sylveon 2796",
        }
    ]

    rows = extract_rows_from_candidates(candidates, "https://favoritepokemon.vercel.app/#/stats")

    assert [(row["raw_rank"], row["pokemon_name"], row["raw_vote_count"]) for row in rows] == [
        (1, "Mimikyu", 4244),
        (2, "Gengar", 2986),
        (3, "Sylveon", 2796),
    ]
    assert all(row["extraction_confidence"] == "high" for row in rows)


def test_parse_full_ranking_table_row_text():
    row = _parse_table_row_text("#103 Tinkaton 123", "https://favoritepokemon.vercel.app/#/stats")

    assert row["pokemon_name"] == "Tinkaton"
    assert row["raw_rank"] == 103
    assert row["raw_vote_count"] == 123
    assert row["raw_row_json"]["full_ranking_table"] is True


def test_extract_rows_ignores_latest_declarations_and_global_summary():
    candidates = [
        {"selector": "section div", "text": "Latest 10 declarations Gabe chose Petilil - 1 minute ago"},
        {"selector": "section div", "text": "Declarations 319793 Unique Pokémon 1025 Pokédex covered 100.0%"},
        {"selector": "section div", "text": "THE FINAL 5 POKÉMON CHOSEN TO COMPLETE THE POKÉDEX: #846 #951"},
    ]

    rows = extract_rows_from_candidates(candidates, "https://favoritepokemon.vercel.app/#/stats")

    assert rows == []
