"""
Rarity classification utilities for hit/non-hit bucketing.

This module provides era-aware rarity classification based on the active
base-config RARITY_MAPPING, treating it as the source of truth for
determining which cards are chase/hit cards.

Key principle:
    A card is a "hit" if and only if its raw rarity maps to 'hits'
    according to config.RARITY_MAPPING. This is NOT hardcoded as
    "rares and above" or any other shortcut.
"""

import re

import pandas as pd


RARITY_KEY_SEPARATOR_PATTERN = re.compile(r"[\s-]+")
RARITY_KEY_DUPLICATE_SEPARATOR_PATTERN = re.compile(r"_+")


def normalize_rarity_string(rarity_raw: str) -> str:
    """Normalize rarity strings for comparison.
    
    Parameters
    ----------
    rarity_raw : str
        Raw rarity value from dataframe or config.
    
    Returns
    -------
    str
        Normalized rarity (lowercase, stripped whitespace).
    """
    return str(rarity_raw).lower().strip()


def normalize_rarity_key(rarity_raw: str) -> str:
    """Normalize raw rarity text into a stable underscore-separated key."""
    if pd.isna(rarity_raw):
        return ""

    normalized = normalize_rarity_string(rarity_raw)
    normalized = RARITY_KEY_SEPARATOR_PATTERN.sub("_", normalized)
    normalized = RARITY_KEY_DUPLICATE_SEPARATOR_PATTERN.sub("_", normalized)
    return normalized.strip("_")


def is_hit_rarity(rarity_raw: str, config) -> bool:
    """Check if a rarity maps to 'hits' according to config.
    
    This consults the active era's base-config RARITY_MAPPING to determine
    if a card with the given rarity should be classified as a hit/chase card.
    
    Parameters
    ----------
    rarity_raw : str
        Raw rarity value (e.g., "ultra rare", "double rare").
    config : BaseSetConfig
        The era/set configuration object with RARITY_MAPPING attribute.
    
    Returns
    -------
    bool
        True if the rarity maps to 'hits', False otherwise.
        
    Raises
    ------
    AttributeError
        If config does not have RARITY_MAPPING.
    
    Examples
    --------
    >>> is_hit_rarity("ultra rare", scarlet_config)
    True
    >>> is_hit_rarity("common", scarlet_config)
    False
    >>> is_hit_rarity("special illustration rare", scarlet_config)
    True
    """
    if not hasattr(config, 'RARITY_MAPPING'):
        raise AttributeError(
            f"Config {config.__class__.__name__} does not have RARITY_MAPPING attribute."
        )
    
    normalized = normalize_rarity_string(rarity_raw)
    mapped_group = config.RARITY_MAPPING.get(normalized)
    return mapped_group == 'hits'


def get_rarity_group(rarity_raw: str, config) -> str:
    """Get the rarity group for a card's raw rarity.
    
    Parameters
    ----------
    rarity_raw : str
        Raw rarity value.
    config : BaseSetConfig
        Configuration object with RARITY_MAPPING.
    
    Returns
    -------
    str
        The mapped rarity group ('hits', 'common', 'uncommon', 'rare', etc.).
        Returns None if rarity is not in the mapping.
    
    Raises
    ------
    AttributeError
        If config does not have RARITY_MAPPING.
    """
    if not hasattr(config, 'RARITY_MAPPING'):
        raise AttributeError(
            f"Config {config.__class__.__name__} does not have RARITY_MAPPING attribute."
        )
    
    normalized = normalize_rarity_string(rarity_raw)
    return config.RARITY_MAPPING.get(normalized)


def is_hit_classification(classification_key: str) -> bool:
    """Check whether a normalized classification key represents a recognized hit bucket."""
    from .special_type_normalization import RECOGNIZED_PATTERN_BUCKETS

    return normalize_rarity_key(classification_key) in RECOGNIZED_PATTERN_BUCKETS


def is_hit_row(row: pd.Series, config) -> bool:
    """Classify a card row as hit/non-hit using normalized classification first, then raw rarity."""
    if is_hit_classification(row.get("classification_key", "")):
        return True

    return is_hit_rarity(row.get("Rarity", ""), config)


def get_chase_metrics_excluded_rarities(config) -> set[str]:
    """Return normalized raw rarities excluded from chase/hit-derived metrics."""
    configured = getattr(config, "CHASE_METRICS_EXCLUDED_RARITIES", set())
    if configured is None:
        return set()
    return {normalize_rarity_string(rarity) for rarity in configured}


def is_excluded_from_chase_metrics(rarity_raw: str, config) -> bool:
    """Check if a raw rarity should be excluded from hit/chase-derived metrics."""
    normalized = normalize_rarity_string(rarity_raw)
    return normalized in get_chase_metrics_excluded_rarities(config)


def filter_card_ev_by_hits(card_ev_contributions: dict, df, config) -> tuple:
    """Filter card EV contributions into hit and non-hit pools.

    Uses card_number (stable identity) for matching when the DataFrame has a
    'Card Number' column with non-empty values. Falls back to card-name matching
    only when card_number is not available.

    Card name is NOT used as the primary identity key for hit classification.
    Multiple distinct cards can share a name (e.g., two printings of 'Charizard ex'
    at different rarities); using card_number prevents misclassification.

    Parameters
    ----------
    card_ev_contributions : dict
        Mapping of {card_key: ev_value} where card_key is card_number when
        Card Number is in the DataFrame, otherwise card_name.
    df : pd.DataFrame
        Original card dataframe with 'Card Name', 'Rarity', and optionally
        'Card Number' columns.
    config : BaseSetConfig
        Configuration with RARITY_MAPPING.

    Returns
    -------
    tuple
        (hit_ev_contributions, non_hit_ev_contributions) where each is
        a dict of {card_key: ev_value}.

    Notes
    -----
    - Cards with EV <= 0 are excluded from both result dicts.
    - Unmatched cards (key not found in df) are classified as non-hit with
      a diagnostic warning. They are NOT silently dropped.
    - Ambiguous matches (same card_number appears multiple times in df) emit
      a diagnostic warning and use the first matching row.
    """
    hit_contributions = {}
    non_hit_contributions = {}

    # Determine if we should use card_number-based matching
    use_card_number = (
        "Card Number" in df.columns
        and df["Card Number"].astype(str).str.strip().replace("", pd.NA).notna().any()
    )

    if use_card_number:
        # Build an index: card_number → first matching row's hit classification
        # Check for duplicates (same card_number appearing more than once)
        card_number_col = df["Card Number"].astype(str).str.strip()
        df_indexed = df.assign(_card_key=card_number_col)
        duplicate_keys = df_indexed[df_indexed.duplicated(subset=["_card_key"], keep=False)]["_card_key"].unique()
        if len(duplicate_keys) > 0:
            print(
                f"[IDENTITY_WARNING] Duplicate card_number entries detected in DataFrame for "
                f"{len(duplicate_keys)} card number(s): {list(duplicate_keys)[:10]}. "
                "Using first matching row for hit classification."
            )
        first_rows_by_card_number = df_indexed.groupby("_card_key", sort=False).first()
        hit_status_by_card_number = {}
        for card_key, row in first_rows_by_card_number.iterrows():
            is_hit = bool(is_hit_row(row, config))
            if is_hit and is_excluded_from_chase_metrics(row.get("Rarity", ""), config):
                is_hit = False
            hit_status_by_card_number[str(card_key)] = is_hit
    else:
        # Legacy: build name-based index
        print(
            "[IDENTITY_WARNING] Using card-name-based hit classification fallback. "
            "Same-named cards with different rarities may be misclassified. "
            "Ensure 'Card Number' is passed through the data pipeline."
        )
        name_col = df["Card Name"].astype(str).str.lower().str.strip()
        hit_status_by_name = {}
        for normalized_name, (_, row) in zip(name_col, df.iterrows()):
            if normalized_name not in hit_status_by_name:
                is_hit = bool(is_hit_row(row, config))
                if is_hit and is_excluded_from_chase_metrics(row.get("Rarity", ""), config):
                    is_hit = False
                hit_status_by_name[normalized_name] = is_hit

    for card_key, ev_value in card_ev_contributions.items():
        if float(ev_value) <= 0.0:
            continue

        if use_card_number:
            is_hit = hit_status_by_card_number.get(str(card_key).strip())
            if is_hit is None:
                print(
                    f"[IDENTITY_UNMATCHED] Card key '{card_key}' not found in DataFrame by card_number. "
                    "Classifying as non-hit (conservative fallback). "
                    "Check that card_number values are consistent between config and DB data."
                )
                non_hit_contributions[card_key] = float(ev_value)
                continue
        else:
            # Legacy name-based fallback
            normalized_key = str(card_key).strip().lower()
            is_hit = hit_status_by_name.get(normalized_key)
            if is_hit is None:
                print(
                    f"[IDENTITY_UNMATCHED] Card '{card_key}' not found in DataFrame by name. "
                    "Classifying as non-hit (conservative fallback)."
                )
                non_hit_contributions[card_key] = float(ev_value)
                continue

        if is_hit:
            hit_contributions[card_key] = float(ev_value)
        else:
            non_hit_contributions[card_key] = float(ev_value)

    return hit_contributions, non_hit_contributions
