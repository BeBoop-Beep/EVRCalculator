import json, os, sys
sys.path.insert(0, r"d:\EVRCalculator")
from backend.db.clients.supabase_client import supabase

out_dir = r"d:\EVRCalculator\backend\research\scratch_pass1a_supplement"
def dump(name, obj):
    with open(os.path.join(out_dir, name), "w") as f:
        json.dump(obj, f, default=str, indent=2)

sel = ("id,calculation_run_id,sealed_product_id,set_id,product_family,product_name,pack_count,"
       "random_pack_count,random_pack_expected_value,"
       "product_market_cost,price_as_of,price_source,simulation_count,"
       "expected_value,median_value,p05_value,p95_value,p99_value,min_value,max_value,"
       "standard_deviation,chance_to_recover_cost,expected_loss_when_losing,"
       "median_loss_when_losing,total_value_to_cost_ratio,"
       "financial_rip_v4_score,financial_rip_v4_status,financial_rip_v4_rankable,"
       "financial_rip_v4_version,financial_rip_v4_payload,"
       "collector_appeal_score,collector_appeal_version,"
       "overall_rip_v10_score,overall_rip_v10_version,overall_rip_v10_rankable,"
       "created_at,updated_at")

all_rows = []
page = 0
PAGE = 1000
while True:
    r = (supabase.table("simulation_sealed_product_results")
         .select(sel)
         .order("id")
         .range(page*PAGE, page*PAGE+PAGE-1)
         .execute())
    batch = r.data or []
    all_rows.extend(batch)
    if len(batch) < PAGE:
        break
    page += 1

dump("sealed_product_results_all.json", all_rows)
print("sealed_product_results rows:", len(all_rows))
