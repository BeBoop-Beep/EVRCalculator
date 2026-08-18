from backend.db.services.rip_decision_freshness import evaluate_rip_decision_staleness


def _decision(**overrides):
    value = {
        "contractVersion": "rip-decision-contract-v1",
        "currentRunAvailable": True,
        "sourceCalculationRunId": "run-1",
        "sourceSealedMarketClassificationVersion": "classification-v3",
        "sourceSealedMarketSnapshotContractVersion": "market-v3",
        "sourceSealedProductResultCount": 2,
        "sourceSealedProductResultsUpdatedAt": "2026-08-18T10:00:00Z",
        "sealedProducts": {"sourceCalculationRunId": "run-1", "productCount": 2},
        "topChase": {"sourceCalculationRunId": "run-1"},
    }
    value.update(overrides)
    return value


def _reasons(decision, **overrides):
    authority = {
        "ranked": True,
        "expected_run_id": "run-1",
        "expected_sealed_market_classification_version": "classification-v3",
        "expected_sealed_market_contract_version": "market-v3",
        "expected_product_result_count": 2,
        "expected_product_results_updated_at": "2026-08-18T10:00:00Z",
    }
    authority.update(overrides)
    return {reason["code"] for reason in evaluate_rip_decision_staleness(decision, **authority)}


def test_current_matching_provenance_is_fresh():
    assert _reasons(_decision()) == set()


def test_stale_and_missing_classification_provenance_are_explicit():
    assert "classification_version_mismatch" in _reasons(
        _decision(sourceSealedMarketClassificationVersion="classification-v2")
    )
    assert "classification_provenance_missing" in _reasons(
        _decision(sourceSealedMarketClassificationVersion=None)
    )


def test_same_run_product_finalization_invalidates_older_decision():
    assert "product_results_stale" in _reasons(
        _decision(), expected_product_results_updated_at="2026-08-18T11:00:00Z"
    )


def test_incomplete_product_population_is_stale():
    assert "product_result_count_mismatch" in _reasons(
        _decision(sourceSealedProductResultCount=1)
    )
