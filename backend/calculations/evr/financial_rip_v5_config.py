"""Authoritative, versioned configuration for Financial RIP V5.

V5 replaces exactly ONE V4 component: ``loss_resilience`` -> ``shortfall_resilience``.
The other five components, their transforms and the 25/20/15/25/10/5 weight
vector are the V4 objects, numerically identical.

WHY (and what this does NOT claim)
----------------------------------
Loss Resilience conditions only on losing outcomes, so turning some losses into
wins can leave it flat or lower it. Shortfall Resilience is an expectation of a
non-increasing loss over ALL outcomes, so a first-order improvement can never
lower it. The 2026 adjudication (docs/research/financial_rip_v5_final_adjudication.md)
approved promotion on CONSTRUCT VALIDITY. It did not find a large ranking
improvement (V4/V5 Financial rank Spearman 0.9976), SR remains ~0.98 correlated
with Typical Retention, and real P(win) never reached the high-win region where
the synthetic plateau benefit was shown. Do not describe V5 more strongly.

FORMULA (frozen; do not retune)
-------------------------------
    R  = X / C
    SR = 100 * [1 - 0.70*E[(1-R)+] - 0.60*E[(0.50-R)+]]
       = 100 * (0.70*CappedRecovery + 0.30*DepthResilience)
"""

from __future__ import annotations

from typing import Any, Dict, Tuple

from backend.calculations.evr.financial_rip_v4_config import (
    FINANCIAL_RIP_V4_COMPONENT_ORDER,
    FINANCIAL_RIP_V4_PUBLIC_COMPONENT_KEYS,
    FINANCIAL_RIP_V4_WEIGHTS,
)

FINANCIAL_RIP_V5_VERSION = "financial_rip_v5_shortfall_resilience_25_20_15_25_10_5"
FINANCIAL_RIP_V5_CONFIG_VERSION = "financial_rip_v5_config_v1"
FINANCIAL_RIP_V5_RESEARCH_CANDIDATE_ID = "FINANCIAL_RIP_V5_CANDIDATE"
FINANCIAL_RIP_V5_SHORTFALL_KEY = "shortfall_resilience"
FINANCIAL_RIP_V5_REPLACED_KEY = "loss_resilience"

# Frozen SR coefficients.
SR_BREAK_EVEN_COEFFICIENT = 0.70   # weight on E[(1-R)+]
SR_DEEP_SHORTFALL_COEFFICIENT = 0.60  # weight on E[(0.50-R)+]
SR_DEEP_THRESHOLD_RATIO = 0.50
SR_CAPPED_RECOVERY_SHARE = 0.70    # equivalent 70/30 form
SR_DEPTH_RESILIENCE_SHARE = 0.30

FINANCIAL_RIP_V5_WEIGHTS: Dict[str, float] = {
    ("shortfall_resilience" if key == "loss_resilience" else key): weight
    for key, weight in FINANCIAL_RIP_V4_WEIGHTS.items()
}
FINANCIAL_RIP_V5_COMPONENT_ORDER: Tuple[str, ...] = tuple(
    FINANCIAL_RIP_V5_SHORTFALL_KEY if key == "loss_resilience" else key
    for key in FINANCIAL_RIP_V4_COMPONENT_ORDER
)
FINANCIAL_RIP_V5_PUBLIC_COMPONENT_KEYS: Dict[str, str] = {
    (FINANCIAL_RIP_V5_SHORTFALL_KEY if key == "loss_resilience" else key): value
    for key, value in FINANCIAL_RIP_V4_PUBLIC_COMPONENT_KEYS.items()
}

#: Component sub-key on a V5 payload that holds the exact sufficient statistics.
FINANCIAL_RIP_V5_RAW_KEYS: Tuple[str, ...] = (
    "outcomeCount", "scoringCost",
    "countBelowCost", "sumBelowCost", "countBelowHalfCost", "sumBelowHalfCost",
    "cappedRecovery", "expectedShortfallToCost", "expectedDeepShortfall",
    "depthResilience", "formula",
)


def financial_rip_v5_weights_payload() -> Dict[str, Any]:
    return {
        "scoreVersion": FINANCIAL_RIP_V5_VERSION,
        "configVersion": FINANCIAL_RIP_V5_CONFIG_VERSION,
        "weights": dict(FINANCIAL_RIP_V5_WEIGHTS),
        "componentOrder": list(FINANCIAL_RIP_V5_COMPONENT_ORDER),
        "publicComponentKeys": dict(FINANCIAL_RIP_V5_PUBLIC_COMPONENT_KEYS),
        "shortfallResilience": {
            "breakEvenCoefficient": SR_BREAK_EVEN_COEFFICIENT,
            "deepShortfallCoefficient": SR_DEEP_SHORTFALL_COEFFICIENT,
            "deepThresholdRatio": SR_DEEP_THRESHOLD_RATIO,
        },
        "researchCandidateId": FINANCIAL_RIP_V5_RESEARCH_CANDIDATE_ID,
        "changeFromV4": (
            "Loss Resilience is replaced by Shortfall Resilience "
            "(100*(1-0.70*E[(1-R)+]-0.60*E[(0.50-R)+])). Five components, "
            "transforms and the 25/20/15/25/10/5 weights are unchanged from V4."
        ),
    }


def _audit_config() -> None:
    if abs(sum(FINANCIAL_RIP_V5_WEIGHTS.values()) - 1.0) > 1e-12:
        raise ValueError("FINANCIAL_RIP_V5_WEIGHTS must sum to 1.0")
    decided = {"true_win_frequency": .25, "typical_retention": .20, "shortfall_resilience": .15,
               "realistic_upside": .25, "jackpot_upside": .10, "base_economic_efficiency": .05}
    if FINANCIAL_RIP_V5_WEIGHTS != decided or tuple(decided) != FINANCIAL_RIP_V5_COMPONENT_ORDER:
        raise ValueError("Financial RIP V5 weights/order differ from the approved 25/20/15/25/10/5")
    if abs(SR_CAPPED_RECOVERY_SHARE * 1 + SR_DEPTH_RESILIENCE_SHARE - 1.0) > 1e-12:
        raise ValueError("SR 70/30 shares must sum to 1")
    if abs(SR_DEPTH_RESILIENCE_SHARE * 2 - SR_DEEP_SHORTFALL_COEFFICIENT) > 1e-12 or \
            abs(SR_BREAK_EVEN_COEFFICIENT - SR_CAPPED_RECOVERY_SHARE) > 1e-12:
        raise ValueError("SR coefficients are internally inconsistent with the frozen formula")


_audit_config()
