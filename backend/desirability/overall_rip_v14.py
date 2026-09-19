"""Overall RIP V14 = 0.86*Financial V5 + 0.04*ChaseAccessibilityScore(k) + 0.10*Collector V5.

Controlled substitution of Financial V4 -> V5 in Overall V12. Fails closed: each
pillar must carry its exact required version, nothing is renormalized and there
is no fallback to Financial V4 / Overall V12. Registered but NOT canonical.
"""

from __future__ import annotations

from typing import Any, Dict, List

from backend.desirability.chase_accessibility_overall_score import (
    CHASE_ACCESSIBILITY_OVERALL_SCORE_K,
    chase_accessibility_overall_score,
)
from backend.desirability.scoring_config import (
    OVERALL_RIP_V14_EFFECTIVE_WEIGHTS,
    OVERALL_RIP_V14_REQUIRED_FINANCIAL_VERSION,
    OVERALL_RIP_V14_VERSION,
    OVERALL_RIP_V14_WEIGHTS,
    overall_rip_v14_required_chase_accessibility_version,
    overall_rip_v14_required_collector_appeal_version,
)
from backend.desirability.weighted_rip import _as_float


def _refuse(reason: str, **extra: Any) -> Dict[str, Any]:
    return {"score": None, "version": OVERALL_RIP_V14_VERSION,
            "status": "unavailable_missing_input", "statusReason": reason,
            "components": {}, "weights": dict(OVERALL_RIP_V14_WEIGHTS),
            "rankable": False, **extra}


def compute_overall_rip_v14(
    financial_rip_v5_score: Any,
    chase_accessibility_raw: Any,
    collector_appeal_v5_score: Any,
    *,
    financial_version: str,
    chase_accessibility_version: str,
    collector_appeal_version: str,
    accessibility_k: float = CHASE_ACCESSIBILITY_OVERALL_SCORE_K,
) -> Dict[str, Any]:
    """Versions are keyword-required so a caller cannot pass a V4 score unlabelled."""
    expected = {
        "financial_rip_v5": (financial_version, OVERALL_RIP_V14_REQUIRED_FINANCIAL_VERSION),
        "chase_accessibility_v1": (chase_accessibility_version,
                                   overall_rip_v14_required_chase_accessibility_version()),
        "collector_appeal_v5": (collector_appeal_version,
                                overall_rip_v14_required_collector_appeal_version()),
    }
    wrong = [name for name, (got, want) in expected.items() if got != want]
    if wrong:
        return _refuse("Overall RIP V14 requires exact input versions; mismatched: "
                       + ", ".join(wrong) + ". No fallback to Financial V4 / Overall V12.",
                       mismatchedInputVersions=wrong)
    financial = _as_float(financial_rip_v5_score)
    access = chase_accessibility_overall_score(chase_accessibility_raw, k=accessibility_k)
    appeal = _as_float(collector_appeal_v5_score)
    missing: List[str] = [n for n, v in (("financial_rip_v5", financial),
                                          ("chase_accessibility_v1", access),
                                          ("collector_appeal_v5", appeal)) if v is None]
    if missing:
        return _refuse("Overall RIP V14 missing: " + ", ".join(missing)
                       + ". No pillar is renormalized.", missingInputs=missing)
    w = OVERALL_RIP_V14_WEIGHTS
    parts = {"financial": w["financial_rip"] * financial,
             "access": w["chase_accessibility"] * access,
             "appeal": w["collector_appeal"] * appeal}
    score = max(0.0, min(100.0, sum(parts.values())))
    return {
        "score": round(score, 4), "version": OVERALL_RIP_V14_VERSION, "status": "ready",
        "components": {
            "financialRipV5": {"score": round(financial, 4), "weight": round(w["financial_rip"], 6),
                               "contribution": round(parts["financial"], 4)},
            "chaseAccessibility": {"raw": _as_float(chase_accessibility_raw),
                                   "score": round(access, 4),
                                   "weight": round(w["chase_accessibility"], 6),
                                   "contribution": round(parts["access"], 4),
                                   "transformK": accessibility_k},
            "collectorAppeal": {"score": round(appeal, 4), "weight": round(w["collector_appeal"], 6),
                                "contribution": round(parts["appeal"], 4)},
        },
        "weights": dict(w), "effectiveWeights": dict(OVERALL_RIP_V14_EFFECTIVE_WEIGHTS),
        "formula": ("0.86 * financial_rip_v5 + 0.04 * chase_accessibility_overall_score(k=0.002) "
                    "+ 0.10 * collector_appeal_v5"),
        "rankable": True,
    }
