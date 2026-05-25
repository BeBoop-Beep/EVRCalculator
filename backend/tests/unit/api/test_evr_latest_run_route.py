import json
from unittest.mock import patch

from fastapi.testclient import TestClient

from backend.api.main import app


client = TestClient(app)


SWSH6_UUID_INPUT_FIXTURE = "0dd7683c-4146-4dcd-a04c-6f686bd91417"
SWSH6_RUN_ID = "0dd7683c-4146-4dcd-a04c-6f686bd91417"
SWSH7_RUN_ID = "91e93106-b677-46de-b398-6728aa7842fb"


def _snapshot(run_id: str, target_id: str):
    return {
        "calculation_run_id": run_id,
        "summary": {
            "calculation_run_id": run_id,
            "pack_cost": 4.0,
            "mean_value": 5.0,
            "median_value": 4.5,
            "roi": 0.25,
            "roi_percent": 25.0,
            "prob_profit": 0.5,
        },
        "run": {
            "id": run_id,
            "target_type": "set",
            "target_id": target_id,
        },
        "simulation_summary": {
            "calculation_run_id": run_id,
            "pack_cost": 4.0,
            "mean_value": 5.0,
            "median_value": 4.5,
            "roi": 0.25,
            "roi_percent": 25.0,
            "prob_profit": 0.5,
        },
    }


def test_latest_run_route_returns_swsh6_snapshot_for_set_key():
    expected_snapshot = _snapshot(SWSH6_RUN_ID, "set-uuid-swsh6")

    with patch("backend.api.main.get_latest_evr_run_snapshot", return_value=expected_snapshot) as mock_service:
        response = client.get("/evr/runs/latest", params={"target_type": "set", "target_id": "swsh6"})

    assert response.status_code == 200
    payload = response.json()
    assert payload["snapshot"]["calculation_run_id"] == SWSH6_RUN_ID
    assert payload["snapshot"]["summary"]["calculation_run_id"] == SWSH6_RUN_ID
    mock_service.assert_called_once_with(target_type="set", target_id="swsh6")


def test_latest_run_route_returns_swsh7_snapshot_for_set_key():
    expected_snapshot = _snapshot(SWSH7_RUN_ID, "set-uuid-swsh7")

    with patch("backend.api.main.get_latest_evr_run_snapshot", return_value=expected_snapshot) as mock_service:
        response = client.get("/evr/runs/latest", params={"target_type": "set", "target_id": "swsh7"})

    assert response.status_code == 200
    payload = response.json()
    assert payload["snapshot"]["calculation_run_id"] == SWSH7_RUN_ID
    assert payload["snapshot"]["summary"]["calculation_run_id"] == SWSH7_RUN_ID
    mock_service.assert_called_once_with(target_type="set", target_id="swsh7")


def test_latest_run_route_returns_same_swsh6_snapshot_for_uuid_input():
    expected_snapshot = _snapshot(SWSH6_RUN_ID, SWSH6_UUID_INPUT_FIXTURE)

    with patch("backend.api.main.get_latest_evr_run_snapshot", return_value=expected_snapshot) as mock_service:
        response = client.get("/evr/runs/latest", params={"target_type": "set", "target_id": SWSH6_UUID_INPUT_FIXTURE})

    assert response.status_code == 200
    payload = response.json()
    assert payload["snapshot"]["calculation_run_id"] == SWSH6_RUN_ID
    assert payload["snapshot"]["run"]["id"] == SWSH6_RUN_ID
    mock_service.assert_called_once_with(target_type="set", target_id=SWSH6_UUID_INPUT_FIXTURE)


def test_latest_run_route_returns_404_for_unknown_target():
    with patch("backend.api.main.get_latest_evr_run_snapshot", return_value=None) as mock_service:
        response = client.get("/evr/runs/latest", params={"target_type": "set", "target_id": "unknown-set"})

    assert response.status_code == 404
    assert response.json() == {"detail": "No EVR run snapshot found"}
    mock_service.assert_called_once_with(target_type="set", target_id="unknown-set")


def test_latest_run_route_preserves_aliases_critical_fields_and_json_serializability():
    expected_snapshot = _snapshot(SWSH6_RUN_ID, "set-uuid-swsh6")

    with patch("backend.api.main.get_latest_evr_run_snapshot", return_value=expected_snapshot):
        response = client.get("/evr/runs/latest", params={"target_type": "set", "target_id": "swsh6"})

    assert response.status_code == 200
    payload = response.json()
    snapshot = payload["snapshot"]
    summary = snapshot["summary"]

    assert "calculation_run_id" in snapshot
    assert "summary" in snapshot
    assert "run" in snapshot
    assert "simulation_summary" in snapshot
    for field in ("pack_cost", "mean_value", "median_value", "roi", "roi_percent", "prob_profit"):
        assert summary[field] is not None

    assert json.loads(response.content) == payload