"""Read-only user pack repricing service for Tools pack simulator."""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional, Sequence, Tuple

from backend.calculations.evr.derived_metrics import _build_runtime_v2_pack_score_payload
from backend.db.clients.supabase_client import public_read_client
from backend.interpretation.rips import build_rip_interpretation

logger = logging.getLogger(__name__)


class UserPackSimulationError(Exception):
    """Structured error for tools pack simulator service."""

    def __init__(self, status_code: int, message: str, code: str):
        self.status_code = status_code
        self.message = message
        self.code = code
        super().__init__(message)


def _first_row(result: Any) -> Optional[Dict[str, Any]]:
    if result and result.data and len(result.data) > 0:
        return result.data[0]
    return None


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


def _normalize_probability(value: Any) -> Optional[float]:
    parsed = _to_optional_float(value)
    if parsed is None:
        return None
    if parsed > 1.0:
        parsed = parsed / 100.0
    if parsed < 0.0:
        return 0.0
    if parsed > 1.0:
        return 1.0
    return parsed


def _safe_ratio(numerator: Optional[float], denominator: Optional[float]) -> Optional[float]:
    if numerator is None or denominator is None or denominator == 0:
        return None
    return numerator / denominator


def _percentile_value(percentiles: Sequence[Dict[str, Any]], requested: float) -> Optional[float]:
    for row in percentiles:
        p = _to_optional_float(row.get("percentile"))
        value = _to_optional_float(row.get("value"))
        if p is None or value is None:
            continue
        if abs(p - requested) < 0.001 or abs((p * 100.0) - requested) < 0.001:
            return value
    return None


def _rows_to_probability_bins(rows: Sequence[Dict[str, Any]]) -> List[Tuple[float, float, float]]:
    parsed_rows: List[Tuple[float, float, Optional[float], Optional[float]]] = []
    for row in rows:
        floor = _to_optional_float(row.get("threshold_floor", row.get("bin_floor")))
        ceiling = _to_optional_float(row.get("threshold_ceiling", row.get("bin_ceiling")))
        probability = _normalize_probability(row.get("probability"))
        occurrence_count = _to_optional_float(row.get("occurrence_count"))
        if floor is None and ceiling is None:
            continue
        if floor is None:
            floor = ceiling
        if ceiling is None:
            ceiling = floor
        if ceiling < floor:
            floor, ceiling = ceiling, floor
        parsed_rows.append((floor, ceiling, probability, occurrence_count))

    if not parsed_rows:
        return []

    total_occurrence = sum((r[3] or 0.0) for r in parsed_rows)
    bins: List[Tuple[float, float, float]] = []
    for floor, ceiling, probability, occurrence_count in parsed_rows:
        if probability is not None:
            weight = probability
        elif total_occurrence > 0 and occurrence_count is not None:
            weight = occurrence_count / total_occurrence
        else:
            continue
        bins.append((floor, ceiling, max(0.0, weight)))

    total_weight = sum(weight for _, _, weight in bins)
    if total_weight <= 0:
        return []

    return [(floor, ceiling, weight / total_weight) for floor, ceiling, weight in bins]


def _probability_ge_from_bins(bins: Sequence[Tuple[float, float, float]], threshold: float) -> Optional[float]:
    if not bins:
        return None

    total = 0.0
    for floor, ceiling, weight in bins:
        if threshold <= floor:
            total += weight
            continue
        if threshold >= ceiling:
            continue

        span = ceiling - floor
        if span <= 0:
            total += 0.0
            continue
        fraction = (ceiling - threshold) / span
        total += max(0.0, min(1.0, fraction)) * weight

    return max(0.0, min(1.0, total))


def _loss_metrics_from_bins(
    bins: Sequence[Tuple[float, float, float]],
    pack_cost: float,
) -> Tuple[Optional[float], Optional[float], Optional[float]]:
    if not bins:
        return None, None, None

    loss_probability = 0.0
    expected_loss_unconditional = 0.0
    point_masses: List[Tuple[float, float]] = []

    for floor, ceiling, weight in bins:
        if pack_cost <= floor:
            continue

        lower = floor
        upper = min(ceiling, pack_cost)
        span = ceiling - floor
        if span <= 0:
            seg_probability = weight if floor < pack_cost else 0.0
            if seg_probability <= 0:
                continue
            representative_loss = max(pack_cost - floor, 0.0)
            loss_probability += seg_probability
            expected_loss_unconditional += representative_loss * seg_probability
            point_masses.append((representative_loss, seg_probability))
            continue

        seg_probability = weight * ((upper - lower) / span)
        if seg_probability <= 0:
            continue

        # Expected loss for X ~ Uniform(lower, upper) is pack_cost - E[X].
        expected_segment_loss = pack_cost - ((lower + upper) / 2.0)
        representative_median_loss = pack_cost - ((lower + upper) / 2.0)

        loss_probability += seg_probability
        expected_loss_unconditional += expected_segment_loss * seg_probability
        point_masses.append((max(0.0, representative_median_loss), seg_probability))

    if loss_probability <= 0:
        return 0.0, 0.0, 0.0

    expected_loss_when_losing = expected_loss_unconditional / loss_probability

    point_masses.sort(key=lambda item: item[0])
    running = 0.0
    median_loss_when_losing = None
    threshold = loss_probability * 0.5
    for value, mass in point_masses:
        running += mass
        if running >= threshold:
            median_loss_when_losing = value
            break

    return (
        loss_probability,
        expected_loss_when_losing,
        median_loss_when_losing,
    )


def _extract_set_images_and_name(set_row: Dict[str, Any], fallback_target_id: str) -> Dict[str, Any]:
    return {
        "set_name": str(set_row.get("name") or fallback_target_id),
        "logo_image_url": set_row.get("logo_image_url"),
        "symbol_image_url": set_row.get("symbol_image_url"),
        "hero_image_url": set_row.get("hero_image_url"),
    }


def _resolve_set_row(target_id: str) -> Dict[str, Any]:
    direct_result = (
        public_read_client.table("sets")
        .select("id,name,canonical_key,logo_image_url,symbol_image_url,hero_image_url")
        .eq("id", target_id)
        .limit(1)
        .execute()
    )
    direct_row = _first_row(direct_result)
    if direct_row:
        return direct_row

    canonical_result = (
        public_read_client.table("sets")
        .select("id,name,canonical_key,logo_image_url,symbol_image_url,hero_image_url")
        .eq("canonical_key", target_id)
        .limit(1)
        .execute()
    )
    return _first_row(canonical_result) or {}


def _resolve_top_hit_image_fields(
    variant_row: Optional[Dict[str, Any]],
    card_row: Optional[Dict[str, Any]],
) -> Dict[str, Optional[str]]:
    variant_small = _to_optional_str((variant_row or {}).get("image_small_url"))
    card_small = _to_optional_str((card_row or {}).get("image_small_url"))
    variant_large = _to_optional_str((variant_row or {}).get("image_large_url"))
    card_large = _to_optional_str((card_row or {}).get("image_large_url"))

    return {
        "image_url": variant_small or card_small or variant_large or card_large,
        "image_small_url": variant_small or card_small,
        "image_large_url": variant_large or card_large,
    }


def _enrich_top_hits_with_images(top_hits: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
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

    variant_lookup: Dict[str, Dict[str, Any]] = {}
    card_lookup: Dict[str, Dict[str, Any]] = {}

    if variant_ids:
        variant_result = (
            public_read_client.table("card_variants")
            .select("id,card_id,image_small_url,image_large_url")
            .in_("id", variant_ids)
            .execute()
        )
        variant_lookup = {
            str(row.get("id")): row
            for row in (variant_result.data or [])
            if row.get("id") is not None
        }

    derived_card_ids = {
        str(row.get("card_id"))
        for row in variant_lookup.values()
        if row.get("card_id") is not None
    }
    all_card_ids = sorted(set(card_ids) | derived_card_ids)
    if all_card_ids:
        card_result = (
            public_read_client.table("cards")
            .select("id,image_small_url,image_large_url")
            .in_("id", all_card_ids)
            .execute()
        )
        card_lookup = {
            str(row.get("id")): row
            for row in (card_result.data or [])
            if row.get("id") is not None
        }

    enriched_hits: List[Dict[str, Any]] = []
    for hit in top_hits:
        variant_id = _to_optional_str(hit.get("card_variant_id"))
        card_id = _to_optional_str(hit.get("card_id"))
        variant_row = variant_lookup.get(variant_id) if variant_id else None
        card_row = None
        if card_id:
            card_row = card_lookup.get(card_id)
        elif variant_row and variant_row.get("card_id") is not None:
            card_row = card_lookup.get(str(variant_row.get("card_id")))

        image_fields = _resolve_top_hit_image_fields(variant_row, card_row)
        enriched_hits.append(
            {
                **hit,
                **image_fields,
            }
        )

    return enriched_hits


def _compute_rank_and_tier(score: Optional[float], population_scores: Sequence[Optional[float]]) -> Tuple[Optional[int], Optional[str]]:
    valid_scores = [value for value in population_scores if value is not None]
    if score is None or not valid_scores:
        return None, None

    sorted_scores = sorted(valid_scores, reverse=True)
    rank = 1 + sum(1 for existing in sorted_scores if existing > score)
    total = len(sorted_scores)
    percentile = (rank / total) * 100.0

    if percentile <= 10:
        tier = "S"
    elif percentile <= 25:
        tier = "A"
    elif percentile <= 50:
        tier = "B"
    elif percentile <= 75:
        tier = "C"
    elif percentile <= 90:
        tier = "D"
    else:
        tier = "F"

    return rank, tier


def _coalesce_optional_float(*values: Any) -> Optional[float]:
    for value in values:
        parsed = _to_optional_float(value)
        if parsed is not None:
            return parsed
    return None


def _coalesce_optional_str(*values: Any) -> Optional[str]:
    for value in values:
        parsed = _to_optional_str(value)
        if parsed is not None:
            return parsed
    return None


def _summarize_interpretation(payload: Dict[str, Any]) -> Optional[str]:
    if not payload:
        return None
    direct = _to_optional_str(payload.get("packScore"))
    if direct:
        return direct
    nested = (((payload.get("meta") or {}).get("packScore") or {}).get("summary"))
    return _to_optional_str(nested)


def _build_percentile_object(percentiles: Sequence[Dict[str, Any]]) -> Dict[str, Any]:
    result: Dict[str, Any] = {}
    for row in percentiles:
        percentile = _to_optional_float(row.get("percentile"))
        value = _to_optional_float(row.get("value"))
        if percentile is None or value is None:
            continue

        if percentile <= 1.0:
            percentile = percentile * 100.0
        key = f"p{int(round(percentile))}"
        result[key] = value

    if not result:
        result["points"] = list(percentiles)
    return result


def _format_signed_number(value: Optional[float], *, decimals: int = 1, suffix: str = "") -> Optional[str]:
    if value is None:
        return None
    sign = "+" if value > 0 else "-" if value < 0 else ""
    formatted = f"{abs(value):.{decimals}f}"
    label = f"{sign}{formatted}"
    if suffix:
        label = f"{label} {suffix}".strip()
    return label


def _format_signed_currency(value: Optional[float]) -> Optional[str]:
    if value is None:
        return None
    sign = "+" if value > 0 else "-" if value < 0 else ""
    return f"{sign}${abs(value):.2f}"


def _format_currency(value: Optional[float]) -> Optional[str]:
    if value is None:
        return None
    return f"${value:.2f}"


def _transform_history_trend_rows(
    history_rows: Sequence[Dict[str, Any]],
    *,
    baseline_pack_cost: Optional[float],
    custom_pack_cost: float,
) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    market_rows: List[Dict[str, Any]] = []
    custom_rows: List[Dict[str, Any]] = []

    for row in history_rows:
        market_pack_cost = (
            _to_optional_float(row.get("market_pack_cost"))
            or _to_optional_float(row.get("pack_cost"))
            or baseline_pack_cost
        )
        mean_ratio_market = _to_optional_float(row.get("simulated_mean_pack_value_vs_pack_cost"))
        median_ratio_market = _to_optional_float(row.get("simulated_median_pack_value_vs_pack_cost"))
        p95_ratio_market = _to_optional_float(row.get("p95_value_to_cost_ratio"))

        scale = None
        if market_pack_cost is not None and custom_pack_cost > 0:
            scale = market_pack_cost / custom_pack_cost

        mean_ratio_custom = None
        median_ratio_custom = None
        p95_ratio_custom = None
        if scale is not None:
            if mean_ratio_market is not None:
                mean_ratio_custom = mean_ratio_market * scale
            if median_ratio_market is not None:
                median_ratio_custom = median_ratio_market * scale
            if p95_ratio_market is not None:
                p95_ratio_custom = p95_ratio_market * scale

        market_rows.append(
            {
                "snapshot_date": row.get("snapshot_date"),
                "run_created_at": row.get("run_created_at"),
                "calculation_run_id": row.get("calculation_run_id"),
                "market_pack_cost": market_pack_cost,
                "custom_pack_cost": custom_pack_cost,
                "simulated_mean_pack_value_vs_pack_cost": mean_ratio_market,
                "simulated_median_pack_value_vs_pack_cost": median_ratio_market,
                "p95_value_to_cost_ratio": p95_ratio_market,
                "mean_to_market_cost_ratio": mean_ratio_market,
                "median_to_market_cost_ratio": median_ratio_market,
                "p95_to_market_cost_ratio": p95_ratio_market,
                "mean_to_custom_cost_ratio": mean_ratio_custom,
                "median_to_custom_cost_ratio": median_ratio_custom,
                "p95_to_custom_cost_ratio": p95_ratio_custom,
            }
        )
        custom_rows.append(
            {
                "snapshot_date": row.get("snapshot_date"),
                "run_created_at": row.get("run_created_at"),
                "calculation_run_id": row.get("calculation_run_id"),
                "market_pack_cost": market_pack_cost,
                "custom_pack_cost": custom_pack_cost,
                "simulated_mean_pack_value_vs_pack_cost": mean_ratio_custom,
                "simulated_median_pack_value_vs_pack_cost": median_ratio_custom,
                "p95_value_to_cost_ratio": p95_ratio_custom,
                "mean_to_market_cost_ratio": mean_ratio_market,
                "median_to_market_cost_ratio": median_ratio_market,
                "p95_to_market_cost_ratio": p95_ratio_market,
                "mean_to_custom_cost_ratio": mean_ratio_custom,
                "median_to_custom_cost_ratio": median_ratio_custom,
                "p95_to_custom_cost_ratio": p95_ratio_custom,
            }
        )

    market_rows.sort(key=lambda item: (str(item.get("snapshot_date") or ""), str(item.get("run_created_at") or "")))
    custom_rows.sort(key=lambda item: (str(item.get("snapshot_date") or ""), str(item.get("run_created_at") or "")))
    return market_rows, custom_rows


def simulate_with_custom_price(
    target_type: str,
    target_id: str,
    custom_pack_cost: float,
    mode: str = "fast",
) -> Dict[str, Any]:
    requested_target_type = _to_optional_str(target_type)
    requested_target_id = _to_optional_str(target_id)
    requested_mode = _to_optional_str(mode) or "fast"
    custom_cost = _to_optional_float(custom_pack_cost)

    if requested_target_type != "set":
        raise UserPackSimulationError(
            status_code=400,
            message="target_type currently only supports 'set'",
            code="INVALID_TARGET_TYPE",
        )
    if not requested_target_id:
        raise UserPackSimulationError(
            status_code=400,
            message="target_id is required",
            code="INVALID_TARGET_ID",
        )
    if custom_cost is None:
        raise UserPackSimulationError(
            status_code=400,
            message="custom_pack_cost must be numeric",
            code="INVALID_CUSTOM_PACK_COST",
        )
    if custom_cost <= 0:
        raise UserPackSimulationError(
            status_code=400,
            message="custom_pack_cost must be greater than 0",
            code="INVALID_CUSTOM_PACK_COST",
        )
    if custom_cost >= 1000:
        raise UserPackSimulationError(
            status_code=400,
            message="custom_pack_cost must be less than 1000",
            code="INVALID_CUSTOM_PACK_COST",
        )

    approximation_notes: List[str] = []

    set_row = _resolve_set_row(requested_target_id)
    resolved_set_id = _to_optional_str(set_row.get("id")) or requested_target_id

    rip_result = (
        public_read_client.table("explore_rip_statistics_latest")
        .select("*")
        .eq("set_id", resolved_set_id)
        .limit(1)
        .execute()
    )
    rip_row = _first_row(rip_result)
    if not rip_row and requested_target_id != resolved_set_id:
        rip_fallback_result = (
            public_read_client.table("explore_rip_statistics_latest")
            .select("*")
            .eq("set_id", requested_target_id)
            .limit(1)
            .execute()
        )
        rip_row = _first_row(rip_fallback_result)

    if not rip_row:
        raise UserPackSimulationError(
            status_code=404,
            message="No persisted RIP Statistics payload is available for this set",
            code="TARGET_NOT_FOUND",
        )

    run_id = _to_optional_str(rip_row.get("calculation_run_id"))
    if not run_id:
        raise UserPackSimulationError(
            status_code=500,
            message="Latest RIP Statistics row is missing calculation_run_id",
            code="MISSING_CALCULATION_RUN_ID",
        )

    distribution_bins_result = (
        public_read_client.table("simulation_value_distribution_bins")
        .select(
            "bin_floor,bin_ceiling,occurrence_count,probability,cumulative_probability,survival_probability"
        )
        .eq("calculation_run_id", run_id)
        .order("bin_floor", desc=False)
        .execute()
    )
    distribution_bins = distribution_bins_result.data or []

    threshold_bins_result = (
        public_read_client.table("simulation_value_threshold_bins")
        .select(
            "threshold_floor,threshold_ceiling,occurrence_count,probability,cumulative_probability,survival_probability,bucket_label,bucket_order"
        )
        .eq("calculation_run_id", run_id)
        .order("bucket_order", desc=False)
        .execute()
    )
    threshold_bins = threshold_bins_result.data or []

    top_hits_result = (
        public_read_client.table("simulation_input_cards_with_near_mint_price")
        .select("card_id,card_variant_id,card_name,rarity_bucket,ev_contribution,current_near_mint_price")
        .eq("calculation_run_id", run_id)
        .order("ev_contribution", desc=True)
        .limit(10)
        .execute()
    )
    top_hits = _enrich_top_hits_with_images(top_hits_result.data or [])

    rankings_result = (
        public_read_client.table("simulation_pull_summary")
        .select("rarity_bucket,pulled_count,avg_sampled_value,total_sampled_value")
        .eq("calculation_run_id", run_id)
        .order("rarity_bucket", desc=False)
        .execute()
    )
    rankings = rankings_result.data or []

    rip_statistics: Dict[str, Any] = {"pack_paths": {}, "normal_pack_states": {}}
    state_counts_result = (
        public_read_client.table("simulation_state_counts")
        .select("state_group,state_name,occurrence_count")
        .eq("calculation_run_id", run_id)
        .execute()
    )
    for row in (state_counts_result.data or []):
        group = row.get("state_group")
        name = row.get("state_name")
        count = row.get("occurrence_count", 0)
        if group == "pack_path":
            rip_statistics["pack_paths"][name] = count
        elif group == "normal_pack_state":
            rip_statistics["normal_pack_states"][name] = count

    percentiles_result = (
        public_read_client.table("simulation_percentiles")
        .select("percentile,value")
        .eq("calculation_run_id", run_id)
        .order("percentile", desc=False)
        .execute()
    )
    percentiles = percentiles_result.data or []

    run_summary_result = (
        public_read_client.table("simulation_run_summary")
        .select(
            "pack_cost,mean_value,median_value,net_value,roi,roi_percent,prob_profit,prob_big_hit,"
            "expected_loss_when_losing,median_loss_when_losing,coefficient_of_variation,tail_value_p05"
        )
        .eq("calculation_run_id", run_id)
        .single()
        .execute()
    )
    run_summary = run_summary_result.data or {}

    derived_result = (
        public_read_client.table("simulation_derived_metrics")
        .select("*")
        .eq("calculation_run_id", run_id)
        .single()
        .execute()
    )
    derived_metrics = derived_result.data or {}

    ranking_current_result = (
        public_read_client.table("set_pack_score_rankings_latest")
        .select("target_id,pack_rank,pack_tier,profit_rank,profit_tier,safety_rank,safety_tier,stability_rank,stability_tier")
        .eq("target_id", resolved_set_id)
        .limit(1)
        .execute()
    )
    ranking_current = _first_row(ranking_current_result) or {}

    ranking_population_result = (
        public_read_client.table("set_pack_score_rankings_latest")
        .select("target_id,pack_score,profit_score,safety_score,stability_score")
        .execute()
    )
    ranking_population = ranking_population_result.data or []

    history_rows: List[Dict[str, Any]] = []
    try:
        history_result = (
            public_read_client.table("calculation_history_trend")
            .select(
                "snapshot_date,simulated_mean_pack_value_vs_pack_cost,"
                "simulated_median_pack_value_vs_pack_cost,run_created_at,calculation_run_id,"
                "p95_value_to_cost_ratio,market_pack_cost,pack_cost"
            )
            .eq("target_type", "set")
            .eq("target_id", resolved_set_id)
            .order("snapshot_date", desc=True)
            .limit(180)
            .execute()
        )
        history_rows = history_result.data or []
    except Exception:
        try:
            history_result_fallback = (
                public_read_client.table("calculation_history_trend")
                .select(
                    "snapshot_date,simulated_mean_pack_value_vs_pack_cost,"
                    "simulated_median_pack_value_vs_pack_cost,run_created_at,calculation_run_id,"
                    "p95_value_to_cost_ratio"
                )
                .eq("target_type", "set")
                .eq("target_id", resolved_set_id)
                .order("snapshot_date", desc=True)
                .limit(180)
                .execute()
            )
            history_rows = history_result_fallback.data or []
        except Exception:
            approximation_notes.append(
                "Historical trend data could not be loaded for this set."
            )

    baseline_pack_cost = (
        _to_optional_float(rip_row.get("pack_cost"))
        or _to_optional_float(run_summary.get("pack_cost"))
    )
    mean_value = (
        _to_optional_float(rip_row.get("mean_value"))
        or _to_optional_float(run_summary.get("mean_value"))
    )
    median_value = (
        _to_optional_float(rip_row.get("median_value"))
        or _to_optional_float(run_summary.get("median_value"))
    )
    prob_profit_baseline = (
        _normalize_probability(rip_row.get("prob_profit"))
        if rip_row.get("prob_profit") is not None
        else _normalize_probability(run_summary.get("prob_profit"))
    )
    prob_big_hit_baseline = (
        _normalize_probability(rip_row.get("prob_big_hit"))
        if rip_row.get("prob_big_hit") is not None
        else _normalize_probability(run_summary.get("prob_big_hit"))
    )

    expected_loss_baseline = (
        _to_optional_float(rip_row.get("expected_loss_when_losing"))
        or _to_optional_float(run_summary.get("expected_loss_when_losing"))
    )
    median_loss_baseline = (
        _to_optional_float(rip_row.get("median_loss_when_losing"))
        or _to_optional_float(run_summary.get("median_loss_when_losing"))
    )

    if baseline_pack_cost is None or mean_value is None or median_value is None:
        raise UserPackSimulationError(
            status_code=500,
            message="Missing required baseline summary fields in latest simulation payload",
            code="MISSING_BASELINE_SUMMARY_FIELDS",
        )

    history_trend_market, history_trend_custom = _transform_history_trend_rows(
        history_rows,
        baseline_pack_cost=baseline_pack_cost,
        custom_pack_cost=custom_cost,
    )

    baseline_roi = _safe_ratio(mean_value, baseline_pack_cost)
    baseline_roi_percent = ((baseline_roi - 1.0) * 100.0) if baseline_roi is not None else None
    baseline_net_value = mean_value - baseline_pack_cost

    probability_bins = _rows_to_probability_bins(threshold_bins or distribution_bins)
    if not probability_bins:
        approximation_notes.append(
            "Distribution bins were unavailable; probability and loss metrics reuse baseline values where needed."
        )

    custom_prob_profit = _probability_ge_from_bins(probability_bins, custom_cost)
    if custom_prob_profit is None:
        custom_prob_profit = prob_profit_baseline

    custom_big_hit_threshold = custom_cost * 5.0
    custom_prob_big_hit = _probability_ge_from_bins(probability_bins, custom_big_hit_threshold)
    if custom_prob_big_hit is None:
        custom_prob_big_hit = prob_big_hit_baseline

    losing_probability, custom_expected_loss, custom_median_loss = _loss_metrics_from_bins(probability_bins, custom_cost)
    if custom_expected_loss is None:
        custom_expected_loss = expected_loss_baseline
    if custom_median_loss is None:
        custom_median_loss = median_loss_baseline

    p95_value = _percentile_value(percentiles, 95.0)
    if p95_value is None:
        p95_ratio = _to_optional_float(rip_row.get("p95_value_to_cost_ratio"))
        if p95_ratio is not None:
            p95_value = p95_ratio * baseline_pack_cost

    tail_value_p05 = _percentile_value(percentiles, 5.0)
    if tail_value_p05 is None:
        tail_value_p05 = (
            _to_optional_float(rip_row.get("tail_value_p05"))
            or _to_optional_float(run_summary.get("tail_value_p05"))
        )

    score_payload = _build_runtime_v2_pack_score_payload(
        pack_metrics={
            "pack_cost": custom_cost,
            "mean": mean_value,
            "median": median_value,
            "p95": p95_value,
            "prob_profit": custom_prob_profit,
            "expected_loss_given_loss": custom_expected_loss,
            "median_loss_given_loss": custom_median_loss,
            "tail_value_p05": tail_value_p05,
            "coefficient_of_variation": (
                _to_optional_float(rip_row.get("coefficient_of_variation"))
                or _to_optional_float(run_summary.get("coefficient_of_variation"))
            ),
        },
        chase_metrics={
            "hhi_ev_concentration": _to_optional_float(rip_row.get("hhi_ev_concentration"))
            or _to_optional_float(derived_metrics.get("hhi_ev_concentration")),
            "effective_chase_count": _to_optional_float(rip_row.get("effective_chase_count"))
            or _to_optional_float(derived_metrics.get("effective_chase_count")),
        },
    )

    custom_profit_score = _to_optional_float(score_payload.get("profit_score"))
    custom_safety_score = _to_optional_float(score_payload.get("safety_score"))
    baseline_stability_score = _to_optional_float(rip_row.get("stability_score"))
    custom_stability_score = baseline_stability_score

    if (
        custom_profit_score is not None
        and custom_safety_score is not None
        and custom_stability_score is not None
    ):
        # Match runtime v2 weight blend while preserving baseline stability for repricing.
        custom_pack_score = round(
            (custom_profit_score * 0.45) + (custom_safety_score * 0.30) + (custom_stability_score * 0.25),
            2,
        )
    else:
        custom_pack_score = _to_optional_float(score_payload.get("pack_score"))

    population_pack_scores = [_to_optional_float(row.get("pack_score")) for row in ranking_population]
    population_profit_scores = [_to_optional_float(row.get("profit_score")) for row in ranking_population]
    population_safety_scores = [_to_optional_float(row.get("safety_score")) for row in ranking_population]
    population_stability_scores = [_to_optional_float(row.get("stability_score")) for row in ranking_population]
    custom_pack_rank, custom_pack_tier = _compute_rank_and_tier(custom_pack_score, population_pack_scores)
    custom_profit_rank, custom_profit_tier = _compute_rank_and_tier(custom_profit_score, population_profit_scores)
    custom_safety_rank, custom_safety_tier = _compute_rank_and_tier(custom_safety_score, population_safety_scores)
    custom_stability_rank, custom_stability_tier = _compute_rank_and_tier(
        custom_stability_score,
        population_stability_scores,
    )

    baseline_interpretation_payload = build_rip_interpretation(
        {
            "summary": {
                **rip_row,
                "pack_cost": baseline_pack_cost,
                "mean_value": mean_value,
                "median_value": median_value,
                "net_value": baseline_net_value,
                "roi": baseline_roi,
                "roi_percent": baseline_roi_percent,
                "prob_profit": prob_profit_baseline,
                "prob_big_hit": prob_big_hit_baseline,
                "expected_loss_when_losing": expected_loss_baseline,
                "median_loss_when_losing": median_loss_baseline,
            },
            "rankings": [],
            "rip_statistics": {"pack_paths": {}, "normal_pack_states": {}},
            "percentiles": percentiles,
            "distribution_bins": distribution_bins,
            "threshold_bins": threshold_bins,
            "top_hits": [],
            "history_trend": history_trend_market,
        }
    )

    custom_roi = _safe_ratio(mean_value, custom_cost)
    custom_roi_percent = ((custom_roi - 1.0) * 100.0) if custom_roi is not None else None
    custom_net_value = mean_value - custom_cost

    custom_interpretation_payload = build_rip_interpretation(
        {
            "summary": {
                **rip_row,
                "pack_cost": custom_cost,
                "mean_value": mean_value,
                "median_value": median_value,
                "net_value": custom_net_value,
                "roi": custom_roi,
                "roi_percent": custom_roi_percent,
                "prob_profit": custom_prob_profit,
                "prob_big_hit": custom_prob_big_hit,
                "expected_loss_when_losing": custom_expected_loss,
                "median_loss_when_losing": custom_median_loss,
                "profit_score": custom_profit_score,
                "safety_score": custom_safety_score,
                "stability_score": custom_stability_score,
                "pack_score": custom_pack_score,
                "pack_tier": custom_pack_tier or rip_row.get("pack_tier"),
                "profit_tier": custom_profit_tier or rip_row.get("profit_tier"),
                "safety_tier": custom_safety_tier or rip_row.get("safety_tier"),
                "stability_tier": custom_stability_tier or rip_row.get("stability_tier"),
            },
            "rankings": rankings,
            "rip_statistics": rip_statistics,
            "percentiles": percentiles,
            "distribution_bins": distribution_bins,
            "threshold_bins": threshold_bins,
            "top_hits": top_hits,
            "history_trend": history_trend_custom,
        }
    )

    baseline = {
        "pack_cost": baseline_pack_cost,
        "simulation_count": _to_optional_float(rip_row.get("simulation_count"))
        or _to_optional_float(run_summary.get("simulation_count")),
        "pack_score": _to_optional_float(rip_row.get("pack_score")),
        "pack_rank": _coalesce_optional_float(rip_row.get("pack_rank"), ranking_current.get("pack_rank")),
        "pack_tier": _coalesce_optional_str(rip_row.get("pack_tier"), ranking_current.get("pack_tier")),
        "profit_score": _to_optional_float(rip_row.get("profit_score")),
        "profit_rank": _coalesce_optional_float(rip_row.get("profit_rank"), ranking_current.get("profit_rank")),
        "profit_tier": _coalesce_optional_str(rip_row.get("profit_tier"), ranking_current.get("profit_tier")),
        "safety_score": _to_optional_float(rip_row.get("safety_score")),
        "safety_rank": _coalesce_optional_float(rip_row.get("safety_rank"), ranking_current.get("safety_rank")),
        "safety_tier": _coalesce_optional_str(rip_row.get("safety_tier"), ranking_current.get("safety_tier")),
        "stability_score": _to_optional_float(rip_row.get("stability_score")),
        "stability_rank": _coalesce_optional_float(rip_row.get("stability_rank"), ranking_current.get("stability_rank")),
        "stability_tier": _coalesce_optional_str(rip_row.get("stability_tier"), ranking_current.get("stability_tier")),
        "prob_profit": prob_profit_baseline,
        "prob_big_hit": prob_big_hit_baseline,
        "mean_value": mean_value,
        "median_value": median_value,
        "net_value": baseline_net_value,
        "roi": baseline_roi,
        "roi_percent": baseline_roi_percent,
        "expected_loss_when_losing": expected_loss_baseline,
        "median_loss_when_losing": median_loss_baseline,
        "interpretation": _summarize_interpretation(baseline_interpretation_payload),
        "interpretation_meta": baseline_interpretation_payload.get("meta"),
    }

    custom = {
        "pack_cost": custom_cost,
        "simulation_count": None,
        "pack_score": custom_pack_score,
        "pack_rank": custom_pack_rank,
        "pack_tier": custom_pack_tier or baseline.get("pack_tier"),
        "profit_score": custom_profit_score,
        "profit_rank": custom_profit_rank,
        "profit_tier": custom_profit_tier,
        "safety_score": custom_safety_score,
        "safety_rank": custom_safety_rank,
        "safety_tier": custom_safety_tier,
        "stability_score": custom_stability_score,
        "stability_rank": custom_stability_rank,
        "stability_tier": custom_stability_tier,
        "prob_profit": custom_prob_profit,
        "prob_big_hit": custom_prob_big_hit,
        "mean_value": mean_value,
        "median_value": median_value,
        "net_value": custom_net_value,
        "roi": custom_roi,
        "roi_percent": custom_roi_percent,
        "expected_loss_when_losing": custom_expected_loss,
        "median_loss_when_losing": custom_median_loss,
        "interpretation": _summarize_interpretation(custom_interpretation_payload),
        "interpretation_meta": custom_interpretation_payload.get("meta"),
    }

    if threshold_bins and not distribution_bins:
        approximation_notes.append(
            "Used simulation_value_threshold_bins for repricing approximations because value distribution bins were unavailable."
        )
    if custom_prob_profit is None or custom_prob_big_hit is None:
        approximation_notes.append(
            "Could not fully recompute probability metrics from bins; fallback values were used where necessary."
        )
    if losing_probability is None:
        approximation_notes.append(
            "Loss metrics were approximated from histogram bins rather than raw simulation outcomes."
        )
    if requested_mode != "fast":
        approximation_notes.append(
            "Only fast repricing mode is currently supported; request mode was treated as fast."
        )

    p95_to_market_cost_ratio = _safe_ratio(p95_value, baseline_pack_cost)
    p95_to_custom_cost_ratio = _safe_ratio(p95_value, custom_cost)

    chance_to_beat_cost_diff_pts = None
    if custom_prob_profit is not None and prob_profit_baseline is not None:
        chance_to_beat_cost_diff_pts = (custom_prob_profit - prob_profit_baseline) * 100.0

    roi_return_diff_pts = None
    if custom_roi_percent is not None and baseline_roi_percent is not None:
        roi_return_diff_pts = custom_roi_percent - baseline_roi_percent

    average_loss_diff = None
    if custom_expected_loss is not None and expected_loss_baseline is not None:
        average_loss_diff = custom_expected_loss - expected_loss_baseline

    p95_cost_diff = None
    if p95_to_custom_cost_ratio is not None and p95_to_market_cost_ratio is not None:
        p95_cost_diff = p95_to_custom_cost_ratio - p95_to_market_cost_ratio

    latest_history_row = history_trend_custom[-1] if history_trend_custom else None

    comparison = {
        "pack_cost_delta": (custom.get("pack_cost") or 0.0) - (baseline.get("pack_cost") or 0.0),
        "pack_score_delta": (custom.get("pack_score") or 0.0) - (baseline.get("pack_score") or 0.0),
        "profit_score_delta": (custom.get("profit_score") or 0.0) - (baseline.get("profit_score") or 0.0),
        "safety_score_delta": (custom.get("safety_score") or 0.0) - (baseline.get("safety_score") or 0.0),
        "stability_score_delta": (custom.get("stability_score") or 0.0) - (baseline.get("stability_score") or 0.0),
        "prob_profit_delta": (custom.get("prob_profit") or 0.0) - (baseline.get("prob_profit") or 0.0),
        "roi_percent_delta": (custom.get("roi_percent") or 0.0) - (baseline.get("roi_percent") or 0.0),
        "prob_profit_delta_percentage_points": chance_to_beat_cost_diff_pts,
        "roi_percent_delta_percentage_points": roi_return_diff_pts,
        "tier_changed": _to_optional_str(custom.get("pack_tier")) != _to_optional_str(baseline.get("pack_tier")),
        "summary_metrics": {
            "pack_cost": {
                "market_value": baseline_pack_cost,
                "custom_value": custom_cost,
                "difference_value": (custom_cost - baseline_pack_cost),
                "difference_label": _format_signed_currency((custom_cost - baseline_pack_cost)),
                "difference_unit": "currency",
                "is_improvement": custom_cost < baseline_pack_cost,
            },
            "chance_to_beat_cost": {
                "market_value": prob_profit_baseline,
                "custom_value": custom_prob_profit,
                "difference_value": chance_to_beat_cost_diff_pts,
                "difference_label": _format_signed_number(chance_to_beat_cost_diff_pts, decimals=1, suffix="pts"),
                "difference_unit": "percentage_points",
                "is_improvement": (chance_to_beat_cost_diff_pts or 0.0) > 0.0,
            },
            "average_loss_when_losing": {
                "market_value": expected_loss_baseline,
                "custom_value": custom_expected_loss,
                "difference_value": average_loss_diff,
                "difference_label": _format_signed_currency(average_loss_diff),
                "difference_unit": "currency",
                "is_improvement": (average_loss_diff or 0.0) < 0.0,
            },
            "roi_return": {
                "market_value": baseline_roi_percent,
                "custom_value": custom_roi_percent,
                "difference_value": roi_return_diff_pts,
                "difference_label": _format_signed_number(roi_return_diff_pts, decimals=1, suffix="pts"),
                "difference_unit": "percentage_points",
                "is_improvement": (roi_return_diff_pts or 0.0) > 0.0,
            },
            "average_pack_value": {
                "value": mean_value,
                "value_label": _format_currency(mean_value),
                "note": "Same simulation value",
            },
        },
        "score_deltas": {
            "pack": (custom.get("pack_score") or 0.0) - (baseline.get("pack_score") or 0.0),
            "profit": (custom.get("profit_score") or 0.0) - (baseline.get("profit_score") or 0.0),
            "safety": (custom.get("safety_score") or 0.0) - (baseline.get("safety_score") or 0.0),
            "stability": (custom.get("stability_score") or 0.0) - (baseline.get("stability_score") or 0.0),
        },
        "pillar_metrics": {
            "profit": {
                "chance_to_beat_cost": {
                    "market_value": prob_profit_baseline,
                    "custom_value": custom_prob_profit,
                    "difference_value": chance_to_beat_cost_diff_pts,
                    "difference_unit": "percentage_points",
                },
                "p95_to_cost": {
                    "market_value": p95_to_market_cost_ratio,
                    "custom_value": p95_to_custom_cost_ratio,
                    "difference_value": p95_cost_diff,
                    "difference_label": _format_signed_number(p95_cost_diff, decimals=2),
                },
                "roi_return": {
                    "market_value": baseline_roi_percent,
                    "custom_value": custom_roi_percent,
                    "difference_value": roi_return_diff_pts,
                    "difference_unit": "percentage_points",
                },
            },
            "safety": {
                "average_loss_when_losing": {
                    "market_value": expected_loss_baseline,
                    "custom_value": custom_expected_loss,
                    "difference_value": average_loss_diff,
                },
                "typical_loss_when_losing": {
                    "market_value": median_loss_baseline,
                    "custom_value": custom_median_loss,
                    "difference_value": (
                        (custom_median_loss - median_loss_baseline)
                        if custom_median_loss is not None and median_loss_baseline is not None
                        else None
                    ),
                },
                "bad_pack_floor": {
                    "market_value": tail_value_p05,
                    "custom_value": tail_value_p05,
                    "difference_value": 0.0,
                },
            },
            "stability": {
                "stability_score": {
                    "market_value": baseline_stability_score,
                    "custom_value": custom_stability_score,
                    "difference_value": (
                        (custom_stability_score - baseline_stability_score)
                        if custom_stability_score is not None and baseline_stability_score is not None
                        else None
                    ),
                }
            },
        },
        "historical_cost_ratios": {
            "latest": {
                "mean_to_custom_cost_ratio": _to_optional_float((latest_history_row or {}).get("mean_to_custom_cost_ratio")),
                "median_to_custom_cost_ratio": _to_optional_float((latest_history_row or {}).get("median_to_custom_cost_ratio")),
                "p95_to_custom_cost_ratio": _to_optional_float((latest_history_row or {}).get("p95_to_custom_cost_ratio")),
                "mean_to_market_cost_ratio": _to_optional_float((latest_history_row or {}).get("mean_to_market_cost_ratio")),
                "median_to_market_cost_ratio": _to_optional_float((latest_history_row or {}).get("median_to_market_cost_ratio")),
                "p95_to_market_cost_ratio": _to_optional_float((latest_history_row or {}).get("p95_to_market_cost_ratio")),
            }
        },
    }

    return {
        "target": {
            "target_type": "set",
            "target_id": resolved_set_id,
            **_extract_set_images_and_name(set_row, resolved_set_id),
        },
        "baseline": baseline,
        "custom": custom,
        "comparison": comparison,
        "charts": {
            "distribution_bins": distribution_bins,
            "threshold_bins": threshold_bins,
            "percentiles": _build_percentile_object(percentiles),
            "baseline_reference_lines": {
                "pack_cost": baseline_pack_cost,
                "mean_value": mean_value,
                "median_value": median_value,
            },
            "custom_reference_lines": {
                "pack_cost": custom_cost,
                "break_even": custom_cost,
                "big_hit_threshold": custom_big_hit_threshold,
            },
        },
        "context": {
            "top_hits": top_hits,
            "rankings": rankings,
            "rip_statistics": rip_statistics,
            "history_trend": history_trend_custom,
            "history_trend_market": history_trend_market,
        },
        "meta": {
            "mode": "repriced_from_latest_distribution",
            "requested_mode": requested_mode,
            "uses_latest_production_simulation": True,
            "writes_to_database": False,
            "calculation_run_id": run_id,
            "approximation_notes": approximation_notes,
        },
    }
