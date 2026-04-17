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


def filter_card_ev_by_hits(card_ev_contributions: dict, df, config) -> tuple:
    """Filter card EV contributions into hit and non-hit pools.
    
    Takes a card_ev_contributions dictionary and the original dataframe,
    and splits contributions based on the config's rarity mapping.
    
    Parameters
    ----------
    card_ev_contributions : dict
        Mapping of {card_name: ev_value}.
    df : pd.DataFrame
        Original card dataframe with 'Card Name' and 'Rarity' columns.
    config : BaseSetConfig
        Configuration with RARITY_MAPPING.
    
    Returns
    -------
    tuple
        (hit_ev_contributions, non_hit_ev_contributions) where each is
        a dict of {card_name: ev_value}.
    
    Notes
    -----
    - Card names are normalized to strip/lowercase for matching against dataframe.
    - Cards not found in dataframe are categorized based on whether they would
      be hits if they existed (conservative: missing cards assumed non-hit).
    - Zero-EV cards are omitted from both result dicts.
    """
    hit_contributions = {}
    non_hit_contributions = {}
    
    for card_name, ev_value in card_ev_contributions.items():
        if float(ev_value) <= 0.0:
            continue
        
        # Find the card's rarity in the dataframe
        # Normalize card name for matching
        normalized_card_name = str(card_name).strip().lower()
        matching_rows = df[
            df['Card Name'].astype(str).str.lower().str.strip() == normalized_card_name
        ]
        
        if not matching_rows.empty:
            # Use the first match's rarity
            rarity_raw = matching_rows.iloc[0]['Rarity']
            is_hit = is_hit_rarity(rarity_raw, config)
        else:
            # Card not found; assume non-hit to be conservative
            is_hit = False
        
        if is_hit:
            hit_contributions[card_name] = float(ev_value)
        else:
            non_hit_contributions[card_name] = float(ev_value)
    
    return hit_contributions, non_hit_contributions
