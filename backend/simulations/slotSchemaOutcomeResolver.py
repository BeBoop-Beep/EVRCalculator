from __future__ import annotations

import re
from typing import Any, Dict, Iterable, Mapping, MutableMapping, Optional

import pandas as pd


_SPECIAL_FILTER_KEYS = frozenset(
    {
        "card_number_range",
        "card_number_min",
        "card_number_max",
        "name_contains",
        "name_not_contains",
        "name_contains_all",
        "name_pattern",
    }
)

_COLUMN_ALIASES = {
    "rarity": ("rarity", "Rarity", "rarity_raw"),
    "printing_type": ("printing_type", "Printing Type", "printing_type_key"),
    "card_number": ("card_number", "Card Number"),
    "name": ("name", "Card Name"),
}


def _resolve_column_name(available_columns: Iterable[str], canonical: str) -> Optional[str]:
    available = set(available_columns)
    for candidate in _COLUMN_ALIASES.get(canonical, (canonical,)):
        if candidate in available:
            return candidate
    return None


def _coerce_text_series(df: pd.DataFrame, canonical: str) -> pd.Series:
    column_name = _resolve_column_name(df.columns, canonical)
    if column_name is None:
        raise ValueError(
            f"slot_schema outcome mapping requires column for {canonical!r}. "
            f"Available columns: {sorted(df.columns.tolist())}."
        )
    return df[column_name].fillna("").astype(str)


def _coerce_card_number(value: Any) -> Optional[int]:
    if value is None:
        return None
    if isinstance(value, bool):
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


def _coerce_card_number_series(df: pd.DataFrame) -> pd.Series:
    column_name = _resolve_column_name(df.columns, "card_number")
    if column_name is None:
        raise ValueError(
            "slot_schema outcome mapping requires card number column for card-number filters. "
            f"Available columns: {sorted(df.columns.tolist())}."
        )
    return df[column_name].map(_coerce_card_number)


def _parse_card_number_range(raw: Any) -> tuple[int, int]:
    if isinstance(raw, str):
        parts = [piece.strip() for piece in raw.split("-", 1)]
        if len(parts) != 2 or not parts[0].isdigit() or not parts[1].isdigit():
            raise ValueError(
                "card_number_range must be 'min-max' (numeric). "
                f"Received {raw!r}."
            )
        start = int(parts[0])
        end = int(parts[1])
    elif isinstance(raw, (tuple, list)) and len(raw) == 2:
        start = int(raw[0])
        end = int(raw[1])
    else:
        raise ValueError(
            "card_number_range must be 'min-max' string or [min, max] pair. "
            f"Received {raw!r}."
        )

    if start > end:
        raise ValueError(
            "card_number_range is invalid: min cannot be greater than max. "
            f"Received {raw!r}."
        )
    return start, end


def _normalize_text(value: Any) -> str:
    return str(value).strip().lower()


def _apply_named_filter(df: pd.DataFrame, mask: pd.Series, operator: str, value: Any) -> pd.Series:
    names = _coerce_text_series(df, "name")

    if operator == "name_contains":
        needle = str(value)
        return mask & names.str.contains(needle, case=False, regex=False)

    if operator == "name_not_contains":
        needle = str(value)
        return mask & ~names.str.contains(needle, case=False, regex=False)

    if operator == "name_contains_all":
        if not isinstance(value, (list, tuple)) or len(value) == 0:
            raise ValueError("name_contains_all must be a non-empty list of substrings.")
        updated = mask
        for needle in value:
            updated = updated & names.str.contains(str(needle), case=False, regex=False)
        return updated

    if operator == "name_pattern":
        pattern_text = str(value).strip()
        match = re.fullmatch(r"endswith\((['\"])(.*)\1\)", pattern_text)
        if not match:
            raise ValueError(
                "name_pattern currently supports only endswith('...') syntax. "
                f"Received {pattern_text!r}."
            )
        suffix = match.group(2)
        return mask & names.str.endswith(suffix)

    raise ValueError(f"Unknown name filter operator: {operator!r}.")


def _apply_filter_dict(df: pd.DataFrame, mask: pd.Series, filter_dict: Mapping[str, Any]) -> pd.Series:
    updated_mask = mask
    for key, value in filter_dict.items():
        if key == "card_number_range":
            start, end = _parse_card_number_range(value)
            numbers = _coerce_card_number_series(df)
            updated_mask = updated_mask & numbers.ge(start) & numbers.le(end)
            continue

        if key == "card_number_min":
            numbers = _coerce_card_number_series(df)
            updated_mask = updated_mask & numbers.ge(int(value))
            continue

        if key == "card_number_max":
            numbers = _coerce_card_number_series(df)
            updated_mask = updated_mask & numbers.le(int(value))
            continue

        if key in {"name_contains", "name_not_contains", "name_contains_all", "name_pattern"}:
            updated_mask = _apply_named_filter(df, updated_mask, key, value)
            continue

        column_name = _resolve_column_name(df.columns, key)
        if column_name is None:
            raise ValueError(
                f"Unknown slot_schema filter operator/column {key!r}. "
                f"Available columns: {sorted(df.columns.tolist())}."
            )
        target = _normalize_text(value)
        updated_mask = updated_mask & df[column_name].fillna("").astype(str).map(_normalize_text).eq(target)

    return updated_mask


def _exclude_reverse_variants_if_needed(df: pd.DataFrame, mask: pd.Series, include_reverse_variants: bool) -> pd.Series:
    if include_reverse_variants:
        return mask

    printing_col = _resolve_column_name(df.columns, "printing_type")
    if printing_col is None:
        raise ValueError(
            "include_reverse_variants=False requires printing_type column so reverse-holo rows can be excluded."
        )
    printing = df[printing_col].fillna("").astype(str).str.strip().str.lower()
    return mask & printing.ne("reverse-holo")


def validate_slot_schema_outcome_pool_mapping(
    config: Any,
    available_columns: Optional[Iterable[str]] = None,
) -> Dict[str, Dict[str, Any]]:
    mapping = getattr(config, "SLOT_SCHEMA_OUTCOME_POOL_MAPPING", None)
    if mapping is None:
        raise ValueError(
            "slot_schema outcome pool mapping is missing: expected config.SLOT_SCHEMA_OUTCOME_POOL_MAPPING."
        )
    if not isinstance(mapping, Mapping) or len(mapping) == 0:
        raise ValueError("SLOT_SCHEMA_OUTCOME_POOL_MAPPING must be a non-empty mapping.")

    normalized_mapping: MutableMapping[str, Dict[str, Any]] = {}
    for outcome, details in mapping.items():
        if not isinstance(outcome, str) or not outcome.strip():
            raise ValueError(f"Invalid outcome key in SLOT_SCHEMA_OUTCOME_POOL_MAPPING: {outcome!r}.")
        if not isinstance(details, Mapping):
            raise ValueError(f"Outcome mapping for {outcome!r} must be a mapping-like object.")

        card_filter = details.get("card_filter", {})
        variant_filter = details.get("variant_filter", {})
        include_reverse_variants = bool(details.get("include_reverse_variants", True))

        if not isinstance(card_filter, Mapping):
            raise ValueError(f"{outcome!r}.card_filter must be a mapping.")
        if not isinstance(variant_filter, Mapping):
            raise ValueError(f"{outcome!r}.variant_filter must be a mapping.")

        combined_filters = dict(card_filter)
        combined_filters.update(variant_filter)

        if available_columns is not None:
            columns = list(available_columns)
            for key in combined_filters:
                if key in _SPECIAL_FILTER_KEYS:
                    if key.startswith("card_number") and _resolve_column_name(columns, "card_number") is None:
                        raise ValueError(
                            f"{outcome!r} uses {key!r}, but card number columns are missing from input."
                        )
                    if key.startswith("name_") and _resolve_column_name(columns, "name") is None:
                        raise ValueError(
                            f"{outcome!r} uses {key!r}, but name columns are missing from input."
                        )
                    continue
                if _resolve_column_name(columns, key) is None:
                    raise ValueError(
                        f"{outcome!r} includes unknown filter key {key!r}. "
                        f"Available columns: {sorted(columns)}."
                    )

            if not include_reverse_variants and _resolve_column_name(columns, "printing_type") is None:
                raise ValueError(
                    f"{outcome!r} sets include_reverse_variants=False, but printing_type column is unavailable."
                )

        normalized_mapping[outcome] = {
            "source": details.get("source", ""),
            "card_filter": dict(card_filter),
            "variant_filter": dict(variant_filter),
            "include_reverse_variants": include_reverse_variants,
        }

    return dict(normalized_mapping)


def apply_slot_schema_outcome_pool_mapping(
    config: Any,
    simulation_input_df: pd.DataFrame,
    *,
    allow_empty_pools: bool = False,
) -> Dict[str, pd.DataFrame]:
    if not isinstance(simulation_input_df, pd.DataFrame):
        raise ValueError(
            "simulation_input_df must be a pandas DataFrame for slot_schema outcome mapping."
        )

    mapping = validate_slot_schema_outcome_pool_mapping(config, available_columns=simulation_input_df.columns)
    resolved: Dict[str, pd.DataFrame] = {}

    for outcome, details in mapping.items():
        mask = pd.Series(True, index=simulation_input_df.index)
        mask = _apply_filter_dict(simulation_input_df, mask, details.get("card_filter", {}))
        mask = _apply_filter_dict(simulation_input_df, mask, details.get("variant_filter", {}))
        mask = _exclude_reverse_variants_if_needed(
            simulation_input_df,
            mask,
            details.get("include_reverse_variants", True),
        )

        pool_df = simulation_input_df.loc[mask].copy()
        if pool_df.empty and not allow_empty_pools:
            raise ValueError(
                f"Outcome {outcome!r} resolved to an empty pool from SLOT_SCHEMA_OUTCOME_POOL_MAPPING."
            )
        resolved[outcome] = pool_df

    return resolved


def resolve_slot_schema_outcome_pools(config: Any, card_groups_or_dataframe: Any) -> Dict[str, pd.DataFrame]:
    if isinstance(card_groups_or_dataframe, pd.DataFrame):
        return apply_slot_schema_outcome_pool_mapping(config, card_groups_or_dataframe)

    if isinstance(card_groups_or_dataframe, Mapping):
        frames = [
            value
            for value in card_groups_or_dataframe.values()
            if isinstance(value, pd.DataFrame)
        ]
        if not frames:
            raise ValueError(
                "No pandas DataFrame pools were found in card_groups_or_dataframe mapping."
            )
        combined_df = pd.concat(frames, axis=0, ignore_index=True, sort=False)
        return apply_slot_schema_outcome_pool_mapping(config, combined_df)

    raise ValueError(
        "resolve_slot_schema_outcome_pools expects a pandas DataFrame or mapping of pool name -> DataFrame."
    )
