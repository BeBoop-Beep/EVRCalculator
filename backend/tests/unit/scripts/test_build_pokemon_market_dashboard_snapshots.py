import sys

import pytest
from postgrest.exceptions import APIError

from backend.scripts import build_pokemon_market_dashboard_snapshots as command
from backend.scripts.set_value_scope_invariants import SetValueScopeInvariantError


def test_one_bad_set_does_not_stop_later_dashboard_sets(monkeypatch, capsys):
    built = []
    upserted = []

    # Sanctioned local/test gate mode so the fail-closed gate does not block the
    # object() client used to exercise the build loop.
    monkeypatch.setenv("PUBLICATION_GATE_MODE", "disabled")
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
        return (
            {"set_id": "good-set"},
            {"set_id": "good-set", "window_key": "365d"},
            [],
        )

    monkeypatch.setattr(command, "build_coordinated_set_market_snapshot_rows", build)
    monkeypatch.setattr(command, "refresh_canonical_card_market_prices_for_set", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(command, "upsert_rows", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(command, "upsert_row", lambda _client, _table, row, **_kwargs: upserted.append(row["set_id"]))

    command.main()

    assert built == ["bad-set", "good-set"]
    assert upserted == ["good-set", "good-set"]
    assert "built=1 skipped=0 failed=1" in capsys.readouterr().out


def test_consecutive_transient_retry_exhaustion_stops_all_set_build(monkeypatch, capsys):
    attempted = []
    real_retry = command.run_snapshot_operation_with_retry

    monkeypatch.setenv("PUBLICATION_GATE_MODE", "disabled")
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

    monkeypatch.setattr(command, "build_coordinated_set_market_snapshot_rows", fail_build)
    monkeypatch.setattr(command, "refresh_canonical_card_market_prices_for_set", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(command, "upsert_rows", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(command, "upsert_row", lambda *_args, **_kwargs: None)

    command.main()

    assert attempted == ["bad-1"] * 3 + ["bad-2"] * 3
    assert "built=0 skipped=0 failed=2" in capsys.readouterr().out


def test_cards_market_defers_with_exit_3_when_gate_closed(monkeypatch, capsys):
    # A closed (required-mode) gate must defer before any build/write happens.
    built = []
    monkeypatch.delenv("PUBLICATION_GATE_MODE", raising=False)
    monkeypatch.setattr(sys, "argv", ["build_pokemon_market_dashboard_snapshots.py", "--all", "--commit"])
    monkeypatch.setattr(command, "get_client", lambda: object())  # no batch authority => closed
    monkeypatch.setattr(command, "should_commit", lambda _args: True)
    monkeypatch.setattr(command, "resolve_target_sets", lambda _c, _a: [{"id": "set-1"}])
    monkeypatch.setattr(command, "build_coordinated_set_market_snapshot_rows", lambda *_a, **_k: built.append(1))
    monkeypatch.setattr(command, "refresh_canonical_card_market_prices_for_set", lambda *_a, **_k: None)
    monkeypatch.setattr(command, "upsert_row", lambda *_a, **_k: None)
    monkeypatch.setattr(command, "upsert_rows", lambda *_a, **_k: None)

    # main() returns the process exit code (the __main__ guard raises SystemExit
    # with it), matching build_pokemon_set_page_snapshots.py.
    code = command.main()

    assert code == 3
    assert built == []
    assert "publication gate CLOSED" in capsys.readouterr().out
