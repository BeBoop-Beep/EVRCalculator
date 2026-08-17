import sys

import pytest

from backend.db.services.explore_page_service import ExplorePageError
from backend.scripts import build_pokemon_set_page_snapshots as command


def _run(monkeypatch, *, build, argv=None, gate_mode="disabled"):
    # Unit tests run in an explicitly-configured test environment, so the
    # publication gate is put in its sanctioned local/test `disabled` mode unless
    # a test wants to exercise real (required) gate behaviour.
    if gate_mode is None:
        monkeypatch.delenv("PUBLICATION_GATE_MODE", raising=False)
    else:
        monkeypatch.setenv("PUBLICATION_GATE_MODE", gate_mode)
    monkeypatch.setattr(command, "get_client", lambda: object())
    monkeypatch.setattr(command, "should_commit", lambda _args: True)
    monkeypatch.setattr(
        command,
        "resolve_target_sets",
        lambda _client, _args: [{"id": "set-1", "name": "Alpha"}, {"id": "set-2", "name": "Beta"}],
    )
    monkeypatch.setattr(command, "build_set_page_snapshot_row", build)
    monkeypatch.setattr(command, "upsert_row", lambda *_a, **_k: None)
    monkeypatch.setattr(sys, "argv", argv or ["build_pokemon_set_page_snapshots.py", "--all", "--commit"])
    return command.main()


def test_cli_exit_zero_when_all_pages_build(monkeypatch, capsys):
    code = _run(monkeypatch, build=lambda set_row, client=None: {"set_id": set_row["id"]})
    assert code == 0
    assert "built=2" in capsys.readouterr().out


def test_cli_exit_nonzero_when_a_page_fails(monkeypatch, capsys):
    def build(set_row, client=None):
        if set_row["id"] == "set-2":
            raise ExplorePageError(status_code=500, message="boom", code="SUMMARY_QUERY_FAILED")
        return {"set_id": set_row["id"]}

    code = _run(monkeypatch, build=build)
    assert code == 1
    out = capsys.readouterr().out
    assert "built=1" in out
    assert "failed=1" in out


def test_failed_required_contract_build_never_overwrites_previous_snapshot(monkeypatch, capsys):
    upserted = []
    monkeypatch.setenv("PUBLICATION_GATE_MODE", "disabled")
    monkeypatch.setattr(command, "get_client", lambda: object())
    monkeypatch.setattr(command, "should_commit", lambda _args: True)
    monkeypatch.setattr(command, "resolve_target_sets", lambda _client, _args: [{"id": "set-1", "name": "Alpha"}])
    monkeypatch.setattr(command, "build_set_page_snapshot_row",
                        lambda *_a, **_k: (_ for _ in ()).throw(RuntimeError("required Top Chase missing")))
    monkeypatch.setattr(command, "upsert_row", lambda *_a, **_k: upserted.append(1))
    monkeypatch.setattr(sys, "argv", ["build_pokemon_set_page_snapshots.py", "--set-id", "set-1", "--commit"])

    assert command.main() == 1
    assert upserted == []
    assert "built=0 skipped=0 failed=1" in capsys.readouterr().out


# --------------------------------------------------------------------------- #
# Publication gate wiring (Area 5).
# --------------------------------------------------------------------------- #
def test_cli_defers_with_exit_3_when_gate_closed(monkeypatch, capsys):
    # Real (required) gate + a client with no batch authority => closed => defer.
    built = []
    upserted = []
    monkeypatch.delenv("PUBLICATION_GATE_MODE", raising=False)
    monkeypatch.setattr(command, "get_client", lambda: object())  # object() has no .table
    monkeypatch.setattr(command, "should_commit", lambda _args: True)
    monkeypatch.setattr(command, "resolve_target_sets", lambda _c, _a: [{"id": "set-1"}])
    monkeypatch.setattr(command, "build_set_page_snapshot_row", lambda set_row, client=None: built.append(1))
    monkeypatch.setattr(command, "upsert_row", lambda *_a, **_k: upserted.append(1))
    monkeypatch.setattr(sys, "argv", ["build_pokemon_set_page_snapshots.py", "--all", "--commit"])

    code = command.main()

    assert code == 3  # GATE_DEFERRED_EXIT_CODE
    assert built == [] and upserted == []
    assert "publication gate CLOSED" in capsys.readouterr().out


def test_cli_manual_override_publishes_through_closed_gate(monkeypatch, capsys):
    built = []
    monkeypatch.delenv("PUBLICATION_GATE_MODE", raising=False)
    code = _run(
        monkeypatch,
        build=lambda set_row, client=None: (built.append(set_row["id"]) or {"set_id": set_row["id"]}),
        argv=["build_pokemon_set_page_snapshots.py", "--all", "--commit", "--force-publish"],
        gate_mode=None,
    )
    assert code == 0
    assert built == ["set-1", "set-2"]
    assert "OVERRIDDEN" in capsys.readouterr().out


def test_cli_dry_run_reports_gate_decision_and_no_commit(monkeypatch, capsys):
    seen_commit = []
    monkeypatch.delenv("PUBLICATION_GATE_MODE", raising=False)
    monkeypatch.setattr(command, "get_client", lambda: object())
    monkeypatch.setattr(command, "should_commit", lambda args: bool(args.commit))
    monkeypatch.setattr(command, "resolve_target_sets", lambda _c, _a: [{"id": "set-1"}])
    monkeypatch.setattr(command, "build_set_page_snapshot_row", lambda set_row, client=None: {"set_id": set_row["id"]})
    monkeypatch.setattr(command, "upsert_row", lambda *_a, commit=None, **_k: seen_commit.append(commit))
    monkeypatch.setattr(sys, "argv", ["build_pokemon_set_page_snapshots.py", "--all", "--dry-run"])

    code = command.main()

    assert code == 0
    # No real writes: every upsert saw commit=False.
    assert seen_commit and all(value is False for value in seen_commit)
    assert "publication gate decision (dry-run)" in capsys.readouterr().out
