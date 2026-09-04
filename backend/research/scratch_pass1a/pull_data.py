import json, os, sys
sys.path.insert(0, r"d:\EVRCalculator")
from backend.db.clients.supabase_client import supabase

out_dir = r"d:\EVRCalculator\backend\research\scratch_pass1a"

def dump(name, obj):
    with open(os.path.join(out_dir, name), "w") as f:
        json.dump(obj, f, default=str, indent=2)

# 1. Chase accessibility snapshot table does not exist live (PGRST205) - confirmed blocker.
# Reconstruct A_raw ourselves from simulation_card_variant_pull_rates (same formula, same authority table).
all_pr = []
page = 0
PAGE = 1000
while True:
    r = (supabase.table("simulation_card_variant_pull_rates")
         .select("calculation_run_id,set_id,card_variant_id,price_used,modeled_probability,"
                 "effective_pull_rate,pull_count,pack_presence_count,simulation_count,status")
         .gt("pull_count", 0)
         .order("id")
         .range(page*PAGE, page*PAGE+PAGE-1)
         .execute())
    batch = r.data or []
    all_pr.extend(batch)
    if len(batch) < PAGE:
        break
    page += 1
dump("pull_rates_all.json", all_pr)
print("pull_rates rows:", len(all_pr))

# 2. simulation_sealed_product_results - get all rows, page
all_rows = []
page = 0
PAGE = 1000
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
