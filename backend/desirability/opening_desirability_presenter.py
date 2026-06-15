from __future__ import annotations

import math
from typing import Any, Dict, Mapping, Optional


TOOLTIP_COPY = {
    "opening_desirability": (
        "Opening Desirability estimates how exciting a set is to open by combining "
        "collector demand with chase-card appeal."
    ),
    "collector_appeal": (
        "Collector Appeal reflects how desirable the Pokemon and card subjects are, "
        "independent of market price."
    ),
    "chase_appeal": (
        "Chase Appeal reflects the strength, depth, and upside of a set's meaningful chase cards."
    ),
}

MISSING_CHASE_SUMMARY = (
    "Collector Appeal is available, but Chase Appeal needs more market/opening data before "
    "an Opening Desirability score can be shown."
)


def present_opening_desirability(row: Mapping[str, Any]) -> Dict[str, Any]:
    """Build the public-safe Opening Desirability view model.

    This presenter maps internal prototype fields to product-facing labels. It
    intentionally omits exact formulas, internal blend names, and component weights.
    """
    opening_score = _score_or_none(
        _first_present(row, "opening_desirability_score", "primary_rip_desirability_score", "rip_desirability_score_70_30")
    )
    collector_score = _score_or_none(
        _first_present(row, "collector_appeal_score", "pure_desirability_score")
    )
    chase_score = _score_or_none(
        _first_present(row, "chase_appeal_score", "monetary_chase_appeal_score")
    )
    chase_quality = str(
        _first_present(row, "chase_appeal_data_quality", "monetary_data_quality") or "missing"
    )
    if chase_quality not in {"usable", "partial", "missing"}:
        chase_quality = "missing"

    display_status = _display_status(
        opening_score=opening_score,
        collector_score=collector_score,
        chase_score=chase_score,
    )

    return {
        "opening_desirability_score": opening_score,
        "opening_desirability_rank": _int_or_none(
            _first_present(row, "opening_desirability_rank", "rip_desirability_rank_70_30")
        ),
        "collector_appeal_score": collector_score,
        "collector_appeal_rank": _int_or_none(
            _first_present(row, "collector_appeal_rank", "pure_desirability_rank")
        ),
        "chase_appeal_score": chase_score,
        "chase_appeal_rank": _int_or_none(
            _first_present(row, "chase_appeal_rank", "monetary_chase_appeal_rank")
        ),
        "chase_appeal_data_quality": chase_quality,
        "display_status": display_status,
        "summary": _summary(display_status),
        "tooltip_copy": dict(TOOLTIP_COPY),
    }


def _display_status(
    *,
    opening_score: Optional[float],
    collector_score: Optional[float],
    chase_score: Optional[float],
) -> str:
    if opening_score is not None and collector_score is not None and chase_score is not None:
        return "scored"
    if collector_score is not None and chase_score is None:
        return "collector_only"
    return "insufficient_chase_data"


def _summary(display_status: str) -> str:
    if display_status == "scored":
        return "Opening Desirability is available with both Collector Appeal and Chase Appeal signals."
    if display_status == "collector_only":
        return MISSING_CHASE_SUMMARY
    return "Opening Desirability needs more collector and chase-card data before a score can be shown."


def _first_present(row: Mapping[str, Any], *fields: str) -> Any:
    for field in fields:
        value = row.get(field)
        if value is not None and value != "":
            return value
    return None


def _score_or_none(value: Any) -> Optional[float]:
    parsed = _float_or_none(value)
    if parsed is None:
        return None
    return max(0.0, min(100.0, parsed))


def _float_or_none(value: Any) -> Optional[float]:
    if value is None or value == "":
        return None
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(parsed):
        return None
    return parsed


def _int_or_none(value: Any) -> Optional[int]:
    parsed = _float_or_none(value)
    if parsed is None:
        return None
    return int(parsed)
