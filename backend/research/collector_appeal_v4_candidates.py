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
EXACTLY ``2 * MODIFIER_CEILING`` points, achieved only when the lower-D set has
perfect structure and the higher-D set has the worst possible structure. That
number is a design parameter, not an emergent accident, so the inversion
boundary can be stated in the spec instead of discovered in a grid search.

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

    return registry


CANDIDATE_KEYS: Tuple[str, ...] = tuple(candidate_registry())

# The candidate the study recommends. Recorded here so the recommendation is a
# reviewable constant rather than a sentence in a document, and so a test can
# assert it is NOT wired to any canonical path.
RECOMMENDED_CANDIDATE_KEY = "cand_D_additive_c4_damp50"


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
