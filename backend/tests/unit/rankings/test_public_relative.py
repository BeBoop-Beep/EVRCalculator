from backend.rankings.public_relative import (
    compute_leader_normalized_scores, compute_public_relative_scores, public_rank_tier,
    public_leader_rip_tier, public_relative_rip_tier,
)


def test_leader_normalized_scores_are_additive_and_fail_closed():
    rows = [{"id": "leader", "score": 42.8172}, {"id": "next", "score": 42.2344},
            {"id": "missing", "score": None}]
    result = compute_leader_normalized_scores(
        rows, id_getter=lambda row: row["id"], score_getter=lambda row: row["score"]
    )
    assert result == {"leader": 100.0, "next": 98.64, "missing": None}
    assert compute_leader_normalized_scores(
        [{"id": "a", "score": 7}, {"id": "b", "score": 7}],
        id_getter=lambda row: row["id"], score_getter=lambda row: row["score"],
    ) == {"a": 100.0, "b": 100.0}
    assert compute_leader_normalized_scores(
        [{"id": "a", "score": 0}, {"id": "b", "score": -1}],
        id_getter=lambda row: row["id"], score_getter=lambda row: row["score"],
    ) == {"a": None, "b": None}


def test_min_max_equal_and_null_contract():
    rows = [{"id": "a", "score": 10}, {"id": "b", "score": 20}, {"id": "c", "score": 30}, {"id": "n", "score": None}]
    result = compute_public_relative_scores(rows, id_getter=lambda r: r["id"], score_getter=lambda r: r["score"])
    assert result == {"a": 0.0, "b": 50.0, "c": 100.0, "n": None}
    equal = compute_public_relative_scores([{"id": "a", "score": 7}, {"id": "b", "score": 7}], id_getter=lambda r: r["id"], score_getter=lambda r: r["score"])
    assert equal == {"a": 50.0, "b": 50.0}


def test_public_rank_tier_is_the_canonical_sets_authority():
    assert [public_rank_tier(rank, 22) for rank in range(1, 7)] == ["S", "S", "A", "A", "B", "B"]


def test_locked_public_relative_rip_tier_boundaries_and_invalid_values():
    cases = [(100, "S"), (90, "S"), (89.999, "A"), (80, "A"),
             (79.999, "B"), (70, "B"), (69.999, "C"), (45, "C"),
             (44.999, "D"), (15, "D"), (14.999, "F"), (0, "F")]
    assert [(score, public_relative_rip_tier(score)) for score, _ in cases] == cases
    assert all(public_relative_rip_tier(value) is None for value in (None, "", float("nan"), float("inf")))


def test_locked_public_leader_rip_tier_boundaries_and_regressions():
    cases = [(100, "S"), (95, "S"), (94.999, "A"), (90, "A"),
             (89.999, "B"), (80, "B"), (79.999, "C"), (70, "C"),
             (69.999, "D"), (55, "D"), (54.999, "F"), (0, "F")]
    assert [(score, public_leader_rip_tier(score)) for score, _ in cases] == cases
    assert public_leader_rip_tier(98.36) == "S"
    assert public_leader_rip_tier(62) == "D"
    assert all(public_leader_rip_tier(value) is None for value in (None, "", float("nan"), float("inf")))


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
