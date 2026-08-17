"""Targeted backfill of canonical ripDecision blocks for ranked Pokemon sets.

Dry-run by default. ``--commit`` updates only payload_json.ripDecision on each
existing set-page snapshot; no simulation or snapshot builder is invoked.
"""

from __future__ import annotations

import argparse
import copy
import json
from typing import Any, Dict, Iterable, List

from backend.db.clients.supabase_client import create_service_role_client
from backend.db.services.explore_rip_statistics_service import get_rip_statistics_targets_payload
from backend.db.services.rip_decision_service import build_rip_decision_contract


def ranked_targets(rows: Iterable[Dict[str, Any]]) -> List[Dict[str, str]]:
    selected = []
    for row in rows or []:
        overall = row.get("overallRipV8") if isinstance(row.get("overallRipV8"), dict) else {}
        set_id = str(row.get("set_id") or row.get("target_id") or row.get("id") or "").strip()
        run_id = str(row.get("calculation_run_id") or "").strip()
        if overall.get("rank") is not None and set_id and run_id:
            selected.append({"set_id": set_id, "calculation_run_id": run_id})
    return selected


def validate_contract(contract: Dict[str, Any], run_id: str) -> None:
    sealed = contract.get("sealedProducts") or {}
    chase = contract.get("topChase")
    assert contract.get("contractVersion") == "rip-decision-contract-v1"
    assert contract.get("currentRunAvailable") is True
    assert contract.get("sourceCalculationRunId") == run_id
    assert sealed.get("sourceCalculationRunId") == run_id
    assert sealed.get("productCount", 0) > 0
    assert isinstance(chase, dict)
    assert chase.get("sourceCalculationRunId") == run_id
    for field in (
        "cardName", "currentMarketPrice", "modeledProbability", "impliedOddsOneInN",
        "packsFor50PercentChance", "packsFor90PercentChance",
    ):
        assert chase.get(field) is not None, f"topChase.{field} is unavailable"
    for field in (
        "currentMarketPrice", "modeledProbability", "impliedOddsOneInN",
        "packsFor50PercentChance", "packsFor90PercentChance",
    ):
        assert chase[field] > 0, f"topChase.{field} must be positive"


def run(*, commit: bool, client: Any = None) -> Dict[str, Any]:
    service_client = client or create_service_role_client()
    targets = ranked_targets(get_rip_statistics_targets_payload().get("targets") or [])
    report: Dict[str, Any] = {"attempted": len(targets), "succeeded": 0, "failed": [], "sets": []}
    for target in targets:
        set_id, run_id = target["set_id"], target["calculation_run_id"]
        try:
            rows = (
                service_client.table("pokemon_set_page_snapshot_latest")
                .select("set_id,payload_json").eq("set_id", set_id).limit(1).execute().data or []
            )
            if not rows or not isinstance(rows[0].get("payload_json"), dict):
                raise ValueError("existing set-page snapshot is missing")
            contract = build_rip_decision_contract(set_id=set_id, run_id=run_id, client=service_client)
            validate_contract(contract, run_id)
            if commit:
                payload = copy.deepcopy(rows[0]["payload_json"])
                payload["ripDecision"] = contract
                result = (
                    service_client.table("pokemon_set_page_snapshot_latest")
                    .update({"payload_json": payload}).eq("set_id", set_id).execute()
                )
                if not result.data:
                    raise RuntimeError("snapshot update affected no rows")
            report["succeeded"] += 1
            report["sets"].append({
                "set_id": set_id, "calculation_run_id": run_id,
                "productCount": contract["sealedProducts"]["productCount"],
                "topChase": contract["topChase"], "committed": commit,
            })
        except Exception as exc:
            report["failed"].append({"set_id": set_id, "calculation_run_id": run_id, "error": str(exc)})
    return report


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--commit", action="store_true", help="write validated ripDecision blocks")
    args = parser.parse_args()
    report = run(commit=args.commit)
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0 if not report["failed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
