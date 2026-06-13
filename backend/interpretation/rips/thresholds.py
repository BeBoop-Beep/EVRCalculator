"""Thresholds and helpers for RIP interpretation classification."""

from __future__ import annotations

from typing import Any, Optional

PILLAR_INTERPRETATION_WEIGHTS = {
    "profit": 0.45,
    "safety": 0.25,
    "desirability": 0.20,
    "stability": 0.10,
}

INTERPRETATION_TIER_STRENGTH = {
    "S": 5,
    "A": 4,
    "B": 3,
    "C": 2,
    "D": 1,
    "F": 0,
}

HIGH_SCORE_MIN = 70.0
MEDIUM_SCORE_MIN = 40.0

IMBALANCE_GAP_POINTS = 25.0

TOP_SHARE_HIGH_MIN = 0.40
TOP_SHARE_MEDIUM_MIN = 0.20

TOP_RARITY_EV_CONCENTRATION_HIGH_MIN = 0.55

PROBABILITY_STRONG_MIN = 0.55
PROBABILITY_LOW_MAX = 0.30

P95_TO_COST_STRONG_MIN = 1.80
P95_TO_COST_MEDIUM_MIN = 1.25

MEDIAN_TO_COST_WEAK_MAX = 0.70

P05_TAIL_RECOVERY_SEVERE_MULTIPLIER = 0.25

TREND_MEANINGFUL_DELTA_MIN = 0.08


def classify_score_strength(score: Optional[float]) -> str:
    if score is None:
        return "medium"
    if score >= HIGH_SCORE_MIN:
        return "high"
    if score >= MEDIUM_SCORE_MIN:
        return "medium"
    return "low"


def tier_to_strength(tier: Optional[str]) -> Optional[int]:
    if tier is None:
        return None
    return INTERPRETATION_TIER_STRENGTH.get(str(tier).strip().upper())


def score_to_strength(score: Optional[float]) -> Optional[int]:
    if score is None:
        return None
    if score >= 85:
        return 5
    if score >= 70:
        return 4
    if score >= 55:
        return 3
    if score >= 40:
        return 2
    if score >= 25:
        return 1
    return 0


def get_summary_data(data: dict[str, Any]) -> dict[str, Any]:
    summary_data = data.get("summary") if isinstance(data.get("summary"), dict) else data
    return summary_data if isinstance(summary_data, dict) else {}


def normalize_tier(value: Any) -> Optional[str]:
    if value is None:
        return None
    normalized = str(value).strip().upper()
    return normalized or None


def get_tier(summary_data: dict[str, Any], key: str) -> Optional[str]:
    return normalize_tier(summary_data.get(key))


def get_rank(summary_data: dict[str, Any], key: str) -> Optional[float]:
    if key.startswith("relative_"):
        return get_numeric(summary_data, key)
    return get_numeric(summary_data, key, f"relative_{key}")


def get_score(
    summary_data: dict[str, Any],
    score_key: str,
    relative_score_key: Optional[str] = None,
) -> Optional[float]:
    if relative_score_key:
        return get_numeric(summary_data, score_key, relative_score_key)
    return get_numeric(summary_data, score_key)


def tier_or_score_strength(tier: Optional[str], score: Optional[float]) -> Optional[int]:
    tier_strength = tier_to_strength(tier)
    if tier_strength is not None:
        return tier_strength
    return score_to_strength(score)


def _build_pillar_context(summary_data: dict[str, Any], pillar: str) -> dict[str, Any]:
    score = get_score(summary_data, f"{pillar}_score", f"relative_{pillar}_score")
    relative_score = get_score(summary_data, f"relative_{pillar}_score")
    tier = get_tier(summary_data, f"{pillar}_tier")
    rank = get_rank(summary_data, f"{pillar}_rank")
    relative_rank = get_rank(summary_data, f"relative_{pillar}_rank")
    strength = tier_or_score_strength(tier, score if score is not None else relative_score)
    return {
        "score": score,
        "relative_score": relative_score,
        "tier": tier,
        "rank": rank,
        "relative_rank": relative_rank,
        "strength": strength,
    }


def build_profit_context(summary_data: dict[str, Any]) -> dict[str, Any]:
    return _build_pillar_context(summary_data, "profit")


def build_safety_context(summary_data: dict[str, Any]) -> dict[str, Any]:
    return _build_pillar_context(summary_data, "safety")


def build_stability_context(summary_data: dict[str, Any]) -> dict[str, Any]:
    return _build_pillar_context(summary_data, "stability")


def build_desirability_context(summary_data: dict[str, Any]) -> dict[str, Any]:
    return _build_pillar_context(summary_data, "desirability")


def build_pack_context(summary_data: dict[str, Any]) -> dict[str, Any]:
    score = get_score(summary_data, "pack_score", "relative_pack_score")
    tier = get_tier(summary_data, "pack_tier") or get_tier(summary_data, "tier")
    rank = get_rank(summary_data, "pack_rank")
    return {
        "score": score,
        "relative_score": get_score(summary_data, "relative_pack_score"),
        "tier": tier,
        "rank": rank,
        "strength": tier_or_score_strength(tier, score),
    }


def classify_ratio_high_medium_low(
    value: Optional[float],
    *,
    high_min: float,
    medium_min: float,
    missing: str = "medium",
) -> str:
    if value is None:
        return missing
    if value >= high_min:
        return "high"
    if value >= medium_min:
        return "medium"
    return "low"


def classify_share_concentration(
    share: Optional[float],
    *,
    high_min: float = TOP_SHARE_HIGH_MIN,
    medium_min: float = TOP_SHARE_MEDIUM_MIN,
    missing: str = "medium",
) -> str:
    if share is None:
        return missing
    if share >= high_min:
        return "high"
    if share >= medium_min:
        return "medium"
    return "low"


def classify_probability(
    probability: Optional[float],
    *,
    strong_min: float = PROBABILITY_STRONG_MIN,
    low_max: float = PROBABILITY_LOW_MAX,
    missing: str = "medium",
) -> str:
    if probability is None:
        return missing
    if probability >= strong_min:
        return "high"
    if probability < low_max:
        return "low"
    return "medium"


def classify_tail_strength(
    p95_to_cost_ratio: Optional[float],
    *,
    strong_min: float = P95_TO_COST_STRONG_MIN,
    medium_min: float = P95_TO_COST_MEDIUM_MIN,
    missing: str = "medium",
) -> str:
    return classify_ratio_high_medium_low(
        p95_to_cost_ratio,
        high_min=strong_min,
        medium_min=medium_min,
        missing=missing,
    )


def classify_directional_delta(
    delta: Optional[float],
    *,
    meaningful_delta: float = TREND_MEANINGFUL_DELTA_MIN,
    missing: str = "flat",
) -> str:
    if delta is None:
        return missing
    if delta >= meaningful_delta:
        return "up"
    if delta <= -meaningful_delta:
        return "down"
    return "flat"


def safe_percent_share(value: Optional[float], total: Optional[float]) -> Optional[float]:
    if value is None or total is None or total <= 0:
        return None
    return max(0.0, value / total)


def normalize_rarity_name(rarity: Any) -> str:
    raw = str(rarity or "").strip().lower()
    if not raw:
        return "unknown"

    aliases = {
        "sir": "special illustration rare",
        "ir": "illustration rare",
        "ar": "illustration rare",
        "sr": "secret rare",
        "ur": "ultra rare",
        "ace spec": "ace spec rare",
        "acespec": "ace spec rare",
        "reg reverse": "regular reverse",
        "reverse holo": "regular reverse",
        "rev holo": "regular reverse",
        "hits": "unknown",
        "hit": "unknown",
        "non-hit": "unknown",
        "non hit": "unknown",
        "bulk": "unknown",
    }
    return aliases.get(raw, raw)


def format_rarity_label(rarity: Any) -> str:
    normalized = normalize_rarity_name(rarity)

    if normalized == "unknown":
        return "Unknown"

    fixed_labels = {
        "illustration rare": "Illustration Rare",
        "special illustration rare": "Special Illustration Rare",
        "ultra rare": "Ultra Rare",
        "double rare": "Double Rare",
        "hyper rare": "Hyper Rare",
        "ace spec rare": "Ace Spec Rare",
        "common": "Common",
        "uncommon": "Uncommon",
        "rare": "Rare",
        "regular reverse": "Regular Reverse",
        "ex": "ex",
    }

    if normalized in fixed_labels:
        return fixed_labels[normalized]

    parts = []
    for token in normalized.split():
        if token in {"ex", "gx", "v", "vmax", "vstar"}:
            parts.append(token.upper() if token != "ex" else "ex")
        else:
            parts.append(token.capitalize())
    return " ".join(parts)


def get_numeric(payload: dict[str, Any], *keys: str) -> Optional[float]:
    for key in keys:
        if key in payload:
            raw = payload.get(key)
            try:
                return float(raw)
            except (TypeError, ValueError):
                continue
    return None


# ---------------------------------------------------------------------------
# Formatting helpers - produce readable strings for evidence values
# ---------------------------------------------------------------------------

def format_percent(value: Optional[float]) -> str:
    """Convert a 0-1 fraction to a percentage string like '42.3%'."""
    if value is None:
        return "N/A"
    return f"{value * 100:.1f}%"


def format_ratio(value: Optional[float]) -> str:
    """Format a cost-ratio as '1.25x'."""
    if value is None:
        return "N/A"
    return f"{value:.2f}x"


def format_currency(value: Optional[float]) -> str:
    """Format a dollar value as '$4.20'."""
    if value is None:
        return "N/A"
    return f"${value:.2f}"


def format_score(value: Optional[float]) -> str:
    """Format a 0-100 score as '74.2'."""
    if value is None:
        return "N/A"
    return f"{value:.1f}"


def format_cardinality(value: Optional[float]) -> str:
    """Format an effective count as a rounded integer string."""
    if value is None:
        return "N/A"
    return str(int(round(value)))
