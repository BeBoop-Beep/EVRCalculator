"""Mocked-DB tests for the maintained-cache health/alerting check."""
from __future__ import annotations

import backend.scripts.check_market_explorer_maintained_cache_health as health


class Response:
    def __init__(self, data):
        self.data = data


class Query:
    def __init__(self, client, name):
        self.client = client
        self.name = name
        self.eq_filters = {}

    def select(self, *_a, **_k):
        return self

    def eq(self, field, value):
        self.eq_filters[field] = value
        return self

    def in_(self, *_a, **_k):
        return self

    def order(self, *_a, **_k):
        return self

    def range(self, start, end):
        self._start, self._end = start, end
        return self

    def execute(self):
        if self.name == "pokemon_market_date_quality":
            rows = [{"market_date": d} for d in self.client.approved_dates]
            return Response(rows)
        if self.name == health.CACHE_TABLE:
            if self.eq_filters.get("status") == "building":
                return Response(list(self.client.building_rows))
            if self.eq_filters.get("cache_kind") == "maintained":
                return Response(list(self.client.maintained_rows))
            return Response([])
        if self.name == "pokemon_set_value_daily_history_coverage":
            return Response([{"set_id": "set-a"}])
        if self.name == "sets":
            return Response([{"id": "set-a", "catalog_only": False}])
        if self.name == health.V1_COVERAGE_TABLE:
            return Response([{"set_id": "set-a", "computed_through": "2026-09-05"}])
        if self.name == health.V2_COVERAGE_TABLE:
            return Response([{"set_id": "set-a", "retained_from": "2026-05-29",
                              "computed_through": "2026-09-05"}])
        raise AssertionError(self.name)


class Client:
    def __init__(self, approved_dates, maintained_rows, building_rows=()):
        self.approved_dates = approved_dates
        self.maintained_rows = maintained_rows
        self.building_rows = building_rows

    def table(self, name):
        return Query(self, name)


def test_a_failed_maintained_cache_is_alerted():
    client = Client(
        approved_dates=["2026-09-05"],
        maintained_rows=[{
            "query_fingerprint": "abc", "label": "Global All Raw", "status": "failed",
            "computed_through": "2026-09-03", "cache_kind": "maintained",
        }],
    )
    report = health.check_maintained_cache_health(client)
    assert len(report["alerts"]) == 1
    assert report["alerts"][0]["reason"] == "failed"
    assert report["alerts"][0]["fingerprint"] == "abc"


def test_a_stale_ready_cache_beyond_threshold_is_alerted():
    client = Client(
        approved_dates=["2026-09-05"],
        maintained_rows=[{
            "query_fingerprint": "def", "label": "SIR", "status": "ready",
            "computed_through": "2026-09-02", "cache_kind": "maintained",
        }],
    )
    report = health.check_maintained_cache_health(client, stale_threshold_days=1)
    assert len(report["alerts"]) == 1
    assert report["alerts"][0]["reason"] == "stale"
    assert report["alerts"][0]["age_days"] == 3


def test_a_current_ready_cache_is_not_alerted():
    client = Client(
        approved_dates=["2026-09-05"],
        maintained_rows=[{
            "query_fingerprint": "ghi", "label": "Established", "status": "ready",
            "computed_through": "2026-09-05", "cache_kind": "maintained",
        }],
    )
    report = health.check_maintained_cache_health(client)
    assert report["alerts"] == []
    assert report["ready_and_current"] == 1


def test_an_orphan_build_lease_is_alerted():
    client = Client(
        approved_dates=["2026-09-05"],
        maintained_rows=[],
        building_rows=[{
            "query_fingerprint": "jkl", "label": "Premium",
            "build_expires_at": "2020-01-01T00:00:00+00:00",
        }],
    )
    report = health.check_maintained_cache_health(client)
    assert len(report["alerts"]) == 1
    assert report["alerts"][0]["reason"] == "orphan_lease"


def test_no_approved_date_reports_cleanly_rather_than_crashing():
    client = Client(approved_dates=[], maintained_rows=[])
    report = health.check_maintained_cache_health(client)
    assert report["latest_approved_market_date"] is None
    assert report["alerts"] == []


def test_alert_payload_never_carries_bulk_cache_data():
    client = Client(
        approved_dates=["2026-09-05"],
        maintained_rows=[{
            "query_fingerprint": "abc", "label": "Global All Raw", "status": "failed",
            "computed_through": "2026-09-03", "cache_kind": "maintained",
            # Even if the discovery row somehow carried a huge payload, the
            # alert model only has room for the small identifying fields.
            "current_constituents": ["x"] * 33955,
        }],
    )
    report = health.check_maintained_cache_health(client)
    alert = report["alerts"][0]
    assert set(alert.keys()) == {
        "fingerprint", "label", "status", "computed_through",
        "latest_approved_market_date", "age_days", "reason",
    }


def test_health_reports_both_projection_freshness_contracts():
    report = health.check_maintained_cache_health(Client(
        approved_dates=["2026-09-05"], maintained_rows=[]
    ))
    assert report["v1"]["coverage_sets"] == 1
    assert report["v1"]["lagging_sets"] == []
    assert report["v2"]["coverage_sets"] == 1
    assert report["v2"]["retained_from"] == "2026-05-29"
