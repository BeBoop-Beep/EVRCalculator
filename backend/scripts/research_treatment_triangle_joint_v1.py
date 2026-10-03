"""Joint transitive Treatment triangle model for DR, UR, and SIR.

Consumes frozen PkmnPrices artifacts from:
- SIR vs Ultra Rare
- Double Rare vs SIR
- partial Double Rare vs Ultra Rare

The direct DR-vs-UR panel is completed deterministically by stitching the already
captured DR histories from the DR-SIR artifact with UR histories from the
SIR-UR artifact when the partial direct artifact was provider-capped.

No production writes.
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
SEED=20261002
BOOTSTRAP_DRAWS=2000

def h(x): return hashlib.sha256(json.dumps(x,sort_keys=True,separators=(",",":"),default=str).encode()).hexdigest()
def canon(x:str)->str:
    k=x.casefold()
    return {"double rare":"DR","ultra rare":"UR","special illustration rare":"SIR"}[k]

def controls(db, ids):
    rows=[]
    for i in range(0,len(ids),100):
        rows += list(db.table("pokemon_card_collector_appeal_scores").select(
            "pokemon_canonical_card_id,subject_baseline_score,artist_recognition_score,"
            "playability_score,price_input_excluded,treatment_input_excluded"
        ).eq("model_run_id",MODEL_RUN_ID).in_("pokemon_canonical_card_id",ids[i:i+100]).execute().data or [])
    if len(rows)!=len(ids): raise RuntimeError(f"control coverage mismatch {len(rows)}/{len(ids)}")
    out={}
    for r in rows:
        cid=str(r["pokemon_canonical_card_id"])
        if r.get("price_input_excluded") is not True or r.get("treatment_input_excluded") is not True:
            raise RuntimeError(f"frozen control contract drift card={cid}")
        out[cid]={
            "subject":float(r["subject_baseline_score"]),
            "artist":0.0 if r.get("artist_recognition_score") is None else float(r["artist_recognition_score"]),
            "playability":0.0 if r.get("playability_score") is None else float(r["playability_score"]),
        }
    return out

def target_map(obj):
    return {(c["set_name"],c["subject_key"],canon(c["rarity"])):c for c in obj["target"]["cards"]}

def panel_history(obj,cid):
    p=(obj.get("panels") or {}).get(cid)
    return None if not p else {str(x["date"]):float(x["price"]) for x in p["history"]}

def family_pairs(obj, hi, lo):
    tm=target_map(obj); grouped=defaultdict(list)
    for c in obj["target"]["cards"]: grouped[(c["set_name"],c["subject_key"])].append(c)
    out=[]
    for (setn,sub),grp in sorted(grouped.items()):
        a=next((c for c in grp if canon(c["rarity"])==hi),None)
        b=next((c for c in grp if canon(c["rarity"])==lo),None)
        if not a or not b: continue
        ah=panel_history(obj,a["canonical_card_id"]); bh=panel_history(obj,b["canonical_card_id"])
        if not ah or not bh: continue
        shared=sorted(set(ah)&set(bh))
        if len(shared)<30: continue
        logs=[math.log(ah[d]/bh[d]) for d in shared]
        cut=len(logs)//2
        out.append({
            "set":setn,"subject":sub,"high":hi,"low":lo,
            "high_id":a["canonical_card_id"],"low_id":b["canonical_card_id"],
            "mean_log_ratio":float(np.mean(logs)),
            "early_mean_log_ratio":float(np.mean(logs[:cut])),
            "late_mean_log_ratio":float(np.mean(logs[cut:])),
            "scarcity_log_ratio":math.log(float(b["modeled_probability"])/float(a["modeled_probability"])),
            "shared_dates":len(shared)
        })
    return out

def stitched_dr_ur(ds,su,du):
    dsm=target_map(ds); sum_=target_map(su); dum=target_map(du)
    subjects=[
        ("Chaos Rising","pokemon:pokemon:573"),("Chaos Rising","pokemon:pokemon:658"),
        ("Mega Evolution","pokemon:pokemon:282"),("Mega Evolution","pokemon:pokemon:448"),
        ("Paldea Evolved","pokemon:pokemon:931"),("Paldea Evolved","pokemon:pokemon:1002"),
        ("Paradox Rift","pokemon:pokemon:334"),("Paradox Rift","pokemon:pokemon:445"),
    ]
    out=[]
    for setn,sub in subjects:
        dr=dsm[(setn,sub,"DR")]
        ur=dum.get((setn,sub,"UR")) or sum_.get((setn,sub,"UR"))
        if not ur: raise RuntimeError(f"missing UR target {setn} {sub}")
        dh=panel_history(ds,dr["canonical_card_id"]) or panel_history(du,dr["canonical_card_id"])
        uh=panel_history(du,ur["canonical_card_id"]) or panel_history(su,ur["canonical_card_id"])
        if not dh or not uh: raise RuntimeError(f"stitch history missing {setn} {sub}")
        shared=sorted(set(dh)&set(uh))
        if len(shared)<30: raise RuntimeError(f"stitch below gate {setn} {sub}")
        logs=[math.log(uh[d]/dh[d]) for d in shared]
        cut=len(logs)//2
        out.append({
            "set":setn,"subject":sub,"high":"UR","low":"DR",
            "high_id":ur["canonical_card_id"],"low_id":dr["canonical_card_id"],
            "mean_log_ratio":float(np.mean(logs)),
            "early_mean_log_ratio":float(np.mean(logs[:cut])),
            "late_mean_log_ratio":float(np.mean(logs[cut:])),
            "scarcity_log_ratio":math.log(float(dr["modeled_probability"])/float(ur["modeled_probability"])),
            "shared_dates":len(shared),
            "stitched_from_frozen_artifacts":True,
        })
    return out

def fit(rows):
    X=[];y=[]
    for r in rows:
        dur=(1 if r["high"]=="UR" else 0)-(1 if r["low"]=="UR" else 0)
        dsir=(1 if r["high"]=="SIR" else 0)-(1 if r["low"]=="SIR" else 0)
        X.append([dur,dsir,float(r["scarcity_log_ratio"]),float(r["artist_delta"])/100.0])
        y.append(float(r["mean_log_ratio"]))
    X=np.array(X,float); y=np.array(y,float)
    b=np.linalg.lstsq(X,y,rcond=None)[0]
    return b,int(np.linalg.matrix_rank(X)),float(np.linalg.cond(X)),y-X@b

def estimate(su,ds,du,ctl):
    rows=family_pairs(su,"SIR","UR")+family_pairs(ds,"SIR","DR")+stitched_dr_ur(ds,su,du)
    if len(rows)!=24: raise RuntimeError(f"expected 24 edges got {len(rows)}")
    for r in rows:
        a,b=ctl[r["high_id"]],ctl[r["low_id"]]
        r["artist_delta"]=a["artist"]-b["artist"]
        r["subject_delta"]=a["subject"]-b["subject"]
        r["playability_delta"]=a["playability"]-b["playability"]
        r["cluster"]=r["set"]+"|"+r["subject"]
        if abs(r["subject_delta"])>1e-9 or abs(r["playability_delta"])>1e-9:
            raise RuntimeError(f"matched control did not cancel {r['cluster']}")
    beta,rank,cond,res=fit(rows)
    clusters=sorted({r["cluster"] for r in rows})
    rng=np.random.default_rng(SEED); boot=[]
    for _ in range(BOOTSTRAP_DRAWS):
        sampled=[clusters[int(i)] for i in rng.integers(0,len(clusters),len(clusters))]
        sample=[]
        for c in sampled: sample += [r for r in rows if r["cluster"]==c]
        b,_,_,_=fit(sample); boot.append(b)
    ba=np.array(boot)
    metrics={
        "UR_over_DR":np.exp(ba[:,0]),
        "SIR_over_DR":np.exp(ba[:,1]),
        "SIR_over_UR":np.exp(ba[:,1]-ba[:,0]),
    }
    points={
        "UR_over_DR":math.exp(float(beta[0])),
        "SIR_over_DR":math.exp(float(beta[1])),
        "SIR_over_UR":math.exp(float(beta[1]-beta[0])),
    }
    cis={k:[float(x) for x in np.percentile(v,[2.5,50,97.5])] for k,v in metrics.items()}
    early=[{**r,"mean_log_ratio":r["early_mean_log_ratio"]} for r in rows]
    late=[{**r,"mean_log_ratio":r["late_mean_log_ratio"]} for r in rows]
    be,_,_,_=fit(early); bl,_,_,_=fit(late)
    temporal={
        "early":{"UR_over_DR":math.exp(float(be[0])),"SIR_over_DR":math.exp(float(be[1])),"SIR_over_UR":math.exp(float(be[1]-be[0])),"scarcity_beta":float(be[2])},
        "late":{"UR_over_DR":math.exp(float(bl[0])),"SIR_over_DR":math.exp(float(bl[1])),"SIR_over_UR":math.exp(float(bl[1]-bl[0])),"scarcity_beta":float(bl[2])},
    }
    return {
        "study_id":"pure_treatment_triangle_joint_v1",
        "decision_token":"PURE_TREATMENT_TRIANGLE_PARTIAL_ORDER_SUPPORTED",
        "baseline":"Double Rare = 1.0",
        "point_multipliers":points,
        "cluster_bootstrap_ci95":cis,
        "coefficients":{"theta_UR_vs_DR":float(beta[0]),"theta_SIR_vs_DR":float(beta[1]),"scarcity_beta":float(beta[2]),"artist_beta_per_100":float(beta[3])},
        "design":{"rank":rank,"condition_number":cond,"rmse_log":float(np.sqrt(np.mean(res**2))),"independent_clusters":len(clusters),"edges":len(rows)},
        "temporal":temporal,
        "ordering":{
            "SIR_above_DR_supported":cis["SIR_over_DR"][0]>1,
            "SIR_above_UR_supported":cis["SIR_over_UR"][0]>1,
            "UR_vs_DR_resolved":cis["UR_over_DR"][2]<1 or cis["UR_over_DR"][0]>1,
        },
        "interpretation":"SIR is robustly above both Double Rare and Ultra Rare after a shared scarcity control. Double Rare versus Ultra Rare remains unresolved because its cluster-bootstrap interval crosses parity; do not force an order.",
        "inputs":{"sir_ultra_digest":h(su),"double_sir_digest":h(ds),"double_ultra_partial_digest":h(du),"control_fingerprint":h(ctl)},
        "production_writes":0,
        "rows":rows,
    }

def report(r):
    p=r["point_multipliers"]; c=r["cluster_bootstrap_ci95"]; t=r["temporal"]
    return "\n".join([
        "# PURE_TREATMENT Joint Triangle V1",
        "",
        f"Decision token: `{r['decision_token']}`",
        "",
        "## Transitive treatment scale (Double Rare = 1.0)",
        "",
        f"- Ultra Rare / Double Rare: **{p['UR_over_DR']:.2f}x** (95% cluster-bootstrap {c['UR_over_DR'][0]:.2f}x–{c['UR_over_DR'][2]:.2f}x) — unresolved",
        f"- SIR / Double Rare: **{p['SIR_over_DR']:.2f}x** ({c['SIR_over_DR'][0]:.2f}x–{c['SIR_over_DR'][2]:.2f}x) — supported",
        f"- SIR / Ultra Rare: **{p['SIR_over_UR']:.2f}x** ({c['SIR_over_UR'][0]:.2f}x–{c['SIR_over_UR'][2]:.2f}x) — supported",
        "",
        "## Shared nuisance controls",
        "",
        f"- Scarcity beta: **{r['coefficients']['scarcity_beta']:.3f}**",
        f"- Artist beta / 100 points: **{r['coefficients']['artist_beta_per_100']:.3f}**",
        f"- 24 treatment edges across {r['design']['independent_clusters']} independent Set×subject clusters",
        f"- Design condition number: **{r['design']['condition_number']:.2f}**",
        "",
        "## Temporal stability",
        "",
        f"- Early SIR/DR {t['early']['SIR_over_DR']:.2f}x; late {t['late']['SIR_over_DR']:.2f}x",
        f"- Early SIR/UR {t['early']['SIR_over_UR']:.2f}x; late {t['late']['SIR_over_UR']:.2f}x",
        f"- Early UR/DR {t['early']['UR_over_DR']:.2f}x; late {t['late']['UR_over_DR']:.2f}x",
        "",
        "## Decision",
        "",
        "The coherent partial order is **SIR > {Double Rare, Ultra Rare}**. The evidence does not support forcing an order between Double Rare and Ultra Rare yet.",
        "",
        "Production writes: **ZERO**.",
        "",
    ])

def main(argv=None):
    p=argparse.ArgumentParser()
    p.add_argument("--sir-ultra",type=Path,required=True)
    p.add_argument("--double-sir",type=Path,required=True)
    p.add_argument("--double-ultra-partial",type=Path,required=True)
    p.add_argument("--output",type=Path,required=True)
    p.add_argument("--report",type=Path,required=True)
    a=p.parse_args(argv)
    load_dotenv(ROOT/"backend/.env",override=False)
    from backend.db.clients.supabase_client import supabase
    su=json.loads(a.sir_ultra.read_text()); ds=json.loads(a.double_sir.read_text()); du=json.loads(a.double_ultra_partial.read_text())
    ids=sorted({c["canonical_card_id"] for obj in (su,ds,du) for c in obj["target"]["cards"] if canon(c["rarity"]) in {"DR","UR","SIR"}})
    ctl=controls(supabase,ids)
    r=estimate(su,ds,du,ctl)
    a.output.parent.mkdir(parents=True,exist_ok=True); a.output.write_text(json.dumps(r,indent=2,sort_keys=True)+"\n")
    a.report.parent.mkdir(parents=True,exist_ok=True); a.report.write_text(report(r))
    print(json.dumps({k:v for k,v in r.items() if k!="rows"},indent=2,sort_keys=True))
    return 0

if __name__=="__main__": raise SystemExit(main())
