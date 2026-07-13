import sys

from backend.scripts import build_pokemon_market_dashboard_snapshots as command
from backend.scripts.set_value_scope_invariants import SetValueScopeInvariantError


def test_one_bad_set_does_not_stop_later_dashboard_sets(monkeypatch, capsys):
    built = []
    upserted = []

    monkeypatch.setattr(sys, "argv", ["build_pokemon_market_dashboard_snapshots.py", "--all", "--commit"])
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
