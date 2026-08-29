import json
from pathlib import Path
from backend.desirability.treatment_market_prestige_v3 import stable_json_hash
from backend.scripts.build_treatment_market_prestige_v3_round6 import CONTRACT,FAIL_STATUSES,failure_modes,universe_status
ROOT=Path("docs/research")

def test_drift_and_evidence_contract_preregistered():
    assert CONTRACT["score_drift"]["maximum_90_day"]==1.0
    assert CONTRACT["treatment_gate"]["minimum_historical_checkpoints"]==4
    assert CONTRACT["universe_gate"]["minimum_eligible_treatments"]==2

def test_single_treatment_universe_fails_closed():
    assert universe_status({"a":{"status":"AVAILABLE"}},"era")=="INSUFFICIENT_ERA_SUPPORT"

def test_all_failure_modes_are_non_numeric_and_closed():
    modes=failure_modes()
    assert set(modes.values())<=set(FAIL_STATUSES)
    assert modes["partial_database_write"]=="NO_APPROVED_RUN"
    assert modes["new_unsupported_treatment"]=="NEW_TREATMENT_RESEARCHING"

def test_round6_artifacts_and_zero_writes():
    out=ROOT/"treatment_market_prestige_v3_round6_frozen";m=json.loads((out/"manifest.json").read_text());s=json.loads((ROOT/"treatment_market_prestige_v3_round6_study.json").read_text());c=json.loads((out/"production_contract.json").read_text())
    assert stable_json_hash(s)==m["study_hash"]
    assert stable_json_hash(c["operational"])==m["contract_hash"]
    assert s["rows_persisted"]==0
    assert s["implementation_authorization"] in ("PRODUCTION_IMPLEMENTATION_AUTHORIZED","PRODUCTION_IMPLEMENTATION_NOT_AUTHORIZED")
    assert len(s["older_era_matrix"])+len(s["readiness"])==17

def test_latest_approved_is_explicit_and_atomic():
    c=json.loads((ROOT/"treatment_market_prestige_v3_round6_frozen/production_contract.json").read_text())
    reader=c["database"]["latest_approved_reader"]
    assert "explicit approval" in reader["semantics"]
    assert "transaction" in reader["publication_atomicity"]
