"""Publish the bounded Market Explorer V2 daily serving projection.

V1 daily-state storage was retired on 2026-09-09. This module intentionally
contains no read or write path to the retired V1 daily-state or interval
relations. The database owns V2 materialization and exact reconciliation via
``publish_pokemon_market_explorer_daily_v2_for_set``; Python only resolves the
tracked set scope, enforces approved market dates, invokes that verified
publisher, and reports the result.

Historical dates outside the bounded V2 daily retention window are not
materialized here. Market Explorer serves those dates from the V2 interval
fallback authority.
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
from backend.db.services.pokemon_market_explorer_query_service import resolve_tracked_set_ids

LOG = logging.getLogger("market_explorer_daily_projection_publish")

AUTHORITY_RPC = "get_pokemon_canonical_card_variant_authority"
DATE_QUALITY_TABLE = "pokemon_market_date_quality"
MERGE_LEDGER_TABLE = "pokemon_market_explorer_variant_merge_ledger"
SETS_TABLE = "sets"
V2_DAILY_STATES_TABLE = "pokemon_market_explorer_card_daily_states_v2_shadow"
V2_COVERAGE_TABLE = "pokemon_market_explorer_card_daily_coverage_v2_shadow"
V2_INTERVAL_TABLE = "pokemon_market_price_intervals_v2_shadow"
V2_PUBLISH_RPC = "publish_pokemon_market_explorer_daily_v2_for_set"
V2_VERIFY_RPC = "verify_pokemon_market_explorer_daily_v2_for_set"
V2_RETENTION_DAYS = 100

# Compatibility exports for callers that imported the old generic names.
# They now point exclusively at V2 authority.
DAILY_STATES_TABLE = V2_DAILY_STATES_TABLE
COVERAGE_TABLE = V2_COVERAGE_TABLE
INTERVAL_TABLE = V2_INTERVAL_TABLE

APPROVED_STATUSES = ("READY", "LEGACY_VERIFIED")


def _paged(query_factory: Any, *, page_size: int = 1000) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    start = 0
    while True:
        page = list(query_factory().range(start, start + page_size - 1).execute().data or [])
        rows.extend(page)
        if len(page) < page_size:
            return rows
        start += page_size


def _to_date(value: Any) -> date:
    if isinstance(value, date):
        return value
    return date.fromisoformat(str(value)[:10])


@dataclass
class SetReport:
    set_id: str
    mode: str = "unknown"
    approved_dates_considered: int = 0
    dates_materialized: int = 0
    rows_inserted: int = 0
    expected_rows: int = 0
    actual_rows: int = 0
    reconciled: bool = False
    coverage_before: dict[str, Any] | None = None
    coverage_after: dict[str, Any] | None = None
    predecessor_variants_excluded: int = 0
    no_nm_skips: int = 0
    stray_rows_purged: int = 0


@dataclass
class Summary:
    dry_run: bool
    sets_attempted: int = 0
    sets_new: int = 0
    sets_appended: int = 0
    sets_up_to_date: int = 0
    sets_reconciliation_failed: int = 0
    coverage_rows_repaired: int = 0
    total_rows_inserted: int = 0
    failures: int = 0
    elapsed_seconds: float = 0.0
    reports: list[dict[str, Any]] = field(default_factory=list)


def load_set_ids(client: Any, requested: Sequence[str], era_ids: Sequence[str] = ()) -> list[str]:
    tracked = set(resolve_tracked_set_ids(client))
    selected = {str(value) for value in requested if value}
    if selected:
        return sorted(selected & tracked)
    eras = sorted({str(value) for value in era_ids if value})
    if not eras:
        return sorted(tracked)
    rows = _paged(lambda: client.table(SETS_TABLE).select("id,era_id").in_("era_id", eras).order("id"))
    return sorted(tracked & {str(row["id"]) for row in rows if row.get("id")})


def load_approved_dates(
    client: Any, *, after: date | None = None, through: date | None = None,
) -> list[str]:
    query = (
        client.table(DATE_QUALITY_TABLE)
        .select("market_date")
        .eq("tcg", "pokemon")
        .in_("status", list(APPROVED_STATUSES))
    )
    if after is not None:
        query = query.gt("market_date", after.isoformat())
    if through is not None:
        query = query.lte("market_date", through.isoformat())
    rows = _paged(lambda: query.order("market_date"))
    return sorted({str(row["market_date"])[:10] for row in rows if row.get("market_date")})


def load_coverage(client: Any, set_id: str) -> dict[str, Any] | None:
    rows = list(
        client.table(V2_COVERAGE_TABLE)
        .select("set_id,retained_from,computed_through,row_count,retention_days,refreshed_at")
        .eq("set_id", set_id)
        .limit(1)
        .execute().data
        or []
    )
    return dict(rows[0]) if rows else None


def load_variant_ids_for_set(client: Any, set_id: str) -> list[str]:
    rows = _paged(lambda: client.rpc(AUTHORITY_RPC, {"p_set_ids": [set_id]}))
    return sorted({str(row["card_variant_id"]) for row in rows if row.get("card_variant_id")})


def load_retired_predecessor_ids(client: Any, variant_ids: Sequence[str]) -> set[str]:
    if not variant_ids:
        return set()
    rows = _paged(
        lambda: client.table(MERGE_LEDGER_TABLE)
        .select("predecessor_variant_id")
        .in_("predecessor_variant_id", list(variant_ids))
    )
    return {str(row["predecessor_variant_id"]) for row in rows if row.get("predecessor_variant_id")}


def verify_set_v2(
    client: Any, *, set_id: str, through_date: str, retention_days: int = V2_RETENTION_DAYS,
) -> dict[str, Any]:
    response = client.rpc(
        V2_VERIFY_RPC,
        {
            "p_set_id": str(set_id),
            "p_through_date": str(through_date)[:10],
            "p_retention_days": int(retention_days),
        },
    ).execute()
    return dict(response.data or {})


def publish_set_v2(
    client: Any,
    *,
    set_id: str,
    through_date: str,
    retention_days: int = V2_RETENTION_DAYS,
    force_rebuild: bool = False,
) -> dict[str, Any]:
    response = client.rpc(
        V2_PUBLISH_RPC,
        {
            "p_set_id": str(set_id),
            "p_through_date": str(through_date)[:10],
            "p_retention_days": int(retention_days),
            "p_force_rebuild": bool(force_rebuild),
        },
    ).execute()
    result = dict(response.data or {})
    if result.get("status") != "verified" or result.get("reconciled") is not True:
        raise RuntimeError(f"V2 publication returned an unverified result for {set_id}: {result}")
    return result


def _mode_before_publish(coverage: dict[str, Any] | None, through_date: str) -> str:
    if not coverage:
        return "new"
    computed = str(coverage.get("computed_through") or "")[:10]
    return "up_to_date" if computed >= through_date else "append"


def process_set(
    client: Any,
    *,
    commit: bool,
    set_id: str,
    through_date: str,
    retention_days: int = V2_RETENTION_DAYS,
    force_rebuild: bool = False,
) -> SetReport:
    coverage_before = load_coverage(client, set_id)
    planned_mode = "rebuild" if force_rebuild else _mode_before_publish(coverage_before, through_date)
    report = SetReport(set_id=set_id, mode=planned_mode, coverage_before=coverage_before)

    if not commit:
        report.coverage_after = coverage_before
        return report

    result = publish_set_v2(
        client,
        set_id=set_id,
        through_date=through_date,
        retention_days=retention_days,
        force_rebuild=force_rebuild,
    )
    report.mode = str(result.get("mode") or planned_mode)
    report.expected_rows = int(result.get("expected_rows") or 0)
    report.actual_rows = int(result.get("actual_rows") or 0)
    report.reconciled = bool(result.get("reconciled"))
    report.coverage_after = load_coverage(client, set_id)
    if coverage_before is None:
        report.dates_materialized = 1
    elif str(coverage_before.get("computed_through") or "")[:10] < through_date:
        report.dates_materialized = 1
    if report.mode == "rebuilt_after_drift":
        report.stray_rows_purged = int(result.get("mismatch_rows") or 0)
    return report


# Kept as a compatibility helper for old test/import surfaces. Runtime code no
# longer calls it; V2 drift is repaired transactionally by publish_set_v2.
def purge_ineligible_daily_state_rows(
    client: Any, *, commit: bool, set_id: str, eligible_variant_ids: Sequence[str],
) -> int:
    eligible = {str(value) for value in eligible_variant_ids}
    rows = _paged(
        lambda: client.table(V2_DAILY_STATES_TABLE)
        .select("card_variant_id")
        .eq("set_id", set_id)
    )
    stray = sorted({str(row.get("card_variant_id")) for row in rows if row.get("card_variant_id")} - eligible)
    if commit and stray:
        raise RuntimeError(
            "Direct V2 daily-state deletion is intentionally disabled; invoke the verified V2 publisher "
            "with force_rebuild=True so interval authority reconstructs the set transactionally."
        )
    return len(stray)


def run_publish(
    client: Any,
    *,
    commit: bool,
    set_ids: Sequence[str] = (),
    era_ids: Sequence[str] = (),
    through_date: date | None = None,
    retention_days: int = V2_RETENTION_DAYS,
    force_rebuild: bool = False,
) -> dict[str, Any]:
    started = time.monotonic()
    summary = Summary(dry_run=not commit)

    try:
        approved_dates = load_approved_dates(client, through=through_date)
        if not approved_dates:
            raise RuntimeError("no READY/LEGACY_VERIFIED Pokemon market date is available")
        target = (through_date.isoformat() if through_date else approved_dates[-1])
        if target not in approved_dates:
            raise RuntimeError(f"market date {target} is not READY/LEGACY_VERIFIED")

        scopes = load_set_ids(client, set_ids, era_ids)
        for set_id in scopes:
            summary.sets_attempted += 1
            try:
                report = process_set(
                    client,
                    commit=commit,
                    set_id=set_id,
                    through_date=target,
                    retention_days=retention_days,
                    force_rebuild=force_rebuild,
                )
            except Exception as exc:  # noqa: BLE001 - report per-set failures and continue
                summary.failures += 1
                LOG.error(json.dumps({"event": "set_failed", "setId": set_id, "error": str(exc)}, sort_keys=True))
                continue

            if report.mode == "new":
                summary.sets_new += 1
            elif report.mode in {"append", "advanced"}:
                summary.sets_appended += 1
            elif report.mode == "up_to_date":
                summary.sets_up_to_date += 1
            elif report.mode in {"rebuilt", "rebuilt_after_drift", "rebuild"}:
                summary.coverage_rows_repaired += 1

            if commit and not report.reconciled:
                summary.sets_reconciliation_failed += 1
            summary.total_rows_inserted += report.rows_inserted
            summary.reports.append(asdict(report))
            LOG.info(json.dumps({
                "event": "set_complete",
                "setId": set_id,
                "mode": report.mode,
                "reconciled": report.reconciled,
                "dryRun": not commit,
            }, sort_keys=True))
    except Exception as exc:  # noqa: BLE001
        summary.failures += 1
        LOG.error(json.dumps({"event": "publish_failed", "error": str(exc)}, sort_keys=True))

    summary.elapsed_seconds = round(time.monotonic() - started, 3)
    return asdict(summary)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--dry-run", action="store_true", help="Plan the V2 publication; perform no writes.")
    mode.add_argument("--commit", action="store_true", help="Publish through the verified V2 RPC.")
    parser.add_argument("--set-id", action="append", default=[], help="Limit to a set UUID; repeatable.")
    parser.add_argument("--era-id", action="append", default=[], help="Limit to tracked sets in an era; repeatable.")
    parser.add_argument("--through-date", type=date.fromisoformat, default=None,
                        help="Approved ISO market date (default: latest approved).")
    parser.add_argument("--retention-days", type=int, default=V2_RETENTION_DAYS)
    parser.add_argument("--force-rebuild", action="store_true",
                        help="Rebuild each selected set's bounded V2 daily window before verification.")
    return parser


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    args = build_parser().parse_args()
    report = run_publish(
        create_service_role_client(),
        commit=bool(args.commit),
        set_ids=args.set_id,
        era_ids=args.era_id,
        through_date=args.through_date,
        retention_days=args.retention_days,
        force_rebuild=bool(args.force_rebuild),
    )
    print(json.dumps(report, indent=2, sort_keys=True, default=str))
    return 1 if (report["failures"] or report["sets_reconciliation_failed"]) else 0


if __name__ == "__main__":
    raise SystemExit(main())
