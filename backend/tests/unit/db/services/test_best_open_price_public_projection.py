from backend.db.services import public_overall_product_rankings_service as service


SNAPSHOT = {
    "id": "source-snapshot",
    "published_at": "2026-09-08T20:20:33.705413+00:00",
    "market_date": "2026-09-08",
    "cohort_fingerprint": "cohort-fingerprint",
    "full_market_budget": 1350.0,
}
RAW_ROW = {
    "sealed_product_id": "product-1",
    "set_id": "set-1",
    "product_family": "loose_booster_pack",
    "quantity": 101,
    "actual_committed_capital": 1337.24,
    "unused_capital": 12.76,
    "financial_rip_v4_score": 44.0,
    "collector_appeal_score": 60.0,
    "product_market_price": 13.24,
    "expected_value": 8.0,
    "chance_to_recover_capital": 0.25,
}
IDENTITIES = {
    "families": {
        "loose_booster_pack": {
            "products": [{
                "sealedProductId": "product-1",
                "productName": "Alpha Booster Pack",
                "setName": "Alpha",
                "productFamilyLabel": "Loose Booster Pack",
                "familyRank": 1,
                "familySize": 1,
            }],
        },
    },
}
PRESENTATION = {
    "product-1": {
        "publicTier": "S",
        "overallRipLeaderScore": 100,
        "financialRipLeaderScore": 81,
        "overallRipScore": 54.425,
        "budgetRank": 1,
        "budgetCohortSize": 1,
    },
}
PREPARED = {
    "available": True,
    "reason": None,
    "snapshotId": "best-open-snapshot",
    "methodVersion": "best-open-v1",
    "sourceBudgetSnapshotId": "source-snapshot",
    "sourceBudgetPublishedAt": "2026-09-08T20:20:33.705413+00:00",
    "sourceMarketDate": "2026-09-08",
    "sourceCohortFingerprint": "cohort-fingerprint",
    "resolvedCount": 1,
    "unresolvedCount": 0,
    "rows": [{
        "sealed_product_id": "product-1",
        "best_open_price": 14.96,
        "status": "current_number_one_with_headroom",
        "price_gap_dollars": -1.72,
        "price_gap_percent": -0.1299093656,
    }],
}


def _install_common(monkeypatch):
    monkeypatch.setattr(service, "load_latest_snapshot", lambda _client: dict(SNAPSHOT))
    monkeypatch.setattr(service, "load_full_market_ranking", lambda _client, **_kwargs: {
        "rows": [dict(RAW_ROW)], "authority": {},
    })
    monkeypatch.setattr(service, "public_budget_cohort_presentation", lambda _rows, _snapshot: dict(PRESENTATION))


def test_full_market_joins_only_narrow_best_open_presentation_fields(monkeypatch):
    _install_common(monkeypatch)
    monkeypatch.setattr(service, "load_best_open_price_ranking", lambda _client: dict(PREPARED))

    result = service.read_public_overall_product_rankings(
        "full_market", product_family_rankings=IDENTITIES, client=object(),
    )

    assert result["available"] is True
    assert result["bestOpenPrice"] == {
        "available": True,
        "reason": None,
        "snapshotId": "best-open-snapshot",
        "methodVersion": "best-open-v1",
        "sourceMarketDate": "2026-09-08",
        "sourceBudgetSnapshotId": "source-snapshot",
    }
    row = result["rows"][0]
    assert row["bestOpenPrice"] == 14.96
    assert row["bestOpenPriceStatus"] == "current_number_one_with_headroom"
    assert row["bestOpenPriceGapDollars"] == -1.72
    assert row["bestOpenPriceGapPercent"] == -0.1299093656
    assert "benchmark_sealed_product_id" not in row
    assert "current_chase_accessibility_raw" not in row


def test_source_mismatch_hides_best_open_without_taking_down_rankings(monkeypatch):
    _install_common(monkeypatch)
    stale = dict(PREPARED, sourceBudgetPublishedAt="2026-09-07T00:00:00+00:00")
    monkeypatch.setattr(service, "load_best_open_price_ranking", lambda _client: stale)

    result = service.read_public_overall_product_rankings(
        "full_market", product_family_rankings=IDENTITIES, client=object(),
    )

    assert result["available"] is True
    assert result["bestOpenPrice"] == {"available": False, "reason": "source_mismatch"}
    assert "bestOpenPrice" not in result["rows"][0]


def test_incomplete_best_open_cohort_hides_only_optional_layer(monkeypatch):
    _install_common(monkeypatch)
    incomplete = dict(PREPARED, resolvedCount=0, rows=[])
    monkeypatch.setattr(service, "load_best_open_price_ranking", lambda _client: incomplete)

    result = service.read_public_overall_product_rankings(
        "full_market", product_family_rankings=IDENTITIES, client=object(),
    )

    assert result["available"] is True
    assert result["bestOpenPrice"] == {"available": False, "reason": "incomplete_snapshot_rows"}
    assert result["rows"][0]["unitPrice"] == 13.24


def test_best_open_read_error_fails_soft(monkeypatch):
    _install_common(monkeypatch)

    def fail(_client):
        raise RuntimeError("prepared store unavailable")

    monkeypatch.setattr(service, "load_best_open_price_ranking", fail)
    result = service.read_public_overall_product_rankings(
        "full_market", product_family_rankings=IDENTITIES, client=object(),
    )
    assert result["available"] is True
    assert result["bestOpenPrice"] == {"available": False, "reason": "prepared_read_failed"}


def test_standard_budget_never_reads_best_open(monkeypatch):
    monkeypatch.setattr(service, "load_latest_snapshot", lambda _client: dict(SNAPSHOT))
    monkeypatch.setattr(service, "load_budget_ranking", lambda _client, _value, **_kwargs: {
        "rows": [dict(RAW_ROW)], "authority": {},
    })
    monkeypatch.setattr(service, "public_budget_cohort_presentation", lambda _rows, _snapshot: dict(PRESENTATION))

    def should_not_run(_client):
        raise AssertionError("Best-Open store must not be queried for standard budget bands")

    monkeypatch.setattr(service, "load_best_open_price_ranking", should_not_run)
    result = service.read_public_overall_product_rankings(
        "100", product_family_rankings=IDENTITIES, client=object(),
    )

    assert result["available"] is True
    assert result["bestOpenPrice"] == {"available": False, "reason": "full_market_only"}
    assert "bestOpenPrice" not in result["rows"][0]


def test_public_read_passes_captured_snapshot_and_preserves_drift_failure(monkeypatch):
    captured = {"id": "captured"}
    monkeypatch.setattr(service, "load_latest_snapshot", lambda _client: captured)
    def reader(_client, *, source_snapshot):
        assert source_snapshot is captured
        return {"available": False, "reason": "source_publication_changed", "rows": []}
    monkeypatch.setattr(service, "load_full_market_ranking", reader)
    result = service.read_public_overall_product_rankings(client=object(), product_family_rankings={})
    assert result == {"available": False, "reason": "source_publication_changed", "rows": []}
