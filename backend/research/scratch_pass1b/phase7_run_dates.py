import json, sys, collections
sys.path.insert(0, r"d:\EVRCalculator")
from backend.db.clients.supabase_client import supabase

with open(r"d:\EVRCalculator\docs\research\overall_rip_accessibility_primary_cohort.json") as f:
    primary = json.load(f)
set_ids = [row["set_id"] for row in primary]
accessibility_run_by_set = {row["set_id"]: row["calculation_run_id_accessibility"] for row in primary}

# probe columns
r = supabase.table("simulation_card_variant_pull_rates").select("*").limit(1).execute()
print("columns:", list(r.data[0].keys()) if r.data else "no rows")
