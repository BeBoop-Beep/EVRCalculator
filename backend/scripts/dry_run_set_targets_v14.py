"""READ-ONLY live dry run of the V14 set-target blocks, without the heavy ``explore_rip_statistics_latest`` view.

Builds ``financialRipV5`` / ``overallRipV14`` for every current set target from the proven set authority
(``set_financial_authority``), the run-matched Chase Accessibility V1 rows and the current Collector Appeal V5
bundle, then ranks them with the release-driven ranking pass. It uses exactly the production builder's own
block constructor and ranking code; only the source of the target list differs (the run-level base table
instead of the view, which currently exceeds the API statement timeout). Nothing is written to the database.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any, Dict, List

ROOT = Path(__file__).resolve().parents[2]


def main(argv=None) -> int:
    from backend.db.services import explore_rip_statistics_service as svc
    from backend.db.services import rankings_release_authority as ra
    from backend.db.services import rip_release as rr
    from backend.db.services import set_rankings_v14 as sr14
    from backend.db.services.chase_accessibility_service import read_chase_accessibility_snapshots_for_sets
    from backend.db.services.collector_appeal_service import get_collector_appeal_bundle
    from backend.scripts import audit_set_financial_authority as audit
    from backend.scripts.pokemon_snapshot_builders import get_client

    client = get_client()
    v14 = next(b for b in rr.RELEASES.values() if b.requires_v5_schema)
    authority_rows = {str(r["calculation_run_id"]): r for r in audit._target_rows(client) if r.get("financial_rip_v3_payload")}
    set_ids = [str(r["set_id"]) for r in authority_rows.values()]
    accessibility = read_chase_accessibility_snapshots_for_sets(set_ids=set_ids, client=client) or {}
    payloads = (get_collector_appeal_bundle() or {}).get("payloads") or {}

    targets: List[Dict[str, Any]] = []
    for run, row in sorted(authority_rows.items(), key=lambda kv: str(kv[1]["set_id"])):
        set_id = str(row["set_id"])
        collector = svc._resolve_collector_payload({"target_id": set_id, "name": row.get("set_name")}, payloads)
        blocks = sr14.build_v14_target_blocks(
            {"calculation_run_id": run, "target_id": set_id}, authority_row=row, client=client,
            collector_score=svc._resolve_canonical_collector_appeal_score(collector),
            collector_version=(collector.get("collectorAppeal") or {}).get("version"),
            accessibility_row=accessibility.get(set_id), artifact_loader=audit._retrying_loader)
        targets.append({"target_id": set_id, "name": row.get("set_name"), "calculation_run_id": run, **blocks})

    svc._rank_within_cohort(targets, cohort_size=len(targets), release=v14)
    ready = [t for t in targets if t["overallRipV14"].get("status") == "ready"]
    snapshot = {"meta": {"ripWeightsConfig": {"financialRip": {"version": v14.financial_version},
                                              "overallRip": {"version": v14.overall_version},
                                              "publicContract": {"version": v14.public_contract_version}}},
                "targets": targets}
    ranks = sorted(t["overallRipV14"].get("rank") for t in ready if t["overallRipV14"].get("rank") is not None)
    report = {
        "readOnly": True, "targets": len(targets),
        "v5Ready": sum(1 for t in targets if t["financialRipV5"].get("status") == "ready"),
        "v14Ready": len(ready), "ranksContiguous": ranks == list(range(1, len(ranks) + 1)),
        "runMatchesAuthority": all((t["financialRipV5"].get("source") or {}).get("calculationRunId") == t["calculation_run_id"]
                                   for t in targets if t["financialRipV5"].get("status") == "ready"),
        "snapshotReleaseProblems": ra.snapshot_release_problems(snapshot, v14),
        "unavailable": [{"set": t["name"], "v5": t["financialRipV5"].get("statusReason"),
                         "v14": t["overallRipV14"].get("statusReason")} for t in targets
                        if t["overallRipV14"].get("status") != "ready"],
        "rows": [{"set": t["name"], "run": t["calculation_run_id"], "v5": t["financialRipV5"].get("score"),
                  "v14": t["overallRipV14"].get("score"), "rank": t["overallRipV14"].get("rank"),
                  "tier": t["overallRipV14"].get("tier")} for t in targets]}
    out = ROOT / "logs" / "v5_candidate" / "set_targets_v14_dry_run.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, indent=1, default=str), encoding="utf-8")
    print(json.dumps({k: v for k, v in report.items() if k != "rows"}, indent=1, default=str))
    return 0 if report["v14Ready"] == len(targets) and not report["snapshotReleaseProblems"] else 1


if __name__ == "__main__":
    sys.exit(main())
