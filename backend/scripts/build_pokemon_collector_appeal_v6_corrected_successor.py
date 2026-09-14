"""Build and optionally persist the corrected, non-current Collector Appeal V6 successor."""
from __future__ import annotations

import argparse, hashlib, json, math, os, statistics, sys, time
from collections import Counter, defaultdict
from datetime import date
from pathlib import Path
from typing import Any

from dotenv import load_dotenv
from supabase import ClientOptions, create_client

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from backend.desirability.collector_appeal import collector_appeal_v4_frequency_index
from backend.desirability.collector_appeal_inputs import load_pull_rate_model
from backend.desirability.opening_appeal import union_probability_from_cards
from backend.desirability.rarity_buckets import classify_rarity
from backend.db.services.explore_rip_statistics_service import get_rip_statistics_targets_payload
from backend.scripts.research_collector_c3b_playability_lift import build_playability, trainer_scores

MODEL_VERSION = "pokemon_collector_appeal_v6_corrected_complete_trends_v2"
TRENDS_RUN = "77792597-7fb4-48e9-bd52-3034061f9d3e"
TRENDS_HASH = "c8614e5041c279853ad87600226777beb844371289bbef07d41b25c6aa5428db"
OTHER_SOURCES = ["b3997343-1363-45aa-b1b0-9a6de1ce3793", "648e5375-47cb-4972-b01d-faceb6348d1d", "9947aaf7-8647-484f-8c9c-2cec59792cdb"]
SOURCE_IDS = [TRENDS_RUN, *OTHER_SOURCES]
BASE_C3 = ROOT / "backend/artifacts/collector_c3b_card_appeal_shadow_v2.json"
COMPLETE_TRENDS = ROOT / "backend/artifacts/collector_v6_redesign_research/trends_v2_capture/complete_capture_v2.jsonl"
UNIVERSE = ROOT / "backend/artifacts/collector_v6_redesign_research/pokemon_subject_universe.json"
FREEZE = ROOT / "backend/config/pokemon_collector_v6_pokemon_roster_d_freeze_v1.json"
OLD_C4 = ROOT / "backend/artifacts/collector_c4_set_components_shadow_v1.json"
OUTPUT = ROOT / "backend/artifacts/collector_v6_corrected_successor_v1.json"

def canonical_hash(value: Any) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()).hexdigest()

def paged(factory, size=1000):
    rows,start=[],0
    while True:
        page=factory().range(start,start+size-1).execute().data or []
        rows.extend(page)
        if len(page)<size:return rows
        start+=size

def pokemon_d(values: list[float]) -> tuple[float, float, float]:
    vals = sorted((v for v in values if v > 50), reverse=True)
    weights = [0.6**i * 0.4 / (1 - 0.6**8) for i in range(8)]
    stretched = [50 + 50 * ((min(100, v) - 50) / 50) ** 4 for v in vals[:8]]
    strength = sum(w * v for w, v in zip(weights, stretched))
    mass = sum(max(0.0, min(1.0, (v - 60) / 40)) for v in vals)
    breadth = 1 - math.exp(-mass / 4.0)
    return strength + (100 - strength) * 0.20 * breadth, strength, breadth

def trainer_d(values: list[float]) -> float:
    mass = sum(math.sqrt(max((v - 50) / 50, 0)) for v in values)
    return 100 * (1 - math.exp(-mass / 6.0)) if mass else 0.0

def card_baseline(row: dict, composite: dict[str, float]) -> float:
    if row["subject_type"] == "pokemon":
        names = [x.strip() for x in str(row.get("subject_identity") or "").split(" + ") if x.strip()]
        scores = [composite[x] for x in names if x in composite]
        if not scores: raise RuntimeError(f"Pokemon card lacks complete subject authority: {row['canonical_card_id']}")
        return statistics.mean(scores)
    if row["subject_type"] == "trainer": return float(row["subject_appeal_percentile"])
    return 50.0

def _pokemon_trends(client, source_run_id: str) -> list[dict]:
    rows = paged(lambda: client.table("pokemon_collector_entity_observations").select(
        "raw_entity_name,normalized_observation_score,raw_row_json"
    ).eq("source_run_id", source_run_id))
    result = []
    for row in rows:
        raw = row.get("raw_row_json") or {}
        if row.get("normalized_observation_score") is not None:
            result.append({"pokemon_name": raw.get("pokemonName") or row.get("raw_entity_name"),
                           "global_relative": float(row["normalized_observation_score"])})
    return result


def build(client, *, pokemon_trends_source_run_id: str,
          trainer_12m_source_run_id: str, trainer_5y_source_run_id: str,
          playability_source_run_id: str) -> dict:
    trends = _pokemon_trends(client, pokemon_trends_source_run_id)
    fan = {r["pokemon_name"]: float(r["fan_popularity_score"]) for r in json.loads(UNIVERSE.read_text(encoding="utf-8"))}
    composite = {r["pokemon_name"]: .75 * fan[r["pokemon_name"]] + .25 * min(100.0, float(r["global_relative"])) for r in trends}
    if len(composite) != 1025: raise RuntimeError("complete Trends/fan composite coverage mismatch")
    base = json.loads(BASE_C3.read_text(encoding="utf-8"))["shadowRows"]
    trainer_by_id = trainer_scores(client, trainer_12m_source_run_id, trainer_5y_source_run_id)
    refs = paged(lambda: client.table("pokemon_collector_entity_reference").select(
        "id,display_name").eq("entity_type", "trainer").eq("active", True))
    trainer_by_name = {str(row["display_name"]): trainer_by_id[str(row["id"])]
                       for row in refs if str(row["id"]) in trainer_by_id}
    play_by_id = build_playability(client, playability_source_run_id)
    functional = paged(lambda: client.table("pokemon_card_functional_reference").select(
        "id,functional_key").eq("active", True))
    play_by_name = {str(row["functional_key"]): play_by_id[str(row["id"])]
                    for row in functional if str(row["id"]) in play_by_id}
    cards=[]
    for source in base:
        if source["subject_type"] == "trainer":
            values = [trainer_by_name[name.strip()] for name in str(source.get("subject_identity") or "").split(" + ")
                      if name.strip() in trainer_by_name]
            b = statistics.mean(values) if values else float(source["subject_appeal_percentile"])
        else:
            b=card_baseline(source,composite)
        evidence = play_by_name.get(str(source.get("playability_functional_identity") or ""))
        raw = evidence.get("rawScore") if evidence else None
        conf = evidence.get("confidence") if evidence else None
        effective=0.0 if raw is None or conf is None else float(raw)*float(conf)
        lift=(100-b)*.20*(effective/100); final=b+lift
        cards.append({**source,"subject_appeal_corrected":b,"playability_raw_score":raw,
                      "confidence":conf,"applied_lift_corrected":lift,
                      "card_collector_appeal_corrected":final,
                      "source_runs":{"playability":playability_source_run_id,
                                     "trainer12m":trainer_12m_source_run_id,
                                     "trainer5y":trainer_5y_source_run_id}})
    c3_identity={"version":"collector_c3b_corrected_raw_pokemon_v1","pokemonSubject":"raw_75_fan_25_trends_v2","playabilityLambda":.20,"unknownPlayability":"zero_lift","trainerAuthority":"accepted_separate_evidence","functional":"diagnostic_only","artist":"excluded","treatment":"diagnostic_only","scarcity":"diagnostic_only","marketValueInput":"excluded"}
    composite_identity={"version":"pokemon_desirability_raw_75_25_complete_trends_v2_v1","trendsSourceRunId":pokemon_trends_source_run_id,"weights":{"fan":.75,"trends":.25},"trendsScale":"persisted normalized score clamp(global_relative,0,100)","percentileTransform":False,"outputFingerprint":canonical_hash(composite)}
    composite_fp=canonical_hash(composite_identity); c3_identity["pokemonCompositeFingerprint"]=composite_fp; c3_fp=canonical_hash(c3_identity)
    old={x["set_id"]:x for x in json.loads(OLD_C4.read_text(encoding="utf-8"))["sets"]}
    byset=defaultdict(list)
    for row in cards:
        if row["set_id"] in old: byset[row["set_id"]].append(row)
    pull=load_pull_rate_model(client)
    ranking_payload=get_rip_statistics_targets_payload(limit=250,include_rankings_top_chase=False)
    snapshots={str(x.get("set_id") or x.get("target_id")):str(x.get("calculation_run_id")) for x in ranking_payload.get("targets") or [] if x.get("calculation_run_id")}
    sets=[]
    for sid, rows in byset.items():
        pokemon_groups=defaultdict(list); trainer_groups=defaultdict(list)
        for row in rows:
            if row["subject_type"]=="pokemon":
                for name in str(row.get("subject_identity") or "").split(" + "): pokemon_groups[name.strip()].append(row["card_collector_appeal_corrected"])
            elif row["subject_type"]=="trainer":
                for name in str(row.get("subject_identity") or "").split(" + "): trainer_groups[name.strip()].append(row["card_collector_appeal_corrected"])
        pvals=[max(x) for x in pokemon_groups.values()]; tvals=[max(x) for x in trainer_groups.values()]
        dp,s,b=pokemon_d(pvals); dt=trainer_d(tvals); tl=(100-dp)*.15*(dt/100); df=dp+tl
        eligible=[r for r in rows if r.get("hit_eligibility") and r["card_collector_appeal_corrected"]>50]
        old_eligible={r["canonical_card_id"] for r in rows if r.get("hit_eligibility") and float(r["final_card_collector_appeal"])>50}
        new_eligible={r["canonical_card_id"] for r in eligible}
        modeled=[]
        for r in eligible:
            m=(pull.get(sid) or {}).get(classify_rarity(r.get("rarity")).normalized_key)
            if m: modeled.append({"canonical_card_id":r["canonical_card_id"],"pull_probability":m["probability"],"slot_group":m["slot_group"]})
        excess=sum(r["card_collector_appeal_corrected"]-50 for r in eligible)
        covered_ids={r["canonical_card_id"] for r in modeled}; covered=sum(r["card_collector_appeal_corrected"]-50 for r in eligible if r["canonical_card_id"] in covered_ids)
        share=covered/excess if excess else None; f=union_probability_from_cards(list({x["canonical_card_id"]:x for x in modeled}.values())) if modeled and share is not None and share>=.25 else None
        idx=collector_appeal_v4_frequency_index(f) if f is not None else None; z=2*idx-1 if idx is not None else None; mod=(2*z if z>=0 else z) if z is not None else None
        final=max(0,min(100,df+mod)) if mod is not None else None
        oldf=((old.get(sid) or {}).get("frequency") or {}).get("card_gt50",{}).get("value")
        oldcount=((old.get(sid) or {}).get("frequency") or {}).get("card_gt50",{}).get("eligibleCards")
        sets.append({"set_id":sid,"set_name":(old.get(sid) or {}).get("set_name"),"D_pokemon":dp,"S":s,"B":b,"D_trainer":dt,"trainer_lift_points":tl,"D_final":df,"old_desirable_card_count":oldcount,"corrected_desirable_card_count":len(eligible),"entering_cards":sorted(new_eligible-old_eligible),"leaving_cards":sorted(old_eligible-new_eligible),"old_F":oldf,"F":f,"F_delta":None if f is None or oldf is None else f-oldf,"frequency_index":idx,"frequency_modifier":mod,"collector_appeal":final,"calculation_run_id":snapshots.get(sid),"unavailable_reason":None if final is not None else "collector_appeal_unavailable_no_generalized_frequency"})
    ranked=sorted((x for x in sets if x["collector_appeal"] is not None),key=lambda x:(-x["collector_appeal"],x["set_id"]))
    for i,x in enumerate(ranked,1): x["rank"]=i
    freeze=json.loads(FREEZE.read_text(encoding="utf-8")); d_output_fp=canonical_hash([{k:x[k] for k in ("set_id","D_pokemon","D_trainer","trainer_lift_points","D_final")} for x in sorted(sets,key=lambda x:x["set_id"])])
    f_identity={"version":"generalized_desirable_frequency_corrected_c3b_v1","threshold":">50","union":"mutually-exclusive slot addition; independent-slot miss multiplication","coverageFloor":.25,"pullAuthority":"existing accepted exact model","calculationRunLineage":"explicit"}; f_fp=canonical_hash(f_identity)
    c5_identity={"version":"collector_c5_frozen_signed_frequency_v1","anchors":[1/16,1/8,1/4],"modifier":{"up":2,"down":1},"dOutputFingerprint":d_output_fp,"fFingerprint":f_fp}; c5_fp=canonical_hash(c5_identity)
    deps={"c3a5SubjectFingerprint":composite_fp,"c3bFingerprint":c3_fp,"c4RosterFingerprint":freeze["formulaFingerprint"],"c4FrequencyFingerprint":f_fp,"c5Fingerprint":c5_fp}
    source_ids=[pokemon_trends_source_run_id,trainer_12m_source_run_id,trainer_5y_source_run_id,playability_source_run_id]
    manifest={"version":MODEL_VERSION,"dependencies":deps,"sourceEvidence":source_ids,"trends":{"sourceRunId":pokemon_trends_source_run_id,"manifest":"pokemon_trends_anchor_ladder_manifest_v1","manifestFingerprint":"009418a05f6b9631"},"contracts":{"pokemonComposite":composite_identity,"pokemonDFormulaFingerprint":freeze["formulaFingerprint"],"productionDOutputFingerprint":d_output_fp,"trainerLambda":.15,"trainerSeparateDomain":True,"playabilityLambda":.20,"functional":"diagnostic_only","artist":"excluded","treatment":"diagnostic_only","scarcity":"diagnostic_only","marketValueInput":"excluded","c5":c5_identity},"expectedCounts":{"cardRows":len(cards),"c4Rows":len(sets),"c5Rows":len(sets),"scoredRows":len(ranked),"unavailableRows":len(sets)-len(ranked)}}
    fp=canonical_hash(manifest);manifest["topLevelInputFingerprint"]=fp
    return {"modelVersion":MODEL_VERSION,"modelFingerprint":fp,"manifest":manifest,"composite":composite,"compositeFingerprint":composite_fp,"c3bFingerprint":c3_fp,"pokemonDOutputFingerprint":d_output_fp,"generalizedFFingerprint":f_fp,"c5Fingerprint":c5_fp,"cards":cards,"sets":sets}

def persistence_rows(built,run_id):
    deps=built["manifest"]["dependencies"]
    trends_run=built["manifest"]["trends"]["sourceRunId"]
    cards=[{"model_run_id":run_id,"pokemon_canonical_card_id":x["canonical_card_id"],"set_id":x["set_id"],"subject_policy":{"pokemon":"pokemon","trainer":"trainer","neutral_functional":"neutral"}[x["subject_type"]],"subject_baseline_score":x["subject_appeal_corrected"],"artist_recognition_score":None,"playability_score":None if x.get("playability_raw_score") is None else float(x["playability_raw_score"])*float(x["confidence"]),"artist_lift":0,"playability_lift":x["applied_lift_corrected"]/(100-x["subject_appeal_corrected"]) if x["subject_appeal_corrected"]<100 else 0,"combined_lift":x["applied_lift_corrected"]/(100-x["subject_appeal_corrected"]) if x["subject_appeal_corrected"]<100 else 0,"collector_card_appeal_score":x["card_collector_appeal_corrected"],"score_status":"scored","confidence":"insufficient" if x.get("confidence") is None else ("high" if x["confidence"]>=.8 else "medium" if x["confidence"]>=.5 else "low"),"price_input_excluded":True,"treatment_input_excluded":True,"hit_eligibility_independent":True,"component_inputs_json":{"subjectType":x["subject_type"],"subjectIdentity":x.get("subject_identity"),"appliedLiftPoints":x["applied_lift_corrected"],"artistEnabled":False,"functionalDiagnosticOnly":x["subject_type"]=="neutral_functional"},"lineage_json":{"trendsSourceRunId":trends_run,"c3bFingerprint":deps["c3bFingerprint"],"sourceRuns":x["source_runs"],"excludedInputs":["Energy","Artist","Treatment","Scarcity","market value"]}} for x in built["cards"]]
    rankd={x["set_id"]:i+1 for i,x in enumerate(sorted(built["sets"],key=lambda x:(-x["D_final"],x["set_id"])))}
    drows=[{"model_run_id":run_id,"set_id":x["set_id"],"aggregation_version":"pokemon_d_frozen_plus_trainer_headroom_v1","collector_desirability_score":x["D_final"],"collector_desirability_rank":rankd[x["set_id"]],"eligible_card_count":sum(r.get("hit_eligibility") for r in built["cards"] if r["set_id"]==x["set_id"]),"scored_card_count":sum(r.get("hit_eligibility") and r["subject_type"]!="neutral_functional" for r in built["cards"] if r["set_id"]==x["set_id"]),"neutral_card_count":sum(r.get("hit_eligibility") and r["subject_type"]=="neutral_functional" for r in built["cards"] if r["set_id"]==x["set_id"]),"unsupported_card_count":0,"score_coverage_ratio":1,"max_card_appeal_score":max(r["card_collector_appeal_corrected"] for r in built["cards"] if r["set_id"]==x["set_id"]),"top_3_card_appeal_score":None,"top_5_card_appeal_score":None,"effective_desirable_card_count":x["corrected_desirable_card_count"],"subject_rollups_json":[],"top_cards_json":[],"component_inputs_json":{"D_pokemon":x["D_pokemon"],"D_trainer":x["D_trainer"],"trainerLiftPoints":x["trainer_lift_points"],"trainerLambda":.15,"functionalDiagnosticOnly":True,"c3bFingerprint":deps["c3bFingerprint"],"c4RosterFingerprint":deps["c4RosterFingerprint"]},"diagnostics_json":{"S":x["S"],"B":x["B"]}} for x in built["sets"]]
    arows=[{"model_run_id":run_id,"set_id":x["set_id"],"collector_roster_desirability_score":x["D_final"],"generalized_desirable_outcome_frequency":x["F"],"generalized_frequency_status":"available" if x["F"] is not None else "unavailable","generalized_frequency_status_reason":None if x["F"] is not None else x["unavailable_reason"],"frequency_index":x["frequency_index"],"frequency_modifier_points":x["frequency_modifier"],"collector_appeal_score":x["collector_appeal"],"score_status":"scored" if x["collector_appeal"] is not None else "unavailable","score_status_reason":x["unavailable_reason"],"collector_appeal_rank":x.get("rank"),"component_inputs_json":{"formula":"signed_up2_down1","waitTimeAnchors":["1/16","1/8","1/4"],"frequencyThreshold":">50","excludedInputs":["Energy","Artist","Treatment","Scarcity","market value"]},"diagnostics_json":{"D_pokemon":x["D_pokemon"],"D_trainer":x["D_trainer"],"trainerLiftPoints":x["trainer_lift_points"],"calculationRunId":x["calculation_run_id"],"oldF":x["old_F"],"FDelta":x["F_delta"]},"lineage_json":{"c3bFingerprint":deps["c3bFingerprint"],"c4RosterFingerprint":deps["c4RosterFingerprint"],"c4FrequencyFingerprint":deps["c4FrequencyFingerprint"],"c5Fingerprint":deps["c5Fingerprint"],"trendsSourceRunId":trends_run}} for x in built["sets"]]
    return cards,drows,arows

def main():
    ap=argparse.ArgumentParser();ap.add_argument("--write-stage",action="store_true");ap.add_argument("--output",type=Path,default=OUTPUT)
    for flag in ("pokemon-trends","trainer-12m","trainer-5y","playability"):ap.add_argument(f"--{flag}-source-run-id",required=True)
    args=ap.parse_args();load_dotenv(ROOT/"backend/.env",override=False)
    client=create_client(os.environ["SUPABASE_URL"],os.environ["SUPABASE_SERVICE_ROLE_KEY"],options=ClientOptions(postgrest_client_timeout=60));built=build(client,pokemon_trends_source_run_id=args.pokemon_trends_source_run_id,trainer_12m_source_run_id=args.trainer_12m_source_run_id,trainer_5y_source_run_id=args.trainer_5y_source_run_id,playability_source_run_id=args.playability_source_run_id);args.output.write_text(json.dumps(built,indent=2,ensure_ascii=False),encoding="utf-8")
    existing=client.table("pokemon_collector_appeal_model_runs").select("id,status,validation_json").eq("model_version",MODEL_VERSION).eq("input_fingerprint",built["modelFingerprint"]).execute().data or [];run_id=str(existing[0]["id"]) if existing else None;report=(existing[0].get("validation_json") if existing else None)
    if args.write_stage and (not existing or existing[0]["status"] == "building"):
        if not existing:
            run=client.table("pokemon_collector_appeal_model_runs").insert({"model_version":MODEL_VERSION,"as_of_date":date.today().isoformat(),"source_run_ids":built["manifest"]["sourceEvidence"],"input_fingerprint":built["modelFingerprint"],"scoring_config_json":built["manifest"],"price_policy":"excluded","treatment_policy":"disabled_v1","energy_policy":"neutral_v1","hit_eligibility_policy":"independent","diagnostics_json":{"publicationBoundary":"staged_not_current"}}).execute().data[0];run_id=str(run["id"])
        cards,drows,arows=persistence_rows(built,run_id)
        if not existing: client.table("pokemon_collector_appeal_model_run_sources").insert([{"model_run_id":run_id,"source_run_id":s,"source_position":i} for i,s in enumerate(built["manifest"]["sourceEvidence"],1)]).execute()
        for table,rows in (("pokemon_card_collector_appeal_scores",cards),("pokemon_set_collector_desirability_scores",drows),("pokemon_set_collector_appeal_scores",arows)):
            present=client.table(table).select("model_run_id",count="exact").eq("model_run_id",run_id).limit(0).execute().count or 0
            if present not in (0,len(rows)): raise RuntimeError(f"partial append-only output in {table}: {present}/{len(rows)}")
            if not present:
                for i in range(0,len(rows),100): client.table(table).insert(rows[i:i+100]).execute()
        report=client.rpc("validate_pokemon_collector_appeal_model_run",{"p_model_run_id":run_id,"p_diagnostics":{"builder":"build_pokemon_collector_appeal_v6_corrected_successor.py","stagedOnly":True}}).execute().data
    print(json.dumps({"mode":"write-stage" if args.write_stage else "dry-run","modelRunId":run_id,"modelVersion":MODEL_VERSION,"modelFingerprint":built["modelFingerprint"],"compositeFingerprint":built["compositeFingerprint"],"c3bFingerprint":built["c3bFingerprint"],"pokemonDOutputFingerprint":built["pokemonDOutputFingerprint"],"generalizedFFingerprint":built["generalizedFFingerprint"],"c5Fingerprint":built["c5Fingerprint"],"counts":{"cards":len(built["cards"]),"sets":len(built["sets"]),"scored":sum(x["collector_appeal"] is not None for x in built["sets"]),"unavailable":sum(x["collector_appeal"] is None for x in built["sets"])},"validation":report},indent=2));return 0

if __name__=="__main__": raise SystemExit(main())
