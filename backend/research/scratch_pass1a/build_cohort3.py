import json, os
import pandas as pd
import numpy as np

D = r"d:\EVRCalculator\backend\research\scratch_pass1a"
pr = json.load(open(os.path.join(D,"pull_rates_all.json")))
sp = json.load(open(os.path.join(D,"sealed_product_results_all.json")))

pr_df = pd.DataFrame(pr)
sp_df = pd.DataFrame(sp)
sp_df["created_at_ts"] = pd.to_datetime(sp_df["created_at"])
runs_pr = set(pr_df.calculation_run_id.unique())

sp_loose = sp_df[sp_df.product_family=="loose_booster_pack"].copy()
sp_loose = sp_loose[sp_loose.calculation_run_id.isin(runs_pr)]
print("loose+pull_rates-run overlap:", len(sp_loose))
coherent = sp_loose[sp_loose.collector_appeal_score.notna() & sp_loose.overall_rip_v10_score.notna()].copy()
print("also collector_appeal+overall_rip_v10 populated:", len(coherent), "sets:", coherent.set_id.nunique())

coherent = coherent.sort_values("created_at_ts")
latest = coherent.groupby("set_id").tail(1).copy()
print("Primary FULLY-COHERENT cohort sets:", len(latest))
print(latest[["set_id","calculation_run_id","price_as_of","product_market_cost","pack_count","financial_rip_v4_score","collector_appeal_score","overall_rip_v10_score","overall_rip_v10_rankable"]].to_string())

def compute_A_raw(run_id):
    rows = pr_df[pr_df.calculation_run_id==run_id].copy()
    rows = rows[rows.price_used.notna() & rows.modeled_probability.notna()]
    rows["price_used"] = rows["price_used"].astype(float)
    rows["modeled_probability"] = rows["modeled_probability"].astype(float)
    v2 = rows["price_used"]**2
    total_v2 = v2.sum()
    if total_v2 <= 0 or len(rows)==0:
        return None, None, 0
    hc = v2/total_v2
    a_raw = float((hc*rows["modeled_probability"]).sum())
    chase_depth = float(1.0/(hc**2).sum())
    return a_raw, chase_depth, len(rows)

records = []
for _, row in latest.iterrows():
    a_raw, chase_depth, n_variants = compute_A_raw(row["calculation_run_id"])
    d = row.to_dict()
    d["A_raw"] = a_raw
    d["chase_depth"] = chase_depth
    d["n_priced_variants"] = n_variants
    records.append(d)

cohort = pd.DataFrame(records)
cohort = cohort[cohort.A_raw.notna()]
print("\nFinal cohort n=", len(cohort))
print(cohort[["set_id","A_raw","chase_depth","financial_rip_v4_score","collector_appeal_score","overall_rip_v10_score","product_market_cost","pack_count","price_as_of"]].to_string())

# save
cohort.to_json(os.path.join(D,"cohort_final.json"), orient="records")
with open(os.path.join(D,"cohort_final.json"),"w") as f:
    json.dump(json.loads(cohort.to_json(orient="records")), f, indent=2)
