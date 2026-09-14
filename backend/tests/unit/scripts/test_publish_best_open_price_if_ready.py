from __future__ import annotations

from pathlib import Path

from backend.scripts import publish_best_open_price_if_ready as publisher


SOURCE = {
    "id": "source-snapshot",
    "published_at": "2026-09-14T12:00:00+00:00",
    "market_date": "2026-09-14",
    "cohort_fingerprint": "cohort-fp",
    "eligible_cohort_count": 2,
    "full_market_budget": 1350,
    "ranking_method_version": publisher.BUDGET_NORMALIZED_RANKING_METHOD_VERSION,
    "allocation_method_version": publisher.ALLOCATION_METHOD_VERSION,
    "comparison_scope_version": "scope-v1",
    "financial_rip_version": "financial-v4",
    "overall_rip_version": "overall-v12",
    "collector_appeal_version": "collector-v5",
    "chase_accessibility_version": "chase-v1",
    "chase_accessibility_transform_version": "chase-transform-v1",
    "ranked_under_v12_authority": True,
}


def engine_row(pid="p1", rank=1, status="current_number_one_with_headroom"):
    return {
        "sealedProductId": pid,
        "setId": f"set-{pid}",
        "productFamily": "booster_box",
        "sourceCalculationRunId": f"run-{pid}",
        "currentMarketPrice": 100.0,
        "currentQuantity": 13,
        "currentBudgetRank": rank,
        "currentOverallRipV12Score": 90.0,
        "currentFinancialRipV4Score": 80.0,
        "currentCollectorAppealScore": 70.0,
        "currentChaseAccessibilityRaw": 0.02,
        "currentChanceToRecoverCapital": 0.25,
        "currentActualCommittedCapital": 1300.0,
        "status": status,
        "bestOpenPrice": 110.0 if rank == 1 else 90.0,
        "thresholdQuantity": 12 if rank == 1 else 15,
        "priceGapDollars": -10.0 if rank == 1 else 10.0,
        "priceGapPercent": -0.1 if rank == 1 else 0.1,
        "benchmarkSealedProductId": "p2" if pid == "p1" else "p1",
        "benchmarkOverallRipV12Score": 85.0,
        "benchmarkFinancialRipV4Score": 75.0,
        "benchmarkChanceToRecoverCapital": 0.2,
        "benchmarkActualCommittedCapital": 1300.0,
        "candidatePriceEvaluations": 10,
        "bracketExpansions": 2,
        "bracketRefinements": 3,
        "fallbackCount": 0,
        "searchWallSeconds": 1.0,
        "exactness": {
            "thresholdWins": True,
            "nextPriceCents": 11001,
            "nextPriceWins": False,
            "oneCentMaximal": True,
        },
    }


def engine_result():
    rows = [engine_row("p1", 1), engine_row("p2", 2, "resolved_below_market")]
    return {
        "status": "complete",
        "source": {"snapshotId": SOURCE["id"], "cohortFingerprint": SOURCE["cohort_fingerprint"]},
        "products": rows,
        "cohortAnalysis": {
            "attempted": 2,
            "resolved": 2,
            "unresolved": 0,
            "statusCounts": {"current_number_one_with_headroom": 1, "resolved_below_market": 1},
            "discountPercentiles": {"p50": 0.1},
        },
        "timings": {"totalWallSeconds": 60.0},
        "lru": {"hits": 1, "misses": 2, "evictions": 0},
        "constructionMode": "independent_single_q_flat_stream_batch_v1",
        "quantityBatchSize": 24,
    }


class Lock:
    def __init__(self, allowed=True):
        self.allowed = allowed
        self.released = False

    def acquire(self):
        return self.allowed

    def release(self):
        self.released = True


def install_source(monkeypatch, *, already_current=False, historical_exists=False):
    monkeypatch.setattr(publisher, "resolve_source_identity", lambda *_a, **_k: dict(SOURCE))
    monkeypatch.setattr(publisher, "_already_current", lambda *_a, **_k: already_current)
    monkeypatch.setattr(
        publisher,
        "already_published_for_identity",
        lambda *_a, **_k: historical_exists,
    )
    monkeypatch.setattr(
        publisher,
        "_load_source",
        lambda *_a, **_k: (dict(SOURCE), [{"sealed_product_id": "p1"}, {"sealed_product_id": "p2"}], []),
    )
    monkeypatch.setattr(
        publisher,
        "_historical_authority",
        lambda *_a, **_k: {"fingerprint": "authority-fp", "rawBySet": {}},
    )


def test_already_current_is_fast_noop_before_engine(monkeypatch, tmp_path):
    install_source(monkeypatch, already_current=True)
    called = []

    def engine(*_a, **_k):
        called.append(True)
        raise AssertionError("engine must not run")

    code, report = publisher.run(
        commit=True, client=object(), checkpoint_dir=tmp_path, lock=Lock(), engine_runner=engine,
    )
    assert code == 0
    assert report["status"] == "ALREADY_CURRENT"
    assert called == []


def test_recurring_run_pins_current_source_uses_exact_batch24_and_skips_replay(monkeypatch, tmp_path):
    install_source(monkeypatch)
    observed = {}

    def engine(path, **kwargs):
        observed["path"] = path
        observed.update(kwargs)
        return engine_result()

    monkeypatch.setattr(publisher, "verify_no_drift", lambda *_a, **_k: None)
    monkeypatch.setattr(
        publisher,
        "build_payload_from_engine_result",
        lambda _source, rows, **_k: {"snapshot": {"source_budget_snapshot_id": SOURCE["id"]}, "rows": rows, "contentFingerprint": "content-fp"},
    )

    code, report = publisher.run(
        commit=False, client=object(), checkpoint_dir=tmp_path, lock=Lock(), engine_runner=engine,
    )

    assert code == 0
    assert report["status"] == "READY_DRY_RUN"
    assert observed["quantity_batch_size"] == 24
    assert observed["run_determinism"] is False
    assert observed["source_snapshot_id"] == SOURCE["id"]
    assert observed["expected_source_authority_fingerprint"] == "authority-fp"
    assert SOURCE["id"] in str(observed["path"])


def test_invalid_exactness_blocks_before_publish(monkeypatch, tmp_path):
    install_source(monkeypatch)
    bad = engine_result()
    bad["products"][1]["exactness"]["nextPriceWins"] = True
    bad["products"][1]["exactness"]["oneCentMaximal"] = False
    published = []
    monkeypatch.setattr(publisher, "verify_no_drift", lambda *_a, **_k: None)
    monkeypatch.setattr(publisher, "publish_snapshot", lambda *_a, **_k: published.append(True))

    code, report = publisher.run(
        commit=True, client=object(), checkpoint_dir=tmp_path, lock=Lock(),
        engine_runner=lambda *_a, **_k: bad,
    )

    assert code == 1
    assert report["status"] == "VALIDATION_FAILED"
    assert "P*+1 cent maximality failed" in report["failureReason"]
    assert published == []


def test_source_drift_after_expensive_build_blocks_publish(monkeypatch, tmp_path):
    install_source(monkeypatch)
    published = []

    def drift(*_a, **_k):
        raise RuntimeError("source budget ranking authority drifted during computation")

    monkeypatch.setattr(publisher, "verify_no_drift", drift)
    monkeypatch.setattr(publisher, "publish_snapshot", lambda *_a, **_k: published.append(True))

    code, report = publisher.run(
        commit=True, client=object(), checkpoint_dir=tmp_path, lock=Lock(),
        engine_runner=lambda *_a, **_k: engine_result(),
    )

    assert code == 1
    assert report["status"] == "SOURCE_DRIFT"
    assert published == []


def test_happy_commit_publishes_atomically_then_reads_back_same_authority(monkeypatch, tmp_path):
    install_source(monkeypatch)
    monkeypatch.setattr(publisher, "verify_no_drift", lambda *_a, **_k: None)
    monkeypatch.setattr(
        publisher,
        "build_payload_from_engine_result",
        lambda _source, rows, **_k: {"snapshot": {"source_budget_snapshot_id": SOURCE["id"]}, "rows": rows, "contentFingerprint": "content-fp"},
    )
    published = []

    def publish(_client, snapshot, rows):
        published.append((snapshot, rows))
        return "bop-new"

    monkeypatch.setattr(publisher, "publish_snapshot", publish)
    monkeypatch.setattr(
        publisher,
        "load_best_open_price_ranking",
        lambda _client: {
            "available": True,
            "snapshotId": "bop-new",
            "sourceBudgetSnapshotId": SOURCE["id"],
            "resolvedCount": 2,
            "unresolvedCount": 0,
        },
    )
    lock = Lock()
    code, report = publisher.run(
        commit=True, client=object(), checkpoint_dir=tmp_path, lock=lock,
        engine_runner=lambda *_a, **_k: engine_result(),
    )

    assert code == 0
    assert report["status"] == "PUBLISHED"
    assert report["bestOpenSnapshotId"] == "bop-new"
    assert len(published) == 1
    assert len(published[0][1]) == 2
    assert lock.released is True


def test_second_concurrent_run_is_refused_without_source_or_engine_work(tmp_path):
    code, report = publisher.run(
        commit=True,
        client=object(),
        checkpoint_dir=tmp_path,
        lock=Lock(allowed=False),
        engine_runner=lambda *_a, **_k: (_ for _ in ()).throw(AssertionError("must not run")),
    )
    assert code == 3
    assert report["status"] == "ALREADY_RUNNING"
