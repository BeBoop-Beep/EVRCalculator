import json, os, sys
sys.path.insert(0, r"d:\EVRCalculator")
from backend.db.clients.supabase_client import supabase

out_dir = r"d:\EVRCalculator\backend\research\scratch_pass1b"
def dump(name, obj):
    with open(os.path.join(out_dir, name), "w") as f:
        json.dump(obj, f, default=str, indent=2)

primary = json.load(open(r"d:\EVRCalculator\docs\research\overall_rip_accessibility_primary_cohort.json"))
target_sets = {p["set_id"] for p in primary}

sel = ("id,calculation_run_id,sealed_product_id,set_id,product_family,product_name,pack_count,"
       "random_pack_count,product_market_cost,"
       "financial_rip_v4_score,financial_rip_v4_version,collector_appeal_score,collector_appeal_version,"
       "overall_rip_v10_score,overall_rip_v10_version,created_at")
all_rows = []
page = 0
PAGE = 1000
while True:
    r = (supabase.table("simulation_sealed_product_results")
         .select(sel)
         .in_("set_id", list(target_sets))
         .eq("product_family", "loose_booster_pack")
         .order("id")
         .range(page*PAGE, page*PAGE+PAGE-1)
         .execute())
    batch = r.data or []
    all_rows.extend(batch)
    if len(batch) < PAGE:
        break
    page += 1
print("loose_booster_pack rows in target sets:", len(all_rows))
dump("phase7b_sealed_product_loose_pack_all.json", all_rows)

full = [r for r in all_rows if r.get("financial_rip_v4_score") is not None
        and r.get("collector_appeal_score") is not None
        and r.get("overall_rip_v10_score") is not None]
print("fully-enriched rows:", len(full))

import collections
by_run = collections.defaultdict(list)
for r in full:
    by_run[r["calculation_run_id"]].append(r)

print("distinct fully-enriched calculation_run_ids:", len(by_run))
summary = []
for rid, rows in by_run.items():
    sets = {r["set_id"] for r in rows}
    dates = [r["created_at"] for r in rows]
    summary.append({"run_id": rid, "n_products": len(rows), "n_sets": len(sets),
                     "min_created_at": min(dates), "max_created_at": max(dates)})
summary.sort(key=lambda x: x["min_created_at"])
for s in summary:
    print(s)
dump("phase7b_fully_enriched_run_summary.json", summary)
