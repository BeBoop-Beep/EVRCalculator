"""Thresholds and helpers for RIP interpretation classification."""

from __future__ import annotations

from typing import Any, Optional

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
    }
    return aliases.get(raw, raw)


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
# Formatting helpers — produce readable strings for evidence values
# ---------------------------------------------------------------------------

def format_percent(value: Optional[float]) -> str:
    """Convert a 0–1 fraction to a percentage string like '42.3%'."""
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
    """Format a 0–100 score as '74.2'."""
    if value is None:
        return "N/A"
    return f"{value:.1f}"


def format_cardinality(value: Optional[float]) -> str:
    """Format an effective count as a rounded integer string."""
    if value is None:
        return "N/A"
    return str(int(round(value)))
