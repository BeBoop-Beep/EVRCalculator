"""Health check for the shadow PkmnPrices sold-evidence pipeline."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any

from backend.db.clients.supabase_client import create_service_role_client
from backend.pricing_pipeline.pkmnprices_targets import (
    discover_vintage_gap_rows,
    latest_approved_market_date,
    resolve_targets,
)


def _parse_ts(value: Any) -> datetime | None:
    if not value:
        return None
    parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def check(client: Any, *, max_run_age_hours: float = 36.0) -> dict[str, Any]:
    market_date = latest_approved_market_date(client)
    gaps = discover_vintage_gap_rows(client, market_date)
    targets = resolve_targets(client, gaps)
    target_ids = {str(row["canonical_card_id"]) for row in targets}

    runs = (
        client.table("pkmnprices_sold_runs_v1")
        .select("run_id,status,target_count,credits_used,finished_at,error_code,metadata")
        .in_("status", ["COMPLETE", "PARTIAL"])
        .order("finished_at", desc=True)
        .limit(1)
        .execute().data
        or []
    )
    latest = dict(runs[0]) if runs else None
    finished_at = _parse_ts((latest or {}).get("finished_at"))
    age_hours = (
        (datetime.now(timezone.utc) - finished_at).total_seconds() / 3600.0
        if finished_at else None
    )

    sync_rows = (
        client.table("pkmnprices_sold_sync_state_v1")
        .select("canonical_card_id,status,last_success_at,metadata")
        .execute().data
        or []
    )
    sync_by = {str(row["canonical_card_id"]): dict(row) for row in sync_rows}
    missing_sync = sorted(target_ids - set(sync_by))
    incomplete_backfills = sorted(
        cid for cid in target_ids
        if cid in sync_by and (
            sync_by[cid].get("status") != "CURRENT"
            or (sync_by[cid].get("metadata") or {}).get("backfill_complete") is not True
        )
    )

    forbidden = (
        client.table("pkmnprices_ebay_sold_evidence_v1")
        .select("provider_listing_id", count="exact")
        .eq("set_value_nm_eligible", True)
        .limit(1)
        .execute()
    )
    forbidden_count = int(forbidden.count or 0)

    failures = []
    if latest is None:
        failures.append("NO_COMPLETED_OR_PARTIAL_RUN")
    elif latest.get("status") != "COMPLETE":
        failures.append("LATEST_RUN_NOT_COMPLETE")
    if age_hours is None or age_hours > max_run_age_hours:
        failures.append("LATEST_RUN_STALE")
    if missing_sync:
        failures.append("CURRENT_TARGET_SYNC_MISSING")
    if incomplete_backfills:
        failures.append("CURRENT_TARGET_BACKFILL_INCOMPLETE")
    if forbidden_count:
        failures.append("SOLD_EVIDENCE_LEAKED_INTO_NM_ELIGIBILITY")

    return {
        "healthy": not failures,
        "market_date": market_date,
        "current_gap_rows": len(gaps),
        "current_target_cards": len(targets),
        "latest_run": latest,
        "latest_run_age_hours": round(age_hours, 3) if age_hours is not None else None,
        "missing_sync_count": len(missing_sync),
        "incomplete_backfill_count": len(incomplete_backfills),
        "set_value_nm_eligible_rows": forbidden_count,
        "failures": failures,
    }


def main() -> int:
    result = check(create_service_role_client())
    print(json.dumps(result, indent=2, sort_keys=True, default=str))
    return 0 if result["healthy"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
