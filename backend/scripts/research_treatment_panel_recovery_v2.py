"""Research-only recovery of exact NM treatment panels from PkmnPrices history.

No production price or Collector authority is mutated. Output is local JSON only.
"""
from __future__ import annotations

import argparse, hashlib, json, os, re
from collections import defaultdict
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Any

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[2]
import sys
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.pricing_pipeline.pkmnprices_client import PkmnPricesClient
from backend.pricing_pipeline.pkmnprices_credentials import load_pkmnprices_credentials
from backend.desirability.treatment_market_prestige_v3 import normalize_label

VERSION = "treatment_panel_recovery_pkmnprices_nm_v1"
DEFAULT_MARKET_DATE = "2026-09-29"
STRONG_DAYS = 90
MODERATE_DAYS = 30

def _hash(value: Any) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"), default=str).encode()).hexdigest()

def _paged(q):
    rows=[]; start=0
    while True:
        part=q().range(start,start+999).execute().data or []
        rows.extend(part)
        if len(part)<1000: return rows
        start += 1000

def _provider_variant(row: dict[str, Any]) -> str | None:
    if row.get("special_type"):
        return None
    printing = str(row.get("printing_type") or "").strip().lower().replace("_","-")
    finish = {"holo":"Holofoil","reverse-holo":"Reverse Holofoil","reverse_holo":"Reverse Holofoil",
              "non-holo":"Normal","non_holo":"Normal","normal":"Normal"}.get(printing)
    if not finish:
        return None
    edition = str(row.get("edition") or "").strip().lower().replace("_","-")
    prefix = {"1st-edition":"1st Edition ","first-edition":"1st Edition ",
              "unlimited":"Unlimited ","shadowless":"Shadowless "}.get(edition,"")
    return prefix + finish

def _subject_keys(db, card_ids: list[str], cards: dict[str,dict]) -> dict[str,str]:
    links=[]
    for i in range(0,len(card_ids),100):
        chunk=card_ids[i:i+100]
        links += list(db.table("pokemon_card_collector_entity_links").select(
            "pokemon_canonical_card_id,collector_entity_id,link_role,active"
        ).in_("pokemon_canonical_card_id",chunk).eq("active",True).execute().data or [])
    entity_ids=sorted({str(x["collector_entity_id"]) for x in links})
    refs={}
    for i in range(0,len(entity_ids),100):
        chunk=entity_ids[i:i+100]
        for row in list(db.table("pokemon_collector_entity_reference").select(
            "id,entity_type,canonical_key"
        ).in_("id",chunk).execute().data or []):
            refs[str(row["id"])]=row
    by_card=defaultdict(list)
    for row in links:
        ref=refs.get(str(row["collector_entity_id"]))
        if ref and ref.get("entity_type") in {"pokemon","trainer"}:
            by_card[str(row["pokemon_canonical_card_id"])].append(
                f'{ref["entity_type"]}:{ref["canonical_key"]}'
            )
    out={}
    for cid in card_ids:
        keys=sorted(set(by_card.get(cid,[])))
        if keys: out[cid]=" + ".join(keys)
        else:
            c=cards[cid]
            dex=c.get("national_pokedex_numbers") or []
            if dex: out[cid]="pokemon_dex:"+"+".join(map(str,dex))
            elif str(c.get("supertype") or "").casefold()=="trainer":
                out[cid]="trainer_name:"+re.sub(r"\s+"," ",str(c.get("name") or "").strip().casefold())
    return out

def build_cohort(db, *, market_date: str) -> dict[str,Any]:
    run_rows=_paged(lambda: db.table("calculation_runs").select(
        "id,target_id,target_type,market_date"
    ).eq("market_date",market_date).eq("target_type","set"))
    latest={}
    for row in run_rows: latest[str(row["target_id"])]=str(row["id"])
    set_ids=sorted(latest)
    identities=_paged(lambda: db.table("pkmnprices_card_identity_v1").select(
        "provider_card_id,canonical_card_id,tcgplayer_product_id,match_basis,metadata"
    ))
    mapped={str(x["canonical_card_id"]):x for x in identities}
    card_rows=[]
    for i in range(0,len(mapped),100):
        chunk=list(mapped)[i:i+100]
        card_rows += list(db.table("pokemon_canonical_cards").select(
            "id,set_id,name,supertype,rarity,artist,national_pokedex_numbers"
        ).in_("id",chunk).in_("set_id",set_ids).execute().data or [])
    cards={str(x["id"]):x for x in card_rows}
    card_ids=sorted(cards)
    subjects=_subject_keys(db,card_ids,cards)

    legacy_links=[]
    for i in range(0,len(card_ids),100):
        legacy_links += list(db.table("pokemon_canonical_card_legacy_identity_links").select(
            "canonical_card_id,legacy_card_id"
        ).in_("canonical_card_id",card_ids[i:i+100]).execute().data or [])
    legacy_to_canonical={str(x["legacy_card_id"]):str(x["canonical_card_id"]) for x in legacy_links}
    variants=[]
    legacy_ids=sorted(legacy_to_canonical)
    for i in range(0,len(legacy_ids),100):
        variants += list(db.table("card_variants").select(
            "id,card_id,printing_type,special_type,edition"
        ).in_("card_id",legacy_ids[i:i+100]).execute().data or [])
    by_card=defaultdict(list)
    for v in variants:
        cid=legacy_to_canonical.get(str(v["card_id"]))
        if cid: by_card[cid].append(v)

    pull={}
    for set_id,run_id in latest.items():
        for row in _paged(lambda run_id=run_id: db.table("simulation_card_variant_pull_rates").select(
            "card_variant_id,modeled_probability,effective_pull_rate,status"
        ).eq("calculation_run_id",run_id)):
            pull[str(row["card_variant_id"])]=row

    rows=[]; exclusions=[]
    for cid,c in cards.items():
        identity=mapped[cid]
        requested=str((identity.get("metadata") or {}).get("card_variant_id") or "")
        candidates=by_card.get(cid,[])
        selected=next((v for v in candidates if str(v["id"])==requested),None) if requested else None
        if selected is None:
            safe=[v for v in candidates if _provider_variant(v)]
            if len(safe)==1: selected=safe[0]
        subject=subjects.get(cid)
        treatment=normalize_label(c.get("rarity")) or "__unmapped__"
        if not subject or selected is None:
            exclusions.append({"canonical_card_id":cid,"reason":"subject_or_exact_variant_unresolved"})
            continue
        provider_variant=_provider_variant(selected)
        if not provider_variant:
            exclusions.append({"canonical_card_id":cid,"reason":"provider_variant_unresolved"})
            continue
        pr=pull.get(str(selected["id"]))
        rows.append({
            "canonical_card_id":cid,"provider_card_id":int(identity["provider_card_id"]),
            "set_id":str(c["set_id"]),"card_name":c.get("name"),"subject_key":subject,
            "treatment":treatment,"raw_rarity":c.get("rarity"),"card_variant_id":str(selected["id"]),
            "provider_variant":provider_variant,"condition":"Near Mint",
            "modeled_probability":None if not pr else pr.get("modeled_probability"),
            "pull_rate_status":None if not pr else pr.get("status"),
            "match_basis":identity.get("match_basis"),
        })
    grouped=defaultdict(list)
    for row in rows: grouped[(row["set_id"],row["subject_key"])].append(row)
    ladders=[]
    for (set_id,subject),group in grouped.items():
        treatments=sorted({x["treatment"] for x in group})
        if len(treatments)<2: continue
        ladders.append({"set_id":set_id,"subject_key":subject,"treatments":treatments,
                        "cards":sorted(group,key=lambda x:(x["treatment"],x["canonical_card_id"]))})
    eligible_ids={x["canonical_card_id"] for l in ladders for x in l["cards"]}
    return {
        "version":VERSION,"market_date":market_date,
        "counts":{"simulation_sets":len(set_ids),"mapped_cards_in_sets":len(cards),
                  "safe_cards":len(rows),"matched_ladders":len(ladders),
                  "matched_cards":len(eligible_ids),"excluded":len(exclusions)},
        "ladders":sorted(ladders,key=lambda x:(x["set_id"],x["subject_key"])),
        "exclusions":exclusions,
    }

def _sold_job_active(db) -> bool:
    cutoff=(datetime.now(timezone.utc)-timedelta(minutes=20)).isoformat()
    rows=list(db.table("pkmnprices_sold_runs_v1").select("run_id,status,started_at")
              .eq("status","RUNNING").gte("started_at",cutoff).limit(1).execute().data or [])
    return bool(rows)

def _history_rows(payload: dict[str,Any]) -> list[dict[str,Any]]:
    rows=payload.get("data") or payload.get("prices") or payload.get("history") or []
    if not isinstance(rows,list): return []
    out=[]
    for row in rows:
        if not isinstance(row,dict): continue
        day=str(row.get("date") or row.get("day") or row.get("captured_at") or row.get("captured_date") or "")[:10]
        if not day: continue
        value=row.get("avg")
        if value is None: value=row.get("market_price",row.get("price"))
        try: value=float(value)
        except (TypeError,ValueError): continue
        if value>0: out.append({"date":day,"price":value})
    return out

def collect(db, provider, cohort, *, period: str, max_cards: int, credit_cap: int) -> dict[str,Any]:
    if _sold_job_active(db):
        return {"status":"BLOCKED_SOLD_JOB_ACTIVE","provider_calls":0,"credits_used":0}
    cards=[]
    seen=set()
    for ladder in cohort["ladders"]:
        for row in ladder["cards"]:
            if row["canonical_card_id"] not in seen:
                seen.add(row["canonical_card_id"]); cards.append(row)
    cards=cards[:max_cards] if max_cards else cards
    panels={}
    failures=[]
    start=provider.credits_charged
    for row in cards:
        if provider.credits_charged-start >= credit_cap: break
        try:
            payload=provider.price_history_page(
                row["provider_card_id"],period=period,condition="Near Mint",
                variant=row["provider_variant"],limit=365,page=1)
            panels[row["canonical_card_id"]]={"card":row,"history":_history_rows(payload)}
        except Exception as exc:
            failures.append({"canonical_card_id":row["canonical_card_id"],"error":f"{type(exc).__name__}: {exc}"})
    readiness=[]
    for ladder in cohort["ladders"]:
        ids=[x["canonical_card_id"] for x in ladder["cards"] if x["canonical_card_id"] in panels]
        if len(ids)<2: continue
        for i,a in enumerate(ids):
            da={x["date"] for x in panels[a]["history"]}
            for b in ids[i+1:]:
                dbb={x["date"] for x in panels[b]["history"]}
                shared=len(da&dbb)
                readiness.append({"set_id":ladder["set_id"],"subject_key":ladder["subject_key"],
                    "card_a":a,"card_b":b,"treatment_a":panels[a]["card"]["treatment"],
                    "treatment_b":panels[b]["card"]["treatment"],"shared_dates":shared,
                    "status":"PANEL_READY_STRONG" if shared>=STRONG_DAYS else "PANEL_READY_MODERATE" if shared>=MODERATE_DAYS else "HISTORY_BLOCKED"})
    counts=defaultdict(int)
    for x in readiness: counts[x["status"]]+=1
    return {"status":"COMPLETE","version":VERSION,"period":period,
        "provider_calls":len(panels)+len(failures),"credits_used":provider.credits_charged-start,
        "cards_requested":len(cards),"cards_returned":len(panels),"failures":failures,
        "panels":panels,"readiness":readiness,"readiness_counts":dict(counts)}

def main(argv=None):
    p=argparse.ArgumentParser()
    p.add_argument("--market-date",default=DEFAULT_MARKET_DATE)
    p.add_argument("--period",default="180d")
    p.add_argument("--max-cards",type=int,default=0)
    p.add_argument("--credit-cap",type=int,default=5000)
    p.add_argument("--collect",action="store_true")
    p.add_argument("--output",type=Path,default=ROOT/"backend/artifacts/treatment_panel_recovery_v2/result.json")
    args=p.parse_args(argv)
    load_dotenv(ROOT/"backend/.env",override=False)
    from backend.db.clients.supabase_client import supabase
    cohort=build_cohort(supabase,market_date=args.market_date)
    result={"status":"PREFLIGHT_OK","cohort":cohort,"cohort_fingerprint":_hash(cohort),
            "provider_calls":0,"credits_used":0,"production_writes":0}
    if args.collect:
        creds=load_pkmnprices_credentials(allow_frontend_fallback=False)
        provider=PkmnPricesClient(creds.api_key,min_request_interval=.55)
        result={**result,**collect(supabase,provider,cohort,period=args.period,max_cards=args.max_cards,credit_cap=args.credit_cap)}
        result["production_writes"]=0
    args.output.parent.mkdir(parents=True,exist_ok=True)
    args.output.write_text(json.dumps(result,indent=2,sort_keys=True,default=str)+"\n",encoding="utf-8")
    print(json.dumps({k:v for k,v in result.items() if k not in {"cohort","panels"}},indent=2,default=str))
    return 3 if str(result["status"]).startswith("BLOCKED") else 0

if __name__=="__main__": raise SystemExit(main())
