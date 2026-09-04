import json, os
import pandas as pd
import numpy as np

D = r"d:\EVRCalculator\backend\research\scratch_pass1a"
pr = json.load(open(os.path.join(D,"pull_rates_all.json")))
sp = json.load(open(os.path.join(D,"sealed_product_results_all.json")))

pr_df = pd.DataFrame(pr)
sp_df = pd.DataFrame(sp)
print("pull_rates run ids:", pr_df.calculation_run_id.nunique())
print("sealed_product run ids:", sp_df.calculation_run_id.nunique())
print("sp product_family values:", sp_df.product_family.value_counts())

# find overlap: runs present in BOTH tables (same calculation_run_id)
runs_pr = set(pr_df.calculation_run_id.unique())
runs_sp = set(sp_df.calculation_run_id.unique())
overlap = runs_pr & runs_sp
print("overlap run count:", len(overlap))

# for sealed product rows, keep only loose_booster_pack (has pack_count->random_pack_count meaningful and matches per-variant pull model)
sp_loose = sp_df[sp_df.product_family=="loose_booster_pack"].copy()
print("loose rows:", len(sp_loose))
print("loose rows with run in pull_rates overlap:", sp_loose.calculation_run_id.isin(runs_pr).sum())

sp_loose_ok = sp_loose[sp_loose.calculation_run_id.isin(runs_pr)]
print("sets covered:", sp_loose_ok.set_id.nunique())
print(sp_loose_ok[["set_id","calculation_run_id","product_market_cost","random_pack_count","financial_rip_v4_score","collector_appeal_score","overall_rip_v10_score","price_as_of","created_at"]].head(20))
