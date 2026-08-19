"""Financial RIP V4 - the outcome-profile engine under the V4 spec.

There is deliberately no engine code in this module.

V4 differs from V3 in exactly one respect: the Realistic Upside component reads
the normalized P95 threshold-to-cost ratio alone, with no P95-P99
conditional-mean contribution. Everything else - tail selection, the six raw
metric blocks, every transform and anchor, the P95 interpolation, contribution
reconstruction, the disclosure payload, the status vocabulary - is shared with
V3, so it is EXECUTED by the shared engine in
``backend.calculations.evr.financial_rip_v3`` rather than copied here.

A forked engine would be two implementations of one set of percentile mechanics,
free to drift apart silently while both claiming to implement the same tail
contract. The spec object is how the two versions differ in DATA instead.

Reproducibility: V3 is untouched. ``build_financial_rip_v3`` and every V3 stored
row keep working exactly as before, and both builders can be run over the same
outcome vector in the same process.

Research parity: the frozen research candidate ``P95_ONLY_25`` scored a product
as ``sum(w[k] * component[k])`` over the V3 component scores, with the Realistic
Upside score replaced by ``normalize_metric("p95_threshold_ratio", p95Ratio)``
and the V3 weight vector. Because this module runs the same engine with
``p95_threshold_ratio`` at sub-weight 1.0 and the same weights, production V4
reproduces that candidate identically rather than approximately. The property is
asserted directly by
``backend/tests/unit/calculations/test_financial_rip_v4_research_parity.py``.
"""

from __future__ import annotations

from typing import Any, Dict, List, Mapping, Sequence, Tuple

from backend.calculations.evr.financial_rip_v3 import (
    FinancialRipModelSpec,
    build_financial_rip,
    validate_financial_rip_payload,
    verify_financial_rip_score,
)
from backend.calculations.evr.financial_rip_v3_config import (
    FINANCIAL_RIP_V3_MIN_SIMULATION_COUNT,
    FINANCIAL_RIP_V3_VERSION,
    STATUS_READY,
    STATUS_UNAVAILABLE,
    normalize_metric,
)
from backend.calculations.evr.financial_rip_v4_config import (
    FINANCIAL_RIP_V4_COMPONENT_INPUTS,
    FINANCIAL_RIP_V4_COMPONENT_ORDER,
    FINANCIAL_RIP_V4_CONFIG_VERSION,
    FINANCIAL_RIP_V4_NORMALIZATION_VERSION,
    FINANCIAL_RIP_V4_TAIL_CONTRACT_VERSION,
    FINANCIAL_RIP_V4_VERSION,
    FINANCIAL_RIP_V4_WEIGHTS,
    financial_rip_v4_weights_payload,
)

FINANCIAL_RIP_V4_SPEC = FinancialRipModelSpec(
    score_version=FINANCIAL_RIP_V4_VERSION,
    normalization_version=FINANCIAL_RIP_V4_NORMALIZATION_VERSION,
    tail_contract_version=FINANCIAL_RIP_V4_TAIL_CONTRACT_VERSION,
    config_version=FINANCIAL_RIP_V4_CONFIG_VERSION,
    component_order=FINANCIAL_RIP_V4_COMPONENT_ORDER,
    component_inputs=FINANCIAL_RIP_V4_COMPONENT_INPUTS,
    weights=FINANCIAL_RIP_V4_WEIGHTS,
    weights_payload=financial_rip_v4_weights_payload,
)


def build_financial_rip_v4(
    values: Sequence[float],
    pack_cost: Any,
    *,
    chase_metrics: Mapping[str, Any] = None,
    session_data: Mapping[str, Any] = None,
    min_simulation_count: int = FINANCIAL_RIP_V3_MIN_SIMULATION_COUNT,
) -> Dict[str, Any]:
    """Build the complete, authoritative Financial RIP V4 result for one run.

    Same inputs, same guarantees and same JSON-safe output shape as
    ``build_financial_rip_v3``; only the Realistic Upside definition and the
    stamped ``scoreVersion``/``configVersion`` differ.

    The Realistic Upside raw block is unchanged, so ``realisticTailMeanRatio``
    and ``realisticTailMeanValue`` are still disclosed. They simply no longer
    appear in ``subScores`` for that component, because a sub-score is a
    weighted input and this metric now has no weight.
    """
    return build_financial_rip(
        values,
        pack_cost,
        spec=FINANCIAL_RIP_V4_SPEC,
        chase_metrics=chase_metrics,
        session_data=session_data,
        min_simulation_count=min_simulation_count,
    )


def project_financial_rip_v4_from_v3_payload(payload: Mapping[str, Any]) -> Dict[str, Any]:
    """Re-project a PERSISTED Financial RIP V3 payload into Financial RIP V4.

    WHY THIS IS EXACT AND NOT AN APPROXIMATION
    ------------------------------------------
    V4 differs from V3 in one component, and that component's V4 value is a
    deterministic function of a number the V3 payload already carries:

        realistic_upside(V4) = normalize_metric("p95_threshold_ratio", p95Ratio)

    The remaining five component scores are identical between the two models by
    construction, and the weights are identical. So the whole V4 score is
    recoverable from a stored V3 payload with no re-simulation, no outcome
    vector, and no reconstruction of anything that was not persisted. This is
    the same derivation the frozen research candidate used.

    This exists because the set and pack surfaces score from PERSISTED payloads
    rather than from live vectors. It is deliberately NOT how the sealed-product
    path builds V4 - that path holds the real outcome vector and runs the engine
    over it, which is strictly better and is what ``build_financial_rip_v4``
    does.

    A payload that is not a ready V3 payload, or that lacks the P95 ratio,
    yields an explicit unavailable object. Nothing is substituted or guessed.
    """
    if not isinstance(payload, Mapping) or not payload:
        return _projection_unavailable("no_source_payload")
    if payload.get("scoreVersion") != FINANCIAL_RIP_V3_VERSION:
        return _projection_unavailable(
            "source_payload_is_not_financial_rip_v3",
            sourceScoreVersion=payload.get("scoreVersion"),
        )
    if payload.get("status") != STATUS_READY:
        return _projection_unavailable(
            "source_payload_not_ready", sourceStatus=payload.get("status")
        )

    source_components = payload.get("components") or {}
    realistic_raw = dict((source_components.get("realistic_upside") or {}).get("raw") or {})
    p95_ratio = realistic_raw.get("p95ThresholdRatio")
    record = normalize_metric("p95_threshold_ratio", p95_ratio)
    if record.get("score") is None:
        return _projection_unavailable(
            "source_payload_has_no_p95_threshold_ratio", p95ThresholdRatio=p95_ratio
        )

    components: Dict[str, Any] = {}
    for key in FINANCIAL_RIP_V4_COMPONENT_ORDER:
        source = dict(source_components.get(key) or {})
        weight = FINANCIAL_RIP_V4_WEIGHTS[key]
        if key == "realistic_upside":
            score = round(float(record["score"]), 4)
            sub_scores = {
                "p95_threshold_ratio": {
                    "score": score,
                    "raw": record["raw"],
                    "subWeight": 1.0,
                    "clipped": record["clipped"],
                }
            }
        else:
            score = source.get("score")
            sub_scores = dict(source.get("subScores") or {})
        if score is None:
            return _projection_unavailable(
                "source_payload_missing_component_score", missingComponent=key
            )
        components[key] = {
            "score": score,
            "weight": weight,
            "contribution": round(float(score) * weight, 4),
            "available": bool(source.get("available", True)),
            "subScores": sub_scores,
            "raw": dict(source.get("raw") or {}),
        }

    score = max(
        0.0,
        min(
            100.0,
            sum(
                float(components[key]["score"]) * FINANCIAL_RIP_V4_WEIGHTS[key]
                for key in FINANCIAL_RIP_V4_COMPONENT_ORDER
            ),
        ),
    )

    result: Dict[str, Any] = {
        "scoreVersion": FINANCIAL_RIP_V4_VERSION,
        "normalizationVersion": FINANCIAL_RIP_V4_NORMALIZATION_VERSION,
        "tailContractVersion": FINANCIAL_RIP_V4_TAIL_CONTRACT_VERSION,
        "configVersion": FINANCIAL_RIP_V4_CONFIG_VERSION,
        "status": STATUS_READY,
        "statusReason": None,
        "rankable": True,
        "score": round(score, 4),
        "packCost": payload.get("packCost"),
        "components": components,
        "depthAndRobustness": dict(payload.get("depthAndRobustness") or {}),
        "distributionDisclosures": dict(payload.get("distributionDisclosures") or {}),
        "sessionOpeningProfile": payload.get("sessionOpeningProfile"),
        "audit": {
            "weights": financial_rip_v4_weights_payload(),
            "derivation": {
                "method": "reprojected_from_persisted_financial_rip_v3_payload",
                "sourceScoreVersion": FINANCIAL_RIP_V3_VERSION,
                "isExact": True,
                "note": (
                    "Only Realistic Upside is recomputed, from the P95 "
                    "threshold-to-cost ratio the source payload already carries. "
                    "No simulation is re-run and no unpersisted quantity is "
                    "reconstructed."
                ),
            },
        },
    }
    result["audit"]["scoreVerification"] = verify_financial_rip_v4_score(result)
    return result


def _projection_unavailable(reason: str, **extra: Any) -> Dict[str, Any]:
    """An honest unavailable V4 projection. No score, no neutral substitute."""
    return {
        "scoreVersion": FINANCIAL_RIP_V4_VERSION,
        "normalizationVersion": FINANCIAL_RIP_V4_NORMALIZATION_VERSION,
        "tailContractVersion": FINANCIAL_RIP_V4_TAIL_CONTRACT_VERSION,
        "configVersion": FINANCIAL_RIP_V4_CONFIG_VERSION,
        "status": STATUS_UNAVAILABLE,
        "statusReason": reason,
        "rankable": False,
        "score": None,
        "components": {},
        "depthAndRobustness": {},
        "distributionDisclosures": {},
        "sessionOpeningProfile": None,
        "estimationDiagnostics": dict(extra),
        "audit": {"weights": financial_rip_v4_weights_payload()},
    }


def verify_financial_rip_v4_score(result: Mapping[str, Any]) -> Dict[str, Any]:
    """V4 binding of the contribution-reconstruction check."""
    return verify_financial_rip_score(result, spec=FINANCIAL_RIP_V4_SPEC)


def validate_financial_rip_v4_payload(payload: Any) -> Tuple[bool, List[str]]:
    """V4 binding of the structural payload validator."""
    return validate_financial_rip_payload(payload, spec=FINANCIAL_RIP_V4_SPEC)
