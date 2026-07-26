"""Behavioral tests for durable, transactional finalization (Phase 5)."""

from types import SimpleNamespace

import pytest

import backend.db.repositories.scrape_jobs_repository as repo


class _FakeRpc:
    """Records rpc calls and replays a scripted sequence of execute() outcomes."""

    def __init__(self, behaviors):
        self._behaviors = list(behaviors)
        self.calls = []

    def rpc(self, name, params=None):
        self.calls.append((name, params))
        behavior = self._behaviors.pop(0) if self._behaviors else ("data", [])

        def execute():
            kind, value = behavior
            if kind == "raise":
                raise value
            return SimpleNamespace(data=value)

        return SimpleNamespace(execute=execute)


@pytest.fixture(autouse=True)
def _no_sleep(monkeypatch):
    monkeypatch.setattr(repo.time, "sleep", lambda *_: None)


def test_transient_finalization_failure_is_retried_then_succeeds(monkeypatch):
    fake = _FakeRpc([
        ("raise", RuntimeError("connection reset by peer")),
        ("raise", RuntimeError("gateway timeout 504")),
        ("data", [{"ok": True, "idempotent": False, "job_id": 42, "status": "completed"}]),
    ])
    monkeypatch.setattr(repo, "supabase", fake)

    result = repo.finalize_scrape_job(42, "diag-1", "completed", succeeded=1, failed=0)

    assert result["ok"] is True
    assert len(fake.calls) == 3  # two transient failures then success
    assert fake.calls[0][0] == "finalize_scrape_job"


def test_permanent_finalization_failure_is_surfaced_and_recorded(monkeypatch, tmp_path):
    fake = _FakeRpc([("raise", RuntimeError("connection reset")) for _ in range(repo._FINALIZE_MAX_ATTEMPTS)])
    monkeypatch.setattr(repo, "supabase", fake)
    monkeypatch.setattr(repo, "_RECOVERY_DIR", tmp_path / "recovery")

    result = repo.finalize_scrape_job(99, "diag-9", "failed", succeeded=0, failed=1,
                                      error_summary="scraper crashed")

    # Failure is surfaced (not swallowed) ...
    assert result["ok"] is False
    assert result["job_id"] == 99
    # ... and a durable local recovery record exists for the watchdog to reconcile.
    records = list((tmp_path / "recovery").glob("finalize_job_99_*.json"))
    assert len(records) == 1
    assert "scraper crashed" in records[0].read_text(encoding="utf-8")


def test_non_transient_error_is_not_retried(monkeypatch):
    fake = _FakeRpc([("raise", ValueError("invalid final status foo"))])
    monkeypatch.setattr(repo, "supabase", fake)
    monkeypatch.setattr(repo, "_write_finalization_recovery_record", lambda record: "rec")

    result = repo.finalize_scrape_job(7, None, "failed")

    assert result["ok"] is False
    assert len(fake.calls) == 1  # not retried


def test_invalid_final_status_raises_before_any_db_call(monkeypatch):
    fake = _FakeRpc([])
    monkeypatch.setattr(repo, "supabase", fake)
    with pytest.raises(ValueError):
        repo.finalize_scrape_job(1, None, "aborted")
    assert fake.calls == []


def test_finalize_passes_diag_run_id_for_consistent_finalization(monkeypatch):
    fake = _FakeRpc([("data", [{"ok": True}])])
    monkeypatch.setattr(repo, "supabase", fake)

    repo.finalize_scrape_job(5, "diag-5", "completed", succeeded=1, failed=0)

    _, params = fake.calls[0]
    # queue + diagnostic run are finalized together (one RPC, one transaction)
    assert params["p_job_id"] == 5
    assert params["p_diag_run_id"] == "diag-5"
    assert params["p_final_status"] == "completed"
