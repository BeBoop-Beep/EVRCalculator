"""Bounded post-Explorer-publication Activity convergence worker.

The worker reads only persisted Explorer and Activity evidence. It imports no
provider client. A market remains unavailable while its serving Activity
generation is pinned to an older Explorer surface. In commit mode the worker
builds a validated replacement and promotes it only after re-checking that the
Explorer serving pointer has not moved.
"""
from __future__ import annotations

import argparse
import json
import time
from datetime import datetime, timezone
from typing import Any, Callable
from uuid import uuid4

from backend.db.services.market_activity_projection_repository import (
    SupabaseMarketActivitySink,
    SupabaseMarketActivitySource,
)
from backend.pricing_pipeline.market_activity_projection import MarketActivityProjectionBuilder

SURFACE_SERVING = "pokemon_market_explorer_surface_serving_v2"
SURFACE_GENERATIONS = "pokemon_market_explorer_surface_generations_v2"
ACTIVITY_SERVING = "market_activity_market_serving_v1"
ACTIVITY_GENERATIONS = "market_activity_generations_v1"
MAX_SUPPORTED_MARKETS = 10
MAX_RUNTIME_SECONDS = 600.0


def _rows(result: Any) -> list[dict[str, Any]]:
    return [dict(row) for row in (getattr(result, "data", result) or [])]


def _surface(client: Any) -> dict[str, Any]:
    pointer = _rows(client.table(SURFACE_SERVING).select("generation_id").eq(
        "singleton", 1).limit(1).execute())
    generation_id = str((pointer[0] if pointer else {}).get("generation_id") or "")
    if not generation_id:
        raise RuntimeError("EXPLORER_SURFACE_NOT_SERVING")
    rows = _rows(client.table(SURFACE_GENERATIONS).select(
        "generation_id,market_date,state"
    ).eq("generation_id", generation_id).limit(1).execute())
    generation = rows[0] if rows else {}
    if generation.get("state") != "VALIDATED" or not generation.get("market_date"):
        raise RuntimeError("EXPLORER_SURFACE_NOT_VALIDATED")
    return generation


def activity_coherence(client: Any) -> dict[str, Any]:
    surface = _surface(client)
    serving = _rows(client.table(ACTIVITY_SERVING).select(
        "market_key,activity_generation_id"
    ).execute())
    supported = [row for row in serving if row.get("activity_generation_id")]
    ids = [str(row["activity_generation_id"]) for row in supported]
    generations = (_rows(client.table(ACTIVITY_GENERATIONS).select(
        "activity_generation_id,surface_generation_id,state,serving_state,as_of"
    ).in_("activity_generation_id", ids).execute()) if ids else [])
    by_id = {str(row["activity_generation_id"]): row for row in generations}
    markets = []
    for pointer in sorted(supported, key=lambda row: str(row.get("market_key") or "")):
        generation_id = str(pointer["activity_generation_id"])
        generation = by_id.get(generation_id) or {}
        coherent = (
            generation.get("state") == "VALIDATED"
            and generation.get("serving_state") == "SERVING"
            and str(generation.get("surface_generation_id") or "") == str(surface["generation_id"])
            and str(generation.get("as_of") or "")[:10] == str(surface["market_date"])[:10]
        )
        markets.append({
            "marketKey": pointer["market_key"], "activityGenerationId": generation_id,
            "surfaceGenerationId": generation.get("surface_generation_id"),
            "asOf": str(generation.get("as_of") or "")[:10] or None,
            "coherent": coherent,
        })
    return {
        "surfaceGenerationId": str(surface["generation_id"]),
        "marketDate": str(surface["market_date"])[:10],
        "supportedMarketCount": len(markets),
        "coherentMarketCount": sum(int(row["coherent"]) for row in markets),
        "markets": markets,
    }


def validate_candidate(client: Any, generation_id: str, market_key: str) -> dict[str, Any]:
    """Read-only persisted-stage receipt; does not alter serving authority."""
    surface = _surface(client)
    generations = _rows(client.table(ACTIVITY_GENERATIONS).select(
        "activity_generation_id,as_of,surface_generation_id,state,serving_state,diagnostics"
    ).eq("activity_generation_id", generation_id).limit(1).execute())
    generation = generations[0] if generations else {}
    rosters = _rows(client.table("market_activity_rosters_v1").select(
        "market_key,roster_as_of,roster_denominator,roster_revision"
    ).eq("activity_generation_id", generation_id).eq("market_key", market_key).limit(1).execute())
    roster = rosters[0] if rosters else {}
    members = _rows(client.table("market_activity_roster_members_v1").select("rank,instrument_key").eq(
        "activity_generation_id", generation_id).eq("market_key", market_key).execute())
    payloads = _rows(client.table("market_activity_instrument_payloads_v1").select("instrument_key").eq(
        "activity_generation_id", generation_id).execute())
    series = _rows(client.table("market_activity_instrument_series_meta_v1").select("instrument_key").eq(
        "activity_generation_id", generation_id).execute())
    groups = _rows(client.table("market_activity_group_payloads_v1").select("window_days,payload").eq(
        "activity_generation_id", generation_id).eq("market_key", market_key).execute())
    daily_query = client.table("market_activity_daily_v1").select(
        "instrument_key", count="exact"
    ).eq("activity_generation_id", generation_id).limit(1).execute()
    daily_count = int(getattr(daily_query, "count", None) or len(_rows(daily_query)))
    windows = sorted(int(row["window_days"]) for row in groups)
    fingerprints_valid = all(
        isinstance((row.get("payload") or {}).get("evidenceFingerprint"), str)
        and len((row.get("payload") or {})["evidenceFingerprint"]) == 64
        for row in groups
    )
    expected = int(roster.get("roster_denominator") or 0)
    errors = []
    if generation.get("state") != "VALIDATED": errors.append("GENERATION_NOT_VALIDATED")
    if str(generation.get("surface_generation_id") or "") != str(surface["generation_id"]): errors.append("SURFACE_GENERATION_MISMATCH")
    if str(generation.get("as_of") or "")[:10] != str(surface["market_date"])[:10]: errors.append("AS_OF_MISMATCH")
    if not roster: errors.append("ROSTER_MISSING")
    if len(members) != expected: errors.append("ROSTER_MEMBER_COUNT_MISMATCH")
    if len(payloads) != expected: errors.append("PAYLOAD_COUNT_MISMATCH")
    if len(series) != expected: errors.append("SERIES_META_COUNT_MISMATCH")
    if windows != [7, 30, 90, 180]: errors.append("GROUP_WINDOWS_MISMATCH")
    if not fingerprints_valid: errors.append("GROUP_EVIDENCE_INVALID")
    if daily_count <= 0: errors.append("HISTORY_EMPTY")
    return {
        "generationId": generation_id, "marketKey": market_key,
        "surfaceGenerationId": generation.get("surface_generation_id"),
        "currentSurfaceGenerationId": str(surface["generation_id"]),
        "asOf": str(generation.get("as_of") or "")[:10] or None,
        "state": generation.get("state"), "servingState": generation.get("serving_state"),
        "rosterCount": len(members), "rosterDenominator": expected,
        "payloadCount": len(payloads), "seriesMetaCount": len(series),
        "groupWindows": windows, "dailyHistoryRows": daily_count,
        "capabilityEligibleAfterPromotion": not errors,
        "errors": errors, "promoted": False, "providerCalls": 0,
    }


def run_post_publication(
    client: Any, *, commit: bool = False, max_markets: int = MAX_SUPPORTED_MARKETS,
    max_seconds: float = MAX_RUNTIME_SECONDS,
    builder_factory: Callable[[str], MarketActivityProjectionBuilder] | None = None,
) -> dict[str, Any]:
    if not 1 <= max_markets <= MAX_SUPPORTED_MARKETS:
        raise ValueError(f"max_markets must be between 1 and {MAX_SUPPORTED_MARKETS}")
    if not 1 <= max_seconds <= MAX_RUNTIME_SECONDS:
        raise ValueError(f"max_seconds must be between 1 and {MAX_RUNTIME_SECONDS}")
    started = time.monotonic()
    before = activity_coherence(client)
    stale = [row for row in before["markets"] if not row["coherent"]]
    reports: list[dict[str, Any]] = []
    factory = builder_factory or (lambda _market: MarketActivityProjectionBuilder(
        SupabaseMarketActivitySource(client), SupabaseMarketActivitySink(client)))
    for market in stale[:max_markets]:
        if time.monotonic() - started >= max_seconds:
            reports.append({"marketKey": market["marketKey"], "status": "deferred", "reason": "runtime_bound"})
            break
        if not commit:
            reports.append({"marketKey": market["marketKey"], "status": "unavailable_pending_refresh"})
            continue
        generation_id = str(uuid4())
        result = factory(market["marketKey"]).build(
            market["marketKey"], as_of=before["marketDate"], generation_id=generation_id,
        )
        report = {"marketKey": market["marketKey"], "generationId": generation_id,
                  "buildState": result.get("state"), "status": "validation_failed"}
        if result.get("state") != "VALIDATED":
            reports.append(report)
            continue
        current = _surface(client)
        if str(current["generation_id"]) != before["surfaceGenerationId"]:
            report.update({"status": "surface_moved", "promoted": False})
            reports.append(report)
            continue
        promoted = bool(client.rpc("promote_market_activity_generation_v1", {
            "p_activity_generation_id": generation_id,
        }).execute().data)
        report.update({"status": "promoted" if promoted else "promotion_rejected", "promoted": promoted})
        reports.append(report)
    after = activity_coherence(client)
    return {
        "mode": "commit" if commit else "check", "providerCalls": 0,
        "surfaceGenerationId": before["surfaceGenerationId"], "marketDate": before["marketDate"],
        "before": before, "reports": reports, "after": after,
        "elapsedSeconds": round(time.monotonic() - started, 3),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--check", action="store_true")
    mode.add_argument("--commit", action="store_true")
    mode.add_argument("--validate-candidate", action="store_true")
    parser.add_argument("--generation-id")
    parser.add_argument("--market-key")
    parser.add_argument("--max-markets", type=int, default=MAX_SUPPORTED_MARKETS)
    parser.add_argument("--max-seconds", type=float, default=MAX_RUNTIME_SECONDS)
    args = parser.parse_args()
    from backend.db.clients.supabase_client import create_service_role_client
    client = create_service_role_client()
    if args.validate_candidate:
        if not args.generation_id or not args.market_key:
            parser.error("--validate-candidate requires --generation-id and --market-key")
        result = validate_candidate(client, args.generation_id, args.market_key)
        print(json.dumps(result, sort_keys=True, default=str))
        return int(bool(result["errors"]))
    result = run_post_publication(client, commit=args.commit, max_markets=args.max_markets,
                                  max_seconds=args.max_seconds)
    print(json.dumps(result, sort_keys=True, default=str))
    return int(any(row.get("status") in {"validation_failed", "surface_moved", "promotion_rejected"}
                   for row in result["reports"]))


if __name__ == "__main__":
    raise SystemExit(main())
