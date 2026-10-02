"""Preregistered confirmatory replication for Joint Treatment Ladder V1.

Consumes the independent replication panel and applies the frozen shared-scarcity
joint formula with no model tuning. Research only; no production writes.
"""
from __future__ import annotations

import argparse, hashlib, json, math, sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

import numpy as np
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

MODEL_RUN_ID="e282f26e-2136-4105-b0a3-f0974c4d9d70"
MODEL_VERSION="pokemon_collector_appeal_v7_expanded_price_blind_v1"
MODEL_AS_OF_DATE="2026-09-11"
SEED=20261002
BOOTSTRAP_DRAWS=2000
DOUBLE="double rare"
ULTRA="ultra rare"
SIR="special illustration rare"
LEVELS=(DOUBLE,ULTRA,SIR)

EXPLORATORY={
    "sir_double_interval":(1.4307184412540335,4.85794366152502),
    "sir_ultra_interval":(2.726998320400255,5.11906966466205),
    "scarcity_interval":(1.342482494267826,1.9133545121770297),
}

def stable_hash(value:Any)->str:
    return hashlib.sha256(json.dumps(value,sort_keys=True,separators=(",",":"),default=str).encode()).hexdigest()

def _chunks(values:list[str],size:int=100):
    for i in range(0,len(values),size): yield values[i:i+size]

def load_controls(db:Any,card_ids:list[str])->dict[str,dict[str,float]]:
    rows=[]
    for chunk in _chunks(card_ids):
        rows += list(db.table("pokemon_card_collector_appeal_scores").select(
            "pokemon_canonical_card_id,subject_baseline_score,artist_recognition_score,"
            "playability_score,collector_card_appeal_score,price_input_excluded,"
            "treatment_input_excluded"
        ).eq("model_run_id",MODEL_RUN_ID).in_("pokemon_canonical_card_id",chunk).execute().data or [])
    if len(rows)!=len(card_ids):
        raise RuntimeError(f"control coverage mismatch expected={len(card_ids)} got={len(rows)}")
    out={}
    for row in rows:
        cid=str(row["pokemon_canonical_card_id"])
        if row.get("price_input_excluded") is not True or row.get("treatment_input_excluded") is not True:
            raise RuntimeError(f"frozen control contract violated card={cid}")
        out[cid]={
            "subject":float(row["subject_baseline_score"]),
            "artist":0.0 if row.get("artist_recognition_score") is None else float(row["artist_recognition_score"]),
            "playability":0.0 if row.get("playability_score") is None else float(row["playability_score"]),
        }
    return out

def treatment_vector(high:str,low:str)->tuple[float,float]:
    h=high.casefold(); l=low.casefold()
    return float(h==ULTRA)-float(l==ULTRA), float(h==SIR)-float(l==SIR)

def build_edges(panel:dict[str,Any],controls:dict[str,dict[str,float]])->list[dict[str,Any]]:
    ready_keys={(x["set_name"],x["subject_key"]) for x in panel["triad_results"] if x["ready"]}
    edges=[]
    for triad in panel["target"]["triads"]:
        key=(triad["set_name"],triad["subject_key"])
        if key not in ready_keys: continue
        cards={str(x["rarity"]).casefold():x for x in triad["cards"]}
        if set(cards)!=set(LEVELS): raise RuntimeError(f"ready triad rarity mismatch {key}")
        for high_label,low_label in ((ULTRA,DOUBLE),(SIR,DOUBLE),(SIR,ULTRA)):
            high=cards[high_label]; low=cards[low_label]
            hd={str(x["date"]):float(x["price"]) for x in panel["panels"][high["canonical_card_id"]]["history"]}
            ld={str(x["date"]):float(x["price"]) for x in panel["panels"][low["canonical_card_id"]]["history"]}
            shared=sorted(set(hd)&set(ld))
            if len(shared)<30: raise RuntimeError(f"ready edge below gate {key}")
            ratios=[math.log(hd[d]/ld[d]) for d in shared]
            hc=controls[high["canonical_card_id"]]; lc=controls[low["canonical_card_id"]]
            if abs(hc["subject"]-lc["subject"])>1e-9: raise RuntimeError(f"subject mismatch {key}")
            if abs(hc["playability"]-lc["playability"])>1e-9: raise RuntimeError(f"playability mismatch {key}")
            cut=len(ratios)//2
            edges.append({
                "cluster_key":f"{key[0]}|{key[1]}","era_name":triad["era_name"],
                "set_name":key[0],"subject_key":key[1],"high_treatment":high_label,
                "low_treatment":low_label,"mean_log_ratio":float(np.mean(ratios)),
                "early_mean_log_ratio":float(np.mean(ratios[:cut])),
                "late_mean_log_ratio":float(np.mean(ratios[cut:])),
                "scarcity_log_ratio":math.log(float(low["modeled_probability"])/float(high["modeled_probability"])),
                "artist_delta":hc["artist"]-lc["artist"],"shared_dates":len(shared),
            })
    return edges

def design(rows:list[dict[str,Any]],outcome:str)->tuple[np.ndarray,np.ndarray]:
    X=[]; y=[]
    for row in rows:
        ur,sir=treatment_vector(row["high_treatment"],row["low_treatment"])
        X.append([ur,sir,float(row["scarcity_log_ratio"]),float(row["artist_delta"])/100.0])
        y.append(float(row[outcome]))
    return np.array(X,float),np.array(y,float)

def fit(rows:list[dict[str,Any]],outcome:str="mean_log_ratio",equal_cluster:bool=False):
    X,y=design(rows,outcome)
    if equal_cluster:
        counts=Counter(x["cluster_key"] for x in rows)
        w=np.array([1.0/counts[x["cluster_key"]] for x in rows],float)
        root=np.sqrt(w); X=X*root[:,None]; y=y*root
    beta=np.linalg.lstsq(X,y,rcond=None)[0]
    return beta,int(np.linalg.matrix_rank(X)),float(np.linalg.cond(X))

def metrics(beta:np.ndarray):
    return {
        "ultra_vs_double":math.exp(float(beta[0])),
        "sir_vs_double":math.exp(float(beta[1])),
        "sir_vs_ultra":math.exp(float(beta[1]-beta[0])),
        "scarcity_beta":float(beta[2]),"artist_beta":float(beta[3]),
    }

def estimate(panel:dict[str,Any],controls:dict[str,dict[str,float]])->dict[str,Any]:
    coverage=panel.get("coverage") or {}
    if panel.get("status")!="COMPLETE" or int(panel.get("production_writes") or 0)!=0:
        raise RuntimeError("replication panel incomplete or unsafe")
    if not coverage.get("coverage_pass"):
        return {"decision_token":"JOINT_TREATMENT_LADDER_REPLICATION_INSUFFICIENT_COVERAGE","coverage":coverage,"production_writes":0}
    edges=build_edges(panel,controls)
    clusters=sorted({x["cluster_key"] for x in edges})
    if len(edges)!=3*len(clusters): raise RuntimeError("replication edge count mismatch")
    beta,rank,condition=fit(edges); full=metrics(beta)
    early_beta,early_rank,_=fit(edges,"early_mean_log_ratio"); late_beta,late_rank,_=fit(edges,"late_mean_log_ratio")
    early=metrics(early_beta); late=metrics(late_beta)
    equal_beta,equal_rank,equal_condition=fit(edges,equal_cluster=True); equal=metrics(equal_beta)

    by_cluster=defaultdict(list)
    for row in edges: by_cluster[row["cluster_key"]].append(row)
    rng=np.random.default_rng(SEED); boot=[]
    for _ in range(BOOTSTRAP_DRAWS):
        sampled=rng.choice(clusters,size=len(clusters),replace=True); sample=[]
        for c in sampled: sample.extend(by_cluster[str(c)])
        X,y=design(sample,"mean_log_ratio")
        if np.linalg.matrix_rank(X)<4: continue
        boot.append(np.linalg.lstsq(X,y,rcond=None)[0])
    if len(boot)<1900: raise RuntimeError(f"insufficient valid bootstrap draws {len(boot)}")
    ba=np.array(boot)
    ur_ci=np.percentile(ba[:,0],[2.5,97.5]); sir_ci=np.percentile(ba[:,1],[2.5,97.5])
    sir_ur_ci=np.percentile(ba[:,1]-ba[:,0],[2.5,97.5]); scarcity_ci=np.percentile(ba[:,2],[2.5,97.5])

    loo=[]
    for cluster in clusters:
        sample=[x for x in edges if x["cluster_key"]!=cluster]
        b,r,_=fit(sample)
        if r<4: raise RuntimeError(f"LOO rank failure {cluster}")
        loo.append({"cluster_key":cluster,**metrics(b)})

    gates={
        "rank4":rank==4,
        "condition_le_20":condition<=20,
        "scarcity_positive_ci":full["scarcity_beta"]>0 and float(scarcity_ci[0])>0,
        "sir_vs_double_positive_ci":beta[1]>0 and float(sir_ci[0])>0,
        "sir_vs_ultra_positive_ci":(beta[1]-beta[0])>0 and float(sir_ur_ci[0])>0,
        "temporal_signs":early["sir_vs_double"]>1 and early["sir_vs_ultra"]>1 and late["sir_vs_double"]>1 and late["sir_vs_ultra"]>1,
        "loo_signs":all(x["sir_vs_double"]>1 and x["sir_vs_ultra"]>1 for x in loo),
        "sir_double_inside_exploratory_ci":EXPLORATORY["sir_double_interval"][0] <= full["sir_vs_double"] <= EXPLORATORY["sir_double_interval"][1],
        "sir_ultra_inside_exploratory_ci":EXPLORATORY["sir_ultra_interval"][0] <= full["sir_vs_ultra"] <= EXPLORATORY["sir_ultra_interval"][1],
        "scarcity_inside_exploratory_ci":EXPLORATORY["scarcity_interval"][0] <= full["scarcity_beta"] <= EXPLORATORY["scarcity_interval"][1],
    }
    passed=all(gates.values())
    return {
        "study_id":"joint_treatment_ladder_v1_confirmatory_replication",
        "decision_token":"JOINT_TREATMENT_LADDER_V1_REPLICATION_PASS" if passed else "JOINT_TREATMENT_LADDER_V1_REPLICATION_FAIL",
        "coverage":coverage,
        "inputs":{"clusters":len(clusters),"edges":len(edges),"sets":len({x["set_name"] for x in edges}),"eras":len({x["era_name"] for x in edges}),"panel_fingerprint":panel["target"]["fingerprint"],"control_fingerprint":stable_hash(controls)},
        "formula":{"frozen":True,"model":"theta(high)-theta(low)+shared_scarcity*log(p_low/p_high)+artist_delta/100","anchor":"Double Rare=0","bootstrap_draws":BOOTSTRAP_DRAWS,"bootstrap_valid":len(boot)},
        "full_fit":{"rank":rank,"condition_number":condition,**full,
            "ultra_vs_double_ci95":[math.exp(float(ur_ci[0])),math.exp(float(ur_ci[1]))],
            "sir_vs_double_ci95":[math.exp(float(sir_ci[0])),math.exp(float(sir_ci[1]))],
            "sir_vs_ultra_ci95":[math.exp(float(sir_ur_ci[0])),math.exp(float(sir_ur_ci[1]))],
            "scarcity_beta_ci95":[float(scarcity_ci[0]),float(scarcity_ci[1])]},
        "temporal":{"early":early,"late":late},
        "cluster_equal_sensitivity":{"condition_number":equal_condition,**equal},
        "leave_one_cluster_out":loo,"gates":gates,"production_writes":0,
    }

def render(result:dict[str,Any])->str:
    if result["decision_token"]=="JOINT_TREATMENT_LADDER_REPLICATION_INSUFFICIENT_COVERAGE":
        return "# Joint Treatment Ladder V1 Replication\n\nDecision: JOINT_TREATMENT_LADDER_REPLICATION_INSUFFICIENT_COVERAGE\n"
    f=result["full_fit"]; lines=["# Joint Treatment Ladder V1 - Confirmatory Replication","",f"Decision token: {result['decision_token']}","",
        f"- Independent ready triads: **{result['coverage']['ready_triads']}**",
        f"- Ultra Rare / Double Rare: **{f['ultra_vs_double']:.2f}x** (95% {f['ultra_vs_double_ci95'][0]:.2f}-{f['ultra_vs_double_ci95'][1]:.2f})",
        f"- SIR / Double Rare: **{f['sir_vs_double']:.2f}x** (95% {f['sir_vs_double_ci95'][0]:.2f}-{f['sir_vs_double_ci95'][1]:.2f})",
        f"- SIR / Ultra Rare: **{f['sir_vs_ultra']:.2f}x** (95% {f['sir_vs_ultra_ci95'][0]:.2f}-{f['sir_vs_ultra_ci95'][1]:.2f})",
        f"- Shared scarcity beta: **{f['scarcity_beta']:.3f}** (95% {f['scarcity_beta_ci95'][0]:.3f}-{f['scarcity_beta_ci95'][1]:.3f})","","## Frozen gates",""]
    for key,val in result["gates"].items(): lines.append(f"- {key}: **{'PASS' if val else 'FAIL'}**")
    lines += ["","Production writes: **ZERO**.",""]
    return "\n".join(lines)

def main(argv=None):
    p=argparse.ArgumentParser(); p.add_argument("--panel",type=Path,required=True); p.add_argument("--output",type=Path,required=True); p.add_argument("--report",type=Path,required=True); args=p.parse_args(argv)
    panel=json.loads(args.panel.read_text(encoding="utf-8"))
    ready={(x["set_name"],x["subject_key"]) for x in panel["triad_results"] if x["ready"]}
    ready_ids=sorted({card["canonical_card_id"] for triad in panel["target"]["triads"] if (triad["set_name"],triad["subject_key"]) in ready for card in triad["cards"]})
    load_dotenv(ROOT/"backend/.env",override=False)
    from backend.db.clients.supabase_client import supabase
    result=estimate(panel,load_controls(supabase,ready_ids))
    args.output.parent.mkdir(parents=True,exist_ok=True); args.output.write_text(json.dumps(result,indent=2,sort_keys=True)+"\n",encoding="utf-8")
    args.report.parent.mkdir(parents=True,exist_ok=True); args.report.write_text(render(result),encoding="utf-8")
    print(json.dumps({k:v for k,v in result.items() if k!="leave_one_cluster_out"},indent=2,sort_keys=True))
    return 0

if __name__=="__main__": raise SystemExit(main())
