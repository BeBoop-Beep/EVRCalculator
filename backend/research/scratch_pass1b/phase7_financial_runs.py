import json, sys, collections
sys.path.insert(0, r"d:\EVRCalculator")
from backend.db.clients.supabase_client import supabase

with open(r"d:\EVRCalculator\docs\research\overall_rip_accessibility_primary_cohort.json") as f:
    primary = json.load(f)
set_ids = [row["set_id"] for row in primary]

sel = ("id,calculation_run_id,sealed_product_id,set_id,product_family,product_market_cost,"
       "random_pack_count,pack_count,financial_rip_v4_score,collector_appeal_score,"
       "overall_rip_v10_score,expected_value,p95_value,p99_value,created_at")

rows_by_set = collections.defaultdict(list)
page = 0
PAGE = 1000
while True:
    r = (supabase.table("simulation_sealed_product_results")
         .select(sel)
         .in_("set_id", set_ids)
         .eq("product_family", "loose_booster_pack")
         .not_.is_("overall_rip_v10_score", "null")
         .not_.is_("collector_appeal_score", "null")
         .order("id")
         .range(page * PAGE, page * PAGE + PAGE - 1)
         .execute())
    batch = r.data or []
    for row in batch:
        rows_by_set[row["set_id"]].append(row)
    if len(batch) < PAGE:
        break
    page += 1

out = {}
for sid, rows in rows_by_set.items():
    rows_sorted = sorted(rows, key=lambda r: r["created_at"])
    out[sid] = [{"calculation_run_id": r["calculation_run_id"], "created_at": r["created_at"],
                 "sealed_product_id": r["sealed_product_id"], "product_market_cost": r["product_market_cost"]}
                for r in rows_sorted]

with open("phase7_financial_runs_result.json", "w") as f:
    json.dump(out, f, indent=2, default=str)

for sid, rows in out.items():
    print(sid, len(rows), "runs:", [r["created_at"] for r in rows])
