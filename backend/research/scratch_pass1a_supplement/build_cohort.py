import json, os
import pandas as pd
import numpy as np

D = r"d:\EVRCalculator\backend\research\scratch_pass1a_supplement"
DOCS = r"d:\EVRCalculator\docs\research"

sp = json.load(open(os.path.join(D, "sealed_product_results_all.json")))
primary = json.load(open(os.path.join(DOCS, "overall_rip_accessibility_primary_cohort.json")))

sp_df = pd.DataFrame(sp)
sp_df["created_at_ts"] = pd.to_datetime(sp_df["created_at"])

primary_by_set = {p["set_id"]: p for p in primary}
target_sets = set(primary_by_set.keys())

# restrict to target 22 sets
sub = sp_df[sp_df.set_id.isin(target_sets)].copy()
print("rows in target sets (all families, all runs):", len(sub))
print("families present:", sub.product_family.value_counts())

# For each sealed_product_id, take the latest row with BOTH collector_appeal_score and
# overall_rip_v10_score non-null (same enrichment-completeness rule Pass 1A used for Track B).
enriched = sub[sub.collector_appeal_score.notna() & sub.overall_rip_v10_score.notna()].copy()
print("\nenriched rows (has collector+overall):", len(enriched))
enriched_latest = enriched.sort_values("created_at_ts").groupby("sealed_product_id").tail(1)
print("enriched latest per sealed_product_id:", len(enriched_latest))
print(enriched_latest.product_family.value_counts())

excluded = []
records = []
for _, row in enriched_latest.iterrows():
    set_id = row["set_id"]
    pc = row.get("pack_count")
    rpc = row.get("random_pack_count")
    # pack-equivalent count: prefer pack_count if present & >0, else random_pack_count
    pack_eq = None
    if pd.notna(pc) and pc and pc > 0:
        pack_eq = float(pc)
    elif pd.notna(rpc) and rpc and rpc > 0:
        pack_eq = float(rpc)
    if pack_eq is None or pd.isna(row["product_market_cost"]) or row["product_market_cost"] is None:
        excluded.append({"sealed_product_id": row["sealed_product_id"], "set_id": set_id,
                          "product_family": row["product_family"], "reason": "no resolvable pack_count/random_pack_count or market cost"})
        continue
    price = float(row["product_market_cost"])
    eff_cost = price / pack_eq
    a_raw = primary_by_set[set_id]["A_raw"]
    payload = row.get("financial_rip_v4_payload") or {}
    comp = (payload or {}).get("components") or {}
    def comp_score(name):
        c = comp.get(name) or {}
        return c.get("score") if isinstance(c, dict) else None
    records.append({
        "sealed_product_id": row["sealed_product_id"],
        "set_id": set_id,
        "product_family": row["product_family"],
        "product_name": row["product_name"],
        "calculation_run_id": row["calculation_run_id"],
        "run_created_at": str(row["created_at_ts"]),
        "product_market_cost": price,
        "pack_count": row.get("pack_count"),
        "random_pack_count": row.get("random_pack_count"),
        "pack_equivalent_used": pack_eq,
        "effective_pack_cost": eff_cost,
        "A_raw": a_raw,
        "ECE_raw": a_raw / eff_cost,
        "financial_rip_v4_score": row["financial_rip_v4_score"],
        "true_win_frequency": comp_score("true_win_frequency"),
        "typical_retention": comp_score("typical_retention"),
        "loss_resilience": comp_score("loss_resilience"),
        "realistic_upside": comp_score("realistic_upside"),
        "jackpot_upside": comp_score("jackpot_upside"),
        "base_economic_efficiency": comp_score("base_economic_efficiency"),
        "collector_appeal_v5_score": row["collector_appeal_score"],
        "overall_rip_v10_score": row["overall_rip_v10_score"],
        "expected_value": row["expected_value"],
        "p95_value": row["p95_value"],
        "p99_value": row["p99_value"],
        "total_value_to_cost_ratio": row["total_value_to_cost_ratio"],
        "ev_over_cost": (row["expected_value"]/eff_cost) if pd.notna(row["expected_value"]) else None,
        "p95_over_cost": (row["p95_value"]/eff_cost) if pd.notna(row["p95_value"]) else None,
        "p99_over_cost": (row["p99_value"]/eff_cost) if pd.notna(row["p99_value"]) else None,
        "accessibility_run_id": primary_by_set[set_id]["calculation_run_id_accessibility"],
        "accessibility_run_date": primary_by_set[set_id]["market_date_accessibility_run_created_at"],
        "financial_collector_run_id": row["calculation_run_id"],
        "financial_collector_run_date": str(row["created_at_ts"]),
    })

# rows missing financial score / components entirely -> exclude
final = []
for r in records:
    if r["financial_rip_v4_score"] is None:
        excluded.append({"sealed_product_id": r["sealed_product_id"], "set_id": r["set_id"],
                          "product_family": r["product_family"], "reason": "financial_rip_v4_score null despite enrichment filter"})
        continue
    final.append(r)

df = pd.DataFrame(final)
print("\nFINAL COHORT n=", len(df))
print("sets:", df.set_id.nunique())
print("families:\n", df.product_family.value_counts())
print("\nproducts per set:\n", df.groupby("set_id").size().describe())
print("\nexcluded:", len(excluded))
for e in excluded[:30]:
    print(e)

with open(os.path.join(D, "product_cohort_raw.json"), "w") as f:
    json.dump(final, f, indent=2, default=str)
with open(os.path.join(D, "excluded.json"), "w") as f:
    json.dump(excluded, f, indent=2, default=str)

# additional exclusion accounting: products present in target sets but never enriched
all_sp_ids = set(sub["sealed_product_id"].unique())
enriched_ids = set(enriched_latest["sealed_product_id"].unique())
never_enriched = all_sp_ids - enriched_ids
print("\ntotal distinct sealed_product_id in target 22 sets (all families/runs):", len(all_sp_ids))
print("never-enriched sealed_product_ids:", len(never_enriched))
never_enriched_detail = []
for spid in never_enriched:
    rows = sub[sub.sealed_product_id == spid]
    fam = rows.product_family.iloc[0]
    sid = rows.set_id.iloc[0]
    never_enriched_detail.append({"sealed_product_id": spid, "set_id": sid, "product_family": fam,
                                   "reason": "no row for this sealed_product_id ever had both collector_appeal_score and overall_rip_v10_score populated"})
print(pd.DataFrame(never_enriched_detail).product_family.value_counts() if never_enriched_detail else "none")

excluded_full = excluded + never_enriched_detail
with open(os.path.join(D, "excluded.json"), "w") as f:
    json.dump(excluded_full, f, indent=2, default=str)
print("total excluded (final):", len(excluded_full))
