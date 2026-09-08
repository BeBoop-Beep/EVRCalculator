"""Build the frozen C3B/C4/C5 Collector Appeal model as a non-published run.

The default mode is a deterministic, read-only preview. ``--write-shadow`` is
the only write path; it validates the run but deliberately has no promotion
option.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import sys
import time
import tracemalloc
from collections import Counter, defaultdict
from datetime import date
from pathlib import Path
from typing import Any

from dotenv import load_dotenv
from supabase import ClientOptions, create_client

ROOT = Path(__file__).resolve().parents[2]
ARTIFACTS = ROOT / "backend" / "artifacts"
MODEL_VERSION = "pokemon_collector_appeal_v6_generalized_roster_frequency"
SOURCE_IDS = [
    "b3997343-1363-45aa-b1b0-9a6de1ce3793",  # corrected Trainer 12m
    "648e5375-47cb-4972-b01d-faceb6348d1d",  # corrected Trainer 5y
    "9947aaf7-8647-484f-8c9c-2cec59792cdb",  # accepted Limitless
]
FPS = {
    "c3a5SubjectFingerprint": "0773b4d23fd4f50ceaab2598c5f33de12ba2a60f3f04d902e4c7720e5ac8d4af",
    "c3bFingerprint": "a8e810765b7450349bbbc5ad99361a69976fb56798d2b4ad81f1041bc7277b98",
    "c4RosterFingerprint": "e1b1c4310642d86ec505a3c6df0f1b7b668f12f48b887cd0d4dfa5e86efd97f6",
    "c4FrequencyFingerprint": "b6264e7ee06a30f46c282c189ec763af40936209ae68f1dab9105a1e8ae1bc58",
    "c5Fingerprint": "2793fa52e46a7e6b64f1665df88a4700110f5c37f57a97a2f0d99d91024b6adf",
}


def canonical_hash(value: Any) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()).hexdigest()


def load_json(name: str) -> dict[str, Any]:
    return json.loads((ARTIFACTS / name).read_text(encoding="utf-8"))


class DB:
    def __init__(self, client):
        self.c = client; self.read_requests = self.write_requests = self.rows_read = self.rows_written = 0; self.batches = 0; self.errors = []
    def read(self, table, columns="*", **eq):
        self.read_requests += 1
        try:
            q = self.c.table(table).select(columns)
            for k, v in eq.items(): q = q.eq(k, v)
            rows = q.execute().data or []; self.rows_read += len(rows); return rows
        except Exception as e: self.errors.append(type(e).__name__); raise
    def upsert(self, table, rows, on_conflict, batch=250):
        for i in range(0, len(rows), batch):
            chunk = rows[i:i+batch]; self.write_requests += 1; self.batches += 1
            try: self.c.table(table).upsert(chunk, on_conflict=on_conflict).execute(); self.rows_written += len(chunk)
            except Exception as e: self.errors.append(type(e).__name__); raise
    def count(self, table, **eq):
        self.read_requests += 1
        q = self.c.table(table).select("model_run_id", count="exact").limit(0)
        for k, v in eq.items(): q = q.eq(k, v)
        return q.execute().count or 0


def build_manifest(source_rows: list[dict[str, Any]]) -> tuple[dict[str, Any], str]:
    by_id = {r["id"]: r for r in source_rows}
    if set(by_id) != set(SOURCE_IDS): raise RuntimeError("required numerical source run is missing")
    registry = {"version": "pokemon_trainer_query_overrides_v1", "resolvedQueries": by_id[SOURCE_IDS[0]]["raw_payload_json"]["queries"]}
    manifest = {
        "productionPersistenceRevision": 2,
        "dependencies": FPS,
        "sourceEvidence": [{"id": i, "sourceFingerprint": by_id[i]["source_fingerprint"], "captureVersion": by_id[i]["capture_version"]} for i in SOURCE_IDS],
        "pokemonAppealAuthority": {"version": "pokemon_desirability_composite_v1", "subjectScaleContract": "within_eligible_named_subject_class_percentile"},
        "trainerQueryOverrideRegistry": {"version": registry["version"], "fingerprint": canonical_hash(registry)},
        "contracts": {
            "neutralExceptionVersion": "pokemon_collector_neutral_subject_exceptions_v1", "eligibleCohortVersion": "pokemon_collector_c3b_eligible_cohort_v1",
            "hitPolicyVersion": "pokemon_card_desirability_hit_policy_v2_coverage_cleanup", "neutralBaseline": 50, "playabilityCandidate": "candidate_c_confidence_shrunk",
            "lambdaPlayability": .2, "collectorRosterK": 6, "generalizedFrequencyThreshold": ">50", "frequencyWaitTimeAnchors": ["1/16", "1/8", "1/4"],
            "frequencyModifierBudget": {"up": 2, "down": -1}, "excludedInputs": ["Energy", "Artist", "Treatment", "market price", "Dual-Path Depth", "set-level Playability"],
        },
        "expectedCounts": {"cardRows": 18293, "c4Rows": 128, "c5Rows": 128, "scoredRows": 22, "unavailableRows": 106},
    }
    fingerprint = canonical_hash(manifest)
    manifest["topLevelInputFingerprint"] = fingerprint
    return manifest, fingerprint


def payloads(run_id: str):
    c3 = load_json("collector_c3b_card_appeal_shadow_v2.json"); c4 = load_json("collector_c4_set_components_shadow_v1.json"); c5 = load_json("collector_c5_combination_shadow_v1.json")
    cards = []
    neutral_by_set = Counter()
    for x in c3["shadowRows"]:
        b=float(x["subject_appeal_percentile"]); final=float(x["final_card_collector_appeal"]); conf=x.get("confidence")
        normalized=(final-b)/(100-b) if b < 100 else 0.0
        if x["hit_eligibility"] and x["subject_type"] == "neutral_functional": neutral_by_set[x["set_id"]] += 1
        cards.append({"model_run_id":run_id,"pokemon_canonical_card_id":x["canonical_card_id"],"set_id":x["set_id"],"subject_policy":{"pokemon":"pokemon","trainer":"trainer","neutral_functional":"neutral"}[x["subject_type"]],"subject_baseline_score":b,"artist_recognition_score":None,"playability_score":None if x.get("playability_raw_score") is None else x["playability_raw_score"]*conf,"artist_lift":0,"playability_lift":normalized,"combined_lift":normalized,"collector_card_appeal_score":final,"score_status":"scored","confidence":"insufficient" if conf is None else ("high" if conf>=.8 else "medium" if conf>=.5 else "low"),"price_input_excluded":True,"treatment_input_excluded":True,"hit_eligibility_independent":True,"component_inputs_json":{"subjectType":x["subject_type"],"subjectIdentity":x.get("subject_identity"),"functionalIdentity":x.get("playability_functional_identity"),"functionalName":x.get("playability_functional_name"),"playabilityRawScore":x.get("playability_raw_score"),"playabilityConfidence":conf,"playabilityStatus":x["playability_status"],"appliedLiftPoints":x["applied_lift"],"neutralBaseline":x["neutral_baseline_flag"],"artistEnabled":False},"lineage_json":{"c3bFingerprint":FPS["c3bFingerprint"],"c3a5SubjectFingerprint":FPS["c3a5SubjectFingerprint"],"sourceRuns":x["source_runs"],"excludedInputs":["Energy","Artist","Treatment","market price"],"energyExcluded":True}})
    rank = {x["set_id"]: i+1 for i,x in enumerate(sorted(c4["sets"],key=lambda v:(-v["collectorRosterDesirability"],v["set_id"])))}
    drows=[]
    for x in c4["sets"]:
        scores=[g["appeal"] for g in x["topCollectorGroups"]]
        drows.append({"model_run_id":run_id,"set_id":x["set_id"],"aggregation_version":"collector_roster_desirability_production_v1","collector_desirability_score":x["collectorRosterDesirability"],"collector_desirability_rank":rank[x["set_id"]],"eligible_card_count":x["totalHitEligibleCards"],"scored_card_count":x["c3bScoredHitEligibleCards"]-neutral_by_set[x["set_id"]],"neutral_card_count":neutral_by_set[x["set_id"]],"unsupported_card_count":0,"score_coverage_ratio":1,"max_card_appeal_score":max(scores) if scores else None,"top_3_card_appeal_score":sum(scores[:3])/min(3,len(scores)) if scores else None,"top_5_card_appeal_score":sum(scores[:5])/min(5,len(scores)) if scores else None,"effective_desirable_card_count":sum(1 for s in scores if s>50),"subject_rollups_json":x["topCollectorGroups"],"top_cards_json":x["topPlayabilityMembershipEffects"],"component_inputs_json":{"groupRepresentative":"max","saturationK":6,"groupContractVersion":x["groupContractVersion"],"hitPolicyVersion":x["hitPolicyVersion"],"c3bFingerprint":FPS["c3bFingerprint"],"c4RosterFingerprint":FPS["c4RosterFingerprint"]},"diagnostics_json":{"distinctGroupCount":x["distinctGroupCount"],"pokemonGroupCount":x["pokemonGroupCount"],"trainerGroupCount":x["trainerGroupCount"],"neutralFunctionalGroupCount":x["neutralFunctionalGroupCount"],"excludedEnergyCount":x["excludedEnergyCount"]}})
    scored_sorted=sorted((x for x in c5["rows"] if x["status"]=="available"),key=lambda v:(-v["collectorAppeal"],v["set_id"])); c5rank={x["set_id"]:i+1 for i,x in enumerate(scored_sorted)}
    arows=[]
    for x in c5["rows"]:
        ok=x["status"]=="available"
        z=2*x["frequencyIndex"]-1 if ok else None
        modifier=(2*z if z>=0 else z) if ok else None
        arows.append({"model_run_id":run_id,"set_id":x["set_id"],"collector_roster_desirability_score":x["generalizedD"],"generalized_desirable_outcome_frequency":x["generalizedF"] if ok else None,"generalized_frequency_status":"available" if ok else "unavailable","generalized_frequency_status_reason":None if ok else x["reason"],"frequency_index":x["frequencyIndex"] if ok else None,"frequency_modifier_points":modifier,"collector_appeal_score":x["collectorAppeal"] if ok else None,"score_status":"scored" if ok else "unavailable","score_status_reason":None if ok else x["reason"],"collector_appeal_rank":c5rank.get(x["set_id"]),"component_inputs_json":{"formula":"signed_up2_down1","waitTimeAnchors":["1/16","1/8","1/4"],"frequencyThreshold":">50","excludedInputs":["Energy","Artist","Treatment","market price","Dual-Path Depth","set-level Playability"]},"diagnostics_json":{"researchStatus":x["status"],"researchRank":x.get("rank"),"setName":x["set_name"],"researchEffectiveModifierPoints":x.get("modifierPoints")},"lineage_json":{"c3bFingerprint":FPS["c3bFingerprint"],"c4RosterFingerprint":FPS["c4RosterFingerprint"],"c4FrequencyFingerprint":FPS["c4FrequencyFingerprint"],"c5Fingerprint":FPS["c5Fingerprint"]}})
    return cards,drows,arows


def main() -> int:
    ap=argparse.ArgumentParser(); ap.add_argument("--write-shadow",action="store_true"); args=ap.parse_args(); tracemalloc.start(); started=time.perf_counter()
    load_dotenv(ROOT/"backend"/".env",override=False)
    client=create_client(os.environ["SUPABASE_URL"],os.environ["SUPABASE_SERVICE_ROLE_KEY"],options=ClientOptions(postgrest_client_timeout=60)); db=DB(client)
    source_rows=[]
    for sid in SOURCE_IDS: source_rows += db.read("pokemon_collector_source_runs","id,source_fingerprint,capture_version,raw_payload_json",id=sid)
    manifest,fp=build_manifest(source_rows)
    existing=db.read("pokemon_collector_appeal_model_runs","id,status,validation_json",model_version=MODEL_VERSION,input_fingerprint=fp)
    run_id=existing[0]["id"] if existing else "00000000-0000-0000-0000-000000000000"
    t=time.perf_counter(); cards,drows,arows=payloads(run_id); scoring_duration=time.perf_counter()-t
    if args.write_shadow and (not existing or existing[0]["status"] == "building"):
        if not existing:
            response=client.table("pokemon_collector_appeal_model_runs").insert({"model_version":MODEL_VERSION,"as_of_date":date.today().isoformat(),"source_run_ids":SOURCE_IDS,"input_fingerprint":fp,"scoring_config_json":manifest,"price_policy":"excluded","treatment_policy":"disabled_v1","energy_policy":"neutral_v1","hit_eligibility_policy":"independent","diagnostics_json":{"publicationBoundary":"shadow_only"}}).execute(); db.write_requests+=1; db.rows_written+=1; run_id=response.data[0]["id"]
        for rows in (cards,drows,arows):
            for row in rows: row["model_run_id"]=run_id
        db.upsert("pokemon_collector_appeal_model_run_sources",[{"model_run_id":run_id,"source_run_id":s,"source_position":i} for i,s in enumerate(SOURCE_IDS, 1)],"model_run_id,source_run_id")
        for table, rows, conflict in (("pokemon_card_collector_appeal_scores",cards,"model_run_id,pokemon_canonical_card_id"),("pokemon_set_collector_desirability_scores",drows,"model_run_id,set_id"),("pokemon_set_collector_appeal_scores",arows,"model_run_id,set_id")):
            present=db.count(table,model_run_id=run_id)
            if present not in (0,len(rows)): raise RuntimeError(f"partial append-only output in {table}: {present}/{len(rows)}")
            if not present: db.upsert(table,rows,conflict)
        vt=time.perf_counter(); report=client.rpc("validate_pokemon_collector_appeal_model_run",{"p_model_run_id":run_id,"p_diagnostics":{"builder":"build_pokemon_collector_appeal_v6_shadow.py"}}).execute().data; db.write_requests+=1; validation_duration=time.perf_counter()-vt
    else:
        report=existing[0].get("validation_json") if existing else {"passed":None}; validation_duration=0
    current=db.read("pokemon_collector_appeal_current","model_run_id,model_version,as_of_date",scope="pokemon")
    _,peak=tracemalloc.get_traced_memory()
    result={"mode":"write-shadow" if args.write_shadow else "dry-run","modelRunId":run_id if run_id.strip("0-") else None,"modelVersion":MODEL_VERSION,"topLevelInputFingerprint":fp,"counts":{"cards":len(cards),"c4":len(drows),"c5":len(arows),"scored":sum(x["score_status"]=="scored" for x in arows),"unavailable":sum(x["score_status"]=="unavailable" for x in arows)},"validation":report,"currentPointer":current,"telemetry":{"dbReadRequests":db.read_requests,"rowsRead":db.rows_read,"dbWriteRequests":db.write_requests,"rowsWritten":db.rows_written,"writeBatches":db.batches,"scoringAndAggregationSeconds":round(scoring_duration,4),"validationSeconds":round(validation_duration,4),"totalSeconds":round(time.perf_counter()-started,4),"peakMemoryBytes":peak,"dbErrors":db.errors}}
    print(json.dumps(result,indent=2,sort_keys=True)); return 0 if report.get("passed") is not False else 1

if __name__ == "__main__": raise SystemExit(main())
