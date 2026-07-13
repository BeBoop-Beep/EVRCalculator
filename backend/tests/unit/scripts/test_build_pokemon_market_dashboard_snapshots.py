import sys
from postgrest.exceptions import APIError

from backend.scripts import build_pokemon_market_dashboard_snapshots as command
from backend.scripts.set_value_scope_invariants import SetValueScopeInvariantError


def test_one_bad_set_does_not_stop_later_dashboard_sets(monkeypatch, capsys):
    built = []
    upserted = []

    monkeypatch.setattr(
        sys,
        "argv",
        ["build_pokemon_market_dashboard_snapshots.py", "--all", "--commit", "--delay-seconds", "0"],
    )
    monkeypatch.setattr(command, "get_client", lambda: object())
    monkeypatch.setattr(
        command,
        "resolve_target_sets",
        lambda _client, _args: [
            {"id": "bad-set", "name": "Bad Set"},
            {"id": "good-set", "name": "Good Set"},
        ],
    )
    monkeypatch.setattr(command, "should_commit", lambda _args: True)

    def build(set_row, **_kwargs):
        built.append(set_row["id"])
        if set_row["id"] == "bad-set":
            raise SetValueScopeInvariantError(
                {
                    "code": "POKEMON_SET_VALUE_SCOPE_INVARIANT",
                    "setId": "bad-set",
                    "date": "2026-06-16",
                    "scope": "hits",
                    "subsetValue": 200,
                    "checklistValue": 100,
                }
            )
        return ({"set_id": "good-set", "window_key": "365d"}, [])

    monkeypatch.setattr(command, "build_market_dashboard_snapshot_rows", build)
    monkeypatch.setattr(command, "upsert_rows", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(command, "upsert_row", lambda _client, _table, row, **_kwargs: upserted.append(row["set_id"]))

    command.main()

    assert built == ["bad-set", "good-set"]
    assert upserted == ["good-set"]
    assert "built=1 skipped=0 failed=1" in capsys.readouterr().out


def test_consecutive_transient_retry_exhaustion_stops_all_set_build(monkeypatch, capsys):
    attempted = []
    real_retry = command.run_snapshot_operation_with_retry

    monkeypatch.setattr(
        sys,
        "argv",
        [
            "build_pokemon_market_dashboard_snapshots.py",
            "--all",
            "--commit",
            "--delay-seconds",
            "0",
            "--max-consecutive-transient-failures",
            "2",
        ],
    )
    monkeypatch.setattr(command, "get_client", lambda: object())
    monkeypatch.setattr(
        command,
        "resolve_target_sets",
        lambda _client, _args: [
            {"id": "bad-1", "name": "Bad 1"},
            {"id": "bad-2", "name": "Bad 2"},
            {"id": "must-not-run", "name": "Must Not Run"},
        ],
    )
    monkeypatch.setattr(command, "should_commit", lambda _args: True)
    monkeypatch.setattr(
        command,
        "run_snapshot_operation_with_retry",
        lambda operation, **kwargs: real_retry(
            operation,
            **kwargs,
            sleep=lambda _delay: None,
            jitter=lambda _start, _end: 0,
        ),
    )

    def fail_build(set_row, **_kwargs):
        attempted.append(set_row["id"])
        raise APIError({"message": "schema cache unavailable", "code": "PGRST002", "hint": None, "details": None})

    monkeypatch.setattr(command, "build_market_dashboard_snapshot_rows", fail_build)
    monkeypatch.setattr(command, "upsert_rows", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(command, "upsert_row", lambda *_args, **_kwargs: None)

    command.main()

    assert attempted == ["bad-1"] * 3 + ["bad-2"] * 3
    assert "built=0 skipped=0 failed=2" in capsys.readouterr().out
