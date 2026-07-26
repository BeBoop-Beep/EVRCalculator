import sys

import pytest

from backend.scripts import build_pokemon_explore_rankings_snapshot as command


def test_rankings_publishes_when_gate_disabled(monkeypatch):
    upserted = []
    monkeypatch.setenv("PUBLICATION_GATE_MODE", "disabled")
    monkeypatch.setattr(sys, "argv", ["build_pokemon_explore_rankings_snapshot.py", "--all", "--commit"])
    monkeypatch.setattr(command, "get_client", lambda: object())
    monkeypatch.setattr(command, "build_explore_rankings_snapshot_row", lambda limit=None: {"tcg": "pokemon"})
    monkeypatch.setattr(command, "upsert_row", lambda *_a, commit=None, **_k: upserted.append(commit))

    command.main()

    assert upserted == [True]


def test_rankings_defers_with_exit_3_when_gate_closed(monkeypatch, capsys):
    built = []
    monkeypatch.delenv("PUBLICATION_GATE_MODE", raising=False)
    monkeypatch.setattr(sys, "argv", ["build_pokemon_explore_rankings_snapshot.py", "--all", "--commit"])
    monkeypatch.setattr(command, "get_client", lambda: object())  # no batch authority => closed
    monkeypatch.setattr(command, "build_explore_rankings_snapshot_row", lambda limit=None: built.append(1))
    monkeypatch.setattr(command, "upsert_row", lambda *_a, **_k: built.append("write"))

    with pytest.raises(SystemExit) as excinfo:
        command.main()

    assert excinfo.value.code == 3
    assert built == []
    assert "publication gate CLOSED" in capsys.readouterr().out
