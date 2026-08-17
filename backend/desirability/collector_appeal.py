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
# LEGACY. CA7's identity, retained so stored CA7 rows stay identifiable and the
# V2-vs-CA7 comparison has something honest to name. It is NO LONGER the
# canonical Collector Appeal - see COLLECTOR_APPEAL_V2_VERSION below.
COLLECTOR_APPEAL_CA7_VERSION = "collector_appeal_ca7_v1"
# Back-compat alias for existing importers that mean "the CA7 formula's version".
COLLECTOR_APPEAL_VERSION = COLLECTOR_APPEAL_CA7_VERSION
DUAL_PATH_DEPTH_VERSION = "dual_path_depth_v1"

# ---------------------------------------------------------------------------
# COLLECTOR APPEAL V2 (D / F / P, bounded headroom) — SUPERSEDED BY V3
# ---------------------------------------------------------------------------
# Retained, computable and identifiable so stored V2 rows keep their exact
# meaning and the V2-vs-V3 research comparison has an honest number to name. It
# is NO LONGER canonical - see COLLECTOR_APPEAL_V3_VERSION below.
#
# The PUBLIC PRODUCT NAME IS UNCHANGED: "Collector Appeal". There is deliberately
# no second visible card called CA8, Collector Appeal V2 or Enhanced Collector
# Appeal - a product does not get a version number in its name because its
# formula improved. The version lives here, in the code, where it belongs.
#
#     structural_opening_appeal = 0.60 * F + 0.40 * P
#     Collector Appeal          = D + 0.50 * structural_opening_appeal * (1 - D)
#
# i.e.  CA = D + 0.50 * (0.60F + 0.40P) * (1 - D)
#
# WHAT CHANGED FROM CA7, AND WHAT DID NOT
# ---------------------------------------
# CA7 was ``D + 0.50 * P * (1 - D)``: desirability, plus a bounded bonus for
# dual-path structure. The refinement replaces the single structural term P with
# a blend of two structural terms, F and P, and changes nothing else:
#
#   * D is still the foundation and still enters exactly once.
#   * The headroom gain is still 0.50 - the maximum structural bonus is
#     IDENTICAL to CA7's. This is a refinement of what "structure" means, not a
#     rescaling engineered to manufacture rank movement.
#   * (1 - D) still bounds the result at 1.0.
#   * Structure still cannot replace an undesirable roster: at maximum structure
#     only half the remaining headroom is claimable.
#   * F = P = 0 still gives CA = D exactly.
#
# WHY F BELONGS ALONGSIDE P
# -------------------------
# P asks a STRUCTURAL question about the subjects a set cares about: do they
# offer both an attainable printing and a genuine elite chase? It says nothing
# about how often a pack actually delivers one of them. A set can have excellent
# dual-path structure over subjects that are collectively very hard to hit.
#
# F asks the complementary question: how often does the modeled pack actually
# put a desirable card in your hands? The two are related but measure different
# things, and the service reports their rank correlation as a diagnostic so the
# relationship stays visible rather than assumed.

# SUPERSEDED by Collector Appeal V3 (see below). Retained, computable and
# identifiable so stored V2 rows keep their exact meaning and the V2-vs-V3
# research comparison has a real number to name.
COLLECTOR_APPEAL_V2_VERSION = "collector_appeal_v2_desirable_frequency_dual_path"
COLLECTOR_APPEAL_V2_FORMULA_VERSION = "collector_appeal_bounded_headroom_d_f_p_v1"
COLLECTOR_APPEAL_V2_FORMULA_EXPRESSION = "CA = D + 0.50 * (0.60F + 0.40P) * (1 - D)"

# Authoritative constants. Nothing in the calculation, persistence, publication,
# audit or test path is permitted to restate these literals.
COLLECTOR_APPEAL_FREQUENCY_WEIGHT = 0.60
COLLECTOR_APPEAL_DUAL_PATH_WEIGHT = 0.40
COLLECTOR_APPEAL_HEADROOM_GAIN = 0.50

COLLECTOR_APPEAL_V2_STRUCTURAL_WEIGHTS: Dict[str, float] = {
    "desirable_outcome_frequency": COLLECTOR_APPEAL_FREQUENCY_WEIGHT,
    "dual_path_depth": COLLECTOR_APPEAL_DUAL_PATH_WEIGHT,
}

# The V2 diagnostics namespace. Deliberately NOT the CA7 key: leaving a
# `collector_appeal_ca7` block carrying a different formula would make the
# stored identity a lie that nothing could detect.
COLLECTOR_APPEAL_V2_DIAGNOSTICS_KEY = "collector_appeal_v2"


# ---------------------------------------------------------------------------
# THE CANONICAL COLLECTOR APPEAL: V3, a balanced weighted sum of D, H and P
# ---------------------------------------------------------------------------
# The PUBLIC PRODUCT NAME REMAINS "Collector Appeal". As with V2, the version
# lives here, in the code, and never in the product name.
#
#     unit_score   = 0.40*D + 0.35*H + 0.25*P
#     public_score = 100 * unit_score
#
# WHY V2's SHAPE HAD TO GO
# ------------------------
# V2 was ``D + 0.50 * (0.60H + 0.40P) * (1 - D)``: bounded, construct-sound, and
# effectively a restatement of D. The completed 22-set validation measured
# Spearman(V2, D) ~ 0.991 and Spearman(V2, legacy CA7) ~ 0.997. H and P carry
# genuinely distinct information, but the ``(1 - D)`` headroom factor scales
# their entire contribution by a set's remaining headroom, which for a desirable
# roster is small - so the structural terms could barely move the ordering. A
# metric that consumes three inputs and reproduces one of them is publishing a
# claim about structure it is not actually making.
#
# V3 removes the headroom factor. Each input now carries a fixed share of the
# score, so a change in H or P moves the result by the same amount regardless of
# where D happens to sit.
#
# WHY 40 / 35 / 25
# ----------------
# A CONSTRUCT allocation, not a fitted one. D stays nominally most important
# because a roster nobody cares about cannot be rescued by pack structure; H is
# placed close behind it because how often the pack actually delivers a desirable
# card is the opening experience itself; P is materially weighted but lowest
# because dual-path structure is a quality OF the delivery rather than the
# delivery. These weights were NOT selected to produce preferred set rankings,
# to correlate with price, or to pass a rank-movement threshold - the validation
# tool reports what the cohort does under them and does not choose them.
#
# WHAT IS UNCHANGED FROM V2
# -------------------------
#   * D, H and P are the same three constructs, computed by the same modules.
#   * Desirability enters EXACTLY ONCE, as D. H's eligibility uses desirability
#     but never multiplies its magnitude in.
#   * No price, EV, pack cost, profitability or market proxy is read.
#   * A missing input makes the score unavailable, never 0 and never D.

COLLECTOR_APPEAL_V3_VERSION = "collector_appeal_v3_balanced_d40_h35_p25"
COLLECTOR_APPEAL_V3_FORMULA_VERSION = "collector_appeal_weighted_sum_d_h_p_v1"

# Authoritative constants. Nothing in the calculation, persistence, publication,
# audit or test path is permitted to restate these literals, and nothing in the
# PUBLIC payload is permitted to disclose them - see
# ``collector_appeal_v3_public_identity``.
COLLECTOR_APPEAL_V3_DESIRABILITY_WEIGHT = 0.40
COLLECTOR_APPEAL_V3_FREQUENCY_WEIGHT = 0.35
COLLECTOR_APPEAL_V3_DUAL_PATH_WEIGHT = 0.25

# Keyed by the production input names. ``desirable_outcome_frequency`` is the
# quantity the validation brief calls H; there is one implementation of it, in
# ``backend.desirability.desirable_outcome_frequency``.
COLLECTOR_APPEAL_V3_WEIGHTS: Dict[str, float] = {
    "roster_desirability": COLLECTOR_APPEAL_V3_DESIRABILITY_WEIGHT,
    "desirable_outcome_frequency": COLLECTOR_APPEAL_V3_FREQUENCY_WEIGHT,
    "dual_path_depth": COLLECTOR_APPEAL_V3_DUAL_PATH_WEIGHT,
}

COLLECTOR_APPEAL_V3_INPUT_ORDER: Tuple[str, ...] = (
    "roster_desirability",
    "desirable_outcome_frequency",
    "dual_path_depth",
)

# snake_case input key -> the camelCase label a public surface may show. The
# LABEL is publishable; the weight beside it is not.
COLLECTOR_APPEAL_V3_PUBLIC_INPUT_KEYS: Dict[str, str] = {
    "roster_desirability": "rosterDesirability",
    "desirable_outcome_frequency": "desirableOutcomeFrequency",
    "dual_path_depth": "dualPathDepth",
}

# The canonical diagnostics namespace for V3. A new key, for the same reason V2
# took one: leaving a `collector_appeal_v2` block carrying a different formula
# would make the stored identity a lie that nothing could detect.
COLLECTOR_APPEAL_V3_DIAGNOSTICS_KEY = "collector_appeal_v3"

# Reconstruction tolerance for the contribution-sum invariant.
COLLECTOR_APPEAL_V3_RECONSTRUCTION_TOLERANCE = 1e-9

# Chase Appeal (D x M) ships as its own visible metric and is NOT a RIP pillar.
# Intentionally absent from ``collector_appeal_fingerprint.collect_assumptions``:
# that hash identifies the rules behind a stored COLLECTOR APPEAL score, and
# Chase Appeal is a different metric that changes none of them. Adding it there
# would mark every stored CA7 row stale for a metric CA7 does not consume.
CHASE_APPEAL_VERSION = "chase_appeal_ca2_v1"

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


def _audit_collector_appeal_v2_weights() -> None:
    """Structural weights that do not sum to 1.0 silently rescale the bonus.

    ``0.60F + 0.40P`` is documented as a weighted average on [0, 1]; if the
    weights summed to, say, 0.9, the maximum structural bonus would quietly stop
    being the 0.50 headroom gain the formula claims. That must fail at import,
    not at publication.
    """
    total = sum(COLLECTOR_APPEAL_V2_STRUCTURAL_WEIGHTS.values())
    if abs(total - 1.0) > 1e-12:
        raise ValueError(
            "Collector Appeal structural weights must sum to exactly 1.0; got "
            f"{total!r}."
        )
    if not 0.0 <= COLLECTOR_APPEAL_HEADROOM_GAIN <= 1.0:
        raise ValueError("COLLECTOR_APPEAL_HEADROOM_GAIN must be in [0, 1].")


def _audit_collector_appeal_v3_weights() -> None:
    """Weights that do not sum to 1.0 put Collector Appeal off the 0-1 scale.

    V3 is a plain weighted sum with no bounding factor, so the weights ARE the
    scale. If they summed to 0.95 the metric would silently top out at 95 and
    every published "out of 100" statement would be false. That must fail at
    import, not at publication.
    """
    total = sum(COLLECTOR_APPEAL_V3_WEIGHTS.values())
    if abs(total - 1.0) > 1e-12:
        raise ValueError(
            f"COLLECTOR_APPEAL_V3_WEIGHTS must sum to exactly 1.0; got {total!r}."
        )
    if tuple(COLLECTOR_APPEAL_V3_WEIGHTS) != COLLECTOR_APPEAL_V3_INPUT_ORDER:
        raise ValueError("COLLECTOR_APPEAL_V3_INPUT_ORDER must cover the weights in order.")
    if set(COLLECTOR_APPEAL_V3_PUBLIC_INPUT_KEYS) != set(COLLECTOR_APPEAL_V3_WEIGHTS):
        raise ValueError("Every Collector Appeal V3 input needs exactly one public key.")
    for key, weight in COLLECTOR_APPEAL_V3_WEIGHTS.items():
        if not 0.0 < weight < 1.0:
            raise ValueError(f"Collector Appeal V3 weight for '{key}' must be in (0, 1).")
    # The construct ordering is part of the model's identity: D nominally first,
    # H close behind, P material. Reversing it would be a different metric
    # wearing the same version string.
    if not (
        COLLECTOR_APPEAL_V3_DESIRABILITY_WEIGHT
        > COLLECTOR_APPEAL_V3_FREQUENCY_WEIGHT
        > COLLECTOR_APPEAL_V3_DUAL_PATH_WEIGHT
    ):
        raise ValueError(
            "Collector Appeal V3 requires D > H > P by nominal coefficient; got "
            f"{COLLECTOR_APPEAL_V3_WEIGHTS!r}."
        )


_audit_collector_appeal_v2_weights()
_audit_collector_appeal_v3_weights()


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
#
# STATUS: LIVE AND MAINTAINED. NOT DEPRECATED. DO NOT DELETE.
# ---------------------------------------------------------------------------
# Dual-Path Depth (P) is intentionally EXCLUDED from universal Collector Appeal
# V4, and that exclusion is a scoping decision about one score - not a judgement
# that the metric is wrong, stale, or unwanted.
#
# WHY IT LEFT UNIVERSAL COLLECTOR APPEAL
# --------------------------------------
# The V4 ablation held every other assumption identical (same D, same H
# transform and anchors, same neutral point, same +4.0/-2.0 asymmetric modifier,
# same clamp) and varied only whether P entered the structural index. P changed
# 3 of 231 pairwise orderings, moved six sets by exactly one rank each, and left
# Spearman(with P, without P) = 0.9966. For a UNIVERSAL, set-level appeal score
# that is not useful discrimination beyond Desirable Outcome Frequency. See
# docs/research/collector_appeal_v4_promotion_validation.md section 2.
#
# WHY IT STAYS
# ------------
# "Adds little at the population level" and "measures nothing useful" are
# different claims, and only the first is supported. P asks a question whose
# answer plausibly depends on WHO is asking: do the desirable subjects in this
# set offer both an attainable printing and a genuine elite chase? That is a
# strong candidate feature for future PERSONAL FIT / collector-goal models,
# where rarity structure can matter differently depending on the user's stated
# objective. Illustrative cases:
#
#   * master-set collectors, for whom accessible + elite printing paths may
#     change the progression and completion experience;
#   * collectors chasing one specific Pokemon, where SUBJECT-LEVEL dual-path
#     depth (``subject_dual_path`` below already computes exactly this) could
#     measure whether that Pokemon has both an attainable and a premium chase
#     printing;
#   * other personalized collecting profiles where a stated preference makes
#     this structure relevant.
#
# WHAT THIS NOTE DOES NOT AUTHORIZE
# ---------------------------------
# It is NOT permission to add P back to universal Collector Appeal, and it is
# NOT permission to build Personal Fit. Any future personalization work must
# validate P's appropriate use and weighting independently, on its own evidence.
# The bucket separation this preserves is documented in
# docs/research/collector_appeal_v2_validation/three_bucket_architecture.md:
# General Collector Appeal is a set-level property; Personal Fit is a set-user
# interaction; collapsing them is the failure mode that document exists to
# prevent.
#
# The mathematics below is UNCHANGED and must stay that way while it carries
# ``DUAL_PATH_DEPTH_VERSION``: stored P values and the V4 ablation evidence both
# depend on it meaning exactly what it has always meant.
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


def compute_collector_appeal_ca7(d: Any, p: Any, *, lam: float = CA7_PRODUCTION_LAMBDA) -> Optional[float]:
    """LEGACY CA7: ``D + 0.50 * P * (1 - D)``.

    No longer canonical. Retained for the V2-vs-CA7 comparison audit, for
    regression tests, and so any already-stored CA7 row can be reproduced
    exactly. Callers that want the shipping Collector Appeal must call
    :func:`compute_collector_appeal_v2`.
    """
    return bounded_bonus_appeal(d, p, lam)


# The historical name, kept so existing importers do not break. It still means
# CA7 - the legacy formula - and is NOT the canonical Collector Appeal.
compute_collector_appeal = compute_collector_appeal_ca7


def structural_opening_appeal(f: Any, p: Any) -> Optional[float]:
    """``0.60 * F + 0.40 * P`` on [0, 1]: the structural half of Collector Appeal.

    Separated from the final blend so the decomposition the service publishes is
    the SAME number the score used, rather than a re-derivation that could drift.

    Returns None - never 0.0 - when either input is missing. F and P are both
    required: a structural term computed from one of the two would silently mean
    something different from the term the formula documents.
    """
    f_value = _as_float(f)
    p_value = _as_float(p)
    if f_value is None or p_value is None:
        return None
    return _clamp(
        COLLECTOR_APPEAL_FREQUENCY_WEIGHT * _clamp(f_value)
        + COLLECTOR_APPEAL_DUAL_PATH_WEIGHT * _clamp(p_value)
    )


def compute_collector_appeal_v2(d: Any, f: Any, p: Any) -> Optional[float]:
    """SUPERSEDED Collector Appeal V2: ``D + 0.50 * (0.60F + 0.40P) * (1 - D)``.

    No longer canonical - see :func:`compute_collector_appeal_v3`. Retained so a
    stored V2 row can be reproduced exactly and the V2-vs-V3 comparison has a
    real number. It is never used as a fallback when V3 is unavailable.

    The 22-set validation is why it moved: the ``(1 - D)`` headroom factor scales
    the whole structural term by a set's remaining headroom, which compressed F
    and P so severely that V2 tracked D at Spearman ~0.991 and legacy CA7 at
    ~0.997 - three inputs, one input's ordering.

    Properties, all exact and all asserted in the unit tests:
      * ``F = 0, P = 0``      -> ``CA = D``      (no structure costs nothing)
      * ``D = 1``             -> ``CA = 1``      (a perfect roster is already at the ceiling)
      * ``dCA/dD = 1 - 0.5*S >= 0.5 > 0``        (strictly increasing in D)
      * ``dCA/dF = 0.5*0.6*(1-D) >= 0``          (non-decreasing in F)
      * ``dCA/dP = 0.5*0.4*(1-D) >= 0``          (non-decreasing in P)
      * ``CA <= 1`` for all admissible inputs    (bounded by the headroom factor)
      * at ``S = 1``, ``CA = D + 0.5*(1-D)``     (only half the headroom is claimable)

    The last property is the design constraint that keeps the metric honest:
    perfect opening structure over a roster nobody wants cannot out-score a
    beloved roster with no structure at all.

    Returns None - never 0.0 - when any of D, F or P is missing. A structural
    input defaulted to zero would be a claim that the set has no desirable
    outcomes, which absent data does not support.
    """
    d_value = _as_float(d)
    if d_value is None:
        return None
    structural = structural_opening_appeal(f, p)
    if structural is None:
        return None
    d_value = _clamp(d_value)
    return _clamp(d_value + COLLECTOR_APPEAL_HEADROOM_GAIN * structural * (1.0 - d_value))


def collector_appeal_v2_decomposition(d: Any, f: Any, p: Any) -> Dict[str, Any]:
    """The published breakdown, derived from the SAME call the score used.

    Reported so a reader can reconstruct the score by hand. ``headroomBonus`` is
    exactly ``score - D``, so the two lines always add up.
    """
    score = compute_collector_appeal_v2(d, f, p)
    structural = structural_opening_appeal(f, p)
    d_value = _as_float(d)
    return {
        "inputs": {
            "rosterDesirability": d_value,
            "desirableOutcomeFrequency": _as_float(f),
            "dualPathDepth": _as_float(p),
        },
        "structuralOpeningAppeal": round(structural, 6) if structural is not None else None,
        "headroomBonus": (
            round(score - d_value, 6) if score is not None and d_value is not None else None
        ),
    }


# ---------------------------------------------------------------------------
# Collector Appeal V3 — THE canonical calculation
# ---------------------------------------------------------------------------

def _unit_input(value: Any) -> Optional[float]:
    """Coerce one V3 input onto [0, 1], or None.

    Rejects rather than clamps a value outside a small tolerance of [0, 1]. D, H
    and P are all defined on the unit interval by their own modules, so a 1.4 or
    a -0.2 arriving here is not an extreme set - it is a units error or a
    corrupted payload, and clamping it would silently publish a score built from
    a number nobody intended. A hair outside the interval IS clamped: that is
    floating-point residue from a union or a renormalization, not a units error.
    """
    parsed = _as_float(value)
    if parsed is None:
        return None
    if parsed < -1e-9 or parsed > 1.0 + 1e-9:
        return None
    return _clamp(parsed)


def compute_collector_appeal_v3(d: Any, h: Any, p: Any) -> Optional[float]:
    """THE canonical Collector Appeal, on [0, 1]: ``0.40D + 0.35H + 0.25P``.

    ONE entry point, so every surface computes the same number.

    ``h`` is the Desirable Outcome Frequency - the quantity production names F
    and the validation brief names H. They are the same number:
    ``P(a modeled pack contains at least one card tied to an eligible desirable
    Pokemon subject)``. It is NOT a financial win rate; a desirable hit may still
    be a financial loss.

    Properties, all exact and all asserted in the unit tests:
      * ``0 <= CA <= 1`` for every admissible input (the weights sum to 1)
      * ``dCA/dD = 0.40 > 0``, ``dCA/dH = 0.35 > 0``, ``dCA/dP = 0.25 > 0``
        (strictly increasing in each input, independently of the other two)
      * ``D = H = P = v`` -> ``CA = v`` (the weights are a partition of unity)
      * the three contributions sum EXACTLY to the score

    Returns None - never 0.0, never 0.5, never D, never legacy CA7 - when any of
    D, H or P is missing or malformed. A structural input defaulted to zero would
    be a positive claim that the set has no desirable outcomes, which absent data
    does not support; defaulting to D would republish desirability under a name
    that promises three constructs.
    """
    d_value = _unit_input(d)
    h_value = _unit_input(h)
    p_value = _unit_input(p)
    if d_value is None or h_value is None or p_value is None:
        return None
    return _clamp(
        COLLECTOR_APPEAL_V3_DESIRABILITY_WEIGHT * d_value
        + COLLECTOR_APPEAL_V3_FREQUENCY_WEIGHT * h_value
        + COLLECTOR_APPEAL_V3_DUAL_PATH_WEIGHT * p_value
    )


def collector_appeal_v3_missing_inputs(d: Any, h: Any, p: Any) -> List[str]:
    """Which of D/H/P are unavailable, in canonical input order.

    Named individually rather than reported as one "inputs missing" flag: "no
    desirability coverage", "no pull model" and "no dual-path data" call for
    three different fixes, and collapsing them sends an operator to the wrong one.
    """
    values = {
        "roster_desirability": _unit_input(d),
        "desirable_outcome_frequency": _unit_input(h),
        "dual_path_depth": _unit_input(p),
    }
    return [key for key in COLLECTOR_APPEAL_V3_INPUT_ORDER if values[key] is None]


def collector_appeal_v3_decomposition(d: Any, h: Any, p: Any) -> Dict[str, Any]:
    """INTERNAL breakdown of the V3 score: inputs, contributions, and the check.

    Derived from the SAME arithmetic the score uses, so the decomposition can
    never drift from the number it explains.

    NOT FOR THE PUBLIC PAYLOAD. A contribution divided by its input recovers the
    weight exactly, so publishing contributions would publish the weights this
    model deliberately keeps internal. The public projection carries the score,
    the status, the factor VALUES and the version - see
    :func:`collector_appeal_v3_public_identity`.

    ``contributionsReconcile`` is the invariant that the three contributions sum
    to the unit score. It is computed, not assumed: a weight table edited without
    updating the audit would otherwise produce a decomposition that quietly does
    not add up.
    """
    score = compute_collector_appeal_v3(d, h, p)
    missing = collector_appeal_v3_missing_inputs(d, h, p)
    d_value = _unit_input(d)
    h_value = _unit_input(h)
    p_value = _unit_input(p)

    contributions: Dict[str, Optional[float]] = {
        "dContribution": (
            None if d_value is None else COLLECTOR_APPEAL_V3_DESIRABILITY_WEIGHT * d_value
        ),
        "hContribution": (
            None if h_value is None else COLLECTOR_APPEAL_V3_FREQUENCY_WEIGHT * h_value
        ),
        "pContribution": (
            None if p_value is None else COLLECTOR_APPEAL_V3_DUAL_PATH_WEIGHT * p_value
        ),
    }
    reconciles: Optional[bool] = None
    if score is not None and all(value is not None for value in contributions.values()):
        total = sum(float(value) for value in contributions.values())
        reconciles = abs(total - score) <= COLLECTOR_APPEAL_V3_RECONSTRUCTION_TOLERANCE

    return {
        "version": COLLECTOR_APPEAL_V3_VERSION,
        "formulaVersion": COLLECTOR_APPEAL_V3_FORMULA_VERSION,
        "unitScore": score,
        "publicScore": None if score is None else score * 100.0,
        "inputs": {
            "d": d_value,
            "h": h_value,
            "p": p_value,
        },
        **contributions,
        "contributionsReconcile": reconciles,
        "missingInputs": missing,
    }


def collector_appeal_v3_public_identity() -> Dict[str, Any]:
    """What a PUBLIC surface may say about the V3 model.

    Version identifiers and high-level factor labels only. Deliberately absent:
    the weights, an executable formula string, the internal thresholds, and any
    validation statistic or candidate-grid metadata. A published weight vector is
    a published formula - the arithmetic is a one-liner - and this model's
    weighting is internal by decision, not by oversight.
    """
    return {
        "version": COLLECTOR_APPEAL_V3_VERSION,
        "formulaVersion": COLLECTOR_APPEAL_V3_FORMULA_VERSION,
        "factors": [
            {
                "key": COLLECTOR_APPEAL_V3_PUBLIC_INPUT_KEYS[key],
                "label": label,
                "interpretation": interpretation,
            }
            for key, label, interpretation in (
                (
                    "roster_desirability",
                    "Roster Desirability",
                    "How desirable this set's Pokemon are, before pull difficulty.",
                ),
                (
                    "desirable_outcome_frequency",
                    "Desirable Outcome Frequency",
                    "How often a modeled pack delivers a card tied to a desirable Pokemon.",
                ),
                (
                    "dual_path_depth",
                    "Dual-Path Depth",
                    "Whether desirable Pokemon offer both an attainable printing and an elite chase.",
                ),
            )
        ],
        "excludedInputs": [
            "market_price",
            "expected_value",
            "pack_cost",
            "profitability",
            "financial_score",
            "market_rank_proxy",
            "scarcity_price_proxy",
        ],
        "subjectScope": {
            "modeled": ["pokemon"],
            "notYetModeled": ["trainer", "artist"],
        },
        "weightsDisclosed": False,
    }


# ---------------------------------------------------------------------------
# THE CANONICAL COLLECTOR APPEAL: V4, desirability with an asymmetric H modifier
# ---------------------------------------------------------------------------
# The PUBLIC PRODUCT NAME REMAINS "Collector Appeal". As with V2 and V3, the
# version lives here, in the code, and never in the product name.
#
#     sH = clamp01((log2(H) - log2(1/16)) / (log2(1/4) - log2(1/16)))
#        = clamp01((log2(H) + 4) / 2)
#     z  = 2*sH - 1
#     m  = +4.0*z   if z >= 0          (points, on the 0-100 scale)
#     m  = +2.0*z   if z <  0
#     CA = clamp(100*D + m, 0, 100)
#
# THE CONSTRUCT
# -------------
#     D = underlying collector desirability   -> the dominant baseline
#     H = desirable outcome accessibility     -> a modest tiebreaker
#     "D ranks the neighbourhood. H settles many close calls."
#
# WHY V3's SHAPE HAD TO GO
# ------------------------
# V3 was ``0.40D + 0.35H + 0.25P``: three peer addends. A nominal coefficient is
# not influence - what orders a weighted sum is the DISPERSION of each weighted
# contribution - and on the 22-set cohort D's contribution range (0.178) barely
# exceeded H's and P's combined (0.162), and was carried almost entirely by a
# single low outlier. Measured: Spearman(V3, D) = 0.589 against
# Spearman(V3, H) = 0.832, with the median set landing three places off the
# desirability order and 41% moving five or more. A metric named for how
# desirable a set's content is was ordering by hit frequency.
#
# V4 restores D as the baseline and gives structure a fixed, small budget.
#
# WHY THE MODIFIER IS CENTRED, NOT FLOORED
# ----------------------------------------
# CA7 and V2 floored the structural term at zero and bounded it by ``(1 - D)``.
# For the sets anyone argues about ``(1 - D)`` is 0.05-0.13, so the whole term
# was scaled down by an order of magnitude exactly where it was meant to break
# ties - which is why V2 tracked D at rho 0.991 while claiming three inputs. A
# floored bonus can only add, so the only way to make it matter is to make it
# big, and a big one-sided bonus is what lets a mediocre roster climb. Centring
# at NEUTRAL structure lets good accessibility add and poor accessibility
# subtract while the total span stays small. That is what "tiebreaker" means
# arithmetically, and it is why neutral H returns exactly D.
#
# WHY THE ASYMMETRY (+4.0 UP, ONLY -2.0 DOWN)
# -------------------------------------------
# Strong accessibility genuinely delivers something: a pack that regularly hands
# you a Pokemon you care about is a better box to open. Difficulty costs only
# half as much, because a hard chase can itself be the appeal - punishing it
# symmetrically would encode "easier is better", which is a taste, not a
# measurement. Phantasmal Flames is the case in point: brutal chase odds, yet it
# earns the cohort's second-largest positive modifier, because H measures how
# often a pack delivers A desirable card, not how easy the top card is.
#
# WHY H IS ANCHORED ON LOG2 WAIT TIME
# -----------------------------------
# Frequency is perceived multiplicatively: the felt difference between "every 4
# packs" and "every 8" is the same as between "every 8" and "every 16". The
# anchors are FIXED and stated in collector language, never cohort percentiles,
# so adding or removing a set can never move another set's score.
#
# WHY P IS GONE
# -------------
# See the retention note above ``subject_dual_path``. In short: the ablation held
# every other assumption identical and varied only whether P entered, and P
# changed 3 of 231 pairwise orderings while leaving Spearman(with P, without P)
# = 0.9966. The calculation is RETAINED and maintained as a diagnostic and as a
# candidate Personal Fit feature; it is simply not an input to the universal
# score.
#
# WHAT IS UNCHANGED FROM V3
# -------------------------
#   * D and H are the same two constructs, computed by the same modules.
#   * Desirability enters EXACTLY ONCE, as D. H's eligibility uses desirability
#     but never multiplies its magnitude in.
#   * No price, EV, pack cost, profitability or market proxy is read.
#   * A missing input makes the score unavailable, never 0 and never D.
#   * D is passed through UNCHANGED - not rescaled, not min-maxed, not ranked.

COLLECTOR_APPEAL_V4_VERSION = "collector_appeal_v4_h_only_d_baseline_up4_down2"
COLLECTOR_APPEAL_V4_FORMULA_VERSION = "collector_appeal_h_only_centred_asymmetric_modifier_v1"
# V5 deliberately reuses V4's arithmetic.  Its identity moves because D now
# comes from contextual Universal Set Desirability V4 rather than roster V3.
COLLECTOR_APPEAL_V5_VERSION = "collector_appeal_v5_contextual_roster_h_only_d_baseline_up4_down2"
COLLECTOR_APPEAL_V5_FORMULA_VERSION = COLLECTOR_APPEAL_V4_FORMULA_VERSION

# Authoritative constants. Nothing in the calculation, persistence, publication,
# audit or test path is permitted to restate these literals, and nothing in the
# PUBLIC payload is permitted to disclose the ceiling or floor - see
# ``collector_appeal_v4_public_identity``.
#
# H transform anchors, expressed as "one desirable card per N packs".
COLLECTOR_APPEAL_V4_H_ANCHOR_ZERO_ONE_IN_N = 16.0      # sH = 0.0
COLLECTOR_APPEAL_V4_H_ANCHOR_NEUTRAL_ONE_IN_N = 8.0    # sH = 0.5  (NEUTRAL)
COLLECTOR_APPEAL_V4_H_ANCHOR_ONE_ONE_IN_N = 4.0        # sH = 1.0

# The modifier, in PUBLIC POINTS on the 0-100 scale.
COLLECTOR_APPEAL_V4_MODIFIER_CEILING_POINTS = 4.0
COLLECTOR_APPEAL_V4_DOWNSIDE_DAMPING = 0.50
COLLECTOR_APPEAL_V4_MODIFIER_FLOOR_POINTS = (
    -COLLECTOR_APPEAL_V4_MODIFIER_CEILING_POINTS * COLLECTOR_APPEAL_V4_DOWNSIDE_DAMPING
)  # = -2.0

# The single behavioural promise: the widest D gap accessibility can overturn is
# the FULL SPAN of the modifier - best-structured challenger (+4.0) against
# worst-structured incumbent (-2.0). Derived, not measured, and verified by
# exhaustive search in the tests.
COLLECTOR_APPEAL_V4_MAX_PAIRWISE_STRUCTURAL_ADVANTAGE_POINTS = (
    COLLECTOR_APPEAL_V4_MODIFIER_CEILING_POINTS - COLLECTOR_APPEAL_V4_MODIFIER_FLOOR_POINTS
)  # = 6.0

COLLECTOR_APPEAL_V4_INPUT_ORDER: Tuple[str, ...] = (
    "roster_desirability",
    "desirable_outcome_frequency",
)

# snake_case input key -> the camelCase label a public surface may show.
COLLECTOR_APPEAL_V4_PUBLIC_INPUT_KEYS: Dict[str, str] = {
    "roster_desirability": "rosterDesirability",
    "desirable_outcome_frequency": "desirableOutcomeFrequency",
}

# The canonical diagnostics namespace for V4. A new key, for the same reason V2
# and V3 each took one: leaving a `collector_appeal_v3` block carrying a
# different formula would make the stored identity a lie that nothing could
# detect.
COLLECTOR_APPEAL_V4_DIAGNOSTICS_KEY = "collector_appeal_v4"

# The exact formula, as one unambiguous string. BOTH branches are written out,
# because a single-branch summary would misstate the model: this must never be
# described as ``D + 4*(2*sH - 1)``, which overstates the downside by a factor of
# two and misstates the inversion boundary by 2 points.
COLLECTOR_APPEAL_V4_FORMULA_EXPRESSION = (
    "sH = clamp01((log2(H) - log2(1/16)) / (log2(1/4) - log2(1/16))); "
    "z = 2*sH - 1; "
    "m = 4.0*z if z >= 0 else 2.0*z; "
    "CA = clamp(100*D + m, 0, 100)"
)

# THE MONOTONICITY CONTRACT, STATED RATHER THAN IMPLIED.
#
#   NON-DECREASING in D everywhere on [0, 1];
#   STRICTLY INCREASING in D wherever ``100*D + m`` lies strictly inside
#   (0, 100).
#
# Ties can arise ONLY where the clamp binds, which needs D above 0.96 or below
# 0.02. No set in the eligible cohort is in either region (observed range
# 0.5107 to 0.9548), so on real data the score is strictly increasing in D
# throughout - but that is a fact about the DATA, not about the FORMULA, and the
# two are recorded separately on purpose. A test asserts the data fact and fails
# loudly if a future set enters the region, rather than letting it tie silently.
#
# The clamp is retained rather than engineered away. Tapering the bonus into the
# last points of headroom would reintroduce exactly the ``(1 - D)`` shrinkage
# that made V2 a restatement of D, and precisely for the elite sets the
# tiebreaker exists to separate; letting the score exceed 100 would break the
# published "out of 100" claim. Clamping, with the region named and monitored,
# is the least dishonest of the three.
COLLECTOR_APPEAL_V4_MONOTONICITY_CONTRACT: Dict[str, Any] = {
    "in_d": "non_decreasing_everywhere_strictly_increasing_off_the_clamp",
    "in_h": "non_decreasing_everywhere",
    "in_p": "not_an_input",
    "upper_saturation_begins_above_d": (
        (100.0 - COLLECTOR_APPEAL_V4_MODIFIER_CEILING_POINTS) / 100.0
    ),
    "lower_saturation_begins_below_d": -COLLECTOR_APPEAL_V4_MODIFIER_FLOOR_POINTS / 100.0,
    "ties_possible_only_inside_saturation": True,
}

COLLECTOR_APPEAL_V4_RECONSTRUCTION_TOLERANCE = 1e-9


def _audit_collector_appeal_v4_constants() -> None:
    """A V4 whose constants contradict its documented contract must not import.

    The asymmetry is the property most likely to be broken by a well-meaning
    edit - "surely the floor should be -4" - and an asymmetry silently turned
    symmetric would change every below-neutral score while leaving the version
    string, the formula string and the tests' names intact.
    """
    if COLLECTOR_APPEAL_V4_MODIFIER_CEILING_POINTS <= 0:
        raise ValueError("Collector Appeal V4 modifier ceiling must be positive.")
    if not 0.0 <= COLLECTOR_APPEAL_V4_DOWNSIDE_DAMPING <= 1.0:
        raise ValueError("Collector Appeal V4 downside damping must be in [0, 1].")
    expected_floor = (
        -COLLECTOR_APPEAL_V4_MODIFIER_CEILING_POINTS * COLLECTOR_APPEAL_V4_DOWNSIDE_DAMPING
    )
    if abs(COLLECTOR_APPEAL_V4_MODIFIER_FLOOR_POINTS - expected_floor) > 1e-12:
        raise ValueError(
            "Collector Appeal V4 floor must equal -ceiling * damping; got "
            f"{COLLECTOR_APPEAL_V4_MODIFIER_FLOOR_POINTS!r}, expected {expected_floor!r}."
        )
    if COLLECTOR_APPEAL_V4_MODIFIER_FLOOR_POINTS >= 0:
        raise ValueError("Collector Appeal V4 floor must be negative.")
    span = (
        COLLECTOR_APPEAL_V4_MODIFIER_CEILING_POINTS - COLLECTOR_APPEAL_V4_MODIFIER_FLOOR_POINTS
    )
    if abs(COLLECTOR_APPEAL_V4_MAX_PAIRWISE_STRUCTURAL_ADVANTAGE_POINTS - span) > 1e-12:
        raise ValueError("Collector Appeal V4 pairwise span must equal ceiling - floor.")
    # The anchors must be strictly ordered as wait times, or the log2 map inverts
    # and a rarer desirable outcome would score as MORE accessible.
    if not (
        COLLECTOR_APPEAL_V4_H_ANCHOR_ZERO_ONE_IN_N
        > COLLECTOR_APPEAL_V4_H_ANCHOR_NEUTRAL_ONE_IN_N
        > COLLECTOR_APPEAL_V4_H_ANCHOR_ONE_ONE_IN_N
        > 0
    ):
        raise ValueError("Collector Appeal V4 H anchors must be strictly decreasing wait times.")
    if set(COLLECTOR_APPEAL_V4_PUBLIC_INPUT_KEYS) != set(COLLECTOR_APPEAL_V4_INPUT_ORDER):
        raise ValueError("Every Collector Appeal V4 input needs exactly one public key.")
    if "dual_path_depth" in COLLECTOR_APPEAL_V4_INPUT_ORDER:
        raise ValueError("Collector Appeal V4 must not consume dual_path_depth.")


_audit_collector_appeal_v4_constants()


def collector_appeal_v4_frequency_index(h: Any) -> Optional[float]:
    """Map H onto [0, 1] against the FIXED wait-time anchors. 0.5 == neutral.

    Plain English: 0.0 means a desirable card turns up about once every 16 packs
    or worse, 0.5 means about once every 8, 1.0 means about once every 4 or
    better. Nothing about the cohort enters, so a set scores the same whoever
    else happens to be measured alongside it.

    Returns None - never 0.0 - for a missing, non-positive or out-of-range H.
    ``H = 0`` exactly would mean "no modeled pack can produce a desirable card",
    which is a data condition rather than a weak set, and ``log2(0)`` is
    undefined; scoring it as the worst possible accessibility would be a claim
    the absence does not support.
    """
    value = _unit_input(h)
    if value is None or value <= 0.0:
        return None
    weak = math.log2(1.0 / COLLECTOR_APPEAL_V4_H_ANCHOR_ZERO_ONE_IN_N)
    strong = math.log2(1.0 / COLLECTOR_APPEAL_V4_H_ANCHOR_ONE_ONE_IN_N)
    return _clamp((math.log2(value) - weak) / (strong - weak))


def collector_appeal_v4_modifier_points(h: Any) -> Optional[float]:
    """The signed accessibility adjustment in PUBLIC POINTS, centred at neutral.

        z = 2*sH - 1
        m = ceiling * z             for z >= 0
        m = ceiling * z * damping   for z <  0

    Bounded to ``[-2.0, +4.0]``. Returns None - never 0.0 - when H is
    unavailable: zero is the value for NEUTRAL accessibility, and reporting
    "neutral" for "unknown" would be a measurement the data does not support.
    """
    index = collector_appeal_v4_frequency_index(h)
    if index is None:
        return None
    centred = 2.0 * index - 1.0
    damping = 1.0 if centred >= 0.0 else COLLECTOR_APPEAL_V4_DOWNSIDE_DAMPING
    return COLLECTOR_APPEAL_V4_MODIFIER_CEILING_POINTS * centred * damping


def compute_collector_appeal_v4(d: Any, h: Any) -> Optional[float]:
    """THE canonical Collector Appeal, on [0, 1].

    ONE entry point, so every surface computes the same number. Returns the UNIT
    score, exactly as :func:`compute_collector_appeal_v3` did, so a caller that
    multiplies by 100 to publish keeps working unchanged.

    Takes NO ``p`` argument. A signature that accepted and ignored dual-path
    depth would let a caller pass it and believe it had been used.

    ``h`` is the Desirable Outcome Frequency:
    ``P(a modeled pack contains at least one card tied to an eligible desirable
    Pokemon subject)``. It is NOT a financial win rate; a desirable hit may still
    be a financial loss.

    Properties, all exact and all asserted in the unit tests:
      * ``0 <= CA <= 1`` for every admissible input
      * neutral H (one desirable card per 8 packs) -> ``CA = D`` EXACTLY
      * ``dCA/dD = 1`` off the clamp; non-decreasing in D everywhere
      * non-decreasing in H everywhere
      * the widest D gap H can overturn is 6.00 public points, at any D

    Returns None - never 0.0, never 0.5, never D, never a previous version's
    score - when either D or H is missing or malformed.
    """
    d_value = _unit_input(d)
    if d_value is None:
        return None
    modifier = collector_appeal_v4_modifier_points(h)
    if modifier is None:
        return None
    return _clamp(d_value + modifier / 100.0)


def collector_appeal_v4_missing_inputs(d: Any, h: Any) -> List[str]:
    """Which of D/H are unavailable, in canonical input order.

    Named individually rather than reported as one "inputs missing" flag: "no
    desirability coverage" and "no pull model" call for different fixes, and
    collapsing them sends an operator to the wrong one.
    """
    values = {
        "roster_desirability": _unit_input(d),
        "desirable_outcome_frequency": collector_appeal_v4_frequency_index(h),
    }
    return [key for key in COLLECTOR_APPEAL_V4_INPUT_ORDER if values[key] is None]


def collector_appeal_v4_decomposition(d: Any, h: Any) -> Dict[str, Any]:
    """INTERNAL breakdown of the V4 score: inputs, the modifier, and the check.

    Derived from the SAME arithmetic the score uses, so the decomposition can
    never drift from the number it explains.

    NOT FOR THE PUBLIC PAYLOAD. ``frequencyIndex`` and ``modifierPoints`` between
    them disclose the ceiling and the damping exactly - two points of the curve
    determine the line - and V4's budget is internal by decision. The public
    projection carries the score, the status, the factor VALUES and the version;
    see :func:`collector_appeal_v4_public_identity`.

    ``reconstructsScore`` is computed, not assumed: a constant edited without
    updating the audit would otherwise produce a decomposition that quietly does
    not add up.
    """
    score = compute_collector_appeal_v4(d, h)
    d_value = _unit_input(d)
    index = collector_appeal_v4_frequency_index(h)
    modifier = collector_appeal_v4_modifier_points(h)

    reconstructs: Optional[bool] = None
    if score is not None and d_value is not None and modifier is not None:
        expected = _clamp(d_value + modifier / 100.0)
        reconstructs = abs(expected - score) <= COLLECTOR_APPEAL_V4_RECONSTRUCTION_TOLERANCE

    return {
        "version": COLLECTOR_APPEAL_V4_VERSION,
        "formulaVersion": COLLECTOR_APPEAL_V4_FORMULA_VERSION,
        "unitScore": score,
        "publicScore": None if score is None else score * 100.0,
        "inputs": {"d": d_value, "h": _as_float(h)},
        "frequencyIndex": index,
        "modifierPoints": modifier,
        "modifierDirection": (
            None if modifier is None else ("positive" if modifier >= 0 else "negative")
        ),
        "baselinePublicScore": None if d_value is None else d_value * 100.0,
        "clamped": (
            None
            if score is None or d_value is None or modifier is None
            else not (0.0 <= d_value + modifier / 100.0 <= 1.0)
        ),
        "reconstructsScore": reconstructs,
        "missingInputs": collector_appeal_v4_missing_inputs(d, h),
    }


def collector_appeal_v4_public_identity() -> Dict[str, Any]:
    """What a PUBLIC surface may say about the V4 model.

    Version identifiers and high-level factor labels only. Deliberately absent:
    the modifier ceiling and floor, the damping, the H anchors, an executable
    formula string, and any validation statistic. Publishing the ceiling and the
    anchors together is publishing the formula - the arithmetic is a one-liner -
    and this model's budget is internal by decision, not by oversight.

    ``dualPathDepth`` is named in ``excludedInputs`` rather than omitted. A
    surface that previously showed three factors needs to be able to say WHY it
    now shows two, and silence would read as an outage.
    """
    return {
        "version": COLLECTOR_APPEAL_V4_VERSION,
        "formulaVersion": COLLECTOR_APPEAL_V4_FORMULA_VERSION,
        "factors": [
            {
                "key": COLLECTOR_APPEAL_V4_PUBLIC_INPUT_KEYS[key],
                "label": label,
                "interpretation": interpretation,
            }
            for key, label, interpretation in (
                (
                    "roster_desirability",
                    "Roster Desirability",
                    "How desirable this set's Pokemon are, before pull difficulty.",
                ),
                (
                    "desirable_outcome_frequency",
                    "Desirable Outcome Frequency",
                    "How often a modeled pack delivers a card tied to a desirable Pokemon.",
                ),
            )
        ],
        "excludedInputs": [
            "dual_path_depth",
            "market_price",
            "expected_value",
            "pack_cost",
            "profitability",
            "financial_score",
            "market_rank_proxy",
            "scarcity_price_proxy",
        ],
        "dualPathDepthStatus": "retained_as_diagnostic_not_a_collector_appeal_input",
        "subjectScope": {
            "modeled": ["pokemon"],
            "notYetModeled": ["trainer", "artist"],
        },
        "weightsDisclosed": False,
    }


def compute_chase_appeal(d: Any, m_star: Any) -> Optional[float]:
    """THE production Chase Appeal: ``D * M`` on [0, 1]. Algebraically CA2.

    A SEPARATE, VISIBLE METRIC - NOT A RIP PILLAR
    ---------------------------------------------
    Chase Appeal answers a different question from Collector Appeal: "how do this
    set's desirability and its elite scarcity combine into a chase structure?"
    The market study found it survives the set-size correction on its own, so it
    ships under its own name (see
    docs/research/collector_appeal_market_prediction_results.md section 2).

    It is deliberately NOT added to RIP, and the canonical Collector Appeal
    formula does not contain it. Overall RIP is exactly
    ``0.90 * Financial RIP V3 + 0.10 * Collector Appeal``, and D already enters
    through Collector Appeal; adding D x M as a separate term would apply
    desirability to Overall RIP a second time. M's financial consequence - the
    upper tail of pack value - is already measured, on the money side, by
    Financial RIP V3's Realistic Upside and Jackpot Upside. A test pins that
    Chase Appeal is absent from both the Collector Appeal formula and the
    Overall RIP components.

    WHY THIS EXISTS RATHER THAN READING THE GRID
    --------------------------------------------
    ``compute_collector_appeal_candidates`` also produces D*M under the key
    ``CA2_chase``, but that grid is research: its whole purpose is to COMPARE
    candidates, and serving a number off it would be shipping a candidate as a
    product - the exact confusion this module's header forbids. So the shipped
    metric gets one named entry point with its own version. A test asserts this
    function and the grid's CA2 never disagree, so the two cannot drift.

    Returns None - never 0.0 - when either input is missing.
    """
    d_value = _as_float(d)
    m_value = _as_float(m_star)
    if d_value is None or m_value is None:
        return None
    return _clamp(_clamp(d_value) * _clamp(m_value))


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
