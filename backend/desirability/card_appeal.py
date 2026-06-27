"""Card-level appeal scoring helpers for Pokemon market validation snapshots."""

from __future__ import annotations

import math
import re
from typing import Any, Optional

ADJUSTED_CARD_APPEAL_WEIGHTS = {
    "pokemon": 0.55,
    "treatment": 0.25,
    "scarcity": 0.20,
}

SCARCITY_MAX_DENOMINATOR = 2000.0

# V1 treatment weights. These are intentionally coarse and should be audited
# against real market behavior before being used as a ranking product.
TREATMENT_SCORE_RULES = (
    ("special illustration rare", 96.0),
    ("special illustration", 96.0),
    ("illustration rare", 84.0),
    ("hyper rare", 82.0),
    ("gold", 82.0),
    ("ultra rare", 80.0),
    ("ace spec", 68.0),
    ("double rare", 62.0),
    ("rare holo", 45.0),
    ("holo rare", 45.0),
    ("rare", 36.0),
    ("uncommon", 22.0),
    ("common", 18.0),
)


def to_optional_float(value: Any) -> Optional[float]:
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return None
    return parsed if math.isfinite(parsed) else None


def clamp_score(value: Any) -> Optional[float]:
    parsed = to_optional_float(value)
    if parsed is None:
        return None
    return max(0.0, min(parsed, 100.0))


def normalize_rarity_label(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "").strip().lower().replace("_", " ").replace("-", " "))


def get_treatment_score(rarity: Any) -> Optional[float]:
    normalized = normalize_rarity_label(rarity)
    if not normalized:
        return None
    for needle, score in TREATMENT_SCORE_RULES:
        if needle in normalized:
            return score
    return 30.0


def normalize_pull_probability(value: Any) -> Optional[float]:
    parsed = to_optional_float(value)
    if parsed is None or parsed <= 0:
        return None
    if parsed <= 1:
        return parsed
    return 1.0 / parsed


def calculate_scarcity_score(
    pull_probability: Any = None,
    *,
    odds_denominator: Any = None,
    max_denominator: float = SCARCITY_MAX_DENOMINATOR,
) -> Optional[float]:
    probability = normalize_pull_probability(pull_probability)
    if probability is None:
        denominator = to_optional_float(odds_denominator)
        if denominator is None or denominator <= 0:
            return None
        probability = 1.0 / denominator

    if probability >= 1:
        return 0.0

    denominator = max(1.0, 1.0 / probability)
    normalized = math.log(denominator) / math.log(max_denominator)
    return round(max(0.0, min(normalized, 1.0)) * 100.0, 2)


def calculate_adjusted_card_appeal(
    pokemon_desirability_score: Any,
    treatment_score: Any,
    scarcity_score: Any = None,
) -> Optional[float]:
    components = {
        "pokemon": clamp_score(pokemon_desirability_score),
        "treatment": clamp_score(treatment_score),
        "scarcity": clamp_score(scarcity_score),
    }
    available = {
        key: score
        for key, score in components.items()
        if score is not None
    }
    if not available or available.get("pokemon") is None:
        return None

    total_weight = sum(ADJUSTED_CARD_APPEAL_WEIGHTS[key] for key in available)
    if total_weight <= 0:
        return None

    weighted = sum(
        score * ADJUSTED_CARD_APPEAL_WEIGHTS[key]
        for key, score in available.items()
    )
    return round(weighted / total_weight, 2)
