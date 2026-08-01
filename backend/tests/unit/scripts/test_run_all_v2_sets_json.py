import json

from backend.scripts import run_all_v2_sets as script


class Approved:
    SET_NAME = "Future Set"
    ERA = "Mega Evolution"
    USE_MONTE_CARLO_V2 = True
    PULL_MODEL_STATUS = "approved"


def test_json_preflight_reports_exact_match(monkeypatch, capsys):
    monkeypatch.setattr(script, "discover_sets", lambda: {"futureSet": Approved})
    monkeypatch.setattr("sys.argv", ["run_all_v2_sets.py", "--set", "futureSet", "--dry-run", "--json"])
    assert script.main() == 0
    line = next(line for line in capsys.readouterr().out.splitlines() if line.startswith("SIMULATION_JSON="))
    payload = json.loads(line.split("=", 1)[1])
    assert payload["matched_set_count"] == 1
    assert payload["matched_sets"][0] == {
        "canonical_key": "futureSet", "set_name": "Future Set",
        "use_monte_carlo_v2": True, "pull_model_status": "approved",
    }


def test_json_preflight_reports_zero_matches(monkeypatch, capsys):
    monkeypatch.setattr(script, "discover_sets", lambda: {})
    monkeypatch.setattr("sys.argv", ["run_all_v2_sets.py", "--set", "missing", "--dry-run", "--json"])
    assert script.main() == 0
    line = next(line for line in capsys.readouterr().out.splitlines() if line.startswith("SIMULATION_JSON="))
    assert json.loads(line.split("=", 1)[1])["matched_set_count"] == 0
