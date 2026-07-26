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
