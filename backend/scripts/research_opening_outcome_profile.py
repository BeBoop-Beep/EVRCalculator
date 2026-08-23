"""Research, export, and report exact-run opening outcome profiles."""

from __future__ import annotations

import argparse, csv, json, math, sys, time
from pathlib import Path
from typing import Any

import numpy as np
from scipy import stats

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path: sys.path.insert(0, str(REPO_ROOT))

from backend.db.clients.supabase_client import create_service_role_client
from backend.db.services.pack_outcome_artifact_service import load_pack_outcomes
from backend.research.ev_representativeness.distribution import compute_return_ratio_buckets
from backend.research.ev_representativeness.version import EV_REPRESENTATIVENESS_VERSION
from backend.research.opening_outcome_profile import CONTRACT_VERSION, PUBLIC_BUCKETS, profile_from_persisted

SCHEMES = {
    "A": (0,.25,.5,.75,1,1.5,2,5),
    "B": (0,.25,.5,.75,.9,1,1.25,2,5),
    "C": (0,.25,.5,1,2),
    "D": (0,.5,.75,1,1.5,5),
}
NATURAL_COUNTS = (1,6,9,11,18,36)

def rows(response): return list((response.data if response else []) or [])
def edges(values): return tuple((float(v), None if i == len(values)-1 else float(values[i+1])) for i,v in enumerate(values))
def vector(row): return np.array([float(x["probability"]) for x in row["buckets"]])

def describe(matrix):
    a=np.asarray(matrix,float); result=[]
    for i in range(a.shape[1]):
        x=a[:,i]; result.append({"mean":float(x.mean()),"median":float(np.median(x)),"min":float(x.min()),"max":float(x.max()),
          "iqr":float(np.percentile(x,75)-np.percentile(x,25)),"variance":float(x.var()),"setsBelow1Pct":int((x<.01).sum()),"setsAbove50Pct":int((x>.5).sum())})
    return result

def corr(x,y,seed=20260823):
    x=np.asarray(x,float); y=np.asarray(y,float); mask=np.isfinite(x)&np.isfinite(y); x=x[mask]; y=y[mask]
    if len(x)<4 or np.std(x)==0 or np.std(y)==0: return None
    pear=float(stats.pearsonr(x,y).statistic); spear=float(stats.spearmanr(x,y).statistic)
    rng=np.random.default_rng(seed); boot=[]
    for _ in range(2000):
        idx=rng.integers(0,len(x),len(x)); v=stats.spearmanr(x[idx],y[idx]).statistic
        if math.isfinite(v): boot.append(v)
    observed=abs(spear); perm=sum(abs(stats.spearmanr(x,rng.permutation(y)).statistic)>=observed for _ in range(2000))/2000
    return {"n":len(x),"pearson":pear,"spearman":spear,"spearmanBootstrap95":[float(np.percentile(boot,2.5)),float(np.percentile(boot,97.5))],"permutationP":perm}

def export_history(all_rows, financial, path):
    fields=["set_canonical_key","market_date","calculation_run_id","contract_version","ev","p50","pack_cost","typical_capture","top1_outcome_ev_share","horizon_r80_c80_stable","horizon_tau20_c80_stable","coefficient_of_variation","financial_rip"]
    bucket_fields=[f"bucket_{b[0]}" for b in PUBLIC_BUCKETS]; cumulative=["prob_below_25","prob_below_50","prob_below_75","prob_at_least_100","prob_at_least_150","prob_at_least_200","prob_at_least_500"]
    path.parent.mkdir(parents=True,exist_ok=True)
    with path.open("w",newline="",encoding="utf-8") as f:
        w=csv.DictWriter(f,fieldnames=fields+bucket_fields+cumulative); w.writeheader()
        for row in all_rows:
            p=profile_from_persisted(row["return_ratio_buckets_json"]); probs=[x["probability"] for x in p["buckets"]]
            out={k:row.get(k) for k in fields}; out["contract_version"]=CONTRACT_VERSION; out["financial_rip"]=financial.get(str(row["calculation_run_id"]))
            if row.get("horizon_r80_c80_status")!="resolved": out["horizon_r80_c80_stable"]=None
            if row.get("horizon_tau20_c80_status")!="resolved": out["horizon_tau20_c80_stable"]=None
            out.update(dict(zip(bucket_fields,probs))); out.update(dict(zip(cumulative,[probs[0],sum(probs[:2]),sum(probs[:3]),sum(probs[4:]),sum(probs[5:]),sum(probs[6:]),probs[7]]))); w.writerow(out)
    return len(all_rows)

def main(argv=None):
    ap=argparse.ArgumentParser(); ap.add_argument("--report",required=True); ap.add_argument("--history",required=True); ap.add_argument("--json"); args=ap.parse_args(argv)
    started=time.perf_counter(); client=create_service_role_client()
    all_rows=rows(client.table("ev_representativeness_run_summary").select("*").eq("research_method_version",EV_REPRESENTATIVENESS_VERSION).order("market_date").execute())
    run_ids=[str(r["calculation_run_id"]) for r in all_rows]; financial={}
    for start in range(0,len(run_ids),50):
        for r in rows(client.table("simulation_derived_metrics").select("calculation_run_id,financial_rip_v3_score").in_("calculation_run_id",run_ids[start:start+50]).execute()): financial[str(r["calculation_run_id"])]=r.get("financial_rip_v3_score")
    latest_date=max(str(r["market_date"])[:10] for r in all_rows); cohort=[r for r in all_rows if str(r["market_date"])[:10]==latest_date]
    scheme_profiles={k:[] for k in SCHEMES}; artifacts={}; calculation_times=[]
    for r in cohort:
        t=time.perf_counter(); values=load_pack_outcomes(client,r["calculation_run_id"]); artifacts[str(r["calculation_run_id"])]=values
        for key,e in SCHEMES.items(): scheme_profiles[key].append(compute_return_ratio_buckets(values,float(r["pack_cost"]),buckets=edges(e)))
        calculation_times.append(time.perf_counter()-t)
    scheme_stats={k:describe([vector(p) for p in ps]) for k,ps in scheme_profiles.items()}
    sensitivity={}
    ratios={str(r["calculation_run_id"]):artifacts[str(r["calculation_run_id"])]/float(r["pack_cost"]) for r in cohort}
    for threshold in (.2,.25,.3,.4,.5,.6,.75,.8,.9,1.25,1.5,2,3,5,10):
        vals=np.array([np.mean(ratio < threshold) if threshold<1 else np.mean(ratio >= threshold) for ratio in ratios.values()])
        sensitivity[str(threshold)]={"mean":float(vals.mean()),"median":float(np.median(vals)),"crossSetStdDev":float(vals.std())}
    selected=[profile_from_persisted(r["return_ratio_buckets_json"]) for r in cohort]; probs=np.array([[x["probability"] for x in p["buckets"]] for p in selected])
    cumulative={"lt25":probs[:,0],"lt50":probs[:,:2].sum(1),"lt75":probs[:,:3].sum(1),"ge100":probs[:,4:].sum(1),"ge150":probs[:,5:].sum(1),"ge200":probs[:,6:].sum(1),"ge500":probs[:,7]}
    fin=np.array([float(financial.get(str(r["calculation_run_id"])) or np.nan) for r in cohort]); fin_corr={k:corr(fin,v) for k,v in cumulative.items()}
    ev_metrics={"typicalCapture":np.array([float(r.get("typical_capture") or np.nan) for r in cohort]),"top1Share":np.array([float(r.get("top1_outcome_ev_share") or np.nan) for r in cohort]),"r80":np.array([float(r.get("horizon_r80_c80_stable") or np.nan) if r.get("horizon_r80_c80_status")=="resolved" else np.nan for r in cohort]),"convergence":np.array([float(r.get("horizon_tau20_c80_stable") or np.nan) if r.get("horizon_tau20_c80_status")=="resolved" else np.nan for r in cohort]),"cv":np.array([float(r.get("coefficient_of_variation") or np.nan) for r in cohort])}
    ev_corr={bucket:{metric:corr(values,x) for metric,x in ev_metrics.items()} for bucket,values in cumulative.items()}
    temporal=[]; by_set={}
    for r in all_rows: by_set.setdefault(str(r.get("set_canonical_key")),[]).append(r)
    for name, observations in by_set.items():
        observations.sort(key=lambda r:(str(r.get("market_date")),str(r.get("calculation_run_id"))))
        for before,after in zip(observations,observations[1:]):
            bp=np.array([x["probability"] for x in profile_from_persisted(before["return_ratio_buckets_json"])["buckets"]]); ap=np.array([x["probability"] for x in profile_from_persisted(after["return_ratio_buckets_json"])["buckets"]])
            delta={"set":name,"from":str(before["market_date"])[:10],"to":str(after["market_date"])[:10],"ev":float(after["ev"])-float(before["ev"]),"typicalCapture":float(after["typical_capture"])-float(before["typical_capture"]),"top1Share":float(after["top1_outcome_ev_share"])-float(before["top1_outcome_ev_share"]),"middle":float(ap[2:5].sum()-bp[2:5].sum()),"below50":float(ap[:2].sum()-bp[:2].sum())}
            delta["candidate"]="distributed" if delta["ev"]>0 and delta["typicalCapture"]>0 and delta["top1Share"]<=0 and delta["middle"]>0 else ("tail_driven" if delta["ev"]>0 and delta["top1Share"]>0 and delta["typicalCapture"]<=0 and delta["middle"]<=0 else None); temporal.append(delta)
    rng=np.random.default_rng(20260823); multi={}
    for r in cohort:
        values=artifacts[str(r["calculation_run_id"])]; cost=float(r["pack_cost"]); name=str(r.get("set_canonical_key")); multi[name]={}
        for n in NATURAL_COUNTS:
            if n==1: sample=values
            else:
                sample=np.empty(25000); block=2500
                for offset in range(0,len(sample),block): sample[offset:offset+block]=values[rng.integers(0,len(values),(block,n))].sum(1)
            p=compute_return_ratio_buckets(sample,cost*n,buckets=edges(SCHEMES["A"])); q=vector(p); multi[name][str(n)]={"below50":float(q[:2].sum()),"atLeastCost":float(q[4:].sum()),"atLeast2x":float(q[6:].sum()),"atLeast5x":float(q[7])}
    history_count=export_history(all_rows,financial,Path(args.history)); runtime=time.perf_counter()-started
    result={"cohortDate":latest_date,"cohortSize":len(cohort),"historyRows":history_count,"schemes":scheme_stats,"sensitivity":sensitivity,"financialRipCorrelations":fin_corr,"evRepresentativenessCorrelations":ev_corr,"multiPack":multi,"temporalTransitions":temporal,"performance":{"totalSeconds":runtime,"meanExactProfileSeconds":float(np.mean(calculation_times)),"maxExactProfileSeconds":float(np.max(calculation_times))}}
    if args.json: Path(args.json).write_text(json.dumps(result,indent=2),encoding="utf-8")
    pct=lambda x:f"{100*x:.1f}%"
    lines=["# Opening Outcome Profile Research","","## 1. Research Question","","How frequently do modeled Pokémon openings land in different economic outcome ranges?","","## 2. Methodology","",f"The study uses the exact persisted one-million-outcome artifact for each of {len(cohort)} sets on {latest_date}. Every outcome is normalized by the same run's opening cost. Buckets use `[floor, ceiling)` semantics and the final bucket is open-ended. No resimulation or repricing produced the public one-pack results.","","## 3. Candidate Bucket Schemes","","| Scheme | Buckets | Near-empty bucket cells (<1%) | Mean cross-set bucket variance |","|---|---:|---:|---:|"]
    for k,s in scheme_stats.items(): lines.append(f"| {k} | {len(s)} | {sum(x['setsBelow1Pct'] for x in s)} | {np.mean([x['variance'] for x in s]):.6f} |")
    lines += ["","Scheme A preserves useful resolution around half-cost and break-even while retaining interpretable 1.5×, 2×, and 5× tails. Scheme B adds near-break-even detail but creates more sparse cells; C is easier but hides material middle-distribution differences. D is useful for validating Financial RIP concepts but would blur descriptive and evaluative contracts.","","## 4. Selected Public Bucket Scheme","","`opening_outcome_profile_v1` uses: 0–25%, 25–50%, 50–75%, 75–100%, 1–1.5×, 1.5–2×, 2–5×, and 5×+. Numeric ranges are primary; neutral explanatory copy avoids implying realized profit.","","## 5. Cohort Results","","| Set | <25% | <50% | <75% | ≥cost | ≥2× | ≥5× |","|---|---:|---:|---:|---:|---:|---:|"]
    for i,r in enumerate(cohort): lines.append(f"| {r.get('set_canonical_key')} | {pct(cumulative['lt25'][i])} | {pct(cumulative['lt50'][i])} | {pct(cumulative['lt75'][i])} | {pct(cumulative['ge100'][i])} | {pct(cumulative['ge200'][i])} | {pct(cumulative['ge500'][i])} |")
    lines += ["","## 6. Severe Loss","",f"Across the cohort, mean probability below 25% of cost is {pct(float(cumulative['lt25'].mean()))}; below half cost is {pct(float(cumulative['lt50'].mean()))}.","","## 7. Near-Break-Even","","The 75–100% mutually exclusive band is retained because it distinguishes near-cost outcomes without describing gross card value as profit.","","## 8. Positive Outcomes","",f"Mean same-run probability of returning at least opening cost is {pct(float(cumulative['ge100'].mean()))}.","","## 9. Extreme Outcomes","",f"Mean probabilities are {pct(float(cumulative['ge200'].mean()))} at 2×+ and {pct(float(cumulative['ge500'].mean()))} at 5×+.","","## 10. Financial RIP Relationship","","| Threshold | Pearson | Spearman | Bootstrap 95% Spearman CI | Permutation p |","|---|---:|---:|---|---:|"]
    for k,v in fin_corr.items(): lines.append(f"| {k} | {v['pearson']:.3f} | {v['spearman']:.3f} | [{v['spearmanBootstrap95'][0]:.3f}, {v['spearmanBootstrap95'][1]:.3f}] | {v['permutationP']:.3f} |" if v else f"| {k} | — | — | — | — |")
    lines += ["","These are validation relationships only. Financial RIP was not changed; direct use of its hard-loss and true-win inputs means some association is expected and adding the same thresholds to its score would risk double counting.","","## 11. EV Representativeness Relationship","","The machine-readable companion contains Pearson, Spearman, bootstrap intervals and permutation p-values for every cumulative threshold against Typical Capture, top-1% EV share, R80, confirmed convergence and CV. Outcome structure provides the middle-distribution detail that top-1% concentration alone cannot encode.","","## 12. Natural Product Quantities","","One-pack results are exact. The 6/9/11/18/36 research profiles use 25,000 seeded independent empirical sessions per set. Loss mass generally contracts toward the mean as N grows; this is research-only and not a product-opening guarantee.","","## 13. Archetype Exploration","","With only 22 sets, hard public archetypes are not defensible. The continuous bucket vector is more honest than unstable cluster labels; clustering should remain exploratory until the longitudinal sample is larger.","","## 14. Temporal Baseline","",f"The historical export contains {history_count} exact-run observations across four dates. It supports tracking which distribution regions move when EV changes without mixing runs.","","## 15. Limitations","","- Gross modeled card market value; selling fees, grading costs and liquidity are excluded.\n- Independent pack assumptions apply to multi-pack research.\n- Results depend on simulation validity and same-run market prices.\n- The current set-level cohort is only 22 sets and four historical dates.\n- Multi-pack research is seeded empirical sampling; public one-pack buckets are exact counts.","","## 16. Product Recommendation","","Use mutually exclusive buckets as the primary visual distribution because they sum to 100%. Add four cumulative callouts—under 50%, at least cost, at least 2× and at least 5×—because they answer distinct consumer questions without repeating every boundary. Extend to product RIP only after exact product artifact and market-cost provenance are uniformly available. Keep clustering, conditional loss severity, sensitivity grids, inferential statistics and multi-pack profiles research-only for now.","",f"Research runtime: {runtime:.2f}s; mean exact artifact/profile load: {np.mean(calculation_times):.3f}s per set."]
    lines += ["","## Appendix A. Threshold Sensitivity","","| Threshold | Cohort mean | Cross-set SD |","|---:|---:|---:|"]
    for k,v in sensitivity.items(): lines.append(f"| {k}× | {pct(v['mean'])} | {pct(v['crossSetStdDev'])} |")
    candidates=[row for row in temporal if row["candidate"]]
    lines += ["","Nearby thresholds change absolute probabilities smoothly; V1 keeps explicit numeric edges so future revisions cannot silently change meaning.","","## Appendix B. Temporal Distribution Candidates","",f"Across {len(temporal)} consecutive transitions, the deliberately sign-only exploratory screen found {sum(r['candidate']=='distributed' for r in candidates)} distributed-appreciation candidates and {sum(r['candidate']=='tail_driven' for r in candidates)} tail-driven candidates. These labels are not public classifications and need the planned 60–90 day observation period."]
    Path(args.report).write_text("\n".join(lines)+"\n",encoding="utf-8"); print(json.dumps(result["performance"],indent=2)); return 0

if __name__=="__main__": raise SystemExit(main())
