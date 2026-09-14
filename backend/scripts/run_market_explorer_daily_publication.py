"""Coordinated V2-only daily publication for Market Explorer card prices.

Normal daily contract for an approved Pokemon market date:
  1. Refresh current canonical Market Explorer metadata.
  2. Publish every tracked set through the verified bounded V2 daily publisher.
  3. Fail closed if any set does not exactly reconcile to V2 interval authority.
  4. Defer maintained-cache building to the separate resource-guarded worker.

Historical repair uses the same V2 publisher with ``force_rebuild=True``. Only
the bounded V2 daily window is rematerialized; older history remains served by
the V2 interval fallback. V1 daily-state/coverage storage is not read or
written anywhere in this module.
"""
from __future__ import annotations

import argparse
import json
import logging
import time
from dataclasses import asdict, dataclass, field
from datetime import date
from typing import Any, Sequence

from backend.db.clients.supabase_client import create_service_role_client
from backend.db.services.market_explorer_maintained_cache_ops import caches_overlapping_set_ids
from backend.db.services.pokemon_market_explorer_query_service import resolve_tracked_set_ids
from backend.scripts.publish_market_explorer_daily_projection import (
    APPROVED_STATUSES,
    AUTHORITY_RPC,
    DATE_QUALITY_TABLE,
    MERGE_LEDGER_TABLE,
    V2_COVERAGE_TABLE,
    V2_RETENTION_DAYS,
    _paged,
    publish_set_v2,
    run_publish,
)

LOG = logging.getLogger("market_explorer_daily_publication")

CURRENT_METADATA_TABLE = "pokemon_market_explorer_card_current_metadata"
CURRENT_METADATA_REFRESH_RPC = "refresh_pokemon_market_explorer_card_current_metadata"
COVERAGE_TABLE = V2_COVERAGE_TABLE
CARDS_ASSET_TABLE = "pokemon_market_explorer_cache_state"
INVALIDATE_CACHE_SCOPED_RPC = "invalidate_pokemon_market_explorer_query_cache_scoped"


# --- Market date resolution --------------------------------------------------

def resolve_latest_approved_market_date(client: Any) -> str | None:
    rows = _paged(
        lambda: client.table(DATE_QUALITY_TABLE)
        .select("market_date")
        .eq("tcg", "pokemon")
        .in_("status", list(APPROVED_STATUSES))
        .order("market_date")
    )
    dates = sorted({str(row["market_date"])[:10] for row in rows if row.get("market_date")})
    return dates[-1] if dates else None


def market_date_is_approved(client: Any, market_date: str) -> bool:
    rows = list(
        client.table(DATE_QUALITY_TABLE)
        .select("status")
        .eq("tcg", "pokemon")
        .eq("market_date", str(market_date)[:10])
        .limit(1)
        .execute().data
        or []
    )
    return bool(rows and str(rows[0].get("status")) in APPROVED_STATUSES)


# --- Current metadata --------------------------------------------------------

@dataclass
class MetadataRefreshReport:
    expected_row_count: int = 0
    rows_upserted: int = 0
    rows_removed: int = 0
    retired_predecessor_excluded: int = 0
    catalog_only_sets_excluded: int = 0
    sets_considered: int = 0


def load_retired_predecessor_ids_global(client: Any) -> set[str]:
    rows = _paged(lambda: client.table(MERGE_LEDGER_TABLE).select("predecessor_variant_id"))
    return {str(row["predecessor_variant_id"]) for row in rows if row.get("predecessor_variant_id")}


def load_current_authority_rows(client: Any, set_ids: Sequence[str]) -> list[dict[str, Any]]:
    if not set_ids:
        return []
    retired = load_retired_predecessor_ids_global(client)
    rows = _paged(lambda: client.rpc(AUTHORITY_RPC, {"p_set_ids": list(set_ids)}))
    out: list[dict[str, Any]] = []
    seen: set[str] = set()
    for row in rows:
        variant_id = str(row.get("card_variant_id") or "")
        if not variant_id or variant_id in retired or variant_id in seen:
            continue
        seen.add(variant_id)
        out.append({"card_variant_id": variant_id, "set_id": str(row.get("set_id") or "")})
    return out


def refresh_current_metadata(client: Any, *, commit: bool) -> MetadataRefreshReport:
    tracked_set_ids = resolve_tracked_set_ids(client)
    report = MetadataRefreshReport(sets_considered=len(tracked_set_ids))
    expected_rows = load_current_authority_rows(client, tracked_set_ids)
    report.expected_row_count = len(expected_rows)
    if not commit:
        return report

    rows_before = _paged(lambda: client.table(CURRENT_METADATA_TABLE).select("card_variant_id"))
    ids_before = {str(row["card_variant_id"]) for row in rows_before if row.get("card_variant_id")}

    client.rpc(CURRENT_METADATA_REFRESH_RPC, {"p_set_ids": list(tracked_set_ids)}).execute()

    rows_after = _paged(lambda: client.table(CURRENT_METADATA_TABLE).select("card_variant_id"))
    ids_after = {str(row["card_variant_id"]) for row in rows_after if row.get("card_variant_id")}
    report.rows_upserted = len(ids_after)
    report.rows_removed = len(ids_before - ids_after)
    return report


# --- Maintained-cache deferral ----------------------------------------------

def deferred_cache_report(
    client: Any | None = None, *, only_set_ids: Sequence[str] = (),
) -> dict[str, Any]:
    report: dict[str, Any] = {"status": "deferred", "reason": "separate_operational_worker"}
    if only_set_ids and client is not None:
        affected = caches_overlapping_set_ids(client, only_set_ids)
        report["affected"] = sorted(
            str(row.get("query_fingerprint") or "") for row in affected
            if row.get("query_fingerprint")
        )
    return report


# --- Normal daily publication ------------------------------------------------

@dataclass
class DailyPublicationSummary:
    dry_run: bool
    market_date: str | None = None
    status: str = "not_started"
    metadata_refresh: dict[str, Any] | None = None
    projection: dict[str, Any] | None = None
    v2_projection: dict[str, Any] | None = None
    caches: dict[str, Any] | None = None
    elapsed_seconds: float = 0.0
    error: str | None = None


def advance_v2_daily_shadow(
    client: Any,
    *,
    commit: bool,
    set_ids: Sequence[str],
    through_date: str,
    retention_days: int = V2_RETENTION_DAYS,
) -> dict[str, Any]:
    """Compatibility helper: publish the selected sets through verified V2 only."""
    report: dict[str, Any] = {
        "through_date": str(through_date)[:10],
        "retention_days": retention_days,
        "sets_considered": len(set_ids),
        "sets_advanced": 0,
        "failures": [],
        "reports": [],
    }
    if not commit:
        return report
    for set_id in set_ids:
        try:
            result = publish_set_v2(
                client,
                set_id=str(set_id),
                through_date=str(through_date)[:10],
                retention_days=retention_days,
            )
            report["sets_advanced"] += 1
            report["reports"].append(result)
        except Exception as exc:  # noqa: BLE001
            report["failures"].append({"set_id": str(set_id), "error": f"{type(exc).__name__}: {exc}"})
    return report


def run_daily_publication(
    client: Any, *, commit: bool, market_date: str | None = None,
) -> dict[str, Any]:
    started = time.monotonic()
    summary = DailyPublicationSummary(dry_run=not commit)

    resolved = str(market_date)[:10] if market_date else resolve_latest_approved_market_date(client)
    if not resolved or not market_date_is_approved(client, resolved):
        summary.status = "not_ready"
        summary.error = f"market date {resolved!r} is not READY/LEGACY_VERIFIED; refusing to publish"
        summary.elapsed_seconds = round(time.monotonic() - started, 3)
        return asdict(summary)
    summary.market_date = resolved

    metadata_report = refresh_current_metadata(client, commit=commit)
    summary.metadata_refresh = asdict(metadata_report)

    tracked_set_ids = resolve_tracked_set_ids(client)
    projection_report = run_publish(
        client,
        commit=commit,
        set_ids=tracked_set_ids,
        through_date=date.fromisoformat(resolved),
        retention_days=V2_RETENTION_DAYS,
    )
    summary.projection = projection_report
    # Kept temporarily for response-contract compatibility. Both fields now
    # describe the same and only V2 projection; there is no V1 phase.
    summary.v2_projection = projection_report

    if projection_report.get("failures") or projection_report.get("sets_reconciliation_failed"):
        summary.status = "projection_failed"
        summary.error = "one or more sets failed verified V2 daily publication"
        summary.elapsed_seconds = round(time.monotonic() - started, 3)
        return asdict(summary)

    summary.caches = deferred_cache_report()
    summary.status = "ok"
    summary.elapsed_seconds = round(time.monotonic() - started, 3)
    return asdict(summary)


# --- Historical repair -------------------------------------------------------

@dataclass
class HistoricalRepairSummary:
    dry_run: bool
    repair_start: str
    repair_through: str
    set_ids: list[str] = field(default_factory=list)
    reprojected_rows: int = 0
    reconciled: bool = False
    expected_rows: int = 0
    actual_rows: int = 0
    coverage_repaired: list[dict[str, Any]] = field(default_factory=list)
    stray_rows_purged: int = 0
    repair_generation_bumped: bool = False
    cache_entries_invalidated: int = 0
    caches: dict[str, Any] | None = None
    status: str = "not_started"
    error: str | None = None
    elapsed_seconds: float = 0.0


def run_historical_repair(
    client: Any,
    *,
    commit: bool,
    set_ids: Sequence[str],
    repair_start: date,
    repair_through: date | None = None,
) -> dict[str, Any]:
    """Rebuild the bounded V2 window for affected sets and invalidate caches.

    ``repair_start`` identifies the historical correction for audit/reporting.
    V2 does not rematerialize unbounded history: dates older than the retained
    daily window are served directly from V2 intervals. A force rebuild
    therefore reconstructs the complete current bounded window from interval
    authority and verifies it transactionally for each affected set.
    """
    started = time.monotonic()
    selected = sorted({str(value) for value in set_ids if value})
    resolved_through = (
        repair_through.isoformat() if repair_through else resolve_latest_approved_market_date(client)
    )
    summary = HistoricalRepairSummary(
        dry_run=not commit,
        repair_start=repair_start.isoformat(),
        repair_through=str(resolved_through or ""),
        set_ids=selected,
    )

    if not selected:
        summary.status = "no_sets"
        summary.elapsed_seconds = round(time.monotonic() - started, 3)
        return asdict(summary)
    if not resolved_through or not market_date_is_approved(client, resolved_through):
        summary.status = "not_ready"
        summary.error = f"repair through date {resolved_through!r} is not READY/LEGACY_VERIFIED"
        summary.elapsed_seconds = round(time.monotonic() - started, 3)
        return asdict(summary)

    projection = run_publish(
        client,
        commit=commit,
        set_ids=selected,
        through_date=date.fromisoformat(resolved_through),
        retention_days=V2_RETENTION_DAYS,
        force_rebuild=True,
    )

    reports = list(projection.get("reports") or [])
    summary.expected_rows = sum(int(row.get("expected_rows") or 0) for row in reports)
    summary.actual_rows = sum(int(row.get("actual_rows") or 0) for row in reports)
    summary.reconciled = (
        not projection.get("failures")
        and not projection.get("sets_reconciliation_failed")
        and (not commit or all(row.get("reconciled") is True for row in reports))
    )
    summary.reprojected_rows = summary.actual_rows if commit else 0
    summary.coverage_repaired = [
        dict(row.get("coverage_after") or {}) for row in reports if row.get("coverage_after")
    ]

    if projection.get("failures") or projection.get("sets_reconciliation_failed"):
        summary.status = "reconciliation_failed"
        summary.error = "one or more sets failed verified V2 bounded rebuild"
        summary.elapsed_seconds = round(time.monotonic() - started, 3)
        return asdict(summary)

    if commit:
        response = client.rpc(INVALIDATE_CACHE_SCOPED_RPC, {"p_set_ids": selected}).execute()
        summary.cache_entries_invalidated = int(response.data or 0)
        summary.repair_generation_bumped = True

    summary.caches = deferred_cache_report(client, only_set_ids=selected)
    summary.status = "ok"
    summary.elapsed_seconds = round(time.monotonic() - started, 3)
    return asdict(summary)


# --- CLI ---------------------------------------------------------------------

def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--dry-run", action="store_true", help="Plan the run; perform no writes.")
    mode.add_argument("--commit", action="store_true", help="Execute through verified V2 publication.")
    parser.add_argument("--market-date", type=date.fromisoformat, default=None,
                        help="Override target market date (default: latest approved).")
    repair = parser.add_argument_group("historical repair")
    repair.add_argument("--repair", action="store_true", help="Force-rebuild affected bounded V2 daily windows.")
    repair.add_argument("--repair-set-id", action="append", default=[], help="Repeatable set UUID.")
    repair.add_argument("--repair-start", type=date.fromisoformat, default=None)
    repair.add_argument("--repair-through", type=date.fromisoformat, default=None)
    return parser


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    args = build_parser().parse_args()
    client = create_service_role_client()
    commit = bool(args.commit)

    if args.repair:
        if not args.repair_start or not args.repair_set_id:
            raise SystemExit("--repair requires --repair-start and at least one --repair-set-id")
        report = run_historical_repair(
            client,
            commit=commit,
            set_ids=args.repair_set_id,
            repair_start=args.repair_start,
            repair_through=args.repair_through,
        )
        print(json.dumps(report, indent=2, sort_keys=True, default=str))
        return 1 if report["status"] != "ok" else 0

    report = run_daily_publication(
        client,
        commit=commit,
        market_date=args.market_date.isoformat() if args.market_date else None,
    )
    print(json.dumps(report, indent=2, sort_keys=True, default=str))
    return 1 if report["status"] != "ok" else 0


if __name__ == "__main__":
    raise SystemExit(main())
