import pytest

from backend.db.services.ev_representativeness_public_service import (
    PUBLIC_CONTRACT_VERSION,
    attach_public_v1_to_targets,
    project_public_v1,
    project_opening_outcome_profile_v1,
    sort_history_rows,
)


def summary(**overrides):
    row = {
        "calculation_run_id": "run-A",
        "research_method_version": "ev_representativeness_v1",
        "market_date": "2026-08-22",
        "source_artifact_sha256": "a" * 64,
        "typical_capture": 0.209,
        "top1_outcome_ev_share": 0.641,
        "horizon_r80_c80_stable": 2812,
        "horizon_r80_c80_status": "resolved",
        "horizon_tau20_c80_stable": 5906,
        "horizon_tau20_c80_status": "resolved",
    }
    row.update(overrides)
    return row


def curve(run="run-A", version="ev_representativeness_v1", packs=1, estimate=0.073, stage="coarse"):
    return {"calculation_run_id": run, "research_method_version": version,
            "scope_kind": "pack_grid", "metric_key": "realization_ge_0.80",
            "pack_count": packs, "estimate": estimate, "stage": stage}


def test_public_projection_maps_only_allowlisted_fields_and_probabilities():
    payload = project_public_v1(summary(secret_seed=123), [curve()], expected_calculation_run_id="run-A")
    assert payload["contractVersion"] == PUBLIC_CONTRACT_VERSION
    assert payload["methodVersion"] == "ev_representativeness_v1"
    assert payload["calculationRunId"] == "run-A"
    assert payload["typicalCapture"] == 0.209
    assert payload["realizationHorizon"]["packCount"] == 2812
    assert payload["convergenceHorizon"]["packCount"] == 5906
    assert payload["realizationByPackCount"] == [
        {"packCount": 1, "probabilityAtLeast80PercentEv": 0.073}
    ]
    assert "secret_seed" not in payload


def test_same_run_invariant_never_returns_newer_other_run():
    assert project_public_v1(summary(calculation_run_id="run-B"), [curve(run="run-B")],
                             expected_calculation_run_id="run-A") is None


def test_future_method_version_is_not_silently_consumed():
    assert project_public_v1(summary(research_method_version="ev_representativeness_v2"), [],
                             expected_calculation_run_id="run-A") is None


def test_unratified_horizon_is_not_exposed_as_confirmed():
    payload = project_public_v1(
        summary(horizon_tau20_c80_status="confirmation_did_not_ratify"), [],
        expected_calculation_run_id="run-A",
    )
    assert payload["realizationHorizon"]["status"] == "confirmed"
    assert payload["convergenceHorizon"] is None


def test_resolved_at_minimum_grid_point_is_a_legitimate_confirmed_horizon():
    """finite_sample.resolve_horizon reports two genuinely-resolved statuses:
    'resolved' and 'resolved_at_minimum_grid_point' (a horizon found at the
    very first grid point, typically a small/cheap set). Both are real
    confirmed horizons and must publish a headline, not be treated as
    missing/exceeds-cap coverage."""
    payload = project_public_v1(
        summary(horizon_r80_c80_status="resolved_at_minimum_grid_point"), [],
        expected_calculation_run_id="run-A",
    )
    assert payload["realizationHorizon"] == {
        "targetEvRatio": 0.80, "openerProbability": 0.80, "packCount": 2812, "status": "confirmed",
    }


def test_exceeds_search_cap_and_degenerate_ev_never_fabricate_a_pack_count():
    for status in ("exceeds_search_cap", "degenerate_ev"):
        payload = project_public_v1(
            summary(horizon_r80_c80_status=status), [], expected_calculation_run_id="run-A",
        )
        assert payload["realizationHorizon"] is None


def test_curve_projection_ignores_wrong_run_and_method_and_prefers_sharper_stage():
    payload = project_public_v1(
        summary(),
        [curve(estimate=0.1), curve(estimate=0.2, stage="refine"),
         curve(run="run-B", estimate=0.9), curve(version="ev_representativeness_v2", estimate=0.8)],
        expected_calculation_run_id="run-A",
    )
    assert payload["realizationByPackCount"][0]["probabilityAtLeast80PercentEv"] == 0.2


def test_projection_read_failure_is_non_blocking_and_does_not_mutate_targets():
    class BrokenClient:
        def table(self, _name):
            raise RuntimeError("research unavailable")

    source = [{"calculation_run_id": "run-A", "name": "Set A"}]
    assert attach_public_v1_to_targets(BrokenClient(), source) == source
    assert "evRepresentativeness" not in source[0]


def test_history_order_is_deterministic_in_both_directions():
    rows = [
        {"market_date": "2026-08-22", "calculation_run_id": "b"},
        {"market_date": "2026-08-17", "calculation_run_id": "z"},
        {"market_date": "2026-08-22", "calculation_run_id": "a"},
    ]
    assert [row["calculation_run_id"] for row in sort_history_rows(rows)] == ["z", "a", "b"]
    assert [row["calculation_run_id"] for row in sort_history_rows(rows, descending=True)] == ["b", "a", "z"]


def test_outcome_profile_is_exact_run_versioned_and_allowlisted():
    row = summary(return_ratio_buckets_json={
        "cost": 10, "sampleSize": 8,
        "buckets": [
            {"ratioFloor": floor, "ratioCeiling": ceiling, "occurrenceCount": 1, "probability": .125}
            for floor, ceiling in ((0,.25),(.25,.5),(.5,.75),(.75,1),(1,1.5),(1.5,2),(2,5),(5,None))
        ],
    }, ev=7, p50=3)
    payload = project_opening_outcome_profile_v1(row, expected_calculation_run_id="run-A")
    assert payload["contractVersion"] == "opening_outcome_profile_v1"
    assert payload["calculationRunId"] == "run-A"
    assert payload["cumulativeProbabilities"][1]["probability"] == pytest.approx(.5)
    assert "diagnostics_json" not in payload
    assert project_opening_outcome_profile_v1(row, expected_calculation_run_id="run-B") is None
