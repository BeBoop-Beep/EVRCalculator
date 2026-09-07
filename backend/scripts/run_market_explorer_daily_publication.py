"""Coordinated daily publication for the Market Explorer card-price serving
projection: current-metadata refresh -> projection append -> exact
reconciliation -> V1 coverage advance -> bounded V2 shadow advance -> EXIT.

P0 INCIDENT NOTE (2026-09): this script used to end with an in-process
"dynamic maintained-cache prewarm" step that rebuilt every stale
``cache_kind='maintained'`` cache (21 of them, all stale on a bad day) through
the real planner/persistent-cache path, serially, inside the SAME process as
the authoritative projection. That drove the Oracle scraper VM to memory
saturation and made it unresponsive over SSH. Maintained-cache
building/warming is NOT part of normal daily publication or historical
repair any more -- it never imports the planner/cache machinery on this path.
That work now lives entirely in the separate, lean, serial,
resource-guarded, lockable operational CLI
``backend/scripts/run_market_explorer_maintained_cache_prewarm.py``, which by
default builds at most one stale cache per invocation and exits, releasing
all process memory before the next one is considered. Discovery helpers that
both scripts need (identifying which maintained caches exist / are affected
by a repair) live in the shared, planner-importing module
``backend/db/services/market_explorer_maintained_cache_ops.py`` -- this
script imports ONLY the read-only discovery half of that module for the
repair path's "which caches are affected" report, never the build half.

Why a separate orchestrator and not a stage bolted onto
``run_daily_opening_publication.py``: that script's contract (simulations ->
verified opening-analytics cohort -> RIP Stats / Rankings / Chase snapshots)
is a completely different domain -- sealed-product opening outcomes and RIP
scoring, not the card-price time series this module operationalizes. It has
no notion of ``pokemon_market_explorer_card_daily_states`` /
``pokemon_market_explorer_card_daily_coverage`` / maintained query caches at
all, and its exit-code/gate semantics (publication authority, simulation
freshness, rollover) don't map onto this workflow's inputs (approved market
dates, interval authority, projection coverage). Bolting this on would either
silently piggyback on an unrelated gate or require threading a second,
semantically distinct success/failure path through a script that already has
eight sequential gates. There is no safe existing integration point for this
domain; this module is a small script in the same family
(``backend/scripts/*_publication.py`` / ``publish_market_explorer_daily_projection.py``)
that a future cron entry can call directly, exactly the way
``run_daily_opening_publication.py`` is invoked on its own line in the
production schedule.

Contract per approved market date D (see task spec):
  1. Interval authority for D is assumed current (not touched here).
  2. D must be READY/LEGACY_VERIFIED in ``pokemon_market_date_quality``
     (checked, never manufactured) -- otherwise this is a no-op (CASE D).
  3. Refresh ``pokemon_market_explorer_card_current_metadata`` against
     current canonical authority (one row per current physical variant, no
     retired-predecessor or catalog-only leakage).
  4. Append D into ``pokemon_market_explorer_card_daily_states`` for every
     tracked set via the existing, already-tested
     ``publish_market_explorer_daily_projection.run_publish`` -- reused, not
     reimplemented.
  5. Reconciliation and coverage advancement happen INSIDE step 4's
     per-set contract (never activated on reconciliation failure) --
     preserved exactly, not re-derived here.
  6. EXIT. Maintained-cache state can never change this result -- the
     ``caches`` field of the summary is always the explicit marker
     ``{"status": "deferred", "reason": "separate_operational_worker"}``,
     never a build outcome.

Dry-run is the default-safe mode; writes require ``--commit`` and use only
the service-role client, exactly like the sibling publish/repair scripts.
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
from backend.db.services.market_explorer_maintained_cache_ops import (
    caches_overlapping_set_ids,
)
from backend.db.services.pokemon_market_explorer_query_service import (
    resolve_tracked_set_ids,
)
from backend.scripts.publish_market_explorer_daily_projection import (
    APPROVED_STATUSES,
    AUTHORITY_RPC,
    DATE_QUALITY_TABLE,
    MERGE_LEDGER_TABLE,
    _paged,
    run_publish,
)

LOG = logging.getLogger("market_explorer_daily_publication")

CURRENT_METADATA_TABLE = "pokemon_market_explorer_card_current_metadata"
CURRENT_METADATA_REFRESH_RPC = "refresh_pokemon_market_explorer_card_current_metadata"
COVERAGE_TABLE = "pokemon_market_explorer_card_daily_coverage"
CARDS_ASSET_TABLE = "pokemon_market_explorer_cache_state"
INVALIDATE_CACHE_SCOPED_RPC = "invalidate_pokemon_market_explorer_query_cache_scoped"
REPROJECT_DAILY_STATES_RPC = "reproject_pokemon_market_explorer_card_daily_states"
ADVANCE_V2_DAILY_RPC = "advance_pokemon_market_explorer_daily_v2_shadow_for_set"
V2_RETENTION_DAYS = 100


# --- Market date resolution --------------------------------------------------

def resolve_latest_approved_market_date(client: Any) -> str | None:
    """Latest READY/LEGACY_VERIFIED ``pokemon_market_date_quality`` date.

    Never wall-clock. If nothing is approved, returns ``None`` -- callers
    must fail closed (CASE D), not synthesize a date.
    """
    rows = _paged(lambda: client.table(DATE_QUALITY_TABLE).select("market_date")
                  .eq("tcg", "pokemon").in_("status", list(APPROVED_STATUSES))
                  .order("market_date"))
    dates = sorted({str(row["market_date"])[:10] for row in rows})
    return dates[-1] if dates else None


def market_date_is_approved(client: Any, market_date: str) -> bool:
    rows = list((client.table(DATE_QUALITY_TABLE).select("status")
                 .eq("tcg", "pokemon").eq("market_date", market_date)
                 .limit(1).execute()).data or [])
    if not rows:
        return False
    return str(rows[0].get("status")) in APPROVED_STATUSES


# --- Current-metadata projection refresh -------------------------------------

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
    return {str(row["predecessor_variant_id"]) for row in rows}


def load_current_authority_rows(client: Any, set_ids: Sequence[str]) -> list[dict[str, Any]]:
    """One row per current physical variant across ``set_ids``, excluding any
    active vintage-predecessor retirement. Never reads catalog-only sets --
    the caller passes only ``resolve_tracked_set_ids`` output.
    """
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
        out.append({
            "card_variant_id": variant_id,
            "set_id": str(row.get("set_id") or ""),
        })
    return out


def refresh_current_metadata(client: Any, *, commit: bool) -> MetadataRefreshReport:
    """Reconcile ``pokemon_market_explorer_card_current_metadata`` to the
    exact current canonical authority -- no retired-predecessor leakage, no
    catalog-only leakage.

    Delegates the actual write to the real production RPC
    ``refresh_pokemon_market_explorer_card_current_metadata(p_set_ids uuid[])``
    (the same RPC that originally populated this table -- see migration
    ``20260903192911_add_market_explorer_current_metadata_projection``)
    rather than hand-rolling a raw table upsert. A hand-rolled upsert here
    previously supplied only ``card_variant_id``/``set_id`` for each row,
    which is correct for updating an existing row but violates the table's
    NOT NULL constraints (e.g. ``canonical_card_id``) the first time a
    genuinely new variant needs a row -- the RPC knows the full column
    contract and derives it server-side; this function must not attempt to
    reconstruct that contract in Python.
    """
    tracked_set_ids = resolve_tracked_set_ids(client)
    report = MetadataRefreshReport(sets_considered=len(tracked_set_ids))

    expected_rows = load_current_authority_rows(client, tracked_set_ids)
    report.expected_row_count = len(expected_rows)

    if not commit:
        return report

    rows_before = _paged(lambda: client.table(CURRENT_METADATA_TABLE).select("card_variant_id"))
    ids_before = {str(row["card_variant_id"]) for row in rows_before}

    client.rpc(CURRENT_METADATA_REFRESH_RPC, {"p_set_ids": list(tracked_set_ids)}).execute()

    rows_after = _paged(lambda: client.table(CURRENT_METADATA_TABLE).select("card_variant_id"))
    ids_after = {str(row["card_variant_id"]) for row in rows_after}
    report.rows_upserted = len(ids_after)
    report.rows_removed = len(ids_before - ids_after)  # informational only; RPC owns removal
    return report


# --- Maintained-cache deferral (read-only; never builds) ---------------------

def deferred_cache_report(client: Any | None = None, *,
                           only_set_ids: Sequence[str] = ()) -> dict[str, Any]:
    """The explicit marker that replaces the old in-process cache-prewarm
    result. Maintained-cache building is NEVER part of this script's call
    path any more -- see the module docstring's P0 incident note. When
    ``only_set_ids`` is given (the historical-repair path) this does a
    read-only discovery pass (via
    ``market_explorer_maintained_cache_ops.caches_overlapping_set_ids``) so
    the report names which maintained caches are affected and therefore
    deferred to the separate operational worker; it never builds anything.
    """
    report: dict[str, Any] = {"status": "deferred", "reason": "separate_operational_worker"}
    if only_set_ids and client is not None:
        affected = caches_overlapping_set_ids(client, only_set_ids)
        report["affected"] = sorted(str(row.get("query_fingerprint") or "") for row in affected)
    return report


# --- Normal-day orchestration -------------------------------------------------

@dataclass
class DailyPublicationSummary:
    dry_run: bool
    market_date: str | None = None
    status: str = "not_started"  # ready | not_ready | projection_failed | ok
    metadata_refresh: dict[str, Any] | None = None
    projection: dict[str, Any] | None = None
    v2_projection: dict[str, Any] | None = None
    caches: dict[str, Any] | None = None
    elapsed_seconds: float = 0.0
    error: str | None = None


def advance_v2_daily_shadow(
    client: Any, *, commit: bool, set_ids: Sequence[str], through_date: str,
    retention_days: int = V2_RETENTION_DAYS,
) -> dict[str, Any]:
    """Advance the bounded V2 serving shadow for the canonical V1 resolver set."""
    report: dict[str, Any] = {
        "through_date": through_date,
        "retention_days": retention_days,
        "sets_considered": len(set_ids),
        "sets_advanced": 0,
        "failures": [],
    }
    if not commit:
        return report
    for set_id in set_ids:
        try:
            client.rpc(ADVANCE_V2_DAILY_RPC, {
                "p_set_id": str(set_id),
                "p_through_date": through_date,
                "p_retention_days": retention_days,
            }).execute()
            report["sets_advanced"] += 1
        except Exception as exc:
            report["failures"].append({
                "set_id": str(set_id), "error": f"{type(exc).__name__}: {exc}",
            })
    return report


def run_daily_publication(
    client: Any, *, commit: bool, market_date: str | None = None,
) -> dict[str, Any]:
    started = time.monotonic()
    summary = DailyPublicationSummary(dry_run=not commit)

    resolved = market_date or resolve_latest_approved_market_date(client)
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
        client, commit=commit, set_ids=tracked_set_ids, through_date=date.fromisoformat(resolved),
    )
    summary.projection = projection_report

    if projection_report.get("failures") or projection_report.get("sets_reconciliation_failed"):
        # Coverage was NOT activated for any failed set inside run_publish;
        # a failed set stays at its previous computed_through. `caches`
        # stays None here (never even the deferred marker) -- a failed
        # projection publishes nothing for the cache worker to act on yet.
        summary.status = "projection_failed"
        summary.error = "one or more sets failed projection reconciliation; coverage held at prior date"
        summary.elapsed_seconds = round(time.monotonic() - started, 3)
        return asdict(summary)

    summary.v2_projection = advance_v2_daily_shadow(
        client, commit=commit, set_ids=tracked_set_ids, through_date=resolved,
    )
    if summary.v2_projection["failures"]:
        summary.status = "projection_failed"
        summary.error = "one or more sets failed bounded V2 daily advancement"
        summary.elapsed_seconds = round(time.monotonic() - started, 3)
        return asdict(summary)

    # Maintained-cache state can never change this result: no build, no
    # warm, no advance, no import of the planner/cache machinery happens on
    # this path. See the module docstring's P0 incident note.
    summary.caches = deferred_cache_report()
    summary.status = "ok"
    summary.elapsed_seconds = round(time.monotonic() - started, 3)
    return asdict(summary)


# --- Historical repair orchestration -----------------------------------------

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
    client: Any, *, commit: bool, set_ids: Sequence[str], repair_start: date,
    repair_through: date | None = None,
) -> dict[str, Any]:
    """Rebuild affected daily projection from ``repair_start`` (the earliest
    affected approved date) through the canonical current date, exactly
    reconcile, restore coverage from actual rows, bump ``repair_generation``,
    and invalidate (never rebuild inline) the maintained caches whose scope
    overlaps the affected sets -- those rebuilds are reported as deferred to
    the separate operational worker. Interval repair itself is assumed
    already done upstream -- this function only re-derives the projection
    from it. Repair remains valid even with stale caches: a stale maintained
    cache is a correctness gap for that cache's own next read, never a
    reason to fail or block this repair.
    """
    started = time.monotonic()
    set_ids = sorted({str(v) for v in set_ids})
    through = (repair_through or date.today()).isoformat()
    summary = HistoricalRepairSummary(
        dry_run=not commit, repair_start=repair_start.isoformat(),
        repair_through=through, set_ids=set_ids,
    )

    if not set_ids:
        summary.status = "no_sets"
        summary.elapsed_seconds = round(time.monotonic() - started, 3)
        return asdict(summary)

    if commit:
        response = client.rpc(REPROJECT_DAILY_STATES_RPC, {
            "p_set_ids": set_ids, "p_start_date": repair_start.isoformat(), "p_end_date": through,
        }).execute()
        summary.reprojected_rows = int(response.data or 0)

    # Exact reconcile against interval authority, one set at a time, reusing
    # the same point-in-time join/expected-count contract as the daily
    # publish path.
    from backend.scripts.publish_market_explorer_daily_projection import (
        count_actual_rows,
        load_approved_dates,
        load_interval_join,
        load_retired_predecessor_ids,
        load_variant_ids_for_set,
        purge_ineligible_daily_state_rows,
    )

    approved_dates = load_approved_dates(client, after=None, through=date.fromisoformat(through))
    approved_dates = [d for d in approved_dates if d >= repair_start.isoformat()]

    expected_total = 0
    actual_total = 0
    purged_total = 0
    for set_id in set_ids:
        variant_ids = load_variant_ids_for_set(client, set_id)
        retired = load_retired_predecessor_ids(client, variant_ids)
        eligible = [v for v in variant_ids if v not in retired]
        # Purge BEFORE counting actual -- the reprojection RPC above is an
        # opaque DB-side path this module does not control; it may re-derive
        # rows for an ineligible instrument (e.g. a duplicate_alias) from raw
        # intervals alone. Purging here, using the same authority-eligible
        # set that produces `expected`, guarantees both sides of this
        # reconciliation compare the identical instrument universe.
        purged_total += purge_ineligible_daily_state_rows(
            client, commit=commit, set_id=set_id, eligible_variant_ids=eligible,
        )
        expected = sum(len(load_interval_join(client, eligible, d)) for d in approved_dates)
        actual = count_actual_rows(client, set_id) if commit else expected
        expected_total += expected
        actual_total += actual
    summary.stray_rows_purged = purged_total
    summary.expected_rows = expected_total
    summary.actual_rows = actual_total
    summary.reconciled = expected_total == actual_total

    if not summary.reconciled:
        summary.status = "reconciliation_failed"
        summary.elapsed_seconds = round(time.monotonic() - started, 3)
        return asdict(summary)

    # Coverage restored from ACTUAL projection state, never incremented.
    from backend.scripts.publish_market_explorer_daily_projection import (
        activate_or_repair_coverage,
        SetReport,
    )
    for set_id in set_ids:
        report = SetReport(set_id=set_id, mode="repair")
        activate_or_repair_coverage(client, commit=commit, set_id=set_id, report=report)
        summary.coverage_repaired.append(report.coverage_after or {})

    if commit:
        response = client.rpc(INVALIDATE_CACHE_SCOPED_RPC, {"p_set_ids": set_ids}).execute()
        summary.cache_entries_invalidated = int(response.data or 0)
    summary.repair_generation_bumped = True  # atomic on the DB side inside the RPC above

    # Invalidation already happened above via INVALIDATE_CACHE_SCOPED_RPC.
    # Rebuilding those now-invalidated maintained caches is NEVER done
    # inline here -- report which ones are affected and defer them to the
    # separate operational worker. `client` is passed only for a read-only
    # discovery query, never a build.
    summary.caches = deferred_cache_report(client, only_set_ids=set_ids)
    summary.status = "ok"
    summary.elapsed_seconds = round(time.monotonic() - started, 3)
    return asdict(summary)


# --- CLI ---------------------------------------------------------------------

def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--dry-run", action="store_true", help="Plan the run; perform no writes.")
    mode.add_argument("--commit", action="store_true", help="Execute via the service-role client.")
    parser.add_argument("--market-date", type=date.fromisoformat, default=None,
                        help="Override the target market date (default: latest approved).")
    sub = parser.add_argument_group("historical repair (mutually exclusive with normal daily mode)")
    sub.add_argument("--repair", action="store_true", help="Run the historical-repair path instead.")
    sub.add_argument("--repair-set-id", action="append", default=[], help="Repeatable.")
    sub.add_argument("--repair-start", type=date.fromisoformat, default=None)
    sub.add_argument("--repair-through", type=date.fromisoformat, default=None)
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
            client, commit=commit, set_ids=args.repair_set_id,
            repair_start=args.repair_start, repair_through=args.repair_through,
        )
        print(json.dumps(report, indent=2, sort_keys=True, default=str))
        return 1 if report["status"] not in {"ok"} else 0

    report = run_daily_publication(
        client, commit=commit,
        market_date=args.market_date.isoformat() if args.market_date else None,
    )
    print(json.dumps(report, indent=2, sort_keys=True, default=str))
    return 1 if report["status"] not in {"ok"} else 0


if __name__ == "__main__":
    raise SystemExit(main())
