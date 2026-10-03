"""Research-only matched Treatment edge panel collector.

Given two treatments and a frozen Set list, collects every same-subject identity
that has exactly one card in each treatment inside the Set. Reuses prior research
panels when supplied and fetches only missing exact Near-Mint histories.

No production writes.
"""
from __future__ import annotations
import argparse, hashlib, json, sys
from collections import defaultdict
from pathlib import Path
from typing import Any
from dotenv import load_dotenv

ROOT=Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path: sys.path.insert(0,str(ROOT))

from backend.pricing_pipeline.pkmnprices_client import PkmnPricesAPIError,PkmnPricesClient
from backend.pricing_pipeline.pkmnprices_credentials import load_pkmnprices_credentials
from backend.scripts.research_treatment_gate_expansion_v2 import (
    _subject_keys,_exact_name_number_matches,_provider_set_matches,_printing_variant
)
from backend.scripts.research_treatment_panel_recovery_v2 import _history_rows

MARKET_DATE="2026-09-29"
STRONG_DAYS=90
MODERATE_DAYS=30

def stable_hash(v:Any)->str:
    return hashlib.sha256(json.dumps(v,sort_keys=True,separators=(",",":"),default=str).encode()).hexdigest()

def chunks(vals,size=100):
    for i in range(0,len(vals),size): yield vals[i:i+size]

def merge_panels(paths):
    panels={}; digests=[]
    for path in paths:
        obj=json.loads(path.read_text(encoding="utf-8")); digests.append(stable_hash(obj))
        for cid,panel in dict(obj.get("panels") or {}).items(): panels.setdefault(str(cid),panel)
    return panels,digests

def build_target(db,*,market_date,treatment_a,treatment_b,set_names):
    treatments=[treatment_a,treatment_b]
    set_rows=list(db.table("sets").select("id,name,era_id").in_("name",set_names).execute().data or [])
    set_by_name={str(x["name"]):dict(x) for x in set_rows}
    if set(set_by_name)!=set(set_names): raise RuntimeError(f"Set resolution incomplete {set(set_names)-set(set_by_name)}")
    era_ids=sorted({str(x["era_id"]) for x in set_rows if x.get("era_id")})
    eras={}
    if era_ids:
        erows=list(db.table("eras").select("id,name").in_("id",era_ids).execute().data or [])
        eras={str(x["id"]):str(x["name"]) for x in erows}
    run_rows=list(db.table("calculation_runs").select("id,target_id,created_at").eq("market_date",market_date).eq("target_type","set").in_("target_id",[x["id"] for x in set_rows]).order("created_at",desc=True).execute().data or [])
    run_by_set={}
    for row in run_rows: run_by_set.setdefault(str(row["target_id"]),str(row["id"]))
    if len(run_by_set)!=len(set_names): raise RuntimeError("simulation authority incomplete")

    cards=[]
    set_ids=[str(x["id"]) for x in set_rows]
    for chunk in chunks(set_ids):
        cards.extend(db.table("pokemon_canonical_cards").select(
            "id,set_id,name,number,printed_number,rarity,pokemon_tcg_api_card_id"
        ).in_("set_id",chunk).in_("rarity",treatments).execute().data or [])
    ids=[str(x["id"]) for x in cards]; subjects=_subject_keys(db,ids)
    grouped=defaultdict(list)
    for c in cards:
        subject=subjects.get(str(c["id"]))
        if subject: grouped[(str(c["set_id"]),subject)].append(dict(c))
    eligible={key:rows for key,rows in grouped.items()
              if len(rows)==2 and {str(x["rarity"]) for x in rows}==set(treatments)}
    if not eligible: raise RuntimeError("no eligible pair identities")

    target_cards=[x for rows in eligible.values() for x in rows]
    target_ids=[str(x["id"]) for x in target_cards]
    identities=[]
    for chunk in chunks(target_ids):
        identities.extend(db.table("pkmnprices_card_identity_v1").select(
            "provider_card_id,canonical_card_id,match_basis,metadata"
        ).in_("canonical_card_id",chunk).execute().data or [])
    idmap={str(x["canonical_card_id"]):dict(x) for x in identities}
    api_ids=sorted({str(x.get("pokemon_tcg_api_card_id")) for x in target_cards if x.get("pokemon_tcg_api_card_id")})
    legacy=[]
    for chunk in chunks(api_ids):
        legacy.extend(db.table("cards").select("id,pokemon_tcg_api_id,rarity,card_number").in_("pokemon_tcg_api_id",chunk).execute().data or [])
    legacy_by_api={str(x["pokemon_tcg_api_id"]):dict(x) for x in legacy}

    id_to_set={str(x["id"]):x for x in set_rows}
    out=[]
    for (set_id,subject),rows in eligible.items():
        st=id_to_set[set_id]; set_name=str(st["name"]); era_name=eras.get(str(st.get("era_id")),"unknown")
        for c in rows:
            legacy_row=legacy_by_api.get(str(c.get("pokemon_tcg_api_card_id") or ""))
            if not legacy_row: raise RuntimeError(f"legacy identity missing card={c['id']}")
            run_id=run_by_set[set_id]
            sim=list(db.table("simulation_input_cards").select("card_variant_id,card_id,effective_pull_rate").eq("calculation_run_id",run_id).eq("card_id",str(legacy_row["id"])).execute().data or [])
            if len(sim)!=1: raise RuntimeError(f"simulation variant resolution failed card={c['id']} rows={len(sim)}")
            vid=str(sim[0]["card_variant_id"])
            pull=list(db.table("simulation_card_variant_pull_rates").select(
                "modeled_probability,printing_type,special_type,status"
            ).eq("calculation_run_id",run_id).eq("card_variant_id",vid).execute().data or [])
            if len(pull)!=1 or not pull[0].get("modeled_probability"): raise RuntimeError(f"pull authority missing card={c['id']}")
            pv=_printing_variant(pull[0].get("printing_type"),pull[0].get("special_type"))
            if not pv: raise RuntimeError(f"provider variant unsupported card={c['id']}")
            ident=idmap.get(str(c["id"])); frozen=str((ident or {}).get("metadata",{}).get("card_variant_id") or "")
            if frozen and frozen!=vid: raise RuntimeError(f"variant drift card={c['id']}")
            out.append({
              "canonical_card_id":str(c["id"]),"set_id":set_id,"set_name":set_name,"era_name":era_name,
              "subject_key":subject,"card_name":c["name"],"number":str(c["number"]),"rarity":c["rarity"],
              "card_variant_id":vid,"provider_variant":pv,"modeled_probability":float(pull[0]["modeled_probability"]),
              "provider_card_id":None if not ident else int(ident["provider_card_id"]),
              "identity_source":None if not ident else str(ident.get("match_basis") or "cached")
            })
    order={treatment_a:0,treatment_b:1}
    out=sorted(out,key=lambda x:(x["era_name"],x["set_name"],x["subject_key"],order[x["rarity"]]))
    by_set=defaultdict(int)
    for (set_id,subject) in eligible: by_set[id_to_set[set_id]["name"]]+=1
    return {
      "version":"treatment_pair_edge_panel_v1","market_date":market_date,
      "treatment_a":treatment_a,"treatment_b":treatment_b,"set_names":set_names,
      "identity_count":len(eligible),"card_count":len(out),"set_identity_counts":dict(by_set),
      "cards":out,"fingerprint":stable_hash(out)
    }

def resolve_provider(provider,row):
    if row.get("provider_card_id"): return int(row["provider_card_id"]),"cached"
    candidates=provider.cards_by_name_number(name=row["card_name"],number=row["number"],language="English",per_page=100)
    exact=_exact_name_number_matches(candidates,name=row["card_name"],number=row["number"])
    if len(exact)>1: exact=[x for x in exact if _provider_set_matches(x,row["set_name"])]
    if len(exact)!=1: raise RuntimeError(f"provider identity count={len(exact)} {row['set_name']} {row['card_name']} {row['number']}")
    return int(exact[0]["id"]),"research_exact_name_number_set"

def capture(provider,target,base_panels,base_digests,period,credit_cap,min_ready_sets):
    a=target["treatment_a"]; b=target["treatment_b"]; panels={}; failures=[]; reused=0; fetched=0; start=provider.credits_charged
    for row in target["cards"]:
        cid=row["canonical_card_id"]
        if cid in base_panels: panels[cid]=base_panels[cid]; reused+=1; continue
        if provider.credits_charged-start>=credit_cap: failures.append({"canonical_card_id":cid,"error":"local_credit_cap"}); break
        try:
            pid,source=resolve_provider(provider,row)
            payload=provider.price_history_page(pid,period=period,condition="Near Mint",variant=row["provider_variant"],limit=365,page=1)
            hist=_history_rows(payload); fetched+=1
            panels[cid]={"card":{**row,"provider_card_id":pid,"identity_source":source},"history":hist}
            print(f"[pair-edge] {a} -> {b} set={row['set_name']} subject={row['subject_key']} rarity={row['rarity']} rows={len(hist)} credits={provider.credits_charged-start}",flush=True)
        except PkmnPricesAPIError as exc:
            failures.append({"canonical_card_id":cid,"error":f"{exc}"})
            if exc.code=="credit_limit_exceeded": break
        except Exception as exc:
            failures.append({"canonical_card_id":cid,"error":f"{type(exc).__name__}: {exc}"})
    groups=defaultdict(list)
    for row in target["cards"]: groups[(row["set_name"],row["subject_key"])].append(row)
    readiness=[]
    for (set_name,subject),rows in sorted(groups.items()):
        by={x["rarity"]:x for x in rows}; common=None
        for t in (a,b):
            cid=by[t]["canonical_card_id"]
            if cid not in panels: common=set(); break
            dates={x["date"] for x in panels[cid]["history"]}; common=dates if common is None else common&dates
        shared=len(common or set())
        status="PANEL_READY_STRONG" if shared>=STRONG_DAYS else "PANEL_READY_MODERATE" if shared>=MODERATE_DAYS else "HISTORY_BLOCKED"
        readiness.append({"era_name":rows[0]["era_name"],"set_name":set_name,"subject_key":subject,"shared_dates":shared,"status":status,
                          "card_a":by[a]["canonical_card_id"],"card_b":by[b]["canonical_card_id"]})
    by_set=defaultdict(list)
    for x in readiness: by_set[x["set_name"]].append(x)
    set_results=[]
    for set_name,rows in sorted(by_set.items()):
        ready=[x for x in rows if x["status"]!="HISTORY_BLOCKED"]
        set_results.append({"era_name":rows[0]["era_name"],"set_name":set_name,"identity_count":len(rows),"ready_identities":len(ready),
                            "passes_G1_G4":len(ready)>=2 and len({cid for x in ready for cid in (x["card_a"],x["card_b"])})>=4})
    passing=[x for x in set_results if x["passes_G1_G4"]]
    progression=len(passing)>=min_ready_sets
    return {
      "status":"COMPLETE" if not failures else "PARTIAL","version":target["version"],"period":period,"target":target,
      "base_artifact_digests":base_digests,"reused_panels":reused,"fetched_panels":fetched,
      "provider_calls":provider.successful_request_count,"request_attempt_count":provider.request_attempt_count,
      "credits_used":provider.credits_charged-start,"provider_credit_limit":provider.credits_limit,"failures":failures,
      "panels":panels,"readiness":readiness,"set_results":set_results,"required_ready_sets":min_ready_sets,
      "progression_pass":progression,"production_writes":0
    }

def main(argv=None):
    p=argparse.ArgumentParser()
    p.add_argument("--treatment-a",required=True); p.add_argument("--treatment-b",required=True)
    p.add_argument("--set",dest="sets",action="append",required=True)
    p.add_argument("--min-ready-sets",type=int,default=2)
    p.add_argument("--base-artifact",type=Path,action="append",default=[])
    p.add_argument("--market-date",default=MARKET_DATE); p.add_argument("--period",default="180d")
    p.add_argument("--credit-cap",type=int,default=5000); p.add_argument("--output",type=Path,required=True)
    args=p.parse_args(argv); load_dotenv(ROOT/"backend/.env",override=False)
    from backend.db.clients.supabase_client import supabase
    target=build_target(supabase,market_date=args.market_date,treatment_a=args.treatment_a,treatment_b=args.treatment_b,set_names=args.sets)
    base,digests=merge_panels(args.base_artifact)
    creds=load_pkmnprices_credentials(allow_frontend_fallback=False); provider=PkmnPricesClient(creds.api_key,min_request_interval=.55,timeout=10,max_retries=0)
    result=capture(provider,target,base,digests,args.period,args.credit_cap,args.min_ready_sets)
    args.output.parent.mkdir(parents=True,exist_ok=True); args.output.write_text(json.dumps(result,indent=2,sort_keys=True,default=str)+"\n",encoding="utf-8")
    print(json.dumps({k:v for k,v in result.items() if k not in {"target","panels","readiness"}},indent=2,sort_keys=True,default=str))
    return 0 if result["status"]=="COMPLETE" and result["progression_pass"] else 2
if __name__=="__main__": raise SystemExit(main())
