"""Taxonomy and empirical helpers for Card Treatment Prestige V2.

This module deliberately contains no numeric treatment ladder.  Production
scores come only from an approved database study run.
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass
from typing import Any, Iterable, Mapping, Optional, Sequence

METHODOLOGY_VERSION = "card_treatment_prestige_v2"
TAXONOMY_VERSION = "pokemon_card_treatment_taxonomy_v2"


def _key(value: Any) -> Optional[str]:
    text = re.sub(r"[^a-z0-9]+", "_", str(value or "").strip().lower()).strip("_")
    return text or None


RARITY_ALIASES = {
    "special_illustration": "special_illustration_rare",
    "special_illustration_rare": "special_illustration_rare",
    "illustration_rare": "illustration_rare",
    "hyper_rare": "hyper_rare_gold",
    "rare_secret": "secret_rare",
    "ultra_rare": "ultra_rare",
    "double_rare": "double_rare",
    "rare_holo": "rare_holo",
    "holo_rare": "rare_holo",
    "rare": "rare",
    "uncommon": "uncommon",
    "common": "common",
    "ace_spec_rare": "ace_spec",
    "ace_spec": "ace_spec",
}
PRINTING_ALIASES = {
    "normal": "normal", "non_holo": "normal", "holo": "holo",
    "holofoil": "holo", "reverse": "reverse_holo", "reverse_holo": "reverse_holo",
}
SPECIAL_ALIASES = {
    "pokeball": "poke_ball", "poke_ball": "poke_ball",
    "masterball": "master_ball", "master_ball": "master_ball",
    "stamped": "stamped",
}


@dataclass(frozen=True)
class TreatmentIdentity:
    treatment_key: Optional[str]
    rarity_key: Optional[str]
    printing_type: Optional[str]
    special_type: Optional[str]
    edition: Optional[str]
    status: str


def resolve_treatment_identity(*, rarity: Any, printing_type: Any = None,
                               special_type: Any = None, edition: Any = None,
                               era: Any = None) -> TreatmentIdentity:
    del era  # retained in the signature because lookup scope is era-aware
    raw_rarity = _key(rarity)
    rarity_key = RARITY_ALIASES.get(raw_rarity or "")
    printing_key = PRINTING_ALIASES.get(_key(printing_type) or "")
    special_key = SPECIAL_ALIASES.get(_key(special_type) or "")
    edition_key = _key(edition)
    if raw_rarity and rarity_key is None:
        return TreatmentIdentity(None, None, printing_key, special_key, edition_key, "unmapped_treatment")
    if rarity_key is None:
        return TreatmentIdentity(None, None, printing_key, special_key, edition_key, "unmapped_treatment")
    parts = [rarity_key]
    if printing_key and printing_key != "normal":
        parts.append(printing_key)
    if special_key:
        parts.append(special_key)
    if edition_key:
        parts.append(edition_key)
    return TreatmentIdentity("__".join(parts), rarity_key, printing_key, special_key, edition_key, "mapped")


def positive_log_price(value: Any) -> Optional[float]:
    try: value = float(value)
    except (TypeError, ValueError): return None
    return math.log(value) if math.isfinite(value) and value > 0 else None


def pull_probability(value: Any) -> Optional[float]:
    try: value = float(value)
    except (TypeError, ValueError): return None
    if not math.isfinite(value) or value <= 0: return None
    probability = value if value <= 1 else 1.0 / value
    return probability if 0 < probability <= 1 else None


def log_pull_odds(value: Any) -> Optional[float]:
    probability = pull_probability(value)
    return math.log(1.0 / probability) if probability else None


def pairwise_superiority_scores(draws: Mapping[str, Sequence[float]]) -> dict[str, float]:
    keys = sorted(draws)
    if len(keys) < 2: return {}
    length = min(len(draws[key]) for key in keys)
    if not length: return {}
    return {key: 10.0 * sum(
        sum(float(draws[key][b]) > float(draws[other][b]) for b in range(length)) / length
        for other in keys if other != key
    ) / (len(keys) - 1) for key in keys}


def common_support_bounds(groups: Mapping[str, Iterable[float]], *, lower: float = .10,
                          upper: float = .90) -> Optional[tuple[float, float]]:
    import numpy as np
    valid = [list(values) for values in groups.values() if list(values)]
    if len(valid) < 2: return None
    low = max(float(np.quantile(values, lower)) for values in valid)
    high = min(float(np.quantile(values, upper)) for values in valid)
    return (low, high) if low <= high else None
