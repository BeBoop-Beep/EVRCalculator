"""finalize_scrape_job_run surfaces failures instead of silently returning None."""

from types import SimpleNamespace

import pytest

import backend.db.repositories.scrape_diagnostics_repository as diag


class _FakeTableQuery:
    def __init__(self, behaviors):
        self._behaviors = behaviors

    def update(self, _payload):
        return self

    def eq(self, _col, _val):
        return self

    def execute(self):
        kind, value = self._behaviors.pop(0)
        if kind == "raise":
            raise value
        return SimpleNamespace(data=value)


class _FakeSupabase:
    def __init__(self, behaviors):
        self._behaviors = behaviors
        self.table_calls = 0

    def table(self, _name):
        self.table_calls += 1
        return _FakeTableQuery(self._behaviors)


@pytest.fixture(autouse=True)
def _no_sleep(monkeypatch):
    monkeypatch.setattr(diag.time, "sleep", lambda *_: None)


def test_transient_diag_finalization_retried_then_succeeds(monkeypatch):
    fake = _FakeSupabase([
        ("raise", RuntimeError("connection reset")),
        ("data", [{"id": "run-1", "status": "success"}]),
    ])
    monkeypatch.setattr(diag, "supabase", fake)

    result = diag.finalize_scrape_job_run("run-1", {"status": "success"})

    assert result["ok"] is True
    assert fake.table_calls == 2


def test_permanent_diag_finalization_surfaces_failure(monkeypatch):
    fake = _FakeSupabase([("raise", RuntimeError("connection reset"))
                          for _ in range(diag._DIAG_MAX_ATTEMPTS)])
    monkeypatch.setattr(diag, "supabase", fake)

    result = diag.finalize_scrape_job_run("run-9", {"status": "failed"})

    assert result["ok"] is False
    assert result["reason"] == "db_error"


def test_no_rows_updated_is_surfaced_not_swallowed(monkeypatch):
    fake = _FakeSupabase([("data", [])])
    monkeypatch.setattr(diag, "supabase", fake)

    result = diag.finalize_scrape_job_run("missing", {"status": "success"})

    assert result["ok"] is False
    assert result["reason"] == "no_rows_updated"
