from pathlib import Path

from backend.scripts.research_collector_cross_domain_temporal_v1 import (
    CANDIDATE,
    EXPECTED_COUNTS,
    GUARDRAILS,
    TEMPORAL_DATES,
    decide,
    fold_pass,
)


def test_temporal_contract_is_frozen():
    assert CANDIDATE == "ANCHOR25"
    assert TEMPORAL_DATES == (
        "2026-09-14",
        "2026-09-17",
        "2026-09-20",
        "2026-09-23",
        "2026-09-26",
    )
    assert EXPECTED_COUNTS == {
        "candidateCards": 4355,
        "modeledRows": 4331,
        "modeledSets": 22,
        "dropped": {"no_modeled_pull_probability": 24},
    }
    assert GUARDRAILS == {
        "weightedWithinSetRho": -0.005,
        "controlledOosR2": -0.002,
        "heldOutSpearman": -0.010,
        "pairConcordance": 0.0,
    }


def test_fold_gate_requires_every_guardrail():
    passing = {
        "weightedWithinSetRho": -0.005,
        "controlledOosR2": -0.002,
        "heldOutSpearman": -0.010,
        "pairConcordance": 0.0,
    }
    assert fold_pass(True, passing)
    failing = dict(passing)
    failing["pairConcordance"] = -1e-9
    assert not fold_pass(True, failing)
    assert not fold_pass(False, passing)


def test_final_decision_is_preregistered_four_of_five():
    assert decide(True, [{"dataValid": True, "passed": True}] * 4 + [{"dataValid": True, "passed": False}]) == "ANCHOR25_TEMPORAL_VALIDATION_PASS"
    assert decide(True, [{"dataValid": True, "passed": True}] * 3 + [{"dataValid": True, "passed": False}] * 2) == "ANCHOR25_TEMPORAL_VALIDATION_FAIL"
    assert decide(True, [{"dataValid": True, "passed": True}] * 3 + [{"dataValid": False, "passed": False}] * 2) == "ANCHOR25_TEMPORAL_AUTHORITY_INSUFFICIENT"
    assert decide(False, [{"dataValid": True, "passed": True}] * 5) == "ANCHOR25_TEMPORAL_VALIDATION_INVALID"


def test_temporal_harness_has_no_database_write_calls():
    source = Path("backend/scripts/research_collector_cross_domain_temporal_v1.py").read_text(encoding="utf-8").lower()
    # Allow sys.path.insert(); reject persistence-shaped client calls.
    for token in (".insert([", ".insert({", ".update({", ".delete()", ".upsert("):
        assert token not in source
    assert 'service_client.table("conditions").select(' in source
    assert 'service_client.table("card_variant_price_observation_ranges_v2").select(' in source
    assert source.count(".table(") == 2
    assert ".rpc(" not in source
    # Historical authority is pinned to the exact Phase 1 SQL semantics after the mutable RPC drifted.
    assert "historical_prices_phase1_sql(" in source
    assert "20260928204424_market_explorer_root_standard_frozen_roster_v2" in source
