import json, os
import pandas as pd
import numpy as np

D = r"d:\EVRCalculator\backend\research\scratch_pass1a"
pr = json.load(open(os.path.join(D,"pull_rates_all.json")))
sp = json.load(open(os.path.join(D,"sealed_product_results_all.json")))

pr_df = pd.DataFrame(pr)
sp_df = pd.DataFrame(sp)
sp_df["created_at_ts"] = pd.to_datetime(sp_df["created_at"])

sp_loose = sp_df[sp_df.product_family=="loose_booster_pack"].copy()
runs_pr = set(pr_df.calculation_run_id.unique())
sp_loose = sp_loose[sp_loose.calculation_run_id.isin(runs_pr)]

# pick latest run per set (by created_at)
sp_loose = sp_loose.sort_values("created_at_ts")
latest = sp_loose.groupby("set_id").tail(1).copy()
print("Primary cohort sets:", len(latest))
print(sorted(latest.set_id.tolist()))

# Also record price_as_of per row and check same-date coherence
print(latest[["set_id","calculation_run_id","price_as_of","created_at","product_market_cost","random_pack_count","financial_rip_v4_score","financial_rip_v4_status","financial_rip_v4_rankable","collector_appeal_score","collector_appeal_version","overall_rip_v10_score","overall_rip_v10_rankable"]].to_string())

def compute_A_raw(run_id):
    rows = pr_df[pr_df.calculation_run_id==run_id].copy()
    rows = rows[rows.price_used.notna() & rows.modeled_probability.notna()]
    rows["price_used"] = rows["price_used"].astype(float)
    rows["modeled_probability"] = rows["modeled_probability"].astype(float)
    v2 = rows["price_used"]**2
    total_v2 = v2.sum()
    if total_v2 <= 0 or len(rows)==0:
        return None, None, 0, 0.0
    hc = v2/total_v2
    a_raw = float((hc*rows["modeled_probability"]).sum())
    chase_depth = float(1.0/(hc**2).sum()) if (hc**2).sum()>0 else None
    mapped_mass = float(hc.sum())  # should be 1.0 among priced rows; coverage vs all drawable variants tracked separately
    return a_raw, chase_depth, len(rows), mapped_mass

records = []
for _, row in latest.iterrows():
    a_raw, chase_depth, n_variants, mapped_mass = compute_A_raw(row["calculation_run_id"])
    records.append({**row.to_dict(), "A_raw": a_raw, "chase_depth": chase_depth,
                     "n_priced_variants": n_variants, "mapped_hc_mass_priced": mapped_mass})

cohort = pd.DataFrame(records)
cohort = cohort[cohort.A_raw.notna()]
print("\nCohort with valid A_raw:", len(cohort))
print(cohort[["set_id","A_raw","chase_depth","n_priced_variants","financial_rip_v4_score","collector_appeal_score","product_market_cost","random_pack_count"]].to_string())

cohort.to_json(os.path.join(D,"cohort_products.json"), orient="records", indent=2)
