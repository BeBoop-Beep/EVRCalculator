import sys
sys.path.insert(0, r"d:\EVRCalculator")
from backend.db.clients.supabase_client import supabase

tables = [
    "pokemon_set_chase_accessibility_snapshot_latest",
    "simulation_card_variant_pull_rates",
    "simulation_sealed_product_results",
    "sealed_products",
    "pokemon_sets",
]
for t in tables:
    try:
        r = supabase.table(t).select("*").limit(1).execute()
        print(t, "OK", len(r.data or []), (list(r.data[0].keys()) if r.data else "no rows"))
    except Exception as e:
        print(t, "FAIL", str(e)[:200])
