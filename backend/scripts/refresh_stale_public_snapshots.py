from __future__ import annotations

import argparse
import logging
import re
import sys
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence, Tuple
from uuid import UUID

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from backend.db.services.publication_gate import (
    GATE_DEFERRED_EXIT_CODE,
    evaluate_publication_gate,
    gate_decision_report,
)
from backend.db.services.set_publication_revalidation import (
    log_revalidation_diagnostics,
    notify_set_publication,
)
from backend.db.services.rip_decision_freshness import evaluate_rip_decision_staleness
from backend.scripts.snapshot_query_retry import run_snapshot_operation_with_retry
from backend.desirability.set_validation import FORMULA_VERSION, build_desirability_validation_payload, build_opening_set_audit
from backend.scripts.build_pokemon_desirability_validation_snapshots import (
    _audit_row,
    _build_global_validation_snapshot_payload,
    _read_cards_snapshot,
    _read_page_snapshots,
    _target_rows,
    _upsert_global_validation_snapshot,
)
from backend.scripts.pokemon_snapshot_builders import (
    DEFAULT_DASHBOARD_DAYS,
    DEFAULT_DASHBOARD_WINDOW,
    build_coordinated_set_market_snapshot_rows,
    build_set_page_snapshot_row,
    get_client,
    list_pokemon_sets,
    refresh_canonical_card_market_prices_for_set,
    resolve_set_row,
    upsert_row,
    upsert_rows,
)
from backend.scripts.pokemon_explore_rankings_publisher import publish_explore_rip_rankings_snapshot
from backend.scripts.build_pokemon_explore_card_movers_snapshot import build as build_explore_card_movers
from backend.scripts.build_pokemon_explore_set_value_snapshot import build as build_explore_set_values

logger = logging.getLogger(__name__)

KNOWN_SET_PAGE_STALE_WARNING_PATTERNS = (
    "explore_rip_statistics_latest unavailable",
    "failed to derive eligible card counts",
    "failed to load top hits",
    "desirability validation could not be generated",
    "simulation drivers are unavailable",
    "simulation drivers unavailable",
    "simulation_input_cards is failed",
    "skipped live repair during route render",
)
RANKINGS_STALE_THRESHOLD_SECONDS = 300
# Set-page strict verification is simulation-aware. A partial page that is
# explicitly labeled simulation-unavailable must PASS strict mode; a page that
# claims every section is current must still fail on the usual staleness checks.
# unavailableSections must at least name these flagship simulation-derived areas.
_REQUIRED_UNAVAILABLE_SECTIONS = frozenset({"summary", "top_hits", "openingProfitVsCost"})


@dataclass(frozen=True)
class SimulationDerivedSection:
    """One simulation-derived surface of a published set page.

    ``freshness_keys``  — every ``meta.sectionFreshness`` alias the section may
                          be labeled under.
    ``payload_paths``   — every payload location the section's data may occupy.
    ``declaration_keys``— every alias that counts as declaring the section in
                          ``simulationAvailability.unavailableSections``.

    Both camelCase and snake_case aliases are listed on purpose: the set-page
    builder writes snake_case payload sections while the slim normalizers
    (pokemon_public_snapshot_service) re-emit the same content camelCased. The
    verifier must recognise either without a second schema.
    """

    key: str
    freshness_keys: Tuple[str, ...]
    payload_paths: Tuple[Tuple[str, ...], ...]
    declaration_keys: Tuple[str, ...]


# The COMPLETE simulation-derived surface. Verification walks these directly
# rather than trusting the payload's own carriedForwardSections list, so a page
# cannot hide a section simply by omitting it from that list.
SIMULATION_DERIVED_SECTIONS: Tuple[SimulationDerivedSection, ...] = (
    SimulationDerivedSection(
        key="simulationSummary",
        freshness_keys=("simulationSummary", "simulation_summary", "summary"),
        payload_paths=(("summary",),),
        declaration_keys=("summary", "simulationSummary", "simulation_summary"),
    ),
    SimulationDerivedSection(
        key="simulationDrivers",
        freshness_keys=("simulationDrivers", "simulation_drivers", "topHits", "top_hits"),
        payload_paths=(("top_hits",), ("topHits",), ("simulationDrivers",)),
        declaration_keys=("top_hits", "topHits", "simulationDrivers", "simulation_drivers"),
    ),
    SimulationDerivedSection(
        key="openingProfitVsCost",
        freshness_keys=("openingProfitVsCost", "opening_profit_vs_cost"),
        payload_paths=(("openingProfitVsCost",), ("opening_profit_vs_cost",)),
        declaration_keys=("openingProfitVsCost", "opening_profit_vs_cost"),
    ),
    SimulationDerivedSection(
        key="outcomeDistribution",
        freshness_keys=("outcomeDistribution", "outcome_distribution"),
        payload_paths=(
            ("outcomeDistribution",),
            ("distribution_bins",),
            ("threshold_bins",),
            ("percentiles",),
        ),
        declaration_keys=(
            "outcomeDistribution",
            "outcome_distribution",
            "distribution_bins",
            "threshold_bins",
            "percentiles",
        ),
    ),
    SimulationDerivedSection(
        key="simulationMetrics",
        freshness_keys=("simulationMetrics", "simulation_metrics", "ripStatistics", "rip_statistics"),
        payload_paths=(("rip_statistics",), ("ripStatistics",)),
        declaration_keys=("rip_statistics", "ripStatistics", "simulationMetrics", "simulation_metrics"),
    ),
    SimulationDerivedSection(
        key="valueStructure",
        freshness_keys=("valueStructure", "value_structure", "rarityContribution", "rarity_contribution"),
        payload_paths=(("rankings",), ("rarityContribution",), ("rarity_contribution",)),
        declaration_keys=("rankings", "rarityContribution", "rarity_contribution", "valueStructure"),
    ),
    SimulationDerivedSection(
        key="packPaths",
        freshness_keys=("packPaths", "pack_paths", "packBreakdown", "pack_breakdown"),
        payload_paths=(
            ("rip_statistics", "pack_paths"),
            ("ripStatistics", "packPaths"),
            ("packPaths",),
        ),
        # Pack paths live INSIDE rip_statistics, so declaring that parent
        # section is what the builder does and what the contract accepts.
        declaration_keys=("rip_statistics", "ripStatistics", "packPaths", "pack_paths"),
    ),
    SimulationDerivedSection(
        key="historyTrend",
        freshness_keys=("historyTrend", "history_trend"),
        payload_paths=(("history_trend",), ("historyTrend",)),
        declaration_keys=("history_trend", "historyTrend"),
    ),
    SimulationDerivedSection(
        key="pullRateAssumptions",
        freshness_keys=("pullRateAssumptions", "pull_rate_assumptions"),
        payload_paths=(("pull_rate_assumptions",), ("pullRateAssumptions",)),
        declaration_keys=("pull_rate_assumptions", "pullRateAssumptions"),
    ),
)
# Flat sectionFreshness key list kept for the "must never be labeled current"
# sweep.
_SIMULATION_SECTION_FRESHNESS_KEYS = tuple(
    key for section in SIMULATION_DERIVED_SECTIONS for key in section.freshness_keys
)
# simulation_input_cards source values that legitimately mean "no simulation row".
_SIMULATION_UNAVAILABLE_SOURCE_VALUES = frozenset(
    {"NO_ROW", "NO_ROWS", "MISSING", "UNAVAILABLE", "UNAVAILABLE_FALLBACK"}
)
# Bounded per-set rebuild retries. Only transient data-service errors are
# retried (classified inside run_snapshot_operation_with_retry) with exponential
# backoff, so a momentary Supabase timeout does not fail an otherwise-recoverable
# set — while a genuine error still fails fast after the bound. Kept small to
# avoid amplifying disk I/O during recovery. Sequential by design (no parallel
# DB-heavy snapshot generation).
_REBUILD_MAX_ATTEMPTS = 3

# --- planning observability -------------------------------------------------
# The full-catalog planner issues hundreds of reads before it writes anything.
# Without progress output a healthy-but-slow plan and a blocked network request
# look identical (exactly the state that made a daily run appear hung).
#
# CADENCE, and why it is 3 and not 10.
# Planning measures at roughly 4 seconds per set over the 209-set catalog. At an
# interval of 10 that is ~40 seconds of INFO silence between heartbeats, so the
# previous operational statement — "silence beyond ~10s means a blocked request"
# — was simply wrong, and a healthy run looked hung. At an interval of 3 the
# expected heartbeat is ~12 seconds under that same measured baseline.
#
# NO STRICT MAXIMUM IS CLAIMED. Network latency varies, and a single PostgREST
# call may legitimately stay silent until the service-role client's finite
# timeout (SUPABASE_SERVICE_ROLE_POSTGREST_TIMEOUT_SECONDS, default 60s — see
# backend.db.clients.supabase_client). THAT timeout, not this interval, is the
# real upper bound on one blocked request.
PLANNING_PROGRESS_INTERVAL = 3    # INFO heartbeat every N sets (~10-20s observed)
SLOW_PLANNING_SET_SECONDS = 10.0  # always log a set slower than this
SLOW_QUERY_SECONDS = 5.0          # always log a single SELECT slower than this

# Server-side JSON path projection: PostgREST evaluates the path and returns ONE
# scalar, so the cards snapshot's (large) payload_json never crosses the wire.
CARDS_GENERATION_ID_PROJECTION = "generation_id:payload_json->meta->snapshot->>generationId"

# HEAVY READS IN THE READ-ONLY PLANNING PHASE — why each large JSON column is
# fetched, audited because the planner scans the whole published catalog and one
# needless blob per set is hundreds of megabytes across a run.
#
#   pokemon_set_cards_snapshot_latest.cards_json + .payload_json
#       (_cards_snapshot_staleness) REQUIRED. Priced-card coverage and 7D
#       movement-contract coverage are per-card counts; no aggregate column
#       carries them. Fetched ONCE per set, in one request.
#   pokemon_set_cards_snapshot_latest.payload_json
#       (_market_snapshot_staleness) REMOVED. It fetched the whole document a
#       SECOND time per set to compare one generation-ID string; that string is
#       now projected server-side (CARDS_GENERATION_ID_PROJECTION above). This
#       was the read the interrupt stack landed in.
#   pokemon_set_market_dashboard_snapshot_latest.payload_json,
#   .set_value_histories_json, .top_chase_card_histories_json,
#   .performance_vs_cost_history_json
#       (_market_snapshot_staleness) REQUIRED, and all four arrive in ONE
#       request for the row. Each history's END DATE is the invariant under
#       test, and the snapshot stores no end-date columns: meta's
#       setValueHistoryLatestDateByScope is only present on newer rows, so the
#       raw histories remain the fallback, and OPvC additionally needs the
#       per-point isCarriedForward flag to find the last REAL simulation date.
#   pokemon_set_page_snapshot_latest.payload_json
#       (_set_page_snapshot_staleness) REQUIRED for the completeness marker and
#       the rank-field check. One request per set. (_verify_set_page reads it
#       again — deliberately, AFTER the rebuild phase, where the point is to see
#       the newly written row.)
#   pokemon_explore_rankings_snapshot_latest.ranking_payload_json /
#   pokemon_desirability_validation_snapshot_latest.payload_json
#       (_global_snapshot_staleness) REQUIRED for cohort/target/publication
#       markers. TWO reads per run in total, not per set.
#   every _latest_for_* helper selects a single timestamp column, ordered and
#       limited to one row. Nothing to trim.
#
# Duplicate REQUESTS (not columns) removed: _latest_run_id_for_set was issued
# twice per set during planning — see _PLANNING_RUN_ID_CACHE below.


def _rebuild_with_bounded_retry(operation, *, operation_name: str, set_id: str, client: Any):
    """Run a rebuild with bounded, transient-only retries against one client.

    The shared client is reused (no parallelism, no client churn) so recovery
    stays I/O-safe. Non-transient errors raise immediately for the caller's
    per-set failure handling.
    """
    return run_snapshot_operation_with_retry(
        operation,
        operation_name=operation_name,
        set_id=set_id,
        max_attempts=_REBUILD_MAX_ATTEMPTS,
        client_factory=lambda: client,
    )


@dataclass
class FreshnessResult:
    family: str
    stale: bool
    reason: str
    snapshot_updated_at: Optional[str] = None
    max_dependency_updated_at: Optional[str] = None
    dependency_checks: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)


@dataclass
class SetRefreshPlan:
    set_row: Dict[str, Any]
    cards: FreshnessResult
    market_dashboard: FreshnessResult
    set_page: FreshnessResult


@dataclass
class SetPageFreshnessAudit:
    """Post-run guard: set-page snapshots vs their simulation/market sources."""

    total: int = 0
    fresh: int = 0
    stale_details: List[str] = field(default_factory=list)
    max_staleness_seconds: float = 0.0
    max_staleness_set: Optional[str] = None

    @property
    def stale(self) -> int:
        return len(self.stale_details)


@dataclass
class RefreshSummary:
    source_checks_performed: int = 0
    stale_snapshot_families: set[str] = field(default_factory=set)
    rebuilt_sets: Dict[str, List[str]] = field(default_factory=lambda: {"sealed_market": [], "cards": [], "market_dashboard": [], "set_page": []})
    skipped_sets: Dict[str, List[str]] = field(default_factory=lambda: {"sealed_market": [], "cards": [], "market_dashboard": [], "set_page": []})
    failed_sets: Dict[str, List[str]] = field(default_factory=lambda: {"sealed_market": [], "cards": [], "market_dashboard": [], "set_page": []})
    warnings_remaining: List[str] = field(default_factory=list)
    problem_canonical_keys: List[str] = field(default_factory=list)
    global_rebuilt: List[str] = field(default_factory=list)
    global_skipped: List[str] = field(default_factory=list)
    global_failed: List[str] = field(default_factory=list)
    set_page_audit: Optional[SetPageFreshnessAudit] = None


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Refresh stale public snapshots from source freshness")
    mode_group = parser.add_mutually_exclusive_group()
    mode_group.add_argument("--dry-run", action="store_true", help="Report stale snapshots without writing")
    mode_group.add_argument("--commit", action="store_true", help="Rebuild stale snapshots")
    parser.add_argument("--strict", action="store_true", help="Exit non-zero if stale/problem snapshots remain")
    parser.add_argument("--set-id", help="Optional Pokemon set id, canonical key, or Pokemon API set id")
    parser.add_argument("--tcg", default="pokemon", help="TCG to refresh; only pokemon is supported for now")
    parser.add_argument("--days", type=int, default=DEFAULT_DASHBOARD_DAYS, help="Market dashboard history days")
    parser.add_argument("--window", default=DEFAULT_DASHBOARD_WINDOW, help="Market dashboard window key")
    parser.add_argument(
        "--market-date",
        help="America/Phoenix market date whose scrape batch gates promotion (default: newest batch)",
    )
    parser.add_argument(
        "--force-publish",
        action="store_true",
        help="Manual-recovery override: promote even when the scrape batch cohort is incomplete (loudly logged)",
    )
    parser.add_argument(
        "--gate-wait-attempts",
        type=int,
        default=0,
        help=(
            "Bounded automatic retry: re-evaluate a CLOSED publication gate this many extra times "
            "before deferring, so a cohort that completes shortly after this run starts still "
            "publishes in the same daily window (0 = defer immediately)"
        ),
    )
    parser.add_argument(
        "--gate-wait-seconds",
        type=float,
        default=600.0,
        help="Delay between bounded gate re-evaluations (default 600s)",
    )
    return parser


def _await_open_publication_gate(
    client: Any,
    *,
    market_date: Optional[str],
    override: bool,
    attempts: int,
    delay_seconds: float,
    sleep=time.sleep,
):
    """Evaluate the publication gate, with a BOUNDED automatic retry.

    The daily order is scrape -> batch completion -> simulations -> publication.
    When publication starts while the day's cohort is still finishing, the gate
    correctly refuses to publish — but deferring immediately leaves the site a
    full day stale even though the cohort completes minutes later, and requires
    an operator to rerun the command by hand.

    So a closed gate is re-evaluated a bounded number of times, minutes apart.
    This is deliberately NOT a polling loop: attempts are capped, the delay is
    measured in minutes, and each attempt is a single indexed batch-row read, so
    the added database load is a handful of reads per day. Exhausting the
    attempts defers exactly as before (dedicated exit code, nothing written).
    """
    gate = evaluate_publication_gate(client, market_date=market_date, override=override)
    remaining = max(0, int(attempts))
    attempt = 0
    while not gate.allowed and remaining > 0:
        attempt += 1
        logger.warning(
            "[publication-gate] closed [%s]: %s; automatic re-evaluation %s/%s in %.0fs",
            gate.reason_code,
            gate.reason,
            attempt,
            int(attempts),
            delay_seconds,
        )
        print(
            f"publication gate closed [{gate.reason_code}]; awaiting cohort completion "
            f"(automatic re-evaluation {attempt}/{int(attempts)} in {delay_seconds:.0f}s)"
        )
        sleep(max(0.0, float(delay_seconds)))
        remaining -= 1
        gate = evaluate_publication_gate(client, market_date=market_date, override=override)
        if gate.allowed:
            logger.info(
                "[publication-gate] reopened after %s automatic re-evaluation(s); publishing", attempt
            )
            print(f"publication gate OPENED after {attempt} automatic re-evaluation(s); publishing")
    return gate


def _to_text(value: Any) -> Optional[str]:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


# Postgres renders fractional seconds at whatever precision the value needs,
# trimming trailing zeros: 2026-08-03T04:59:35.25412+00:00 has five digits.
# datetime.fromisoformat on Python 3.8 accepts ONLY 3 or 6, so such a timestamp
# raised ValueError and parsed as None. That is not a harmless gap: _is_newer
# treats an unparseable right-hand side as "older than anything", so every
# freshness comparison against one of these timestamps returned True and
# reported a perfectly current snapshot as stale (25 sets in one --strict run).
# Normalize the fractional part to 6 digits before parsing.
_FRACTIONAL_SECONDS_RE = re.compile(r"(?<=:\d\d)\.(\d+)")


def _normalize_fractional_seconds(text: str) -> str:
    return _FRACTIONAL_SECONDS_RE.sub(lambda match: "." + match.group(1)[:6].ljust(6, "0"), text, count=1)


def _parse_datetime(value: Any) -> Optional[datetime]:
    text = _to_text(value)
    if not text:
        return None
    try:
        parsed = datetime.fromisoformat(_normalize_fractional_seconds(text.replace("Z", "+00:00")))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _max_datetime_text(*values: Any) -> Optional[str]:
    best_text: Optional[str] = None
    best_dt: Optional[datetime] = None
    for value in values:
        dt = _parse_datetime(value)
        if dt is not None and (best_dt is None or dt > best_dt):
            best_dt = dt
            best_text = _to_text(value)
    return best_text


def _is_newer(left: Any, right: Any) -> bool:
    left_dt = _parse_datetime(left)
    right_dt = _parse_datetime(right)
    return bool(left_dt and (right_dt is None or left_dt > right_dt))


def _is_newer_by_more_than(left: Any, right: Any, seconds: int) -> bool:
    left_dt = _parse_datetime(left)
    right_dt = _parse_datetime(right)
    if not left_dt or not right_dt:
        return False
    return (left_dt - right_dt).total_seconds() > seconds


def _first_row(result: Any) -> Optional[Dict[str, Any]]:
    rows = list((result.data if result else []) or [])
    return rows[0] if rows else None


def _is_timeout_error(exc: BaseException) -> bool:
    """Is this failure the client's finite PostgREST timeout firing?

    Classified by TYPE NAME rather than by importing httpx, so the diagnostic
    stays correct whichever transport the installed client uses. Used only to
    label the log line; a timeout is a failure either way and is never converted
    into a result.
    """
    return "timeout" in type(exc).__name__.lower()


def _execute_query(
    label: str, query: Any, *, set_id: Optional[str] = None
) -> Tuple[List[Dict[str, Any]], Optional[str]]:
    """Run one planning SELECT, timed, with a slow-query diagnostic.

    ``except Exception`` on purpose: KeyboardInterrupt is a BaseException and
    must propagate immediately so Ctrl+C during the read-only planning phase
    aborts the run rather than being classified as a transient query failure.
    Every request is bounded by the client's configured PostgREST HTTP timeout
    (SUPABASE_SERVICE_ROLE_POSTGREST_TIMEOUT_SECONDS, see
    backend.db.clients.supabase_client) — this wrapper adds observability, not a
    second client stack or a second timeout. That timeout is the upper bound on
    how long one blocked call can stay silent.

    A TIMED-OUT query is reported at WARNING with the query LABEL, the SET ID,
    the elapsed time and the exception TYPE — that is the failure an operator
    watching a silent run needs to see, and it is what distinguishes a blocked
    call from a merely slow one. Its exception MESSAGE stays at DEBUG on
    purpose: it can carry a PostgREST response body, which must never reach the
    scheduler log.

    Every OTHER failure stays at DEBUG, unchanged. `_latest_timestamp`
    deliberately probes timestamp columns that may not exist on a given table
    and falls through to the next one, so ordinary planning produces hundreds of
    expected, handled query errors per run. Promoting those to WARNING would
    bury the timeout line this diagnostic exists to surface.
    """
    started = time.monotonic()
    try:
        result = query.execute()
    except Exception as exc:
        elapsed = time.monotonic() - started
        if _is_timeout_error(exc):
            logger.warning(
                "[refresh-query] timeout label=%s set_id=%s elapsed=%.2fs error_type=%s",
                label, set_id, elapsed, type(exc).__name__,
            )
        logger.debug(
            "source freshness query failed label=%s set_id=%s elapsed=%.2fs error=%s",
            label, set_id, elapsed, exc,
        )
        return [], str(exc)
    elapsed = time.monotonic() - started
    if elapsed >= SLOW_QUERY_SECONDS:
        # Label + set id only. Never response bodies, headers or credentials.
        logger.warning("[refresh-query] slow label=%s set_id=%s elapsed=%.2fs", label, set_id, elapsed)
    return list(result.data or []), None


def _latest_timestamp(
    client: Any,
    *,
    table: str,
    timestamp_columns: Sequence[str],
    filters: Sequence[Tuple[str, Any]] = (),
    in_filters: Sequence[Tuple[str, Sequence[Any]]] = (),
) -> Tuple[Optional[str], List[str]]:
    checks: List[str] = []
    for column in timestamp_columns:
        query = client.table(table).select(column)
        for field, value in filters:
            query = query.eq(field, value)
        for field, values in in_filters:
            value_list = [value for value in values if value is not None]
            if not value_list:
                checks.append(f"{table}.{column}: skipped empty in-filter {field}")
                query = None
                break
            query = query.in_(field, value_list)
        if query is None:
            continue
        rows, error = _execute_query(f"{table}.{column}", query.order(column, desc=True).limit(1))
        checks.append(f"{table}.{column}: {'error' if error else 'ok'}")
        if rows and rows[0].get(column):
            return _to_text(rows[0].get(column)), checks
    return None, checks


def _row_exists(client: Any, *, table: str, field: str, value: Any) -> bool:
    rows, _error = _execute_query(
        f"{table}.exists",
        client.table(table).select(field).eq(field, value).limit(1),
    )
    return bool(rows)


def _read_snapshot_row(client: Any, table: str, select_fields: str, filters: Sequence[Tuple[str, Any]]) -> Optional[Dict[str, Any]]:
    query = client.table(table).select(select_fields)
    for field, value in filters:
        query = query.eq(field, value)
    rows, _error = _execute_query(f"{table}.snapshot", query.limit(1))
    return rows[0] if rows else None


@dataclass(frozen=True)
class CardsGenerationRead:
    """Outcome of the narrow cards-snapshot generation-marker read.

    Three outcomes are kept DISTINCT on purpose. ``generation_id is None`` alone
    cannot be trusted: an unreadable query and a snapshot row that genuinely has
    no marker are different defects, and neither may ever be silently compared
    equal to the market dashboard's generation ID.
    """

    generation_id: Optional[str]
    row_found: bool
    error: Optional[str]
    checks: List[str]

    @property
    def readable(self) -> bool:
        return self.error is None


def _read_cards_snapshot_generation_id(client: Any, set_id: str) -> CardsGenerationRead:
    """Read ONLY ``payload_json.meta.snapshot.generationId`` for one set.

    The previous implementation selected the whole ``payload_json`` document and
    reached into it in Python — a multi-megabyte download, parsed by pydantic,
    once per set, purely to compare one string. The projection below makes
    PostgREST do the extraction server-side.
    """
    label = "pokemon_set_cards_snapshot_latest.generation_id"
    rows, error = _execute_query(
        label,
        client.table("pokemon_set_cards_snapshot_latest")
        .select(CARDS_GENERATION_ID_PROJECTION)
        .eq("set_id", set_id)
        .limit(1),
        set_id=set_id,
    )
    if error:
        return CardsGenerationRead(None, False, error, [f"{label}: error {error}"])
    if not rows:
        return CardsGenerationRead(None, False, None, [f"{label}: no row"])
    return CardsGenerationRead(_to_text(rows[0].get("generation_id")), True, None, [f"{label}: ok"])


def _legacy_card_ids(client: Any, set_id: str) -> List[str]:
    rows, _error = _execute_query(
        "cards.ids",
        client.table("cards").select("id").eq("set_id", set_id),
    )
    return [str(row["id"]) for row in rows if row.get("id") is not None]


def _canonical_card_ids(client: Any, set_id: str) -> List[str]:
    rows, _error = _execute_query(
        "pokemon_canonical_cards.ids",
        client.table("pokemon_canonical_cards").select("id").eq("set_id", set_id),
    )
    return [str(row["id"]) for row in rows if row.get("id") is not None]


def _variant_ids_for_set(client: Any, set_id: str) -> List[str]:
    card_ids = _legacy_card_ids(client, set_id)
    if not card_ids:
        return []
    rows, _error = _execute_query(
        "card_variants.ids",
        client.table("card_variants").select("id").in_("card_id", card_ids),
    )
    return [str(row["id"]) for row in rows if row.get("id") is not None]


def _canonical_selected_variant_ids(client: Any, set_id: str) -> List[str]:
    rows, _error = _execute_query(
        "pokemon_canonical_card_market_prices_latest.variant_ids",
        client.table("pokemon_canonical_card_market_prices_latest")
        .select("card_variant_id")
        .eq("set_id", set_id),
    )
    return sorted({str(row["card_variant_id"]) for row in rows if row.get("card_variant_id") is not None})


def _latest_for_set_cards(client: Any, set_id: str) -> Tuple[Optional[str], List[str]]:
    checks: List[str] = []
    timestamps: List[Optional[str]] = []
    for table, columns in (
        ("pokemon_canonical_cards", ("updated_at", "created_at")),
        ("cards", ("updated_at", "created_at")),
    ):
        latest, table_checks = _latest_timestamp(client, table=table, timestamp_columns=columns, filters=(("set_id", set_id),))
        checks.extend(table_checks)
        timestamps.append(latest)

    legacy_card_ids = _legacy_card_ids(client, set_id)
    variant_ids = sorted(set(_variant_ids_for_set(client, set_id)) | set(_canonical_selected_variant_ids(client, set_id)))
    canonical_card_ids = _canonical_card_ids(client, set_id)

    latest, table_checks = _latest_timestamp(
        client,
        table="card_variants",
        timestamp_columns=("updated_at", "created_at"),
        in_filters=(("card_id", legacy_card_ids),),
    )
    checks.extend(table_checks)
    timestamps.append(latest)

    latest, table_checks = _latest_timestamp(
        client,
        table="card_variant_price_observations",
        timestamp_columns=("captured_at", "updated_at", "created_at"),
        in_filters=(("card_variant_id", variant_ids),),
    )
    checks.extend(table_checks)
    timestamps.append(latest)

    latest, table_checks = _latest_timestamp(
        client,
        table="pokemon_card_desirability_links",
        timestamp_columns=("updated_at", "created_at"),
        in_filters=(("pokemon_canonical_card_id", canonical_card_ids),),
    )
    checks.extend(table_checks)
    timestamps.append(latest)

    latest, table_checks = _latest_timestamp(
        client,
        table="pokemon_desirability_composite_scores",
        timestamp_columns=("updated_at", "created_at"),
    )
    checks.extend(table_checks)
    timestamps.append(latest)
    return _max_datetime_text(*timestamps), checks


def _latest_for_market_dashboard(client: Any, set_id: str) -> Tuple[Optional[str], List[str]]:
    checks: List[str] = []
    timestamps: List[Optional[str]] = []
    for table, columns in (
        ("pokemon_set_value_daily_history", ("updated_at", "snapshot_date", "created_at")),
        ("pokemon_set_top_chase_card_daily_history", ("updated_at", "snapshot_date", "created_at")),
    ):
        latest, table_checks = _latest_timestamp(client, table=table, timestamp_columns=columns, filters=(("set_id", set_id),))
        checks.extend(table_checks)
        timestamps.append(latest)

    latest, table_checks = _latest_timestamp(
        client,
        table="card_variant_price_observations",
        timestamp_columns=("captured_at", "updated_at", "created_at"),
        in_filters=(("card_variant_id", sorted(set(_variant_ids_for_set(client, set_id)) | set(_canonical_selected_variant_ids(client, set_id)))),),
    )
    checks.extend(table_checks)
    timestamps.append(latest)

    # The dashboard's performance_vs_cost_history_json is built from the set's
    # simulation history. Without these dependencies a newer simulation run can
    # leave the dashboard stale while the set-page snapshot (which does track
    # simulation_latest_by_target) rebuilds, producing two conflicting OPvC
    # histories. Both queries stay scoped to this set so one set's simulation
    # never invalidates every other set's dashboard.
    for table, columns in (
        ("simulation_latest_by_target", ("updated_at", "run_at")),
        ("calculation_history_trend", ("run_created_at", "snapshot_date")),
    ):
        latest, table_checks = _latest_timestamp(
            client,
            table=table,
            timestamp_columns=columns,
            filters=(("target_type", "set"), ("target_id", set_id)),
        )
        checks.extend(table_checks)
        timestamps.append(latest)
    return _max_datetime_text(*timestamps), checks


def _latest_simulation_history_date(client: Any, set_id: str) -> Tuple[Optional[str], List[str]]:
    """Latest calculation_history_trend snapshot_date for this set (date only)."""
    latest, checks = _latest_timestamp(
        client,
        table="calculation_history_trend",
        timestamp_columns=("snapshot_date",),
        filters=(("target_type", "set"), ("target_id", set_id)),
    )
    return (latest[:10] if latest else None), checks


SET_VALUE_HISTORY_SCOPES = ("standard", "hits", "top10")


def _latest_set_value_history_by_scope(client: Any, set_id: str, *, column: str) -> Tuple[Dict[str, Optional[str]], List[str]]:
    latest_by_scope: Dict[str, Optional[str]] = {}
    checks: List[str] = []
    for scope in SET_VALUE_HISTORY_SCOPES:
        latest, scope_checks = _latest_timestamp(
            client,
            table="pokemon_set_value_daily_history",
            timestamp_columns=(column,),
            filters=(("set_id", set_id), ("value_scope", scope)),
        )
        latest_by_scope[scope] = latest
        checks.extend(scope_checks)
    return latest_by_scope, checks


def _history_latest_date(history: Any) -> Optional[str]:
    dates = [
        _to_text((point or {}).get("date") or (point or {}).get("snapshotDate") or (point or {}).get("snapshot_date"))
        for point in (history if isinstance(history, list) else [])
        if isinstance(point, dict)
    ]
    return max((date[:10] for date in dates if date), default=None)


def _performance_history_latest_real_date(history: Any) -> Optional[str]:
    """Last OPvC point backed by a real simulation run.

    Carried-forward points exist for chart continuity and must never establish
    the history's freshness — treating one as current is exactly how a dashboard
    that stopped advancing keeps looking published. Mirrors
    audit_opening_analytics_publication.latest_real_performance_date.
    """
    latest: Optional[str] = None
    for point in history if isinstance(history, list) else []:
        if not isinstance(point, dict):
            continue
        if point.get("isCarriedForward") or point.get("is_carried_forward"):
            continue
        raw = point.get("date") or point.get("snapshotDate") or point.get("snapshot_date")
        date_key = (_to_text(raw) or "")[:10] or None
        if date_key and (latest is None or date_key > latest):
            latest = date_key
    return latest


def _dashboard_set_value_latest_date_by_scope(row: Dict[str, Any]) -> Dict[str, Optional[str]]:
    payload = row.get("payload_json") if isinstance(row.get("payload_json"), dict) else {}
    meta = payload.get("meta") if isinstance(payload.get("meta"), dict) else {}
    meta_dates = meta.get("setValueHistoryLatestDateByScope")
    if not isinstance(meta_dates, dict):
        meta_dates = meta.get("set_value_history_latest_date_by_scope")
    if isinstance(meta_dates, dict):
        return {scope: _to_text(meta_dates.get(scope)) for scope in SET_VALUE_HISTORY_SCOPES}

    histories_by_scope = row.get("set_value_histories_json")
    if not isinstance(histories_by_scope, dict):
        histories_by_scope = payload.get("setValueHistoriesByScope") or payload.get("set_value_histories_by_scope") or {}
    if not isinstance(histories_by_scope, dict):
        histories_by_scope = {}
    return {scope: _history_latest_date(histories_by_scope.get(scope)) for scope in SET_VALUE_HISTORY_SCOPES}


def _latest_for_explore_rankings(client: Any) -> Tuple[Optional[str], List[str]]:
    checks: List[str] = []
    timestamps: List[Optional[str]] = []
    for table, columns in (
        ("explore_rip_statistics_latest", ("updated_at", "run_at", "created_at")),
        ("simulation_latest_by_target", ("updated_at", "run_at")),
        ("pokemon_set_market_dashboard_snapshot_latest", ("updated_at",)),
        ("pokemon_set_opening_desirability_latest", ("updated_at", "built_at", "created_at")),
    ):
        latest, table_checks = _latest_timestamp(client, table=table, timestamp_columns=columns)
        checks.extend(table_checks)
        timestamps.append(latest)
    return _max_datetime_text(*timestamps), checks


def _latest_for_set_page(client: Any, set_id: str) -> Tuple[Optional[str], List[str]]:
    checks: List[str] = []
    timestamps: List[Optional[str]] = []
    for table, columns, filters in (
        ("pokemon_explore_rankings_snapshot_latest", ("updated_at",), (("tcg", "pokemon"), ("scope", "rip-statistics"))),
        ("pokemon_set_cards_snapshot_latest", ("updated_at",), (("set_id", set_id),)),
        ("pokemon_set_market_dashboard_snapshot_latest", ("updated_at",), (("set_id", set_id),)),
        ("simulation_latest_by_target", ("updated_at", "run_at"), (("target_type", "set"), ("target_id", set_id))),
        ("explore_rip_statistics_latest", ("updated_at", "run_at", "created_at"), (("set_id", set_id),)),
    ):
        latest, table_checks = _latest_timestamp(client, table=table, timestamp_columns=columns, filters=filters)
        checks.extend(table_checks)
        timestamps.append(latest)

    run_id = _latest_run_id_for_set(client, set_id)
    for table in (
        "simulation_input_cards",
        "simulation_input_cards_with_near_mint_price",
        "simulation_sealed_product_results",
    ):
        if run_id:
            latest, table_checks = _latest_timestamp(
                client,
                table=table,
                timestamp_columns=("updated_at", "captured_at", "created_at"),
                filters=(("calculation_run_id", run_id),),
            )
        else:
            latest, table_checks = None, [f"{table}: skipped missing calculation_run_id"]
        checks.extend(table_checks)
        timestamps.append(latest)
    latest, table_checks = _latest_timestamp(
        client,
        table="pokemon_set_sealed_market_snapshot_latest",
        timestamp_columns=("updated_at",),
        filters=(("set_id", set_id),),
    )
    checks.extend(table_checks)
    timestamps.append(latest)
    return _max_datetime_text(*timestamps), checks


def _rip_decision_source_authority(client: Any, set_id: str, run_id: Optional[str]) -> Tuple[Dict[str, Any], List[str]]:
    """Narrow current-source provenance used by semantic Set-page planning."""
    checks: List[str] = []
    market_rows, market_error = _execute_query(
        "pokemon_set_sealed_market_snapshot_latest.rip_decision_authority",
        client.table("pokemon_set_sealed_market_snapshot_latest")
        .select("classification_version,payload_json,updated_at")
        .eq("set_id", set_id)
        .limit(1),
    )
    checks.append(
        "pokemon_set_sealed_market_snapshot_latest.rip_decision_authority: "
        + (f"error {market_error}" if market_error else f"{len(market_rows)} row(s)")
    )
    market = market_rows[0] if market_rows else {}
    market_payload = market.get("payload_json") if isinstance(market.get("payload_json"), dict) else {}
    market_meta = market_payload.get("meta") if isinstance(market_payload.get("meta"), dict) else {}

    product_rows: List[Dict[str, Any]] = []
    product_error = None
    if run_id:
        product_rows, product_error = _execute_query(
            "simulation_sealed_product_results.rip_decision_authority",
            client.table("simulation_sealed_product_results")
            .select("sealed_product_id,updated_at")
            .eq("calculation_run_id", run_id),
        )
    checks.append(
        "simulation_sealed_product_results.rip_decision_authority: "
        + ("skipped missing calculation_run_id" if not run_id else (f"error {product_error}" if product_error else f"{len(product_rows)} row(s)"))
    )
    return {
        "classification_version": _to_text(market.get("classification_version")) or _to_text(market_meta.get("classificationVersion")),
        "snapshot_contract_version": _to_text(market_meta.get("snapshotContractVersion")),
        "product_result_count": len(product_rows),
        "product_results_updated_at": _max_datetime_text(*(_to_text(row.get("updated_at")) for row in product_rows)),
    }, checks


def _latest_for_desirability_validation(client: Any) -> Tuple[Optional[str], List[str]]:
    checks: List[str] = []
    timestamps: List[Optional[str]] = []
    for table, filters in (
        ("pokemon_explore_rankings_snapshot_latest", (("tcg", "pokemon"), ("scope", "rip-statistics"))),
        ("pokemon_set_page_snapshot_latest", ()),
    ):
        latest, table_checks = _latest_timestamp(client, table=table, timestamp_columns=("updated_at",), filters=filters)
        checks.extend(table_checks)
        timestamps.append(latest)
    return _max_datetime_text(*timestamps), checks


def _latest_published_leaderboard(client: Any) -> Tuple[Optional[Dict[str, Any]], List[str]]:
    """The newest COMPLETE published RIP leaderboard snapshot row, if any."""
    rows, error = _execute_query(
        "pokemon_public_rip_leaderboard_snapshots.latest",
        client.table("pokemon_public_rip_leaderboard_snapshots")
        .select(
            "id,market_date,published_at,publication_status,eligible_cohort_count,"
            "cohort_version,cohort_fingerprint,overall_rip_version,financial_rip_version,"
            "ca7_version,diagnostics_json"
        )
        .eq("publication_status", "complete")
        .order("market_date", desc=True)
        .order("published_at", desc=True)
        .limit(1),
    )
    checks = [
        "pokemon_public_rip_leaderboard_snapshots: "
        + (f"error {error}" if error else f"{len(rows)} row(s)")
    ]
    return (rows[0] if rows else None), checks


def _published_leaderboard_rows(client: Any, snapshot_id: str) -> Tuple[List[Dict[str, Any]], List[str]]:
    rows, error = _execute_query(
        "pokemon_public_rip_leaderboard_rows.by_snapshot",
        client.table("pokemon_public_rip_leaderboard_rows")
        .select("set_id,set_canonical_key,overall_rip_rank,simulation_calculation_run_id")
        .eq("snapshot_id", snapshot_id),
    )
    checks = [
        "pokemon_public_rip_leaderboard_rows: "
        + (f"error {error}" if error else f"{len(rows)} row(s)")
    ]
    return rows, checks


def _latest_eligible_run_id_by_set(client: Any) -> Tuple[Dict[str, Optional[str]], List[str]]:
    """The latest accepted simulation run per set, keyed by set id.

    Read from ``explore_rip_statistics_latest`` - the same view the ranking
    service builds targets from - so "the latest eligible run" means the same
    thing to the freshness check and to the payload it is judging.
    """
    rows, error = _execute_query(
        "explore_rip_statistics_latest.run_ids",
        client.table("explore_rip_statistics_latest").select(
            "set_id,calculation_run_id,financial_rip_v3_score_version"
        ),
    )
    checks = [
        "explore_rip_statistics_latest.run_ids: "
        + (f"error {error}" if error else f"{len(rows)} row(s)")
    ]
    by_set: Dict[str, Optional[str]] = {}
    for row in rows:
        set_id = _to_text(row.get("set_id"))
        if set_id:
            by_set[set_id] = _to_text(row.get("calculation_run_id"))
    return by_set, checks


def _leaderboard_contract_staleness(client: Any) -> Tuple[List[Dict[str, Any]], List[str]]:
    """Version/cohort/source-run staleness of the published RIP leaderboard.

    THE GAP THIS CLOSES. Every other check in this file compares TIMESTAMPS. A
    scoring-version change moves no timestamp, so a leaderboard published under
    an obsolete Financial RIP / Collector Appeal / Overall RIP / public contract
    version stayed classified "fresh" indefinitely - and a matching market date
    read as proof of currency. The verdict comes from the shared evaluator in
    ``public_rip_publication_contract`` so the refresher, the publisher and the
    audit cannot disagree about what "current" means.
    """
    from backend.db.services.public_rip_publication_contract import (
        evaluate_leaderboard_staleness,
        supported_cohort_fingerprint,
    )

    checks: List[str] = []
    snapshot, snapshot_checks = _latest_published_leaderboard(client)
    checks.extend(snapshot_checks)
    if not snapshot:
        return evaluate_leaderboard_staleness(None), checks

    published_rows, row_checks = _published_leaderboard_rows(client, str(snapshot.get("id")))
    checks.extend(row_checks)
    latest_runs, run_checks = _latest_eligible_run_id_by_set(client)
    checks.extend(run_checks)

    published_run_by_set = {
        _to_text(row.get("set_id")): _to_text(row.get("simulation_calculation_run_id"))
        for row in published_rows
        if _to_text(row.get("set_id"))
    }
    # Compared only over the sets the leaderboard actually carries. A supported
    # set missing from the leaderboard is already reported by the row-count
    # reason; reporting it a second time as a superseded run would name the same
    # defect twice under two different fixes.
    scoped_latest = {
        set_id: run_id
        for set_id, run_id in latest_runs.items()
        if set_id in published_run_by_set
    }
    reasons = evaluate_leaderboard_staleness(
        snapshot,
        ranked_row_count=len(published_rows),
        latest_eligible_run_id_by_set=scoped_latest,
        published_run_id_by_set=published_run_by_set,
        cohort=supported_cohort_fingerprint(),
    )
    return reasons, checks


# Per-invocation planning memo. `_latest_run_id_for_set` is called twice per set
# during planning (once by `_latest_for_set_page`, once by
# `_source_rows_exist_for_set_page`) and answers identically both times.
# Installed and TORN DOWN by `_build_plan` in a finally block, so it is scoped to
# exactly one planning pass and can never carry stale data across runs — nor
# across the later write/rebuild phase, where a run id may legitimately change.
_PLANNING_RUN_ID_CACHE: Optional[Dict[str, Optional[str]]] = None


def _latest_run_id_for_set(client: Any, set_id: str) -> Optional[str]:
    cache = _PLANNING_RUN_ID_CACHE
    if cache is not None and set_id in cache:
        return cache[set_id]
    run_id = _latest_run_id_for_set_uncached(client, set_id)
    if cache is not None:
        cache[set_id] = run_id
    return run_id


def _latest_run_id_for_set_uncached(client: Any, set_id: str) -> Optional[str]:
    rows, _error = _execute_query(
        "explore_rip_statistics_latest.latest_run",
        client.table("explore_rip_statistics_latest")
        .select("set_id,calculation_run_id,run_at")
        .eq("set_id", set_id)
        .order("run_at", desc=True)
        .limit(1),
    )
    row = rows[0] if rows else None
    if row and row.get("calculation_run_id"):
        return str(row.get("calculation_run_id"))
    rows, _error = _execute_query(
        "simulation_latest_by_target.latest_run",
        client.table("simulation_latest_by_target")
        .select("target_type,target_id,calculation_run_id,run_at")
        .eq("target_type", "set")
        .eq("target_id", set_id)
        .order("run_at", desc=True)
        .limit(1),
    )
    row = rows[0] if rows else None
    return str(row.get("calculation_run_id")) if row and row.get("calculation_run_id") else None


def _has_known_stale_warning(warnings: Iterable[Any]) -> bool:
    warning_text = "\n".join(str(warning).lower() for warning in warnings or [])
    return any(pattern in warning_text for pattern in KNOWN_SET_PAGE_STALE_WARNING_PATTERNS)


def _extract_snapshot_completeness(payload: Dict[str, Any]) -> Dict[str, Any]:
    meta = payload.get("meta") if isinstance(payload.get("meta"), dict) else {}
    completeness = meta.get("snapshotCompleteness")
    if not isinstance(completeness, dict):
        completeness = meta.get("snapshot_completeness")
    return completeness if isinstance(completeness, dict) else {}


def _extract_section_freshness(payload: Dict[str, Any]) -> Dict[str, Any]:
    meta = payload.get("meta") if isinstance(payload.get("meta"), dict) else {}
    freshness = meta.get("sectionFreshness")
    if not isinstance(freshness, dict):
        freshness = meta.get("section_freshness")
    return freshness if isinstance(freshness, dict) else {}


def _extract_embedded_rankings_updated_at(payload: Dict[str, Any]) -> Optional[str]:
    completeness = _extract_snapshot_completeness(payload)
    return _to_text(
        completeness.get("explore_rankings_snapshot_updated_at")
        or completeness.get("exploreRankingsSnapshotUpdatedAt")
    )


def _set_page_has_rank_fields(payload: Dict[str, Any]) -> bool:
    summary = payload.get("summary") if isinstance(payload.get("summary"), dict) else {}
    rank_keys = (
        "desirability_rank",
        "pack_score_rank",
        "pack_rank",
        "profit_rank",
        "safety_rank",
        "stability_rank",
        "relative_pack_score_rank",
        "overall_rank",
    )
    return any(summary.get(key) is not None for key in rank_keys)


def _source_rows_exist_for_set_page(client: Any, set_id: str) -> bool:
    run_id = _latest_run_id_for_set(client, set_id)
    simulation_rows_exist = bool(
        run_id
        and (
            _row_exists(client, table="simulation_input_cards", field="calculation_run_id", value=run_id)
            or _row_exists(
                client,
                table="simulation_input_cards_with_near_mint_price",
                field="calculation_run_id",
                value=run_id,
            )
        )
    )
    return simulation_rows_exist or _row_exists(client, table="pokemon_canonical_cards", field="set_id", value=set_id)


def _cards_snapshot_staleness(client: Any, set_id: str) -> FreshnessResult:
    dependency_updated_at, checks = _latest_for_set_cards(client, set_id)
    row = _read_snapshot_row(
        client,
        "pokemon_set_cards_snapshot_latest",
        "set_id,cards_json,card_count,payload_json,updated_at",
        (("set_id", set_id),),
    )
    if not row:
        return FreshnessResult("cards", True, "snapshot row missing", None, dependency_updated_at, checks)
    payload = row.get("payload_json") if isinstance(row.get("payload_json"), dict) else {}
    snapshot_meta = (payload.get("meta") or {}).get("snapshot")
    marker_missing = not isinstance(snapshot_meta, dict)
    movement_marker_missing = not bool(
        isinstance(snapshot_meta, dict)
        and snapshot_meta.get("movementContractVersion")
        and snapshot_meta.get("generationId")
        and snapshot_meta.get("windowConvention")
        and "movementAsOfDate" in snapshot_meta
        and snapshot_meta.get("builtAt")
    )
    correlation_missing = not isinstance(
        payload.get("cardAppealMarketPriceCorrelation") or payload.get("card_appeal_market_price_correlation"),
        dict,
    )
    snapshot_updated_at = _to_text(row.get("updated_at"))
    cards = row.get("cards_json") if isinstance(row.get("cards_json"), list) else []
    priced_count = sum(
        1 for card in cards
        if isinstance(card, dict)
        and (card.get("marketPrice") is not None or card.get("market_price") is not None)
    )
    movement_contract_count = sum(
        1 for card in cards
        if isinstance(card, dict)
        and isinstance(card.get("movement7d") or card.get("movement_7d"), dict)
    )
    selected_price_rows, selected_price_error = _execute_query(
        "pokemon_canonical_card_market_prices_latest.coverage",
        client.table("pokemon_canonical_card_market_prices_latest")
        .select("canonical_card_id,market_price")
        .eq("set_id", set_id),
    )
    if selected_price_error:
        checks.append(f"pokemon_canonical_card_market_prices_latest.coverage: {selected_price_error}")
    authoritative_priced_count = sum(1 for price_row in selected_price_rows if price_row.get("market_price") is not None)
    if authoritative_priced_count and priced_count < authoritative_priced_count:
        return FreshnessResult(
            "cards", True, "snapshot priced-card coverage below canonical selected-price coverage",
            snapshot_updated_at, dependency_updated_at, checks,
        )
    if priced_count and movement_contract_count < priced_count:
        return FreshnessResult(
            "cards", True, "priced cards missing 7D movement contracts", snapshot_updated_at, dependency_updated_at, checks
        )
    if marker_missing:
        return FreshnessResult("cards", True, "required completeness marker missing", snapshot_updated_at, dependency_updated_at, checks)
    if movement_marker_missing:
        return FreshnessResult("cards", True, "movement generation marker missing", snapshot_updated_at, dependency_updated_at, checks)
    if correlation_missing:
        return FreshnessResult("cards", True, "card appeal validation payload missing", snapshot_updated_at, dependency_updated_at, checks)
    if _is_newer(dependency_updated_at, snapshot_updated_at):
        return FreshnessResult("cards", True, "dependency newer than snapshot", snapshot_updated_at, dependency_updated_at, checks)
    return FreshnessResult("cards", False, "fresh", snapshot_updated_at, dependency_updated_at, checks)


def _market_snapshot_staleness(client: Any, set_id: str, window: str) -> FreshnessResult:
    dependency_updated_at, checks = _latest_for_market_dashboard(client, set_id)
    value_history_updated_by_scope, value_updated_checks = _latest_set_value_history_by_scope(client, set_id, column="updated_at")
    value_history_date_by_scope, value_date_checks = _latest_set_value_history_by_scope(client, set_id, column="snapshot_date")
    checks.extend(value_updated_checks)
    checks.extend(value_date_checks)
    latest_value_history_updated_at = _max_datetime_text(*value_history_updated_by_scope.values())
    latest_value_history_date = max((date for date in value_history_date_by_scope.values() if date), default=None)
    dependency_updated_at = _max_datetime_text(dependency_updated_at, latest_value_history_updated_at)
    simulation_history_date, simulation_date_checks = _latest_simulation_history_date(client, set_id)
    checks.extend(simulation_date_checks)
    row = _read_snapshot_row(
        client,
        "pokemon_set_market_dashboard_snapshot_latest",
        "set_id,window_key,payload_json,set_value_histories_json,top_chase_card_histories_json,performance_vs_cost_history_json,latest_market_date,updated_at",
        (("set_id", set_id), ("window_key", window)),
    )
    if not row:
        return FreshnessResult("market_dashboard", True, "snapshot row missing", None, dependency_updated_at, checks)
    payload = row.get("payload_json") if isinstance(row.get("payload_json"), dict) else {}
    snapshot_meta = (payload.get("meta") or {}).get("snapshot")
    marker_missing = not isinstance(snapshot_meta, dict)
    movement_marker_missing = not bool(
        isinstance(snapshot_meta, dict)
        and snapshot_meta.get("movementContractVersion")
        and snapshot_meta.get("generationId")
        and snapshot_meta.get("windowConvention")
        and "movementAsOfDate" in snapshot_meta
        and snapshot_meta.get("builtAt")
    )
    snapshot_updated_at = _to_text(row.get("updated_at"))
    latest_market_date = _to_text(row.get("latest_market_date") or payload.get("latestMarketDate") or payload.get("latest_market_date"))
    top_chase_histories = row.get("top_chase_card_histories_json")
    top_chase_history_end = max(
        (
            _history_latest_date(history)
            for history in (top_chase_histories.values() if isinstance(top_chase_histories, dict) else [])
        ),
        default=None,
    )
    if top_chase_histories and latest_market_date and top_chase_history_end != latest_market_date:
        return FreshnessResult(
            "market_dashboard", True, "top chase history end differs from latest_market_date",
            snapshot_updated_at, dependency_updated_at, checks,
        )
    dashboard_date_by_scope = _dashboard_set_value_latest_date_by_scope(row)
    if marker_missing:
        return FreshnessResult("market_dashboard", True, "required completeness marker missing", snapshot_updated_at, dependency_updated_at, checks)
    if _is_newer(latest_value_history_updated_at, snapshot_updated_at):
        return FreshnessResult("market_dashboard", True, "set value daily history updated after market dashboard", snapshot_updated_at, dependency_updated_at, checks)
    if _is_newer(latest_value_history_date, latest_market_date):
        return FreshnessResult("market_dashboard", True, "set value daily history date newer than latest_market_date", snapshot_updated_at, dependency_updated_at, checks)
    for scope, raw_date in value_history_date_by_scope.items():
        if _is_newer(raw_date, dashboard_date_by_scope.get(scope)):
            return FreshnessResult(
                "market_dashboard",
                True,
                f"{scope} set value history newer than dashboard history",
                snapshot_updated_at,
                dependency_updated_at,
                checks,
            )
    performance_history = row.get("performance_vs_cost_history_json")
    if not isinstance(performance_history, list):
        performance_history = payload.get("performanceVsCostHistory") or payload.get("performance_vs_cost_history")
    dashboard_performance_history_end = _performance_history_latest_real_date(performance_history)
    if _is_newer(simulation_history_date, dashboard_performance_history_end):
        return FreshnessResult(
            "market_dashboard",
            True,
            "simulation history newer than dashboard performance history",
            snapshot_updated_at,
            dependency_updated_at,
            checks,
        )
    if _is_newer(dependency_updated_at, snapshot_updated_at):
        return FreshnessResult("market_dashboard", True, "dependency newer than snapshot", snapshot_updated_at, dependency_updated_at, checks)
    if movement_marker_missing:
        return FreshnessResult("market_dashboard", True, "movement generation marker missing", snapshot_updated_at, dependency_updated_at, checks)
    # Cards-vs-dashboard generation parity. This needs exactly ONE string from
    # the cards snapshot, so it reads exactly that string (server-side JSON
    # projection) instead of downloading the whole cards payload_json.
    cards_generation = _read_cards_snapshot_generation_id(client, set_id)
    checks.extend(cards_generation.checks)
    if not cards_generation.readable:
        # Fail closed: an unreadable cards snapshot is never evidence of a
        # matching generation ID.
        return FreshnessResult(
            "market_dashboard",
            True,
            f"cards snapshot generation ID unreadable: {cards_generation.error}",
            snapshot_updated_at,
            dependency_updated_at,
            checks,
        )
    if not cards_generation.row_found:
        return FreshnessResult(
            "market_dashboard",
            True,
            "cards snapshot row missing for generation comparison",
            snapshot_updated_at,
            dependency_updated_at,
            checks,
        )
    if cards_generation.generation_id != _to_text(snapshot_meta.get("generationId")):
        return FreshnessResult(
            "market_dashboard",
            True,
            "cards and market dashboard generation IDs differ",
            snapshot_updated_at,
            dependency_updated_at,
            checks,
        )
    return FreshnessResult("market_dashboard", False, "fresh", snapshot_updated_at, dependency_updated_at, checks)


def _set_page_snapshot_staleness(client: Any, set_id: str) -> FreshnessResult:
    dependency_updated_at, checks = _latest_for_set_page(client, set_id)
    row = _read_snapshot_row(
        client,
        "pokemon_set_page_snapshot_latest",
        "set_id,payload_json,updated_at",
        (("set_id", set_id),),
    )
    if not row:
        return FreshnessResult("set_page", True, "snapshot row missing", None, dependency_updated_at, checks)
    payload = row.get("payload_json") if isinstance(row.get("payload_json"), dict) else {}
    meta = payload.get("meta") if isinstance(payload.get("meta"), dict) else {}
    warnings = list(meta.get("warnings") or [])
    snapshot_updated_at = _to_text(row.get("updated_at"))
    completeness = _extract_snapshot_completeness(payload)
    if not isinstance(completeness, dict) or not completeness:
        return FreshnessResult("set_page", True, "required completeness marker missing", snapshot_updated_at, dependency_updated_at, checks, warnings)
    rankings_updated_at, rankings_checks = _latest_timestamp(
        client,
        table="pokemon_explore_rankings_snapshot_latest",
        timestamp_columns=("updated_at",),
        filters=(("tcg", "pokemon"), ("scope", "rip-statistics")),
    )
    checks.extend(rankings_checks)
    if rankings_updated_at and not _set_page_has_rank_fields(payload):
        return FreshnessResult("set_page", True, "rank fields missing while rankings snapshot exists", snapshot_updated_at, dependency_updated_at, checks, warnings)
    if _is_newer(dependency_updated_at, snapshot_updated_at):
        return FreshnessResult("set_page", True, "dependency newer than snapshot", snapshot_updated_at, dependency_updated_at, checks, warnings)
    ranked = _set_page_has_rank_fields(payload)
    run_id = _latest_run_id_for_set(client, set_id)
    if ranked:
        authority, authority_checks = _rip_decision_source_authority(client, set_id, run_id)
        checks.extend(authority_checks)
        decision_reasons = evaluate_rip_decision_staleness(
            payload.get("ripDecision"),
            ranked=True,
            expected_run_id=run_id,
            expected_sealed_market_classification_version=authority["classification_version"],
            expected_sealed_market_contract_version=authority["snapshot_contract_version"],
            expected_product_result_count=authority["product_result_count"],
            expected_product_results_updated_at=authority["product_results_updated_at"],
        )
        if decision_reasons:
            return FreshnessResult(
                "set_page", True, decision_reasons[0]["message"], snapshot_updated_at,
                dependency_updated_at, checks, warnings,
            )
    if _has_known_stale_warning(warnings) and _source_rows_exist_for_set_page(client, set_id):
        return FreshnessResult("set_page", True, "known stale warning present while source rows exist", snapshot_updated_at, dependency_updated_at, checks, warnings)
    return FreshnessResult("set_page", False, "fresh", snapshot_updated_at, dependency_updated_at, checks, warnings)


def _global_snapshot_staleness(client: Any, *, family: str) -> FreshnessResult:
    if family == "explore_rankings":
        dependency_updated_at, checks = _latest_for_explore_rankings(client)
        row = _read_snapshot_row(
            client,
            "pokemon_explore_rankings_snapshot_latest",
            "tcg,scope,ranking_payload_json,updated_at",
            (("tcg", "pokemon"), ("scope", "rip-statistics")),
        )
        payload_key = "ranking_payload_json"
    elif family == "desirability_validation":
        dependency_updated_at, checks = _latest_for_desirability_validation(client)
        row = _read_snapshot_row(
            client,
            "pokemon_desirability_validation_snapshot_latest",
            "tcg,scope,payload_json,updated_at",
            (("tcg", "pokemon"), ("scope", "latest")),
        )
        payload_key = "payload_json"
    else:
        raise ValueError(f"Unsupported global family: {family}")

    if not row:
        return FreshnessResult(family, True, "snapshot row missing", None, dependency_updated_at, checks)
    payload = row.get(payload_key) if isinstance(row.get(payload_key), dict) else {}
    snapshot_updated_at = _to_text(row.get("updated_at"))
    marker_missing = not isinstance((payload.get("meta") or {}).get("snapshot"), dict)
    if marker_missing:
        return FreshnessResult(family, True, "required completeness marker missing", snapshot_updated_at, dependency_updated_at, checks)
    if family == "explore_rankings":
        meta = payload.get("meta") or {}
        snapshot_meta = meta.get("snapshot") or {}
        cohort = meta.get("publicAnalyticsCohort") or {}
        ranked_count = int((cohort.get("overallRanked") or {}).get("rankedSetCount") or 0)
        targets = list(payload.get("targets") or [])
        if any(not snapshot_meta.get(key) for key in ("publicationId", "marketDate", "builtAt")):
            return FreshnessResult(family, True, "canonical publication metadata missing", snapshot_updated_at, dependency_updated_at, checks)
        if ranked_count <= 0 or len(targets) != ranked_count:
            return FreshnessResult(family, True, "complete public cohort marker/count invalid", snapshot_updated_at, dependency_updated_at, checks)
        if any(
            (target.get("overallRipRankComparisonStatus1d")
             or target.get("overall_rip_rank_comparison_status_1d"))
            not in {"available", "new", "unavailable"}
            for target in targets
        ):
            return FreshnessResult(family, True, "1D RIP comparison status missing", snapshot_updated_at, dependency_updated_at, checks)
        publication = _read_snapshot_row(
            client,
            "pokemon_public_rip_leaderboard_snapshots",
            "id,publication_status",
            (("id", snapshot_meta["publicationId"]),),
        )
        if not publication or publication.get("publication_status") != "complete":
            return FreshnessResult(family, True, "canonical publication row missing or incomplete", snapshot_updated_at, dependency_updated_at, checks)
        # SCORING-CONTRACT staleness, checked BEFORE the timestamp comparison
        # below. A version cutover moves no timestamp, so reaching the timestamp
        # check first is exactly how an obsolete contract stayed "fresh" while 22
        # fresh Financial RIP V3 simulations sat underneath it.
        contract_reasons, contract_checks = _leaderboard_contract_staleness(client)
        checks.extend(contract_checks)
        if contract_reasons:
            detail = "; ".join(str(reason.get("detail")) for reason in contract_reasons[:4])
            if len(contract_reasons) > 4:
                detail += f" (+{len(contract_reasons) - 4} more)"
            return FreshnessResult(
                family, True, f"published scoring contract is not canonical: {detail}",
                snapshot_updated_at, dependency_updated_at, checks,
            )
    if _is_newer(dependency_updated_at, snapshot_updated_at):
        return FreshnessResult(family, True, "dependency newer than snapshot", snapshot_updated_at, dependency_updated_at, checks)
    return FreshnessResult(family, False, "fresh", snapshot_updated_at, dependency_updated_at, checks)


def _resolve_sets(client: Any, *, set_id: Optional[str]) -> List[Dict[str, Any]]:
    if set_id:
        return [resolve_set_row(client, set_id)]
    return list_pokemon_sets(client)


def _build_plan(client: Any, *, set_rows: List[Dict[str, Any]], window: str) -> Tuple[List[SetRefreshPlan], FreshnessResult, FreshnessResult, int]:
    """READ-ONLY classification of every snapshot family. Writes nothing.

    Progress is logged deterministically because this phase is long, silent and
    indistinguishable from a hang: every set at DEBUG, a heartbeat every
    PLANNING_PROGRESS_INTERVAL sets at INFO, and ALWAYS any set slower than
    SLOW_PLANNING_SET_SECONDS regardless of where it falls in the interval.

    OPERATIONAL EXPECTATION. Under the measured current workload (~4s per set,
    209 sets, interval 3) normal INFO heartbeats arrive roughly every 10-20
    seconds. That is an expectation, NOT a guarantee: network latency varies,
    and a single request may remain silent until its finite service-role
    PostgREST timeout. That timeout — not this interval — is the actual upper
    bound for one blocked PostgREST call. A `[refresh-query] timeout` line names
    the query label and set id when it fires.
    """
    global _PLANNING_RUN_ID_CACHE

    plans: List[SetRefreshPlan] = []
    source_checks = 0
    total = len(set_rows)
    plan_started = time.monotonic()
    logger.info("[refresh-plan] starting sets=%s", total)
    _PLANNING_RUN_ID_CACHE = {}
    try:
        for index, set_row in enumerate(set_rows, start=1):
            set_id = str(set_row["id"])
            canonical_key = str(set_row.get("canonical_key") or set_id)
            logger.debug(
                "[refresh-plan] checking %s/%s key=%s id=%s", index, total, canonical_key, set_id
            )
            set_started = time.monotonic()
            cards = _cards_snapshot_staleness(client, set_id)
            market = _market_snapshot_staleness(client, set_id, window)
            page = _set_page_snapshot_staleness(client, set_id)
            elapsed = time.monotonic() - set_started
            source_checks += len(cards.dependency_checks) + len(market.dependency_checks) + len(page.dependency_checks)
            plans.append(SetRefreshPlan(set_row=set_row, cards=cards, market_dashboard=market, set_page=page))
            checked = "[refresh-plan] checked %s/%s key=%s elapsed=%.2fs"
            if elapsed >= SLOW_PLANNING_SET_SECONDS or index % PLANNING_PROGRESS_INTERVAL == 0 or index == total:
                logger.info(checked, index, total, canonical_key, elapsed)
            else:
                logger.debug(checked, index, total, canonical_key, elapsed)
        logger.info("[refresh-plan] checking global families (explore_rankings, desirability_validation)")
        rankings = _global_snapshot_staleness(client, family="explore_rankings")
        validation = _global_snapshot_staleness(client, family="desirability_validation")
    finally:
        # Dropped on success, on failure and on KeyboardInterrupt alike.
        _PLANNING_RUN_ID_CACHE = None
    source_checks += len(rankings.dependency_checks) + len(validation.dependency_checks)
    logger.info(
        "[refresh-plan] complete sets=%s elapsed=%.2fs", total, time.monotonic() - plan_started
    )
    return plans, rankings, validation, source_checks


def _set_label(set_row: Dict[str, Any]) -> str:
    return f"{set_row.get('canonical_key') or set_row.get('id')} ({set_row.get('name')})"


def _record_stale(summary: RefreshSummary, result: FreshnessResult) -> None:
    if result.stale:
        summary.stale_snapshot_families.add(result.family)


def _maybe_rebuild_coordinated_market(
    client: Any,
    plan: SetRefreshPlan,
    *,
    commit: bool,
    days: int,
    window: str,
    summary: RefreshSummary,
) -> None:
    if not plan.cards.stale and not plan.market_dashboard.stale:
        return
    set_row = plan.set_row
    canonical_key = str(set_row.get("canonical_key") or set_row.get("id"))
    if not commit:
        reason = f"cards={plan.cards.reason}; market_dashboard={plan.market_dashboard.reason}"
        summary.skipped_sets["cards"].append(f"{canonical_key}: dry-run coordinated rebuild {reason}")
        summary.skipped_sets["market_dashboard"].append(f"{canonical_key}: dry-run coordinated rebuild {reason}")
        return
    def _operation(op_client: Any) -> None:
        refresh_canonical_card_market_prices_for_set(op_client, str(set_row["id"]), commit=True)
        cards_row, dashboard_row, history_rows = build_coordinated_set_market_snapshot_rows(
            set_row,
            days=days,
            window=window,
            client=op_client,
        )
        upsert_row(
            op_client,
            "pokemon_set_cards_snapshot_latest",
            cards_row,
            on_conflict="set_id",
            commit=True,
        )
        upsert_rows(
            op_client,
            "pokemon_set_top_chase_card_daily_history",
            history_rows,
            on_conflict="set_id,snapshot_date,rank",
            commit=True,
        )
        upsert_row(
            op_client,
            "pokemon_set_market_dashboard_snapshot_latest",
            dashboard_row,
            on_conflict="set_id,window_key",
            commit=True,
        )

    try:
        _rebuild_with_bounded_retry(
            _operation,
            operation_name="coordinated_cards_market",
            set_id=str(set_row["id"]),
            client=client,
        )
        summary.rebuilt_sets["cards"].append(canonical_key)
        summary.rebuilt_sets["market_dashboard"].append(canonical_key)
        # Every coordinated write committed — bust the frontend seed cache so the
        # new market date replaces any older cached shell/overview response
        # (best-effort, no-op when unconfigured).
        notify_set_publication(set_row, window=window, commit=True)
    except Exception as exc:
        logger.exception("failed coordinated cards/market snapshot refresh %s", _set_label(set_row))
        summary.failed_sets["cards"].append(f"{canonical_key}: {exc}")
        summary.failed_sets["market_dashboard"].append(f"{canonical_key}: {exc}")


def _maybe_rebuild_rankings(client: Any, rankings: FreshnessResult, *, commit: bool, summary: RefreshSummary) -> None:
    if not rankings.stale:
        return
    if not commit:
        summary.global_skipped.append(f"explore_rankings: dry-run {rankings.reason}")
        return
    try:
        publish_explore_rip_rankings_snapshot(client, commit=True)
        summary.global_rebuilt.append("explore_rankings")
    except Exception as exc:
        logger.exception("failed explore rankings snapshot refresh")
        summary.global_failed.append(f"explore_rankings: {exc}")


def _maybe_rebuild_explore_card_movers(
    client: Any, *, market_date: Optional[str], commit: bool, summary: RefreshSummary
) -> None:
    if not market_date:
        summary.global_failed.append("explore_card_movers: promoted market date unavailable")
        return
    try:
        candidate = build_explore_card_movers(
            client=client, market_date=str(market_date)[:10], commit=False
        )
        current = _read_snapshot_row(
            client, "pokemon_explore_card_movers_snapshot_latest",
            "source_generation_fingerprint",
            (("tcg", "pokemon"), ("scope", "explore"), ("window_key", "7D")),
        )
        stale = (
            not current
            or current.get("source_generation_fingerprint")
            != candidate.get("source_generation_fingerprint")
        )
        if not stale:
            return
        summary.stale_snapshot_families.add("explore_card_movers")
        if not commit:
            summary.global_skipped.append("explore_card_movers: dry-run source generation changed")
            return
        from backend.db.services.pokemon_explore_card_movers_service import upsert_explore_card_movers_snapshot
        upsert_explore_card_movers_snapshot(candidate, client=client)
        summary.global_rebuilt.append("explore_card_movers")
    except Exception as exc:
        logger.exception("failed Explore card movers snapshot refresh")
        summary.global_failed.append(f"explore_card_movers: {exc}")


def _maybe_rebuild_explore_set_values(
    client: Any, *, market_date: Optional[str], commit: bool, summary: RefreshSummary,
    market_index_history: Optional[Sequence[Mapping[str, Any]]] = None,
) -> None:
    if not market_date:
        summary.global_failed.append("explore_set_values: promoted market date unavailable")
        return
    try:
        build_kwargs = {"client": client, "market_date": str(market_date)[:10], "commit": False}
        if market_index_history is not None:
            build_kwargs["market_index_history"] = market_index_history
        candidate = build_explore_set_values(**build_kwargs)
        current = _read_snapshot_row(
            client, "pokemon_explore_set_value_snapshot_latest", "source_generation_fingerprint",
            (("tcg", "pokemon"), ("scope", "market")),
        )
        stale = not current or current.get("source_generation_fingerprint") != candidate.get("source_generation_fingerprint")
        if not stale:
            return
        summary.stale_snapshot_families.add("explore_set_values")
        if not commit:
            summary.global_skipped.append("explore_set_values: dry-run source generation changed")
            return
        from backend.db.services.pokemon_explore_set_value_service import upsert_explore_set_value_snapshot
        upsert_explore_set_value_snapshot(candidate, client=client)
        summary.global_rebuilt.append("explore_set_values")
    except Exception as exc:
        logger.exception("failed global Market Set Value snapshot refresh")
        summary.global_failed.append(f"explore_set_values: {exc}")


def _maybe_rebuild_set_page(
    client: Any,
    plan: SetRefreshPlan,
    *,
    rankings_updated_at: Optional[str],
    commit: bool,
    summary: RefreshSummary,
) -> None:
    rankings_rebuilt_after_set_page = bool(rankings_updated_at and _is_newer(rankings_updated_at, plan.set_page.snapshot_updated_at))
    # plan.market_dashboard.stale means the market dashboard was (or is about
    # to be) rebuilt earlier in THIS run — the set page embeds history/market
    # context from it, so it must be rebuilt after, in the same run. Deferring
    # it to the next invocation left set pages one refresh behind their
    # market dashboards (stale Performance vs Cost flatline).
    needs_rebuild = (
        plan.set_page.stale
        or plan.cards.stale
        or plan.market_dashboard.stale
        or rankings_rebuilt_after_set_page
    )
    if not needs_rebuild:
        return
    set_row = plan.set_row
    canonical_key = str(set_row.get("canonical_key") or set_row.get("id"))
    if not commit:
        summary.skipped_sets["set_page"].append(f"{canonical_key}: dry-run dependency/set page stale")
        return
    def _operation(op_client: Any) -> None:
        row = build_set_page_snapshot_row(set_row, client=op_client)
        upsert_row(op_client, "pokemon_set_page_snapshot_latest", row, on_conflict="set_id", commit=True)

    try:
        _rebuild_with_bounded_retry(
            _operation,
            operation_name="set_page",
            set_id=str(set_row["id"]),
            client=client,
        )
        summary.rebuilt_sets["set_page"].append(canonical_key)
        # Invalidate the frontend shell/overview seed cache on a fresh publish.
        notify_set_publication(set_row, commit=True)
    except Exception as exc:
        logger.exception("failed set page snapshot refresh %s", _set_label(set_row))
        summary.failed_sets["set_page"].append(f"{canonical_key}: {exc}")


def _build_validation_snapshot(client: Any, *, commit: bool, summary: RefreshSummary) -> None:
    if not commit:
        return
    try:
        page_rows = _read_page_snapshots(client)
        targets = _target_rows(page_rows)
        opening_audit = build_opening_set_audit(targets)
        audit_rows: List[Dict[str, Any]] = []
        skipped: List[Dict[str, str]] = []
        for page_row in page_rows:
            set_id = _to_text(page_row.get("set_id"))
            payload = page_row.get("payload_json") or {}
            if not set_id:
                skipped.append({"set_id": "", "reason": "missing set_id"})
                continue
            try:
                validation = build_desirability_validation_payload(
                    set_id=set_id,
                    set_payload=payload,
                    target_rows=targets,
                    cards_payload=_read_cards_snapshot(client, set_id),
                )
                validation["generated_at"] = datetime.now(timezone.utc).isoformat()
                validation["formula_version"] = FORMULA_VERSION
                audit_rows.append(_audit_row(validation))
            except Exception as exc:
                logger.exception("failed desirability validation row set_id=%s", set_id)
                skipped.append({"set_id": set_id, "reason": str(exc)})
        global_payload = _build_global_validation_snapshot_payload(
            audit_rows=audit_rows,
            skipped=skipped,
            opening_audit=opening_audit,
        )
        _upsert_global_validation_snapshot(client, global_payload)
        summary.global_rebuilt.append("desirability_validation")
    except Exception as exc:
        logger.exception("failed desirability validation snapshot refresh")
        summary.global_failed.append(f"desirability_validation: {exc}")


def _set_page_has_identity(payload: Dict[str, Any]) -> bool:
    target = payload.get("target") if isinstance(payload.get("target"), dict) else {}
    return bool(_to_text(target.get("target_id") or target.get("id")))


def _has_content(value: Any) -> bool:
    """True when a payload node carries real data.

    Container skeletons count as EMPTY: the partial set-page builder publishes
    ``rip_statistics = {"pack_paths": {}, "normal_pack_states": {}}``, which is a
    truthy dict but holds nothing. Treating it as populated would make every
    legitimately-unavailable page fail strict mode.
    """
    if value is None or isinstance(value, bool):
        return bool(value)
    if isinstance(value, (int, float)):
        return True
    if isinstance(value, str):
        return bool(value.strip())
    if isinstance(value, dict):
        return any(_has_content(item) for item in value.values())
    if isinstance(value, (list, tuple, set)):
        return any(_has_content(item) for item in value)
    return True


def _payload_at(payload: Dict[str, Any], path: Tuple[str, ...]) -> Any:
    node: Any = payload
    for key in path:
        if not isinstance(node, dict):
            return None
        node = node.get(key)
    return node


def _section_is_populated(payload: Dict[str, Any], section: SimulationDerivedSection) -> bool:
    return any(_has_content(_payload_at(payload, path)) for path in section.payload_paths)


def _section_freshness_entries(
    section_freshness: Dict[str, Any], section: SimulationDerivedSection
) -> List[Tuple[str, Dict[str, Any]]]:
    entries: List[Tuple[str, Dict[str, Any]]] = []
    for key in section.freshness_keys:
        entry = section_freshness.get(key)
        if isinstance(entry, dict):
            entries.append((key, entry))
    return entries


def _verify_simulation_derived_sections_absent(
    canonical_key: str,
    payload: Dict[str, Any],
    availability: Dict[str, Any],
    section_freshness: Dict[str, Any],
) -> List[str]:
    """The complete simulation-unavailable surface contract.

    Independent of ``carriedForwardSections``: every known simulation-derived
    section is inspected directly, so a page cannot pass by simply not
    mentioning a section it is misrepresenting.
    """
    problems: List[str] = []
    declared = {str(section) for section in (availability.get("unavailableSections") or [])}

    for section in SIMULATION_DERIVED_SECTIONS:
        entries = _section_freshness_entries(section_freshness, section)
        statuses = {key: str(entry.get("status") or "").lower() for key, entry in entries}
        populated = _section_is_populated(payload, section)

        for key, status in statuses.items():
            if status in ("fresh", "current"):
                problems.append(
                    f"{canonical_key}: simulation section {key} labeled {status} while simulation is unavailable"
                )

        stale_entries = [(key, entry) for key, entry in entries if statuses.get(key) == "stale"]
        if populated and not stale_entries:
            problems.append(
                f"{canonical_key}: simulation section {section.key} is populated but not labeled stale "
                "while simulation is unavailable"
            )
        # Carried-forward content must be dated; an undated "stale" section is
        # indistinguishable from current data to every downstream consumer.
        for key, entry in stale_entries:
            if not _to_text(entry.get("dataAsOf") or entry.get("sourceDate") or entry.get("source_date")):
                problems.append(
                    f"{canonical_key}: carried-forward section {key} has no source/data-as-of date"
                )

        if not populated and not (declared & set(section.declaration_keys)):
            problems.append(
                f"{canonical_key}: unavailableSections missing absent simulation section {section.key} "
                f"(accepted aliases {sorted(section.declaration_keys)})"
            )

    return problems


def _verify_no_current_simulation_advertisement(
    canonical_key: str, payload: Dict[str, Any], meta: Dict[str, Any], availability: Dict[str, Any]
) -> List[str]:
    """A page with no simulation must not advertise a run id or an as-of date."""
    problems: List[str] = []
    summary = payload.get("summary") if isinstance(payload.get("summary"), dict) else {}
    request = meta.get("request") if isinstance(meta.get("request"), dict) else {}
    run_id = _to_text(
        summary.get("calculation_run_id")
        or summary.get("run_id")
        or request.get("calculation_run_id")
        or payload.get("calculation_run_id")
    )
    if run_id:
        problems.append(
            f"{canonical_key}: simulation run id {run_id} advertised while simulation is unavailable"
        )
    for label, value in (
        ("simulationAvailability.asOfDate", availability.get("asOfDate")),
        ("summary.run_at", summary.get("run_at")),
        ("meta.simulationSourceDate", meta.get("simulationSourceDate")),
    ):
        if _to_text(value):
            problems.append(
                f"{canonical_key}: {label}={_to_text(value)} advertised while simulation is unavailable"
            )
    return problems


def _verify_partial_set_page(
    canonical_key: str,
    payload: Dict[str, Any],
    meta: Dict[str, Any],
    availability: Dict[str, Any],
    section_freshness: Dict[str, Any],
) -> List[str]:
    """Contract for a set page explicitly labeled simulation-unavailable.

    Empty simulation-derived sections (top_hits, OPvC, run id, simulation source
    NO_ROW/MISSING) are EXPECTED here and must not fail. Instead the page must
    truthfully declare its unavailability and never label absent simulation data
    as fresh/current.
    """
    problems: List[str] = []
    if not _to_text(availability.get("reason")):
        problems.append(f"{canonical_key}: simulationAvailability.reason missing for unavailable page")

    unavailable = availability.get("unavailableSections")
    if not isinstance(unavailable, list) or not unavailable:
        problems.append(f"{canonical_key}: unavailableSections must be nonempty for an unavailable page")
    else:
        missing_declarations = _REQUIRED_UNAVAILABLE_SECTIONS - {str(section) for section in unavailable}
        if missing_declarations:
            problems.append(
                f"{canonical_key}: unavailableSections missing simulation-derived sections {sorted(missing_declarations)}"
            )

    warnings = [str(warning).lower() for warning in (meta.get("warnings") or [])]
    if not any("simulation" in warning and "unavailable" in warning for warning in warnings):
        problems.append(f"{canonical_key}: simulation-unavailable warning missing")

    # The COMPLETE simulation-derived surface, inspected directly (never only via
    # the payload's own carriedForwardSections list).
    problems.extend(
        _verify_simulation_derived_sections_absent(
            canonical_key, payload, availability, section_freshness
        )
    )
    problems.extend(
        _verify_no_current_simulation_advertisement(canonical_key, payload, meta, availability)
    )

    # Sections the payload itself declares carried-forward must also hold up:
    # labeled stale, with a defensible source/data-as-of date.
    for key in availability.get("carriedForwardSections") or []:
        section = section_freshness.get(key) if isinstance(section_freshness.get(key), dict) else {}
        status = str(section.get("status") or "").lower()
        if status != "stale":
            problems.append(
                f"{canonical_key}: carried-forward section {key} not labeled stale (status={status or 'missing'})"
            )
        elif not _to_text(section.get("dataAsOf") or section.get("sourceDate")):
            problems.append(f"{canonical_key}: carried-forward section {key} has no source/data-as-of date")
    return sorted(set(problems), key=problems.index)


def _verify_available_set_page(
    client: Any,
    set_id: str,
    canonical_key: str,
    payload: Dict[str, Any],
    meta: Dict[str, Any],
    row: Dict[str, Any],
    section_freshness: Dict[str, Any],
    rankings_updated_at: Optional[str],
) -> List[str]:
    """Stricter contract for a page that claims simulation data is available."""
    problems: List[str] = []
    sources = meta.get("sources") if isinstance(meta.get("sources"), dict) else {}
    warnings = list(meta.get("warnings") or [])
    if len(payload.get("top_hits") or []) <= 0:
        problems.append(f"{canonical_key}: top_hits missing")
    if sources.get("simulation_input_cards") != "OK":
        problems.append(f"{canonical_key}: simulation_input_cards source={sources.get('simulation_input_cards')}")
    if _has_known_stale_warning(warnings) and _source_rows_exist_for_set_page(client, set_id):
        problems.append(f"{canonical_key}: stale warning remains")
    if rankings_updated_at and not _set_page_has_rank_fields(payload):
        problems.append(f"{canonical_key}: rank fields missing while rankings snapshot exists")

    set_page_updated_at = _to_text(row.get("updated_at"))
    embedded_rankings_updated_at = _extract_embedded_rankings_updated_at(payload)
    decision_signal_ranks = section_freshness.get("decisionSignalRanks")
    decision_signal_rank_status = (
        _to_text(decision_signal_ranks.get("status"))
        if isinstance(decision_signal_ranks, dict)
        else None
    )

    if rankings_updated_at and _is_newer(rankings_updated_at, set_page_updated_at):
        problems.append(f"{canonical_key}: rankings snapshot rebuilt after set page snapshot")
    elif rankings_updated_at and embedded_rankings_updated_at and _is_newer(rankings_updated_at, embedded_rankings_updated_at):
        problems.append(f"{canonical_key}: set page embedded rankings snapshot is stale")
    elif decision_signal_rank_status and decision_signal_rank_status.lower() == "stale" and rankings_updated_at and embedded_rankings_updated_at and _is_newer(rankings_updated_at, embedded_rankings_updated_at):
        problems.append(f"{canonical_key}: decision signal ranks marked stale with newer rankings snapshot available")

    return problems


def _verify_set_page(client: Any, set_row: Dict[str, Any], *, rankings_updated_at: Optional[str]) -> List[str]:
    """Simulation-aware strict verification for a published set-page snapshot.

    The set-page builder can intentionally publish a partial page for a set with
    no simulation run (``meta.simulationAvailability.available == false``). Such a
    page has empty simulation-derived sections BY DESIGN and must pass strict
    mode as long as it truthfully declares its unavailability. A page that claims
    simulation is available is held to the stricter (original) expectations. A
    malformed/identity-less page fails either way.
    """
    set_id = str(set_row["id"])
    canonical_key = str(set_row.get("canonical_key") or set_id)
    row = _read_snapshot_row(
        client,
        "pokemon_set_page_snapshot_latest",
        "set_id,payload_json,updated_at",
        (("set_id", set_id),),
    )
    if not row:
        return [f"{canonical_key}: set page snapshot missing"]
    payload = row.get("payload_json") if isinstance(row.get("payload_json"), dict) else {}
    meta = payload.get("meta") if isinstance(payload.get("meta"), dict) else {}
    problems: List[str] = []

    # Structural markers required for EVERY published page, partial or not.
    if not _set_page_has_identity(payload):
        problems.append(f"{canonical_key}: set identity missing")
    if not isinstance(meta.get("snapshot"), dict):
        problems.append(f"{canonical_key}: meta.snapshot missing")
    if not isinstance(meta.get("snapshotCompleteness") or meta.get("snapshot_completeness"), dict):
        problems.append(f"{canonical_key}: snapshotCompleteness missing")

    availability = meta.get("simulationAvailability")
    if not isinstance(availability, dict):
        availability = meta.get("simulation_availability")
    if not isinstance(availability, dict):
        # A partial (or any) page must declare simulation availability.
        problems.append(f"{canonical_key}: simulationAvailability metadata missing")
        return problems

    section_freshness = _extract_section_freshness(payload)
    available = availability.get("available")
    if available is False:
        problems.extend(
            _verify_partial_set_page(canonical_key, payload, meta, availability, section_freshness)
        )
    elif available is True:
        problems.extend(
            _verify_available_set_page(
                client,
                set_id,
                canonical_key,
                payload,
                meta,
                row,
                section_freshness,
                rankings_updated_at,
            )
        )
    else:
        problems.append(
            f"{canonical_key}: simulationAvailability.available must be a boolean, got {available!r}"
        )

    return problems


def _verify_after_build(client: Any, set_rows: List[Dict[str, Any]], summary: RefreshSummary) -> None:
    rankings_row = _read_snapshot_row(
        client,
        "pokemon_explore_rankings_snapshot_latest",
        "tcg,scope,updated_at",
        (("tcg", "pokemon"), ("scope", "rip-statistics")),
    )
    rankings_updated_at = _to_text((rankings_row or {}).get("updated_at"))
    problems: List[str] = []
    for set_row in set_rows:
        problems.extend(_verify_set_page(client, set_row, rankings_updated_at=rankings_updated_at))
    summary.warnings_remaining = problems
    summary.problem_canonical_keys = [problem.split(":", 1)[0] for problem in problems[:10]]


def _staleness_seconds(dependency_updated_at: Any, snapshot_updated_at: Any) -> float:
    dependency_dt = _parse_datetime(dependency_updated_at)
    snapshot_dt = _parse_datetime(snapshot_updated_at)
    if not dependency_dt or not snapshot_dt:
        return 0.0
    return max(0.0, (dependency_dt - snapshot_dt).total_seconds())


def _audit_set_page_freshness(client: Any, set_rows: List[Dict[str, Any]]) -> SetPageFreshnessAudit:
    """Post-run freshness guard for the set-page snapshot family.

    Compares each set page snapshot's updated_at against the newest simulation
    run timestamp and the market dashboard snapshot timestamp — the two
    dependencies whose lag produces stale Performance vs Cost history on the
    set-detail pages. Only the sets this run processed are audited, so
    intentionally unsupported/hidden sets never count against strict mode.
    """
    audit = SetPageFreshnessAudit()
    for set_row in set_rows:
        set_id = str(set_row["id"])
        canonical_key = str(set_row.get("canonical_key") or set_id)
        audit.total += 1
        row = _read_snapshot_row(
            client,
            "pokemon_set_page_snapshot_latest",
            "set_id,updated_at",
            (("set_id", set_id),),
        )
        snapshot_updated_at = _to_text((row or {}).get("updated_at"))
        if not row or not snapshot_updated_at:
            audit.stale_details.append(f"{canonical_key}: set page snapshot missing")
            continue

        simulation_run_at, _checks = _latest_timestamp(
            client,
            table="simulation_latest_by_target",
            timestamp_columns=("updated_at", "run_at"),
            filters=(("target_type", "set"), ("target_id", set_id)),
        )
        rip_run_at, _checks = _latest_timestamp(
            client,
            table="explore_rip_statistics_latest",
            timestamp_columns=("updated_at", "run_at", "created_at"),
            filters=(("set_id", set_id),),
        )
        market_updated_at, _checks = _latest_timestamp(
            client,
            table="pokemon_set_market_dashboard_snapshot_latest",
            timestamp_columns=("updated_at",),
            filters=(("set_id", set_id),),
        )

        latest_simulation = _max_datetime_text(simulation_run_at, rip_run_at)
        reasons: List[str] = []
        if _is_newer(latest_simulation, snapshot_updated_at):
            reasons.append(f"simulation newer ({latest_simulation} > {snapshot_updated_at})")
        if _is_newer(market_updated_at, snapshot_updated_at):
            reasons.append(f"market dashboard newer ({market_updated_at} > {snapshot_updated_at})")

        if not reasons:
            audit.fresh += 1
            continue

        audit.stale_details.append(f"{canonical_key}: {'; '.join(reasons)}")
        staleness = _staleness_seconds(_max_datetime_text(latest_simulation, market_updated_at), snapshot_updated_at)
        if staleness > audit.max_staleness_seconds:
            audit.max_staleness_seconds = staleness
            audit.max_staleness_set = canonical_key
    return audit


def _has_hard_failures(summary: RefreshSummary) -> bool:
    """A requested set (or global family) build actually failed.

    Distinct from staleness/verification warnings: these are builds that raised
    or were caught-and-recorded by an inner builder. The CLI must return nonzero
    on these regardless of --strict so a scheduler never treats a partial
    recovery as success.
    """
    return bool(
        summary.global_failed
        or any(summary.failed_sets[family] for family in summary.failed_sets)
    )


def _strict_should_fail(summary: RefreshSummary, *, commit: bool) -> bool:
    audit = summary.set_page_audit
    return bool(
        summary.warnings_remaining
        or summary.global_failed
        or any(summary.failed_sets[family] for family in summary.failed_sets)
        or (audit and audit.stale)
        or (not commit and summary.stale_snapshot_families)
    )


def _print_summary(summary: RefreshSummary) -> None:
    print("public snapshot refresh summary")
    print(f"source checks performed: {summary.source_checks_performed}")
    print(f"stale snapshot families detected: {', '.join(sorted(summary.stale_snapshot_families)) or 'none'}")
    print(f"global rebuilt: {', '.join(summary.global_rebuilt) or 'none'}")
    print(f"global skipped: {', '.join(summary.global_skipped) or 'none'}")
    print(f"global failed: {', '.join(summary.global_failed) or 'none'}")
    for family in ("sealed_market", "cards", "market_dashboard", "set_page"):
        print(f"{family} rebuilt: {len(summary.rebuilt_sets[family])} {summary.rebuilt_sets[family][:20]}")
        print(f"{family} skipped: {len(summary.skipped_sets[family])} {summary.skipped_sets[family][:20]}")
        print(f"{family} failed: {len(summary.failed_sets[family])} {summary.failed_sets[family][:20]}")
    print(f"warnings remaining: {len(summary.warnings_remaining)}")
    for warning in summary.warnings_remaining[:20]:
        print(f"  {warning}")
    print(f"first 10 problem canonical keys: {summary.problem_canonical_keys[:10]}")
    audit = summary.set_page_audit
    if audit is not None:
        print("set page freshness audit")
        print(f"  sets compared: {audit.total}")
        print(f"  fresh: {audit.fresh}")
        print(f"  stale: {audit.stale}")
        if audit.max_staleness_set:
            print(f"  max staleness: {audit.max_staleness_seconds / 3600.0:.1f}h ({audit.max_staleness_set})")
        for detail in audit.stale_details[:20]:
            print(f"  stale: {detail}")


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    logging.getLogger("httpx").setLevel(logging.WARNING)
    args = build_parser().parse_args()
    if str(args.tcg or "").strip().lower() != "pokemon":
        raise SystemExit("Only --tcg pokemon is supported by this refresh script")

    commit = bool(args.commit)
    client = get_client()

    # Batch-cohort gate: downstream promotion only when the day's scrape cohort
    # is observation-complete. In required mode (production default) the gate
    # fails closed on every failure class. A closed gate DEFERS publication with
    # a dedicated exit code (distinct from a build failure) so the scheduler
    # never treats "nothing published" as success. Dry-run reports the decision.
    gate = _await_open_publication_gate(
        client,
        market_date=args.market_date,
        override=args.force_publish,
        # Only a committing run may wait: a dry-run must stay fast and read-only.
        attempts=args.gate_wait_attempts if commit else 0,
        delay_seconds=args.gate_wait_seconds,
    )
    if not commit:
        print(
            "stale public snapshot refresh: publication gate decision (dry-run) "
            f"[{gate.reason_code}] allowed={gate.allowed}: {gate.reason}"
        )
    elif not gate.allowed:
        print("public snapshot refresh gated")
        for line in gate_decision_report(gate, entry_point="stale public snapshot refresh"):
            print(line)
        print("operator action: resolve/requeue the incomplete scrape batch, then rerun the refresh")
        raise SystemExit(GATE_DEFERRED_EXIT_CODE)
    elif gate.override:
        print(f"publication gate OVERRIDDEN (manual recovery) [{gate.reason_code}]: {gate.reason}")

    set_rows = _resolve_sets(client, set_id=args.set_id)
    # PLAN BEFORE WRITE. Nothing below this call writes until _build_plan has
    # classified EVERY set; an interruption or failure during planning therefore
    # leaves production untouched.
    plans, rankings, validation, source_checks = _build_plan(client, set_rows=set_rows, window=args.window)
    logger.info(
        "[refresh-phase] planning complete; entering %s phase sets=%s",
        "rebuild/write" if commit else "dry-run report",
        len(plans),
    )

    summary = RefreshSummary(source_checks_performed=source_checks)
    for plan in plans:
        _record_stale(summary, plan.cards)
        _record_stale(summary, plan.market_dashboard)
        _record_stale(summary, plan.set_page)
    _record_stale(summary, rankings)

    # Sealed Market is deliberately refreshed from sealed ingestion alone,
    # before and independently of card/simulation/RIP snapshot families.
    from backend.scripts.build_pokemon_set_sealed_market_snapshots import build_one as build_sealed_market
    for plan in plans:
        canonical_key = str(plan.set_row.get("canonical_key") or plan.set_row.get("id"))
        # Unit/in-memory plans may use symbolic IDs; persisted sets use UUIDs.
        # Do not let a non-database fixture trigger a real Supabase read.
        try:
            UUID(str(plan.set_row.get("id")))
        except (TypeError, ValueError):
            summary.skipped_sets["sealed_market"].append(f"{canonical_key}: non-persisted set id")
            continue
        try:
            report = build_sealed_market(plan.set_row, commit)
            if report["action"] == "unchanged":
                summary.skipped_sets["sealed_market"].append(canonical_key)
            elif commit:
                summary.rebuilt_sets["sealed_market"].append(canonical_key)
            else:
                summary.stale_snapshot_families.add("sealed_market")
                summary.skipped_sets["sealed_market"].append(f"{canonical_key}: dry-run {report['action']}")
        except Exception as exc:
            summary.failed_sets["sealed_market"].append(f"{canonical_key}: {exc}")

    # Rebuild order for the remaining families: coordinated Cards + Market
    # Dashboard, global Set Values, global card movers, rankings, set pages,
    # validation. Global Market reads never catch themselves up at route time.
    for plan in plans:
        _maybe_rebuild_coordinated_market(
            client,
            plan,
            commit=commit,
            days=args.days,
            window=args.window,
            summary=summary,
        )

    if not args.set_id:
        # Global Market is a two-stage publication: canonical set-value history
        # first, then its chain-linked Pokemon-level index, then the page-ready
        # snapshot that embeds marketOverview.
        index_ready = False
        index_history_for_snapshot = None
        try:
            if not hasattr(client, "table"):
                raise LookupError("legacy test client has no PostgREST surface")
            from backend.db.services.pokemon_market_index_service import build_market_index_history, persist_index_rows
            index_rows = build_market_index_history(client, through_date=args.market_date or gate.market_date)
            if commit:
                persist_index_rows(client, index_rows)
            else:
                summary.stale_snapshot_families.add("pokemon_market_index")
                index_history_for_snapshot = index_rows
            index_ready = True
        except LookupError:
            # Strict repository fakes used by pre-index orchestration tests do
            # not model PostgREST. Real clients always expose table().
            summary.global_skipped.append("pokemon_market_index: client unavailable")
        except Exception as exc:
            summary.global_failed.append(f"pokemon_market_index: {exc}")
        if index_ready:
            _maybe_rebuild_explore_set_values(
                client, market_date=args.market_date or gate.market_date,
                commit=commit, summary=summary,
                market_index_history=index_history_for_snapshot,
            )
        _maybe_rebuild_explore_card_movers(
            client, market_date=args.market_date or gate.market_date,
            commit=commit, summary=summary,
        )

    rankings_needed = rankings.stale
    if rankings_needed:
        summary.stale_snapshot_families.add("explore_rankings")
    rankings_reason = rankings.reason
    _maybe_rebuild_rankings(
        client,
        FreshnessResult("explore_rankings", rankings_needed, rankings_reason),
        commit=commit,
        summary=summary,
    )

    rankings_row_after_rebuild = _read_snapshot_row(
        client,
        "pokemon_explore_rankings_snapshot_latest",
        "tcg,scope,updated_at",
        (("tcg", "pokemon"), ("scope", "rip-statistics")),
    )
    rankings_updated_at_after_rebuild = _to_text((rankings_row_after_rebuild or {}).get("updated_at"))

    for plan in plans:
        _maybe_rebuild_set_page(
            client,
            plan,
            rankings_updated_at=rankings_updated_at_after_rebuild,
            commit=commit,
            summary=summary,
        )

    _verify_after_build(client, set_rows, summary)
    summary.set_page_audit = _audit_set_page_freshness(client, set_rows)
    _print_summary(summary)
    # Tagged seed invalidation stays best-effort and non-fatal, but it is no
    # longer silent: a run where it was never configured and a run where every
    # POST succeeded must be distinguishable in the log, because "database is
    # current but the page still shows yesterday" has exactly one other cause.
    print(log_revalidation_diagnostics())

    # A hard build failure always fails the run so the scheduler never treats a
    # partial recovery as success; --strict additionally fails on staleness.
    if _has_hard_failures(summary) or (args.strict and _strict_should_fail(summary, commit=commit)):
        raise SystemExit(1)


if __name__ == "__main__":
    main()
