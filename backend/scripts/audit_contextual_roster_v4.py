"""Read-only old/new cohort audit for contextual roster V4."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from backend.db.clients.supabase_client import public_read_client
from backend.db.services.collector_appeal_service import get_collector_appeal_bundle
from backend.db.services.contextual_set_desirability_service import build_contextual_desirability_bundle
from backend.db.services.universal_set_desirability_service import get_universal_desirability_bundle
from backend.desirability.collector_appeal import compute_collector_appeal_v4
from backend.desirability.weighted_rip import compute_overall_rip_v8, spearman


def ranks(rows, key):
    ordered = sorted((r for r in rows if r.get(key) is not None), key=lambda r: (-r[key], r["set_id"]))
    return {r["set_id"]: i for i, r in enumerate(ordered, 1)}


def overlap(a, b, n):
    return len(set(list(a)[:n]) & set(list(b)[:n]))


def main():
    old = get_universal_desirability_bundle(force_refresh=True)["payloads"]
    new = build_contextual_desirability_bundle()["payloads"]
    collector = get_collector_appeal_bundle(force_refresh=True)["payloads"]
    run_ids = [r.get("source_calculation_run_id") for r in new.values() if r.get("source_calculation_run_id")]
    financial = {}
    for run_id in run_ids:
        data = public_read_client.table("simulation_derived_metrics").select("calculation_run_id,financial_rip_v3_score").eq("calculation_run_id", run_id).limit(1).execute().data or []
        if data:
            financial[str(run_id)] = data[0].get("financial_rip_v3_score")
    rows = []
    for set_id, v4 in new.items():
        v3 = old.get(set_id) or {}
        ca = collector.get(set_id) or {}
        h = ((ca.get("desirableOutcomeFrequency") or {}).get("rawValue"))
        old_ca = ((ca.get("collectorAppeal") or {}).get("score"))
        new_ca_unit = compute_collector_appeal_v4(v4.get("score") / 100 if v4.get("score") is not None else None, h)
        new_ca = new_ca_unit * 100 if new_ca_unit is not None else None
        fin = financial.get(str(v4.get("source_calculation_run_id")))
        old_overall = compute_overall_rip_v8(fin, old_ca).get("score")
        new_overall = compute_overall_rip_v8(fin, new_ca).get("score")
        if v3.get("score") is not None and v4.get("score") is not None:
            rows.append({"set_id": set_id, "set": v4.get("set_name"),
                         "old_roster": v3.get("score"), "new_roster": v4.get("score"),
                         "old_collector": old_ca, "new_collector": new_ca,
                         "old_overall": old_overall, "new_overall": new_overall,
                         "priority_subjects": v4.get("modeled_pokemon", [])[:10]})
    for prefix, key in (("roster", "roster"), ("collector", "collector"), ("overall", "overall")):
        old_r, new_r = ranks(rows, f"old_{key}"), ranks(rows, f"new_{key}")
        for row in rows:
            row[f"old_{prefix}_rank"] = old_r.get(row["set_id"])
            row[f"new_{prefix}_rank"] = new_r.get(row["set_id"])
            row[f"{prefix}_rank_delta"] = (old_r[row["set_id"]] - new_r[row["set_id"]]) if row["set_id"] in old_r and row["set_id"] in new_r else None
            if row.get(f"old_{key}") is not None and row.get(f"new_{key}") is not None:
                row[f"{prefix}_delta"] = round(row[f"new_{key}"] - row[f"old_{key}"], 4)
    old_order = [r["set_id"] for r in sorted(rows, key=lambda r: -r["old_roster"])]
    new_order = [r["set_id"] for r in sorted(rows, key=lambda r: -r["new_roster"])]
    report = {"generated_at": datetime.now(timezone.utc).isoformat(), "cohort_size": len(rows),
              "unsupported_or_missing_context_count": len(new) - len(rows),
              "roster_spearman": spearman([r["old_roster"] for r in rows], [r["new_roster"] for r in rows]),
              "top5_overlap": overlap(old_order, new_order, 5), "top10_overlap": overlap(old_order, new_order, 10),
              "mean_absolute_roster_rank_delta": sum(abs(r["roster_rank_delta"]) for r in rows) / len(rows) if rows else None,
              "largest_up": sorted(rows, key=lambda r: r["roster_rank_delta"], reverse=True)[:5],
              "largest_down": sorted(rows, key=lambda r: r["roster_rank_delta"])[:5], "rows": rows}
    path = Path("logs/contextual_roster_v4_cohort_audit.json")
    path.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(path)
    print(json.dumps({k: report[k] for k in ("cohort_size", "roster_spearman", "top5_overlap", "top10_overlap", "mean_absolute_roster_rank_delta")}, indent=2))


if __name__ == "__main__":
    main()
