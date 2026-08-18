import pytest

from backend.scripts.backfill_ranked_set_rip_decisions import ranked_targets, validate_contract


def test_ranked_targets_follow_canonical_overall_rip_v9_only():
    rows = [
        {"set_id": "v9", "calculation_run_id": "run-9", "overallRipV9": {"rank": 1}, "overallRipV8": {}},
        {"set_id": "v8-only", "calculation_run_id": "run-8", "overallRipV8": {"rank": 2}},
        {"set_id": "unranked", "calculation_run_id": "run-u", "overallRipV9": {"rank": None}},
    ]
    assert ranked_targets(rows) == [{"set_id": "v9", "calculation_run_id": "run-9"}]


def test_backfill_rejects_cross_contract_run_mismatch():
    contract = {
        "contractVersion": "rip-decision-contract-v1", "currentRunAvailable": True,
        "sourceCalculationRunId": "run-current",
        "sealedProducts": {"sourceCalculationRunId": "run-current", "productCount": 1},
        "topChase": {"sourceCalculationRunId": "run-stale", "cardName": "Chase",
                     "currentMarketPrice": 1, "modeledProbability": 0.1, "impliedOddsOneInN": 10,
                     "packsFor50PercentChance": 7, "packsFor90PercentChance": 22},
    }
    with pytest.raises(AssertionError):
        validate_contract(contract, "run-current")
