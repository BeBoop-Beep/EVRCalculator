import sys

import pytest

from backend.scripts import build_pokemon_explore_rankings_snapshot as command


def test_rankings_publishes_when_gate_disabled(monkeypatch):
    published = []
    monkeypatch.setenv("PUBLICATION_GATE_MODE", "disabled")
    monkeypatch.setattr(sys, "argv", ["build_pokemon_explore_rankings_snapshot.py", "--all", "--commit"])
    class _Client:
        def table(self, _name):
            return self
        def select(self, _fields):
            return self
        def eq(self, _field, _value):
            return self
        def limit(self, _value):
            return self
        def execute(self):
            return type("Result", (), {"data": []})()
        def rpc(self, name, params):
            published.append((name, params))
            return self

    monkeypatch.setattr(command, "get_client", _Client)
    row = {"tcg": "pokemon", "ranking_payload_json": {"meta": {}, "targets": []}}
    monkeypatch.setattr(command, "build_explore_rankings_snapshot_row", lambda **_kwargs: row)
    monkeypatch.setattr(command, "_publication_contract", lambda _row: ({"id": "snapshot-1", "market_date": "2026-08-01"}, [{"set_id": "s1"}]))
    monkeypatch.setattr(command, "_previous_calendar_day_payload", lambda *_args: None)
    monkeypatch.setattr(command, "attach_daily_rip_rank_movements", lambda payload, _previous: payload)

    command.main()

    assert published[0][0] == "publish_pokemon_public_rip_leaderboard"


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
