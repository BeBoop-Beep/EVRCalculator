"""Mocked tests for the V2-only Market Explorer health check."""
from __future__ import annotations

import ast
import inspect

from backend.scripts import check_market_explorer_maintained_cache_health as health
from backend.db.services.market_explorer_surface_freshness import read_surface_freshness


class _Response:
    def __init__(self, data):
        self.data = data


class _Query:
    def __init__(self, rows):
        self.rows = rows

    def select(self, *_a, **_k):
        return self

    def eq(self, *_a, **_k):
        return self

    def in_(self, *_a, **_k):
        return self

    def order(self, *_a, **_k):
        return self

    def range(self, start, end):
        self.start, self.end = start, end
        return self

    def execute(self):
        start = getattr(self, "start", 0)
        end = getattr(self, "end", len(self.rows) - 1)
        return _Response(self.rows[start:end + 1])


class _CoverageClient:
    def __init__(self, rows):
        self.rows = rows

    def table(self, name):
        assert name == health.V2_COVERAGE_TABLE
        return _Query(self.rows)


def test_surface_freshness_adapter_is_one_compact_rpc_and_preserves_dates():
    class C:
        def __init__(self): self.calls = []
        def rpc(self, name, params):
            self.calls.append((name, params))
            return type("R", (), {"execute": lambda _self: _Response({
                "status": "CURRENT", "canonicalAcceptedDate": "2026-09-27",
                "surfaceV2Date": "2026-09-27", "surfaceLagDays": 0,
            })})()
    client = C()
    result = read_surface_freshness(client)
    assert client.calls == [("get_pokemon_market_explorer_surface_freshness_v2", {})]
    assert result["canonicalAcceptedDate"] == "2026-09-27"
    assert result["surfaceV2Date"] == "2026-09-27"


def test_v2_coverage_report_is_healthy_only_when_every_tracked_set_is_current():
    client = _CoverageClient([
        {
            "set_id": "set-a",
            "retained_from": "2026-06-03",
            "computed_through": "2026-09-10",
            "row_count": 10,
            "retention_days": 100,
        },
        {
            "set_id": "set-b",
            "retained_from": "2026-06-03",
            "computed_through": "2026-09-10",
            "row_count": 20,
            "retention_days": 100,
        },
    ])
    report = health._v2_coverage_report(
        client, {"set-a", "set-b"}, "2026-09-10",
    )
    assert report["healthy"] is True
    assert report["coverage_sets"] == 2
    assert report["authority_sets"] == 2
    assert report["lagging_sets"] == []
    assert report["retained_from"] == "2026-06-03"


def test_v2_coverage_report_flags_missing_or_lagging_sets():
    client = _CoverageClient([
        {
            "set_id": "set-a",
            "retained_from": "2026-06-03",
            "computed_through": "2026-09-09",
            "row_count": 10,
            "retention_days": 100,
        },
    ])
    report = health._v2_coverage_report(
        client, {"set-a", "set-b"}, "2026-09-10",
    )
    assert report["healthy"] is False
    assert report["lagging_sets"] == ["set-a", "set-b"]


def _patch_common(monkeypatch, maintained):
    monkeypatch.setattr(health, "resolve_latest_approved_market_date", lambda *_a: "2026-09-10")
    monkeypatch.setattr(health, "read_surface_freshness", lambda *_a: {
        "status": "CURRENT", "reason": None,
        "canonicalAcceptedDate": "2026-09-10", "surfaceV2Date": "2026-09-10",
        "surfaceLagDays": 0, "maintainedCacheTotal": len(maintained),
        "maintainedCacheCurrent": sum(r.get("status") == "ready" and r.get("computed_through") == "2026-09-10" for r in maintained),
        "maintainedCacheNotCurrent": sum(not (r.get("status") == "ready" and r.get("computed_through") == "2026-09-10") for r in maintained),
    })
    monkeypatch.setattr(
        health,
        "_v2_coverage_report",
        lambda *_a, **_k: {
            "coverage_sets": 1,
            "authority_sets": 1,
            "min_computed_through": "2026-09-10",
            "max_computed_through": "2026-09-10",
            "retained_from": "2026-06-03",
            "lagging_sets": [],
            "healthy": True,
        },
    )
    monkeypatch.setattr(health, "discover_maintained_caches", lambda *_a: maintained)
    monkeypatch.setattr(health, "_paged", lambda *_a, **_k: [])


def test_failed_maintained_cache_is_alerted(monkeypatch):
    _patch_common(monkeypatch, [{
        "query_fingerprint": "abc",
        "label": "Global All Raw",
        "status": "failed",
        "computed_through": "2026-09-09",
    }])
    report = health.check_maintained_cache_health(object())
    assert report["v2"]["healthy"] is True
    assert report["alerts"][0]["reason"] == "failed"
    assert report["alerts"][0]["fingerprint"] == "abc"


def test_stale_ready_cache_is_alerted(monkeypatch):
    _patch_common(monkeypatch, [{
        "query_fingerprint": "def",
        "label": "SIR",
        "status": "ready",
        "computed_through": "2026-09-08",
    }])
    report = health.check_maintained_cache_health(object(), stale_threshold_days=0)
    assert report["alerts"][0]["reason"] == "stale"
    assert report["alerts"][0]["age_days"] == 2


def test_current_ready_cache_is_clean(monkeypatch):
    _patch_common(monkeypatch, [{
        "query_fingerprint": "ghi",
        "label": "Global All",
        "status": "ready",
        "computed_through": "2026-09-10",
    }])
    report = health.check_maintained_cache_health(object())
    assert report["alerts"] == []
    assert report["ready_and_current"] == 1


def test_no_approved_date_reports_cleanly(monkeypatch):
    monkeypatch.setattr(health, "read_surface_freshness", lambda *_a: {
        "status": "NO_ACCEPTED_MARKET_DATE", "canonicalAcceptedDate": None,
    })
    report = health.check_maintained_cache_health(object())
    assert report["latest_approved_market_date"] is None
    assert report["alerts"] == []


def test_compact_freshness_rpc_exposes_stale_surface_even_when_caches_are_current(monkeypatch):
    _patch_common(monkeypatch, [{
        "query_fingerprint": "ghi", "label": "Global All", "status": "ready",
        "computed_through": "2026-09-10",
    }])
    monkeypatch.setattr(health, "read_surface_freshness", lambda *_a: {
        "status": "STALE", "reason": "SURFACE_V2_PUBLICATION_LAG",
        "canonicalAcceptedDate": "2026-09-10", "surfaceV2Date": "2026-09-09",
        "surfaceLagDays": 1, "maintainedCacheTotal": 1,
        "maintainedCacheCurrent": 1, "maintainedCacheNotCurrent": 0,
    })
    report = health.check_maintained_cache_health(object())
    assert report["v2"]["healthy"] is False
    assert report["v2"]["surface_lag_days"] == 1
    assert report["ready_and_current"] == 1


def test_health_module_contains_no_exact_v1_coverage_relation_literal():
    tree = ast.parse(inspect.getsource(health))
    strings = {
        node.value for node in ast.walk(tree)
        if isinstance(node, ast.Constant) and isinstance(node.value, str)
    }
    assert "pokemon_market_explorer_card_daily_coverage" not in strings
