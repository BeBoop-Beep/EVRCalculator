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
    points = history(15)
    windows = compute_window_movements(points)
    assert windows["7D"]["amount"] == 6.0
    assert windows["7D"]["coverage"] == "full"
    assert windows["30D"]["amount"] == 14.0
    assert windows["30D"]["coverage"] == "partial"
    assert windows["30D"]["isSinceFirstAvailable"] is True


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
    assert published["windows"]["30D"]["amount"] == 29.0


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
