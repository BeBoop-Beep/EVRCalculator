import numpy as np
import pandas as pd
from typing import Set

from .rarity_classification import normalize_rarity_key
from .special_type_normalization import (
    RECOGNIZED_PATTERN_BUCKETS,
    derive_classification_key,
    derive_pattern_key,
    normalize_special_type_key,
)

REVERSE_PRICE_COLUMN = "Reverse Variant Price ($)"


def normalize_reverse_classification_key(value: str) -> str:
    normalized_special_type = normalize_special_type_key(value)
    if normalized_special_type in RECOGNIZED_PATTERN_BUCKETS:
        return normalized_special_type

    return normalize_rarity_key(value)


def get_normalized_reverse_eligible_rarity_keys(config) -> Set[str]:
    provider = getattr(config, "get_reverse_eligible_rarities", None)
    if not callable(provider):
        raise ValueError("Config must define get_reverse_eligible_rarities() for reverse EV calculations.")

    return {
        normalize_reverse_classification_key(rarity)
        for rarity in provider()
        if rarity is not None and str(rarity).strip()
    }


def get_normalized_base_rarity_key_series(df: pd.DataFrame) -> pd.Series:
    if "rarity_key" in df.columns:
        source = df["rarity_key"]
    elif "rarity_raw" in df.columns:
        source = df["rarity_raw"]
    elif "Rarity" in df.columns:
        source = df["Rarity"]
    else:
        raise ValueError("Reverse EV calculations require either 'rarity_raw' or 'Rarity'.")

    return source.fillna("").apply(normalize_rarity_key)


def get_normalized_classification_key_series(df: pd.DataFrame) -> pd.Series:
    if "classification_key" in df.columns:
        classification_keys = df["classification_key"].fillna("").apply(normalize_reverse_classification_key)

        if "pattern_key" in df.columns:
            pattern_keys = df["pattern_key"].fillna("").apply(normalize_special_type_key).apply(derive_pattern_key)
            pattern_mask = pattern_keys.isin(RECOGNIZED_PATTERN_BUCKETS)
            if pattern_mask.any():
                classification_keys = classification_keys.where(~pattern_mask, pattern_keys)

        if "aggregation_key" in df.columns:
            aggregation_keys = df["aggregation_key"].fillna("").apply(normalize_reverse_classification_key)
            aggregation_pattern_mask = aggregation_keys.isin(RECOGNIZED_PATTERN_BUCKETS)
            if aggregation_pattern_mask.any():
                classification_keys = classification_keys.where(~aggregation_pattern_mask, aggregation_keys)

        return classification_keys

    rarity_keys = get_normalized_base_rarity_key_series(df)

    if "special_type_key" in df.columns:
        special_type_keys = df["special_type_key"].fillna("").apply(normalize_special_type_key)
    elif "Special Type" in df.columns:
        special_type_keys = df["Special Type"].fillna("").apply(normalize_special_type_key)
    else:
        special_type_keys = pd.Series("", index=df.index, dtype="object")

    classification_keys = [
        normalize_reverse_classification_key(derive_classification_key(rarity_key, special_type_key))
        for rarity_key, special_type_key in zip(rarity_keys, special_type_keys)
    ]
    return pd.Series(classification_keys, index=df.index, dtype="object")


def build_reverse_eligible_pool(config, df: pd.DataFrame) -> pd.DataFrame:
    if REVERSE_PRICE_COLUMN not in df.columns:
        return df.iloc[0:0].copy()

    rarity_keys = get_normalized_base_rarity_key_series(df)
    classification_keys = get_normalized_classification_key_series(df)
    reverse_eligible_keys = get_normalized_reverse_eligible_rarity_keys(config)
    explicit_pattern_keys = reverse_eligible_keys & RECOGNIZED_PATTERN_BUCKETS
    base_rarity_keys = reverse_eligible_keys - RECOGNIZED_PATTERN_BUCKETS
    pattern_overlay_mask = classification_keys.isin(RECOGNIZED_PATTERN_BUCKETS)

    eligible_mask = (
        rarity_keys.isin(base_rarity_keys) & ~pattern_overlay_mask
    ) | classification_keys.isin(explicit_pattern_keys)

    reverse_prices = pd.to_numeric(df[REVERSE_PRICE_COLUMN], errors="coerce")
    reverse_pool = df.loc[eligible_mask & reverse_prices.notna()].copy()
    reverse_pool[REVERSE_PRICE_COLUMN] = reverse_prices.loc[reverse_pool.index].astype(float)
    return reverse_pool


def get_regular_reverse_probability(slot_name: str, slot_config: dict) -> float:
    if not isinstance(slot_config, dict) or not slot_config:
        raise ValueError(f"Reverse slot '{slot_name}' must define a non-empty probability mapping.")

    normalized_probs = pd.to_numeric(pd.Series(slot_config), errors="coerce")
    if normalized_probs.isna().any():
        raise ValueError(f"Reverse slot '{slot_name}' contains a non-numeric probability.")

    if ((normalized_probs < 0) | (normalized_probs > 1)).any():
        raise ValueError(f"Reverse slot '{slot_name}' contains a probability outside [0, 1].")

    prob_sum = float(normalized_probs.sum())
    if not np.isclose(prob_sum, 1.0, atol=1e-8):
        raise ValueError(f"Reverse slot '{slot_name}' probabilities must sum to 1.0. Found {prob_sum:.12f}")

    regular_reverse_prob = float(normalized_probs.get("regular reverse", 0.0))
    if regular_reverse_prob < 0 or regular_reverse_prob > 1:
        raise ValueError(f"Reverse slot '{slot_name}' regular reverse probability is invalid.")

    return regular_reverse_prob