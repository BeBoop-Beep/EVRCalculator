import json, sys, collections
sys.path.insert(0, r"d:\EVRCalculator")
from backend.db.clients.supabase_client import supabase

with open(r"d:\EVRCalculator\docs\research\overall_rip_accessibility_primary_cohort.json") as f:
    primary = json.load(f)
set_ids = [row["set_id"] for row in primary]
accessibility_run_by_set = {row["set_id"]: row["calculation_run_id_accessibility"] for row in primary}

run_dates = collections.defaultdict(dict)  # set_id -> run_id -> {min,max,count}
page = 0
PAGE = 1000
while True:
    r = (supabase.table("simulation_card_variant_pull_rates")
         .select("set_id,calculation_run_id,created_at")
         .in_("set_id", set_ids)
         .gt("pull_count", 0)
         .order("id")
         .range(page * PAGE, page * PAGE + PAGE - 1)
         .execute())
    batch = r.data or []
    for row in batch:
        sid, rid, ts = row["set_id"], row["calculation_run_id"], row["created_at"]
        d = run_dates[sid].setdefault(rid, {"min": ts, "max": ts, "count": 0})
        d["count"] += 1
        if ts < d["min"]:
            d["min"] = ts
        if ts > d["max"]:
            d["max"] = ts
    if len(batch) < PAGE:
        break
    page += 1

out = {}
for sid, runs in run_dates.items():
    sorted_runs = sorted(runs.items(), key=lambda kv: kv[1]["max"], reverse=True)
    out[sid] = {
        "primary_cohort_accessibility_run": accessibility_run_by_set[sid],
        "runs_sorted_newest_first": [
            {"run_id": rid, "min_created_at": d["min"], "max_created_at": d["max"], "row_count": d["count"]}
            for rid, d in sorted_runs
        ],
    }

with open("phase7_run_dates_result.json", "w") as f:
    json.dump(out, f, indent=2, default=str)

for sid, info in out.items():
    print(sid, "primary_run=", info["primary_cohort_accessibility_run"])
    for r in info["runs_sorted_newest_first"]:
        marker = " <-- PRIMARY" if r["run_id"] == info["primary_cohort_accessibility_run"] else ""
        print("   ", r["run_id"], r["max_created_at"], "rows=", r["row_count"], marker)
