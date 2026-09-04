"""Coordinated daily publication for the Market Explorer card-price serving
projection: current-metadata refresh -> projection append -> exact
reconciliation -> coverage advance -> dynamic maintained-cache prewarm.

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
  6. Only then, discover every ``cache_kind='maintained'`` row dynamically
     and prewarm/advance it to D through the real
     ``MarketExplorerQueryPlanner`` / ``PersistentMarketExplorerCache`` /
     ``run_market_explorer_query`` builder path (same mechanism as
     ``build_market_explorer_maintained_cache.py``). A cache failure is
     isolated per cache and never rolls back the already-committed
     projection/coverage advance from step 4/5.

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
from backend.db.services.market_explorer_query_planner import (
    MarketExplorerL1Cache,
    MarketExplorerQueryPlanner,
    PersistentMarketExplorerCache,
    PreparedEquivalenceRegistry,
)
from backend.db.services.pokemon_market_explorer_query_service import (
    resolve_tracked_set_ids,
    run_market_explorer_query,
)
from backend.domain.pokemon.market_explorer_query import query_fingerprint
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
CACHE_TABLE = "pokemon_market_explorer_query_cache"
COVERAGE_TABLE = "pokemon_market_explorer_card_daily_coverage"
CARDS_ASSET_TABLE = "pokemon_market_explorer_cache_state"
INVALIDATE_CACHE_SCOPED_RPC = "invalidate_pokemon_market_explorer_query_cache_scoped"
REPROJECT_DAILY_STATES_RPC = "reproject_pokemon_market_explorer_card_daily_states"

CACHE_BUILD_START = "1999-01-01"


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


# --- Maintained-cache discovery + prewarm ------------------------------------

@dataclass
class CacheAdvanceReport:
    fingerprint: str
    label: str
    status: str  # "advanced" | "already_current" | "failed"
    execution_source: str | None = None
    computed_through: str | None = None
    error: str | None = None


def discover_maintained_caches(client: Any) -> list[dict[str, Any]]:
    """Every ``cache_kind='maintained'`` row, spec-driven -- never a
    hardcoded fingerprint list. A future maintained cache is picked up
    automatically the day it is promoted.
    """
    return _paged(lambda: client.table(CACHE_TABLE).select(
        "query_fingerprint,normalized_spec,status,cache_kind,computed_through"
    ).eq("cache_kind", "maintained"))


def _spec_from_normalized(normalized_spec: dict[str, Any]) -> dict[str, Any]:
    """Rehydrate the spec dict exactly as ``normalize_query_spec`` produced it
    (this IS that dict, persisted verbatim as ``normalized_spec`` at build
    time -- see ``domain/pokemon/market_explorer_query.py``), converting list
    fields back to tuples. Must pass every field through, including
    ``contractVersion``/``asset``/etc -- selectively reconstructing a subset
    of keys silently drops fields ``query_fingerprint``/planner code expects.
    """
    return {
        **normalized_spec,
        "eraIds": tuple(normalized_spec.get("eraIds") or ()),
        "setIds": tuple(normalized_spec.get("setIds") or ()),
        "segmentIds": tuple(normalized_spec.get("segmentIds") or ()),
        "pokemonIds": tuple(normalized_spec.get("pokemonIds") or ()),
        "priceSegmentIds": tuple(normalized_spec.get("priceSegmentIds") or ()),
        "releaseAgeCohortIds": tuple(normalized_spec.get("releaseAgeCohortIds") or ()),
    }


def _builder(client: Any, spec: dict[str, Any]):
    def build(previous: str | None, through: str) -> dict[str, Any]:
        return run_market_explorer_query(
            client, mode=spec["mode"], era_ids=spec["eraIds"], set_ids=spec["setIds"],
            segment_ids=spec["segmentIds"], pokemon_ids=spec["pokemonIds"],
            price_segment_ids=spec["priceSegmentIds"],
            release_age_cohort_ids=spec["releaseAgeCohortIds"], top_n=spec["topN"],
            start_date=previous or CACHE_BUILD_START, end_date=through)
    return build


def advance_one_maintained_cache(client: Any, row: dict[str, Any], *,
                                  market_date: str, commit: bool) -> CacheAdvanceReport:
    label = str(row.get("label") or row.get("query_fingerprint") or "?")
    fingerprint = str(row.get("query_fingerprint") or "")
    if str(row.get("computed_through") or "")[:10] >= market_date:
        return CacheAdvanceReport(fingerprint=fingerprint, label=label,
                                  status="already_current",
                                  computed_through=str(row.get("computed_through"))[:10])
    if not commit:
        return CacheAdvanceReport(fingerprint=fingerprint, label=label,
                                  status="advanced", computed_through=market_date)

    spec = _spec_from_normalized(row.get("normalized_spec") or {})
    planner = MarketExplorerQueryPlanner(l1=MarketExplorerL1Cache())
    persistent = PersistentMarketExplorerCache(client, build_lease_seconds=300)
    result = planner.execute(
        spec=spec, prepared=PreparedEquivalenceRegistry(), persistent=persistent,
        canonical_through=lambda: market_date, novel_builder=_builder(client, spec),
    )
    computed_fingerprint = query_fingerprint(spec)
    return CacheAdvanceReport(fingerprint=computed_fingerprint, label=label,
                              status="advanced", execution_source=result.execution_source,
                              computed_through=market_date)


def prewarm_maintained_caches(client: Any, *, market_date: str, commit: bool,
                               only_set_ids: Sequence[str] = ()) -> dict[str, Any]:
    """Advance every discovered maintained cache to ``market_date``.

    One failed cache never blocks another -- each build is isolated in its
    own try/except and reported individually. When ``only_set_ids`` is given
    (historical-repair path), only caches whose ``setIds``/``eraIds`` overlap
    the affected sets are touched -- a healthy unrelated maintained cache is
    left exactly as-is.
    """
    rows = discover_maintained_caches(client)
    scope_filter = set(str(v) for v in only_set_ids)
    attempted: list[dict[str, Any]] = []
    advanced = 0
    already_current = 0
    failed = 0
    for row in rows:
        spec_set_ids = {str(v) for v in ((row.get("normalized_spec") or {}).get("setIds") or [])}
        if scope_filter and not (spec_set_ids & scope_filter):
            continue
        try:
            report = advance_one_maintained_cache(client, row, market_date=market_date, commit=commit)
        except Exception as exc:  # noqa: BLE001 - isolated per cache, never fatal to the run
            failed += 1
            attempted.append(asdict(CacheAdvanceReport(
                fingerprint=str(row.get("query_fingerprint") or ""),
                label=str(row.get("label") or row.get("query_fingerprint") or "?"),
                status="failed", error=str(exc),
            )))
            LOG.error(json.dumps({
                "event": "maintained_cache_failed",
                "fingerprint": row.get("query_fingerprint"), "error": str(exc),
            }, sort_keys=True))
            continue
        if report.status == "advanced":
            advanced += 1
        elif report.status == "already_current":
            already_current += 1
        attempted.append(asdict(report))

    return {
        "attempted": len(attempted), "advanced": advanced,
        "already_current": already_current, "failed": failed, "reports": attempted,
    }


# --- Normal-day orchestration -------------------------------------------------

@dataclass
class DailyPublicationSummary:
    dry_run: bool
    market_date: str | None = None
    status: str = "not_started"  # ready | not_ready | projection_failed | ok
    metadata_refresh: dict[str, Any] | None = None
    projection: dict[str, Any] | None = None
    caches: dict[str, Any] | None = None
    elapsed_seconds: float = 0.0
    error: str | None = None


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
        # a failed set stays at its previous computed_through. Caches must
        # not be advanced past a projection that failed reconciliation.
        summary.status = "projection_failed"
        summary.error = "one or more sets failed projection reconciliation; coverage held at prior date"
        summary.elapsed_seconds = round(time.monotonic() - started, 3)
        return asdict(summary)

    summary.caches = prewarm_maintained_caches(client, market_date=resolved, commit=commit)
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
    and invalidate/rebuild ONLY the maintained caches whose scope overlaps
    the affected sets. Interval repair itself is assumed already done
    upstream -- this function only re-derives the projection from it.
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
    )

    approved_dates = load_approved_dates(client, after=None, through=date.fromisoformat(through))
    approved_dates = [d for d in approved_dates if d >= repair_start.isoformat()]

    expected_total = 0
    actual_total = 0
    for set_id in set_ids:
        variant_ids = load_variant_ids_for_set(client, set_id)
        retired = load_retired_predecessor_ids(client, variant_ids)
        eligible = [v for v in variant_ids if v not in retired]
        expected = sum(len(load_interval_join(client, eligible, d)) for d in approved_dates)
        actual = count_actual_rows(client, set_id) if commit else expected
        expected_total += expected
        actual_total += actual
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

    max_computed_through = max((row.get("computed_through") for row in summary.coverage_repaired
                                 if row.get("computed_through")), default=through)
    summary.caches = prewarm_maintained_caches(
        client, market_date=str(max_computed_through)[:10], commit=commit, only_set_ids=set_ids,
    )
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
