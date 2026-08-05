"""Pre-registered Collector Appeal candidate grid (CA8 family). RESEARCH ONLY.

WHAT THIS IS FOR
----------------
The canonical Collector Appeal already shipped on this branch as

    CA = D + 0.50 * (0.60F + 0.40P) * (1 - D)

which is exactly the primary candidate this grid registers as
``CA8_D_H60_P40_L50``. The grid exists so that choice can be EVALUATED against
its own sensitivity neighbourhood and against the formulas it replaced - not so
it can be re-selected. Reading a number off this grid and shipping it would be
promoting a candidate on the strength of a comparison it was built to lose or
win; the production formula lives in ``backend.desirability.collector_appeal``
and is not touched from here.

Nothing in this module is imported by a scoring, persistence, publication or
ranking path. It computes candidate scores from already-computed D, H and P and
performs no I/O.

NAMING: ``H`` HERE IS ``F`` IN PRODUCTION - ONE QUANTITY, TWO LABELS
-------------------------------------------------------------------
The validation brief names the frequency term ``H``. The shipping code names the
same quantity ``F`` (``desirable_outcome_frequency``). They are THE SAME NUMBER:

    H === F === P(a modeled pack contains at least one card tied to an eligible
                  desirable Pokemon subject)

This module uses ``H`` in its candidate identifiers, because those identifiers
are the brief's traceability contract and must match it exactly. It uses ``H``
in its function signatures for the same reason. Everywhere it consumes a real
value it reads the production ``F`` through
``backend.desirability.desirable_outcome_frequency`` - there is no second
implementation, and ``ALIAS_NOTE`` below is published into the manifest so a
reader of the artifacts is never left guessing whether H and F differ.

THE FAMILY
----------
    S  = alpha * H + (1 - alpha) * P          (structural opening appeal)
    CA = D + lambda * S * (1 - D)             (bounded headroom)

``alpha`` splits the structural term between frequency and dual-path depth.
``lambda`` is the headroom gain: the share of a set's remaining appeal (1 - D)
that perfect structure may claim.

PRE-REGISTRATION IS THE POINT
-----------------------------
The nine combinations below were fixed BEFORE any result in this validation
phase was examined, and the primary candidate was fixed before the grid. The
selection rule is declared here, in code, rather than left to the report:

    The primary candidate is alpha=0.60, lambda=0.50. It does not change
    because another cell correlates better with price, produces preferred
    rankings, moves a chosen set upward, maximizes rank movement, or tells a
    cleaner story.

A test walks this module's AST to assert there is no optimizer, no search loop
over the grid, no `max(...)`/`sorted(...)` over a fitted objective, and no
market-price identifier anywhere in the candidate path. Those are the mechanical
guards; the constant above is the substantive one.
"""

from __future__ import annotations

import math
from typing import Any, Dict, Mapping, Optional, Tuple

# Read, never redefined. If the production formula's constants move, the grid's
# primary cell moves with them and the mismatch test fails loudly rather than
# letting the "primary candidate" silently stop describing what shipped.
from backend.desirability.collector_appeal import (
    COLLECTOR_APPEAL_DUAL_PATH_WEIGHT,
    COLLECTOR_APPEAL_FREQUENCY_WEIGHT,
    COLLECTOR_APPEAL_HEADROOM_GAIN,
    COLLECTOR_APPEAL_V3_INPUT_ORDER,
    COLLECTOR_APPEAL_V3_WEIGHTS,
)

CANDIDATE_FAMILY_VERSION = "collector_appeal_ca8_pre_registered_grid_v1"

ALIAS_NOTE = (
    "H (this module, and the validation brief) and F (production, "
    "backend.desirability.desirable_outcome_frequency) are the same quantity: "
    "P(a modeled pack contains at least one card tied to an eligible desirable "
    "Pokemon subject). There is one implementation, in production; this module "
    "consumes it and never recomputes it."
)

# ---------------------------------------------------------------------------
# PRE-REGISTERED GRIDS
# ---------------------------------------------------------------------------
# Registered before results were examined. A test pins these exact tuples, so
# adding a cell after seeing an outcome cannot pass review silently.

COLLECTOR_APPEAL_FREQUENCY_WEIGHT_GRID: Tuple[float, ...] = (0.50, 0.60, 0.70)
COLLECTOR_APPEAL_HEADROOM_GAIN_GRID: Tuple[float, ...] = (0.25, 0.50, 0.75)

# The primary candidate. NOT a result of the grid - an input to it.
PRIMARY_FREQUENCY_WEIGHT: float = 0.60
PRIMARY_HEADROOM_GAIN: float = 0.50

SELECTION_RULE = (
    "The primary candidate is fixed at alpha=0.60, lambda=0.50 on construct "
    "grounds and is NOT selected from the grid. The other eight cells are "
    "sensitivity variants reported for completeness. No cell is promoted "
    "because it correlates better with price, produces preferred rankings, "
    "moves a specific set upward, maximizes rank movement, or produces a "
    "cleaner narrative."
)


def candidate_key(alpha: float, lam: float) -> str:
    """``CA8_D_H60_P40_L50`` - the scientific traceability identifier.

    Encodes all three weights, including the redundant P weight, so an
    identifier read in isolation (in a CSV, a chart axis, a commit message)
    fully determines the formula that produced it. ``CA8_D_H60_L50`` would
    require the reader to know that P's weight is ``1 - alpha``.

    The PUBLIC product name, if any of this is ever promoted, stays "Collector
    Appeal". These keys are for traceability, never for display.
    """
    return (
        f"CA8_D_H{int(round(alpha * 100))}"
        f"_P{int(round((1.0 - alpha) * 100))}"
        f"_L{int(round(lam * 100))}"
    )


PRIMARY_CANDIDATE_KEY = candidate_key(PRIMARY_FREQUENCY_WEIGHT, PRIMARY_HEADROOM_GAIN)

# Deterministic order: alpha-major, then lambda. Iteration order of the grid is
# part of the artifact contract - a reordering would silently reshuffle every
# row of every CSV keyed by position.
CANDIDATE_GRID: Tuple[Tuple[float, float], ...] = tuple(
    (alpha, lam)
    for alpha in COLLECTOR_APPEAL_FREQUENCY_WEIGHT_GRID
    for lam in COLLECTOR_APPEAL_HEADROOM_GAIN_GRID
)

CANDIDATE_KEYS: Tuple[str, ...] = tuple(candidate_key(a, l) for a, l in CANDIDATE_GRID)


def _as_float(value: Any) -> Optional[float]:
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return None
    return parsed if math.isfinite(parsed) else None


def _clamp(value: float, low: float = 0.0, high: float = 1.0) -> float:
    return max(low, min(high, value))


def structural_opening_appeal(h: Any, p: Any, alpha: float) -> Optional[float]:
    """``S = alpha * H + (1 - alpha) * P`` on [0, 1].

    Returns None - never 0.0 - when either input is missing. Both are required:
    a structural term computed from one of the two would silently mean something
    different from the term the formula documents, while still producing a
    number that sorts.
    """
    h_value = _as_float(h)
    p_value = _as_float(p)
    if h_value is None or p_value is None:
        return None
    a = float(alpha)
    return _clamp(a * _clamp(h_value) + (1.0 - a) * _clamp(p_value))


def compute_candidate(d: Any, h: Any, p: Any, *, alpha: float, lam: float) -> Optional[float]:
    """``CA = D + lambda * (alpha*H + (1-alpha)*P) * (1 - D)`` on [0, 1].

    Exact properties, all asserted in the unit tests, for every (alpha, lambda)
    in [0,1]x[0,1]:

      * ``H = 0, P = 0``  -> ``CA = D``            (no structure costs nothing)
      * ``D = 1``         -> ``CA = 1``            (already at the ceiling)
      * ``dCA/dD = 1 - lambda*S >= 1 - lambda``    (non-decreasing in D)
      * ``dCA/dH = lambda*alpha*(1-D) >= 0``       (non-decreasing in H)
      * ``dCA/dP = lambda*(1-alpha)*(1-D) >= 0``   (non-decreasing in P)
      * ``CA <= 1``                                (bounded by the headroom factor)

    Returns None - never 0.0 - when any of D, H or P is missing. Defaulting a
    structural input to zero would assert the set has no desirable outcomes,
    which absent data does not support.
    """
    d_value = _as_float(d)
    if d_value is None:
        return None
    structural = structural_opening_appeal(h, p, alpha)
    if structural is None:
        return None
    d_value = _clamp(d_value)
    return _clamp(d_value + float(lam) * structural * (1.0 - d_value))


def compute_all_candidates(d: Any, h: Any, p: Any) -> Dict[str, Optional[float]]:
    """Every pre-registered candidate for one set, keyed by traceability id.

    Always returns all nine keys. A missing input yields None for all of them
    rather than a short dict, so a caller cannot mistake "unavailable" for "not
    in the grid".
    """
    return {
        candidate_key(alpha, lam): compute_candidate(d, h, p, alpha=alpha, lam=lam)
        for alpha, lam in CANDIDATE_GRID
    }


def compute_primary(d: Any, h: Any, p: Any) -> Optional[float]:
    """The primary candidate, alpha=0.60 lambda=0.50.

    Algebraically identical to the shipping
    ``collector_appeal.compute_collector_appeal_v2``. A test asserts the two
    agree across a dense grid of inputs, so this module cannot drift into
    describing a formula production does not compute.
    """
    return compute_candidate(
        d, h, p, alpha=PRIMARY_FREQUENCY_WEIGHT, lam=PRIMARY_HEADROOM_GAIN
    )


def decomposition(d: Any, h: Any, p: Any, *, alpha: float, lam: float) -> Dict[str, Any]:
    """Per-set breakdown, derived from the SAME call that produced the score."""
    score = compute_candidate(d, h, p, alpha=alpha, lam=lam)
    structural = structural_opening_appeal(h, p, alpha)
    d_value = _as_float(d)
    return {
        "candidateKey": candidate_key(alpha, lam),
        "alpha": float(alpha),
        "lambda": float(lam),
        "d": d_value,
        "h": _as_float(h),
        "p": _as_float(p),
        "structuralOpeningAppeal": structural,
        "score": score,
        "headroomBonus": (
            score - d_value if score is not None and d_value is not None else None
        ),
    }


def candidate_registry() -> Dict[str, Any]:
    """The pre-registration record, published verbatim into the manifest."""
    return {
        "familyVersion": CANDIDATE_FAMILY_VERSION,
        "formula": "CA = D + lambda * (alpha*H + (1-alpha)*P) * (1 - D)",
        "frequencyWeightGrid": list(COLLECTOR_APPEAL_FREQUENCY_WEIGHT_GRID),
        "headroomGainGrid": list(COLLECTOR_APPEAL_HEADROOM_GAIN_GRID),
        "primaryCandidateKey": PRIMARY_CANDIDATE_KEY,
        "primaryAlpha": PRIMARY_FREQUENCY_WEIGHT,
        "primaryLambda": PRIMARY_HEADROOM_GAIN,
        "candidateKeys": list(CANDIDATE_KEYS),
        "selectionRule": SELECTION_RULE,
        "aliasNote": ALIAS_NOTE,
        "matchesProductionFormula": primary_matches_production(),
        "matchesProductionFormulaNote": (
            "FALSE is the expected value now. This CA8 grid is the bounded-headroom "
            "family, and production has moved to the Collector Appeal V3 balanced "
            "weighted sum (0.40D + 0.35H + 0.25P). The grid is retained as the "
            "family the shipping formula is compared AGAINST - the primary cell "
            "still reproduces the superseded Collector Appeal V2 exactly, which is "
            "what makes the V2-vs-V3 comparison honest."
        ),
        "supersededFamilyConstants": {
            "frequencyWeight": COLLECTOR_APPEAL_FREQUENCY_WEIGHT,
            "dualPathWeight": COLLECTOR_APPEAL_DUAL_PATH_WEIGHT,
            "headroomGain": COLLECTOR_APPEAL_HEADROOM_GAIN,
        },
        "canonicalProductionKey": CANONICAL_PRODUCTION_KEY,
        "overallWeightGrid": list(OVERALL_COLLECTOR_APPEAL_WEIGHT_GRID),
        "canonicalOverallWeight": canonical_overall_weight(),
    }


def primary_matches_production() -> bool:
    """Does the pre-registered CA8 primary still describe the shipping formula?

    Reported rather than asserted at import time, because a mismatch is a
    FINDING for the validation report - "production moved away from the candidate
    this grid evaluates" - not a reason to crash a research script that is
    otherwise still able to describe both.

    It now returns False, and that is the correct answer: production ships the
    Collector Appeal V3 balanced sum, which is not in this bounded-headroom
    family at all. The grid's primary cell still reproduces Collector Appeal V2
    exactly, so the comparison it supports remains valid.
    """
    return (
        abs(PRIMARY_FREQUENCY_WEIGHT - COLLECTOR_APPEAL_FREQUENCY_WEIGHT) < 1e-12
        and abs((1.0 - PRIMARY_FREQUENCY_WEIGHT) - COLLECTOR_APPEAL_DUAL_PATH_WEIGHT) < 1e-12
        and abs(PRIMARY_HEADROOM_GAIN - COLLECTOR_APPEAL_HEADROOM_GAIN) < 1e-12
        and _primary_matches_canonical_entry_point()
    )


def _primary_matches_canonical_entry_point() -> bool:
    """Does the grid's primary agree with the CANONICAL production entry point?

    Checked on a dense probe rather than on constants alone: matching weights in
    a family production no longer uses would still report True, which is exactly
    the false reassurance this function exists to avoid.
    """
    from backend.desirability.collector_appeal import compute_collector_appeal_v3

    for d in (0.0, 0.25, 0.5, 0.75, 1.0):
        for h in (0.0, 0.5, 1.0):
            for p in (0.0, 0.5, 1.0):
                primary = compute_primary(d, h, p)
                canonical = compute_collector_appeal_v3(d, h, p)
                if primary is None or canonical is None:
                    return False
                if abs(primary - canonical) > 1e-12:
                    return False
    return True


# ---------------------------------------------------------------------------
# Comparison formulas (NOT candidates - the things the candidates are judged against)
# ---------------------------------------------------------------------------
# Held here so the validation script compares against ONE definition of each
# baseline. CA6 and legacy CA7 are re-expressed rather than imported where their
# production entry points take different arguments; a test asserts each agrees
# with its production counterpart exactly.

COMPARISON_KEYS: Tuple[str, ...] = (
    "pure_D",
    "CA6_dual_path_utility",
    "CA7_legacy_bounded_bonus_50",
    "collector_appeal_v2_bounded_headroom",
    "collector_appeal_v3_balanced",
    "chase_appeal_D_times_M",
)

# The CANONICAL production formula's key inside this study. Named so a reader of
# a CSV column can tell at a glance which column is the shipping model and which
# are the things it is being compared against.
CANONICAL_PRODUCTION_KEY = "collector_appeal_v3_balanced"
SUPERSEDED_V2_KEY = "collector_appeal_v2_bounded_headroom"
PURE_D_KEY = "pure_D"
LEGACY_CA7_KEY = "CA7_legacy_bounded_bonus_50"


def compute_comparisons(
    *, d: Any, p: Any, h: Any = None, m: Any = None
) -> Dict[str, Optional[float]]:
    """Every formula the study compares, on the same [0,1] scale.

    Pure D, CA6, legacy CA7, the superseded Collector Appeal V2 bounded-headroom
    formula, the canonical Collector Appeal V3 balanced formula, and Chase
    Appeal.

    Every one is IMPORTED from production rather than re-expressed here, so a
    comparison baseline cannot drift from the formula it claims to be. ``h`` is
    optional only so an older caller that predates the V2/V3 columns still runs;
    without it those two columns report unavailable rather than a wrong number.
    """
    from backend.desirability.collector_appeal import (
        CA7_PRODUCTION_LAMBDA,
        compute_chase_appeal,
        compute_collector_appeal_ca7,
        compute_collector_appeal_v2,
        compute_collector_appeal_v3,
        dual_path_utility,
    )

    d_value = _as_float(d)
    utility = dual_path_utility(p)
    return {
        "pure_D": d_value,
        "CA6_dual_path_utility": (
            None if (d_value is None or utility is None) else _clamp(d_value * utility)
        ),
        "CA7_legacy_bounded_bonus_50": compute_collector_appeal_ca7(
            d_value, p, lam=CA7_PRODUCTION_LAMBDA
        ),
        SUPERSEDED_V2_KEY: compute_collector_appeal_v2(d_value, h, p),
        CANONICAL_PRODUCTION_KEY: compute_collector_appeal_v3(d_value, h, p),
        "chase_appeal_D_times_M": compute_chase_appeal(d_value, m),
    }


# ---------------------------------------------------------------------------
# Collector Appeal V3 input-influence probes (RESEARCH ONLY)
# ---------------------------------------------------------------------------
# Two ways to "remove" an input from a weighted sum, and they answer different
# questions. Both are reported, because reporting only one invites the reader to
# assume the other would agree.
#
#   removal WITHOUT renormalization : drop the term, keep the other weights.
#       Answers "how much of the score does this input contribute?" The result
#       is not on the 0-100 scale any more, which is fine for a RANK comparison
#       and is why the score itself is not reported as a score.
#
#   drop AND renormalize            : drop the term, rescale the survivors to
#       sum to 1. Answers "what would the metric look like if it had been built
#       without this input?" - the counterfactual model, still on 0-100.
#
# Neither is a candidate. Neither is ever promoted. They exist to measure what
# the observed cohort does under the shipping weights.

COLLECTOR_APPEAL_V3_INPUT_KEYS: Tuple[str, ...] = tuple(COLLECTOR_APPEAL_V3_INPUT_ORDER)

# study-facing name -> production weight key. The study speaks D/H/P.
COLLECTOR_APPEAL_V3_STUDY_KEYS: Dict[str, str] = {
    "d": "roster_desirability",
    "h": "desirable_outcome_frequency",
    "p": "dual_path_depth",
}


def collector_appeal_v3_weight(study_key: str) -> float:
    """The production weight for one study-facing input name."""
    return float(COLLECTOR_APPEAL_V3_WEIGHTS[COLLECTOR_APPEAL_V3_STUDY_KEYS[study_key]])


def compute_v3_without_input(
    d: Any, h: Any, p: Any, *, dropped: str, renormalize: bool
) -> Optional[float]:
    """Collector Appeal V3 with one input removed, on [0, 1].

    ``dropped`` is one of ``"d"``, ``"h"``, ``"p"``. With ``renormalize=False``
    the surviving weights are unchanged, so the result is bounded above by
    ``1 - weight(dropped)``. With ``renormalize=True`` the survivors are scaled
    to sum to 1 and the result is back on [0, 1].

    Every input is still REQUIRED to be present, including the dropped one. That
    is deliberate: comparing a two-input score computed over 22 sets against a
    three-input score computed over 19 would attribute a coverage difference to
    the dropped input.
    """
    if dropped not in COLLECTOR_APPEAL_V3_STUDY_KEYS:
        raise KeyError(f"Unknown Collector Appeal input {dropped!r}")
    values = {"d": _as_float(d), "h": _as_float(h), "p": _as_float(p)}
    if any(value is None for value in values.values()):
        return None
    kept = {key: value for key, value in values.items() if key != dropped}
    weights = {key: collector_appeal_v3_weight(key) for key in kept}
    total = sum(weights.values())
    if renormalize:
        if total <= 0:
            return None
        weights = {key: weight / total for key, weight in weights.items()}
    return _clamp(sum(_clamp(kept[key]) * weights[key] for key in kept))


def collector_appeal_v3_contributions(d: Any, h: Any, p: Any) -> Dict[str, Optional[float]]:
    """Per-input contribution to the unit score, for the influence report.

    Delegates to the production decomposition so the study cannot report a
    contribution the shipping formula did not compute.
    """
    from backend.desirability.collector_appeal import collector_appeal_v3_decomposition

    decomposition = collector_appeal_v3_decomposition(d, h, p)
    return {
        "d": decomposition.get("dContribution"),
        "h": decomposition.get("hContribution"),
        "p": decomposition.get("pContribution"),
    }


# ---------------------------------------------------------------------------
# Overall RIP weight grid (research)
# ---------------------------------------------------------------------------
# Pre-registered, and READ from the config that owns it
# (``scoring_config.OVERALL_RIP_COLLECTOR_APPEAL_SENSITIVITY_WEIGHTS``) rather
# than restated, so the study and production cannot disagree about which weights
# are candidates and which one ships.
#
# 0.00 is the financial-only baseline and is included so every comparison has a
# "what if appeal carried no weight at all" reference column rather than an
# implied one. 0.13 and 0.14 are RESEARCH sensitivity points only: 0.14 already
# falls below the 0.95 Spearman guardrail under the existing formula, and 0.10 is
# the canonical production weight.


def _overall_weight_grid() -> Tuple[float, ...]:
    from backend.desirability.scoring_config import (
        OVERALL_RIP_COLLECTOR_APPEAL_SENSITIVITY_WEIGHTS,
    )

    return tuple(OVERALL_RIP_COLLECTOR_APPEAL_SENSITIVITY_WEIGHTS)


OVERALL_COLLECTOR_APPEAL_WEIGHT_GRID: Tuple[float, ...] = _overall_weight_grid()


def canonical_overall_weight() -> float:
    """The production Collector Appeal weight in Overall RIP, read from config."""
    from backend.desirability.scoring_config import OVERALL_RIP_V7_WEIGHTS

    return float(OVERALL_RIP_V7_WEIGHTS["collector_appeal"])


def compute_overall(financial_rip_v3: Any, collector_appeal: Any, weight: float) -> Optional[float]:
    """``Overall_w = (1 - w) * FinancialRipV3 + w * CollectorAppeal``.

    Both inputs on 0-100. Returns None when either is missing: there is no
    fallback to a financial-only number under an Overall label, for the same
    reason production has none - it would be a different model wearing the
    canonical name. At ``weight = 0`` the appeal input is still REQUIRED, so the
    baseline column covers exactly the same cohort as the weighted columns and
    a coverage difference can never be mistaken for a weight effect.
    """
    financial = _as_float(financial_rip_v3)
    appeal = _as_float(collector_appeal)
    if financial is None or appeal is None:
        return None
    w = float(weight)
    return (1.0 - w) * financial + w * appeal
