import pytest

from backend.scripts.extend_current_pokemon_collector_v7_set import (
    _assert_control_stability,
)


def _built(*rows):
    return {"sets": list(rows)}


def test_control_stability_allows_only_requested_additive_set():
    report = _assert_control_stability(
        target_set_id="target",
        current_sets={
            "old": {
                "collector_desirability_score": 60.0,
                "collector_desirability_rank": 1,
            }
        },
        current_appeal={
            "old": {"collector_appeal_score": 55.0, "score_status": "scored"}
        },
        built=_built(
            {"set_id": "old", "D_final": 60.0, "collector_appeal": 55.0},
            {"set_id": "target", "D_final": 72.0, "collector_appeal": None},
        ),
    )

    assert report["addedSetIds"] == ["target"]
    assert report["maxControlDDelta"] == 0.0
    assert report["maxControlCollectorAppealDelta"] == 0.0


def test_control_stability_rejects_unexpected_additive_set():
    with pytest.raises(RuntimeError, match="unexpected sets"):
        _assert_control_stability(
            target_set_id="target",
            current_sets={"old": {"collector_desirability_score": 60.0}},
            current_appeal={"old": {"collector_appeal_score": 55.0}},
            built=_built(
                {"set_id": "old", "D_final": 60.0, "collector_appeal": 55.0},
                {"set_id": "target", "D_final": 72.0, "collector_appeal": None},
                {"set_id": "surprise", "D_final": 50.0, "collector_appeal": None},
            ),
        )


def test_control_stability_rejects_historical_score_drift():
    with pytest.raises(RuntimeError, match="control scores changed"):
        _assert_control_stability(
            target_set_id="target",
            current_sets={"old": {"collector_desirability_score": 60.0}},
            current_appeal={"old": {"collector_appeal_score": 55.0}},
            built=_built(
                {"set_id": "old", "D_final": 60.01, "collector_appeal": 55.0},
                {"set_id": "target", "D_final": 72.0, "collector_appeal": None},
            ),
        )


def test_control_stability_allows_requested_target_refresh():
    report = _assert_control_stability(
        target_set_id="target",
        current_sets={
            "old": {"collector_desirability_score": 60.0},
            "target": {"collector_desirability_score": 70.0},
        },
        current_appeal={
            "old": {"collector_appeal_score": 55.0},
            "target": {"collector_appeal_score": None},
        },
        built=_built(
            {"set_id": "old", "D_final": 60.0, "collector_appeal": 55.0},
            {"set_id": "target", "D_final": 74.0, "collector_appeal": 62.0},
        ),
    )

    assert report["addedSetIds"] == []
    assert report["maxControlDDelta"] == 0.0
