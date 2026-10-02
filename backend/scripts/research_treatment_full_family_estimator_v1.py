"""Research-only exhaustive PURE_TREATMENT estimator for validated three-level families."""
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
REF="Ultra Rare"
CONFIG={
 "dr-ultra-sir":{"a":"Double Rare","b":"Special Illustration Rare","label_a":"double","label_b":"sir"},
 "hyper-ultra-sir":{"a":"Hyper Rare","b":"Special Illustration Rare","label_a":"hyper","label_b":"sir"},
}

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

def fit(rows,a_treatment,b_treatment,pure=True):
    y=np.array([float(x["mean_log_ratio"]) for x in rows],float)
    X=[]
    for x in rows:
        base=[1.0 if x["treatment"]==a_treatment else 0.0,1.0 if x["treatment"]==b_treatment else 0.0]
        if pure: base += [float(x["scarcity_log_ratio"]),float(x["artist_delta"])/100.0]
        else: base += [float(x["artist_delta"])/100.0]
        X.append(base)
    X=np.array(X,float)
    beta=np.linalg.lstsq(X,y,rcond=None)[0]
    return beta,int(np.linalg.matrix_rank(X)),float(np.linalg.cond(X))

def transform(beta):
    a=float(beta[0]); b=float(beta[1])
    return {
      "a_vs_ref_log":a,"a_vs_ref_multiplier":math.exp(a),
      "b_vs_ref_log":b,"b_vs_ref_multiplier":math.exp(b),
      "b_vs_a_log":b-a,"b_vs_a_multiplier":math.exp(b-a),
    }

def build_rows(artifact,controls,cfg):
    a_t=cfg["a"]; b_t=cfg["b"]; treatments={a_t,REF,b_t}
    cards=list(artifact["target"]["cards"]); panels=dict(artifact["panels"])
    groups=defaultdict(list)
    for c in cards: groups[(c["set_name"],c["subject_key"])].append(c)
    rows=[]; subjects=[]
    for (set_name,subject),group in sorted(groups.items()):
        by={x["rarity"]:x for x in group}
        if set(by)!=treatments: raise RuntimeError(f"bad treatment triplet {set_name} {subject}: {sorted(by)}")
        histories={}; common=None
        for t in (a_t,REF,b_t):
            cid=by[t]["canonical_card_id"]
            if cid not in panels: raise RuntimeError(f"missing panel {cid}")
            histories[t]={str(x["date"]):float(x["price"]) for x in panels[cid]["history"]}
            d=set(histories[t]); common=d if common is None else common&d
        shared=sorted(common or set())
        if len(shared)<30: raise RuntimeError(f"panel below gate {set_name} {subject}")
        rc=controls[by[REF]["canonical_card_id"]]
        subjects.append({"era_name":by[REF]["era_name"],"set_name":set_name,"subject_key":subject,"shared_dates":len(shared)})
        cut=len(shared)//2
        for t in (a_t,b_t):
            card=by[t]; cc=controls[card["canonical_card_id"]]
            if abs(cc["subject"]-rc["subject"])>1e-9: raise RuntimeError(f"subject mismatch {set_name} {subject} {t}")
            if abs(cc["playability"]-rc["playability"])>1e-9: raise RuntimeError(f"playability mismatch {set_name} {subject} {t}")
            vals=[math.log(histories[t][day]/histories[REF][day]) for day in shared]
            rows.append({
              "era_name":card["era_name"],"set_name":set_name,"subject_key":subject,"treatment":t,
              "shared_dates":len(shared),"mean_log_ratio":float(np.mean(vals)),
              "early_mean_log_ratio":float(np.mean(vals[:cut])),"late_mean_log_ratio":float(np.mean(vals[cut:])),
              "scarcity_log_ratio":math.log(float(by[REF]["modeled_probability"])/float(card["modeled_probability"])),
              "artist_delta":cc["artist"]-rc["artist"],"subject_delta":0.0,"playability_delta":0.0,
              "raw_multiplier":math.exp(float(np.mean(vals))),
            })
    expected=2*int(artifact["target"]["identity_count"])
    if len(rows)!=expected: raise RuntimeError(f"contrast count mismatch expected={expected} got={len(rows)}")
    return rows,subjects

def bootstrap(rows,cfg,pure):
    groups=defaultdict(list)
    for r in rows: groups[(r["set_name"],r["subject_key"])].append(r)
    keys=sorted(groups); rng=np.random.default_rng(SEED); valid=[]; attempts=0; req=4 if pure else 3
    while len(valid)<BOOTSTRAP_DRAWS and attempts<MAX_BOOTSTRAP_ATTEMPTS:
        attempts+=1; sample=[]
        for idx in rng.integers(0,len(keys),len(keys)): sample.extend(groups[keys[int(idx)]])
        beta,rank,_=fit(sample,cfg["a"],cfg["b"],pure)
        if rank==req and np.all(np.isfinite(beta)): valid.append(beta)
    if len(valid)<1500: raise RuntimeError(f"insufficient valid bootstrap draws={len(valid)} attempts={attempts}")
    return np.array(valid),attempts

def estimate(artifact,controls):
    family=str(artifact.get("family") or "")
    if family not in CONFIG: raise RuntimeError(f"unsupported family {family}")
    if artifact.get("status")!="COMPLETE" or artifact.get("progression_pass") is not True: raise RuntimeError("full family gate not passed")
    cfg=CONFIG[family]; rows,subjects=build_rows(artifact,controls,cfg)
    pure,rank,cond=fit(rows,cfg["a"],cfg["b"],True); package,prank,pcond=fit(rows,cfg["a"],cfg["b"],False)
    if rank!=4 or prank!=3: raise RuntimeError(f"design rank pure={rank} package={prank}")
    early=[{**x,"mean_log_ratio":x["early_mean_log_ratio"]} for x in rows]
    late=[{**x,"mean_log_ratio":x["late_mean_log_ratio"]} for x in rows]
    eb,er,_=fit(early,cfg["a"],cfg["b"],True); lb,lr,_=fit(late,cfg["a"],cfg["b"],True)
    if er!=4 or lr!=4: raise RuntimeError("temporal design rank deficient")
    bp,attp=bootstrap(rows,cfg,True); bk,attk=bootstrap(rows,cfg,False)
    ptrans=np.array([[b[0],b[1],b[1]-b[0]] for b in bp]); ktrans=np.array([[b[0],b[1],b[1]-b[0]] for b in bk])
    pci=np.percentile(ptrans,[2.5,50,97.5],axis=0); kci=np.percentile(ktrans,[2.5,50,97.5],axis=0)
    pt=transform(pure); kt=transform(package); et=transform(eb); lt=transform(lb)
    for row in rows:
        ti=0 if row["treatment"]==cfg["a"] else 1
        row["pure_log_effect"]=row["mean_log_ratio"]-float(pure[2])*row["scarcity_log_ratio"]-float(pure[3])*(row["artist_delta"]/100.0)
        row["pure_residual_vs_family_mean"]=row["pure_log_effect"]-float(pure[ti])

    set_results=[]
    for era,set_name in sorted({(x["era_name"],x["set_name"]) for x in rows}):
        subset=[x for x in rows if x["set_name"]==set_name]
        av=[x["pure_log_effect"] for x in subset if x["treatment"]==cfg["a"]]
        bv=[x["pure_log_effect"] for x in subset if x["treatment"]==cfg["b"]]
        aa=float(np.mean(av)); bb=float(np.mean(bv))
        set_results.append({"era_name":era,"set_name":set_name,"identity_count":len(av),
                            "a_vs_ref_multiplier":math.exp(aa),"b_vs_ref_multiplier":math.exp(bb),"b_vs_a_multiplier":math.exp(bb-aa)})
    era_results=[]
    for era in sorted({x["era_name"] for x in rows}):
        subset=[x for x in rows if x["era_name"]==era]
        av=[x["pure_log_effect"] for x in subset if x["treatment"]==cfg["a"]]
        bv=[x["pure_log_effect"] for x in subset if x["treatment"]==cfg["b"]]
        aa=float(np.mean(av)); bb=float(np.mean(bv))
        era_results.append({"era_name":era,"identity_count":len(av),
                            "a_vs_ref_multiplier":math.exp(aa),"b_vs_ref_multiplier":math.exp(bb),"b_vs_a_multiplier":math.exp(bb-aa)})
    keys=sorted({(x["set_name"],x["subject_key"]) for x in rows}); loo=[]
    for key in keys:
        sample=[x for x in rows if (x["set_name"],x["subject_key"])!=key]
        b,r,_=fit(sample,cfg["a"],cfg["b"],True)
        if r==4: loo.append({"dropped_set":key[0],"dropped_subject":key[1],**transform(b)})
    return {
      "study_id":f"pure_treatment_full_{family.replace('-','_')}_v1","decision_token":"PURE_TREATMENT_FULL_FAMILY_ESTIMATED",
      "family":family,"treatments":{"a":cfg["a"],"reference":REF,"b":cfg["b"]},
      "formula":{"pureModel":"outcome ~ treatment dummies + log(reference pull probability/treatment pull probability) + artist_delta/100",
                 "subjectControl":"exact matched identity; zero delta required","playabilityControl":"frozen V7; zero delta required",
                 "bootstrap":"2000 valid whole-subject resamples; rank-deficient draws discarded"},
      "inputs":{"artifact_digest":stable_hash(artifact),"identities":artifact["target"]["identity_count"],"cards":artifact["target"]["card_count"],
                "sets":len(artifact["set_results"]),"control_run_id":MODEL_RUN_ID},
      "pure":{**pt,"scarcity_beta":float(pure[2]),"artist_beta_per_100":float(pure[3]),"design_rank":rank,"condition_number":cond,
              "a_ci95":[math.exp(float(pci[0,0])),math.exp(float(pci[2,0]))],
              "b_ci95":[math.exp(float(pci[0,1])),math.exp(float(pci[2,1]))],
              "b_vs_a_ci95":[math.exp(float(pci[0,2])),math.exp(float(pci[2,2]))],
              "bootstrap_valid_draws":len(bp),"bootstrap_attempts":attp},
      "package":{**kt,"artist_beta_per_100":float(package[2]),"condition_number":pcond,
              "a_ci95":[math.exp(float(kci[0,0])),math.exp(float(kci[2,0]))],
              "b_ci95":[math.exp(float(kci[0,1])),math.exp(float(kci[2,1]))],
              "b_vs_a_ci95":[math.exp(float(kci[0,2])),math.exp(float(kci[2,2]))],
              "bootstrap_valid_draws":len(bk),"bootstrap_attempts":attk},
      "temporal":{"early":et,"late":lt,"all_contrast_signs_stable":bool(
          np.sign(eb[0])==np.sign(lb[0]) and np.sign(eb[1])==np.sign(lb[1]) and np.sign(eb[1]-eb[0])==np.sign(lb[1]-lb[0]))},
      "sets":set_results,"eras":era_results,"rows":rows,"subjects":subjects,"leave_one_subject_out":loo,
      "production_writes":0,
    }

def render(r):
    p=r["pure"]; t=r["treatments"]; tm=r["temporal"]
    lines=[
      f"# PURE_TREATMENT Full Family V1 — {t['a']} / {t['reference']} / {t['b']}","",
      f"Decision token: `{r['decision_token']}`","",
      f"- {t['a']} vs {t['reference']}: **{p['a_vs_ref_multiplier']:.3f}x** (95% {p['a_ci95'][0]:.3f}x–{p['a_ci95'][1]:.3f}x)",
      f"- {t['reference']}: **1.000x reference**",
      f"- {t['b']} vs {t['reference']}: **{p['b_vs_ref_multiplier']:.3f}x** (95% {p['b_ci95'][0]:.3f}x–{p['b_ci95'][1]:.3f}x)",
      f"- {t['b']} vs {t['a']}: **{p['b_vs_a_multiplier']:.3f}x** (95% {p['b_vs_a_ci95'][0]:.3f}x–{p['b_vs_a_ci95'][1]:.3f}x)","",
      f"- identities: **{r['inputs']['identities']}**",
      f"- cards: **{r['inputs']['cards']}**",
      f"- early/late sign stability: **{str(tm['all_contrast_signs_stable']).lower()}**","",
      "## Set-level adjusted ladder","",
      f"| Era | Set | Identities | {t['a']}/{t['reference']} | {t['b']}/{t['reference']} | {t['b']}/{t['a']} |",
      "|---|---|---:|---:|---:|---:|"
    ]
    for x in r["sets"]:
        lines.append(f"| {x['era_name']} | {x['set_name']} | {x['identity_count']} | {x['a_vs_ref_multiplier']:.3f}x | {x['b_vs_ref_multiplier']:.3f}x | {x['b_vs_a_multiplier']:.3f}x |")
    lines += ["","Production writes: **ZERO**.",""]
    return "\n".join(lines)

def main(argv=None):
    p=argparse.ArgumentParser(); p.add_argument("--artifact",type=Path,required=True); p.add_argument("--output",type=Path,required=True); p.add_argument("--report",type=Path,required=True)
    a=p.parse_args(argv); load_dotenv(ROOT/"backend/.env",override=False)
    from backend.db.clients.supabase_client import supabase
    art=json.loads(a.artifact.read_text(encoding="utf-8")); ids=[str(x["canonical_card_id"]) for x in art["target"]["cards"]]
    result=estimate(art,load_controls(supabase,ids))
    a.output.parent.mkdir(parents=True,exist_ok=True); a.output.write_text(json.dumps(result,indent=2,sort_keys=True)+"\n",encoding="utf-8")
    a.report.parent.mkdir(parents=True,exist_ok=True); a.report.write_text(render(result),encoding="utf-8")
    print(json.dumps({k:v for k,v in result.items() if k not in {"rows","leave_one_subject_out"}},indent=2,sort_keys=True))
    return 0
if __name__=="__main__": raise SystemExit(main())
