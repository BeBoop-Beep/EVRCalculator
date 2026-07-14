import sys

from postgrest.exceptions import APIError

from backend.scripts import build_pokemon_set_cards_snapshots as command


def test_cards_snapshot_parser_paces_all_sets_but_allows_zero():
    defaults = command.build_parser().parse_args(["--all"])
    disabled = command.build_parser().parse_args(["--all", "--delay-seconds", "0"])

    assert defaults.delay_seconds == 0.35
    assert defaults.max_consecutive_transient_failures == 3
    assert disabled.delay_seconds == 0


def test_cards_build_stops_after_consecutive_transient_retry_exhaustion(monkeypatch, capsys):
    attempted = []
    real_retry = command.run_snapshot_operation_with_retry

    monkeypatch.setattr(
        sys,
        "argv",
        [
            "build_pokemon_set_cards_snapshots.py",
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

    def fail_refresh(_client, set_id, **_kwargs):
        attempted.append(set_id)
        raise APIError(
            {
                "message": "schema cache unavailable",
                "code": "PGRST002",
                "hint": None,
                "details": None,
            }
        )

    monkeypatch.setattr(command, "refresh_canonical_card_market_prices_for_set", fail_refresh)
    monkeypatch.setattr(command, "build_coordinated_set_market_snapshot_rows", lambda _set_row, **_kwargs: ({}, {}, []))
    monkeypatch.setattr(command, "upsert_row", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(command, "upsert_rows", lambda *_args, **_kwargs: None)

    command.main()

    assert attempted == ["bad-1"] * 3 + ["bad-2"] * 3
    assert "built=0 failed=2" in capsys.readouterr().out
