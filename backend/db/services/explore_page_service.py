"""Service for aggregating Explore page simulation data."""

from __future__ import annotations

import difflib
import logging
import math
import time
from typing import Any, Dict, List, Optional

from backend.db.clients.supabase_client import public_read_client
from backend.interpretation.rips import build_rip_interpretation

logger = logging.getLogger(__name__)

DEFAULT_DISTRIBUTION_BINS_LIMIT = 50
MAX_DISTRIBUTION_BINS_LIMIT = 200
DEFAULT_TOP_HITS_LIMIT = 10
MAX_TOP_HITS_LIMIT = 50
DEFAULT_HISTORY_TREND_LIMIT = 180
MAX_HISTORY_TREND_LIMIT = 180
MIN_LIMIT = 1

_BIGGEST_UPSIDE_P95_CAP = 5.0
_BIGGEST_UPSIDE_P99_CAP = 10.0
_BIGGEST_UPSIDE_P95_WEIGHT = 0.70
_BIGGEST_UPSIDE_P99_WEIGHT = 0.30

_RIP_SUMMARY_META_KEYS = frozenset(
    {
        "set_id",
        "calculation_run_id",
        "run_at",
        "created_at",
        "updated_at",
    }
)

_RIP_SUMMARY_REQUIRED_FIELDS = (
    "pack_score",
    "relative_pack_score",
    "pack_rank",
    "pack_tier",
    "profit_score",
    "safety_score",
    "stability_score",
    "profit_rank",
    "profit_tier",
    "safety_rank",
    "safety_tier",
    "stability_rank",
    "stability_tier",
    "relative_profit_score",
    "relative_safety_score",
    "relative_stability_score",
    "pack_cost",
    "mean_value",
    "median_value",
    "roi_percent",
    "prob_profit",
    "p95_value_to_cost_ratio",
    "p99_value_to_cost_ratio",
    "mean_value_to_cost_ratio",
    "median_value_to_cost_ratio",
    "expected_loss_when_losing_fraction",
    "median_loss_when_losing_fraction",
    "p05_shortfall_to_cost",
    "expected_loss_when_losing",
    "median_loss_when_losing",
    "expected_loss_per_pack",
    "tail_value_p05",
    "coefficient_of_variation",
    "hhi_ev_concentration",
    "effective_chase_count",
    "top1_ev_share",
    "top3_ev_share",
    "top5_ev_share",
)

_RIP_SUMMARY_SUPPLEMENT_FIELDS = (
    "pack_tier",
    "profit_rank",
    "profit_tier",
    "safety_rank",
    "safety_tier",
    "stability_rank",
    "stability_tier",
    "relative_profit_score",
    "relative_safety_score",
    "relative_stability_score",
    "desirability_score",
    "relative_desirability_score",
    "desirability_rank",
    "desirability_tier",
    "desirability_scoring_version",
    "desirability_source_summary_id",
    "desirability_source_table",
    "desirability_source_metric",
    "desirability_is_fallback",
    "desirability_fallback_reason",
    "median_value_to_cost_ratio",
    "median_loss_when_losing_fraction",
    "experience_score",
    "chase_potential_score",
    "experience_tier",
    "chase_potential_tier",
    "mean_value_to_cost_rank",
    "mean_value_to_cost_tier",
    "p95_value_to_cost_rank",
    "p95_value_to_cost_tier",
    "derived_metric_version",
)

_OPTIONAL_HIT_SET_VALUE_SUMMARY_FIELDS = (
    "simulated_set_value",
    "simulated_set_value_card_count",
    "average_hit_value",
    "hit_ev_per_pack",
    "hit_pull_rate",
    "hit_cards_pulled",
)

_DESIRABILITY_DRIVER_CARD_CANDIDATE_LIMIT = 25
_DESIRABILITY_DRIVER_DISPLAY_LIMIT = 3
_DESIRABILITY_DRIVER_POKEMON_LIMIT = 5
_DESIRABILITY_PREMIUM_RARITY_MIN_PRIORITY = 70


def _to_optional_str(value: Any) -> Optional[str]:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


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


class ExplorePageError(Exception):
    """Structured error for Explore page service."""

    def __init__(self, status_code: int, message: str, code: str):
        self.status_code = status_code
        self.message = message
        self.code = code
        super().__init__(message)


def _first_row(result) -> Optional[Dict[str, Any]]:
    """Extract first row from Supabase query result."""
    if result and result.data and len(result.data) > 0:
        return result.data[0]
    return None


def _sanitize_limit(value: Any, *, default: int, max_value: int) -> int:
    """Convert untrusted limit input into a safe bounded integer."""
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


def _to_optional_int(value: Any) -> Optional[int]:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _load_history_trend_rows(
    requested_target_type: str,
    requested_target_id: str,
    history_trend_limit: int,
) -> tuple[List[Dict[str, Any]], str]:
    """Load history trend rows while tolerating partial/legacy view schemas."""

    select_attempts = [
        (
            "snapshot_date,mean_value_to_cost_ratio,median_value_to_cost_ratio,"
            "simulated_mean_pack_value_vs_pack_cost,simulated_median_pack_value_vs_pack_cost,"
            "pack_cost,mean_value,median_value,run_created_at,calculation_run_id,p95_value_to_cost_ratio",
            "OK_CANONICAL",
        ),
        (
            "snapshot_date,mean_value_to_cost_ratio,median_value_to_cost_ratio,"
            "simulated_mean_pack_value_vs_pack_cost,simulated_median_pack_value_vs_pack_cost,"
            "pack_cost,mean_value,median_value,run_created_at,calculation_run_id",
            "OK_CANONICAL_NO_P95",
        ),
        (
            "snapshot_date,mean_value_to_cost_ratio,median_value_to_cost_ratio,"
            "simulated_mean_pack_value_vs_pack_cost,simulated_median_pack_value_vs_pack_cost,"
            "run_created_at,calculation_run_id",
            "OK_CANONICAL_CORE",
        ),
        (
            "snapshot_date,simulated_mean_pack_value_vs_pack_cost,"
            "simulated_median_pack_value_vs_pack_cost,run_created_at,calculation_run_id,"
            "p95_value_to_cost_ratio",
            "OK_LEGACY_P95",
        ),
        (
            "snapshot_date,simulated_mean_pack_value_vs_pack_cost,"
            "simulated_median_pack_value_vs_pack_cost,run_created_at,calculation_run_id",
            "OK_LEGACY",
        ),
    ]

    last_exception: Optional[Exception] = None

    for select_columns, source_key in select_attempts:
        try:
            history_result = (
                public_read_client.table("calculation_history_trend")
                .select(select_columns)
                .eq("target_type", requested_target_type)
                .eq("target_id", requested_target_id)
                .order("snapshot_date", desc=True)
                .limit(history_trend_limit)
                .execute()
            )
            history_rows = history_result.data if history_result and history_result.data else []
            history_rows.sort(
                key=lambda row: (str(row.get("snapshot_date") or ""), str(row.get("run_created_at") or ""))
            )
            return history_rows, source_key
        except Exception as exc:
            last_exception = exc
            logger.warning(
                "[explore-page] calculation_history_trend select fallback failed target_type=%s target_id=%s source=%s: %s",
                requested_target_type,
                requested_target_id,
                source_key,
                exc,
            )

    if last_exception:
        raise last_exception

    return [], "FAILED"


def _load_set_maps() -> tuple[Dict[str, Any], Dict[str, str]]:
    from backend.constants.tcg.pokemon.megaEvolutionEra.setMap import (
        SET_ALIAS_MAP as mega_alias_map,
        SET_CONFIG_MAP as mega_config_map,
    )
    from backend.constants.tcg.pokemon.scarletAndVioletEra.setMap import (
        SET_ALIAS_MAP as sv_alias_map,
        SET_CONFIG_MAP as sv_config_map,
    )

    config_map = {
        **sv_config_map,
        **mega_config_map,
    }
    alias_map = {
        **sv_alias_map,
        **mega_alias_map,
    }
    return config_map, alias_map


def _build_constants_config_map() -> Dict[str, Any]:
    config_map, _ = _load_set_maps()
    return config_map


def _build_constants_alias_map() -> Dict[str, str]:
    # Mega Evolution aliases intentionally override on collision.
    _, alias_map = _load_set_maps()
    return alias_map


def _normalize_key(value: Any) -> str:
    return str(value or "").strip().lower()


def _normalize_rarity(value: Any) -> str:
    return (
        str(value or "")
        .strip()
        .lower()
        .replace("_", " ")
        .replace("-", " ")
    )


def _is_base_population_rarity(rarity: str) -> bool:
    return rarity in {"common", "uncommon", "rare"}


def _is_special_pack_rarity(rarity: str) -> bool:
    return rarity in {"god pack", "demi god pack"}


def _to_positive_probability(value: Any) -> Optional[float]:
    parsed = _to_optional_float(value)
    if parsed is None or parsed <= 0:
        return None
    return parsed


def _to_positive_denominator(value: Any) -> Optional[int]:
    parsed = _to_optional_float(value)
    if parsed is None or parsed <= 0:
        return None
    return int(round(parsed))


def _resolve_set_config(target_set_identifier: str) -> tuple[Optional[Any], Optional[str]]:
    config_map = _build_constants_config_map()
    alias_map = _build_constants_alias_map()

    raw = str(target_set_identifier or "").strip()
    key = raw.lower()
    if not key:
        return None, None

    canonical_key_by_lower = {str(k).lower(): str(k) for k in config_map.keys()}

    if key in alias_map:
        canonical_key = alias_map[key]
        return config_map.get(canonical_key), canonical_key

    if key in canonical_key_by_lower:
        canonical_key = canonical_key_by_lower[key]
        return config_map.get(canonical_key), canonical_key

    # Allow direct lookup by class-level SET_ID / SET_NAME values.
    for canonical_key, config_class in config_map.items():
        if _normalize_key(getattr(config_class, "SET_ID", "")) == key:
            return config_class, canonical_key
        if _normalize_key(getattr(config_class, "SET_NAME", "")) == key:
            return config_class, canonical_key

    # Last-pass fuzzy match across known aliases and canonical keys.
    possible_inputs = list(alias_map.keys()) + list(canonical_key_by_lower.keys())
    matches = difflib.get_close_matches(key, possible_inputs, n=1, cutoff=0.6)
    if matches:
        matched_key = matches[0]
        canonical_key = alias_map.get(matched_key) or canonical_key_by_lower.get(matched_key)
        if canonical_key and canonical_key in config_map:
            return config_map.get(canonical_key), canonical_key

    return None, None


def _fetch_set_metadata_for_target(requested_target_id: str) -> Optional[Dict[str, Any]]:
    target_id = str(requested_target_id or "").strip()
    if not target_id:
        return None

    # Reuse known-safe columns that are already queried elsewhere in service code.
    selected_columns = "id,name,canonical_key,pokemon_api_set_id"

    identity_filters: List[tuple[str, str]] = [
        ("id", target_id),
        ("canonical_key", target_id),
        ("pokemon_api_set_id", target_id),
    ]

    for field, value in identity_filters:
        try:
            set_result = (
                public_read_client.table("sets")
                .select(selected_columns)
                .eq(field, value)
                .limit(1)
                .execute()
            )
            set_row = _first_row(set_result)
            if set_row:
                return set_row
        except Exception:
            continue

    # Some datasets store a slug while others only expose canonical_key.
    # Attempt slug match but tolerate schemas where slug is unavailable.
    try:
        slug_result = (
            public_read_client.table("sets")
            .select(selected_columns + ",slug")
            .eq("slug", target_id)
            .limit(1)
            .execute()
        )
        slug_row = _first_row(slug_result)
        if slug_row:
            return slug_row
    except Exception:
        pass

    # Name fallback for slug-like target ids.
    candidate_name = target_id.replace("-", " ").replace("_", " ").strip()
    if candidate_name:
        try:
            name_result = (
                public_read_client.table("sets")
                .select(selected_columns)
                .eq("name", candidate_name)
                .limit(1)
                .execute()
            )
            name_row = _first_row(name_result)
            if name_row:
                return name_row
        except Exception:
            pass

    return None


def _resolve_set_config_for_explore_target(
    requested_target_id: str,
    summary: Dict[str, Any],
    warnings: List[str],
    sources: Dict[str, str],
) -> tuple[Optional[Any], Optional[str]]:
    candidates: List[str] = []

    def _add_candidate(raw: Any) -> None:
        candidate = str(raw or "").strip()
        if candidate and candidate not in candidates:
            candidates.append(candidate)

    _add_candidate(requested_target_id)
    _add_candidate(summary.get("set_id"))

    set_metadata: Optional[Dict[str, Any]] = None
    try:
        set_metadata = _fetch_set_metadata_for_target(requested_target_id)
        if set_metadata:
            sources["pull_rate_assumptions_set_metadata"] = "OK"
        else:
            sources["pull_rate_assumptions_set_metadata"] = "NO_ROW"
    except Exception as exc:
        logger.warning(
            "[explore-page] sets metadata lookup failed for pull-rate assumptions target_id=%s: %s",
            requested_target_id,
            exc,
        )
        sources["pull_rate_assumptions_set_metadata"] = "FAILED"

    if set_metadata:
        _add_candidate(set_metadata.get("id"))
        _add_candidate(set_metadata.get("canonical_key"))
        _add_candidate(set_metadata.get("pokemon_api_set_id"))
        _add_candidate(set_metadata.get("name"))

    for candidate in candidates:
        config_class, canonical_key = _resolve_set_config(candidate)
        if config_class is not None and canonical_key:
            sources["pull_rate_assumptions_config_resolution"] = f"OK:{canonical_key}"
            return config_class, canonical_key

    sources["pull_rate_assumptions_config_resolution"] = "FAILED"
    warnings.append("Pull-rate assumptions config resolution failed for this set target")
    return None, None


def _collect_generic_probability_inputs(config_class: Any) -> tuple[Dict[str, float], Dict[str, set[str]], int]:
    probabilities_by_rarity: Dict[str, float] = {}
    slot_labels_by_rarity: Dict[str, set[str]] = {}
    regular_reverse_slot_count = 0

    def _add_probability(rarity_name: Any, probability: Any, label: str) -> None:
        rarity_key = _normalize_rarity(rarity_name)
        if not rarity_key:
            return

        prob = _to_positive_probability(probability)
        if prob is None:
            return

        probabilities_by_rarity[rarity_key] = probabilities_by_rarity.get(rarity_key, 0.0) + prob
        slot_labels_by_rarity.setdefault(rarity_key, set()).add(label)

    reverse_slot_probabilities = getattr(config_class, "REVERSE_SLOT_PROBABILITIES", {}) or {}
    if isinstance(reverse_slot_probabilities, dict):
        for slot_payload in reverse_slot_probabilities.values():
            if not isinstance(slot_payload, dict):
                continue
            for rarity_name, probability in slot_payload.items():
                _add_probability(rarity_name, probability, "Reverse slot model")
                if _normalize_rarity(rarity_name) == "regular reverse":
                    regular_reverse_slot_count += 1

    rare_slot_probability = getattr(config_class, "RARE_SLOT_PROBABILITY", {}) or {}
    if isinstance(rare_slot_probability, dict):
        for rarity_name, probability in rare_slot_probability.items():
            _add_probability(rarity_name, probability, "Rare slot model")

    return probabilities_by_rarity, slot_labels_by_rarity, regular_reverse_slot_count


def _build_pull_rate_assumption_row(
    *,
    group: str,
    rarity: str,
    card_count: Optional[int],
    slot_count: Optional[int],
    expected_cards_per_pack: Optional[float],
    rarity_odds_denominator: Optional[float],
    specific_card_odds_denominator: Optional[float],
    probability_label: Optional[str],
    pack_model_label: Optional[str],
    slot_label: Optional[str],
    notes: Optional[str],
) -> Dict[str, Any]:
    return {
        "group": group,
        "rarity": rarity,
        "card_count": card_count,
        "slot_count": slot_count,
        "expected_cards_per_pack": expected_cards_per_pack,
        "rarity_odds_denominator": rarity_odds_denominator,
        "specific_card_odds_denominator": specific_card_odds_denominator,
        "probability_label": probability_label,
        "pack_model_label": pack_model_label,
        "slot_label": slot_label,
        "notes": notes,
    }


def _build_special_pack_rule_rows(
    *,
    config_class: Any,
    pull_rate_mapping: Dict[str, Any],
) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []

    def _append_special_row(config_attr_name: str, rarity_name: str) -> None:
        pack_config = getattr(config_class, config_attr_name, {}) or {}
        if not isinstance(pack_config, dict) or not pack_config.get("enabled"):
            return

        pull_rate = _to_positive_probability(pack_config.get("pull_rate"))
        rarity_odds_denominator = int(round(1 / pull_rate)) if pull_rate else None

        specific_card_odds_denominator = _to_positive_denominator(pull_rate_mapping.get(rarity_name))
        card_count = None
        if rarity_odds_denominator and specific_card_odds_denominator:
            card_count = int(round(specific_card_odds_denominator / rarity_odds_denominator))

        strategy = pack_config.get("strategy") if isinstance(pack_config.get("strategy"), dict) else {}
        strategy_type = str(strategy.get("type") or "").strip()
        notes = "Special pack model rule from set config."
        if strategy_type:
            notes = f"Special pack model rule from set config (strategy: {strategy_type})."

        rows.append(
            _build_pull_rate_assumption_row(
                group="special_pack_rules",
                rarity=rarity_name,
                card_count=card_count,
                slot_count=None,
                expected_cards_per_pack=None,
                rarity_odds_denominator=rarity_odds_denominator,
                specific_card_odds_denominator=specific_card_odds_denominator,
                probability_label=None,
                pack_model_label=(
                    f"1 in {rarity_odds_denominator:,} packs"
                    if rarity_odds_denominator
                    else None
                ),
                slot_label="Special pack model",
                notes=notes,
            )
        )

    _append_special_row("GOD_PACK_CONFIG", "god pack")
    _append_special_row("DEMI_GOD_PACK_CONFIG", "demi god pack")
    return rows


def _build_pull_rate_assumptions(
    *,
    config_class: Any,
    run_id: str,
    warnings: List[str],
    sources: Dict[str, str],
) -> Optional[Dict[str, Any]]:
    pull_rate_mapping = getattr(config_class, "PULL_RATE_MAPPING", {}) or {}
    if not isinstance(pull_rate_mapping, dict) or not pull_rate_mapping:
        sources["pull_rate_assumptions"] = "NO_PULL_RATE_MAPPING"
        return None

    normalized_mapping = {
        _normalize_rarity_label(key): value for key, value in pull_rate_mapping.items()
    }

    generic_probabilities, slot_labels_by_rarity, regular_reverse_slot_count = _collect_generic_probability_inputs(config_class)
    generic_denominators: Dict[str, int] = {}
    for rarity_key, probability in generic_probabilities.items():
        if probability <= 0:
            continue
        generic_denominators[rarity_key] = int(round(1 / probability))

    slot_defaults = getattr(config_class, "SLOTS_PER_RARITY", {}) or {}
    common_slot_count = int(slot_defaults.get("common", 4)) if _to_positive_denominator(slot_defaults.get("common", 4)) else 4
    uncommon_slot_count = int(slot_defaults.get("uncommon", 3)) if _to_positive_denominator(slot_defaults.get("uncommon", 3)) else 3
    reverse_slot_count_default = _to_positive_denominator(slot_defaults.get("reverse"))
    reverse_slot_count = reverse_slot_count_default or regular_reverse_slot_count or 2

    cards_rows: List[Dict[str, Any]] = []
    rarity_card_ids: Dict[str, set[str]] = {}
    try:
        cards_result = (
            public_read_client.table("simulation_input_cards_with_near_mint_price")
            .select("card_id,card_variant_id,card_name,rarity_bucket")
            .eq("calculation_run_id", run_id)
            .execute()
        )
        cards_rows = list(cards_result.data or [])

        for row in cards_rows:
            rarity_key = _normalize_rarity(row.get("rarity_bucket"))
            if not rarity_key:
                continue

            identifier = _normalize_key(row.get("card_variant_id"))
            if not identifier:
                identifier = _normalize_key(row.get("card_id"))
            if not identifier:
                identifier = _normalize_key(row.get("card_name"))
            if not identifier:
                continue

            rarity_card_ids.setdefault(rarity_key, set()).add(identifier)
        sources["pull_rate_assumptions_card_counts"] = "OK"
    except Exception as exc:
        logger.warning(
            "[explore-page] simulation_input_cards_with_near_mint_price pull-rate count query failed run_id=%s: %s",
            run_id,
            exc,
        )
        warnings.append("Failed to derive eligible card counts for pull-rate assumptions")
        sources["pull_rate_assumptions_card_counts"] = "FAILED"
        sources["pull_rate_assumptions_regular_reverse_count"] = "FAILED"

    def _derive_regular_reverse_card_count() -> Optional[int]:
        if not cards_rows:
            if sources.get("pull_rate_assumptions_regular_reverse_count") != "FAILED":
                sources["pull_rate_assumptions_regular_reverse_count"] = "UNAVAILABLE"
            return None

        rows_by_rarity: Dict[str, List[Dict[str, Any]]] = {}
        for row in cards_rows:
            rarity_key = _normalize_rarity(row.get("rarity_bucket"))
            if not rarity_key:
                continue
            rows_by_rarity.setdefault(rarity_key, []).append(row)

        candidate_rows = rows_by_rarity.get("regular reverse", [])
        if not candidate_rows:
            fallback_rarities = {"common", "uncommon", "rare"}
            candidate_rows = [
                row
                for rarity_key, rows in rows_by_rarity.items()
                if rarity_key in fallback_rarities
                for row in rows
            ]

        if not candidate_rows:
            sources["pull_rate_assumptions_regular_reverse_count"] = "UNAVAILABLE"
            return None

        # Regular reverse sampling in sim pools is variant-row based when variant ids are available.
        use_variant_ids = any(_normalize_key(row.get("card_variant_id")) for row in candidate_rows)
        identifier_field = "card_variant_id" if use_variant_ids else "card_id"
        identifiers = {
            _normalize_key(row.get(identifier_field))
            for row in candidate_rows
            if _normalize_key(row.get(identifier_field))
        }

        if not identifiers:
            sources["pull_rate_assumptions_regular_reverse_count"] = "UNAVAILABLE"
            return None

        sources["pull_rate_assumptions_regular_reverse_count"] = "OK"
        return len(identifiers)

    pack_structure_rows: List[Dict[str, Any]] = []

    common_pool_count = _to_positive_denominator(pull_rate_mapping.get("common"))
    common_specific = (
        (common_pool_count / common_slot_count)
        if common_pool_count and common_slot_count > 0
        else None
    )
    pack_structure_rows.append(
        _build_pull_rate_assumption_row(
            group="pack_structure",
            rarity="common",
            card_count=common_pool_count,
            slot_count=common_slot_count,
            expected_cards_per_pack=float(common_slot_count),
            rarity_odds_denominator=None,
            specific_card_odds_denominator=common_specific,
            probability_label=f"{common_slot_count} cards per pack",
            pack_model_label=f"{common_slot_count} cards per pack",
            slot_label="Base pack composition",
            notes="Base pack slot population; multiple cards appear per pack.",
        )
    )

    uncommon_pool_count = _to_positive_denominator(pull_rate_mapping.get("uncommon"))
    uncommon_specific = (
        (uncommon_pool_count / uncommon_slot_count)
        if uncommon_pool_count and uncommon_slot_count > 0
        else None
    )
    pack_structure_rows.append(
        _build_pull_rate_assumption_row(
            group="pack_structure",
            rarity="uncommon",
            card_count=uncommon_pool_count,
            slot_count=uncommon_slot_count,
            expected_cards_per_pack=float(uncommon_slot_count),
            rarity_odds_denominator=None,
            specific_card_odds_denominator=uncommon_specific,
            probability_label=f"{uncommon_slot_count} cards per pack",
            pack_model_label=f"{uncommon_slot_count} cards per pack",
            slot_label="Base pack composition",
            notes="Base pack slot population; multiple cards appear per pack.",
        )
    )

    rare_card_count = _to_positive_denominator(pull_rate_mapping.get("rare"))
    rare_probability = _to_positive_probability((getattr(config_class, "RARE_SLOT_PROBABILITY", {}) or {}).get("rare"))
    rare_rarity_odds = int(round(1 / rare_probability)) if rare_probability else None
    rare_specific = (
        (rare_card_count / rare_probability)
        if rare_card_count and rare_probability
        else None
    )
    pack_structure_rows.append(
        _build_pull_rate_assumption_row(
            group="pack_structure",
            rarity="rare",
            card_count=rare_card_count,
            slot_count=_to_positive_denominator(slot_defaults.get("rare", 1)) or 1,
            expected_cards_per_pack=rare_probability,
            rarity_odds_denominator=rare_rarity_odds,
            specific_card_odds_denominator=rare_specific,
            probability_label=None,
            pack_model_label=(
                f"{(rare_probability * 100):.1f}% rare-slot outcome"
                if rare_probability
                else None
            ),
            slot_label="Rare slot model",
            notes="Regular rare outcome in the rare slot.",
        )
    )

    regular_reverse_probability = generic_probabilities.get("regular reverse")
    regular_reverse_rarity_odds = (
        int(round(1 / regular_reverse_probability))
        if regular_reverse_probability and regular_reverse_probability > 0
        else None
    )
    regular_reverse_card_count = _derive_regular_reverse_card_count()
    regular_reverse_specific = (
        (regular_reverse_card_count / regular_reverse_probability)
        if regular_reverse_probability and regular_reverse_card_count
        else None
    )
    pack_structure_rows.append(
        _build_pull_rate_assumption_row(
            group="pack_structure",
            rarity="regular reverse",
            card_count=regular_reverse_card_count,
            slot_count=reverse_slot_count,
            expected_cards_per_pack=regular_reverse_probability,
            rarity_odds_denominator=regular_reverse_rarity_odds,
            specific_card_odds_denominator=regular_reverse_specific,
            probability_label=(
                f"Reverse slot outcome across {reverse_slot_count} slots"
                if reverse_slot_count
                else "Reverse slot outcome"
            ),
            pack_model_label=(
                f"{regular_reverse_probability:.2f} slots per pack"
                if regular_reverse_probability
                else None
            ),
            slot_label="Reverse slot model",
            notes="Reverse slot baseline outcome; specific-card odds require eligible reverse pool count.",
        )
    )

    special_pack_rows = _build_special_pack_rule_rows(
        config_class=config_class,
        pull_rate_mapping=pull_rate_mapping,
    )
    special_pack_rarities = {
        _normalize_rarity(row.get("rarity"))
        for row in special_pack_rows
        if row.get("rarity")
    }

    hit_rarity_rows: List[Dict[str, Any]] = []
    hit_rarity_keys = {
        _normalize_rarity(rarity_name)
        for rarity_name in pull_rate_mapping.keys()
        if _normalize_rarity(rarity_name)
    }
    hit_rarity_keys.update(generic_denominators.keys())
    hit_rarity_keys = {
        rarity_key
        for rarity_key in hit_rarity_keys
        if rarity_key
        and not _is_base_population_rarity(rarity_key)
        and rarity_key != "regular reverse"
        and rarity_key not in special_pack_rarities
        and not _is_special_pack_rarity(rarity_key)
    }

    for rarity_key in sorted(hit_rarity_keys):
        rarity_odds_denominator = generic_denominators.get(rarity_key)
        specific_card_odds_denominator = _to_positive_denominator(pull_rate_mapping.get(rarity_key))

        card_count: Optional[int] = None
        if rarity_odds_denominator and specific_card_odds_denominator:
            card_count = int(round(specific_card_odds_denominator / rarity_odds_denominator))
        elif rarity_odds_denominator and not specific_card_odds_denominator:
            derived_count = len(rarity_card_ids.get(rarity_key, set())) or None
            if derived_count:
                card_count = derived_count
                specific_card_odds_denominator = rarity_odds_denominator * card_count

        slot_labels = sorted(slot_labels_by_rarity.get(rarity_key, set()))
        notes = "Specific-card odds sourced from set config PULL_RATE_MAPPING."
        if specific_card_odds_denominator is None and rarity_odds_denominator is not None:
            notes = "Specific-card odds derived from rarity odds and eligible card count fallback."
        elif rarity_odds_denominator is None:
            notes = "Generic rarity odds are unavailable for this rarity in slot probability config."

        hit_rarity_rows.append(
            _build_pull_rate_assumption_row(
                group="hit_rarity_model",
                rarity=rarity_key,
                card_count=card_count,
                slot_count=None,
                expected_cards_per_pack=generic_probabilities.get(rarity_key),
                rarity_odds_denominator=rarity_odds_denominator,
                specific_card_odds_denominator=specific_card_odds_denominator,
                probability_label=None,
                pack_model_label=None,
                slot_label=" + ".join(slot_labels) if slot_labels else None,
                notes=notes,
            )
        )

    groups = [
        {
            "key": "pack_structure",
            "label": "Pack Structure",
            "rows": pack_structure_rows,
        },
        {
            "key": "hit_rarity_model",
            "label": "Hit Rarity Model",
            "rows": hit_rarity_rows,
        },
        {
            "key": "special_pack_rules",
            "label": "Special Pack Rules",
            "rows": special_pack_rows,
        },
    ]

    rows = [row for group in groups for row in group["rows"]]

    sources["pull_rate_assumptions"] = "OK" if rows else "NO_ROWS"
    return {
        "groups": groups,
        "rows": rows,
        "meta": {
            "is_modelled": True,
            "is_modeled": True,
            "source_label": "Config-based pack model + inDex-derived card counts",
        },
    }


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
    """Blend Big Hit Upside (P95) and God Pull Upside (P99) into a 0-100 score."""

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


def _rank_tier_from_percentile(rank: int, total: int) -> str:
    if rank <= max(1, math.ceil(total * 0.05)):
        return "S"
    if rank <= max(1, math.ceil(total * 0.15)):
        return "A"
    if rank <= max(1, math.ceil(total * 0.30)):
        return "B"
    if rank <= max(1, math.ceil(total * 0.50)):
        return "C"
    if rank <= max(1, math.ceil(total * 0.75)):
        return "D"
    return "F"


def _populate_biggest_upside_metrics_for_set(
    summary: Dict[str, Any],
    requested_target_id: str,
    warnings: List[str],
    sources: Dict[str, str],
) -> None:
    """Attach blended Biggest Upside score + relative/rank/tier for set targets."""

    summary["biggest_upside_score"] = _blend_biggest_upside_score(
        summary.get("p95_value_to_cost_ratio"),
        summary.get("p99_value_to_cost_ratio"),
    )

    if summary.get("biggest_upside_score") is None:
        summary["relative_biggest_upside_score"] = None
        summary["biggest_upside_rank"] = None
        summary["biggest_upside_tier"] = None
        return

    try:
        peers_result = (
            public_read_client.table("explore_rip_statistics_latest")
            .select("set_id,p95_value_to_cost_ratio,p99_value_to_cost_ratio")
            .execute()
        )
        peer_rows = peers_result.data if peers_result and peers_result.data else []
    except Exception as exc:
        logger.warning(
            "[explore-page] biggest_upside peer query failed target_id=%s: %s",
            requested_target_id,
            exc,
        )
        warnings.append("Failed to compute blended Biggest Upside rank context")
        sources["biggest_upside_blend"] = "FAILED"
        summary["relative_biggest_upside_score"] = None
        summary["biggest_upside_rank"] = None
        summary["biggest_upside_tier"] = None
        return

    scored_peers: List[tuple[str, float]] = []
    for row in peer_rows:
        if not isinstance(row, dict):
            continue
        set_id = str(row.get("set_id") or "").strip()
        if not set_id:
            continue
        blended = _blend_biggest_upside_score(
            row.get("p95_value_to_cost_ratio"),
            row.get("p99_value_to_cost_ratio"),
        )
        if blended is None:
            continue
        scored_peers.append((set_id, blended))

    if not scored_peers:
        sources["biggest_upside_blend"] = "NO_PEERS"
        summary["relative_biggest_upside_score"] = None
        summary["biggest_upside_rank"] = None
        summary["biggest_upside_tier"] = None
        return

    scores_only = [score for _, score in scored_peers]
    score_min = min(scores_only)
    score_max = max(scores_only)
    target_score = _to_optional_float(summary.get("biggest_upside_score"))
    if target_score is None:
        summary["relative_biggest_upside_score"] = None
    elif score_max <= score_min:
        summary["relative_biggest_upside_score"] = 50.0
    else:
        summary["relative_biggest_upside_score"] = 100.0 * ((target_score - score_min) / (score_max - score_min))

    ranked = sorted(scored_peers, key=lambda item: item[1], reverse=True)
    rank_lookup = {set_id: index for index, (set_id, _) in enumerate(ranked, start=1)}
    target_rank = rank_lookup.get(requested_target_id)
    summary["biggest_upside_rank"] = target_rank
    summary["biggest_upside_tier"] = (
        _rank_tier_from_percentile(target_rank, len(ranked)) if target_rank is not None else None
    )
    sources["biggest_upside_blend"] = "SERVICE_COMPUTED"


def _populate_relative_average_return_score_for_set(
    summary: Dict[str, Any],
    requested_target_id: str,
    warnings: List[str],
    sources: Dict[str, str],
) -> None:
    mean_ratio = _resolve_mean_value_to_cost_ratio(summary)
    if mean_ratio is None:
        summary["relative_average_return_score"] = None
        return

    try:
        peers_result = (
            public_read_client.table("explore_rip_statistics_latest")
            .select("set_id,mean_value_to_cost_ratio")
            .execute()
        )
        peer_rows = peers_result.data if peers_result and peers_result.data else []
    except Exception as exc:
        logger.warning(
            "[explore-page] average_return peer query failed target_id=%s: %s",
            requested_target_id,
            exc,
        )
        warnings.append("Failed to compute relative Expected Value context")
        sources["average_return_relative"] = "FAILED"
        summary["relative_average_return_score"] = None
        return

    peer_ratios: List[float] = []
    for row in peer_rows:
        if not isinstance(row, dict):
            continue
        if not str(row.get("set_id") or "").strip():
            continue
        ratio = _to_optional_float(row.get("mean_value_to_cost_ratio"))
        if ratio is None:
            ratio = _resolve_mean_value_to_cost_ratio(row)
        if ratio is not None:
            peer_ratios.append(ratio)

    if not peer_ratios:
        sources["average_return_relative"] = "NO_PEERS"
        summary["relative_average_return_score"] = None
        return

    score_min = min(peer_ratios)
    score_max = max(peer_ratios)
    if score_max <= score_min:
        summary["relative_average_return_score"] = 50.0
    else:
        summary["relative_average_return_score"] = 100.0 * ((mean_ratio - score_min) / (score_max - score_min))
    sources["average_return_relative"] = "SERVICE_COMPUTED"


def _populate_p99_ratio_from_percentiles(summary: Dict[str, Any], percentiles: List[Dict[str, Any]]) -> None:
    if summary.get("p99_value_to_cost_ratio") is not None:
        return

    pack_cost = _to_optional_float(summary.get("pack_cost"))
    if pack_cost is None or pack_cost <= 0:
        return

    p99_value: Optional[float] = None
    for row in percentiles:
        if not isinstance(row, dict):
            continue
        percentile = _to_optional_float(row.get("percentile"))
        if percentile is None or abs(percentile - 99.0) >= 0.001:
            continue
        p99_value = _to_optional_float(row.get("value"))
        if p99_value is not None:
            break

    if p99_value is None:
        return

    summary["p99_value"] = p99_value
    summary["p99_value_to_cost_ratio"] = p99_value / pack_cost


def _safe_tooltip_copy(value: Any) -> Dict[str, Any]:
    if isinstance(value, dict):
        return dict(value)
    return {}


def _strip_public_weight_metadata(value: Any) -> Any:
    """Remove internal weighting artifacts from the public Explore payload."""
    blocked_keys = {
        "formula",
        "interpretation_weights",
        "weight",
        "weighted_drag",
        "weighted_driver",
        "weighted_impact",
        "weights",
        "weights_normalized",
        "weights_pct",
    }
    if isinstance(value, dict):
        return {
            key: _strip_public_weight_metadata(child)
            for key, child in value.items()
            if str(key).lower() not in blocked_keys
        }
    if isinstance(value, list):
        return [_strip_public_weight_metadata(item) for item in value]
    return value


def _opening_desirability_source(opening_payload: Optional[Dict[str, Any]]) -> str:
    if not opening_payload:
        return "missing"
    if _to_optional_float(opening_payload.get("openingDesirabilityScore")) is not None:
        return "opening_desirability"
    if _to_optional_float(opening_payload.get("collectorAppealScore")) is not None:
        return "collector_appeal_fallback"
    return "missing"


def _public_opening_desirability_payload(row: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "openingDesirabilityScore": _to_optional_float(row.get("opening_desirability_score")),
        "openingDesirabilityRank": _to_optional_int(row.get("opening_desirability_rank")),
        "collectorAppealScore": _to_optional_float(row.get("collector_appeal_score")),
        "collectorAppealRank": _to_optional_int(row.get("collector_appeal_rank")),
        "chaseAppealScore": _to_optional_float(row.get("chase_appeal_score")),
        "chaseAppealRank": _to_optional_int(row.get("chase_appeal_rank")),
        "chaseAppealDataQuality": _to_optional_str(row.get("chase_appeal_data_quality")) or "missing",
        "displayStatus": _to_optional_str(row.get("opening_desirability_display_status"))
        or "insufficient_chase_data",
        "summary": _to_optional_str(row.get("opening_desirability_summary")) or "",
        "tooltipCopy": _safe_tooltip_copy(row.get("public_tooltip_copy_json")),
        "builtAt": _to_optional_str(row.get("built_at")),
    }


def _populate_opening_desirability_for_set(
    *,
    summary: Dict[str, Any],
    requested_target_id: str,
    resolved_set_id: Optional[str],
    resolved_set_canonical_key: Optional[str],
    warnings: List[str],
    sources: Dict[str, str],
) -> Optional[Dict[str, Any]]:
    target_id = str(requested_target_id or "").strip()
    resolved_id = str(resolved_set_id or "").strip()
    resolved_canonical_key = str(resolved_set_canonical_key or "").strip()

    if not target_id and not resolved_id and not resolved_canonical_key:
        sources["pokemon_set_opening_desirability_latest"] = "SKIPPED_MISSING_SET_ID"
        summary["rip_desirability_source"] = "missing"
        return None

    selected_columns = (
        "set_id,set_name,set_canonical_key,opening_desirability_score,"
        "opening_desirability_rank,collector_appeal_score,collector_appeal_rank,"
        "chase_appeal_score,chase_appeal_rank,chase_appeal_data_quality,"
        "opening_desirability_display_status,opening_desirability_summary,"
        "public_tooltip_copy_json,scoring_version,built_at"
    )

    try:
        row = None
        lookup_attempts: List[tuple[str, str]] = [
            ("set_id", resolved_id),
            ("set_id", target_id),
            ("set_canonical_key", resolved_canonical_key),
            ("set_canonical_key", target_id),
        ]
        attempted_filters: List[tuple[str, str]] = []
        for field, value in lookup_attempts:
            lookup_value = str(value or "").strip()
            if not lookup_value or (field, lookup_value) in attempted_filters:
                continue
            attempted_filters.append((field, lookup_value))
            try:
                result = (
                    public_read_client.table("pokemon_set_opening_desirability_latest")
                    .select(selected_columns)
                    .eq(field, lookup_value)
                    .order("built_at", desc=True)
                    .limit(1)
                    .execute()
                )
            except Exception:
                continue
            row = _first_row(result)
            if row:
                break

        if not row:
            sources["pokemon_set_opening_desirability_latest"] = "NO_ROW"
            summary["rip_desirability_source"] = "missing"
            return None

        payload = _public_opening_desirability_payload(row)
        summary["rip_desirability_source"] = _opening_desirability_source(payload)
        sources["pokemon_set_opening_desirability_latest"] = "OK"
        return payload
    except Exception as exc:
        logger.warning(
            "[explore-page] Opening Desirability query failed target_id=%s resolved_set_id=%s resolved_set_canonical_key=%s: %s",
            target_id,
            resolved_id,
            resolved_canonical_key,
            exc,
        )
        warnings.append("Failed to load Opening Desirability")
        sources["pokemon_set_opening_desirability_latest"] = "FAILED"
        summary["rip_desirability_source"] = "missing"
        return None


def _missing_required_fields(row: Dict[str, Any], required_fields: tuple[str, ...]) -> List[str]:
    """Return required field names that are absent from a row."""
    return [field for field in required_fields if field not in row]


def _ensure_optional_summary_fields(summary: Dict[str, Any]) -> None:
    for field in _OPTIONAL_HIT_SET_VALUE_SUMMARY_FIELDS:
        summary.setdefault(field, None)


def _public_score(value: Any) -> Optional[float]:
    parsed = _to_optional_float(value)
    if parsed is None or not math.isfinite(parsed):
        return None
    return round(parsed, 4)


def _first_non_empty_text(*values: Any) -> Optional[str]:
    for value in values:
        text = str(value or "").strip()
        if text:
            return text
    return None


def _normalize_desirability_subject_key(value: Any) -> Optional[str]:
    text = str(value or "").strip().lower()
    if not text:
        return None
    return " ".join(text.replace(",", " ").split())


def _desirability_rarity_priority(value: Any) -> int:
    rarity = str(value or "").strip().lower()
    if not rarity:
        return 0

    if "special illustration rare" in rarity or rarity == "sir":
        return 100
    if "alternate art" in rarity or "alt art" in rarity:
        return 95
    if "secret rare" in rarity or "hyper rare" in rarity or "gold" in rarity:
        return 90
    if "ultra rare" in rarity:
        return 80
    if "illustration rare" in rarity:
        return 70
    if "double rare" in rarity:
        return 20
    if any(token in rarity for token in (" ex", "-ex", " v", "-v", "vmax", "vstar", "gx")):
        return 10
    return 0


def _desirability_driver_sort_key(driver: Dict[str, Any]) -> tuple[int, float, float, float, int, str]:
    return (
        int(driver.get("_rarity_priority") or 0),
        _to_optional_float(driver.get("desirability_score")) or 0.0,
        _to_optional_float(driver.get("favorite_score")) or 0.0,
        _to_optional_float(driver.get("trend_score")) or 0.0,
        int(driver.get("notable_hit_count") or 0),
        str(driver.get("card_name") or ""),
    )


def _latest_composite_scores_by_reference(reference_ids: List[int]) -> Dict[int, Dict[str, Any]]:
    if not reference_ids:
        return {}

    response = (
        public_read_client.table("pokemon_desirability_composite_scores")
        .select(
            "pokemon_reference_id,fan_popularity_score,current_trend_score,"
            "desirability_score,created_at"
        )
        .in_("pokemon_reference_id", reference_ids[:50])
        .order("created_at", desc=True)
        .execute()
    )

    scores_by_reference: Dict[int, Dict[str, Any]] = {}
    for row in response.data or []:
        try:
            reference_id = int(row.get("pokemon_reference_id"))
        except (TypeError, ValueError):
            continue
        scores_by_reference.setdefault(reference_id, row)
    return scores_by_reference


def _collect_desirability_reference_ids(summary_row: Dict[str, Any]) -> List[int]:
    reference_ids: List[int] = []

    for card in (summary_row.get("top_desirable_cards_json") or [])[:_DESIRABILITY_DRIVER_CARD_CANDIDATE_LIMIT]:
        for link in card.get("linked_pokemon") or []:
            try:
                reference_id = int(link.get("pokemon_reference_id"))
            except (TypeError, ValueError):
                continue
            if reference_id not in reference_ids:
                reference_ids.append(reference_id)

    for pokemon in (summary_row.get("top_desirable_pokemon_json") or [])[:_DESIRABILITY_DRIVER_POKEMON_LIMIT]:
        try:
            reference_id = int(pokemon.get("pokemon_reference_id"))
        except (TypeError, ValueError):
            continue
        if reference_id not in reference_ids:
            reference_ids.append(reference_id)

    return reference_ids


def _public_desirability_driver_cards(
    summary_row: Dict[str, Any],
    scores_by_reference: Dict[int, Dict[str, Any]],
) -> List[Dict[str, Any]]:
    candidates_by_subject: Dict[str, List[Dict[str, Any]]] = {}

    for card in (summary_row.get("top_desirable_cards_json") or [])[:_DESIRABILITY_DRIVER_CARD_CANDIDATE_LIMIT]:
        links = [link for link in (card.get("linked_pokemon") or []) if isinstance(link, dict)]
        primary_link = links[0] if links else {}
        reference_id: Optional[int] = None
        try:
            reference_id = int(primary_link.get("pokemon_reference_id"))
        except (TypeError, ValueError):
            reference_id = None

        composite_row = scores_by_reference.get(reference_id or -1) or {}
        matched_names = [
            str(link.get("pokemon_name")).strip()
            for link in links
            if str(link.get("pokemon_name") or "").strip()
        ]
        unique_matched_names = list(dict.fromkeys(matched_names))
        matched_pokemon = ", ".join(unique_matched_names) if unique_matched_names else None
        subject = matched_pokemon or _first_non_empty_text(card.get("name"))
        subject_key = _normalize_desirability_subject_key(subject)
        if not subject_key:
            continue

        rarity = _first_non_empty_text(card.get("rarity"))
        rarity_priority = _desirability_rarity_priority(rarity)

        candidates_by_subject.setdefault(subject_key, []).append(
            {
                "card_name": _first_non_empty_text(card.get("name")),
                "matched_pokemon": matched_pokemon,
                "matched_subject": subject,
                "desirability_score": _public_score(card.get("card_desirability_score")),
                "favorite_score": _public_score(composite_row.get("fan_popularity_score")),
                "fan_score": _public_score(composite_row.get("fan_popularity_score")),
                "trend_score": _public_score(composite_row.get("current_trend_score")),
                "rarity": rarity,
                "card_number": _first_non_empty_text(card.get("printed_number"), card.get("number")),
                "printed_number": _first_non_empty_text(card.get("printed_number")),
                "_rarity_priority": rarity_priority,
            }
        )

    representatives: List[Dict[str, Any]] = []
    for subject_candidates in candidates_by_subject.values():
        ranked_candidates = sorted(
            subject_candidates,
            key=lambda item: (
                int(item.get("_rarity_priority") or 0),
                _to_optional_float(item.get("desirability_score")) or 0.0,
                _to_optional_float(item.get("favorite_score")) or 0.0,
                _to_optional_float(item.get("trend_score")) or 0.0,
                str(item.get("card_name") or ""),
            ),
            reverse=True,
        )
        representative = dict(ranked_candidates[0])
        representative["notable_hit_count"] = len(subject_candidates)
        representatives.append(representative)

    premium_representatives = [
        item
        for item in representatives
        if int(item.get("_rarity_priority") or 0) >= _DESIRABILITY_PREMIUM_RARITY_MIN_PRIORITY
    ]
    fallback_representatives = [
        item
        for item in representatives
        if int(item.get("_rarity_priority") or 0) < _DESIRABILITY_PREMIUM_RARITY_MIN_PRIORITY
    ]
    selected = sorted(premium_representatives, key=_desirability_driver_sort_key, reverse=True)[
        :_DESIRABILITY_DRIVER_DISPLAY_LIMIT
    ]
    if len(selected) < _DESIRABILITY_DRIVER_DISPLAY_LIMIT:
        selected.extend(
            sorted(fallback_representatives, key=_desirability_driver_sort_key, reverse=True)[
                : _DESIRABILITY_DRIVER_DISPLAY_LIMIT - len(selected)
            ]
        )

    public_fields = {
        "card_name",
        "matched_pokemon",
        "matched_subject",
        "desirability_score",
        "favorite_score",
        "fan_score",
        "trend_score",
        "rarity",
        "card_number",
        "printed_number",
        "notable_hit_count",
    }
    return [
        {key: value for key, value in driver.items() if key in public_fields and value is not None}
        for driver in selected
    ]


def _normalize_public_collector_driver_card(card: Any) -> Optional[Dict[str, Any]]:
    if not isinstance(card, dict):
        return None

    linked_source = card.get("linked_pokemon")
    if linked_source is None:
        linked_source = card.get("linkedPokemon")

    linked_pokemon: List[Dict[str, Any]] = []
    if isinstance(linked_source, list):
        for entry in linked_source:
            if not isinstance(entry, dict):
                continue
            pokemon_name = _first_non_empty_text(
                entry.get("pokemon_name"),
                entry.get("pokemonName"),
                entry.get("name"),
            )
            pokemon_reference_id = _first_non_empty_text(
                entry.get("pokemon_reference_id"),
                entry.get("pokemonReferenceId"),
                entry.get("pokedex_number"),
            )
            if pokemon_name or pokemon_reference_id:
                linked_pokemon.append(
                    {
                        "pokemonName": pokemon_name,
                        "pokemonReferenceId": pokemon_reference_id,
                    }
                )

    if not linked_pokemon:
        matched_pokemon = _first_non_empty_text(card.get("matched_pokemon"), card.get("matchedPokemon"))
        if matched_pokemon:
            linked_pokemon = [{"pokemonName": matched_pokemon, "pokemonReferenceId": None}]

    normalized = {
        "name": _first_non_empty_text(card.get("name"), card.get("card_name"), card.get("cardName")),
        "printedNumber": _first_non_empty_text(
            card.get("printed_number"),
            card.get("printedNumber"),
            card.get("card_number"),
            card.get("cardNumber"),
            card.get("number"),
        ),
        "rarity": _first_non_empty_text(card.get("rarity")),
        "cardDesirabilityScore": _public_score(
            card.get("card_desirability_score")
            if card.get("card_desirability_score") is not None
            else card.get("cardDesirabilityScore")
            if card.get("cardDesirabilityScore") is not None
            else card.get("desirability_score")
            if card.get("desirability_score") is not None
            else card.get("desirabilityScore")
        ),
        "linkedPokemon": linked_pokemon,
        "imageUrl": _first_non_empty_text(
            card.get("image_url"),
            card.get("imageUrl"),
            card.get("image_small_url"),
            card.get("imageSmallUrl"),
            card.get("image_large_url"),
            card.get("imageLargeUrl"),
        ),
        "imageSmallUrl": _first_non_empty_text(card.get("image_small_url"), card.get("imageSmallUrl")),
        "imageLargeUrl": _first_non_empty_text(card.get("image_large_url"), card.get("imageLargeUrl")),
    }

    if not normalized["name"]:
        return None
    return normalized


def _build_public_top_collector_appeal_drivers(
    *,
    summary_cards: Optional[List[Dict[str, Any]]] = None,
    raw_cards: Optional[List[Dict[str, Any]]] = None,
) -> List[Dict[str, Any]]:
    preferred_source = summary_cards if isinstance(summary_cards, list) and summary_cards else raw_cards
    cards = preferred_source if isinstance(preferred_source, list) else []

    drivers: List[Dict[str, Any]] = []
    for card in cards:
        normalized = _normalize_public_collector_driver_card(card)
        if normalized:
            drivers.append(normalized)
        if len(drivers) >= 3:
            break
    return drivers


def _public_desirability_driver_pokemon(
    summary_row: Dict[str, Any],
    scores_by_reference: Dict[int, Dict[str, Any]],
) -> List[Dict[str, Any]]:
    drivers: List[Dict[str, Any]] = []

    for pokemon in (summary_row.get("top_desirable_pokemon_json") or [])[:_DESIRABILITY_DRIVER_POKEMON_LIMIT]:
        try:
            reference_id = int(pokemon.get("pokemon_reference_id"))
        except (TypeError, ValueError):
            reference_id = None
        composite_row = scores_by_reference.get(reference_id or -1) or {}
        drivers.append(
            {
                "pokemon_name": _first_non_empty_text(pokemon.get("pokemon_name")),
                "matched_subject": _first_non_empty_text(pokemon.get("pokemon_name")),
                "desirability_score": _public_score(pokemon.get("desirability_score")),
                "favorite_score": _public_score(composite_row.get("fan_popularity_score")),
                "fan_score": _public_score(composite_row.get("fan_popularity_score")),
                "trend_score": _public_score(composite_row.get("current_trend_score")),
                "hit_card_count": pokemon.get("hit_card_count"),
            }
        )

    return drivers


def _populate_desirability_drivers_for_set(
    summary: Dict[str, Any],
    requested_target_id: str,
    warnings: List[str],
    sources: Dict[str, str],
) -> None:
    summary["top_desirability_cards"] = []
    summary["top_desirability_pokemon"] = []
    summary["top_collector_appeal_drivers"] = []

    source_summary_id = str(summary.get("desirability_source_summary_id") or "").strip()
    target_id = str(requested_target_id or "").strip()
    if not source_summary_id and not target_id:
        sources["pokemon_set_hit_desirability_summaries"] = "SKIPPED_MISSING_SET_ID"
        return

    try:
        base_query = public_read_client.table("pokemon_set_hit_desirability_summaries").select(
            "id,set_id,top_desirable_cards_json,top_desirable_pokemon_json,built_at"
        )
        summary_row = None
        if source_summary_id:
            response = base_query.eq("id", source_summary_id).limit(1).execute()
            summary_row = _first_row(response)

        if not summary_row and target_id:
            fallback_response = (
                public_read_client.table("pokemon_set_hit_desirability_summaries")
                .select("id,set_id,top_desirable_cards_json,top_desirable_pokemon_json,built_at")
                .eq("set_id", target_id)
                .order("built_at", desc=True)
                .limit(1)
                .execute()
            )
            summary_row = _first_row(fallback_response)

        if not summary_row:
            sources["pokemon_set_hit_desirability_summaries"] = "NO_ROW"
            return

        reference_ids = _collect_desirability_reference_ids(summary_row)
        try:
            scores_by_reference = _latest_composite_scores_by_reference(reference_ids)
            sources["pokemon_desirability_composite_scores"] = "OK" if reference_ids else "SKIPPED_NO_REFERENCES"
        except Exception as composite_exc:
            logger.warning(
                "[explore-page] pokemon_desirability_composite_scores enrichment failed target_id=%s: %s",
                target_id,
                composite_exc,
            )
            warnings.append("Failed to load supplemental desirability driver score components")
            sources["pokemon_desirability_composite_scores"] = "FAILED"
            scores_by_reference = {}

        summary["top_desirability_cards"] = _public_desirability_driver_cards(
            summary_row,
            scores_by_reference,
        )
        summary["top_collector_appeal_drivers"] = _build_public_top_collector_appeal_drivers(
            summary_cards=summary.get("top_desirability_cards"),
            raw_cards=summary_row.get("top_desirable_cards_json"),
        )
        summary["top_desirability_pokemon"] = _public_desirability_driver_pokemon(
            summary_row,
            scores_by_reference,
        )
        sources["pokemon_set_hit_desirability_summaries"] = "OK"
    except Exception as exc:
        logger.warning(
            "[explore-page] pokemon_set_hit_desirability_summaries enrichment failed target_id=%s: %s",
            target_id,
            exc,
        )
        warnings.append("Failed to load top desirability drivers")
        sources["pokemon_set_hit_desirability_summaries"] = "FAILED"


def _lookup_latest_run_from_calculation_runs(target_type: str, target_id: str) -> str:
    """Fallback latest run lookup when canonical latest view is unavailable."""
    run_result = (
        public_read_client.table("calculation_runs")
        .select("id,created_at,target_type,target_id")
        .eq("target_type", target_type)
        .eq("target_id", target_id)
        .order("created_at", desc=True)
        .limit(1)
        .execute()
    )
    run_row = _first_row(run_result)
    if not run_row or not run_row.get("id"):
        raise ExplorePageError(
            status_code=404,
            message="No simulation data found for this target",
            code="TARGET_NOT_FOUND",
        )
    return str(run_row.get("id"))


def get_explore_page_payload(
    target_type: str,
    target_id: str,
    limit_distribution_bins: Any = DEFAULT_DISTRIBUTION_BINS_LIMIT,
    limit_top_hits: Any = DEFAULT_TOP_HITS_LIMIT,
) -> Dict[str, Any]:
    """Aggregate simulation data for Explore page."""
    total_started = time.perf_counter()

    requested_target_type = (target_type or "").strip()
    requested_target_id = (target_id or "").strip()

    if not requested_target_type or not requested_target_id:
        raise ExplorePageError(
            status_code=400,
            message="target_type and target_id are required",
            code="INVALID_TARGET",
        )

    clamped_distribution_bins_limit = _sanitize_limit(
        limit_distribution_bins,
        default=DEFAULT_DISTRIBUTION_BINS_LIMIT,
        max_value=MAX_DISTRIBUTION_BINS_LIMIT,
    )
    clamped_top_hits_limit = _sanitize_limit(
        limit_top_hits,
        default=DEFAULT_TOP_HITS_LIMIT,
        max_value=MAX_TOP_HITS_LIMIT,
    )
    history_trend_limit = _sanitize_limit(
        DEFAULT_HISTORY_TREND_LIMIT,
        default=DEFAULT_HISTORY_TREND_LIMIT,
        max_value=MAX_HISTORY_TREND_LIMIT,
    )

    warnings: List[str] = []
    sources: Dict[str, str] = {}

    # Fields from simulation_latest_by_target that are lookup keys, not metrics.
    _CANONICAL_META_KEYS = frozenset({"target_type", "target_id", "calculation_run_id", "run_at"})

    # Prefer RIP-specific summary source for set targets first.
    summary: Dict[str, Any] = {}
    resolved_set_id: Optional[str] = None
    resolved_set_canonical_key: Optional[str] = None
    summary_from_canonical = False
    summary_from_rip_latest = False
    if requested_target_type == "set":
        try:
            rip_latest_result = (
                public_read_client.table("explore_rip_statistics_latest")
                .select("*")
                .eq("set_id", requested_target_id)
                .limit(1)
                .execute()
            )
            rip_latest_row = _first_row(rip_latest_result)
            if rip_latest_row:
                resolved_set_id = _to_optional_str(rip_latest_row.get("set_id"))
                rip_run_id = rip_latest_row.get("calculation_run_id")
                if rip_run_id:
                    run_id = str(rip_run_id)
                    summary = {
                        k: v for k, v in rip_latest_row.items() if k not in _RIP_SUMMARY_META_KEYS
                    }

                    # While the view is being updated, enrich with fields already available
                    # in set_pack_score_rankings_latest without computing anything in service.
                    try:
                        ranking_result = (
                            public_read_client.table("set_pack_score_rankings_latest")
                            .select(
                                "target_id,calculation_run_id,"
                                + ",".join(_RIP_SUMMARY_SUPPLEMENT_FIELDS)
                            )
                            .eq("target_id", requested_target_id)
                            .eq("calculation_run_id", run_id)
                            .limit(1)
                            .execute()
                        )
                        ranking_row = _first_row(ranking_result)
                        if ranking_row:
                            for field in _RIP_SUMMARY_SUPPLEMENT_FIELDS:
                                if field in ranking_row and (
                                    field not in summary or summary.get(field) is None
                                ):
                                    summary[field] = ranking_row.get(field)
                            sources["set_pack_score_rankings_latest"] = "OK"
                        else:
                            sources["set_pack_score_rankings_latest"] = "NO_ROW"
                    except Exception as ranking_exc:
                        logger.warning(
                            "[explore-page] set_pack_score_rankings_latest supplement failed "
                            "target_id=%s run_id=%s: %s",
                            requested_target_id,
                            run_id,
                            ranking_exc,
                        )
                        warnings.append(
                            "Failed to load supplemental RIP ranking fields from "
                            "set_pack_score_rankings_latest"
                        )
                        sources["set_pack_score_rankings_latest"] = "FAILED"

                    summary_from_rip_latest = True
                    summary_from_canonical = True
                    sources["explore_rip_statistics_latest"] = "OK"
                    sources["summary_source"] = "explore_rip_statistics_latest"
                    sources["latest_target_source"] = "explore_rip_statistics_latest"
                    sources["simulation_latest_by_target"] = "SKIPPED_RIP_SUMMARY"
                    sources["simulation_run_summary"] = "SKIPPED_RIP_SUMMARY"
                    sources["simulation_derived_metrics"] = "SKIPPED_RIP_SUMMARY"

                    missing_fields = _missing_required_fields(summary, _RIP_SUMMARY_REQUIRED_FIELDS)
                    if missing_fields:
                        warnings.append(
                            "explore_rip_statistics_latest is missing required summary fields: "
                            + ", ".join(missing_fields)
                            + ". Update view public.explore_rip_statistics_latest."
                        )
                        sources["explore_rip_statistics_latest"] = "MISSING_REQUIRED_FIELDS"
                else:
                    warnings.append(
                        "explore_rip_statistics_latest did not expose calculation_run_id; "
                        "fell back to simulation_latest_by_target"
                    )
                    sources["explore_rip_statistics_latest"] = "MISSING_CALCULATION_RUN_ID_FALLBACK"
            else:
                sources["explore_rip_statistics_latest"] = "NO_ROW_FALLBACK"
        except Exception as exc:
            logger.warning(
                "[explore-page] explore_rip_statistics_latest unavailable target_id=%s; "
                "falling back to simulation_latest_by_target: %s",
                requested_target_id,
                exc,
            )
            warnings.append(
                "explore_rip_statistics_latest unavailable; fell back to simulation_latest_by_target"
            )
            sources["explore_rip_statistics_latest"] = "UNAVAILABLE_FALLBACK"

    # Prefer canonical latest-by-target source when RIP summary wasn't used.
    # The view uses run_at (not created_at) as its timestamp column.
    if not summary_from_rip_latest:
        try:
            latest_target_result = (
                public_read_client.table("simulation_latest_by_target")
                .select("*")
                .eq("target_type", requested_target_type)
                .eq("target_id", requested_target_id)
                .order("run_at", desc=True)
                .limit(1)
                .execute()
            )
            latest_target_row = _first_row(latest_target_result)
            if not latest_target_row:
                raise ExplorePageError(
                    status_code=404,
                    message="No simulation data found for this target",
                    code="TARGET_NOT_FOUND",
                )

            latest_run_id = latest_target_row.get("calculation_run_id")
            if not latest_run_id:
                warnings.append(
                    "simulation_latest_by_target did not expose calculation_run_id; "
                    "fell back to calculation_runs latest lookup"
                )
                sources["simulation_latest_by_target"] = "MISSING_CALCULATION_RUN_ID_FALLBACK"
                run_id = _lookup_latest_run_from_calculation_runs(
                    requested_target_type,
                    requested_target_id,
                )
                sources["latest_target_source"] = "calculation_runs_fallback"
            else:
                run_id = str(latest_run_id)
                # Build summary directly from the canonical row — no separate summary/derived queries needed.
                summary = {k: v for k, v in latest_target_row.items() if k not in _CANONICAL_META_KEYS}
                summary_from_canonical = True
                sources["simulation_latest_by_target"] = "OK"
                sources["summary_source"] = "simulation_latest_by_target"
                sources["latest_target_source"] = "simulation_latest_by_target"
                sources["simulation_run_summary"] = "SKIPPED_CANONICAL"
                sources["simulation_derived_metrics"] = "SKIPPED_CANONICAL"
        except ExplorePageError:
            raise
        except Exception as exc:
            logger.warning(
                "[explore-page] simulation_latest_by_target unavailable target_type=%s target_id=%s; "
                "falling back to calculation_runs: %s",
                requested_target_type,
                requested_target_id,
                exc,
            )
            warnings.append(
                "simulation_latest_by_target unavailable or missing required columns; "
                "fell back to calculation_runs latest lookup"
            )
            sources["simulation_latest_by_target"] = "UNAVAILABLE_FALLBACK"
            try:
                run_id = _lookup_latest_run_from_calculation_runs(
                    requested_target_type,
                    requested_target_id,
                )
                sources["latest_target_source"] = "calculation_runs_fallback"
            except ExplorePageError:
                raise
            except Exception as fallback_exc:
                logger.exception(
                    "[explore-page] calculation_runs query failed target_type=%s target_id=%s",
                    requested_target_type,
                    requested_target_id,
                )
                raise ExplorePageError(
                    status_code=500,
                    message="Failed to fetch simulation data",
                    code="RUN_QUERY_FAILED",
                ) from fallback_exc

    # Summary + derived metrics (required only when canonical view was not used).
    summary_started = time.perf_counter()
    if not summary_from_canonical:
        try:
            summary_result = (
                public_read_client.table("simulation_run_summary")
                .select(
                    "pack_cost,mean_value,median_value,min_value,max_value,std_dev,"
                    "total_ev,net_value,roi,roi_percent,prob_profit,prob_big_hit,big_hit_threshold,"
                    "expected_loss_when_losing,median_loss_when_losing,tail_value_p05,coefficient_of_variation"
                )
                .eq("calculation_run_id", run_id)
                .single()
                .execute()
            )
            summary = summary_result.data if summary_result and summary_result.data else {}
            if not summary:
                raise ExplorePageError(
                    status_code=500,
                    message="Failed to load required summary statistics",
                    code="SUMMARY_QUERY_FAILED",
                )
            sources["simulation_run_summary"] = "OK"
            sources["summary_source"] = "simulation_run_summary+simulation_derived_metrics"
        except ExplorePageError:
            raise
        except Exception as exc:
            logger.exception("[explore-page] simulation_run_summary required query failed run_id=%s", run_id)
            raise ExplorePageError(
                status_code=500,
                message="Failed to load required summary statistics",
                code="SUMMARY_QUERY_FAILED",
            ) from exc

        try:
            derived_result = (
                public_read_client.table("simulation_derived_metrics")
                .select("*")
                .eq("calculation_run_id", run_id)
                .single()
                .execute()
            )
            derived_metrics = derived_result.data if derived_result and derived_result.data else {}
            if not derived_metrics:
                raise ExplorePageError(
                    status_code=500,
                    message="Failed to load required derived metrics",
                    code="DERIVED_QUERY_FAILED",
                )
            summary.update(derived_metrics)
            sources["simulation_derived_metrics"] = "OK"
        except ExplorePageError:
            raise
        except Exception as exc:
            logger.exception("[explore-page] simulation_derived_metrics required query failed run_id=%s", run_id)
            raise ExplorePageError(
                status_code=500,
                message="Failed to load required derived metrics",
                code="DERIVED_QUERY_FAILED",
            ) from exc

    summary_ms = (time.perf_counter() - summary_started) * 1000

    # Rankings (optional)
    rankings_started = time.perf_counter()
    rankings: List[Dict[str, Any]] = []
    try:
        rankings_result = (
            public_read_client.table("simulation_pull_summary")
            .select("rarity_bucket,pulled_count,avg_sampled_value,total_sampled_value")
            .eq("calculation_run_id", run_id)
            .order("rarity_bucket", desc=False)
            .execute()
        )
        rankings = rankings_result.data if rankings_result.data else []
        sources["simulation_pull_summary"] = "OK"
    except Exception as exc:
        logger.warning("[explore-page] simulation_pull_summary failed run_id=%s: %s", run_id, exc)
        warnings.append("Failed to load rarity rankings")
        sources["simulation_pull_summary"] = "FAILED"
    rankings_ms = (time.perf_counter() - rankings_started) * 1000

    # RIP statistics (optional)
    rip_started = time.perf_counter()
    rip_statistics: Dict[str, Any] = {"pack_paths": {}, "normal_pack_states": {}}
    try:
        rip_result = (
            public_read_client.table("simulation_state_counts")
            .select("state_group,state_name,occurrence_count")
            .eq("calculation_run_id", run_id)
            .execute()
        )
        for row in (rip_result.data or []):
            group = row.get("state_group", "")
            name = row.get("state_name", "")
            count = row.get("occurrence_count", 0)
            if group == "pack_path":
                rip_statistics["pack_paths"][name] = count
            elif group == "normal_pack_state":
                rip_statistics["normal_pack_states"][name] = count
        sources["simulation_state_counts"] = "OK"
    except Exception as exc:
        logger.warning("[explore-page] simulation_state_counts failed run_id=%s: %s", run_id, exc)
        warnings.append("Failed to load RIP statistics")
        sources["simulation_state_counts"] = "FAILED"
    rip_ms = (time.perf_counter() - rip_started) * 1000

    # Percentiles (optional)
    percentiles_started = time.perf_counter()
    percentiles: List[Dict[str, Any]] = []
    try:
        percentiles_result = (
            public_read_client.table("simulation_percentiles")
            .select("percentile,value")
            .eq("calculation_run_id", run_id)
            .order("percentile", desc=False)
            .execute()
        )
        percentiles = percentiles_result.data if percentiles_result.data else []
        sources["simulation_percentiles"] = "OK"
    except Exception as exc:
        logger.warning("[explore-page] simulation_percentiles failed run_id=%s: %s", run_id, exc)
        warnings.append("Failed to load percentiles")
        sources["simulation_percentiles"] = "FAILED"
    percentiles_ms = (time.perf_counter() - percentiles_started) * 1000

    _populate_p99_ratio_from_percentiles(summary, percentiles)
    opening_desirability: Optional[Dict[str, Any]] = None
    if requested_target_type == "set":
        try:
            opening_set_metadata = _fetch_set_metadata_for_target(requested_target_id)
            if opening_set_metadata:
                resolved_set_id = resolved_set_id or _to_optional_str(opening_set_metadata.get("id"))
                resolved_set_canonical_key = resolved_set_canonical_key or _to_optional_str(
                    opening_set_metadata.get("canonical_key")
                )
                sources["opening_desirability_set_metadata"] = "OK"
            else:
                sources["opening_desirability_set_metadata"] = "NO_ROW"
        except Exception as exc:
            logger.warning(
                "[explore-page] Opening Desirability set metadata lookup failed target_id=%s: %s",
                requested_target_id,
                exc,
            )
            sources["opening_desirability_set_metadata"] = "FAILED"

        _populate_biggest_upside_metrics_for_set(summary, requested_target_id, warnings, sources)
        _populate_relative_average_return_score_for_set(summary, requested_target_id, warnings, sources)
        _populate_desirability_drivers_for_set(summary, requested_target_id, warnings, sources)
        opening_desirability = _populate_opening_desirability_for_set(
            summary=summary,
            requested_target_id=requested_target_id,
            resolved_set_id=resolved_set_id,
            resolved_set_canonical_key=resolved_set_canonical_key,
            warnings=warnings,
            sources=sources,
        )
        if opening_desirability is not None:
            opening_desirability["topCollectorAppealDrivers"] = _build_public_top_collector_appeal_drivers(
                summary_cards=summary.get("top_collector_appeal_drivers"),
                raw_cards=summary.get("top_desirability_cards"),
            )
    _ensure_optional_summary_fields(summary)

    # Distribution bins (optional, separate query)
    distribution_started = time.perf_counter()
    distribution_bins: List[Dict[str, Any]] = []
    try:
        distribution_result = (
            public_read_client.table("simulation_value_distribution_bins")
            .select(
                "bin_floor,bin_ceiling,occurrence_count,probability,"
                "cumulative_probability,survival_probability"
            )
            .eq("calculation_run_id", run_id)
            .order("bin_floor", desc=False)
            .limit(clamped_distribution_bins_limit)
            .execute()
        )
        distribution_bins = distribution_result.data if distribution_result.data else []
        sources["simulation_value_distribution_bins"] = "OK"
    except Exception as exc:
        logger.warning("[explore-page] simulation_value_distribution_bins failed run_id=%s: %s", run_id, exc)
        warnings.append("Failed to load distribution bins")
        sources["simulation_value_distribution_bins"] = "FAILED"
    distribution_ms = (time.perf_counter() - distribution_started) * 1000

    # Threshold bins (optional, separate query)
    threshold_started = time.perf_counter()
    threshold_bins: List[Dict[str, Any]] = []
    try:
        threshold_result = (
            public_read_client.table("simulation_value_threshold_bins")
            .select(
                "threshold_floor,threshold_ceiling,occurrence_count,probability,"
                "cumulative_probability,survival_probability,bucket_label,bucket_order"
            )
            .eq("calculation_run_id", run_id)
            .order("bucket_order", desc=False)
            .execute()
        )
        threshold_bins = threshold_result.data if threshold_result.data else []
        sources["simulation_value_threshold_bins"] = "OK"
    except Exception as exc:
        logger.warning("[explore-page] simulation_value_threshold_bins failed run_id=%s: %s", run_id, exc)
        warnings.append("Failed to load threshold bins")
        sources["simulation_value_threshold_bins"] = "FAILED"
    threshold_ms = (time.perf_counter() - threshold_started) * 1000

    # Top hits (optional)
    top_hits_started = time.perf_counter()
    top_hits: List[Dict[str, Any]] = []
    try:
        top_hits_result = (
            public_read_client.table("simulation_input_cards_with_near_mint_price")
            .select("card_id,card_variant_id,card_name,rarity_bucket,ev_contribution,current_near_mint_price")
            .eq("calculation_run_id", run_id)
            .order("ev_contribution", desc=True)
            .limit(clamped_top_hits_limit)
            .execute()
        )
        raw_hits = top_hits_result.data if top_hits_result.data else []
        top_hits = _enrich_top_hits_with_images(raw_hits)
        sources["simulation_input_cards"] = "OK" if top_hits else "NO_ROWS"
        if not top_hits:
            warnings.append(
                "Simulation Drivers unavailable: simulation_input_cards_with_near_mint_price "
                f"returned no rows for calculation_run_id={run_id}"
            )
    except Exception as exc:
        logger.warning("[explore-page] simulation_input_cards failed run_id=%s: %s", run_id, exc)
        warnings.append(
            "Failed to load top hits from simulation_input_cards_with_near_mint_price "
            f"for calculation_run_id={run_id}: {exc}"
        )
        sources["simulation_input_cards"] = "FAILED"
    top_hits_ms = (time.perf_counter() - top_hits_started) * 1000

    # Historical trend (optional)
    history_started = time.perf_counter()
    history_trend: List[Dict[str, Any]] = []
    try:
        history_rows, history_source = _load_history_trend_rows(
            requested_target_type=requested_target_type,
            requested_target_id=requested_target_id,
            history_trend_limit=history_trend_limit,
        )
        history_trend = history_rows
        sources["calculation_history_trend"] = history_source
    except Exception as exc:
        logger.warning(
            "[explore-page] calculation_history_trend failed target_type=%s target_id=%s: %s",
            requested_target_type,
            requested_target_id,
            exc,
        )
        warnings.append("Failed to load historical trend")
        sources["calculation_history_trend"] = "FAILED"
    history_ms = (time.perf_counter() - history_started) * 1000

    total_ms = (time.perf_counter() - total_started) * 1000

    interpretation = _strip_public_weight_metadata(
        build_rip_interpretation(
            {
                "summary": summary,
                "rankings": rankings,
                "rip_statistics": rip_statistics,
                "percentiles": percentiles,
                "distribution_bins": distribution_bins,
                "threshold_bins": threshold_bins,
                "top_hits": top_hits,
                "history_trend": history_trend,
            }
        )
    )

    pull_rate_assumptions = None
    if requested_target_type == "set":
        config_class, _ = _resolve_set_config_for_explore_target(
            requested_target_id,
            summary,
            warnings,
            sources,
        )
        if config_class is not None:
            pull_rate_assumptions = _build_pull_rate_assumptions(
                config_class=config_class,
                run_id=run_id,
                warnings=warnings,
                sources=sources,
            )
        else:
            sources["pull_rate_assumptions"] = "SET_CONFIG_NOT_FOUND"

    return {
        "summary": summary,
        "rankings": rankings,
        "rip_statistics": rip_statistics,
        "percentiles": percentiles,
        "distribution_bins": distribution_bins,
        "threshold_bins": threshold_bins,
        "top_hits": top_hits,
        "history_trend": history_trend,
        "interpretation": interpretation,
        "openingDesirability": opening_desirability,
        "pull_rate_assumptions": pull_rate_assumptions,
        "meta": {
            "request": {
                "target_type": requested_target_type,
                "target_id": requested_target_id,
                "limit_distribution_bins": clamped_distribution_bins_limit,
                "limit_top_hits": clamped_top_hits_limit,
                "limit_history_trend": history_trend_limit,
            },
            "sources": sources,
            "warnings": warnings,
            "timings": {
                "summary_ms": round(summary_ms, 2),
                "rankings_ms": round(rankings_ms, 2),
                "rip_statistics_ms": round(rip_ms, 2),
                "percentiles_ms": round(percentiles_ms, 2),
                "distribution_bins_ms": round(distribution_ms, 2),
                "threshold_bins_ms": round(threshold_ms, 2),
                "top_hits_ms": round(top_hits_ms, 2),
                "history_trend_ms": round(history_ms, 2),
                "total_backend_ms": round(total_ms, 2),
            },
        },
    }


def _normalize_rarity_label(label):
    return label.lower().strip().replace("_", " ").replace("-", " ").replace("  ", " ")

def _build_pull_rate_assumptions(
    *,
    config_class: Any,
    run_id: str,
    warnings: List[str],
    sources: Dict[str, str],
) -> Optional[Dict[str, Any]]:
    pull_rate_mapping = getattr(config_class, "PULL_RATE_MAPPING", {}) or {}
    if not isinstance(pull_rate_mapping, dict) or not pull_rate_mapping:
        sources["pull_rate_assumptions"] = "NO_PULL_RATE_MAPPING"
        return None

    normalized_mapping = {
        _normalize_rarity_label(key): value for key, value in pull_rate_mapping.items()
    }

    generic_probabilities, slot_labels_by_rarity, regular_reverse_slot_count = _collect_generic_probability_inputs(config_class)
    generic_denominators: Dict[str, int] = {}
    for rarity_key, probability in generic_probabilities.items():
        if probability <= 0:
            continue
        generic_denominators[rarity_key] = int(round(1 / probability))

    slot_defaults = getattr(config_class, "SLOTS_PER_RARITY", {}) or {}
    common_slot_count = int(slot_defaults.get("common", 4)) if _to_positive_denominator(slot_defaults.get("common", 4)) else 4
    uncommon_slot_count = int(slot_defaults.get("uncommon", 3)) if _to_positive_denominator(slot_defaults.get("uncommon", 3)) else 3
    reverse_slot_count_default = _to_positive_denominator(slot_defaults.get("reverse"))
    reverse_slot_count = reverse_slot_count_default or regular_reverse_slot_count or 2

    cards_rows: List[Dict[str, Any]] = []
    rarity_card_ids: Dict[str, set[str]] = {}
    try:
        cards_result = (
            public_read_client.table("simulation_input_cards_with_near_mint_price")
            .select("card_id,card_variant_id,card_name,rarity_bucket")
            .eq("calculation_run_id", run_id)
            .execute()
        )
        cards_rows = list(cards_result.data or [])

        for row in cards_rows:
            rarity_key = _normalize_rarity(row.get("rarity_bucket"))
            if not rarity_key:
                continue

            identifier = _normalize_key(row.get("card_variant_id"))
            if not identifier:
                identifier = _normalize_key(row.get("card_id"))
            if not identifier:
                identifier = _normalize_key(row.get("card_name"))
            if not identifier:
                continue

            rarity_card_ids.setdefault(rarity_key, set()).add(identifier)
        sources["pull_rate_assumptions_card_counts"] = "OK"
    except Exception as exc:
        logger.warning(
            "[explore-page] simulation_input_cards_with_near_mint_price pull-rate count query failed run_id=%s: %s",
            run_id,
            exc,
        )
        warnings.append("Failed to derive eligible card counts for pull-rate assumptions")
        sources["pull_rate_assumptions_card_counts"] = "FAILED"
        sources["pull_rate_assumptions_regular_reverse_count"] = "FAILED"

    def _derive_regular_reverse_card_count() -> Optional[int]:
        if not cards_rows:
            if sources.get("pull_rate_assumptions_regular_reverse_count") != "FAILED":
                sources["pull_rate_assumptions_regular_reverse_count"] = "UNAVAILABLE"
            return None

        rows_by_rarity: Dict[str, List[Dict[str, Any]]] = {}
        for row in cards_rows:
            rarity_key = _normalize_rarity(row.get("rarity_bucket"))
            if not rarity_key:
                continue
            rows_by_rarity.setdefault(rarity_key, []).append(row)

        candidate_rows = rows_by_rarity.get("regular reverse", [])
        if not candidate_rows:
            fallback_rarities = {"common", "uncommon", "rare"}
            candidate_rows = [
                row
                for rarity_key, rows in rows_by_rarity.items()
                if rarity_key in fallback_rarities
                for row in rows
            ]

        if not candidate_rows:
            sources["pull_rate_assumptions_regular_reverse_count"] = "UNAVAILABLE"
            return None

        # Regular reverse sampling in sim pools is variant-row based when variant ids are available.
        use_variant_ids = any(_normalize_key(row.get("card_variant_id")) for row in candidate_rows)
        identifier_field = "card_variant_id" if use_variant_ids else "card_id"
        identifiers = {
            _normalize_key(row.get(identifier_field))
            for row in candidate_rows
            if _normalize_key(row.get(identifier_field))
        }

        if not identifiers:
            sources["pull_rate_assumptions_regular_reverse_count"] = "UNAVAILABLE"
            return None

        sources["pull_rate_assumptions_regular_reverse_count"] = "OK"
        return len(identifiers)

    pack_structure_rows: List[Dict[str, Any]] = []

    common_pool_count = _to_positive_denominator(pull_rate_mapping.get("common"))
    common_specific = (
        (common_pool_count / common_slot_count)
        if common_pool_count and common_slot_count > 0
        else None
    )
    pack_structure_rows.append(
        _build_pull_rate_assumption_row(
            group="pack_structure",
            rarity="common",
            card_count=common_pool_count,
            slot_count=common_slot_count,
            expected_cards_per_pack=float(common_slot_count),
            rarity_odds_denominator=None,
            specific_card_odds_denominator=common_specific,
            probability_label=f"{common_slot_count} cards per pack",
            pack_model_label=f"{common_slot_count} cards per pack",
            slot_label="Base pack composition",
            notes="Base pack slot population; multiple cards appear per pack.",
        )
    )

    uncommon_pool_count = _to_positive_denominator(pull_rate_mapping.get("uncommon"))
    uncommon_specific = (
        (uncommon_pool_count / uncommon_slot_count)
        if uncommon_pool_count and uncommon_slot_count > 0
        else None
    )
    pack_structure_rows.append(
        _build_pull_rate_assumption_row(
            group="pack_structure",
            rarity="uncommon",
            card_count=uncommon_pool_count,
            slot_count=uncommon_slot_count,
            expected_cards_per_pack=float(uncommon_slot_count),
            rarity_odds_denominator=None,
            specific_card_odds_denominator=uncommon_specific,
            probability_label=f"{uncommon_slot_count} cards per pack",
            pack_model_label=f"{uncommon_slot_count} cards per pack",
            slot_label="Base pack composition",
            notes="Base pack slot population; multiple cards appear per pack.",
        )
    )

    rare_card_count = _to_positive_denominator(pull_rate_mapping.get("rare"))
    rare_probability = _to_positive_probability((getattr(config_class, "RARE_SLOT_PROBABILITY", {}) or {}).get("rare"))
    rare_rarity_odds = int(round(1 / rare_probability)) if rare_probability else None
    rare_specific = (
        (rare_card_count / rare_probability)
        if rare_card_count and rare_probability
        else None
    )
    pack_structure_rows.append(
        _build_pull_rate_assumption_row(
            group="pack_structure",
            rarity="rare",
            card_count=rare_card_count,
            slot_count=_to_positive_denominator(slot_defaults.get("rare", 1)) or 1,
            expected_cards_per_pack=rare_probability,
            rarity_odds_denominator=rare_rarity_odds,
            specific_card_odds_denominator=rare_specific,
            probability_label=None,
            pack_model_label=(
                f"{(rare_probability * 100):.1f}% rare-slot outcome"
                if rare_probability
                else None
            ),
            slot_label="Rare slot model",
            notes="Regular rare outcome in the rare slot.",
        )
    )

    regular_reverse_probability = generic_probabilities.get("regular reverse")
    regular_reverse_rarity_odds = (
        int(round(1 / regular_reverse_probability))
        if regular_reverse_probability and regular_reverse_probability > 0
        else None
    )
    regular_reverse_card_count = _derive_regular_reverse_card_count()
    regular_reverse_specific = (
        (regular_reverse_card_count / regular_reverse_probability)
        if regular_reverse_probability and regular_reverse_card_count
        else None
    )
    pack_structure_rows.append(
        _build_pull_rate_assumption_row(
            group="pack_structure",
            rarity="regular reverse",
            card_count=regular_reverse_card_count,
            slot_count=reverse_slot_count,
            expected_cards_per_pack=regular_reverse_probability,
            rarity_odds_denominator=regular_reverse_rarity_odds,
            specific_card_odds_denominator=regular_reverse_specific,
            probability_label=(
                f"Reverse slot outcome across {reverse_slot_count} slots"
                if reverse_slot_count
                else "Reverse slot outcome"
            ),
            pack_model_label=(
                f"{regular_reverse_probability:.2f} slots per pack"
                if regular_reverse_probability
                else None
            ),
            slot_label="Reverse slot model",
            notes="Reverse slot baseline outcome; specific-card odds require eligible reverse pool count.",
        )
    )

    special_pack_rows = _build_special_pack_rule_rows(
        config_class=config_class,
        pull_rate_mapping=pull_rate_mapping,
    )
    special_pack_rarities = {
        _normalize_rarity(row.get("rarity"))
        for row in special_pack_rows
        if row.get("rarity")
    }

    hit_rarity_rows: List[Dict[str, Any]] = []
    hit_rarity_keys = {
        _normalize_rarity(rarity_name)
        for rarity_name in pull_rate_mapping.keys()
        if _normalize_rarity(rarity_name)
    }
    hit_rarity_keys.update(generic_denominators.keys())
    hit_rarity_keys = {
        rarity_key
        for rarity_key in hit_rarity_keys
        if rarity_key
        and not _is_base_population_rarity(rarity_key)
        and rarity_key != "regular reverse"
        and rarity_key not in special_pack_rarities
        and not _is_special_pack_rarity(rarity_key)
    }

    for rarity_key in sorted(hit_rarity_keys):
        rarity_odds_denominator = generic_denominators.get(rarity_key)
        specific_card_odds_denominator = _to_positive_denominator(pull_rate_mapping.get(rarity_key))

        card_count: Optional[int] = None
        if rarity_odds_denominator and specific_card_odds_denominator:
            card_count = int(round(specific_card_odds_denominator / rarity_odds_denominator))
        elif rarity_odds_denominator and not specific_card_odds_denominator:
            derived_count = len(rarity_card_ids.get(rarity_key, set())) or None
            if derived_count:
                card_count = derived_count
                specific_card_odds_denominator = rarity_odds_denominator * card_count

        slot_labels = sorted(slot_labels_by_rarity.get(rarity_key, set()))
        notes = "Specific-card odds sourced from set config PULL_RATE_MAPPING."
        if specific_card_odds_denominator is None and rarity_odds_denominator is not None:
            notes = "Specific-card odds derived from rarity odds and eligible card count fallback."
        elif rarity_odds_denominator is None:
            notes = "Generic rarity odds are unavailable for this rarity in slot probability config."

        hit_rarity_rows.append(
            _build_pull_rate_assumption_row(
                group="hit_rarity_model",
                rarity=rarity_key,
                card_count=card_count,
                slot_count=None,
                expected_cards_per_pack=generic_probabilities.get(rarity_key),
                rarity_odds_denominator=rarity_odds_denominator,
                specific_card_odds_denominator=specific_card_odds_denominator,
                probability_label=None,
                pack_model_label=None,
                slot_label=" + ".join(slot_labels) if slot_labels else None,
                notes=notes,
            )
        )

    groups = [
        {
            "key": "pack_structure",
            "label": "Pack Structure",
            "rows": pack_structure_rows,
        },
        {
            "key": "hit_rarity_model",
            "label": "Hit Rarity Model",
            "rows": hit_rarity_rows,
        },
        {
            "key": "special_pack_rules",
            "label": "Special Pack Rules",
            "rows": special_pack_rows,
        },
    ]

    rows = [row for group in groups for row in group["rows"]]

    sources["pull_rate_assumptions"] = "OK" if rows else "NO_ROWS"
    return {
        "groups": groups,
        "rows": rows,
        "meta": {
            "is_modelled": True,
            "is_modeled": True,
            "source_label": "Config-based pack model + inDex-derived card counts",
        },
    }


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
    """Blend Big Hit Upside (P95) and God Pull Upside (P99) into a 0-100 score."""

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


def _rank_tier_from_percentile(rank: int, total: int) -> str:
    if rank <= max(1, math.ceil(total * 0.05)):
        return "S"
    if rank <= max(1, math.ceil(total * 0.15)):
        return "A"
    if rank <= max(1, math.ceil(total * 0.30)):
        return "B"
    if rank <= max(1, math.ceil(total * 0.50)):
        return "C"
    if rank <= max(1, math.ceil(total * 0.75)):
        return "D"
    return "F"


def _populate_biggest_upside_metrics_for_set(
    summary: Dict[str, Any],
    requested_target_id: str,
    warnings: List[str],
    sources: Dict[str, str],
) -> None:
    """Attach blended Biggest Upside score + relative/rank/tier for set targets."""

    summary["biggest_upside_score"] = _blend_biggest_upside_score(
        summary.get("p95_value_to_cost_ratio"),
        summary.get("p99_value_to_cost_ratio"),
    )

    if summary.get("biggest_upside_score") is None:
        summary["relative_biggest_upside_score"] = None
        summary["biggest_upside_rank"] = None
        summary["biggest_upside_tier"] = None
        return

    try:
        peers_result = (
            public_read_client.table("explore_rip_statistics_latest")
            .select("set_id,p95_value_to_cost_ratio,p99_value_to_cost_ratio")
            .execute()
        )
        peer_rows = peers_result.data if peers_result and peers_result.data else []
    except Exception as exc:
        logger.warning(
            "[explore-page] biggest_upside peer query failed target_id=%s: %s",
            requested_target_id,
            exc,
        )
        warnings.append("Failed to compute blended Biggest Upside rank context")
        sources["biggest_upside_blend"] = "FAILED"
        summary["relative_biggest_upside_score"] = None
        summary["biggest_upside_rank"] = None
        summary["biggest_upside_tier"] = None
        return

    scored_peers: List[tuple[str, float]] = []
    for row in peer_rows:
        if not isinstance(row, dict):
            continue
        set_id = str(row.get("set_id") or "").strip()
        if not set_id:
            continue
        blended = _blend_biggest_upside_score(
            row.get("p95_value_to_cost_ratio"),
            row.get("p99_value_to_cost_ratio"),
        )
        if blended is None:
            continue
        scored_peers.append((set_id, blended))

    if not scored_peers:
        sources["biggest_upside_blend"] = "NO_PEERS"
        summary["relative_biggest_upside_score"] = None
        summary["biggest_upside_rank"] = None
        summary["biggest_upside_tier"] = None
        return

    scores_only = [score for _, score in scored_peers]
    score_min = min(scores_only)
    score_max = max(scores_only)
    target_score = _to_optional_float(summary.get("biggest_upside_score"))
    if target_score is None:
        summary["relative_biggest_upside_score"] = None
    elif score_max <= score_min:
        summary["relative_biggest_upside_score"] = 50.0
    else:
        summary["relative_biggest_upside_score"] = 100.0 * ((target_score - score_min) / (score_max - score_min))

    ranked = sorted(scored_peers, key=lambda item: item[1], reverse=True)
    rank_lookup = {set_id: index for index, (set_id, _) in enumerate(ranked, start=1)}
    target_rank = rank_lookup.get(requested_target_id)
    summary["biggest_upside_rank"] = target_rank
    summary["biggest_upside_tier"] = (
        _rank_tier_from_percentile(target_rank, len(ranked)) if target_rank is not None else None
    )
    sources["biggest_upside_blend"] = "SERVICE_COMPUTED"


def _populate_relative_average_return_score_for_set(
    summary: Dict[str, Any],
    requested_target_id: str,
    warnings: List[str],
    sources: Dict[str, str],
) -> None:
    mean_ratio = _resolve_mean_value_to_cost_ratio(summary)
    if mean_ratio is None:
        summary["relative_average_return_score"] = None
        return

    try:
        peers_result = (
            public_read_client.table("explore_rip_statistics_latest")
            .select("set_id,mean_value_to_cost_ratio")
            .execute()
        )
        peer_rows = peers_result.data if peers_result and peers_result.data else []
    except Exception as exc:
        logger.warning(
            "[explore-page] average_return peer query failed target_id=%s: %s",
            requested_target_id,
            exc,
        )
        warnings.append("Failed to compute relative Expected Value context")
        sources["average_return_relative"] = "FAILED"
        summary["relative_average_return_score"] = None
        return

    peer_ratios: List[float] = []
    for row in peer_rows:
        if not isinstance(row, dict):
            continue
        if not str(row.get("set_id") or "").strip():
            continue
        ratio = _to_optional_float(row.get("mean_value_to_cost_ratio"))
        if ratio is None:
            ratio = _resolve_mean_value_to_cost_ratio(row)
        if ratio is not None:
            peer_ratios.append(ratio)

    if not peer_ratios:
        sources["average_return_relative"] = "NO_PEERS"
        summary["relative_average_return_score"] = None
        return

    score_min = min(peer_ratios)
    score_max = max(peer_ratios)
    if score_max <= score_min:
        summary["relative_average_return_score"] = 50.0
    else:
        summary["relative_average_return_score"] = 100.0 * ((mean_ratio - score_min) / (score_max - score_min))
    sources["average_return_relative"] = "SERVICE_COMPUTED"


def _populate_p99_ratio_from_percentiles(summary: Dict[str, Any], percentiles: List[Dict[str, Any]]) -> None:
    if summary.get("p99_value_to_cost_ratio") is not None:
        return

    pack_cost = _to_optional_float(summary.get("pack_cost"))
    if pack_cost is None or pack_cost <= 0:
        return

    p99_value: Optional[float] = None
    for row in percentiles:
        if not isinstance(row, dict):
            continue
        percentile = _to_optional_float(row.get("percentile"))
        if percentile is None or abs(percentile - 99.0) >= 0.001:
            continue
        p99_value = _to_optional_float(row.get("value"))
        if p99_value is not None:
            break

    if p99_value is None:
        return

    summary["p99_value"] = p99_value
    summary["p99_value_to_cost_ratio"] = p99_value / pack_cost


def _missing_required_fields(row: Dict[str, Any], required_fields: tuple[str, ...]) -> List[str]:
    """Return required field names that are absent from a row."""
    return [field for field in required_fields if field not in row]


def _lookup_latest_run_from_calculation_runs(target_type: str, target_id: str) -> str:
    """Fallback latest run lookup when canonical latest view is unavailable."""
    run_result = (
        public_read_client.table("calculation_runs")
        .select("id,created_at,target_type,target_id")
        .eq("target_type", target_type)
        .eq("target_id", target_id)
        .order("created_at", desc=True)
        .limit(1)
        .execute()
    )
    run_row = _first_row(run_result)
    if not run_row or not run_row.get("id"):
        raise ExplorePageError(
            status_code=404,
            message="No simulation data found for this target",
            code="TARGET_NOT_FOUND",
        )
    return str(run_row.get("id"))


def get_explore_page_payload(
    target_type: str,
    target_id: str,
    limit_distribution_bins: Any = DEFAULT_DISTRIBUTION_BINS_LIMIT,
    limit_top_hits: Any = DEFAULT_TOP_HITS_LIMIT,
) -> Dict[str, Any]:
    """Aggregate simulation data for Explore page."""
    total_started = time.perf_counter()

    requested_target_type = (target_type or "").strip()
    requested_target_id = (target_id or "").strip()

    if not requested_target_type or not requested_target_id:
        raise ExplorePageError(
            status_code=400,
            message="target_type and target_id are required",
            code="INVALID_TARGET",
        )

    clamped_distribution_bins_limit = _sanitize_limit(
        limit_distribution_bins,
        default=DEFAULT_DISTRIBUTION_BINS_LIMIT,
        max_value=MAX_DISTRIBUTION_BINS_LIMIT,
    )
    clamped_top_hits_limit = _sanitize_limit(
        limit_top_hits,
        default=DEFAULT_TOP_HITS_LIMIT,
        max_value=MAX_TOP_HITS_LIMIT,
    )
    history_trend_limit = _sanitize_limit(
        DEFAULT_HISTORY_TREND_LIMIT,
        default=DEFAULT_HISTORY_TREND_LIMIT,
        max_value=MAX_HISTORY_TREND_LIMIT,
    )

    warnings: List[str] = []
    sources: Dict[str, str] = {}

    # Fields from simulation_latest_by_target that are lookup keys, not metrics.
    _CANONICAL_META_KEYS = frozenset({"target_type", "target_id", "calculation_run_id", "run_at"})

    # Prefer RIP-specific summary source for set targets first.
    summary: Dict[str, Any] = {}
    resolved_set_id: Optional[str] = None
    resolved_set_canonical_key: Optional[str] = None
    summary_from_canonical = False
    summary_from_rip_latest = False
    if requested_target_type == "set":
        try:
            rip_latest_result = (
                public_read_client.table("explore_rip_statistics_latest")
                .select("*")
                .eq("set_id", requested_target_id)
                .limit(1)
                .execute()
            )
            rip_latest_row = _first_row(rip_latest_result)
            if rip_latest_row:
                resolved_set_id = _to_optional_str(rip_latest_row.get("set_id"))
                rip_run_id = rip_latest_row.get("calculation_run_id")
                if rip_run_id:
                    run_id = str(rip_run_id)
                    summary = {
                        k: v for k, v in rip_latest_row.items() if k not in _RIP_SUMMARY_META_KEYS
                    }

                    # While the view is being updated, enrich with fields already available
                    # in set_pack_score_rankings_latest without computing anything in service.
                    try:
                        ranking_result = (
                            public_read_client.table("set_pack_score_rankings_latest")
                            .select(
                                "target_id,calculation_run_id,"
                                + ",".join(_RIP_SUMMARY_SUPPLEMENT_FIELDS)
                            )
                            .eq("target_id", requested_target_id)
                            .eq("calculation_run_id", run_id)
                            .limit(1)
                            .execute()
                        )
                        ranking_row = _first_row(ranking_result)
                        if ranking_row:
                            for field in _RIP_SUMMARY_SUPPLEMENT_FIELDS:
                                if field in ranking_row and (
                                    field not in summary or summary.get(field) is None
                                ):
                                    summary[field] = ranking_row.get(field)
                            sources["set_pack_score_rankings_latest"] = "OK"
                        else:
                            sources["set_pack_score_rankings_latest"] = "NO_ROW"
                    except Exception as ranking_exc:
                        logger.warning(
                            "[explore-page] set_pack_score_rankings_latest supplement failed "
                            "target_id=%s run_id=%s: %s",
                            requested_target_id,
                            run_id,
                            ranking_exc,
                        )
                        warnings.append(
                            "Failed to load supplemental RIP ranking fields from "
                            "set_pack_score_rankings_latest"
                        )
                        sources["set_pack_score_rankings_latest"] = "FAILED"

                    summary_from_rip_latest = True
                    summary_from_canonical = True
                    sources["explore_rip_statistics_latest"] = "OK"
                    sources["summary_source"] = "explore_rip_statistics_latest"
                    sources["latest_target_source"] = "explore_rip_statistics_latest"
                    sources["simulation_latest_by_target"] = "SKIPPED_RIP_SUMMARY"
                    sources["simulation_run_summary"] = "SKIPPED_RIP_SUMMARY"
                    sources["simulation_derived_metrics"] = "SKIPPED_RIP_SUMMARY"

                    missing_fields = _missing_required_fields(summary, _RIP_SUMMARY_REQUIRED_FIELDS)
                    if missing_fields:
                        warnings.append(
                            "explore_rip_statistics_latest is missing required summary fields: "
                            + ", ".join(missing_fields)
                            + ". Update view public.explore_rip_statistics_latest."
                        )
                        sources["explore_rip_statistics_latest"] = "MISSING_REQUIRED_FIELDS"
                else:
                    warnings.append(
                        "explore_rip_statistics_latest did not expose calculation_run_id; "
                        "fell back to simulation_latest_by_target"
                    )
                    sources["explore_rip_statistics_latest"] = "MISSING_CALCULATION_RUN_ID_FALLBACK"
            else:
                sources["explore_rip_statistics_latest"] = "NO_ROW_FALLBACK"
        except Exception as exc:
            logger.warning(
                "[explore-page] explore_rip_statistics_latest unavailable target_id=%s; "
                "falling back to simulation_latest_by_target: %s",
                requested_target_id,
                exc,
            )
            warnings.append(
                "explore_rip_statistics_latest unavailable; fell back to simulation_latest_by_target"
            )
            sources["explore_rip_statistics_latest"] = "UNAVAILABLE_FALLBACK"

    # Prefer canonical latest-by-target source when RIP summary wasn't used.
    # The view uses run_at (not created_at) as its timestamp column.
    if not summary_from_rip_latest:
        try:
            latest_target_result = (
                public_read_client.table("simulation_latest_by_target")
                .select("*")
                .eq("target_type", requested_target_type)
                .eq("target_id", requested_target_id)
                .order("run_at", desc=True)
                .limit(1)
                .execute()
            )
            latest_target_row = _first_row(latest_target_result)
            if not latest_target_row:
                raise ExplorePageError(
                    status_code=404,
                    message="No simulation data found for this target",
                    code="TARGET_NOT_FOUND",
                )

            latest_run_id = latest_target_row.get("calculation_run_id")
            if not latest_run_id:
                warnings.append(
                    "simulation_latest_by_target did not expose calculation_run_id; "
                    "fell back to calculation_runs latest lookup"
                )
                sources["simulation_latest_by_target"] = "MISSING_CALCULATION_RUN_ID_FALLBACK"
                run_id = _lookup_latest_run_from_calculation_runs(
                    requested_target_type,
                    requested_target_id,
                )
                sources["latest_target_source"] = "calculation_runs_fallback"
            else:
                run_id = str(latest_run_id)
                # Build summary directly from the canonical row — no separate summary/derived queries needed.
                summary = {k: v for k, v in latest_target_row.items() if k not in _CANONICAL_META_KEYS}
                summary_from_canonical = True
                sources["simulation_latest_by_target"] = "OK"
                sources["summary_source"] = "simulation_latest_by_target"
                sources["latest_target_source"] = "simulation_latest_by_target"
                sources["simulation_run_summary"] = "SKIPPED_CANONICAL"
                sources["simulation_derived_metrics"] = "SKIPPED_CANONICAL"
        except ExplorePageError:
            raise
        except Exception as exc:
            logger.warning(
                "[explore-page] simulation_latest_by_target unavailable target_type=%s target_id=%s; "
                "falling back to calculation_runs: %s",
                requested_target_type,
                requested_target_id,
                exc,
            )
            warnings.append(
                "simulation_latest_by_target unavailable or missing required columns; "
                "fell back to calculation_runs latest lookup"
            )
            sources["simulation_latest_by_target"] = "UNAVAILABLE_FALLBACK"
            try:
                run_id = _lookup_latest_run_from_calculation_runs(
                    requested_target_type,
                    requested_target_id,
                )
                sources["latest_target_source"] = "calculation_runs_fallback"
            except ExplorePageError:
                raise
            except Exception as fallback_exc:
                logger.exception(
                    "[explore-page] calculation_runs query failed target_type=%s target_id=%s",
                    requested_target_type,
                    requested_target_id,
                )
                raise ExplorePageError(
                    status_code=500,
                    message="Failed to fetch simulation data",
                    code="RUN_QUERY_FAILED",
                ) from fallback_exc

    # Summary + derived metrics (required only when canonical view was not used).
    summary_started = time.perf_counter()
    if not summary_from_canonical:
        try:
            summary_result = (
                public_read_client.table("simulation_run_summary")
                .select(
                    "pack_cost,mean_value,median_value,min_value,max_value,std_dev,"
                    "total_ev,net_value,roi,roi_percent,prob_profit,prob_big_hit,big_hit_threshold,"
                    "expected_loss_when_losing,median_loss_when_losing,tail_value_p05,coefficient_of_variation"
                )
                .eq("calculation_run_id", run_id)
                .single()
                .execute()
            )
            summary = summary_result.data if summary_result and summary_result.data else {}
            if not summary:
                raise ExplorePageError(
                    status_code=500,
                    message="Failed to load required summary statistics",
                    code="SUMMARY_QUERY_FAILED",
                )
            sources["simulation_run_summary"] = "OK"
            sources["summary_source"] = "simulation_run_summary+simulation_derived_metrics"
        except ExplorePageError:
            raise
        except Exception as exc:
            logger.exception("[explore-page] simulation_run_summary required query failed run_id=%s", run_id)
            raise ExplorePageError(
                status_code=500,
                message="Failed to load required summary statistics",
                code="SUMMARY_QUERY_FAILED",
            ) from exc

        try:
            derived_result = (
                public_read_client.table("simulation_derived_metrics")
                .select("*")
                .eq("calculation_run_id", run_id)
                .single()
                .execute()
            )
            derived_metrics = derived_result.data if derived_result and derived_result.data else {}
            if not derived_metrics:
                raise ExplorePageError(
                    status_code=500,
                    message="Failed to load required derived metrics",
                    code="DERIVED_QUERY_FAILED",
                )
            summary.update(derived_metrics)
            sources["simulation_derived_metrics"] = "OK"
        except ExplorePageError:
            raise
        except Exception as exc:
            logger.exception("[explore-page] simulation_derived_metrics required query failed run_id=%s", run_id)
            raise ExplorePageError(
                status_code=500,
                message="Failed to load required derived metrics",
                code="DERIVED_QUERY_FAILED",
            ) from exc

    summary_ms = (time.perf_counter() - summary_started) * 1000

    # Rankings (optional)
    rankings_started = time.perf_counter()
    rankings: List[Dict[str, Any]] = []
    try:
        rankings_result = (
            public_read_client.table("simulation_pull_summary")
            .select("rarity_bucket,pulled_count,avg_sampled_value,total_sampled_value")
            .eq("calculation_run_id", run_id)
            .order("rarity_bucket", desc=False)
            .execute()
        )
        rankings = rankings_result.data if rankings_result.data else []
        sources["simulation_pull_summary"] = "OK"
    except Exception as exc:
        logger.warning("[explore-page] simulation_pull_summary failed run_id=%s: %s", run_id, exc)
        warnings.append("Failed to load rarity rankings")
        sources["simulation_pull_summary"] = "FAILED"
    rankings_ms = (time.perf_counter() - rankings_started) * 1000

    # RIP statistics (optional)
    rip_started = time.perf_counter()
    rip_statistics: Dict[str, Any] = {"pack_paths": {}, "normal_pack_states": {}}
    try:
        rip_result = (
            public_read_client.table("simulation_state_counts")
            .select("state_group,state_name,occurrence_count")
            .eq("calculation_run_id", run_id)
            .execute()
        )
        for row in (rip_result.data or []):
            group = row.get("state_group", "")
            name = row.get("state_name", "")
            count = row.get("occurrence_count", 0)
            if group == "pack_path":
                rip_statistics["pack_paths"][name] = count
            elif group == "normal_pack_state":
                rip_statistics["normal_pack_states"][name] = count
        sources["simulation_state_counts"] = "OK"
    except Exception as exc:
        logger.warning("[explore-page] simulation_state_counts failed run_id=%s: %s", run_id, exc)
        warnings.append("Failed to load RIP statistics")
        sources["simulation_state_counts"] = "FAILED"
    rip_ms = (time.perf_counter() - rip_started) * 1000

    # Percentiles (optional)
    percentiles_started = time.perf_counter()
    percentiles: List[Dict[str, Any]] = []
    try:
        percentiles_result = (
            public_read_client.table("simulation_percentiles")
            .select("percentile,value")
            .eq("calculation_run_id", run_id)
            .order("percentile", desc=False)
            .execute()
        )
        percentiles = percentiles_result.data if percentiles_result.data else []
        sources["simulation_percentiles"] = "OK"
    except Exception as exc:
        logger.warning("[explore-page] simulation_percentiles failed run_id=%s: %s", run_id, exc)
        warnings.append("Failed to load percentiles")
        sources["simulation_percentiles"] = "FAILED"
    percentiles_ms = (time.perf_counter() - percentiles_started) * 1000

    _populate_p99_ratio_from_percentiles(summary, percentiles)
    opening_desirability: Optional[Dict[str, Any]] = None
    if requested_target_type == "set":
        try:
            opening_set_metadata = _fetch_set_metadata_for_target(requested_target_id)
            if opening_set_metadata:
                resolved_set_id = resolved_set_id or _to_optional_str(opening_set_metadata.get("id"))
                resolved_set_canonical_key = resolved_set_canonical_key or _to_optional_str(
                    opening_set_metadata.get("canonical_key")
                )
                sources["opening_desirability_set_metadata"] = "OK"
            else:
                sources["opening_desirability_set_metadata"] = "NO_ROW"
        except Exception as exc:
            logger.warning(
                "[explore-page] Opening Desirability set metadata lookup failed target_id=%s: %s",
                requested_target_id,
                exc,
            )
            sources["opening_desirability_set_metadata"] = "FAILED"

        _populate_biggest_upside_metrics_for_set(summary, requested_target_id, warnings, sources)
        _populate_relative_average_return_score_for_set(summary, requested_target_id, warnings, sources)
        _populate_desirability_drivers_for_set(summary, requested_target_id, warnings, sources)
        opening_desirability = _populate_opening_desirability_for_set(
            summary=summary,
            requested_target_id=requested_target_id,
            resolved_set_id=resolved_set_id,
            resolved_set_canonical_key=resolved_set_canonical_key,
            warnings=warnings,
            sources=sources,
        )
        if opening_desirability is not None:
            opening_desirability["topCollectorAppealDrivers"] = _build_public_top_collector_appeal_drivers(
                summary_cards=summary.get("top_collector_appeal_drivers"),
                raw_cards=summary.get("top_desirability_cards"),
            )
    _ensure_optional_summary_fields(summary)

    # Distribution bins (optional, separate query)
    distribution_started = time.perf_counter()
    distribution_bins: List[Dict[str, Any]] = []
    try:
        distribution_result = (
            public_read_client.table("simulation_value_distribution_bins")
            .select(
                "bin_floor,bin_ceiling,occurrence_count,probability,"
                "cumulative_probability,survival_probability"
            )
            .eq("calculation_run_id", run_id)
            .order("bin_floor", desc=False)
            .limit(clamped_distribution_bins_limit)
            .execute()
        )
        distribution_bins = distribution_result.data if distribution_result.data else []
        sources["simulation_value_distribution_bins"] = "OK"
    except Exception as exc:
        logger.warning("[explore-page] simulation_value_distribution_bins failed run_id=%s: %s", run_id, exc)
        warnings.append("Failed to load distribution bins")
        sources["simulation_value_distribution_bins"] = "FAILED"
    distribution_ms = (time.perf_counter() - distribution_started) * 1000

    # Threshold bins (optional, separate query)
    threshold_started = time.perf_counter()
    threshold_bins: List[Dict[str, Any]] = []
    try:
        threshold_result = (
            public_read_client.table("simulation_value_threshold_bins")
            .select(
                "threshold_floor,threshold_ceiling,occurrence_count,probability,"
                "cumulative_probability,survival_probability,bucket_label,bucket_order"
            )
            .eq("calculation_run_id", run_id)
            .order("bucket_order", desc=False)
            .execute()
        )
        threshold_bins = threshold_result.data if threshold_result.data else []
        sources["simulation_value_threshold_bins"] = "OK"
    except Exception as exc:
        logger.warning("[explore-page] simulation_value_threshold_bins failed run_id=%s: %s", run_id, exc)
        warnings.append("Failed to load threshold bins")
        sources["simulation_value_threshold_bins"] = "FAILED"
    threshold_ms = (time.perf_counter() - threshold_started) * 1000

    # Top hits (optional)
    top_hits_started = time.perf_counter()
    top_hits: List[Dict[str, Any]] = []
    try:
        top_hits_result = (
            public_read_client.table("simulation_input_cards_with_near_mint_price")
            .select("card_id,card_variant_id,card_name,rarity_bucket,ev_contribution,current_near_mint_price")
            .eq("calculation_run_id", run_id)
            .order("ev_contribution", desc=True)
            .limit(clamped_top_hits_limit)
            .execute()
        )
        raw_hits = top_hits_result.data if top_hits_result.data else []
        top_hits = _enrich_top_hits_with_images(raw_hits)
        sources["simulation_input_cards"] = "OK" if top_hits else "NO_ROWS"
        if not top_hits:
            warnings.append(
                "Simulation Drivers unavailable: simulation_input_cards_with_near_mint_price "
                f"returned no rows for calculation_run_id={run_id}"
            )
    except Exception as exc:
        logger.warning("[explore-page] simulation_input_cards failed run_id=%s: %s", run_id, exc)
        warnings.append(
            "Failed to load top hits from simulation_input_cards_with_near_mint_price "
            f"for calculation_run_id={run_id}: {exc}"
        )
        sources["simulation_input_cards"] = "FAILED"
    top_hits_ms = (time.perf_counter() - top_hits_started) * 1000

    # Historical trend (optional)
    history_started = time.perf_counter()
    history_trend: List[Dict[str, Any]] = []
    try:
        history_rows, history_source = _load_history_trend_rows(
            requested_target_type=requested_target_type,
            requested_target_id=requested_target_id,
            history_trend_limit=history_trend_limit,
        )
        history_trend = history_rows
        sources["calculation_history_trend"] = history_source
    except Exception as exc:
        logger.warning(
            "[explore-page] calculation_history_trend failed target_type=%s target_id=%s: %s",
            requested_target_type,
            requested_target_id,
            exc,
        )
        warnings.append("Failed to load historical trend")
        sources["calculation_history_trend"] = "FAILED"
    history_ms = (time.perf_counter() - history_started) * 1000

    total_ms = (time.perf_counter() - total_started) * 1000

    interpretation = _strip_public_weight_metadata(
        build_rip_interpretation(
            {
                "summary": summary,
                "rankings": rankings,
                "rip_statistics": rip_statistics,
                "percentiles": percentiles,
                "distribution_bins": distribution_bins,
                "threshold_bins": threshold_bins,
                "top_hits": top_hits,
                "history_trend": history_trend,
            }
        )
    )

    pull_rate_assumptions = None
    if requested_target_type == "set":
        config_class, _ = _resolve_set_config_for_explore_target(
            requested_target_id,
            summary,
            warnings,
            sources,
        )
        if config_class is not None:
            pull_rate_assumptions = _build_pull_rate_assumptions(
                config_class=config_class,
                run_id=run_id,
                warnings=warnings,
                sources=sources,
            )
        else:
            sources["pull_rate_assumptions"] = "SET_CONFIG_NOT_FOUND"

    return {
        "summary": summary,
        "rankings": rankings,
        "rip_statistics": rip_statistics,
        "percentiles": percentiles,
        "distribution_bins": distribution_bins,
        "threshold_bins": threshold_bins,
        "top_hits": top_hits,
        "history_trend": history_trend,
        "interpretation": interpretation,
        "openingDesirability": opening_desirability,
        "pull_rate_assumptions": pull_rate_assumptions,
        "meta": {
            "request": {
                "target_type": requested_target_type,
                "target_id": requested_target_id,
                "limit_distribution_bins": clamped_distribution_bins_limit,
                "limit_top_hits": clamped_top_hits_limit,
                "limit_history_trend": history_trend_limit,
            },
            "sources": sources,
            "warnings": warnings,
            "timings": {
                "summary_ms": round(summary_ms, 2),
                "rankings_ms": round(rankings_ms, 2),
                "rip_statistics_ms": round(rip_ms, 2),
                "percentiles_ms": round(percentiles_ms, 2),
                "distribution_bins_ms": round(distribution_ms, 2),
                "threshold_bins_ms": round(threshold_ms, 2),
                "top_hits_ms": round(top_hits_ms, 2),
                "history_trend_ms": round(history_ms, 2),
                "total_backend_ms": round(total_ms, 2),
            },
        },
    }
