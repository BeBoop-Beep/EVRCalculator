"""Service for RIP Statistics target discovery and default target selection."""

from __future__ import annotations

import json
import logging
import math
import time
from datetime import date, timedelta
from typing import Any, Dict, Iterable, List, Mapping, Optional, Tuple

from backend.db.clients.supabase_client import public_read_client
from backend.db.services.collector_appeal_service import get_collector_appeal_bundle
from backend.db.services.public_read_retry import run_batch_read_with_retry
from backend.db.services.rip_desirability_comparison import build_rip_desirability_comparison_payload
from backend.db.services.universal_set_desirability_service import (
    get_universal_desirability_bundle,
    public_payload as universal_public_payload,
)
from backend.desirability.public_analytics_policy import (
    OVERALL_RANKED_CA7_VERSION_MISMATCH,
    PublicCohortIntegrityError,
    assert_cohort_integrity,
    audit_overall_ranked_cohort,
    build_public_cohort,
    public_analytics_status,
)
from backend.desirability.scoring_config import (
    CANONICAL_FINANCIAL_RIP_VERSION,
    CANONICAL_OVERALL_RIP_VERSION,
    FINANCIAL_RIP_V2_VERSION,
    FINANCIAL_RIP_WEIGHTS,
    OVERALL_RIP_EFFECTIVE_WEIGHTS,
    OVERALL_RIP_V4_VERSION,
    OVERALL_RIP_V6_VERSION,
    OVERALL_RIP_V7_EFFECTIVE_WEIGHTS,
    OVERALL_RIP_V7_VERSION,
    OVERALL_RIP_V7_WEIGHTS,
    OVERALL_RIP_V8_EFFECTIVE_WEIGHTS,
    OVERALL_RIP_V8_VERSION,
    OVERALL_RIP_V8_WEIGHTS,
    OVERALL_RIP_V9_EFFECTIVE_WEIGHTS,
    OVERALL_RIP_V9_VERSION,
    OVERALL_RIP_V9_WEIGHTS,
    OVERALL_RIP_WEIGHTS,
    WEIGHTS_DISCLOSURE,
    canonical_public_rip_contract_version,
)
from backend.desirability.public_rip_contract_v4 import (
    PUBLIC_RIP_CONTRACT_V4_KEY,
    build_public_rip_contract_v4,
)
from backend.desirability.public_rip_contract_v5 import (
    PUBLIC_RIP_CONTRACT_V5_KEY,
    build_public_rip_contract_v5,
)
from backend.desirability.public_rip_contract_v6 import (
    PUBLIC_RIP_CONTRACT_V6_KEY,
    build_public_rip_contract_v6,
)
from backend.desirability.public_rip_contract_v8 import (
    PUBLIC_RIP_CONTRACT_V8_KEY,
    build_public_rip_contract_v8,
)
from backend.desirability.public_rip_contract_v9 import (
    PUBLIC_RIP_CONTRACT_V9_KEY,
    build_public_rip_contract_v9,
)
from backend.desirability.public_rip_contract_v7 import (
    PUBLIC_RIP_CONTRACT_V7_KEY,
    build_public_rip_contract_v7,
)
from backend.desirability.collector_appeal import (
    COLLECTOR_APPEAL_CA7_VERSION,
    COLLECTOR_APPEAL_V2_VERSION,
    COLLECTOR_APPEAL_V3_VERSION,
    COLLECTOR_APPEAL_V4_VERSION,
    COLLECTOR_APPEAL_V5_VERSION,
)
from backend.calculations.evr.financial_rip_v3_config import (
    FINANCIAL_RIP_V3_COMPONENT_ORDER,
    FINANCIAL_RIP_V3_NORMALIZATION_VERSION,
    FINANCIAL_RIP_V3_VERSION,
)
from backend.desirability.universal_set_desirability import assess_simulation_coverage
from backend.desirability.weighted_rip import (
    compute_financial_rip,
    compute_financial_rip_v3,
    compute_overall_rip,
    compute_overall_rip_v5,
    compute_overall_rip_v6,
    compute_overall_rip_v7,
    compute_overall_rip_v8,
    compute_overall_rip_v9,
)
from backend.interpretation.rips import build_rip_interpretation

logger = logging.getLogger(__name__)

DEFAULT_TARGETS_LIMIT = 100
MAX_TARGETS_LIMIT = 200
MIN_LIMIT = 1

_BIGGEST_UPSIDE_P95_CAP = 5.0
_BIGGEST_UPSIDE_P99_CAP = 10.0
_BIGGEST_UPSIDE_P95_WEIGHT = 0.70
_BIGGEST_UPSIDE_P99_WEIGHT = 0.30
_SET_VALUE_HISTORY_SCOPE = "standard"
_SET_VALUE_HISTORY_CHUNK_SIZE = 50
_SET_VALUE_HISTORY_DAYS_PER_SET_LIMIT = 45
_CANONICAL_PRICE_PAGE_SIZE = 1000
_PUBLISHED_DATE_LOOKBACK = 30


class ExploreRipStatisticsTargetsError(Exception):
    """Structured error for RIP Statistics target discovery."""

    def __init__(
        self,
        status_code: int,
        message: str,
        code: str,
        *,
        retry_after_seconds: Optional[int] = None,
    ):
        self.status_code = status_code
        self.message = message
        self.code = code
        self.retry_after_seconds = retry_after_seconds
        super().__init__(message)


def _sanitize_limit(value: Any, *, default: int, max_value: int) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return default
    if parsed < MIN_LIMIT:
        return MIN_LIMIT
    if parsed > max_value:
        return max_value
    return parsed


def _to_optional_float(value: Any) -> Optional[float]:
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return None
    return parsed


def _to_optional_str(value: Any) -> Optional[str]:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _chunks(values: List[str], size: int) -> Iterable[List[str]]:
    for index in range(0, len(values), size):
        yield values[index:index + size]


def _load_opening_desirability_lookup(
    set_ids: List[str],
    *,
    sources: Dict[str, str],
    warnings: List[str],
) -> Dict[str, Dict[str, Any]]:
    unique_set_ids = sorted({_to_optional_str(set_id) for set_id in set_ids if _to_optional_str(set_id)})
    if not unique_set_ids:
        sources["pokemon_set_opening_desirability_latest"] = "SKIPPED"
        return {}
    try:
        result = (
            public_read_client.table("pokemon_set_opening_desirability_latest")
            .select(
                "set_id,set_name,set_canonical_key,opening_desirability_score,opening_desirability_rank,"
                "collector_appeal_score,collector_appeal_rank,opening_desirability_display_status,"
                "opening_desirability_summary,source_v2_component_row_id,source_rip_calculation_run_id,"
                "scoring_version,built_at"
            )
            .in_("set_id", unique_set_ids)
            .eq("opening_desirability_display_status", "scored")
            .execute()
        )
        lookup = {
            str(row["set_id"]): row
            for row in (result.data or [])
            if row.get("set_id") and _to_optional_float(row.get("opening_desirability_score")) is not None
        }
        sources["pokemon_set_opening_desirability_latest"] = "OK"
        return lookup
    except Exception as exc:
        logger.warning("[rip-statistics-targets] opening desirability enrichment failed: %s", exc)
        warnings.append("Failed to load opening desirability for one or more RIP targets")
        sources["pokemon_set_opening_desirability_latest"] = "FAILED"
        return {}


def _load_top_10_card_value_lookup(
    set_ids: List[str],
    *,
    sources: Dict[str, str],
    warnings: List[str],
) -> Dict[str, Dict[str, Any]]:
    unique_set_ids = sorted({_to_optional_str(set_id) for set_id in set_ids if _to_optional_str(set_id)})
    if not unique_set_ids:
        sources["pokemon_canonical_card_market_prices_latest"] = "SKIPPED"
        return {}

    rows_by_set: Dict[str, List[Dict[str, Any]]] = {set_id: [] for set_id in unique_set_ids}
    try:
        for chunk in _chunks(unique_set_ids, _SET_VALUE_HISTORY_CHUNK_SIZE):
            start = 0
            while True:
                result = (
                    public_read_client.table("pokemon_canonical_card_market_prices_latest")
                    .select("set_id,canonical_card_id,market_price,captured_at,source,price_selection_reason")
                    .in_("set_id", chunk)
                    .order("set_id", desc=False)
                    .order("market_price", desc=True)
                    .order("canonical_card_id", desc=False)
                    .range(start, start + _CANONICAL_PRICE_PAGE_SIZE - 1)
                    .execute()
                )
                page = list(result.data or [])
                for row in page:
                    set_id = _to_optional_str(row.get("set_id"))
                    if set_id in rows_by_set:
                        rows_by_set[set_id].append(row)
                if len(page) < _CANONICAL_PRICE_PAGE_SIZE:
                    break
                start += _CANONICAL_PRICE_PAGE_SIZE

        lookup: Dict[str, Dict[str, Any]] = {}
        for set_id, rows in rows_by_set.items():
            priced_rows = [
                row
                for row in rows
                if _to_optional_float(row.get("market_price")) is not None
                and _to_optional_float(row.get("market_price")) >= 0
            ]
            priced_rows.sort(
                key=lambda row: (
                    -(_to_optional_float(row.get("market_price")) or 0.0),
                    str(row.get("canonical_card_id") or ""),
                )
            )
            selected = priced_rows[:10]
            lookup[set_id] = {
                "top_10_card_value": round(
                    sum(_to_optional_float(row.get("market_price")) or 0.0 for row in selected),
                    2,
                ) if selected else None,
                "top_10_card_value_sample_size": len(selected),
                "top_10_card_value_priced_card_count": len(priced_rows),
                "top_10_card_value_candidate_card_count": len(rows),
                "top_10_card_value_unavailable_price_count": len(rows) - len(priced_rows),
                "top_10_card_value_coverage": round(min(len(selected), 10) / 10.0, 2),
                "top_10_card_value_source": "pokemon_canonical_card_market_prices_latest",
                "top_10_card_value_price_as_of": max(
                    (str(row.get("captured_at")) for row in selected if row.get("captured_at")),
                    default=None,
                ),
            }
        sources["pokemon_canonical_card_market_prices_latest"] = "OK"
        return lookup
    except Exception as exc:
        logger.warning("[rip-statistics-targets] Top 10 Card Value enrichment failed: %s", exc)
        warnings.append("Failed to load canonical card prices for one or more RIP targets")
        sources["pokemon_canonical_card_market_prices_latest"] = "FAILED"
        return {}


def _rank_top_10_card_values(targets: List[Dict[str, Any]]) -> None:
    sortable = [
        target
        for target in targets
        if _to_optional_float(target.get("top_10_card_value")) is not None
    ]
    sortable.sort(
        key=lambda target: (
            -(_to_optional_float(target.get("top_10_card_value")) or 0.0),
            str(target.get("target_id") or ""),
        )
    )
    for rank, target in enumerate(sortable, start=1):
        target["top_10_card_value_rank"] = rank


def _build_rip_core_interpretation(target: Dict[str, Any]) -> Dict[str, Any]:
    core_summary = dict(target)
    core_summary.update(
        {
            "pack_score": target.get("rip_score_without_desirability"),
            "relative_pack_score": target.get("relative_rip_core_score"),
            "pack_rank": target.get("rip_rank_without_desirability"),
            "pack_tier": target.get("rip_core_tier"),
            "desirability_score": None,
            "relative_desirability_score": None,
            "desirability_rank": None,
            "desirability_tier": None,
        }
    )
    try:
        interpretation = build_rip_interpretation({"summary": core_summary})
        pack_meta = ((interpretation or {}).get("meta") or {}).get("packScore") or {}
        return {
            "label": _to_optional_str(pack_meta.get("label")),
            "summary": _to_optional_str(pack_meta.get("summary")) or _to_optional_str(interpretation.get("packScore")),
            "severity": _to_optional_str(pack_meta.get("severity")),
            "reason_code": _to_optional_str(pack_meta.get("reason_code")),
        }
    except Exception:
        logger.warning("[rip-statistics-targets] failed to build RIP Core interpretation target=%s", target.get("target_id"))
        return {"label": None, "summary": None, "severity": None, "reason_code": None}


def _load_complete_published_snapshot_dates(
    *, sources: Dict[str, str], warnings: List[str]
) -> Tuple[Optional[str], Optional[str]]:
    """Select the newest two distinct complete, promoted market dates."""
    try:
        result = (
            public_read_client.table("pokemon_scrape_batches")
            .select("market_date,status,promoted_at,missing_set_count,expected_set_count")
            .order("market_date", desc=True)
            .limit(_PUBLISHED_DATE_LOOKBACK)
            .execute()
        )
        dates: List[str] = []
        for row in result.data or []:
            try:
                missing = int(row.get("missing_set_count"))
                expected = int(row.get("expected_set_count"))
            except (TypeError, ValueError):
                continue
            market_date = _to_optional_str(row.get("market_date"))
            if (
                market_date
                and str(row.get("status") or "").lower() == "complete"
                and row.get("promoted_at")
                and missing == 0
                and expected > 0
                and market_date[:10] not in dates
            ):
                dates.append(market_date[:10])
            if len(dates) == 2:
                break
        sources["pokemon_scrape_batches"] = "OK"
        if len(dates) < 2:
            warnings.append("No distinct previous complete published market snapshot is available")
        return (dates[0] if dates else None, dates[1] if len(dates) > 1 else None)
    except Exception as exc:
        logger.warning("[rip-statistics-targets] published market date lookup failed: %s", exc)
        warnings.append("Failed to resolve complete published market snapshot dates")
        sources["pokemon_scrape_batches"] = "FAILED"
        return None, None


def _load_current_checklist_set_value_lookup(
    set_ids: List[str],
    *,
    current_snapshot_date: Optional[str] = None,
    sources: Dict[str, str],
    warnings: List[str],
) -> Dict[str, Dict[str, Any]]:
    """Load latest canonical checklist set value rows for Explore validation targets."""

    unique_set_ids = sorted({_to_optional_str(set_id) for set_id in set_ids if _to_optional_str(set_id)})
    if not unique_set_ids:
        sources["pokemon_set_value_daily_history"] = "SKIPPED"
        return {}

    started = time.perf_counter()
    latest_by_set_id: Dict[str, Dict[str, Any]] = {}
    rows_by_set_id: Dict[str, List[Dict[str, Any]]] = {}
    try:
        for chunk in _chunks(unique_set_ids, _SET_VALUE_HISTORY_CHUNK_SIZE):
            result = (
                public_read_client.table("pokemon_set_value_daily_history")
                .select("set_id,snapshot_date,set_value,priced_card_count,total_card_count,source")
                .in_("set_id", chunk)
                .eq("value_scope", _SET_VALUE_HISTORY_SCOPE)
                .order("snapshot_date", desc=True)
                .limit(max(len(chunk) * _SET_VALUE_HISTORY_DAYS_PER_SET_LIMIT, len(chunk)))
                .execute()
            )
            for row in result.data or []:
                set_id = _to_optional_str(row.get("set_id"))
                if not set_id:
                    continue
                value = _to_optional_float(row.get("set_value"))
                if value is None or value <= 0:
                    continue
                rows_by_set_id.setdefault(set_id, []).append(row)
        for set_id, rows in rows_by_set_id.items():
            by_date = {str(row.get("snapshot_date") or "")[:10]: row for row in rows}
            current = by_date.get(current_snapshot_date or "")
            if current is None:
                continue
            latest = dict(current)
            latest_by_set_id[set_id] = latest
            try:
                comparison_date = (date.fromisoformat(str(current_snapshot_date)[:10]) - timedelta(days=7)).isoformat()
            except (TypeError, ValueError):
                latest["comparison_status_7d"] = "unavailable"
                continue
            previous = by_date.get(comparison_date)
            if previous is None:
                latest["comparison_status_7d"] = "new"
            else:
                latest["previous_set_value_7d"] = _to_optional_float(previous.get("set_value"))
                latest["previous_set_value_date_7d"] = comparison_date
                latest["comparison_status_7d"] = "available"

        sources["pokemon_set_value_daily_history"] = "OK"
        logger.info(
            "[rip-statistics-targets] loaded checklist set values matched=%s/%s in %.1fms",
            len(latest_by_set_id),
            len(unique_set_ids),
            (time.perf_counter() - started) * 1000,
        )
    except Exception as exc:
        logger.warning("[rip-statistics-targets] checklist set value enrichment failed: %s", exc)
        warnings.append("Failed to load checklist set value data for one or more RIP targets")
        sources["pokemon_set_value_daily_history"] = "FAILED"
        return {}

    return latest_by_set_id


def _resolve_mean_value_to_cost_ratio(row: Dict[str, Any]) -> Optional[float]:
    ratio = _to_optional_float(row.get("mean_value_to_cost_ratio"))
    if ratio is not None:
        return ratio

    mean_value = _to_optional_float(row.get("mean_value"))
    pack_cost = _to_optional_float(row.get("pack_cost"))
    if mean_value is None or pack_cost is None or pack_cost <= 0:
        return None
    return mean_value / pack_cost


def _blend_biggest_upside_score(
    p95_value_to_cost_ratio: Optional[float],
    p99_value_to_cost_ratio: Optional[float],
) -> Optional[float]:
    """Blend Strong Upside (P95) and Jackpot Upside (P99) into a 0-100 score."""

    p95 = _to_optional_float(p95_value_to_cost_ratio)
    p99 = _to_optional_float(p99_value_to_cost_ratio)
    if p95 is None and p99 is None:
        return None

    def _normalize(raw: Optional[float], cap: float) -> float:
        if raw is None:
            return 0.0
        bounded = min(max(raw, 0.0), cap)
        return (bounded / cap) * 100.0

    norm_p95 = _normalize(p95, _BIGGEST_UPSIDE_P95_CAP)
    norm_p99 = _normalize(p99, _BIGGEST_UPSIDE_P99_CAP)
    return (_BIGGEST_UPSIDE_P95_WEIGHT * norm_p95) + (_BIGGEST_UPSIDE_P99_WEIGHT * norm_p99)


def _compute_relative_scores(rows: List[Dict[str, Any]], score_key: str) -> Dict[str, Optional[float]]:
    """Compute 0-100 relative scores for a score field across current rows."""

    scored_rows = [
        (str(row.get("target_id")), _to_optional_float(row.get(score_key)))
        for row in rows
        if row.get("target_id")
    ]
    valid_scores = [score for _, score in scored_rows if score is not None]
    if not valid_scores:
        return {target_id: None for target_id, _ in scored_rows}

    score_min = min(valid_scores)
    score_max = max(valid_scores)
    if score_max <= score_min:
        return {
            target_id: (50.0 if score is not None else None)
            for target_id, score in scored_rows
        }

    return {
        target_id: (100.0 * ((score - score_min) / (score_max - score_min)) if score is not None else None)
        for target_id, score in scored_rows
    }


def _shorten_canonical_label(value: Optional[str]) -> Optional[str]:
    if value is None:
        return None

    text = str(value).strip()
    if not text:
        return None

    for separator in (",", " - ", " — "):
        if separator in text:
            head = text.split(separator, 1)[0].strip()
            return head or text
    return text


def _build_recommendation_labels(summary_row: Dict[str, Any]) -> tuple[Optional[str], Optional[str], Optional[str]]:
    try:
        interpretation = build_rip_interpretation(summary_row)
    except Exception:
        logger.warning("[rip-statistics-targets] failed to build interpretation for target row")
        return None, None, None

    pack_score_meta = ((interpretation or {}).get("meta") or {}).get("packScore") or {}
    canonical_header = _to_optional_str(pack_score_meta.get("label"))
    quick_label = _shorten_canonical_label(canonical_header)
    severity = _to_optional_str(pack_score_meta.get("severity"))
    return canonical_header, quick_label, severity


def _build_rank_sort_key(row: Dict[str, Any]) -> tuple[int, float, str]:
    placeholder = bool(row.get("pack_score_is_placeholder"))
    pack_score = _to_optional_float(row.get("pack_score"))
    run_at = str(row.get("run_at") or "")
    return (
        1 if placeholder else 0,
        -(pack_score if pack_score is not None else float("-inf")),
        run_at,
    )


def _build_set_order_key(target_id: str, set_row: Dict[str, Any]) -> tuple[int, str, int, str, str, str]:
    release_date = _to_optional_str(set_row.get("release_date"))
    pokemon_api_set_id = _to_optional_str(set_row.get("pokemon_api_set_id"))
    set_name = _to_optional_str(set_row.get("name")) or target_id
    return (
        1 if release_date is None else 0,
        release_date or "",
        1 if pokemon_api_set_id is None else 0,
        pokemon_api_set_id or "",
        set_name.casefold(),
        target_id,
    )


def _calculate_score_ranks_and_tiers(
    rows: List[Dict[str, Any]], score_key: str
) -> Dict[str, Dict[str, Any]]:
    """Calculate rank and tier for each row based on a score field.
    
    Args:
        rows: List of target rows with score data
        score_key: The score field name (e.g., 'pack_score', 'profit_score')
    
    Returns:
        Dict mapping target_id to {rank, tier} for that score
    """
    result: Dict[str, Dict[str, Any]] = {}
    
    # Sort rows by score descending (highest score = rank 1)
    scored_rows = [
        (str(row.get("target_id")), _to_optional_float(row.get(score_key)))
        for row in rows
        if row.get("target_id")
    ]
    scored_rows_with_valid_scores = [
        (target_id, score) for target_id, score in scored_rows if score is not None
    ]
    
    if not scored_rows_with_valid_scores:
        # All rows have null scores for this score_key
        for target_id, _ in scored_rows:
            result[target_id] = {"rank": None, "tier": None, "cohortSize": 0}
        return result
    
    # Sort by score descending, breaking exact ties on the target id.
    #
    # Without the tie-break the order of equal scores was whatever order the
    # rows arrived in, so two sets on an identical score could swap ranks
    # between two runs over unchanged data - a rank that moves with no input
    # change is indistinguishable, to a reader, from a real movement. The
    # tie-break cannot reorder any pair with different scores.
    scored_rows_with_valid_scores.sort(key=lambda item: (-item[1], item[0]))
    total = len(scored_rows_with_valid_scores)
    
    # Assign ranks and calculate rank-bucket tiers (mirrors DB view semantics)
    for rank, (target_id, score) in enumerate(scored_rows_with_valid_scores, start=1):
        if rank <= max(1, math.ceil(total * 0.05)):
            tier = "S"
        elif rank <= max(1, math.ceil(total * 0.15)):
            tier = "A"
        elif rank <= max(1, math.ceil(total * 0.30)):
            tier = "B"
        elif rank <= max(1, math.ceil(total * 0.50)):
            tier = "C"
        elif rank <= max(1, math.ceil(total * 0.75)):
            tier = "D"
        else:
            tier = "F"
        
        result[target_id] = {"rank": rank, "tier": tier, "cohortSize": total}
    
    # Rows without scores get None
    for target_id, _ in scored_rows:
        if target_id not in result:
            result[target_id] = {"rank": None, "tier": None, "cohortSize": total}
    
    return result


def _resolve_desirability_key(target: Mapping[str, Any]) -> Optional[str]:
    """The id the desirability bundles are keyed by, for one target row."""
    return _to_optional_str(target.get("set_id")) or _to_optional_str(target.get("target_id"))


def _resolve_collector_payload(
    target: Mapping[str, Any],
    collector_payloads: Mapping[str, Any],
) -> Dict[str, Any]:
    resolved_id = _resolve_desirability_key(target)
    payload = collector_payloads.get(resolved_id or "") or collector_payloads.get(
        str(target.get("target_id") or "")
    )
    return dict(payload) if isinstance(payload, Mapping) else {}


# Which metrics get a public rank, and where each one's score lives on the
# target row. Declared as data so "rank everything the contract exposes" is one
# list to read rather than nine call sites to audit.
# Roster desirability is deliberately absent: Universal Set Desirability carries
# its own ALL-SET rank (rank / rankedSetCount / percentile) from its bundle, and
# it is not simulation-scoped. Ranking it again inside the 21-set simulated
# cohort would publish two different ranks for one score under one product name.
PUBLIC_RANKED_METRICS: Tuple[Tuple[str, str], ...] = (
    ("_rank_rip", "rip"),
    ("_rank_rip_core", "ripCore"),
    ("_rank_profit", "profit"),
    ("_rank_safety", "safety"),
    ("_rank_stability", "stability"),
    ("_rank_collector_appeal", "collectorAppeal"),
    ("_rank_collector_roster_desirability", "collectorAppeal.rosterDesirability"),
    ("_rank_collector_desirable_outcome_frequency", "collectorAppeal.desirableOutcomeFrequency"),
    ("_rank_chase_appeal", "chaseAppeal"),
    ("_rank_dual_path_depth", "dualPathDepth"),
    # Canonical V3/V5 ranks. Ranked by the ABSOLUTE fixed-anchor V3 score, never
    # by a cohort min-max transformation of it: min-maxing before ranking would
    # not change the order but would put a cohort-dependent number under a field
    # whose whole contract is cohort independence.
    ("_rank_financial_rip_v3", "financialRipV3"),
    ("_rank_overall_rip_v5", "overallRipV5"),
    # Superseded, still ranked so the V6-vs-V7 comparison has both orderings.
    ("_rank_overall_rip_v6", "overallRipV6"),
    # The CANONICAL Overall rank, from the absolute 90/10 V7 score.
    ("_rank_overall_rip_v7", "overallRipV7"),
    ("_rank_overall_rip_v8", "overallRipV8"),
    ("_rank_overall_rip_v9", "overallRipV9"),
    *(
        (f"_rank_v3_{component}", f"financialRipV3.{component}")
        for component in FINANCIAL_RIP_V3_COMPONENT_ORDER
    ),
)


# ---------------------------------------------------------------------------
# Financial RIP V3 / Overall RIP V5 objects
# ---------------------------------------------------------------------------

def _parse_v3_payload(raw: Any) -> Dict[str, Any]:
    """Read the persisted V3 audit document off a row.

    Supabase returns JSONB as a dict, but a driver or a view cast can hand back
    a JSON string. Both are accepted; anything else is treated as absent rather
    than coerced into a shape that would then validate against nothing.
    """
    if isinstance(raw, Mapping):
        return dict(raw)
    if isinstance(raw, str) and raw.strip():
        try:
            parsed = json.loads(raw)
        except (TypeError, ValueError):
            return {}
        return dict(parsed) if isinstance(parsed, dict) else {}
    return {}


def _build_financial_rip_v3(target: Mapping[str, Any]) -> Dict[str, Any]:
    """The canonical Financial RIP V3 object for one target.

    Consumes the PERSISTED authoritative payload and validates it. Nothing here
    reinterprets P95, P99, probability-of-profit or any other flattened public
    field: the conditional tail means V3 depends on cannot be reconstructed from
    percentile thresholds, so a "helpful" reconstruction here would be a
    different, unlabelled model.

    A missing, stale-versioned or invalid payload produces an explicit
    unavailable object. It never borrows a Financial RIP V2 number.
    """
    payload = _parse_v3_payload(target.get("financial_rip_v3_payload"))
    run_identity = {
        "calculationRunId": _to_optional_str(target.get("calculation_run_id")),
        "runAt": _to_optional_str(target.get("run_at")),
        "packCost": _to_optional_float(target.get("pack_cost")),
        "simulationCount": _to_optional_float(target.get("financial_rip_v3_simulation_count")),
        "scoreVersion": _to_optional_str(target.get("financial_rip_v3_score_version")),
        "normalizationVersion": _to_optional_str(
            target.get("financial_rip_v3_normalization_version")
        ),
    }

    if not payload:
        return {
            "score": None,
            "scoreVersion": FINANCIAL_RIP_V3_VERSION,
            "normalizationVersion": FINANCIAL_RIP_V3_NORMALIZATION_VERSION,
            "status": "unavailable",
            "statusReason": "no_financial_rip_v3_payload_on_latest_run",
            "statusDetail": (
                "The latest accepted simulation for this set has no Financial RIP "
                "V3 payload. It predates the V3 engine and must be re-run; V3 is "
                "not reconstructed from stored percentiles."
            ),
            "rankable": False,
            "components": {},
            "depthAndRobustness": {},
            "distributionDisclosures": {},
            "sessionOpeningProfile": None,
            "sourceRun": run_identity,
        }

    verified = compute_financial_rip_v3(payload)
    components_source = payload.get("components") or {}
    # The RAW metrics travel with the component so the card renders values from
    # the same run as the score it is shown beside.
    components = {
        key: {
            **(verified.get("components") or {}).get(key, {}),
            "available": bool((components_source.get(key) or {}).get("available", True)),
            "raw": dict((components_source.get(key) or {}).get("raw") or {}),
        }
        for key in FINANCIAL_RIP_V3_COMPONENT_ORDER
    }

    return {
        "score": verified.get("score"),
        "scoreVersion": payload.get("scoreVersion") or FINANCIAL_RIP_V3_VERSION,
        "normalizationVersion": (
            payload.get("normalizationVersion") or FINANCIAL_RIP_V3_NORMALIZATION_VERSION
        ),
        "status": verified.get("status"),
        "statusReason": verified.get("statusReason"),
        "statusDetail": payload.get("statusDetail"),
        "validationProblems": verified.get("validationProblems"),
        "rankable": bool(verified.get("rankable")),
        "components": components,
        "depthAndRobustness": dict(payload.get("depthAndRobustness") or {}),
        "distributionDisclosures": dict(payload.get("distributionDisclosures") or {}),
        "sessionOpeningProfile": payload.get("sessionOpeningProfile"),
        "sourceRun": run_identity,
        "audit": dict(payload.get("audit") or {}),
    }


def _rank_financial_rip_v3(row: Mapping[str, Any]) -> Optional[float]:
    return _to_optional_float((row.get("financialRipV3") or {}).get("score"))


def _rank_overall_rip_v5(row: Mapping[str, Any]) -> Optional[float]:
    return _to_optional_float((row.get("overallRipV5") or {}).get("score"))


def _rank_overall_rip_v6(row: Mapping[str, Any]) -> Optional[float]:
    """The superseded 80/20 Overall rank, kept for the V6-vs-V7 comparison."""
    return _to_optional_float((row.get("overallRipV6") or {}).get("score"))


def _rank_overall_rip_v7(row: Mapping[str, Any]) -> Optional[float]:
    """The superseded 90/10-over-V3 Overall rank, kept for the V7-vs-V8 comparison."""
    return _to_optional_float((row.get("overallRipV7") or {}).get("score"))


def _rank_overall_rip_v8(row: Mapping[str, Any]) -> Optional[float]:
    """The canonical Overall rank, from the ABSOLUTE 90/10-over-V4 score.

    Never from a cohort min-max transformation of it: min-maxing would not
    change the order, but it would put a cohort-dependent number under a field
    whose contract is that adding a set cannot change it.
    """
    return _to_optional_float((row.get("overallRipV8") or {}).get("score"))


def _rank_overall_rip_v9(row: Mapping[str, Any]) -> Optional[float]:
    return _to_optional_float((row.get("overallRipV9") or {}).get("score"))


def _make_v3_component_extractor(component: str):
    def _extract(row: Mapping[str, Any]) -> Optional[float]:
        components = (row.get("financialRipV3") or {}).get("components") or {}
        return _to_optional_float((components.get(component) or {}).get("score"))

    _extract.__name__ = f"_rank_v3_{component}"
    return _extract


# Registered into module globals so `_rank_within_cohort`'s data-driven lookup
# finds them exactly like the hand-written extractors above. Generating them
# keeps the six component ranks from being six near-identical copy-pastes that
# can each acquire their own typo.
for _v3_component_key in FINANCIAL_RIP_V3_COMPONENT_ORDER:
    globals()[f"_rank_v3_{_v3_component_key}"] = _make_v3_component_extractor(_v3_component_key)


# Appeal versions that are definitively NOT legacy CA7. Everything else found in
# a `collectorAppeal` block is CA7-era and is surfaced to the mismatch audit
# rather than dropped.
_POST_CA7_APPEAL_VERSIONS = frozenset(
    {COLLECTOR_APPEAL_V2_VERSION, COLLECTOR_APPEAL_V3_VERSION, COLLECTOR_APPEAL_V4_VERSION, COLLECTOR_APPEAL_V5_VERSION}
)


def _resolve_canonical_collector_appeal_score(collector: Mapping[str, Any]) -> Optional[float]:
    """The canonical Collector Appeal V4, identified BY ITS DECLARED VERSION.

    ``collectorAppeal.score`` is a positional read, and the object at that
    position has now changed meaning three times: it was CA7, then the V2
    bounded headroom formula, then the V3 balanced sum, and it is now V4 (D plus
    a centred asymmetric H modifier). Reading it positionally would let a bundle
    built or CACHED by an older code path feed a V3 number into Overall RIP V8
    under a V8 label - the exact silent-substitution failure the contract
    forbids, and the one a 6-hour in-process cache makes a real possibility on
    the first request after a deploy.

    So the version is checked. A payload that does not declare the canonical
    version yields None, and Overall RIP V8 reports unavailable with a reason.
    """
    appeal = collector.get("collectorAppeal") or {}
    if appeal.get("version") != COLLECTOR_APPEAL_V5_VERSION:
        return None
    return appeal.get("score")


def _resolve_legacy_collector_appeal_v3_score(collector: Mapping[str, Any]) -> Optional[float]:
    """Collector Appeal V3, for the superseded V7 blend only.

    Read from the explicit legacy block the service now publishes. Never falls
    back to the canonical `collectorAppeal` object: after the V4 cutover that
    object is a V4 score, and feeding it to Overall RIP V7 would compute a
    number that is neither V7 nor V8 while wearing V7's name.
    """
    legacy = collector.get("legacyCollectorAppealV3") or {}
    if legacy.get("version") != COLLECTOR_APPEAL_V3_VERSION:
        return None
    return legacy.get("score")


def _resolve_legacy_collector_appeal_v2_score(collector: Mapping[str, Any]) -> Optional[float]:
    """Collector Appeal V2, for the superseded V6 blend only.

    Two payload shapes carry it, and both are read: post-cutover under
    ``legacyCollectorAppealV2``, and pre-cutover under ``collectorAppeal``
    itself - because before the balanced-sum change that block WAS V2, as its
    own ``version`` string attests. The second branch is guarded by that version
    string rather than assumed, so a canonical V3 score can never be mistaken for
    V2 and quietly change what Overall RIP V6 means.
    """
    legacy = collector.get("legacyCollectorAppealV2") or {}
    if legacy.get("score") is not None:
        return legacy.get("score")
    appeal = collector.get("collectorAppeal") or {}
    if appeal.get("version") == COLLECTOR_APPEAL_V2_VERSION:
        return appeal.get("score")
    return None


def _resolve_legacy_ca7_score(collector: Mapping[str, Any]) -> Optional[float]:
    """Legacy CA7, for the superseded v4/V5 blends only.

    Two payload shapes carry CA7, and both are read:

      * post-cutover: under ``legacyCollectorAppealCA7``, computed alongside the
        canonical formula;
      * pre-cutover: under ``collectorAppeal`` itself - because before the
        refinement that block WAS CA7, as its own ``version`` string attests.

    The second branch is guarded by that version string rather than assumed, so
    a canonical D/F/P score can never be mistaken for CA7 and quietly change
    what Overall RIP v4 means. Without it, a bundle cached by the previous build
    would silently drop Overall RIP v4/V5 for every set.
    """
    legacy = collector.get("legacyCollectorAppealCA7") or {}
    if legacy.get("score") is not None:
        return legacy.get("score")
    appeal = collector.get("collectorAppeal") or {}
    # Anything that is neither the canonical V3 formula nor the superseded V2 is,
    # by definition, the CA7-era appeal number this payload carries. Guarding on
    # "not a known post-CA7 version" rather than "== CA7" keeps a payload written
    # under some other legacy version visible to the mismatch audit below, which
    # is what fails the cohort closed. Silently dropping it would turn a version
    # conflict into a quiet absence.
    if appeal.get("version") not in _POST_CA7_APPEAL_VERSIONS:
        return appeal.get("score")
    return None


def _resolve_legacy_ca7_version(collector: Mapping[str, Any]) -> Optional[str]:
    """The version of whatever legacy appeal number fed the v4/V5 blends.

    Read from the same two shapes ``_resolve_legacy_ca7_score`` reads, so the
    mismatch audit compares the version OF the number that was actually used.
    """
    legacy = collector.get("legacyCollectorAppealCA7") or {}
    if legacy.get("version"):
        return legacy.get("version")
    appeal = collector.get("collectorAppeal") or {}
    version = appeal.get("version")
    return version if version not in _POST_CA7_APPEAL_VERSIONS else None


def _attach_public_rip_contract(
    targets: List[Dict[str, Any]],
    *,
    sources: Dict[str, str],
    warnings: List[str],
) -> Dict[str, Any]:
    """Fix the public cohort, then compute every public score, rank and tier in it.

    ORDER IS THE WHOLE POINT
    ------------------------
    Coverage, then eligibility, then the cohort, then the rows, then the ranks.
    The defect this replaces ranked all 33 simulated sets and let the frontend
    hide 12, so a public page could say "#1 of 33" while listing 21. A rank is a
    property OF a cohort; computing it before the cohort is fixed produces a
    number that is not about anything the reader can see.

    Every rank here is therefore computed against ``cohort`` only. Hidden sets
    still get their own payload (a set page must render something), but they are
    never in the population any public rank is quoted against, and they never
    receive a canonical RIP.
    """
    # The same failure posture as this file's other enrichments: a bundle-build
    # failure degrades to an honest unavailable state (canonical RIP reports
    # incomplete_missing_desirability), never to a legacy score and never to a
    # 500 that takes the whole leaderboard down with it.
    try:
        collector_bundle = get_collector_appeal_bundle()
        collector_payloads = collector_bundle.get("payloads") or {}
        sources["collector_appeal_bundle"] = "OK"
    except Exception as exc:
        logger.exception("[rip-statistics-targets] collector appeal bundle failed")
        warnings.append("Failed to load Collector Appeal for RIP targets")
        sources["collector_appeal_bundle"] = "FAILED"
        collector_payloads = {}

    # 1. The cohort, from set metadata through the centralized backend policy.
    cohort = build_public_cohort(
        [
            {
                "set_id": str(target.get("target_id")),
                "name": target.get("name"),
                "era_id": target.get("era_id"),
                "era": target.get("era"),
            }
            for target in targets
            if target.get("target_id")
        ]
    )
    cohort_ids = set(cohort["eligibleSetIds"])

    # 2. Every row's scores. The CANONICAL Overall RIP is
    #    0.90 * Financial RIP V3 + 0.10 * Collector Appeal V3. Collector Appeal
    #    is the sole desirability input, and it already consumes Universal Set
    #    Desirability as its D input - so the universal score is NEVER blended in
    #    a second time here, and Chase Appeal is never added as a separate term.
    for target in targets:
        collector = _resolve_collector_payload(target, collector_payloads)
        pillars = {
            "profit": target.get("profit_score"),
            "safety": target.get("safety_score"),
            "stability": target.get("stability_score"),
        }
        # The three appeal inputs, each resolved by the version the payload
        # DECLARES rather than by field position - see the helpers for why a
        # positional read is unsafe across a formula change.
        collector_appeal_score = _resolve_canonical_collector_appeal_score(collector)
        collector_appeal_v2_score = _resolve_legacy_collector_appeal_v2_score(collector)
        ca7_score = _resolve_legacy_ca7_score(collector)

        target["openingExperience"] = _build_opening_experience(target, collector, cohort)
        # LEGACY, still computed and still published: Financial RIP V2 and
        # Overall RIP v4. Their meanings are unchanged by the V3 cutover; they
        # are what the Legacy V2 comparison view and the V2-vs-V3 audit read.
        target["ripCore"] = compute_financial_rip(pillars)
        target["rip"] = compute_overall_rip(pillars, ca7_score)
        # CANONICAL: Financial RIP V3 from the persisted authoritative payload,
        # and Overall RIP V5 = 0.90 * V3 + 0.10 * the SAME CA7 score v4 used.
        # CA7 is untouched by this task; only the financial input changed.
        financial_v3 = _build_financial_rip_v3(target)
        target["financialRipV3"] = financial_v3
        # SUPERSEDED but still computed: the 90/10 blend over legacy CA7, kept
        # so the V5-vs-V6 comparison has a real number and a rollback has a
        # reference. It is not the canonical Overall RIP.
        target["overallRipV5"] = compute_overall_rip_v5(financial_v3.get("score"), ca7_score)
        # SUPERSEDED but still computed: the 80/20 blend over Collector Appeal
        # V2, kept so the V6-vs-V7 comparison has a real number and a rollback
        # has a reference. It is not the canonical Overall RIP.
        target["overallRipV6"] = compute_overall_rip_v6(
            financial_v3.get("score"), collector_appeal_v2_score
        )
        # SUPERSEDED but still computed: the 90/10 blend over Collector Appeal
        # V3, kept so the V7-vs-V8 comparison has a real number and a rollback
        # has a reference. It is not the canonical Overall RIP, and it is fed
        # from the explicit V3 legacy block - never from the canonical appeal
        # object, which now carries V4.
        target["overallRipV7"] = compute_overall_rip_v7(
            financial_v3.get("score"),
            _resolve_legacy_collector_appeal_v3_score(collector),
        )
        # CANONICAL: 0.90 * Financial RIP V3 + 0.10 * Collector Appeal V4.
        # `collector_appeal_score` is the score the Collector Appeal service
        # publishes under the canonical version; V3, V2 and legacy CA7 are
        # deliberately NOT used here, in either direction.
        target["overallRipV8"] = compute_overall_rip_v8(
            financial_v3.get("score"),
            ((collector.get("legacyCollectorAppealV4") or {}).get("score")),
        )
        target["overallRipV9"] = compute_overall_rip_v9(
            financial_v3.get("score"), collector_appeal_score
        )
        target["publicAnalyticsStatus"] = public_analytics_status(
            {"name": target.get("name"), "era_id": target.get("era_id"), "era": target.get("era")}
        )

    # 3. Integrity: an eligible set with no UNIVERSAL desirability is an error.
    #    Checked against the universal score rather than CA7, because CA7 being
    #    absent is now an expected state rather than a contradiction.
    try:
        assert_cohort_integrity(
            cohort,
            {
                str(target.get("target_id")): (
                    (target.get("universalSetDesirability") or {}).get("score")
                )
                for target in targets
                if str(target.get("target_id")) in cohort_ids
            },
        )
    except PublicCohortIntegrityError as exc:
        # Loud, and reported in the payload. Not swallowed: the alternative is a
        # leaderboard whose denominator silently disagrees with its own list.
        logger.error("[rip-statistics-targets] public cohort integrity: %s", exc)
        warnings.append(str(exc))
        cohort["status"] = "integrity_error"

    # 4. Ranks - only now, and only within the cohort.
    cohort_rows = [target for target in targets if str(target.get("target_id")) in cohort_ids]
    _rank_within_cohort(cohort_rows, cohort_size=len(cohort_ids))

    # 5. Overall-ranked cohort audit, against the CANONICAL Overall RIP.
    #    Overall RIP V7 needs a valid Collector Appeal V3, so the Overall ranking
    #    is a stricter population than the eligible cohort: an eligible set
    #    without one keeps Financial RIP + Universal Set Desirability but is
    #    flagged out of the Overall denominator (never dropped silently, never
    #    given a fabricated Overall RIP). Mixed appeal versions fail closed.
    #
    #    Audited on `overallRipV8`, NOT on `overallRipV7` and NOT on the legacy
    #    `rip` (v4) object. Auditing a superseded model would certify the cohort
    #    of something nobody publishes any more: a set could hold a V7 score off
    #    Collector Appeal V3 while having no canonical V8 score at all, and the
    #    denominator would count it.
    overall_available = {
        str(target.get("target_id")): (target.get("overallRipV9") or {}).get("score") is not None
        for target in cohort_rows
    }
    # The version OF THE NUMBER that fed the canonical blend, read from the
    # appeal block the V8 resolver accepted. A set whose appeal declares some
    # other version contributes that version here, so the mismatch check sees it
    # rather than a quiet absence.
    appeal_version_by_set = {
        str(target.get("target_id")): (
            (target.get("openingExperience") or {}).get("collectorAppeal") or {}
        ).get("version")
        for target in cohort_rows
        if (target.get("overallRipV9") or {}).get("score") is not None
    }
    overall_audit = audit_overall_ranked_cohort(
        cohort.get("eligibleSetIds") or [], overall_available, appeal_version_by_set
    )
    # The canonical version this cohort MUST be on, carried beside the observed
    # one so a publication guard compares two explicit values rather than
    # inferring the expectation.
    #
    # `appealVersionMatchesCanonical` is expected to be True whenever anything is
    # ranked at all, because `_resolve_canonical_collector_appeal_score` is the
    # single guard: a payload declaring any other version yields None and the set
    # simply has no V7 score. It is published rather than assumed so a publication
    # audit can assert the property instead of trusting it, and so a future change
    # that loosens the resolver shows up here rather than silently.
    overall_audit["expectedAppealVersion"] = COLLECTOR_APPEAL_V5_VERSION
    overall_audit["expectedOverallRipVersion"] = OVERALL_RIP_V9_VERSION
    overall_audit["appealVersionMatchesCanonical"] = (
        overall_audit["appealVersion"] == COLLECTOR_APPEAL_V5_VERSION
    )
    cohort["overallRanked"] = overall_audit
    if overall_audit["status"] == OVERALL_RANKED_CA7_VERSION_MISMATCH:
        # Fail closed: two Overall RIPs under different Collector Appeal formulas
        # are not comparable, so this leaderboard is not fit to publish as one
        # cohort.
        logger.error(
            "[rip-statistics-targets] Overall RIP cohort mixes Collector Appeal "
            "versions %s; not publishable as one ranking.",
            overall_audit["appealVersions"],
        )
        warnings.append(
            "Overall RIP ranking mixes multiple Collector Appeal versions "
            f"({', '.join(overall_audit['appealVersions'])}); the cohort is not comparable."
        )
        cohort["status"] = "integrity_error"
    elif overall_audit["missingAppealCount"]:
        logger.warning(
            "[rip-statistics-targets] %s eligible set(s) excluded from the Overall "
            "RIP ranking for missing Collector Appeal: %s",
            overall_audit["missingAppealCount"],
            overall_audit["missingAppealSetIds"],
        )
        warnings.append(
            f"{overall_audit['missingAppealCount']} eligible set(s) have no Collector "
            "Appeal and are excluded from the Overall RIP ranking (Financial RIP and "
            "Universal Set Desirability remain available)."
        )
    return cohort


def _rank_within_cohort(cohort_rows: List[Dict[str, Any]], *, cohort_size: int) -> None:
    """Rank and tier every publicly-exposed metric across the fixed cohort."""
    for extractor_name, contract_key in PUBLIC_RANKED_METRICS:
        extractor = globals()[extractor_name]
        scratch = [
            {"target_id": row.get("target_id"), "_score": extractor(row)}
            for row in cohort_rows
        ]
        ranked = _calculate_score_ranks_and_tiers(scratch, "_score")
        for row in cohort_rows:
            entry = ranked.get(str(row.get("target_id"))) or {}
            _apply_rank(row, contract_key, entry, cohort_size=cohort_size)
    _attach_relative_scores(cohort_rows)
    _attach_cohort_fingerprint(cohort_rows)


def _attach_cohort_fingerprint(cohort_rows: List[Dict[str, Any]]) -> None:
    """Stamp every ranked row with the fingerprint of the cohort it was ranked in.

    A rank, a relative score and a denominator are all statements ABOUT a
    population, and a consumer that holds one without being able to identify that
    population cannot tell whether two numbers are comparable. The fingerprint is
    computed with the SAME helper the publication contract uses
    (``supported_cohort_fingerprint``), so the value published on a target block
    and the value recorded in the snapshot's diagnostics are the same kind of
    thing and can be compared directly.

    The cohort keys are passed in explicitly rather than letting the helper
    resolve the registry: this is the cohort that was actually ranked, and a
    fingerprint of some other population would be worse than none.
    """
    from backend.db.services.public_rip_publication_contract import (
        supported_cohort_fingerprint,
    )

    keys = [
        str(row.get("canonical_key") or row.get("target_id") or "").strip()
        for row in cohort_rows
    ]
    fingerprint = supported_cohort_fingerprint([key for key in keys if key])
    for row in cohort_rows:
        row["cohortFingerprint"] = fingerprint["fingerprint"]


def _attach_relative_scores(cohort_rows: List[Dict[str, Any]]) -> None:
    """Cohort-relative 0-100 scores for Overall RIP, Financial RIP and pillars.

    The ABSOLUTE score is the direct formula result (``rip.score`` /
    ``ripCore.score`` / a pillar ``.score``). The RELATIVE score is its min-max
    position within THIS fixed public cohort, computed with the same canonical
    ``_compute_relative_scores`` helper and alongside the ranks so the relative
    score, the rank, and the cohort denominator always describe the same
    population. Written as ``relativeScore`` on each object, distinct from the
    absolute ``score`` and never overwriting it.

    Overall/Financial relative are min-max of the FINAL absolute formula outputs
    (``rip.score`` / ``ripCore.score``), never a blend of already-relative
    inputs — the extractors read the authoritative absolute scores directly.
    """
    # V3/V5 relative scores are DIAGNOSTIC ONLY. `financialRipV3.score` stays the
    # absolute fixed-anchor score; the cohort-relative number lives under a
    # separate, explicitly named field so nothing can mistake one for the other.
    for extractor, obj_key in (
        (_rank_rip, "rip"),
        (_rank_rip_core, "ripCore"),
        (_rank_financial_rip_v3, "financialRipV3"),
        (_rank_overall_rip_v5, "overallRipV5"),
        (_rank_overall_rip_v6, "overallRipV6"),
        (_rank_overall_rip_v7, "overallRipV7"),
        (_rank_overall_rip_v8, "overallRipV8"),
        (_rank_overall_rip_v9, "overallRipV9"),
    ):
        scratch = [
            {"target_id": row.get("target_id"), "_score": extractor(row)}
            for row in cohort_rows
        ]
        relatives = _compute_relative_scores(scratch, "_score")
        for row in cohort_rows:
            obj = row.get(obj_key)
            if not isinstance(obj, dict):
                continue
            relative = relatives.get(str(row.get("target_id")))
            obj["relativeScore"] = round(relative, 2) if relative is not None else None

    # Collector Appeal V3 is a canonical published pillar in its own right, so it
    # gets the same absolute/relative pair. Its ABSOLUTE score is what the 90/10
    # Overall blend consumes; this relative number is presentation only and is
    # never fed back into a formula (see the module note on _rank_overall_rip_v7).
    appeal_scratch = [
        {"target_id": row.get("target_id"), "_score": _rank_collector_appeal(row)}
        for row in cohort_rows
    ]
    appeal_relatives = _compute_relative_scores(appeal_scratch, "_score")
    for row in cohort_rows:
        appeal = (row.get("openingExperience") or {}).get("collectorAppeal")
        if isinstance(appeal, dict):
            relative = appeal_relatives.get(str(row.get("target_id")))
            appeal["relativeScore"] = round(relative, 2) if relative is not None else None

    # Every WEIGHTED Financial RIP V3 component carries its own relative score,
    # computed INDEPENDENTLY from its own absolute component score across the
    # same cohort. Deliberately not derived from the parent's relative score and
    # deliberately not fed back into the parent: Financial RIP V3 is the weighted
    # sum of the ABSOLUTE components, and computing it from relative ones would
    # make a set's financial score depend on which other sets exist.
    #
    # Depth and Robustness is excluded for the same reason it has no rank: it is
    # an unweighted diagnostic, and giving it the full ranked/relative treatment
    # would present it as a seventh weighted component.
    for component_key in FINANCIAL_RIP_V3_COMPONENT_ORDER:
        extractor = globals()[f"_rank_v3_{component_key}"]
        scratch = [
            {"target_id": row.get("target_id"), "_score": extractor(row)}
            for row in cohort_rows
        ]
        relatives = _compute_relative_scores(scratch, "_score")
        for row in cohort_rows:
            components = (row.get("financialRipV3") or {}).get("components") or {}
            component = components.get(component_key)
            if isinstance(component, dict):
                relative = relatives.get(str(row.get("target_id")))
                component["relativeScore"] = round(relative, 2) if relative is not None else None

    for factor_key, extractor in (
        ("rosterDesirability", _rank_collector_roster_desirability),
        ("desirableOutcomeFrequency", _rank_collector_desirable_outcome_frequency),
    ):
        scratch = [{"target_id": row.get("target_id"), "_score": extractor(row)} for row in cohort_rows]
        relatives = _compute_relative_scores(scratch, "_score")
        for row in cohort_rows:
            appeal = ((row.get("openingExperience") or {}).get("collectorAppeal") or {})
            if isinstance(appeal, dict):
                standing = appeal.setdefault("factorStandings", {}).setdefault(factor_key, {})
                relative = relatives.get(str(row.get("target_id")))
                standing["relativeScore"] = round(relative, 2) if relative is not None else None

    # The three Financial RIP pillars also carry a cohort-relative public score,
    # restoring main's `relative_profit_score`/`relative_safety_score`/
    # `relative_stability_score` presentation. Each pillar lives in TWO places
    # (ripCore.components and rip.financialRip.components) from two calls to
    # compute_financial_rip; both are written so neither surface can disagree.
    for pillar, extractor in (
        ("profit", _rank_profit),
        ("safety", _rank_safety),
        ("stability", _rank_stability),
    ):
        scratch = [
            {"target_id": row.get("target_id"), "_score": extractor(row)}
            for row in cohort_rows
        ]
        relatives = _compute_relative_scores(scratch, "_score")
        for row in cohort_rows:
            relative = relatives.get(str(row.get("target_id")))
            rounded = round(relative, 2) if relative is not None else None
            for components in (
                (row.get("ripCore") or {}).get("components") or {},
                ((row.get("rip") or {}).get("financialRip") or {}).get("components") or {},
            ):
                component = components.get(pillar)
                if isinstance(component, dict):
                    component["relativeScore"] = rounded


def _apply_rank(
    row: Dict[str, Any],
    contract_key: str,
    entry: Mapping[str, Any],
    *,
    cohort_size: int,
) -> None:
    """Write a rank/tier/cohortSize onto the object it describes.

    Every ranked object carries its OWN denominator. A rank without the cohort
    it was computed against is the ambiguity this phase is removing, so the two
    always travel together.
    """
    # Each metric's denominator is its actual valid comparison population. It
    # normally equals the eligible public cohort, but a null factor is omitted
    # rather than counted as a measured zero.
    metric_cohort_size = entry.get("cohortSize", cohort_size)
    if contract_key in (
        "rip", "ripCore", "financialRipV3",
        "overallRipV5", "overallRipV6", "overallRipV7", "overallRipV8", "overallRipV9",
    ):
        target = row.get(contract_key) or {}
        target["rank"] = entry.get("rank")
        target["tier"] = entry.get("tier")
        target["cohortSize"] = metric_cohort_size
        return
    if contract_key.startswith("financialRipV3."):
        # A per-component rank on the V3 breakdown. Depth and Robustness is
        # deliberately NOT in this list: it is an unweighted diagnostic, and
        # giving it a rank alongside the six would present it as a seventh
        # weighted component.
        component_key = contract_key.split(".", 1)[1]
        components = (row.get("financialRipV3") or {}).get("components") or {}
        component = components.get(component_key)
        if isinstance(component, dict):
            component["rank"] = entry.get("rank")
            component["tier"] = entry.get("tier")
            component["cohortSize"] = metric_cohort_size
        return
    if contract_key.startswith("collectorAppeal."):
        factor_key = contract_key.split(".", 1)[1]
        appeal = ((row.get("openingExperience") or {}).get("collectorAppeal") or {})
        if isinstance(appeal, dict):
            appeal.setdefault("factorStandings", {})[factor_key] = {
                "rank": entry.get("rank"), "tier": entry.get("tier"), "cohortSize": metric_cohort_size,
            }
        return
    if contract_key in ("profit", "safety", "stability"):
        # The pillars live on Financial RIP now. Overall RIP carries the same
        # Financial RIP object under `financialRip`, so both surfaces are ranked
        # from one computation rather than two that can disagree.
        blocks = [
            (row.get("ripCore") or {}).get("components") or {},
            ((row.get("rip") or {}).get("financialRip") or {}).get("components") or {},
        ]
        for components in blocks:
            component = components.get(contract_key)
            if isinstance(component, dict):
                component["rank"] = entry.get("rank")
                component["tier"] = entry.get("tier")
                component["cohortSize"] = metric_cohort_size
        return
    opening = row.get("openingExperience") or {}
    block = opening.get(contract_key)
    if isinstance(block, dict):
        block["rank"] = entry.get("rank")
        block["cohortSize"] = metric_cohort_size
        # Dual-Path Depth is a structural index, not a graded 0-100 metric, so it
        # gets a rank but deliberately no tier: a "D tier" on a scale whose
        # maximum is not attainable would read as a verdict on the set.
        if contract_key != "dualPathDepth":
            block["tier"] = entry.get("tier")


def _rank_rip(row: Mapping[str, Any]) -> Optional[float]:
    return _to_optional_float((row.get("rip") or {}).get("score"))


def _rank_rip_core(row: Mapping[str, Any]) -> Optional[float]:
    return _to_optional_float((row.get("ripCore") or {}).get("score"))


def _rank_profit(row: Mapping[str, Any]) -> Optional[float]:
    return _to_optional_float(row.get("profit_score"))


def _rank_safety(row: Mapping[str, Any]) -> Optional[float]:
    return _to_optional_float(row.get("safety_score"))


def _rank_stability(row: Mapping[str, Any]) -> Optional[float]:
    return _to_optional_float(row.get("stability_score"))


def _opening_metric(row: Mapping[str, Any], key: str, field: str = "score") -> Optional[float]:
    block = (row.get("openingExperience") or {}).get(key) or {}
    return _to_optional_float(block.get(field))


def _rank_collector_appeal(row: Mapping[str, Any]) -> Optional[float]:
    return _opening_metric(row, "collectorAppeal")


def _collector_factor(row: Mapping[str, Any], key: str) -> Optional[float]:
    appeal = (row.get("openingExperience") or {}).get("collectorAppeal") or {}
    return _to_optional_float((appeal.get("factors") or {}).get(key))


def _rank_collector_roster_desirability(row: Mapping[str, Any]) -> Optional[float]:
    return _collector_factor(row, "rosterDesirability")


def _rank_collector_desirable_outcome_frequency(row: Mapping[str, Any]) -> Optional[float]:
    return _collector_factor(row, "desirableOutcomeFrequency")


def _rank_chase_appeal(row: Mapping[str, Any]) -> Optional[float]:
    return _opening_metric(row, "chaseAppeal")


def _rank_dual_path_depth(row: Mapping[str, Any]) -> Optional[float]:
    return _opening_metric(row, "dualPathDepth", "rawValue")


def _build_opening_experience(
    target: Mapping[str, Any],
    collector: Mapping[str, Any],
    cohort: Mapping[str, Any],
) -> Dict[str, Any]:
    """The public Simulation Opening Experience contract for one set.

    Assembled from the Collector Appeal service's payload only. Nothing is
    recomputed here; this shapes and labels what that service already decided.

    The aggregate roster score remains independently available on
    ``universalSetDesirability``. This block also carries the Collector service's
    roster detail projection so V8 can package the exact modeled species and its
    frequency-eligibility annotation without recomputing either.
    """
    base = {
        "cohort": {
            "version": cohort.get("version"),
            "eligibleSetCount": cohort.get("eligibleSetCount"),
        },
    }
    if not collector:
        return {
            **base,
            "status": "unavailable",
            "coverage": {
                "status": "unavailable",
                "reasons": ["no_component_source_row"],
                "scope": "simulation_opening_experience",
            },
        }

    coverage = dict(collector.get("coverage") or {})
    coverage["scope"] = "simulation_opening_experience"
    return {
        **base,
        "status": collector.get("status"),
        "version": (collector.get("collectorAppeal") or {}).get("version"),
        "asOf": collector.get("asOf"),
        # H and P: two of the three inputs to the canonical Collector Appeal. H
        # (published as `desirableOutcomeFrequency`) is a nonfinancial frequency
        # and is NOT a win rate.
        #
        "rosterDesirability": dict(collector.get("rosterDesirability") or {}),
        "desirableOutcomeFrequency": dict(collector.get("desirableOutcomeFrequency") or {}),
        "dualPathDepth": dict(collector.get("dualPathDepth") or {}),
        "collectorAppeal": dict(collector.get("collectorAppeal") or {}),
        # Superseded, carried for the comparison surfaces and the audit only.
        "legacyCollectorAppealV2": dict(collector.get("legacyCollectorAppealV2") or {}),
        "legacyCollectorAppealCA7": dict(collector.get("legacyCollectorAppealCA7") or {}),
        # Still a separate diagnostic. Deliberately NOT a term of Collector
        # Appeal and NOT a term of Overall RIP - adding D x M alongside a
        # Collector Appeal that already contains D would apply desirability twice.
        "chaseAppeal": dict(collector.get("chaseAppeal") or {}),
        "topSubjects": list(collector.get("topSubjects") or []),
        "coverage": coverage,
    }


def _load_rankings_top_chase_lookup(
    ranked_rows: Iterable[Mapping[str, Any]], *, sources: Dict[str, str], warnings: List[str]
) -> Dict[str, Dict[str, Any]]:
    """Copy canonical set-page Top Chases for the ranked cohort in one read.

    Rankings never rebuilds or infers a chase. The already-validated set-page
    ``ripDecision.topChase`` is the only source, and its run identity must match
    the Rankings target before the compact scanner object is attached.
    """
    target_runs = {
        str(row.get("set_id")): _to_optional_str(row.get("calculation_run_id"))
        for row in ranked_rows
        if row.get("set_id") and _to_optional_str(row.get("calculation_run_id"))
    }
    set_ids = sorted(target_runs)
    if not set_ids:
        sources["rankings_top_chase"] = "SKIPPED"
        return {}

    try:
        snapshot_rows = list((
            public_read_client.table("pokemon_set_page_snapshot_latest")
            .select("set_id,payload_json")
            .in_("set_id", set_ids)
            .execute()
        ).data or [])
    except Exception as exc:
        logger.warning("[rip-statistics-targets] Rankings chase snapshot read failed: %s", exc)
        warnings.append("Failed to load canonical set-page Top Chase data for ranked targets")
        sources["rankings_top_chase"] = "FAILED"
        return {}

    lookup: Dict[str, Dict[str, Any]] = {}
    missing: List[str] = []
    for row in snapshot_rows:
        set_id = _to_optional_str(row.get("set_id"))
        payload = row.get("payload_json") if isinstance(row.get("payload_json"), dict) else {}
        decision = payload.get("ripDecision") if isinstance(payload.get("ripDecision"), dict) else {}
        chase = decision.get("topChase") if isinstance(decision.get("topChase"), dict) else None
        if not set_id or not chase:
            if set_id:
                missing.append(set_id)
            continue
        target_run = target_runs.get(set_id)
        chase_run = _to_optional_str(chase.get("sourceCalculationRunId"))
        if target_run and chase_run and target_run != chase_run:
            raise RuntimeError(
                "Refusing stale Rankings Top Chase publication for set_id="
                f"{set_id}: target run {target_run} != set-page chase run {chase_run}"
            )
        card_name = _to_optional_str(chase.get("cardName"))
        market_price = _to_optional_float(chase.get("currentMarketPrice"))
        odds = _to_optional_float(chase.get("impliedOddsOneInN"))
        packs_to_50 = _to_optional_float(chase.get("packsFor50PercentChance"))
        if (
            not card_name
            or market_price is None or market_price <= 0
            or odds is None or odds <= 0
            or packs_to_50 is None or packs_to_50 <= 0
        ):
            missing.append(set_id)
            continue
        lookup[set_id] = {
            "cardName": card_name,
            "currentMarketPrice": market_price,
            "impliedOddsOneInN": odds,
            "packsFor50PercentChance": int(packs_to_50),
            # Retained in the server payload for publication audit. The RSC
            # client projection deliberately drops this field.
            "sourceCalculationRunId": chase_run,
        }

    missing.extend(sorted(set(set_ids) - {str(row.get("set_id")) for row in snapshot_rows}))
    if missing:
        warnings.append(
            "Canonical Rankings Top Chase unavailable for set_ids: "
            + ",".join(sorted(set(missing)))
        )
    sources["rankings_top_chase"] = "OK" if not missing else "PARTIAL"
    return lookup


def get_rip_statistics_targets_payload(
    limit: Any = DEFAULT_TARGETS_LIMIT,
    *,
    include_rankings_top_chase: bool = True,
) -> Dict[str, Any]:
    """Return available RIP targets and the best default target from persisted data."""
    total_started = time.perf_counter()
    clamped_limit = _sanitize_limit(limit, default=DEFAULT_TARGETS_LIMIT, max_value=MAX_TARGETS_LIMIT)

    warnings: List[str] = []
    sources: Dict[str, str] = {}

    query_started = time.perf_counter()
    try:
        # `explore_rip_statistics_latest` is a windowed view that measures ~6s
        # against an 8s statement_timeout, so a cold run exceeds the budget and
        # returns 57014 - the "explore_rip_statistics_latest read failed" that
        # took the whole payload down with it. The read is unchanged; it is only
        # retried, because the second attempt runs against a warm cache.
        targets_result = run_batch_read_with_retry(
            lambda: (
                public_read_client.table("explore_rip_statistics_latest")
                .select("*")
                .order("pack_score", desc=True)
                .order("run_at", desc=True)
                .limit(clamped_limit)
                .execute()
            ),
            operation_name="explore_rip_statistics_latest.targets",
        )
        raw_rows = [row for row in (targets_result.data or []) if row.get("set_id")]
        sources["explore_rip_statistics_latest"] = "OK"
        sources["simulation_latest_by_target"] = "SKIPPED_RIP_SUMMARY"
    except Exception as exc:
        logger.exception("[rip-statistics-targets] explore_rip_statistics_latest query failed")
        raise ExploreRipStatisticsTargetsError(
            status_code=500,
            message="Failed to load RIP Statistics targets",
            code="TARGETS_QUERY_FAILED",
        ) from exc
    query_ms = (time.perf_counter() - query_started) * 1000

    if not raw_rows:
        raise ExploreRipStatisticsTargetsError(
            status_code=404,
            message="No RIP Statistics targets found",
            code="TARGETS_NOT_FOUND",
        )

    ranked_rows = sorted(raw_rows, key=_build_rank_sort_key)

    if include_rankings_top_chase:
        rankings_top_chase_lookup = _load_rankings_top_chase_lookup(
            ranked_rows,
            sources=sources,
            warnings=warnings,
        )
    else:
        # Targeted ripDecision repair is itself the producer of the canonical
        # Top Chase block. Requiring the old block to match the new run before
        # repair creates a dependency cycle; all public/default reads retain
        # the strict stale-run guard above.
        rankings_top_chase_lookup = {}
        sources["rankings_top_chase"] = "SKIPPED_TARGETED_REPAIR"

    set_lookup_by_target_id: Dict[str, Dict[str, Any]] = {}
    era_lookup: Dict[str, Dict[str, Any]] = {}

    set_ids = sorted({str(row.get("set_id")) for row in ranked_rows if row.get("set_id")})
    if set_ids:
        set_started = time.perf_counter()
        try:
            set_result = (
                public_read_client.table("sets")
                .select(
                    "id,name,canonical_key,release_date,pokemon_api_set_id,era_id,logo_image_url,symbol_image_url,hero_image_url"
                )
                .in_("id", set_ids)
                .execute()
            )
            for row in (set_result.data or []):
                set_id = _to_optional_str(row.get("id"))
                if set_id:
                    set_lookup_by_target_id[set_id] = row

            unresolved_target_ids = [
                target_id for target_id in set_ids if target_id not in set_lookup_by_target_id
            ]
            if unresolved_target_ids:
                canonical_result = (
                    public_read_client.table("sets")
                    .select(
                        "id,name,canonical_key,release_date,pokemon_api_set_id,era_id,logo_image_url,symbol_image_url,hero_image_url"
                    )
                    .in_("canonical_key", unresolved_target_ids)
                    .execute()
                )
                for row in (canonical_result.data or []):
                    canonical_key = _to_optional_str(row.get("canonical_key"))
                    if canonical_key and canonical_key in unresolved_target_ids:
                        set_lookup_by_target_id[canonical_key] = row

            sources["sets"] = "OK"
        except Exception as exc:
            logger.warning("[rip-statistics-targets] set enrichment failed: %s", exc)
            warnings.append("Failed to load set metadata for one or more RIP targets")
            sources["sets"] = "FAILED"
        set_ms = (time.perf_counter() - set_started) * 1000
    else:
        set_ms = 0.0
        sources["sets"] = "SKIPPED"

    set_value_started = time.perf_counter()
    set_value_lookup_ids = sorted(
        {
            resolved_id
            for resolved_id in [
                *set_ids,
                *[
                    _to_optional_str(set_row.get("id"))
                    for set_row in set_lookup_by_target_id.values()
                ],
            ]
            if resolved_id
        }
    )
    current_snapshot_date, previous_snapshot_date = _load_complete_published_snapshot_dates(
        sources=sources, warnings=warnings
    )
    current_checklist_set_value_lookup = _load_current_checklist_set_value_lookup(
        set_value_lookup_ids,
        current_snapshot_date=current_snapshot_date,
        sources=sources,
        warnings=warnings,
    )
    set_value_ms = (time.perf_counter() - set_value_started) * 1000

    desirability_started = time.perf_counter()
    opening_desirability_lookup = _load_opening_desirability_lookup(
        set_value_lookup_ids,
        sources=sources,
        warnings=warnings,
    )
    desirability_ms = (time.perf_counter() - desirability_started) * 1000

    top_10_started = time.perf_counter()
    top_10_card_value_lookup = _load_top_10_card_value_lookup(
        set_value_lookup_ids,
        sources=sources,
        warnings=warnings,
    )
    top_10_ms = (time.perf_counter() - top_10_started) * 1000

    era_ids = sorted(
        {
            str(row.get("era_id"))
            for row in set_lookup_by_target_id.values()
            if row.get("era_id") is not None
        }
    )
    if era_ids:
        era_started = time.perf_counter()
        try:
            era_result = (
                public_read_client.table("eras")
                .select("id,name")
                .in_("id", era_ids)
                .execute()
            )
            era_lookup = {
                str(row.get("id")): row
                for row in (era_result.data or [])
                if row.get("id") is not None
            }
            sources["eras"] = "OK"
        except Exception as exc:
            logger.warning("[rip-statistics-targets] era enrichment failed: %s", exc)
            warnings.append("Failed to load era metadata for one or more RIP targets")
            sources["eras"] = "FAILED"
        era_ms = (time.perf_counter() - era_started) * 1000
    else:
        era_ms = 0.0
        sources["eras"] = "SKIPPED"

    # Fetch ratio rank/tier fields not exposed by explore_rip_statistics_latest
    ratio_rank_tier_lookup: Dict[str, Dict[str, Any]] = {}
    if set_ids:
        ratio_started = time.perf_counter()
        try:
            ratio_result = (
                public_read_client.table("set_pack_score_rankings_latest")
                .select(
                    "target_id,mean_value_to_cost_rank,mean_value_to_cost_tier,"
                    "p95_value_to_cost_rank,p95_value_to_cost_tier"
                )
                .in_("target_id", set_ids)
                .execute()
            )
            for ratio_row in (ratio_result.data or []):
                tid = _to_optional_str(ratio_row.get("target_id"))
                if tid:
                    ratio_rank_tier_lookup[tid] = ratio_row
            sources["ratio_rank_tiers"] = "OK"
        except Exception as exc:
            logger.warning("[rip-statistics-targets] ratio rank/tier enrichment failed: %s", exc)
            warnings.append("Failed to load ratio rank/tier data for one or more RIP targets")
            sources["ratio_rank_tiers"] = "FAILED"

    ordered_rows = sorted(
        ranked_rows,
        key=lambda row: _build_set_order_key(
            str(row.get("set_id")),
            set_lookup_by_target_id.get(str(row.get("set_id"))) or {},
        ),
    )

    default_target_id: Optional[str] = None
    for row in ranked_rows:
        target_id = _to_optional_str(row.get("set_id"))
        if target_id and _to_optional_float(row.get("pack_score")) is not None:
            default_target_id = target_id
            break
    if default_target_id is None and ranked_rows:
        default_target_id = _to_optional_str(ranked_rows[0].get("target_id"))

    targets: List[Dict[str, Any]] = []
    for row in ordered_rows:
        target_id = str(row.get("set_id"))
        set_row = set_lookup_by_target_id.get(target_id) or {}
        era_row = era_lookup.get(str(set_row.get("era_id"))) if set_row.get("era_id") is not None else None
        summary_row = {
            key: value
            for key, value in row.items()
            if key not in {"set_id", "calculation_run_id", "run_at", "created_at", "updated_at"}
        }
        canonical_recommendation_header, leaderboard_label, recommendation_severity = _build_recommendation_labels(
            summary_row
        )
        pack_rank = row.get("pack_rank")
        pack_tier = _to_optional_str(row.get("pack_tier"))
        resolved_set_id = _to_optional_str(set_row.get("id")) or target_id
        checklist_set_value_row = (
            current_checklist_set_value_lookup.get(resolved_set_id)
            or current_checklist_set_value_lookup.get(target_id)
            or {}
        )
        checklist_set_value = _to_optional_float(checklist_set_value_row.get("set_value"))
        opening_desirability_row = (
            opening_desirability_lookup.get(resolved_set_id)
            or opening_desirability_lookup.get(target_id)
            or {}
        )
        top_10_card_value_row = (
            top_10_card_value_lookup.get(resolved_set_id)
            or top_10_card_value_lookup.get(target_id)
            or {}
        )
        embedded_desirability_score = _to_optional_float(row.get("desirability_score"))
        joined_desirability_score = _to_optional_float(opening_desirability_row.get("opening_desirability_score"))
        canonical_desirability_score = (
            embedded_desirability_score
            if embedded_desirability_score is not None
            else joined_desirability_score
        )
        
        targets.append(
            {
                "target_type": "set",
                "target_id": target_id,
                "id": resolved_set_id,
                "set_id": resolved_set_id,
                "canonical_key": set_row.get("canonical_key"),
                "slug": set_row.get("canonical_key"),
                "pokemon_api_set_id": set_row.get("pokemon_api_set_id"),
                "name": str(set_row.get("name") or target_id),
                "era": era_row.get("name") if era_row else None,
                # The table-backed era key, threaded through so the public
                # analytics policy can classify on the reliable identifier
                # rather than falling back to matching a display name.
                "era_id": _to_optional_str(set_row.get("era_id")),
                "logo_image_url": set_row.get("logo_image_url"),
                "symbol_image_url": set_row.get("symbol_image_url"),
                "hero_image_url": set_row.get("hero_image_url"),
                "leaderboard_label": leaderboard_label,
                "canonical_recommendation_header": canonical_recommendation_header,
                "recommendation_severity": recommendation_severity,
                "relative_pack_score": row.get("relative_pack_score"),
                "pack_score": row.get("pack_score"),
                "pack_rank": pack_rank,
                "pack_tier": pack_tier,
                "relative_profit_score": row.get("relative_profit_score"),
                "profit_score": row.get("profit_score"),
                "profit_rank": row.get("profit_rank"),
                "profit_tier": row.get("profit_tier"),
                "relative_safety_score": row.get("relative_safety_score"),
                "safety_score": row.get("safety_score"),
                "safety_rank": row.get("safety_rank"),
                "safety_tier": row.get("safety_tier"),
                "relative_stability_score": row.get("relative_stability_score"),
                "stability_score": row.get("stability_score"),
                "stability_rank": row.get("stability_rank"),
                "stability_tier": row.get("stability_tier"),
                "relative_desirability_score": row.get("relative_desirability_score"),
                "desirability_score": canonical_desirability_score,
                "desirability_rank": row.get("desirability_rank"),
                "desirability_tier": row.get("desirability_tier"),
                "desirability_scoring_version": row.get("desirability_scoring_version") or opening_desirability_row.get("scoring_version"),
                "desirability_source_summary_id": row.get("desirability_source_summary_id") or opening_desirability_row.get("source_v2_component_row_id"),
                "desirability_source_table": row.get("desirability_source_table") or ("pokemon_set_opening_desirability_latest" if joined_desirability_score is not None else None),
                "desirability_source_metric": row.get("desirability_source_metric") or ("opening_desirability_score" if joined_desirability_score is not None else None),
                "desirability_is_fallback": row.get("desirability_is_fallback") if row.get("desirability_is_fallback") is not None else False,
                "desirability_fallback_reason": row.get("desirability_fallback_reason"),
                "opening_desirability_score": joined_desirability_score,
                "opening_desirability_rank": opening_desirability_row.get("opening_desirability_rank"),
                "collector_appeal_score": opening_desirability_row.get("collector_appeal_score"),
                "collector_appeal_rank": opening_desirability_row.get("collector_appeal_rank"),
                "opening_desirability_summary": opening_desirability_row.get("opening_desirability_summary"),
                "relative_experience_score": row.get("relative_experience_score"),
                "experience_score": row.get("experience_score"),
                "experience_rank": row.get("experience_rank"),
                "experience_tier": row.get("experience_tier"),
                "relative_chase_potential_score": row.get("relative_chase_potential_score"),
                "chase_potential_score": row.get("chase_potential_score"),
                "chase_potential_rank": row.get("chase_potential_rank"),
                "chase_potential_tier": row.get("chase_potential_tier"),
                "mean_value_to_cost_ratio": row.get("mean_value_to_cost_ratio"),
                "mean_value_to_cost_rank": ratio_rank_tier_lookup.get(target_id, {}).get("mean_value_to_cost_rank"),
                "mean_value_to_cost_tier": ratio_rank_tier_lookup.get(target_id, {}).get("mean_value_to_cost_tier"),
                "p95_value_to_cost_ratio": row.get("p95_value_to_cost_ratio"),
                "p99_value_to_cost_ratio": row.get("p99_value_to_cost_ratio"),
                "p95_value_to_cost_rank": ratio_rank_tier_lookup.get(target_id, {}).get("p95_value_to_cost_rank"),
                "p95_value_to_cost_tier": ratio_rank_tier_lookup.get(target_id, {}).get("p95_value_to_cost_tier"),
                "pack_cost": row.get("pack_cost"),
                "mean_value": row.get("mean_value"),
                "median_value": row.get("median_value"),
                # AVERAGE LOSS WHEN LOSING — E[pack_cost - value | value < cost],
                # in dollars.
                #
                # This is a PASSTHROUGH of an existing published column, not a new
                # statistic. It is produced by compute_downside_metrics as
                # `expected_loss_given_loss`, persisted as the required
                # `simulation_run_summary.expected_loss_when_losing`, and already
                # exposed by `explore_rip_statistics_latest` — the very row this
                # projection is reading. It cost no extra query, join or column to
                # add; the value was simply being dropped on the way out.
                #
                # It is NOT derivable from what the leaderboard already published.
                # `pack_cost - mean_value` is the unconditional gap between price
                # and Expected Value, which says nothing about the size of a loss:
                # a set whose packs return $0 half the time and 2x cost the other
                # half has an unconditional gap of $0 and an average loss when
                # losing of a full pack cost. Any consumer needing the conditional
                # statistic must read this field rather than reconstruct one.
                "expected_loss_when_losing": row.get("expected_loss_when_losing"),
                "simulated_set_value": row.get("simulated_set_value"),
                "simulated_set_value_card_count": row.get("simulated_set_value_card_count"),
                "set_value_for_validation": checklist_set_value,
                "setValueForValidation": checklist_set_value,
                "current_checklist_set_value": checklist_set_value,
                "currentChecklistSetValue": checklist_set_value,
                "checklist_set_value": checklist_set_value,
                "checklistSetValue": checklist_set_value,
                "current_checklist_set_value_date": checklist_set_value_row.get("snapshot_date"),
                "currentChecklistSetValueDate": checklist_set_value_row.get("snapshot_date"),
                "checklist_set_value_source": checklist_set_value_row.get("source"),
                "checklistSetValueSource": checklist_set_value_row.get("source"),
                "checklist_set_value_priced_card_count": checklist_set_value_row.get("priced_card_count"),
                "checklistSetValuePricedCardCount": checklist_set_value_row.get("priced_card_count"),
                "checklist_set_value_total_card_count": checklist_set_value_row.get("total_card_count"),
                "checklistSetValueTotalCardCount": checklist_set_value_row.get("total_card_count"),
                "checklist_set_value_as_of": checklist_set_value_row.get("snapshot_date"),
                "checklistSetValueAsOf": checklist_set_value_row.get("snapshot_date"),
                "previous_checklist_set_value_7d": checklist_set_value_row.get("previous_set_value_7d"),
                "previousChecklistSetValue7d": checklist_set_value_row.get("previous_set_value_7d"),
                "previous_checklist_set_value_date_7d": checklist_set_value_row.get("previous_set_value_date_7d"),
                "previousChecklistSetValueDate7d": checklist_set_value_row.get("previous_set_value_date_7d"),
                "set_value_comparison_status_7d": checklist_set_value_row.get("comparison_status_7d") or "unavailable",
                "setValueComparisonStatus7d": checklist_set_value_row.get("comparison_status_7d") or "unavailable",
                # The current rankings view is latest-only. Until a durable,
                # completion-qualified cohort snapshot exists, publishing a
                # numeric RIP rank movement would be misleading.
                "rip_rank_comparison_status_1d": "unavailable",
                "ripRankComparisonStatus1d": "unavailable",
                **top_10_card_value_row,
                "roi_percent": row.get("roi_percent"),
                "prob_profit": row.get("prob_profit"),
                "prob_big_hit": row.get("prob_big_hit"),
                "run_at": row.get("run_at"),
                # --- Financial RIP V3 source row -----------------------------
                # Carried raw so the V3 object, its rank and its published
                # provenance all come from ONE row: the score, the raw metrics
                # and the pack cost below are the same simulation run, and the
                # contract builder never mixes a score from one run with raw
                # metrics from another.
                "calculation_run_id": row.get("calculation_run_id"),
                "rankingsChase": rankings_top_chase_lookup.get(str(row.get("set_id"))),
                "financial_rip_v3_payload": row.get("financial_rip_v3_payload"),
                "financial_rip_v3_score": row.get("financial_rip_v3_score"),
                "financial_rip_v3_status": row.get("financial_rip_v3_status"),
                "financial_rip_v3_score_version": row.get("financial_rip_v3_score_version"),
                "financial_rip_v3_normalization_version": row.get(
                    "financial_rip_v3_normalization_version"
                ),
                "financial_rip_v3_rankable": row.get("financial_rip_v3_rankable"),
                "financial_rip_v3_simulation_count": row.get("financial_rip_v3_simulation_count"),
                "top2_ev_share": row.get("top2_ev_share"),
            }
        )

    desirability_rows = [
        {
            "target_id": target.get("target_id"),
            "desirability_score": _to_optional_float(target.get("desirability_score")),
        }
        for target in targets
    ]
    desirability_ranks = _calculate_score_ranks_and_tiers(desirability_rows, "desirability_score")
    desirability_relatives = _compute_relative_scores(desirability_rows, "desirability_score")
    for target in targets:
        target_id = str(target.get("target_id"))
        rank_payload = desirability_ranks.get(target_id, {})
        relative_desirability = desirability_relatives.get(target_id)
        target["relative_desirability_score"] = (
            round(relative_desirability, 2)
            if relative_desirability is not None
            else None
        )
        target["desirability_rank"] = rank_payload.get("rank")
        target["desirability_tier"] = rank_payload.get("tier")

    # Blend Biggest Upside lens from P95 (Strong Upside) + P99 (Jackpot Upside).
    blended_rows = [
        {
            "target_id": target.get("target_id"),
            "biggest_upside_score": _blend_biggest_upside_score(
                target.get("p95_value_to_cost_ratio"),
                target.get("p99_value_to_cost_ratio"),
            ),
        }
        for target in targets
    ]
    blended_score_lookup = {
        str(row.get("target_id")): _to_optional_float(row.get("biggest_upside_score"))
        for row in blended_rows
        if row.get("target_id")
    }
    blended_ranks = _calculate_score_ranks_and_tiers(blended_rows, "biggest_upside_score")
    blended_relatives = _compute_relative_scores(blended_rows, "biggest_upside_score")

    for target in targets:
        target_id = str(target.get("target_id"))
        rank_payload = blended_ranks.get(target_id, {})
        blended_score = blended_score_lookup.get(target_id)
        target["biggest_upside_score"] = (
            round(blended_score, 2)
            if blended_score is not None
            else None
        )
        target["relative_biggest_upside_score"] = (
            round(blended_relatives[target_id], 2)
            if blended_relatives.get(target_id) is not None
            else None
        )
        target["biggest_upside_rank"] = rank_payload.get("rank")
        target["biggest_upside_tier"] = rank_payload.get("tier")

    average_return_rows = [
        {
            "target_id": target.get("target_id"),
            "average_return_score": _resolve_mean_value_to_cost_ratio(target),
        }
        for target in targets
    ]
    average_return_relatives = _compute_relative_scores(average_return_rows, "average_return_score")
    for target in targets:
        target_id = str(target.get("target_id"))
        relative_average = average_return_relatives.get(target_id)
        target["relative_average_return_score"] = (
            round(relative_average, 2)
            if relative_average is not None
            else None
        )

    p99_rows = [
        {
            "target_id": target.get("target_id"),
            "p99_value_to_cost_score": _to_optional_float(target.get("p99_value_to_cost_ratio")),
        }
        for target in targets
    ]
    p99_ranks = _calculate_score_ranks_and_tiers(p99_rows, "p99_value_to_cost_score")
    p99_relatives = _compute_relative_scores(p99_rows, "p99_value_to_cost_score")
    for target in targets:
        target_id = str(target.get("target_id"))
        p99_rank_payload = p99_ranks.get(target_id, {})
        relative_p99 = p99_relatives.get(target_id)
        target["relative_p99_value_to_cost_score"] = (
            round(relative_p99, 2)
            if relative_p99 is not None
            else None
        )
        target["p99_value_to_cost_rank"] = p99_rank_payload.get("rank")
        target["p99_value_to_cost_tier"] = p99_rank_payload.get("tier")

    _rank_top_10_card_values(targets)

    comparison_payload = build_rip_desirability_comparison_payload(targets)
    targets = comparison_payload["rows"]
    comparison_diagnostics = comparison_payload["diagnostics"]
    for target in targets:
        core_interpretation = _build_rip_core_interpretation(target)
        target["rip_core_interpretation"] = core_interpretation
        target["rip_core_interpretation_label"] = core_interpretation.get("label")
        target["rip_core_interpretation_summary"] = core_interpretation.get("summary")
        target["rip_core_interpretation_severity"] = core_interpretation.get("severity")
    logger.info(
        "[rip-statistics-targets] RIP desirability comparison valid=%s/%s missing_desirability=%s "
        "raises_rank=%s lowers_rank=%s minimal=%s",
        comparison_diagnostics["valid_comparison_count"],
        comparison_diagnostics["total_sets"],
        comparison_diagnostics["missing_desirability_count"],
        comparison_diagnostics["raises_rank_count"],
        comparison_diagnostics["lowers_rank_count"],
        comparison_diagnostics["minimal_impact_count"],
    )

    # Universal Set Desirability v3 stays as a SUPPORTING metric (Roster
    # Desirability). It is no longer the 10% RIP pillar - see
    # _attach_public_rip_contract.
    universal_bundle = get_universal_desirability_bundle()
    universal_payloads = universal_bundle.get("payloads") or {}
    # Reported so a consumer can tell "these sets have no desirability" from "the
    # desirability source was not read". Without it both arrive as an empty
    # bundle and every set is published `unavailable`, which is a claim about the
    # sets that a timed-out query is not entitled to make.
    universal_status = universal_bundle.get("status")
    if universal_status != "ok":
        logger.error(
            "[rip-statistics-targets] universal desirability bundle FAILED to build; "
            "every set will report desirability unavailable. This payload is not fit to publish."
        )
        warnings.append(
            "Universal Set Desirability could not be read; its coverage in this payload "
            "reflects a failed read, not the sets."
        )
        sources["universal_desirability_bundle"] = "FAILED"
    else:
        sources["universal_desirability_bundle"] = "OK"
    # Descriptive context only. Desirability's RIP weight comes from the config
    # defaults; this correlation never zeroes it (see scoring_config).
    set_value_association = universal_bundle.get("setValueAssociation")
    for target in targets:
        resolved_id = _resolve_desirability_key(target)
        universal_row = universal_payloads.get(resolved_id or "") or universal_payloads.get(
            str(target.get("target_id") or "")
        )
        universal = universal_public_payload(universal_row, set_value_association)
        target["universalSetDesirability"] = universal
        target["desirabilityCoverage"] = (universal or {}).get("coverage") or {
            "status": "unavailable",
            "reasons": ["missing_demand_scores"],
        }
        target["simulationCoverage"] = assess_simulation_coverage(target)

    cohort = _attach_public_rip_contract(targets, sources=sources, warnings=warnings)

    # Compact public v4 projection: ONE object both Explore and the set page read,
    # lifted verbatim from the canonical rip/ripCore/universalSetDesirability/
    # openingExperience objects above (nothing recomputed). Attached to every
    # target so hidden sets still snapshot a (mostly-null) contract for their set
    # page, and the leaderboard reads the cohort-ranked one.
    for target in targets:
        target[PUBLIC_RIP_CONTRACT_V4_KEY] = build_public_rip_contract_v4(target)
        # The CANONICAL v5 projection (Financial RIP V3 + Overall RIP V5), with
        # V2/v4 preserved under an explicit `legacy` namespace. Additive: the v4
        # key above is byte-for-byte what it always was.
        target[PUBLIC_RIP_CONTRACT_V5_KEY] = build_public_rip_contract_v5(target)
        # Superseded projection: Overall RIP V6 (80/20) over Collector Appeal V2.
        # Additive and unchanged; kept for the V6-vs-V7 comparison.
        target[PUBLIC_RIP_CONTRACT_V6_KEY] = build_public_rip_contract_v6(target)
        # Superseded projection: Overall RIP V7 (90/10) over Collector Appeal
        # V3. Additive and unchanged; kept for the V7-vs-V8 comparison and for
        # any consumer still pinned to that key, which keeps receiving exactly
        # the V3-backed projection it has always received.
        target[PUBLIC_RIP_CONTRACT_V7_KEY] = build_public_rip_contract_v7(target)
        # The CANONICAL v8 projection: Overall RIP V8 (90/10 over Collector
        # Appeal V4) and Collector Appeal V4 as a first-class block, with
        # V2/v4/V5/V6/V7/CA7 preserved under `legacy`. Additive: every key above
        # is unchanged.
        target[PUBLIC_RIP_CONTRACT_V8_KEY] = build_public_rip_contract_v8(target)
        target[PUBLIC_RIP_CONTRACT_V9_KEY] = build_public_rip_contract_v9(target)

    default_target_row = next(
        (target for target in targets if target.get("target_id") == default_target_id),
        targets[0],
    )

    total_ms = (time.perf_counter() - total_started) * 1000
    return {
        "targets": targets,
        "default_target": {
            "target_type": default_target_row["target_type"],
            "target_id": default_target_row["target_id"],
        },
        "meta": {
            "sources": sources,
            "warnings": warnings,
            "ripDesirabilityComparison": comparison_diagnostics,
            "rip_desirability_comparison": comparison_diagnostics,
            "setValueAssociation": set_value_association,
            "desirabilityBundleStatus": universal_status,
            # THE SCORING IDENTITY OF THIS PAYLOAD.
            #
            # This block is not documentation. The leaderboard publisher reads
            # `overallRip.version` and `financialRip.version` straight out of it
            # and writes them into `pokemon_public_rip_leaderboard_snapshots`, so
            # whatever is stated here IS what production reports it published.
            #
            # It previously stated Financial RIP V2 and Overall RIP v4 - the
            # models this service had already stopped treating as canonical -
            # which is why the newest published leaderboard reported
            # `financial_rip_v2_60_25_15` / `overall_rip_v4_90_financial_10_ca7`
            # while 22 fresh Financial RIP V3 simulations sat underneath it. The
            # versions are now read from the ONE canonical selection in
            # `scoring_config`, so a future cutover cannot leave this behind.
            "ripWeightsConfig": {
                "financialRip": {
                    "version": CANONICAL_FINANCIAL_RIP_VERSION,
                },
                "overallRip": {
                    "weights": dict(OVERALL_RIP_V9_WEIGHTS),
                    "effectiveWeights": dict(OVERALL_RIP_V9_EFFECTIVE_WEIGHTS),
                    "version": CANONICAL_OVERALL_RIP_VERSION,
                },
                "collectorAppeal": {
                    # Version only. Collector Appeal's internal weights are not
                    # disclosed - see public_rip_contract_v7's header.
                    "version": COLLECTOR_APPEAL_V5_VERSION,
                    "weightsDisclosed": False,
                },
                "publicContract": {
                    "version": canonical_public_rip_contract_version(),
                },
                # Superseded models, under an explicitly legacy namespace so
                # nothing selects one by fallback and the comparison surfaces
                # still have the numbers they need.
                "legacy": {
                    "financialRipV2": {
                        "weights": dict(FINANCIAL_RIP_WEIGHTS),
                        "version": FINANCIAL_RIP_V2_VERSION,
                    },
                    "overallRipV4": {
                        "weights": dict(OVERALL_RIP_WEIGHTS),
                        "effectiveWeights": dict(OVERALL_RIP_EFFECTIVE_WEIGHTS),
                        "version": OVERALL_RIP_V4_VERSION,
                    },
                    "overallRipV6": {"version": OVERALL_RIP_V6_VERSION},
                    "collectorAppealV2": {"version": COLLECTOR_APPEAL_V2_VERSION},
                    "collectorAppealCA7": {"version": COLLECTOR_APPEAL_CA7_VERSION},
                },
                "weightsLabel": WEIGHTS_DISCLOSURE,
                "configVersion": "scoring_config_v1",
            },
            # The population every public rank in this payload was computed
            # against. Exposed rather than implied: a denominator the client has
            # to infer is a denominator the client can get wrong.
            "publicAnalyticsCohort": {
                "version": cohort.get("version"),
                "eligibleSetCount": cohort.get("eligibleSetCount"),
                "status": cohort.get("status"),
                "excludedCountsByReason": cohort.get("excludedCountsByReason"),
                # The Overall RIP ranking is CA7-gated, so its denominator can be
                # smaller than the eligible cohort. Surfaced so a client quotes
                # "#x of <overallRankedSetCount>" for Overall RIP, not "of 21".
                "overallRanked": cohort.get("overallRanked"),
            },
            "deprecatedFields": {
                "pack_score": "Legacy 45/25/20/10 blend; superseded by the versioned `rip` object. Do not read.",
                "relative_pack_score": "Legacy cohort min-max presentation, NOT the canonical RIP score. Do not read.",
                "pack_rank": "Legacy 33-set rank. Superseded by `rip.rank` (cohort-scoped). Do not read.",
                "pack_tier": "Legacy 33-set tier. Superseded by `rip.tier`. Do not read.",
                "relative_profit_score": "Legacy min-max presentation; use `rip.components.profit.score`.",
                "relative_safety_score": "Legacy min-max presentation; use `rip.components.safety.score`.",
                "relative_stability_score": "Legacy min-max presentation; use `rip.components.stability.score`.",
                "relative_desirability_score": "Legacy min-max presentation; use `openingExperience.collectorAppeal.score`.",
                "collector_appeal_score": (
                    "AMBIGUOUS LEGACY FIELD: this is Pure/Universal Desirability, NOT Collector "
                    "Appeal (CA7). It is intentionally NOT repointed. Read "
                    "`openingExperience.rosterDesirability` or `openingExperience.collectorAppeal`."
                ),
                "opening_desirability_score": "Legacy prototype metric; superseded by `openingExperience`.",
                "rip_score_with_desirability": "Legacy comparison field; see `rip` and universalSetDesirability.gate.",
                "rip_score_without_desirability": "Legacy comparison field; see `ripCore.score`.",
            },
            "comparisonSnapshots": {
                "currentMarketDate": current_snapshot_date,
                "previousMarketDate": previous_snapshot_date,
            },
            "timings": {
                "targets_query_ms": round(query_ms, 2),
                "set_enrichment_ms": round(set_ms, 2),
                "set_value_enrichment_ms": round(set_value_ms, 2),
                "opening_desirability_enrichment_ms": round(desirability_ms, 2),
                "top_10_card_value_enrichment_ms": round(top_10_ms, 2),
                "era_enrichment_ms": round(era_ms, 2),
                "total_backend_ms": round(total_ms, 2),
            },
            "request": {
                "limit": clamped_limit,
            },
        },
    }
