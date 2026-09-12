from datetime import date
import pytest

from backend.research.historical_rip import (
    QUALITY_BLOCKED, assert_idempotent, cohort_identity, historical_features,
    historical_v7_availability, select_as_of_source, source_effective_periods,
    metric_gates, research_readiness, classify_chase_lineage,
)


def run(identifier, captured):
    return {"id": identifier, "source_name": "artist", "status": "success", "captured_at": captured,
            "raw_payload_json": {"timeframe": "12m"}}


def test_as_of_selection_never_uses_future_source():
    rows = [run("old", "2026-09-01T00:00:00+00:00"), run("future", "2026-09-12T00:00:00+00:00")]
    assert select_as_of_source(rows, source_name="artist", timeframe="12m", as_of=date(2026,9,10))["id"] == "old"


def test_missing_required_source_is_explicitly_unavailable():
    result = historical_v7_availability(date(2026,9,11), {})
    assert result["qualityStatus"] == QUALITY_BLOCKED and result["collectorAvailable"] is False


def test_future_evidence_fails_closed():
    source = {"id":"x", "captured_at":"2026-09-12T00:00:00+00:00"}
    with pytest.raises(ValueError, match="future source leakage"):
        historical_v7_availability(date(2026,9,11), {k:source for k in ("pokemon_trends","trainer_12m","trainer_5y","artist_12m","artist_5y","playability")})


def test_effective_period_stops_before_next_capture():
    periods = source_effective_periods([run("a","2026-09-01T00:00:00+00:00"),run("b","2026-09-05T00:00:00+00:00")],7)
    assert periods[0]["effectiveUntil"] == "2026-09-04"


def test_cohort_fingerprint_is_order_independent_and_rank_is_not_score():
    assert cohort_identity(["b","a"])["cohortFingerprint"] == cohort_identity(["a","b"])["cohortFingerprint"]


def test_features_exclude_partial_and_future_points():
    points=[{"as_of_date":"2026-09-01","quality_status":"READY","score":80},
            {"as_of_date":"2026-09-02","quality_status":"PARTIAL","score":1},
            {"as_of_date":"2026-09-12","quality_status":"READY","score":100}]
    result=historical_features(points,as_of=date(2026,9,10),value_key="score")
    assert result["n"] == 1 and result["current"] == 80


def test_history_identity_is_idempotent():
    row={"set_id":"s","as_of_date":"2026-09-11","collector_model_version":"v7"}
    with pytest.raises(ValueError,match="duplicate"):
        assert_idempotent([row,row])


def test_minimum_history_gates_do_not_invent_metrics():
    assert metric_gates(1)["basic"] == "INSUFFICIENT_HISTORY"
    assert metric_gates(30)["stability30d"] == "READY"
    assert metric_gates(89)["historicalQuality90d"] == "INSUFFICIENT_HISTORY"


def test_research_readiness_requires_primary_90_observation_gate():
    assert research_readiness(dates=1, sets=128, forward_target_available=True,
                              same_version=True, no_lookahead=True,
                              predictor_variation=True) == "HISTORICAL_QUALITY_RESEARCH_NOT_READY"


def test_chase_lineage_classifies_first_missing_authority():
    assert classify_chase_lineage({"formula_version":"v1"}) == "CHASE_HISTORY_BLOCKED_PROBABILITY"
    assert classify_chase_lineage({"probability_run_id":"p","formula_version":"v1"}) == "CHASE_HISTORY_BLOCKED_DESIRABILITY"
