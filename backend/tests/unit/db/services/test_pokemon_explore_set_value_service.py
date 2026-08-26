import json
from datetime import date, timedelta

import pytest

from backend.db.services.pokemon_explore_set_value_service import (
    ExploreSetValueUnavailable,
    build_global_set_value_row,
    compute_window_movements,
)


def history(days=40, start=100.0, set_id="set-1"):
    first = date(2026, 1, 1)
    return [{"set_id": set_id, "snapshot_date": (first + timedelta(days=i)).isoformat(), "set_value": start + i} for i in range(days)]


def prepared(rows):
    return [{"date": row["snapshot_date"], "setValue": row["set_value"]} for row in rows]


def pokemon_set():
    return {"id": "set-1", "canonical_key": "alpha", "name": "Alpha", "logo_image_url": "logo"}


def test_window_semantics_keep_exact_selected_period_and_partial_status():
    # The series moves exactly $1 per calendar day, so a window's amount IS its
    # elapsed-day span. 7D must move 7.0, not the 6.0 the retired inclusive
    # `days - 1` count produced.
    points = history(15)
    windows = compute_window_movements(points)
    assert windows["7D"]["amount"] == 7.0
    assert windows["7D"]["coverage"] == "full"
    # Fifteen days of history cannot reach a 30-day target, so this falls back
    # to the Set's first observation and SAYS SO rather than presenting 14 days
    # of movement as a 30D return.
    assert windows["30D"]["amount"] == 14.0
    assert windows["30D"]["coverage"] == "partial"
    assert windows["30D"]["isSinceFirstAvailable"] is True
    assert windows["30D"]["targetStartDate"] == "2025-12-16"


def test_set_market_window_targets_match_the_canonical_resolver():
    """THE PINNED MATRIX, shared with the global Market and the frontend.

    The Set Market used to own a second date formula. It now calls
    `resolve_market_window_target`, so a 7D on /Market -> Set Market, a 7D on
    that Set's Cards Market Index and a 7D on the global Market are the same
    seven elapsed calendar days by construction.
    """
    from backend.domain.pokemon.market_index import resolve_market_window_target

    expected = {"7D": "2026-08-18", "30D": "2026-07-26", "3M": "2026-05-27",
                "6M": "2026-02-26", "1Y": "2025-08-25"}
    first = date(2025, 1, 1)
    points = [
        {"date": (first + timedelta(days=i)).isoformat(), "value": 100.0}
        for i in range((date(2026, 8, 25) - first).days + 1)
    ]
    windows = compute_window_movements(points)
    for key, target in expected.items():
        assert windows[key]["targetStartDate"] == target, key
        assert windows[key]["startDate"] == target, key
        assert windows[key]["coverage"] == "full", key
        # And it is literally the canonical resolver's answer, not a lookalike.
        assert resolve_market_window_target("2026-08-25", key) == target, key
    # 1D stays the previous OBSERVED close; lifetime stays the Set's own start.
    assert windows["1D"]["startDate"] == "2026-08-24"
    assert windows["lifetime"]["targetStartDate"] is None
    assert windows["lifetime"]["startDate"] == "2025-01-01"


def test_fresh_365d_snapshot_wins_over_stale_30d_row():
    rows = history()
    target_date = rows[-1]["snapshot_date"]
    dashboards = [
        {"set_id": "set-1", "window_key": "30d", "latest_market_date": "2025-12-01", "set_value_histories_json": {"standard": [{"date": "2025-12-01", "setValue": 9999}]}},
        {"set_id": "set-1", "window_key": "365d", "latest_market_date": target_date, "set_value_histories_json": {"standard": prepared(rows)}},
    ]
    result = build_global_set_value_row([pokemon_set()], dashboards, {"set-1": rows}, target_market_date=target_date)
    published = result["payload_json"]["sets"][0]
    assert published["currentSetValue"] == rows[-1]["set_value"]
    assert published["setValueAsOf"] == target_date
    assert published["windows"]["30D"]["amount"] == 30.0


def test_publication_fails_closed_when_set_market_and_canonical_history_disagree():
    rows = history()
    target_date = rows[-1]["snapshot_date"]
    wrong = prepared(rows)
    wrong[-1]["setValue"] += 1
    with pytest.raises(ExploreSetValueUnavailable, match="disagree"):
        build_global_set_value_row([pokemon_set()], [{"set_id": "set-1", "window_key": "365d", "latest_market_date": target_date, "set_value_histories_json": {"standard": wrong}}], {"set-1": rows}, target_market_date=target_date)


def test_compact_contract_is_not_raw_dashboard_history():
    rows = history(131)
    target_date = rows[-1]["snapshot_date"]
    result = build_global_set_value_row([pokemon_set()], [{"set_id": "set-1", "window_key": "365d", "latest_market_date": target_date, "set_value_histories_json": {"standard": prepared(rows)}}], {"set-1": rows}, target_market_date=target_date)
    published = result["payload_json"]["sets"][0]
    assert len(published["trend"]) <= 48
    assert "setValueHistoriesByScope" not in json.dumps(result["payload_json"])
    assert published["trend"][-1] == [target_date, rows[-1]["set_value"]]
    assert len(published["recentDailyTrend"]) == 30
    assert published["recentDailyTrend"] == [[row["snapshot_date"], row["set_value"]] for row in rows[-30:]]
    assert result["payload_json"]["meta"]["recentDailyTrendPointLimit"] == 30


def test_recent_daily_trend_preserves_real_missing_dates_without_fabrication():
    rows = history(35)
    missing_date = rows[-5]["snapshot_date"]
    rows = [row for row in rows if row["snapshot_date"] != missing_date]
    target_date = rows[-1]["snapshot_date"]
    result = build_global_set_value_row([pokemon_set()], [{"set_id": "set-1", "window_key": "365d", "latest_market_date": target_date, "set_value_histories_json": {"standard": prepared(rows)}}], {"set-1": rows}, target_market_date=target_date)
    recent = result["payload_json"]["sets"][0]["recentDailyTrend"]
    assert len(recent) == 30
    assert missing_date not in [point[0] for point in recent]
    assert recent == sorted(recent)
    assert recent[-1] == [target_date, rows[-1]["set_value"]]


def _published_row(days=40):
    rows = history(days)
    target_date = rows[-1]["snapshot_date"]
    dashboards = [
        {
            "set_id": "set-1",
            "window_key": "365d",
            "latest_market_date": target_date,
            "set_value_histories_json": {"standard": prepared(rows)},
        }
    ]
    built = build_global_set_value_row(
        [pokemon_set()], dashboards, {"set-1": rows}, target_market_date=target_date
    )
    return built, built["payload_json"]["sets"][0], rows


def test_every_client_selectable_window_survives_into_the_snapshot():
    """The /Market pills are pure client-side slices, so all seven must ship."""
    from backend.db.services.pokemon_explore_set_value_service import WINDOWS

    _, published, _ = _published_row(days=400)

    assert set(published["windows"]) == {key for key, _ in WINDOWS}
    assert len(published["windows"]) == 7
    for key, window in published["windows"].items():
        assert isinstance(window["amount"], float), key
        assert isinstance(window["percent"], float), key
        assert window["startDate"] <= window["endDate"], key


def test_current_set_value_matches_the_canonical_final_history_point():
    _, published, rows = _published_row()

    assert published["currentSetValue"] == rows[-1]["set_value"]
    assert published["setValueAsOf"] == rows[-1]["snapshot_date"]
    assert published["historyEndDate"] == rows[-1]["snapshot_date"]
    assert published["historyStartDate"] == rows[0]["snapshot_date"]
    assert published["historyPointCount"] == len(rows)


def test_priced_and_total_card_counts_are_not_published_as_null_fields():
    """_points() normalizes to {date, value}, so those keys could only ever be None.

    Publishing them anyway advertised two permanently-null fields on every row.
    They have no consumer, so the compact snapshot omits them entirely rather
    than shipping a misleading contract.
    """
    _, published, _ = _published_row()

    assert "pricedCardCount" not in published
    assert "totalCardCount" not in published
    # Every field the ladder actually renders must carry a real value. `era` and
    # `symbolUrl` are genuinely optional set identity, so they are excluded.
    for key in ("setId", "name", "currentSetValue", "setValueAsOf", "windows", "trend"):
        assert published[key] is not None, key


def test_prepared_history_metadata_cannot_leak_into_the_compact_row():
    """Even when the dashboard history CARRIES the counts, they are not republished."""
    rows = history()
    target_date = rows[-1]["snapshot_date"]
    rich = [
        {**point, "pricedCardCount": 111, "totalCardCount": 222}
        for point in prepared(rows)
    ]
    dashboards = [
        {
            "set_id": "set-1",
            "window_key": "365d",
            "latest_market_date": target_date,
            "set_value_histories_json": {"standard": rich},
        }
    ]
    built = build_global_set_value_row(
        [pokemon_set()], dashboards, {"set-1": rows}, target_market_date=target_date
    )
    published = built["payload_json"]["sets"][0]

    assert "pricedCardCount" not in published
    assert "totalCardCount" not in published
    assert 111 not in json.loads(json.dumps(published)).values()


def test_snapshot_row_carries_the_columns_the_table_requires():
    built, published, _ = _published_row()

    assert built["tcg"] == "pokemon"
    assert built["scope"] == "market"
    assert built["market_date"] == published["setValueAsOf"]
    assert built["set_count"] == len(built["payload_json"]["sets"])
    assert built["payload_size_bytes"] > 0
    assert len(built["source_generation_fingerprint"]) == 64
    assert built["payload_json"]["meta"]["snapshot"]["marketDate"] == built["market_date"]


def test_fingerprint_tracks_the_source_generation():
    """Same sources => same fingerprint (no write); changed value => new one."""
    rows = history()
    target_date = rows[-1]["snapshot_date"]

    def _build(history_rows):
        dashboards = [
            {
                "set_id": "set-1",
                "window_key": "365d",
                "latest_market_date": target_date,
                "set_value_histories_json": {"standard": prepared(history_rows)},
            }
        ]
        return build_global_set_value_row(
            [pokemon_set()], dashboards, {"set-1": history_rows}, target_market_date=target_date
        )["source_generation_fingerprint"]

    assert _build(rows) == _build(rows)

    moved = [dict(row) for row in rows]
    moved[-1]["set_value"] = moved[-1]["set_value"] + 1.0
    assert _build(moved) != _build(rows)
