from backend.rankings.public_relative import (
    compute_leader_normalized_scores, compute_public_relative_scores, public_rank_tier,
    public_leader_rip_tier, public_relative_rip_tier, public_rip_display_score,
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
    cases = [(100, "S"), (95.50, "S"), (95.49, "A"), (94.99, "A"),
             (89.50, "A"), (89.49, "B"), (79.50, "B"), (79.49, "C"),
             (64.50, "C"), (64.49, "D"), (49.50, "D"), (49.49, "F"), (0, "F")]
    assert [(score, public_leader_rip_tier(score)) for score, _ in cases] == cases
    assert public_leader_rip_tier(98.36) == "S"
    assert public_leader_rip_tier(62) == "D"
    assert public_rip_display_score(95.49) == public_rip_display_score(94.99) == 9.5
    assert public_leader_rip_tier(95.49) == public_leader_rip_tier(94.99) == "A"
    assert all(public_leader_rip_tier(value) is None for value in (None, "", float("nan"), float("inf")))


def test_public_leader_tier_matches_every_approved_display_boundary_and_not_rank():
    displayed_cases = [(10.0, "S"), (9.6, "S"), (9.5, "A"), (9.0, "A"),
                       (8.9, "B"), (8.0, "B"), (7.9, "C"), (6.5, "C"),
                       (6.4, "D"), (5.0, "D"), (4.9, "F")]
    assert [(shown, public_leader_rip_tier(shown * 10)) for shown, _ in displayed_cases] == displayed_cases
    # Rank is deliberately absent from this helper: even a cohort leader grades from its visible score.
    assert public_leader_rip_tier(62) == "D"


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
    projected = public_budget_cohort_presentation(fifty, {"ranked_under_v12_authority": False})
    assert projected["a"]["overallRipRelativeScore"] == 100.0
    assert projected["a"]["financialRipRelativeScore"] == 0.0
    assert projected["a"]["budgetModelTier"] == "C"
    assert projected["a"]["publicTier"] == "S"
    # An extreme row from another budget never enters this function/cohort.
    assert "other-budget" not in projected


# ---- Follow-up B1: explicit benchmark vs absolute tier contracts ----
import pytest as _pytest
from backend.rankings.public_relative import absolute_rank_percentile_tier, benchmark_relative_tier


@_pytest.mark.parametrize(("score", "rank", "size", "expected"), [
    (5.00, 1, 22, "C"), (5.00, 22, 22, "C"), (4.75, 22, 22, "C"), (5.25, 1, 22, "C"),
    (5.10, 1, 22, "C"),
    (5.251, 1, 22, "S"), (5.251, 2, 22, "A"), (5.251, 3, 22, "B"), (5.251, 22, 22, "B"),
    (4.749, 17, 22, "D"), (4.749, 18, 22, "F"), (4.749, 22, 22, "F"),
    (4.60, 2, 2, "D"), (5.26, 1, 2, "S"), (4.60, 4, 4, "F"), (4.60, 3, 4, "D"),
    (4.60, 3, 3, "D"),
    (7.358, 1, 22, "S"), (6.426, 2, 22, "A"), (6.374, 3, 22, "B"), (5.237, 10, 22, "C"),
    (4.564, 16, 22, "D"), (4.348, 18, 22, "F"),
    (5.149, 1, 2, "C"), (4.602, 2, 2, "D"), (5.260, 1, 2, "S"), (4.306, 2, 2, "D"),
    (None, 1, 22, None), (5.5, None, 22, None), (5.5, 1, None, None),
    (5.5, 0, 22, None), (5.5, 23, 22, None), (5.5, 1, 0, None), ("x", 1, 22, None),
    (float("nan"), 1, 22, None),
])
def test_benchmark_relative_tier_contract(score, rank, size, expected):
    assert benchmark_relative_tier(score, rank, size) == expected


def test_benchmark_floor_cutoffs_are_floor_not_ceil():
    # N=150: floor(1.5)=1 S, floor(15)=15 A.  ceil would give 2 and 15.
    assert [benchmark_relative_tier(6, r, 150) for r in (1, 2, 15, 16)] == ["S", "A", "A", "B"]
    # N=7: max(1, floor(.07))=1 S, max(1, floor(.7))=1 A cutoff -> rank 2 is B.
    assert [benchmark_relative_tier(6, r, 7) for r in (1, 2)] == ["S", "B"]


@_pytest.mark.parametrize(("rank", "size", "expected"), [
    (1, 138, "S"), (2, 138, "A"), (13, 138, "A"), (14, 138, "B"), (34, 138, "B"),
    (35, 138, "C"), (69, 138, "C"), (70, 138, "D"), (103, 138, "D"), (104, 138, "F"),
    (138, 138, "F"),
    (182, 18293, "S"), (183, 18293, "A"), (1829, 18293, "A"), (1830, 18293, "B"),
    (4573, 18293, "B"), (4574, 18293, "C"), (9146, 18293, "C"), (9147, 18293, "D"),
    (13719, 18293, "D"), (13720, 18293, "F"), (18293, 18293, "F"),
    (1, 1, "S"), (None, 138, None), (1, None, None), (0, 138, None), (139, 138, None),
])
def test_absolute_rank_percentile_tier_contract(rank, size, expected):
    assert absolute_rank_percentile_tier(rank, size) == expected


def test_benchmark_presentation_uses_benchmark_helper_not_legacy_rank_bands():
    from backend.db.services.rankings_redesign_contract_service import benchmark_presentation
    assert benchmark_presentation(4.564, rank=16, cohort_size=22)["tier"] == "D"
    assert benchmark_presentation(5.10, rank=1, cohort_size=22)["tier"] == "C"
    assert benchmark_presentation(None, rank=1, cohort_size=22)["tier"] is None
    assert benchmark_presentation(4.602, rank=2, cohort_size=2)["tier"] == "D"
