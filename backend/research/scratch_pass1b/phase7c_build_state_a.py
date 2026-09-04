import json, os, sys, math
sys.path.insert(0, r"d:\EVRCalculator")
from backend.db.clients.supabase_client import supabase

out_dir = r"d:\EVRCalculator\backend\research\scratch_pass1b"
def dump(name, obj):
    with open(os.path.join(out_dir, name), "w") as f:
        json.dump(obj, f, default=str, indent=2)

primary = json.load(open(r"d:\EVRCalculator\docs\research\overall_rip_accessibility_primary_cohort.json"))
target_sets = {p["set_id"] for p in primary}

per_set_runs = json.load(open(os.path.join(out_dir, "phase7_per_set_pull_rate_runs.json")))
# earliest run per set = state A accessibility run
earliest_run = {sid: runs[0] for sid, runs in per_set_runs.items() if sid in target_sets}
print("sets with earliest run identified:", len(earliest_run))

# fetch full pull-rate rows for those specific run_ids
run_ids = [r["run_id"] for r in earliest_run.values()]
all_rows = []
page = 0
PAGE = 1000
while True:
    r = (supabase.table("simulation_card_variant_pull_rates")
         .select("calculation_run_id,set_id,card_variant_id,price_used,modeled_probability,created_at")
         .in_("calculation_run_id", run_ids)
         .gt("pull_count", 0)
         .order("id")
         .range(page*PAGE, page*PAGE+PAGE-1)
         .execute())
    batch = r.data or []
    all_rows.extend(batch)
    if len(batch) < PAGE:
        break
    page += 1
print("state A pull-rate rows fetched:", len(all_rows))
dump("phase7c_state_a_pull_rates.json", all_rows)

import collections
by_set = collections.defaultdict(list)
for row in all_rows:
    by_set[row["set_id"]].append(row)

def compute_A_raw(rows):
    values = [r["price_used"] for r in rows if r.get("price_used") is not None and r.get("modeled_probability") is not None]
    probs = [r["modeled_probability"] for r in rows if r.get("price_used") is not None and r.get("modeled_probability") is not None]
    squares = [v*v for v in values]
    total = math.fsum(squares)
    if total <= 0:
        return None, None, 0
    hc = [s/total for s in squares]
    a_raw = math.fsum(w*p for w,p in zip(hc, probs))
    n_hc = 1.0/math.fsum(w*w for w in hc)
    return a_raw, n_hc, len(values)

state_a = {}
for sid, run_info in earliest_run.items():
    rows = by_set.get(sid, [])
    a_raw, n_hc, n_priced = compute_A_raw(rows)
    state_a[sid] = {
        "set_id": sid,
        "accessibility_run_id": run_info["run_id"],
        "accessibility_run_date": run_info["min_created_at"],
        "A_raw": a_raw,
        "chase_depth_N_HC": n_hc,
        "n_priced_variants": n_priced,
        "per_variant": {
            "card_variant_id": [r["card_variant_id"] for r in rows if r.get("price_used") is not None and r.get("modeled_probability") is not None],
            "price_used": [r["price_used"] for r in rows if r.get("price_used") is not None and r.get("modeled_probability") is not None],
            "modeled_probability": [r["modeled_probability"] for r in rows if r.get("price_used") is not None and r.get("modeled_probability") is not None],
        }
    }

dump("phase7c_state_a_accessibility.json", state_a)
for sid, s in list(state_a.items())[:5]:
    print(sid, s["accessibility_run_date"], s["A_raw"], s["n_priced_variants"])
