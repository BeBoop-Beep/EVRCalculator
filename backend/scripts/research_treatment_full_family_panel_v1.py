"""Research-only exhaustive matched-treatment panels inside frozen Sets.

Supports frozen family configurations:
- dr-ultra-sir: all eligible identities in Chaos Rising, Mega Evolution,
  Paldea Evolved, and Paradox Rift.
- hyper-ultra-sir: all eligible identities in the eight simulation-supported S&V Sets with >=2 complete Hyper/Ultra/SIR identities.

Reuses one or more prior artifacts and fetches only missing exact-NM histories.
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

CONFIG={
 "dr-ultra-sir":{
   "version":"treatment_full_dr_ultra_sir_v1",
   "sets":["Chaos Rising","Mega Evolution","Paldea Evolved","Paradox Rift"],
   "treatments":["Double Rare","Ultra Rare","Special Illustration Rare"],
   "eras":{"Chaos Rising":"Mega Evolution","Mega Evolution":"Mega Evolution","Paldea Evolved":"Scarlet and Violet","Paradox Rift":"Scarlet and Violet"},
   "era_min_sets":{"Mega Evolution":2,"Scarlet and Violet":2},
 },
 "hyper-ultra-sir":{
   "version":"treatment_full_hyper_ultra_sir_v1",
   "sets":["Paldea Evolved","Temporal Forces","Destined Rivals","Paradox Rift","Journey Together","Scarlet and Violet Base Set","Surging Sparks","Twilight Masquerade"],
   "treatments":["Hyper Rare","Ultra Rare","Special Illustration Rare"],
   "eras":{"Paldea Evolved":"Scarlet and Violet","Temporal Forces":"Scarlet and Violet","Destined Rivals":"Scarlet and Violet","Paradox Rift":"Scarlet and Violet","Journey Together":"Scarlet and Violet","Scarlet and Violet Base Set":"Scarlet and Violet","Surging Sparks":"Scarlet and Violet","Twilight Masquerade":"Scarlet and Violet"},
   "era_min_sets":{"Scarlet and Violet":2},
 },
}

def _hash(v:Any)->str:
    return hashlib.sha256(json.dumps(v,sort_keys=True,separators=(",",":"),default=str).encode()).hexdigest()

def _chunks(vals,size=100):
    for i in range(0,len(vals),size): yield vals[i:i+size]

def build_target(db,market_date,family):
    cfg=CONFIG[family]; set_names=cfg["sets"]; treatments=cfg["treatments"]
    sets=list(db.table("sets").select("id,name").in_("name",set_names).execute().data or [])
    set_by_name={str(x["name"]):str(x["id"]) for x in sets}
    if set(set_by_name)!=set(set_names): raise RuntimeError("target Set resolution incomplete")
    runs=list(db.table("calculation_runs").select("id,target_id,created_at").eq("market_date",market_date).eq("target_type","set").in_("target_id",list(set_by_name.values())).order("created_at",desc=True).execute().data or [])
    run_by_set={}
    for x in runs: run_by_set.setdefault(str(x["target_id"]),str(x["id"]))
    if len(run_by_set)!=len(set_names): raise RuntimeError("simulation authority incomplete")

    cards=[]
    for chunk in _chunks(list(set_by_name.values())):
        cards.extend(db.table("pokemon_canonical_cards").select(
            "id,set_id,name,number,printed_number,rarity,pokemon_tcg_api_card_id"
        ).in_("set_id",chunk).in_("rarity",treatments).execute().data or [])
    ids=[str(x["id"]) for x in cards]; subjects=_subject_keys(db,ids)

    grouped=defaultdict(list)
    for c in cards:
        set_name=next(name for name,sid in set_by_name.items() if sid==str(c["set_id"]))
        subject=subjects.get(str(c["id"]))
        if subject: grouped[(set_name,subject)].append(dict(c))
    eligible={
      key:rows for key,rows in grouped.items()
      if {str(x["rarity"]) for x in rows}==set(treatments) and len(rows)==len(treatments)
    }
    if not eligible: raise RuntimeError("no eligible matched identities")

    target_cards=[c for rows in eligible.values() for c in rows]
    target_ids=[str(x["id"]) for x in target_cards]
    identities=[]
    for chunk in _chunks(target_ids):
        identities.extend(db.table("pkmnprices_card_identity_v1").select(
            "provider_card_id,canonical_card_id,match_basis,metadata"
        ).in_("canonical_card_id",chunk).execute().data or [])
    idmap={str(x["canonical_card_id"]):dict(x) for x in identities}

    api_ids=sorted({str(x.get("pokemon_tcg_api_card_id")) for x in target_cards if x.get("pokemon_tcg_api_card_id")})
    legacy=[]
    for chunk in _chunks(api_ids):
        legacy.extend(db.table("cards").select("id,pokemon_tcg_api_id,rarity,card_number").in_("pokemon_tcg_api_id",chunk).execute().data or [])
    legacy_by_api={str(x["pokemon_tcg_api_id"]):dict(x) for x in legacy}

    out=[]
    for (set_name,subject),rows in eligible.items():
        for c in rows:
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
            ident=idmap.get(str(c["id"])); frozen=str((ident or {}).get("metadata",{}).get("card_variant_id") or "")
            if frozen and frozen!=vid: raise RuntimeError(f"variant drift {c['id']}")
            out.append({
              "canonical_card_id":str(c["id"]),"set_id":str(c["set_id"]),"set_name":set_name,
              "era_name":cfg["eras"][set_name],"subject_key":subject,"card_name":c["name"],"number":str(c["number"]),
              "rarity":c["rarity"],"card_variant_id":vid,"provider_variant":pv,
              "modeled_probability":float(pull[0]["modeled_probability"]),
              "provider_card_id":None if not ident else int(ident["provider_card_id"]),
              "identity_source":None if not ident else str(ident.get("match_basis") or "cached"),
            })
    order={t:i for i,t in enumerate(treatments)}
    out=sorted(out,key=lambda x:(x["era_name"],x["set_name"],x["subject_key"],order[x["rarity"]]))
    counts=defaultdict(int)
    for x in out: counts[x["set_name"]]+=1
    return {"family":family,"version":cfg["version"],"market_date":market_date,"treatments":treatments,"cards":out,
            "identity_count":len(eligible),"card_count":len(out),"set_card_counts":dict(counts),"fingerprint":_hash(out)}

def resolve_provider(provider,row):
    if row.get("provider_card_id"): return int(row["provider_card_id"]),"cached"
    candidates=provider.cards_by_name_number(name=row["card_name"],number=row["number"],language="English",per_page=100)
    exact=_exact_name_number_matches(candidates,name=row["card_name"],number=row["number"])
    if len(exact)>1: exact=[x for x in exact if _provider_set_matches(x,row["set_name"])]
    if len(exact)!=1: raise RuntimeError(f"provider identity count={len(exact)} {row['set_name']} {row['card_name']} {row['number']}")
    return int(exact[0]["id"]),"research_exact_name_number_set"

def merge_panels(paths):
    panels={}
    digests=[]
    for p in paths:
        obj=json.loads(p.read_text(encoding="utf-8")); digests.append(_hash(obj))
        for cid,panel in dict(obj.get("panels") or {}).items():
            panels.setdefault(str(cid),panel)
    return panels,digests

def capture(provider,target,base_panels,base_digests,period,credit_cap):
    treatments=list(target["treatments"]); panels={}; failures=[]; reused=0; fetched=0; start=provider.credits_charged
    for row in target["cards"]:
        cid=row["canonical_card_id"]
        if cid in base_panels:
            panels[cid]=base_panels[cid]; reused+=1; continue
        if provider.credits_charged-start>=credit_cap: failures.append({"canonical_card_id":cid,"error":"local_credit_cap"}); break
        try:
            pid,source=resolve_provider(provider,row)
            payload=provider.price_history_page(pid,period=period,condition="Near Mint",variant=row["provider_variant"],limit=365,page=1)
            hist=_history_rows(payload); fetched+=1
            panels[cid]={"card":{**row,"provider_card_id":pid,"identity_source":source},"history":hist}
            print(f"[full-family] family={target['family']} set={row['set_name']} subject={row['subject_key']} rarity={row['rarity']} rows={len(hist)} credits={provider.credits_charged-start}",flush=True)
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
        for t in treatments:
            cid=by[t]["canonical_card_id"]
            if cid not in panels: common=set(); break
            d={x["date"] for x in panels[cid]["history"]}; common=d if common is None else common&d
        shared=len(common or set())
        status="PANEL_READY_STRONG" if shared>=STRONG_DAYS else "PANEL_READY_MODERATE" if shared>=MODERATE_DAYS else "HISTORY_BLOCKED"
        readiness.append({"era_name":rows[0]["era_name"],"set_name":set_name,"subject_key":subject,"shared_dates_all":shared,"status":status,
                          "cards":{t:by[t]["canonical_card_id"] for t in treatments}})
    by_set=defaultdict(list)
    for x in readiness: by_set[x["set_name"]].append(x)
    set_results=[]
    for set_name,rows in sorted(by_set.items()):
        ready=[x for x in rows if x["status"]!="HISTORY_BLOCKED"]
        set_results.append({"era_name":rows[0]["era_name"],"set_name":set_name,"identity_count":len(rows),"ready_identities":len(ready),
                            "passes_G1_G4":len(ready)>=2 and len({cid for x in ready for cid in x["cards"].values()})>=2*len(treatments)})
    cfg=CONFIG[target["family"]]; era_results=[]
    for era,min_sets in cfg["era_min_sets"].items():
        rows=[x for x in set_results if x["era_name"]==era]; passing=[x for x in rows if x["passes_G1_G4"]]
        era_results.append({"era_name":era,"target_sets":len(rows),"passing_sets":len(passing),"required_sets":min_sets,"passes":len(passing)>=min_sets})
    return {"status":"COMPLETE" if not failures else "PARTIAL","family":target["family"],"version":target["version"],"period":period,
            "target":target,"base_artifact_digests":base_digests,"reused_panels":reused,"fetched_panels":fetched,
            "provider_calls":provider.successful_request_count,"request_attempt_count":provider.request_attempt_count,
            "credits_used":provider.credits_charged-start,"provider_credit_limit":provider.credits_limit,"failures":failures,
            "panels":panels,"readiness":readiness,"set_results":set_results,"era_results":era_results,
            "progression_pass":all(x["passes"] for x in era_results),"production_writes":0}

def main(argv=None):
    p=argparse.ArgumentParser(); p.add_argument("--family",choices=sorted(CONFIG),required=True); p.add_argument("--base-artifact",type=Path,action="append",default=[]); p.add_argument("--market-date",default=MARKET_DATE); p.add_argument("--period",default="180d"); p.add_argument("--credit-cap",type=int,default=15000); p.add_argument("--output",type=Path,required=True)
    a=p.parse_args(argv); load_dotenv(ROOT/"backend/.env",override=False)
    from backend.db.clients.supabase_client import supabase
    target=build_target(supabase,a.market_date,a.family); base,digests=merge_panels(a.base_artifact)
    creds=load_pkmnprices_credentials(allow_frontend_fallback=False); provider=PkmnPricesClient(creds.api_key,min_request_interval=.55,timeout=10,max_retries=0)
    result=capture(provider,target,base,digests,a.period,a.credit_cap)
    a.output.parent.mkdir(parents=True,exist_ok=True); a.output.write_text(json.dumps(result,indent=2,sort_keys=True,default=str)+"\n",encoding="utf-8")
    print(json.dumps({k:v for k,v in result.items() if k not in {"target","panels","readiness"}},indent=2,sort_keys=True,default=str))
    return 0 if result["status"]=="COMPLETE" and result["progression_pass"] else 2
if __name__=="__main__": raise SystemExit(main())
