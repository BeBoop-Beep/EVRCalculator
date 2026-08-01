import json
import subprocess

from backend.scripts import create_daily_scrape_batch as script


def test_detector_failure_does_not_change_batch_success(monkeypatch, capsys):
    monkeypatch.setattr(script, "_load_backend_env", lambda: None)
    monkeypatch.setattr(script, "_market_date_iso", lambda timezone_name: "2026-08-01")
    monkeypatch.setattr(
        script, "create_batch",
        lambda market_date, trigger_source: {
            "id": 7, "market_date": market_date, "status": "pending",
            "expected_set_count": 3, "queued_set_count": 3,
        },
    )
    monkeypatch.setattr(script, "run_new_set_discovery", lambda timeout: {"status": "failed"})
    monkeypatch.setattr("sys.argv", ["create_daily_scrape_batch.py"])
    assert script.main() == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["batch_id"] == 7
    assert payload["new_set_discovery"]["status"] == "failed"


def test_skip_detector(monkeypatch, capsys):
    monkeypatch.setattr(script, "_load_backend_env", lambda: None)
    monkeypatch.setattr(script, "_market_date_iso", lambda timezone_name: "2026-08-01")
    monkeypatch.setattr(
        script, "create_batch",
        lambda *_: {"id": 8, "market_date": "2026-08-01", "status": "pending",
                    "expected_set_count": 1, "queued_set_count": 1},
    )
    monkeypatch.setattr("sys.argv", ["create_daily_scrape_batch.py", "--skip-new-set-detection"])
    assert script.main() == 0
    assert json.loads(capsys.readouterr().out)["new_set_discovery"] == {"status": "skipped"}


def test_detector_timeout_is_best_effort(monkeypatch):
    monkeypatch.setattr(
        script.subprocess, "run",
        lambda *args, **kwargs: (_ for _ in ()).throw(subprocess.TimeoutExpired(args[0], 5)),
    )
    assert script.run_new_set_discovery(5) == {"status": "timed_out", "timeout_seconds": 5}


def test_check_only_never_invokes_detector(monkeypatch):
    monkeypatch.setattr(script, "_load_backend_env", lambda: None)
    monkeypatch.setattr(script, "_market_date_iso", lambda timezone_name: "2026-08-01")
    monkeypatch.setattr(script, "check_only", lambda market_date, deadline: 0)
    monkeypatch.setattr(
        script, "run_new_set_discovery",
        lambda timeout: (_ for _ in ()).throw(AssertionError("detector invoked")),
    )
    monkeypatch.setattr("sys.argv", ["create_daily_scrape_batch.py", "--check-only"])
    assert script.main() == 0
