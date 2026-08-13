"""RESEARCH-ONLY candidate architectures for a desirability-dominant Collector Appeal.

NOT CANONICAL. NOTHING HERE IS PRODUCTION.
------------------------------------------
``backend.desirability.collector_appeal.compute_collector_appeal_v3`` remains THE
canonical Collector Appeal. This module adds no canonical version constant, is
imported by no service, no publication path and no snapshot builder, and every
identifier it exports is prefixed ``collector_appeal_v4_candidate_``. A unit test
asserts the canonical constants are untouched and that no production module
imports this file.

WHAT THIS MODULE IMPLEMENTS, AND WHAT IT DELIBERATELY DOES NOT
--------------------------------------------------------------
It implements ONE thing: the COMBINATION ARCHITECTURE - how an already-computed
D, H and P are combined into a single Collector Appeal number.

It does NOT recompute D, H or P. Those have exactly one implementation each
(``universal_set_desirability``, ``desirable_outcome_frequency``,
``collector_appeal.compute_dual_path_depth``) and a second copy here would be a
second definition of the product's inputs.

THE CONSTRUCT THIS ARCHITECTURE ENCODES
---------------------------------------
    Collector Appeal is primarily a measure of how desirable a set's collectible
    content is. Pull accessibility and structure may refine that appeal,
    especially between similarly desirable sets, but should not usually
    substitute for large differences in collector demand.

Operationally: **D ranks the neighbourhood; structure decides the close calls.**

The family below expresses that as

    CA = D  +  bounded_structural_modifier(H, P)          [additive family]
    CA = D * (1 + bounded_relative_modifier(H, P))        [multiplicative family]

with the modifier CENTRED at a neutral structure rather than floored at zero.
Centring is the substantive design decision. A floored bonus (CA7, V2) can only
ever add, so the only way to make structure matter is to make the bonus large -
and a large one-sided bonus is exactly what lets a mediocre roster climb. A
centred modifier lets excellent structure add and poor structure subtract while
the TOTAL structural span stays small, which is what "tiebreaker" means.

THE SINGLE MOST IMPORTANT PROPERTY
----------------------------------
For the additive family the maximum D gap that structure can overturn is
EXACTLY ``MODIFIER_CEILING - MODIFIER_FLOOR`` points - i.e. the full span of the
modifier, achieved only when the lower-D set has perfect structure and the
higher-D set has the worst possible structure. That number is a design
parameter, not an emergent accident, so the inversion boundary can be stated in
the spec instead of discovered in a grid search.

NOTE THE ASYMMETRY. For the FROZEN candidate the span is NOT ``2 * ceiling``:
the downside is damped, so the modifier runs ``+4.0`` to ``-2.0`` and the span
is ``6.0``, not ``8.0``. Writing the frozen model as ``D + 4*(2S-1)`` would be a
false statement of it - see ``FROZEN_FORMULA_EXPRESSION``, which states both
branches explicitly.

NORMALIZATION IS FIXED-ANCHOR, NEVER COHORT-RELATIVE
----------------------------------------------------
D is passed through UNCHANGED - not min-maxed, not rescaled, not ranked. H and P
are mapped onto a structural index through PRE-REGISTERED FIXED ANCHORS stated
below in collector language. Adding or removing a set can never move another
set's score. There is no search loop over any constant in this module.

NO FINANCIAL INPUT
------------------
No price, pack cost, EV, profit, set value or market proxy is read here.
"""

from __future__ import annotations

import math
from typing import Any, Dict, List, Mapping, Optional, Sequence, Tuple

from backend.desirability.collector_appeal import (
    CA7_PRODUCTION_LAMBDA,
    compute_collector_appeal_ca7,
    compute_collector_appeal_v2,
    compute_collector_appeal_v3,
)

# Research identity. Deliberately NOT of the form ``collector_appeal_v4`` alone:
# a bare "v4" reads like a promoted successor, and nothing here is promoted.
COLLECTOR_APPEAL_V4_CANDIDATE_FAMILY_VERSION = (
    "collector_appeal_v4_candidate_centred_structural_modifier_research_v1"
)
COLLECTOR_APPEAL_V4_CANDIDATE_STATUS = "research_candidate_not_canonical"

# ---------------------------------------------------------------------------
# FIXED ANCHORS for the structural index. Pre-registered, stated in collector
# language, and expressed as pack-experience facts rather than cohort statistics.
# ---------------------------------------------------------------------------

# H is P(a modeled pack contains a card tied to a desirable subject). Frequency
# is perceived multiplicatively - the felt difference between "every 4 packs" and
# "every 8 packs" is the same as between "every 8" and "every 16" - so H is
# anchored on a LOG2 wait-time scale centred on one desirable card per 8 packs.
H_NEUTRAL_ONE_IN_N = 8.0     # neutral structure: a desirable card about every 8 packs
H_STRONG_ONE_IN_N = 4.0      # index 1.0: about every 4 packs
H_WEAK_ONE_IN_N = 16.0       # index 0.0: about every 16 packs

# P is a share-weighted [0, 1] dual-path index and is already linear in its own
# construct, so it is anchored linearly. Neutral is the midpoint of the anchors.
P_WEAK_ANCHOR = 0.10         # index 0.0: desirable subjects essentially single-path
P_STRONG_ANCHOR = 0.50       # index 1.0: desirable subjects broadly dual-path
P_NEUTRAL = (P_WEAK_ANCHOR + P_STRONG_ANCHOR) / 2.0

# How the two structural signals share the structural budget. H outweighs P
# because H is the opening experience itself (does a pack hand you something you
# care about?) while P is a property OF the ladder around that content. See the
# P audit in the study document: P is retained at a minority share precisely so
# the cohort can be re-run with and without it.
STRUCTURAL_H_WEIGHT = 0.70
STRUCTURAL_P_WEIGHT = 0.30

# Research ceilings, on the public 0-100 scale, for the modifier's ONE-SIDED
# magnitude. These are SCENARIOS to be reported, not defaults to be shipped.
MODIFIER_CEILING_GRID: Tuple[float, ...] = (2.0, 4.0, 6.0, 8.0)

# Asymmetry scenario: a set whose desirable content is hard to reach is not
# thereby unappealing - difficulty is part of a chase's appeal - so the DOWNWARD
# half of the modifier is optionally damped relative to the upward half. 1.0 is
# the symmetric control.
PENALTY_DAMPING_GRID: Tuple[float, ...] = (1.0, 0.5)

# Multiplicative family: CA = D * (1 + gain * centred_structure). Expressed as a
# fraction of D so structure scales what is already there rather than creating
# appeal. 0.05 means "perfect structure is worth 5% more of this set's own
# desirability", which at D = 95 is +4.8 points and at D = 51 is +2.6.
MULTIPLICATIVE_GAIN_GRID: Tuple[float, ...] = (0.04, 0.08)

PUBLIC_SCALE = 100.0


def _as_float(value: Any) -> Optional[float]:
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return None
    return parsed if math.isfinite(parsed) else None


def _clamp(value: float, low: float = 0.0, high: float = 1.0) -> float:
    return max(low, min(high, value))


# ---------------------------------------------------------------------------
# The structural index
# ---------------------------------------------------------------------------


def h_structural_index(h: Any) -> Optional[float]:
    """Map H onto [0, 1] against FIXED wait-time anchors. 0.5 == neutral.

    ``index = (log2(H) - log2(1/16)) / (log2(1/4) - log2(1/16))``

    Plain English: 0.0 means a desirable card turns up about once every 16 packs
    or worse, 0.5 means about once every 8, 1.0 means about once every 4 or
    better. Nothing about the cohort enters; a set scores the same whoever else
    is measured.

    Returns None - never 0.0 - for a missing or non-positive H. H = 0 exactly
    would mean "no modeled pack can produce a desirable card", which is a data
    condition, not a weak set.
    """
    value = _as_float(h)
    if value is None or value <= 0.0:
        return None
    weak = math.log2(1.0 / H_WEAK_ONE_IN_N)
    strong = math.log2(1.0 / H_STRONG_ONE_IN_N)
    return _clamp((math.log2(value) - weak) / (strong - weak))


def p_structural_index(p: Any) -> Optional[float]:
    """Map P onto [0, 1] against FIXED dual-path anchors. 0.5 == neutral."""
    value = _as_float(p)
    if value is None:
        return None
    return _clamp((value - P_WEAK_ANCHOR) / (P_STRONG_ANCHOR - P_WEAK_ANCHOR))


def structural_index(
    h: Any,
    p: Any,
    *,
    h_weight: float = STRUCTURAL_H_WEIGHT,
    p_weight: float = STRUCTURAL_P_WEIGHT,
) -> Optional[float]:
    """``S`` on [0, 1]: how good this set's obtainability structure is, absolutely.

    ``S = 0.5`` is NEUTRAL structure and produces no modifier at all. That is the
    property that makes the modifier a refinement rather than a second source of
    appeal.

    A weight of exactly 0 drops that input, and its value is then not required -
    this is how the D+H-only and D+P-only variants are computed WITHOUT a second
    formula. Returns None when a required input is unavailable.
    """
    total = h_weight + p_weight
    if abs(total - 1.0) > 1e-12:
        raise ValueError(f"structural weights must sum to 1.0; got {total!r}")
    accumulated = 0.0
    if h_weight > 0.0:
        h_index = h_structural_index(h)
        if h_index is None:
            return None
        accumulated += h_weight * h_index
    if p_weight > 0.0:
        p_index = p_structural_index(p)
        if p_index is None:
            return None
        accumulated += p_weight * p_index
    return _clamp(accumulated)


def structural_modifier_points(
    h: Any,
    p: Any,
    *,
    ceiling: float,
    penalty_damping: float = 1.0,
    h_weight: float = STRUCTURAL_H_WEIGHT,
    p_weight: float = STRUCTURAL_P_WEIGHT,
) -> Optional[float]:
    """The signed structural adjustment in PUBLIC POINTS, centred at neutral.

        m = ceiling * (2S - 1)                for S >= 0.5
        m = ceiling * (2S - 1) * damping      for S <  0.5

    Bounded to ``[-ceiling * damping, +ceiling]``. With ``damping = 1`` the
    modifier is symmetric; with ``damping = 0.5`` poor obtainability costs half
    what excellent obtainability earns, which encodes "a hard chase is still a
    chase" without pretending difficulty is a virtue.
    """
    if ceiling < 0.0:
        raise ValueError("ceiling must be non-negative")
    if not 0.0 <= penalty_damping <= 1.0:
        raise ValueError("penalty_damping must be in [0, 1]")
    s = structural_index(h, p, h_weight=h_weight, p_weight=p_weight)
    if s is None:
        return None
    centred = 2.0 * s - 1.0
    return ceiling * centred * (1.0 if centred >= 0.0 else penalty_damping)


# ---------------------------------------------------------------------------
# The candidate scores. All on the PUBLIC 0-100 scale, all taking UNIT D/H/P.
# ---------------------------------------------------------------------------


def collector_appeal_v4_candidate_additive(
    d: Any,
    h: Any,
    p: Any,
    *,
    ceiling: float,
    penalty_damping: float = 1.0,
    h_weight: float = STRUCTURAL_H_WEIGHT,
    p_weight: float = STRUCTURAL_P_WEIGHT,
) -> Optional[float]:
    """``CA = 100*D + m(H, P)``, clamped to [0, 100]. RESEARCH ONLY.

    Properties (all asserted in the unit tests):
      * ``dCA/dD = 100 > 0`` wherever the clamp is not active - strictly
        increasing in D at equal structure, with NO dependence on H or P.
      * neutral structure (``S = 0.5``) gives ``CA = 100*D`` exactly.
      * the maximum D gap structure can overturn is exactly
        ``ceiling * (1 + penalty_damping)`` points.
      * any missing input returns None, never 0 and never D.

    The clamp at 100 is the one place strict monotonicity can fail, and it can
    only bind when ``100*D + ceiling > 100``. The audit reports how many cohort
    sets saturate at each ceiling; a ceiling that saturates real sets is
    disqualified on that ground alone, not on where it puts them.
    """
    d_value = _as_float(d)
    if d_value is None:
        return None
    modifier = structural_modifier_points(
        h, p, ceiling=ceiling, penalty_damping=penalty_damping,
        h_weight=h_weight, p_weight=p_weight,
    )
    if modifier is None:
        return None
    return _clamp(PUBLIC_SCALE * _clamp(d_value) + modifier, 0.0, PUBLIC_SCALE)


def collector_appeal_v4_candidate_multiplicative(
    d: Any,
    h: Any,
    p: Any,
    *,
    gain: float,
    penalty_damping: float = 1.0,
    h_weight: float = STRUCTURAL_H_WEIGHT,
    p_weight: float = STRUCTURAL_P_WEIGHT,
) -> Optional[float]:
    """``CA = 100*D * (1 + gain * centred_structure)``. RESEARCH ONLY.

    Structure scales a set's OWN desirability instead of adding an absolute
    amount, so it can never manufacture appeal for a set that has none: at
    ``D = 0`` every structure scores 0. The cost is that the same structural
    advantage is worth more points to an already-desirable set, which widens the
    top of the table and narrows the bottom - reported, not assumed.

    ``dCA/dD = 100*(1 + gain*centred) > 0`` for every ``gain < 1``.
    """
    if not 0.0 <= gain < 1.0:
        raise ValueError("gain must be in [0, 1)")
    d_value = _as_float(d)
    if d_value is None:
        return None
    s = structural_index(h, p, h_weight=h_weight, p_weight=p_weight)
    if s is None:
        return None
    centred = 2.0 * s - 1.0
    if centred < 0.0:
        centred *= penalty_damping
    return _clamp(PUBLIC_SCALE * _clamp(d_value) * (1.0 + gain * centred), 0.0, PUBLIC_SCALE)


def max_overturnable_d_gap_points(ceiling: float, penalty_damping: float = 1.0) -> float:
    """The additive family's inversion boundary, in public D points.

    Derived, not measured: the widest possible structural swing is
    ``+ceiling`` for the challenger and ``-ceiling*damping`` for the incumbent,
    so any D gap strictly larger than the sum can never be overturned by
    structure alone, at any H or P.
    """
    return ceiling * (1.0 + penalty_damping)


# ---------------------------------------------------------------------------
# The comparison registry: baselines and candidates, one callable each.
# ---------------------------------------------------------------------------


def _baseline_d_only(d: Any, h: Any, p: Any) -> Optional[float]:
    value = _as_float(d)
    return None if value is None else PUBLIC_SCALE * _clamp(value)


def _baseline_v3(d: Any, h: Any, p: Any) -> Optional[float]:
    score = compute_collector_appeal_v3(d, h, p)
    return None if score is None else PUBLIC_SCALE * score


def _baseline_ca7(d: Any, h: Any, p: Any) -> Optional[float]:
    score = compute_collector_appeal_ca7(d, p, lam=CA7_PRODUCTION_LAMBDA)
    return None if score is None else PUBLIC_SCALE * score


def _baseline_v2(d: Any, h: Any, p: Any) -> Optional[float]:
    score = compute_collector_appeal_v2(d, h, p)
    return None if score is None else PUBLIC_SCALE * score


def _additive(ceiling: float, **kwargs: Any):
    def scorer(d: Any, h: Any, p: Any) -> Optional[float]:
        return collector_appeal_v4_candidate_additive(d, h, p, ceiling=ceiling, **kwargs)

    return scorer


def _multiplicative(gain: float, **kwargs: Any):
    def scorer(d: Any, h: Any, p: Any) -> Optional[float]:
        return collector_appeal_v4_candidate_multiplicative(d, h, p, gain=gain, **kwargs)

    return scorer


def candidate_registry() -> Dict[str, Dict[str, Any]]:
    """Every model in the comparison, keyed. Order is the reporting order.

    ``family`` distinguishes the three existing models (which must be reproduced
    exactly, never re-derived) from the research candidates.
    """
    registry: Dict[str, Dict[str, Any]] = {
        "D_only": {
            "label": "D only (no structure)",
            "family": "reference",
            "formula": "CA = 100*D",
            "scorer": _baseline_d_only,
            "max_flip_gap": 0.0,
        },
        "baseline_A_v3": {
            "label": "Baseline A - production V3",
            "family": "existing",
            "formula": "CA = 100*(0.40D + 0.35H + 0.25P)",
            "scorer": _baseline_v3,
            "max_flip_gap": None,
        },
        "baseline_B_ca7": {
            "label": "Baseline B - legacy CA7",
            "family": "existing",
            "formula": "CA = 100*(D + 0.50*P*(1-D))",
            "scorer": _baseline_ca7,
            "max_flip_gap": None,
        },
        "baseline_C_v2": {
            "label": "Baseline C - bounded V2",
            "family": "existing",
            "formula": "CA = 100*(D + 0.50*(0.60H + 0.40P)*(1-D))",
            "scorer": _baseline_v2,
            "max_flip_gap": None,
        },
    }

    for ceiling in MODIFIER_CEILING_GRID:
        for damping in PENALTY_DAMPING_GRID:
            suffix = "" if damping == 1.0 else f"_damp{int(damping*100)}"
            key = f"cand_D_additive_c{int(ceiling)}{suffix}"
            registry[key] = {
                "label": f"Candidate D - centred H/P modifier, ceiling +/-{ceiling:g}"
                + ("" if damping == 1.0 else f", penalty x{damping:g}"),
                "family": "candidate",
                "formula": f"CA = 100*D + {ceiling:g}*(2S-1)"
                + ("" if damping == 1.0 else f" [downside x{damping:g}]"),
                "scorer": _additive(ceiling, penalty_damping=damping),
                "max_flip_gap": max_overturnable_d_gap_points(ceiling, damping),
            }

    # Candidate E: H-dominant, P reduced to a near-tiebreaker.
    registry["cand_E_h_dominant_c4"] = {
        "label": "Candidate E - H-dominant (0.85H/0.15P), ceiling +/-4",
        "family": "candidate",
        "formula": "CA = 100*D + 4*(2S-1), S = 0.85*sH + 0.15*sP",
        "scorer": _additive(4.0, h_weight=0.85, p_weight=0.15),
        "max_flip_gap": max_overturnable_d_gap_points(4.0),
    }

    # Candidate F: is P needed at all?
    registry["cand_F_d_plus_h_c4"] = {
        "label": "Candidate F - D + H only, ceiling +/-4",
        "family": "candidate",
        "formula": "CA = 100*D + 4*(2*sH - 1)",
        "scorer": _additive(4.0, h_weight=1.0, p_weight=0.0),
        "max_flip_gap": max_overturnable_d_gap_points(4.0),
    }

    # The P-audit control: D + P only, same budget.
    registry["cand_P_only_control_c4"] = {
        "label": "P audit control - D + P only, ceiling +/-4",
        "family": "candidate",
        "formula": "CA = 100*D + 4*(2*sP - 1)",
        "scorer": _additive(4.0, h_weight=0.0, p_weight=1.0),
        "max_flip_gap": max_overturnable_d_gap_points(4.0),
    }

    for gain in MULTIPLICATIVE_GAIN_GRID:
        registry[f"cand_G_multiplicative_g{int(gain*100)}"] = {
            "label": f"Candidate G - multiplicative, gain {gain:g}",
            "family": "candidate",
            "formula": f"CA = 100*D * (1 + {gain:g}*(2S-1))",
            "scorer": _multiplicative(gain),
            "max_flip_gap": None,  # D-dependent; measured rather than derived
        }

    # The FROZEN candidate and its P ablation twin. Added here, at the end, so
    # every analysis in the audit covers them automatically and none of them can
    # be run against a stale hand-copied definition. Defined further down the
    # module; this function is only ever called after import completes.
    registry[FROZEN_CANDIDATE_KEY] = {
        "label": "FROZEN candidate - asymmetric H70/P30, +4.0 / -2.0",
        "family": "frozen_candidate",
        "formula": FROZEN_FORMULA_EXPRESSION,
        "scorer": lambda d, h, p: collector_appeal_v4_candidate_frozen(d, h, p),
        "max_flip_gap": FROZEN_MAX_PAIRWISE_STRUCTURAL_ADVANTAGE,
    }
    registry[FROZEN_ABLATION_KEY] = {
        "label": "P ABLATION - asymmetric H only, +4.0 / -2.0",
        "family": "frozen_ablation",
        "formula": "S = sH; " + FROZEN_FORMULA_EXPRESSION.split("S = 0.70*sH + 0.30*sP; ")[-1],
        "scorer": lambda d, h, p: collector_appeal_v4_candidate_frozen_h_only(d, h, p),
        "max_flip_gap": FROZEN_MAX_PAIRWISE_STRUCTURAL_ADVANTAGE,
    }
    return registry


# The candidate the study recommends. Recorded here so the recommendation is a
# reviewable constant rather than a sentence in a document, and so a test can
# assert it is NOT wired to any canonical path.
RECOMMENDED_CANDIDATE_KEY = "cand_D_additive_c4_damp50"


# ===========================================================================
# THE FROZEN CANDIDATE
#
# Everything above is the exploration that led here and stays for comparison.
# Everything below is the ONE frozen model, stated so that no reader has to
# reconstruct it from a grid entry, and so that no future edit can change what a
# score under this version string means without changing the version string.
# ===========================================================================

# THE ASYMMETRY IS IN THE NAME. Calling this "c4" or writing it as
# ``D + 4*(2S-1)`` would be a false statement of the model: the downside is
# damped to half, so the floor is -2 and not -4. A version identifier that omits
# the floor would let a reader reproduce the wrong number and believe they had
# reproduced the right one.
FROZEN_CANDIDATE_KEY = "collector_appeal_v4_candidate_asymmetric_h70p30_up4_down2"
FROZEN_CANDIDATE_VERSION = (
    "collector_appeal_v4_candidate_asym_d_plus_h70p30_ceil4_floor2_research_v1"
)
FROZEN_CANDIDATE_FORMULA_VERSION = "collector_appeal_v4_centred_asymmetric_modifier_v1"
FROZEN_CANDIDATE_STATUS = "research_candidate_frozen_not_canonical"

# --- H transform: log2 wait-time anchors -----------------------------------
FROZEN_H_ANCHOR_ZERO_ONE_IN_N = 16.0    # sH = 0.0
FROZEN_H_ANCHOR_NEUTRAL_ONE_IN_N = 8.0  # sH = 0.5  (NEUTRAL)
FROZEN_H_ANCHOR_ONE_ONE_IN_N = 4.0      # sH = 1.0

# --- P transform: linear dual-path anchors ---------------------------------
FROZEN_P_ANCHOR_ZERO = 0.10             # sP = 0.0
FROZEN_P_ANCHOR_NEUTRAL = 0.30          # sP = 0.5  (NEUTRAL)
FROZEN_P_ANCHOR_ONE = 0.50              # sP = 1.0

# --- structural blend ------------------------------------------------------
FROZEN_H_WEIGHT = 0.70
FROZEN_P_WEIGHT = 0.30
FROZEN_NEUTRAL_S = 0.50                 # S at which the modifier is exactly 0

# --- the asymmetric modifier, in PUBLIC POINTS -----------------------------
FROZEN_MODIFIER_CEILING = 4.0           # maximum POSITIVE modifier, at S = 1
FROZEN_DOWNSIDE_DAMPING = 0.50          # the negative branch's multiplier
FROZEN_MODIFIER_FLOOR = -FROZEN_MODIFIER_CEILING * FROZEN_DOWNSIDE_DAMPING  # = -2.0

# --- the single behavioural promise ---------------------------------------
# The widest D gap structure can overturn: best-structured challenger (+4.0)
# against worst-structured incumbent (-2.0). Derived, then verified by
# exhaustive search in the test suite.
FROZEN_MAX_PAIRWISE_STRUCTURAL_ADVANTAGE = FROZEN_MODIFIER_CEILING - FROZEN_MODIFIER_FLOOR  # 6.0

# --- bounds ----------------------------------------------------------------
FROZEN_OUTPUT_DOMAIN = (0.0, 100.0)

# THE MONOTONICITY CONTRACT, STATED RATHER THAN IMPLIED
# ----------------------------------------------------
# The intended contract is:
#
#   NON-DECREASING in D everywhere on [0, 1];
#   STRICTLY INCREASING in D on the UNSATURATED REGION, which is
#       100*D + m(H, P)  strictly inside (0, 100).
#
# Ties can arise ONLY where the clamp binds, and the clamp can bind only for
#   D > (100 - 4.0)/100 = 0.96   at the top, or
#   D < 2.0/100        = 0.02    at the bottom.
# No set in the eligible cohort is in either region (max D = 0.9548, min
# D = 0.5107), so on real data the function is strictly increasing in D
# throughout - but that is a fact about the DATA, not about the FORMULA, and the
# two are recorded separately here on purpose.
#
# The clamp is retained rather than engineered away. The alternatives were:
#   (a) taper the bonus into the last few points of headroom - which reintroduces
#       exactly the (1-D) headroom shrinkage that made V2 a restatement of D,
#       precisely for the elite sets the tiebreaker exists to separate;
#   (b) let the score exceed 100 - which breaks the published "out of 100" claim.
# Clamping, with the saturation region named and monitored, is the least
# dishonest of the three. The audit reports the saturating-set count every run;
# a cohort that ever puts a set above D = 0.96 is a review trigger, not a silent
# tie.
FROZEN_MONOTONICITY_CONTRACT = {
    "in_d": "non_decreasing_everywhere_strictly_increasing_off_the_clamp",
    "in_h": "non_decreasing_everywhere",
    "in_p": "non_decreasing_everywhere",
    "upper_saturation_begins_above_d": (100.0 - FROZEN_MODIFIER_CEILING) / 100.0,
    "lower_saturation_begins_below_d": -FROZEN_MODIFIER_FLOOR / 100.0,
    "ties_possible_only_inside_saturation": True,
}

FROZEN_MISSING_DATA_POLICY = {
    "missing_input_returns": "None",
    "never_substitutes_zero": True,
    "never_substitutes_d": True,
    "h_must_be_strictly_positive": True,
}

# The exact formula, as one unambiguous string. Written out with BOTH branches
# because a single-branch summary would misstate the model.
FROZEN_FORMULA_EXPRESSION = (
    "sH = clamp01((log2(H) - log2(1/16)) / (log2(1/4) - log2(1/16))); "
    "sP = clamp01((P - 0.10) / (0.50 - 0.10)); "
    "S = 0.70*sH + 0.30*sP; "
    "z = 2*S - 1; "
    "m = 4.0*z if z >= 0 else 2.0*z; "
    "CA = clamp(100*D + m, 0, 100)"
)


def collector_appeal_v4_candidate_frozen(d: Any, h: Any, p: Any) -> Optional[float]:
    """THE frozen candidate. RESEARCH ONLY - not canonical, not published.

    ``CA = clamp(100*D + m, 0, 100)`` where ``m`` rises to +4.0 for perfect
    obtainability and falls to only -2.0 for the worst: the branches are
    deliberately asymmetric, because a set whose desirable content is hard to
    reach is not thereby an unappealing set, while a set that hands you desirable
    cards readily has genuinely delivered something.

    Implemented as a thin, explicit call into the shared modifier rather than as
    its own arithmetic, so the frozen model and the grid entry it was chosen from
    can never disagree. A test asserts they are identical on a dense grid.
    """
    return collector_appeal_v4_candidate_additive(
        d,
        h,
        p,
        ceiling=FROZEN_MODIFIER_CEILING,
        penalty_damping=FROZEN_DOWNSIDE_DAMPING,
        h_weight=FROZEN_H_WEIGHT,
        p_weight=FROZEN_P_WEIGHT,
    )


def collector_appeal_v4_candidate_frozen_h_only(d: Any, h: Any, p: Any = None) -> Optional[float]:
    """The P ABLATION twin: identical in every respect except that P is absent.

    Same D input, same H transform and anchors, same neutral point, same +4.0
    ceiling, same -2.0 floor, same clamp, same missing-data policy. The ONLY
    difference is ``S = sH`` instead of ``S = 0.70*sH + 0.30*sP``, so any
    difference in behaviour between this and the frozen candidate is attributable
    to P and to nothing else. ``p`` is accepted and ignored so the two share a
    call signature.
    """
    return collector_appeal_v4_candidate_additive(
        d,
        h,
        p,
        ceiling=FROZEN_MODIFIER_CEILING,
        penalty_damping=FROZEN_DOWNSIDE_DAMPING,
        h_weight=1.0,
        p_weight=0.0,
    )


FROZEN_ABLATION_KEY = "collector_appeal_v4_candidate_asymmetric_h_only_up4_down2"


def frozen_candidate_assumptions() -> Dict[str, Any]:
    """Every assumption capable of changing a frozen-candidate score.

    Hashed into the fingerprint below. Version identifiers and the status label
    are recorded but EXCLUDED from the hash for the same reason the canonical
    fingerprint excludes them: relabelling a model changes no computed number,
    and hashing a label would mark every score stale for a rename.
    """
    return {
        "formula_expression": FROZEN_FORMULA_EXPRESSION,
        "h_transform": {
            "kind": "log2_wait_time",
            "anchor_zero_one_in_n": FROZEN_H_ANCHOR_ZERO_ONE_IN_N,
            "anchor_neutral_one_in_n": FROZEN_H_ANCHOR_NEUTRAL_ONE_IN_N,
            "anchor_one_one_in_n": FROZEN_H_ANCHOR_ONE_ONE_IN_N,
            "clamped": True,
            "requires_strictly_positive_h": True,
        },
        "p_transform": {
            "kind": "linear",
            "anchor_zero": FROZEN_P_ANCHOR_ZERO,
            "anchor_neutral": FROZEN_P_ANCHOR_NEUTRAL,
            "anchor_one": FROZEN_P_ANCHOR_ONE,
            "clamped": True,
        },
        "structural_blend": {"h_weight": FROZEN_H_WEIGHT, "p_weight": FROZEN_P_WEIGHT},
        "neutral_structural_index": FROZEN_NEUTRAL_S,
        "modifier": {
            "positive_ceiling_points": FROZEN_MODIFIER_CEILING,
            "downside_damping": FROZEN_DOWNSIDE_DAMPING,
            "negative_floor_points": FROZEN_MODIFIER_FLOOR,
            "asymmetric": True,
            "centred_at_neutral": True,
        },
        "max_pairwise_structural_advantage_points": FROZEN_MAX_PAIRWISE_STRUCTURAL_ADVANTAGE,
        "output_domain": list(FROZEN_OUTPUT_DOMAIN),
        "monotonicity_contract": FROZEN_MONOTONICITY_CONTRACT,
        "missing_data_policy": FROZEN_MISSING_DATA_POLICY,
        "d_is_rescaled": False,
        "cohort_relative_normalization": False,
        "financial_inputs": [],
    }


def frozen_candidate_fingerprint() -> str:
    """SHA-256 over the frozen assumptions.

    Uses the CANONICAL fingerprint machinery rather than a second hashing
    implementation, so the candidate's identity is computed by the same
    deterministic canonicalization the production metric uses.
    """
    from backend.desirability.collector_appeal_fingerprint import fingerprint_assumptions

    return fingerprint_assumptions(frozen_candidate_assumptions())


def frozen_candidate_identity() -> Dict[str, Any]:
    """Human-readable identity plus the hash. Never stored on a canonical path."""
    return {
        "key": FROZEN_CANDIDATE_KEY,
        "version": FROZEN_CANDIDATE_VERSION,
        "formulaVersion": FROZEN_CANDIDATE_FORMULA_VERSION,
        "status": FROZEN_CANDIDATE_STATUS,
        "formula": FROZEN_FORMULA_EXPRESSION,
        "modifierCeiling": FROZEN_MODIFIER_CEILING,
        "modifierFloor": FROZEN_MODIFIER_FLOOR,
        "maxPairwiseStructuralAdvantage": FROZEN_MAX_PAIRWISE_STRUCTURAL_ADVANTAGE,
        "monotonicityContract": dict(FROZEN_MONOTONICITY_CONTRACT),
        "fingerprint": frozen_candidate_fingerprint(),
        "fingerprintAlgorithm": "sha256",
    }


def score_all(d: Any, h: Any, p: Any) -> Dict[str, Optional[float]]:
    """Every registered model's public score for one set."""
    return {key: entry["scorer"](d, h, p) for key, entry in candidate_registry().items()}


def structural_diagnostics(h: Any, p: Any) -> Dict[str, Optional[float]]:
    """The structural index and its parts, for interpretability tables."""
    return {
        "sH": h_structural_index(h),
        "sP": p_structural_index(p),
        "S": structural_index(h, p),
        "centred": (
            None
            if structural_index(h, p) is None
            else 2.0 * float(structural_index(h, p)) - 1.0
        ),
    }


# Defined last: ``candidate_registry`` now references the frozen constants above,
# so the key tuple can only be materialized once the module is fully loaded.
CANDIDATE_KEYS: Tuple[str, ...] = tuple(candidate_registry())
