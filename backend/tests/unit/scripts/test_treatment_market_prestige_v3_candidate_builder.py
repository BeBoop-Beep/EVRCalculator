from backend.db.services.treatment_market_prestige_v3_service import build_candidate_payload
from backend.desirability.treatment_market_prestige_v3 import stable_json_hash

def test_round8_candidate_is_recomputed_and_deterministic():
    a=build_candidate_payload()
    assert a["candidateHash"]==stable_json_hash({k:a[k] for k in ("run","universes","results","regimeSets")})
    assert len(a["results"])==38 and len(a["universes"])==11
    assert sum(x["final_availability_status"]=="AVAILABLE" for x in a["results"])==23
    assert sum(x["final_availability_status"]=="AVAILABLE" for x in a["universes"])==4
    assert a["run"]["approved"] is False and a["run"]["approval_status"]=="candidate"

def test_mega_double_rare_is_null_after_universe_gate():
    p=build_candidate_payload();row=next(x for x in p["results"] if x["universe_key"]=="Mega Evolution" and x["treatment_key"]=="double_rare")
    assert row["evidence_status"]=="AVAILABLE"
    assert row["final_availability_status"]=="INSUFFICIENT_ERA_SUPPORT"
    assert row["magnitude_score"] is None

def test_all_unavailable_candidate_results_use_null_not_zero():
    p=build_candidate_payload()
    assert all(x["magnitude_score"] is None and x["score_interval_low"] is None and x["score_interval_high"] is None for x in p["results"] if x["final_availability_status"]!="AVAILABLE")
