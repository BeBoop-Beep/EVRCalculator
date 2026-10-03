"""Research-only generic matched Treatment-edge estimator."""
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
SEED=20261002; BOOTSTRAP_DRAWS=2000; MAX_ATTEMPTS=20000

def stable_hash(v:Any)->str:
    return hashlib.sha256(json.dumps(v,sort_keys=True,separators=(",",":"),default=str).encode()).hexdigest()
def chunks(vals,size=100):
    for i in range(0,len(vals),size): yield vals[i:i+size]

def load_controls(db,ids):
    rows=[]
    for chunk in chunks(ids):
        rows.extend(db.table("pokemon_card_collector_appeal_scores").select(
          "pokemon_canonical_card_id,subject_baseline_score,artist_recognition_score,playability_score,price_input_excluded,treatment_input_excluded"
        ).eq("model_run_id",MODEL_RUN_ID).in_("pokemon_canonical_card_id",chunk).execute().data or [])
    if len(rows)!=len(ids): raise RuntimeError(f"control coverage mismatch {len(rows)}/{len(ids)}")
    out={}
    for r in rows:
        cid=str(r["pokemon_canonical_card_id"])
        if r.get("price_input_excluded") is not True or r.get("treatment_input_excluded") is not True: raise RuntimeError(f"control contract violated {cid}")
        out[cid]={"subject":float(r["subject_baseline_score"]),
                  "artist":0.0 if r.get("artist_recognition_score") is None else float(r["artist_recognition_score"]),
                  "playability":0.0 if r.get("playability_score") is None else float(r["playability_score"])}
    return out

def fit(rows):
    y=np.array([float(x["mean_log_ratio"]) for x in rows],float)
    X=np.array([[1.0,float(x["scarcity_log_ratio"]),float(x["artist_delta"])/100.0] for x in rows],float)
    beta=np.linalg.lstsq(X,y,rcond=None)[0]
    return beta,int(np.linalg.matrix_rank(X)),float(np.linalg.cond(X))

def build_rows(artifact,controls):
    target=artifact["target"]; a=target["treatment_a"]; b=target["treatment_b"]; panels=dict(artifact["panels"])
    groups=defaultdict(list)
    for c in target["cards"]: groups[(c["set_name"],c["subject_key"])].append(c)
    rows=[]
    for (set_name,subject),group in sorted(groups.items()):
        by={x["rarity"]:x for x in group}
        if set(by)!={a,b}: raise RuntimeError(f"invalid pair {set_name} {subject}")
        pa={str(x["date"]):float(x["price"]) for x in panels[by[a]["canonical_card_id"]]["history"]}
        pb={str(x["date"]):float(x["price"]) for x in panels[by[b]["canonical_card_id"]]["history"]}
        shared=sorted(set(pa)&set(pb))
        if len(shared)<30: raise RuntimeError(f"panel below gate {set_name} {subject}")
        ca=controls[by[a]["canonical_card_id"]]; cb=controls[by[b]["canonical_card_id"]]
        if abs(ca["subject"]-cb["subject"])>1e-9: raise RuntimeError(f"subject mismatch {set_name} {subject}")
        if abs(ca["playability"]-cb["playability"])>1e-9: raise RuntimeError(f"playability mismatch {set_name} {subject}")
        vals=[math.log(pb[d]/pa[d]) for d in shared]; cut=len(shared)//2
        rows.append({
          "era_name":by[a]["era_name"],"set_name":set_name,"subject_key":subject,"shared_dates":len(shared),
          "mean_log_ratio":float(np.mean(vals)),"early_mean_log_ratio":float(np.mean(vals[:cut])),"late_mean_log_ratio":float(np.mean(vals[cut:])),
          "scarcity_log_ratio":math.log(float(by[a]["modeled_probability"])/float(by[b]["modeled_probability"])),
          "artist_delta":cb["artist"]-ca["artist"],"raw_multiplier":math.exp(float(np.mean(vals)))
        })
    return rows

def bootstrap(rows):
    groups={(x["set_name"],x["subject_key"]):x for x in rows}; keys=sorted(groups); rng=np.random.default_rng(SEED)
    valid=[]; attempts=0
    while len(valid)<BOOTSTRAP_DRAWS and attempts<MAX_ATTEMPTS:
        attempts+=1; sample=[groups[keys[int(i)]] for i in rng.integers(0,len(keys),len(keys))]
        beta,rank,_=fit(sample)
        if rank==3 and np.all(np.isfinite(beta)): valid.append(beta)
    if len(valid)<1500: raise RuntimeError(f"insufficient valid bootstrap draws {len(valid)} attempts={attempts}")
    return np.array(valid),attempts

def estimate(artifact,controls):
    if artifact.get("status")!="COMPLETE" or artifact.get("progression_pass") is not True: raise RuntimeError("edge gate not passed")
    rows=build_rows(artifact,controls); beta,rank,cond=fit(rows)
    if rank!=3: raise RuntimeError(f"design rank {rank}/3")
    early=[{**x,"mean_log_ratio":x["early_mean_log_ratio"]} for x in rows]; late=[{**x,"mean_log_ratio":x["late_mean_log_ratio"]} for x in rows]
    eb,er,_=fit(early); lb,lr,_=fit(late)
    if er!=3 or lr!=3: raise RuntimeError("temporal rank deficient")
    boot,attempts=bootstrap(rows); ci=np.percentile(boot,[2.5,50,97.5],axis=0)
    effect=float(beta[0])
    sets=[]
    for era,set_name in sorted({(x["era_name"],x["set_name"]) for x in rows}):
        vals=[]
        for x in rows:
            if x["set_name"]==set_name:
                vals.append(x["mean_log_ratio"]-float(beta[1])*x["scarcity_log_ratio"]-float(beta[2])*(x["artist_delta"]/100.0))
        m=float(np.mean(vals)); sets.append({"era_name":era,"set_name":set_name,"identity_count":len(vals),"edge_multiplier":math.exp(m),"edge_log_effect":m})
    eras=[]
    for era in sorted({x["era_name"] for x in rows}):
        vals=[x["mean_log_ratio"]-float(beta[1])*x["scarcity_log_ratio"]-float(beta[2])*(x["artist_delta"]/100.0) for x in rows if x["era_name"]==era]
        m=float(np.mean(vals)); eras.append({"era_name":era,"identity_count":len(vals),"edge_multiplier":math.exp(m),"edge_log_effect":m})
    return {
      "study_id":"pure_treatment_pair_edge_v1","decision_token":"PURE_TREATMENT_PAIR_EDGE_ESTIMATED",
      "treatment_a":artifact["target"]["treatment_a"],"treatment_b":artifact["target"]["treatment_b"],
      "inputs":{"artifact_digest":stable_hash(artifact),"identities":len(rows),"sets":len(sets),"control_run_id":MODEL_RUN_ID},
      "pure":{"b_vs_a_log":effect,"b_vs_a_multiplier":math.exp(effect),"b_vs_a_ci95":[math.exp(float(ci[0,0])),math.exp(float(ci[2,0]))],
              "scarcity_beta":float(beta[1]),"scarcity_beta_ci95":[float(ci[0,1]),float(ci[2,1])],
              "artist_beta_per_100":float(beta[2]),"artist_beta_ci95":[float(ci[0,2]),float(ci[2,2])],
              "design_rank":rank,"condition_number":cond,"bootstrap_valid_draws":len(boot),"bootstrap_attempts":attempts},
      "temporal":{"early_multiplier":math.exp(float(eb[0])),"late_multiplier":math.exp(float(lb[0])),
                  "same_sign":bool(np.sign(eb[0])==np.sign(lb[0]))},
      "sets":sets,"eras":eras,"rows":rows,"production_writes":0
    }

def main(argv=None):
    p=argparse.ArgumentParser(); p.add_argument("--artifact",type=Path,required=True); p.add_argument("--output",type=Path,required=True); p.add_argument("--report",type=Path,required=True)
    a=p.parse_args(argv); load_dotenv(ROOT/"backend/.env",override=False)
    from backend.db.clients.supabase_client import supabase
    art=json.loads(a.artifact.read_text(encoding="utf-8")); ids=[str(x["canonical_card_id"]) for x in art["target"]["cards"]]
    r=estimate(art,load_controls(supabase,ids)); t1=r["treatment_a"]; t2=r["treatment_b"]; p1=r["pure"]
    a.output.parent.mkdir(parents=True,exist_ok=True); a.output.write_text(json.dumps(r,indent=2,sort_keys=True)+"\n",encoding="utf-8")
    report="\n".join([f"# PURE_TREATMENT Pair Edge V1 — {t1} → {t2}","",f"Decision token: `{r['decision_token']}`","",
      f"- {t2} vs {t1}: **{p1['b_vs_a_multiplier']:.3f}x** (95% {p1['b_vs_a_ci95'][0]:.3f}x–{p1['b_vs_a_ci95'][1]:.3f}x)",
      f"- early: **{r['temporal']['early_multiplier']:.3f}x**; late: **{r['temporal']['late_multiplier']:.3f}x**",
      f"- identities: **{r['inputs']['identities']}**","", "Production writes: **ZERO**.",""])
    a.report.parent.mkdir(parents=True,exist_ok=True); a.report.write_text(report,encoding="utf-8")
    print(json.dumps({k:v for k,v in r.items() if k!="rows"},indent=2,sort_keys=True)); return 0
if __name__=="__main__": raise SystemExit(main())
