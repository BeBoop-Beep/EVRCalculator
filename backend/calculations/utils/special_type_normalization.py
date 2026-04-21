import re

import pandas as pd

from .rarity_classification import normalize_rarity_key, normalize_rarity_string


SPECIAL_TYPE_ALIAS_LOOKUP = {
    "pokeball": "pokeball_pattern",
    "pokeballpattern": "pokeball_pattern",
    "masterball": "master_ball_pattern",
    "masterballpattern": "master_ball_pattern",
}
RECOGNIZED_PATTERN_BUCKETS = frozenset(SPECIAL_TYPE_ALIAS_LOOKUP.values())
SPECIAL_TYPE_ALIAS_PATTERN = re.compile(r"[^a-z0-9]+")


def normalize_special_type_string(special_type_raw: str) -> str:
    if pd.isna(special_type_raw):
        return ""

    return normalize_rarity_string(special_type_raw)


def normalize_special_type_key(special_type_raw: str) -> str:
    normalized = normalize_special_type_string(special_type_raw)
    if not normalized:
        return ""

    alias_key = SPECIAL_TYPE_ALIAS_PATTERN.sub("", normalized)
    canonical_key = SPECIAL_TYPE_ALIAS_LOOKUP.get(alias_key)
    if canonical_key is not None:
        return canonical_key

    return normalize_rarity_key(normalized)


def is_recognized_pattern_special_type(special_type_key: str) -> bool:
    return special_type_key in RECOGNIZED_PATTERN_BUCKETS


def derive_pattern_key(special_type_key: str) -> str:
    if is_recognized_pattern_special_type(special_type_key):
        return special_type_key

    return ""


def derive_aggregation_key(rarity_key: str, special_type_key: str) -> str:
    pattern_key = derive_pattern_key(special_type_key)
    if pattern_key:
        return pattern_key

    return rarity_key


def derive_classification_key(rarity_key: str, special_type_key: str) -> str:
    return derive_aggregation_key(rarity_key, special_type_key)