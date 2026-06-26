from datetime import datetime, timedelta, timezone

from backend.scripts import refresh_stale_public_snapshots as refresh


def _iso(dt):
    return dt.astimezone(timezone.utc).isoformat()


def _row(set_id: str, set_updated: str, rankings_embedded: str, *, include_ranks: bool = True):
    summary = {
        "target_id": set_id,
        "set_id": set_id,
        "name": "Set",
    }
    if include_ranks:
        summary["pack_rank"] = 3
        summary["profit_rank"] = 4
    return {
        "set_id": set_id,
        "updated_at": set_updated,
        "payload_json": {
            "summary": summary,
            "meta": {
                "snapshotCompleteness": {
                    "explore_rankings_snapshot_updated_at": rankings_embedded,
                },
                "sectionFreshness": {
                    "decisionSignalRanks": {
                        "status": "fresh",
                    }
                },
                "warnings": [],
                "sources": {"simulation_input_cards": "OK"},
            },
            "top_hits": [{"card_name": "Chase"}],
        },
    }


def test_verify_set_page_no_false_positive_when_set_page_newer_than_rankings_and_ranks_present(monkeypatch):
    t0 = datetime(2026, 6, 25, 10, 0, tzinfo=timezone.utc)
    rankings_updated = _iso(t0)
    set_updated = _iso(t0 + timedelta(minutes=12))

    monkeypatch.setattr(
        refresh,
        "_read_snapshot_row",
        lambda _client, table, _select_fields, _filters: (
            {"updated_at": rankings_updated} if table == "pokemon_explore_rankings_snapshot_latest" else _row("set-1", set_updated, rankings_updated)
        ),
    )
    monkeypatch.setattr(refresh, "_has_known_stale_warning", lambda _warnings: False)
    monkeypatch.setattr(refresh, "_source_rows_exist_for_set_page", lambda _client, _set_id: True)

    problems = refresh._verify_set_page(None, {"id": "set-1", "canonical_key": "whiteFlare"}, rankings_updated_at=rankings_updated)

    assert problems == []


def test_verify_set_page_stale_when_rankings_rebuilt_after_set_page(monkeypatch):
    t0 = datetime(2026, 6, 25, 10, 0, tzinfo=timezone.utc)
    set_updated = _iso(t0)
    rankings_updated = _iso(t0 + timedelta(minutes=15))

    monkeypatch.setattr(
        refresh,
        "_read_snapshot_row",
        lambda _client, table, _select_fields, _filters: (
            {"updated_at": rankings_updated} if table == "pokemon_explore_rankings_snapshot_latest" else _row("set-1", set_updated, set_updated)
        ),
    )
    monkeypatch.setattr(refresh, "_has_known_stale_warning", lambda _warnings: False)
    monkeypatch.setattr(refresh, "_source_rows_exist_for_set_page", lambda _client, _set_id: True)

    problems = refresh._verify_set_page(None, {"id": "set-1", "canonical_key": "whiteFlare"}, rankings_updated_at=rankings_updated)

    assert any("rankings snapshot rebuilt after set page snapshot" in problem for problem in problems)


def test_verify_set_page_stale_when_rank_fields_missing(monkeypatch):
    t0 = datetime(2026, 6, 25, 10, 0, tzinfo=timezone.utc)
    rankings_updated = _iso(t0)

    monkeypatch.setattr(
        refresh,
        "_read_snapshot_row",
        lambda _client, table, _select_fields, _filters: (
            {"updated_at": rankings_updated}
            if table == "pokemon_explore_rankings_snapshot_latest"
            else _row("set-1", rankings_updated, rankings_updated, include_ranks=False)
        ),
    )
    monkeypatch.setattr(refresh, "_has_known_stale_warning", lambda _warnings: False)
    monkeypatch.setattr(refresh, "_source_rows_exist_for_set_page", lambda _client, _set_id: True)

    problems = refresh._verify_set_page(None, {"id": "set-1", "canonical_key": "whiteFlare"}, rankings_updated_at=rankings_updated)

    assert any("rank fields missing" in problem for problem in problems)
