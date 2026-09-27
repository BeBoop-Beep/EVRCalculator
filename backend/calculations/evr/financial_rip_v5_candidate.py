"""Research-only Financial RIP V5 shortfall candidate. No canonical wiring."""

from __future__ import annotations

import math
from typing import Any, Mapping, Sequence

import numpy as np

from backend.calculations.evr.financial_rip_v3 import PreparedFinancialRipDistribution
from backend.calculations.evr.financial_rip_v4 import build_financial_rip_v4
from backend.calculations.evr.financial_rip_v4_config import (
    FINANCIAL_RIP_V4_VERSION, FINANCIAL_RIP_V4_WEIGHTS,
)

CANDIDATE_ID = "FINANCIAL_RIP_V5_CANDIDATE"
COMPONENT_KEY = "shortfall_resilience"
WEIGHTS = {
    (COMPONENT_KEY if key == "loss_resilience" else key): weight
    for key, weight in FINANCIAL_RIP_V4_WEIGHTS.items()
}


def shortfall_resilience_direct(values: Sequence[float], cost: float) -> float:
    """Reference formula; intended for tests and bounded research vectors."""
    array = np.asarray(values, dtype=np.float64).ravel()
    if not math.isfinite(cost) or cost <= 0 or not array.size or not np.all(np.isfinite(array)) or np.any(array < 0):
        raise ValueError("Shortfall resilience requires finite nonnegative outcomes and positive cost")
    ratios = array / cost
    return float(100 * (1 - .70 * np.maximum(1 - ratios, 0).mean()
                        - .60 * np.maximum(.50 - ratios, 0).mean()))


def shortfall_resilience_prepared(prepared: PreparedFinancialRipDistribution, cost: float) -> float:
    """Exact threshold counts and prefix sums; no price-specific outcome vector."""
    if (prepared.invalid_reason or not prepared.n or not math.isfinite(cost) or cost <= 0
            or prepared.minimum_base + prepared.value_offset < 0):
        raise ValueError("Shortfall resilience requires finite nonnegative outcomes and positive cost")
    below_cost = prepared._count_below(cost)
    below_half = prepared._count_below(.5 * cost)
    loss_one = (below_cost * cost - prepared._sum_first(below_cost)) / (prepared.n * cost)
    loss_half = (below_half * (.5 * cost) - prepared._sum_first(below_half)) / (prepared.n * cost)
    return float(100 * (1 - .70 * loss_one - .60 * loss_half))


def score_financial_rip_v5_candidate(
    values: Sequence[float] | PreparedFinancialRipDistribution,
    pack_cost: float,
    *,
    chase_metrics: Mapping[str, Any] | None = None,
    session_data: Mapping[str, Any] | None = None,
    min_simulation_count: int = 10000,
) -> dict[str, Any]:
    """Score from outcomes only; the V4 payload alone is insufficient."""
    return score_financial_rip_v5_candidate_with_control(
        values, pack_cost, chase_metrics=chase_metrics, session_data=session_data,
        min_simulation_count=min_simulation_count,
    )[1]


def score_financial_rip_v5_candidate_with_control(
    values: Sequence[float] | PreparedFinancialRipDistribution,
    pack_cost: float,
    *,
    chase_metrics: Mapping[str, Any] | None = None,
    session_data: Mapping[str, Any] | None = None,
    min_simulation_count: int = 10000,
    control_payload: Mapping[str, Any] | None = None,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Research companion returning the unchanged V4 control and V5 payload."""
    prepared = values if isinstance(values, PreparedFinancialRipDistribution) else PreparedFinancialRipDistribution.prepare(values)
    control = (dict(control_payload) if control_payload is not None else
               build_financial_rip_v4(prepared, pack_cost, chase_metrics=chase_metrics,
                                      session_data=session_data,
                                      min_simulation_count=min_simulation_count))
    if control_payload is not None and (
        control.get("scoreVersion") != FINANCIAL_RIP_V4_VERSION
        or control.get("packCost") != round(float(pack_cost), 4)
    ):
        raise ValueError(
            "supplied V4 control does not match candidate cost and version: "
            f"version={control.get('scoreVersion')!r}, cost={control.get('packCost')!r}, "
            f"expectedCost={round(float(pack_cost), 4)!r}"
        )
    result = {**control, "scoreVersion": CANDIDATE_ID, "configVersion": CANDIDATE_ID,
              "researchOnly": True}
    if control["status"] != "ready":
        return control, result
    if prepared.minimum_base + prepared.value_offset < 0:
        return control, {"scoreVersion": CANDIDATE_ID, "researchOnly": True,
                "status": "unavailable", "statusReason": "negative_outcome_value",
                "rankable": False, "score": None}
    sr = shortfall_resilience_prepared(prepared, float(pack_cost))
    components = {key: dict(block) for key, block in control["components"].items()
                  if key != "loss_resilience"}
    components[COMPONENT_KEY] = {
        "score": round(sr, 4), "weight": .15, "contribution": round(round(sr, 4) * .15, 4),
        "available": True, "subScores": {},
        "raw": {"cappedRecovery": round(1 - (prepared._count_below(pack_cost) * pack_cost
                    - prepared._sum_first(prepared._count_below(pack_cost))) / (prepared.n * pack_cost), 10),
                "formula": "100 * (1 - 0.70*E[(1-R)+] - 0.60*E[(0.50-R)+])"},
    }
    result["components"] = components
    result["score"] = round(sum(components[key]["score"] * weight for key, weight in WEIGHTS.items()), 4)
    result["audit"] = {"candidateId": CANDIDATE_ID, "weights": dict(WEIGHTS),
                       "sourceControlVersion": control["scoreVersion"]}
    return control, result


def project_financial_rip_v5_from_payload(payload: Mapping[str, Any]) -> dict[str, Any]:
    """Fail closed: V3/V4 aggregates omit the depth below half of cost."""
    return {"scoreVersion": CANDIDATE_ID, "researchOnly": True, "status": "unavailable",
            "statusReason": "raw_outcomes_or_exact_prepared_distribution_required",
            "rankable": False, "score": None}
