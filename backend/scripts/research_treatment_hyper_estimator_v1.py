"""Research-only PURE_TREATMENT estimator for Hyper Rare / Ultra Rare / SIR."""
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
MAX_BOOTSTRAP_ATTEMPTS=20000
HR="Hyper Rare"; UR="Ultra Rare"; SIR="Special Illustration Rare"

def stable_hash(v:Any)->str:
    return hashlib.sha256(json.dumps(v,sort_keys=True,separators=(",",":"),default=str).encode()).hexdigest()

def _chunks(vals,size=100):
    for i in range(0,len(vals),size): yield vals[i:i+size]

def load_controls(db,ids):
    rows=[]
    for chunk in _chunks(ids):
        rows.extend(db.table("pokemon_card_collector_appeal_scores").select(
            "pokemon_canonical_card_id,subject_baseline_score,artist_recognition_score,playability_score,"
            "price_input_excluded,treatment_input_excluded"
        ).eq("model_run_id",MODEL_RUN_ID).in_("pokemon_canonical_card_id",chunk).execute().data or [])
    if len(rows)!=len(ids): raise RuntimeError(f"control coverage mismatch {len(rows)}/{len(ids)}")
    out={}
    for r in rows:
        cid=str(r["pokemon_canonical_card_id"])
        if r.get("price_input_excluded") is not True or r.get("treatment_input_excluded") is not True:
            raise RuntimeError(f"frozen control contract violated {cid}")
        out[cid]={
            "subject":float(r["subject_baseline_score"]),
            "artist":0.0 if r.get("artist_recognition_score") is None else float(r["artist_recognition_score"]),
            "playability":0.0 if r.get("playability_score") is None else float(r["playability_score"]),
        }
    return out

def fit(rows,pure=True):
    y=np.array([float(x["mean_log_ratio"]) for x in rows])
    X=[]
    for x in rows:
        base=[1.0 if x["treatment"]==HR else 0.0,1.0 if x["treatment"]==SIR else 0.0]
        if pure: base += [float(x["scarcity_log_ratio"]),float(x["artist_delta"])/100.0]
        else: base += [float(x["artist_delta"])/100.0]
        X.append(base)
    X=np.array(X,float)
    beta=np.linalg.lstsq(X,y,rcond=None)[0]
    return beta,int(np.linalg.matrix_rank(X)),float(np.linalg.cond(X))

def transform(beta):
    hr=float(beta[0]); sir=float(beta[1])
    return {
      "hyper_vs_ultra_log":hr,"hyper_vs_ultra_multiplier":math.exp(hr),
      "sir_vs_ultra_log":sir,"sir_vs_ultra_multiplier":math.exp(sir),
      "sir_vs_hyper_log":sir-hr,"sir_vs_hyper_multiplier":math.exp(sir-hr),
    }

def build_rows(artifact,controls):
    cards=list(artifact["target"]["cards"]); panels=dict(artifact["panels"])
    groups=defaultdict(list)
    for c in cards: groups[(c["set_name"],c["subject_key"])].append(c)
    rows=[]; subjects=[]
    for (set_name,subject),group in sorted(groups.items()):
        by={x["rarity"]:x for x in group}
        if set(by)!={HR,UR,SIR}: raise RuntimeError(f"bad triplet {set_name} {subject}")
        histories={}; common=None
        for t in (HR,UR,SIR):
            cid=by[t]["canonical_card_id"]
            histories[t]={str(x["date"]):float(x["price"]) for x in panels[cid]["history"]}
            d=set(histories[t]); common=d if common is None else common&d
        shared=sorted(common or set())
        if len(shared)<30: raise RuntimeError(f"panel below gate {set_name} {subject}")
        ur=by[UR]; uc=controls[ur["canonical_card_id"]]
        subjects.append({"set_name":set_name,"subject_key":subject,"shared_dates":len(shared)})
        cut=len(shared)//2
        for t in (HR,SIR):
            card=by[t]; cc=controls[card["canonical_card_id"]]
            if abs(cc["subject"]-uc["subject"])>1e-9: raise RuntimeError(f"subject mismatch {set_name} {subject} {t}")
            if abs(cc["playability"]-uc["playability"])>1e-9: raise RuntimeError(f"playability mismatch {set_name} {subject} {t}")
            vals=[math.log(histories[t][d]/histories[UR][d]) for d in shared]
            rows.append({
              "set_name":set_name,"subject_key":subject,"treatment":t,"shared_dates":len(shared),
              "mean_log_ratio":float(np.mean(vals)),"early_mean_log_ratio":float(np.mean(vals[:cut])),
              "late_mean_log_ratio":float(np.mean(vals[cut:])),
              "scarcity_log_ratio":math.log(float(ur["modeled_probability"])/float(card["modeled_probability"])),
              "artist_delta":cc["artist"]-uc["artist"],"subject_delta":0.0,"playability_delta":0.0,
              "raw_multiplier":math.exp(float(np.mean(vals))),
            })
    if len(rows)!=8: raise RuntimeError(f"expected 8 contrasts got {len(rows)}")
    return rows,subjects

def bootstrap(rows,pure=True):
    groups=defaultdict(list)
    for r in rows: groups[(r["set_name"],r["subject_key"])].append(r)
    keys=sorted(groups); rng=np.random.default_rng(SEED)
    valid=[]; attempts=0; required_rank=4 if pure else 3
    while len(valid)<BOOTSTRAP_DRAWS and attempts<MAX_BOOTSTRAP_ATTEMPTS:
        attempts+=1; sample=[]
        for idx in rng.integers(0,len(keys),len(keys)): sample.extend(groups[keys[int(idx)]])
        beta,rank,_=fit(sample,pure)
        if rank==required_rank and np.all(np.isfinite(beta)): valid.append(beta)
    if len(valid)<1000: raise RuntimeError(f"insufficient valid bootstrap draws {len(valid)} attempts={attempts}")
    return np.array(valid),attempts

def estimate(artifact,controls):
    if artifact.get("status")!="COMPLETE" or artifact.get("era_progression") is not True: raise RuntimeError("Hyper bridge gate did not pass")
    rows,subjects=build_rows(artifact,controls)
    pure,rank,cond=fit(rows,True); package,prank,pcond=fit(rows,False)
    if rank!=4: raise RuntimeError(f"pure design rank {rank}/4")
    if prank!=3: raise RuntimeError(f"package design rank {prank}/3")
    early=[{**x,"mean_log_ratio":x["early_mean_log_ratio"]} for x in rows]
    late=[{**x,"mean_log_ratio":x["late_mean_log_ratio"]} for x in rows]
    eb,erank,_=fit(early,True); lb,lrank,_=fit(late,True)
    if erank!=4 or lrank!=4: raise RuntimeError("temporal design rank deficient")
    bp,attempts_p=bootstrap(rows,True); bk,attempts_k=bootstrap(rows,False)
    # direct transformed arrays for CIs
    ptrans=np.array([[b[0],b[1],b[1]-b[0]] for b in bp])
    ktrans=np.array([[b[0],b[1],b[1]-b[0]] for b in bk])
    pci=np.percentile(ptrans,[2.5,50,97.5],axis=0); kci=np.percentile(ktrans,[2.5,50,97.5],axis=0)
    pt=transform(pure); kt=transform(package); et=transform(eb); lt=transform(lb)
    loo=[]; keys=sorted({(x["set_name"],x["subject_key"]) for x in rows})
    for key in keys:
        sample=[x for x in rows if (x["set_name"],x["subject_key"])!=key]
        b,r,_=fit(sample,True)
        loo.append({"dropped_set":key[0],"dropped_subject":key[1],"rank":r,**transform(b)})
    return {
      "study_id":"pure_treatment_hyper_v1","decision_token":"PURE_TREATMENT_HYPER_PILOT_ESTIMATED",
      "formula":{"referenceTreatment":UR,"contrasts":[HR,SIR],
                 "pureModel":"outcome ~ HyperRare_dummy + SIR_dummy + log(UR_pull_probability/treatment_pull_probability) + artist_delta/100",
                 "subjectControl":"exact matched identity; verified zero delta",
                 "playabilityControl":"frozen V7; verified zero delta",
                 "bootstrap":"2000 valid whole-subject resamples; rank-deficient resamples discarded"},
      "inputs":{"artifact_digest":stable_hash(artifact),"identities":4,"sets":2,"era":"Scarlet and Violet","control_run_id":MODEL_RUN_ID},
      "pure":{**pt,"scarcity_beta":float(pure[2]),"artist_beta_per_100":float(pure[3]),"design_rank":rank,"condition_number":cond,
              "hyper_ci95":[math.exp(float(pci[0,0])),math.exp(float(pci[2,0]))],
              "sir_ci95":[math.exp(float(pci[0,1])),math.exp(float(pci[2,1]))],
              "sir_vs_hyper_ci95":[math.exp(float(pci[0,2])),math.exp(float(pci[2,2]))],
              "bootstrap_valid_draws":len(bp),"bootstrap_attempts":attempts_p},
      "package":{**kt,"artist_beta_per_100":float(package[2]),"condition_number":pcond,
              "hyper_ci95":[math.exp(float(kci[0,0])),math.exp(float(kci[2,0]))],
              "sir_ci95":[math.exp(float(kci[0,1])),math.exp(float(kci[2,1]))],
              "sir_vs_hyper_ci95":[math.exp(float(kci[0,2])),math.exp(float(kci[2,2]))],
              "bootstrap_valid_draws":len(bk),"bootstrap_attempts":attempts_k},
      "temporal":{"early":et,"late":lt,"all_contrast_signs_stable":bool(
          np.sign(eb[0])==np.sign(lb[0]) and np.sign(eb[1])==np.sign(lb[1]) and np.sign(eb[1]-eb[0])==np.sign(lb[1]-lb[0]))},
      "rows":rows,"subjects":subjects,"leave_one_subject_out":loo,
      "production_writes":0,
    }

def render(r):
    p=r["pure"]; t=r["temporal"]
    return "\n".join([
      "# PURE_TREATMENT Hyper Rare / Ultra Rare / SIR V1","",
      f"Decision token: `{r['decision_token']}`","",
      f"- Hyper Rare vs Ultra Rare: **{p['hyper_vs_ultra_multiplier']:.3f}x** (95% {p['hyper_ci95'][0]:.3f}x–{p['hyper_ci95'][1]:.3f}x)",
      "- Ultra Rare: **1.000x reference**",
      f"- SIR vs Ultra Rare: **{p['sir_vs_ultra_multiplier']:.3f}x** (95% {p['sir_ci95'][0]:.3f}x–{p['sir_ci95'][1]:.3f}x)",
      f"- SIR vs Hyper Rare: **{p['sir_vs_hyper_multiplier']:.3f}x** (95% {p['sir_vs_hyper_ci95'][0]:.3f}x–{p['sir_vs_hyper_ci95'][1]:.3f}x)","",
      f"Early Hyper/Ultra: {t['early']['hyper_vs_ultra_multiplier']:.3f}x; late: {t['late']['hyper_vs_ultra_multiplier']:.3f}x",
      f"Early SIR/Ultra: {t['early']['sir_vs_ultra_multiplier']:.3f}x; late: {t['late']['sir_vs_ultra_multiplier']:.3f}x",
      f"All contrast signs stable: **{str(t['all_contrast_signs_stable']).lower()}**","",
      "Production writes: **ZERO**.",""
    ])

def main(argv=None):
    p=argparse.ArgumentParser(); p.add_argument("--artifact",type=Path,required=True); p.add_argument("--output",type=Path,required=True); p.add_argument("--report",type=Path,required=True)
    a=p.parse_args(argv); load_dotenv(ROOT/"backend/.env",override=False)
    from backend.db.clients.supabase_client import supabase
    art=json.loads(a.artifact.read_text(encoding="utf-8"))
    ids=[str(x["canonical_card_id"]) for x in art["target"]["cards"]]
    controls=load_controls(supabase,ids); result=estimate(art,controls)
    a.output.parent.mkdir(parents=True,exist_ok=True); a.output.write_text(json.dumps(result,indent=2,sort_keys=True)+"\n",encoding="utf-8")
    a.report.parent.mkdir(parents=True,exist_ok=True); a.report.write_text(render(result),encoding="utf-8")
    print(json.dumps({k:v for k,v in result.items() if k not in {"rows","leave_one_subject_out"}},indent=2,sort_keys=True))
    return 0
if __name__=="__main__": raise SystemExit(main())
