"""Authoritative, versioned configuration for Financial RIP V4.

WHAT V4 CHANGES, AND WHAT IT DELIBERATELY DOES NOT
--------------------------------------------------
V4 changes ONE thing relative to V3: the definition of Realistic Upside.

    V3  realistic_upside = 0.40 * p95_threshold_ratio
                         + 0.60 * realistic_tail_mean_ratio
    V4  realistic_upside = 1.00 * p95_threshold_ratio

The P95-P99 conditional-mean contribution is REMOVED. Nothing else moves. In
particular V4 re-uses V3 objects, by import rather than by copy, for:

  * the six top-level weights (25/20/15/25/10/5 - unchanged, and Realistic
    Upside retains its full 25% influence),
  * every normalization transform, anchor and knot, including the
    ``p95_threshold_ratio`` piecewise-linear transform itself,
  * the P95 interpolation (``numpy.percentile`` linear interpolation, applied in
    ``compute_realistic_upside_raw``),
  * True Win Frequency, Typical Retention, Loss Resilience, Jackpot Upside and
    Base Economic Efficiency, and their sub-weights,
  * the empirical rank-exact tail contract,
  * the minimum simulation count and the whole status vocabulary.

Because the transforms and anchors are literally the V3 objects, the
``normalizationVersion`` and ``tailContractVersion`` V4 stamps are the V3
strings. That is not an oversight: a DIFFERENT normalization version string would
assert a change to the anchors that did not happen, and the contract tests would
then be unable to prove the anchors are shared. ``scoreVersion`` is what
separates a V4 row from a V3 row, and it is distinct.

WHY P95-ONLY
------------
See the Financial RIP V4 decision record (2026-08-18). In short: the V3 Realistic
Upside definition was the primary source of the questionable matched-capital
decisions found by the audit. On the August 17 development authority, at 25%
influence, the P95-only definition:

  * cut Layer-1 matched-capital inversions from 15 to 8 across 5,796 comparisons
    at the 5% tolerance (3 at the 2% tolerance),
  * cut Realistic/Jackpot correlation from ~0.790 to ~0.530,
  * preserved ~101.1% of reachable-upside positive-control separation,
  * produced no Layer-2, Layer-3 or Layer-4 defects and no top-strategy changes.

The 20%-influence variant removed four further inversions but retained only
~77.9% of the reachable-upside separation, with no material behavioral
advantage. Realistic Upside therefore keeps its 25% weight.

V4 IS A NEW VERSION, NOT A MUTATION OF V3
-----------------------------------------
V3 remains fully computable and its stored rows remain reproducible. Nothing in
this module edits a V3 object; ``FINANCIAL_RIP_V4_WEIGHTS`` is an independent
copy so a future divergence in one cannot be read through the other.
"""

from __future__ import annotations

from typing import Any, Dict, Tuple

from backend.calculations.evr.financial_rip_v3_config import (
    FINANCIAL_RIP_V3_COMPONENT_INPUTS,
    FINANCIAL_RIP_V3_COMPONENT_ORDER,
    FINANCIAL_RIP_V3_MIN_SIMULATION_COUNT,
    FINANCIAL_RIP_V3_NORMALIZATION_VERSION,
    FINANCIAL_RIP_V3_PUBLIC_COMPONENT_KEYS,
    FINANCIAL_RIP_V3_TAIL_CONTRACT_VERSION,
    FINANCIAL_RIP_V3_TRANSFORMS,
    FINANCIAL_RIP_V3_WEIGHTS,
    JACKPOT_UPSIDE_SUBWEIGHTS,
    LOSS_RESILIENCE_SUBWEIGHTS,
)

# ---------------------------------------------------------------------------
# Version identifiers
# ---------------------------------------------------------------------------
# Distinct from every existing identifier, and self-describing: the model, the
# Realistic Upside definition and the weight vector are all readable from the
# string, so a stored row stays interpretable without this module.

FINANCIAL_RIP_V4_VERSION = "financial_rip_v4_outcome_profile_p95_only_25_20_15_25_10_5"
FINANCIAL_RIP_V4_CONFIG_VERSION = "financial_rip_v4_config_v1"

# Shared with V3 BY VALUE because they are shared IN FACT. See the module
# docstring: V4 does not move an anchor, a knot or a tail rule.
FINANCIAL_RIP_V4_NORMALIZATION_VERSION = FINANCIAL_RIP_V3_NORMALIZATION_VERSION
FINANCIAL_RIP_V4_TAIL_CONTRACT_VERSION = FINANCIAL_RIP_V3_TAIL_CONTRACT_VERSION

# The research identifier of the frozen candidate this configuration implements.
# Production V4 must reproduce that candidate exactly; see
# ``backend/scripts/research_financial_rip_v4_parity.py``.
FINANCIAL_RIP_V4_RESEARCH_CANDIDATE_ID = "P95_ONLY_25"
FINANCIAL_RIP_V4_RESEARCH_AUTHORITY_DATE = "2026-08-17"


# ---------------------------------------------------------------------------
# Weights
# ---------------------------------------------------------------------------
# Numerically identical to the V3 table, and held as an independent copy on
# purpose: the decision record fixes 25/20/15/25/10/5 for V4 specifically, and a
# later change to the V3 table (which must not happen, but is the failure this
# guards) must not silently become a change to V4.

FINANCIAL_RIP_V4_WEIGHTS: Dict[str, float] = {
    "true_win_frequency": 0.25,
    "typical_retention": 0.20,
    "loss_resilience": 0.15,
    "realistic_upside": 0.25,
    "jackpot_upside": 0.10,
    "base_economic_efficiency": 0.05,
}

FINANCIAL_RIP_V4_COMPONENT_ORDER: Tuple[str, ...] = FINANCIAL_RIP_V3_COMPONENT_ORDER
FINANCIAL_RIP_V4_PUBLIC_COMPONENT_KEYS: Dict[str, str] = dict(
    FINANCIAL_RIP_V3_PUBLIC_COMPONENT_KEYS
)

# THE ONE SUBSTANTIVE CHANGE.
#
# ``realistic_tail_mean_ratio`` is no longer an input to the score. It is still
# COMPUTED and still DISCLOSED in the raw block of the component - a reader is
# still told what a good pack actually pays - it simply carries zero weight,
# exactly as ``hard_loss_probability`` has always been disclosed-but-unweighted
# inside Loss Resilience.
REALISTIC_UPSIDE_SUBWEIGHTS_V4: Dict[str, float] = {
    "p95_threshold_ratio": 1.0,
}

FINANCIAL_RIP_V4_COMPONENT_INPUTS: Dict[str, Dict[str, float]] = {
    **{
        component: dict(inputs)
        for component, inputs in FINANCIAL_RIP_V3_COMPONENT_INPUTS.items()
    },
    "realistic_upside": dict(REALISTIC_UPSIDE_SUBWEIGHTS_V4),
}

# Disclosed-but-unweighted raw inputs, per component. Declared as data so the
# audit payload and the contract tests read one table instead of two lists.
FINANCIAL_RIP_V4_UNWEIGHTED_DISCLOSURES: Dict[str, Tuple[str, ...]] = {
    "loss_resilience": ("hard_loss_probability",),
    "realistic_upside": ("realistic_tail_mean_ratio",),
}

CANONICAL_FINANCIAL_RIP_V4_VERSION = FINANCIAL_RIP_V4_VERSION


def financial_rip_v4_weights_payload() -> Dict[str, Any]:
    """The published, self-describing V4 weight and version disclosure."""
    return {
        "scoreVersion": FINANCIAL_RIP_V4_VERSION,
        "normalizationVersion": FINANCIAL_RIP_V4_NORMALIZATION_VERSION,
        "tailContractVersion": FINANCIAL_RIP_V4_TAIL_CONTRACT_VERSION,
        "configVersion": FINANCIAL_RIP_V4_CONFIG_VERSION,
        "weights": dict(FINANCIAL_RIP_V4_WEIGHTS),
        "subWeights": {
            "lossResilience": dict(LOSS_RESILIENCE_SUBWEIGHTS),
            "realisticUpside": dict(REALISTIC_UPSIDE_SUBWEIGHTS_V4),
            "jackpotUpside": dict(JACKPOT_UPSIDE_SUBWEIGHTS),
        },
        "publicComponentKeys": dict(FINANCIAL_RIP_V4_PUBLIC_COMPONENT_KEYS),
        "componentOrder": list(FINANCIAL_RIP_V4_COMPONENT_ORDER),
        "minimumSimulationCount": FINANCIAL_RIP_V3_MIN_SIMULATION_COUNT,
        "unweightedDisclosures": {
            component: list(metrics)
            for component, metrics in FINANCIAL_RIP_V4_UNWEIGHTED_DISCLOSURES.items()
        },
        "changeFromV3": (
            "Realistic Upside is the normalized P95 threshold-to-cost ratio alone. "
            "The P95-P99 conditional-mean contribution is removed; the metric "
            "remains disclosed and unweighted. Every other component, transform, "
            "anchor, tail rule and weight is unchanged from Financial RIP V3."
        ),
        "researchCandidateId": FINANCIAL_RIP_V4_RESEARCH_CANDIDATE_ID,
        "researchAuthorityDate": FINANCIAL_RIP_V4_RESEARCH_AUTHORITY_DATE,
        "temporalValidationStatus": "none_independent_temporal_validation_at_promotion",
    }


def _audit_config() -> None:
    """Fail at import, not at score time, on an internally inconsistent config."""
    total = sum(FINANCIAL_RIP_V4_WEIGHTS.values())
    if abs(total - 1.0) > 1e-12:
        raise ValueError(f"FINANCIAL_RIP_V4_WEIGHTS must sum to 1.0; got {total!r}.")

    if tuple(FINANCIAL_RIP_V4_WEIGHTS) != FINANCIAL_RIP_V4_COMPONENT_ORDER:
        raise ValueError("FINANCIAL_RIP_V4_WEIGHTS must be declared in component order.")

    # The decision record fixes these six numbers. Restating them here as an
    # assertion makes a typo in the table above an import-time failure rather
    # than a silently mis-weighted leaderboard.
    decided = {
        "true_win_frequency": 0.25,
        "typical_retention": 0.20,
        "loss_resilience": 0.15,
        "realistic_upside": 0.25,
        "jackpot_upside": 0.10,
        "base_economic_efficiency": 0.05,
    }
    if FINANCIAL_RIP_V4_WEIGHTS != decided:
        raise ValueError(
            "FINANCIAL_RIP_V4_WEIGHTS does not match the weights fixed by the "
            "Financial RIP V4 decision record (25/20/15/25/10/5)."
        )

    if REALISTIC_UPSIDE_SUBWEIGHTS_V4 != {"p95_threshold_ratio": 1.0}:
        raise ValueError(
            "V4 Realistic Upside must be the P95 threshold ratio alone at weight "
            "1.0. Any other table is a different model."
        )

    for component, inputs in FINANCIAL_RIP_V4_COMPONENT_INPUTS.items():
        if component != "realistic_upside":
            if inputs != FINANCIAL_RIP_V3_COMPONENT_INPUTS[component]:
                raise ValueError(
                    f"V4 component {component!r} must be identical to V3; only "
                    "Realistic Upside changes."
                )
        sub_total = sum(inputs.values())
        if abs(sub_total - 1.0) > 1e-12:
            raise ValueError(
                f"V4 sub-weights for {component!r} must sum to 1.0; got {sub_total!r}."
            )
        for metric in inputs:
            if metric not in FINANCIAL_RIP_V3_TRANSFORMS:
                raise ValueError(
                    f"V4 input {metric!r} has no normalization transform. V4 "
                    "introduces no new raw metric."
                )

    if FINANCIAL_RIP_V4_WEIGHTS is FINANCIAL_RIP_V3_WEIGHTS:
        raise ValueError(
            "FINANCIAL_RIP_V4_WEIGHTS must be an independent object from the V3 table."
        )


_audit_config()
