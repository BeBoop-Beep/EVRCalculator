"""Shared deterministic public ranking-presentation helpers."""

from __future__ import annotations

from typing import Any, Callable, Dict, Iterable, Mapping, Optional
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
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


def public_rip_display_score(leader_score: Any) -> Optional[float]:
    """Return the exact one-decimal 0-10 score shown publicly, using half-up rounding."""
    score = _optional_number(leader_score)
    if score is None:
        return None
    try:
        return float((Decimal(str(score)) / Decimal("10")).quantize(Decimal("0.1"), rounding=ROUND_HALF_UP))
    except (InvalidOperation, ValueError):
        return None


def public_leader_rip_tier(leader_score: Any) -> Optional[str]:
    """Grade the exact one-decimal leader-curved score displayed to users."""
    score = public_rip_display_score(leader_score)
    if score is None:
        return None
    if score >= 9.6:
        return "S"
    if score >= 9.0:
        return "A"
    if score >= 8.0:
        return "B"
    if score >= 6.5:
        return "C"
    if score >= 5.0:
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


def compute_leader_normalized_scores(
    rows: Iterable[Mapping[str, Any]], *, id_getter: Callable[[Mapping[str, Any]], Any],
    score_getter: Callable[[Mapping[str, Any]], Any],
) -> Dict[str, Optional[float]]:
    """Additive public scores anchored to the cohort leader at exactly 100.

    Null and non-finite observations remain unavailable. A cohort whose best
    valid absolute score is non-positive cannot define a meaningful positive
    leader curve, so every observation fails closed to ``None``.
    """
    scored = [(str(id_getter(row)), _optional_number(score_getter(row))) for row in rows]
    valid = [score for _, score in scored if score is not None]
    if not valid or max(valid) <= 0:
        return {identity: None for identity, _ in scored}
    leader = max(valid)
    return {
        identity: (round(100.0 * score / leader, 2) if score is not None else None)
        for identity, score in scored
    }


def public_rank_tier(rank: Any, cohort_size: Any) -> Optional[str]:
    """LEGACY rank-only tier (ceil bands 5/15/30/50/75%).

    No production caller remains.  Kept only for external/older imports; use
    ``benchmark_relative_tier`` (Set/Era 0-10 benchmark) or
    ``absolute_rank_percentile_tier`` (no neutral point) instead.
    """
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


BENCHMARK_REFERENCE_SCORE = 5.0
BENCHMARK_NEUTRAL_HALF_BAND = 0.25
_BAND_EPSILON = 1e-9


def _valid_rank_and_size(rank: Any, cohort_size: Any) -> Optional[tuple[int, int]]:
    try:
        numeric_rank, size = int(rank), int(cohort_size)
    except (TypeError, ValueError, OverflowError):
        return None
    if size <= 0 or numeric_rank <= 0 or numeric_rank > size:
        return None
    return numeric_rank, size


def benchmark_relative_tier(score: Any, rank: Any, cohort_size: Any,
                            reference: float = BENCHMARK_REFERENCE_SCORE) -> Optional[str]:
    """Tier for benchmark-centered Set/Era scores (0-10, Pokemon average = 5.0).

    Scores within ``reference +/- 0.25`` (inclusive) are C regardless of rank.
    Above the band: S top 1%, A through top 10%, B remainder.  Below the band:
    F for the bottom quartile (cohorts of 4 or more only), otherwise D.
    Cohort cut-offs use floor, never ceil.
    """
    try:
        value = float(score)
    except (TypeError, ValueError):
        return None
    if math.isnan(value) or math.isinf(value):
        return None
    position = _valid_rank_and_size(rank, cohort_size)
    if position is None:
        return None
    numeric_rank, size = position
    delta = value - reference
    if abs(delta) <= BENCHMARK_NEUTRAL_HALF_BAND + _BAND_EPSILON:
        return "C"
    if delta > 0:
        s_count = max(1, size // 100)
        a_cutoff = max(s_count, size // 10)
        if numeric_rank <= s_count:
            return "S"
        return "A" if numeric_rank <= a_cutoff else "B"
    f_count = max(1, size // 4)
    return "F" if size >= 4 and numeric_rank > size - f_count else "D"


def absolute_rank_percentile_tier(rank: Any, cohort_size: Any) -> Optional[str]:
    """Tier for absolute scores with no benchmark-neutral point (Products, Cards).

    S top 1%, A through top 10%, B through 25%, C through 50%, D through 75%,
    F the bottom 25%.  Floor-based cut-offs, each at least the previous one.
    """
    position = _valid_rank_and_size(rank, cohort_size)
    if position is None:
        return None
    numeric_rank, size = position
    cutoff = 1
    for percent, label in ((1, "S"), (10, "A"), (25, "B"), (50, "C"), (75, "D")):
        cutoff = max(cutoff, size * percent // 100)
        if numeric_rank <= cutoff:
            return label
    return "F"


# LEGACY compatibility name for the first product-relative implementation.
public_product_rank_tier = public_rank_tier
