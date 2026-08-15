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

    assert steps_run == [
        "set sealed market snapshots",
        "coordinated set cards and market dashboards",
        "global market set value",
        "global explore card movers",
        "explore rankings",
        "set pages",
    ]


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


# The sealed step's CLI predates the batch publication gate and takes neither
# flag, so it is deliberately invoked without the gate context.
_STEPS_WITHOUT_GATE_CONTEXT = {"set sealed market snapshots"}


def test_orchestration_forwards_override_to_children(monkeypatch):
    captured = []
    _stub_gate(monkeypatch, proceed=True)
    monkeypatch.setattr(command, "_run_step", lambda label, args: captured.append((label, args)) or 0)
    monkeypatch.setattr(
        sys, "argv",
        ["build_pokemon_public_snapshots.py", "--commit", "--force-publish", "--market-date", "2026-07-25"],
    )

    command.main()

    forwarded = [label for label, _ in captured if label not in _STEPS_WITHOUT_GATE_CONTEXT]
    assert "global market set value" in forwarded
    for label, args in captured:
        if label in _STEPS_WITHOUT_GATE_CONTEXT:
            continue
        assert "--force-publish" in args, label
        assert "--market-date" in args and "2026-07-25" in args, label


def test_global_set_value_runs_after_the_coordinated_dashboard_publication(monkeypatch):
    """The aggregate validates against the PREPARED 365d dashboard histories.

    Running it before the coordinated dashboard step would validate the candidate
    against the previous generation, so the ordering is a correctness contract,
    not a preference. It must also precede nothing that depends on it.
    """
    steps_run = []
    _stub_gate(monkeypatch, proceed=True)
    monkeypatch.setattr(command, "_run_step", lambda label, args: steps_run.append(label) or 0)
    monkeypatch.setattr(sys, "argv", ["build_pokemon_public_snapshots.py", "--commit"])

    command.main()

    assert "global market set value" in steps_run, (
        "a full public build that omits the global Market Set Value stage can publish every "
        "surrounding artifact and still leave /Market's Set Value ladder empty"
    )
    assert steps_run.index("global market set value") > steps_run.index(
        "coordinated set cards and market dashboards"
    )


def test_global_set_value_step_invokes_the_existing_builder_script(monkeypatch):
    """No second implementation of build_global_set_value_row may exist."""
    captured = {}
    _stub_gate(monkeypatch, proceed=True)
    monkeypatch.setattr(
        command, "_run_step", lambda label, args: captured.__setitem__(label, args) or 0
    )
    monkeypatch.setattr(sys, "argv", ["build_pokemon_public_snapshots.py", "--dry-run"])

    command.main()

    args = captured["global market set value"]
    assert args[0] == "backend/scripts/build_pokemon_explore_set_value_snapshot.py"
    assert "--dry-run" in args
