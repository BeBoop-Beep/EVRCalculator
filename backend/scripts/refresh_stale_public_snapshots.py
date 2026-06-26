from __future__ import annotations

import argparse
import logging
import sys
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

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
    build_cards_snapshot_row,
    build_explore_rankings_snapshot_row,
    build_market_dashboard_snapshot_rows,
    build_set_page_snapshot_row,
    get_client,
    list_pokemon_sets,
    resolve_set_row,
    upsert_row,
    upsert_rows,
)

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
class RefreshSummary:
    source_checks_performed: int = 0
    stale_snapshot_families: set[str] = field(default_factory=set)
    rebuilt_sets: Dict[str, List[str]] = field(default_factory=lambda: {"cards": [], "market_dashboard": [], "set_page": []})
    skipped_sets: Dict[str, List[str]] = field(default_factory=lambda: {"cards": [], "market_dashboard": [], "set_page": []})
    failed_sets: Dict[str, List[str]] = field(default_factory=lambda: {"cards": [], "market_dashboard": [], "set_page": []})
    warnings_remaining: List[str] = field(default_factory=list)
    problem_canonical_keys: List[str] = field(default_factory=list)
    global_rebuilt: List[str] = field(default_factory=list)
    global_skipped: List[str] = field(default_factory=list)
    global_failed: List[str] = field(default_factory=list)


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
    return parser


def _to_text(value: Any) -> Optional[str]:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _parse_datetime(value: Any) -> Optional[datetime]:
    text = _to_text(value)
    if not text:
        return None
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
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


def _execute_query(label: str, query: Any) -> Tuple[List[Dict[str, Any]], Optional[str]]:
    try:
        result = query.execute()
    except Exception as exc:
        logger.debug("source freshness query failed label=%s error=%s", label, exc)
        return [], str(exc)
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
    variant_ids = _variant_ids_for_set(client, set_id)
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
        in_filters=(("card_variant_id", _variant_ids_for_set(client, set_id)),),
    )
    checks.extend(table_checks)
    timestamps.append(latest)
    return _max_datetime_text(*timestamps), checks


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
    for table in ("simulation_input_cards", "simulation_input_cards_with_near_mint_price"):
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
    return _max_datetime_text(*timestamps), checks


def _latest_for_desirability_validation(client: Any) -> Tuple[Optional[str], List[str]]:
    checks: List[str] = []
    timestamps: List[Optional[str]] = []
    for table, filters in (
        ("pokemon_explore_rankings_snapshot_latest", (("tcg", "pokemon"), ("scope", "rip-statistics"))),
        ("pokemon_set_page_snapshot_latest", ()),
        ("pokemon_set_market_dashboard_snapshot_latest", ()),
    ):
        latest, table_checks = _latest_timestamp(client, table=table, timestamp_columns=("updated_at",), filters=filters)
        checks.extend(table_checks)
        timestamps.append(latest)
    return _max_datetime_text(*timestamps), checks


def _latest_run_id_for_set(client: Any, set_id: str) -> Optional[str]:
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
        "set_id,payload_json,updated_at",
        (("set_id", set_id),),
    )
    if not row:
        return FreshnessResult("cards", True, "snapshot row missing", None, dependency_updated_at, checks)
    payload = row.get("payload_json") if isinstance(row.get("payload_json"), dict) else {}
    marker_missing = not isinstance((payload.get("meta") or {}).get("snapshot"), dict)
    correlation_missing = not isinstance(
        payload.get("cardAppealMarketPriceCorrelation") or payload.get("card_appeal_market_price_correlation"),
        dict,
    )
    snapshot_updated_at = _to_text(row.get("updated_at"))
    if marker_missing:
        return FreshnessResult("cards", True, "required completeness marker missing", snapshot_updated_at, dependency_updated_at, checks)
    if correlation_missing:
        return FreshnessResult("cards", True, "card appeal validation payload missing", snapshot_updated_at, dependency_updated_at, checks)
    if _is_newer(dependency_updated_at, snapshot_updated_at):
        return FreshnessResult("cards", True, "dependency newer than snapshot", snapshot_updated_at, dependency_updated_at, checks)
    return FreshnessResult("cards", False, "fresh", snapshot_updated_at, dependency_updated_at, checks)


def _market_snapshot_staleness(client: Any, set_id: str, window: str) -> FreshnessResult:
    dependency_updated_at, checks = _latest_for_market_dashboard(client, set_id)
    row = _read_snapshot_row(
        client,
        "pokemon_set_market_dashboard_snapshot_latest",
        "set_id,window_key,payload_json,updated_at",
        (("set_id", set_id), ("window_key", window)),
    )
    if not row:
        return FreshnessResult("market_dashboard", True, "snapshot row missing", None, dependency_updated_at, checks)
    payload = row.get("payload_json") if isinstance(row.get("payload_json"), dict) else {}
    marker_missing = not isinstance((payload.get("meta") or {}).get("snapshot"), dict)
    snapshot_updated_at = _to_text(row.get("updated_at"))
    if marker_missing:
        return FreshnessResult("market_dashboard", True, "required completeness marker missing", snapshot_updated_at, dependency_updated_at, checks)
    if _is_newer(dependency_updated_at, snapshot_updated_at):
        return FreshnessResult("market_dashboard", True, "dependency newer than snapshot", snapshot_updated_at, dependency_updated_at, checks)
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
    if _is_newer(dependency_updated_at, snapshot_updated_at):
        return FreshnessResult(family, True, "dependency newer than snapshot", snapshot_updated_at, dependency_updated_at, checks)
    return FreshnessResult(family, False, "fresh", snapshot_updated_at, dependency_updated_at, checks)


def _resolve_sets(client: Any, *, set_id: Optional[str]) -> List[Dict[str, Any]]:
    if set_id:
        return [resolve_set_row(client, set_id)]
    return list_pokemon_sets(client)


def _build_plan(client: Any, *, set_rows: List[Dict[str, Any]], window: str) -> Tuple[List[SetRefreshPlan], FreshnessResult, FreshnessResult, int]:
    plans: List[SetRefreshPlan] = []
    source_checks = 0
    for set_row in set_rows:
        set_id = str(set_row["id"])
        cards = _cards_snapshot_staleness(client, set_id)
        market = _market_snapshot_staleness(client, set_id, window)
        page = _set_page_snapshot_staleness(client, set_id)
        source_checks += len(cards.dependency_checks) + len(market.dependency_checks) + len(page.dependency_checks)
        plans.append(SetRefreshPlan(set_row=set_row, cards=cards, market_dashboard=market, set_page=page))
    rankings = _global_snapshot_staleness(client, family="explore_rankings")
    validation = _global_snapshot_staleness(client, family="desirability_validation")
    source_checks += len(rankings.dependency_checks) + len(validation.dependency_checks)
    return plans, rankings, validation, source_checks


def _set_label(set_row: Dict[str, Any]) -> str:
    return f"{set_row.get('canonical_key') or set_row.get('id')} ({set_row.get('name')})"


def _record_stale(summary: RefreshSummary, result: FreshnessResult) -> None:
    if result.stale:
        summary.stale_snapshot_families.add(result.family)


def _maybe_rebuild_cards(client: Any, plan: SetRefreshPlan, *, commit: bool, summary: RefreshSummary) -> None:
    if not plan.cards.stale:
        return
    set_row = plan.set_row
    canonical_key = str(set_row.get("canonical_key") or set_row.get("id"))
    if not commit:
        summary.skipped_sets["cards"].append(f"{canonical_key}: dry-run {plan.cards.reason}")
        return
    try:
        row = build_cards_snapshot_row(set_row)
        upsert_row(client, "pokemon_set_cards_snapshot_latest", row, on_conflict="set_id", commit=True)
        summary.rebuilt_sets["cards"].append(canonical_key)
    except Exception as exc:
        logger.exception("failed cards snapshot refresh %s", _set_label(set_row))
        summary.failed_sets["cards"].append(f"{canonical_key}: {exc}")


def _maybe_rebuild_market(client: Any, plan: SetRefreshPlan, *, commit: bool, days: int, window: str, summary: RefreshSummary) -> None:
    if not plan.market_dashboard.stale:
        return
    set_row = plan.set_row
    canonical_key = str(set_row.get("canonical_key") or set_row.get("id"))
    if not commit:
        summary.skipped_sets["market_dashboard"].append(f"{canonical_key}: dry-run {plan.market_dashboard.reason}")
        return
    try:
        dashboard_row, history_rows = build_market_dashboard_snapshot_rows(set_row, days=days, window=window, client=client)
        upsert_rows(
            client,
            "pokemon_set_top_chase_card_daily_history",
            history_rows,
            on_conflict="set_id,snapshot_date,rank",
            commit=True,
        )
        upsert_row(
            client,
            "pokemon_set_market_dashboard_snapshot_latest",
            dashboard_row,
            on_conflict="set_id,window_key",
            commit=True,
        )
        summary.rebuilt_sets["market_dashboard"].append(canonical_key)
    except Exception as exc:
        logger.exception("failed market dashboard snapshot refresh %s", _set_label(set_row))
        summary.failed_sets["market_dashboard"].append(f"{canonical_key}: {exc}")


def _maybe_rebuild_rankings(client: Any, rankings: FreshnessResult, *, commit: bool, summary: RefreshSummary) -> None:
    if not rankings.stale:
        return
    if not commit:
        summary.global_skipped.append(f"explore_rankings: dry-run {rankings.reason}")
        return
    try:
        row = build_explore_rankings_snapshot_row()
        upsert_row(
            client,
            "pokemon_explore_rankings_snapshot_latest",
            row,
            on_conflict="tcg,scope",
            commit=True,
        )
        summary.global_rebuilt.append("explore_rankings")
    except Exception as exc:
        logger.exception("failed explore rankings snapshot refresh")
        summary.global_failed.append(f"explore_rankings: {exc}")


def _maybe_rebuild_set_page(
    client: Any,
    plan: SetRefreshPlan,
    *,
    rankings_updated_at: Optional[str],
    commit: bool,
    summary: RefreshSummary,
) -> None:
    rankings_rebuilt_after_set_page = bool(rankings_updated_at and _is_newer(rankings_updated_at, plan.set_page.snapshot_updated_at))
    needs_rebuild = plan.set_page.stale or plan.cards.stale or plan.market_dashboard.stale or rankings_rebuilt_after_set_page
    if not needs_rebuild:
        return
    set_row = plan.set_row
    canonical_key = str(set_row.get("canonical_key") or set_row.get("id"))
    if not commit:
        summary.skipped_sets["set_page"].append(f"{canonical_key}: dry-run dependency/set page stale")
        return
    try:
        row = build_set_page_snapshot_row(set_row, client=client)
        upsert_row(client, "pokemon_set_page_snapshot_latest", row, on_conflict="set_id", commit=True)
        summary.rebuilt_sets["set_page"].append(canonical_key)
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


def _verify_set_page(client: Any, set_row: Dict[str, Any], *, rankings_updated_at: Optional[str]) -> List[str]:
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
    sources = meta.get("sources") if isinstance(meta.get("sources"), dict) else {}
    warnings = list(meta.get("warnings") or [])
    problems: List[str] = []
    if len(payload.get("top_hits") or []) <= 0:
        problems.append(f"{canonical_key}: top_hits missing")
    if sources.get("simulation_input_cards") != "OK":
        problems.append(f"{canonical_key}: simulation_input_cards source={sources.get('simulation_input_cards')}")
    if not isinstance(meta.get("snapshotCompleteness") or meta.get("snapshot_completeness"), dict):
        problems.append(f"{canonical_key}: snapshotCompleteness missing")
    if _has_known_stale_warning(warnings) and _source_rows_exist_for_set_page(client, set_id):
        problems.append(f"{canonical_key}: stale warning remains")
    if rankings_updated_at and not _set_page_has_rank_fields(payload):
        problems.append(f"{canonical_key}: rank fields missing while rankings snapshot exists")

    set_page_updated_at = _to_text(row.get("updated_at"))
    embedded_rankings_updated_at = _extract_embedded_rankings_updated_at(payload)
    decision_signal_ranks = _extract_section_freshness(payload).get("decisionSignalRanks")
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


def _print_summary(summary: RefreshSummary) -> None:
    print("public snapshot refresh summary")
    print(f"source checks performed: {summary.source_checks_performed}")
    print(f"stale snapshot families detected: {', '.join(sorted(summary.stale_snapshot_families)) or 'none'}")
    print(f"global rebuilt: {', '.join(summary.global_rebuilt) or 'none'}")
    print(f"global skipped: {', '.join(summary.global_skipped) or 'none'}")
    print(f"global failed: {', '.join(summary.global_failed) or 'none'}")
    for family in ("cards", "market_dashboard", "set_page"):
        print(f"{family} rebuilt: {len(summary.rebuilt_sets[family])} {summary.rebuilt_sets[family][:20]}")
        print(f"{family} skipped: {len(summary.skipped_sets[family])} {summary.skipped_sets[family][:20]}")
        print(f"{family} failed: {len(summary.failed_sets[family])} {summary.failed_sets[family][:20]}")
    print(f"warnings remaining: {len(summary.warnings_remaining)}")
    for warning in summary.warnings_remaining[:20]:
        print(f"  {warning}")
    print(f"first 10 problem canonical keys: {summary.problem_canonical_keys[:10]}")


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    logging.getLogger("httpx").setLevel(logging.WARNING)
    args = build_parser().parse_args()
    if str(args.tcg or "").strip().lower() != "pokemon":
        raise SystemExit("Only --tcg pokemon is supported by this refresh script")

    commit = bool(args.commit)
    client = get_client()
    set_rows = _resolve_sets(client, set_id=args.set_id)
    plans, rankings, validation, source_checks = _build_plan(client, set_rows=set_rows, window=args.window)

    summary = RefreshSummary(source_checks_performed=source_checks)
    for plan in plans:
        _record_stale(summary, plan.cards)
        _record_stale(summary, plan.market_dashboard)
        _record_stale(summary, plan.set_page)
    _record_stale(summary, rankings)
    _record_stale(summary, validation)

    # Rebuild order: set cards, market dashboards, explore rankings, set pages, desirability validation.
    for plan in plans:
        _maybe_rebuild_cards(client, plan, commit=commit, summary=summary)
    for plan in plans:
        _maybe_rebuild_market(client, plan, commit=commit, days=args.days, window=args.window, summary=summary)

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

    validation_needed = validation.stale or rankings_needed or any(plan.set_page.stale for plan in plans)
    if validation_needed:
        summary.stale_snapshot_families.add("desirability_validation")
    if validation_needed:
        if commit:
            _build_validation_snapshot(client, commit=True, summary=summary)
        else:
            summary.global_skipped.append("desirability_validation: dry-run dependency/global snapshot stale")

    _verify_after_build(client, set_rows, summary)
    _print_summary(summary)

    stale_or_failed = bool(
        summary.warnings_remaining
        or summary.global_failed
        or any(summary.failed_sets[family] for family in summary.failed_sets)
        or (not commit and summary.stale_snapshot_families)
    )
    if args.strict and stale_or_failed:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
