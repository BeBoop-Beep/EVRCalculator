import json
import subprocess

import pytest

from backend.db.services.pokemon_scrape_runtime_preflight import RuntimePreflightReport
from backend.scripts import create_daily_scrape_batch as script


def _stub_preflight(monkeypatch, *, ok=True):
    """Batch creation now runs a runtime/database registry preflight first.

    These tests are about the post-batch detector, so the preflight is stubbed
    rather than allowed to reach the real database.
    """
    report = RuntimePreflightReport(runtime_git_sha="deadbeef", loaded_eras=["testEra"])
    report.local_registry_hash = "hash-local"
    report.database_cohort_hash = "hash-local"
    if not ok:
        report.missing_local_keys = ["ghostSet"]
    monkeypatch.setattr(script, "run_runtime_preflight", lambda: report)
    monkeypatch.setattr(
        script, "persist_runtime_provenance",
        lambda batch_id, preflight: {"status": "recorded"},
    )
    return report


def test_detector_failure_does_not_change_batch_success(monkeypatch, capsys):
    monkeypatch.setattr(script, "_load_backend_env", lambda: None)
    monkeypatch.setattr(script, "_market_date_iso", lambda timezone_name: "2026-08-01")
    _stub_preflight(monkeypatch)
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
    _stub_preflight(monkeypatch)
    monkeypatch.setattr(
        script, "create_batch",
        lambda *_: {"id": 8, "market_date": "2026-08-01", "status": "pending",
                    "expected_set_count": 1, "queued_set_count": 1},
    )
    monkeypatch.setattr("sys.argv", ["create_daily_scrape_batch.py", "--skip-new-set-detection"])
    assert script.main() == 0
    assert json.loads(capsys.readouterr().out)["new_set_discovery"] == {"status": "skipped"}


def test_failed_preflight_blocks_batch_creation_and_the_detector(monkeypatch, capsys):
    """A registry mismatch must stop everything before any job is enqueued."""
    monkeypatch.setattr(script, "_load_backend_env", lambda: None)
    monkeypatch.setattr(script, "_market_date_iso", lambda timezone_name: "2026-08-01")
    _stub_preflight(monkeypatch, ok=False)
    monkeypatch.setattr(
        script, "create_batch",
        lambda *_: pytest.fail("create_batch must not run after a failed preflight"),
    )
    monkeypatch.setattr(
        script, "run_new_set_discovery",
        lambda timeout: pytest.fail("detector must not run after a failed preflight"),
    )
    # Alerting is best-effort and must not reach the network in a unit test.
    monkeypatch.setattr(
        "backend.alerts.scrape_alerts.alert_runtime_registry_mismatch",
        lambda market_date, report: None,
    )
    monkeypatch.setattr("sys.argv", ["create_daily_scrape_batch.py"])

    assert script.main() == 1
    # The failure is reported as the structured preflight report.
    assert json.loads(capsys.readouterr().out)["ok"] is False


def test_unrecorded_provenance_is_not_reported_as_a_verified_batch(monkeypatch, capsys):
    monkeypatch.setattr(script, "_load_backend_env", lambda: None)
    monkeypatch.setattr(script, "_market_date_iso", lambda timezone_name: "2026-08-01")
    _stub_preflight(monkeypatch)
    monkeypatch.setattr(
        script, "persist_runtime_provenance",
        lambda batch_id, preflight: {"status": "failed", "error": "no batch row updated"},
    )
    monkeypatch.setattr(
        script, "create_batch",
        lambda *_: {"id": 9, "market_date": "2026-08-01", "status": "pending",
                    "expected_set_count": 1, "queued_set_count": 1},
    )
    monkeypatch.setattr(script, "run_new_set_discovery", lambda timeout: {"status": "completed"})
    monkeypatch.setattr("sys.argv", ["create_daily_scrape_batch.py"])

    # The batch is real, but claiming it is fully verified would be a lie.
    assert script.main() == 1
    assert json.loads(capsys.readouterr().out)["runtime_provenance"]["status"] == "failed"


def test_successful_batch_records_runtime_provenance(monkeypatch, capsys):
    monkeypatch.setattr(script, "_load_backend_env", lambda: None)
    monkeypatch.setattr(script, "_market_date_iso", lambda timezone_name: "2026-08-01")
    _stub_preflight(monkeypatch)
    monkeypatch.setattr(
        script, "create_batch",
        lambda *_: {"id": 10, "market_date": "2026-08-01", "status": "pending",
                    "expected_set_count": 1, "queued_set_count": 1},
    )
    monkeypatch.setattr(script, "run_new_set_discovery", lambda timeout: {"status": "completed"})
    monkeypatch.setattr("sys.argv", ["create_daily_scrape_batch.py"])

    assert script.main() == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["runtime_provenance"]["status"] == "recorded"
    assert payload["runtime_preflight"]["runtime"]["git_sha"] == "deadbeef"


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
