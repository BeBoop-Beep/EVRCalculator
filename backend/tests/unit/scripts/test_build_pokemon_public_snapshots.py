import sys
import types

import pytest

from backend.scripts import build_pokemon_public_snapshots as command


def _stub_gate(monkeypatch, *, proceed, exit_code=0):
    enforcement = types.SimpleNamespace(
        decision=types.SimpleNamespace(reason_code="test", reason="test"),
        proceed=proceed,
        exit_code=exit_code,
    )
    monkeypatch.setattr(command, "get_client", lambda: object())
    monkeypatch.setattr(command, "enforce_cli_publication_gate", lambda *_a, **_k: enforcement)


def test_orchestration_defers_and_runs_no_children_when_gate_closed(monkeypatch):
    # A closed gate at the orchestration level must NOT spawn any child step.
    steps_run = []
    _stub_gate(monkeypatch, proceed=False, exit_code=3)
    monkeypatch.setattr(command, "_run_step", lambda label, args: steps_run.append(label) or 0)
    monkeypatch.setattr(sys, "argv", ["build_pokemon_public_snapshots.py", "--commit"])

    with pytest.raises(SystemExit) as excinfo:
        command.main()

    assert excinfo.value.code == 3
    assert steps_run == []


def test_orchestration_runs_children_when_gate_open(monkeypatch):
    steps_run = []
    _stub_gate(monkeypatch, proceed=True)
    monkeypatch.setattr(command, "_run_step", lambda label, args: steps_run.append(label) or 0)
    monkeypatch.setattr(sys, "argv", ["build_pokemon_public_snapshots.py", "--commit"])

    command.main()  # all steps exit 0 => no SystemExit

    assert len(steps_run) == 3


def test_orchestration_child_deferral_propagates_exit_3(monkeypatch):
    # If a child races and defers (exit 3), the pipeline reports deferred, not failed.
    _stub_gate(monkeypatch, proceed=True)
    monkeypatch.setattr(
        command,
        "_run_step",
        lambda label, args: 3 if label == "explore rankings" else 0,
    )
    monkeypatch.setattr(sys, "argv", ["build_pokemon_public_snapshots.py", "--commit"])

    with pytest.raises(SystemExit) as excinfo:
        command.main()

    assert excinfo.value.code == 3


def test_orchestration_child_failure_propagates_exit_1(monkeypatch):
    _stub_gate(monkeypatch, proceed=True)
    monkeypatch.setattr(
        command,
        "_run_step",
        lambda label, args: 1 if label == "set pages" else 0,
    )
    monkeypatch.setattr(sys, "argv", ["build_pokemon_public_snapshots.py", "--commit"])

    with pytest.raises(SystemExit) as excinfo:
        command.main()

    assert excinfo.value.code == 1


def test_orchestration_forwards_override_to_children(monkeypatch):
    captured = []
    _stub_gate(monkeypatch, proceed=True)
    monkeypatch.setattr(command, "_run_step", lambda label, args: captured.append(args) or 0)
    monkeypatch.setattr(
        sys, "argv",
        ["build_pokemon_public_snapshots.py", "--commit", "--force-publish", "--market-date", "2026-07-25"],
    )

    command.main()

    for args in captured:
        assert "--force-publish" in args
        assert "--market-date" in args and "2026-07-25" in args
