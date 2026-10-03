"""Post-hoc heterogeneity diagnostic after Joint Treatment replication failure.

Not confirmatory and not a rescue fit. Holds the confirmatory replication nuisance
coefficients fixed, then estimates Set-specific latent Treatment levels to measure
between-Set heterogeneity. Research only.
"""
from __future__ import annotations
import argparse, json, math, sys
from collections import defaultdict
from pathlib import Path
from typing import Any
import numpy as np
from dotenv import load_dotenv

ROOT=Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path: sys.path.insert(0,str(ROOT))

MODEL_RUN_ID="e282f26e-2136-4105-b0a3-f0974c4d9d70"
BETA_SCARCITY=0.5453503421390186
BETA_ARTIST=-0.29310979389251257
SEED=20261002
BOOTSTRAP=2000
DR="double rare"; UR="ultra rare"; SIR="special illustration rare"

def chunks(xs,n=100):
    for i in range(0,len(xs),n): yield xs[i:i+n]

def load_controls(db,ids):
    rows=[]
    for chunk in chunks(ids):
        rows += list(db.table("pokemon_card_collector_appeal_scores").select(
            "pokemon_canonical_card_id,subject_baseline_score,artist_recognition_score,playability_score"
        ).eq("model_run_id",MODEL_RUN_ID).in_("pokemon_canonical_card_id",chunk).execute().data or [])
    if len(rows)!=len(ids): raise RuntimeError(f"control coverage {len(rows)}/{len(ids)}")
    return {str(r["pokemon_canonical_card_id"]):{
        "subject":float(r["subject_baseline_score"]),
        "artist":0.0 if r.get("artist_recognition_score") is None else float(r["artist_recognition_score"]),
        "playability":0.0 if r.get("playability_score") is None else float(r["playability_score"])
    } for r in rows}

def tvec(high,low):
    h=high.casefold(); l=low.casefold()
    return np.array([float(h==UR)-float(l==UR),float(h==SIR)-float(l==SIR)],float)

def edges(panel,controls):
    ready={(x["set_name"],x["subject_key"]) for x in panel["triad_results"] if x["ready"]}
    out=[]
    for triad in panel["target"]["triads"]:
        key=(triad["set_name"],triad["subject_key"])
        if key not in ready: continue
        cards={str(c["rarity"]).casefold():c for c in triad["cards"]}
        for high,low in ((UR,DR),(SIR,DR),(SIR,UR)):
            hc,lc=cards[high],cards[low]
            hd={x["date"]:float(x["price"]) for x in panel["panels"][hc["canonical_card_id"]]["history"]}
            ld={x["date"]:float(x["price"]) for x in panel["panels"][lc["canonical_card_id"]]["history"]}
            shared=sorted(set(hd)&set(ld))
            y=float(np.mean([math.log(hd[d]/ld[d]) for d in shared]))
            hctl=controls[hc["canonical_card_id"]]; lctl=controls[lc["canonical_card_id"]]
            if abs(hctl["subject"]-lctl["subject"])>1e-9 or abs(hctl["playability"]-lctl["playability"])>1e-9:
                raise RuntimeError(f"control mismatch {key}")
            scarcity=math.log(float(lc["modeled_probability"])/float(hc["modeled_probability"]))
            artist=(hctl["artist"]-lctl["artist"])/100.0
            adjusted=y-BETA_SCARCITY*scarcity-BETA_ARTIST*artist
            out.append({"set_name":triad["set_name"],"era_name":triad["era_name"],"subject_key":triad["subject_key"],
                        "high":high,"low":low,"x":tvec(high,low).tolist(),"adjusted":adjusted})
    return out

def fit_set(rows):
    X=np.array([r["x"] for r in rows],float); y=np.array([r["adjusted"] for r in rows],float)
    b=np.linalg.lstsq(X,y,rcond=None)[0]
    return float(b[0]),float(b[1])

def main(argv=None):
    p=argparse.ArgumentParser(); p.add_argument("--panel",type=Path,required=True); p.add_argument("--output",type=Path,required=True); p.add_argument("--report",type=Path,required=True); args=p.parse_args(argv)
    panel=json.loads(args.panel.read_text())
    ready={(x["set_name"],x["subject_key"]) for x in panel["triad_results"] if x["ready"]}
    ids=sorted({c["canonical_card_id"] for t in panel["target"]["triads"] if (t["set_name"],t["subject_key"]) in ready for c in t["cards"]})
    load_dotenv(ROOT/"backend/.env",override=False)
    from backend.db.clients.supabase_client import supabase
    es=edges(panel,load_controls(supabase,ids))
    byset=defaultdict(list)
    for e in es: byset[e["set_name"]].append(e)
    rng=np.random.default_rng(SEED); results=[]
    for set_name,rows in sorted(byset.items()):
        ur,sir=fit_set(rows)
        clusters=sorted({r["subject_key"] for r in rows}); byc=defaultdict(list)
        for r in rows: byc[r["subject_key"]].append(r)
        draws=[]
        for _ in range(BOOTSTRAP):
            sample=[]
            for c in rng.choice(clusters,size=len(clusters),replace=True): sample.extend(byc[str(c)])
            draws.append(fit_set(sample))
        a=np.array(draws)
        ur_ci=np.percentile(a[:,0],[2.5,97.5]); sir_ci=np.percentile(a[:,1],[2.5,97.5]); diff=a[:,1]-a[:,0]; diff_ci=np.percentile(diff,[2.5,97.5])
        results.append({"set_name":set_name,"era_name":rows[0]["era_name"],"identities":len(clusters),
                        "ur_vs_dr":math.exp(ur),"ur_vs_dr_ci95":[math.exp(float(ur_ci[0])),math.exp(float(ur_ci[1]))],
                        "sir_vs_dr":math.exp(sir),"sir_vs_dr_ci95":[math.exp(float(sir_ci[0])),math.exp(float(sir_ci[1]))],
                        "sir_vs_ur":math.exp(sir-ur),"sir_vs_ur_ci95":[math.exp(float(diff_ci[0])),math.exp(float(diff_ci[1]))]})
    sir_dr=[math.log(x["sir_vs_dr"]) for x in results]; sir_ur=[math.log(x["sir_vs_ur"]) for x in results]; ur_dr=[math.log(x["ur_vs_dr"]) for x in results]
    summary={"study_id":"joint_treatment_replication_set_heterogeneity_v1","status":"posthoc_diagnostic",
             "fixed_nuisance":{"scarcity_beta":BETA_SCARCITY,"artist_beta":BETA_ARTIST},
             "sets":results,
             "heterogeneity":{"sir_vs_dr_log_sd":float(np.std(sir_dr,ddof=1)),"sir_vs_dr_multiplier_range":[min(x["sir_vs_dr"] for x in results),max(x["sir_vs_dr"] for x in results)],
                              "sir_vs_ur_log_sd":float(np.std(sir_ur,ddof=1)),"sir_vs_ur_multiplier_range":[min(x["sir_vs_ur"] for x in results),max(x["sir_vs_ur"] for x in results)],
                              "ur_vs_dr_log_sd":float(np.std(ur_dr,ddof=1)),"ur_vs_dr_multiplier_range":[min(x["ur_vs_dr"] for x in results),max(x["ur_vs_dr"] for x in results)]},
             "production_writes":0}
    args.output.parent.mkdir(parents=True,exist_ok=True); args.output.write_text(json.dumps(summary,indent=2,sort_keys=True)+"\n")
    lines=["# Treatment Replication Set Heterogeneity — Post-hoc Diagnostic","",
           "Fixed nuisance coefficients are the confirmatory replication full-fit values; no Set-specific scarcity refit is performed.","",
           "| Set | Era | N | UR/DR | SIR/DR | SIR/UR |","|---|---|---:|---:|---:|---:|"]
    for x in results: lines.append(f"| {x['set_name']} | {x['era_name']} | {x['identities']} | {x['ur_vs_dr']:.2f}x | {x['sir_vs_dr']:.2f}x | {x['sir_vs_ur']:.2f}x |")
    h=summary["heterogeneity"]; lines += ["","## Between-Set spread","",
      f"- SIR/DR range: **{h['sir_vs_dr_multiplier_range'][0]:.2f}x–{h['sir_vs_dr_multiplier_range'][1]:.2f}x**; log-SD {h['sir_vs_dr_log_sd']:.3f}",
      f"- SIR/UR range: **{h['sir_vs_ur_multiplier_range'][0]:.2f}x–{h['sir_vs_ur_multiplier_range'][1]:.2f}x**; log-SD {h['sir_vs_ur_log_sd']:.3f}",
      f"- UR/DR range: **{h['ur_vs_dr_multiplier_range'][0]:.2f}x–{h['ur_vs_dr_multiplier_range'][1]:.2f}x**; log-SD {h['ur_vs_dr_log_sd']:.3f}",
      "","Research diagnostic only. Production writes: **ZERO**.",""]
    args.report.parent.mkdir(parents=True,exist_ok=True); args.report.write_text("\n".join(lines))
    print(json.dumps(summary,indent=2,sort_keys=True))
    return 0
if __name__=="__main__": raise SystemExit(main())
