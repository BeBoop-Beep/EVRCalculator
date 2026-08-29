import json
from pathlib import Path
from backend.desirability.treatment_market_prestige_v3 import stable_json_hash
ROOT=Path("docs/research")

def load():
    return json.loads((ROOT/"treatment_market_prestige_v3_round8_study.json").read_text())

def test_frozen_inputs_and_contract_are_exact():
    s=load();assert s["input_verification"]["status"]=="VERIFIED";assert s["input_verification"]["checkpoint_manifests"]==40;assert s["contract_verification"]["status"]=="UNCHANGED"

def test_failed_treatments_have_null_production_scores():
    for x in load()["treatment_matrix"]:
        if x["finalAvailabilityStatus"]!="AVAILABLE":assert x["score"] is None and x["scoreInterval"] is None

def test_universe_gate_and_unsupported_third_regime():
    m={x["universeId"]:x for x in load()["universe_matrix"]};assert m["sun_and_moon_r3"]["publicationStatus"]=="INSUFFICIENT_REGIME_SUPPORT";assert m["sun_and_moon_r3"]["eligibleTreatmentCount"]==0
    assert all(x["eligibleTreatmentCount"]>=2 for x in m.values() if x["publicationStatus"]=="AVAILABLE")

def test_treatment_can_pass_evidence_but_fail_final_universe_gate():
    row=next(x for x in load()["treatment_matrix"] if x["universeId"]=="Mega Evolution" and x["treatmentKey"]=="double_rare")
    assert row["evidenceStatus"]=="AVAILABLE"
    assert row["finalAvailabilityStatus"]=="INSUFFICIENT_ERA_SUPPORT"
    assert row["score"] is None

def test_atomic_simulation_never_approves_or_exposes_partial_write():
    for x in load()["atomic_publication_backtest"]:assert x["actuallyApproved"] is False and x["partialWriteVisibility"]=="none"

def test_failure_modes_all_close_with_null_scores():
    assert all(x["failClosed"] and x["score"] is None for x in load()["failure_mode_retest"].values())

def test_artifact_hashes_and_zero_writes():
    out=ROOT/"treatment_market_prestige_v3_round8_rerun";m=json.loads((out/"manifest.json").read_text());s=load();p=json.loads((out/"candidate_payload.json").read_text());assert stable_json_hash(s)==m["study_hash"];assert stable_json_hash(p)==m["candidate_payload_hash"];assert s["rows_persisted"]==0 and p["approved"] is False
