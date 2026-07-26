import sys

from backend.db.services.explore_page_service import ExplorePageError
from backend.scripts import build_pokemon_set_page_snapshots as command


def _run(monkeypatch, *, build):
    monkeypatch.setattr(command, "get_client", lambda: object())
    monkeypatch.setattr(command, "should_commit", lambda _args: True)
    monkeypatch.setattr(
        command,
        "resolve_target_sets",
        lambda _client, _args: [{"id": "set-1", "name": "Alpha"}, {"id": "set-2", "name": "Beta"}],
    )
    monkeypatch.setattr(command, "build_set_page_snapshot_row", build)
    monkeypatch.setattr(command, "upsert_row", lambda *_a, **_k: None)
    monkeypatch.setattr(sys, "argv", ["build_pokemon_set_page_snapshots.py", "--all", "--commit"])
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
