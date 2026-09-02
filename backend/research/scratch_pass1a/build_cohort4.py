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

# Track A: latest run per set WITH pull_rates (Accessibility-capable)
a_track = sp_loose[sp_loose.calculation_run_id.isin(runs_pr)].sort_values("created_at_ts").groupby("set_id").tail(1)
# Track B: latest run per set WITH collector_appeal+overall_rip_v10 (Financial/Collector-capable), regardless of pull_rates presence
b_track = sp_loose[sp_loose.collector_appeal_score.notna() & sp_loose.overall_rip_v10_score.notna()].sort_values("created_at_ts").groupby("set_id").tail(1)

print("Track A (Accessibility-capable) sets:", a_track.set_id.nunique())
print("Track B (Financial/Collector-capable) sets:", b_track.set_id.nunique())
common_sets = set(a_track.set_id) & set(b_track.set_id)
print("Common sets:", len(common_sets))

a_idx = a_track.set_index("set_id")
b_idx = b_track.set_index("set_id")
rows=[]
for s in common_sets:
    ra, rb = a_idx.loc[s], b_idx.loc[s]
    rows.append({
        "set_id": s,
        "run_A": ra["calculation_run_id"], "date_A": str(ra["created_at_ts"]),
        "run_B": rb["calculation_run_id"], "date_B": str(rb["created_at_ts"]),
        "offset_days": (ra["created_at_ts"]-rb["created_at_ts"]).total_seconds()/86400.0,
        "cost_A": ra["product_market_cost"], "cost_B": rb["product_market_cost"],
    })
off_df = pd.DataFrame(rows)
print(off_df.to_string())
print("\noffset_days stats:", off_df.offset_days.describe())
