"""Authoritative, versioned scoring-weight configuration.

Every weight and threshold in the universal-desirability + weighted-RIP
architecture lives here, in one place, as a *parameter*. Nothing in this file
is an empirically optimized truth: each value is a **reasoned default** chosen
by judgment, labeled as such, and expected to be adjustable (including by a
future per-user weight customizer) without touching scoring code.

Hard rule carried by this module's design: RIP pillar weights are a value
judgment about what matters when opening a set. They are NEVER fitted to, or
selected by, correlation with price or set value. Doing so would turn RIP into
a price predictor and destroy its differentiation.
"""

from __future__ import annotations

from typing import Dict, Iterable, Mapping, Optional


# ---------------------------------------------------------------------------
# Version identifiers
# ---------------------------------------------------------------------------

RIP_V3_VERSION = "rip_v3_weighted_four_component"
# The legacy four-pillar blend's version, retained ONLY so stored rows written
# under it remain identifiable. Nothing computes under it any more.
FINANCIAL_RIP_V2_LEGACY_VERSION = "financial_rip_v2"
FINANCIAL_RIP_V2_VERSION = "financial_rip_v2_60_25_15"
# SUPERSEDED. Overall RIP v3 was Financial RIP + a bounded, capped Universal Set
# Desirability adjustment. It is retained ONLY so any stored row written under it
# remains identifiable. Nothing computes under it any more - see
# OVERALL_RIP_V4_VERSION below and compute_overall_rip.
OVERALL_RIP_V3_VERSION = "overall_rip_v3_financial_plus_universal_desirability"
# The shipping Overall RIP: a weighted blend of Financial RIP and the CA7 Opening
# Desirability score, with NO cap and NO additive adjustment. Universal Set
# Desirability enters Overall RIP ONLY through CA7 (which consumes it as its D
# base), never separately - see OVERALL_RIP_WEIGHTS and compute_overall_rip.
OVERALL_RIP_V4_VERSION = "overall_rip_v4_90_financial_10_ca7"
UNIVERSAL_SET_DESIRABILITY_VERSION = "universal_set_desirability_v3"
UNIVERSAL_ELIGIBILITY_POLICY_VERSION = "universal_desirability_eligibility_v2"
SIMULATION_OPENING_DETAILS_VERSION = "simulation_opening_details_v1"
SCORING_CONFIG_VERSION = "scoring_config_v1"

WEIGHTS_DISCLOSURE = (
    "Reasoned default weighting - a judgment call about what matters when "
    "opening a set, not an empirically optimized or 'correct' value."
)


# ---------------------------------------------------------------------------
# Financial RIP weights
# ---------------------------------------------------------------------------
# Financial RIP = 0.60*Profit + 0.25*Safety + 0.15*Stability
#
# These sum to exactly 1.00 over the three simulation pillars, so there is no
# renormalization step and the published weight IS the applied weight. That was
# not true before: the previous model carried a fourth desirability pillar at
# 0.10, and excluding it renormalized 0.58/0.20/0.12 to 0.644/0.222/0.133 - so
# the number shown as "58%" was never the number applied.
#
# Desirability is deliberately NOT a weight here. It enters Overall RIP as a
# bounded ADDITIVE adjustment instead (see below), because blending a
# price-independent popularity score into a weighted average of financial
# outcomes silently converts it into a financial claim.

FINANCIAL_RIP_WEIGHTS: Dict[str, float] = {
    "profit": 0.60,
    "safety": 0.25,
    "stability": 0.15,
}

FINANCIAL_PILLARS = ("profit", "safety", "stability")

# Retained for the legacy four-pillar helpers and the report-only sensitivity
# study. NOT the shipping model - see FINANCIAL_RIP_WEIGHTS.
DEFAULT_RIP_WEIGHTS: Dict[str, float] = {
    "profit": 0.58,
    "safety": 0.20,
    "stability": 0.12,
    "desirability": 0.10,
}


# ---------------------------------------------------------------------------
# Overall RIP: a weighted blend of Financial RIP and CA7 Opening Desirability
# ---------------------------------------------------------------------------
#   Overall RIP = 0.90 * Financial RIP + 0.10 * Opening Desirability (CA7)
#
# Effective final weights, since Financial RIP is itself 0.60/0.25/0.15:
#   Profit               0.54
#   Safety               0.225
#   Stability            0.135
#   Opening Desirability 0.10
#
# There is NO cap, NO recentering, and NO additive +/-3/+/-5 adjustment. A set
# may move many points on Overall RIP relative to Financial RIP because of
# desirability, and that is intentional: Financial RIP and Overall RIP are both
# published side by side, so the reader can always see the financial-only number.
#
# CA7 (Opening Desirability) already consumes Universal Set Desirability as its D
# base, so Universal Set Desirability enters Overall RIP EXACTLY ONCE, through
# CA7. It is never added to Overall RIP a second time.

OVERALL_RIP_WEIGHTS: Dict[str, float] = {
    "financial_rip": 0.90,
    "opening_desirability": 0.10,
}

# The effective per-input weights after expanding Financial RIP's 60/25/15. Held
# here so presentation surfaces read one authoritative source rather than each
# re-deriving 0.90 * 0.60 = 0.54 and risking drift.
OVERALL_RIP_EFFECTIVE_WEIGHTS: Dict[str, float] = {
    "profit": OVERALL_RIP_WEIGHTS["financial_rip"] * FINANCIAL_RIP_WEIGHTS["profit"],
    "safety": OVERALL_RIP_WEIGHTS["financial_rip"] * FINANCIAL_RIP_WEIGHTS["safety"],
    "stability": OVERALL_RIP_WEIGHTS["financial_rip"] * FINANCIAL_RIP_WEIGHTS["stability"],
    "opening_desirability": OVERALL_RIP_WEIGHTS["opening_desirability"],
}

# ---------------------------------------------------------------------------
# SUPERSEDED capped-adjustment constants (NOT used by scoring)
# ---------------------------------------------------------------------------
# These described the retired Overall RIP v3 additive-adjustment model
# (clamp((D - 50) / 10, -cap, +cap)). They are retained ONLY so the historical
# cap-selection research (backend/scripts/build_desirability_cap_study.py) and any
# stored v3 row remain identifiable. NOTHING in the authoritative scoring path
# reads them any more - Overall RIP is now the OVERALL_RIP_WEIGHTS blend above.
DESIRABILITY_ADJUSTMENT_BASELINE = 50.0
DESIRABILITY_ADJUSTMENT_DIVISOR = 10.0
DESIRABILITY_ADJUSTMENT_CAP = 3.0
DESIRABILITY_ADJUSTMENT_CAP_CANDIDATES = (3.0, 5.0)


# ---------------------------------------------------------------------------
# Universal Set Desirability component weights (Phase 6)
# ---------------------------------------------------------------------------
# Special Pack Appeal is not universally available (it needs pack-mechanic
# config, a simulation-flavored input), so the prior 30/25/35 intent is
# renormalized across 90 into exact fractions.

UNIVERSAL_COMPONENT_WEIGHTS: Dict[str, float] = {
    "chase_subject_strength": 30.0 / 90.0,   # 33.333%
    "chase_subject_depth": 25.0 / 90.0,      # 27.778%
    "favorite_hit_coverage": 35.0 / 90.0,    # 38.889%
}

# Chase Subject Strength slot weights over the top-3 distinct subjects.
# Missing slots renormalize over the available weights (never insert zero).
CHASE_STRENGTH_SLOT_WEIGHTS = (0.50, 0.30, 0.20)

# Chase Subject Depth: effective-subject-count saturation cap for the 0-100
# fallback transform ``depth = 100 * (min(effective_count, CAP) - 1) / (CAP - 1)``.
# Sensitivity is reported for 6 / 8 / 10 in the stress tests.
DEPTH_EFFECTIVE_COUNT_CAP = 8.0
DEPTH_EFFECTIVE_COUNT_SENSITIVITY_CAPS = (6.0, 8.0, 10.0)

# Favorite Hit Coverage: demand baseline for a subject to contribute, and the
# saturation constant for the fixed transform
# ``coverage = 100 * (1 - exp(-raw / FAVORITE_COVERAGE_SATURATION_K))``.
# The fixed transform is the shipping normalization (chosen over cohort
# percentile scaling after the leave-one-set-out stability stress test); the
# cohort-robust variant remains available for diagnostics.
FAVORITE_COVERAGE_DEMAND_BASELINE = 50.0
FAVORITE_COVERAGE_SATURATION_K = 3.0
FAVORITE_COVERAGE_NORMALIZATION_VERSION = "favorite_hit_coverage_saturated_v1"


# ---------------------------------------------------------------------------
# Set-value association (DESCRIPTIVE DIAGNOSTIC - deliberately NOT a gate)
# ---------------------------------------------------------------------------
# An earlier design gated desirability's entry into RIP on Universal Set
# Desirability v3 tracking total set value at Spearman >= 0.50 (near the prior
# ~0.70 benchmark). That gate was REMOVED on purpose, and must not be
# reintroduced:
#
#   Universal Set Desirability intentionally excludes scarcity, Treatment,
#   price, and simulation data. Market price is JOINTLY produced by demand,
#   scarcity, prestige, supply, age, and other card characteristics. Requiring
#   a deliberately price-independent construct to preserve a price correlation
#   would select the construct back toward price contamination - i.e. it would
#   punish the score precisely for being clean. A low raw correlation with set
#   value is an expected property of a pure subject-appeal measure, not
#   evidence that the measure is broken.
#
# The correlation is still computed and reported as descriptive context
# ("Market Association"). It never auto-fails desirability and never forces its
# RIP weight to zero.
#
# The real construct validation is the card-level market amplification study
# (backend/scripts/build_card_market_amplification_study.py): does appeal add
# incremental out-of-sample predictive value for log(price) beyond structural
# controls and ACTUAL pull scarcity, and does scarcity amplify appeal?

SET_VALUE_ASSOCIATION_IS_DIAGNOSTIC_ONLY = True
SET_VALUE_ASSOCIATION_PRIOR_BENCHMARK = 0.70  # prior shipped score, context only

SET_VALUE_ASSOCIATION_DISCLOSURE = (
    "Descriptive context only: higher set desirability is positively associated "
    "with set value in the current sample. This is not a price forecast, not "
    "causal proof, and not a gate on the score. A pure subject-appeal measure is "
    "not expected to reproduce price, which is jointly driven by scarcity, "
    "prestige, supply, and age."
)


# ---------------------------------------------------------------------------
# Pillar weight-sensitivity alternatives (Phase 9, report-only)
# ---------------------------------------------------------------------------

WEIGHT_SENSITIVITY_ALTERNATIVES: Dict[str, Dict[str, float]] = {
    "default_58_20_12_10": dict(DEFAULT_RIP_WEIGHTS),
    "alt_50_25_15_10": {"profit": 0.50, "safety": 0.25, "stability": 0.15, "desirability": 0.10},
    "alt_65_17_8_10": {"profit": 0.65, "safety": 0.17, "stability": 0.08, "desirability": 0.10},
    "desirability_0": {"profit": 0.58, "safety": 0.20, "stability": 0.12, "desirability": 0.0},
    "desirability_15": {"profit": 0.55, "safety": 0.19, "stability": 0.11, "desirability": 0.15},
}


# ---------------------------------------------------------------------------
# Renormalization (one rule, applied everywhere a component is absent)
# ---------------------------------------------------------------------------

def renormalize_weights(
    weights: Mapping[str, float],
    *,
    exclude: Iterable[str] = (),
) -> Dict[str, float]:
    """Renormalize ``weights`` proportionally to sum to 1.0.

    Components in ``exclude`` (or with weight <= 0) are dropped and the
    remaining weights are scaled by the same factor. This is the single
    renormalization rule for every absence case: a component failing its gate,
    a user setting a weight to 0, or a set lacking a component. There is no
    second table of magic numbers.
    """
    excluded = set(exclude)
    kept = {
        key: float(value)
        for key, value in weights.items()
        if key not in excluded and float(value) > 0.0
    }
    total = sum(kept.values())
    if total <= 0.0:
        return {}
    return {key: value / total for key, value in kept.items()}


def resolve_rip_weights(
    overrides: Optional[Mapping[str, float]] = None,
    *,
    include_desirability: bool = True,
) -> Dict[str, float]:
    """Return the effective RIP weights: config defaults, optional overrides,
    renormalized to sum exactly 1.0 (dropping desirability when excluded)."""
    base = dict(DEFAULT_RIP_WEIGHTS)
    if overrides:
        for key, value in overrides.items():
            if key in base:
                base[key] = float(value)
    exclude = () if include_desirability else ("desirability",)
    return renormalize_weights(base, exclude=exclude)


def rip_weights_payload(weights: Mapping[str, float]) -> Dict[str, object]:
    """Public payload describing the weights in force, sourced from config."""
    return {
        "weights": {key: round(float(value), 6) for key, value in weights.items()},
        "defaults": dict(DEFAULT_RIP_WEIGHTS),
        "weightsLabel": WEIGHTS_DISCLOSURE,
        "configVersion": SCORING_CONFIG_VERSION,
    }
