"""Round 6: estimate six locked local contrasts after nuisance reparameterization."""
from __future__ import annotations

import hashlib, json, math
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
from scipy.linalg import qr

from backend.scripts.build_card_treatment_prestige_v2_round5 import MANIFEST_HASH, MAPPING_HASH, STUDY_ID

SEED=20260828
ELIGIBLE={("Mega Evolution","common","rare"),("Mega Evolution","common","uncommon"),("Mega Evolution","rare","uncommon"),
          ("Scarlet and Violet","common","uncommon"),("Scarlet and Violet","rare","uncommon"),("Scarlet and Violet","common","rare")}


def _raw_design(rows,b,scarcity="linear",mechanics=True):
    names=["intercept","treatment_b"];cols=[np.ones(len(rows)),np.asarray([float(r["rarity_designation"]==b) for r in rows])]
    odds=np.asarray([r["log_odds"] for r in rows])
    if scarcity=="linear":names.append("log_exact_pull_scarcity");cols.append(odds)
    else:
        cuts=np.unique(np.quantile(odds,[.25,.5,.75]));bins=np.digitize(odds,cuts)
        for level in range(1,len(cuts)+1):names.append(f"scarcity_stratum:{level}");cols.append((bins==level).astype(float))
    for key,prefix,value in (("set_id","set",lambda r:r["set_id"]),("species","species",lambda r:r["subject_ids"][0])):
        levels=sorted({value(r) for r in rows})
        for level in levels[1:]:names.append(f"{prefix}:{level}");cols.append(np.asarray([float(value(r)==level) for r in rows]))
    if mechanics:
        levels=sorted({str(r.get("mechanic_or_card_form") or "__unknown__") for r in rows})
        for level in levels[1:]:names.append(f"mechanic:{level}");cols.append(np.asarray([float(str(r.get("mechanic_or_card_form") or "__unknown__")==level) for r in rows]))
    return np.column_stack(cols),names


def reparameterize(rows,b,scarcity="linear",mechanics=True,weights=None):
    raw,names=_raw_design(rows,b,scarcity,mechanics);t=raw[:,1];N=np.delete(raw,1,axis=1);nn=names[:1]+names[2:]
    _,R,piv=qr(N,mode="economic",pivoting=True);tol=max(N.shape)*abs(R[0,0])*np.finfo(float).eps
    nrank=int(np.sum(np.abs(np.diag(R))>tol));keep=sorted(piv[:nrank]);removed=[nn[i] for i in range(len(nn)) if i not in keep]
    X=np.column_stack([t,N[:,keep]]);columns=["treatment_b"]+[nn[i] for i in keep]
    w=np.ones(len(rows)) if weights is None else np.asarray(weights,float);root=np.sqrt(w);Xw=X*root[:,None]
    rank=int(np.linalg.matrix_rank(Xw));residual=t-N[:,keep]@np.linalg.lstsq(N[:,keep],t,rcond=None)[0]
    estimable=rank==X.shape[1] and float(residual@residual)>1e-10
    y=np.asarray([math.log(r["price"]) for r in rows]);beta=np.linalg.lstsq(Xw,y*root,rcond=None)[0];u=y-X@beta
    s=np.linalg.svd(Xw,compute_uv=False)
    return {"X":X,"y":y,"weights":w,"beta":beta,"resid":u,"coefficient":float(beta[0]) if estimable else None,
        "rank":rank,"columns":X.shape[1],"raw_columns":raw.shape[1],"condition_number":float(s[0]/s[-1]),
        "residual_treatment_variance":float(np.var(residual)),"treatment_estimable":estimable,"kept_columns":columns,
        "removed_columns":[{"column":x,"classification":"NUISANCE_REDUNDANCY_REMOVED"} for x in removed],
        "column_space_proof":{"nuisance_rank_before":int(np.linalg.matrix_rank(N)),"nuisance_rank_after":int(np.linalg.matrix_rank(N[:,keep])),
            "max_projection_error":float(np.max(np.abs(N-N[:,keep]@np.linalg.lstsq(N[:,keep],N,rcond=None)[0]))),
            "treatment_not_in_nuisance_span":bool(estimable)}}


def wild_ci(fit,rows,draws,seed):
    X,w,beta,u=fit["X"],fit["weights"],fit["beta"],fit["resid"];root=np.sqrt(w);Xw=X*root[:,None]
    bread=np.linalg.inv(Xw.T@Xw);clusters=sorted({r["set_id"] for r in rows});rng=np.random.default_rng(seed);samples=[]
    for _ in range(draws):
        signs={c:rng.choice((-1.,1.)) for c in clusters};uw=np.asarray([u[i]*signs[r["set_id"]] for i,r in enumerate(rows)])*root
        samples.append(float((beta+bread@(Xw.T@uw))[0]))
    return {"method":"Rademacher wild cluster bootstrap","cluster_unit":"set","clusters":len(clusters),"draws":draws,
        "ci_low":float(np.quantile(samples,.025)),"ci_high":float(np.quantile(samples,.975))}


def coefficient(rows,b,**kwargs):
    fit=reparameterize(rows,b,**kwargs);return fit["coefficient"] if fit["treatment_estimable"] else None


def estimate_pair(pair,mapping,draws,index):
    a,b=pair["treatment_a"],pair["treatment_b"];low,high=pair["overlap_interval_log_odds"]
    rows=[r for r in mapping if r.get("price") and r["price"]>0 and len(r.get("subject_ids") or [])==1 and r["era_id"]==pair["era_id"]
          and r["rarity_designation"] in {a,b} and low<=r["log_odds"]<=high]
    counts=Counter(r["rarity_designation"] for r in rows);fit=reparameterize(rows,b)
    base={"era":pair["era"],"era_id":pair["era_id"],"treatment_a":a,"treatment_b":b,"n":len(rows),"n_a":counts[a],"n_b":counts[b],
        "sets":len({r["set_id"] for r in rows}),"species":len({r["subject_ids"][0] for r in rows}),"exact_pull_scarcity_overlap":[low,high],
        "reparameterization":{k:fit[k] for k in ("raw_columns","columns","rank","condition_number","residual_treatment_variance","removed_columns","column_space_proof")}}
    if not fit["treatment_estimable"]:return {**base,"status":"LOCAL_EFFECT_UNIDENTIFIED"}
    ci=wild_ci(fit,rows,draws,SEED+index);primary=fit["coefficient"]
    flexible=coefficient(rows,b,scarcity="strata");no_mechanics=coefficient(rows,b,mechanics=False)
    species_prices=defaultdict(list)
    for r in rows:species_prices[r["subject_ids"][0]].append(r["price"])
    cutoff=float(np.quantile([np.median(x) for x in species_prices.values()],.95))
    demand_rows=[r for r in rows if np.median(species_prices[r["subject_ids"][0]])<=cutoff];demand=coefficient(demand_rows,b)
    cuts=np.unique(np.quantile([r["log_odds"] for r in rows],[.2,.4,.6,.8]));bins=np.digitize([r["log_odds"] for r in rows],cuts)
    cells=Counter((bins[i],r["rarity_designation"]) for i,r in enumerate(rows));weights=[1/cells[(bins[i],r["rarity_designation"])] for i,r in enumerate(rows)]
    balanced=coefficient(rows,b,weights=weights)
    loo=[]
    for sid in sorted({r["set_id"] for r in rows}):
        subset=[r for r in rows if r["set_id"]!=sid];value=coefficient(subset,b)
        loo.append({"excluded_set_id":sid,"coefficient":value,"estimable":value is not None,"sign":None if value is None else (1 if value>0 else -1 if value<0 else 0)})
    rng=np.random.default_rng(SEED+1000+index);permuted=[]
    # The nuisance column space is invariant under label permutation.  Apply
    # Frisch-Waugh-Lovell with one cached orthonormal nuisance basis instead of
    # recomputing pivoted QR 199 times.
    nuisance=fit["X"][:,1:];q,_=np.linalg.qr(nuisance,mode="reduced");y=fit["y"];y_residual=y-q@(q.T@y)
    original_labels=np.asarray([r["rarity_designation"] for r in rows],dtype=object)
    for _ in range(199):
        labels=original_labels.copy();strata=defaultdict(list)
        for i,r in enumerate(rows):strata[(r["set_id"],bins[i])].append(i)
        for ids in strata.values():
            shuffled=labels[ids].copy();rng.shuffle(shuffled);labels[ids]=shuffled
        t=(labels==b).astype(float);t_residual=t-q@(q.T@t);denominator=float(t_residual@t_residual)
        if denominator>1e-10:permuted.append(float((t_residual@y_residual)/denominator))
    p=(1+sum(abs(x)>=abs(primary) for x in permuted))/(1+len(permuted)) if permuted else None
    values=[flexible,no_mechanics,demand,balanced];sign=lambda x:1 if x>0 else -1 if x<0 else 0
    stable=all(x is not None and sign(x)==sign(primary) and abs(x-primary)<=.5 for x in values)
    loo_stable=all(x["estimable"] and x["sign"]==sign(primary) and abs(x["coefficient"]-primary)<=.5 for x in loo)
    return {**base,"coefficient_log_price_b_vs_a":primary,"adjusted_price_association_pct":100*math.expm1(primary),
        "wild_cluster_inference":ci,"leave_one_set_out":loo,"scarcity_strata_coefficient":flexible,
        "demand_outlier_coefficient":demand,"demand_outlier_rule":"remove species above the 95th percentile of within-sample median price (locked B2 sensitivity; not an independent demand control)",
        "mechanics_sensitivity_without_controls":no_mechanics,"mechanics_sensitivity_interpretation":"secondary sensitivity only; primary estimand retains mechanics",
        "balance_weighted_coefficient":balanced,"permutation_placebo":{"draws":len(permuted),"raw_p_value":p},
        "robustness":{"sensitivity_stable":stable,"leave_one_set_out_stable":loo_stable,"wild_ci_excludes_zero":ci["ci_low"]>0 or ci["ci_high"]<0},
        "status_pre_multiplicity":"CANDIDATE_VALIDATED" if stable and loo_stable and (ci["ci_low"]>0 or ci["ci_high"]<0) and p is not None else "LOCAL_EFFECT_UNCERTAIN"}


def holm(results):
    valid=sorted([(r["permutation_placebo"]["raw_p_value"],i) for i,r in enumerate(results) if r.get("permutation_placebo")],key=lambda x:x[0]);running=0
    for rank,(p,i) in enumerate(valid):
        adjusted=max(running,min(1.,p*(len(valid)-rank)));running=adjusted;results[i]["permutation_placebo"]["holm_adjusted_p_value"]=adjusted
    for r in results:
        if r.get("status_pre_multiplicity")=="CANDIDATE_VALIDATED" and r["permutation_placebo"].get("holm_adjusted_p_value",1)<.05:r["status"]="LOCALLY_VALIDATED"
        elif r.get("status") is None:r["status"]="LOCAL_EFFECT_UNCERTAIN"


def freeze_demand(client,outdir):
    rows=[]
    for start in range(0,5000,500):
        batch=client.table("pokemon_desirability_composite_scores").select("pokemon_reference_id,pokedex_number,pokemon_name,desirability_score,fan_popularity_score,current_trend_score,scoring_version,created_at,fan_popularity_snapshot_id,current_trend_snapshot_id,score_components_json").range(start,start+499).execute().data or []
        rows+=batch
        if len(batch)<500:break
    rows=sorted(rows,key=lambda r:int(r["pokemon_reference_id"]));payload=json.dumps(rows,sort_keys=True,separators=(",",":"),ensure_ascii=True);digest=hashlib.sha256(payload.encode()).hexdigest()
    snapshot_id=f"pokemon-demand-v1-{digest[:16]}";outdir.mkdir(parents=True,exist_ok=True)
    (outdir/"rows.json").write_text(json.dumps({"snapshot_id":snapshot_id,"rows":rows},indent=2),encoding="utf-8")
    manifest={"snapshot_id":snapshot_id,"sha256":digest,"rows":len(rows),"frozen_at":datetime.now(timezone.utc).isoformat(),
        "source_table":"pokemon_desirability_composite_scores","scoring_versions":sorted({r["scoring_version"] for r in rows}),
        "build_timestamps":sorted({r["created_at"] for r in rows}),"fan_snapshot_ids":sorted({r["fan_popularity_snapshot_id"] for r in rows}),
        "trend_snapshot_ids":sorted({r["current_trend_snapshot_id"] for r in rows if r.get("current_trend_snapshot_id") is not None}),
        "uses_card_market_price":False,"uses_rarity_or_treatment":False}
    (outdir/"manifest.json").write_text(json.dumps(manifest,indent=2),encoding="utf-8");return manifest


def main():
    root=Path("docs/research");study_path=root/"card_treatment_prestige_v2_study.json";study=json.loads(study_path.read_text());mapping=json.loads((root/"card_treatment_prestige_v2_frozen_cohort/canonical_mapping.json").read_text())
    assert study["round5"]["frozen_study_id"]==STUDY_ID and study["round5"]["manifest_hash"]==MANIFEST_HASH and study["round5"]["canonical_mapping_hash"]==MAPPING_HASH
    pairs=[p for p in study["round4"]["pair_results"] if (p["era"],p["treatment_a"],p["treatment_b"]) in ELIGIBLE]
    results=[estimate_pair(p,mapping["rows"],1000,i) for i,p in enumerate(pairs)];holm(results)
    from dotenv import load_dotenv
    load_dotenv(Path("backend/.env"));from backend.db.clients.supabase_client import create_service_role_client
    demand=freeze_demand(create_service_role_client(),root/"card_treatment_prestige_v2_demand_snapshot")
    validated=sum(r["status"]=="LOCALLY_VALIDATED" for r in results);status="LOCAL_RARITY_DESIGNATION_EFFECTS_VALIDATED" if validated else "NO_LOCAL_RARITY_DESIGNATION_EFFECTS_VALIDATED"
    study["round6"]={"status":status,"universal_decision":"DO_NOT_APPROVE_CARD_TREATMENT_PRESTIGE_V2","frozen_study_id":STUDY_ID,
        "manifest_hash":MANIFEST_HASH,"canonical_mapping_hash":MAPPING_HASH,"eligible_contrasts":results,"locally_validated_count":validated,
        "multiple_testing":{"method":"Holm family-wise correction applied to six preregistered permutation p-values","family_size":6,"alpha":.05},
        "scientifically_nested_contrasts":[x for x in study["round5"]["contrast_diagnostics"] if x["rank_failure_classification"]=="scientific_nesting"],
        "high_product_relevance_status":"scientifically unidentified; no coefficients estimated in Round 6",
        "frozen_demand_snapshot":demand,"database_rows_persisted":0,"production_scores_published":0,
        "next_direction":"PRESERVE_LOCAL_V2_EVIDENCE_NO_PRODUCT_SCORE" if validated else "RETIRE_V2_AND_ENTER_TREATMENT_MARKET_PRESTIGE_V3"}
    study["decision"]="DO_NOT_APPROVE_CARD_TREATMENT_PRESTIGE_V2";study_path.write_text(json.dumps(study,indent=2),encoding="utf-8")
    print(json.dumps({"status":status,"validated":validated,"demand_snapshot_id":demand["snapshot_id"],"demand_hash":demand["sha256"]},indent=2))


if __name__=="__main__":main()
