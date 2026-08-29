from datetime import date,timedelta
import pytest
from backend.db.services import treatment_market_prestige_v3_service as svc

class Result:
    def __init__(self,data):self.data=data
class Query:
    def __init__(self,rows):self.rows=list(rows)
    def select(self,*a,**k):return self
    def eq(self,key,value):self.rows=[r for r in self.rows if str(r.get(key))==str(value)];return self
    def order(self,key,desc=False):self.rows=sorted(self.rows,key=lambda r:str(r.get(key) or ""),reverse=desc);return self
    def limit(self,n):self.rows=self.rows[:n];return self
    def execute(self):return Result(self.rows)
class Client:
    def __init__(self,tables=None,rpc_error=None):self.tables=tables or {};self.calls=[];self.rpc_error=rpc_error
    def table(self,name):return Query(self.tables.get(name,[]))
    def rpc(self,name,payload):
        self.calls.append((name,payload));error=self.rpc_error
        class RPC:
            def execute(self):
                if error:raise error
                return Result("run-1")
        return RPC()

def run_row(**extra):
    return {"approval_status":"approved","production_contract_hash":svc.PRODUCTION_CONTRACT_HASH,"baseline_version":svc.BASELINE_VERSION,"market_reference_date":date.today().isoformat(),"approved_at":date.today().isoformat()+"T00:00:00+00:00",**extra}

def score_row(**extra):
    return {"era_id":"era","treatment_key":"illustration_rare","comparison_universe_type":"ERA_RELATIVE","set_id":None,"final_availability_status":"AVAILABLE","universe_availability_status":"AVAILABLE","magnitude_score":5.4321,"score_interval_low":5.1,"score_interval_high":5.8,"model_version":svc.MODEL_VERSION,"methodology_version":svc.METHODOLOGY_VERSION,"market_reference_date":date.today().isoformat(),"era_name":"XY","treatment_regime_id":None,"treatment_label":"Illustration Rare","confidence_status":"STANDARD","evidence_status":"AVAILABLE","card_count":100,"set_count":5,"comparison_universe_size":6,**extra}

def test_no_approved_run_and_no_taxonomy_fail_closed_without_fallback():
    assert svc.resolve_card_treatment_market_prestige(set_id="set",era_id="era",rarity="Illustration Rare",client=Client())["status"]=="NO_APPROVED_RUN"
    assert svc.resolve_card_treatment_market_prestige(set_id="set",era_id="era",rarity=None,client=Client())["status"]=="TAXONOMY_UNMAPPED"

def test_available_approved_era_score_uses_one_decimal_display():
    c=Client({"treatment_market_prestige_publication_runs":[run_row()],"latest_approved_treatment_market_prestige":[score_row()]})
    x=svc.resolve_card_treatment_market_prestige(set_id="set",era_id="era",rarity="Illustration Rare",client=c)
    assert x["status"]=="AVAILABLE" and x["score"]==5.4321 and x["scoreDisplay"]=="5.4"

def test_mega_treatment_evidence_cannot_bypass_failed_universe():
    row=score_row(universe_availability_status="INSUFFICIENT_ERA_SUPPORT",final_availability_status="INSUFFICIENT_ERA_SUPPORT",magnitude_score=None)
    c=Client({"treatment_market_prestige_publication_runs":[run_row()],"latest_approved_treatment_market_prestige":[row]})
    x=svc.resolve_card_treatment_market_prestige(set_id="mega-set",era_id="era",rarity="Illustration Rare",client=c)
    assert x["status"]=="INSUFFICIENT_ERA_SUPPORT" and x["score"] is None

def test_new_treatment_and_missing_regime_never_borrow():
    c=Client({"treatment_market_prestige_publication_runs":[run_row()],"latest_approved_treatment_market_prestige":[score_row(treatment_key="rare_holo",comparison_universe_type="TREATMENT_REGIME_RELATIVE",set_id="other")]})
    assert svc.resolve_card_treatment_market_prestige(set_id="set",era_id="era",rarity="new treatment",client=c)["status"]=="NEW_TREATMENT_RESEARCHING"
    assert svc.resolve_card_treatment_market_prestige(set_id="set",era_id="era",rarity="Rare Holo",client=c)["status"]=="INSUFFICIENT_REGIME_SUPPORT"

def test_stale_and_baseline_mismatch_fail_closed():
    stale=run_row(market_reference_date=(date.today()-timedelta(days=46)).isoformat())
    assert svc.resolve_card_treatment_market_prestige(set_id="s",era_id="era",rarity="Rare",client=Client({"treatment_market_prestige_publication_runs":[stale]}))["status"]=="MODEL_STALE"
    bad=run_row(baseline_version="other")
    assert svc.resolve_card_treatment_market_prestige(set_id="s",era_id="era",rarity="Rare",client=Client({"treatment_market_prestige_publication_runs":[bad]}))["status"]=="NO_APPROVED_RUN"

def test_candidate_hash_and_partial_rpc_failure_do_not_approve():
    payload={"run":{},"universes":[],"results":[],"regimeSets":[]};payload["candidateHash"]=svc.stable_json_hash(payload)
    c=Client(rpc_error=RuntimeError("rollback"))
    with pytest.raises(RuntimeError,match="rollback"):svc.stage_candidate(payload,client=c)
    assert [name for name,_ in c.calls]==["stage_treatment_market_prestige_v3_candidate"]

def test_approval_is_explicit_and_actor_required():
    with pytest.raises(ValueError):svc.approve_candidate("run",approval_actor="",client=Client())
    c=Client();assert svc.approve_candidate("run",approval_actor="release-bot",client=c)=="run-1"
    assert c.calls[0][0]=="approve_treatment_market_prestige_v3_candidate"
