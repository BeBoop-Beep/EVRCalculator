"""Build the price-free Pull Scarcity control study from current read authorities.

READ ONLY: this module performs GET/select requests and writes research artifacts only.
It never publishes database rows and never changes Collector Appeal.
"""
from __future__ import annotations

import csv
import json
import math
import statistics
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

from dotenv import load_dotenv

from backend.calculations.utils.rarity_classification import normalize_rarity_key
from backend.desirability.chase_accessibility import assert_probability_authority, compute_chase_accessibility

ROOT = Path("docs/research/pull_scarcity_control_v1")
VERSION = "pull_scarcity_control_v1_exact_variant_presence"


def paged(factory, size: int = 1000) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for start in range(0, 100_000, size):
        batch = list(factory().range(start, start + size - 1).execute().data or [])
        out.extend(batch)
        if len(batch) < size:
            return out
    raise RuntimeError("read safety limit exceeded")


def quantiles(values: Iterable[float]) -> dict[str, Any]:
    x = sorted(float(v) for v in values)
    if not x:
        return {"n": 0, "min": None, "p25": None, "median": None, "p75": None, "max": None, "iqr": None, "ratioMaxMin": None}
    def q(frac: float) -> float:
        pos = (len(x) - 1) * frac; lo = int(pos); hi = min(lo + 1, len(x) - 1)
        return x[lo] + (x[hi] - x[lo]) * (pos - lo)
    p25, p75 = q(.25), q(.75)
    return {"n": len(x), "min": x[0], "p25": p25, "median": q(.5), "p75": p75,
            "max": x[-1], "iqr": p75-p25, "ratioMaxMin": x[-1]/x[0]}


def spearman(x: list[float], y: list[float]) -> float | None:
    if len(x) < 3 or len(set(x)) < 2 or len(set(y)) < 2: return None
    def ranks(v):
        order=sorted(range(len(v)), key=lambda i:v[i]); r=[0.0]*len(v); i=0
        while i<len(v):
            j=i
            while j+1<len(v) and v[order[j+1]]==v[order[i]]: j+=1
            rank=(i+j+2)/2
            for k in range(i,j+1): r[order[k]]=rank
            i=j+1
        return r
    a,b=ranks(x),ranks(y); ma,mb=statistics.mean(a),statistics.mean(b)
    num=sum((u-ma)*(v-mb) for u,v in zip(a,b)); den=math.sqrt(sum((u-ma)**2 for u in a)*sum((v-mb)**2 for v in b))
    return num/den if den else None


def write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fields=list(rows[0]) if rows else []
    with path.open("w", newline="", encoding="utf-8") as f:
        w=csv.DictWriter(f, fieldnames=fields); w.writeheader(); w.writerows(rows)


def main() -> int:
    load_dotenv("backend/.env")
    from backend.db.clients.supabase_client import service_read_client as client
    ROOT.mkdir(parents=True, exist_ok=True)
    authorities=paged(lambda: client.table("explore_rip_statistics_latest").select("set_id,set_name,calculation_run_id"))
    sets={str(r["id"]):r for r in paged(lambda: client.table("sets").select("id,name,canonical_key,release_date,era_id,supports_opening_simulation"))}
    eras={str(r["id"]):r.get("name") for r in paged(lambda: client.table("eras").select("id,name"))}
    canon={str(r["id"]):r for r in paged(lambda: client.table("pokemon_canonical_cards").select("id,set_id,name,number,rarity,supertype"))}
    bridges=paged(lambda: client.table("pokemon_canonical_card_market_prices_latest").select("canonical_card_id,legacy_card_id,card_variant_id,set_id"))
    by_legacy={str(r["legacy_card_id"]):str(r["canonical_card_id"]) for r in bridges if r.get("legacy_card_id")}
    variants={str(r["id"]):r for r in paged(lambda: client.table("card_variants").select("id,printing_type,special_type,edition"))}
    c4=json.loads(Path("backend/artifacts/collector_c4_set_components_shadow_v1.json").read_text(encoding="utf-8"))
    c4_by_set={str(r["set_id"]):r for r in c4["sets"]}
    cards=[]; set_metrics=[]; authority_checks=[]
    for a in authorities:
        run=str(a["calculation_run_id"]); sid=str(a["set_id"])
        vr=paged(lambda run=run: client.table("simulation_card_variant_pull_rates").select(
            "calculation_run_id,set_id,card_id,card_variant_id,modeled_probability,effective_pull_rate,pull_count,pack_presence_count,simulation_count,model_source,model_version,status,price_used").eq("calculation_run_id",run))
        check=assert_probability_authority(vr); authority_checks.append({"setId":sid,"setName":a.get("set_name"),**check})
        chase=compute_chase_accessibility(variants=vr,has_pull_model=bool(vr),set_id=sid,calculation_run_id=run)
        ps=[]
        for r in vr:
            p=r.get("modeled_probability")
            if p is None: continue
            cid=by_legacy.get(str(r.get("card_id")))
            c=canon.get(cid or "",{}); v=variants.get(str(r.get("card_variant_id")),{})
            s=sets.get(sid,{})
            row={"canonical_card_id":cid,"card_variant_id":r.get("card_variant_id"),"card_name":c.get("name"),"card_number":c.get("number"),
                 "set_id":sid,"set_name":s.get("name") or a.get("set_name"),"era":eras.get(str(s.get("era_id"))),"raw_rarity":c.get("rarity"),
                 "canonical_treatment":normalize_rarity_key(c.get("rarity")),"printing_type":v.get("printing_type"),"special_type":v.get("special_type"),"edition":v.get("edition"),
                 "modeled_probability":float(p),"expected_packs":1/float(p),"log_expected_packs":-math.log(float(p)),"information_bits":-math.log2(float(p)),
                 "calculation_run_id":run,"model_source":r.get("model_source"),"model_version":r.get("model_version"),"probability_role":"derived pack-presence result"}
            cards.append(row); ps.append(float(p))
        sm=sets.get(sid,{}); frozen=c4_by_set.get(sid,{})
        freq=(frozen.get("frequency") or {}).get("card_gt50") or {}
        set_metrics.append({"setId":sid,"setName":sm.get("name") or a.get("set_name"),"era":eras.get(str(sm.get("era_id"))),"calculationRunId":run,
                            "variantCount":len(ps),"probability":quantiles(ps),"rarestP":min(ps) if ps else None,"medianP":statistics.median(ps) if ps else None,
                            "meanP":statistics.mean(ps) if ps else None,"generalizedF":freq.get("value"),"desirableCardCount":freq.get("eligibleCards"),
                            "modeledDesirableCardCount":freq.get("modeledCards"),"desirableCoverageShare":freq.get("coveredDesirableMassShare"),
                            "effectiveDepth":chase.get("chaseDepth"),"chaseAccessibility":chase.get("accessibility"),"chaseStatus":chase.get("status")})
    by_rarity=defaultdict(list); by_treatment=defaultdict(list); by_era_treatment=defaultdict(list)
    for r in cards:
        by_rarity[r["raw_rarity"] or "__UNMAPPED__"].append(r["modeled_probability"])
        by_treatment[r["canonical_treatment"] or "__UNMAPPED__"].append(r["modeled_probability"])
        by_era_treatment[(r["era"] or "__UNMAPPED__",r["canonical_treatment"] or "__UNMAPPED__")].append(r["modeled_probability"])
    rarity=[{"rarity":k,**quantiles(v)} for k,v in sorted(by_rarity.items())]
    treatment=[{"treatment":k,**quantiles(v)} for k,v in sorted(by_treatment.items())]
    era_treatment=[{"era":k[0],"treatment":k[1],**quantiles(v)} for k,v in sorted(by_era_treatment.items())]
    same=[]
    for label, group in by_rarity.items():
        q=quantiles(group)
        if q["n"]>=2 and q["ratioMaxMin"]>=2: same.append({"rarity":label,**q})
    different=[]; rs=sorted(rarity,key=lambda r:r["median"] or -1)
    for i,a in enumerate(rs):
        for b in rs[i+1:]:
            ratio=max(a["median"],b["median"])/min(a["median"],b["median"])
            if ratio<=1.1: different.append({"rarityA":a["rarity"],"rarityB":b["rarity"],"medianRatio":ratio})
    chase_pairs=[m for m in set_metrics if m["chaseAccessibility"] is not None and m["medianP"] is not None]
    chase_corr=spearman([m["medianP"] for m in chase_pairs],[m["chaseAccessibility"] for m in chase_pairs])
    f_pairs=[m for m in set_metrics if m["generalizedF"] is not None and m["medianP"] is not None]
    f_corr=spearman([m["medianP"] for m in f_pairs],[m["generalizedF"] for m in f_pairs])
    manifest={"version":VERSION,"builtAt":datetime.now(timezone.utc).isoformat(),"priceFreeConstruction":True,"databaseWrites":0,
              "authoritativeSetCount":len(authorities),"cardVariantCount":len(cards),"mappedCanonicalCardCount":sum(bool(r["canonical_card_id"]) for r in cards),
              "authorityFailures":sum(not r["holds"] for r in authority_checks),"generalizedFAvailableSetCount":len(f_pairs),
              "generalizedFMedianProbabilitySpearman":f_corr,"chaseReadySetCount":sum(m["chaseStatus"]=="ready" for m in set_metrics),"chaseMedianProbabilitySpearman":chase_corr,
              "finalDecision":"SCARCITY_DIAGNOSTIC_ONLY"}
    write_csv(ROOT/"card_scarcity.csv",cards); write_csv(ROOT/"rarity_distribution.csv",rarity); write_csv(ROOT/"treatment_distribution.csv",treatment); write_csv(ROOT/"era_treatment_distribution.csv",era_treatment)
    (ROOT/"analysis.json").write_text(json.dumps({"manifest":manifest,"authorityChecks":authority_checks,"setMetrics":set_metrics,"sameRarityDifferentScarcity":same,"differentRaritySimilarScarcity":different},indent=2),encoding="utf-8")
    print(json.dumps(manifest,indent=2)); return 0


if __name__ == "__main__": raise SystemExit(main())
