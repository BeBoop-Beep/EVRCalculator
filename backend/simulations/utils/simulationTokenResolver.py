from __future__ import annotations

import re
from typing import Dict, List, Literal, Tuple

import pandas as pd

from backend.calculations.utils.rarity_classification import normalize_rarity_key, normalize_rarity_string
from backend.calculations.utils.special_type_normalization import (
    derive_aggregation_key,
    derive_pattern_key,
    normalize_special_type_key,
)


_TOKEN_ALIAS_PATTERN = re.compile(r"[^a-z0-9]+")
_TOKEN_WHITESPACE_PATTERN = re.compile(r"\s+")
_CANONICAL_TOKEN_ALIASES = {
    "pokeball": "poke ball pattern",
    "pokeballpattern": "poke ball pattern",
    "masterball": "master ball pattern",
    "masterballpattern": "master ball pattern",
}
_MATCH_KEY_TO_CANONICAL_TOKEN = {
    "pokeball_pattern": "poke ball pattern",
    "master_ball_pattern": "master ball pattern",
}
_SIMULATION_BASE_RARITY_ALIASES = {
    "holo_rare": "rare",
    "rare_holo": "rare",
    "rare_holofoil": "rare",
    "holofoil_rare": "rare",
}
SimulationResolverMode = Literal["base_rarity", "pattern", "aggregation"]


def _normalize_simulation_base_rarity_key(value: str) -> str:
    key = normalize_rarity_key(value)
    return _SIMULATION_BASE_RARITY_ALIASES.get(key, key)


def normalize_simulation_token(token: str) -> str:
    normalized = normalize_rarity_string(token)
    if not normalized:
        return ""

    alias_key = _TOKEN_ALIAS_PATTERN.sub("", normalized)
    canonical = _CANONICAL_TOKEN_ALIASES.get(alias_key)
    if canonical is not None:
        return canonical

    return _TOKEN_WHITESPACE_PATTERN.sub(" ", normalized)


def canonical_token_to_match_key(token: str, *, mode: SimulationResolverMode) -> str:
    canonical = normalize_simulation_token(token)
    if not canonical:
        return ""

    rarity_key = normalize_rarity_key(canonical)
    special_type_key = normalize_special_type_key(canonical)
    if mode == "base_rarity":
        return rarity_key
    if mode == "pattern":
        return derive_pattern_key(special_type_key)
    if mode == "aggregation":
        return derive_aggregation_key(rarity_key, special_type_key)

    raise ValueError(f"Unsupported simulation resolver mode '{mode}'.")


def match_key_to_canonical_token(match_key: str, *, mode: SimulationResolverMode) -> str:
    normalizer = normalize_special_type_key if mode == "pattern" else normalize_rarity_key
    normalized_key = normalizer(match_key)
    if not normalized_key:
        return ""

    return _MATCH_KEY_TO_CANONICAL_TOKEN.get(normalized_key, normalized_key.replace("_", " "))


def _empty_key_series(df: pd.DataFrame) -> pd.Series:
    return pd.Series("", index=df.index, dtype="object")


def _get_base_rarity_match_keys(df: pd.DataFrame) -> Tuple[pd.Series, str]:
    # base_rarity_key is the ONLY safe source for base slot sampling per the data contract.
    # It must be checked before rarity_key / rarity_raw / Rarity.
    for column in ("base_rarity_key", "rarity_key", "rarity_raw", "Rarity"):
        if column in df.columns:
            return (
                df[column].fillna("").astype(str).map(_normalize_simulation_base_rarity_key),
                column,
            )

    return _empty_key_series(df), "<missing>"


def _get_pattern_match_keys(df: pd.DataFrame) -> Tuple[pd.Series, str]:
    if "pattern_key" in df.columns:
        pattern_keys = df["pattern_key"].fillna("").astype(str).map(normalize_special_type_key)
        pattern_keys = pattern_keys.map(derive_pattern_key)
        if pattern_keys.ne("").any():
            return pattern_keys, "pattern_key"

    for column in (
        "special_type_key",
        "special_type_raw",
        "special_type",
        "Special Type",
        "special type",
        "classification_key",
        "aggregation_key",
        "rarity_raw",
        "Rarity",
    ):
        if column in df.columns:
            pattern_keys = df[column].fillna("").astype(str).map(normalize_special_type_key)
            pattern_keys = pattern_keys.map(derive_pattern_key)
            if pattern_keys.ne("").any():
                return pattern_keys, column

    return _empty_key_series(df), "<missing>"


def _get_aggregation_match_keys(df: pd.DataFrame) -> Tuple[pd.Series, str]:
    for column in ("aggregation_key", "classification_key"):
        if column in df.columns:
            aggregation_keys = df[column].fillna("").astype(str).map(normalize_rarity_key)
            if aggregation_keys.ne("").any():
                return aggregation_keys, column

    rarity_keys, rarity_source = _get_base_rarity_match_keys(df)
    if "special_type_key" in df.columns:
        special_type_keys = df["special_type_key"].fillna("").astype(str).map(normalize_special_type_key)
        source = "special_type_key"
    elif "Special Type" in df.columns:
        special_type_keys = df["Special Type"].fillna("").astype(str).map(normalize_special_type_key)
        source = "Special Type"
    else:
        special_type_keys = _empty_key_series(df)
        source = "<missing>"

    aggregation_keys = pd.Series(
        [
            derive_aggregation_key(rarity_key, special_type_key)
            for rarity_key, special_type_key in zip(rarity_keys.tolist(), special_type_keys.tolist())
        ],
        index=df.index,
        dtype="object",
    )
    return aggregation_keys, f"derived:{rarity_source}+{source}"


def get_row_match_keys(df: pd.DataFrame, *, mode: SimulationResolverMode) -> Tuple[pd.Series, str]:
    if mode == "base_rarity":
        return _get_base_rarity_match_keys(df)
    if mode == "pattern":
        return _get_pattern_match_keys(df)
    if mode == "aggregation":
        return _get_aggregation_match_keys(df)

    raise ValueError(f"Unsupported simulation resolver mode '{mode}'.")


def get_simulation_token_mode(token: str) -> SimulationResolverMode:
    pattern_key = canonical_token_to_match_key(token, mode="pattern")
    if pattern_key:
        return "pattern"

    return "base_rarity"


def list_available_canonical_tokens(df: pd.DataFrame, *, mode: SimulationResolverMode) -> List[str]:
    if df.empty:
        return []

    row_match_keys, _ = get_row_match_keys(df, mode=mode)
    return sorted({match_key_to_canonical_token(key, mode=mode) for key in row_match_keys.tolist() if key})


def resolve_hit_pool_rows(
    hit_cards: pd.DataFrame,
    requested_token: str,
    *,
    mode: SimulationResolverMode,
) -> Tuple[pd.DataFrame, Dict[str, object]]:
    requested = "" if requested_token is None else str(requested_token)
    canonical_token = normalize_simulation_token(requested)
    requested_match_key = canonical_token_to_match_key(canonical_token, mode=mode)
    available_tokens = list_available_canonical_tokens(hit_cards, mode=mode)

    if hit_cards.empty or not requested_match_key:
        return hit_cards.iloc[0:0], {
            "mode": mode,
            "requested_token": requested,
            "canonical_token": canonical_token,
            "requested_match_key": requested_match_key,
            "available_tokens": available_tokens,
            "match_source": None,
        }

    row_match_keys, match_source = get_row_match_keys(hit_cards, mode=mode)
    eligible = hit_cards.loc[row_match_keys.eq(requested_match_key)]
    return eligible, {
        "mode": mode,
        "requested_token": requested,
        "canonical_token": canonical_token,
        "requested_match_key": requested_match_key,
        "available_tokens": available_tokens,
        "match_source": match_source,
    }


def format_token_resolution_error(
    *,
    mode: SimulationResolverMode,
    requested_token: str,
    canonical_token: str,
    available_tokens: List[str],
) -> str:
    available = ", ".join(f"'{token}'" for token in available_tokens) if available_tokens else "<none>"
    return (
        f"resolver mode '{mode}' requested token '{requested_token}' normalized to canonical token '{canonical_token}'. "
        f"Available canonical tokens: {available}"
    )