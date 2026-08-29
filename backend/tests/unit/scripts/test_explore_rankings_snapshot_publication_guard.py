"""The Explore rankings snapshot must never publish a FAILED desirability read.

The incident these cover: the Universal Set Desirability bundle raised on a
statement timeout, its service swallowed the exception and returned an empty
payload, and the builder published that - marking all 33 simulated sets
"desirability unavailable" and nulling every RIP score. The published row looked
exactly like a healthy build, so nothing downstream could tell it apart.
"""

import pytest

from backend.desirability.scoring_config import (
    CANONICAL_FINANCIAL_RIP_VERSION,
    CANONICAL_OVERALL_RIP_VERSION,
)
from backend.scripts import pokemon_snapshot_builders as builders
from backend.db.services.era_set_strength_service import METHODOLOGY_VERSION as ERA_STRENGTH_METHODOLOGY_VERSION


def _payload(*, desirability_status, targets=None):
    return {
        "targets": targets if targets is not None else [],
        "default_target": {"target_type": "set", "target_id": "s1"},
        "meta": {"desirabilityBundleStatus": desirability_status},
    }


def test_failed_desirability_bundle_is_not_published(monkeypatch):
    monkeypatch.setattr(
        builders,
        "get_rip_statistics_targets_payload",
        lambda limit: _payload(desirability_status="failed"),
    )
    with pytest.raises(RuntimeError, match="Refusing to publish"):
        builders.build_explore_rankings_snapshot_row()


def test_absent_desirability_status_is_not_published(monkeypatch):
    """An older payload with no status is not evidence of a good build."""
    monkeypatch.setattr(
        builders,
        "get_rip_statistics_targets_payload",
        lambda limit: {"targets": [], "default_target": {}, "meta": {}},
    )
    with pytest.raises(RuntimeError, match="Refusing to publish"):
        builders.build_explore_rankings_snapshot_row()


def test_ok_desirability_bundle_publishes(monkeypatch):
    monkeypatch.setattr(
        builders,
        "get_rip_statistics_targets_payload",
        lambda limit: _payload(desirability_status="ok"),
    )
    monkeypatch.setattr(builders, "is_opening_set_row", lambda _row: True)

    row = builders.build_explore_rankings_snapshot_row()

    assert row["tcg"] == "pokemon"
    assert row["scope"] == "rip-statistics"
    assert row["ranking_payload_json"]["meta"]["desirabilityBundleStatus"] == "ok"
    assert row["ranking_payload_json"]["eraSetStrengthV1"]["methodologyVersion"] == ERA_STRENGTH_METHODOLOGY_VERSION
    assert row["ranking_payload_json"]["eraSetStrengthV1"]["eras"] == []


def _canonical_meta(market_date: str) -> dict:
    """Publication meta on the CANONICAL models, which is the only shape that
    may produce a published rank movement."""
    return {
        "comparisonSnapshots": {"currentMarketDate": market_date},
        "ripWeightsConfig": {
            "overallRip": {"version": CANONICAL_OVERALL_RIP_VERSION},
            "financialRip": {"version": CANONICAL_FINANCIAL_RIP_VERSION},
        },
        "publicAnalyticsCohort": {"version": "cohort-v1"},
    }


def test_daily_rank_movement_compares_v7_against_v7_and_v3_against_v3():
    current = {
        "meta": _canonical_meta("2026-08-01"),
        "targets": [{
            "set_id": "stable-1",
            "overallRipV8": {"rank": 2},
            "financialRipV3": {"rank": 4},
            # Legacy objects carry DIFFERENT ranks on purpose: if either is read,
            # the movement below changes and this test fails.
            "rip": {"rank": 9},
            "ripCore": {"rank": 11},
        }],
    }
    previous = {
        "meta": _canonical_meta("2026-07-31"),
        "targets": [{
            "set_id": "stable-1",
            "overallRipV8": {"rank": 5},
            "financialRipV3": {"rank": 3},
            "rip": {"rank": 17},
            "ripCore": {"rank": 19},
        }],
    }

    result = builders.attach_daily_rip_rank_movements(current, previous)
    target = result["targets"][0]

    assert target["previousOverallRipRank1d"] == 5
    assert target["overallRipRankComparisonStatus1d"] == "available"
    assert target["overallRipRankMovement1d"] == 3
    assert target["previousFinancialRipRank1d"] == 3
    assert target["financialRipRankMovement1d"] == -1


def test_a_set_that_did_not_move_publishes_zero_movement():
    """The verified production defect, as a fixture.

    On 2026-08-11 Scarlet and Violet 151 held Overall RIP V7 rank 5 on both days
    while its legacy v4 rank was 7. The movement field was built from the v4 rank
    and the Explore table subtracted it from the current V7 rank, so the row
    rendered a one-day rise of two places for a set that had not moved.
    """
    def payload(market_date, v7_rank, v4_rank):
        return {
            "meta": _canonical_meta(market_date),
            "targets": [{
                "set_id": "sv151",
                "overallRipV8": {"rank": v7_rank},
                "financialRipV3": {"rank": v7_rank},
                "rip": {"rank": v4_rank},
                "ripCore": {"rank": v4_rank},
            }],
        }

    result = builders.attach_daily_rip_rank_movements(
        payload("2026-08-11", v7_rank=5, v4_rank=7),
        payload("2026-08-10", v7_rank=5, v4_rank=7),
    )
    target = result["targets"][0]

    assert target["previousOverallRipRank1d"] == 5
    assert target["overallRipRankMovement1d"] == 0, "a set that did not move must report no movement"
    assert target["financialRipRankMovement1d"] == 0


def test_movement_is_unavailable_across_a_scoring_model_boundary():
    """V4 -> V7 and V2 -> V3 are never subtracted from one another."""
    current = {
        "meta": _canonical_meta("2026-08-05"),
        "targets": [{"set_id": "s", "overallRipV8": {"rank": 2}, "financialRipV3": {"rank": 2}}],
    }
    legacy_previous = {
        "meta": {
            "comparisonSnapshots": {"currentMarketDate": "2026-08-04"},
            "ripWeightsConfig": {
                "overallRip": {"version": "overall_rip_v4_90_financial_10_ca7"},
                "financialRip": {"version": "financial_rip_v2_60_25_15"},
            },
            "publicAnalyticsCohort": {"version": "cohort-v1"},
        },
        "targets": [{"set_id": "s", "rip": {"rank": 7}, "ripCore": {"rank": 8}}],
    }

    target = builders.attach_daily_rip_rank_movements(current, legacy_previous)["targets"][0]

    assert target["overallRipRankComparisonStatus1d"] == "unavailable"
    assert target["previousOverallRipRank1d"] is None
    assert target["overallRipRankMovement1d"] is None
    assert target["financialRipRankComparisonStatus1d"] == "unavailable"
    assert target["financialRipRankMovement1d"] is None


def test_two_matched_but_superseded_snapshots_still_publish_no_movement():
    """Equality between the two days is not enough - both must be canonical.

    A pair of v4 snapshots agrees with itself, but the field it populates is
    read beside a V7 rank, so it must stay empty.
    """
    def legacy(market_date, rank):
        return {
            "meta": {
                "comparisonSnapshots": {"currentMarketDate": market_date},
                "ripWeightsConfig": {
                    "overallRip": {"version": "overall_rip_v4_90_financial_10_ca7"},
                    "financialRip": {"version": "financial_rip_v2_60_25_15"},
                },
                "publicAnalyticsCohort": {"version": "cohort-v1"},
            },
            "targets": [{"set_id": "s", "rip": {"rank": rank}, "overallRipV8": {"rank": rank}}],
        }

    target = builders.attach_daily_rip_rank_movements(
        legacy("2026-08-05", 2), legacy("2026-08-04", 6)
    )["targets"][0]

    assert target["overallRipRankComparisonStatus1d"] == "unavailable"
    assert target["overallRipRankMovement1d"] is None


def test_a_set_absent_from_the_previous_publication_is_new_not_moved():
    current = {
        "meta": _canonical_meta("2026-08-05"),
        "targets": [{"set_id": "fresh", "overallRipV8": {"rank": 3}, "financialRipV3": {"rank": 3}}],
    }
    previous = {
        "meta": _canonical_meta("2026-08-04"),
        "targets": [{"set_id": "other", "overallRipV8": {"rank": 1}, "financialRipV3": {"rank": 1}}],
    }

    target = builders.attach_daily_rip_rank_movements(current, previous)["targets"][0]

    assert target["overallRipRankComparisonStatus1d"] == "new"
    assert target["previousOverallRipRank1d"] is None
    assert target["overallRipRankMovement1d"] is None


def test_rank_history_failure_is_unavailable_not_new():
    """A failed read of yesterday is not the same claim as "this set is new"."""
    current = {
        "meta": _canonical_meta("2026-08-01"),
        "targets": [{"set_id": "stable-1", "overallRipV8": {"rank": 2}, "financialRipV3": {"rank": 2}}],
    }

    result = builders.attach_daily_rip_rank_movements(current, None)

    assert result["targets"][0]["overallRipRankComparisonStatus1d"] == "unavailable"
    assert result["targets"][0]["overallRipRankMovement1d"] is None


def test_older_snapshot_is_not_substituted_for_previous_day():
    """A five-day-old publication is not "yesterday", even on the same model."""
    current = {
        "meta": _canonical_meta("2026-08-01"),
        "targets": [{"set_id": "stable-1", "overallRipV8": {"rank": 2}, "financialRipV3": {"rank": 2}}],
    }
    older = {
        "meta": _canonical_meta("2026-07-27"),
        "targets": [{"set_id": "stable-1", "overallRipV8": {"rank": 8}, "financialRipV3": {"rank": 8}}],
    }
    result = builders.attach_daily_rip_rank_movements(current, older)
    assert result["targets"][0]["overallRipRankComparisonStatus1d"] == "unavailable"
    assert result["targets"][0]["overallRipRankMovement1d"] is None
