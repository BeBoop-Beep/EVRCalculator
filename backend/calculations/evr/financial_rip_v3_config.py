"""Authoritative, versioned configuration for Financial RIP V3.

ONE SOURCE OF TRUTH
-------------------
Every weight, threshold, anchor and version identifier the V3 outcome-profile
engine uses lives here. Calculation, persistence, publication, ranking, the
audit scripts and the tests all read THIS module. No literal 0.25 / 10_000 /
0.50 is permitted to appear a second time anywhere in the V3 path - a duplicated
weight is a drift point, and a drift point in a scoring engine is a silent
mis-score rather than a crash.

WHY FIXED ABSOLUTE NORMALIZATION
--------------------------------
Financial RIP V2 normalizes several inputs against the currently-simulated
cohort, so adding or retiring a set moves every other set's score. V3 does not:
every raw metric is mapped to 0-100 through a FIXED transform defined below.
Adding a set changes ranks (a rank is a property of a cohort) but never changes
an existing set's absolute V3 score. That is the property that makes V3 scores
comparable across time and across publication runs.

WHY THESE ANCHORS
-----------------
Each transform's knots are chosen from the FINANCIAL MEANING of the metric
first, then sanity-checked against the observed range of the current simulation
cohort by ``backend/scripts/audit_financial_rip_v3_inputs.py``. The audit
reports, per metric, how many sets clip at each bound; if a bound clips a large
share of the cohort the anchor is wrong and should be revised HERE, with the
normalization version bumped, rather than patched at a call site.

Interpretation of the headline knots:

  * ``true_win_probability`` 0.50 -> 100. A pack that recovers its cost half the
    time is a coin flip, which is as good as sealed Pokemon product realistically
    gets; scoring it 100 keeps the top of the scale meaningful instead of
    reserving it for an unreachable 100% win rate.
  * ``typical_retention_ratio`` 1.00 -> 100. The typical (median) pack fully
    recovering its cost is the natural ceiling for "typical".
  * loss-resilience inputs are ratios/shares bounded in [0, 1] by construction,
    so they map linearly and CANNOT clip.
  * upside ratios saturate. An unbounded multiple must not produce an unbounded
    score, so the jackpot transforms are exponential-saturating (the same
    ``100 * (1 - exp(-raw / K))`` family already used by Favorite Hit Coverage in
    ``backend.desirability.scoring_config``) and can never reach, let alone
    exceed, 100.
  * ``base_rtp_excluding_top_1pct`` 1.00 -> 100. Returning cost on average with
    the top 1% removed is a fully efficient product.

MISSING DATA IS NOT 50
----------------------
There is deliberately no neutral fallback anywhere in this file. A required raw
metric that is unavailable makes its component unavailable, which makes
Financial RIP V3 unavailable with an explicit reason. A neutral 50 would rank a
set with no data alongside sets with data.
"""

from __future__ import annotations

import math
from typing import Any, Dict, Optional, Sequence, Tuple


# ---------------------------------------------------------------------------
# Version identifiers
# ---------------------------------------------------------------------------
# Deliberately distinct from every existing identifier. In particular this is
# NOT `RIP_V3_VERSION` ("rip_v3_weighted_four_component"), which names the
# historical Profit/Safety/Stability/Desirability blend and describes a
# materially different model. Reusing it would make two incompatible scores
# indistinguishable in stored rows.

FINANCIAL_RIP_V3_VERSION = "financial_rip_v3_outcome_profile_25_20_15_25_10_5"
FINANCIAL_RIP_V3_NORMALIZATION_VERSION = "financial_rip_v3_fixed_absolute_piecewise_v1"
FINANCIAL_RIP_V3_TAIL_CONTRACT_VERSION = "empirical_rank_exact_mass_v1"
FINANCIAL_RIP_V3_CONFIG_VERSION = "financial_rip_v3_config_v1"

OVERALL_RIP_V5_VERSION = "overall_rip_v5_90_financial_v3_10_ca7"
PUBLIC_RIP_CONTRACT_V5_VERSION = "public_rip_contract_v5"

DEPTH_AND_ROBUSTNESS_VERSION = "depth_and_robustness_v1"


# ---------------------------------------------------------------------------
# Top-level component weights
# ---------------------------------------------------------------------------
# These six MUST sum to exactly 1.0 and are asserted below at import time.
#
# The shape of the model: how often you get your money back (25) and how good
# the realistic good outcome is (25) dominate; what a typical pack returns (20)
# and how soft the losses are (15) shape the middle; the exceptional jackpot is
# capped at a 10-point maximum contribution so one enormous card cannot buy a
# product a top score; and expected value survives as a 5-point economic
# guardrail rather than the headline it was in V2.

FINANCIAL_RIP_V3_WEIGHTS: Dict[str, float] = {
    "true_win_frequency": 0.25,
    "typical_retention": 0.20,
    "loss_resilience": 0.15,
    "realistic_upside": 0.25,
    "jackpot_upside": 0.10,
    "base_economic_efficiency": 0.05,
}

# Canonical display/rendering order. The frontend renders in exactly this order.
FINANCIAL_RIP_V3_COMPONENT_ORDER: Tuple[str, ...] = (
    "true_win_frequency",
    "typical_retention",
    "loss_resilience",
    "realistic_upside",
    "jackpot_upside",
    "base_economic_efficiency",
)

# snake_case component key -> public camelCase key. The presenters read this
# rather than each re-deriving the casing.
FINANCIAL_RIP_V3_PUBLIC_COMPONENT_KEYS: Dict[str, str] = {
    "true_win_frequency": "trueWinFrequency",
    "typical_retention": "typicalRetention",
    "loss_resilience": "lossResilience",
    "realistic_upside": "realisticUpside",
    "jackpot_upside": "jackpotUpside",
    "base_economic_efficiency": "baseEconomicEfficiency",
}

# Sub-component weights, per component. Each block sums to 1.0.
LOSS_RESILIENCE_SUBWEIGHTS: Dict[str, float] = {
    # What a losing pack actually hands back, in cost-relative terms.
    "average_retention_given_loss": 0.70,
    # How many of the losses are near-misses rather than wipeouts.
    "soft_loss_share_given_loss": 0.30,
}
# `hard_loss_probability` is DISCLOSED but deliberately unweighted: it is
# algebraically tied to the same distribution buckets as the two weighted
# sub-inputs, so weighting it too would double-count one axis.

REALISTIC_UPSIDE_SUBWEIGHTS: Dict[str, float] = {
    "p95_threshold_ratio": 0.40,
    "realistic_tail_mean_ratio": 0.60,
}

JACKPOT_UPSIDE_SUBWEIGHTS: Dict[str, float] = {
    "p99_threshold_ratio": 0.35,
    "jackpot_tail_mean_ratio": 0.65,
}


# ---------------------------------------------------------------------------
# Requirements and thresholds
# ---------------------------------------------------------------------------

# Below this many simulated packs the empirical 99th percentile and the top-1%
# conditional mean rest on too few observations to publish. 10_000 runs put at
# least 100 observations in the jackpot bucket.
FINANCIAL_RIP_V3_MIN_SIMULATION_COUNT = 10_000

# R = X / C below this is a "hard" loss (less than half the cost recovered);
# at or above it, but below 1.0, is a "soft" loss.
SOFT_LOSS_RATIO_THRESHOLD = 0.50

# Requested empirical tail masses. Actual selected counts/shares are always
# reported alongside these in the payload - see the tail contract note below.
JACKPOT_TAIL_SHARE = 0.01
REALISTIC_TAIL_SHARE = 0.05

# Numeric tolerance for the contribution-reconstruction check.
SCORE_RECONSTRUCTION_TOLERANCE = 1e-6


# ---------------------------------------------------------------------------
# Status vocabulary
# ---------------------------------------------------------------------------

STATUS_READY = "ready"
STATUS_UNAVAILABLE = "unavailable"

REASON_INVALID_PACK_COST = "invalid_pack_cost"
REASON_EMPTY_OUTCOMES = "empty_outcome_vector"
REASON_NON_FINITE_OUTCOMES = "non_finite_outcome_vector"
REASON_INSUFFICIENT_RUNS = "insufficient_simulation_count"
REASON_MISSING_COMPONENT = "missing_required_component"


# ---------------------------------------------------------------------------
# Fixed normalization transforms
# ---------------------------------------------------------------------------
# Two families only, both fixed and both absolute:
#
#   piecewise_linear : an ordered list of (raw, score) knots. Between knots the
#                      mapping is linear; outside the outer knots it CLIPS, and
#                      the clip is reported.
#   saturating_exp   : score = 100 * (1 - exp(-raw / k)), for raw >= 0. Strictly
#                      increasing, asymptotic to 100, so an arbitrarily large
#                      outlier can never produce an out-of-range score. Used
#                      wherever the raw input is an unbounded value multiple.
#
# `direction` is always "higher_is_better" in V3: every raw input is defined so
# that more is better. There is no inverted transform to get the sign wrong on.

PIECEWISE_LINEAR = "piecewise_linear"
SATURATING_EXP = "saturating_exp"


FINANCIAL_RIP_V3_TRANSFORMS: Dict[str, Dict[str, Any]] = {
    # --- True Win Frequency -------------------------------------------------
    "true_win_probability": {
        "family": PIECEWISE_LINEAR,
        "direction": "higher_is_better",
        "unit": "probability",
        "knots": ((0.00, 0.0), (0.05, 20.0), (0.10, 40.0), (0.20, 60.0), (0.35, 80.0), (0.50, 100.0)),
        "rationale": (
            "P(pack value >= pack cost). 5% is the low end of a modern booster, "
            "10% is common, 20% is strong, and a 50% coin flip is the practical "
            "ceiling for sealed product and therefore scores 100."
        ),
    },
    # --- Typical Retention --------------------------------------------------
    "typical_retention_ratio": {
        "family": PIECEWISE_LINEAR,
        "direction": "higher_is_better",
        "unit": "ratio_to_cost",
        "knots": ((0.00, 0.0), (0.10, 10.0), (0.25, 30.0), (0.40, 50.0), (0.60, 70.0), (0.80, 85.0), (1.00, 100.0)),
        "rationale": (
            "P50(pack value) / pack cost. The median pack recovering its full "
            "cost is the natural ceiling for a TYPICAL outcome, so 1.00 scores "
            "100 and saturates. Extra resolution is placed in 0.25-0.60 where "
            "modern boosters actually sit."
        ),
    },
    # --- Loss Resilience ----------------------------------------------------
    # Both inputs are bounded in [0, 1] by construction, so these map linearly
    # and can never clip. Kept as explicit transforms anyway so the audit
    # payload carries a transform version for every normalized number.
    "average_retention_given_loss": {
        "family": PIECEWISE_LINEAR,
        "direction": "higher_is_better",
        "unit": "ratio_to_cost",
        "knots": ((0.00, 0.0), (1.00, 100.0)),
        "rationale": (
            "E[value/cost | value < cost]. Bounded in [0, 1) by definition, so a "
            "direct linear read: a losing pack that hands back 60% of cost scores "
            "60. No clipping is possible."
        ),
    },
    "soft_loss_share_given_loss": {
        "family": PIECEWISE_LINEAR,
        "direction": "higher_is_better",
        "unit": "share",
        "knots": ((0.00, 0.0), (1.00, 100.0)),
        "rationale": (
            "P(0.50 <= R < 1 | R < 1). A conditional share bounded in [0, 1]; "
            "the fraction of losses that are near-misses rather than wipeouts."
        ),
    },
    # --- Realistic Upside ---------------------------------------------------
    "p95_threshold_ratio": {
        "family": PIECEWISE_LINEAR,
        "direction": "higher_is_better",
        "unit": "ratio_to_cost",
        "knots": ((0.00, 0.0), (1.00, 40.0), (2.00, 70.0), (4.00, 90.0), (8.00, 100.0)),
        "rationale": (
            "Q95(pack value) / pack cost - where the top 5% BEGINS. A set whose "
            "top-5% threshold merely breaks even scores 40; 2x scores 70; 4x "
            "scores 90. 8x is a realistic-tail ceiling and saturates."
        ),
    },
    "realistic_tail_mean_ratio": {
        "family": PIECEWISE_LINEAR,
        "direction": "higher_is_better",
        "unit": "ratio_to_cost",
        "knots": ((0.00, 0.0), (1.50, 40.0), (3.00, 70.0), (6.00, 90.0), (12.00, 100.0)),
        "rationale": (
            "Mean of the 95th-to-99th percentile band / pack cost, i.e. what a "
            "good-but-not-miraculous pack actually pays. The band mean sits above "
            "the P95 threshold, so its knots are shifted up ~1.5x relative to the "
            "threshold transform to keep the two on a comparable 0-100 footing."
        ),
    },
    # --- Jackpot Upside -----------------------------------------------------
    # Saturating on purpose. One 5000x card must not create an unbounded score.
    "p99_threshold_ratio": {
        "family": SATURATING_EXP,
        "direction": "higher_is_better",
        "unit": "ratio_to_cost",
        "k": 8.0,
        "rationale": (
            "Q99(pack value) / pack cost. Saturating-exponential: 8x scores ~63, "
            "20x ~92, 40x ~99. Strictly increasing and asymptotic to 100, so no "
            "outlier can push the component out of range."
        ),
    },
    "jackpot_tail_mean_ratio": {
        "family": SATURATING_EXP,
        "direction": "higher_is_better",
        "unit": "ratio_to_cost",
        "k": 25.0,
        "rationale": (
            "Mean of the top 1% of outcomes / pack cost. The top-1% conditional "
            "mean is dominated by the single biggest chase and is routinely an "
            "order of magnitude above the P99 threshold, so it saturates far "
            "later: 25x scores ~63, 60x ~91."
        ),
    },
    # --- Base Economic Efficiency ------------------------------------------
    "base_rtp_excluding_top_1pct": {
        "family": PIECEWISE_LINEAR,
        "direction": "higher_is_better",
        "unit": "ratio_to_cost",
        "knots": ((0.00, 0.0), (0.40, 25.0), (0.60, 50.0), (0.80, 75.0), (1.00, 100.0)),
        "rationale": (
            "Mean of every outcome OUTSIDE the top 1% / pack cost. Returning cost "
            "on average once the jackpots are removed is full efficiency and "
            "scores 100. Scoring base RTP rather than total RTP is what stops one "
            "extremely valuable chase from making ordinary opening economics look "
            "stronger than they are."
        ),
    },
}


# Which raw metric feeds which component, and with what sub-weight. Declared as
# data so the component builder, the validator and the audit script all read one
# table instead of three hand-maintained lists.
FINANCIAL_RIP_V3_COMPONENT_INPUTS: Dict[str, Dict[str, float]] = {
    "true_win_frequency": {"true_win_probability": 1.0},
    "typical_retention": {"typical_retention_ratio": 1.0},
    "loss_resilience": dict(LOSS_RESILIENCE_SUBWEIGHTS),
    "realistic_upside": dict(REALISTIC_UPSIDE_SUBWEIGHTS),
    "jackpot_upside": dict(JACKPOT_UPSIDE_SUBWEIGHTS),
    "base_economic_efficiency": {"base_rtp_excluding_top_1pct": 1.0},
}


# ---------------------------------------------------------------------------
# Depth and Robustness classification (UNWEIGHTED diagnostic)
# ---------------------------------------------------------------------------
# This is not a seventh component and is never subtracted from the V3 score.
# Realistic Upside already excludes the top 1%, Jackpot Upside is capped at a
# 10-point contribution, and Base Economics excludes the top 1% - concentration
# is therefore already prevented from dominating V3. Penalising it again here
# would double-count it. Depth and Robustness exists to EXPLAIN a profile.
#
# Thresholds are on top-1 card EV share, versioned so a re-tuning is visible.

DEPTH_AND_ROBUSTNESS_THRESHOLDS: Tuple[Tuple[float, str], ...] = (
    (0.25, "broad"),
    (0.45, "moderately_concentrated"),
    (0.70, "chase_heavy"),
    (1.01, "extremely_concentrated"),
)

DEPTH_AND_ROBUSTNESS_LABELS: Dict[str, str] = {
    "broad": "Broad",
    "moderately_concentrated": "Moderately concentrated",
    "chase_heavy": "Chase-heavy",
    "extremely_concentrated": "Extremely concentrated",
}


# ---------------------------------------------------------------------------
# Canonical version resolution (the cutover switch)
# ---------------------------------------------------------------------------
# ONE authoritative selection, read by every public builder, ranking path and
# presenter. Promotion is this constant, not a scattering of conditionals and
# not an environment variable that can differ between two workers mid-publish
# and emit two score versions into one leaderboard.

CANONICAL_FINANCIAL_RIP_VERSION = FINANCIAL_RIP_V3_VERSION
CANONICAL_OVERALL_RIP_VERSION = OVERALL_RIP_V5_VERSION

# Overall RIP's 90/10 relationship is UNCHANGED by the V3 cutover; only the
# financial input changes (V2 -> V3). Held here so V5 and the legacy V4 path
# cannot drift apart on the weights they share.
OVERALL_RIP_V5_WEIGHTS: Dict[str, float] = {
    "financial_rip": 0.90,
    "opening_desirability": 0.10,
}


# ---------------------------------------------------------------------------
# Transform application
# ---------------------------------------------------------------------------

def _piecewise_linear(raw: float, knots: Sequence[Tuple[float, float]]) -> Tuple[float, Optional[str]]:
    """Map ``raw`` through ordered ``knots``, reporting which bound clipped."""
    low_raw, low_score = knots[0]
    high_raw, high_score = knots[-1]
    if raw <= low_raw:
        return low_score, ("lower" if raw < low_raw else None)
    if raw >= high_raw:
        return high_score, ("upper" if raw > high_raw else None)
    for index in range(len(knots) - 1):
        left_raw, left_score = knots[index]
        right_raw, right_score = knots[index + 1]
        if left_raw <= raw <= right_raw:
            span = right_raw - left_raw
            if span <= 0:
                return right_score, None
            fraction = (raw - left_raw) / span
            return left_score + fraction * (right_score - left_score), None
    return high_score, "upper"


def normalize_metric(metric_key: str, raw_value: Optional[float]) -> Dict[str, Any]:
    """Normalize one raw V3 input to 0-100 under its FIXED transform.

    Returns a full audit record - raw value, score, transform family and
    parameters, clip status and direction - so every normalized number in the
    published payload can be traced back to the arithmetic that produced it.

    A missing or non-finite raw value yields ``score=None`` and
    ``available=False``. It does NOT yield 50.
    """
    spec = FINANCIAL_RIP_V3_TRANSFORMS.get(metric_key)
    if spec is None:
        raise KeyError(f"No fixed V3 transform is configured for '{metric_key}'.")

    record: Dict[str, Any] = {
        "metric": metric_key,
        "raw": None,
        "score": None,
        "available": False,
        "transformVersion": FINANCIAL_RIP_V3_NORMALIZATION_VERSION,
        "transform": spec["family"],
        "direction": spec["direction"],
        "unit": spec["unit"],
        "clipped": False,
        "clippedAt": None,
    }

    if raw_value is None:
        return record
    try:
        raw = float(raw_value)
    except (TypeError, ValueError):
        return record
    if not math.isfinite(raw):
        return record

    record["raw"] = raw
    record["available"] = True

    if spec["family"] == PIECEWISE_LINEAR:
        knots = spec["knots"]
        score, clipped_at = _piecewise_linear(raw, knots)
        record["breakpoints"] = [[float(a), float(b)] for a, b in knots]
        record["clipped"] = clipped_at is not None
        record["clippedAt"] = clipped_at
    elif spec["family"] == SATURATING_EXP:
        k = float(spec["k"])
        # Negative raw values are not meaningful for a value multiple; clamp to
        # the 0 floor and say so rather than emitting a negative score.
        if raw < 0.0:
            score = 0.0
            record["clipped"] = True
            record["clippedAt"] = "lower"
        else:
            score = 100.0 * (1.0 - math.exp(-raw / k))
        record["saturationK"] = k
        record["formula"] = "100 * (1 - exp(-raw / k))"
    else:  # pragma: no cover - guarded by the import-time audit below
        raise ValueError(f"Unknown transform family '{spec['family']}' for '{metric_key}'.")

    record["score"] = float(max(0.0, min(100.0, score)))
    return record


def classify_depth_and_robustness(top1_ev_share: Optional[float]) -> Optional[str]:
    """Readable concentration tag from top-1 card EV share, or None if absent."""
    if top1_ev_share is None:
        return None
    try:
        share = float(top1_ev_share)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(share):
        return None
    for upper_bound, tag in DEPTH_AND_ROBUSTNESS_THRESHOLDS:
        if share < upper_bound:
            return tag
    return DEPTH_AND_ROBUSTNESS_THRESHOLDS[-1][1]


def financial_rip_v3_weights_payload() -> Dict[str, Any]:
    """Auditable description of the model, for the debug block of the contract.

    The frontend does NOT need this to render; the six component cards carry no
    visible weight percentage. It is published so the arithmetic stays checkable.
    """
    return {
        "scoreVersion": FINANCIAL_RIP_V3_VERSION,
        "normalizationVersion": FINANCIAL_RIP_V3_NORMALIZATION_VERSION,
        "tailContractVersion": FINANCIAL_RIP_V3_TAIL_CONTRACT_VERSION,
        "configVersion": FINANCIAL_RIP_V3_CONFIG_VERSION,
        "weights": dict(FINANCIAL_RIP_V3_WEIGHTS),
        "subWeights": {
            "lossResilience": dict(LOSS_RESILIENCE_SUBWEIGHTS),
            "realisticUpside": dict(REALISTIC_UPSIDE_SUBWEIGHTS),
            "jackpotUpside": dict(JACKPOT_UPSIDE_SUBWEIGHTS),
        },
        "minSimulationCount": FINANCIAL_RIP_V3_MIN_SIMULATION_COUNT,
        "softLossRatioThreshold": SOFT_LOSS_RATIO_THRESHOLD,
        "requestedTailShares": {
            "jackpot": JACKPOT_TAIL_SHARE,
            "realistic": REALISTIC_TAIL_SHARE,
        },
        "transforms": {
            key: {
                "family": spec["family"],
                "direction": spec["direction"],
                "unit": spec["unit"],
                **({"breakpoints": [[float(a), float(b)] for a, b in spec["knots"]]} if "knots" in spec else {}),
                **({"saturationK": float(spec["k"])} if "k" in spec else {}),
                "rationale": spec["rationale"],
            }
            for key, spec in FINANCIAL_RIP_V3_TRANSFORMS.items()
        },
    }


# ---------------------------------------------------------------------------
# Import-time self-audit
# ---------------------------------------------------------------------------
# A weights table that does not sum to 1.0 produces a score that is not on the
# 0-100 scale it claims. That must fail at import, not at publication.

def _audit_config() -> None:
    total = sum(FINANCIAL_RIP_V3_WEIGHTS.values())
    if abs(total - 1.0) > 1e-12:
        raise ValueError(f"FINANCIAL_RIP_V3_WEIGHTS must sum to 1.0; got {total!r}.")

    if tuple(FINANCIAL_RIP_V3_WEIGHTS) != FINANCIAL_RIP_V3_COMPONENT_ORDER:
        raise ValueError("FINANCIAL_RIP_V3_COMPONENT_ORDER must cover the weights in order.")

    if set(FINANCIAL_RIP_V3_PUBLIC_COMPONENT_KEYS) != set(FINANCIAL_RIP_V3_WEIGHTS):
        raise ValueError("Every V3 component needs exactly one public camelCase key.")

    for component, inputs in FINANCIAL_RIP_V3_COMPONENT_INPUTS.items():
        if component not in FINANCIAL_RIP_V3_WEIGHTS:
            raise ValueError(f"'{component}' has inputs but no top-level weight.")
        sub_total = sum(inputs.values())
        if abs(sub_total - 1.0) > 1e-12:
            raise ValueError(f"Sub-weights for '{component}' must sum to 1.0; got {sub_total!r}.")
        for metric in inputs:
            if metric not in FINANCIAL_RIP_V3_TRANSFORMS:
                raise ValueError(f"'{metric}' feeds '{component}' but has no fixed transform.")

    if set(FINANCIAL_RIP_V3_COMPONENT_INPUTS) != set(FINANCIAL_RIP_V3_WEIGHTS):
        raise ValueError("Every V3 component must declare its raw inputs.")

    for metric, spec in FINANCIAL_RIP_V3_TRANSFORMS.items():
        family = spec.get("family")
        if family == PIECEWISE_LINEAR:
            knots = spec.get("knots") or ()
            if len(knots) < 2:
                raise ValueError(f"'{metric}' needs at least two knots.")
            raws = [knot[0] for knot in knots]
            if raws != sorted(raws):
                raise ValueError(f"Knots for '{metric}' must be sorted by raw value.")
        elif family == SATURATING_EXP:
            if float(spec.get("k", 0.0)) <= 0.0:
                raise ValueError(f"Saturation constant for '{metric}' must be positive.")
        else:
            raise ValueError(f"Unknown transform family '{family}' for '{metric}'.")

    if abs(sum(OVERALL_RIP_V5_WEIGHTS.values()) - 1.0) > 1e-12:
        raise ValueError("OVERALL_RIP_V5_WEIGHTS must sum to 1.0.")


_audit_config()
