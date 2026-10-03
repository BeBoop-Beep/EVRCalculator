"""Confirmatory independent panel capture for Joint Treatment Ladder V1.

Research only. Selects the preregistered 21 independent complete
Double Rare / Ultra Rare / Special Illustration Rare triads from five frozen
Sets, excluding all discovery clusters. Resolves PkmnPrices identities in-memory,
captures exact Near-Mint daily history, and writes a local JSON artifact only.
"""
from __future__ import annotations

import argparse, hashlib, json, sys
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

VERSION = "joint_treatment_ladder_v1_replication_panel_v1"
MARKET_DATE = "2026-09-29"
TREATMENTS = {"double rare", "ultra rare", "special illustration rare"}
FROZEN_SETS = {
    "Perfect Order": "Mega Evolution",
    "Phantasmal Flames": "Mega Evolution",
    "Scarlet and Violet 151": "Scarlet and Violet",
    "Twilight Masquerade": "Scarlet and Violet",
    "Obsidian Flames": "Scarlet and Violet",
}
DISCOVERY = {
    ("Chaos Rising", "pokemon:pokemon:573"),
    ("Chaos Rising", "pokemon:pokemon:658"),
    ("Mega Evolution", "pokemon:pokemon:282"),
    ("Mega Evolution", "pokemon:pokemon:448"),
    ("Paldea Evolved", "pokemon:pokemon:931"),
    ("Paldea Evolved", "pokemon:pokemon:959"),
    ("Paldea Evolved", "pokemon:pokemon:1002"),
    ("Paradox Rift", "pokemon:pokemon:334"),
    ("Paradox Rift", "pokemon:pokemon:445"),
}
EXPECTED_BY_SET = {
    "Perfect Order": 4,
    "Phantasmal Flames": 4,
    "Scarlet and Violet 151": 5,
    "Twilight Masquerade": 4,
    "Obsidian Flames": 4,
}
STRONG_DAYS = 90
MODERATE_DAYS = 30


def stable_hash(value: Any) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"), default=str).encode()).hexdigest()


def _paged(query_factory):
    rows=[]; start=0
    while True:
        part=list(query_factory().range(start,start+999).execute().data or [])
        rows.extend(dict(x) for x in part)
        if len(part)<1000: return rows
        start += 1000


def _number_key(value: Any) -> str:
    text=str(value or "").strip().casefold()
    if "/" in text: text=text.split("/",1)[0]
    text=text.lstrip("0") or "0"
    return str(int(text)) if text.isdigit() else text


def _provider_name_matches(provider_name: Any, target_name: Any) -> bool:
    provider=str(provider_name or "").strip().casefold()
    target=str(target_name or "").strip().casefold()
    return bool(target) and (provider==target or provider.startswith(target+" - "))


def _provider_set_matches(row: dict[str,Any], set_name: str) -> bool:
    observed=str((row.get("set") or {}).get("name") or "").strip().casefold()
    target=set_name.strip().casefold()
    return observed==target or observed.endswith(": "+target)


def _provider_variant(printing_type: Any, special_type: Any) -> str | None:
    if special_type:
        return None
    key=str(printing_type or "").strip().casefold().replace("_","-")
    return {
        "holo":"Holofoil","holofoil":"Holofoil",
        "reverse-holo":"Reverse Holofoil",
        "non-holo":"Normal","normal":"Normal",
    }.get(key)


def _subject_keys(db: Any, card_ids: list[str]) -> dict[str,str]:
    links=[]
    for i in range(0,len(card_ids),100):
        links += list(db.table("pokemon_card_collector_entity_links").select(
            "pokemon_canonical_card_id,collector_entity_id,active"
        ).in_("pokemon_canonical_card_id",card_ids[i:i+100]).eq("active",True).execute().data or [])
    entity_ids=sorted({str(x["collector_entity_id"]) for x in links})
    refs={}
    for i in range(0,len(entity_ids),100):
        rows=db.table("pokemon_collector_entity_reference").select(
            "id,entity_type,canonical_key"
        ).in_("id",entity_ids[i:i+100]).execute().data or []
        refs.update({str(x["id"]):dict(x) for x in rows})
    grouped=defaultdict(list)
    for row in links:
        ref=refs.get(str(row["collector_entity_id"]))
        if ref and ref.get("entity_type") in {"pokemon","trainer"}:
            grouped[str(row["pokemon_canonical_card_id"])].append(
                f'{ref["entity_type"]}:{ref["canonical_key"]}'
            )
    return {cid:" + ".join(sorted(set(vals))) for cid,vals in grouped.items() if vals}


def build_target(db: Any, market_date: str) -> dict[str,Any]:
    set_rows=db.table("sets").select("id,name").in_("name",sorted(FROZEN_SETS)).execute().data or []
    set_by_name={str(x["name"]):str(x["id"]) for x in set_rows}
    if set(set_by_name)!=set(FROZEN_SETS):
        raise RuntimeError("frozen Set resolution mismatch")
    name_by_set={v:k for k,v in set_by_name.items()}

    runs=_paged(lambda: db.table("calculation_runs").select(
        "id,target_id,created_at"
    ).eq("market_date",market_date).eq("target_type","set").in_(
        "target_id",list(set_by_name.values())
    ).order("created_at",desc=True))
    run_by_set={}
    for row in runs:
        run_by_set.setdefault(str(row["target_id"]),str(row["id"]))
    if len(run_by_set)!=5:
        raise RuntimeError("simulation authority missing")

    cards=_paged(lambda: db.table("pokemon_canonical_cards").select(
        "id,set_id,name,number,printed_number,rarity,pokemon_tcg_api_card_id"
    ).in_("set_id",list(set_by_name.values())))
    cards=[x for x in cards if str(x.get("rarity") or "").casefold() in TREATMENTS]
    subjects=_subject_keys(db,[str(x["id"]) for x in cards])
    for card in cards:
        card["subject_key"]=subjects.get(str(card["id"]))
        card["set_name"]=name_by_set[str(card["set_id"])]

    grouped=defaultdict(list)
    for card in cards:
        if card["subject_key"] and (card["set_name"],card["subject_key"]) not in DISCOVERY:
            grouped[(card["set_name"],card["subject_key"])].append(card)

    triads=[]
    for (set_name,subject_key), group in grouped.items():
        by_rarity={str(x["rarity"]).casefold():x for x in group}
        if set(by_rarity)==TREATMENTS:
            triads.append({
                "set_name":set_name,
                "era_name":FROZEN_SETS[set_name],
                "subject_key":subject_key,
                "cards":[by_rarity[k] for k in sorted(TREATMENTS)],
            })
    triads=sorted(triads,key=lambda x:(x["era_name"],x["set_name"],x["subject_key"]))
    observed=defaultdict(int)
    for triad in triads: observed[triad["set_name"]]+=1
    if dict(observed)!=EXPECTED_BY_SET or len(triads)!=21:
        raise RuntimeError(f"frozen triad count mismatch observed={dict(observed)}")

    target_cards=[card for triad in triads for card in triad["cards"]]
    identities=_paged(lambda: db.table("pkmnprices_card_identity_v1").select(
        "provider_card_id,canonical_card_id,match_basis,metadata"
    ).in_("canonical_card_id",[str(x["id"]) for x in target_cards]))
    identity_by_card={str(x["canonical_card_id"]):x for x in identities}

    api_ids=sorted({str(x["pokemon_tcg_api_card_id"]) for x in target_cards if x.get("pokemon_tcg_api_card_id")})
    legacy=[]
    for i in range(0,len(api_ids),100):
        legacy += list(db.table("cards").select(
            "id,pokemon_tcg_api_id,rarity,card_number"
        ).in_("pokemon_tcg_api_id",api_ids[i:i+100]).execute().data or [])
    legacy_by_api={str(x["pokemon_tcg_api_id"]):dict(x) for x in legacy}

    final=[]
    for triad in triads:
        out_cards=[]
        for card in triad["cards"]:
            run_id=run_by_set[str(card["set_id"])]
            legacy_row=legacy_by_api.get(str(card.get("pokemon_tcg_api_card_id") or ""))
            if not legacy_row:
                raise RuntimeError(f"legacy identity missing card={card['id']}")
            sim=list(db.table("simulation_input_cards").select(
                "card_variant_id,card_id,card_name,effective_pull_rate"
            ).eq("calculation_run_id",run_id).eq("card_id",str(legacy_row["id"])).execute().data or [])
            if len(sim)!=1:
                raise RuntimeError(f"simulation variant resolution failed card={card['id']} rows={len(sim)}")
            variant_id=str(sim[0]["card_variant_id"])
            pulls=list(db.table("simulation_card_variant_pull_rates").select(
                "modeled_probability,printing_type,special_type,status"
            ).eq("calculation_run_id",run_id).eq("card_variant_id",variant_id).execute().data or [])
            if len(pulls)!=1 or not pulls[0].get("modeled_probability"):
                raise RuntimeError(f"pull authority missing card={card['id']}")
            provider_variant=_provider_variant(pulls[0].get("printing_type"),pulls[0].get("special_type"))
            if not provider_variant:
                raise RuntimeError(f"provider variant unsupported card={card['id']}")
            identity=identity_by_card.get(str(card["id"]))
            frozen_variant=str((identity or {}).get("metadata",{}).get("card_variant_id") or "")
            if frozen_variant and frozen_variant!=variant_id:
                raise RuntimeError(f"cached variant drift card={card['id']}")
            out_cards.append({
                "canonical_card_id":str(card["id"]),
                "set_id":str(card["set_id"]),
                "set_name":triad["set_name"],
                "era_name":triad["era_name"],
                "subject_key":triad["subject_key"],
                "card_name":card["name"],
                "number":str(card["number"]),
                "rarity":card["rarity"],
                "card_variant_id":variant_id,
                "provider_variant":provider_variant,
                "modeled_probability":float(pulls[0]["modeled_probability"]),
                "provider_card_id":None if not identity else int(identity["provider_card_id"]),
                "identity_source":None if not identity else str(identity.get("match_basis") or "cached"),
            })
        final.append({**{k:v for k,v in triad.items() if k!="cards"},"cards":out_cards})

    return {
        "version":VERSION,"market_date":market_date,
        "triad_count":len(final),"card_count":sum(len(x["cards"]) for x in final),
        "by_set":dict(observed),"triads":final,
        "fingerprint":stable_hash(final),
    }


def resolve_provider_id(provider: PkmnPricesClient, row: dict[str,Any]) -> tuple[int,str]:
    if row.get("provider_card_id"):
        return int(row["provider_card_id"]),"cached"
    candidates=provider.cards_by_name_number(
        name=row["card_name"],number=row["number"],language="English",per_page=100
    )
    exact=[x for x in candidates if _provider_name_matches(x.get("name"),row["card_name"])
           and _number_key(x.get("number"))==_number_key(row["number"])]
    if len(exact)>1:
        exact=[x for x in exact if _provider_set_matches(x,row["set_name"])]
    if len(exact)!=1:
        raise RuntimeError(
            f"provider identity count={len(exact)} card={row['canonical_card_id']} "
            f"name={row['card_name']} number={row['number']} set={row['set_name']}"
        )
    return int(exact[0]["id"]),"research_exact_name_number_set"


def capture(provider: PkmnPricesClient,target:dict[str,Any],period:str,credit_cap:int)->dict[str,Any]:
    start=provider.credits_charged
    panels={}; failures=[]
    for triad in target["triads"]:
        for row in triad["cards"]:
            if provider.credits_charged-start>=credit_cap:
                failures.append({"card":row["canonical_card_id"],"error":"local_credit_cap"})
                break
            try:
                pid,source=resolve_provider_id(provider,row)
                payload=provider.price_history_page(
                    pid,period=period,condition="Near Mint",
                    variant=row["provider_variant"],limit=365,page=1
                )
                history=_history_rows(payload)
                panels[row["canonical_card_id"]]={
                    "card":{**row,"provider_card_id":pid,"identity_source":source},
                    "history":history,
                }
                print(
                    f"[replication-panel] set={row['set_name']} subject={row['subject_key']} "
                    f"rarity={row['rarity']} provider={pid} rows={len(history)} "
                    f"credits={provider.credits_charged-start}",flush=True
                )
            except PkmnPricesAPIError as exc:
                failures.append({"card":row["canonical_card_id"],"error":str(exc)})
                if exc.code=="credit_limit_exceeded": break
            except Exception as exc:
                failures.append({"card":row["canonical_card_id"],"error":f"{type(exc).__name__}: {exc}"})
        if failures and failures[-1].get("error") in {"local_credit_cap"}:
            break

    triad_results=[]
    for triad in target["triads"]:
        cards={str(x["rarity"]).casefold():x for x in triad["cards"]}
        edges=[]
        labels=["double rare","ultra rare","special illustration rare"]
        for i,a in enumerate(labels):
            for b in labels[i+1:]:
                ca,cb=cards[a],cards[b]
                pa=panels.get(ca["canonical_card_id"]); pb=panels.get(cb["canonical_card_id"])
                shared=0
                if pa and pb:
                    shared=len({x["date"] for x in pa["history"]}&{x["date"] for x in pb["history"]})
                status="STRONG" if shared>=STRONG_DAYS else "MODERATE" if shared>=MODERATE_DAYS else "BLOCKED"
                edges.append({"a":a,"b":b,"shared_dates":shared,"status":status})
        ready=all(x["status"] in {"STRONG","MODERATE"} for x in edges)
        triad_results.append({
            "set_name":triad["set_name"],"era_name":triad["era_name"],
            "subject_key":triad["subject_key"],"edges":edges,"ready":ready
        })

    ready=[x for x in triad_results if x["ready"]]
    mega=sum(x["ready"] and x["era_name"]=="Mega Evolution" for x in triad_results)
    sv=sum(x["ready"] and x["era_name"]=="Scarlet and Violet" for x in triad_results)
    coverage_pass=len(ready)>=16 and mega>=6 and sv>=8
    return {
        "status":"COMPLETE" if not failures else "PARTIAL",
        "version":VERSION,"period":period,
        "provider_calls":provider.successful_request_count,
        "request_attempt_count":provider.request_attempt_count,
        "credits_used":provider.credits_charged-start,
        "provider_credit_limit":provider.credits_limit,
        "provider_rate_remaining":provider.rate_remaining,
        "failures":failures,"target":target,"panels":panels,
        "triad_results":triad_results,
        "coverage":{"ready_triads":len(ready),"mega_ready":mega,"sv_ready":sv,
                    "coverage_pass":coverage_pass},
        "production_writes":0,
    }


def main(argv=None):
    p=argparse.ArgumentParser()
    p.add_argument("--market-date",default=MARKET_DATE)
    p.add_argument("--period",default="180d")
    p.add_argument("--credit-cap",type=int,default=8000)
    p.add_argument("--capture",action="store_true")
    p.add_argument("--output",type=Path,required=True)
    args=p.parse_args(argv)
    load_dotenv(ROOT/"backend/.env",override=False)
    from backend.db.clients.supabase_client import supabase
    target=build_target(supabase,args.market_date)
    result={"status":"PREFLIGHT_OK","target":target,"production_writes":0}
    if args.capture:
        creds=load_pkmnprices_credentials(allow_frontend_fallback=False)
        provider=PkmnPricesClient(creds.api_key,min_request_interval=.55,timeout=10,max_retries=0)
        result=capture(provider,target,args.period,args.credit_cap)
    args.output.parent.mkdir(parents=True,exist_ok=True)
    args.output.write_text(json.dumps(result,indent=2,sort_keys=True,default=str)+"\n",encoding="utf-8")
    public={k:v for k,v in result.items() if k not in {"target","panels","triad_results"}}
    if "coverage" in result: public["coverage"]=result["coverage"]
    print(json.dumps(public,indent=2,sort_keys=True,default=str))
    return 0 if result["status"] in {"PREFLIGHT_OK","COMPLETE"} else 2


if __name__=="__main__":
    raise SystemExit(main())
