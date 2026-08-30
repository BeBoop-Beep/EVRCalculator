"""Independent America/Phoenix watchdog for the daily Pokémon market pipeline."""

from __future__ import annotations

import argparse
import json
import os
from datetime import datetime, time, timedelta, timezone
from typing import Any, Dict, List, Mapping, Optional

from backend.alerts.scrape_alerts import queue_alert
from backend.db.clients.supabase_client import supabase


PHOENIX = timezone(timedelta(hours=-7), "America/Phoenix")
TERMINAL_BATCH_STATES = {"complete", "failed", "incomplete"}


def _clock(value: str) -> time:
    hour, minute = (int(part) for part in value.split(":", 1))
    return time(hour, minute)


def evaluate_watchdog_state(state: Mapping[str, Any], *, now: datetime) -> List[Dict[str, Any]]:
    local_now = now.astimezone(PHOENIX)
    market_date = local_now.date().isoformat()
    failures: List[Dict[str, Any]] = []
    batch_deadline = _clock(os.getenv("MARKET_BATCH_DEADLINE_AZ", "03:10"))
    publication_deadline = _clock(os.getenv("MARKET_PUBLICATION_DEADLINE_AZ", "07:00"))
    batch = state.get("batch")

    if local_now.time() >= batch_deadline and not batch:
        failures.append({"alert_type": "batch_not_created", "failure_class": "missing_batch",
                         "message": f"No daily scrape batch exists after {batch_deadline} America/Phoenix."})
    if batch and str(batch.get("status")) not in TERMINAL_BATCH_STATES:
        updated = batch.get("updated_at") or batch.get("started_at") or batch.get("created_at")
        if updated:
            parsed = datetime.fromisoformat(str(updated).replace("Z", "+00:00"))
            age = (now.astimezone(timezone.utc) - parsed.astimezone(timezone.utc)).total_seconds() / 60
            if age >= int(os.getenv("MARKET_BATCH_STALL_MINUTES", "120")):
                failures.append({"alert_type": "batch_progress_stalled", "failure_class": str(batch.get("status") or "unknown"),
                                 "message": f"Batch {batch.get('id')} status={batch.get('status')} has not progressed for {int(age)} minutes.",
                                 "batch_id": batch.get("id"), "status": batch.get("status")})

    dates = dict(state.get("authority_dates") or {})
    if local_now.time() >= publication_deadline:
        public_date = dates.get("accepted_market_quality")
        if public_date != market_date:
            failures.append({"alert_type": "market_publication_stale", "failure_class": "accepted_date_stale",
                             "message": f"Latest accepted market date is {public_date or 'missing'}; expected {market_date}."})
        present = {key: value for key, value in dates.items() if value}
        if present and len(set(present.values())) > 1:
            failures.append({"alert_type": "market_snapshot_date_divergence", "failure_class": "authority_date_mismatch",
                             "message": f"Public market authorities disagree: {present}.", "actual_dates": present})

    for failure in failures:
        failure["market_date"] = market_date
    return failures


def _latest_date(client: Any, table: str, column: str, **filters: Any) -> Optional[str]:
    query = client.table(table).select(column)
    for key, value in filters.items():
        query = query.eq(key, value)
    rows = list(query.order(column, desc=True).limit(1).execute().data or [])
    return str(rows[0].get(column))[:10] if rows and rows[0].get(column) else None


def load_watchdog_state(client: Any, market_date: str) -> Dict[str, Any]:
    batches = list((client.table("pokemon_scrape_batches")
                    .select("id,market_date,status,created_at,started_at,updated_at,completed_at")
                    .eq("market_date", market_date).limit(1).execute()).data or [])
    return {
        "batch": batches[0] if batches else None,
        "authority_dates": {
            "accepted_market_quality": _latest_date(client, "pokemon_market_date_quality", "market_date", status="READY"),
            "set_value": _latest_date(client, "pokemon_set_value_daily_history", "snapshot_date", value_scope="standard"),
            "set_market_dashboard": _latest_date(client, "pokemon_set_market_dashboard_snapshot_latest", "market_date"),
            "sealed_snapshot": _latest_date(client, "pokemon_set_sealed_market_snapshot_latest", "market_date"),
            "global_market_index": _latest_date(client, "pokemon_market_index_daily_history", "market_date", tcg="pokemon"),
        },
    }


def run_watchdog(*, client: Any = supabase, now: Optional[datetime] = None) -> Dict[str, Any]:
    resolved_now = now or datetime.now(timezone.utc)
    market_date = resolved_now.astimezone(PHOENIX).date().isoformat()
    state = load_watchdog_state(client, market_date)
    failures = evaluate_watchdog_state(state, now=resolved_now)
    queued = 0
    for failure in failures:
        result = queue_alert(
            failure["alert_type"],
            title=f"Pokémon market watchdog: {failure['failure_class']} — {market_date}",
            message=failure["message"],
            severity="critical",
            dedupe_key=f"{failure['alert_type']}:{market_date}:{failure['failure_class']}",
            payload=failure,
        )
        queued += int(result is not None)
    return {"healthy": not failures, "market_date": market_date, "failure_count": len(failures),
            "queued_or_deduplicated_count": queued, "failures": failures, "state": state}


def main() -> int:
    argparse.ArgumentParser(description=__doc__).parse_args()
    report = run_watchdog()
    print(json.dumps(report, indent=2, sort_keys=True, default=str))
    return 0 if report["healthy"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
