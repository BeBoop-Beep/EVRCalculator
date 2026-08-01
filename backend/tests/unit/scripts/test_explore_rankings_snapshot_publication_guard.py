"""The Explore rankings snapshot must never publish a FAILED desirability read.

The incident these cover: the Universal Set Desirability bundle raised on a
statement timeout, its service swallowed the exception and returned an empty
payload, and the builder published that - marking all 33 simulated sets
"desirability unavailable" and nulling every RIP score. The published row looked
exactly like a healthy build, so nothing downstream could tell it apart.
"""

import pytest

from backend.scripts import pokemon_snapshot_builders as builders


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


def test_daily_rank_movement_uses_distinct_compatible_published_payloads():
    meta = {
        "comparisonSnapshots": {"currentMarketDate": "2026-08-01", "previousMarketDate": "2026-07-31"},
        "ripWeightsConfig": {"overallRip": {"version": "rip-v4"}, "financialRip": {"version": "financial-v2"}},
        "publicAnalyticsCohort": {"version": "cohort-v1"},
    }
    previous_meta = {
        **meta,
        "comparisonSnapshots": {"currentMarketDate": "2026-07-31", "previousMarketDate": "2026-07-30"},
    }
    current = {"meta": meta, "targets": [{"set_id": "stable-1", "rip": {"rank": 2}, "ripCore": {"rank": 4}}]}
    previous = {"meta": previous_meta, "targets": [{"set_id": "stable-1", "rip": {"rank": 5}, "ripCore": {"rank": 3}}]}

    result = builders.attach_daily_rip_rank_movements(current, previous)

    assert result["targets"][0]["previousRipRank1d"] == 5
    assert result["targets"][0]["ripRankComparisonStatus1d"] == "available"
    assert result["targets"][0]["overallRipRankMovement1d"] == 3
    assert result["targets"][0]["financialRipRankMovement1d"] == -1


def test_rank_history_failure_is_unavailable_not_new():
    current = {
        "meta": {
            "comparisonSnapshots": {"currentMarketDate": "2026-08-01", "previousMarketDate": "2026-07-31"},
            "ripWeightsConfig": {"overallRip": {"version": "rip-v4"}, "financialRip": {"version": "financial-v2"}},
            "publicAnalyticsCohort": {"version": "cohort-v1"},
        },
        "targets": [{"set_id": "stable-1", "rip": {"rank": 2}}],
    }

    result = builders.attach_daily_rip_rank_movements(current, None)

    assert result["targets"][0]["ripRankComparisonStatus1d"] == "unavailable"


def test_older_snapshot_is_not_substituted_for_previous_day():
    current = {
        "meta": {
            "comparisonSnapshots": {"currentMarketDate": "2026-08-01"},
            "ripWeightsConfig": {"overallRip": {"version": "rip-v4"}, "financialRip": {"version": "financial-v2"}},
            "publicAnalyticsCohort": {"version": "cohort-v1"},
        },
        "targets": [{"set_id": "stable-1", "rip": {"rank": 2}}],
    }
    older = {
        "meta": {
            **current["meta"],
            "comparisonSnapshots": {"currentMarketDate": "2026-07-27"},
        },
        "targets": [{"set_id": "stable-1", "rip": {"rank": 8}}],
    }
    result = builders.attach_daily_rip_rank_movements(current, older)
    assert result["targets"][0]["overallRipRankComparisonStatus1d"] == "unavailable"
