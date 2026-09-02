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

a_track = sp_loose[sp_loose.calculation_run_id.isin(runs_pr)].sort_values("created_at_ts").groupby("set_id").tail(1).set_index("set_id")
b_track = sp_loose[sp_loose.collector_appeal_score.notna() & sp_loose.overall_rip_v10_score.notna()].sort_values("created_at_ts").groupby("set_id").tail(1).set_index("set_id")
common = sorted(set(a_track.index) & set(b_track.index))

def variant_rows(run_id):
    rows = pr_df[pr_df.calculation_run_id==run_id].copy()
    rows = rows[rows.price_used.notna() & rows.modeled_probability.notna()]
    rows["price_used"]=rows["price_used"].astype(float)
    rows["modeled_probability"]=rows["modeled_probability"].astype(float)
    return rows

records=[]
variant_store={}
for s in common:
    ra = a_track.loc[s]; rb = b_track.loc[s]
    rows = variant_rows(ra["calculation_run_id"])
    v2 = rows["price_used"]**2
    total_v2 = v2.sum()
    hc = v2/total_v2
    a_raw = float((hc*rows["modeled_probability"]).sum())
    chase_depth = float(1.0/(hc**2).sum())
    variant_store[s] = {
        "card_variant_id": rows["card_variant_id"].tolist(),
        "price_used": rows["price_used"].tolist(),
        "modeled_probability": rows["modeled_probability"].tolist(),
        "HC": hc.tolist(),
    }
    payload = rb.get("financial_rip_v4_payload") or {}
    comp = (payload or {}).get("components") or {}
    def comp_score(name):
        c = comp.get(name) or {}
        return c.get("score") if isinstance(c, dict) else None
    records.append({
        "set_id": s,
        "run_A_accessibility": ra["calculation_run_id"],
        "date_A": str(ra["created_at_ts"]),
        "run_B_financial_collector": rb["calculation_run_id"],
        "date_B": str(rb["created_at_ts"]),
        "offset_days": (ra["created_at_ts"]-rb["created_at_ts"]).total_seconds()/86400.0,
        "product_market_cost_A": ra["product_market_cost"],
        "product_market_cost_B": rb["product_market_cost"],
        "pack_count": rb["pack_count"],
        "A_raw": a_raw,
        "chase_depth": chase_depth,
        "n_priced_variants": len(rows),
        "financial_rip_v4_score": rb["financial_rip_v4_score"],
        "true_win_frequency": comp_score("true_win_frequency"),
        "typical_retention": comp_score("typical_retention"),
        "loss_resilience": comp_score("loss_resilience"),
        "realistic_upside": comp_score("realistic_upside"),
        "jackpot_upside": comp_score("jackpot_upside"),
        "base_economic_efficiency": comp_score("base_economic_efficiency"),
        "collector_appeal_score": rb["collector_appeal_score"],
        "overall_rip_v10_score": rb["overall_rip_v10_score"],
        "expected_value": rb["expected_value"],
        "p95_value": rb["p95_value"],
        "p99_value": rb["p99_value"],
        "total_value_to_cost_ratio": rb["total_value_to_cost_ratio"],
    })

cohort = pd.DataFrame(records)
cohort["effective_pack_cost"] = cohort["product_market_cost_B"] / cohort["pack_count"]
cohort["ev_over_cost"] = cohort["expected_value"] / cohort["effective_pack_cost"]
cohort["p95_over_cost"] = cohort["p95_value"] / cohort["effective_pack_cost"]
cohort["p99_over_cost"] = cohort["p99_value"] / cohort["effective_pack_cost"]
cohort["ECE_raw"] = cohort["A_raw"] / cohort["effective_pack_cost"]
cohort["price_efficiency"] = 1.0/cohort["effective_pack_cost"]

print(cohort.to_string())
print("\nn=", len(cohort))
print("financial_rip_v4 component non-null check:", cohort[["true_win_frequency","typical_retention","loss_resilience","realistic_upside","jackpot_upside","base_economic_efficiency"]].notna().sum())

with open(os.path.join(D,"cohort_final_v2.json"),"w") as f:
    json.dump(json.loads(cohort.to_json(orient="records")), f, indent=2)
with open(os.path.join(D,"variant_store.json"),"w") as f:
    json.dump(variant_store, f)
