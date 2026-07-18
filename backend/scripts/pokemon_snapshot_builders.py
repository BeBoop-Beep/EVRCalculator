from __future__ import annotations

import argparse
import logging
import time
from contextlib import contextmanager
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional
from uuid import UUID, uuid4

from dotenv import load_dotenv
from postgrest.types import ReturnMethod

from backend.db.clients.supabase_client import create_service_role_client
from backend.db.services.explore_page_service import (
    DEFAULT_TOP_HITS_LIMIT,
    get_explore_page_payload,
)
from backend.db.services.explore_rip_statistics_service import get_rip_statistics_targets_payload
from backend.db.services.pokemon_set_cards_service import get_pokemon_set_cards_payload
from backend.db.services.pokemon_card_market_delta_contract import (
    WINDOW_CONVENTION,
    calculate_pokemon_card_market_delta,
    utc_date_key,
)
from backend.db.services.data_service_health import is_transient_data_service_error
from backend.db.services.pokemon_public_snapshot_service import (
    enrich_cards_payload_with_desirability,
)
from backend.db.services.pokemon_set_market_service import (
    SET_VALUE_SCOPES,
    build_pokemon_set_card_movements_by_window_payload,
    get_pokemon_set_top_market_cards_payload,
    get_pokemon_set_value_history_payload,
)
from backend.desirability.set_validation import (
    build_opening_set_audit,
    is_opening_set_row,
)
from backend.scripts.set_value_scope_invariants import validate_histories_by_scope

logger = logging.getLogger(__name__)

DEFAULT_DASHBOARD_WINDOW = "365d"
DEFAULT_DASHBOARD_DAYS = 365
TOP_CHASE_HISTORY_SOURCE_WINDOW_DAYS = DEFAULT_DASHBOARD_DAYS
TOP_CHASE_NEAR_MINT_CONDITION_ID = "4f8d1181-670e-4aea-937c-4d98d2e531a6"
TOP_CHASE_HISTORY_SOURCE = "card_variant_price_observations"
DEFAULT_RANKINGS_LIMIT = 200
DEFAULT_UPSERT_BATCH_SIZE = 500
TOP_CHASE_HISTORY_FIELDS = {"priceHistory", "price_history"}
RIP_DESIRABILITY_COMPARISON_FIELDS = (
    "rip_score_without_desirability",
    "rip_score_with_desirability",
    "rip_score_delta",
    "rip_rank_without_desirability",
    "rip_rank_with_desirability",
    "rip_rank_delta",
    "desirability_component_score",
    "rip_desirability_impact_label",
    "rip_desirability_comparison_version",
    "relative_rip_core_score",
    "rip_core_rank",
    "rip_core_tier",
    "rip_core_interpretation",
    "rip_core_interpretation_label",
    "rip_core_interpretation_summary",
    "rip_core_interpretation_severity",
    "rip_presentation_normalization_version",
    "relative_pack_score_normalization_version",
    "relative_rip_core_score_normalization_version",
)

MARKET_MOVERS_WINDOWS_DAYS = {"1D": 1, "7D": 7, "30D": 30}
MARKET_MOVERS_COMPATIBILITY_WINDOW = "30D"
MOVEMENT_CONTRACT_VERSION = "pokemon_card_movement_v1"
CARD_PRICE_OBSERVATION_CHUNK_SIZE = 50
CARD_PRICE_OBSERVATION_PAGE_SIZE = 1000
CARD_MOVEMENT_LOOKBACK_DAYS = 45
CARD_MOVEMENT_MIN_SPAN_DAYS = {7: 3, 30: 14}
CARD_MOVEMENT_MAX_SPAN_DAYS = {7: 10, 30: 45}
CARD_MOVEMENT_MIN_CURRENT_PRICE = 1.0
CARD_MOVEMENT_MIN_ABSOLUTE_CHANGE = 0.25
CARD_MOVEMENT_MAX_ABSOLUTE_PERCENT = 300.0

TOP_HITS_WARNING_PATTERNS = (
    "top hits",
    "simulation_input_cards is failed",
    "simulation drivers unavailable",
    "simulation drivers are unavailable",
)
RANKINGS_STALE_THRESHOLD_SECONDS = 300
RANK_CONTEXT_FIELDS = (
    "pack_rank",
    "pack_tier",
    "profit_rank",
    "profit_tier",
    "safety_rank",
    "safety_tier",
    "desirability_rank",
    "desirability_tier",
    "stability_rank",
    "stability_tier",
)
EXPLORE_RIP_UNAVAILABLE_WARNING = "explore_rip_statistics_latest unavailable"
RANKINGS_STALE_WARNING = "rankings snapshot is stale relative to set page snapshot"


def load_backend_env() -> None:
    env_path = Path(__file__).resolve().parents[1] / ".env"
    if env_path.exists():
        load_dotenv(dotenv_path=env_path, override=False)
    else:
        load_dotenv(override=False)


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def first_non_empty(*values: Any) -> Optional[str]:
    for value in values:
        if value is None:
            continue
        text = str(value).strip()
        if text:
            return text
    return None


def parse_date_key(value: Any) -> Optional[str]:
    if isinstance(value, date) and not isinstance(value, datetime):
        return value.isoformat()
    text = first_non_empty(value)
    if not text:
        return None
    if len(text) >= 10 and text[4] == "-" and text[7] == "-":
        return text[:10]
    try:
        return datetime.fromisoformat(text.replace("Z", "+00:00")).date().isoformat()
    except ValueError:
        return None


def parse_datetime(value: Any) -> Optional[datetime]:
    text = first_non_empty(value)
    if not text:
        return None
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def to_optional_float(value: Any) -> Optional[float]:
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return None
    return parsed


def is_uuid_like(value: Any) -> bool:
    text = first_non_empty(value)
    if not text:
        return False
    try:
        UUID(text)
    except (TypeError, ValueError, AttributeError):
        return False
    return True


def resolve_set_row(client: Any, set_identifier: str) -> Dict[str, Any]:
    resolved = first_non_empty(set_identifier)
    if not resolved:
        raise ValueError("set_id is required")

    lookup_columns = ["canonical_key", "pokemon_api_set_id"]
    if is_uuid_like(resolved):
        lookup_columns.insert(0, "id")

    selected_columns = (
        "id,name,canonical_key,pokemon_api_set_id,release_date,logo_image_url,"
        "symbol_image_url,hero_image_url"
    )
    for column in lookup_columns:
        try:
            result = client.table("sets").select(selected_columns).eq(column, resolved).limit(1).execute()
        except Exception as exc:
            if is_transient_data_service_error(exc):
                raise
            logger.exception("set lookup failed field=%s value=%s", column, resolved)
            continue
        rows = list(result.data or [])
        if rows:
            return rows[0]

    raise ValueError(f"Pokemon set not found: {set_identifier}")


def list_pokemon_sets(client: Any) -> List[Dict[str, Any]]:
    columns = (
        "id,name,canonical_key,pokemon_api_set_id,release_date,logo_image_url,"
        "symbol_image_url,hero_image_url"
    )
    try:
        result = client.table("sets").select(columns).order("release_date", desc=True).execute()
    except Exception as exc:
        if is_transient_data_service_error(exc):
            raise
        logger.warning("ordered Pokemon set listing failed; retrying without server-side sort", exc_info=True)
        result = client.table("sets").select(columns).execute()
    return [row for row in (result.data or []) if row.get("id")]


def resolve_target_sets(client: Any, args: argparse.Namespace) -> List[Dict[str, Any]]:
    if args.all:
        return list_pokemon_sets(client)
    return [resolve_set_row(client, args.set_id)]


def add_target_set_args(parser: argparse.ArgumentParser) -> None:
    target_group = parser.add_mutually_exclusive_group(required=True)
    target_group.add_argument("--all", action="store_true", help="Build snapshots for all Pokemon sets")
    target_group.add_argument("--set-id", help="Build snapshots for one set id, canonical key, or Pokemon API set id")
    mode_group = parser.add_mutually_exclusive_group()
    mode_group.add_argument("--dry-run", action="store_true", help="Build and log without writing")
    mode_group.add_argument("--commit", action="store_true", help="Upsert snapshot rows")


def should_commit(args: argparse.Namespace) -> bool:
    return bool(args.commit)


def refresh_canonical_card_market_prices_for_set(
    client: Any,
    set_id: str,
    *,
    commit: bool,
) -> Optional[int]:
    """Refresh the authoritative canonical selected-price layer for one set.

    Snapshot builders must not infer checklist prices directly from raw
    observations.  This RPC keeps the canonical selection layer in the
    lineage before a Cards snapshot reads it.
    """
    if not commit:
        logger.info(
            "[dry-run] would refresh pokemon_canonical_card_market_prices_latest set_id=%s",
            set_id,
        )
        return None
    result = client.rpc(
        "refresh_pokemon_canonical_card_market_prices_latest_for_set",
        {"target_set_id": set_id},
    ).execute()
    data = getattr(result, "data", None)
    if isinstance(data, list):
        value = data[0] if data else 0
        if isinstance(value, dict):
            value = next(iter(value.values()), 0)
    else:
        value = data
    refreshed_rows = int(value or 0)
    logger.info(
        "refreshed pokemon_canonical_card_market_prices_latest set_id=%s rows=%s",
        set_id,
        refreshed_rows,
    )
    return refreshed_rows


def with_snapshot_meta(
    payload: Dict[str, Any],
    *,
    snapshot_type: str,
    built_at: str,
    generation_id: Optional[str] = None,
    movement_as_of_date: Optional[str] = None,
) -> Dict[str, Any]:
    meta = dict(payload.get("meta") or {})
    snapshot_meta = dict(meta.get("snapshot") or {})
    snapshot_meta.update(
        {
            "type": snapshot_type,
            "builtAt": built_at,
            "source": "pokemon_snapshot_builders",
        }
    )
    if generation_id:
        snapshot_meta.update(
            {
                "movementContractVersion": MOVEMENT_CONTRACT_VERSION,
                "windowConvention": WINDOW_CONVENTION,
                "movementAsOfDate": movement_as_of_date,
                # Canonical market as-of date for every market-driven surface
                # served from this generation. Same value as movementAsOfDate;
                # exposed under the explicit shared-contract name.
                "marketAsOfDate": movement_as_of_date,
                "generationId": generation_id,
            }
        )
    meta["snapshot"] = snapshot_meta
    return {**payload, "meta": meta}


def _summary_subset(summary: Dict[str, Any], keys: Iterable[str]) -> Dict[str, Any]:
    return {key: summary.get(key) for key in keys if key in summary}


def _set_identity_tokens(*rows: Dict[str, Any]) -> set[str]:
    tokens: set[str] = set()
    identity_keys = (
        "id",
        "set_id",
        "target_id",
        "slug",
        "canonical_key",
        "pokemon_api_set_id",
    )
    for row in rows:
        if not isinstance(row, dict):
            continue
        for key in identity_keys:
            token = first_non_empty(row.get(key))
            if token:
                tokens.add(token.lower())
    return tokens


def _find_matching_rankings_target(
    *,
    set_id: str,
    set_row: Dict[str, Any],
    payload: Dict[str, Any],
    target_rows: Iterable[Dict[str, Any]],
) -> Optional[Dict[str, Any]]:
    payload_set = payload.get("set") if isinstance(payload.get("set"), dict) else {}
    expected_tokens = _set_identity_tokens(
        {"id": set_id, "set_id": set_id, "target_id": set_id},
        set_row,
        payload_set,
    )
    for target in target_rows:
        if not isinstance(target, dict):
            continue
        target_tokens = _set_identity_tokens(target)
        if expected_tokens.intersection(target_tokens):
            return target
    return None


def _comparison_fields_from_target(target: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    if not isinstance(target, dict):
        return {}
    return {key: target.get(key) for key in RIP_DESIRABILITY_COMPARISON_FIELDS if key in target}


def _target_rank_context_fields(target: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    if not isinstance(target, dict):
        return {}
    summary = target.get("summary") if isinstance(target.get("summary"), dict) else {}
    fields: Dict[str, Any] = {}
    for key in RANK_CONTEXT_FIELDS:
        if key in target and target.get(key) is not None:
            fields[key] = target.get(key)
        elif key in summary and summary.get(key) is not None:
            fields[key] = summary.get(key)
    return fields


def _merge_canonical_rip_contract_into_set_payload(
    *,
    payload: Dict[str, Any],
    set_id: str,
    set_row: Dict[str, Any],
    rankings_payload: Dict[str, Any],
) -> Dict[str, Any]:
    """Copy the canonical public contract from the rankings target into the set page.

    The same backend bundle powers both surfaces BY CONSTRUCTION: these objects
    are lifted verbatim from the row ``get_rip_statistics_targets_payload``
    ranked, so the Explore leaderboard and the set Insights page cannot disagree
    about a score, a rank, or a denominator - they are reading one object.

    Nothing is recomputed here, and the legacy summary fields are left exactly
    as they were: they remain for backward compatibility and are listed in the
    payload's deprecation metadata.
    """
    target_rows = rankings_payload.get("targets") or []
    matching_target = _find_matching_rankings_target(
        set_id=set_id,
        set_row=set_row,
        payload=payload,
        target_rows=target_rows,
    )
    if not isinstance(matching_target, dict):
        return payload

    next_payload = dict(payload)
    for key in (
        "rip",
        "ripCore",
        # Compact public v4 contract (absoluteScore/relativeScore/rank/
        # rankedSetCount per block; CA7-gated Overall). Lifted verbatim so the
        # set page and Explore read one object, never two that can disagree.
        "publicRipContractV4",
        "openingExperience",
        "publicAnalyticsStatus",
        # The authoritative desirability score and the two coverage axes. The
        # set page renders Set Desirability from `universalSetDesirability`
        # directly, so omitting it here left the section with nothing to read
        # even when the rankings target carried a full score.
        "universalSetDesirability",
        "desirabilityCoverage",
        "simulationCoverage",
    ):
        value = matching_target.get(key)
        if value is not None:
            next_payload[key] = value
    cohort = (rankings_payload.get("meta") or {}).get("publicAnalyticsCohort")
    if isinstance(cohort, dict):
        next_payload["publicAnalyticsCohort"] = cohort
    return next_payload


def _merge_rip_desirability_comparison_into_set_payload(
    *,
    payload: Dict[str, Any],
    set_id: str,
    set_row: Dict[str, Any],
    target_rows: Iterable[Dict[str, Any]],
) -> Dict[str, Any]:
    matching_target = _find_matching_rankings_target(
        set_id=set_id,
        set_row=set_row,
        payload=payload,
        target_rows=target_rows,
    )
    comparison_fields = _comparison_fields_from_target(matching_target)
    if not comparison_fields:
        return payload

    next_payload = dict(payload)
    summary = dict(next_payload.get("summary") or {})
    summary.update(comparison_fields)
    next_payload["summary"] = summary

    set_payload = dict(next_payload.get("set") or {})
    set_payload.update(comparison_fields)
    next_payload["set"] = set_payload
    return next_payload


def _merge_rank_context_into_set_payload(
    *,
    payload: Dict[str, Any],
    set_id: str,
    set_row: Dict[str, Any],
    target_rows: Iterable[Dict[str, Any]],
) -> Dict[str, Any]:
    matching_target = _find_matching_rankings_target(
        set_id=set_id,
        set_row=set_row,
        payload=payload,
        target_rows=target_rows,
    )
    rank_fields = _target_rank_context_fields(matching_target)
    if not rank_fields:
        return payload

    next_payload = dict(payload)
    summary = dict(next_payload.get("summary") or {})
    set_payload = dict(next_payload.get("set") or {})
    for key, value in rank_fields.items():
        if summary.get(key) is None:
            summary[key] = value
        if set_payload.get(key) is None:
            set_payload[key] = value
    next_payload["summary"] = summary
    next_payload["set"] = set_payload
    return next_payload


def _snapshot_payload_run_id(payload: Dict[str, Any]) -> Optional[str]:
    summary = payload.get("summary") if isinstance(payload.get("summary"), dict) else {}
    meta = payload.get("meta") if isinstance(payload.get("meta"), dict) else {}
    request = meta.get("request") if isinstance(meta.get("request"), dict) else {}
    return first_non_empty(
        summary.get("calculation_run_id"),
        summary.get("run_id"),
        request.get("calculation_run_id"),
        payload.get("calculation_run_id"),
    )


def _clean_top_hits_warnings(warnings: Iterable[Any]) -> List[Any]:
    cleaned: List[Any] = []
    for warning in warnings or []:
        warning_text = str(warning).lower()
        if any(pattern in warning_text for pattern in TOP_HITS_WARNING_PATTERNS):
            continue
        cleaned.append(warning)
    return cleaned


def _clean_explore_rip_fallback_warnings(warnings: Iterable[Any]) -> List[Any]:
    return [
        warning
        for warning in warnings or []
        if EXPLORE_RIP_UNAVAILABLE_WARNING not in str(warning).lower()
    ]


def _append_debug_warning(meta: Dict[str, Any], warning: str) -> None:
    debug_warnings = list(meta.get("debugWarnings") or meta.get("debug_warnings") or [])
    if warning not in debug_warnings:
        debug_warnings.append(warning)
    meta["debugWarnings"] = debug_warnings
    meta["debug_warnings"] = debug_warnings


def _load_top_hits_from_view(client: Any, *, run_id: str, limit: int) -> List[Dict[str, Any]]:
    result = (
        client.table("simulation_input_cards_with_near_mint_price")
        .select("card_id,card_variant_id,card_name,rarity_bucket,ev_contribution,current_near_mint_price")
        .eq("calculation_run_id", run_id)
        .order("ev_contribution", desc=True)
        .limit(limit)
        .execute()
    )
    return list(result.data or [])


def _load_top_hits_from_input_cards(client: Any, *, run_id: str, limit: int) -> List[Dict[str, Any]]:
    result = (
        client.table("simulation_input_cards")
        .select("card_id,card_variant_id,card_name,rarity_bucket,ev_contribution,price_used,condition_id")
        .eq("calculation_run_id", run_id)
        .order("ev_contribution", desc=True)
        .limit(limit)
        .execute()
    )
    return list(result.data or [])


def _top_hit_image_fields(
    variant_row: Optional[Dict[str, Any]],
    card_row: Optional[Dict[str, Any]],
) -> Dict[str, Optional[str]]:
    variant_small = first_non_empty((variant_row or {}).get("image_small_url"))
    card_small = first_non_empty((card_row or {}).get("image_small_url"))
    variant_large = first_non_empty((variant_row or {}).get("image_large_url"))
    card_large = first_non_empty((card_row or {}).get("image_large_url"))
    return {
        "image_url": variant_small or card_small or variant_large or card_large,
        "image_small_url": variant_small or card_small,
        "image_large_url": variant_large or card_large,
    }


def _enrich_snapshot_top_hits_with_images(client: Any, top_hits: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    variant_ids = sorted(
        {
            str(hit.get("card_variant_id"))
            for hit in top_hits
            if hit.get("card_variant_id") is not None
        }
    )
    card_ids = sorted(
        {
            str(hit.get("card_id"))
            for hit in top_hits
            if hit.get("card_id") is not None
        }
    )

    try:
        variant_rows = (
            client.table("card_variants")
            .select("id,card_id,image_small_url,image_large_url")
            .in_("id", variant_ids)
            .execute()
            .data
            if variant_ids
            else []
        )
        variant_lookup = {
            str(row.get("id")): row
            for row in (variant_rows or [])
            if row.get("id") is not None
        }
        derived_card_ids = {
            str(row.get("card_id"))
            for row in variant_lookup.values()
            if row.get("card_id") is not None
        }
        all_card_ids = sorted(set(card_ids) | derived_card_ids)
        card_rows = (
            client.table("cards")
            .select("id,image_small_url,image_large_url")
            .in_("id", all_card_ids)
            .execute()
            .data
            if all_card_ids
            else []
        )
    except Exception as exc:
        if is_transient_data_service_error(exc):
            raise
        logger.warning("top hits snapshot completion image enrichment failed", exc_info=True)
        return top_hits

    card_lookup = {
        str(row.get("id")): row
        for row in (card_rows or [])
        if row.get("id") is not None
    }

    enriched_hits: List[Dict[str, Any]] = []
    for hit in top_hits:
        variant_id = first_non_empty(hit.get("card_variant_id"))
        card_id = first_non_empty(hit.get("card_id"))
        variant_row = variant_lookup.get(variant_id or "")
        card_row = card_lookup.get(card_id or "")
        if card_row is None and variant_row and variant_row.get("card_id") is not None:
            card_row = card_lookup.get(str(variant_row.get("card_id")))
        enriched_hits.append({**hit, **_top_hit_image_fields(variant_row, card_row)})
    return enriched_hits


def _complete_snapshot_top_hits(
    payload: Dict[str, Any],
    *,
    set_id: str,
    client: Optional[Any] = None,
    limit: int = DEFAULT_TOP_HITS_LIMIT,
) -> Dict[str, Any]:
    if not isinstance(payload, dict):
        return payload

    if payload.get("top_hits"):
        meta = dict(payload.get("meta") or {})
        meta["warnings"] = _clean_top_hits_warnings(meta.get("warnings") or [])
        return {**payload, "meta": meta}

    meta = dict(payload.get("meta") or {})
    sources = dict(meta.get("sources") or {})
    if sources.get("simulation_input_cards") not in {"FAILED", "NO_ROWS", None, "MISSING"}:
        return payload

    run_id = _snapshot_payload_run_id(payload)
    if not run_id:
        return payload

    resolved_client = client or get_client()
    source = "simulation_input_cards_with_near_mint_price"
    view_failure_detail: Optional[str] = None
    try:
        top_hits = _load_top_hits_from_view(resolved_client, run_id=run_id, limit=limit)
    except Exception as exc:
        if is_transient_data_service_error(exc):
            raise
        logger.warning("top hits snapshot completion view query failed set_id=%s run_id=%s", set_id, run_id, exc_info=True)
        view_failure_detail = "simulation_input_cards_with_near_mint_price query failed during snapshot completion"
        top_hits = []

    if not top_hits:
        source = "simulation_input_cards"
        try:
            top_hits = _load_top_hits_from_input_cards(resolved_client, run_id=run_id, limit=limit)
        except Exception as exc:
            if is_transient_data_service_error(exc):
                raise
            logger.warning("top hits snapshot completion input query failed set_id=%s run_id=%s", set_id, run_id, exc_info=True)
            top_hits = []

    if not top_hits:
        return payload

    enriched_hits = _enrich_snapshot_top_hits_with_images(resolved_client, top_hits)
    sources["simulation_input_cards"] = "OK"
    sources["simulation_input_cards_snapshot_completion"] = source
    meta["sources"] = sources
    meta["warnings"] = _clean_top_hits_warnings(meta.get("warnings") or [])
    if view_failure_detail and source == "simulation_input_cards":
        _append_debug_warning(meta, view_failure_detail)
    meta.pop("simulationDriversRepairSkipped", None)
    return {
        **payload,
        "top_hits": enriched_hits,
        "meta": meta,
    }


def _first_row(client: Any, table_name: str, configure_query) -> Optional[Dict[str, Any]]:
    try:
        result = configure_query(client.table(table_name)).limit(1).execute()
    except Exception as exc:
        if is_transient_data_service_error(exc):
            raise
        logger.warning("snapshot diagnostic query failed table=%s", table_name, exc_info=True)
        return None
    rows = list(result.data or [])
    return rows[0] if rows else None


def _count_rows(client: Any, table_name: str, *, field: str, value: str) -> Optional[int]:
    try:
        result = client.table(table_name).select(field).eq(field, value).execute()
    except Exception as exc:
        if is_transient_data_service_error(exc):
            raise
        logger.warning("snapshot diagnostic count failed table=%s field=%s", table_name, field, exc_info=True)
        return None
    return len(list(result.data or []))


def _load_rankings_snapshot_updated_at(client: Any) -> Optional[str]:
    row = _first_row(
        client,
        "pokemon_explore_rankings_snapshot_latest",
        lambda query: query.select("updated_at").eq("tcg", "pokemon").eq("scope", "rip-statistics"),
    )
    return first_non_empty((row or {}).get("updated_at"))


def _load_cards_snapshot_payload(client: Any, set_id: str) -> Optional[Dict[str, Any]]:
    row = _first_row(
        client,
        "pokemon_set_cards_snapshot_latest",
        lambda query: query.select("set_id,payload_json,updated_at").eq("set_id", set_id),
    )
    payload = (row or {}).get("payload_json")
    return payload if isinstance(payload, dict) else None


def _load_existing_set_page_snapshot_row(client: Any, set_id: str) -> Optional[Dict[str, Any]]:
    return _first_row(
        client,
        "pokemon_set_page_snapshot_latest",
        lambda query: query.select("set_id,payload_json,updated_at,source_updated_at,as_of").eq("set_id", set_id),
    )


def _valid_list_section(payload: Dict[str, Any], *keys: str) -> bool:
    return any(isinstance(payload.get(key), list) and len(payload.get(key) or []) > 0 for key in keys)


def _valid_dict_section(payload: Dict[str, Any], *keys: str) -> bool:
    return any(isinstance(payload.get(key), dict) and len(payload.get(key) or {}) > 0 for key in keys)


def _rank_context_from_payload(payload: Dict[str, Any]) -> Dict[str, Any]:
    summary = payload.get("summary") if isinstance(payload.get("summary"), dict) else {}
    set_payload = payload.get("set") if isinstance(payload.get("set"), dict) else {}
    rank_context: Dict[str, Any] = {}
    for key in RANK_CONTEXT_FIELDS:
        value = summary.get(key)
        if value is None:
            value = set_payload.get(key)
        if value is not None:
            rank_context[key] = value
    return rank_context


def _snapshot_built_at(payload: Dict[str, Any]) -> Optional[str]:
    meta = payload.get("meta") if isinstance(payload.get("meta"), dict) else {}
    snapshot = meta.get("snapshot") if isinstance(meta.get("snapshot"), dict) else {}
    return first_non_empty(snapshot.get("builtAt"), snapshot.get("built_at"))


def _section_data_as_of(payload: Dict[str, Any], row: Optional[Dict[str, Any]] = None) -> Optional[str]:
    summary = payload.get("summary") if isinstance(payload.get("summary"), dict) else {}
    meta = payload.get("meta") if isinstance(payload.get("meta"), dict) else {}
    return first_non_empty(
        summary.get("run_at"),
        summary.get("as_of"),
        meta.get("asOfDate"),
        meta.get("as_of_date"),
        (row or {}).get("source_updated_at"),
        (row or {}).get("as_of"),
        _snapshot_built_at(payload),
        (row or {}).get("updated_at"),
    )


def _existing_section_freshness(payload: Dict[str, Any], section_key: str) -> Dict[str, Any]:
    meta = payload.get("meta") if isinstance(payload.get("meta"), dict) else {}
    freshness = meta.get("sectionFreshness") if isinstance(meta.get("sectionFreshness"), dict) else {}
    section = freshness.get(section_key)
    return dict(section) if isinstance(section, dict) else {}


def _section_source(payload: Dict[str, Any], *, fallback: str, source_keys: Iterable[str] = ()) -> str:
    meta = payload.get("meta") if isinstance(payload.get("meta"), dict) else {}
    sources = meta.get("sources") if isinstance(meta.get("sources"), dict) else {}
    run_id = _snapshot_payload_run_id(payload)
    source = first_non_empty(
        *[
            candidate
            for candidate in tuple(sources.get(key) for key in source_keys) + (fallback,)
            if str(candidate or "").upper() not in {"OK", "FAILED", "NO_ROWS", "MISSING", "UNAVAILABLE_FALLBACK"}
        ]
    )
    return f"{source}/{run_id}" if run_id and source else (source or fallback)


def _fresh_section_status(
    payload: Dict[str, Any],
    *,
    section_key: str,
    built_at: str,
    source: str,
    row: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    return {
        "status": "fresh",
        "dataAsOf": _section_data_as_of(payload, row) or built_at,
        "lastSuccessfulAt": built_at,
        "attemptedAt": built_at,
        "source": source,
    }


def _stale_section_status(
    old_payload: Dict[str, Any],
    *,
    section_key: str,
    attempted_at: str,
    source: str,
    reason: str,
    old_row: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    previous = _existing_section_freshness(old_payload, section_key)
    data_as_of = first_non_empty(previous.get("dataAsOf"), _section_data_as_of(old_payload, old_row))
    last_successful_at = first_non_empty(previous.get("lastSuccessfulAt"), _snapshot_built_at(old_payload), (old_row or {}).get("updated_at"))
    previous_source = first_non_empty(previous.get("source"), source)
    return {
        "status": "stale",
        "dataAsOf": data_as_of,
        "lastSuccessfulAt": last_successful_at,
        "attemptedAt": attempted_at,
        "source": previous_source or source,
        "reason": reason,
    }


def _missing_section_status(*, built_at: str, source: str, reason: str) -> Dict[str, Any]:
    return {
        "status": "missing",
        "dataAsOf": None,
        "lastSuccessfulAt": None,
        "attemptedAt": built_at,
        "source": source,
        "reason": reason,
    }


def _merge_last_known_good_snapshot_sections(
    payload: Dict[str, Any],
    *,
    existing_row: Optional[Dict[str, Any]],
    built_at: str,
) -> Dict[str, Any]:
    if not isinstance(payload, dict):
        return payload

    old_payload = (existing_row or {}).get("payload_json")
    if not isinstance(old_payload, dict):
        old_payload = {}

    next_payload = dict(payload)
    meta = dict(next_payload.get("meta") or {})
    section_freshness = dict(meta.get("sectionFreshness") or {})

    new_top_hits_valid = _valid_list_section(next_payload, "top_hits", "topHits")
    old_top_hits_valid = _valid_list_section(old_payload, "top_hits", "topHits")
    simulation_source = _section_source(
        next_payload,
        fallback="simulation_input_cards",
        source_keys=("simulation_input_cards_snapshot_completion",),
    )
    if new_top_hits_valid:
        section_freshness["simulationDrivers"] = _fresh_section_status(
            next_payload,
            section_key="simulationDrivers",
            built_at=built_at,
            source=simulation_source,
        )
    elif old_top_hits_valid:
        old_hits = old_payload.get("top_hits") if isinstance(old_payload.get("top_hits"), list) else old_payload.get("topHits")
        next_payload["top_hits"] = list(old_hits or [])
        section_freshness["simulationDrivers"] = _stale_section_status(
            old_payload,
            section_key="simulationDrivers",
            attempted_at=built_at,
            source=_section_source(
                old_payload,
                fallback="simulation_input_cards",
                source_keys=("simulation_input_cards_snapshot_completion",),
            ),
            reason="current snapshot build did not include valid top_hits",
            old_row=existing_row,
        )
    else:
        section_freshness["simulationDrivers"] = _missing_section_status(
            built_at=built_at,
            source=simulation_source,
            reason="no valid top_hits have been captured yet",
        )

    new_rank_context = _rank_context_from_payload(next_payload)
    old_rank_context = _rank_context_from_payload(old_payload)
    current_summary = next_payload.get("summary") if isinstance(next_payload.get("summary"), dict) else {}
    current_set_payload = next_payload.get("set") if isinstance(next_payload.get("set"), dict) else {}
    missing_rank_keys = [key for key in RANK_CONTEXT_FIELDS if current_summary.get(key) is None and current_set_payload.get(key) is None]
    copied_rank_context = {key: old_rank_context[key] for key in missing_rank_keys if key in old_rank_context}
    if copied_rank_context:
        summary = dict(next_payload.get("summary") or {})
        set_payload = dict(next_payload.get("set") or {})
        for key, value in copied_rank_context.items():
            if summary.get(key) is None:
                summary[key] = value
            if set_payload.get(key) is None:
                set_payload[key] = value
        next_payload["summary"] = summary
        next_payload["set"] = set_payload
        section_freshness["decisionSignalRanks"] = _stale_section_status(
            old_payload,
            section_key="decisionSignalRanks",
            attempted_at=built_at,
            source=_section_source(old_payload, fallback="pokemon_explore_rankings_snapshot_latest"),
            reason="current snapshot build did not include complete rank fields",
            old_row=existing_row,
        )
    elif new_rank_context:
        section_freshness["decisionSignalRanks"] = _fresh_section_status(
            next_payload,
            section_key="decisionSignalRanks",
            built_at=built_at,
            source=_section_source(next_payload, fallback="pokemon_explore_rankings_snapshot_latest"),
        )
    else:
        section_freshness["decisionSignalRanks"] = _missing_section_status(
            built_at=built_at,
            source=_section_source(next_payload, fallback="pokemon_explore_rankings_snapshot_latest"),
            reason="no valid rank fields have been captured yet",
        )

    new_card_appeal_valid = _valid_dict_section(next_payload, "cardAppealMarketPriceCorrelation", "card_appeal_market_price_correlation")
    old_card_appeal_valid = _valid_dict_section(old_payload, "cardAppealMarketPriceCorrelation", "card_appeal_market_price_correlation")
    card_appeal_source = _section_source(
        next_payload,
        fallback="pokemon_set_cards_snapshot_latest",
        source_keys=("card_appeal_validation_snapshot",),
    )
    if new_card_appeal_valid:
        section_freshness["cardAppealValidation"] = _fresh_section_status(
            next_payload,
            section_key="cardAppealValidation",
            built_at=built_at,
            source=card_appeal_source,
        )
    elif old_card_appeal_valid:
        correlation = old_payload.get("cardAppealMarketPriceCorrelation") or old_payload.get("card_appeal_market_price_correlation")
        next_payload["cardAppealMarketPriceCorrelation"] = correlation
        next_payload["card_appeal_market_price_correlation"] = correlation
        old_card_validation = old_payload.get("cardDesirabilityValidation") or old_payload.get("card_desirability_validation")
        if isinstance(old_card_validation, dict):
            next_payload["cardDesirabilityValidation"] = old_card_validation
            next_payload["card_desirability_validation"] = old_card_validation
        section_freshness["cardAppealValidation"] = _stale_section_status(
            old_payload,
            section_key="cardAppealValidation",
            attempted_at=built_at,
            source=_section_source(
                old_payload,
                fallback="pokemon_set_cards_snapshot_latest",
                source_keys=("card_appeal_validation_snapshot",),
            ),
            reason="current snapshot build did not include card appeal market-price validation",
            old_row=existing_row,
        )
    else:
        section_freshness["cardAppealValidation"] = _missing_section_status(
            built_at=built_at,
            source=card_appeal_source,
            reason="no valid card appeal market-price validation has been captured yet",
        )

    # desirabilityValidation is RETIRED, not merely absent. The carry-forward
    # branch that used to live here would resurrect the legacy rank-alignment
    # payload from the previous snapshot row on every rebuild, so the section
    # could never actually die. New snapshots drop the keys; the freshness entry
    # says why, so a staleness audit reads "retired" instead of "broken".
    next_payload.pop("desirabilityValidation", None)
    next_payload.pop("desirability_validation", None)
    section_freshness["desirabilityValidation"] = {
        "status": "retired",
        "builtAt": built_at,
        "reason": (
            "The Desirability Evidence section was replaced by Opening Experience "
            "(Collector Appeal); its validation payload is no longer produced."
        ),
    }

    meta["sectionFreshness"] = section_freshness
    next_payload["meta"] = meta
    return next_payload


def _merge_card_appeal_snapshot_payload(
    payload: Dict[str, Any],
    *,
    set_id: str,
    client: Optional[Any],
) -> Dict[str, Any]:
    if client is None:
        return payload
    cards_payload = _load_cards_snapshot_payload(client, set_id)
    if not cards_payload:
        return payload

    correlation = (
        cards_payload.get("cardAppealMarketPriceCorrelation")
        or cards_payload.get("card_appeal_market_price_correlation")
    )
    card_validation = cards_payload.get("cardDesirabilityValidation") or cards_payload.get("card_desirability_validation")
    if not isinstance(correlation, dict) and not isinstance(card_validation, dict):
        return payload

    next_payload = dict(payload)
    meta = dict(next_payload.get("meta") or {})
    sources = dict(meta.get("sources") or {})
    sources["card_appeal_validation_snapshot"] = "pokemon_set_cards_snapshot_latest"
    meta["sources"] = sources
    if isinstance(correlation, dict):
        next_payload["cardAppealMarketPriceCorrelation"] = correlation
        next_payload["card_appeal_market_price_correlation"] = correlation
    if isinstance(card_validation, dict):
        next_payload["cardDesirabilityValidation"] = card_validation
        next_payload["card_desirability_validation"] = card_validation
    next_payload["meta"] = meta
    return next_payload


def _is_rankings_snapshot_stale(*, built_at: str, rankings_updated_at: Optional[str]) -> bool:
    built_dt = parse_datetime(built_at)
    rankings_dt = parse_datetime(rankings_updated_at)
    if built_dt is None or rankings_dt is None:
        return False
    return (built_dt - rankings_dt).total_seconds() > RANKINGS_STALE_THRESHOLD_SECONDS


def _load_snapshot_completeness_diagnostics(
    *,
    client: Any,
    set_id: str,
    payload: Dict[str, Any],
    built_at: str,
) -> Dict[str, Any]:
    explore_row = _first_row(
        client,
        "explore_rip_statistics_latest",
        lambda query: query.select("set_id,calculation_run_id,run_at").eq("set_id", set_id),
    )
    latest_row = _first_row(
        client,
        "simulation_latest_by_target",
        lambda query: query.select("target_type,target_id,calculation_run_id,run_at").eq("target_type", "set").eq("target_id", set_id),
    )
    run_id = (
        _snapshot_payload_run_id(payload)
        or first_non_empty((explore_row or {}).get("calculation_run_id"))
        or first_non_empty((latest_row or {}).get("calculation_run_id"))
    )
    rankings_updated_at = _load_rankings_snapshot_updated_at(client)
    input_count = _count_rows(client, "simulation_input_cards", field="calculation_run_id", value=run_id) if run_id else None
    near_mint_count = (
        _count_rows(client, "simulation_input_cards_with_near_mint_price", field="calculation_run_id", value=run_id)
        if run_id
        else None
    )
    warnings = list((payload.get("meta") or {}).get("warnings") or [])
    return {
        "set_page_snapshot_built_at": built_at,
        "explore_rankings_snapshot_updated_at": rankings_updated_at,
        "explore_rip_statistics_latest": {
            "availability": "OK" if explore_row else "NO_ROW",
            "run_at": first_non_empty((explore_row or {}).get("run_at")),
            "calculation_run_id": first_non_empty((explore_row or {}).get("calculation_run_id")),
        },
        "simulation_latest_by_target": {
            "availability": "OK" if latest_row else "NO_ROW",
            "run_at": first_non_empty((latest_row or {}).get("run_at")),
            "calculation_run_id": first_non_empty((latest_row or {}).get("calculation_run_id")),
        },
        "simulation_input_cards_row_count": input_count,
        "simulation_input_cards_with_near_mint_price_row_count": near_mint_count,
        "top_hits_included_count": len(payload.get("top_hits") or []),
        "warnings_after_repair": warnings,
    }


def _finalize_snapshot_completeness(
    payload: Dict[str, Any],
    *,
    set_id: str,
    client: Optional[Any],
    built_at: str,
) -> Dict[str, Any]:
    if client is None:
        return payload

    diagnostics = _load_snapshot_completeness_diagnostics(
        client=client,
        set_id=set_id,
        payload=payload,
        built_at=built_at,
    )
    meta = dict(payload.get("meta") or {})
    warnings = list(meta.get("warnings") or [])
    summary = payload.get("summary") if isinstance(payload.get("summary"), dict) else {}
    decision_signal_fields = (
        "pack_rank",
        "profit_rank",
        "safety_rank",
        "desirability_rank",
        "stability_rank",
    )
    has_decision_signal_ranks = any(summary.get(field) is not None for field in decision_signal_fields)
    section_freshness = meta.get("sectionFreshness") if isinstance(meta.get("sectionFreshness"), dict) else {}
    decision_signal_freshness = section_freshness.get("decisionSignalRanks") if isinstance(section_freshness.get("decisionSignalRanks"), dict) else {}
    freshness_status = first_non_empty(decision_signal_freshness.get("status"))
    debug_warnings = list(diagnostics.get("debugWarnings") or diagnostics.get("debug_warnings") or [])
    if diagnostics["explore_rip_statistics_latest"]["availability"] == "OK":
        warnings = _clean_explore_rip_fallback_warnings(warnings)
    rankings_stale = _is_rankings_snapshot_stale(
        built_at=built_at,
        rankings_updated_at=diagnostics.get("explore_rankings_snapshot_updated_at"),
    )
    if rankings_stale:
        if has_decision_signal_ranks and freshness_status in {"fresh", "stale"}:
            if RANKINGS_STALE_WARNING not in debug_warnings:
                debug_warnings.append(RANKINGS_STALE_WARNING)
        elif RANKINGS_STALE_WARNING not in warnings:
            warnings.append(RANKINGS_STALE_WARNING)

    diagnostics["warnings_after_repair"] = warnings
    diagnostics["debugWarnings"] = debug_warnings
    diagnostics["debug_warnings"] = debug_warnings
    meta["warnings"] = warnings
    if debug_warnings:
        meta["debugWarnings"] = debug_warnings
        meta["debug_warnings"] = debug_warnings
    meta["snapshotCompleteness"] = diagnostics
    meta["snapshot_completeness"] = diagnostics
    return {**payload, "meta": meta}


def build_set_page_snapshot_row(set_row: Dict[str, Any], *, client: Optional[Any] = None) -> Dict[str, Any]:
    built_at = utc_now_iso()
    set_id = str(set_row["id"])
    payload = get_explore_page_payload("set", set_id)
    payload = _complete_snapshot_top_hits(payload, set_id=set_id, client=client)
    try:
        rankings_payload = get_rip_statistics_targets_payload(limit=DEFAULT_RANKINGS_LIMIT)
        target_rows = rankings_payload.get("targets") or []
        payload = _merge_rip_desirability_comparison_into_set_payload(
            payload=payload,
            set_id=set_id,
            set_row=set_row,
            target_rows=target_rows,
        )
        payload = _merge_rank_context_into_set_payload(
            payload=payload,
            set_id=set_id,
            set_row=set_row,
            target_rows=target_rows,
        )
        payload = _merge_canonical_rip_contract_into_set_payload(
            payload=payload,
            set_id=set_id,
            set_row=set_row,
            rankings_payload=rankings_payload,
        )
        # The legacy desirabilityValidation payload (rank-alignment bars,
        # set-value scatter, market agree/conflict verdicts) is no longer
        # produced: its only consumer was the public Desirability Evidence
        # section, which the Opening Experience section replaced. Pure Roster
        # Desirability is price-independent by construction, so validating it
        # against set value was never the right proof for the construct.
        # backend/desirability/set_validation.py remains for research use.
    except Exception as exc:
        if is_transient_data_service_error(exc):
            raise
        logger.warning("canonical RIP contract merge failed set_id=%s", set_id, exc_info=True)
        meta = dict(payload.get("meta") or {})
        warnings = list(meta.get("warnings") or [])
        warnings.append("Canonical RIP contract could not be merged into this snapshot.")
        meta["warnings"] = warnings
        payload["meta"] = meta
    payload = _merge_card_appeal_snapshot_payload(payload, set_id=set_id, client=client)
    payload = with_snapshot_meta(payload, snapshot_type="pokemon_set_page", built_at=built_at)
    existing_row = _load_existing_set_page_snapshot_row(client, set_id) if client is not None else None
    payload = _merge_last_known_good_snapshot_sections(payload, existing_row=existing_row, built_at=built_at)
    payload = _finalize_snapshot_completeness(payload, set_id=set_id, client=client, built_at=built_at)
    summary = payload.get("summary") if isinstance(payload.get("summary"), dict) else {}

    set_identity = {
        "id": set_id,
        "name": set_row.get("name"),
        "slug": set_row.get("canonical_key"),
        "pokemon_api_set_id": set_row.get("pokemon_api_set_id"),
        "release_date": set_row.get("release_date"),
        "logo_image_url": set_row.get("logo_image_url"),
        "symbol_image_url": set_row.get("symbol_image_url"),
        "hero_image_url": set_row.get("hero_image_url"),
    }
    title_card = {
        **set_identity,
        **_summary_subset(
            summary,
            (
                "pack_score",
                "pack_tier",
                "pack_rank",
                "pack_cost",
                "mean_value",
                "median_value",
                "prob_profit",
                "prob_big_hit",
                "p95_value_to_cost_ratio",
                "p99_value_to_cost_ratio",
            ),
        ),
    }
    rip_summary = _summary_subset(
        summary,
        (
            "pack_score",
            "relative_pack_score",
            "pack_rank",
            "pack_tier",
            "profit_score",
            "safety_score",
            "stability_score",
            "desirability_score",
            "experience_score",
            "relative_experience_score",
            "experience_tier",
            "experience_rank",
            "chase_potential_score",
            "relative_chase_potential_score",
            "chase_potential_tier",
            "chase_potential_rank",
            "biggest_upside_score",
            "relative_biggest_upside_score",
            "biggest_upside_tier",
            "biggest_upside_rank",
            "average_return_score",
            "relative_average_return_score",
            "mean_value_to_cost_score",
            "relative_mean_value_to_cost_score",
            "mean_value_to_cost_tier",
            "mean_value_to_cost_rank",
            *RANK_CONTEXT_FIELDS,
            *RIP_DESIRABILITY_COMPARISON_FIELDS,
        ),
    )
    market_summary = _summary_subset(
        summary,
        (
            "pack_cost",
            "mean_value",
            "median_value",
            "mean_value_to_cost_ratio",
            "median_value_to_cost_ratio",
            "roi_percent",
            "prob_profit",
            "prob_big_hit",
            "p95_value_to_cost_ratio",
            "p99_value_to_cost_ratio",
            "simulated_set_value",
            "simulated_set_value_card_count",
            "average_hit_value",
            "expected_loss_per_pack",
        ),
    )
    risk_summary = _summary_subset(
        summary,
        (
            "expected_loss_when_losing_fraction",
            "median_loss_when_losing_fraction",
            "p05_shortfall_to_cost",
            "expected_loss_when_losing",
            "median_loss_when_losing",
            "tail_value_p05",
            "coefficient_of_variation",
        ),
    )
    concentration = _summary_subset(
        summary,
        ("hhi_ev_concentration", "effective_chase_count", "top1_ev_share", "top3_ev_share", "top5_ev_share"),
    )

    return {
        "set_id": set_id,
        "set_identity_json": set_identity,
        "title_card_json": title_card,
        "rip_summary_json": rip_summary,
        "market_summary_json": market_summary,
        "risk_summary_json": risk_summary,
        "concentration_json": concentration,
        "desirability_summary_json": payload.get("openingDesirability") or {},
        "set_intelligence_json": payload.get("interpretation") or {},
        "payload_json": payload,
        "as_of": first_non_empty(summary.get("run_at"), payload.get("meta", {}).get("asOfDate"), built_at),
        "source_updated_at": first_non_empty(summary.get("run_at"), built_at),
    }


def _load_simulation_performance_history(client: Any, set_id: str) -> List[Dict[str, Any]]:
    """Load simulation performance history for a set from calculation_history_trend + simulation_run_summary."""
    resolved_client = client or get_client()
    try:
        result = (
            resolved_client.table("calculation_history_trend")
            .select(
                "snapshot_date,calculation_run_id,run_created_at,"
                "simulated_mean_pack_value_vs_pack_cost,simulated_median_pack_value_vs_pack_cost,"
                "p95_value_to_cost_ratio"
            )
            .eq("target_type", "set")
            .eq("target_id", set_id)
            .order("snapshot_date", desc=False)
            .execute()
        )
        rows = list(result.data or [])
    except Exception as exc:
        if is_transient_data_service_error(exc):
            raise
        logger.warning("simulation performance history load failed set_id=%s", set_id, exc_info=True)
        return []

    run_ids = sorted({str(row["calculation_run_id"]) for row in rows if row.get("calculation_run_id")})
    summary_lookup: Dict[str, Dict[str, Any]] = {}
    if run_ids:
        try:
            summary_result = (
                resolved_client.table("simulation_run_summary")
                .select("calculation_run_id,pack_cost,mean_value,median_value")
                .in_("calculation_run_id", run_ids)
                .execute()
            )
            for summary_row in list(summary_result.data or []):
                run_id_key = first_non_empty(summary_row.get("calculation_run_id"))
                if run_id_key:
                    summary_lookup[run_id_key] = summary_row
        except Exception as exc:
            if is_transient_data_service_error(exc):
                raise
            logger.warning("simulation run summary join failed set_id=%s", set_id, exc_info=True)

    points: List[Dict[str, Any]] = []
    for row in rows:
        date_key = parse_date_key(row.get("snapshot_date"))
        if not date_key:
            continue
        run_id = first_non_empty(row.get("calculation_run_id"))
        run_created_at = first_non_empty(row.get("run_created_at"))
        mean_ratio = to_optional_float(row.get("simulated_mean_pack_value_vs_pack_cost"))
        median_ratio = to_optional_float(row.get("simulated_median_pack_value_vs_pack_cost"))
        p95_ratio = to_optional_float(row.get("p95_value_to_cost_ratio"))
        summary = summary_lookup.get(run_id or "") or {}
        pack_cost = to_optional_float(summary.get("pack_cost"))
        mean_value = to_optional_float(summary.get("mean_value"))
        median_value = to_optional_float(summary.get("median_value"))
        points.append({
            "date": date_key,
            "snapshot_date": date_key,
            "sourceDate": date_key,
            "source_date": date_key,
            "calculationRunId": run_id,
            "calculation_run_id": run_id,
            "runCreatedAt": run_created_at,
            "run_created_at": run_created_at,
            "packCost": pack_cost,
            "pack_cost": pack_cost,
            "meanValue": mean_value,
            "mean_value": mean_value,
            "medianValue": median_value,
            "median_value": median_value,
            "meanValueToCostRatio": mean_ratio,
            "mean_value_to_cost_ratio": mean_ratio,
            "simulatedMeanPackValueVsPackCost": mean_ratio,
            "simulated_mean_pack_value_vs_pack_cost": mean_ratio,
            "medianValueToCostRatio": median_ratio,
            "median_value_to_cost_ratio": median_ratio,
            "simulatedMedianPackValueVsPackCost": median_ratio,
            "simulated_median_pack_value_vs_pack_cost": median_ratio,
            "p95ValueToCostRatio": p95_ratio,
            "p95_value_to_cost_ratio": p95_ratio,
            "source": "calculation_history_trend+simulation_run_summary",
            "provider": "calculation_history_trend+simulation_run_summary",
            "isCarriedForward": False,
            "is_carried_forward": False,
        })
    return points


def _latest_history_date(histories_by_scope: Dict[str, List[Dict[str, Any]]]) -> Optional[str]:
    latest: Optional[str] = None
    for history in histories_by_scope.values():
        for point in history:
            date_key = first_non_empty(point.get("date"), point.get("snapshot_date"))
            if date_key and (latest is None or date_key > latest):
                latest = date_key
    return latest


def _top_chase_variant_ids(cards: List[Dict[str, Any]]) -> List[str]:
    variant_ids: List[str] = []
    seen: set[str] = set()
    for card in cards:
        variant_id = first_non_empty(card.get("cardVariantId"), card.get("card_variant_id"))
        if variant_id and variant_id not in seen:
            seen.add(variant_id)
            variant_ids.append(variant_id)
    return variant_ids


def _has_top_chase_history_points(history_by_card: Dict[str, List[Dict[str, Any]]]) -> bool:
    return any(isinstance(history, list) and len(history) > 0 for history in history_by_card.values())


def _top_chase_history_counts(history_by_card: Dict[str, List[Dict[str, Any]]]) -> List[int]:
    return [len(history) for history in history_by_card.values() if isinstance(history, list)]


def _top_chase_histories_cover_source_window(
    history_by_card: Dict[str, List[Dict[str, Any]]],
    *,
    variant_ids: List[str],
    source_window_days: int,
    latest_date_key: Optional[str] = None,
) -> bool:
    if not variant_ids:
        return _has_top_chase_history_points(history_by_card)
    for variant_id in variant_ids:
        history = history_by_card.get(variant_id)
        if not isinstance(history, list) or len(history) < source_window_days:
            return False
        if latest_date_key:
            history_end = max(
                (parse_date_key(point.get("date")) for point in history if isinstance(point, dict)),
                default=None,
            )
            if history_end != latest_date_key:
                return False
    return True


def _normalize_match_text(value: Any) -> str:
    return " ".join(str(value or "").strip().lower().split())


def _normalize_card_number(value: Any) -> str:
    compact = str(value or "").strip().replace(" ", "").lower()
    if "/" in compact:
        compact = compact.split("/", 1)[0]
    stripped = compact.lstrip("0")
    return stripped or compact


def _card_match_keys(name: Any, number: Any) -> List[str]:
    normalized_name = _normalize_match_text(name)
    normalized_number = _normalize_card_number(number)
    if not normalized_name or not normalized_number:
        return []
    return [
        f"name+number:{normalized_name}:{normalized_number}",
        f"name+raw_number:{normalized_name}:{str(number or '').strip().replace(' ', '').lower()}",
    ]


def _query_table_rows(client: Any, table_name: str, configure_query) -> List[Dict[str, Any]]:
    result = configure_query(client.table(table_name)).execute()
    return list(result.data or [])


def _build_top_chase_canonical_history_context(
    client: Any,
    *,
    set_id: str,
    cards: List[Dict[str, Any]],
    selected_price_rows: Optional[List[Dict[str, Any]]] = None,
) -> Dict[str, Any]:
    canonical_cards = _query_table_rows(
        client,
        "pokemon_canonical_cards",
        lambda query: query.select("id,set_id,pokemon_tcg_api_card_id,name,number,printed_number").eq("set_id", set_id),
    )
    legacy_cards = _query_table_rows(
        client,
        "cards",
        lambda query: query.select("id,set_id,name,card_number,pokemon_tcg_api_id").eq("set_id", set_id),
    )
    legacy_card_ids = [str(card["id"]) for card in legacy_cards if card.get("id") is not None]
    variant_rows = (
        _query_table_rows(
            client,
            "card_variants",
            lambda query: query.select("id,card_id,pokemon_tcg_api_id").in_("card_id", legacy_card_ids),
        )
        if legacy_card_ids
        else []
    )
    if selected_price_rows is None:
        selected_price_rows = _query_table_rows(
            client,
            "pokemon_canonical_card_market_prices_latest",
            lambda query: query.select(
                "canonical_card_id,card_variant_id,condition_id,printing_type,market_price,captured_at,source"
            ).eq("set_id", set_id),
        )
    else:
        selected_price_rows = list(selected_price_rows)

    canonical_by_id = {
        str(card["id"]): card
        for card in canonical_cards
        if card.get("id") is not None
    }
    canonical_by_api_id = {
        str(card["pokemon_tcg_api_card_id"]): card
        for card in canonical_cards
        if card.get("pokemon_tcg_api_card_id") is not None
    }
    canonical_by_match_key: Dict[str, Dict[str, Any]] = {}
    for card in canonical_cards:
        for key in _card_match_keys(card.get("name"), card.get("number")) + _card_match_keys(
            card.get("name"), card.get("printed_number")
        ):
            canonical_by_match_key.setdefault(key, card)

    legacy_card_to_canonical_id: Dict[str, str] = {}
    for legacy_card in legacy_cards:
        canonical = None
        api_id = first_non_empty(legacy_card.get("pokemon_tcg_api_id"))
        if api_id:
            canonical = canonical_by_api_id.get(api_id)
        if canonical is None:
            for key in _card_match_keys(legacy_card.get("name"), legacy_card.get("card_number")):
                canonical = canonical_by_match_key.get(key)
                if canonical is not None:
                    break
        if canonical and legacy_card.get("id") is not None:
            legacy_card_to_canonical_id[str(legacy_card["id"])] = str(canonical["id"])

    variant_to_canonical_id: Dict[str, str] = {}
    for variant in variant_rows:
        variant_id = first_non_empty(variant.get("id"))
        if not variant_id:
            continue
        canonical_id = legacy_card_to_canonical_id.get(str(variant.get("card_id")))
        variant_api_id = first_non_empty(variant.get("pokemon_tcg_api_id"))
        if variant_api_id and variant_api_id in canonical_by_api_id:
            canonical_id = str(canonical_by_api_id[variant_api_id]["id"])
        if canonical_id in canonical_by_id:
            variant_to_canonical_id[variant_id] = canonical_id

    selected_variant_to_canonical_id = {
        str(row["card_variant_id"]): str(row["canonical_card_id"])
        for row in selected_price_rows
        if row.get("card_variant_id") is not None
        and row.get("canonical_card_id") is not None
        and str(row.get("canonical_card_id")) in canonical_by_id
    }
    selected_condition_by_variant = {
        str(row["card_variant_id"]): str(row["condition_id"])
        for row in selected_price_rows
        if row.get("card_variant_id") is not None and row.get("condition_id") is not None
    }
    selected_price_by_canonical_id = {
        str(row["canonical_card_id"]): row
        for row in selected_price_rows
        if row.get("canonical_card_id") is not None
        and str(row.get("canonical_card_id")) in canonical_by_id
        and row.get("card_variant_id") is not None
        and row.get("condition_id") is not None
        and to_optional_float(row.get("market_price")) is not None
    }
    variant_to_canonical_id.update(selected_variant_to_canonical_id)

    display_key_to_canonical_id: Dict[str, str] = {}
    for card in cards:
        display_key = first_non_empty(card.get("cardVariantId"), card.get("card_variant_id"), card.get("cardId"), card.get("card_id"), card.get("id"))
        variant_id = first_non_empty(card.get("cardVariantId"), card.get("card_variant_id"))
        card_id = first_non_empty(card.get("cardId"), card.get("card_id"), card.get("id"))
        canonical_id = (
            variant_to_canonical_id.get(variant_id or "")
            or legacy_card_to_canonical_id.get(card_id or "")
            or (card_id if card_id in canonical_by_id else None)
        )
        if display_key and canonical_id:
            display_key_to_canonical_id[str(display_key)] = canonical_id

    return {
        "canonical_by_id": canonical_by_id,
        "variant_to_canonical_id": variant_to_canonical_id,
        "display_key_to_canonical_id": display_key_to_canonical_id,
        "selected_price_by_canonical_id": selected_price_by_canonical_id,
        "condition_by_variant": selected_condition_by_variant,
        "variant_ids": sorted(
            variant_id
            for variant_id, canonical_id in (
                selected_variant_to_canonical_id.items()
                if selected_variant_to_canonical_id
                else variant_to_canonical_id.items()
            )
            if canonical_id in set(display_key_to_canonical_id.values())
        ),
    }


def _compact_top_chase_canonical_observation_rows(
    rows: List[Dict[str, Any]],
    *,
    variant_to_canonical_id: Dict[str, str],
    display_key_to_canonical_id: Dict[str, str],
    condition_by_variant: Optional[Dict[str, str]] = None,
) -> Dict[str, List[Dict[str, Any]]]:
    points_by_canonical_date: Dict[str, Dict[str, Dict[str, Any]]] = {}
    captured_at_by_canonical_date: Dict[str, Dict[str, str]] = {}
    daily_counts_by_canonical_date: Dict[str, Dict[str, int]] = {}
    for row in rows:
        variant_id = first_non_empty(row.get("card_variant_id"))
        condition_id = first_non_empty(row.get("condition_id"))
        if condition_by_variant and condition_id != condition_by_variant.get(variant_id or ""):
            continue
        canonical_id = variant_to_canonical_id.get(variant_id or "")
        captured_at = first_non_empty(row.get("captured_at"), row.get("capturedAt"))
        date_key = parse_date_key(captured_at)
        price = to_optional_float(row.get("market_price") if "market_price" in row else row.get("marketPrice"))
        if not canonical_id or not date_key or price is None or price <= 0:
            continue
        daily_counts = daily_counts_by_canonical_date.setdefault(canonical_id, {})
        daily_counts[date_key] = daily_counts.get(date_key, 0) + 1
        existing_captured_at = captured_at_by_canonical_date.setdefault(canonical_id, {}).get(date_key)
        if existing_captured_at and captured_at and captured_at <= existing_captured_at:
            continue
        captured_at_by_canonical_date[canonical_id][date_key] = captured_at or date_key
        points_by_canonical_date.setdefault(canonical_id, {})[date_key] = {
            "date": date_key,
            "marketPrice": round(price, 2),
            "market_price": round(price, 2),
            "sourceDate": date_key,
            "source_date": date_key,
            "sourceVariantId": variant_id,
            "source_variant_id": variant_id,
            "dailyObservationCount": daily_counts[date_key],
            "daily_observation_count": daily_counts[date_key],
            "isObserved": True,
            "is_observed": True,
            "isCarriedForward": False,
            "is_carried_forward": False,
        }

    histories_by_display_key: Dict[str, List[Dict[str, Any]]] = {}
    for display_key, canonical_id in display_key_to_canonical_id.items():
        points = points_by_canonical_date.get(canonical_id, {})
        if points:
            histories_by_display_key[display_key] = [points[date_key] for date_key in sorted(points.keys())]
    return histories_by_display_key


def _load_top_chase_histories_from_observations(
    client: Any,
    *,
    set_id: str,
    cards: Optional[List[Dict[str, Any]]] = None,
    variant_ids: List[str],
    latest_date_key: Optional[str],
    days: int,
) -> Dict[str, List[Dict[str, Any]]]:
    if not variant_ids:
        return {}

    resolved_latest_date_key = first_non_empty(latest_date_key)
    if not resolved_latest_date_key:
        try:
            latest_result = (
                client.table("card_variant_price_observations")
                .select("captured_at")
                .in_("card_variant_id", variant_ids)
                .eq("condition_id", TOP_CHASE_NEAR_MINT_CONDITION_ID)
                .gt("market_price", 0)
                .order("captured_at", desc=True)
                .limit(1)
                .execute()
            )
            latest_rows = list(latest_result.data or [])
            resolved_latest_date_key = parse_date_key((latest_rows[0] if latest_rows else {}).get("captured_at"))
        except Exception as exc:
            if is_transient_data_service_error(exc):
                raise
            logger.warning("top chase observation history latest lookup failed set_id=%s", set_id, exc_info=True)
            return {}

    try:
        latest_date = date.fromisoformat(str(resolved_latest_date_key)[:10])
    except (TypeError, ValueError):
        return {}

    start_date = latest_date - timedelta(days=max(days - 1, 0))
    end_date = latest_date + timedelta(days=1)
    canonical_context: Dict[str, Any] = {}
    try:
        canonical_context = _build_top_chase_canonical_history_context(
            client,
            set_id=set_id,
            cards=list(cards or []),
        )
    except Exception as exc:
        if is_transient_data_service_error(exc):
            raise
        logger.warning("[pokemon-snapshot] canonical top chase history context failed set_id=%s", set_id, exc_info=True)
        canonical_context = {}

    canonical_variant_ids = list(canonical_context.get("variant_ids") or [])
    if canonical_variant_ids:
        try:
            canonical_condition_by_variant = dict(canonical_context.get("condition_by_variant") or {})
            canonical_condition_ids = sorted(set(canonical_condition_by_variant.values()))
            latest_result = (
                client.table("card_variant_price_observations")
                .select("captured_at")
                .in_("card_variant_id", canonical_variant_ids)
                .in_("condition_id", canonical_condition_ids)
                .gt("market_price", 0)
                .order("captured_at", desc=True)
                .limit(1)
                .execute()
            )
            canonical_latest_date_key = parse_date_key((list(latest_result.data or [])[:1] or [{}])[0].get("captured_at"))
            if canonical_latest_date_key:
                canonical_latest_date = date.fromisoformat(canonical_latest_date_key)
                if canonical_latest_date > latest_date:
                    latest_date = canonical_latest_date
                    start_date = latest_date - timedelta(days=max(days - 1, 0))
                    end_date = latest_date + timedelta(days=1)
            result = (
                client.table("card_variant_price_observations")
                .select("card_variant_id,condition_id,captured_at,market_price")
                .in_("card_variant_id", canonical_variant_ids)
                .in_("condition_id", canonical_condition_ids)
                .gt("market_price", 0)
                .gte("captured_at", start_date.isoformat())
                .lt("captured_at", end_date.isoformat())
                .order("captured_at", desc=False)
                .execute()
            )
            histories = _compact_top_chase_canonical_observation_rows(
                list(result.data or []),
                variant_to_canonical_id=dict(canonical_context.get("variant_to_canonical_id") or {}),
                display_key_to_canonical_id=dict(canonical_context.get("display_key_to_canonical_id") or {}),
                condition_by_variant=canonical_condition_by_variant,
            )
            if histories:
                logger.info(
                    "[pokemon-snapshot] canonical top chase histories set_id=%s cards=%s variants=%s",
                    set_id,
                    len(histories),
                    len(canonical_variant_ids),
                )
                return histories
        except Exception as exc:
            if is_transient_data_service_error(exc):
                raise
            logger.warning("canonical top chase observation history load failed set_id=%s", set_id, exc_info=True)

    try:
        result = (
            client.table("card_variant_price_observations")
            .select("card_variant_id,captured_at,market_price")
            .in_("card_variant_id", variant_ids)
            .eq("condition_id", TOP_CHASE_NEAR_MINT_CONDITION_ID)
            .gt("market_price", 0)
            .gte("captured_at", start_date.isoformat())
            .lt("captured_at", end_date.isoformat())
            .order("captured_at", desc=False)
            .execute()
        )
    except Exception as exc:
        if is_transient_data_service_error(exc):
            raise
        logger.warning("top chase observation history load failed set_id=%s", set_id, exc_info=True)
        return {}

    points_by_variant_date: Dict[str, Dict[str, Dict[str, Any]]] = {}
    captured_at_by_variant_date: Dict[str, Dict[str, str]] = {}
    for row in result.data or []:
        variant_id = first_non_empty(row.get("card_variant_id"))
        captured_at = first_non_empty(row.get("captured_at"), row.get("capturedAt"))
        date_key = parse_date_key(captured_at)
        price = to_optional_float(row.get("market_price") if "market_price" in row else row.get("marketPrice"))
        if not variant_id or not date_key or price is None or price <= 0:
            continue
        existing_captured_at = captured_at_by_variant_date.setdefault(variant_id, {}).get(date_key)
        if existing_captured_at and captured_at and captured_at <= existing_captured_at:
            continue
        captured_at_by_variant_date[variant_id][date_key] = captured_at or date_key
        points_by_variant_date.setdefault(variant_id, {})[date_key] = {
            "date": date_key,
            "marketPrice": round(price, 2),
            "market_price": round(price, 2),
            "sourceDate": date_key,
            "source_date": date_key,
            "isObserved": True,
            "is_observed": True,
        }

    return {
        variant_id: [points[date_key] for date_key in sorted(points.keys())]
        for variant_id, points in points_by_variant_date.items()
        if points
    }


def _history_by_card(cards: List[Dict[str, Any]]) -> Dict[str, List[Dict[str, Any]]]:
    history_by_card: Dict[str, List[Dict[str, Any]]] = {}
    for card in cards:
        key = first_non_empty(card.get("cardVariantId"), card.get("card_variant_id"), card.get("cardId"), card.get("card_id"))
        if not key:
            continue
        history = card.get("priceHistory") if isinstance(card.get("priceHistory"), list) else card.get("price_history")
        compact_history: List[Dict[str, Any]] = []
        for point in list(history or []):
            date_key = first_non_empty(point.get("date"), point.get("capturedAt"), point.get("captured_at"))
            if not date_key:
                continue
            compact_point = {
                "date": str(date_key)[:10],
                "marketPrice": point.get("marketPrice", point.get("market_price", point.get("price"))),
                "market_price": point.get("market_price", point.get("marketPrice", point.get("price"))),
            }
            source_date = first_non_empty(point.get("sourceDate"), point.get("source_date"))
            if source_date:
                compact_point["sourceDate"] = str(source_date)[:10]
                compact_point["source_date"] = str(source_date)[:10]
            compact_history.append(compact_point)
        if compact_history:
            history_by_card[str(key)] = compact_history
    return history_by_card


def _forward_fill_history_through_date(
    history: List[Dict[str, Any]],
    *,
    end_date_key: Optional[str],
) -> List[Dict[str, Any]]:
    """Materialize each market day while preserving the last real source date."""
    if not history or not end_date_key:
        return list(history or [])
    observed_by_date: Dict[str, Dict[str, Any]] = {}
    for point in history:
        date_key = parse_date_key(point.get("date") or point.get("capturedAt") or point.get("captured_at"))
        price = to_optional_float(point.get("marketPrice") if "marketPrice" in point else point.get("market_price"))
        if date_key and price is not None and date_key <= end_date_key:
            observed_by_date[date_key] = dict(point)
    if not observed_by_date:
        return []
    cursor = date.fromisoformat(min(observed_by_date))
    end_date = date.fromisoformat(end_date_key)
    last_point: Optional[Dict[str, Any]] = None
    filled: List[Dict[str, Any]] = []
    while cursor <= end_date:
        date_key = cursor.isoformat()
        observed = observed_by_date.get(date_key)
        if observed is not None:
            source_date = parse_date_key(observed.get("sourceDate") or observed.get("source_date")) or date_key
            carried_forward = bool(
                observed.get("isCarriedForward")
                or observed.get("is_carried_forward")
                or source_date < date_key
            )
            last_point = {
                **observed,
                "date": date_key,
                "sourceDate": source_date,
                "source_date": source_date,
                "isObserved": not carried_forward,
                "is_observed": not carried_forward,
                "isCarriedForward": carried_forward,
                "is_carried_forward": carried_forward,
            }
            filled.append(last_point)
        elif last_point is not None:
            price = to_optional_float(last_point.get("marketPrice") if "marketPrice" in last_point else last_point.get("market_price"))
            source_date = parse_date_key(last_point.get("sourceDate") or last_point.get("source_date") or last_point.get("date"))
            last_point = {
                **last_point,
                "date": date_key,
                "marketPrice": round(price, 2) if price is not None else None,
                "market_price": round(price, 2) if price is not None else None,
                "sourceDate": source_date,
                "source_date": source_date,
                "dailyObservationCount": 0,
                "daily_observation_count": 0,
                "isObserved": False,
                "is_observed": False,
                "isCarriedForward": True,
                "is_carried_forward": True,
            }
            filled.append(last_point)
        cursor += timedelta(days=1)
    return filled


def _compact_top_chase_cards(cards: List[Dict[str, Any]], history_by_card: Dict[str, List[Dict[str, Any]]]) -> List[Dict[str, Any]]:
    compact_cards: List[Dict[str, Any]] = []
    for card in cards:
        compact_card = {key: value for key, value in card.items() if key not in TOP_CHASE_HISTORY_FIELDS}
        history_key = first_non_empty(card.get("cardVariantId"), card.get("card_variant_id"), card.get("cardId"), card.get("card_id"))
        compact_history = history_by_card.get(str(history_key)) if history_key else None
        if compact_history:
            compact_card["priceHistory"] = compact_history
            compact_card["price_history"] = compact_history
            latest_price_point = next(
                (point for point in reversed(compact_history) if to_optional_float(point.get("marketPrice") if "marketPrice" in point else point.get("market_price")) is not None),
                None,
            )
            if latest_price_point:
                latest_price = round(
                    to_optional_float(
                        latest_price_point.get("marketPrice")
                        if "marketPrice" in latest_price_point
                        else latest_price_point.get("market_price")
                    )
                    or 0,
                    2,
                )
                compact_card["marketPrice"] = latest_price
                compact_card["estimatedMarketPrice"] = latest_price
                compact_card["estimated_market_price"] = latest_price
                compact_card["priceUsed"] = latest_price
                compact_card["price_used"] = latest_price
                latest_date = first_non_empty(latest_price_point.get("date"), latest_price_point.get("sourceDate"), latest_price_point.get("source_date"))
                source_date = first_non_empty(latest_price_point.get("sourceDate"), latest_price_point.get("source_date"), latest_date)
                if latest_date:
                    compact_card["priceUpdatedAt"] = latest_date[:10]
                    compact_card["price_updated_at"] = latest_date[:10]
                    compact_card["historyEndDate"] = latest_date[:10]
                    compact_card["history_end_date"] = latest_date[:10]
                if source_date:
                    compact_card["priceSourceDate"] = source_date[:10]
                    compact_card["price_source_date"] = source_date[:10]
                compact_card["priceCarriedForward"] = bool(latest_date and source_date and source_date[:10] < latest_date[:10])
                compact_card["price_carried_forward"] = compact_card["priceCarriedForward"]
        compact_cards.append(compact_card)
    return compact_cards


def _enrich_top_chase_cards_with_canonical_deltas(
    cards: List[Dict[str, Any]],
    *,
    histories: Dict[str, List[Dict[str, Any]]],
    canonical_context: Dict[str, Any],
    latest_market_date: Optional[str],
    movement_metadata: Optional[Dict[str, Any]] = None,
) -> tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    diagnostics: List[Dict[str, Any]] = []
    enriched_cards: List[Dict[str, Any]] = []
    display_to_canonical = dict(canonical_context.get("display_key_to_canonical_id") or {})
    selected_by_canonical = dict(canonical_context.get("selected_price_by_canonical_id") or {})
    for card in cards:
        enriched = dict(card)
        display_key = first_non_empty(
            card.get("cardVariantId"), card.get("card_variant_id"),
            card.get("cardId"), card.get("card_id"), card.get("id"),
        )
        canonical_id = display_to_canonical.get(display_key or "")
        selected = selected_by_canonical.get(canonical_id or "")
        if not canonical_id:
            diagnostics.append({
                "type": "top_chase_missing_canonical_identity",
                "displayCardId": display_key,
                "name": first_non_empty(card.get("name")),
            })
            enriched_cards.append(enriched)
            continue
        if not selected:
            diagnostics.append({
                "type": "top_chase_missing_selected_variant",
                "canonicalCardId": canonical_id,
                "displayCardId": display_key,
            })
            enriched_cards.append(enriched)
            continue
        if not latest_market_date:
            enriched_cards.append(enriched)
            continue
        selected_variant_id = first_non_empty(selected.get("card_variant_id"))
        selected_condition_id = first_non_empty(selected.get("condition_id"))
        if not selected_variant_id or not selected_condition_id:
            diagnostics.append({
                "type": "top_chase_missing_selected_variant",
                "canonicalCardId": canonical_id,
                "displayCardId": display_key,
            })
            enriched_cards.append(enriched)
            continue
        original_variant_id = first_non_empty(card.get("cardVariantId"), card.get("card_variant_id"))
        original_condition_id = first_non_empty(card.get("conditionId"), card.get("condition_id"), card.get("conditionIdUsed"), card.get("condition_id_used"))
        if original_variant_id and original_variant_id != selected_variant_id:
            diagnostics.append({
                "type": "top_chase_variant_mismatch",
                "canonicalCardId": canonical_id,
                "simulationVariantId": original_variant_id,
                "canonicalVariantId": selected_variant_id,
            })
        if original_condition_id and original_condition_id != selected_condition_id:
            diagnostics.append({
                "type": "top_chase_condition_mismatch",
                "canonicalCardId": canonical_id,
                "simulationConditionId": original_condition_id,
                "canonicalConditionId": selected_condition_id,
            })
        history = histories.get(display_key or "") or histories.get(selected_variant_id) or []
        calculated_movements = {
            window_key: calculate_pokemon_card_market_delta(
                observations=history,
                selected_current_price=selected.get("market_price"),
                selected_variant_id=selected_variant_id,
                selected_condition_id=selected_condition_id,
                latest_market_date=latest_market_date,
                requested_window_days=window_days,
                selected_current_source_date=selected.get("captured_at"),
                selected_current_source=selected.get("source"),
            )
            for window_key, window_days in MARKET_MOVERS_WINDOWS_DAYS.items()
        }
        movements = {
            window_key: {
                **movement,
                "canonicalCardId": canonical_id,
                "canonical_card_id": canonical_id,
            }
            for window_key, movement in calculated_movements.items()
            if movement.get("startDate")
            and movement.get("endDate")
            and movement.get("startDate") < movement.get("endDate")
            and movement.get("changeAmount") is not None
            and movement.get("changePercent") is not None
        }
        if movement_metadata:
            movements = {
                window_key: {**movement, **movement_metadata}
                for window_key, movement in movements.items()
            }
        current_price = round(to_optional_float(selected.get("market_price")) or 0, 2)
        enriched.update({
            "id": canonical_id,
            "cardId": canonical_id,
            "card_id": canonical_id,
            "canonicalCardId": canonical_id,
            "canonical_card_id": canonical_id,
            "cardVariantId": selected_variant_id,
            "card_variant_id": selected_variant_id,
            "conditionId": selected_condition_id,
            "condition_id": selected_condition_id,
            "conditionIdUsed": selected_condition_id,
            "condition_id_used": selected_condition_id,
            "marketPrice": current_price,
            "estimatedMarketPrice": current_price,
            "estimated_market_price": current_price,
            "priceUsed": current_price,
            "price_used": current_price,
            "marketDate": latest_market_date,
            "market_date": latest_market_date,
            "windowConvention": WINDOW_CONVENTION,
            "window_convention": WINDOW_CONVENTION,
            "marketDeltaWindows": movements,
            "market_delta_windows": movements,
            "movementMetadata": dict(movement_metadata or {}),
            "movement_metadata": dict(movement_metadata or {}),
        })
        enriched_cards.append(enriched)
    return enriched_cards, diagnostics


def _top_chase_raw_movement_histories(
    histories: Dict[str, List[Dict[str, Any]]],
    *,
    latest_market_date: Optional[str],
) -> Dict[str, List[Dict[str, Any]]]:
    end_date_key = parse_date_key(latest_market_date)
    if not end_date_key:
        return {}
    cutoff = (date.fromisoformat(end_date_key) - timedelta(days=CARD_MOVEMENT_LOOKBACK_DAYS)).isoformat()
    result: Dict[str, List[Dict[str, Any]]] = {}
    for key, points in histories.items():
        usable = []
        for point in points if isinstance(points, list) else []:
            point_date = parse_date_key(
                first_non_empty(point.get("date"), point.get("captured_at"), point.get("capturedAt"))
            )
            if not point_date or point_date < cutoff or point_date > end_date_key:
                continue
            if point.get("isObserved") is False or point.get("is_observed") is False:
                continue
            if point.get("isCarriedForward") is True or point.get("is_carried_forward") is True:
                continue
            usable.append(point)
        if usable:
            result[key] = usable
    return result


def build_top_chase_history_rows(
    *,
    set_id: str,
    top_cards: List[Dict[str, Any]],
    histories: Dict[str, List[Dict[str, Any]]],
) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    for rank, card in enumerate(top_cards, start=1):
        history_key = first_non_empty(
            card.get("cardVariantId"), card.get("card_variant_id"), card.get("cardId"), card.get("card_id")
        )
        card_history = histories.get(str(history_key)) if history_key else None
        if not card_history:
            card_history = card.get("priceHistory") if isinstance(card.get("priceHistory"), list) else card.get("price_history")
        latest_point_date = first_non_empty(card.get("priceUpdatedAt"), card.get("price_updated_at"))
        points = list(card_history or [])
        if not points and latest_point_date:
            points = [{
                "date": latest_point_date[:10],
                "marketPrice": card.get("marketPrice") or card.get("estimatedMarketPrice"),
                "source": card.get("source") or card.get("provider"),
                "sourceDate": latest_point_date[:10],
            }]
        for point in points:
            snapshot_date = first_non_empty(point.get("date"), point.get("capturedAt"), point.get("captured_at"))
            if not snapshot_date:
                continue
            rows.append({
                "set_id": set_id,
                "snapshot_date": snapshot_date[:10],
                "card_id": first_non_empty(card.get("cardId"), card.get("card_id"), card.get("id")),
                "card_variant_id": first_non_empty(
                    point.get("sourceVariantId"), point.get("source_variant_id"),
                    card.get("cardVariantId"), card.get("card_variant_id"),
                ),
                "rank": rank,
                "name": first_non_empty(card.get("name")),
                "rarity": first_non_empty(card.get("rarity")),
                "image_url": first_non_empty(card.get("imageUrl"), card.get("image_url")),
                "image_small_url": first_non_empty(card.get("imageSmallUrl"), card.get("image_small_url")),
                "image_large_url": first_non_empty(card.get("imageLargeUrl"), card.get("image_large_url")),
                "market_price": point.get("marketPrice") or point.get("market_price") or card.get("marketPrice"),
                "source": first_non_empty(point.get("source"), point.get("provider"), card.get("source"), card.get("provider")),
                "source_date": (first_non_empty(point.get("sourceDate"), point.get("source_date"), snapshot_date) or "")[:10],
            })
    return rows


def build_market_dashboard_snapshot_rows(
    set_row: Dict[str, Any],
    *,
    days: int = DEFAULT_DASHBOARD_DAYS,
    window: str = DEFAULT_DASHBOARD_WINDOW,
    client: Any = None,
    generation_id: Optional[str] = None,
    built_at: Optional[str] = None,
    selected_price_rows: Optional[List[Dict[str, Any]]] = None,
) -> tuple[Dict[str, Any], List[Dict[str, Any]]]:
    built_at = built_at or utc_now_iso()
    generation_id = generation_id or str(uuid4())
    set_id = str(set_row["id"])
    histories_by_scope: Dict[str, List[Dict[str, Any]]] = {}
    available_scope_lookup: Dict[str, Dict[str, Any]] = {}
    standard_meta: Dict[str, Any] = {}

    for scope in SET_VALUE_SCOPES:
        payload = get_pokemon_set_value_history_payload(set_id=set_id, days=days, value_scope=scope)
        history = list(payload.get("history") or [])
        histories_by_scope[scope] = history
        if scope == "standard":
            standard_meta = payload.get("meta") or {}
        for entry in (payload.get("meta") or {}).get("availableScopes") or (payload.get("meta") or {}).get("available_scopes") or []:
            key = first_non_empty(entry.get("key"))
            if key:
                available_scope_lookup[key] = entry

    # Public snapshots must never materialize a subset scope that exceeds the
    # same-date complete checklist, even if corrupt history already exists.
    validate_histories_by_scope(histories_by_scope, set_id=set_id)

    perf_history = _load_simulation_performance_history(client, set_id)
    latest_performance_date = max(
        (p["date"] for p in perf_history if p.get("date")),
        default=None,
    )
    latest_set_value_history_date = _latest_history_date(histories_by_scope)

    top_payload = get_pokemon_set_top_market_cards_payload(
        set_id=set_id,
        limit=10,
        days=TOP_CHASE_HISTORY_SOURCE_WINDOW_DAYS,
    )
    top_cards = list(top_payload.get("cards") or [])
    top_chase_canonical_context: Dict[str, Any] = {}
    try:
        top_chase_canonical_context = _build_top_chase_canonical_history_context(
            client or get_client(),
            set_id=set_id,
            cards=top_cards,
            selected_price_rows=selected_price_rows,
        )
    except Exception as exc:
        if is_transient_data_service_error(exc):
            raise
        logger.warning("[pokemon-snapshot] top chase canonical delta context failed set_id=%s", set_id, exc_info=True)
    selected_market_dates = [
        utc_date_key(row.get("captured_at"))
        for row in (top_chase_canonical_context.get("selected_price_by_canonical_id") or {}).values()
    ]
    canonical_market_date = max(
        (value for value in selected_market_dates if value),
        default=latest_set_value_history_date,
    )
    top_chase_card_histories = _history_by_card(top_cards)
    variant_ids = _top_chase_variant_ids(top_cards)
    canonical_variant_ids = list(top_chase_canonical_context.get("variant_ids") or [])
    needs_canonical_history = bool(canonical_variant_ids)
    if needs_canonical_history or not _top_chase_histories_cover_source_window(
        top_chase_card_histories,
        variant_ids=variant_ids,
        source_window_days=TOP_CHASE_HISTORY_SOURCE_WINDOW_DAYS,
        latest_date_key=canonical_market_date,
    ):
        history_variant_ids = canonical_variant_ids or variant_ids
        if history_variant_ids:
            loaded_histories = _load_top_chase_histories_from_observations(
                client or get_client(),
                set_id=set_id,
                cards=top_cards,
                variant_ids=history_variant_ids,
                latest_date_key=canonical_market_date,
                days=TOP_CHASE_HISTORY_SOURCE_WINDOW_DAYS,
            )
            if loaded_histories:
                top_chase_card_histories = {**top_chase_card_histories, **loaded_histories}
    top_chase_movement_histories = _top_chase_raw_movement_histories(
        top_chase_card_histories,
        latest_market_date=canonical_market_date,
    )
    top_chase_card_histories = {
        key: _forward_fill_history_through_date(history, end_date_key=canonical_market_date)
        for key, history in top_chase_card_histories.items()
    }
    compact_top_cards = _compact_top_chase_cards(top_cards, top_chase_card_histories)
    compact_top_cards, top_chase_identity_diagnostics = _enrich_top_chase_cards_with_canonical_deltas(
        compact_top_cards,
        histories=top_chase_movement_histories,
        canonical_context=top_chase_canonical_context,
        latest_market_date=canonical_market_date,
        movement_metadata={
            "movementContractVersion": MOVEMENT_CONTRACT_VERSION,
            "windowConvention": WINDOW_CONVENTION,
            "movementAsOfDate": canonical_market_date,
            "marketAsOfDate": canonical_market_date,
            "generationId": generation_id,
            "builtAt": built_at,
        },
    )
    top_chase_window_counts = {
        window_key: sum(
            1
            for card in compact_top_cards
            if isinstance(card.get("marketDeltaWindows"), dict)
            and isinstance(card["marketDeltaWindows"].get(window_key), dict)
        )
        for window_key in MARKET_MOVERS_WINDOWS_DAYS
    }
    top_chase_missing_canonical_identity_count = sum(
        diagnostic.get("type") == "top_chase_missing_canonical_identity"
        for diagnostic in top_chase_identity_diagnostics
    )
    top_chase_missing_selected_variant_count = sum(
        diagnostic.get("type") == "top_chase_missing_selected_variant"
        for diagnostic in top_chase_identity_diagnostics
    )
    top_chase_partial_card_count = sum(
        any(
            movement.get("isPartialWindow") is True
            for movement in (card.get("marketDeltaWindows") or {}).values()
            if isinstance(movement, dict)
        )
        for card in compact_top_cards
    )
    top_chase_priced_card_count = sum(
        (to_optional_float(card.get("marketPrice")) or 0) > 0
        for card in compact_top_cards
    )
    top_chase_movement_warnings = []
    if top_chase_priced_card_count > 0 and sum(top_chase_window_counts.values()) == 0:
        warning = "Top Chase has priced cards but no usable 1D/7D/30D movement contracts."
        top_chase_movement_warnings.append(warning)
        logger.warning("[pokemon-snapshot] %s set_id=%s", warning, set_id)
    # Re-key the canonical selected-variant histories as aliases so the slim
    # Top Chase reader and frontend can resolve history after the public card
    # identity is changed from the simulation variant to the selected variant.
    for display_key, canonical_id in (top_chase_canonical_context.get("display_key_to_canonical_id") or {}).items():
        selected = (top_chase_canonical_context.get("selected_price_by_canonical_id") or {}).get(canonical_id) or {}
        selected_variant_id = first_non_empty(selected.get("card_variant_id"))
        history = top_chase_card_histories.get(display_key)
        if selected_variant_id and history:
            top_chase_card_histories[selected_variant_id] = history
    top_chase_history_counts = _top_chase_history_counts(top_chase_card_histories)
    top_chase_observed_dates = [
        str(point.get("date"))[:10]
        for history in top_chase_card_histories.values()
        if isinstance(history, list)
        for point in history
        if parse_date_key(point.get("date"))
    ]
    movement_windows_payload = build_pokemon_set_card_movements_by_window_payload(
        set_id=set_id,
        window_days=tuple(MARKET_MOVERS_WINDOWS_DAYS.values()),
        client=client,
        selected_price_rows=selected_price_rows,
    )
    market_movers_by_window = movement_windows_payload.get("marketMoversByWindow") or {}
    market_movers_by_window_snake = movement_windows_payload.get("market_movers_by_window") or {}
    market_movers = market_movers_by_window[MARKET_MOVERS_COMPATIBILITY_WINDOW]
    market_movers_snake = market_movers_by_window_snake[MARKET_MOVERS_COMPATIBILITY_WINDOW]
    set_value_history_latest_date_by_scope = {
        scope: _latest_history_date({scope: history})
        for scope, history in histories_by_scope.items()
    }
    set_value_history_point_count_by_scope = {
        scope: len(history) if isinstance(history, list) else 0
        for scope, history in histories_by_scope.items()
    }
    latest_set_value_history_date = max(
        (date for date in set_value_history_latest_date_by_scope.values() if date),
        default=latest_set_value_history_date,
    )
    latest_market_date = canonical_market_date or latest_set_value_history_date
    dashboard_payload = {
        "set": top_payload.get("set")
        or {
            "id": set_row.get("id"),
            "name": set_row.get("name"),
            "slug": set_row.get("canonical_key"),
            "pokemon_api_set_id": set_row.get("pokemon_api_set_id"),
        },
        "window": window,
        "window_key": window,
        "days": days,
        "setValueHistoriesByScope": histories_by_scope,
        "set_value_histories_by_scope": histories_by_scope,
        "performanceVsCostHistory": perf_history,
        "performance_vs_cost_history": perf_history,
        "topChaseCards": compact_top_cards,
        "top_chase_cards": compact_top_cards,
        "topChaseCardHistories": top_chase_card_histories,
        "top_chase_card_histories": top_chase_card_histories,
        "marketMovers": market_movers,
        "market_movers": market_movers_snake,
        "marketMoversByWindow": market_movers_by_window,
        "market_movers_by_window": market_movers_by_window_snake,
        "availableScopes": list(available_scope_lookup.values()),
        "available_scopes": list(available_scope_lookup.values()),
        "latestMarketDate": latest_market_date,
        "latest_market_date": latest_market_date,
        "meta": {
            "window": window,
            "window_key": window,
            "days": days,
            "asOfDate": latest_market_date,
            "latestSetValueHistoryDate": latest_set_value_history_date,
            "latest_set_value_history_date": latest_set_value_history_date,
            "setValueHistoryLatestDateByScope": set_value_history_latest_date_by_scope,
            "set_value_history_latest_date_by_scope": set_value_history_latest_date_by_scope,
            "setValueHistoryPointCountByScope": set_value_history_point_count_by_scope,
            "set_value_history_point_count_by_scope": set_value_history_point_count_by_scope,
            "sources": {
                "set_value_histories": "pokemon_set_value_daily_history",
                "performance_vs_cost_history": "calculation_history_trend+simulation_run_summary",
                "performanceVsCostHistory": "calculation_history_trend+simulation_run_summary",
                "top_chase_cards": "pokemon_set_top_chase_card_daily_history/simulation_input_cards",
                "market_movers": "card_variant_price_observations/card_market_usd_latest_by_condition",
                "market_movers_by_window": "card_variant_price_observations/card_market_usd_latest_by_condition",
            },
            "latestPerformanceDate": latest_performance_date,
            "latest_performance_date": latest_performance_date,
            "warnings": (
                list(standard_meta.get("warnings") or [])
                + list((top_payload.get("meta") or {}).get("warnings") or [])
                + ([] if perf_history else ["Simulation performance history is unavailable for this set."])
                + top_chase_movement_warnings
            ),
            "topChaseHistorySource": TOP_CHASE_HISTORY_SOURCE,
            "topChaseHistorySourceWindowDays": TOP_CHASE_HISTORY_SOURCE_WINDOW_DAYS,
            "topChaseHistoryMinPoints": min(top_chase_history_counts) if top_chase_history_counts else 0,
            "topChaseHistoryMaxPoints": max(top_chase_history_counts) if top_chase_history_counts else 0,
            "topChaseHistoryFirstObservedDate": min(top_chase_observed_dates) if top_chase_observed_dates else None,
            "topChaseHistoryLatestObservedDate": max(top_chase_observed_dates) if top_chase_observed_dates else None,
            "topChaseHistoryHydratedFromDailyTable": False,
            "windowConvention": WINDOW_CONVENTION,
            "movementQueryDiagnostics": movement_windows_payload.get("meta") or {},
            "topChaseIdentityDiagnostics": top_chase_identity_diagnostics,
            "topChaseCardCount": len(compact_top_cards),
            "topChaseMovementCountByWindow": top_chase_window_counts,
            "topChaseMissingCanonicalIdentityCount": top_chase_missing_canonical_identity_count,
            "topChaseMissingSelectedVariantCount": top_chase_missing_selected_variant_count,
            "topChasePartialCardCount": top_chase_partial_card_count,
            "topChaseCardsWith1dMovement": top_chase_window_counts["1D"],
            "topChaseCardsWith7dMovement": top_chase_window_counts["7D"],
            "topChaseCardsWith30dMovement": top_chase_window_counts["30D"],
            "topChaseCardsMissingCanonicalIdentity": top_chase_missing_canonical_identity_count,
            "topChaseCardsMissingSelectedVariant": top_chase_missing_selected_variant_count,
            "topChaseCardsUsingPartialWindow": top_chase_partial_card_count,
            "snapshot": {
                "type": "pokemon_set_market_dashboard",
                "builtAt": built_at,
                "source": "pokemon_snapshot_builders",
                "movementContractVersion": MOVEMENT_CONTRACT_VERSION,
                "windowConvention": WINDOW_CONVENTION,
                "movementAsOfDate": latest_market_date,
                "marketAsOfDate": latest_market_date,
                "generationId": generation_id,
            },
        },
    }

    history_rows = build_top_chase_history_rows(
        set_id=set_id,
        top_cards=top_cards,
        histories=top_chase_card_histories,
    )

    return (
        {
            "set_id": set_id,
            "window_key": window,
            "payload_json": dashboard_payload,
            "set_value_histories_json": histories_by_scope,
            "performance_vs_cost_history_json": perf_history,
            "top_chase_cards_json": compact_top_cards,
            "top_chase_card_histories_json": top_chase_card_histories,
            "available_scopes_json": list(available_scope_lookup.values()),
            "latest_market_date": latest_market_date,
        },
        history_rows,
    )


def _query_rows(client, table_name: str, configure_query) -> List[Dict[str, Any]]:
    query = configure_query(client.table(table_name))
    result = query.execute()
    return list(result.data or [])


def _query_paginated_rows(
    client: Any,
    table_name: str,
    configure_query,
    *,
    page_size: int = CARD_PRICE_OBSERVATION_PAGE_SIZE,
) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    start = 0
    safe_page_size = max(1, int(page_size))
    while True:
        query = configure_query(client.table(table_name))
        result = query.range(start, start + safe_page_size - 1).execute()
        page = list(result.data or [])
        rows.extend(page)
        if len(page) < safe_page_size:
            return rows
        start += safe_page_size


def _build_card_appeal_price_index_for_set(
    *,
    set_id: str,
    canonical_cards: List[Dict[str, Any]],
    client: Any = None,
    selected_price_rows: Optional[List[Dict[str, Any]]] = None,
) -> Dict[str, Dict[str, Any]]:
    """Load the canonical pricing contract directly.

    The previous implementation rebuilt canonical identity through the legacy
    ``cards``/``card_variants`` tables.  Canonical-only checklist cards were
    therefore absent even though the selected-price view had a valid row.
    """
    try:
        client = client or get_client()
        selected_rows = list(selected_price_rows) if selected_price_rows is not None else _query_rows(
            client,
            "pokemon_canonical_card_market_prices_latest",
            lambda query: query.select(
                "canonical_card_id,set_id,card_variant_id,condition_id,printing_type,market_price,"
                "captured_at,source,price_selection_reason,refreshed_at"
            ).eq("set_id", set_id),
        )
        canonical_ids = {str(card.get("id")) for card in canonical_cards if card.get("id") is not None}
        return {
            str(row["canonical_card_id"]): {
                "market_price": to_optional_float(row.get("market_price")),
                "variant_id": first_non_empty(row.get("card_variant_id")),
                "condition_id": first_non_empty(row.get("condition_id")),
                "printing_type": first_non_empty(row.get("printing_type")),
                "captured_at": utc_date_key(row.get("captured_at")),
                "source": first_non_empty(row.get("source")),
                "price_selection_reason": first_non_empty(row.get("price_selection_reason")),
                "refreshed_at": first_non_empty(row.get("refreshed_at")),
            }
            for row in selected_rows
            if row.get("canonical_card_id") is not None
            and str(row.get("canonical_card_id")) in canonical_ids
            and to_optional_float(row.get("market_price")) is not None
        }
    except Exception as exc:
        if is_transient_data_service_error(exc):
            raise
        logger.warning("[pokemon-snapshot] card appeal price index lookup failed", exc_info=True)
        return {}


def _chunks(values: List[str], size: int) -> Iterable[List[str]]:
    for index in range(0, len(values), size):
        yield values[index : index + size]


def _load_selected_price_observations(
    client: Any,
    *,
    prices_by_card: Dict[str, Dict[str, Any]],
    latest_market_date: str,
) -> Dict[str, List[Dict[str, Any]]]:
    variant_to_card = {
        str(price["variant_id"]): card_id
        for card_id, price in prices_by_card.items()
        if price.get("variant_id") and price.get("condition_id")
    }
    condition_by_variant = {
        str(price["variant_id"]): str(price["condition_id"])
        for price in prices_by_card.values()
        if price.get("variant_id") and price.get("condition_id")
    }
    if not variant_to_card:
        return {}

    end_date = date.fromisoformat(latest_market_date)
    start_date = (end_date - timedelta(days=CARD_MOVEMENT_LOOKBACK_DAYS)).isoformat()
    observations_by_card: Dict[str, List[Dict[str, Any]]] = {}
    for variant_ids in _chunks(sorted(variant_to_card), CARD_PRICE_OBSERVATION_CHUNK_SIZE):
        condition_ids = sorted({condition_by_variant[variant_id] for variant_id in variant_ids})
        rows = _query_paginated_rows(
            client,
            "card_variant_price_observations",
            lambda query: query.select("id,card_variant_id,condition_id,market_price,source,captured_at")
            .in_("card_variant_id", variant_ids)
            .in_("condition_id", condition_ids)
            .gte("captured_at", start_date)
            .lte("captured_at", latest_market_date)
            .order("captured_at", desc=True)
            .order("id", desc=True),
        )
        for row in rows:
            variant_id = first_non_empty(row.get("card_variant_id"))
            condition_id = first_non_empty(row.get("condition_id"))
            price = to_optional_float(row.get("market_price"))
            source_date = parse_date_key(row.get("captured_at"))
            if (
                not variant_id
                or not source_date
                or price is None
                or condition_id != condition_by_variant.get(variant_id)
            ):
                continue
            card_id = variant_to_card.get(variant_id)
            if card_id:
                observations_by_card.setdefault(card_id, []).append(
                    {**row, "market_price": price, "source_date": source_date}
                )
    for rows in observations_by_card.values():
        rows.sort(key=lambda row: (row["source_date"], first_non_empty(row.get("captured_at")) or ""))
    return observations_by_card


def _latest_market_date_for_set(client: Any, set_id: str) -> Optional[str]:
    try:
        rows = _query_rows(
            client,
            "pokemon_set_value_daily_history",
            lambda query: query.select("snapshot_date")
            .eq("set_id", set_id)
            .order("snapshot_date", desc=True)
            .limit(1),
        )
        return parse_date_key((rows[0] if rows else {}).get("snapshot_date"))
    except Exception as exc:
        if is_transient_data_service_error(exc):
            raise
        logger.warning("[pokemon-snapshot] latest market date lookup failed set_id=%s", set_id, exc_info=True)
        return None


def _last_observation_on_or_before(rows: List[Dict[str, Any]], boundary: str) -> Optional[Dict[str, Any]]:
    matches = [row for row in rows if row.get("source_date") and row["source_date"] <= boundary]
    return matches[-1] if matches else None


def _movement_contract(
    *,
    price: Dict[str, Any],
    observations: List[Dict[str, Any]],
    latest_market_date: str,
    window_days: int,
) -> Dict[str, Any]:
    return calculate_pokemon_card_market_delta(
        observations=observations,
        selected_current_price=price.get("market_price"),
        selected_variant_id=price.get("variant_id"),
        selected_condition_id=price.get("condition_id"),
        latest_market_date=latest_market_date,
        requested_window_days=window_days,
        selected_current_source_date=price.get("captured_at"),
        selected_current_source=price.get("source"),
    )


def _enrich_cards_with_authoritative_prices_and_movements(
    payload: Dict[str, Any],
    *,
    set_id: str,
    prices_by_card: Dict[str, Dict[str, Any]],
    client: Any,
) -> Dict[str, Any]:
    price_dates = [utc_date_key(price.get("captured_at")) for price in prices_by_card.values()]
    available_price_dates = [date_key for date_key in price_dates if date_key]
    latest_market_date = None
    if available_price_dates:
        latest_market_date = max(available_price_dates)
    elif prices_by_card:
        latest_market_date = _latest_market_date_for_set(client, set_id)
    observations_by_card = (
        _load_selected_price_observations(
            client,
            prices_by_card=prices_by_card,
            latest_market_date=latest_market_date,
        )
        if latest_market_date
        else {}
    )
    cards: List[Dict[str, Any]] = []
    for card in payload.get("cards") or []:
        enriched = dict(card)
        card_id = first_non_empty(card.get("id"), card.get("cardId"), card.get("card_id"))
        price = prices_by_card.get(card_id or "")
        if price and to_optional_float(price.get("market_price")) is not None:
            observations = observations_by_card.get(card_id or "", [])
            # The canonical selected-price view owns public identity and the
            # current price. Raw observations supply baselines only.
            effective_price = dict(price)
            market_price = round(to_optional_float(effective_price.get("market_price")) or 0, 2)
            source_date = parse_date_key(effective_price.get("captured_at"))
            enriched.update(
                {
                    "marketPrice": market_price,
                    "market_price": market_price,
                    "currentPrice": market_price,
                    "current_price": market_price,
                    "cardVariantId": price.get("variant_id"),
                    "card_variant_id": price.get("variant_id"),
                    "conditionId": price.get("condition_id"),
                    "condition_id": price.get("condition_id"),
                    "printingType": price.get("printing_type"),
                    "printing_type": price.get("printing_type"),
                    "priceUpdatedAt": source_date,
                    "price_updated_at": source_date,
                    "priceSourceDate": source_date,
                    "price_source_date": source_date,
                    "marketDate": latest_market_date,
                    "market_date": latest_market_date,
                    "priceCarriedForward": bool(source_date and latest_market_date and source_date < latest_market_date),
                    "price_carried_forward": bool(source_date and latest_market_date and source_date < latest_market_date),
                    "priceSource": effective_price.get("source"),
                    "price_source": effective_price.get("source"),
                    "priceSelectionReason": price.get("price_selection_reason"),
                    "price_selection_reason": price.get("price_selection_reason"),
                }
            )
            if latest_market_date:
                for window_days in (7, 30):
                    movement = _movement_contract(
                        price=effective_price,
                        observations=observations,
                        latest_market_date=latest_market_date,
                        window_days=window_days,
                    )
                    suffix = f"{window_days}d"
                    enriched[f"movement{suffix}"] = movement
                    enriched[f"movement_{suffix}"] = {
                        "window": movement["window"],
                        "window_days": movement["windowDays"],
                        "window_convention": movement["windowConvention"],
                        "target_start_date": movement["targetStartDate"],
                        "start_date": movement["startDate"],
                        "end_date": movement["endDate"],
                        "starting_price": movement["startingPrice"],
                        "current_price": movement["currentPrice"],
                        "change_amount": movement["changeAmount"],
                        "change_percent": movement["changePercent"],
                        "enough_history": movement["enoughHistory"],
                        "reliable": movement["reliable"],
                        "reliability": movement["reliability"],
                        "full_window_coverage": movement["fullWindowCoverage"],
                        "is_partial_window": movement["isPartialWindow"],
                        "window_coverage_days": movement["windowCoverageDays"],
                        "requested_window_days": movement["requestedWindowDays"],
                        "start_source_date": movement["startSourceDate"],
                        "end_source_date": movement["endSourceDate"],
                        "start_carried_forward": movement["startCarriedForward"],
                        "end_carried_forward": movement["endCarriedForward"],
                        "card_variant_id": movement["cardVariantId"],
                        "condition_id": movement["conditionId"],
                        "source": movement["source"],
                        "history_point_count": movement["historyPointCount"],
                    }
                    enriched[f"change{suffix}Amount"] = movement["changeAmount"]
                    enriched[f"change{suffix}Percent"] = movement["changePercent"]
                    enriched[f"movement{suffix}Reliable"] = movement["reliable"]
                    enriched[f"change_{suffix}_amount"] = movement["changeAmount"]
                    enriched[f"change_{suffix}_percent"] = movement["changePercent"]
                    enriched[f"movement_{suffix}_reliable"] = movement["reliable"]
        cards.append(enriched)
    meta = dict(payload.get("meta") or {})
    meta["pricingContract"] = {
        "source": "pokemon_canonical_card_market_prices_latest+card_variant_price_observations",
        "latestMarketDate": latest_market_date,
        "windowConvention": WINDOW_CONVENTION,
    }
    return {**payload, "cards": cards, "meta": meta}


def _with_cards_pricing_contract_diagnostics(payload: Dict[str, Any]) -> Dict[str, Any]:
    cards = list(payload.get("cards") or [])

    def has_delta(card: Dict[str, Any], suffix: str) -> bool:
        return bool(
            to_optional_float(card.get(f"change{suffix}Amount")) is not None
            or to_optional_float(card.get(f"change{suffix}Percent")) is not None
        )

    priced_cards = [card for card in cards if to_optional_float(card.get("marketPrice")) is not None]
    cards_with_7d_delta = sum(1 for card in priced_cards if has_delta(card, "7d"))
    cards_with_30d_delta = sum(1 for card in priced_cards if has_delta(card, "30d"))
    full_7d = sum(
        1
        for card in priced_cards
        if has_delta(card, "7d") and bool((card.get("movement7d") or {}).get("fullWindowCoverage"))
    )
    full_30d = sum(
        1
        for card in priced_cards
        if has_delta(card, "30d") and bool((card.get("movement30d") or {}).get("fullWindowCoverage"))
    )
    partial_7d = sum(
        1
        for card in priced_cards
        if has_delta(card, "7d") and bool((card.get("movement7d") or {}).get("isPartialWindow"))
    )
    partial_30d = sum(
        1
        for card in priced_cards
        if has_delta(card, "30d") and bool((card.get("movement30d") or {}).get("isPartialWindow"))
    )
    meta = dict(payload.get("meta") or {})
    contract = dict(meta.get("pricingContract") or {})
    contract.update(
        {
            "canonicalCardCount": len(cards),
            "pricedCardCount": len(priced_cards),
            "cardsWith7dDelta": cards_with_7d_delta,
            "cardsWith30dDelta": cards_with_30d_delta,
            "cardsWithFull7dCoverage": full_7d,
            "cardsWithFull30dCoverage": full_30d,
            "cardsWithPartial7dDelta": partial_7d,
            "cardsWithPartial30dDelta": partial_30d,
            "cardsMissingUsableHistory": len(priced_cards) - cards_with_30d_delta,
        }
    )
    meta["pricingContract"] = contract
    if priced_cards and cards_with_30d_delta == 0:
        warning = "Priced cards are present but no usable 30D card deltas were produced."
        warnings = list(meta.get("warnings") or [])
        if warning not in warnings:
            warnings.append(warning)
        meta["warnings"] = warnings
        logger.warning(
            "[pokemon-snapshot] priced cards without usable 30D deltas priced=%s canonical=%s",
            len(priced_cards),
            len(cards),
        )
    return {**payload, "cards": cards, "meta": meta}


def build_cards_snapshot_row(
    set_row: Dict[str, Any],
    *,
    client: Any = None,
    generation_id: Optional[str] = None,
    built_at: Optional[str] = None,
    selected_price_rows: Optional[List[Dict[str, Any]]] = None,
) -> Dict[str, Any]:
    set_id = str(set_row["id"])
    client = client or get_client()
    generation_id = generation_id or str(uuid4())
    built_at = built_at or utc_now_iso()
    payload = get_pokemon_set_cards_payload(set_id)
    prices_by_card = _build_card_appeal_price_index_for_set(
        set_id=set_id,
        canonical_cards=list(payload.get("cards") or []),
        client=client,
        selected_price_rows=selected_price_rows,
    )
    payload = _enrich_cards_with_authoritative_prices_and_movements(
        payload,
        set_id=set_id,
        prices_by_card=prices_by_card,
        client=client,
    )
    payload = enrich_cards_payload_with_desirability(payload, prices_by_card=prices_by_card)
    payload = _with_cards_pricing_contract_diagnostics(payload)
    selected_market_dates = [
        date_key
        for price in prices_by_card.values()
        if (date_key := utc_date_key(price.get("captured_at")))
    ]
    pricing_contract = (payload.get("meta") or {}).get("pricingContract") or {}
    movement_as_of_date = first_non_empty(
        pricing_contract.get("latestMarketDate"),
        max(selected_market_dates, default=None),
    )
    movement_metadata = {
        "movementContractVersion": MOVEMENT_CONTRACT_VERSION,
        "windowConvention": WINDOW_CONVENTION,
        "movementAsOfDate": movement_as_of_date,
        "marketAsOfDate": movement_as_of_date,
        "generationId": generation_id,
        "builtAt": built_at,
    }
    cards = [
        {
            **card,
            "movementMetadata": movement_metadata,
            "movement_metadata": movement_metadata,
        }
        for card in list(payload.get("cards") or [])
    ]
    payload = {**payload, "cards": cards}
    payload = with_snapshot_meta(
        payload,
        snapshot_type="pokemon_set_cards",
        built_at=built_at,
        generation_id=generation_id,
        movement_as_of_date=movement_as_of_date,
    )
    return {
        "set_id": set_id,
        "cards_json": cards,
        "payload_json": payload,
        "card_count": len(cards),
    }


class PokemonSnapshotMovementParityError(RuntimeError):
    """Raised before writes when coordinated movement contracts disagree."""

    def __init__(self, set_id: str, mismatches: List[Dict[str, Any]]):
        self.set_id = set_id
        self.mismatches = mismatches
        super().__init__(
            f"Pokemon movement parity failed for set_id={set_id}: "
            f"{len(mismatches)} mismatch(es)"
        )


def validate_coordinated_movement_parity(
    cards_row: Dict[str, Any],
    dashboard_row: Dict[str, Any],
) -> None:
    """Reject a dashboard snapshot when any overlapping movement differs."""
    from backend.scripts.audit_pokemon_card_delta_parity import audit_payloads

    set_id = str(cards_row.get("set_id") or dashboard_row.get("set_id") or "")
    mismatches = audit_payloads(
        cards_row.get("cards_json") or [],
        dashboard_row.get("payload_json") or {},
        set_id=set_id,
    )
    if mismatches:
        logger.error(
            "[pokemon-snapshot] coordinated movement parity failed set_id=%s mismatches=%s sample=%s",
            set_id,
            len(mismatches),
            mismatches[:5],
        )
        raise PokemonSnapshotMovementParityError(set_id, mismatches)


def build_coordinated_set_market_snapshot_rows(
    set_row: Dict[str, Any],
    *,
    days: int = DEFAULT_DASHBOARD_DAYS,
    window: str = DEFAULT_DASHBOARD_WINDOW,
    client: Any = None,
) -> tuple[Dict[str, Any], Dict[str, Any], List[Dict[str, Any]]]:
    """Build Cards and Dashboard from one refreshed client/generation boundary."""
    client = client or get_client()
    generation_id = str(uuid4())
    built_at = utc_now_iso()
    set_id = str(set_row["id"])
    selected_price_rows = _query_rows(
        client,
        "pokemon_canonical_card_market_prices_latest",
        lambda query: query.select(
            "canonical_card_id,set_id,card_variant_id,condition_id,printing_type,market_price,"
            "captured_at,source,price_selection_reason,refreshed_at"
        ).eq("set_id", set_id),
    )
    cards_row = build_cards_snapshot_row(
        set_row,
        client=client,
        generation_id=generation_id,
        built_at=built_at,
        selected_price_rows=selected_price_rows,
    )
    dashboard_row, top_chase_history_rows = build_market_dashboard_snapshot_rows(
        set_row,
        days=days,
        window=window,
        client=client,
        generation_id=generation_id,
        built_at=built_at,
        selected_price_rows=selected_price_rows,
    )
    validate_coordinated_movement_parity(cards_row, dashboard_row)
    return cards_row, dashboard_row, top_chase_history_rows


def build_explore_rankings_snapshot_row(*, limit: int = DEFAULT_RANKINGS_LIMIT) -> Dict[str, Any]:
    built_at = utc_now_iso()
    payload = get_rip_statistics_targets_payload(limit=limit)
    targets = list(payload.get("targets") or [])
    opening_targets = [target for target in targets if is_opening_set_row(target)]
    meta = dict(payload.get("meta") or {})
    opening_set_audit = build_opening_set_audit(targets)
    meta["snapshot"] = {
        "type": "pokemon_explore_rankings",
        "builtAt": built_at,
        "source": "pokemon_snapshot_builders",
    }
    meta["openingSetAudit"] = opening_set_audit
    meta["opening_set_audit"] = opening_set_audit
    payload = {**payload, "targets": opening_targets, "meta": meta}

    # A desirability read that FAILED renders every set "unavailable". Publishing
    # that overwrites good stored rows with a statement about the sets that the
    # failure never justified - and it looks exactly like a successful build, so
    # nothing downstream can tell it apart. Refuse instead: the previous snapshot
    # stays served, and the non-zero exit is the signal.
    if meta.get("desirabilityBundleStatus") != "ok":
        raise RuntimeError(
            "Refusing to publish the Explore rankings snapshot: the Universal Set "
            "Desirability bundle failed to build, so every set would be published "
            "as desirability-unavailable. The previous snapshot is left in place. "
            "Re-run once the source reads succeed."
        )

    comparison_diagnostics = meta.get("ripDesirabilityComparison") or meta.get("rip_desirability_comparison") or {}
    logger.info(
        "[pokemon-snapshot] RIP desirability comparison valid=%s/%s opening_targets=%s",
        comparison_diagnostics.get("valid_comparison_count"),
        comparison_diagnostics.get("total_sets"),
        len(opening_targets),
    )
    return {
        "tcg": "pokemon",
        "scope": "rip-statistics",
        "ranking_payload_json": payload,
        "default_target_json": payload.get("default_target") or {},
    }


def upsert_row(client: Any, table: str, row: Dict[str, Any], *, on_conflict: str, commit: bool) -> None:
    if not commit:
        logger.info("[dry-run] would upsert %s conflict=%s keys=%s", table, on_conflict, sorted(row.keys()))
        return
    for attempt in range(3):
        try:
            client.table(table).upsert(
                row,
                on_conflict=on_conflict,
                returning=ReturnMethod.minimal,
            ).execute()
            break
        except Exception as exc:
            if "57014" not in str(exc) and "statement timeout" not in str(exc).lower():
                raise
            if attempt == 2:
                raise
            delay = 2 ** attempt
            logger.warning(
                "statement timeout upserting %s; retrying in %ss (%s/3)",
                table,
                delay,
                attempt + 1,
            )
            time.sleep(delay)
    logger.info("upserted %s conflict=%s", table, on_conflict)


def upsert_rows(
    client: Any,
    table: str,
    rows: List[Dict[str, Any]],
    *,
    on_conflict: str,
    commit: bool,
    batch_size: int = DEFAULT_UPSERT_BATCH_SIZE,
) -> None:
    if not rows:
        logger.info("no rows for %s", table)
        return
    if not commit:
        logger.info("[dry-run] would upsert %s rows into %s conflict=%s", len(rows), table, on_conflict)
        return
    safe_batch_size = max(1, int(batch_size or DEFAULT_UPSERT_BATCH_SIZE))
    for start in range(0, len(rows), safe_batch_size):
        batch = rows[start : start + safe_batch_size]
        client.table(table).upsert(batch, on_conflict=on_conflict).execute()
        logger.info(
            "upserted %s/%s rows into %s conflict=%s",
            min(start + len(batch), len(rows)),
            len(rows),
            table,
            on_conflict,
        )
    logger.info("upserted %s rows into %s", len(rows), table)


def get_client() -> Any:
    load_backend_env()
    return create_service_role_client()


@contextmanager
def snapshot_service_client_scope(client: Any):
    """Route offline service reads through the fresh client for this attempt."""

    from backend.db.services import explore_page_service
    from backend.db.services import explore_rip_statistics_service
    from backend.db.services import pokemon_public_snapshot_service
    from backend.db.services import pokemon_set_cards_service
    from backend.db.services import pokemon_set_market_service
    from backend.db.services import set_desirability_service

    modules = (
        explore_page_service,
        explore_rip_statistics_service,
        pokemon_public_snapshot_service,
        pokemon_set_cards_service,
        pokemon_set_market_service,
        set_desirability_service,
    )
    previous = [(module, getattr(module, "public_read_client", None)) for module in modules]
    try:
        for module, _old_client in previous:
            if hasattr(module, "public_read_client"):
                module.public_read_client = client
        yield
    finally:
        for module, old_client in previous:
            if hasattr(module, "public_read_client"):
                module.public_read_client = old_client
