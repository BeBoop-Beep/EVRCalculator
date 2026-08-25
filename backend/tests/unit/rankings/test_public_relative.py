from backend.rankings.public_relative import compute_public_relative_scores, public_product_rank_tier


def test_min_max_equal_and_null_contract():
    rows = [{"id": "a", "score": 10}, {"id": "b", "score": 20}, {"id": "c", "score": 30}, {"id": "n", "score": None}]
    result = compute_public_relative_scores(rows, id_getter=lambda r: r["id"], score_getter=lambda r: r["score"])
    assert result == {"a": 0.0, "b": 50.0, "c": 100.0, "n": None}
    equal = compute_public_relative_scores([{"id": "a", "score": 7}, {"id": "b", "score": 7}], id_getter=lambda r: r["id"], score_getter=lambda r: r["score"])
    assert equal == {"a": 50.0, "b": 50.0}


def test_product_public_rank_tiers_for_fifteen_item_cohort():
    assert [public_product_rank_tier(rank, 15) for rank in range(1, 5)] == ["S", "A", "A", "B"]


def test_overall_and_financial_are_independently_standardized():
    rows = [{"id": "a", "overall": 30, "financial": 10}, {"id": "b", "overall": 20, "financial": 30}, {"id": "c", "overall": 10, "financial": 20}]
    overall = compute_public_relative_scores(rows, id_getter=lambda r: r["id"], score_getter=lambda r: r["overall"])
    financial = compute_public_relative_scores(rows, id_getter=lambda r: r["id"], score_getter=lambda r: r["financial"])
    assert overall == {"a": 100.0, "b": 50.0, "c": 0.0}
    assert financial == {"a": 0.0, "b": 100.0, "c": 50.0}


def test_budget_projection_is_cohort_isolated_and_preserves_model_tier():
    from backend.db.services.budget_product_ranking_service import public_budget_cohort_presentation
    fifty = [
        {"sealed_product_id": "a", "overall_rip_v10_score": 30, "financial_rip_v4_score": 10, "budget_rank": 1, "budget_cohort_size": 2, "budget_tier": "C"},
        {"sealed_product_id": "b", "overall_rip_v10_score": 20, "financial_rip_v4_score": 30, "budget_rank": 2, "budget_cohort_size": 2, "budget_tier": "D"},
    ]
    projected = public_budget_cohort_presentation(fifty)
    assert projected["a"]["overallRipRelativeScore"] == 100.0
    assert projected["a"]["financialRipRelativeScore"] == 0.0
    assert projected["a"]["budgetModelTier"] == "C"
    assert projected["a"]["publicTier"] == "S"
    # An extreme row from another budget never enters this function/cohort.
    assert "other-budget" not in projected
