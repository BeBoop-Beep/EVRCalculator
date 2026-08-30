import subprocess

import pytest

from backend.scripts.recover_pokemon_market_date import recover_range


class Result:
    def __init__(self, data): self.data = data


class Query:
    def __init__(self, rows): self.rows = rows
    def select(self, *_): return self
    def eq(self, key, value): self.rows = [r for r in self.rows if r.get(key) == value]; return self
    def limit(self, _): return self
    def execute(self): return Result(self.rows)


class Client:
    def __init__(self, rows): self.rows = rows
    def table(self, name): assert name == "pokemon_scrape_batches"; return Query(list(self.rows))


def batch(day, status="complete", missing=0):
    return {"id": day, "market_date": day, "status": status, "expected_set_count": 165,
            "succeeded_set_count": 165 if status == "complete" else 10,
            "missing_set_count": missing, "promoted_at": "now", "runtime_git_sha": "sha",
            "runtime_registry_hash": "hash"}


def runner(calls, fail_at=None):
    def run(command, **_kwargs):
        calls.append(command)
        code = 1 if fail_at and fail_at in " ".join(command) else 0
        return subprocess.CompletedProcess(command, code, stdout="{}", stderr="failed" if code else "")
    return run


def test_missing_or_incomplete_batch_refuses_before_any_command():
    calls = []
    with pytest.raises(RuntimeError): recover_range(Client([]), start="2026-08-29", end="2026-08-29", commit=True, runner=runner(calls))
    with pytest.raises(RuntimeError): recover_range(Client([batch("2026-08-29", "running")]), start="2026-08-29", end="2026-08-29", commit=True, runner=runner(calls))
    assert calls == []


def test_complete_batch_runs_repair_then_snapshots_then_audit():
    calls = []
    report = recover_range(Client([batch("2026-08-29")]), start="2026-08-29", end="2026-08-29", commit=True, runner=runner(calls))
    assert report["ok"] is True
    assert [command[1] for command in calls] == [
        "backend/scripts/repair_pokemon_set_value_history.py",
        "backend/scripts/refresh_stale_public_snapshots.py",
        "backend/scripts/audit_pokemon_market_publication.py",
    ]


@pytest.mark.parametrize("failure", ["repair_pokemon", "refresh_stale", "audit_pokemon"])
def test_each_failed_dependency_stops_immediately(failure):
    calls = []
    with pytest.raises(RuntimeError):
        recover_range(Client([batch("2026-08-29")]), start="2026-08-29", end="2026-08-29", commit=True, runner=runner(calls, failure))
    assert failure in " ".join(calls[-1])


def test_range_is_ascending_and_first_date_failure_blocks_second():
    rows = [batch("2026-08-30"), batch("2026-08-29")]
    calls = []
    with pytest.raises(RuntimeError):
        recover_range(Client(rows), start="2026-08-29", end="2026-08-30", commit=True,
                      runner=runner(calls, "repair_pokemon"))
    assert all("2026-08-30" not in " ".join(command) for command in calls)


def test_dry_run_is_idempotent_and_does_not_build():
    calls = []
    result = recover_range(Client([batch("2026-08-29"), batch("2026-08-30")]),
                           start="2026-08-29", end="2026-08-30", commit=False, runner=runner(calls))
    assert [row["market_date"] for row in result["dates"]] == ["2026-08-29", "2026-08-30"]
    assert calls == []
