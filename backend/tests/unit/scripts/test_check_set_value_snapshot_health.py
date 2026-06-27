import sys

import pytest

from backend.scripts import check_set_value_snapshot_health as health


def test_health_report_flags_future_dates_after_phoenix_current_date(monkeypatch):
    set_rows = [
        {"id": "set-1", "canonical_key": "alpha", "name": "Alpha"},
    ]
    raw_dates = {
        ("set-1", "standard"): "2026-06-27",
        ("set-1", "hits"): None,
        ("set-1", "top10"): None,
    }
    dashboards = {
        "set-1": {
            "latest_market_date": "2026-06-27",
            "set_value_histories_json": {
                "standard": [{"date": "2026-06-27", "setValue": 100}],
            },
        },
    }

    monkeypatch.setattr(health, "_set_rows", lambda _client, _set_id: set_rows)
    monkeypatch.setattr(health, "_read_dashboard_row", lambda _client, set_id, _window: dashboards[set_id])
    monkeypatch.setattr(health, "latest_observation_utc_for_set", lambda _client, _set_id: "2026-06-27T01:30:00+00:00")
    monkeypatch.setattr(
        health,
        "_latest_raw_date_for_scope",
        lambda _client, set_id, scope: raw_dates[(set_id, scope)],
    )

    report = health.analyze_set_value_snapshot_health(None, local_current_date="2026-06-26")

    assert report["market_day_timezone"] == "America/Phoenix"
    assert report["local_current_date"] == "2026-06-26"
    assert report["issue_set_count"] == 1
    assert report["issue_scope_count"] == 2
    assert {row["scope"] for row in report["issues"]} == {"dashboard", "standard"}
    assert {row["latest_observation_local_date"] for row in report["issues"]} == {"2026-06-26"}
    assert any(row["reason"] == "set value snapshot_date is after local current date" for row in report["issues"])


def test_health_report_flags_utc_shifted_snapshot_date(monkeypatch):
    monkeypatch.setattr(health, "_set_rows", lambda _client, _set_id: [{"id": "set-1", "canonical_key": "chaosRising", "name": "Chaos Rising"}])
    monkeypatch.setattr(
        health,
        "_read_dashboard_row",
        lambda _client, _set_id, _window: {
            "latest_market_date": "2026-06-27",
            "set_value_histories_json": {"standard": [{"date": "2026-06-27", "setValue": 100}]},
        },
    )
    monkeypatch.setattr(health, "latest_observation_utc_for_set", lambda _client, _set_id: "2026-06-27T01:46:00+00:00")
    monkeypatch.setattr(
        health,
        "_latest_raw_date_for_scope",
        lambda _client, _set_id, scope: "2026-06-27" if scope == "standard" else None,
    )

    report = health.analyze_set_value_snapshot_health(None, local_current_date="2026-06-27")

    assert report["issue_set_count"] == 1
    assert any(
        row["scope"] == "standard"
        and row["latest_raw_observation_utc"] == "2026-06-27T01:46:00+00:00"
        and row["latest_observation_local_date"] == "2026-06-26"
        and row["latest_set_value_snapshot_date"] == "2026-06-27"
        for row in report["issues"]
    )


def test_health_report_marks_missing_market_dashboard_stale(monkeypatch):
    monkeypatch.setattr(health, "_set_rows", lambda _client, _set_id: [{"id": "set-1", "canonical_key": "alpha", "name": "Alpha"}])
    monkeypatch.setattr(health, "_read_dashboard_row", lambda _client, _set_id, _window: None)
    monkeypatch.setattr(health, "latest_observation_utc_for_set", lambda _client, _set_id: "2026-06-25T12:00:00+00:00")
    monkeypatch.setattr(
        health,
        "_latest_raw_date_for_scope",
        lambda _client, _set_id, scope: "2026-06-25" if scope == "standard" else None,
    )

    report = health.analyze_set_value_snapshot_health(None, local_current_date="2026-06-25")

    assert report["stale_set_count"] == 1
    assert report["stale_scope_count"] == 1
    assert report["stale_sets"][0]["latest_market_dashboard_date"] is None


def test_health_report_flags_implausible_hits_rollup(monkeypatch):
    monkeypatch.setattr(health, "_set_rows", lambda _client, _set_id: [{"id": "set-1", "canonical_key": "alpha", "name": "Alpha"}])
    monkeypatch.setattr(
        health,
        "_read_dashboard_row",
        lambda _client, _set_id, _window: {
            "latest_market_date": "2026-06-26",
            "set_value_histories_json": {
                "standard": [{"date": "2026-06-26", "setValue": 90}],
                "hits": [{"date": "2026-06-26", "setValue": 2241823}],
            },
        },
    )
    monkeypatch.setattr(health, "latest_observation_utc_for_set", lambda _client, _set_id: "2026-06-26T12:00:00+00:00")
    monkeypatch.setattr(health, "_latest_raw_date_for_scope", lambda _client, _set_id, _scope: "2026-06-26")
    monkeypatch.setattr(
        health,
        "_latest_raw_metrics_by_scope",
        lambda _client, _set_id: {
            "standard": {"snapshot_date": "2026-06-26", "set_value": 90, "priced_card_count": 3},
            "hits": {"snapshot_date": "2026-06-26", "set_value": 2241823, "priced_card_count": 4},
            "top10": {"snapshot_date": "2026-06-26", "set_value": 90, "priced_card_count": 3},
        },
    )

    report = health.analyze_set_value_snapshot_health(
        None,
        local_current_date="2026-06-26",
        extreme_hits_threshold=100000,
    )

    reasons = {row["reason"] for row in report["issues"]}
    assert "hits set_value is implausibly above standard set_value" in reasons
    assert "hits priced_card_count exceeds standard priced_card_count" in reasons
    assert "hits set_value exceeds extreme threshold" in reasons


def test_health_script_strict_exits_nonzero_when_stale(monkeypatch, capsys):
    monkeypatch.setattr(health, "get_client", lambda: None)
    monkeypatch.setattr(
        health,
        "analyze_set_value_snapshot_health",
        lambda _client, **_kwargs: {
            "total_sets_with_raw_history": 1,
            "stale_set_count": 1,
            "stale_scope_count": 1,
            "worst_days_behind": 5,
            "stale_sets": [],
        },
    )
    monkeypatch.setattr(sys, "argv", ["check_set_value_snapshot_health.py", "--strict"])

    with pytest.raises(SystemExit) as exc:
        health.main()

    assert exc.value.code == 1
    assert "issue_set_count = 1" in capsys.readouterr().out


def test_health_script_json_output(monkeypatch, capsys):
    monkeypatch.setattr(health, "get_client", lambda: None)
    monkeypatch.setattr(
        health,
        "analyze_set_value_snapshot_health",
        lambda _client, **_kwargs: {
            "total_sets_with_raw_history": 0,
            "stale_set_count": 0,
            "stale_scope_count": 0,
            "worst_days_behind": 0,
            "stale_sets": [],
        },
    )
    monkeypatch.setattr(sys, "argv", ["check_set_value_snapshot_health.py", "--json", "--strict"])

    health.main()

    assert '"stale_set_count": 0' in capsys.readouterr().out
