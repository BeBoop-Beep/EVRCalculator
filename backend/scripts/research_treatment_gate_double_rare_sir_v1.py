"""Research-only gate expansion for Double Rare vs Special Illustration Rare."""
from __future__ import annotations

import argparse, hashlib, json, math, sys
from collections import defaultdict
from pathlib import Path
from typing import Any
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.pricing_pipeline.pkmnprices_client import PkmnPricesAPIError, PkmnPricesClient
from backend.pricing_pipeline.pkmnprices_credentials import load_pkmnprices_credentials
from backend.scripts.research_treatment_panel_recovery_v2 import _history_rows

VERSION = "treatment_gate_expansion_double_rare_sir_v1"
MARKET_DATE = "2026-09-29"
STRONG_DAYS = 90
MODERATE_DAYS = 30
LOW = "Double Rare"
HIGH = "Special Illustration Rare"

TARGETS = {
    "Ascended Heroes": ("pokemon:pokemon:149", "pokemon:pokemon:150"),
    "Phantasmal Flames": ("pokemon:pokemon:6", "pokemon:pokemon:428"),
    "Surging Sparks": ("pokemon:pokemon:635", "pokemon:pokemon:1018"),
    "Twilight Masquerade": ("pokemon:pokemon:658", "pokemon:pokemon:1013"),
}
ERA_BY_SET = {
    "Ascended Heroes": "Mega Evolution",
    "Phantasmal Flames": "Mega Evolution",
    "Surging Sparks": "Scarlet and Violet",
    "Twilight Masquerade": "Scarlet and Violet",
}

def _hash(v: Any) -> str:
    return hashlib.sha256(json.dumps(v, sort_keys=True, separators=(",", ":"), default=str).encode()).hexdigest()

def _number_key(value: Any) -> str:
    text = str(value or "").strip().casefold()
    if "/" in text:
        text = text.split("/", 1)[0]
    text = text.lstrip("0") or "0"
    return str(int(text)) if text.isdigit() else text

def _provider_name_matches(provider_name: Any, target_name: Any) -> bool:
    p = str(provider_name or "").strip().casefold()
    t = str(target_name or "").strip().casefold()
    return bool(t) and (p == t or p.startswith(t + " - "))

def _provider_set_matches(row: dict[str, Any], set_name: str) -> bool:
    observed = str((row.get("set") or {}).get("name") or "").strip().casefold()
    target = set_name.strip().casefold()
    return observed == target or observed.endswith(": " + target)

def _printing_variant(printing_type: Any, special_type: Any) -> str | None:
    if special_type:
        return None
    key = str(printing_type or "").strip().casefold().replace("_", "-")
    return {"holo":"Holofoil","holofoil":"Holofoil","reverse-holo":"Reverse Holofoil","non-holo":"Normal","normal":"Normal"}.get(key)

def _paged(factory):
    out=[]; start=0
    while True:
        page=list(factory().range(start,start+999).execute().data or [])
        out.extend(dict(x) for x in page)
        if len(page)<1000: return out
        start += 1000

def _subject_keys(db, card_ids):
    links=[]
    for i in range(0,len(card_ids),100):
        links.extend(db.table("pokemon_card_collector_entity_links").select(
            "pokemon_canonical_card_id,collector_entity_id,active"
        ).in_("pokemon_canonical_card_id",card_ids[i:i+100]).eq("active",True).execute().data or [])
    eids=sorted({str(x["collector_entity_id"]) for x in links})
    refs={}
    for i in range(0,len(eids),100):
        for row in db.table("pokemon_collector_entity_reference").select(
            "id,entity_type,canonical_key"
        ).in_("id",eids[i:i+100]).execute().data or []:
            refs[str(row["id"])]=dict(row)
    grouped=defaultdict(list)
    for row in links:
        ref=refs.get(str(row["collector_entity_id"]))
        if ref and ref.get("entity_type") in {"pokemon","trainer"}:
            grouped[str(row["pokemon_canonical_card_id"])].append(f'{ref["entity_type"]}:{ref["canonical_key"]}')
    return {cid:" + ".join(sorted(set(vals))) for cid,vals in grouped.items() if vals}

def build_targets(db, market_date: str):
    sets=db.table("sets").select("id,name").in_("name",sorted(TARGETS)).execute().data or []
    set_by_name={str(x["name"]):str(x["id"]) for x in sets}
    if set(set_by_name)!=set(TARGETS): raise RuntimeError("Set resolution incomplete")
    runs=_paged(lambda: db.table("calculation_runs").select("id,target_id,created_at").eq(
        "market_date",market_date).eq("target_type","set").in_("target_id",list(set_by_name.values())).order("created_at",desc=True))
    run_by_set={}
    for row in runs: run_by_set.setdefault(str(row["target_id"]),str(row["id"]))
    cards=_paged(lambda: db.table("pokemon_canonical_cards").select(
        "id,set_id,name,number,printed_number,rarity,pokemon_tcg_api_card_id"
    ).in_("set_id",list(set_by_name.values())).in_("rarity",[LOW,HIGH]))
    card_ids=[str(x["id"]) for x in cards]
    subjects=_subject_keys(db,card_ids)
    identities=_paged(lambda: db.table("pkmnprices_card_identity_v1").select(
        "provider_card_id,canonical_card_id,match_basis,metadata"
    ).in_("canonical_card_id",card_ids))
    identity_by={str(x["canonical_card_id"]):dict(x) for x in identities}
    api_ids=sorted({str(x.get("pokemon_tcg_api_card_id")) for x in cards if x.get("pokemon_tcg_api_card_id")})
    legacy=[]
    for i in range(0,len(api_ids),100):
        legacy.extend(db.table("cards").select("id,pokemon_tcg_api_id,rarity,card_number").in_(
            "pokemon_tcg_api_id",api_ids[i:i+100]).execute().data or [])
    legacy_by_api={str(x["pokemon_tcg_api_id"]):dict(x) for x in legacy}
    selected=[]
    for c in cards:
        set_name=next(n for n,sid in set_by_name.items() if sid==str(c["set_id"]))
        subject=subjects.get(str(c["id"]))
        if subject in TARGETS[set_name]:
            selected.append({**dict(c),"set_name":set_name,"subject_key":subject})
    if len(selected)!=16:
        raise RuntimeError(f"expected 16 cards got {len(selected)}")
    inputs=[]
    for c in selected:
        run_id=run_by_set[str(c["set_id"])]
        identity=identity_by.get(str(c["id"]))
        direct=str((identity or {}).get("metadata",{}).get("card_variant_id") or "")
        legacy_row=legacy_by_api.get(str(c.get("pokemon_tcg_api_card_id") or ""))
        if not legacy_row: raise RuntimeError(f"legacy card missing {c['id']}")
        sim=list(db.table("simulation_input_cards").select(
            "card_variant_id,card_id,card_name,effective_pull_rate"
        ).eq("calculation_run_id",run_id).eq("card_id",str(legacy_row["id"])).execute().data or [])
        if len(sim)!=1: raise RuntimeError(f"simulation variant resolution failed card={c['id']} rows={len(sim)}")
        variant_id=str(sim[0]["card_variant_id"])
        if direct and direct!=variant_id: raise RuntimeError(f"identity variant drift {c['id']}")
        pulls=list(db.table("simulation_card_variant_pull_rates").select(
            "modeled_probability,printing_type,special_type,status"
        ).eq("calculation_run_id",run_id).eq("card_variant_id",variant_id).execute().data or [])
        if len(pulls)!=1 or not pulls[0].get("modeled_probability"): raise RuntimeError(f"pull missing {c['id']}")
        provider_variant=_printing_variant(pulls[0].get("printing_type"),pulls[0].get("special_type"))
        if not provider_variant: raise RuntimeError(f"provider variant unsupported {c['id']}")
        inputs.append({
            "canonical_card_id":str(c["id"]),"set_id":str(c["set_id"]),"set_name":set_name,
            "era_name":ERA_BY_SET[set_name],"subject_key":subject,"card_name":c["name"],
            "number":str(c["number"]),"rarity":c["rarity"],"card_variant_id":variant_id,
            "provider_variant":provider_variant,"modeled_probability":float(pulls[0]["modeled_probability"]),
            "provider_card_id":None if not identity else int(identity["provider_card_id"]),
            "identity_source":None if not identity else str(identity.get("match_basis") or "cached"),
        })
    return {"version":VERSION,"market_date":market_date,"low_treatment":LOW,"high_treatment":HIGH,
            "cards":sorted(inputs,key=lambda x:(x["era_name"],x["set_name"],x["subject_key"],x["rarity"])),
            "fingerprint":_hash(inputs)}

def resolve_provider_id(provider,row):
    if row.get("provider_card_id"): return int(row["provider_card_id"]),"cached"
    rows=provider.cards_by_name_number(name=row["card_name"],number=row["number"],language="English",per_page=100)
    exact=[x for x in rows if _provider_name_matches(x.get("name"),row["card_name"]) and _number_key(x.get("number"))==_number_key(row["number"])]
    if len(exact)>1: exact=[x for x in exact if _provider_set_matches(x,row["set_name"])]
    if len(exact)!=1: raise RuntimeError(f"provider identity count={len(exact)} card={row['canonical_card_id']}")
    return int(exact[0]["id"]),"research_exact_name_number_set"

def capture(provider,target,period,credit_cap):
    start=provider.credits_charged; panels={}; failures=[]
    for row in target["cards"]:
        if provider.credits_charged-start>=credit_cap: break
        try:
            pid,source=resolve_provider_id(provider,row)
            payload=provider.price_history_page(pid,period=period,condition="Near Mint",variant=row["provider_variant"],limit=365,page=1)
            history=_history_rows(payload)
            panels[row["canonical_card_id"]]={"card":{**row,"provider_card_id":pid,"identity_source":source},"history":history}
            print(f"[double-rare-sir] set={row['set_name']} subject={row['subject_key']} rarity={row['rarity']} rows={len(history)} credits={provider.credits_charged-start}",flush=True)
        except Exception as exc:
            failures.append({"canonical_card_id":row["canonical_card_id"],"error":f"{type(exc).__name__}: {exc}"})
            if isinstance(exc,PkmnPricesAPIError) and exc.code=="credit_limit_exceeded": break
    subject_results=[]; grouped=defaultdict(list)
    for row in target["cards"]: grouped[(row["set_name"],row["subject_key"])].append(row)
    for (set_name,subject),rows in sorted(grouped.items()):
        if len(rows)!=2 or {r["rarity"] for r in rows}!={LOW,HIGH}: raise RuntimeError(f"unexpected group {set_name} {subject}")
        a=next(r for r in rows if r["rarity"]==HIGH); b=next(r for r in rows if r["rarity"]==LOW)
        pa=panels.get(a["canonical_card_id"]); pb=panels.get(b["canonical_card_id"]); shared=0
        if pa and pb:
            shared=len({x["date"] for x in pa["history"]}&{x["date"] for x in pb["history"]})
        status="PANEL_READY_STRONG" if shared>=STRONG_DAYS else "PANEL_READY_MODERATE" if shared>=MODERATE_DAYS else "HISTORY_BLOCKED"
        subject_results.append({"era_name":ERA_BY_SET[set_name],"set_name":set_name,"subject_key":subject,"shared_dates":shared,"status":status,
                                "cards":[a["canonical_card_id"],b["canonical_card_id"]]})
    set_results=[]; by_set=defaultdict(list)
    for x in subject_results: by_set[x["set_name"]].append(x)
    for set_name,rows in sorted(by_set.items()):
        ready=[x for x in rows if x["status"] in {"PANEL_READY_STRONG","PANEL_READY_MODERATE"}]
        set_results.append({"era_name":ERA_BY_SET[set_name],"set_name":set_name,"matched_identities":len(rows),"ready_identities":len(ready),
                            "passes_G1_G4":len(ready)>=2 and len({cid for x in ready for cid in x["cards"]})>=4})
    era_results=[]
    for era in ("Mega Evolution","Scarlet and Violet"):
        passing=[x for x in set_results if x["era_name"]==era and x["passes_G1_G4"]]
        era_results.append({"era_name":era,"passing_sets":len(passing),"passes_era_progression":len(passing)>=2})
    return {"status":"COMPLETE" if not failures else "PARTIAL","version":VERSION,"period":period,
            "target":target,"panels":panels,"subject_results":subject_results,"set_results":set_results,"era_results":era_results,
            "cross_era_progression":all(x["passes_era_progression"] for x in era_results),
            "provider_calls":provider.successful_request_count,"request_attempt_count":provider.request_attempt_count,
            "credits_used":provider.credits_charged-start,"provider_credit_limit":provider.credits_limit,
            "provider_rate_remaining":provider.rate_remaining,"failures":failures,"production_writes":0}

def main(argv=None):
    p=argparse.ArgumentParser(); p.add_argument("--market-date",default=MARKET_DATE); p.add_argument("--period",default="180d")
    p.add_argument("--credit-cap",type=int,default=3000); p.add_argument("--capture",action="store_true")
    p.add_argument("--output",type=Path,required=True); args=p.parse_args(argv)
    load_dotenv(ROOT/"backend/.env",override=False)
    from backend.db.clients.supabase_client import supabase
    target=build_targets(supabase,args.market_date)
    result={"status":"PREFLIGHT_OK","target":target,"production_writes":0}
    if args.capture:
        creds=load_pkmnprices_credentials(allow_frontend_fallback=False)
        provider=PkmnPricesClient(creds.api_key,min_request_interval=.55,timeout=10,max_retries=0)
        result=capture(provider,target,args.period,args.credit_cap)
    args.output.parent.mkdir(parents=True,exist_ok=True)
    args.output.write_text(json.dumps(result,indent=2,sort_keys=True,default=str)+"\n",encoding="utf-8")
    print(json.dumps({k:v for k,v in result.items() if k not in {"target","panels"}},indent=2,sort_keys=True,default=str))
    return 0 if result["status"] in {"PREFLIGHT_OK","COMPLETE"} else 2

if __name__=="__main__": raise SystemExit(main())
