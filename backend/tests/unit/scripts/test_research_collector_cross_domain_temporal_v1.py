from pathlib import Path

from backend.scripts.research_collector_cross_domain_temporal_v1 import (
    CANDIDATE,
    EXPECTED_COUNTS,
    GUARDRAILS,
    PRICE_FILES,
    TEMPORAL_DATES,
    canonical_hash,
    decide,
    fold_pass,
    fold_seed,
    read_json,
    write_json,
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
    assert set(PRICE_FILES) == {"2026-09-11", *TEMPORAL_DATES}


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


def test_temporal_harness_is_offline_and_has_no_database_write_calls():
    source = Path("backend/scripts/research_collector_cross_domain_temporal_v1.py").read_text(encoding="utf-8").lower()
    for token in (".insert(", ".update(", ".delete(", ".upsert(", ".rpc(", ".table(", "execute_sql"):
        assert token not in source
    assert "supabase" not in source
    assert "requests" not in source
    assert "prices_20260920.json" in source
    assert "frozen_temporal_cohort_part1.json" in source
    assert "authority_amendment_3.md" in source


def test_runtime_helpers_survive_authority_refactors(tmp_path):
    target = tmp_path / "payload.json"
    payload = {"a": 1, "b": ["x", "y"]}
    write_json(target, payload)
    assert read_json(target) == payload
    assert len(canonical_hash(payload)) == 64
    assert fold_seed("2026-09-14") == 20260929 + 20260914
