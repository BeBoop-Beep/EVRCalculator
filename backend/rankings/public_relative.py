"""Shared deterministic public ranking-presentation helpers."""

from __future__ import annotations

from typing import Any, Callable, Dict, Iterable, Mapping, Optional


def _optional_number(value: Any) -> Optional[float]:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number


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


def public_product_rank_tier(rank: Any, cohort_size: Any) -> Optional[str]:
    """Product public tier from rank percentile; unavailable remains un-tiered."""
    try:
        numeric_rank, size = int(rank), int(cohort_size)
    except (TypeError, ValueError, ZeroDivisionError):
        return None
    percentile = numeric_rank / size
    if numeric_rank == 1 or percentile <= 0.10:
        return "S"
    if percentile <= 0.25:
        return "A"
    if percentile <= 0.50:
        return "B"
    if percentile <= 0.75:
        return "C"
    return "D"
