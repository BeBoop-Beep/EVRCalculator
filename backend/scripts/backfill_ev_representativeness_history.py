"""Audit and safely backfill Tier A from exact historical outcome artifacts."""

from __future__ import annotations

import argparse
import csv
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from backend.db.clients.supabase_client import create_service_role_client
from backend.db.services.ev_representativeness_service import build_tier_a_for_run
from backend.research.ev_representativeness.version import EV_REPRESENTATIVENESS_VERSION


def _rows(response: Any) -> List[Dict[str, Any]]:
    return list((response.data if response else []) or [])


def _paged(query_factory) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    offset = 0
    while True:
        page = _rows(query_factory().range(offset, offset + 999).execute())
        rows.extend(page)
        if len(page) < 1000:
            return rows
        offset += 1000


def audit(client: Any) -> Dict[str, Any]:
    artifacts = _paged(lambda: client.table("simulation_pack_outcome_artifacts").select(
        "calculation_run_id,raw_sha256,outcome_count,created_at"
    ).order("created_at"))
    run_ids = [str(row["calculation_run_id"]) for row in artifacts]
    runs: Dict[str, Dict[str, Any]] = {}
    summaries: Dict[str, Dict[str, Any]] = {}
    histories: Dict[str, Dict[str, Any]] = {}
    for start in range(0, len(run_ids), 50):
        chunk = run_ids[start:start + 50]
        for row in _rows(client.table("calculation_runs").select(
            "id,target_id,target_type,created_at,engine_version"
        ).in_("id", chunk).execute()):
            runs[str(row["id"])] = row
        for row in _rows(client.table("simulation_run_summary").select(
            "calculation_run_id,pack_cost,mean_value,simulation_count"
        ).in_("calculation_run_id", chunk).execute()):
            summaries[str(row["calculation_run_id"])] = row
        for row in _rows(client.table("calculation_history_trend").select(
            "calculation_run_id,snapshot_date,target_id,target_type"
        ).in_("calculation_run_id", chunk).execute()):
            histories[str(row["calculation_run_id"])] = row
    existing = {
        str(row["calculation_run_id"])
        for row in _paged(lambda: client.table("ev_representativeness_run_summary")
                           .select("calculation_run_id")
                           .eq("research_method_version", EV_REPRESENTATIVENESS_VERSION))
    }
    set_ids = sorted({str(row.get("target_id")) for row in runs.values() if row.get("target_id")})
    set_keys: Dict[str, str] = {}
    for start in range(0, len(set_ids), 100):
        for row in _rows(client.table("sets").select("id,canonical_key").in_("id", set_ids[start:start + 100]).execute()):
            set_keys[str(row["id"])] = str(row.get("canonical_key") or row["id"])
    eligible, skipped = [], []
    for artifact in artifacts:
        run_id = str(artifact["calculation_run_id"])
        reason = None
        run, summary, history = runs.get(run_id), summaries.get(run_id), histories.get(run_id)
        if not run:
            reason = "missing_calculation_run"
        elif run.get("target_type") != "set":
            reason = "not_set_run"
        elif not summary:
            reason = "missing_simulation_run_summary"
        elif not history or not history.get("snapshot_date"):
            reason = "missing_market_date"
        elif float(summary.get("pack_cost") or 0) <= 0:
            reason = "invalid_pack_cost"
        elif int(summary.get("simulation_count") or 0) <= 0:
            reason = "invalid_simulation_count"
        item = {
            "calculationRunId": run_id,
            "setId": (history or run or {}).get("target_id"),
            "setCanonicalKey": set_keys.get(str((history or run or {}).get("target_id"))),
            "marketDate": str((history or {}).get("snapshot_date") or "")[:10] or None,
            "artifactSha256": artifact.get("raw_sha256"),
            "outcomeCount": artifact.get("outcome_count"),
            "alreadyBuilt": run_id in existing,
        }
        (skipped if reason else eligible).append({**item, **({"reason": reason} if reason else {})})
    date_counts = Counter(item["marketDate"] for item in eligible)
    set_counts = Counter(str(item["setCanonicalKey"] or item["setId"]) for item in eligible)
    dates = sorted(date for date in date_counts if date)
    return {
        "methodVersion": EV_REPRESENTATIVENESS_VERSION,
        "totalHistoricalArtifacts": len(artifacts),
        "eligibleRuns": len(eligible),
        "alreadyBuiltRuns": sum(item["alreadyBuilt"] for item in eligible),
        "backfillableRuns": sum(not item["alreadyBuilt"] for item in eligible),
        "uniqueMarketDates": dates,
        "earliestRecoverableDate": dates[0] if dates else None,
        "latestRecoverableDate": dates[-1] if dates else None,
        "observationsPerDate": dict(sorted(date_counts.items())),
        "observationsPerSet": dict(sorted(set_counts.items())),
        "skipped": skipped,
        "eligible": eligible,
    }


def export_history(client: Any, path: Path) -> int:
    summaries = _paged(lambda: client.table("ev_representativeness_run_summary")
                       .select("*").eq("research_method_version", EV_REPRESENTATIVENESS_VERSION)
                       .order("market_date").order("set_canonical_key"))
    run_ids = [str(row["calculation_run_id"]) for row in summaries]
    curve: Dict[tuple[str, int], Any] = {}
    for start in range(0, len(run_ids), 50):
        chunk = run_ids[start:start + 50]
        rows = _rows(client.table("ev_representativeness_curve")
                     .select("calculation_run_id,pack_count,estimate,stage")
                     .eq("research_method_version", EV_REPRESENTATIVENESS_VERSION)
                     .eq("scope_kind", "pack_grid").eq("metric_key", "realization_ge_0.80")
                     .in_("pack_count", [1, 6, 9, 18, 36]).in_("calculation_run_id", chunk)
                     .order("calculation_run_id").order("pack_count").order("stage").execute())
        rank = {"coarse": 0, "refine": 1, "confirm": 2}
        for row in rows:
            key = (str(row["calculation_run_id"]), int(row["pack_count"]))
            if key not in curve or rank.get(str(row.get("stage")), -1) > rank.get(str(curve[key].get("stage")), -1):
                curve[key] = row
    fields = ["market_date", "set_id", "set_canonical_key", "calculation_run_id", "research_method_version",
              "ev", "p50", "typical_capture", "pack_cost", "ev_to_cost", "coefficient_of_variation",
              "top1_outcome_ev_share", "top5_outcome_ev_share", "top10_outcome_ev_share",
              "horizon_r80_c80_stable", "horizon_r80_c80_status",
              "horizon_tau20_c80_stable", "horizon_tau20_c80_status",
              "realization_ge_80_n1", "realization_ge_80_n6", "realization_ge_80_n9",
              "realization_ge_80_n18", "realization_ge_80_n36", "source_artifact_sha256", "built_at"]
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields); writer.writeheader()
        for row in summaries:
            run_id = str(row["calculation_run_id"]); ev = float(row.get("ev") or 0); cost = float(row.get("pack_cost") or 0)
            output = {key: row.get(key) for key in fields}
            if row.get("horizon_r80_c80_status") != "resolved":
                output["horizon_r80_c80_stable"] = None
            if row.get("horizon_tau20_c80_status") != "resolved":
                output["horizon_tau20_c80_stable"] = None
            output["ev_to_cost"] = ev / cost if cost > 0 else None
            for count in (1, 6, 9, 18, 36):
                point = curve.get((run_id, count))
                output[f"realization_ge_80_n{count}"] = point.get("estimate") if point else None
            writer.writerow(output)
    return len(summaries)


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--backfill", action="store_true")
    parser.add_argument("--audit-out")
    parser.add_argument("--history-out")
    args = parser.parse_args(argv)
    client = create_service_role_client(); report = audit(client)
    results = []
    if args.backfill:
        pending = [item for item in report["eligible"] if not item["alreadyBuilt"]]
        for index, item in enumerate(pending, 1):
            try:
                result = build_tier_a_for_run(client, item["calculationRunId"])
                results.append({**item, **result})
                print(f"[{index}/{len(pending)}] {item['marketDate']} {item['calculationRunId']} {result['status']}")
            except Exception as exc:  # one historical run must not abort the audit
                results.append({**item, "status": "failed", "error": str(exc)})
                print(f"[{index}/{len(pending)}] {item['calculationRunId']} FAILED {exc}")
        report = audit(client)
        report["backfillResults"] = results
    if args.audit_out:
        path = Path(args.audit_out); path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(report, indent=2, default=str), encoding="utf-8")
    if args.history_out:
        report["historyExportRows"] = export_history(client, Path(args.history_out))
    print(json.dumps({key: report.get(key) for key in (
        "totalHistoricalArtifacts", "eligibleRuns", "alreadyBuiltRuns", "backfillableRuns",
        "uniqueMarketDates", "earliestRecoverableDate", "latestRecoverableDate", "historyExportRows")}, indent=2))
    return 0 if not any(row.get("status") == "failed" for row in results) else 2


if __name__ == "__main__":
    raise SystemExit(main())
