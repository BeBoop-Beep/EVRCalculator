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

from typing import Dict, Iterable, Mapping, Optional, Tuple

# Financial RIP V3's own configuration is the authoritative source for its
# version identifiers, weights and anchors; it is imported rather than restated
# so there is exactly ONE definition of each. The dependency runs
# desirability -> calculations (never the reverse).
from backend.calculations.evr.financial_rip_v3_config import (
    FINANCIAL_RIP_V3_VERSION as FINANCIAL_RIP_V3_VERSION,
    FINANCIAL_RIP_V3_WEIGHTS as FINANCIAL_RIP_V3_WEIGHTS,
    OVERALL_RIP_V5_VERSION as OVERALL_RIP_V5_VERSION_FROM_CONFIG,
    OVERALL_RIP_V5_WEIGHTS as OVERALL_RIP_V5_WEIGHTS,
    PUBLIC_RIP_CONTRACT_V5_VERSION as PUBLIC_RIP_CONTRACT_V5_VERSION,
)
# Financial RIP V4 is a separate, additionally-available model version - see the
# module docstring of `financial_rip_v4_config`. It is imported for the same
# reason as V3: so its identity and weights have exactly one definition.
from backend.calculations.evr.financial_rip_v4_config import (
    FINANCIAL_RIP_V4_VERSION as FINANCIAL_RIP_V4_VERSION,
    FINANCIAL_RIP_V4_WEIGHTS as FINANCIAL_RIP_V4_WEIGHTS,
    FINANCIAL_RIP_V4_WEIGHTS as _FINANCIAL_RIP_V4_WEIGHTS,
)
# NOTE: Collector Appeal's version constants are deliberately NOT imported at
# module scope. `collector_appeal` -> `factorized_opening_appeal` -> this module
# is a real import cycle, and this module is the leaf. They are read through the
# lazy accessors below instead, so `collector_appeal` remains the single source
# of those strings without either module having to duplicate them.


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
# The CANONICAL Overall RIP after the V3 cutover. Same 90/10 relationship as v4;
# the financial input changes from Financial RIP V2 (60/25/15 Profit/Safety/
# Stability) to the six-component Financial RIP V3 outcome-profile score. v4 is
# retained, computed and published as a clearly-labelled LEGACY block.
OVERALL_RIP_V5_VERSION = OVERALL_RIP_V5_VERSION_FROM_CONFIG
UNIVERSAL_SET_DESIRABILITY_VERSION = "universal_set_desirability_v3"
UNIVERSAL_SET_DESIRABILITY_V4_VERSION = "universal_set_desirability_v4_contextual_chase"
CONTEXTUAL_CHASE_PRIORITY_VERSION = "contextual_chase_priority_subject_ev_share_v3_1pct_all_positive_ev_no_fallback_max10pct_unresolved"
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


# ---------------------------------------------------------------------------
# Canonical version resolution — the V3/V5 cutover switch
# ---------------------------------------------------------------------------
# ONE authoritative selection. Every public builder, ranking path and presenter
# reads these two constants to decide which model is canonical; promotion is a
# change HERE, not a conditional scattered through the publication layer.
#
# Deliberately NOT an environment variable. Two workers publishing one
# leaderboard under different env values would emit two incompatible score
# versions into a single ranked cohort, and nothing downstream would notice.
#
# After the cutover:
#   canonical Financial RIP    = Financial RIP V3 (six-component outcome profile)
#   canonical Collector Appeal = Collector Appeal V3 (0.40D + 0.35H + 0.25P)
#   canonical Overall RIP      = 0.90 * Financial RIP V3 + 0.10 * Collector Appeal V3
#
# Financial RIP V2 and Overall RIP v4 remain COMPUTED and PUBLISHED, under
# explicitly legacy labels, for historical comparison, the V2-vs-V3 audit,
# regression tests and rollback diagnostics. They no longer feed the canonical
# score or the canonical ranking.

# ---------------------------------------------------------------------------
# Overall RIP V6: 80% Financial RIP V3 + 20% Collector Appeal V2 — SUPERSEDED
# ---------------------------------------------------------------------------
# HISTORICAL / RESEARCH ONLY. Retained so a stored V6 row keeps its exact meaning
# and the V6-vs-V7 comparison has an honest number to name. It is no longer on
# any canonical path - see OVERALL_RIP_V7_VERSION below.
#
# V6 moved two things off V5: the split (90/10 -> 80/20) and the appeal input
# (legacy CA7 -> the D/F/P Collector Appeal V2).
#
# WHY THE 80/20 SPLIT WAS REVERSED
# --------------------------------
# The 22-set validation measured 80/20 against Financial-only at Spearman ~0.869,
# mean absolute rank movement ~1.82, Top-5 overlap 60% and a maximum movement of
# 12 ranks - through the owner-defined guardrails (Spearman >= 0.95, Top-5 >= 0.80,
# mean movement <= 1.5) rather than near them. A 20% weight on a non-financial
# construct was reordering the leaderboard's financial claim.

OVERALL_RIP_V6_VERSION = "overall_rip_v6_80_financial_v3_20_collector_appeal_v2"

OVERALL_RIP_V6_WEIGHTS: Dict[str, float] = {
    "financial_rip": 0.80,
    "collector_appeal": 0.20,
}

# The effective per-input weights after expanding Financial RIP V3's six
# components across its 0.80 share. Held here so presentation surfaces read one
# authoritative source rather than each re-deriving 0.80 * 0.25 = 0.20.
#
#   True Win Frequency        0.80 * 0.25 = 0.20
#   Typical Retention         0.80 * 0.20 = 0.16
#   Loss Resilience           0.80 * 0.15 = 0.12
#   Realistic Upside          0.80 * 0.25 = 0.20
#   Jackpot Upside            0.80 * 0.10 = 0.08
#   Base Economic Efficiency  0.80 * 0.05 = 0.04
#   Collector Appeal                        0.20
#                                     total 1.00
OVERALL_RIP_V6_EFFECTIVE_WEIGHTS: Dict[str, float] = {
    **{
        component: OVERALL_RIP_V6_WEIGHTS["financial_rip"] * weight
        for component, weight in FINANCIAL_RIP_V3_WEIGHTS.items()
    },
    "collector_appeal": OVERALL_RIP_V6_WEIGHTS["collector_appeal"],
}


# ---------------------------------------------------------------------------
# Overall RIP V7: 90% Financial RIP V3 + 10% Collector Appeal V3 — SUPERSEDED
# ---------------------------------------------------------------------------
# HISTORICAL / COMPARISON ONLY, and UNCHANGED in every constant below. It is the
# V3-BACKED composition and must keep meaning exactly that, so any row ever
# written under `overall_rip_v7_...` stays reproducible. Superseded by V8, which
# keeps the 90/10 split and swaps the appeal input to Collector Appeal V4.
#
#     Overall RIP = 0.90 * Financial RIP V3 + 0.10 * Collector Appeal V3
#
# The financial input is UNCHANGED from V5 and V6: the same absolute
# fixed-anchor six-component Financial RIP V3, with the same weights. Two things
# move relative to V6:
#
#   1. the split, back from 80/20 to 90/10, and
#   2. the appeal input, from Collector Appeal V2 (bounded headroom) to
#      Collector Appeal V3 (the balanced 0.40D + 0.35H + 0.25P sum).
#
# V7 IS A NEW IDENTIFIER, NOT A REPOINTED V5
# ------------------------------------------
# V5's version string reads `..._90_financial_v3_10_ca7` and V6's reads
# `..._80_financial_v3_20_collector_appeal_v2`; both are accurate about
# themselves. V7 shares V5's 90/10 SPLIT but not V5's appeal input, so reusing
# V5 would make a stored row mean two different things depending on when it was
# written, with nothing in the row to say which. Every prior identifier keeps its
# exact prior meaning.
#
# WHY 90/10 AND NOT 86/14
# -----------------------
# 14% already falls below the owner-defined 0.95 Spearman guardrail against
# Financial-only under the existing formula. 13% remains a research sensitivity
# candidate and is registered as such in
# OVERALL_RIP_COLLECTOR_APPEAL_SENSITIVITY_WEIGHTS below - it is NOT production
# configuration, and nothing on a canonical path reads that tuple.

OVERALL_RIP_V7_VERSION = "overall_rip_v7_90_financial_v3_10_collector_appeal_v3"

OVERALL_RIP_V7_WEIGHTS: Dict[str, float] = {
    "financial_rip": 0.90,
    "collector_appeal": 0.10,
}

# The effective per-input weights after expanding Financial RIP V3's six
# components across its 0.90 share. Held here so presentation surfaces read one
# authoritative source rather than each re-deriving 0.90 * 0.25 = 0.225.
#
#   True Win Frequency        0.90 * 0.25 = 0.225
#   Typical Retention         0.90 * 0.20 = 0.180
#   Loss Resilience           0.90 * 0.15 = 0.135
#   Realistic Upside          0.90 * 0.25 = 0.225
#   Jackpot Upside            0.90 * 0.10 = 0.090
#   Base Economic Efficiency  0.90 * 0.05 = 0.045
#   Collector Appeal                        0.100
#                                     total 1.000
OVERALL_RIP_V7_EFFECTIVE_WEIGHTS: Dict[str, float] = {
    **{
        component: OVERALL_RIP_V7_WEIGHTS["financial_rip"] * weight
        for component, weight in FINANCIAL_RIP_V3_WEIGHTS.items()
    },
    "collector_appeal": OVERALL_RIP_V7_WEIGHTS["collector_appeal"],
}


# ---------------------------------------------------------------------------
# Overall RIP V8: 90% Financial RIP V3 + 10% Collector Appeal V4 — CANONICAL
# ---------------------------------------------------------------------------
#     Overall RIP = 0.90 * Financial RIP V3 + 0.10 * Collector Appeal V4
#
# EXACTLY ONE THING MOVES FROM V7: the appeal INPUT, from Collector Appeal V3
# (the balanced 0.40D + 0.35H + 0.25P sum) to Collector Appeal V4 (D plus a
# centred, asymmetric H modifier, with P removed). The split is UNCHANGED at
# 90/10 and the financial input is the same absolute fixed-anchor six-component
# Financial RIP V3 with the same weights.
#
# WHY A NEW IDENTIFIER FOR AN UNCHANGED SPLIT
# -------------------------------------------
# Because the version string names the INPUTS, not just the ratio. V7 reads
# `..._90_financial_v3_10_collector_appeal_v3` - a statement that is true of
# every row ever written under it. Repointing V7 at a V4-backed composition
# would make that string false for new rows while leaving old rows unmarked, so
# a stored `overall_rip_v7...` row would mean two different things depending on
# when it was written, with nothing in the row to say which. That is the exact
# failure V7 itself was created to avoid when it declined to repoint V5.
#
# The number can be identical and the identity still has to move: two rows that
# happen to agree numerically are not the same measurement if they consumed
# different constructs.
#
# THE WEIGHT IS DELIBERATELY NOT CHANGED HERE
# -------------------------------------------
# The V4 validation recommended 7.5% as the largest appeal weight that clears
# the Spearman and 5-plus-rank-share guardrails on every compatible historical
# date, but that recommendation is PROVISIONAL: its worst-state Spearman margin
# is +0.000311 across only about six distinct Financial RIP configurations. The
# evidence gate is to re-measure once roughly twenty further distinct financial
# states have accumulated. Moving the weight now, merely because the appeal
# input was already being changed, would be spending a decision the evidence has
# not yet paid for - and would also make any post-cutover leaderboard movement
# unattributable between "the appeal metric changed" and "its weight changed".
#
# 7.5% remains a separately tracked follow-up. It is registered as a research
# sensitivity value below, NOT as production configuration.

OVERALL_RIP_V8_VERSION = "overall_rip_v8_90_financial_v3_10_collector_appeal_v4"

OVERALL_RIP_V8_WEIGHTS: Dict[str, float] = {
    "financial_rip": 0.90,
    "collector_appeal": 0.10,
}

# The effective per-input weights after expanding Financial RIP V3's six
# components across its 0.90 share. Numerically identical to V7's by
# construction - the split did not move - and held separately anyway so a future
# change to one cannot silently be read through the other.
OVERALL_RIP_V8_EFFECTIVE_WEIGHTS: Dict[str, float] = {
    **{
        component: OVERALL_RIP_V8_WEIGHTS["financial_rip"] * weight
        for component, weight in FINANCIAL_RIP_V3_WEIGHTS.items()
    },
    "collector_appeal": OVERALL_RIP_V8_WEIGHTS["collector_appeal"],
}

# V9 changes only the declared Collector Appeal input (V4 -> V5).  The
# financial model and 90/10 composition are intentionally unchanged.
OVERALL_RIP_V9_VERSION = "overall_rip_v9_90_financial_v3_10_collector_appeal_v5"
OVERALL_RIP_V9_WEIGHTS: Dict[str, float] = dict(OVERALL_RIP_V8_WEIGHTS)
OVERALL_RIP_V9_EFFECTIVE_WEIGHTS: Dict[str, float] = dict(OVERALL_RIP_V8_EFFECTIVE_WEIGHTS)

# ---------------------------------------------------------------------------
# Overall RIP V10 - 90% Financial RIP V4 + 10% Collector Appeal V5
# ---------------------------------------------------------------------------
# V10 changes only the declared FINANCIAL input (V3 -> V4). The appeal input
# stays Collector Appeal V5 and the composition stays 90/10, exactly as the
# Financial RIP V4 decision record specifies.
#
# WHY A NEW VERSION FOR AN UNCHANGED SPLIT
# ----------------------------------------
# The same reason V8 and V9 were new versions: the identifier names its INPUTS,
# not just the ratio. The V9 string asserts a Financial-V3-backed composition,
# and that assertion is true of every row ever written under it. Repointing V9
# at Financial RIP V4 would make the string false for new rows while leaving old
# rows unmarked, so one version would mean two different things depending on
# write date. Overall RIP V9 therefore remains fully computable and its stored
# rows remain reproducible.

OVERALL_RIP_V10_VERSION = "overall_rip_v10_90_financial_v4_10_collector_appeal_v5"

OVERALL_RIP_V10_WEIGHTS: Dict[str, float] = {
    "financial_rip": 0.90,
    "collector_appeal": 0.10,
}

# The effective per-input weights after expanding the six Financial RIP V4
# components across the 0.90 share. The V4 component weights are numerically
# identical to V3 (25/20/15/25/10/5 is unchanged by the V4 decision), so these
# numbers match V9 - but they are derived from the V4 table, not the V3 one, so
# the derivation stays truthful about which model it expands.
OVERALL_RIP_V10_EFFECTIVE_WEIGHTS: Dict[str, float] = {
    **{
        component: OVERALL_RIP_V10_WEIGHTS["financial_rip"] * weight
        for component, weight in _FINANCIAL_RIP_V4_WEIGHTS.items()
    },
    "collector_appeal": OVERALL_RIP_V10_WEIGHTS["collector_appeal"],
}

# ---------------------------------------------------------------------------
# Overall RIP sensitivity weights (RESEARCH ONLY - never production)
# ---------------------------------------------------------------------------
# The Collector Appeal shares the read-only validation tool reports against the
# Financial-only baseline. 0.10 is the canonical production weight and appears
# here only so the sensitivity table contains its own reference column.
#
# NOTHING ON A CANONICAL PATH READS THIS TUPLE. It exists so a sensitivity study
# has a pre-registered grid instead of an ad-hoc one, and so 0.13 has a declared
# home as a research candidate rather than drifting toward production by sitting
# in the same dict as the shipping weight.
# 0.075 is the V4 validation's PROVISIONAL recommendation and lives here, in the
# research grid, precisely so it cannot drift into production by sitting beside
# the shipping weight. Adopting it is gated on re-measuring the historical
# replay once roughly twenty further distinct Financial RIP states exist; the
# margin on the worst state observed so far is +0.000311.
OVERALL_RIP_COLLECTOR_APPEAL_SENSITIVITY_WEIGHTS: tuple = (
    0.00, 0.05, 0.075, 0.10, 0.13, 0.14, 0.15, 0.20,
)

# The predeclared production guardrails, versus a Financial-only ranking. Held
# as config so the validation tool cannot quietly report against a weaker bar
# than the one that was agreed. Raising any of these to make a configuration
# pass is a change to THIS constant, in review, not a change inside a script.
OVERALL_RIP_PRODUCTION_GUARDRAILS: Dict[str, float] = {
    "min_spearman_vs_financial_only": 0.95,
    "min_top5_overlap": 0.80,
    "max_mean_absolute_rank_movement": 1.5,
    "max_share_moving_5_plus_ranks": 0.10,
}


# THE CUTOVER SWITCHES
# ---------------------------------------------------
# Financial RIP V4 and Overall RIP V10 are now the canonical selection.
#
# Promotion is exactly these two constants, and flipping them was a PUBLICATION
# event, not a code-implementation one: every published snapshot, leaderboard
# row and product row must be rebuilt under V4/V10, since several production
# readers (product_family_rankings_service among them) admit a row only when
# its stored version EQUALS the canonical one. V3/V9 remain registered and
# computable so historical rows stay readable - they are simply no longer the
# constants returned here.
#
# `CANONICAL_FINANCIAL_RIP_VERSION` is defined HERE, not in
# `financial_rip_v3_config`, because that module cannot import Financial RIP
# V4's identity without creating a circular import (V4's config module imports
# FROM the V3 one). This module already imports both identities at module
# scope with no cycle, and already owns the identical kind of switch for
# `CANONICAL_OVERALL_RIP_VERSION` below - a second definition of a cutover
# switch is a second cutover. There is one.
CANONICAL_FINANCIAL_RIP_VERSION = FINANCIAL_RIP_V4_VERSION
CANONICAL_OVERALL_RIP_VERSION = OVERALL_RIP_V10_VERSION
CANONICAL_OVERALL_RIP_WEIGHTS: Dict[str, float] = dict(OVERALL_RIP_V10_WEIGHTS)

# The registry of every model version this build can compute, canonical or not.
# Publication contracts, audit scripts and the historical readers resolve a
# stored row by looking its declared version up HERE, so a legacy row is always
# identifiable and is never silently reinterpreted as the canonical model.
KNOWN_FINANCIAL_RIP_VERSIONS: Tuple[str, ...] = (
    FINANCIAL_RIP_V2_LEGACY_VERSION,
    FINANCIAL_RIP_V2_VERSION,
    FINANCIAL_RIP_V3_VERSION,
    FINANCIAL_RIP_V4_VERSION,
)

KNOWN_OVERALL_RIP_VERSIONS: Tuple[str, ...] = (
    OVERALL_RIP_V3_VERSION,
    OVERALL_RIP_V4_VERSION,
    OVERALL_RIP_V5_VERSION,
    OVERALL_RIP_V6_VERSION,
    OVERALL_RIP_V7_VERSION,
    OVERALL_RIP_V8_VERSION,
    OVERALL_RIP_V9_VERSION,
    OVERALL_RIP_V10_VERSION,
)
LEGACY_FINANCIAL_RIP_VERSION = FINANCIAL_RIP_V2_VERSION
LEGACY_OVERALL_RIP_VERSION = OVERALL_RIP_V4_VERSION
LEGACY_OVERALL_RIP_V5_VERSION = OVERALL_RIP_V5_VERSION
LEGACY_OVERALL_RIP_V6_VERSION = OVERALL_RIP_V6_VERSION
LEGACY_OVERALL_RIP_V7_VERSION = OVERALL_RIP_V7_VERSION


def canonical_collector_appeal_version() -> str:
    """The canonical Collector Appeal score version (D + asymmetric H modifier).

    Lazily imported to break the `collector_appeal` -> `factorized_opening_appeal`
    -> `scoring_config` cycle. The string is defined once, in `collector_appeal`.
    """
    from backend.desirability.collector_appeal import COLLECTOR_APPEAL_V5_VERSION

    return COLLECTOR_APPEAL_V5_VERSION


def canonical_collector_appeal_formula_version() -> str:
    """The canonical Collector Appeal FORMULA version.

    Distinct from the score version on purpose: the score version names the
    model, the formula version names its arithmetic shape. A future change that
    keeps the shape but moves an input would move one and not the other.
    """
    from backend.desirability.collector_appeal import COLLECTOR_APPEAL_V5_FORMULA_VERSION

    return COLLECTOR_APPEAL_V5_FORMULA_VERSION


def legacy_collector_appeal_v3_version() -> str:
    """Collector Appeal V3's version. Superseded by V4; comparison and rollback only."""
    from backend.desirability.collector_appeal import COLLECTOR_APPEAL_V3_VERSION

    return COLLECTOR_APPEAL_V3_VERSION


def legacy_collector_appeal_v2_version() -> str:
    """Collector Appeal V2's version. Superseded; comparison and rollback only."""
    from backend.desirability.collector_appeal import COLLECTOR_APPEAL_V2_VERSION

    return COLLECTOR_APPEAL_V2_VERSION


def legacy_collector_appeal_version() -> str:
    """Legacy CA7's version. Superseded; retained for comparison and rollback."""
    from backend.desirability.collector_appeal import COLLECTOR_APPEAL_CA7_VERSION

    return COLLECTOR_APPEAL_CA7_VERSION


def canonical_public_rip_contract_version() -> str:
    """The canonical public RIP contract version.

    Lazily imported: `public_rip_contract_v8` imports this module, so a
    module-scope import would be a cycle. The string is defined once, in the
    contract module that implements it.
    """
    from backend.desirability.public_rip_contract_v10 import (
        PUBLIC_RIP_CONTRACT_V10_VERSION,
    )

    return PUBLIC_RIP_CONTRACT_V10_VERSION


def canonical_overall_rip_is_v9() -> bool:
    return CANONICAL_OVERALL_RIP_VERSION == OVERALL_RIP_V9_VERSION


def canonical_overall_rip_is_v10() -> bool:
    """True when Overall RIP V10 (90% Financial V4 + 10% Collector Appeal V5) is canonical."""
    return CANONICAL_OVERALL_RIP_VERSION == OVERALL_RIP_V10_VERSION


def canonical_financial_rip_is_v4() -> bool:
    """True when Financial RIP V4 is the canonical financial score."""
    return CANONICAL_FINANCIAL_RIP_VERSION == FINANCIAL_RIP_V4_VERSION


def is_known_financial_rip_version(version: object) -> bool:
    """True for any financial model version this build can identify."""
    return version in KNOWN_FINANCIAL_RIP_VERSIONS


def is_known_overall_rip_version(version: object) -> bool:
    """True for any Overall model version this build can identify."""
    return version in KNOWN_OVERALL_RIP_VERSIONS


def canonical_financial_rip_is_v3() -> bool:
    """True when Financial RIP V3 is the canonical financial score."""
    return CANONICAL_FINANCIAL_RIP_VERSION == FINANCIAL_RIP_V3_VERSION


def canonical_overall_rip_is_v7() -> bool:
    """True when Overall RIP V7 (90/10 over Collector Appeal V3) is canonical.

    RETAINED AND NOW FALSE. V8 is canonical. The predicate is kept rather than
    deleted so any caller still asking the V7 question gets a truthful ``False``
    instead of an ImportError that a `try/except` might swallow into a default.
    """
    return CANONICAL_OVERALL_RIP_VERSION == OVERALL_RIP_V7_VERSION


def canonical_overall_rip_is_v8() -> bool:
    """True when Overall RIP V8 (90/10 over Collector Appeal V4) is canonical."""
    return CANONICAL_OVERALL_RIP_VERSION == OVERALL_RIP_V8_VERSION


def canonical_scoring_selection() -> Dict[str, object]:
    """The published description of which models are canonical right now."""
    return {
        "canonicalFinancialRipVersion": CANONICAL_FINANCIAL_RIP_VERSION,
        "canonicalOverallRipVersion": CANONICAL_OVERALL_RIP_VERSION,
        "canonicalCollectorAppealVersion": canonical_collector_appeal_version(),
        "canonicalCollectorAppealFormulaVersion": (
            canonical_collector_appeal_formula_version()
        ),
        "canonicalPublicRipContractVersion": canonical_public_rip_contract_version(),
        "legacyFinancialRipVersion": LEGACY_FINANCIAL_RIP_VERSION,
        "legacyOverallRipVersion": LEGACY_OVERALL_RIP_VERSION,
        "legacyOverallRipV5Version": LEGACY_OVERALL_RIP_V5_VERSION,
        "legacyOverallRipV6Version": LEGACY_OVERALL_RIP_V6_VERSION,
        "legacyOverallRipV7Version": LEGACY_OVERALL_RIP_V7_VERSION,
        "legacyCollectorAppealV3Version": legacy_collector_appeal_v3_version(),
        "legacyCollectorAppealV2Version": legacy_collector_appeal_v2_version(),
        "legacyCollectorAppealVersion": legacy_collector_appeal_version(),
        "overallRipWeights": dict(OVERALL_RIP_V9_WEIGHTS),
        "overallRipEffectiveWeights": dict(OVERALL_RIP_V9_EFFECTIVE_WEIGHTS),
        # Implemented and computable, but NOT canonical. Disclosed so a reader of
        # this payload can see that a newer model exists and has not been
        # promoted, rather than inferring from its absence that it does not exist.
        "availableFinancialRipVersions": list(KNOWN_FINANCIAL_RIP_VERSIONS),
        "availableOverallRipVersions": list(KNOWN_OVERALL_RIP_VERSIONS),
        "implementedNotCanonicalFinancialRipVersion": FINANCIAL_RIP_V4_VERSION,
        "implementedNotCanonicalOverallRipVersion": OVERALL_RIP_V10_VERSION,
        "note": (
            "Overall RIP V9 is 90% Financial RIP V3 + 10% Collector Appeal V5. "
            "Financial RIP V2, Overall RIP v4/V5/V6/V7/V8, Collector Appeal V4/V3, "
            "Collector Appeal V2 and legacy CA7 remain identifiable under "
            "explicitly legacy labels and are never selected by fallback. "
            "Financial RIP V4 and Overall RIP V10 are implemented and computable "
            "but are deliberately not yet canonical; promotion is a separate "
            "change to CANONICAL_FINANCIAL_RIP_VERSION and "
            "CANONICAL_OVERALL_RIP_VERSION together with a snapshot rebuild."
        ),
        "dualPathDepthStatus": (
            "retained_as_diagnostic_not_a_collector_appeal_input"
        ),
    }


def _audit_overall_rip_weights() -> None:
    """Weights that do not sum to 1.0 put Overall RIP off the 0-100 scale."""
    for name, table in (
        ("OVERALL_RIP_V6_WEIGHTS", OVERALL_RIP_V6_WEIGHTS),
        ("OVERALL_RIP_V6_EFFECTIVE_WEIGHTS", OVERALL_RIP_V6_EFFECTIVE_WEIGHTS),
        ("OVERALL_RIP_V7_WEIGHTS", OVERALL_RIP_V7_WEIGHTS),
        ("OVERALL_RIP_V7_EFFECTIVE_WEIGHTS", OVERALL_RIP_V7_EFFECTIVE_WEIGHTS),
        ("OVERALL_RIP_V8_WEIGHTS", OVERALL_RIP_V8_WEIGHTS),
        ("OVERALL_RIP_V8_EFFECTIVE_WEIGHTS", OVERALL_RIP_V8_EFFECTIVE_WEIGHTS),
        ("OVERALL_RIP_V9_WEIGHTS", OVERALL_RIP_V9_WEIGHTS),
        ("OVERALL_RIP_V9_EFFECTIVE_WEIGHTS", OVERALL_RIP_V9_EFFECTIVE_WEIGHTS),
        ("OVERALL_RIP_V10_WEIGHTS", OVERALL_RIP_V10_WEIGHTS),
        ("OVERALL_RIP_V10_EFFECTIVE_WEIGHTS", OVERALL_RIP_V10_EFFECTIVE_WEIGHTS),
    ):
        total = sum(table.values())
        if abs(total - 1.0) > 1e-12:
            raise ValueError(f"{name} must sum to 1.0; got {total!r}.")
    # The canonical selection must be internally consistent: a CANONICAL_* switch
    # pointing at V7 while the weights table still reads 80/20 would be two
    # cutovers disagreeing, and every caller would get whichever it imported.
    if CANONICAL_OVERALL_RIP_VERSION == OVERALL_RIP_V7_VERSION:
        if CANONICAL_OVERALL_RIP_WEIGHTS != OVERALL_RIP_V7_WEIGHTS:
            raise ValueError(
                "CANONICAL_OVERALL_RIP_WEIGHTS must match OVERALL_RIP_V7_WEIGHTS "
                "while V7 is the canonical Overall RIP."
            )
    if CANONICAL_OVERALL_RIP_VERSION == OVERALL_RIP_V10_VERSION:
        if CANONICAL_OVERALL_RIP_WEIGHTS != OVERALL_RIP_V10_WEIGHTS:
            raise ValueError(
                "CANONICAL_OVERALL_RIP_WEIGHTS must match OVERALL_RIP_V10_WEIGHTS "
                "while V10 is the canonical Overall RIP."
            )
    # The V4 decision record fixes V10 at 90/10 over Financial V4 and Collector
    # Appeal V5. A drift in either share is an import-time failure.
    if OVERALL_RIP_V10_WEIGHTS != {"financial_rip": 0.90, "collector_appeal": 0.10}:
        raise ValueError(
            "OVERALL_RIP_V10_WEIGHTS must be 90% Financial RIP V4 + 10% Collector "
            "Appeal V5, as fixed by the Financial RIP V4 decision record."
        )
    # Two versions must never share an identifier string, or one stored row would
    # be indistinguishable from another model.
    for name, versions in (
        ("KNOWN_FINANCIAL_RIP_VERSIONS", KNOWN_FINANCIAL_RIP_VERSIONS),
        ("KNOWN_OVERALL_RIP_VERSIONS", KNOWN_OVERALL_RIP_VERSIONS),
    ):
        if len(set(versions)) != len(versions):
            raise ValueError(f"{name} contains a duplicated version identifier.")
    if CANONICAL_OVERALL_RIP_VERSION not in KNOWN_OVERALL_RIP_VERSIONS:
        raise ValueError(
            "CANONICAL_OVERALL_RIP_VERSION must be a registered Overall version."
        )
    if CANONICAL_FINANCIAL_RIP_VERSION not in KNOWN_FINANCIAL_RIP_VERSIONS:
        raise ValueError(
            "CANONICAL_FINANCIAL_RIP_VERSION must be a registered financial version."
        )
    if OVERALL_RIP_COLLECTOR_APPEAL_SENSITIVITY_WEIGHTS[0] != 0.0:
        raise ValueError(
            "The sensitivity grid must start at 0.00 so every comparison has an "
            "explicit Financial-only reference column rather than an implied one."
        )
    canonical_weight = OVERALL_RIP_V7_WEIGHTS["collector_appeal"]
    if canonical_weight not in OVERALL_RIP_COLLECTOR_APPEAL_SENSITIVITY_WEIGHTS:
        raise ValueError(
            "The canonical Collector Appeal weight must appear in the sensitivity "
            "grid, or the study cannot report the shipping configuration."
        )


_audit_overall_rip_weights()

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
