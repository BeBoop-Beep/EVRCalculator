from datetime import date, timedelta

from backend.db.services.pokemon_explore_set_value_service import build_global_set_value_row


def _history(days=40):
    first = date(2026, 1, 1)
    return [
        {
            "set_id": "set-1",
            "snapshot_date": (first + timedelta(days=i)).isoformat(),
            "set_value": 100.0 + i,
        }
        for i in range(days)
    ]


def _market_set(*, ready=True):
    return {
        "id": "set-1",
        "canonical_key": "alpha",
        "name": "Alpha",
        "era": "Test Era",
        "market_scope": "standard",
        "market_publication_ready": ready,
    }


def test_certified_market_path_publishes_without_dashboard_snapshot():
    rows = _history()
    target = rows[-1]["snapshot_date"]
    result = build_global_set_value_row(
        [_market_set()], [], {"set-1": rows}, target_market_date=target
    )
    assert result["set_count"] == 1
    assert result["payload_json"]["sets"][0]["currentSetValue"] == rows[-1]["set_value"]
    assert result["payload_json"]["meta"]["source"] == "canonical_root_set_market_history_v1"
    assert result["_diagnostics"]["marketAuthorityMode"] is True


def test_uncertified_but_current_market_scope_still_publishes_current():
    """MEMBERSHIP != CERTIFICATION: an uncertified (market_publication_ready=False)
    set whose canonical history still reaches today still appears on the Market
    page, annotated as current -- it is never dropped from the result set."""
    rows = _history()
    target = rows[-1]["snapshot_date"]
    result = build_global_set_value_row(
        [_market_set(ready=False)], [], {"set-1": rows}, target_market_date=target
    )
    assert result["set_count"] == 1
    published = result["payload_json"]["sets"][0]
    assert published["currentSetValue"] == rows[-1]["set_value"]
    assert published["valueStatus"] == "current"
    assert result["_diagnostics"]["eligibleSetCount"] == 1


def test_stale_certification_still_publishes_with_stale_annotation():
    """A set whose canonical history has not reached the target market date
    (e.g. Paldean Fates-shaped: complete coverage, but not every component
    price is dated on/after the canonical market date) still publishes, with
    its last-known value and an honest stale annotation -- never suppressed."""
    rows = _history(days=40)
    target_date = date.fromisoformat(rows[-1]["snapshot_date"]) + timedelta(days=1)
    target = target_date.isoformat()
    result = build_global_set_value_row(
        [_market_set(ready=False)], [], {"set-1": rows}, target_market_date=target
    )
    assert result["set_count"] == 1
    published = result["payload_json"]["sets"][0]
    assert published["currentSetValue"] == rows[-1]["set_value"]
    assert published["valueStatus"] == "stale"
    assert published["lastUpdated"] == rows[-1]["snapshot_date"]
    assert result["_diagnostics"]["staleSets"] == [
        {"setId": "set-1", "canonicalDate": rows[-1]["snapshot_date"]}
    ]


def test_no_price_identity_at_all_publishes_as_unavailable_not_dropped():
    """A set with no canonical Set Value history at all (genuinely insufficient
    price identity) still appears on the Market page -- explicitly unavailable,
    never a fabricated value, and never dropped from the result set."""
    result = build_global_set_value_row(
        [_market_set(ready=False)], [], {"set-1": []}, target_market_date="2026-09-09"
    )
    assert result["set_count"] == 1
    published = result["payload_json"]["sets"][0]
    assert published["currentSetValue"] is None
    assert published["valueStatus"] == "unavailable"
    assert published["lastUpdated"] is None
    assert result["_diagnostics"]["missingSets"] == ["set-1"]


def test_stale_optional_dashboard_does_not_veto_certified_set_value():
    rows = _history()
    target = rows[-1]["snapshot_date"]
    dashboard = {
        "set_id": "set-1",
        "window_key": "365d",
        "latest_market_date": "2025-01-01",
        "set_value_histories_json": {"standard": [{"date": "2025-01-01", "setValue": 99999.0}]},
        "cardsMarket": {"marketIndex": {"currentValue": None}},
    }
    result = build_global_set_value_row(
        [_market_set()], [dashboard], {"set-1": rows}, target_market_date=target
    )
    assert result["set_count"] == 1
    assert result["payload_json"]["sets"][0]["currentSetValue"] == rows[-1]["set_value"]
    assert result["_diagnostics"]["staleOptionalDashboardSetIds"] == ["set-1"]


def test_current_malformed_optional_market_index_is_omitted_not_authoritative():
    rows = _history()
    target = rows[-1]["snapshot_date"]
    dashboard = {
        "set_id": "set-1",
        "window_key": "365d",
        "latest_market_date": target,
        "cardsMarket": {
            "marketIndex": {
                "currentValue": None,
                "asOf": target,
                "movements": {"7D": {"available": True}},
            }
        },
    }
    result = build_global_set_value_row(
        [_market_set()], [dashboard], {"set-1": rows}, target_market_date=target
    )
    published = result["payload_json"]["sets"][0]
    assert "marketIndex" not in published
    assert result["_diagnostics"]["missingMarketIndexSetIds"] == ["set-1"]
    assert result["_diagnostics"]["invalidOptionalMarketIndexSetIds"] == ["set-1"]
