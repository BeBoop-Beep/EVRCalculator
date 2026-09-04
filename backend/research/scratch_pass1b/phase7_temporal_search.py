"""Pass 1B Phase 7: exhaustive temporal authority search for a SECOND genuine
Accessibility-capable state. READ-ONLY DB queries; nothing written."""
import json, sys, collections
sys.path.insert(0, r"d:\EVRCalculator")
from backend.db.clients.supabase_client import supabase

out = {}

# --- Step 1: live simulation_card_variant_pull_rates run inventory ---
# Pull distinct (set_id, calculation_run_id) + a representative created_at/updated_at
# for the primary cohort's 22 set_ids, to see how many DISTINCT runs per set remain live.
with open(r"d:\EVRCalculator\docs\research\overall_rip_accessibility_primary_cohort.json") as f:
    primary = json.load(f)
set_ids = [row["set_id"] for row in primary]
accessibility_run_by_set = {row["set_id"]: row["calculation_run_id_accessibility"] for row in primary}

runs_by_set = collections.defaultdict(set)
page = 0
PAGE = 1000
rows_scanned = 0
while True:
    r = (supabase.table("simulation_card_variant_pull_rates")
         .select("set_id,calculation_run_id")
         .in_("set_id", set_ids)
         .gt("pull_count", 0)
         .order("id")
         .range(page * PAGE, page * PAGE + PAGE - 1)
         .execute())
    batch = r.data or []
    rows_scanned += len(batch)
    for row in batch:
        runs_by_set[row["set_id"]].add(row["calculation_run_id"])
    if len(batch) < PAGE:
        break
    page += 1

distinct_run_counts = {sid: len(runs) for sid, runs in runs_by_set.items()}
sets_with_ge2_runs = {sid: list(runs) for sid, runs in runs_by_set.items() if len(runs) >= 2}

out["step1_pull_rates_run_inventory"] = {
    "rows_scanned": rows_scanned,
    "sets_checked": len(set_ids),
    "distinct_run_count_per_set": distinct_run_counts,
    "sets_with_2_or_more_distinct_runs": sets_with_ge2_runs,
    "n_sets_with_2plus_runs": len(sets_with_ge2_runs),
}
print("rows scanned:", rows_scanned)
print("distinct run counts per set:", distinct_run_counts)
print("sets with >=2 distinct runs:", len(sets_with_ge2_runs))

with open("phase7_temporal_search_partial.json", "w") as f:
    json.dump(out, f, indent=2, default=str)
