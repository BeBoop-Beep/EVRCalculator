import subprocess
from types import SimpleNamespace

import pytest

from backend.scripts.recover_pokemon_market_date import recover_range


CURRENT_HASH = "current-hash"


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


def approved_preflight():
    return SimpleNamespace(ok=True, registry_hashes_match=True, database_cohort_count=165,
                           database_cohort_hash=CURRENT_HASH, to_dict=lambda: {"ok": True})


def batch(day, status="complete", missing=0, expected=165, registry_hash=CURRENT_HASH):
    return {"id": day, "market_date": day, "status": status, "expected_set_count": expected,
            "succeeded_set_count": expected if status == "complete" else 10,
            "missing_set_count": missing, "promoted_at": "now", "runtime_git_sha": "sha",
            "runtime_registry_hash": registry_hash}


def runner(calls, fail_at=None, payload="{}"):
    def run(command, **_kwargs):
        calls.append(command)
        code = 1 if fail_at and fail_at in " ".join(command) else 0
        return subprocess.CompletedProcess(command, code, stdout=payload, stderr="failed" if code else "")
    return run


def recover(client, calls, *, start="2026-08-29", end="2026-08-29", commit=True, run=None):
    return recover_range(client, start=start, end=end, commit=commit,
                         runner=run or runner(calls), preflight_runner=approved_preflight)


def test_missing_or_incomplete_batch_refuses_before_any_command():
    calls = []
    with pytest.raises(RuntimeError): recover(Client([]), calls)
    with pytest.raises(RuntimeError): recover(Client([batch("2026-08-29", "running")]), calls)
    assert calls == []


def test_complete_current_batch_runs_repair_then_snapshots_then_audit():
    calls = []
    report = recover(Client([batch("2026-08-29")]), calls)
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
        recover(Client([batch("2026-08-29")]), calls, run=runner(calls, failure))
    assert failure in " ".join(calls[-1])


def test_range_is_ascending_and_first_date_failure_blocks_second():
    calls = []
    rows = [batch("2026-08-30"), batch("2026-08-29")]
    with pytest.raises(RuntimeError):
        recover(Client(rows), calls, start="2026-08-29", end="2026-08-30",
                run=runner(calls, "repair_pokemon"))
    assert all("2026-08-30" not in " ".join(command) for command in calls)


def test_expected_drift_dry_run_is_non_mutating_and_operator_safe():
    calls = []
    payload = '{"ok": true, "mode": "dry_run", "repair_needed": true}'
    result = recover(Client([batch("2026-08-29")]), calls, commit=False,
                     run=runner(calls, payload=payload))
    assert result["dates"][0]["repair_preview"]["result"]["repair_needed"] is True
    assert len(calls) == 1 and "--commit" not in calls[0]


def test_stale_163_set_old_hash_batch_is_rejected_and_current_is_accepted():
    calls = []
    with pytest.raises(RuntimeError, match="stale cohort count"):
        recover(Client([batch("2026-08-29", expected=163, registry_hash="old-hash")]), calls)
    assert calls == []
    result = recover(Client([batch("2026-08-29")]), calls, commit=False)
    assert result["dates"][0]["registry_provenance_approved"] is True


def test_current_count_with_old_hash_is_rejected():
    calls = []
    with pytest.raises(RuntimeError, match="stale registry hash"):
        recover(Client([batch("2026-08-29", registry_hash="old-hash")]), calls)
    assert calls == []


def test_range_prevalidates_provenance_before_advancing_any_date():
    calls = []
    rows = [batch("2026-08-29"), batch("2026-08-30", expected=163, registry_hash="old-hash")]
    with pytest.raises(RuntimeError, match="stale cohort count"):
        recover(Client(rows), calls, start="2026-08-29", end="2026-08-30")
    assert calls == []
