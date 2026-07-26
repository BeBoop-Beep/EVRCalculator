"""Deterministic cohort validation for the public relative RIP standardization.

Proves the restored production scoring contract end to end over the pure ranking
helpers in :mod:`backend.db.services.explore_rip_statistics_service`:

  * relative scores are min-max of the FINAL absolute formula outputs,
  * the best eligible set gets 100 and the lowest gets 0,
  * relative ordering exactly matches absolute ordering,
  * Overall relative is derived from the Overall ABSOLUTE (the 90/10 blend),
    never blended from already-relative inputs,
  * a set missing CA7 (absolute Overall None) never enters the Overall
    normalization cohort,
  * Financial and Overall may have different denominators,
  * rank-bucket tiers match production (5/15/30/50/75 → S/A/B/C/D, remainder F),
  * the equal-score fallback and null preservation from main are intact.
"""

from __future__ import annotations

from backend.db.services.explore_rip_statistics_service import (
    _attach_relative_scores,
    _calculate_score_ranks_and_tiers,
    _compute_relative_scores,
    _rank_within_cohort,
)


def _pillar(score):
    return {"score": score}


def _row(target_id, *, overall, financial, profit, safety, stability):
    """A cohort row shaped like a ranked explore target.

    Pillar extractors read the top-level ``*_score`` fields; pillar relatives are
    written onto the component dicts (in both ripCore and rip.financialRip).
    """
    components = {
        "profit": _pillar(profit),
        "safety": _pillar(safety),
        "stability": _pillar(stability),
    }
    financial_components = {k: dict(v) for k, v in components.items()}
    return {
        "target_id": target_id,
        "profit_score": profit,
        "safety_score": safety,
        "stability_score": stability,
        "rip": {"score": overall, "financialRip": {"components": financial_components}},
        "ripCore": {"score": financial, "components": components},
    }


def _cohort():
    # Absolute Overall scores span a compressed range (the reason the raw formula
    # is not a good public language); relative must stretch them to 0-100.
    return [
        _row("A", overall=33.8, financial=27.0, profit=40.0, safety=10.0, stability=3.0),
        _row("B", overall=33.1, financial=26.2, profit=39.0, safety=9.5, stability=2.6),
        _row("C", overall=29.4, financial=22.3, profit=30.0, safety=8.0, stability=2.0),
        _row("D", overall=21.0, financial=15.5, profit=18.0, safety=6.0, stability=1.0),
        _row("E", overall=12.5, financial=9.0, profit=10.0, safety=3.0, stability=0.5),
    ]


def _by_id(rows):
    return {r["target_id"]: r for r in rows}


def test_best_gets_100_lowest_gets_0_and_ordering_matches_absolute():
    rows = _cohort()
    _rank_within_cohort(rows, cohort_size=len(rows))
    by_id = _by_id(rows)

    # Best (A) → 100, lowest (E) → 0 for both Overall and Financial.
    assert by_id["A"]["rip"]["relativeScore"] == 100.0
    assert by_id["E"]["rip"]["relativeScore"] == 0.0
    assert by_id["A"]["ripCore"]["relativeScore"] == 100.0
    assert by_id["E"]["ripCore"]["relativeScore"] == 0.0

    # Closely-spaced top sets both land high (A=100, B in the high 90s).
    assert 95.0 <= by_id["B"]["rip"]["relativeScore"] < 100.0

    # Relative ordering exactly matches absolute ordering.
    abs_order = sorted(rows, key=lambda r: r["rip"]["score"], reverse=True)
    rel_order = sorted(rows, key=lambda r: r["rip"]["relativeScore"], reverse=True)
    assert [r["target_id"] for r in abs_order] == [r["target_id"] for r in rel_order]

    # Ranks follow the same ordering (rank 1 = highest absolute).
    assert by_id["A"]["rip"]["rank"] == 1
    assert by_id["E"]["rip"]["rank"] == 5


def test_overall_relative_derived_from_overall_absolute_not_a_blend_of_relatives():
    """Overall relative must be min-max of Overall absolute, not of Financial rel.

    Set C's Overall absolute sits between B and D. If Overall relative were
    (incorrectly) a blend of Financial-relative and CA7-relative it would drift;
    here we prove Overall relative reproduces exactly the min-max of rip.score.
    """
    rows = _cohort()
    _rank_within_cohort(rows, cohort_size=len(rows))
    by_id = _by_id(rows)

    overall_min = min(r["rip"]["score"] for r in rows)
    overall_max = max(r["rip"]["score"] for r in rows)
    for r in rows:
        expected = round(100.0 * (r["rip"]["score"] - overall_min) / (overall_max - overall_min), 2)
        assert r["rip"]["relativeScore"] == expected

    # Financial relative is independently min-max of ripCore.score.
    fin_min = min(r["ripCore"]["score"] for r in rows)
    fin_max = max(r["ripCore"]["score"] for r in rows)
    for r in rows:
        expected = round(100.0 * (r["ripCore"]["score"] - fin_min) / (fin_max - fin_min), 2)
        assert r["ripCore"]["relativeScore"] == expected

    # The two are genuinely different presentations for a mid set.
    assert by_id["C"]["rip"]["relativeScore"] != by_id["C"]["ripCore"]["relativeScore"]


def test_missing_ca7_excluded_from_overall_cohort_but_kept_in_financial():
    rows = _cohort()
    # Set C loses CA7: Overall absolute is None (unavailable), Financial intact.
    rows[2]["rip"]["score"] = None
    _rank_within_cohort(rows, cohort_size=len(rows))
    by_id = _by_id(rows)

    # C is excluded from Overall: no relative, no rank.
    assert by_id["C"]["rip"]["relativeScore"] is None
    assert by_id["C"]["rip"]["rank"] is None

    # C stays in Financial with a real relative + rank.
    assert by_id["C"]["ripCore"]["relativeScore"] is not None
    assert by_id["C"]["ripCore"]["rank"] is not None

    # The Overall min-max is computed over the 4 remaining sets only: the best
    # remaining (A) is still 100 and the worst remaining (E) still 0.
    assert by_id["A"]["rip"]["relativeScore"] == 100.0
    assert by_id["E"]["rip"]["relativeScore"] == 0.0


def test_pillar_relatives_attached_to_both_component_locations():
    rows = _cohort()
    _attach_relative_scores(rows)
    for r in rows:
        core_profit = r["ripCore"]["components"]["profit"].get("relativeScore")
        fin_profit = r["rip"]["financialRip"]["components"]["profit"].get("relativeScore")
        assert core_profit is not None
        assert core_profit == fin_profit  # both surfaces agree
    by_id = _by_id(rows)
    # Best/worst profit pillar → 100 / 0.
    assert by_id["A"]["ripCore"]["components"]["profit"]["relativeScore"] == 100.0
    assert by_id["E"]["ripCore"]["components"]["profit"]["relativeScore"] == 0.0


def test_rank_bucket_tiers_match_production():
    # 20 sets, descending scores 100..5, so percentile buckets are exact.
    rows = [
        _row(f"S{i:02d}", overall=100.0 - i * 5, financial=100.0 - i * 5,
             profit=100.0 - i, safety=50.0, stability=25.0)
        for i in range(20)
    ]
    _rank_within_cohort(rows, cohort_size=len(rows))
    tier_by_rank = {r["rip"]["rank"]: r["rip"]["tier"] for r in rows}
    # top 5% (rank 1) = S; through 15% (2-3) = A; through 30% (4-6) = B;
    # through 50% (7-10) = C; through 75% (11-15) = D; remainder (16-20) = F.
    assert tier_by_rank[1] == "S"
    assert tier_by_rank[3] == "A"
    assert tier_by_rank[6] == "B"
    assert tier_by_rank[10] == "C"
    assert tier_by_rank[15] == "D"
    assert tier_by_rank[20] == "F"


def test_equal_score_fallback_and_null_preservation_from_main():
    # All equal → the main equal-score fallback yields 50.0, nulls preserved.
    rows = [
        {"target_id": "X", "_score": 42.0},
        {"target_id": "Y", "_score": 42.0},
        {"target_id": "Z", "_score": None},
    ]
    relatives = _compute_relative_scores(rows, "_score")
    assert relatives["X"] == 50.0
    assert relatives["Y"] == 50.0
    assert relatives["Z"] is None


def test_financial_and_overall_may_have_different_denominators():
    rows = _cohort()
    rows[2]["rip"]["score"] = None  # C missing CA7
    _rank_within_cohort(rows, cohort_size=len(rows))

    overall_ranked = [r for r in rows if r["rip"]["rank"] is not None]
    financial_ranked = [r for r in rows if r["ripCore"]["rank"] is not None]
    assert len(overall_ranked) == 4
    assert len(financial_ranked) == 5
