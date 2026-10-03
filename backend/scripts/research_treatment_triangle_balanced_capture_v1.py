"""Balanced research-only triangle capture across 5 Sets per era.

Captures Double Rare, Ultra Rare, and SIR for every subject with all three
treatments in the selected 10-Set cohort. No production writes.
"""
from __future__ import annotations
import argparse, hashlib, json, sys
from collections import defaultdict
from pathlib import Path
from typing import Any
from dotenv import load_dotenv

ROOT=Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path: sys.path.insert(0,str(ROOT))

from backend.pricing_pipeline.pkmnprices_client import PkmnPricesAPIError, PkmnPricesClient
from backend.pricing_pipeline.pkmnprices_credentials import load_pkmnprices_credentials
from backend.scripts.research_treatment_gate_expansion_v2 import (
    _paged,_subject_keys,_printing_variant,_exact_name_number_matches,_provider_set_matches,_history_rows
)

VERSION="treatment_triangle_balanced_10set_v1"
MARKET_DATE="2026-09-29"
TREATMENTS={"Double Rare","Ultra Rare","Special Illustration Rare"}
SET_NAMES=[
    "Mega Evolution","Chaos Rising","Perfect Order","Phantasmal Flames","Pitch Black",
    "Paradox Rift","Destined Rivals","Paldea Evolved","Surging Sparks","Temporal Forces",
]
ERA_BY_SET={
    "Mega Evolution":"Mega Evolution","Chaos Rising":"Mega Evolution","Perfect Order":"Mega Evolution",
    "Phantasmal Flames":"Mega Evolution","Pitch Black":"Mega Evolution",
    "Paradox Rift":"Scarlet and Violet","Destined Rivals":"Scarlet and Violet",
    "Paldea Evolved":"Scarlet and Violet","Surging Sparks":"Scarlet and Violet",
    "Temporal Forces":"Scarlet and Violet",
}

def stable_hash(v:Any)->str:
    return hashlib.sha256(json.dumps(v,sort_keys=True,separators=(",",":"),default=str).encode()).hexdigest()

def build_targets(db,market_date:str)->dict[str,Any]:
    sets=list(db.table("sets").select("id,name").in_("name",SET_NAMES).execute().data or [])
    set_by_name={str(x["name"]):str(x["id"]) for x in sets}
    if set(set_by_name)!=set(SET_NAMES): raise RuntimeError("selected Set resolution incomplete")
    runs=_paged(lambda: db.table("calculation_runs").select("id,target_id,created_at")
                .eq("market_date",market_date).eq("target_type","set")
                .in_("target_id",list(set_by_name.values())).order("created_at",desc=True))
    run_by_set={}
    for r in runs: run_by_set.setdefault(str(r["target_id"]),str(r["id"]))
    if len(run_by_set)!=len(SET_NAMES): raise RuntimeError("simulation authority incomplete for selected Sets")
    cards=_paged(lambda: db.table("pokemon_canonical_cards")
                 .select("id,set_id,name,number,printed_number,rarity,pokemon_tcg_api_card_id")
                 .in_("set_id",list(set_by_name.values())).in_("rarity",sorted(TREATMENTS)))
    subjects=_subject_keys(db,[str(x["id"]) for x in cards])
    groups=defaultdict(list)
    for c in cards:
        subject=subjects.get(str(c["id"]))
        if subject: groups[(str(c["set_id"]),subject)].append(dict(c))
    eligible={(sid,subj) for (sid,subj),rows in groups.items() if {x["rarity"] for x in rows}==TREATMENTS}
    selected=[c for c in cards if (str(c["set_id"]),subjects.get(str(c["id"]))) in eligible]
    if len(selected)!=3*len(eligible): raise RuntimeError("triangle card count mismatch")

    identities=_paged(lambda: db.table("pkmnprices_card_identity_v1")
                      .select("provider_card_id,canonical_card_id,match_basis,metadata")
                      .in_("canonical_card_id",[str(x["id"]) for x in selected]))
    identity_by={str(x["canonical_card_id"]):dict(x) for x in identities}

    api_ids=sorted({str(x.get("pokemon_tcg_api_card_id")) for x in selected if x.get("pokemon_tcg_api_card_id")})
    legacy=[]
    for i in range(0,len(api_ids),100):
        legacy += list(db.table("cards").select("id,pokemon_tcg_api_id,rarity,card_number")
                       .in_("pokemon_tcg_api_id",api_ids[i:i+100]).execute().data or [])
    legacy_by={str(x["pokemon_tcg_api_id"]):dict(x) for x in legacy}

    inputs=[]
    for card in selected:
        cid=str(card["id"]); set_id=str(card["set_id"]); subject=subjects[cid]
        set_name=next(n for n,sid in set_by_name.items() if sid==set_id)
        identity=identity_by.get(cid)
        direct=str((identity or {}).get("metadata",{}).get("card_variant_id") or "")
        legacy_row=legacy_by.get(str(card.get("pokemon_tcg_api_card_id") or ""))
        if not legacy_row: raise RuntimeError(f"legacy identity missing card={cid}")
        sim=list(db.table("simulation_input_cards").select("card_variant_id,card_id,effective_pull_rate")
                 .eq("calculation_run_id",run_by_set[set_id]).eq("card_id",str(legacy_row["id"])).execute().data or [])
        if len(sim)!=1: raise RuntimeError(f"simulation variant resolution failed card={cid} rows={len(sim)}")
        variant_id=str(sim[0]["card_variant_id"])
        if direct and direct!=variant_id: raise RuntimeError(f"frozen variant drift card={cid}")
        pulls=list(db.table("simulation_card_variant_pull_rates")
                   .select("modeled_probability,printing_type,special_type,status")
                   .eq("calculation_run_id",run_by_set[set_id]).eq("card_variant_id",variant_id).execute().data or [])
        if len(pulls)!=1 or not pulls[0].get("modeled_probability"): raise RuntimeError(f"pull authority missing card={cid}")
        pv=_printing_variant(pulls[0].get("printing_type"),pulls[0].get("special_type"))
        if not pv: raise RuntimeError(f"provider variant unsupported card={cid}")
        inputs.append({
            "canonical_card_id":cid,"set_id":set_id,"set_name":set_name,"era_name":ERA_BY_SET[set_name],
            "subject_key":subject,"card_name":card["name"],"number":str(card["number"]),"rarity":card["rarity"],
            "card_variant_id":variant_id,"provider_variant":pv,"modeled_probability":float(pulls[0]["modeled_probability"]),
            "provider_card_id":None if not identity else int(identity["provider_card_id"]),
        })
    return {"version":VERSION,"market_date":market_date,
            "cards":sorted(inputs,key=lambda x:(x["era_name"],x["set_name"],x["subject_key"],x["rarity"])),
            "set_names":SET_NAMES,"identity_count":len(eligible),"card_count":len(inputs)}

def resolve(provider,row):
    if row.get("provider_card_id"): return int(row["provider_card_id"]),"cached"
    rows=provider.cards_by_name_number(name=row["card_name"],number=row["number"],language="English",per_page=100)
    exact=_exact_name_number_matches(rows,name=row["card_name"],number=row["number"])
    if len(exact)>1: exact=[x for x in exact if _provider_set_matches(x,row["set_name"])]
    if len(exact)!=1: raise RuntimeError(f"provider identity count={len(exact)} card={row['canonical_card_id']} {row['card_name']} #{row['number']} {row['set_name']}")
    return int(exact[0]["id"]),"research_exact_name_number_set"

def capture(provider,target,period,credit_cap):
    start=provider.credits_charged; panels={}; failures=[]
    for i,row in enumerate(target["cards"],1):
        if provider.credits_charged-start>=credit_cap:
            failures.append({"card":row["canonical_card_id"],"error":"local_credit_cap"}); break
        try:
            pid,source=resolve(provider,row)
            payload=provider.price_history_page(pid,period=period,condition="Near Mint",variant=row["provider_variant"],limit=365,page=1)
            hist=_history_rows(payload)
            panels[row["canonical_card_id"]]={"card":{**row,"provider_card_id":pid,"identity_source":source},"history":hist}
            print(f"[balanced-triangle] {i}/{len(target['cards'])} {row['set_name']} {row['subject_key']} {row['rarity']} rows={len(hist)} credits={provider.credits_charged-start}",flush=True)
        except PkmnPricesAPIError as exc:
            failures.append({"card":row["canonical_card_id"],"error":f"{exc}"})
            if exc.code=="credit_limit_exceeded": break
        except Exception as exc:
            failures.append({"card":row["canonical_card_id"],"error":f"{type(exc).__name__}: {exc}"})
    groups=defaultdict(list)
    for row in target["cards"]: groups[(row["set_name"],row["subject_key"])].append(row)
    subjects=[]
    for (set_name,subject),rows in sorted(groups.items()):
        date_sets=[]
        for row in rows:
            p=panels.get(row["canonical_card_id"])
            date_sets.append(set() if not p else {x["date"] for x in p["history"]})
        shared=len(set.intersection(*date_sets)) if all(date_sets) else 0
        subjects.append({"era_name":ERA_BY_SET[set_name],"set_name":set_name,"subject_key":subject,
                         "shared_all_three_dates":shared,
                         "status":"PANEL_READY_STRONG" if shared>=90 else "PANEL_READY_MODERATE" if shared>=30 else "HISTORY_BLOCKED"})
    counts=defaultdict(int)
    for x in subjects: counts[x["status"]]+=1
    return {"status":"COMPLETE" if not failures else "PARTIAL","version":VERSION,"period":period,
            "target":target,"target_fingerprint":stable_hash(target),"provider_calls":provider.successful_request_count,
            "request_attempt_count":provider.request_attempt_count,"credits_used":provider.credits_charged-start,
            "provider_credit_limit":provider.credits_limit,"provider_rate_remaining":provider.rate_remaining,
            "failures":failures,"panels":panels,"subject_results":subjects,"readiness_counts":dict(counts),
            "all_subjects_ready":all(x["status"]!="HISTORY_BLOCKED" for x in subjects),"production_writes":0}

def main(argv=None):
    p=argparse.ArgumentParser(); p.add_argument("--market-date",default=MARKET_DATE); p.add_argument("--period",default="180d")
    p.add_argument("--credit-cap",type=int,default=25000); p.add_argument("--capture",action="store_true"); p.add_argument("--output",type=Path,required=True)
    a=p.parse_args(argv); load_dotenv(ROOT/"backend/.env",override=False)
    from backend.db.clients.supabase_client import supabase
    target=build_targets(supabase,a.market_date)
    result={"status":"PREFLIGHT_OK","target":target,"target_fingerprint":stable_hash(target),"production_writes":0}
    if a.capture:
        creds=load_pkmnprices_credentials(allow_frontend_fallback=False)
        provider=PkmnPricesClient(creds.api_key,min_request_interval=.55,timeout=10.0,max_retries=0)
        result=capture(provider,target,a.period,a.credit_cap)
    a.output.parent.mkdir(parents=True,exist_ok=True); a.output.write_text(json.dumps(result,indent=2,sort_keys=True,default=str)+"\n",encoding="utf-8")
    print(json.dumps({k:v for k,v in result.items() if k not in {"target","panels","subject_results"}},indent=2,sort_keys=True,default=str))
    return 0 if result["status"] in {"PREFLIGHT_OK","COMPLETE"} else 2
if __name__=="__main__": raise SystemExit(main())
