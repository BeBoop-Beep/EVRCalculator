"""Unit tests for the Bucket 3A dry-run/commit builder wrapper.

No live DB: uses a small fake client and a fake lock to exercise the
control-flow contract (source-identity resolution, skip-if-published,
drift-abort, dry-run report, already_running).
"""

from __future__ import annotations

from typing import Any, Dict, List

import pytest

from backend.scripts import build_budget_product_best_open_price_snapshot as builder


class _Resp:
    def __init__(self, data):
        self.data = data


class _Query:
    def __init__(self, rows):
        self._rows = list(rows)

    def select(self, *_a, **_k):
        return self

    def eq(self, field, value):
        self._rows = [r for r in self._rows if str(r.get(field)) == str(value)]
        return self

    def limit(self, n):
        self._rows = self._rows[:n]
        return self

    def execute(self):
        return _Resp(self._rows)


class FakeClient:
    def __init__(self, tables: Dict[str, List[Dict[str, Any]]]):
        self._tables = dict(tables)
        self.published = []

    def table(self, name):
        return _Query(self._tables.get(name, []))

    def rpc(self, name, params):
        self.published.append((name, params))
        return _Query([{"data": "new-snap-id"}])


class FakeLock:
    def __init__(self, acquirable=True):
        self._acquirable = acquirable
        self.released = False

    def acquire(self):
        return self._acquirable

    def release(self):
        self.released = True


SOURCE = {
    "id": "src-1", "published_at": "2026-09-01T00:00:00Z", "market_date": "2026-09-01",
    "cohort_fingerprint": "fp-1", "eligible_cohort_count": 2, "full_market_budget": 1400,
    "ranking_method_version": "rmv1", "allocation_method_version": "amv1",
    "comparison_scope_version": "csv1", "financial_rip_version": "frv4", "overall_rip_version": "orv12",
    "collector_appeal_version": "cav1",
    "chase_accessibility_version": "chase-exact-v1",
    "chase_accessibility_transform_version": "chase-transform-exact-v1",
}

LATEST_POINTER = [{"ranking_method_version": "rmv1", "allocation_method_version": "amv1", "snapshot_id": "src-1"}]

ENGINE_ROW = {
    "sealedProductId": "p1", "setId": "s1", "productFamily": "booster_box", "sourceCalculationRunId": "run1",
    "currentMarketPrice": 100.0, "currentQuantity": 14, "currentBudgetRank": 1, "currentOverallRipV12Score": 0.9,
    "currentFinancialRipV4Score": 0.75, "currentCollectorAppealScore": 0.6, "currentChaseAccessibilityRaw": 0.5,
    "currentChanceToRecoverCapital": 0.7, "currentActualCommittedCapital": 1400.0,
    "status": "current_number_one_with_headroom", "bestOpenPrice": 110.0, "thresholdQuantity": 12,
    "priceGapDollars": -10.0, "priceGapPercent": -0.1, "benchmarkSealedProductId": "p2",
    "benchmarkOverallRipV12Score": 0.8, "benchmarkFinancialRipV4Score": 0.65,
    "benchmarkChanceToRecoverCapital": 0.6, "benchmarkActualCommittedCapital": 1600.0,
    "candidatePriceEvaluations": 5, "bracketExpansions": 2,
    "bracketRefinements": 3, "fallbackCount": 0, "searchWallSeconds": 1.2,
}


def _client(extra_snapshots=None):
    return FakeClient({
        "budget_product_ranking_latest": LATEST_POINTER,
        "budget_product_ranking_snapshots": [SOURCE],
        "budget_product_best_open_price_snapshots": list(extra_snapshots or []),
    })


def test_reports_already_running_without_touching_source(tmp_path):
    client = _client()
    result = builder.run(
        client=client, engine_rows=[ENGINE_ROW], unresolved_count=1, runtime_seconds=1.0,
        diagnostics_json={}, ranking_method_version="rmv1", allocation_method_version="amv1",
        commit=False, report_path=tmp_path / "report.json", lock=FakeLock(acquirable=False),
    )
    assert result == {"status": "already_running"}


def test_skips_when_already_published_for_this_exact_identity(tmp_path):
    client = _client(extra_snapshots=[{
        "id": "existing", "source_budget_snapshot_id": "src-1",
        "source_budget_published_at": "2026-09-01T00:00:00Z",
        "best_open_price_method_version": builder.BEST_OPEN_PRICE_METHOD_VERSION,
    }])
    result = builder.run(
        client=client, engine_rows=[ENGINE_ROW], unresolved_count=1, runtime_seconds=1.0,
        diagnostics_json={}, ranking_method_version="rmv1", allocation_method_version="amv1",
        commit=False, report_path=tmp_path / "report.json", lock=FakeLock(),
    )
    assert result == {"status": "already_published", "sourceBudgetSnapshotId": "src-1"}


def test_raises_on_resolved_plus_unresolved_mismatch(tmp_path):
    client = _client()
    with pytest.raises(RuntimeError, match="expected total"):
        builder.run(
            client=client, engine_rows=[ENGINE_ROW], unresolved_count=5, runtime_seconds=1.0,
            diagnostics_json={}, ranking_method_version="rmv1", allocation_method_version="amv1",
            commit=False, report_path=tmp_path / "report.json", lock=FakeLock(),
        )


def test_dry_run_writes_local_report_and_does_not_call_rpc(tmp_path):
    client = _client()
    report_path = tmp_path / "report.json"
    result = builder.run(
        client=client, engine_rows=[ENGINE_ROW], unresolved_count=1, runtime_seconds=1.0,
        diagnostics_json={}, ranking_method_version="rmv1", allocation_method_version="amv1",
        commit=False, report_path=report_path, lock=FakeLock(),
    )
    assert result["status"] == "dry_run"
    assert report_path.exists()
    assert client.published == []
    assert result["snapshot"]["chase_accessibility_version"] == "chase-exact-v1"
    assert result["snapshot"]["chase_accessibility_transform_version"] == "chase-transform-exact-v1"


def test_commit_calls_the_publication_rpc(tmp_path):
    client = _client()
    result = builder.run(
        client=client, engine_rows=[ENGINE_ROW], unresolved_count=1, runtime_seconds=1.0,
        diagnostics_json={}, ranking_method_version="rmv1", allocation_method_version="amv1",
        commit=True, report_path=tmp_path / "report.json", lock=FakeLock(),
    )
    assert result["status"] == "published"
    assert len(client.published) == 1
    assert client.published[0][0] == "publish_budget_product_best_open_price_snapshot"


def test_lock_is_released_even_on_exception(tmp_path):
    client = _client()
    lock = FakeLock()
    with pytest.raises(RuntimeError):
        builder.run(
            client=client, engine_rows=[ENGINE_ROW], unresolved_count=5, runtime_seconds=1.0,
            diagnostics_json={}, ranking_method_version="rmv1", allocation_method_version="amv1",
            commit=False, report_path=tmp_path / "report.json", lock=lock,
        )
    assert lock.released is True


def test_verify_no_drift_aborts_when_live_source_changed():
    stale_source = dict(SOURCE)
    drifted_client = FakeClient({
        "budget_product_ranking_latest": LATEST_POINTER,
        "budget_product_ranking_snapshots": [dict(SOURCE, published_at="2026-09-02T00:00:00Z")],
    })
    with pytest.raises(RuntimeError, match="drifted during computation"):
        builder.verify_no_drift(
            drifted_client, stale_source, ranking_method_version="rmv1", allocation_method_version="amv1",
        )
