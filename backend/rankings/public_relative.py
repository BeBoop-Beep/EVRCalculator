"""Shared deterministic public ranking-presentation helpers."""

from __future__ import annotations

from typing import Any, Callable, Dict, Iterable, Mapping, Optional
import math


def _optional_number(value: Any) -> Optional[float]:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def public_relative_rip_tier(relative_score: Any) -> Optional[str]:
    """Locked public RIP tier bands over an already-relative 0-100 score."""
    score = _optional_number(relative_score)
    if score is None:
        return None
    if score >= 90:
        return "S"
    if score >= 80:
        return "A"
    if score >= 70:
        return "B"
    if score >= 45:
        return "C"
    if score >= 15:
        return "D"
    return "F"


def compute_public_relative_scores(
    rows: Iterable[Mapping[str, Any]], *, id_getter: Callable[[Mapping[str, Any]], Any],
    score_getter: Callable[[Mapping[str, Any]], Any],
) -> Dict[str, Optional[float]]:
    """Min-max scores: best 100, worst 0, ties 50, nulls excluded."""
    scored = [(str(id_getter(row)), _optional_number(score_getter(row))) for row in rows]
    valid = [score for _, score in scored if score is not None]
    if not valid:
        return {identity: None for identity, _ in scored}
    low, high = min(valid), max(valid)
    if high <= low:
        return {identity: (50.0 if score is not None else None) for identity, score in scored}
    return {
        identity: (round(100.0 * (score - low) / (high - low), 2) if score is not None else None)
        for identity, score in scored
    }


def public_rank_tier(rank: Any, cohort_size: Any) -> Optional[str]:
    """Canonical Sets public rank-bucket tier shared by every RIP ranking."""
    try:
        numeric_rank, size = int(rank), int(cohort_size)
    except (TypeError, ValueError, ZeroDivisionError):
        return None
    if size <= 0 or numeric_rank <= 0:
        return None
    if numeric_rank <= max(1, math.ceil(size * 0.05)):
        return "S"
    if numeric_rank <= max(1, math.ceil(size * 0.15)):
        return "A"
    if numeric_rank <= max(1, math.ceil(size * 0.30)):
        return "B"
    if numeric_rank <= max(1, math.ceil(size * 0.50)):
        return "C"
    if numeric_rank <= max(1, math.ceil(size * 0.75)):
        return "D"
    return "F"


# Compatibility name for the first product-relative implementation.
public_product_rank_tier = public_rank_tier
