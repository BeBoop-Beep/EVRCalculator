import sys

import pytest

from backend.scripts import build_pokemon_explore_rankings_snapshot as command


def test_rankings_publishes_when_gate_disabled(monkeypatch):
    published = []
    monkeypatch.setenv("PUBLICATION_GATE_MODE", "disabled")
    monkeypatch.setattr(sys, "argv", ["build_pokemon_explore_rankings_snapshot.py", "--all", "--commit"])
    client = object()
    monkeypatch.setattr(command, "get_client", lambda: client)
    monkeypatch.setattr(
        command,
        "publish_explore_rip_rankings_snapshot",
        lambda client, **kwargs: published.append((client, kwargs)),
    )

    command.main()

    assert len(published) == 1
    assert published[0][0] is client
    assert published[0][1] == {
        "limit": command.DEFAULT_RANKINGS_LIMIT, "market_date": None, "commit": True,
    }


def test_rankings_defers_with_exit_3_when_gate_closed(monkeypatch, capsys):
    built = []
    monkeypatch.delenv("PUBLICATION_GATE_MODE", raising=False)
    monkeypatch.setattr(sys, "argv", ["build_pokemon_explore_rankings_snapshot.py", "--all", "--commit"])
    monkeypatch.setattr(command, "get_client", lambda: object())  # no batch authority => closed
    monkeypatch.setattr(command, "publish_explore_rip_rankings_snapshot", lambda *_a, **_k: built.append(1))

    with pytest.raises(SystemExit) as excinfo:
        command.main()

    assert excinfo.value.code == 3
    assert built == []
    assert "publication gate CLOSED" in capsys.readouterr().out
