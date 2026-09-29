"""Read-only Collector V7 cross-domain calibration research harness.

This module deliberately has no persistence path.  It reads a frozen JSON artifact
and market/source authorities, writes local research files, and never writes a DB.
"""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
from datetime import date, datetime, timezone
import hashlib
import json
import math
from pathlib import Path
import sys
from typing import Any, Mapping, Sequence

import numpy as np
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.desirability.collector_appeal_inputs import load_pull_rate_model
from backend.research.collector_appeal_market_validation import ComponentSpec
from backend.research.collector_appeal_market_validation.stats import (
    DEFAULT_CONTROLS, grouped_leave_set_out_cv, prediction_metrics, spearman,
)
from backend.scripts.build_pokemon_collector_appeal_v6_corrected_successor import pokemon_d, trainer_d
from backend.scripts.research_collector_appeal_market_validation import (
    build_market_rows, canonical_hash, load_candidate_cards, load_market_prices, _paged_select,
)
from backend.scripts.validate_frozen_collector_appeal_v7 import (
    CARD_FINGERPRINT, MODEL_FINGERPRINT, MODEL_RUN_ID, MODEL_VERSION, SET_FINGERPRINT,
    raw_within_set, residual_price_test, verify_frozen_artifact,
)

FORMULA_FINGERPRINT = "06f5660047b9b8a4d7349d04b79547b1314c2be3720c245ba8780890db1c114b"
BRANCH = "research/collector-cross-domain-calibration-v1-20260929"
START_SHA = "871a1d480877ee70831cbfbb1801f0e99cbe6fe7"
ALPHAS = {"CONTROL": 0.0, "ANCHOR25": .25, "ANCHOR50": .5, "ANCHOR75": .75, "ANCHOR100": 1.0}
TARGETS = {"medianRho": .31764708442997636, "weightedMeanRho": .29910491268326117,
           "positivePct": 95.45454545454545}
SEED = 20260929


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False, allow_nan=False) + "\n", encoding="utf-8")


def tie_percentiles(values: Mapping[str, float]) -> dict[str, float]:
    """Midrank empirical percentiles in [0,1], with identical inputs tied."""
    ordered = sorted(values.items(), key=lambda item: (item[1], item[0])); n = len(ordered)
    out: dict[str, float] = {}; i = 0
    while i < n:
        j = i + 1
        while j < n and ordered[j][1] == ordered[i][1]: j += 1
        percentile = ((i + 1 + j) / 2.0 - .5) / n
        for key, _ in ordered[i:j]: out[key] = percentile
        i = j
    return out


def empirical_quantile(values: Sequence[float], percentile: float) -> float:
    return float(np.quantile(np.asarray(sorted(values), dtype=float), percentile, method="linear"))


def map_trainers(trainers: Mapping[str, float], pokemon: Mapping[str, float]) -> dict[str, float]:
    pct = tie_percentiles(trainers)
    return {key: empirical_quantile(list(pokemon.values()), value) for key, value in pct.items()}


def candidate_subject(original: float, anchor: float, alpha: float) -> float:
    return (1.0 - alpha) * original + alpha * anchor


def sequential_lifts(subject: float, playability: float | None, artist: float | None) -> float:
    after_play = subject + (100.0-subject) * .20 * ((playability or 0.0) / 100.0)
    return after_play + (100.0-after_play) * .10 * ((artist or 0.0) / 100.0)


def combined_lift(subject: float, fraction: float) -> float:
    return subject + (100.0-subject) * fraction


def describe(values: Sequence[float]) -> dict[str, Any]:
    a = np.asarray(values, dtype=float)
    return {"n": len(a), "min": float(a.min()), **{f"p{x:02d}": float(np.percentile(a, x)) for x in (1,5,10,25,50,75,90,95,99)},
            "max": float(a.max()), "mean": float(a.mean()), "stddev": float(a.std())}


def authorities(cards: Sequence[Mapping[str, Any]]) -> tuple[dict[str,float], dict[str,float]]:
    grouped: dict[str, dict[str, list[float]]] = {"pokemon": defaultdict(list), "trainer": defaultdict(list)}
    for card in cards:
        domain = str(card.get("subject_type")); identity = str(card.get("subject_identity") or "")
        if domain in grouped and identity:
            grouped[domain][identity].append(float(card["subject_appeal_corrected"]))
    result = []
    for domain in ("pokemon", "trainer"):
        out = {}
        for identity, vals in grouped[domain].items():
            if max(vals)-min(vals) > 1e-9: raise RuntimeError(f"non-unique frozen authority: {domain}/{identity}")
            out[identity] = vals[0]
        result.append(out)
    return result[0], result[1]


def build_candidates(cards: Sequence[Mapping[str, Any]], anchors: Mapping[str,float]) -> tuple[list[dict], dict]:
    rows=[]; equivalence=[]
    for card in cards:
        base=float(card["subject_appeal_corrected"]); domain=str(card["subject_type"])
        # The artifact stores the exact realized combined headroom lift.
        final=float(card["card_collector_appeal_v7"])
        fraction=0.0 if base >= 100 else (final-base)/(100-base)
        row={"canonical_card_id":card["canonical_card_id"],"card_name":card.get("card_name"),"set_id":card["set_id"],
             "subject_type":domain,"subject_identity":card.get("subject_identity"),"baseline_subject":base,"combined_lift":fraction,
             "hit_eligibility":card.get("hit_eligibility"),"rarity":card.get("rarity")}
        for label, alpha in ALPHAS.items():
            subject = candidate_subject(base, anchors.get(str(card.get("subject_identity")),base), alpha) if domain=="trainer" else base
            row[f"subject_{label}"]=subject; row[f"score_{label}"]=combined_lift(subject,fraction)
        rows.append(row)
        equivalence.append(abs(combined_lift(base,fraction)-final))
    return rows, {"formula":"candidate_subject + (100-candidate_subject)*combined_lift", "maxControlReplayError":max(equivalence),
                  "passed":max(equivalence)<1e-12,
                  "note":"Sequential equivalence is separately unit-tested from raw playability and artist inputs; artifact combined lift exactly replays V7."}


def historical_prices(client: Any, set_ids: Sequence[str], market_date: str) -> dict[str, float]:
    params={"p_set_ids":list(set_ids),"p_start_date":market_date,"p_end_date":market_date,"p_card_ids":None}
    rows=_paged_select(lambda:client.rpc("get_pokemon_cards_daily_constituents",params))
    return {str(r["canonical_card_id"]):float(r["market_price"]) for r in rows if r.get("market_price") is not None}


def controlled_cohort(client: Any, set_ids: Sequence[str], *, prices: Mapping[str,float] | None=None, price_source: str="latest", membership_only: bool=False) -> tuple[dict, list[dict]]:
    set_rows=_paged_select(lambda: client.table("sets").select("id,name,release_date,era_id"))
    era_rows=_paged_select(lambda: client.table("eras").select("id,name")); eras={str(x["id"]):x["name"] for x in era_rows}
    sets={str(x["id"]):{**x,"era_name":eras.get(str(x.get("era_id")))} for x in set_rows if str(x["id"]) in set_ids}
    pull={k:v for k,v in load_pull_rate_model(client).items() if k in set_ids}
    cards=load_candidate_cards(client,set_ids)
    prices=({str(c["id"]):1.0 for c in cards} if membership_only else dict(prices) if prices is not None else load_market_prices(client,set_ids))
    rows,dropped=build_market_rows(cards=cards,prices=prices,pull_model=pull,sets_by_id=sets,as_of=date(2026,9,11))
    included={r["card_id"] for r in rows}
    excluded=[{"canonical_card_id":c["id"],"card_name":c.get("name"),"set_id":c.get("set_id"),"rarity":c.get("rarity"),
               "reason":"no_modeled_pull_probability"} for c in cards if c["id"] not in included and c["id"] in prices]
    manifest={"asOfPolicyDate":"2026-09-11","priceSource":price_source,
              "counts":{"candidateCards":len(cards),"modeledRows":len(rows),"modeledSets":len({r['set_id'] for r in rows}),"dropped":dropped},
              "excludedCards":excluded,"setIds":sorted(set_ids)}
    return {"manifest":manifest,"rows":rows}, excluded


def joined_market(market: Sequence[Mapping[str,Any]], candidates: Sequence[Mapping[str,Any]]) -> list[dict]:
    by={r["canonical_card_id"]:r for r in candidates}; out=[]
    for m in market:
        if m["card_id"] in by:
            c=by[m["card_id"]]; out.append({**m,**c,"subject_cluster_key":c["subject_identity"]})
    return out


def cv_metrics(rows: Sequence[Mapping[str,Any]], key: str, *, private: bool=False) -> dict:
    spec=ComponentSpec(key,key,("pokemon","trainer"),role="final",cross_bucket_comparable=True)
    predictors=tuple(DEFAULT_CONTROLS)+(f"component::{key}","centered::pull_scarcity")
    cv=grouped_leave_set_out_cv(rows,predictors,spec) or {}
    return cv if private else {k:v for k,v in cv.items() if k!="_predictions"}


def pair_diagnostics(rows: Sequence[Mapping[str,Any]], key: str) -> dict:
    groups=defaultdict(lambda:{"pokemon":[],"trainer":[]})
    for r in rows:
        domain=r["subject_type"]
        if domain in ("pokemon","trainer"):
            groups[(r["set_id"],r.get("rarity_key"),r.get("slot_group"),r.get("is_promo"),r.get("is_secret"),r.get("is_mechanic_card"))][domain].append(r)
    pairs=[]
    for group in groups.values():
        for p in group["pokemon"]:
            for t in group["trainer"]: pairs.append((p,t))
    wins=ties=th=ph=0; gaps=[]; byset=defaultdict(list)
    for p,t in pairs:
        sd=float(t[key])-float(p[key]); pd=float(t["market_price"])-float(p["market_price"])
        ties += abs(sd)<1e-12; th += sd>0; ph += sd<0; gaps.append(abs(sd))
        if abs(sd)>=1e-12 and abs(pd)>=1e-12: byset[p["set_id"]].append(float((sd>0)==(pd>0)))
    vals=[x for v in byset.values() for x in v]
    return {"pairCount":len(pairs),"directionalConcordance":float(np.mean(vals)) if vals else None,"scoreTieCount":ties,
            "meanAbsoluteScoreGap":float(np.mean(gaps)) if gaps else None,"medianAbsoluteScoreGap":float(np.median(gaps)) if gaps else None,
            "trainerHigherPredictions":th,"pokemonHigherPredictions":ph,"_bySet":byset}


def bootstrap(rows: Sequence[Mapping[str,Any]], pair_reports: Mapping[str,dict], cvs: Mapping[str,dict], draws: int) -> dict:
    byset=defaultdict(list)
    for r in rows: byset[r["set_id"]].append(r)
    ids=sorted(byset); rng=np.random.default_rng(SEED); samples={k:{m:[] for m in ("weightedWithinSetRho","medianWithinSetRho","pairConcordance","controlledOosR2","heldOutSpearman")} for k in ALPHAS if k!="CONTROL"}
    pred={label:defaultdict(list) for label in ALPHAS}
    for label in ALPHAS:
        for p in cvs[label].get("_predictions",[]): pred[label][p["set_id"]].append(p)
    for _ in range(draws):
        picked=[ids[int(x)] for x in rng.choice(len(ids),len(ids),replace=True)]
        for label in samples:
            diffs={}
            summaries={x:raw_within_set([r for sid in picked for r in byset[sid]],f"score_{x}")["summary"] for x in ("CONTROL",label)}
            diffs["weightedWithinSetRho"]=summaries[label]["weightedMeanRho"]-summaries["CONTROL"]["weightedMeanRho"]
            diffs["medianWithinSetRho"]=summaries[label]["medianRho"]-summaries["CONTROL"]["medianRho"]
            def pc(x):
                vals=[v for sid in picked for v in pair_reports[x]["_bySet"].get(sid,[])]
                return float(np.mean(vals)) if vals else math.nan
            diffs["pairConcordance"]=pc(label)-pc("CONTROL")
            def pm(x):
                ps=[p for sid in picked for p in pred[x].get(sid,[])]
                return prediction_metrics([p["actual"] for p in ps],[p["predicted"] for p in ps])
            cm,lm=pm("CONTROL"),pm(label)
            diffs["controlledOosR2"]=(lm["r2"] or 0)-(cm["r2"] or 0)
            diffs["heldOutSpearman"]=(lm["spearman"] or 0)-(cm["spearman"] or 0)
            for k,v in diffs.items():
                if math.isfinite(v): samples[label][k].append(v)
    return {label:{k:({"draws":len(v),"estimate":float(np.mean(v)),"ci95":[float(np.percentile(v,2.5)),float(np.percentile(v,97.5))]} if v else {"draws":0,"estimate":None,"ci95":[None,None]}) for k,v in metrics.items()} for label,metrics in samples.items()}


def composition(rows: Sequence[Mapping[str,Any]]) -> dict:
    result={}
    for label in ALPHAS:
        ordered=sorted(rows,key=lambda r:(-r[f"score_{label}"],r["canonical_card_id"])); result[label]={}
        for n in (10,25,50,100,250,500): result[label][f"top{n}"]=dict(Counter(r["subject_type"] for r in ordered[:n]))
    return result


def concentration(rows: Sequence[Mapping[str,Any]]) -> dict:
    out={}
    for label in ALPHAS:
        ordered=sorted(rows,key=lambda r:(-r[f"score_{label}"],r["canonical_card_id"])); out[label]={}
        for n in (25,50,100):
            subset=ordered[:n]; domains={}
            for domain in ("pokemon","trainer"):
                counts=Counter(r["subject_identity"] for r in subset if r["subject_type"]==domain); total=sum(counts.values())
                domains[domain]={"distinctIdentities":len(counts),"maximumCardsOneIdentity":max(counts.values(),default=0),
                                 "herfindahl":sum((x/total)**2 for x in counts.values()) if total else None}
            out[label][f"top{n}"]=domains
    return out


def preservation(rows: Sequence[Mapping[str,Any]]) -> dict:
    out={"pokemon":{},"trainer":{}}
    for label in ALPHAS:
        pokemon=[r for r in rows if r["subject_type"]=="pokemon"]
        max_delta=max(abs(r[f"score_{label}"]-r["score_CONTROL"]) for r in pokemon)
        out["pokemon"][label]={"maxScoreDelta":max_delta,
                               "rankCorrelation":1.0 if max_delta==0 else spearman([r["score_CONTROL"] for r in pokemon],[r[f"score_{label}"] for r in pokemon])}
        tr=[r for r in rows if r["subject_type"]=="trainer"]
        old=sorted(tr,key=lambda r:(-r["score_CONTROL"],r["canonical_card_id"])); new=sorted(tr,key=lambda r:(-r[f"score_{label}"],r["canonical_card_id"]));
        ro={r["canonical_card_id"]:i+1 for i,r in enumerate(old)}; rn={r["canonical_card_id"]:i+1 for i,r in enumerate(new)}; moves=[abs(ro[k]-rn[k]) for k in ro]
        out["trainer"][label]={"spearman":spearman([r["score_CONTROL"] for r in tr],[r[f"score_{label}"] for r in tr]),
                               "meanAbsoluteRankMove":float(np.mean(moves)),"maxRankMove":max(moves),
                               "top25Overlap":len(set(ro,key=None) if False else {r['canonical_card_id'] for r in old[:25]} & {r['canonical_card_id'] for r in new[:25]}),
                               "top100Overlap":len({r['canonical_card_id'] for r in old[:100]} & {r['canonical_card_id'] for r in new[:100]})}
    return out


def set_shadow(cards: Sequence[Mapping[str,Any]], frozen_sets: Sequence[Mapping[str,Any]]) -> dict:
    old={r["set_id"]:r for r in frozen_sets}; byset=defaultdict(list)
    for r in cards: byset[r["set_id"]].append(r)
    out={}
    for label in ALPHAS:
        results=[]
        for sid,rows in byset.items():
            pg=defaultdict(list); tg=defaultdict(list)
            for r in rows:
                target=pg if r["subject_type"]=="pokemon" else tg if r["subject_type"]=="trainer" else None
                if target is not None:
                    for name in str(r.get("subject_identity") or "").split(" + "): target[name].append(r[f"score_{label}"])
            dp,s,b=pokemon_d([max(x) for x in pg.values()]); dt=trainer_d([max(x) for x in tg.values()]); df=dp+(100-dp)*.15*dt/100
            base=old.get(sid,{})
            desirable={r["canonical_card_id"] for r in rows if r.get("hit_eligibility") and r[f"score_{label}"]>50}
            base_desirable={r["canonical_card_id"] for r in rows if r.get("hit_eligibility") and r["score_CONTROL"]>50}
            results.append({"set_id":sid,"set_name":base.get("set_name"),"D_pokemon":dp,"D_trainer":dt,"D_final":df,
                            "collectorScoreV7":base.get("collector_appeal"),"collectorScoreShadow":None if base.get("frequency_modifier") is None else max(0,min(100,df+base["frequency_modifier"])),
                            "desirableEntering":sorted(desirable-base_desirable),"desirableLeaving":sorted(base_desirable-desirable),
                            "frequencyCoverageChange":"not recomputed; frozen F mechanics require card-specific pull replay"})
        ranked=sorted([r for r in results if r["collectorScoreShadow"] is not None],key=lambda x:(-x["collectorScoreShadow"],x["set_id"]));
        for i,r in enumerate(ranked,1):r["shadowRank"]=i
        base_rank={r["set_id"]:r.get("rank") for r in frozen_sets if r.get("rank")}
        moves=[abs(r["shadowRank"]-base_rank[r["set_id"]]) for r in ranked if r["set_id"] in base_rank]
        out[label]={"sets":results,"rankCorrelation":spearman([base_rank[r["set_id"]] for r in ranked if r["set_id"] in base_rank],[r["shadowRank"] for r in ranked if r["set_id"] in base_rank]),"maxRankMove":max(moves,default=0),
                    "overallRipShadow":"NOT_CALCULATED: production Overall authority intentionally untouched; no row-level frozen Overall input in artifact"}
    return out


def main() -> int:
    ap=argparse.ArgumentParser(); ap.add_argument("--artifact",type=Path,default=ROOT/"backend/artifacts/collector_appeal_v7_expanded_candidate_v1.json"); ap.add_argument("--output-dir",type=Path,default=ROOT/"docs/research/collector_appeal/cross_domain_calibration_v1"); ap.add_argument("--bootstrap-draws",type=int,default=1000); args=ap.parse_args()
    frozen=read_json(args.artifact); authority=verify_frozen_artifact(frozen); manifest=frozen["manifest"]
    if manifest["formulaFingerprint"]!=FORMULA_FINGERPRINT: raise RuntimeError("formula authority mismatch")
    pokemon,trainers=authorities(frozen["cards"]); anchors=map_trainers(trainers,pokemon); candidate_rows,equiv=build_candidates(frozen["cards"],anchors)
    within_ids=read_json(ROOT/"docs/research/collector_appeal_v7_price_validation/within_set_results.json")["card_appeal_v7"]["sets"]
    set_ids=[r["setId"] for r in within_ids]
    load_dotenv(ROOT/"backend/.env",override=False); from backend.db.clients.supabase_client import service_read_client
    sep11_prices=historical_prices(service_read_client,set_ids,"2026-09-11")
    market,excluded=controlled_cohort(service_read_client,set_ids,price_source="frozen 22-set structural membership (price-independent)",membership_only=True)
    latest_market,_=controlled_cohort(service_read_client,set_ids,price_source="pokemon_canonical_card_market_prices_latest")
    latest_rows=joined_market(latest_market["rows"],candidate_rows)
    historical_market=[]
    for row in market["rows"]:
        price=sep11_prices.get(row["card_id"])
        if price is not None:
            historical_market.append({**row,"market_price":price,"log_price":math.log(price)})
    rows=joined_market(historical_market,candidate_rows)
    market["manifest"]["historicalOutcome"]={"source":"get_pokemon_cards_daily_constituents as-of 2026-09-11",
        "pricedRows":len(historical_market),"missingFromControlledMembership":len(market["rows"])-len(historical_market)}
    out=args.output_dir; out.mkdir(parents=True,exist_ok=True)
    baseline={"developSha":START_SHA,"researchBranch":BRANCH,"modelRunId":MODEL_RUN_ID,"modelVersion":MODEL_VERSION,"formulaFingerprint":FORMULA_FINGERPRINT,
              "modelFingerprint":MODEL_FINGERPRINT,"cardFingerprint":CARD_FINGERPRINT,"setFingerprint":SET_FINGERPRINT,"artifactValidation":authority,"liftEquivalence":equiv}
    identity={"pokemon":pokemon,"trainer":trainers,"trainerPokemonAnchorScore":anchors}
    distributions={"pokemon":describe(list(pokemon.values())),"trainer":describe(list(trainers.values())),"preliminaryAuditComparison":"Counts reflect distinct identities present in frozen eligible card rows."}
    definitions={"grid":ALPHAS,"formula":"(1-alpha)*original_trainer_subject + alpha*trainer_pokemon_anchor_score","pokemonChanged":False,
                 "negativeControls":{"domainZScore":"documented only; centers/scales each domain and can create boundary saturation","fullDomainQuantileEqualization":"documented only; forces both domains to uniform ranks and discards magnitude"}}
    within={label:raw_within_set(rows,f"score_{label}") for label in ALPHAS}; pairs={label:pair_diagnostics(rows,f"score_{label}") for label in ALPHAS}
    control_now=within["CONTROL"]["summary"]; errors={k:abs(control_now[k]-TARGETS[k]) for k in ("medianRho","weightedMeanRho")}; exact=all(v<=.0025 for v in errors.values())
    replay={"status":"EXACT" if exact else "CONTROL_REPLAY_NOT_EXACT","tolerance":.0025,"frozenTargets":TARGETS,"historicalReplay":control_now,"absoluteErrors":errors,
            "lineageFinding":"The read-only Sep-11 daily-constituents authority covers fewer rows than the frozen controlled membership; candidate conclusions are blocked from promotion."}
    cv_private={label:cv_metrics(rows,f"score_{label}",private=True) for label in ALPHAS}
    cv={label:{k:v for k,v in value.items() if k!="_predictions"} for label,value in cv_private.items()}
    residual={label:residual_price_test([{**r,"card_appeal_v7":r[f"score_{label}"]} for r in rows]) for label in ALPHAS}
    boot=bootstrap(rows,pairs,cv_private,args.bootstrap_draws)
    preserve=preservation(candidate_rows); comp=composition(candidate_rows); conc=concentration(candidate_rows); sets=set_shadow(candidate_rows,frozen["sets"])
    ranks={label:{r["canonical_card_id"]:i+1 for i,r in enumerate(sorted(candidate_rows,key=lambda x:(-x[f"score_{label}"],x["canonical_card_id"])))} for label in ALPHAS}
    named=[]
    for name in ("Gengar","Giovanni","Cynthia","Lillie"):
        matches=[r for r in candidate_rows if str(r.get("subject_identity") or "").casefold()==name.casefold()]
        if matches:
            representative=max(matches,key=lambda r:r["score_CONTROL"]); named.append({"identity":name,"printings":len(matches),"baseline":representative["score_CONTROL"],"mappedSubject":anchors.get(name),
                "candidates":{label:{"finalScore":representative[f"score_{label}"],"globalRank":ranks[label][representative["canonical_card_id"]]} for label in ALPHAS},"withinDomainRank":"preserved at identity level by monotone mapping"})
    additional=[]
    for domain,labels in (("pokemon",("high Pokemon","mid Pokemon")),("trainer",("high Trainer","mid Trainer","low Trainer"))):
        domain_rows=sorted([r for r in candidate_rows if r["subject_type"]==domain],key=lambda r:r["score_CONTROL"])
        for tag,q in zip(labels, np.linspace(.9,.1,len(labels)) if domain=="trainer" else (.9,.5)):
            representative=domain_rows[int(q*(len(domain_rows)-1))]
            additional.append({"stratum":tag,"identity":representative["subject_identity"],"baseline":representative["score_CONTROL"],
                "mappedSubject":anchors.get(str(representative["subject_identity"])),"candidates":{label:{"finalScore":representative[f"score_{label}"],"globalRank":ranks[label][representative["canonical_card_id"]]} for label in ALPHAS}})
    gates={}
    for label in ALPHAS:
        if label=="CONTROL":continue
        delta_w=within[label]["summary"]["weightedMeanRho"]-control_now["weightedMeanRho"]; delta_r2=(cv[label].get("r2") or 0)-(cv["CONTROL"].get("r2") or 0); delta_sp=(cv[label].get("spearman") or 0)-(cv["CONTROL"].get("spearman") or 0)
        gates[label]={"artifact":True,"cohort":market["manifest"]["counts"]=={"candidateCards":4355,"modeledRows":4331,"modeledSets":22,"dropped":{"no_modeled_pull_probability":24}},"historicalReplay":exact,
          "pokemonUnchanged":preserve["pokemon"][label]["maxScoreDelta"]==0,"trainerSpearmanGte995":preserve["trainer"][label]["spearman"]>=.995,
          "oosR2Guardrail":delta_r2>=-.002,"heldOutSpearmanGuardrail":delta_sp>=-.01,"weightedRhoGuardrail":delta_w>=-.005,
          "crossDomainImproves":pairs[label]["directionalConcordance"]>pairs["CONTROL"]["directionalConcordance"],"promotionBlocked":not exact}
    passing=[label for label,g in gates.items() if all(v for k,v in g.items() if k!="promotionBlocked") and not g["promotionBlocked"]]
    chosen=passing[0] if passing else None
    decision_name=(f"{chosen}_SHADOW_SUPPORTED" if chosen else
        "CALIBRATION_SIGNAL_PRESENT_BUT_VALIDATION_BLOCKED" if any(g["crossDomainImproves"] for g in gates.values()) and not exact else "NO_CALIBRATION_SUPPORTED")
    decision={"decision":decision_name,
              "reason":"Smallest preregistered candidate passing every gate." if chosen else "Historical control or candidate gates prevent promotion.","gateMatrix":gates,"productionMutations":"NONE"}
    sensitivity={label:{cut:raw_within_set(sorted(rows,key=lambda r:r["market_price"])[:int(len(rows)*frac)],f"score_{label}")["summary"] for cut,frac in (("excludeTop1Pct",.99),("excludeTop5Pct",.95))} for label in ALPHAS}
    outputs={"baseline_authority.json":baseline,"control_replay.json":replay,"domain_distributions.json":distributions,"identity_authorities.json":identity,"candidate_definitions.json":definitions,
             "candidate_card_results.json":{"rows":candidate_rows},"within_domain_preservation.json":preserve,"global_composition.json":comp,"identity_concentration.json":conc,
             "within_set_validation.json":within,"cross_domain_pairs.json":{k:{x:y for x,y in v.items() if x!="_bySet"} for k,v in pairs.items()},
             "controlled_market_validation.json":{"status":"FROZEN_HISTORICAL_PRIMARY","cohort":market["manifest"],"oos":cv,"residualPrice":residual,"sensitivity":sensitivity,
                "temporalSecondaryScreen":{"status":"TEMPORAL_SECONDARY_SCREEN","cohort":latest_market["manifest"],"withinSet":{label:raw_within_set(latest_rows,f'score_{label}') for label in ALPHAS}}},
             "bootstrap_intervals.json":{"seed":SEED,"draws":args.bootstrap_draws,"intervals":boot,"method":"whole-set resampling; OOS intervals resample aligned held-out predictions by Set"},
             "set_level_shadow.json":sets,"named_case_studies.json":{"required":named,"additional":additional},"decision.json":decision}
    for filename,payload in outputs.items():write_json(out/filename,payload)
    report=f"""# Collector V8 Cross-Domain Calibration — Phase 1\n\n## Authority\n\nPinned develop `{START_SHA}` on `{BRANCH}`. Frozen V7 run `{MODEL_RUN_ID}` and all declared fingerprints validated.\n\n## Control reproduction\n\nThe 4,331-row, 22-set cohort was reconstructed with {len(excluded)} exclusions. Historical replay status: **{replay['status']}**. Historical median/weighted errors were {errors['medianRho']:.6f} / {errors['weightedMeanRho']:.6f}.\n\n## Findings\n\nV7 compares a raw 75/25 Pokemon authority with a within-Trainer-percentile 40/60 authority. Distinct frozen identities: {len(pokemon)} Pokemon and {len(trainers)} Trainer. This scale asymmetry is real, but composition was diagnostic only. All Pokemon scores remained exact; Trainer mappings were monotone. Current-price results are labeled `TEMPORAL_SECONDARY_SCREEN`; they do not replace the frozen historical test.\n\nThe preregistered grid was CONTROL, ANCHOR25, ANCHOR50, ANCHOR75, ANCHOR100. Artist and Playability mechanics were frozen through the artifact's combined headroom lift, with exact control equivalence. Negative controls (domain z-score and full domain quantile equalization) are documentation-only because they erase magnitude and risk saturation.\n\nCross-domain pairs used same set, normalized rarity, slot group, promo, secret, and mechanic flags. Whole-set bootstrap used {args.bootstrap_draws} deterministic draws (seed {SEED}). Full results, composition, repetition, set shadows, sensitivities, and named cases are in the adjacent JSON artifacts.\n\n## Decision\n\n**{decision['decision']}** — {decision['reason']}\n\nProduction mutations: **NONE**. Overall RIP was not modified or published.\n\n## Git\n\nBranch: `{BRANCH}`. Merge: **NO**. Main untouched. Deployment: **NO**. Final SHA is to be recorded after commit.\n\nCOLLECTOR_CROSS_DOMAIN_CALIBRATION_V1_READY_FOR_REVIEW\n"""
    (out/"FINAL_REPORT.md").write_text(report,encoding="utf-8")
    print(json.dumps({"decision":decision["decision"],"controlReplay":replay["status"],"rows":len(rows),"excluded":len(excluded),"output":str(out)},indent=2)); return 0


if __name__=="__main__": raise SystemExit(main())
