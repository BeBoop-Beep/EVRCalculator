from unittest.mock import patch

from backend.db.services.calculation_run_query_service import get_latest_evr_run_snapshot


def _snapshot(run_id: str):
    return {
        "run": {
            "id": run_id,
            "target_type": "set",
            "target_id": "set-uuid",
        },
        "comparison_metrics": {},
        "derived_metrics": {},
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


@patch("backend.db.services.calculation_run_query_service.get_set_by_name")
@patch("backend.db.services.calculation_run_query_service.get_set_by_canonical_key")
@patch("backend.db.services.calculation_run_query_service.get_set_by_pokemon_api_set_id")
@patch("backend.db.services.calculation_run_query_service.get_set_by_id")
@patch("backend.db.services.calculation_run_query_service.get_latest_run_snapshot_for_target")
def test_get_latest_snapshot_resolves_swsh6_set_key_to_same_uuid_run(
    mock_repo,
    mock_get_set_by_id,
    mock_get_set_by_pokemon_api_set_id,
    mock_get_set_by_canonical_key,
    mock_get_set_by_name,
):
    mock_get_set_by_id.return_value = None
    mock_get_set_by_pokemon_api_set_id.return_value = {
        "id": "set-uuid-swsh6",
        "pokemon_api_set_id": "swsh6",
        "canonical_key": "chillingReign",
        "name": "Chilling Reign",
    }
    mock_get_set_by_canonical_key.return_value = None
    mock_get_set_by_name.return_value = None

    expected = _snapshot("run-swsh6")

    def _repo_side_effect(target_type, target_id):
        if target_type == "set" and target_id == "set-uuid-swsh6":
            return expected
        return None

    mock_repo.side_effect = _repo_side_effect

    result = get_latest_evr_run_snapshot(target_type="set", target_id="swsh6")

    assert result is not None
    assert result["calculation_run_id"] == "run-swsh6"
    assert result["summary"]["pack_cost"] == 4.0
    assert any(call.args == ("set", "set-uuid-swsh6") for call in mock_repo.call_args_list)


@patch("backend.db.services.calculation_run_query_service.get_set_by_name")
@patch("backend.db.services.calculation_run_query_service.get_set_by_canonical_key")
@patch("backend.db.services.calculation_run_query_service.get_set_by_pokemon_api_set_id")
@patch("backend.db.services.calculation_run_query_service.get_set_by_id")
@patch("backend.db.services.calculation_run_query_service.get_latest_run_snapshot_for_target")
def test_get_latest_snapshot_resolves_swsh7_set_key_to_same_uuid_run(
    mock_repo,
    mock_get_set_by_id,
    mock_get_set_by_pokemon_api_set_id,
    mock_get_set_by_canonical_key,
    mock_get_set_by_name,
):
    mock_get_set_by_id.return_value = None
    mock_get_set_by_pokemon_api_set_id.return_value = {
        "id": "set-uuid-swsh7",
        "pokemon_api_set_id": "swsh7",
        "canonical_key": "evolvingSkies",
        "name": "Evolving Skies",
    }
    mock_get_set_by_canonical_key.return_value = None
    mock_get_set_by_name.return_value = None

    expected = _snapshot("run-swsh7")

    def _repo_side_effect(target_type, target_id):
        if target_type == "set" and target_id == "set-uuid-swsh7":
            return expected
        return None

    mock_repo.side_effect = _repo_side_effect

    result = get_latest_evr_run_snapshot(target_type="set", target_id="swsh7")

    assert result is not None
    assert result["calculation_run_id"] == "run-swsh7"
    assert result["summary"]["mean_value"] == 5.0
    assert any(call.args == ("set", "set-uuid-swsh7") for call in mock_repo.call_args_list)


@patch("backend.db.services.calculation_run_query_service.get_set_by_name")
@patch("backend.db.services.calculation_run_query_service.get_set_by_canonical_key")
@patch("backend.db.services.calculation_run_query_service.get_set_by_pokemon_api_set_id")
@patch("backend.db.services.calculation_run_query_service.get_set_by_id")
@patch("backend.db.services.calculation_run_query_service.get_latest_run_snapshot_for_target")
def test_uuid_target_id_behavior_still_works(
    mock_repo,
    mock_get_set_by_id,
    mock_get_set_by_pokemon_api_set_id,
    mock_get_set_by_canonical_key,
    mock_get_set_by_name,
):
    uuid_target = "0dd7683c-4146-4dcd-a04c-6f686bd91417"
    mock_get_set_by_id.return_value = None
    mock_get_set_by_pokemon_api_set_id.return_value = None
    mock_get_set_by_canonical_key.return_value = None
    mock_get_set_by_name.return_value = None
    mock_repo.return_value = _snapshot("run-swsh6")

    result = get_latest_evr_run_snapshot(target_type="set", target_id=uuid_target)

    assert result is not None
    assert result["calculation_run_id"] == "run-swsh6"
    mock_repo.assert_called_with("set", uuid_target)


@patch("backend.db.services.calculation_run_query_service.get_set_by_name")
@patch("backend.db.services.calculation_run_query_service.get_set_by_canonical_key")
@patch("backend.db.services.calculation_run_query_service.get_set_by_pokemon_api_set_id")
@patch("backend.db.services.calculation_run_query_service.get_set_by_id")
@patch("backend.db.services.calculation_run_query_service.get_latest_run_snapshot_for_target")
def test_unknown_set_target_returns_none_without_crash(
    mock_repo,
    mock_get_set_by_id,
    mock_get_set_by_pokemon_api_set_id,
    mock_get_set_by_canonical_key,
    mock_get_set_by_name,
):
    mock_get_set_by_id.return_value = None
    mock_get_set_by_pokemon_api_set_id.return_value = None
    mock_get_set_by_canonical_key.return_value = None
    mock_get_set_by_name.return_value = None
    mock_repo.return_value = None

    result = get_latest_evr_run_snapshot(target_type="set", target_id="unknown-set")

    assert result is None


@patch("backend.db.services.calculation_run_query_service.get_set_by_name")
@patch("backend.db.services.calculation_run_query_service.get_set_by_canonical_key")
@patch("backend.db.services.calculation_run_query_service.get_set_by_pokemon_api_set_id")
@patch("backend.db.services.calculation_run_query_service.get_set_by_id")
@patch("backend.db.services.calculation_run_query_service.get_latest_run_snapshot_for_target")
def test_snapshot_includes_compatibility_aliases(
    mock_repo,
    mock_get_set_by_id,
    mock_get_set_by_pokemon_api_set_id,
    mock_get_set_by_canonical_key,
    mock_get_set_by_name,
):
    mock_get_set_by_id.return_value = None
    mock_get_set_by_pokemon_api_set_id.return_value = None
    mock_get_set_by_canonical_key.return_value = None
    mock_get_set_by_name.return_value = None
    mock_repo.return_value = _snapshot("run-any")

    result = get_latest_evr_run_snapshot(target_type="set", target_id="run-any")

    assert result is not None
    assert result["calculation_run_id"] == "run-any"
    assert result["summary"]["roi_percent"] == 25.0
