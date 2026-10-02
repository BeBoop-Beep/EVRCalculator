"""Balanced joint three-treatment Treatment model for Double Rare, Ultra Rare, and SIR.

Research only. Fits one common scarcity coefficient across both treatment
contrasts to avoid the collinearity observed in separate pairwise pilots.
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
DOUBLE="Double Rare"; ULTRA="Ultra Rare"; SIR="Special Illustration Rare"
SEED=20261002; BOOTSTRAP_DRAWS=2000

def stable_hash(v:Any)->str:
    return hashlib.sha256(json.dumps(v,sort_keys=True,separators=(",",":"),default=str).encode()).hexdigest()

def chunks(v,size=100):
    for i in range(0,len(v),size): yield v[i:i+size]

def load_controls(db,card_ids):
    rows=[]
    for ch in chunks(card_ids):
        rows += list(db.table("pokemon_card_collector_appeal_scores")
                     .select("pokemon_canonical_card_id,subject_baseline_score,artist_recognition_score,playability_score,price_input_excluded,treatment_input_excluded")
                     .eq("model_run_id",MODEL_RUN_ID).in_("pokemon_canonical_card_id",ch).execute().data or [])
    if len(rows)!=len(card_ids): raise RuntimeError(f"control coverage mismatch expected={len(card_ids)} got={len(rows)}")
    out={}
    for r in rows:
        cid=str(r["pokemon_canonical_card_id"])
        if r.get("price_input_excluded") is not True or r.get("treatment_input_excluded") is not True:
            raise RuntimeError(f"control contamination card={cid}")
        out[cid]={"subject":float(r["subject_baseline_score"]),
                  "artist":0.0 if r.get("artist_recognition_score") is None else float(r["artist_recognition_score"]),
                  "playability":0.0 if r.get("playability_score") is None else float(r["playability_score"])}
    return out

def build_contrasts(artifact,controls):
    if artifact.get("status")!="COMPLETE" or artifact.get("all_subjects_ready") is not True:
        raise RuntimeError("triangle artifact not complete/ready")
    cards=artifact["target"]["cards"]; panels=artifact["panels"]
    groups=defaultdict(list)
    for c in cards: groups[(c["set_name"],c["subject_key"])].append(c)
    contrasts=[]; subjects=[]
    for (set_name,subject),rows in sorted(groups.items()):
        by={r["rarity"]:r for r in rows}
        if set(by)!= {DOUBLE,ULTRA,SIR}: raise RuntimeError(f"incomplete triangle {set_name} {subject}")
        histories={}
        for treatment,row in by.items():
            histories[treatment]={x["date"]:float(x["price"]) for x in panels[row["canonical_card_id"]]["history"]}
        shared=sorted(set(histories[DOUBLE]) & set(histories[ULTRA]) & set(histories[SIR]))
        if len(shared)<90: raise RuntimeError(f"triangle below strong gate {set_name} {subject} {len(shared)}")
        dr=by[DOUBLE]; drc=controls[dr["canonical_card_id"]]
        subject_rows=[]
        for treatment,label in ((ULTRA,"ultra"),(SIR,"sir")):
            tr=by[treatment]; tc=controls[tr["canonical_card_id"]]
            if abs(tc["subject"]-drc["subject"])>1e-9: raise RuntimeError("subject control mismatch")
            if abs(tc["playability"]-drc["playability"])>1e-9: raise RuntimeError("playability control mismatch")
            ratios=[math.log(histories[treatment][d]/histories[DOUBLE][d]) for d in shared]
            cut=len(shared)//2
            row={"era_name":tr["era_name"],"set_name":set_name,"subject_key":subject,"contrast":label,
                 "shared_dates":len(shared),"mean_log_ratio":float(np.mean(ratios)),
                 "early_mean_log_ratio":float(np.mean(ratios[:cut])),"late_mean_log_ratio":float(np.mean(ratios[cut:])),
                 "scarcity_log_ratio":math.log(float(dr["modeled_probability"])/float(tr["modeled_probability"])),
                 "artist_delta":tc["artist"]-drc["artist"],
                 "treatment_probability":float(tr["modeled_probability"]),"double_probability":float(dr["modeled_probability"])}
            contrasts.append(row); subject_rows.append(row)
        subjects.append({"era_name":rows[0]["era_name"],"set_name":set_name,"subject_key":subject,"shared_dates":len(shared)})
    if len(subjects)<8 or len(contrasts)!=2*len(subjects): raise RuntimeError("unexpected triangle size")
    return contrasts,subjects

def fit(rows,key="mean_log_ratio"):
    y=np.array([float(r[key]) for r in rows])
    X=np.array([[1.0 if r["contrast"]=="ultra" else 0.0,
                 1.0 if r["contrast"]=="sir" else 0.0,
                 float(r["scarcity_log_ratio"]),
                 float(r["artist_delta"])/100.0] for r in rows])
    beta=np.linalg.lstsq(X,y,rcond=None)[0]
    return beta,int(np.linalg.matrix_rank(X)),float(np.linalg.cond(X))

def hierarchical_effects(rows,beta,set_key="set_name"):
    adjusted=[]
    for r in rows:
        value=float(r["mean_log_ratio"])-float(beta[2])*float(r["scarcity_log_ratio"])-float(beta[3])*(float(r["artist_delta"])/100.0)
        adjusted.append({**r,"adjusted_log_effect":value})
    grouped=defaultdict(list)
    for r in adjusted:
        grouped[(r["era_name"],r[set_key],r["contrast"])].append(r["adjusted_log_effect"])
    set_map=defaultdict(dict)
    for (era,set_name,contrast),values in grouped.items():
        set_map[(era,set_name)][contrast]=float(np.mean(values))
    set_rows=[]
    for (era,set_name),vals in sorted(set_map.items()):
        if set(vals)!={"ultra","sir"}: raise RuntimeError(f"incomplete hierarchical set {era} {set_name}")
        set_rows.append({
            "era_name":era,"set_name":set_name,
            "ultra_vs_double_log":vals["ultra"],"ultra_vs_double_multiplier":math.exp(vals["ultra"]),
            "sir_vs_double_log":vals["sir"],"sir_vs_double_multiplier":math.exp(vals["sir"]),
            "sir_vs_ultra_log":vals["sir"]-vals["ultra"],"sir_vs_ultra_multiplier":math.exp(vals["sir"]-vals["ultra"]),
        })
    era_rows=[]
    for era in sorted({r["era_name"] for r in set_rows}):
        subset=[r for r in set_rows if r["era_name"]==era]
        u=float(np.mean([r["ultra_vs_double_log"] for r in subset]))
        ss=float(np.mean([r["sir_vs_double_log"] for r in subset]))
        era_rows.append({
            "era_name":era,"set_count":len(subset),
            "ultra_vs_double_log":u,"ultra_vs_double_multiplier":math.exp(u),
            "sir_vs_double_log":ss,"sir_vs_double_multiplier":math.exp(ss),
            "sir_vs_ultra_log":ss-u,"sir_vs_ultra_multiplier":math.exp(ss-u),
        })
    u=float(np.mean([r["ultra_vs_double_log"] for r in era_rows]))
    ss=float(np.mean([r["sir_vs_double_log"] for r in era_rows]))
    global_row={
        "era_count":len(era_rows),"set_count":len(set_rows),
        "ultra_vs_double_log":u,"ultra_vs_double_multiplier":math.exp(u),
        "sir_vs_double_log":ss,"sir_vs_double_multiplier":math.exp(ss),
        "sir_vs_ultra_log":ss-u,"sir_vs_ultra_multiplier":math.exp(ss-u),
    }
    return {"global":global_row,"eras":era_rows,"sets":set_rows}

def estimate(artifact,controls):
    rows,subjects=build_contrasts(artifact,controls)
    beta,rank,cond=fit(rows)
    if rank<4: raise RuntimeError(f"joint design rank deficient rank={rank}")
    early,_,_=fit(rows,"early_mean_log_ratio"); late,_,_=fit(rows,"late_mean_log_ratio")
    by_subject=defaultdict(list)
    by_set_subjects=defaultdict(list)
    for r in rows:
        by_subject[(r["set_name"],r["subject_key"])].append(r)
    for key in sorted(by_subject):
        by_set_subjects[(by_subject[key][0]["era_name"],key[0])].append(key)
    keys=sorted(by_subject)
    rng=np.random.default_rng(SEED); boots=[]; hierarchy_boots=[]
    era_sets=defaultdict(list)
    for era,set_name in sorted(by_set_subjects): era_sets[era].append(set_name)
    for _ in range(BOOTSTRAP_DRAWS):
        sample=[]
        for era in sorted(era_sets):
            sets=era_sets[era]
            sampled_sets=[sets[int(i)] for i in rng.integers(0,len(sets),len(sets))]
            for set_index,set_name in enumerate(sampled_sets):
                subject_keys=by_set_subjects[(era,set_name)]
                sampled_subjects=[subject_keys[int(i)] for i in rng.integers(0,len(subject_keys),len(subject_keys))]
                boot_set=f"{era}|bootset{set_index}"
                for subject_key in sampled_subjects:
                    for row in by_subject[subject_key]:
                        sample.append({**row,"_boot_set":boot_set})
        b,rk,_=fit(sample)
        if rk==4:
            boots.append(b)
            h=hierarchical_effects(sample,b,set_key="_boot_set")["global"]
            hierarchy_boots.append([h["ultra_vs_double_log"],h["sir_vs_double_log"],h["sir_vs_ultra_log"]])
    B=np.array(boots)
    ci=np.percentile(B,[2.5,50,97.5],axis=0)
    sir_ultra_bootstrap=B[:,1]-B[:,0]
    sir_ultra_ci=np.percentile(sir_ultra_bootstrap,[2.5,50,97.5])
    loo=[]
    for key in keys:
        sample=[r for r in rows if (r["set_name"],r["subject_key"])!=key]
        b,rk,c=fit(sample)
        loo.append({"dropped_set":key[0],"dropped_subject":key[1],"rank":rk,"condition_number":c,
                    "ultra_log":float(b[0]),"ultra_multiplier":math.exp(float(b[0])),
                    "sir_log":float(b[1]),"sir_multiplier":math.exp(float(b[1])),
                    "sir_vs_ultra_log":float(b[1]-b[0]),"sir_vs_ultra_multiplier":math.exp(float(b[1]-b[0]))})
    def block(b):
        return {"ultra_vs_double_log":float(b[0]),"ultra_vs_double_multiplier":math.exp(float(b[0])),
                "sir_vs_double_log":float(b[1]),"sir_vs_double_multiplier":math.exp(float(b[1])),
                "sir_vs_ultra_log":float(b[1]-b[0]),"sir_vs_ultra_multiplier":math.exp(float(b[1]-b[0])),
                "scarcity_beta":float(b[2]),"artist_beta_per_100":float(b[3])}
    era=[]
    for e in sorted({r["era_name"] for r in rows}):
        er=[r for r in rows if r["era_name"]==e]
        b,rk,c=fit(er)
        era.append({"era_name":e,"rank":rk,"condition_number":c,**block(b)})
    hierarchy=hierarchical_effects(rows,beta)
    HB=np.array(hierarchy_boots)
    hci=np.percentile(HB,[2.5,50,97.5],axis=0)
    hierarchy["global"]["bootstrap_ultra_multiplier_ci95"]=[math.exp(float(hci[0,0])),math.exp(float(hci[2,0]))]
    hierarchy["global"]["bootstrap_sir_multiplier_ci95"]=[math.exp(float(hci[0,1])),math.exp(float(hci[2,1]))]
    hierarchy["global"]["bootstrap_sir_vs_ultra_multiplier_ci95"]=[math.exp(float(hci[0,2])),math.exp(float(hci[2,2]))]
    hierarchy["global"]["bootstrap_valid_draws"]=len(hierarchy_boots)
    result={"study_id":"treatment_triangle_joint_balanced_v2",
            "decision_token":"TREATMENT_TRIANGLE_BALANCED_HIERARCHY_ESTIMATED",
            "inputs":{"artifact_fingerprint":stable_hash(artifact),"collector_model_run_id":MODEL_RUN_ID,
                      "collector_model_version":MODEL_VERSION,"collector_as_of_date":MODEL_AS_OF_DATE,
                      "subjects":len(subjects),"contrasts":len(rows),"sets":len({r["set_name"] for r in rows}),"eras":len({r["era_name"] for r in rows})},
            "global":{**block(beta),"rank":rank,"condition_number":cond,
                      "bootstrap_valid_draws":len(boots),
                      "ultra_log_ci95":[float(ci[0,0]),float(ci[2,0])],
                      "ultra_multiplier_ci95":[math.exp(float(ci[0,0])),math.exp(float(ci[2,0]))],
                      "sir_log_ci95":[float(ci[0,1]),float(ci[2,1])],
                      "sir_multiplier_ci95":[math.exp(float(ci[0,1])),math.exp(float(ci[2,1]))],
                      "sir_vs_ultra_log_ci95":[float(sir_ultra_ci[0]),float(sir_ultra_ci[2])],
                      "sir_vs_ultra_multiplier_ci95":[math.exp(float(sir_ultra_ci[0])),math.exp(float(sir_ultra_ci[2]))]},
            "temporal":{"early":block(early),"late":block(late)},
            "hierarchy":hierarchy,
            "eras":era,"subjects":subjects,"contrasts_detail":rows,"leave_one_subject_out":loo,
            "robustness":{"early_late_ultra_same_sign":bool(early[0]*late[0]>0),
                          "early_late_sir_same_sign":bool(early[1]*late[1]>0),
                          "loo_ultra_multiplier_range":[min(x["ultra_multiplier"] for x in loo),max(x["ultra_multiplier"] for x in loo)],
                          "loo_sir_multiplier_range":[min(x["sir_multiplier"] for x in loo),max(x["sir_multiplier"] for x in loo)],
                          "loo_sir_vs_ultra_range":[min(x["sir_vs_ultra_multiplier"] for x in loo),max(x["sir_vs_ultra_multiplier"] for x in loo)]},
            "production_writes":0}
    return result

def render(r):
    g=r["global"]; h=r["hierarchy"]["global"]; t=r["temporal"]; rob=r["robustness"]
    lines=["# Balanced Joint Treatment Triangle V2 — Double Rare / Ultra Rare / SIR","",
           f"Decision token: `{r['decision_token']}`","",
           "## Set-first hierarchical Treatment ladder","",
           f"- Double Rare baseline: **1.00x**",
           f"- Ultra Rare vs Double Rare: **{h['ultra_vs_double_multiplier']:.2f}x** (nested bootstrap {h['bootstrap_ultra_multiplier_ci95'][0]:.2f}x–{h['bootstrap_ultra_multiplier_ci95'][1]:.2f}x)",
           f"- SIR vs Double Rare: **{h['sir_vs_double_multiplier']:.2f}x** (nested bootstrap {h['bootstrap_sir_multiplier_ci95'][0]:.2f}x–{h['bootstrap_sir_multiplier_ci95'][1]:.2f}x)",
           f"- SIR vs Ultra Rare: **{h['sir_vs_ultra_multiplier']:.2f}x** (nested bootstrap {h['bootstrap_sir_vs_ultra_multiplier_ci95'][0]:.2f}x–{h['bootstrap_sir_vs_ultra_multiplier_ci95'][1]:.2f}x)",
           f"- Hierarchy: {h['set_count']} Sets across {h['era_count']} eras, equal Set weight within era","",
           "## Raw pooled nuisance-model coefficients","",
           f"- Double Rare baseline: **1.00x**",
           f"- Ultra Rare vs Double Rare: **{g['ultra_vs_double_multiplier']:.2f}x** (95% bootstrap {g['ultra_multiplier_ci95'][0]:.2f}x–{g['ultra_multiplier_ci95'][1]:.2f}x)",
           f"- SIR vs Double Rare: **{g['sir_vs_double_multiplier']:.2f}x** (95% bootstrap {g['sir_multiplier_ci95'][0]:.2f}x–{g['sir_multiplier_ci95'][1]:.2f}x)",
           f"- Implied SIR vs Ultra Rare: **{g['sir_vs_ultra_multiplier']:.2f}x**",
           f"- Shared scarcity coefficient: **{g['scarcity_beta']:.3f}**",
           f"- Design rank/condition: **{g['rank']} / {g['condition_number']:.2f}**","",
           "## Temporal","",
           f"- Early: Ultra {t['early']['ultra_vs_double_multiplier']:.2f}x; SIR {t['early']['sir_vs_double_multiplier']:.2f}x; SIR/Ultra {t['early']['sir_vs_ultra_multiplier']:.2f}x",
           f"- Late: Ultra {t['late']['ultra_vs_double_multiplier']:.2f}x; SIR {t['late']['sir_vs_double_multiplier']:.2f}x; SIR/Ultra {t['late']['sir_vs_ultra_multiplier']:.2f}x","",
           "## Era fits",""]
    for e in r["eras"]: lines.append(f"- **{e['era_name']}**: Ultra {e['ultra_vs_double_multiplier']:.2f}x; SIR {e['sir_vs_double_multiplier']:.2f}x; SIR/Ultra {e['sir_vs_ultra_multiplier']:.2f}x")
    lines += ["","## Influence robustness","",
              f"- Leave-one-subject-out Ultra range: **{rob['loo_ultra_multiplier_range'][0]:.2f}x–{rob['loo_ultra_multiplier_range'][1]:.2f}x**",
              f"- Leave-one-subject-out SIR range: **{rob['loo_sir_multiplier_range'][0]:.2f}x–{rob['loo_sir_multiplier_range'][1]:.2f}x**",
              f"- Leave-one-subject-out SIR/Ultra range: **{rob['loo_sir_vs_ultra_range'][0]:.2f}x–{rob['loo_sir_vs_ultra_range'][1]:.2f}x**","",
              "This balanced joint model extends the same specification across a larger multi-Set cohort after separate pairwise fits exposed scarcity/treatment collinearity. It is research evidence, not a production Treatment score.","","Production writes: **ZERO**."]
    return "\n".join(lines)+"\n"

def main(argv=None):
    p=argparse.ArgumentParser(); p.add_argument("--artifact",type=Path,required=True); p.add_argument("--output",type=Path,required=True); p.add_argument("--report",type=Path,required=True); a=p.parse_args(argv)
    load_dotenv(ROOT/"backend/.env",override=False)
    from backend.db.clients.supabase_client import supabase
    artifact=json.loads(a.artifact.read_text())
    card_ids=[x["canonical_card_id"] for x in artifact["target"]["cards"]]
    controls=load_controls(supabase,card_ids)
    result=estimate(artifact,controls)
    a.output.parent.mkdir(parents=True,exist_ok=True); a.output.write_text(json.dumps(result,indent=2,sort_keys=True)+"\n")
    a.report.parent.mkdir(parents=True,exist_ok=True); a.report.write_text(render(result))
    print(json.dumps({k:v for k,v in result.items() if k not in {"contrasts_detail","leave_one_subject_out"}},indent=2,sort_keys=True))
    return 0
if __name__=="__main__": raise SystemExit(main())
