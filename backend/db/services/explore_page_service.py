"""Service for aggregating Explore page simulation data."""

from __future__ import annotations

import difflib
import logging
import math
import re
import time
from typing import Any, Callable, Dict, List, Mapping, Optional, Sequence, Tuple

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
    from backend.constants.tcg.pokemon.swordAndShieldEra.setMap import (
        SET_ALIAS_MAP as swsh_alias_map,
        SET_CONFIG_MAP as swsh_config_map,
    )

    config_map = {
        **sv_config_map,
        **swsh_config_map,
        **mega_config_map,
    }
    alias_map = {
        **sv_alias_map,
        **swsh_alias_map,
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

    set_result = (
        public_read_client.table("sets")
        .select(selected_columns)
        .eq("id", target_id)
        .limit(1)
        .execute()
    )
    set_row = _first_row(set_result)
    if set_row:
        return set_row

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


def _enrich_slot_schema_classification_rows(
    *,
    cards_rows: List[Dict[str, Any]],
    run_id: str,
    warnings: List[str],
) -> List[Dict[str, Any]]:
    """Attach card/variant metadata needed by slot-schema pool filters at read time."""
    if not cards_rows:
        return []

    enriched_rows = [dict(row) for row in cards_rows]
    variant_ids = sorted(
        {
            _normalize_key(row.get("card_variant_id"))
            for row in cards_rows
            if _normalize_key(row.get("card_variant_id"))
        }
    )
    card_ids = sorted(
        {
            _normalize_key(row.get("card_id"))
            for row in cards_rows
            if _normalize_key(row.get("card_id"))
        }
    )

    variant_lookup: Dict[str, Dict[str, Any]] = {}
    card_lookup: Dict[str, Dict[str, Any]] = {}

    if variant_ids:
        try:
            variant_result = (
                public_read_client.table("card_variants")
                .select("id,card_id,printing_type,special_type,edition")
                .in_("id", variant_ids)
                .execute()
            )
            variant_lookup = {
                _normalize_key(row.get("id")): row
                for row in (variant_result.data or [])
                if _normalize_key(row.get("id"))
            }
        except Exception as exc:
            logger.warning(
                "[explore-page] card_variants enrichment failed for pull-rate assumptions run_id=%s: %s",
                run_id,
                exc,
            )
            warnings.append(
                "Failed to load card variant metadata for slot-schema bucket classification"
            )

    derived_card_ids = {
        _normalize_key(row.get("card_id"))
        for row in variant_lookup.values()
        if _normalize_key(row.get("card_id"))
    }
    all_card_ids = sorted(set(card_ids) | derived_card_ids)
    if all_card_ids:
        try:
            card_result = (
                public_read_client.table("cards")
                .select("id,name,rarity,card_number")
                .in_("id", all_card_ids)
                .execute()
            )
            card_lookup = {
                _normalize_key(row.get("id")): row
                for row in (card_result.data or [])
                if _normalize_key(row.get("id"))
            }
        except Exception as exc:
            logger.warning(
                "[explore-page] cards enrichment failed for pull-rate assumptions run_id=%s: %s",
                run_id,
                exc,
            )
            warnings.append(
                "Failed to load card metadata for slot-schema bucket classification"
            )

    for row in enriched_rows:
        variant_id = _normalize_key(row.get("card_variant_id"))
        card_id = _normalize_key(row.get("card_id"))
        variant_row = variant_lookup.get(variant_id) if variant_id else None
        variant_card_id = _normalize_key((variant_row or {}).get("card_id"))

        if not card_id and variant_card_id:
            row["card_id"] = variant_card_id
            card_id = variant_card_id

        card_row = card_lookup.get(card_id) if card_id else None
        if card_row:
            if row.get("card_number") in (None, ""):
                row["card_number"] = card_row.get("card_number")
            if row.get("rarity") in (None, ""):
                row["rarity"] = card_row.get("rarity")
            if row.get("card_name") in (None, ""):
                row["card_name"] = card_row.get("name")
            if row.get("name") in (None, ""):
                row["name"] = card_row.get("name")

        if variant_row:
            if row.get("printing_type") in (None, ""):
                row["printing_type"] = variant_row.get("printing_type")
            if row.get("special_type") in (None, ""):
                row["special_type"] = variant_row.get("special_type")
            if row.get("edition") in (None, ""):
                row["edition"] = variant_row.get("edition")

    return enriched_rows


def _has_minimum_slot_schema_classification_columns(cards_rows: List[Dict[str, Any]]) -> bool:
    if not cards_rows:
        return False

    available_columns: set[str] = set()
    for row in cards_rows:
        available_columns.update(row.keys())

    has_name_column = "name" in available_columns or "card_name" in available_columns
    required_columns = {"card_number", "rarity", "printing_type"}
    return has_name_column and required_columns.issubset(available_columns)


_SLOT_SCHEMA_COLUMN_ALIASES = {
    "rarity": ("rarity", "Rarity", "rarity_raw"),
    "printing_type": ("printing_type", "Printing Type", "printing_type_key"),
    "card_number": ("card_number", "Card Number"),
    "name": ("name", "Card Name", "card_name"),
}


def _resolve_slot_schema_row_value(row: Mapping[str, Any], key: str) -> Any:
    for candidate in _SLOT_SCHEMA_COLUMN_ALIASES.get(key, (key,)):
        if candidate in row:
            return row.get(candidate)
    return None


def _normalize_slot_schema_text(value: Any) -> str:
    return str(value or "").strip().lower()


def _coerce_slot_schema_card_number(value: Any) -> Optional[int]:
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        if value != value:
            return None
        return int(value)

    text = str(value).strip()
    if not text:
        return None
    match = re.match(r"^(\d+)", text)
    if not match:
        return None
    return int(match.group(1))


def _parse_slot_schema_card_number_range(raw: Any) -> tuple[int, int]:
    if isinstance(raw, str):
        pieces = [piece.strip() for piece in raw.split("-", 1)]
        if len(pieces) != 2 or not pieces[0].isdigit() or not pieces[1].isdigit():
            raise ValueError(f"card_number_range must be 'min-max' (numeric). Received {raw!r}.")
        start = int(pieces[0])
        end = int(pieces[1])
    elif isinstance(raw, (tuple, list)) and len(raw) == 2:
        start = int(raw[0])
        end = int(raw[1])
    else:
        raise ValueError(
            f"card_number_range must be 'min-max' or [min, max]. Received {raw!r}."
        )

    if start > end:
        raise ValueError(f"card_number_range min cannot be greater than max: {raw!r}.")
    return start, end


def _matches_slot_schema_name_filter(name_text: str, operator: str, value: Any) -> bool:
    if operator == "name_contains":
        return str(value).lower() in name_text

    if operator == "name_not_contains":
        return str(value).lower() not in name_text

    if operator == "name_contains_all":
        if not isinstance(value, (list, tuple)) or not value:
            raise ValueError("name_contains_all must be a non-empty list of substrings.")
        return all(str(item).lower() in name_text for item in value)

    if operator == "name_pattern":
        pattern_text = str(value).strip()
        match = re.fullmatch(r"endswith\((['\"])(.*)\1\)", pattern_text)
        if not match:
            raise ValueError(
                "name_pattern currently supports only endswith('...') syntax. "
                f"Received {pattern_text!r}."
            )
        return name_text.endswith(match.group(2).lower())

    raise ValueError(f"Unknown name filter operator: {operator!r}.")


def _row_matches_slot_schema_filters(row: Mapping[str, Any], filters: Mapping[str, Any]) -> bool:
    for key, expected in filters.items():
        if key == "card_number_range":
            start, end = _parse_slot_schema_card_number_range(expected)
            number = _coerce_slot_schema_card_number(_resolve_slot_schema_row_value(row, "card_number"))
            if number is None or number < start or number > end:
                return False
            continue

        if key == "card_number_min":
            number = _coerce_slot_schema_card_number(_resolve_slot_schema_row_value(row, "card_number"))
            if number is None or number < int(expected):
                return False
            continue

        if key == "card_number_max":
            number = _coerce_slot_schema_card_number(_resolve_slot_schema_row_value(row, "card_number"))
            if number is None or number > int(expected):
                return False
            continue

        if key in {"name_contains", "name_not_contains", "name_contains_all", "name_pattern"}:
            name_text = _normalize_slot_schema_text(_resolve_slot_schema_row_value(row, "name"))
            if not _matches_slot_schema_name_filter(name_text, key, expected):
                return False
            continue

        actual = _resolve_slot_schema_row_value(row, key)
        if _normalize_slot_schema_text(actual) != _normalize_slot_schema_text(expected):
            return False

    return True


def _classify_slot_schema_bucket_card_ids_native(
    *,
    config_class: Any,
    classification_rows: List[Dict[str, Any]],
    row_identifier: Callable[[Mapping[str, Any]], Optional[str]],
) -> Dict[str, set[str]]:
    mapping = getattr(config_class, "SLOT_SCHEMA_OUTCOME_POOL_MAPPING", {}) or {}
    if not isinstance(mapping, Mapping) or not mapping:
        return {}

    classified: Dict[str, set[str]] = {}
    for outcome_key, details in mapping.items():
        if not isinstance(details, Mapping):
            raise ValueError(f"Invalid mapping payload for outcome {outcome_key!r}: expected mapping.")

        card_filter = details.get("card_filter", {}) or {}
        variant_filter = details.get("variant_filter", {}) or {}
        include_reverse_variants = bool(details.get("include_reverse_variants", True))

        if not isinstance(card_filter, Mapping):
            raise ValueError(f"{outcome_key!r}.card_filter must be a mapping.")
        if not isinstance(variant_filter, Mapping):
            raise ValueError(f"{outcome_key!r}.variant_filter must be a mapping.")

        identifiers: set[str] = set()
        for row in classification_rows:
            if not include_reverse_variants:
                printing_type = _normalize_slot_schema_text(_resolve_slot_schema_row_value(row, "printing_type"))
                if printing_type == "reverse-holo":
                    continue

            if not _row_matches_slot_schema_filters(row, card_filter):
                continue
            if not _row_matches_slot_schema_filters(row, variant_filter):
                continue

            identifier = row_identifier(row)
            if identifier:
                identifiers.add(identifier)

        normalized_outcome = _normalize_rarity(outcome_key)
        if normalized_outcome and identifiers:
            classified[normalized_outcome] = identifiers

    return classified


def _resolve_slot_schema_classification(
    *,
    config_class: Any,
    classification_rows: List[Dict[str, Any]],
    row_identifier: Callable[[Mapping[str, Any]], Optional[str]],
    run_id: str,
) -> Dict[str, set[str]]:
    try:
        import pandas as pd

        from backend.simulations.slotSchemaOutcomeResolver import apply_slot_schema_outcome_pool_mapping

        cards_df = pd.DataFrame(classification_rows)
        resolved_outcome_pools = apply_slot_schema_outcome_pool_mapping(
            config_class,
            cards_df,
            allow_empty_pools=True,
        )

        classified: Dict[str, set[str]] = {}
        for outcome_key, pool_df in resolved_outcome_pools.items():
            normalized_outcome = _normalize_rarity(outcome_key)
            if not normalized_outcome:
                continue

            outcome_identifiers = {
                identifier
                for row in pool_df.to_dict(orient="records")
                for identifier in [row_identifier(row)]
                if identifier
            }
            if outcome_identifiers:
                classified[normalized_outcome] = outcome_identifiers

        return classified
    except ModuleNotFoundError as exc:
        if _normalize_key(getattr(exc, "name", "")) != "pandas":
            raise
        logger.warning(
            "[explore-page] pandas unavailable for slot_schema classification run_id=%s; using native fallback",
            run_id,
        )
        return _classify_slot_schema_bucket_card_ids_native(
            config_class=config_class,
            classification_rows=classification_rows,
            row_identifier=row_identifier,
        )


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


_MODELED_SWSH_SET_IDS = {
    "swsh1",
    "swsh2",
    "swsh3",
    "swsh5",
    "swsh6",
    "swsh7",
    "swsh9",
    "swsh11",
    "swsh12",
}

# Keep regular SWSH display aligned with the proven swsh6/swsh7 pattern.
# NOTE: swsh10 (Astral Radiance) is intentionally excluded here pending a
# dedicated Trainer Gallery / reverse-slot audit.
_MODELED_SWSH_SINGLE_BUCKET_DISPLAY_SET_IDS = set(_MODELED_SWSH_SET_IDS)

SOURCE_STATUS_DIRECT = "SOURCE_DIRECT"
SOURCE_STATUS_DERIVED_RESIDUAL = "SOURCE_DERIVED_RESIDUAL"
SOURCE_STATUS_PROVISIONAL = "PROVISIONAL_DIRECTIONAL"
SOURCE_STATUS_UNSUPPORTED_SPLIT = "UNSUPPORTED_SPLIT"
SOURCE_STATUS_MISSING = "MISSING_SOURCE"
SOURCE_STATUS_SECONDARY_INDEX_ONLY = "SECONDARY_INDEX_ONLY"
SOURCE_STATUS_INFERRED_MODEL = "INFERRED_MODEL"

_SWSH6_UNSUPPORTED_REFERENCE_BUCKETS = {
    "rainbow trainer",
    "rainbow vmax",
    "gold secret rare",
}

_SWSH7_UNSUPPORTED_REFERENCE_BUCKETS = {
    "full art v",
    "full art trainer",
    "rainbow trainer",
    "rainbow vmax",
    "gold secret rare",
}

_MODELED_OUTCOME_LABELS = {
    "rare": "Baseline",
    "holo rare": "Holo Rare Bucket",
    "regular v": "Regular V Bucket",
    "regular vmax": "Regular VMAX Bucket",
    "full art v": "Full Art V Bucket",
    "full art trainer": "Full Art Trainer Bucket",
    "alternate art v": "Alternate Art V Bucket",
    "alternate art vmax": "Alternate Art VMAX Bucket",
    "rainbow trainer": "Rainbow Trainer Bucket",
    "rainbow vmax": "Rainbow VMAX Bucket",
    "gold secret rare": "Gold Secret Rare Bucket",
}


def _is_modeled_swsh_slot_schema_set(config_class: Any) -> bool:
    if config_class is None:
        return False

    set_id = _normalize_key(getattr(config_class, "SET_ID", ""))
    simulation_engine = _normalize_key(getattr(config_class, "SIMULATION_ENGINE", ""))
    return (
        set_id in _MODELED_SWSH_SET_IDS
        and simulation_engine == "slot_schema"
        and bool(getattr(config_class, "SLOT_SCHEMA_RUNTIME_ENABLED", False))
    )


def _supports_modeled_swsh_combo_pack_breakdown(config_class: Any) -> bool:
    set_id = _normalize_key(getattr(config_class, "SET_ID", ""))
    return set_id not in _MODELED_SWSH_SINGLE_BUCKET_DISPLAY_SET_IDS


def _format_modeled_outcome_label(rarity_key: str) -> str:
    normalized = _normalize_rarity(rarity_key)
    label = _MODELED_OUTCOME_LABELS.get(normalized)
    if label:
        return label
    return " ".join(part.capitalize() for part in normalized.split())


def _modeled_swsh_unsupported_reference_buckets(config_class: Any) -> set[str]:
    set_id = _normalize_key(getattr(config_class, "SET_ID", ""))
    if set_id == "swsh6":
        return set(_SWSH6_UNSUPPORTED_REFERENCE_BUCKETS)
    if set_id == "swsh7":
        return set(_SWSH7_UNSUPPORTED_REFERENCE_BUCKETS)
    return set()


def _build_modeled_swsh_bucket_integrity(
    *,
    configured_outcome_keys: Sequence[str],
    persisted_bucket_keys: Sequence[str],
    displayed_bucket_count: int,
    config_class: Any,
) -> Dict[str, Any]:
    configured_set = {key for key in configured_outcome_keys if key}
    persisted_set = {key for key in persisted_bucket_keys if key}
    unsupported_set = _modeled_swsh_unsupported_reference_buckets(config_class)

    unsupported_persisted = sorted(persisted_set.intersection(unsupported_set))
    unknown_persisted = sorted(persisted_set - configured_set - unsupported_set)
    missing_configured = sorted(configured_set - persisted_set)

    status = "ok"
    message: Optional[str] = None
    if unknown_persisted or missing_configured:
        status = "warning"
        parts: List[str] = []
        if unknown_persisted:
            parts.append("Persisted pull-summary includes unknown bucket labels")
        if missing_configured:
            parts.append("Configured modeled buckets are missing from persisted pull-summary")
        message = "; ".join(parts) + "."

    return {
        "status": status,
        "unknown_persisted_buckets": unknown_persisted,
        "missing_configured_buckets": missing_configured,
        "unsupported_persisted_buckets": unsupported_persisted,
        "configured_bucket_count": len(configured_set),
        "persisted_bucket_count": len(persisted_set),
        "displayed_bucket_count": int(displayed_bucket_count),
        "message": message,
    }


def _parse_slot_schema_combo_state_name(state_name: Any) -> Optional[Dict[str, str]]:
    raw = str(state_name or "").strip().lower()
    if not raw:
        return None

    parts = [part.strip() for part in raw.split("|") if part.strip()]
    reverse_bucket = None
    rare_bucket = None
    for part in parts:
        if part.startswith("reverse:"):
            reverse_bucket = _normalize_rarity(part.split(":", 1)[1])
        elif part.startswith("rare:"):
            rare_bucket = _normalize_rarity(part.split(":", 1)[1])

    if not reverse_bucket or not rare_bucket:
        return None

    return {
        "reverse_bucket": reverse_bucket,
        "rare_bucket": rare_bucket,
    }


def _format_combo_bucket_label(bucket: str) -> str:
    normalized = _normalize_rarity(bucket)
    if normalized == "regular reverse":
        return "Regular Reverse"
    return _format_modeled_outcome_label(normalized)


def _is_reverse_slot_hit(bucket: str) -> bool:
    normalized = _normalize_rarity(bucket)
    return normalized not in {"", "unknown", "regular reverse"}


def _is_rare_slot_hit(bucket: str) -> bool:
    normalized = _normalize_rarity(bucket)
    return normalized not in {"", "unknown", "rare"}


def _build_modeled_swsh_pack_breakdown_display(
    *,
    config_class: Any,
    rankings: List[Dict[str, Any]],
    rip_statistics: Dict[str, Any],
) -> Optional[Dict[str, Any]]:
    if not _is_modeled_swsh_slot_schema_set(config_class):
        return None

    rare_slot_probability = getattr(config_class, "RARE_SLOT_PROBABILITY", {}) or {}
    if not isinstance(rare_slot_probability, Mapping) or not rare_slot_probability:
        return None

    outcome_keys: List[str] = []
    for raw_key, raw_probability in rare_slot_probability.items():
        normalized_key = _normalize_rarity(raw_key)
        if not normalized_key or _to_positive_probability(raw_probability) is None:
            continue
        if normalized_key not in outcome_keys:
            outcome_keys.append(normalized_key)

    ranking_counts = {
        _normalize_rarity(row.get("rarity_bucket")): int(row.get("pulled_count") or 0)
        for row in (rankings or [])
        if _normalize_rarity(row.get("rarity_bucket"))
    }
    persisted_bucket_keys = sorted(ranking_counts.keys())

    bucket_integrity = _build_modeled_swsh_bucket_integrity(
        configured_outcome_keys=outcome_keys,
        persisted_bucket_keys=persisted_bucket_keys,
        displayed_bucket_count=0,
        config_class=config_class,
    )

    if _supports_modeled_swsh_combo_pack_breakdown(config_class):
        combo_state_counts_raw = (rip_statistics or {}).get("slot_schema_combo_states") or {}
        combo_rows: List[Dict[str, Any]] = []
        if isinstance(combo_state_counts_raw, Mapping):
            for state_key, raw_count in combo_state_counts_raw.items():
                parsed = _parse_slot_schema_combo_state_name(state_key)
                if not parsed:
                    continue
                count = int(raw_count or 0)
                if count <= 0:
                    continue

                reverse_bucket = parsed["reverse_bucket"]
                rare_bucket = parsed["rare_bucket"]
                has_reverse_hit = _is_reverse_slot_hit(reverse_bucket)
                has_rare_hit = _is_rare_slot_hit(rare_bucket)
                combo_rows.append(
                    {
                        "key": f"reverse:{reverse_bucket}|rare:{rare_bucket}",
                        "label": f"{_format_combo_bucket_label(reverse_bucket)} + {_format_combo_bucket_label(rare_bucket)}",
                        "count": count,
                        "reverse_bucket": reverse_bucket,
                        "rare_bucket": rare_bucket,
                        "has_reverse_hit": has_reverse_hit,
                        "has_rare_hit": has_rare_hit,
                        "has_double_hit": bool(has_reverse_hit and has_rare_hit),
                    }
                )

        combo_total_count = sum(int(row["count"]) for row in combo_rows)
        if combo_total_count > 0:
            for row in combo_rows:
                row["share"] = float(row["count"] / combo_total_count)
            combo_rows.sort(key=lambda row: row["count"], reverse=True)
            dominant_row = combo_rows[0]
            bucket_integrity["displayed_bucket_count"] = len(combo_rows)
            return {
                "mode": "modeled_outcome_states",
                "supported": True,
                "combo_states_supported": True,
                "state_granularity": "reverse_rare_combo",
                "source": "simulation_state_counts",
                "title": "Modeled outcome states",
                "description": (
                    "Persisted reverse-slot + rare-slot combo states show simulator co-occurrence outcomes at pack level."
                ),
                "disclaimer": (
                    "These states reflect the simulator's slot-based assumptions, not official Pokemon collation guarantees."
                ),
                "limitation_note": (
                    "Combo states are simulator outcome co-occurrence rows persisted from slot-schema packs; they are not"
                    " official Pokemon pull guarantees."
                ),
                "bucket_integrity": bucket_integrity,
                "rows": combo_rows,
                "dominant_key": dominant_row["key"],
                "dominant_label": dominant_row["label"],
                "dominant_share": dominant_row["share"],
            }

    rows: List[Dict[str, Any]] = []
    total_count = 0
    for outcome_key in outcome_keys:
        count = ranking_counts.get(outcome_key)
        if count is None:
            continue
        total_count += count
        rows.append(
            {
                "key": outcome_key,
                "label": _format_modeled_outcome_label(outcome_key),
                "count": count,
            }
        )

    if total_count > 0:
        for row in rows:
            row["share"] = float(row["count"] / total_count)
        rows.sort(key=lambda row: row["count"], reverse=True)
        dominant_row = rows[0]
        bucket_integrity["displayed_bucket_count"] = len(rows)
        return {
            "mode": "modeled_outcome_states",
            "supported": True,
            "combo_states_supported": False,
            "state_granularity": "single_bucket_aggregate",
            "source": "simulation_pull_summary",
            "title": "Modeled outcome states",
            "description": (
                "Modeled outcome buckets show how often each value-bearing bucket was selected by the simulator"
                " under the current slot-based assumptions."
            ),
            "disclaimer": (
                "These states reflect the simulator's slot-based assumptions, not official Pokemon collation guarantees."
            ),
            "limitation_note": (
                "Persisted output currently stores single-bucket aggregates (simulation_pull_summary) and coarse pack/state"
                " counts (simulation_state_counts). Reverse-slot + rare-slot combo co-occurrence is not persisted."
            ),
            "bucket_integrity": bucket_integrity,
            "rows": rows,
            "dominant_key": dominant_row["key"],
            "dominant_label": dominant_row["label"],
            "dominant_share": dominant_row["share"],
        }

    normal_state_counts = (rip_statistics or {}).get("normal_pack_states") or {}
    if isinstance(normal_state_counts, Mapping) and normal_state_counts:
        fallback_source = "simulation_state_counts"
    else:
        fallback_source = "slot_schema_config"

    return {
        "mode": "modeled_outcome_states",
        "supported": False,
        "combo_states_supported": False,
        "state_granularity": "single_bucket_aggregate",
        "source": fallback_source,
        "title": "Modeled outcome states",
        "description": (
            "Modeled outcome states show which value-bearing bucket the simulator selected for a pack."
        ),
        "disclaimer": (
            "These states reflect the simulator's slot-based assumptions, not official Pokemon collation guarantees."
        ),
        "bucket_integrity": bucket_integrity,
        "rows": [],
        "fallback_message": (
            "Modeled rare-slot outcomes are available, but full outcome-state counts require a future simulation-output enhancement."
        ),
    }


def _format_probability_odds_display(probability: Any) -> Optional[str]:
    parsed = _to_positive_probability(probability)
    if parsed is None:
        return None
    denominator = 1 / parsed
    rounded = round(denominator)
    if abs(denominator - rounded) <= 1e-9:
        return f"1/{rounded:,}"
    if denominator < 10:
        return f"1/{denominator:.2f}"
    return f"1/{denominator:.1f}"


def _build_swsh6_pull_rate_references(config_class: Any) -> Dict[str, Any]:
    runtime_table = getattr(config_class, "RARE_SLOT_PROBABILITY", {}) or {}
    draft_audit = getattr(config_class, "CHILLING_REIGN_RARE_SLOT_PROBABILITY_DRAFT_AUDIT", {}) or {}
    source_notes = getattr(config_class, "CHILLING_REIGN_PULL_RATE_SOURCE_NOTES", {}) or {}
    source_links = getattr(config_class, "CHILLING_REIGN_PULL_RATE_SOURCE_LINKS", {}) or {}
    confidence = getattr(config_class, "SLOT_SCHEMA_SOURCE_CONFIDENCE", {}) or {}

    direct_rows = draft_audit.get("source_rows_used", {}) or {}
    provisional_rows = draft_audit.get("source_rows_used_with_assumptions", {}) or {}
    missing_rows = {
        _normalize_rarity(key): str(value)
        for key, value in (draft_audit.get("missing_source_rows", {}) or {}).items()
    }
    unsupported_rows = {
        _normalize_rarity(key)
        for key in (draft_audit.get("unsupported_split_rows", {}) or {}).keys()
    } | _SWSH6_UNSUPPORTED_REFERENCE_BUCKETS

    direct_by_bucket: Dict[str, Dict[str, Any]] = {}
    for source_bucket_label, payload in direct_rows.items():
        if not isinstance(payload, Mapping):
            continue
        normalized_bucket = _normalize_rarity(payload.get("normalized_bucket"))
        if not normalized_bucket:
            continue
        direct_by_bucket[normalized_bucket] = {
            "source_bucket_label": source_bucket_label,
            "source_id": "charizardx_user_rows",
            "source_odds": payload.get("source_odds"),
        }

    provisional_by_bucket: Dict[str, Dict[str, Any]] = {}
    for source_bucket_label, payload in provisional_rows.items():
        if not isinstance(payload, Mapping):
            continue
        normalized_bucket = _normalize_rarity(payload.get("normalized_bucket"))
        if not normalized_bucket:
            continue
        row_key = _normalize_key(source_bucket_label)
        source_id = _to_optional_str(payload.get("source_id")) or "secondary_directional"
        if source_id == "secondary_directional" and "dripshop" in row_key:
            source_id = "dripshop_directional"
        elif source_id == "secondary_directional" and "reddit" in row_key:
            source_id = "reddit_directional"
        provisional_by_bucket[normalized_bucket] = {
            "source_bucket_label": source_bucket_label,
            "source_id": source_id,
            "source_odds": payload.get("source_odds"),
            "caveat": payload.get("assumption"),
        }

    bucket_evidence: List[Dict[str, Any]] = []
    runtime_keys = {_normalize_rarity(key) for key in runtime_table.keys()}
    for raw_bucket, probability_used in runtime_table.items():
        normalized_bucket = _normalize_rarity(raw_bucket)
        status = SOURCE_STATUS_INFERRED_MODEL
        source_ids: List[str] = []
        source_bucket_label: Optional[str] = None
        odds_display = _format_probability_odds_display(probability_used)
        caveat: Optional[str] = None

        if normalized_bucket in direct_by_bucket:
            status = SOURCE_STATUS_DIRECT
            row = direct_by_bucket[normalized_bucket]
            source_ids = [row["source_id"]]
            source_bucket_label = row.get("source_bucket_label")
            odds_display = row.get("source_odds") or odds_display
        elif normalized_bucket in provisional_by_bucket:
            status = SOURCE_STATUS_PROVISIONAL
            row = provisional_by_bucket[normalized_bucket]
            source_ids = [row["source_id"]]
            source_bucket_label = row.get("source_bucket_label")
            odds_display = row.get("source_odds") or odds_display
            caveat = row.get("caveat")
        elif normalized_bucket == "rare":
            status = SOURCE_STATUS_DERIVED_RESIDUAL
            caveat = "Residual bucket derived from remaining modeled probability mass after non-rare buckets."
        elif missing_rows.get(normalized_bucket) == SOURCE_STATUS_MISSING:
            status = SOURCE_STATUS_MISSING

        bucket_evidence.append(
            {
                "source_bucket_label": source_bucket_label or normalized_bucket,
                "normalized_bucket": normalized_bucket,
                "probability_used": float(probability_used),
                "odds_display": odds_display,
                "source_status": status,
                "source_granularity_status": status,
                "used_in_runtime": True,
                "caveat": caveat,
                "source_ids": source_ids,
            }
        )

    for unsupported_bucket in sorted(unsupported_rows):
        if unsupported_bucket in runtime_keys:
            continue
        bucket_evidence.append(
            {
                "source_bucket_label": unsupported_bucket,
                "normalized_bucket": unsupported_bucket,
                "probability_used": None,
                "odds_display": None,
                "source_status": SOURCE_STATUS_UNSUPPORTED_SPLIT,
                "source_granularity_status": SOURCE_STATUS_UNSUPPORTED_SPLIT,
                "used_in_runtime": False,
                "caveat": "Unsupported child split bucket removed from runtime assumptions.",
                "source_ids": [],
            }
        )

    model_status = (
        draft_audit.get("probability_model_status")
        or draft_audit.get("status")
        or confidence.get("status")
        or "unknown"
    )
    model_confidence = "medium" if any(
        row.get("source_status") == SOURCE_STATUS_PROVISIONAL for row in bucket_evidence
    ) else "high"

    source_name = str(source_notes.get("source") or "User-provided CharizardX posting transcription")
    source_aliases = ", ".join(source_notes.get("source_aliases") or [])

    return {
        "model_status": model_status,
        "model_confidence": model_confidence,
        "caveats": [
            confidence.get("source_caveat"),
            draft_audit.get("decision"),
        ],
        "last_reviewed_at": None,
        "sources": [
            {
                "source_id": "charizardx_user_rows",
                "source_name": source_name,
                "source_url": _to_optional_str(source_links.get("charizardx_user_rows")),
                "source_type": "community_transcription",
                "source_confidence": "high",
                "discovered_via": source_aliases or None,
                "notes": "Direct source rows for swsh6 source-locked buckets. Previously labeled CharizardX/user-provided transcription.",
            },
            {
                "source_id": "swsh6_thepricedex_cross_reference_2026_06_holo",
                "source_name": "ThePriceDex Chilling Reign cross-reference",
                "source_url": _to_optional_str(source_links.get("swsh6_thepricedex_cross_reference_2026_06_holo")),
                "source_type": "secondary_index",
                "source_confidence": "medium_low",
                "discovered_via": None,
                "notes": "Secondary-index cross-reference used for provisional holo rare odds (non-direct).",
            },
            {
                "source_id": "dripshop_directional",
                "source_name": "DripShop directional estimate",
                "source_url": _to_optional_str(source_links.get("dripshop_directional")),
                "source_type": "secondary_directional",
                "source_confidence": "medium",
                "discovered_via": None,
                "notes": "Directional provisional estimate for holo rare.",
            },
            {
                "source_id": "reddit_directional",
                "source_name": "Reddit directional estimate",
                "source_url": _to_optional_str(source_links.get("reddit_directional")),
                "source_type": "secondary_directional",
                "source_confidence": "medium",
                "discovered_via": None,
                "notes": "Directional provisional estimate for regular v.",
            },
        ],
        "bucket_evidence": bucket_evidence,
    }


def _build_swsh7_pull_rate_references(config_class: Any) -> Dict[str, Any]:
    runtime_table = getattr(config_class, "RARE_SLOT_PROBABILITY", {}) or {}
    draft_audit = getattr(config_class, "EVOLVING_SKIES_RARE_SLOT_PROBABILITY_DRAFT_AUDIT", {}) or {}
    source_audit = getattr(config_class, "EVOLVING_SKIES_PULL_RATE_SOURCE_AUDIT", {}) or {}
    confidence = getattr(config_class, "SLOT_SCHEMA_SOURCE_CONFIDENCE", {}) or {}

    direct_rows = draft_audit.get("source_rows_used", {}) or {}
    provisional_rows = draft_audit.get("source_rows_used_with_assumptions", {}) or {}

    direct_by_bucket: Dict[str, Dict[str, Any]] = {}
    for source_bucket_label, payload in direct_rows.items():
        if not isinstance(payload, Mapping):
            continue
        normalized_bucket = _normalize_rarity(payload.get("normalized_bucket"))
        if not normalized_bucket:
            continue
        source_family = _normalize_key(payload.get("source_family")) or "tcgplayer_evolving_skies_8000_pack"
        direct_by_bucket[normalized_bucket] = {
            "source_bucket_label": source_bucket_label,
            "source_id": source_family,
            "source_odds": payload.get("source_odds"),
        }

    provisional_by_bucket: Dict[str, Dict[str, Any]] = {}
    for source_bucket_label, payload in provisional_rows.items():
        if not isinstance(payload, Mapping):
            continue
        normalized_bucket = _normalize_rarity(payload.get("normalized_bucket"))
        if not normalized_bucket:
            continue
        provisional_by_bucket[normalized_bucket] = {
            "source_bucket_label": source_bucket_label,
            "source_id": _to_optional_str(payload.get("source_id")) or "thepricedex_cross_reference",
            "source_odds": payload.get("source_odds"),
            "caveat": payload.get("assumption"),
        }

    source_families = source_audit.get("source_families", {}) or {}
    reddit_refs = (((source_families.get("reddit_pull_rate_discussions") or {}).get("references") or [None])[0])
    tcgplayer_refs = (((source_families.get("tcgplayer_evolving_skies_8000_pack") or {}).get("references") or [None])[0])
    thepricedex_refs = (((source_families.get("thepricedex_cross_reference") or {}).get("references") or [None])[0])

    bucket_evidence: List[Dict[str, Any]] = []
    runtime_keys = {_normalize_rarity(key) for key in runtime_table.keys()}
    for raw_bucket, probability_used in runtime_table.items():
        normalized_bucket = _normalize_rarity(raw_bucket)
        status = SOURCE_STATUS_INFERRED_MODEL
        source_ids: List[str] = []
        source_bucket_label: Optional[str] = None
        odds_display = _format_probability_odds_display(probability_used)
        caveat: Optional[str] = None

        if normalized_bucket in direct_by_bucket:
            status = SOURCE_STATUS_DIRECT
            row = direct_by_bucket[normalized_bucket]
            source_ids = [row["source_id"]]
            source_bucket_label = row.get("source_bucket_label")
            odds_display = row.get("source_odds") or odds_display
        elif normalized_bucket in provisional_by_bucket:
            status = SOURCE_STATUS_PROVISIONAL
            row = provisional_by_bucket[normalized_bucket]
            source_ids = [row["source_id"]]
            source_bucket_label = row.get("source_bucket_label")
            odds_display = row.get("source_odds") or odds_display
            caveat = row.get("caveat")
        elif normalized_bucket == "rare":
            status = SOURCE_STATUS_DERIVED_RESIDUAL
            caveat = "Residual bucket derived from remaining modeled probability mass after non-rare buckets."

        bucket_evidence.append(
            {
                "source_bucket_label": source_bucket_label or normalized_bucket,
                "normalized_bucket": normalized_bucket,
                "probability_used": float(probability_used),
                "odds_display": odds_display,
                "source_status": status,
                "source_granularity_status": status,
                "used_in_runtime": True,
                "caveat": caveat,
                "source_ids": source_ids,
            }
        )

    for unsupported_bucket in sorted(_SWSH7_UNSUPPORTED_REFERENCE_BUCKETS):
        if unsupported_bucket in runtime_keys:
            continue
        bucket_evidence.append(
            {
                "source_bucket_label": unsupported_bucket,
                "normalized_bucket": unsupported_bucket,
                "probability_used": None,
                "odds_display": None,
                "source_status": SOURCE_STATUS_UNSUPPORTED_SPLIT,
                "source_granularity_status": SOURCE_STATUS_UNSUPPORTED_SPLIT,
                "used_in_runtime": False,
                "caveat": "Unsupported child split bucket removed from runtime assumptions.",
                "source_ids": [],
            }
        )

    model_status = (
        draft_audit.get("probability_model_status")
        or draft_audit.get("status")
        or confidence.get("status")
        or "unknown"
    )
    model_confidence = "medium" if any(
        row.get("source_status") == SOURCE_STATUS_PROVISIONAL for row in bucket_evidence
    ) else "high"

    return {
        "model_status": model_status,
        "model_confidence": model_confidence,
        "caveats": [
            confidence.get("source_caveat"),
            draft_audit.get("decision"),
        ],
        "last_reviewed_at": None,
        "sources": [
            {
                "source_id": "tcgplayer_evolving_skies_8000_pack",
                "source_name": "TCGplayer Evolving Skies 8000-pack sample",
                "source_url": tcgplayer_refs,
                "source_type": "empirical_sample",
                "source_confidence": "high",
                "discovered_via": "reddit_pull_rate_discussions",
                "notes": "Primary source-level rows used for swsh7 direct bucket probabilities.",
            },
            {
                "source_id": "reddit_pull_rate_discussions",
                "source_name": "Reddit pull-rate discussion references",
                "source_url": reddit_refs,
                "source_type": "discussion_reference",
                "source_confidence": "medium",
                "discovered_via": None,
                "notes": "Traceability and source-discovery reference for published empirical rows.",
            },
            {
                "source_id": "swsh7_thepricedex_cross_reference_2026_06_holo",
                "source_name": "ThePriceDex Evolving Skies cross-reference",
                "source_url": _to_optional_str(thepricedex_refs),
                "source_type": "secondary_index",
                "source_confidence": "medium_low",
                "discovered_via": None,
                "notes": "Secondary-index cross-reference used for provisional holo rare odds (non-direct).",
            },
        ],
        "bucket_evidence": bucket_evidence,
    }


def _build_swsh8_pull_rate_references(config_class: Any) -> Dict[str, Any]:
    sources = getattr(config_class, "FUSION_STRIKE_PULL_RATE_REFERENCE_SOURCES", []) or []
    evidence_rows = getattr(config_class, "FUSION_STRIKE_PULL_RATE_REFERENCE_BUCKET_EVIDENCE", []) or []

    bucket_evidence: List[Dict[str, Any]] = []
    for row in evidence_rows:
        if not isinstance(row, Mapping):
            continue
        bucket_evidence.append(
            {
                "source_bucket_label": row.get("source_bucket_label") or "unknown",
                "normalized_bucket": _normalize_rarity(row.get("normalized_bucket") or row.get("source_bucket_label")),
                "probability_used": None,
                "odds_display": _to_optional_str(row.get("odds_display")),
                "source_status": row.get("source_status") or SOURCE_STATUS_SECONDARY_INDEX_ONLY,
                "source_granularity_status": row.get("source_granularity_status")
                or row.get("source_status")
                or SOURCE_STATUS_SECONDARY_INDEX_ONLY,
                "used_in_runtime": False,
                "caveat": _to_optional_str(row.get("caveat")),
                "source_ids": list(row.get("source_ids") or []),
            }
        )

    normalized_sources: List[Dict[str, Any]] = []
    for source in sources:
        if not isinstance(source, Mapping):
            continue
        normalized_sources.append(
            {
                "source_id": _to_optional_str(source.get("source_id")) or "unknown_source",
                "source_name": _to_optional_str(source.get("source_name")) or "Unknown source",
                "source_url": _to_optional_str(source.get("source_url")),
                "source_type": _to_optional_str(source.get("source_type")) or "reference_only",
                "source_confidence": _to_optional_str(source.get("source_confidence")) or "medium",
                "discovered_via": _to_optional_str(source.get("discovered_via")),
                "notes": _to_optional_str(source.get("notes")),
            }
        )

    return {
        "model_status": "reference_only_verified_sources",
        "model_confidence": "medium",
        "caveats": [
            "Fusion Strike pull-rate references are sample-based evidence and not official Pokemon-published odds.",
            "ThePriceDex rows are cross-reference/index metadata only and must not be treated as SOURCE_DIRECT runtime evidence.",
        ],
        "last_reviewed_at": "2026-05-26",
        "sources": normalized_sources,
        "bucket_evidence": bucket_evidence,
    }


def _get_pull_rate_reference_attr_pair(config_class: Any) -> Optional[Tuple[str, str]]:
    source_attr_names = sorted(
        attr_name
        for attr_name in dir(config_class)
        if attr_name.endswith("_PULL_RATE_REFERENCE_SOURCES")
    )
    evidence_attr_names = {
        attr_name
        for attr_name in dir(config_class)
        if attr_name.endswith("_PULL_RATE_REFERENCE_BUCKET_EVIDENCE")
    }

    for source_attr_name in source_attr_names:
        prefix = source_attr_name[: -len("_PULL_RATE_REFERENCE_SOURCES")]
        evidence_attr_name = f"{prefix}_PULL_RATE_REFERENCE_BUCKET_EVIDENCE"
        if evidence_attr_name in evidence_attr_names:
            return source_attr_name, evidence_attr_name

    return None


def _build_generic_swsh_pull_rate_references(config_class: Any) -> Optional[Dict[str, Any]]:
    attr_pair = _get_pull_rate_reference_attr_pair(config_class)
    if not attr_pair:
        return None

    source_attr_name, evidence_attr_name = attr_pair
    sources = getattr(config_class, source_attr_name, []) or []
    evidence_rows = getattr(config_class, evidence_attr_name, []) or []
    confidence = getattr(config_class, "SLOT_SCHEMA_SOURCE_CONFIDENCE", {}) or {}
    runtime_table = getattr(config_class, "RARE_SLOT_PROBABILITY", {}) or {}

    if not isinstance(sources, list) or not isinstance(evidence_rows, list):
        return None

    runtime_probability_by_bucket = {
        _normalize_rarity(bucket): float(probability)
        for bucket, probability in runtime_table.items()
        if _to_positive_probability(probability) is not None
    }

    normalized_sources: List[Dict[str, Any]] = []
    for source in sources:
        if not isinstance(source, Mapping):
            continue
        normalized_sources.append(
            {
                "source_id": _to_optional_str(source.get("source_id")) or "unknown_source",
                "source_name": _to_optional_str(source.get("source_name")) or "Unknown source",
                "source_url": _to_optional_str(source.get("source_url")),
                "source_type": _to_optional_str(source.get("source_type")) or "reference_only",
                "source_confidence": _to_optional_str(source.get("source_confidence")) or "medium",
                "discovered_via": _to_optional_str(source.get("discovered_via")),
                "notes": _to_optional_str(source.get("notes")),
            }
        )

    bucket_evidence: List[Dict[str, Any]] = []
    for row in evidence_rows:
        if not isinstance(row, Mapping):
            continue

        normalized_bucket = _normalize_rarity(row.get("normalized_bucket") or row.get("source_bucket_label"))
        used_in_runtime = bool(row.get("used_in_runtime"))
        probability_used = runtime_probability_by_bucket.get(normalized_bucket) if used_in_runtime else None

        bucket_evidence.append(
            {
                "source_bucket_label": row.get("source_bucket_label") or normalized_bucket or "unknown",
                "normalized_bucket": normalized_bucket,
                "probability_used": probability_used,
                "odds_display": _to_optional_str(row.get("odds_display")),
                "source_status": row.get("source_status") or SOURCE_STATUS_SECONDARY_INDEX_ONLY,
                "source_granularity_status": row.get("source_granularity_status")
                or row.get("source_status")
                or SOURCE_STATUS_SECONDARY_INDEX_ONLY,
                "used_in_runtime": used_in_runtime,
                "caveat": _to_optional_str(row.get("caveat")),
                "source_ids": list(row.get("source_ids") or []),
            }
        )

    return {
        "model_status": _to_optional_str(confidence.get("status")) or "runtime_candidate_best_available_empirical",
        "model_confidence": "medium",
        "caveats": [
            _to_optional_str(confidence.get("source_caveat")),
        ],
        "last_reviewed_at": None,
        "sources": normalized_sources,
        "bucket_evidence": bucket_evidence,
    }


def _build_pull_rate_references(
    *,
    config_class: Any,
    sources: Dict[str, str],
) -> Optional[Dict[str, Any]]:
    set_id = _normalize_key(getattr(config_class, "SET_ID", ""))
    runtime_table = getattr(config_class, "RARE_SLOT_PROBABILITY", {}) or {}

    if set_id == "swsh8":
        sources["pull_rate_references"] = "OK"
        return _build_swsh8_pull_rate_references(config_class)

    if not isinstance(runtime_table, Mapping) or not runtime_table:
        sources["pull_rate_references"] = "NO_RUNTIME_PROBABILITY"
        return None

    if set_id == "swsh6":
        sources["pull_rate_references"] = "OK"
        return _build_swsh6_pull_rate_references(config_class)
    if set_id == "swsh7":
        sources["pull_rate_references"] = "OK"
        return _build_swsh7_pull_rate_references(config_class)

    generic_swsh_references = _build_generic_swsh_pull_rate_references(config_class)
    if generic_swsh_references is not None:
        sources["pull_rate_references"] = "OK"
        return generic_swsh_references

    sources["pull_rate_references"] = "UNAVAILABLE_FOR_SET"
    return None


def _build_pull_rate_assumptions(
    *,
    config_class: Any,
    run_id: str,
    warnings: List[str],
    sources: Dict[str, str],
) -> Optional[Dict[str, Any]]:
    pull_rate_mapping = getattr(config_class, "PULL_RATE_MAPPING", {}) or {}
    slot_schema_mapping = getattr(config_class, "SLOT_SCHEMA_OUTCOME_POOL_MAPPING", {}) or {}
    has_slot_schema_source = isinstance(slot_schema_mapping, dict) and bool(slot_schema_mapping)
    if not isinstance(pull_rate_mapping, dict):
        pull_rate_mapping = {}
    if not pull_rate_mapping and not has_slot_schema_source:
        sources["pull_rate_assumptions"] = "NO_PULL_RATE_MAPPING"
        return None
    if not pull_rate_mapping and has_slot_schema_source:
        sources["pull_rate_assumptions_mapping_source"] = "SLOT_SCHEMA_RUNTIME_CONFIG"

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
    classified_bucket_card_ids: Dict[str, set[str]] = {}

    def _row_identifier(row: Mapping[str, Any]) -> Optional[str]:
        identifier = _normalize_key(row.get("card_variant_id"))
        if identifier:
            return identifier

        identifier = _normalize_key(row.get("card_id"))
        if identifier:
            return identifier

        identifier = _normalize_key(row.get("card_name"))
        return identifier or None

    try:
        cards_result = (
            public_read_client.table("simulation_input_cards_with_near_mint_price")
            .select("*")
            .eq("calculation_run_id", run_id)
            .execute()
        )
        cards_rows = list(cards_result.data or [])

        for row in cards_rows:
            rarity_key = _normalize_rarity(row.get("rarity_bucket"))
            if not rarity_key:
                continue

            identifier = _row_identifier(row)
            if not identifier:
                continue

            rarity_card_ids.setdefault(rarity_key, set()).add(identifier)

        if has_slot_schema_source and cards_rows:
            sources["pull_rate_assumptions_bucket_classification_source"] = "READ_TIME_CARD_METADATA_CLASSIFICATION"
            classification_rows = _enrich_slot_schema_classification_rows(
                cards_rows=cards_rows,
                run_id=run_id,
                warnings=warnings,
            )
            if not _has_minimum_slot_schema_classification_columns(classification_rows):
                sources["pull_rate_assumptions_bucket_classification"] = "UNAVAILABLE"
                warnings.append(
                    "Slot-schema bucket classification requires card metadata columns (rarity/card_number/printing_type/name)"
                )
            else:
                try:
                    classified_bucket_card_ids = _resolve_slot_schema_classification(
                        config_class=config_class,
                        classification_rows=classification_rows,
                        row_identifier=_row_identifier,
                        run_id=run_id,
                    )

                    sources["pull_rate_assumptions_bucket_classification"] = "OK"
                except Exception as exc:
                    logger.warning(
                        "[explore-page] slot_schema outcome bucket classification failed run_id=%s: %s",
                        run_id,
                        exc,
                    )
                    sources["pull_rate_assumptions_bucket_classification"] = "FAILED"
                    warnings.append(
                        "Failed to derive slot-schema classified eligible card counts for pull-rate assumptions"
                    )
        elif has_slot_schema_source:
            sources["pull_rate_assumptions_bucket_classification_source"] = "READ_TIME_CARD_METADATA_CLASSIFICATION"
            sources["pull_rate_assumptions_bucket_classification"] = "UNAVAILABLE"

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

    def _card_count_for_rarity(rarity_name: str) -> Optional[int]:
        configured_count = _to_positive_denominator(pull_rate_mapping.get(rarity_name))
        if configured_count:
            return configured_count

        derived_count = len(rarity_card_ids.get(_normalize_rarity(rarity_name), set()))
        return derived_count or None

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

    common_pool_count = _card_count_for_rarity("common")
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

    uncommon_pool_count = _card_count_for_rarity("uncommon")
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

    rare_card_count = _card_count_for_rarity("rare")
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
    ordered_hit_rarity_keys: List[str] = []

    def _append_hit_rarity(raw_rarity_name: Any) -> None:
        rarity_key = _normalize_rarity(raw_rarity_name)
        if not rarity_key or rarity_key in ordered_hit_rarity_keys:
            return
        if _is_base_population_rarity(rarity_key) or rarity_key in {"regular reverse", "hit", "hits", "reverse"}:
            return
        if rarity_key in special_pack_rarities or _is_special_pack_rarity(rarity_key):
            return
        ordered_hit_rarity_keys.append(rarity_key)

    for rarity_name in (getattr(config_class, "RARE_SLOT_PROBABILITY", {}) or {}).keys():
        _append_hit_rarity(rarity_name)

    reverse_slot_probabilities = getattr(config_class, "REVERSE_SLOT_PROBABILITIES", {}) or {}
    if isinstance(reverse_slot_probabilities, Mapping):
        for slot_payload in reverse_slot_probabilities.values():
            if not isinstance(slot_payload, Mapping):
                continue
            for rarity_name in slot_payload.keys():
                _append_hit_rarity(rarity_name)

    for rarity_name in pull_rate_mapping.keys():
        _append_hit_rarity(rarity_name)

    for rarity_name in rarity_card_ids.keys():
        _append_hit_rarity(rarity_name)

    for rarity_key in ordered_hit_rarity_keys:
        rarity_odds_denominator = generic_denominators.get(rarity_key)
        configured_specific_card_odds_denominator = _to_positive_denominator(pull_rate_mapping.get(rarity_key))
        specific_card_odds_denominator = configured_specific_card_odds_denominator

        card_count: Optional[int] = None
        if has_slot_schema_source:
            classified_count = len(classified_bucket_card_ids.get(rarity_key, set())) or None
            if classified_count:
                card_count = classified_count
                if rarity_odds_denominator:
                    specific_card_odds_denominator = rarity_odds_denominator * card_count
            elif rarity_odds_denominator and configured_specific_card_odds_denominator:
                card_count = int(round(configured_specific_card_odds_denominator / rarity_odds_denominator))
            elif rarity_odds_denominator:
                derived_count = len(rarity_card_ids.get(rarity_key, set())) or None
                if derived_count:
                    card_count = derived_count
                    specific_card_odds_denominator = rarity_odds_denominator * card_count
                else:
                    specific_card_odds_denominator = None
            else:
                specific_card_odds_denominator = configured_specific_card_odds_denominator
        else:
            if rarity_odds_denominator and specific_card_odds_denominator:
                card_count = int(round(specific_card_odds_denominator / rarity_odds_denominator))
            elif rarity_odds_denominator and not specific_card_odds_denominator:
                derived_count = len(rarity_card_ids.get(rarity_key, set())) or None
                if derived_count:
                    card_count = derived_count
                    specific_card_odds_denominator = rarity_odds_denominator * card_count

        slot_labels = sorted(slot_labels_by_rarity.get(rarity_key, set()))
        notes = "Specific-card odds sourced from set config PULL_RATE_MAPPING."
        if has_slot_schema_source:
            notes = "Specific-card odds derived from modeled bucket probability and classified eligible card count."

        if specific_card_odds_denominator is None and rarity_odds_denominator is not None:
            notes = "Specific-card odds require eligible card counts for this modeled bucket."
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
        warnings.append("Failed to compute relative Average Return context")
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


def _ensure_optional_summary_fields(summary: Dict[str, Any]) -> None:
    for field in _OPTIONAL_HIT_SET_VALUE_SUMMARY_FIELDS:
        summary.setdefault(field, None)


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
    rip_statistics: Dict[str, Any] = {"pack_paths": {}, "normal_pack_states": {}, "slot_schema_combo_states": {}}
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
            elif group == "slot_schema_combo":
                rip_statistics["slot_schema_combo_states"][name] = count
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
    if requested_target_type == "set":
        _populate_biggest_upside_metrics_for_set(summary, requested_target_id, warnings, sources)
        _populate_relative_average_return_score_for_set(summary, requested_target_id, warnings, sources)
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
        sources["simulation_input_cards"] = "OK"
    except Exception as exc:
        logger.warning("[explore-page] simulation_input_cards failed run_id=%s: %s", run_id, exc)
        warnings.append("Failed to load top hits")
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

    config_class = None
    if requested_target_type == "set":
        config_class, _ = _resolve_set_config_for_explore_target(
            requested_target_id,
            summary,
            warnings,
            sources,
        )

    if config_class is not None:
        modeled_display = _build_modeled_swsh_pack_breakdown_display(
            config_class=config_class,
            rankings=rankings,
            rip_statistics=rip_statistics,
        )
        if modeled_display is not None:
            rip_statistics["pack_breakdown_display"] = modeled_display

    interpretation = build_rip_interpretation(
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

    pull_rate_assumptions = None
    pull_rate_references = None
    if requested_target_type == "set":
        if config_class is not None:
            pull_rate_assumptions = _build_pull_rate_assumptions(
                config_class=config_class,
                run_id=run_id,
                warnings=warnings,
                sources=sources,
            )
            pull_rate_references = _build_pull_rate_references(
                config_class=config_class,
                sources=sources,
            )
        else:
            sources["pull_rate_assumptions"] = "SET_CONFIG_NOT_FOUND"
            sources["pull_rate_references"] = "SET_CONFIG_NOT_FOUND"

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
        "pull_rate_assumptions": pull_rate_assumptions,
        "pull_rate_references": pull_rate_references,
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
    slot_schema_mapping = getattr(config_class, "SLOT_SCHEMA_OUTCOME_POOL_MAPPING", {}) or {}
    has_slot_schema_source = isinstance(slot_schema_mapping, dict) and bool(slot_schema_mapping)
    if not isinstance(pull_rate_mapping, dict):
        pull_rate_mapping = {}
    if not pull_rate_mapping and not has_slot_schema_source:
        sources["pull_rate_assumptions"] = "NO_PULL_RATE_MAPPING"
        return None
    if not pull_rate_mapping and has_slot_schema_source:
        sources["pull_rate_assumptions_mapping_source"] = "SLOT_SCHEMA_RUNTIME_CONFIG"

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
    classified_bucket_card_ids: Dict[str, set[str]] = {}

    def _row_identifier(row: Mapping[str, Any]) -> Optional[str]:
        identifier = _normalize_key(row.get("card_variant_id"))
        if identifier:
            return identifier

        identifier = _normalize_key(row.get("card_id"))
        if identifier:
            return identifier

        identifier = _normalize_key(row.get("card_name"))
        return identifier or None

    try:
        cards_result = (
            public_read_client.table("simulation_input_cards_with_near_mint_price")
            .select("*")
            .eq("calculation_run_id", run_id)
            .execute()
        )
        cards_rows = list(cards_result.data or [])

        for row in cards_rows:
            rarity_key = _normalize_rarity(row.get("rarity_bucket"))
            if not rarity_key:
                continue

            identifier = _row_identifier(row)
            if not identifier:
                continue

            rarity_card_ids.setdefault(rarity_key, set()).add(identifier)

        if has_slot_schema_source and cards_rows:
            sources["pull_rate_assumptions_bucket_classification_source"] = "READ_TIME_CARD_METADATA_CLASSIFICATION"
            classification_rows = _enrich_slot_schema_classification_rows(
                cards_rows=cards_rows,
                run_id=run_id,
                warnings=warnings,
            )
            if not _has_minimum_slot_schema_classification_columns(classification_rows):
                sources["pull_rate_assumptions_bucket_classification"] = "UNAVAILABLE"
                warnings.append(
                    "Slot-schema bucket classification requires card metadata columns (rarity/card_number/printing_type/name)"
                )
            else:
                try:
                    classified_bucket_card_ids = _resolve_slot_schema_classification(
                        config_class=config_class,
                        classification_rows=classification_rows,
                        row_identifier=_row_identifier,
                        run_id=run_id,
                    )

                    sources["pull_rate_assumptions_bucket_classification"] = "OK"
                except Exception as exc:
                    logger.warning(
                        "[explore-page] slot_schema outcome bucket classification failed run_id=%s: %s",
                        run_id,
                        exc,
                    )
                    sources["pull_rate_assumptions_bucket_classification"] = "FAILED"
                    warnings.append(
                        "Failed to derive slot-schema classified eligible card counts for pull-rate assumptions"
                    )
        elif has_slot_schema_source:
            sources["pull_rate_assumptions_bucket_classification_source"] = "READ_TIME_CARD_METADATA_CLASSIFICATION"
            sources["pull_rate_assumptions_bucket_classification"] = "UNAVAILABLE"

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

    def _card_count_for_rarity(rarity_name: str) -> Optional[int]:
        configured_count = _to_positive_denominator(pull_rate_mapping.get(rarity_name))
        if configured_count:
            return configured_count

        derived_count = len(rarity_card_ids.get(_normalize_rarity(rarity_name), set()))
        return derived_count or None

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

    common_pool_count = _card_count_for_rarity("common")
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

    uncommon_pool_count = _card_count_for_rarity("uncommon")
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

    rare_card_count = _card_count_for_rarity("rare")
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
    ordered_hit_rarity_keys: List[str] = []

    def _append_hit_rarity(raw_rarity_name: Any) -> None:
        rarity_key = _normalize_rarity(raw_rarity_name)
        if not rarity_key or rarity_key in ordered_hit_rarity_keys:
            return
        if _is_base_population_rarity(rarity_key) or rarity_key in {"regular reverse", "hit", "hits", "reverse"}:
            return
        if rarity_key in special_pack_rarities or _is_special_pack_rarity(rarity_key):
            return
        ordered_hit_rarity_keys.append(rarity_key)

    for rarity_name in (getattr(config_class, "RARE_SLOT_PROBABILITY", {}) or {}).keys():
        _append_hit_rarity(rarity_name)

    reverse_slot_probabilities = getattr(config_class, "REVERSE_SLOT_PROBABILITIES", {}) or {}
    if isinstance(reverse_slot_probabilities, Mapping):
        for slot_payload in reverse_slot_probabilities.values():
            if not isinstance(slot_payload, Mapping):
                continue
            for rarity_name in slot_payload.keys():
                _append_hit_rarity(rarity_name)

    for rarity_name in pull_rate_mapping.keys():
        _append_hit_rarity(rarity_name)

    for rarity_name in rarity_card_ids.keys():
        _append_hit_rarity(rarity_name)

    for rarity_key in ordered_hit_rarity_keys:
        rarity_odds_denominator = generic_denominators.get(rarity_key)
        configured_specific_card_odds_denominator = _to_positive_denominator(pull_rate_mapping.get(rarity_key))
        specific_card_odds_denominator = configured_specific_card_odds_denominator

        card_count: Optional[int] = None
        if has_slot_schema_source:
            classified_count = len(classified_bucket_card_ids.get(rarity_key, set())) or None
            if classified_count:
                card_count = classified_count
                if rarity_odds_denominator:
                    specific_card_odds_denominator = rarity_odds_denominator * card_count
            elif rarity_odds_denominator and configured_specific_card_odds_denominator:
                card_count = int(round(configured_specific_card_odds_denominator / rarity_odds_denominator))
            elif rarity_odds_denominator:
                derived_count = len(rarity_card_ids.get(rarity_key, set())) or None
                if derived_count:
                    card_count = derived_count
                    specific_card_odds_denominator = rarity_odds_denominator * card_count
                else:
                    specific_card_odds_denominator = None
            else:
                specific_card_odds_denominator = configured_specific_card_odds_denominator
        else:
            if rarity_odds_denominator and specific_card_odds_denominator:
                card_count = int(round(specific_card_odds_denominator / rarity_odds_denominator))
            elif rarity_odds_denominator and not specific_card_odds_denominator:
                derived_count = len(rarity_card_ids.get(rarity_key, set())) or None
                if derived_count:
                    card_count = derived_count
                    specific_card_odds_denominator = rarity_odds_denominator * card_count

        slot_labels = sorted(slot_labels_by_rarity.get(rarity_key, set()))
        notes = "Specific-card odds sourced from set config PULL_RATE_MAPPING."
        if has_slot_schema_source:
            notes = "Specific-card odds derived from modeled bucket probability and classified eligible card count."

        if specific_card_odds_denominator is None and rarity_odds_denominator is not None:
            notes = "Specific-card odds require eligible card counts for this modeled bucket."
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
        warnings.append("Failed to compute relative Average Return context")
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
    rip_statistics: Dict[str, Any] = {"pack_paths": {}, "normal_pack_states": {}, "slot_schema_combo_states": {}}
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
            elif group == "slot_schema_combo":
                rip_statistics["slot_schema_combo_states"][name] = count
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
    if requested_target_type == "set":
        _populate_biggest_upside_metrics_for_set(summary, requested_target_id, warnings, sources)
        _populate_relative_average_return_score_for_set(summary, requested_target_id, warnings, sources)
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
        sources["simulation_input_cards"] = "OK"
    except Exception as exc:
        logger.warning("[explore-page] simulation_input_cards failed run_id=%s: %s", run_id, exc)
        warnings.append("Failed to load top hits")
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

    config_class = None
    if requested_target_type == "set":
        config_class, _ = _resolve_set_config_for_explore_target(
            requested_target_id,
            summary,
            warnings,
            sources,
        )

    if config_class is not None:
        modeled_display = _build_modeled_swsh_pack_breakdown_display(
            config_class=config_class,
            rankings=rankings,
            rip_statistics=rip_statistics,
        )
        if modeled_display is not None:
            rip_statistics["pack_breakdown_display"] = modeled_display

    interpretation = build_rip_interpretation(
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

    pull_rate_assumptions = None
    pull_rate_references = None
    if requested_target_type == "set":
        if config_class is not None:
            pull_rate_assumptions = _build_pull_rate_assumptions(
                config_class=config_class,
                run_id=run_id,
                warnings=warnings,
                sources=sources,
            )
            pull_rate_references = _build_pull_rate_references(
                config_class=config_class,
                sources=sources,
            )
        else:
            sources["pull_rate_assumptions"] = "SET_CONFIG_NOT_FOUND"
            sources["pull_rate_references"] = "SET_CONFIG_NOT_FOUND"

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
        "pull_rate_assumptions": pull_rate_assumptions,
        "pull_rate_references": pull_rate_references,
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
