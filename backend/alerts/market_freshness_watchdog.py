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
EXPLORER_CONVERGENCE_AUTHORITY_KEYS = ("explorer_v2",)
EXPLORE_MOVERS_BUILDER = "pokemon_mixed_market_seven_day_movers_v3"
EXPLORE_MOVERS_UNIVERSE_CONTRACT = "serving_cards_and_sealed_exact_instruments_v1"
EXPLORE_MOVERS_BASELINE_GUARD = "target_baseline_reversion_guard_v1"

REQUIRED_AUTHORITY_DATE_KEYS = (
    "accepted_market_quality",
    "set_value",
    "set_market_dashboard",
    "sealed_snapshot",
    "global_market_index",
    "edition_stable_raw",
    "explore_set_value",
    "explore_card_movers",
    "explorer_v2",
    "card_market_current",
    "sealed_product_current",
)


def _clock(value: str) -> time:
    hour, minute = (int(part) for part in value.split(":", 1))
    return time(hour, minute)


def _bounded_error_summary(exc: Exception, limit: int = 500) -> str:
    summary = " ".join(str(exc).split())
    return summary[:limit] or exc.__class__.__name__


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

        explorer_deadline = _clock(
            os.getenv("MARKET_EXPLORER_CONVERGENCE_DEADLINE_AZ", "10:30")
        )
        required_keys = tuple(
            key for key in REQUIRED_AUTHORITY_DATE_KEYS
            if (
                local_now.time() >= explorer_deadline
                or key not in EXPLORER_CONVERGENCE_AUTHORITY_KEYS
            )
        )
        missing_authorities = [key for key in required_keys if not dates.get(key)]
        if missing_authorities:
            failures.append({
                "alert_type": "market_snapshot_date_divergence",
                "failure_class": "authority_date_missing",
                "message": f"Public market authorities are missing dates: {', '.join(missing_authorities)}.",
                "actual_dates": {key: dates.get(key) for key in required_keys},
                "missing_authorities": missing_authorities,
            })

        present = {key: dates.get(key) for key in required_keys if dates.get(key)}
        if present and len(set(present.values())) > 1:
            failures.append({"alert_type": "market_snapshot_date_divergence", "failure_class": "authority_date_mismatch",
                             "message": f"Public market authorities disagree: {present}.", "actual_dates": present})

        movers = dict(state.get("explore_card_movers_contract") or {})
        candidate_instruments = int(movers.get("candidate_instrument_count") or 0)
        published_instruments = int(movers.get("published_instrument_count") or 0)
        expected_published = min(50, candidate_instruments)
        mover_contract_ok = (
            movers.get("builder") == EXPLORE_MOVERS_BUILDER
            and movers.get("universe_contract") == EXPLORE_MOVERS_UNIVERSE_CONTRACT
            and movers.get("baseline_guard") == EXPLORE_MOVERS_BASELINE_GUARD
            and int(movers.get("card_constituent_count") or 0) >= 1000
            and int(movers.get("sealed_constituent_count") or 0) > 0
            and int(movers.get("card_candidate_count") or 0) > 0
            and int(movers.get("sealed_candidate_count") or 0) > 0
            and candidate_instruments > 0
            and published_instruments == expected_published
            and published_instruments == int(movers.get("card_count") or 0)
            and int(movers.get("published_card_count") or 0)
                + int(movers.get("published_sealed_count") or 0)
                == published_instruments
            and int(movers.get("published_sealed_count") or 0) > 0
            and int(movers.get("eligible_set_count") or 0) > 0
        )
        if not mover_contract_ok:
            failures.append({
                "alert_type": "market_snapshot_semantics_invalid",
                "failure_class": "explore_card_movers_universe_contract",
                "message": (
                    "Explore 7D movers are current by date but are not the top 50 "
                    "combined exact-instrument card + sealed market ranking."
                ),
                "observed_contract": movers,
                "expected_contract": {
                    "builder": EXPLORE_MOVERS_BUILDER,
                    "universe_contract": EXPLORE_MOVERS_UNIVERSE_CONTRACT,
                    "baseline_guard": EXPLORE_MOVERS_BASELINE_GUARD,
                },
            })

    for failure in failures:
        failure["market_date"] = market_date
    return failures


def _latest_date(client: Any, table: str, column: str, **filters: Any) -> Optional[str]:
    query = client.table(table).select(column)
    for key, value in filters.items():
        query = query.eq(key, value)
    # Postgres sorts NULL values first for DESC unless NULLS LAST is requested.
    # Excluding NULL authority dates before ordering prevents one legacy/partial
    # row from hiding an otherwise-current publication surface.
    query = query.not_.is_(column, "null")
    rows = list(query.order(column, desc=True).limit(1).execute().data or [])
    return str(rows[0].get(column))[:10] if rows and rows[0].get(column) else None


def _explore_card_movers_contract(client: Any) -> Dict[str, Any]:
    rows = list(
        client.table("pokemon_explore_card_movers_snapshot_latest")
        .select("payload_json,card_count,eligible_set_count")
        .eq("tcg", "pokemon")
        .eq("scope", "explore")
        .eq("window_key", "7D")
        .limit(1)
        .execute().data or []
    )
    if not rows:
        return {}
    row = rows[0]
    payload = row.get("payload_json") or {}
    meta = payload.get("meta") or {}
    coverage = meta.get("coverage") or {}
    return {
        "builder": meta.get("builder"),
        "universe_contract": meta.get("universeContractVersion"),
        "baseline_guard": meta.get("baselineQualityGuardVersion"),
        "card_constituent_count": coverage.get("cardConstituentCount"),
        "sealed_constituent_count": coverage.get("sealedConstituentCount"),
        "card_candidate_count": coverage.get("cardCandidateCount"),
        "sealed_candidate_count": coverage.get("sealedCandidateCount"),
        "candidate_instrument_count": coverage.get("candidateInstrumentCount"),
        "published_card_count": coverage.get("publishedCardCount"),
        "published_sealed_count": coverage.get("publishedSealedCount"),
        "published_instrument_count": coverage.get("publishedInstrumentCount"),
        "card_count": row.get("card_count"),
        "eligible_set_count": row.get("eligible_set_count"),
    }


def _explorer_v2_serving_date(client: Any) -> Optional[str]:
    serving = list(
        client.table("pokemon_market_explorer_surface_serving_v2")
        .select("generation_id")
        .eq("singleton", 1)
        .limit(1)
        .execute().data or []
    )
    generation_id = str((serving[0] if serving else {}).get("generation_id") or "")
    if not generation_id:
        return None
    rows = list(
        client.table("pokemon_market_explorer_surface_generations_v2")
        .select("market_date,state")
        .eq("generation_id", generation_id)
        .limit(1)
        .execute().data or []
    )
    value = (rows[0] if rows else {}).get("market_date")
    return str(value)[:10] if value else None


def load_watchdog_state(client: Any, market_date: str) -> Dict[str, Any]:
    batches = list((client.table("pokemon_scrape_batches")
                    .select("id,market_date,status,created_at,started_at,updated_at,completed_at")
                    .eq("market_date", market_date).limit(1).execute()).data or [])
    return {
        "batch": batches[0] if batches else None,
        "explore_card_movers_contract": _explore_card_movers_contract(client),
        "authority_dates": {
            "accepted_market_quality": _latest_date(client, "pokemon_market_date_quality", "market_date", status="READY"),
            "set_value": _latest_date(client, "pokemon_set_value_daily_history", "snapshot_date", value_scope="standard"),
            "set_market_dashboard": _latest_date(client, "pokemon_set_market_dashboard_snapshot_latest", "latest_market_date"),
            "sealed_snapshot": _latest_date(client, "pokemon_set_sealed_market_snapshot_latest", "market_date"),
            "global_market_index": _latest_date(client, "pokemon_market_index_daily_history", "market_date", tcg="pokemon"),
            "edition_stable_raw": _latest_date(
                client, "pokemon_market_raw_edition_stable_daily_history_v1", "market_date",
            ),
            "explore_set_value": _latest_date(
                client, "pokemon_explore_set_value_snapshot_latest", "market_date",
                tcg="pokemon", scope="market",
            ),
            "explore_card_movers": _latest_date(
                client, "pokemon_explore_card_movers_snapshot_latest", "market_date",
                tcg="pokemon", scope="explore", window_key="7D",
            ),
            "explorer_v2": _explorer_v2_serving_date(client),
            "card_market_current": _latest_date(client, "card_market_usd_latest", "captured_at"),
            "sealed_product_current": _latest_date(client, "sealed_product_market_usd_latest", "captured_at"),
        },
    }


def _execution_failure(exc: Exception, *, market_date: str) -> Dict[str, Any]:
    error_summary = _bounded_error_summary(exc)
    return {
        "alert_type": "market_watchdog_execution_failed",
        "failure_class": "state_load_failed",
        "message": (
            "Market freshness watchdog could not load its authoritative state: "
            f"{exc.__class__.__name__}: {error_summary}"
        ),
        "market_date": market_date,
        "stage": "load_watchdog_state",
        "exception_type": exc.__class__.__name__,
        "error_summary": error_summary,
    }


def run_watchdog(*, client: Any = supabase, now: Optional[datetime] = None,
                 queue_failures: bool = True) -> Dict[str, Any]:
    resolved_now = now or datetime.now(timezone.utc)
    market_date = resolved_now.astimezone(PHOENIX).date().isoformat()
    try:
        state = load_watchdog_state(client, market_date)
    except Exception as exc:
        failure = _execution_failure(exc, market_date=market_date)
        queued = 0
        if queue_failures:
            result = queue_alert(
                failure["alert_type"],
                title=f"Pokémon market watchdog execution failed — {market_date}",
                message=failure["message"],
                severity="critical",
                dedupe_key=f"market_watchdog_execution_failed:{market_date}:load_watchdog_state",
                payload=failure,
            )
            queued = int(result is not None)
        return {
            "healthy": False,
            "execution_failed": True,
            "market_date": market_date,
            "failure_count": 1,
            "queued_or_deduplicated_count": queued,
            "queue_enabled": queue_failures,
            "failures": [failure],
            "state": {},
        }

    failures = evaluate_watchdog_state(state, now=resolved_now)
    queued = 0
    for failure in failures if queue_failures else []:
        result = queue_alert(
            failure["alert_type"],
            title=f"Pokémon market watchdog: {failure['failure_class']} — {market_date}",
            message=failure["message"],
            severity="critical",
            dedupe_key=f"{failure['alert_type']}:{market_date}:{failure['failure_class']}",
            payload=failure,
        )
        queued += int(result is not None)
    return {"healthy": not failures, "execution_failed": False, "market_date": market_date,
            "failure_count": len(failures), "queued_or_deduplicated_count": queued,
            "queue_enabled": queue_failures, "failures": failures, "state": state}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--health", action="store_true", help="Read-only evaluation; do not queue alerts")
    args = parser.parse_args()
    report = run_watchdog(queue_failures=not args.health)
    print(json.dumps(report, indent=2, sort_keys=True, default=str))
    return 0 if report["healthy"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
