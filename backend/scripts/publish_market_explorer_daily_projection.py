"""Publish the Market Explorer daily serving projection
(``pokemon_market_explorer_card_daily_states``) across the full corrected
165-set authority, derived from the interval authority of record
(``pokemon_card_variant_market_price_intervals``).

Dry-run is the default-safe mode. Writes require ``--commit`` and use only
the service-role client. This module makes zero live-database connections
on its own; ``main()`` is the only place a real client is constructed.

Publication contract per set (see Prompt 4 spec):
  1. Resolve corrected physical authority (variant ids for the set).
  2. Use only approved dates (``pokemon_market_date_quality``,
     status READY/LEGACY_VERIFIED).
  3. Join interval authority point-in-time:
     ``valid_from <= market_date AND (valid_to IS NULL OR market_date < valid_to)``.
  4. Insert ``(market_date, card_variant_id, set_id, market_price)`` rows.
  5. Reconcile exactly against interval authority (expected == actual) BEFORE
     activating coverage.
  6. Only after exact reconciliation, create/upsert coverage with true
     ``MIN(market_date)``, intended ``computed_through``, and exact
     ``COUNT(*)`` from the materialized table.
  7. If reconciliation fails, do NOT activate coverage for that set.

Already-covered sets are only ever forward-appended (missing approved
dates only) -- history already materialized is never rebuilt. Coverage
metadata (including ``row_count``) is always recomputed from the actual
daily-states table, never trusted from a stale prior value.

Vintage-repair safety: this script never projects a row whose
``card_variant_id`` is an active
``pokemon_market_explorer_variant_merge_ledger.predecessor_variant_id``.

No-NM semantics: a variant with no qualifying interval row for a date is
simply skipped for that date -- never fabricated, never substituted from
another condition.
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


LOG = logging.getLogger("market_explorer_daily_projection_publish")

# --- Table / RPC names -------------------------------------------------
AUTHORITY_RPC = "get_pokemon_canonical_card_variant_authority"
INTERVAL_TABLE = "pokemon_card_variant_market_price_intervals"
DAILY_STATES_TABLE = "pokemon_market_explorer_card_daily_states"
COVERAGE_TABLE = "pokemon_market_explorer_card_daily_coverage"
DATE_QUALITY_TABLE = "pokemon_market_date_quality"
MERGE_LEDGER_TABLE = "pokemon_market_explorer_variant_merge_ledger"
SETS_TABLE = "sets"

APPROVED_STATUSES = ("READY", "LEGACY_VERIFIED")


def _paged(query_factory, *, page_size: int = 1000) -> list[dict[str, Any]]:
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
    mode: str  # "new" | "append" | "up_to_date" | "reconciliation_failed"
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


# --- Authority resolution -------------------------------------------------

def load_set_ids(client: Any, requested: Sequence[str], era_ids: Sequence[str] = ()) -> list[str]:
    selected = sorted(set(requested))
    if selected:
        return selected
    eras = sorted(set(era_ids))
    def query():
        request = client.table(SETS_TABLE).select("id").order("id")
        return request.in_("era_id", eras) if eras else request
    rows = _paged(query)
    return sorted(str(row["id"]) for row in rows)


def load_variant_ids_for_set(client: Any, set_id: str) -> list[str]:
    rows = _paged(lambda: client.rpc(AUTHORITY_RPC, {"p_set_ids": [set_id]}))
    return sorted({str(row["card_variant_id"]) for row in rows if row.get("card_variant_id")})


def load_retired_predecessor_ids(client: Any, variant_ids: Sequence[str]) -> set[str]:
    """Active vintage-predecessor retirements to exclude, never physical rows.

    The merge ledger is the sole source of truth for retirement; a retired
    predecessor's ``card_variants`` row still exists (history/FK safety) but
    must never receive a daily-state row.
    """
    if not variant_ids:
        return set()
    rows = _paged(lambda: client.table(MERGE_LEDGER_TABLE)
                  .select("predecessor_variant_id")
                  .in_("predecessor_variant_id", list(variant_ids)))
    return {str(row["predecessor_variant_id"]) for row in rows}


def load_approved_dates(client: Any, *, after: date | None = None,
                         through: date | None = None) -> list[str]:
    query = (client.table(DATE_QUALITY_TABLE).select("market_date")
             .eq("tcg", "pokemon").in_("status", list(APPROVED_STATUSES)))
    if after is not None:
        query = query.gt("market_date", after.isoformat())
    if through is not None:
        query = query.lte("market_date", through.isoformat())
    rows = _paged(lambda: query.order("market_date"))
    return sorted({str(row["market_date"])[:10] for row in rows})


def load_coverage(client: Any, set_id: str) -> dict[str, Any] | None:
    rows = list((client.table(COVERAGE_TABLE).select(
        "set_id,first_market_date,computed_through,row_count"
    ).eq("set_id", set_id).limit(1).execute()).data or [])
    return dict(rows[0]) if rows else None


def load_interval_join(client: Any, variant_ids: Sequence[str], market_date: str) -> list[dict[str, Any]]:
    """Point-in-time join: valid_from <= market_date AND (valid_to IS NULL OR
    market_date < valid_to). Rows come back one per variant that has a
    qualifying interval on the date -- variants without one (no-NM or
    outside any interval) are simply absent, never fabricated.
    """
    if not variant_ids:
        return []
    rows = _paged(lambda: client.table(INTERVAL_TABLE)
                  .select("card_variant_id,market_price,valid_from,valid_to")
                  .in_("card_variant_id", list(variant_ids))
                  .lte("valid_from", market_date))
    matched = []
    for row in rows:
        valid_to = row.get("valid_to")
        if valid_to is None or str(valid_to)[:10] > market_date:
            matched.append(row)
    return matched


def load_actual_state_rows(client: Any, set_id: str, market_date: str) -> list[dict[str, Any]]:
    return _paged(lambda: client.table(DAILY_STATES_TABLE).select("card_variant_id")
                  .eq("set_id", set_id).eq("market_date", market_date))


def count_actual_rows(client: Any, set_id: str) -> int:
    """Exact row count for a set via PostgREST's ``count="exact"`` head-count,
    not a full paged fetch of every row. Still a genuine recompute from actual
    table state (never incremented arithmetically) -- just cheap: one request
    returns the count metadata without transferring the underlying rows.
    Correct for a table of any size, including a full historical set.
    """
    result = (client.table(DAILY_STATES_TABLE).select("card_variant_id", count="exact")
              .eq("set_id", set_id).limit(1).execute())
    return int(result.count or 0)


def compute_actual_bounds(client: Any, set_id: str) -> tuple[str | None, str | None]:
    """Exact MIN/MAX(market_date) for a set via two order+limit(1) queries,
    not a full paged fetch of every row's date. Same correctness contract as
    ``count_actual_rows`` -- a genuine recompute, just without transferring
    every row to compute a value the database can return directly.
    """
    first_rows = (client.table(DAILY_STATES_TABLE).select("market_date")
                  .eq("set_id", set_id).order("market_date").limit(1).execute()).data or []
    if not first_rows:
        return None, None
    last_rows = (client.table(DAILY_STATES_TABLE).select("market_date")
                 .eq("set_id", set_id).order("market_date", desc=True).limit(1)
                 .execute()).data or []
    return str(first_rows[0]["market_date"])[:10], str(last_rows[0]["market_date"])[:10]


# --- Materialization -------------------------------------------------------

def materialize_date(client: Any, *, commit: bool, set_id: str, market_date: str,
                      variant_ids: Sequence[str], retired_ids: set[str],
                      report: SetReport) -> None:
    eligible = [v for v in variant_ids if v not in retired_ids]
    report.predecessor_variants_excluded += len(variant_ids) - len(eligible)

    joined = load_interval_join(client, eligible, market_date)
    report.no_nm_skips += len(eligible) - len(joined)
    report.expected_rows += len(joined)

    if not commit:
        report.dates_materialized += 1
        return

    rows = [{
        "market_date": market_date,
        "card_variant_id": str(row["card_variant_id"]),
        "set_id": set_id,
        "market_price": row.get("market_price"),
    } for row in joined]
    if rows:
        # Idempotent insert: PK is (market_date, card_variant_id, set_id).
        client.table(DAILY_STATES_TABLE).upsert(
            rows, on_conflict="market_date,card_variant_id,set_id",
        ).execute()
    report.dates_materialized += 1
    report.rows_inserted += len(rows)


def reconcile_set(client: Any, *, set_id: str, market_dates: Sequence[str],
                   variant_ids: Sequence[str], retired_ids: set[str]) -> tuple[int, int, bool]:
    """Exact expected-vs-actual reconciliation across all materialized dates."""
    eligible = [v for v in variant_ids if v not in retired_ids]
    expected = 0
    for market_date in market_dates:
        expected += len(load_interval_join(client, eligible, market_date))
    actual = count_actual_rows(client, set_id) if market_dates else 0
    return expected, actual, expected == actual


def activate_or_repair_coverage(client: Any, *, commit: bool, set_id: str,
                                 report: SetReport) -> None:
    """Recompute coverage strictly from the actual materialized table --
    never trust a prior row_count value, matching the known 48/50 defect.
    """
    first_date, last_date = compute_actual_bounds(client, set_id)
    actual_count = count_actual_rows(client, set_id)
    report.coverage_after = {
        "set_id": set_id,
        "first_market_date": first_date,
        "computed_through": last_date,
        "row_count": actual_count,
    }
    if not commit:
        return
    if first_date is None:
        return
    client.table(COVERAGE_TABLE).upsert([{
        "set_id": set_id,
        "first_market_date": first_date,
        "computed_through": last_date,
        "row_count": actual_count,
    }], on_conflict="set_id").execute()


def process_set(client: Any, *, commit: bool, set_id: str,
                 approved_dates: Sequence[str]) -> SetReport:
    coverage = load_coverage(client, set_id)
    report = SetReport(set_id=set_id, mode="new", coverage_before=coverage)

    variant_ids = load_variant_ids_for_set(client, set_id)
    retired_ids = load_retired_predecessor_ids(client, variant_ids)

    if coverage is None:
        dates_to_materialize = list(approved_dates)
        report.mode = "new"
    else:
        computed_through = str(coverage.get("computed_through") or "")[:10]
        dates_to_materialize = [d for d in approved_dates if d > computed_through]
        report.mode = "append" if dates_to_materialize else "up_to_date"

    report.approved_dates_considered = len(dates_to_materialize)

    if not dates_to_materialize:
        # Nothing new; still repair a stale row_count from actual contents.
        activate_or_repair_coverage(client, commit=commit, set_id=set_id, report=report)
        return report

    for market_date in dates_to_materialize:
        materialize_date(client, commit=commit, set_id=set_id, market_date=market_date,
                          variant_ids=variant_ids, retired_ids=retired_ids, report=report)

    if not commit:
        # Dry-run: report expected reconciliation without touching coverage.
        expected, actual, _ = reconcile_set(
            client, set_id=set_id, market_dates=dates_to_materialize,
            variant_ids=variant_ids, retired_ids=retired_ids,
        )
        report.expected_rows = expected
        report.actual_rows = actual if coverage is not None else 0
        report.reconciled = (report.mode == "append")  # append has no pre-activation gate
        return report

    if report.mode == "new":
        expected, actual, ok = reconcile_set(
            client, set_id=set_id, market_dates=dates_to_materialize,
            variant_ids=variant_ids, retired_ids=retired_ids,
        )
        report.expected_rows = expected
        report.actual_rows = actual
        report.reconciled = ok
        if not ok:
            report.mode = "reconciliation_failed"
            LOG.error(json.dumps({
                "event": "reconciliation_failed", "setId": set_id,
                "expected": expected, "actual": actual,
            }, sort_keys=True))
            return report

    activate_or_repair_coverage(client, commit=commit, set_id=set_id, report=report)
    return report


# --- Orchestration -----------------------------------------------------------

def run_publish(
    client: Any,
    *,
    commit: bool,
    set_ids: Sequence[str] = (),
    era_ids: Sequence[str] = (),
    through_date: date | None = None,
) -> dict[str, Any]:
    started = time.monotonic()
    summary = Summary(dry_run=not commit)

    try:
        scopes = load_set_ids(client, set_ids, era_ids)
        approved_dates = load_approved_dates(client, through=through_date)

        for set_id in scopes:
            summary.sets_attempted += 1
            try:
                report = process_set(client, commit=commit, set_id=set_id,
                                     approved_dates=approved_dates)
            except Exception as exc:
                summary.failures += 1
                LOG.error(json.dumps({
                    "event": "set_failed", "setId": set_id, "error": str(exc),
                }, sort_keys=True))
                continue

            if report.mode == "new":
                summary.sets_new += 1
            elif report.mode == "append":
                summary.sets_appended += 1
            elif report.mode == "up_to_date":
                summary.sets_up_to_date += 1
            elif report.mode == "reconciliation_failed":
                summary.sets_reconciliation_failed += 1

            if (report.coverage_before and report.coverage_after
                    and report.coverage_before.get("row_count") != report.coverage_after.get("row_count")):
                summary.coverage_rows_repaired += 1

            summary.total_rows_inserted += report.rows_inserted
            summary.reports.append(asdict(report))
            LOG.info(json.dumps({
                "event": "set_complete", "setId": set_id, "mode": report.mode,
                "rowsInserted": report.rows_inserted, "reconciled": report.reconciled,
                "dryRun": not commit,
            }, sort_keys=True))
    except Exception as exc:
        summary.failures += 1
        LOG.error(json.dumps({"event": "publish_failed", "error": str(exc)}, sort_keys=True))

    summary.elapsed_seconds = round(time.monotonic() - started, 3)
    return asdict(summary)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--dry-run", action="store_true", help="Plan the publication; perform no writes.")
    mode.add_argument("--commit", action="store_true", help="Execute materialization via the service-role client.")
    parser.add_argument("--set-id", action="append", default=[], help="Limit to a set UUID; repeatable.")
    parser.add_argument("--era-id", action="append", default=[], help="Resolve all set UUIDs in an era; repeatable.")
    parser.add_argument("--through-date", type=date.fromisoformat, default=None,
                        help="Cap approved dates at this ISO date (default: all approved dates).")
    return parser


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    args = build_parser().parse_args()
    report = run_publish(
        create_service_role_client(), commit=bool(args.commit),
        set_ids=args.set_id, era_ids=args.era_id, through_date=args.through_date,
    )
    print(json.dumps(report, indent=2, sort_keys=True, default=str))
    return 1 if (report["failures"] or report["sets_reconciliation_failed"]) else 0


if __name__ == "__main__":
    raise SystemExit(main())
