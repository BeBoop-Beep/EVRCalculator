import pytest

from backend.scripts.backfill_ranked_set_rip_decisions import ranked_targets, validate_contract


def test_ranked_targets_follow_canonical_overall_rip_v10_only():
    rows = [
        {"set_id": "v10", "calculation_run_id": "run-10", "overallRipV10": {"rank": 1}, "overallRipV9": {}},
        {"set_id": "v9-only", "calculation_run_id": "run-9", "overallRipV9": {"rank": 2}},
        {"set_id": "unranked", "calculation_run_id": "run-u", "overallRipV10": {"rank": None}},
    ]
    assert ranked_targets(rows) == [{"set_id": "v10", "calculation_run_id": "run-10"}]


def test_ranked_targets_never_fall_back_to_v9_when_v10_is_absent():
    """A row ranked only under the superseded V9 model must not be selected as
    a canonical target - there is no implicit V9 fallback for this cutover."""
    rows = [
        {"set_id": "v9-only", "calculation_run_id": "run-9", "overallRipV9": {"rank": 1}},
    ]
    assert ranked_targets(rows) == []


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
