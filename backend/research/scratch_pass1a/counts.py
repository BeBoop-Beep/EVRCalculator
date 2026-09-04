import sys
sys.path.insert(0, r"d:\EVRCalculator")
from backend.db.clients.supabase_client import supabase

r = supabase.table("simulation_sealed_product_results").select("id", count="exact").limit(1).execute()
print("sealed_product_results count:", r.count)
r2 = supabase.table("simulation_card_variant_pull_rates").select("id", count="exact").limit(1).execute()
print("pull_rates count:", r2.count)
# distinct calculation_run_ids in sealed_product_results, recent
r3 = supabase.table("simulation_sealed_product_results").select("calculation_run_id,set_id,created_at").order("created_at", desc=True).limit(30).execute()
for row in r3.data:
    print(row)
