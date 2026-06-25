"""Set-level desirability proof and validation helpers for Pokemon snapshots."""

from __future__ import annotations

import math
from statistics import mean
from typing import Any, Dict, Iterable, List, Mapping, Optional, Tuple

FORMULA_VERSION = "desirability_validation_v1"

ALIGNMENT_WEIGHTS = {
    "top_chase_value": 0.25,
    "top_10_card_value": 0.25,
    "set_value": 0.20,
    "avg_hit_value": 0.15,
    "p95_value": 0.10,
    "expected_value": 0.05,
}

SUBSET_NAME_PATTERNS = (
    ("trainer gallery", "trainer_gallery"),
    ("galarian gallery", "galarian_gallery"),
    ("classic collection", "classic_collection"),
    ("radiant collection", "radiant_collection"),
    ("shiny vault", "shiny_vault"),
)


def to_optional_float(value: Any) -> Optional[float]:
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return None
    return parsed if math.isfinite(parsed) else None


def to_optional_int(value: Any) -> Optional[int]:
    parsed = to_optional_float(value)
    return int(parsed) if parsed is not None else None


def first_present(source: Mapping[str, Any], keys: Iterable[str]) -> Any:
    for key in keys:
        value = source.get(key)
        if value is not None:
            return value
    return None


def first_numeric(source: Mapping[str, Any], keys: Iterable[str]) -> Optional[float]:
    return to_optional_float(first_present(source, keys))


def nested_sources(row: Mapping[str, Any]) -> List[Mapping[str, Any]]:
    sources: List[Mapping[str, Any]] = [row]
    for key in ("summary", "market", "metrics", "snapshot", "openingDesirability", "opening_desirability", "desirabilityValidation", "desirability_validation"):
        value = row.get(key)
        if isinstance(value, Mapping):
            sources.append(value)
    return sources


def first_nested_numeric(row: Mapping[str, Any], keys: Iterable[str]) -> Optional[float]:
    for source in nested_sources(row):
        value = first_numeric(source, keys)
        if value is not None:
            return value
    return None


def first_nested_value(row: Mapping[str, Any], keys: Iterable[str]) -> Any:
    for source in nested_sources(row):
        value = first_present(source, keys)
        if value is not None:
            return value
    return None


def clamp(value: float, lower: float = 0.0, upper: float = 100.0) -> float:
    return max(lower, min(upper, value))


def alignment_score(left_rank: Any, right_rank: Any, total_ranked_sets: int) -> Optional[float]:
    left = to_optional_int(left_rank)
    right = to_optional_int(right_rank)
    if left is None or right is None or total_ranked_sets <= 0:
        return None
    rank_gap = abs(left - right)
    return round(clamp(100.0 - ((rank_gap / total_ranked_sets) * 100.0)), 2)


def alignment_band(score: Any) -> Optional[str]:
    parsed = to_optional_float(score)
    if parsed is None:
        return None
    if parsed >= 75:
        return "strong"
    if parsed >= 55:
        return "moderate"
    return "weak"


def impact_band(score_delta: Any, rank_delta: Any) -> str:
    score = to_optional_float(score_delta) or 0.0
    rank = to_optional_float(rank_delta) or 0.0
    if score > 1 or rank > 0:
        return "lift"
    if score < -1 or rank < 0:
        return "drag"
    return "neutral"


def desirability_impact_summary(band: str) -> str:
    if band == "lift":
        return "Desirability lifts this set because its collector-demand profile is stronger than its math-only RIP profile."
    if band == "drag":
        return "Desirability pulls this set down because its financial profile is stronger than its collector-demand profile."
    return "Desirability is broadly in line with this set's math-only RIP profile."


def desirability_alignment_summary(band: Optional[str]) -> str:
    if band == "strong":
        return "This set's desirability is strongly supported by market and chase outcomes."
    if band == "moderate":
        return "This set shows partial market confirmation, with some chase/value signals aligning more closely than others."
    return "This set's desirability is less confirmed by current market outcomes, which may reflect supply, age, pull-rate, or pricing effects."


def card_appeal_summary(band: Optional[str], available: bool) -> str:
    if not available:
        return "Card appeal validation is not available for this set yet."
    if band in {"strong", "moderate"}:
        return "Card appeal supports this set's desirability because the cards driving collector demand also align with chase/value outcomes."
    return "Card appeal is less confirmed by current market outcomes, which may indicate pricing, supply, pull-rate, or recency effects."


def calculate_rip_core_score_without_desirability(row: Mapping[str, Any]) -> Optional[float]:
    direct = first_nested_numeric(row, ("rip_core_score_without_desirability", "ripCoreScoreWithoutDesirability"))
    if direct is not None:
        return round(direct, 2)
    component_scores = [
        first_nested_numeric(row, ("profit_score", "profitScore", "relative_profit_score", "relativeProfitScore")),
        first_nested_numeric(row, ("safety_score", "safetyScore", "relative_safety_score", "relativeSafetyScore")),
        first_nested_numeric(row, ("stability_score", "stabilityScore", "relative_stability_score", "relativeStabilityScore")),
    ]
    available = [score for score in component_scores if score is not None]
    return round(mean(available), 2) if available else None


def normalize_set_id(row: Mapping[str, Any]) -> Optional[str]:
    value = first_nested_value(row, ("set_id", "setId", "id", "target_id", "targetId"))
    return str(value) if value is not None and str(value).strip() else None


def _truthy(value: Any) -> Optional[bool]:
    if value is True or value is False:
        return value
    text = str(value or "").strip().lower()
    if text in {"true", "1", "yes"}:
        return True
    if text in {"false", "0", "no"}:
        return False
    return None


def subset_type_for_row(row: Mapping[str, Any]) -> Optional[str]:
    explicit = first_nested_value(row, ("subset_type", "subsetType"))
    if explicit:
        return str(explicit)
    name = str(first_nested_value(row, ("name", "set_name", "setName", "canonical_key", "slug")) or "").lower()
    for needle, subset_type in SUBSET_NAME_PATTERNS:
        if needle in name:
            return subset_type
    return None


def parent_opening_set_id(row: Mapping[str, Any]) -> Optional[str]:
    value = first_nested_value(row, ("parent_opening_set_id", "parentOpeningSetId", "parent_set_id", "parentSetId"))
    return str(value) if value is not None and str(value).strip() else None


def is_subset_row(row: Mapping[str, Any]) -> bool:
    explicit = _truthy(first_nested_value(row, ("is_subset", "isSubset")))
    if explicit is not None:
        return explicit
    return subset_type_for_row(row) is not None


def is_opening_set_row(row: Mapping[str, Any]) -> bool:
    explicit = _truthy(first_nested_value(row, ("is_opening_set", "isOpeningSet")))
    if explicit is not None:
        return explicit
    return not is_subset_row(row)


def _merge_subset_into_parent(parent: Dict[str, Any], subset: Dict[str, Any]) -> None:
    for key in ("set_value", "top_10_card_value"):
        subset_value = to_optional_float(subset.get(key))
        if subset_value is not None:
            parent[key] = round((to_optional_float(parent.get(key)) or 0.0) + subset_value, 2)
    for key in ("top_chase_value", "avg_hit_value", "median_hit_value", "card_appeal_score"):
        subset_value = to_optional_float(subset.get(key))
        parent_value = to_optional_float(parent.get(key))
        if subset_value is not None and (parent_value is None or subset_value > parent_value):
            parent[key] = subset_value


def build_opening_set_audit(target_rows: Iterable[Mapping[str, Any]]) -> Dict[str, Any]:
    raw_rows = [row for row in target_rows if isinstance(row, Mapping)]
    subset_rows = [row for row in raw_rows if is_subset_row(row)]
    mapped_subset_rows = [row for row in subset_rows if parent_opening_set_id(row)]
    missing_parent = [normalize_set_id(row) for row in subset_rows if not parent_opening_set_id(row)]
    rollup_parent_ids = sorted({parent_opening_set_id(row) for row in mapped_subset_rows if parent_opening_set_id(row)})
    return {
        "total_raw_pokemon_set_rows": len(raw_rows),
        "total_opening_sets": sum(1 for row in raw_rows if is_opening_set_row(row)),
        "total_subset_rows": len(subset_rows),
        "subset_rows_mapped_to_parent_opening_sets": len(mapped_subset_rows),
        "subset_rows_missing_parent_mapping": len(subset_rows) - len(mapped_subset_rows),
        "subset_rows_missing_parent_mapping_ids": [value for value in missing_parent if value],
        "sets_whose_combined_card_count_or_value_changes_after_rollup": rollup_parent_ids,
    }


def _rank_values(rows: List[Dict[str, Any]], value_key: str, rank_key: str, *, descending: bool = True) -> None:
    sortable = [
        row
        for row in rows
        if to_optional_float(row.get(value_key)) is not None
    ]
    sortable.sort(key=lambda item: to_optional_float(item.get(value_key)) or 0.0, reverse=descending)
    for index, row in enumerate(sortable, start=1):
        row[rank_key] = index


def _extract_card_appeal_from_cards(cards_payload: Optional[Mapping[str, Any]]) -> Optional[float]:
    if not isinstance(cards_payload, Mapping):
        return None
    cards = cards_payload.get("cards")
    if not isinstance(cards, list):
        validation = cards_payload.get("cardDesirabilityValidation") or cards_payload.get("card_desirability_validation") or {}
        cards = validation.get("cards") if isinstance(validation, Mapping) else []
    scores: List[float] = []
    for card in cards or []:
        if not isinstance(card, Mapping):
            continue
        score = first_numeric(
            card,
            (
                "cardAppealScore",
                "card_appeal_score",
                "adjustedCardAppealScore",
                "adjusted_card_appeal_score",
                "scarcityAdjustedCardAppealScore",
                "scarcity_adjusted_card_appeal_score",
            ),
        )
        price = first_numeric(card, ("marketPrice", "market_price", "currentPrice", "current_price"))
        if score is not None and price is not None and price > 0:
            scores.append(score)
    if not scores:
        return None
    return round(mean(sorted(scores, reverse=True)[:10]), 2)


def _base_validation_row(row: Mapping[str, Any]) -> Dict[str, Any]:
    summary = row.get("summary") if isinstance(row.get("summary"), Mapping) else row
    top_hits = row.get("top_hits") if isinstance(row.get("top_hits"), list) else row.get("topHits") if isinstance(row.get("topHits"), list) else []
    top_hit_prices = [
        first_numeric(hit, ("marketPrice", "market_price", "currentPrice", "current_price", "price", "cardPrice", "card_price", "ev_contribution"))
        for hit in top_hits
        if isinstance(hit, Mapping)
    ]
    top_hit_prices = [price for price in top_hit_prices if price is not None]
    return {
        "set_id": normalize_set_id(row),
        "set_name": first_nested_value(row, ("name", "set_name", "setName")),
        "desirability_score": first_nested_numeric(row, ("relative_desirability_score", "relativeDesirabilityScore", "desirability_score", "desirabilityScore", "openingDesirabilityScore", "opening_desirability_score")),
        "desirability_rank": to_optional_int(first_nested_numeric(row, ("desirability_rank", "desirabilityRank", "openingDesirabilityRank", "opening_desirability_rank"))),
        "card_appeal_score": first_nested_numeric(row, ("card_appeal_score", "cardAppealScore", "collectorAppealScore", "collector_appeal_score")),
        "card_appeal_rank": to_optional_int(first_nested_numeric(row, ("card_appeal_rank", "cardAppealRank", "collectorAppealRank", "collector_appeal_rank"))),
        "rip_core_score_without_desirability": calculate_rip_core_score_without_desirability(row),
        "final_rip_score_with_desirability": first_nested_numeric(row, ("relative_pack_score", "relativePackScore", "pack_score", "packScore")),
        "final_rip_rank_with_desirability": to_optional_int(first_nested_numeric(row, ("pack_rank", "packRank", "rank"))),
        "set_value": first_nested_numeric(row, ("checklistSetValue", "checklist_set_value", "currentChecklistSetValue", "current_checklist_set_value", "setValue", "set_value", "simulated_set_value", "simulatedSetValue")),
        "pack_cost": first_nested_numeric(row, ("pack_cost", "packCost", "current_pack_cost", "currentPackCost", "pack_market_price", "packMarketPrice")),
        "expected_value": first_nested_numeric(row, ("mean_value", "meanValue", "expected_value", "expectedValue", "average_pack_value", "averagePackValue")),
        "p95_value": first_nested_numeric(row, ("p95_value", "p95Value", "p95_value_to_cost_ratio", "p95ValueToCostRatio")),
        "top_chase_value": first_nested_numeric(row, ("top_chase_value", "topChaseValue", "max_value", "maxValue", "best_pull", "bestPull")),
        "top_10_card_value": first_nested_numeric(row, ("top_10_card_value", "top10CardValue", "top10_set_value", "top10SetValue")),
        "avg_hit_value": first_nested_numeric(row, ("avg_hit_value", "avgHitValue", "average_hit_value", "averageHitValue", "big_hit_threshold", "bigHitThreshold")),
        "median_hit_value": first_nested_numeric(row, ("median_hit_value", "medianHitValue")),
        "_top_hit_prices": top_hit_prices,
        "_summary": summary,
    }


def build_validation_rows(target_rows: Iterable[Mapping[str, Any]]) -> List[Dict[str, Any]]:
    raw_rows = [row for row in target_rows if isinstance(row, Mapping)]
    opening_rows = [_base_validation_row(row) for row in raw_rows if is_opening_set_row(row)]
    rows = [row for row in opening_rows if row.get("set_id")]
    rows_by_id = {row["set_id"]: row for row in rows}
    for raw_row in raw_rows:
        if not is_subset_row(raw_row):
            continue
        parent_id = parent_opening_set_id(raw_row)
        if not parent_id or parent_id not in rows_by_id:
            continue
        _merge_subset_into_parent(rows_by_id[parent_id], _base_validation_row(raw_row))
    for row in rows:
        if row.get("top_chase_value") is None and row["_top_hit_prices"]:
            row["top_chase_value"] = max(row["_top_hit_prices"])
        if row.get("top_10_card_value") is None and row["_top_hit_prices"]:
            row["top_10_card_value"] = round(sum(sorted(row["_top_hit_prices"], reverse=True)[:10]), 2)
        if row.get("avg_hit_value") is None and row["_top_hit_prices"]:
            row["avg_hit_value"] = round(mean(row["_top_hit_prices"]), 2)
        row.pop("_top_hit_prices", None)
        row.pop("_summary", None)

    for value_key, rank_key in (
        ("desirability_score", "desirability_rank"),
        ("card_appeal_score", "card_appeal_rank"),
        ("rip_core_score_without_desirability", "rip_core_rank_without_desirability"),
        ("final_rip_score_with_desirability", "final_rip_rank_with_desirability"),
        ("set_value", "set_value_rank"),
        ("pack_cost", "pack_cost_rank"),
        ("expected_value", "expected_value_rank"),
        ("p95_value", "p95_rank"),
        ("top_chase_value", "top_chase_value_rank"),
        ("top_10_card_value", "top_10_card_value_rank"),
        ("avg_hit_value", "avg_hit_value_rank"),
        ("median_hit_value", "median_hit_value_rank"),
    ):
        _rank_values(rows, value_key, rank_key)
    return rows


def _weighted_alignment(row: Mapping[str, Any], rank_key: str, total_ranked_sets: int) -> Tuple[Optional[float], Dict[str, float]]:
    scores: Dict[str, float] = {}
    weighted = 0.0
    total_weight = 0.0
    source_rank = row.get(rank_key)
    for target, weight in ALIGNMENT_WEIGHTS.items():
        score = alignment_score(source_rank, row.get(f"{target}_rank" if target != "p95_value" else "p95_rank"), total_ranked_sets)
        if score is None:
            continue
        scores[f"{target}_alignment"] = score
        weighted += score * weight
        total_weight += weight
    if total_weight <= 0:
        return None, scores
    return round(weighted / total_weight, 2), scores


def _signal_name(key: Optional[str]) -> Optional[str]:
    if not key:
        return None
    return key.replace("_alignment", "").replace("_", " ").title()


def finalize_validation_row(row: Dict[str, Any], *, total_ranked_sets: int) -> Dict[str, Any]:
    final_score = to_optional_float(row.get("final_rip_score_with_desirability"))
    core_score = to_optional_float(row.get("rip_core_score_without_desirability"))
    score_delta = round(final_score - core_score, 2) if final_score is not None and core_score is not None else None
    final_rank = to_optional_int(row.get("final_rip_rank_with_desirability"))
    core_rank = to_optional_int(row.get("rip_core_rank_without_desirability"))
    rank_delta = core_rank - final_rank if final_rank is not None and core_rank is not None else None
    band = impact_band(score_delta, rank_delta)

    alignment, alignment_scores = _weighted_alignment(row, "desirability_rank", total_ranked_sets)
    sorted_alignments = sorted(alignment_scores.items(), key=lambda item: item[1])
    alignment_band_value = alignment_band(alignment)

    card_alignment, card_alignment_scores = _weighted_alignment(row, "card_appeal_rank", total_ranked_sets)
    card_band = alignment_band(card_alignment)
    card_available = row.get("card_appeal_score") is not None

    clean_row = {key: value for key, value in row.items() if not str(key).startswith("_")}
    payload = {
        **clean_row,
        "formula_version": FORMULA_VERSION,
        "total_ranked_sets": total_ranked_sets,
        "set_value_sample_size": row.get("_set_value_sample_size"),
        "pack_cost_sample_size": row.get("_pack_cost_sample_size"),
        "expected_value_sample_size": row.get("_expected_value_sample_size"),
        "p95_sample_size": row.get("_p95_sample_size"),
        "desirability_score_delta": score_delta,
        "desirability_rank_delta": rank_delta,
        "desirability_impact_band": band,
        "desirability_impact_summary": desirability_impact_summary(band),
        "desirability_alignment_score": alignment,
        "desirability_alignment_band": alignment_band_value,
        "desirability_alignment_details": alignment_scores,
        "strongest_supporting_signal": _signal_name(sorted_alignments[-1][0]) if sorted_alignments else None,
        "biggest_conflicting_signal": _signal_name(sorted_alignments[0][0]) if sorted_alignments else None,
        "desirability_alignment_summary": desirability_alignment_summary(alignment_band_value),
        "card_appeal_alignment_score": card_alignment,
        "card_appeal_alignment_band": card_band,
        "card_appeal_alignment_details": card_alignment_scores,
        "card_appeal_vs_top_chase_rank_gap": abs(row["card_appeal_rank"] - row["top_chase_value_rank"]) if row.get("card_appeal_rank") and row.get("top_chase_value_rank") else None,
        "card_appeal_vs_top_10_value_rank_gap": abs(row["card_appeal_rank"] - row["top_10_card_value_rank"]) if row.get("card_appeal_rank") and row.get("top_10_card_value_rank") else None,
        "card_appeal_vs_avg_hit_value_rank_gap": abs(row["card_appeal_rank"] - row["avg_hit_value_rank"]) if row.get("card_appeal_rank") and row.get("avg_hit_value_rank") else None,
        "card_appeal_summary": card_appeal_summary(card_band, card_available),
        "missing_data_flags": sorted(
            key
            for key in ("desirability_score", "set_value", "pack_cost", "expected_value", "top_chase_value", "top_10_card_value", "avg_hit_value", "card_appeal_score")
            if row.get(key) is None
        ),
    }
    return payload


def build_desirability_validation_payload(
    *,
    set_id: str,
    set_payload: Optional[Mapping[str, Any]] = None,
    target_rows: Iterable[Mapping[str, Any]] = (),
    cards_payload: Optional[Mapping[str, Any]] = None,
) -> Dict[str, Any]:
    rows = build_validation_rows(target_rows)
    payload_row: Dict[str, Any] = {}
    if isinstance(set_payload, Mapping):
        payload_row = _base_validation_row({"id": set_id, **set_payload})
        card_score = _extract_card_appeal_from_cards(cards_payload)
        if payload_row.get("card_appeal_score") is None and card_score is not None:
            payload_row["card_appeal_score"] = card_score
        if payload_row.get("set_id"):
            existing_index = next((index for index, row in enumerate(rows) if row.get("set_id") == payload_row.get("set_id")), None)
            if existing_index is None:
                rows.append(payload_row)
            else:
                rows[existing_index] = {**rows[existing_index], **{key: value for key, value in payload_row.items() if value is not None}}
            rows = build_validation_rows(rows)

    sample_sizes = {
        "_set_value_sample_size": sum(1 for row in rows if row.get("desirability_score") is not None and row.get("set_value") is not None),
        "_pack_cost_sample_size": sum(1 for row in rows if row.get("desirability_score") is not None and row.get("pack_cost") is not None),
        "_expected_value_sample_size": sum(1 for row in rows if row.get("desirability_score") is not None and row.get("expected_value") is not None),
        "_p95_sample_size": sum(1 for row in rows if row.get("desirability_score") is not None and row.get("p95_value") is not None),
    }
    for row in rows:
        row.update(sample_sizes)
    total_ranked_sets = max(len(rows), 1)
    selected = next((row for row in rows if row.get("set_id") == str(set_id)), None)
    if selected is None:
        selected = _base_validation_row({"id": set_id, **(set_payload or {})})
        selected.update(sample_sizes)
    return finalize_validation_row(selected, total_ranked_sets=total_ranked_sets)
