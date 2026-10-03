"""Research-only joint PURE_TREATMENT estimator for Double Rare / Ultra Rare / SIR.

Consumes the frozen three-level bridge artifact. Ultra Rare is the reference
treatment. No production writes.
"""
from __future__ import annotations

import argparse, hashlib, json, math, sys
from collections import defaultdict
from pathlib import Path
from typing import Any

import numpy as np
from dotenv import load_dotenv

ROOT=Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path: sys.path.insert(0,str(ROOT))

MODEL_RUN_ID="e282f26e-2136-4105-b0a3-f0974c4d9d70"
MODEL_VERSION="pokemon_collector_appeal_v7_expanded_price_blind_v1"
MODEL_AS_OF_DATE="2026-09-11"
SEED=20261002
BOOTSTRAP_DRAWS=2000
DR="Double Rare"
UR="Ultra Rare"
SIR="Special Illustration Rare"

def stable_hash(v:Any)->str:
    return hashlib.sha256(json.dumps(v,sort_keys=True,separators=(",",":"),default=str).encode()).hexdigest()

def _chunks(vals,size=100):
    for i in range(0,len(vals),size): yield vals[i:i+size]

def load_controls(db,card_ids):
    rows=[]
    for chunk in _chunks(card_ids):
        rows.extend(db.table("pokemon_card_collector_appeal_scores").select(
            "pokemon_canonical_card_id,subject_baseline_score,artist_recognition_score,"
            "playability_score,collector_card_appeal_score,price_input_excluded,treatment_input_excluded"
        ).eq("model_run_id",MODEL_RUN_ID).in_("pokemon_canonical_card_id",chunk).execute().data or [])
    if len(rows)!=len(card_ids): raise RuntimeError(f"control coverage mismatch expected={len(card_ids)} got={len(rows)}")
    out={}
    for row in rows:
        cid=str(row["pokemon_canonical_card_id"])
        if row.get("price_input_excluded") is not True or row.get("treatment_input_excluded") is not True:
            raise RuntimeError(f"frozen control contract violated {cid}")
        out[cid]={
            "subject":float(row["subject_baseline_score"]),
            "artist":0.0 if row.get("artist_recognition_score") is None else float(row["artist_recognition_score"]),
            "playability":0.0 if row.get("playability_score") is None else float(row["playability_score"]),
            "collector":float(row["collector_card_appeal_score"]),
        }
    return out

def fit(rows,pure=True):
    y=np.array([float(x["mean_log_ratio"]) for x in rows],dtype=float)
    X=[]
    for x in rows:
        base=[1.0 if x["treatment"]==DR else 0.0,1.0 if x["treatment"]==SIR else 0.0]
        if pure:
            base += [float(x["scarcity_log_ratio"]),float(x["artist_delta"])/100.0]
        else:
            base += [float(x["artist_delta"])/100.0]
        X.append(base)
    X=np.array(X,dtype=float)
    beta=np.linalg.lstsq(X,y,rcond=None)[0]
    return beta,int(np.linalg.matrix_rank(X)),float(np.linalg.cond(X))

def build_rows(artifact,controls):
    cards=list(artifact["target"]["cards"])
    panels=dict(artifact["panels"])
    grouped=defaultdict(list)
    for card in cards: grouped[(card["set_name"],card["subject_key"])].append(card)
    rows=[]
    subject_meta=[]
    for (set_name,subject),group in sorted(grouped.items()):
        by={x["rarity"]:x for x in group}
        if set(by)!={DR,UR,SIR}: raise RuntimeError(f"three-level treatment group invalid {set_name} {subject}")
        dates=None
        histories={}
        for t in (DR,UR,SIR):
            cid=by[t]["canonical_card_id"]
            histories[t]={str(x["date"]):float(x["price"]) for x in panels[cid]["history"]}
            d=set(histories[t])
            dates=d if dates is None else dates & d
        shared=sorted(dates or set())
        if len(shared)<30: raise RuntimeError(f"three-way panel below gate {set_name} {subject}")
        ur=by[UR]
        urc=controls[ur["canonical_card_id"]]
        subject_meta.append({"era_name":ur["era_name"],"set_name":set_name,"subject_key":subject,"shared_dates":len(shared)})
        cut=len(shared)//2
        for t in (DR,SIR):
            card=by[t]
            ctrl=controls[card["canonical_card_id"]]
            if abs(ctrl["subject"]-urc["subject"])>1e-9: raise RuntimeError(f"subject delta nonzero {set_name} {subject} {t}")
            if abs(ctrl["playability"]-urc["playability"])>1e-9: raise RuntimeError(f"playability delta nonzero {set_name} {subject} {t}")
            ratios=[math.log(histories[t][day]/histories[UR][day]) for day in shared]
            rows.append({
                "era_name":ur["era_name"],"set_name":set_name,"subject_key":subject,"treatment":t,
                "shared_dates":len(shared),"first_date":shared[0],"last_date":shared[-1],
                "mean_log_ratio":float(np.mean(ratios)),"early_mean_log_ratio":float(np.mean(ratios[:cut])),
                "late_mean_log_ratio":float(np.mean(ratios[cut:])),
                "scarcity_log_ratio":math.log(float(ur["modeled_probability"])/float(card["modeled_probability"])),
                "artist_delta":ctrl["artist"]-urc["artist"],"playability_delta":0.0,"subject_delta":0.0,
                "raw_multiplier":math.exp(float(np.mean(ratios))),
                "card_id":card["canonical_card_id"],"ur_card_id":ur["canonical_card_id"],
            })
    if len(rows)!=16: raise RuntimeError(f"expected 16 contrasts got={len(rows)}")
    return rows,subject_meta

def transform(beta):
    dr=float(beta[0]); sir=float(beta[1])
    return {
        "double_vs_ultra_log":dr,"double_vs_ultra_multiplier":math.exp(dr),
        "sir_vs_ultra_log":sir,"sir_vs_ultra_multiplier":math.exp(sir),
        "sir_vs_double_log":sir-dr,"sir_vs_double_multiplier":math.exp(sir-dr),
    }

def estimate(artifact,controls):
    if artifact.get("status")!="COMPLETE" or artifact.get("cross_era_progression") is not True:
        raise RuntimeError("three-level bridge gate did not pass")
    if int(artifact.get("production_writes") or 0)!=0: raise RuntimeError("bridge reports production writes")
    rows,subjects=build_rows(artifact,controls)
    pure,rank,cond=fit(rows,True)
    package,_,_=fit(rows,False)
    early=[{**x,"mean_log_ratio":x["early_mean_log_ratio"]} for x in rows]
    late=[{**x,"mean_log_ratio":x["late_mean_log_ratio"]} for x in rows]
    early_b,_,_=fit(early,True); late_b,_,_=fit(late,True)

    grouped=defaultdict(list)
    for row in rows: grouped[(row["set_name"],row["subject_key"])].append(row)
    subject_keys=sorted(grouped)
    rng=np.random.default_rng(SEED)
    boot=[]
    for _ in range(BOOTSTRAP_DRAWS):
        sampled=rng.integers(0,len(subject_keys),len(subject_keys))
        sample=[]
        for idx in sampled: sample.extend(grouped[subject_keys[int(idx)]])
        pb,_,_=fit(sample,True); kb,_,_=fit(sample,False)
        boot.append([*map(float,pb),*map(float,kb),float(pb[1]-pb[0]),float(kb[1]-kb[0])])
    arr=np.array(boot)
    ci=np.percentile(arr,[2.5,50,97.5],axis=0)

    # Adjust each observed contrast by nuisance effects, leaving treatment+residual.
    for row in rows:
        ti=0 if row["treatment"]==DR else 1
        row["pure_log_effect"]=row["mean_log_ratio"]-float(pure[2])*row["scarcity_log_ratio"]-float(pure[3])*(row["artist_delta"]/100.0)
        row["pure_residual_vs_family_mean"]=row["pure_log_effect"]-float(pure[ti])
        row["pure_multiplier"]=math.exp(row["pure_log_effect"])

    set_results=[]
    for era,set_name in sorted({(x["era_name"],x["set_name"]) for x in rows}):
        subset=[x for x in rows if x["set_name"]==set_name]
        vals={t:[x["pure_log_effect"] for x in subset if x["treatment"]==t] for t in (DR,SIR)}
        dr=float(np.mean(vals[DR])); sir=float(np.mean(vals[SIR]))
        set_results.append({"era_name":era,"set_name":set_name,"identity_count":len(vals[DR]),
                            "double_vs_ultra_multiplier":math.exp(dr),"sir_vs_ultra_multiplier":math.exp(sir),
                            "sir_vs_double_multiplier":math.exp(sir-dr)})
    era_results=[]
    for era in sorted({x["era_name"] for x in rows}):
        subset=[x for x in rows if x["era_name"]==era]
        vals={t:[x["pure_log_effect"] for x in subset if x["treatment"]==t] for t in (DR,SIR)}
        dr=float(np.mean(vals[DR])); sir=float(np.mean(vals[SIR]))
        era_results.append({"era_name":era,"identity_count":len(vals[DR]),
                            "double_vs_ultra_multiplier":math.exp(dr),"sir_vs_ultra_multiplier":math.exp(sir),
                            "sir_vs_double_multiplier":math.exp(sir-dr)})

    loo=[]
    for key in subject_keys:
        sample=[x for x in rows if (x["set_name"],x["subject_key"])!=key]
        b,_,_=fit(sample,True); tr=transform(b)
        loo.append({"dropped_set":key[0],"dropped_subject":key[1],**tr})

    pt=transform(pure); pk=transform(package); te=transform(early_b); tl=transform(late_b)
    return {
      "study_id":"pure_treatment_three_level_v1","decision_token":"PURE_TREATMENT_THREE_LEVEL_PILOT_ESTIMATED",
      "formula":{
        "referenceTreatment":UR,
        "contrasts":[DR,SIR],
        "pairOutcome":"mean exact-date log(treatment_NM / UltraRare_NM) on exact three-way shared dates",
        "pureModel":"outcome ~ DoubleRare_dummy + SIR_dummy + log(UR_pull_probability/treatment_pull_probability) + artist_delta/100",
        "packageModel":"outcome ~ DoubleRare_dummy + SIR_dummy + artist_delta/100",
        "subjectControl":"exact matched identity; verified zero delta",
        "playabilityControl":"frozen V7; verified zero delta for all contrasts",
        "bootstrap":"2000 whole-subject resamples (both contrasts retained together)",
      },
      "inputs":{"bridge_digest":stable_hash(artifact),"control_model_run_id":MODEL_RUN_ID,"pairs":16,"identities":8,"sets":4,"eras":2},
      "package":{**pk,"artist_beta_per_100":float(package[2]),
                 "double_ci95":[math.exp(float(ci[0,4])),math.exp(float(ci[2,4]))],
                 "sir_ci95":[math.exp(float(ci[0,5])),math.exp(float(ci[2,5]))],
                 "sir_vs_double_ci95":[math.exp(float(ci[0,8])),math.exp(float(ci[2,8]))]},
      "pure":{**pt,"scarcity_beta":float(pure[2]),"artist_beta_per_100":float(pure[3]),"design_rank":rank,"condition_number":cond,
              "double_ci95":[math.exp(float(ci[0,0])),math.exp(float(ci[2,0]))],
              "sir_ci95":[math.exp(float(ci[0,1])),math.exp(float(ci[2,1]))],
              "sir_vs_double_ci95":[math.exp(float(ci[0,7])),math.exp(float(ci[2,7]))],
              "scarcity_beta_ci95":[float(ci[0,2]),float(ci[2,2])],"artist_beta_ci95":[float(ci[0,3]),float(ci[2,3])]},
      "temporal":{"early":te,"late":tl,"all_contrast_signs_stable":bool(
          np.sign(early_b[0])==np.sign(late_b[0]) and np.sign(early_b[1])==np.sign(late_b[1]) and
          np.sign(early_b[1]-early_b[0])==np.sign(late_b[1]-late_b[0]))},
      "rows":rows,"subjects":subjects,"sets":set_results,"eras":era_results,"leave_one_subject_out":loo,
      "robustness":{
        "double_vs_ultra_loo_min":min(x["double_vs_ultra_multiplier"] for x in loo),
        "double_vs_ultra_loo_max":max(x["double_vs_ultra_multiplier"] for x in loo),
        "sir_vs_ultra_loo_min":min(x["sir_vs_ultra_multiplier"] for x in loo),
        "sir_vs_ultra_loo_max":max(x["sir_vs_ultra_multiplier"] for x in loo),
        "sir_vs_double_loo_min":min(x["sir_vs_double_multiplier"] for x in loo),
        "sir_vs_double_loo_max":max(x["sir_vs_double_multiplier"] for x in loo),
      },
      "production_writes":0,
    }

def render(r):
    p=r["pure"]; t=r["temporal"]; lines=[
      "# PURE_TREATMENT Three-Level V1 — Double Rare / Ultra Rare / SIR","",
      f"Decision token: `{r['decision_token']}`","",
      "## Scarcity-controlled treatment ladder","",
      f"- Double Rare vs Ultra Rare: **{p['double_vs_ultra_multiplier']:.3f}x** (95% bootstrap {p['double_ci95'][0]:.3f}x–{p['double_ci95'][1]:.3f}x)",
      f"- Ultra Rare: **1.000x reference**",
      f"- SIR vs Ultra Rare: **{p['sir_vs_ultra_multiplier']:.3f}x** (95% bootstrap {p['sir_ci95'][0]:.3f}x–{p['sir_ci95'][1]:.3f}x)",
      f"- SIR vs Double Rare: **{p['sir_vs_double_multiplier']:.3f}x** (95% bootstrap {p['sir_vs_double_ci95'][0]:.3f}x–{p['sir_vs_double_ci95'][1]:.3f}x)","",
      "## Temporal stability","",
      f"- Early Double/Ultra: {t['early']['double_vs_ultra_multiplier']:.3f}x; late: {t['late']['double_vs_ultra_multiplier']:.3f}x",
      f"- Early SIR/Ultra: {t['early']['sir_vs_ultra_multiplier']:.3f}x; late: {t['late']['sir_vs_ultra_multiplier']:.3f}x",
      f"- Early SIR/Double: {t['early']['sir_vs_double_multiplier']:.3f}x; late: {t['late']['sir_vs_double_multiplier']:.3f}x",
      f"- All contrast signs stable: **{str(t['all_contrast_signs_stable']).lower()}**","",
      "## Set-level adjusted ladder","",
      "| Era | Set | Double/Ultra | SIR/Ultra | SIR/Double |","|---|---|---:|---:|---:|"
    ]
    for x in r["sets"]: lines.append(f"| {x['era_name']} | {x['set_name']} | {x['double_vs_ultra_multiplier']:.3f}x | {x['sir_vs_ultra_multiplier']:.3f}x | {x['sir_vs_double_multiplier']:.3f}x |")
    lines += ["","Production writes: **ZERO**.",""]
    return "\n".join(lines)

def main(argv=None):
    p=argparse.ArgumentParser(); p.add_argument("--bridge-artifact",type=Path,required=True); p.add_argument("--output",type=Path,required=True); p.add_argument("--report",type=Path,required=True)
    a=p.parse_args(argv); load_dotenv(ROOT/"backend/.env",override=False)
    from backend.db.clients.supabase_client import supabase
    art=json.loads(a.bridge_artifact.read_text(encoding="utf-8"))
    ids=[str(x["canonical_card_id"]) for x in art["target"]["cards"]]
    controls=load_controls(supabase,ids)
    result=estimate(art,controls)
    a.output.parent.mkdir(parents=True,exist_ok=True); a.output.write_text(json.dumps(result,indent=2,sort_keys=True)+"\n",encoding="utf-8")
    a.report.parent.mkdir(parents=True,exist_ok=True); a.report.write_text(render(result),encoding="utf-8")
    print(json.dumps({k:v for k,v in result.items() if k not in {"rows","leave_one_subject_out"}},indent=2,sort_keys=True))
    return 0
if __name__=="__main__": raise SystemExit(main())
