"""Financial RIP V5 - production model (Shortfall Resilience replaces Loss Resilience).

Design
------
V5 is V4 with ONE component swapped. The five unchanged components are produced
by the V4 engine (``build_financial_rip_v4``) and copied verbatim, so they are
numerically identical to V4 by construction. Only ``shortfall_resilience`` is
computed here, from exact counts and prefix sums of the prepared distribution
(no price-specific million-outcome vector).

The frozen research candidate (``financial_rip_v5_candidate.py``) is left
untouched as historical evidence; parity with it is asserted in
``test_financial_rip_v5_production.py``.

What V5 does NOT claim (see docs/research/financial_rip_v5_final_adjudication.md)
-------------------------------------------------------------------------------
Approval rested on construct validity: SR is monotone under first-order
improvements; Loss Resilience is not. The practical correction is modest
(V4/V5 Financial rank Spearman 0.9976), SR stays ~0.98 correlated with Typical
Retention, and real P(win) never reached the synthetic high-win regime.

No payload-only V4 -> V5 projection exists, on purpose: V3/V4 payloads do not
carry E[(0.50-R)+]. ``project_financial_rip_v5_from_v4_payload`` fails closed.
A stored V4 row must never be relabelled V5.
"""

from __future__ import annotations

import math
from typing import Any, Dict, List, Mapping, Sequence, Tuple, Union

from backend.calculations.evr.financial_rip_v3 import (
    FinancialRipModelSpec,
    PreparedFinancialRipDistribution,
    validate_financial_rip_payload,
    verify_financial_rip_score,
)
from backend.calculations.evr.financial_rip_v3_config import (
    FINANCIAL_RIP_V3_MIN_SIMULATION_COUNT,
    STATUS_READY,
    STATUS_UNAVAILABLE,
)
from backend.calculations.evr.financial_rip_v4 import (
    FINANCIAL_RIP_V4_SPEC,
    build_financial_rip_v4,
)
from backend.calculations.evr.financial_rip_v4_config import FINANCIAL_RIP_V4_VERSION
from backend.calculations.evr.financial_rip_v5_config import (
    FINANCIAL_RIP_V5_COMPONENT_ORDER,
    FINANCIAL_RIP_V5_CONFIG_VERSION,
    FINANCIAL_RIP_V5_RAW_KEYS,
    FINANCIAL_RIP_V5_REPLACED_KEY,
    FINANCIAL_RIP_V5_SHORTFALL_KEY,
    FINANCIAL_RIP_V5_VERSION,
    FINANCIAL_RIP_V5_WEIGHTS,
    SR_BREAK_EVEN_COEFFICIENT,
    SR_DEEP_SHORTFALL_COEFFICIENT,
    SR_DEEP_THRESHOLD_RATIO,
    financial_rip_v5_weights_payload,
)

FINANCIAL_RIP_V5_SPEC = FinancialRipModelSpec(
    score_version=FINANCIAL_RIP_V5_VERSION,
    normalization_version=FINANCIAL_RIP_V4_SPEC.normalization_version,
    tail_contract_version=FINANCIAL_RIP_V4_SPEC.tail_contract_version,
    config_version=FINANCIAL_RIP_V5_CONFIG_VERSION,
    component_order=FINANCIAL_RIP_V5_COMPONENT_ORDER,
    component_inputs={k: v for k, v in FINANCIAL_RIP_V4_SPEC.component_inputs.items()
                      if k != FINANCIAL_RIP_V5_REPLACED_KEY},
    weights=FINANCIAL_RIP_V5_WEIGHTS,
    weights_payload=financial_rip_v5_weights_payload,
)

SR_FORMULA = "100 * (1 - 0.70*E[(1-R)+] - 0.60*E[(0.50-R)+])"
_V4_LOSS_INPUT_AUDIT_KEYS = ("average_retention_given_loss", "soft_loss_share_given_loss")
_RAW_ROUND = 10
_SR_RECONSTRUCTION_TOLERANCE = 1e-6


def _unavailable(reason: str, detail: str = "", **extra: Any) -> Dict[str, Any]:
    return {
        "scoreVersion": FINANCIAL_RIP_V5_VERSION,
        "normalizationVersion": FINANCIAL_RIP_V5_SPEC.normalization_version,
        "tailContractVersion": FINANCIAL_RIP_V5_SPEC.tail_contract_version,
        "configVersion": FINANCIAL_RIP_V5_CONFIG_VERSION,
        "status": STATUS_UNAVAILABLE,
        "statusReason": reason,
        "statusDetail": detail,
        "rankable": False,
        "score": None,
        "components": {},
        "estimationDiagnostics": dict(extra),
        "audit": {"weights": financial_rip_v5_weights_payload()},
    }


def shortfall_resilience_sufficient_statistics(
    prepared: PreparedFinancialRipDistribution, cost: float
) -> Dict[str, Any]:
    """Exact sufficient statistics for SR, from counts and prefix sums."""
    if (prepared.invalid_reason or not prepared.n or not math.isfinite(cost) or cost <= 0
            or prepared.minimum_base + prepared.value_offset < 0):
        raise ValueError("Shortfall resilience requires finite nonnegative outcomes and positive cost")
    n = int(prepared.n)
    half = SR_DEEP_THRESHOLD_RATIO * cost
    below_cost = int(prepared._count_below(cost))
    below_half = int(prepared._count_below(half))
    sum_cost = float(prepared._sum_first(below_cost))
    sum_half = float(prepared._sum_first(below_half))
    shortfall = (below_cost * cost - sum_cost) / (n * cost)
    deep = (below_half * half - sum_half) / (n * cost)
    return {
        "outcomeCount": n,
        "scoringCost": round(float(cost), 6),
        "countBelowCost": below_cost,
        "sumBelowCost": round(sum_cost, 6),
        "countBelowHalfCost": below_half,
        "sumBelowHalfCost": round(sum_half, 6),
        "cappedRecovery": round(1.0 - shortfall, _RAW_ROUND),
        "expectedShortfallToCost": round(shortfall, _RAW_ROUND),
        "expectedDeepShortfall": round(deep, _RAW_ROUND),
        "depthResilience": round(1.0 - 2.0 * deep, _RAW_ROUND),
        "formula": SR_FORMULA,
    }


def shortfall_resilience_from_raw(raw: Mapping[str, Any]) -> float:
    """SR from persisted raw expectations (no artifact needed)."""
    return 100.0 * (1.0 - SR_BREAK_EVEN_COEFFICIENT * float(raw["expectedShortfallToCost"])
                    - SR_DEEP_SHORTFALL_COEFFICIENT * float(raw["expectedDeepShortfall"]))


def build_financial_rip_v5(
    values: Union[Sequence[float], PreparedFinancialRipDistribution],
    pack_cost: Any,
    *,
    chase_metrics: Mapping[str, Any] = None,
    session_data: Mapping[str, Any] = None,
    min_simulation_count: int = FINANCIAL_RIP_V3_MIN_SIMULATION_COUNT,
) -> Dict[str, Any]:
    """Authoritative Financial RIP V5 result from an exact outcome vector/distribution."""
    prepared = (values if isinstance(values, PreparedFinancialRipDistribution)
                else PreparedFinancialRipDistribution.prepare(values))
    control = build_financial_rip_v4(
        prepared, pack_cost, chase_metrics=chase_metrics, session_data=session_data,
        min_simulation_count=min_simulation_count,
    )
    if control.get("status") != STATUS_READY:
        return _unavailable(str(control.get("statusReason") or "v4_control_unavailable"),
                            str(control.get("statusDetail") or ""))
    if prepared.minimum_base + prepared.value_offset < 0:
        return _unavailable("negative_outcome_value")
    cost = float(control["packCost"])
    # The V4 control rounds cost to 4dp; the research candidate scored with the
    # caller's cost. Use the caller's exact cost for SR, as the frozen candidate does.
    raw = shortfall_resilience_sufficient_statistics(prepared, float(pack_cost))
    sr = round(shortfall_resilience_from_raw(raw), 4)

    components: Dict[str, Any] = {}
    for key in FINANCIAL_RIP_V5_COMPONENT_ORDER:
        if key == FINANCIAL_RIP_V5_SHORTFALL_KEY:
            weight = FINANCIAL_RIP_V5_WEIGHTS[key]
            components[key] = {"score": sr, "weight": weight,
                               "contribution": round(sr * weight, 4),
                               "available": True, "subScores": {}, "raw": raw}
        else:
            components[key] = dict(control["components"][key])
    score = round(sum(components[k]["score"] * FINANCIAL_RIP_V5_WEIGHTS[k]
                      for k in FINANCIAL_RIP_V5_COMPONENT_ORDER), 4)

    audit = dict(control.get("audit") or {})
    audit["weights"] = financial_rip_v5_weights_payload()
    normalized = {k: v for k, v in (audit.get("normalizedInputs") or {}).items()
                  if k not in _V4_LOSS_INPUT_AUDIT_KEYS}
    audit["normalizedInputs"] = normalized
    audit.update({"candidateId": "FINANCIAL_RIP_V5_CANDIDATE",
                  "sourceControlVersion": FINANCIAL_RIP_V4_VERSION})

    result = {**control, "scoreVersion": FINANCIAL_RIP_V5_VERSION,
              "configVersion": FINANCIAL_RIP_V5_CONFIG_VERSION,
              "score": score, "components": components, "audit": audit}
    result.pop("researchOnly", None)
    verification = verify_financial_rip_score(result, spec=FINANCIAL_RIP_V5_SPEC)
    result["audit"]["scoreVerification"] = verification
    if not verification["reconstructed"]:
        raise ValueError(f"{FINANCIAL_RIP_V5_VERSION} score does not reconstruct: {verification}")
    return result


def verify_financial_rip_v5_score(result: Mapping[str, Any]) -> Dict[str, Any]:
    return verify_financial_rip_score(result, spec=FINANCIAL_RIP_V5_SPEC)


def validate_financial_rip_v5_payload(payload: Any) -> Tuple[bool, List[str]]:
    """Structural validator; also rejects V4-shaped components and unreconstructable SR."""
    ok, problems = validate_financial_rip_payload(payload, spec=FINANCIAL_RIP_V5_SPEC)
    problems = list(problems)
    if not isinstance(payload, Mapping):
        return False, problems
    if payload.get("status") != STATUS_READY:
        return (not problems), problems
    components = payload.get("components") or {}
    if FINANCIAL_RIP_V5_REPLACED_KEY in components:
        problems.append("V5 payload must not carry loss_resilience")
    extra = set(components) - set(FINANCIAL_RIP_V5_COMPONENT_ORDER)
    if extra:
        problems.append(f"unexpected components {sorted(extra)}")
    block = components.get(FINANCIAL_RIP_V5_SHORTFALL_KEY)
    raw = (block or {}).get("raw") if isinstance(block, Mapping) else None
    if not isinstance(raw, Mapping):
        return False, problems + ["shortfall_resilience raw block missing"]
    missing = [k for k in FINANCIAL_RIP_V5_RAW_KEYS if k not in raw]
    if missing:
        return False, problems + [f"shortfall_resilience raw missing {missing}"]
    try:
        n, cost = float(raw["outcomeCount"]), float(raw["scoringCost"])
        s1 = (raw["countBelowCost"] * cost - raw["sumBelowCost"]) / (n * cost)
        s2 = (raw["countBelowHalfCost"] * SR_DEEP_THRESHOLD_RATIO * cost
              - raw["sumBelowHalfCost"]) / (n * cost)
        if abs(s1 - raw["expectedShortfallToCost"]) > 1e-8:
            problems.append("expectedShortfallToCost does not match sufficient statistics")
        if abs(s2 - raw["expectedDeepShortfall"]) > 1e-8:
            problems.append("expectedDeepShortfall does not match sufficient statistics")
        if abs(raw["cappedRecovery"] - (1 - s1)) > 1e-8 or \
                abs(raw["depthResilience"] - (1 - 2 * s2)) > 1e-8:
            problems.append("capped recovery/depth resilience inconsistent")
        stored = float(block["score"])
        if abs(shortfall_resilience_from_raw(raw) - stored) > 1e-4 + _SR_RECONSTRUCTION_TOLERANCE:
            problems.append("stored shortfall_resilience does not reconstruct from raw")
    except (TypeError, ValueError, ZeroDivisionError, KeyError):
        problems.append("shortfall_resilience raw block is malformed")
    return (not problems), problems


def project_financial_rip_v5_from_v4_payload(payload: Mapping[str, Any]) -> Dict[str, Any]:
    """Fail closed. V3/V4 payloads lack E[(0.50-R)+]; V4 rows are never relabelled V5."""
    return _unavailable("raw_outcomes_or_exact_prepared_distribution_required")
