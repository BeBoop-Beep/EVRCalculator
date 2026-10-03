"""Research-only Hyper Rare / Ultra Rare / SIR bridge for Scarlet & Violet.

Reuses existing panels when available and fetches only missing exact-NM histories.
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

VERSION="treatment_hyper_sir_ultra_bridge_v1"
MARKET_DATE="2026-09-29"
STRONG_DAYS=90
MODERATE_DAYS=30
TREATMENTS=("Hyper Rare","Ultra Rare","Special Illustration Rare")
TARGETS={
 "Paldea Evolved":("pokemon:pokemon:1002","pokemon:pokemon:1003"),
 "Temporal Forces":("pokemon:pokemon:1009","pokemon:pokemon:1010"),
}

def _hash(v:Any)->str:
    return hashlib.sha256(json.dumps(v,sort_keys=True,separators=(",",":"),default=str).encode()).hexdigest()

def _chunks(vals,size=100):
    for i in range(0,len(vals),size): yield vals[i:i+size]

def build_target(db,market_date):
    sets=list(db.table("sets").select("id,name").in_("name",sorted(TARGETS)).execute().data or [])
    set_by_name={str(x["name"]):str(x["id"]) for x in sets}
    if set(set_by_name)!=set(TARGETS): raise RuntimeError("target Set resolution incomplete")
    runs=list(db.table("calculation_runs").select("id,target_id,created_at").eq("market_date",market_date).eq("target_type","set").in_("target_id",list(set_by_name.values())).order("created_at",desc=True).execute().data or [])
    run_by_set={}
    for x in runs: run_by_set.setdefault(str(x["target_id"]),str(x["id"]))
    if len(run_by_set)!=2: raise RuntimeError("simulation authority incomplete")
    cards=[]
    for chunk in _chunks(list(set_by_name.values())):
        cards.extend(db.table("pokemon_canonical_cards").select(
            "id,set_id,name,number,printed_number,rarity,pokemon_tcg_api_card_id"
        ).in_("set_id",chunk).in_("rarity",list(TREATMENTS)).execute().data or [])
    ids=[str(x["id"]) for x in cards]
    subjects=_subject_keys(db,ids)
    identities=[]
    for chunk in _chunks(ids):
        identities.extend(db.table("pkmnprices_card_identity_v1").select(
            "provider_card_id,canonical_card_id,match_basis,metadata"
        ).in_("canonical_card_id",chunk).execute().data or [])
    idmap={str(x["canonical_card_id"]):dict(x) for x in identities}
    api_ids=sorted({str(x.get("pokemon_tcg_api_card_id")) for x in cards if x.get("pokemon_tcg_api_card_id")})
    legacy=[]
    for chunk in _chunks(api_ids):
        legacy.extend(db.table("cards").select("id,pokemon_tcg_api_id,rarity,card_number").in_("pokemon_tcg_api_id",chunk).execute().data or [])
    legacy_by_api={str(x["pokemon_tcg_api_id"]):dict(x) for x in legacy}
    selected=[]
    for c in cards:
        set_name=next(name for name,sid in set_by_name.items() if sid==str(c["set_id"]))
        subject=subjects.get(str(c["id"]))
        if subject in TARGETS[set_name]: selected.append({**dict(c),"set_name":set_name,"subject_key":subject})
    if len(selected)!=12: raise RuntimeError(f"expected 12 target cards found={len(selected)}")
    out=[]
    for c in selected:
        legacy_row=legacy_by_api.get(str(c.get("pokemon_tcg_api_card_id") or ""))
        if not legacy_row: raise RuntimeError(f"legacy identity missing {c['id']}")
        run_id=run_by_set[str(c["set_id"])]
        sim=list(db.table("simulation_input_cards").select("card_variant_id,card_id,effective_pull_rate").eq("calculation_run_id",run_id).eq("card_id",str(legacy_row["id"])).execute().data or [])
        if len(sim)!=1: raise RuntimeError(f"simulation variant resolution failed {c['id']} rows={len(sim)}")
        vid=str(sim[0]["card_variant_id"])
        pull=list(db.table("simulation_card_variant_pull_rates").select("modeled_probability,printing_type,special_type,status").eq("calculation_run_id",run_id).eq("card_variant_id",vid).execute().data or [])
        if len(pull)!=1 or not pull[0].get("modeled_probability"): raise RuntimeError(f"pull authority missing {c['id']}")
        pv=_printing_variant(pull[0].get("printing_type"),pull[0].get("special_type"))
        if not pv: raise RuntimeError(f"provider variant unsupported {c['id']}")
        ident=idmap.get(str(c["id"]))
        frozen=str((ident or {}).get("metadata",{}).get("card_variant_id") or "")
        if frozen and frozen!=vid: raise RuntimeError(f"variant drift {c['id']}")
        out.append({
          "canonical_card_id":str(c["id"]),"set_id":str(c["set_id"]),"set_name":c["set_name"],
          "era_name":"Scarlet and Violet","subject_key":c["subject_key"],"card_name":c["name"],
          "number":str(c["number"]),"rarity":c["rarity"],"card_variant_id":vid,"provider_variant":pv,
          "modeled_probability":float(pull[0]["modeled_probability"]),
          "provider_card_id":None if not ident else int(ident["provider_card_id"]),
          "identity_source":None if not ident else str(ident.get("match_basis") or "cached"),
        })
    out=sorted(out,key=lambda x:(x["set_name"],x["subject_key"],TREATMENTS.index(x["rarity"])))
    return {"version":VERSION,"market_date":market_date,"cards":out,"fingerprint":_hash(out)}

def resolve_provider(provider,row):
    if row.get("provider_card_id"): return int(row["provider_card_id"]),"cached"
    candidates=provider.cards_by_name_number(name=row["card_name"],number=row["number"],language="English",per_page=100)
    exact=_exact_name_number_matches(candidates,name=row["card_name"],number=row["number"])
    if len(exact)>1: exact=[x for x in exact if _provider_set_matches(x,row["set_name"])]
    if len(exact)!=1: raise RuntimeError(f"provider identity count={len(exact)} {row['set_name']} {row['card_name']} {row['number']}")
    return int(exact[0]["id"]),"research_exact_name_number_set"

def capture(provider,target,base,period,credit_cap):
    existing=dict(base.get("panels") or {})
    panels={}; failures=[]; start=provider.credits_charged
    for row in target["cards"]:
        cid=row["canonical_card_id"]
        if cid in existing: panels[cid]=existing[cid]; continue
        if provider.credits_charged-start>=credit_cap: failures.append({"canonical_card_id":cid,"error":"local_credit_cap"}); break
        try:
            pid,source=resolve_provider(provider,row)
            payload=provider.price_history_page(pid,period=period,condition="Near Mint",variant=row["provider_variant"],limit=365,page=1)
            hist=_history_rows(payload)
            panels[cid]={"card":{**row,"provider_card_id":pid,"identity_source":source},"history":hist}
            print(f"[hyper-bridge] set={row['set_name']} subject={row['subject_key']} rarity={row['rarity']} provider={pid} rows={len(hist)} credits={provider.credits_charged-start}",flush=True)
        except PkmnPricesAPIError as exc:
            failures.append({"canonical_card_id":cid,"error":f"{exc}"})
            if exc.code=="credit_limit_exceeded": break
        except Exception as exc:
            failures.append({"canonical_card_id":cid,"error":f"{type(exc).__name__}: {exc}"})
    readiness=[]; groups=defaultdict(list)
    for row in target["cards"]: groups[(row["set_name"],row["subject_key"])].append(row)
    for (set_name,subject),rows in sorted(groups.items()):
        by={x["rarity"]:x for x in rows}; common=None
        for t in TREATMENTS:
            cid=by[t]["canonical_card_id"]
            if cid not in panels: common=set(); break
            d={x["date"] for x in panels[cid]["history"]}; common=d if common is None else common & d
        shared=len(common or set())
        status="PANEL_READY_STRONG" if shared>=STRONG_DAYS else "PANEL_READY_MODERATE" if shared>=MODERATE_DAYS else "HISTORY_BLOCKED"
        readiness.append({"set_name":set_name,"subject_key":subject,"shared_dates_three_way":shared,"status":status,
                          "cards":{t:by[t]["canonical_card_id"] for t in TREATMENTS}})
    by_set=defaultdict(list)
    for x in readiness: by_set[x["set_name"]].append(x)
    set_results=[]
    for set_name,rows in sorted(by_set.items()):
        ready=[x for x in rows if x["status"]!="HISTORY_BLOCKED"]
        set_results.append({"set_name":set_name,"matched_identities":len(rows),"ready_identities":len(ready),
                            "passes_G1_G4":len(ready)>=2 and len({cid for x in ready for cid in x["cards"].values()})>=6})
    era_pass=sum(x["passes_G1_G4"] for x in set_results)>=2
    return {"status":"COMPLETE" if not failures else "PARTIAL","version":VERSION,"period":period,"target":target,
            "base_artifact_digest":_hash(base),"provider_calls":provider.successful_request_count,"request_attempt_count":provider.request_attempt_count,
            "credits_used":provider.credits_charged-start,"provider_credit_limit":provider.credits_limit,"failures":failures,"panels":panels,
            "readiness":readiness,"set_results":set_results,"era_progression":era_pass,"production_writes":0}

def main(argv=None):
    p=argparse.ArgumentParser(); p.add_argument("--base-artifact",type=Path,required=True); p.add_argument("--market-date",default=MARKET_DATE); p.add_argument("--period",default="180d"); p.add_argument("--credit-cap",type=int,default=3000); p.add_argument("--output",type=Path,required=True)
    a=p.parse_args(argv); load_dotenv(ROOT/"backend/.env",override=False)
    from backend.db.clients.supabase_client import supabase
    base=json.loads(a.base_artifact.read_text(encoding="utf-8"))
    target=build_target(supabase,a.market_date)
    creds=load_pkmnprices_credentials(allow_frontend_fallback=False)
    provider=PkmnPricesClient(creds.api_key,min_request_interval=.55,timeout=10,max_retries=0)
    result=capture(provider,target,base,a.period,a.credit_cap)
    a.output.parent.mkdir(parents=True,exist_ok=True); a.output.write_text(json.dumps(result,indent=2,sort_keys=True,default=str)+"\n",encoding="utf-8")
    print(json.dumps({k:v for k,v in result.items() if k not in {"target","panels"}},indent=2,sort_keys=True,default=str))
    return 0 if result["status"]=="COMPLETE" and result["era_progression"] else 2
if __name__=="__main__": raise SystemExit(main())
