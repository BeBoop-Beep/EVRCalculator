from backend.desirability.card_collector_rankings import build_card_collector_ranking_rows


def test_card_rank_is_global_deterministic_and_excludes_unscored():
    rows = build_card_collector_ranking_rows([
        {"pokemon_canonical_card_id": "b", "collector_card_appeal_score": 90, "score_status": "scored"},
        {"pokemon_canonical_card_id": "a", "collector_card_appeal_score": 90, "score_status": "scored"},
        {"pokemon_canonical_card_id": "c", "collector_card_appeal_score": None, "score_status": "unavailable"},
    ], "run-1")
    assert [row["pokemon_canonical_card_id"] for row in rows] == ["a", "b"]
    assert [row["rank"] for row in rows] == [1, 2]
    assert {row["cohort_size"] for row in rows} == {2}
