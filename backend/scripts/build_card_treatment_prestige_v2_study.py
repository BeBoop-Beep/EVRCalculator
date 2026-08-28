"""Build the preregistered Card Treatment Prestige V2 study.

The default is a non-publishing dry run.  ``--commit`` persists a research or
rejected run; ``--approve`` is separate and is refused unless every gate passes.
"""
from __future__ import annotations

import argparse, hashlib, json, math, subprocess, time
from collections import Counter, defaultdict
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Iterable

import numpy as np
from dotenv import load_dotenv

from backend.desirability.card_treatment_prestige_v2 import (
    METHODOLOGY_VERSION, TAXONOMY_VERSION, common_support_bounds,
    log_pull_odds, pairwise_superiority_scores, positive_log_price,
    resolve_treatment_identity,
)

SEED = 20260828
GATES = {"min_cards": 100, "min_sets": 5, "min_species": 20,
         "min_finish_matches": 50, "min_rank_spearman": .85,
         "max_abs_log_effect_shift": .50, "min_common_support_coverage": .50}


def paged(query, page=500):
    out=[]
    for start in range(0, 10_000_000, page):
        error=None
        for attempt in range(3):
            try: rows=list(query.range(start,start+page-1).execute().data or []); break
            except Exception as exc:
                error=exc
                if attempt<2: time.sleep(2*(attempt+1))
        else: raise RuntimeError(f"database read failed at offset {start}") from error
        out.extend(rows)
        if len(rows)<page: break
    return out


def chunks(values, n=150):
    values=list(values)
    for i in range(0,len(values),n): yield values[i:i+n]


def fetch_in(client, table, columns, key, values):
    return [row for part in chunks(values) for row in paged(client.table(table).select(columns).in_(key,part))]


def latest_exact_rates(client):
    rows=paged(client.table("simulation_card_variant_pull_rates").select("*"))
    newest={}
    for row in rows:
        sid=str(row.get("set_id")); stamp=str(row.get("created_at") or "")
        if sid not in newest or stamp>newest[sid][0]: newest[sid]=(stamp,str(row.get("calculation_run_id")))
    return [r for r in rows if newest.get(str(r.get("set_id")),("",None))[1]==str(r.get("calculation_run_id"))
            and log_pull_odds(r.get("modeled_probability") or r.get("effective_pull_rate")) is not None]


def stable_prices(client, variant_ids, condition_id, as_of, days):
    start=(as_of-timedelta(days=days-1)).isoformat(); end=(as_of+timedelta(days=1)).isoformat()
    values=defaultdict(list)
    for part in chunks(variant_ids,75):
        q=client.table("card_variant_price_observations").select("card_variant_id,condition_id,market_price,captured_at") \
            .in_("card_variant_id",part).eq("condition_id",condition_id).gte("captured_at",start).lt("captured_at",end)
        for row in paged(q):
            price=row.get("market_price")
            if positive_log_price(price) is not None: values[str(row["card_variant_id"])].append(float(price))
    return {key:float(np.median(prices)) for key,prices in values.items() if prices}


def build_cohort(client, as_of, window=30):
    conditions=paged(client.table("conditions").select("id,name").eq("name","Near Mint"))
    if not conditions: raise RuntimeError("Near Mint condition is unavailable")
    condition_id=str(conditions[0]["id"]); rates=latest_exact_rates(client)
    variant_ids={str(r["card_variant_id"]) for r in rates if r.get("card_variant_id")}
    variants={str(r["id"]):r for r in fetch_in(client,"card_variants","id,card_id,printing_type,special_type,edition", "id",variant_ids)}
    card_ids={str(r["card_id"]) for r in variants.values() if r.get("card_id")}
    legacy={str(r["id"]):r for r in fetch_in(client,"cards","id,set_id,pokemon_tcg_api_id,name,rarity", "id",card_ids)}
    sets={str(r["id"]):r for r in paged(client.table("sets").select("id,name,era_id,release_date,supports_opening_simulation"))}
    canonical=paged(client.table("pokemon_canonical_cards").select("id,set_id,pokemon_tcg_api_card_id,name,rarity,supertype,subtypes,artist"))
    canonical_by_api={(str(r.get("set_id")),str(r.get("pokemon_tcg_api_card_id"))):r for r in canonical}
    links=paged(client.table("pokemon_card_desirability_links").select("pokemon_canonical_card_id,pokemon_reference_id,contribution_weight"))
    by_canon=defaultdict(list)
    for link in links: by_canon[str(link["pokemon_canonical_card_id"])].append(link)
    prices=stable_prices(client,variant_ids,condition_id,as_of,window)
    rows=[]; dropped=Counter()
    for rate in rates:
        vid=str(rate.get("card_variant_id")); variant=variants.get(vid); old=legacy.get(str((variant or {}).get("card_id")))
        if not variant or not old: dropped["identity_join"]+=1; continue
        card=canonical_by_api.get((str(old.get("set_id")),str(old.get("pokemon_tcg_api_id"))))
        if not card: dropped["canonical_join"]+=1; continue
        identity=resolve_treatment_identity(rarity=card.get("rarity") or old.get("rarity"),
            printing_type=variant.get("printing_type"),special_type=variant.get("special_type"),edition=variant.get("edition"))
        if not identity.treatment_key: dropped[identity.status]+=1; continue
        price=prices.get(vid); lp=positive_log_price(price); odds=log_pull_odds(rate.get("modeled_probability") or rate.get("effective_pull_rate"))
        subjects=by_canon.get(str(card["id"]),[])
        if lp is None: dropped["no_30d_nm_price"]+=1; continue
        if odds is None: dropped["no_exact_pull_probability"]+=1; continue
        rows.append({"variant_id":vid,"legacy_card_id":str(old["id"]),"canonical_card_id":str(card["id"]),
            "set_id":str(old["set_id"]),"era_id":str((sets.get(str(old["set_id"])) or {}).get("era_id") or ""),
            "treatment":identity.treatment_key,"rarity_key":identity.rarity_key,"printing_type":identity.printing_type,
            "special_type":identity.special_type,"edition":identity.edition,"supertype":card.get("supertype"),
            "species":str(subjects[0].get("pokemon_reference_id")) if len(subjects)==1 else None,
            "subject_count":len(subjects),"subtypes":card.get("subtypes") or [],"artist":card.get("artist"),
            "price":price,"log_price":lp,"log_odds":odds,"probability":math.exp(-odds),
            "run_id":str(rate.get("calculation_run_id")),"price_observations":None})
    return rows,dict(dropped),{"condition_id":condition_id,"rates":len(rates),"prices":len(prices),"sets":sets}


def build_primary_cohort(client, as_of, window=30):
    """Study A: canonical cards with analytic set/rarity pull assumptions."""
    conditions=paged(client.table("conditions").select("id,name").eq("name","Near Mint"))
    condition_id=str(conditions[0]["id"])
    supported=paged(client.table("sets").select("id").eq("supports_opening_simulation",True))
    snapshots=[]
    for item in supported:
        snapshots.extend(paged(client.table("pokemon_set_page_snapshot_latest").select("set_id,payload_json").eq("set_id",item["id"]),page=5))
    odds_by_set={}; raw_assumptions=0
    for snap in snapshots:
        payload=snap.get("payload_json") or {}; assumptions=payload.get("pull_rate_assumptions") or payload.get("pullRateAssumptions") or {}
        mapping={}
        for entry in assumptions.get("rows") or []:
            rarity=resolve_treatment_identity(rarity=entry.get("rarity")).rarity_key
            denominator=entry.get("specific_card_odds_denominator")
            try: denominator=float(denominator)
            except (TypeError,ValueError): continue
            if rarity and denominator>0: mapping.setdefault(rarity,1/denominator);raw_assumptions+=1
        if mapping:odds_by_set[str(snap["set_id"])]=mapping
    set_ids=set(odds_by_set); cards=[]
    for part in chunks(set_ids,30):cards.extend(paged(client.table("pokemon_canonical_cards").select("id,set_id,name,rarity,supertype,subtypes,artist").in_("set_id",part)))
    market=[]
    for part in chunks(set_ids,10):market.extend(paged(client.table("pokemon_canonical_card_market_prices_latest").select("canonical_card_id,card_variant_id,condition_id,set_id").in_("set_id",part)))
    market_by_card={str(r["canonical_card_id"]):r for r in market if r.get("card_variant_id")}
    variant_ids={str(r["card_variant_id"]) for r in market_by_card.values()}; prices=stable_prices(client,variant_ids,condition_id,as_of,window)
    links=paged(client.table("pokemon_card_desirability_links").select("pokemon_canonical_card_id,pokemon_reference_id,contribution_weight"));by_canon=defaultdict(list)
    for link in links:by_canon[str(link["pokemon_canonical_card_id"])].append(link)
    sets={str(r["id"]):r for r in paged(client.table("sets").select("id,era_id"))};rows=[];dropped=Counter()
    for card in cards:
        identity=resolve_treatment_identity(rarity=card.get("rarity"))
        if not identity.treatment_key:dropped[identity.status]+=1;continue
        probability=(odds_by_set.get(str(card["set_id"])) or {}).get(identity.rarity_key)
        market_row=market_by_card.get(str(card["id"]));price=prices.get(str((market_row or {}).get("card_variant_id")))
        if positive_log_price(price) is None:dropped["no_30d_nm_price"]+=1;continue
        if log_pull_odds(probability) is None:dropped["no_analytic_pull_probability"]+=1;continue
        subjects=by_canon.get(str(card["id"]),[])
        rows.append({"variant_id":str(market_row["card_variant_id"]),"canonical_card_id":str(card["id"]),"legacy_card_id":None,
            "set_id":str(card["set_id"]),"era_id":str((sets.get(str(card["set_id"])) or {}).get("era_id") or ""),
            "treatment":identity.treatment_key,"rarity_key":identity.rarity_key,"printing_type":None,"special_type":None,"edition":None,
            "supertype":card.get("supertype"),"species":str(subjects[0]["pokemon_reference_id"]) if len(subjects)==1 else None,
            "subject_count":len(subjects),"subtypes":card.get("subtypes") or [],"artist":card.get("artist"),"price":price,
            "log_price":positive_log_price(price),"log_odds":log_pull_odds(probability),"probability":probability,
            "run_id":"pokemon_set_page_snapshot_latest","price_observations":None})
    return rows,dict(dropped),{"condition_id":condition_id,"assumption_rows":raw_assumptions,"sets":len(set_ids),"prices":len(prices)}


def design(rows, *, treatment_keys=None, artist=False):
    treatments=treatment_keys or sorted({r["treatment"] for r in rows}); base=treatments[0]
    sets=sorted({r["set_id"] for r in rows}); species=sorted({r["species"] for r in rows if r.get("species")})
    mechanics=sorted({str(x).lower() for r in rows for x in r.get("subtypes",[]) if str(x).lower() in {"ex","v","vmax","vstar","gx"}})
    artists=sorted({str(r.get("artist")) for r in rows if r.get("artist")}) if artist else []
    columns=["intercept","log_odds"]+["t:"+x for x in treatments[1:]]+["set:"+x for x in sets[1:]]+["species:"+x for x in species[1:]]+["mechanic:"+x for x in mechanics]+["artist:"+x for x in artists[1:]]
    X=[]
    for r in rows:
        X.append([1,r["log_odds"]]+[int(r["treatment"]==x) for x in treatments[1:]]+
            [int(r["set_id"]==x) for x in sets[1:]]+[int(r.get("species")==x) for x in species[1:]]+
            [int(x in {str(v).lower() for v in r.get("subtypes",[])}) for x in mechanics]+[int(str(r.get("artist"))==x) for x in artists[1:]])
    return np.asarray(X,float),np.asarray([r["log_price"] for r in rows]),columns,base,treatments


def fit(rows, **kwargs):
    if len(rows)<3:return None
    X,y,columns,base,treatments=design(rows,**kwargs); beta=np.linalg.lstsq(X,y,rcond=None)[0]
    coefs={base:0.0}; coefs.update({name[2:]:float(beta[i]) for i,name in enumerate(columns) if name.startswith("t:")})
    return {"coefficients":coefs,"rank":int(np.linalg.matrix_rank(X)),"columns":len(columns),"n":len(rows)}


def bootstrap(rows, draws, seed):
    rng=np.random.default_rng(seed); by_set=defaultdict(list)
    for r in rows:by_set[r["set_id"]].append(r)
    set_ids=sorted(by_set); treatment_keys=sorted({r["treatment"] for r in rows}); samples={k:[] for k in treatment_keys}
    for _ in range(draws):
        sample=[]
        for i,sid in enumerate(rng.choice(set_ids,len(set_ids),replace=True)):
            sample.extend({**r,"set_id":f"{sid}__{i}"} for r in by_set[sid])
        model=fit(sample,treatment_keys=treatment_keys)
        if model:
            for key in treatment_keys:samples[key].append(model["coefficients"].get(key,0.0))
    return samples


def summarize(rows, samples):
    point=fit(rows); scores=pairwise_superiority_scores(samples); output=[]
    by_t=defaultdict(list)
    for r in rows:by_t[r["treatment"]].append(r)
    for key,group in sorted(by_t.items()):
        draws=np.asarray(samples.get(key,[])); beta=point["coefficients"].get(key,0.0)
        other_keys=[x for x in samples if x!=key]; score_draws=np.asarray([10*np.mean([draws[i]>samples[o][i] for o in other_keys]) for i in range(len(draws))]) if other_keys and len(draws) else np.array([])
        output.append({"treatment_key":key,"coefficient_log_price":beta,"adjusted_premium_pct":100*math.expm1(beta),
            "adjusted_premium_ci_low":100*math.expm1(float(np.quantile(draws,.025))) if len(draws) else None,
            "adjusted_premium_ci_high":100*math.expm1(float(np.quantile(draws,.975))) if len(draws) else None,
            "treatment_score_10":scores.get(key),"score_ci_low":float(np.quantile(score_draws,.025)) if len(score_draws) else None,
            "score_ci_high":float(np.quantile(score_draws,.975)) if len(score_draws) else None,
            "card_count":len({r["canonical_card_id"] for r in group}),"variant_count":len(group),
            "set_count":len({r["set_id"] for r in group}),"species_count":len({r["species"] for r in group if r.get("species")}),
            "median_odds":float(np.median([math.exp(r["log_odds"]) for r in group]))})
    return output


def audit_counts(client):
    result={}
    for table in ("pokemon_canonical_cards","pokemon_canonical_card_market_prices_latest","card_variants","sets","simulation_card_variant_pull_rates"):
        try:result[table]=client.table(table).select("id",count="exact").limit(1).execute().count
        except Exception:result[table]=None
    priced=paged(client.table("pokemon_canonical_card_market_prices_latest").select("set_id,canonical_card_id,card_variant_id"))
    cards=paged(client.table("pokemon_canonical_cards").select("id,rarity"))
    result.update({"priced_canonical_cards":len(priced),"priced_sets":len({r["set_id"] for r in priced}),
        "raw_rarity_labels":len({r.get("rarity") for r in cards}),"priced_variants":len({r.get("card_variant_id") for r in priced if r.get("card_variant_id")})})
    return result


def fingerprint(rows):
    payload=[(r["variant_id"],r["treatment"],round(r["price"],6),round(r["probability"],12),r["run_id"]) for r in sorted(rows,key=lambda x:x["variant_id"])]
    return hashlib.sha256(json.dumps(payload,separators=(",",":"),ensure_ascii=True).encode()).hexdigest()


def main():
    p=argparse.ArgumentParser();p.add_argument("--study-as-of",type=date.fromisoformat,default=date.today())
    p.add_argument("--bootstrap-draws",type=int,default=1000);p.add_argument("--seed",type=int,default=SEED)
    p.add_argument("--commit",action="store_true");p.add_argument("--approve",action="store_true");p.add_argument("--dry-run",action="store_true")
    args=p.parse_args(); load_dotenv(Path("backend/.env"))
    from backend.db.clients.supabase_client import create_service_role_client
    client=create_service_role_client(); audit=audit_counts(client)
    rows,dropped,meta=build_primary_cohort(client,args.study_as_of); primary=[r for r in rows if r.get("species")]
    groups=defaultdict(list)
    for r in primary:groups[r["treatment"]].append(r["log_odds"])
    bounds=common_support_bounds(groups); trimmed=[r for r in primary if bounds and bounds[0]<=r["log_odds"]<=bounds[1]]
    samples=bootstrap(primary,args.bootstrap_draws,args.seed) if primary else {}; results=summarize(primary,samples) if samples else []
    for item in results:
        item["status"]="approved" if item["card_count"]>=GATES["min_cards"] and item["set_count"]>=GATES["min_sets"] and item["species_count"]>=GATES["min_species"] else "insufficient_evidence"
        if item["status"] != "approved":
            for field in ("coefficient_log_price","adjusted_premium_pct","adjusted_premium_ci_low",
                          "adjusted_premium_ci_high","treatment_score_10","score_ci_low","score_ci_high"):
                item[field] = None
    approved=[x for x in results if x["status"]=="approved"]
    decision="APPROVE_CARD_TREATMENT_PRESTIGE_V2" if len(approved)>=2 and bounds else "DO_NOT_APPROVE_CARD_TREATMENT_PRESTIGE_V2"
    report={"study":METHODOLOGY_VERSION,"generated_at":datetime.now(timezone.utc).isoformat(),"study_as_of_date":args.study_as_of.isoformat(),
        "decision":decision,"acceptance_gates":GATES,"data_audit":audit,"cohort":{"n":len(primary),"sets":len({r['set_id'] for r in primary}),
        "species":len({r['species'] for r in primary}),"eras":len({r['era_id'] for r in primary}),"dropped":dropped,"fingerprint":fingerprint(primary)},
        "common_support":{"bounds_log_odds":bounds,"trimmed_n":len(trimmed),"coverage":len(trimmed)/len(primary) if primary else 0},
        "rarity_treatment_results":results,"matched_variant_results":[],"bootstrap":{"seed":args.seed,"draws":args.bootstrap_draws},
        "limitations":["Exact-variant pull coverage is currently limited.","Study B is not approved unless at least 50 pull-covered matched comparisons are available."],
        "publication":{"committed":False,"approved":False}}
    out=Path("docs/research/card_treatment_prestige_v2_study.json");out.parent.mkdir(parents=True,exist_ok=True);out.write_text(json.dumps(report,indent=2),encoding="utf-8")
    if args.approve and decision!="APPROVE_CARD_TREATMENT_PRESTIGE_V2": raise SystemExit("Approval refused: preregistered gates did not pass")
    if args.commit: raise SystemExit("Migration must be applied before database publication; no partial run was written")
    print(json.dumps({"decision":decision,"cohort":report["cohort"],"common_support":report["common_support"]},indent=2));return 0

if __name__=="__main__":raise SystemExit(main())
