"""Collector Appeal: a research candidate grid AND one selected production function.

TWO THINGS LIVE HERE. THEY ARE NOT THE SAME THING.
--------------------------------------------------
1. **The research candidate grid** (CA0-CA7 across every pre-registered weight and
   lambda; ``compute_collector_appeal_candidates``, ``collector_appeal_payload``,
   ``COLLECTOR_APPEAL_CANDIDATE_KEYS``). Research only. It exists to COMPARE
   candidates and is never stored, never served, and never wired into RIP. Its
   whole purpose is to show what each candidate would have done.

2. **The selected production candidate** (``compute_collector_appeal`` = CA7 at
   ``CA7_PRODUCTION_LAMBDA``; identified by ``COLLECTOR_APPEAL_VERSION`` =
   ``collector_appeal_ca7_v1``). This is a PRODUCTION CANDIDATE: one function,
   one lambda, fingerprinted, and proposed for storage as an internal candidate
   under ``diagnostics_json.collector_appeal_ca7``.

Keep the boundary sharp. Reading a number off the grid and reporting it as "the"
Collector Appeal would be reporting a candidate as a product; the grid is a menu,
and only CA7@0.50 was chosen from it - on construct grounds, never by fitting.

NOT THE PUBLIC "COLLECTOR APPEAL"
---------------------------------
The shipping ``collector_appeal_score`` column/API field is Pure/Universal
Desirability - a DIFFERENT construct that happens to share the product name. CA7
is not that metric and must not be persisted under a generic ``collector_appeal``
key. See ``docs/research/collector_appeal_product_naming_transition.md``; no
public rename is authorized.

THE RESEARCH QUESTION
---------------------
Builds on ``factorized_opening_appeal`` (which is itself research-only) and asks
a narrower question than that study did:

    Can ONE nonfinancial Collector Appeal pillar be built from D, A and M that
    genuinely represents the appeal of opening a pack?

THE CENTRAL MATHEMATICAL FACT (established, not assumed - see the results doc):

``access_transform(p) = 1 - scarcity_transform(p)`` at shared anchors. With one
card per subject this makes ``M2 == 1 - broad_access`` EXACTLY. Empirically the
cohort sits close to that line: mean ``A* + M1* - 1 = +0.040`` (range -0.175 to
+0.291), Spearman(A*, M1*) = -0.523.

So A and M are NOT two independent axes to be balanced. They are approximately
ONE axis - a position between "reachable favorites" and "elite chases" - plus a
small residual. Three consequences drive every design decision in this module:

  1. Any formula of the form ``f(A, M)`` collapses, under complementarity, to a
     function of the single variable ``A``. There is nothing to "balance".
  2. The CURVATURE a formula applies to that axis is an arbitrary authorial
     choice, not an empirical finding:
       * ``sqrt(A*M)``      -> hump: rewards the middle BY CONSTRUCTION, and is
                               NOT injective (A=0.2 and A=0.8 tie exactly).
       * ``1-(1-A)(1-M)``   -> convex: rewards the EXTREMES by construction.
       * ``wA*A + wM*M``    -> linear: at wA=wM it is CONSTANT (degenerate).
     None of these curvatures is evidence about collectors. Reporting one as
     "balanced Collector Appeal" would be presenting a modeling choice as a
     measurement.
  3. Position ALONG the A<->M axis is a TASTE axis, not a QUALITY axis. Higher D
     is better for every collector; more A at the cost of M is better only for
     collectors who prefer reachable hits. Collapsing a taste axis into a scalar
     "appeal" requires choosing whose taste to encode - which is exactly the
     collector-preference data this project does not yet have.

``DUAL_PATH_DEPTH`` (P) is the one construct here that escapes (3). It is the
share-weighted degree to which a set's desirable subjects offer BOTH a reachable
printing AND an elite chase. Wanting both is taste-free: no collector is worse
off because the Pikachu they can reach also has a chase variant. P is also the
structural REASON complementarity breaks (multi-card subjects), so it is the
honest second dimension rather than a residual artifact.

Hard rules enforced here (asserted in the unit tests):
  * No price, EV, profit, set value, or market outcome enters any candidate.
  * Desirability is applied exactly once, in ``D``.
  * Every candidate and every weight is PRE-REGISTERED as a module constant
    below. There is no search loop over weights anywhere in this module; a test
    walks the AST to assert that.
  * Fixed normalization only: no cohort percentiles, no observed-max anchors.
    Adding or removing a set can never move another set's score.
  * Missing pull data returns None ("unavailable"), never 0.

Nothing here is fitted to price.
"""

from __future__ import annotations

import math
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence, Tuple

from backend.desirability.opening_appeal import (
    EASY_PROBABILITY,
    ELITE_PROBABILITY,
    access_transform,
    scarcity_transform,
)
from backend.desirability.factorized_opening_appeal import (
    demand_shares,
    desirable_subjects,
)

# The identity of the PRODUCTION-CANDIDATE function (CA7), not of the research
# grid. Renamed from ``collector_appeal_v1_research``: that string described a
# study, and this constant now identifies a formula proposed for production
# storage. The grid below stays research-only and is not covered by this version.
COLLECTOR_APPEAL_VERSION = "collector_appeal_ca7_v1"
DUAL_PATH_DEPTH_VERSION = "dual_path_depth_v1"

# --- Product identity (see docs/research/collector_appeal_product_naming_transition.md)
#
# ``collector_appeal_score`` ALREADY EXISTS in production and is Pure/Universal
# Desirability - a different construct from CA7. Persisting CA7 under a generic
# "collector_appeal" key would put two different definitions behind one product
# name, and the ambiguity would be permanent the moment anything read it.
#
# So the stored block is namespaced ``collector_appeal_ca7`` and declares itself
# an internal candidate. The public field, API response and frontend contract are
# untouched; no rename is authorized.
COLLECTOR_APPEAL_METRIC_NAME = "collector_appeal_ca7"
COLLECTOR_APPEAL_DIAGNOSTICS_KEY = "collector_appeal_ca7"
COLLECTOR_APPEAL_PRODUCT_STATUS = "internal_candidate"

# ---------------------------------------------------------------------------
# PRE-REGISTERED candidate family.
#
# Registered BEFORE any market outcome was examined. Adding a key here after
# seeing an outcome would be candidate scanning; the test suite pins this tuple
# so such an addition cannot pass review silently.
# ---------------------------------------------------------------------------

CA4_WEIGHT_GRID: Tuple[Tuple[float, float], ...] = (
    (0.75, 0.25),
    (0.60, 0.40),
    (0.50, 0.50),
    (0.40, 0.60),
    (0.25, 0.75),
)

# CA5 = D * (wA*gA(A) + wM*gM(M) + wI*gA(A)*gM(M))
#
# gA and gM are DELIBERATELY THE IDENTITY. A and M are already fixed-anchor
# log-probability transforms (access_transform / scarcity_transform map a
# 1-in-10 pull to 1.0 and a 1-in-1000 pull to 0.0 on a log10 scale). They are
# therefore already on a principled, monotone, cohort-independent scale.
# Applying a further curvature would be an arbitrary nonlinearity - precisely
# what this research phase forbids - and any such transform would be
# indistinguishable from tuning if it were chosen after seeing an outcome.
# Identity is the disciplined default and is documented as a decision, not an
# oversight.
CA5_WEIGHT_GRID: Tuple[Tuple[float, float, float], ...] = (
    (0.45, 0.45, 0.10),
    (0.40, 0.40, 0.20),
    (0.35, 0.35, 0.30),
)

# CA6 = D * U(A, M) where U is the dual-path utility. The interpretation is
# stated in plain English in ``dual_path_utility``: reward a set for offering
# both a reachable favorite and an elite chase, with a pre-registered floor so
# that a set with no dual-path structure still scores its desirability.
CA6_DUAL_PATH_FLOOR: float = 0.50
CA6_DUAL_PATH_GAIN: float = 0.50

# CA7 = D + lambda * P * (1 - D)   (on the 0-1 scale; == D + L*P*(100-D)/100)
#
# The bounded-bonus model. Where CA6 treats absent Dual-Path structure as a
# DISCOUNT (a set with P=0 keeps only half its desirability), CA7 treats present
# Dual-Path structure as a BONUS (a set with P=0 keeps all of its desirability,
# and P raises it toward 100).
#
# The (1 - D) factor is what bounds it: the bonus is a fraction of the headroom
# a set has left, so CA7 can never exceed 1.0 and a set that is already maximally
# desirable cannot be pushed past the ceiling by structure.
#
# LAMBDA IS PRE-REGISTERED, NOT FITTED. The three values below were fixed before
# any comparison was run and are the only values evaluated. They are NOT tuned
# against price, set value, or RIP rank movement - a test walks this module's AST
# to assert no search loop exists over them.
CA7_LAMBDA_GRID: Tuple[float, ...] = (0.25, 0.50, 0.75)

# ---------------------------------------------------------------------------
# THE SELECTED PRODUCTION CANDIDATE
#
# CA7 at lambda = 0.50 was selected on CONSTRUCT grounds (see
# docs/research/collector_appeal_product_rollout.md section 7), never by fitting
# to price, set value, or RIP rank movement. lambda = 0.50 is the neutral,
# symmetric prior: dual-path structure at its maximum may claim half of a set's
# remaining appeal headroom.
#
# These are separated from the research grid above because they are what
# PRODUCTION computes. The grid stays for the comparison study; changing either
# constant below changes stored scores and must invalidate the fingerprint.
# ---------------------------------------------------------------------------
CA7_FORMULA = "CA7"
CA7_FORMULA_VERSION = "collector_appeal_ca7_bounded_bonus_v1"
CA7_PRODUCTION_LAMBDA: float = 0.50

# How the formula treats absent inputs. Pinned as a version because flipping any
# of these rules silently changes what a stored score MEANS without changing the
# formula: "missing -> None" and "missing -> 0.0" produce different numbers from
# identical data.
MISSING_DATA_POLICY_VERSION = "collector_appeal_missing_data_v1_none_never_zero"
MISSING_DATA_POLICY = {
    "missing_input_returns": "None",
    "never_substitutes_zero": True,
    "unmodeled_subjects": "renormalize_over_covered_demand_share",
    "no_desirable_subject": "dual_path_depth_is_None",
}

# Rounding and clamping are part of the formula's identity, not presentation:
# both change the stored number.
ROUNDING_POLICY_VERSION = "collector_appeal_rounding_v1"
ROUNDING_POLICY = {
    "clamp_domain": [0.0, 1.0],
    "clamp_applied_to": ["d", "p", "ca6", "ca7"],
    "round_half": "python_banker_default",
    "stored_decimal_places": 6,
}

COLLECTOR_APPEAL_CANDIDATE_KEYS: Tuple[str, ...] = (
    "CA0_desirability_only",
    "CA1_accessible",
    "CA2_chase",
    "CA3_geometric_balance",
    *(f"CA4_linear_{int(wa*100)}_{int(wm*100)}" for wa, wm in CA4_WEIGHT_GRID),
    *(f"CA5_interaction_{int(wa*100)}_{int(wm*100)}_{int(wi*100)}" for wa, wm, wi in CA5_WEIGHT_GRID),
    "CA6_dual_path_utility",
    *(f"CA7_bounded_bonus_{int(lam*100)}" for lam in CA7_LAMBDA_GRID),
)

# Behavioural classification labels.
LABEL_DESIRABILITY_RESTATED = "mostly_desirability_restated"
LABEL_ACCESSIBILITY_RESTATED = "mostly_accessibility_restated"
LABEL_CHASE_RESTATED = "mostly_chase_intensity_restated"
LABEL_RETAINS_BOTH = "retains_both_accessibility_and_chase"
LABEL_SIZE_DRIVEN = "size_driven"
LABEL_FINANCIAL_REDUNDANT = "redundant_with_a_financial_pillar"
LABEL_DISTINCT = "genuinely_distinct"
LABEL_DEGENERATE = "degenerate_by_construction"


def _as_float(value: Any) -> Optional[float]:
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return None
    return parsed if math.isfinite(parsed) else None


def _clamp(value: float, low: float = 0.0, high: float = 1.0) -> float:
    return max(low, min(high, value))


# ---------------------------------------------------------------------------
# The complement gap: the ONLY information in (A, M) that is not in A alone
# ---------------------------------------------------------------------------

def complement_gap(a_star: Any, m_star: Any) -> Optional[float]:
    """``G = A + M - 1``: signed departure from the degenerate single axis.

    Because ``access = 1 - scarcity`` at shared anchors, a set with exactly one
    card per desirable subject has ``G = 0`` identically. G is therefore not a
    correlation artifact - it is a structural measurement of how much a set's
    (A, M) pair carries beyond a single position on one axis.

    G > 0: the set offers more total reach-plus-chase than one axis allows,
           which happens when desirable subjects have MULTIPLE printings (a
           reachable one and an elite one).
    G < 0: desirable subjects sit in a dead middle - neither reachable nor
           elite - so both paths are weak at once.

    Signed, never absolute: the two directions mean opposite things and must not
    be folded together.
    """
    a = _as_float(a_star)
    m = _as_float(m_star)
    if a is None or m is None:
        return None
    return a + m - 1.0


def axis_position(a_star: Any, m_star: Any) -> Optional[float]:
    """Where a set sits on the single access<->chase axis, on [0, 1].

    ``0`` = pure elite-chase set, ``1`` = pure reachable-favorites set. Defined
    as ``A / (A + M)`` so it is invariant to the gap G: it isolates the TASTE
    coordinate from the dual-path coordinate.

    This is reported as a PROFILE coordinate, never as a quality score. A set at
    0.2 is not worse than a set at 0.8; it suits a different collector.
    """
    a = _as_float(a_star)
    m = _as_float(m_star)
    if a is None or m is None:
        return None
    total = a + m
    if total <= 0:
        return None
    return _clamp(a / total)


# ---------------------------------------------------------------------------
# Dual-Path Depth: the taste-free second axis
# ---------------------------------------------------------------------------

def subject_dual_path(
    subject: Mapping[str, Any],
    *,
    easy_probability: float = EASY_PROBABILITY,
    elite_probability: float = ELITE_PROBABILITY,
) -> Optional[Dict[str, Any]]:
    """Does ONE subject offer both a reachable printing and an elite chase?

        dual_path_s = access(p_easiest_card_s) * scarcity(p_rarest_card_s)

    The product is near 1 only when the subject has BOTH a card you can
    realistically pull AND a card that is a genuine chase - which requires at
    least two printings at different scarcities. A single-printing subject
    scores ``access(p) * (1 - access(p))``, which is bounded by 0.25, so one
    card can never masquerade as a dual path.

    Uses the easiest and rarest cards (not a union) because the question is
    whether the two ENDS exist, not how likely the subject is overall.
    Desirability magnitude never enters.
    """
    easiest: Optional[float] = None
    rarest: Optional[float] = None
    easy_card: Optional[Mapping[str, Any]] = None
    rare_card: Optional[Mapping[str, Any]] = None
    for card in subject.get("cards") or []:
        access = access_transform(
            card.get("pull_probability"),
            easy_probability=easy_probability,
            elite_probability=elite_probability,
        )
        if access is None:
            continue
        if easiest is None or access > easiest:
            easiest, easy_card = access, card
        if rarest is None or access < rarest:
            rarest, rare_card = access, card
    if easiest is None or rarest is None:
        return None
    scarcity_of_rarest = 1.0 - rarest
    return {
        "dual_path": _clamp(easiest * scarcity_of_rarest),
        "reachable_access": round(easiest, 6),
        "elite_scarcity": round(scarcity_of_rarest, 6),
        "reachable_card": (easy_card or {}).get("card_name"),
        "elite_card": (rare_card or {}).get("card_name"),
        "printing_count": len(subject.get("cards") or []),
    }


def compute_dual_path_depth(
    subjects: Sequence[Mapping[str, Any]],
    *,
    easy_probability: float = EASY_PROBABILITY,
    elite_probability: float = ELITE_PROBABILITY,
) -> Optional[Dict[str, Any]]:
    """``P = sum(q_s * dual_path_s)`` over desirable distinct subjects.

    Plain English: "for the Pokemon this set's collectors actually care about,
    how often can you both realistically pull one AND still have something to
    chase?"

    ``q_s`` are normalized demand shares, so absolute desirability cancels and
    is never applied a second time. Returns None (never 0) when no desirable
    subject carries modeled pull data.
    """
    eligible = desirable_subjects(subjects)
    if not eligible:
        return None
    shares = demand_shares(eligible)
    if not shares:
        return None

    value = 0.0
    covered = 0.0
    detail: List[Dict[str, Any]] = []
    for row in eligible:
        key = str(row.get("subject_key"))
        share = shares.get(key)
        if share is None:
            continue
        dual = subject_dual_path(
            row, easy_probability=easy_probability, elite_probability=elite_probability
        )
        if dual is None:
            continue
        covered += share
        detail.append({"subject_name": row.get("subject_name"), **dual, "demand_share": round(share, 6)})
    if covered <= 0:
        return None
    # Renormalize over subjects that actually carry modeled pull data, so an
    # unmodeled subject never silently contributes zero dual-path depth.
    for row in detail:
        row["contribution"] = round(row["demand_share"] / covered * row["dual_path"], 6)
        value += row["demand_share"] / covered * row["dual_path"]

    return {
        "value": _clamp(value),
        "version": DUAL_PATH_DEPTH_VERSION,
        "formula": "sum(q_s * access(p_easiest_s) * scarcity(p_rarest_s))",
        "anchors": {"easy_probability": easy_probability, "elite_probability": elite_probability},
        "covered_demand_share": round(covered, 6),
        "multi_printing_subject_count": sum(1 for row in detail if row["printing_count"] > 1),
        "subject_count": len(detail),
        "top_subjects": sorted(detail, key=lambda item: -item["contribution"])[:5],
    }


def dual_path_utility(p: Any) -> Optional[float]:
    """``U = floor + gain * P`` on [0, 1]. The CA6 utility.

    Plain English: a set's Collector Appeal starts from its desirability and is
    raised, by at most ``gain``, to the degree that its desirable Pokemon offer
    both a reachable printing and an elite chase.

    The floor exists so that CA6 never punishes a set for lacking dual-path
    structure below its own desirability - a set of beloved Pokemon with one
    printing each is still appealing to open. floor and gain are PRE-REGISTERED
    constants, not fitted.
    """
    value = _as_float(p)
    if value is None:
        return None
    return _clamp(CA6_DUAL_PATH_FLOOR + CA6_DUAL_PATH_GAIN * _clamp(value))


def compute_collector_appeal(d: Any, p: Any, *, lam: float = CA7_PRODUCTION_LAMBDA) -> Optional[float]:
    """THE production Collector Appeal: CA7 at the selected lambda = 0.50.

    One entry point, so preview and commit cannot diverge on which candidate or
    which lambda they compute. Returns None - never 0.0 - when either input is
    missing (see MISSING_DATA_POLICY).
    """
    return bounded_bonus_appeal(d, p, lam)


def bounded_bonus_appeal(d: Any, p: Any, lam: float) -> Optional[float]:
    """CA7: ``D + lambda * P * (1 - D)`` on [0, 1].

    Plain English: a set's Collector Appeal IS its desirability; offering both a
    reachable printing and an elite chase adds a bonus, and that bonus is a
    share of the appeal the set has not already claimed.

    Bounds and monotonicity hold exactly, for every lambda in [0, 1]:
      * P = 0  -> CA7 = D              (no dual-path structure costs nothing)
      * P = 1  -> CA7 = D + L*(1 - D)  (<= 1 for any D <= 1; equals 1 at L = 1)
      * dCA7/dP = L*(1 - D) >= 0       (non-decreasing in P)
      * dCA7/dD = 1 - L*P >= 1 - L > 0 (strictly increasing in D for L < 1)

    That last derivative is the reason (1 - D) is the right bound and a plain
    additive bonus is not: with ``D + L*P`` a high-P/low-D set could out-score a
    low-P/high-D set, letting structure overrule desirability. Here D always
    dominates.
    """
    d_value = _as_float(d)
    p_value = _as_float(p)
    if d_value is None or p_value is None:
        return None
    d_value = _clamp(d_value)
    p_value = _clamp(p_value)
    return _clamp(d_value + float(lam) * p_value * (1.0 - d_value))


# ---------------------------------------------------------------------------
# Degeneracy analysis (algebra, reported alongside every candidate)
# ---------------------------------------------------------------------------

def degeneracy_note(key: str) -> str:
    """What each candidate reduces to under exact complementarity (M = 1 - A).

    This is ALGEBRA, not an empirical claim. It states what the formula would
    measure if A and M were exact complements; the cohort is close to but not
    exactly on that line, so these describe the dominant behaviour.
    """
    if key == "CA0_desirability_only":
        return "D. Carries no structural information by construction; the simplicity benchmark."
    if key == "CA1_accessible":
        return "D*A - monotone INCREASING in A. A pure accessibility taste."
    if key == "CA2_chase":
        return "D*(1-A) - monotone DECREASING in A. A pure scarcity taste. This is D x M*."
    if key == "CA3_geometric_balance":
        return (
            "D*sqrt(A*(1-A)) - a HUMP peaking at A=0.50. Rewards the middle BY CONSTRUCTION, "
            "not by evidence. NOT INJECTIVE: A=0.2 and A=0.8 score identically, so a highly "
            "accessible set and an extreme-chase set are declared equally appealing."
        )
    if key.startswith("CA4_linear"):
        parts = key.split("_")
        wa, wm = int(parts[2]) / 100.0, int(parts[3]) / 100.0
        slope = wa - wm
        if abs(slope) < 1e-12:
            return (
                "D*((wA-wM)*A + wM) with wA=wM -> the A term CANCELS and the candidate collapses "
                "to a rescaled D (0.50*D). Zero structural content: fully DEGENERATE."
            )
        direction = "accessibility" if slope > 0 else "chase intensity"
        return (
            f"D*({slope:+.2f}*A + {wm:.2f}) - linear in A, favouring {direction}. "
            f"Structural content scales with |wA-wM| = {abs(slope):.2f}."
        )
    if key.startswith("CA5_interaction"):
        parts = key.split("_")
        wa, wm, wi = int(parts[2]) / 100.0, int(parts[3]) / 100.0, int(parts[4]) / 100.0
        slope = wa - wm
        base = "cancels (wA=wM)" if abs(slope) < 1e-12 else f"{slope:+.2f}*A"
        return (
            f"D*({base} + {wm:.2f} + {wi:.2f}*A*(1-A)) - the interaction term A*(1-A) is the SAME "
            f"hump as CA3. With wA=wM the linear part cancels and the candidate becomes a pure "
            f"rescaled hump: it rewards the middle by construction."
        )
    if key == "CA6_dual_path_utility":
        return (
            "D*(floor + gain*P). Independent of position on the A<->M axis by construction; "
            "reads the ORTHOGONAL dual-path structure instead. Does not encode a taste. "
            "Treats absent dual-path structure as a DISCOUNT: at P=0 a set scores 0.50*D."
        )
    if key.startswith("CA7_bounded_bonus"):
        lam = int(key.split("_")[-1]) / 100.0
        return (
            f"D + {lam:.2f}*P*(1-D). Like CA6 it reads the orthogonal dual-path axis and "
            f"encodes no taste, but treats dual-path structure as a BONUS rather than a "
            f"discount: at P=0 a set scores its full D, and P adds at most {lam:.0%} of the "
            f"set's remaining headroom (1-D). Bounded above by 1 for all D, P."
        )
    return "unregistered candidate"


# ---------------------------------------------------------------------------
# Candidate computation
# ---------------------------------------------------------------------------

def compute_collector_appeal_candidates(
    *,
    d: Any,
    a_star: Any,
    m_star: Any,
    dual_path_depth: Any,
) -> Dict[str, Optional[float]]:
    """Every pre-registered Collector Appeal candidate on [0, 1].

    Returns None for every candidate when any required input is missing - never
    a silent zero. ``dual_path_depth`` may be None while the rest are present;
    only CA6 then returns None.
    """
    d_value = _as_float(d)
    a_value = _as_float(a_star)
    m_value = _as_float(m_star)
    if d_value is None or a_value is None or m_value is None:
        return {key: None for key in COLLECTOR_APPEAL_CANDIDATE_KEYS}

    d_value = _clamp(d_value)
    a_value = _clamp(a_value)
    m_value = _clamp(m_value)

    out: Dict[str, Optional[float]] = {
        "CA0_desirability_only": d_value,
        "CA1_accessible": d_value * a_value,
        "CA2_chase": d_value * m_value,
        "CA3_geometric_balance": d_value * math.sqrt(a_value * m_value),
    }
    for wa, wm in CA4_WEIGHT_GRID:
        out[f"CA4_linear_{int(wa*100)}_{int(wm*100)}"] = d_value * (wa * a_value + wm * m_value)
    for wa, wm, wi in CA5_WEIGHT_GRID:
        # gA and gM are the identity by pre-registered decision (see CA5_WEIGHT_GRID).
        out[f"CA5_interaction_{int(wa*100)}_{int(wm*100)}_{int(wi*100)}"] = d_value * _clamp(
            wa * a_value + wm * m_value + wi * a_value * m_value
        )
    utility = dual_path_utility(dual_path_depth)
    out["CA6_dual_path_utility"] = None if utility is None else d_value * utility
    for lam in CA7_LAMBDA_GRID:
        out[f"CA7_bounded_bonus_{int(lam*100)}"] = bounded_bonus_appeal(d_value, dual_path_depth, lam)
    return {key: out.get(key) for key in COLLECTOR_APPEAL_CANDIDATE_KEYS}


# ---------------------------------------------------------------------------
# RIP reweighting (research only; canonical RIP is untouched)
# ---------------------------------------------------------------------------

# The shipping financial ratio. Collector Appeal weight is carved out and the
# remainder is distributed across these in their CURRENT proportions, so no
# arbitrary redistribution among the financial pillars is introduced.
FINANCIAL_RATIO: Dict[str, float] = {"profit": 0.58, "safety": 0.20, "stability": 0.12}
COLLECTOR_APPEAL_WEIGHT_GRID: Tuple[float, ...] = (0.10, 0.15, 0.20, 0.25, 0.30)


def proportional_rip_weights(collector_appeal_weight: float) -> Dict[str, float]:
    """Rescale Profit/Safety/Stability proportionally around a Collector Appeal weight.

    Preserves the current 58:20:12 ratio exactly. At weight 0.10 this reproduces
    the shipping weights.
    """
    w = float(collector_appeal_weight)
    if not 0.0 <= w < 1.0:
        raise ValueError("collector_appeal_weight must be in [0, 1)")
    total = sum(FINANCIAL_RATIO.values())
    remaining = 1.0 - w
    weights = {k: v / total * remaining for k, v in FINANCIAL_RATIO.items()}
    weights["desirability"] = w
    return weights


def profit_funded_rip_weights(collector_appeal_weight: float) -> Dict[str, float]:
    """Sensitivity variant: take the extra Collector Appeal weight from Profit ONLY.

    Reported as a limited sensitivity; proportional rescaling is the primary
    method. Raises when Profit cannot fund the increase.
    """
    w = float(collector_appeal_weight)
    baseline_appeal = 0.10
    profit = FINANCIAL_RATIO["profit"] - (w - baseline_appeal)
    if profit < 0:
        raise ValueError("profit weight would go negative")
    return {
        "profit": profit,
        "safety": FINANCIAL_RATIO["safety"],
        "stability": FINANCIAL_RATIO["stability"],
        "desirability": w,
    }


def collector_appeal_payload(
    *,
    d: Any,
    a_star: Any,
    m_star: Any,
    dual_path_depth: Any,
) -> Dict[str, Any]:
    raw = compute_collector_appeal_candidates(
        d=d, a_star=a_star, m_star=m_star, dual_path_depth=dual_path_depth
    )
    return {
        "version": COLLECTOR_APPEAL_VERSION,
        "d": _as_float(d),
        "a_star": _as_float(a_star),
        "m_star": _as_float(m_star),
        "dual_path_depth": _as_float(dual_path_depth),
        "complement_gap": complement_gap(a_star, m_star),
        "axis_position": axis_position(a_star, m_star),
        "candidates_raw": raw,
        "degeneracy_notes": {key: degeneracy_note(key) for key in COLLECTOR_APPEAL_CANDIDATE_KEYS},
        "available": all(value is not None for value in raw.values()),
        "inputsLabel": "modeledPullScarcity (config-derived pack model), never observed pull data.",
        "excludedInputs": [
            "market_price", "set_value", "expected_value", "profit",
            "treatment_prestige", "any_market_outcome",
        ],
        "researchOnly": True,
    }
