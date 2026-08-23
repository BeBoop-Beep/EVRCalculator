"""Canonical version identifiers and configuration for the EV Representativeness
research layer.

WHY A VERSION MODULE
--------------------
Every number this layer persists is a function of (a) the authoritative
simulation it read, and (b) the methodology constants below. The run identity is
already carried by ``calculation_run_id``; this module carries the other half, so
a stored row stays interpretable without re-reading the code that produced it.

Changing ANY constant here is a new ``EV_REPRESENTATIVENESS_VERSION``. The
version string is part of every primary key in the research schema, so v2 rows
coexist with v1 rows rather than overwriting them.

WHAT THIS MODULE IS NOT
-----------------------
Not a scoring config. Nothing here feeds Financial RIP, Overall RIP, Collector
Appeal or any public metric, and nothing here may. The realization targets and
convergence tolerances below are RESEARCH GRID POINTS, deliberately chosen wide
enough to let the data say which (if any) threshold is defensible - they are not
product thresholds and no public name is attached to any of them.
"""

from __future__ import annotations

from typing import Tuple

# ---------------------------------------------------------------------------
# Method identity
# ---------------------------------------------------------------------------

EV_REPRESENTATIVENESS_VERSION = "ev_representativeness_v1"

#: Stamped onto every Tier A row. Tier A is derived from the exact persisted
#: million-pack artifact, so its provenance is the artifact's own sha256.
TIER_A_SOURCE = "authoritative_pack_outcome_artifact_v1"

#: Stamped onto every Tier B row. Tier B is a seeded, instrumented
#: re-simulation - reproducible from its seed, but NOT the published vector.
TIER_B_SOURCE = "seeded_instrumented_research_resimulation_v1"

#: The session-composition model. Deliberately the same words the sealed-product
#: layer already uses, because it is the same assumption: packs are modeled as
#: independent draws from the empirical one-pack distribution.
SESSION_MODEL_VERSION = "empirical_independent_pack_bootstrap_v1"

#: Binomial-proportion interval used for every probability estimate.
CI_METHOD = "wilson_95"
CI_Z = 1.959963984540054  # two-sided 95%


# ---------------------------------------------------------------------------
# Part 11 - finite-sample EV realization targets
# ---------------------------------------------------------------------------
# P(mean of N packs >= r * EV). 1.00 is included for research completeness only;
# the brief is explicit that exceeding EV is NOT evidence of representativeness,
# so it is never used as a horizon target.

REALIZATION_TARGETS: Tuple[float, ...] = (0.50, 0.70, 0.75, 0.80, 0.90, 1.00)

#: Targets a horizon may be reported for. 1.00 is excluded on purpose.
HORIZON_REALIZATION_TARGETS: Tuple[float, ...] = (0.70, 0.75, 0.80, 0.90)


# ---------------------------------------------------------------------------
# Part 12 - EV representativeness (two-sided convergence) tolerances
# ---------------------------------------------------------------------------
# P(|mean_N / EV - 1| <= tau).

CONVERGENCE_TOLERANCES: Tuple[float, ...] = (0.10, 0.20, 0.25)


# ---------------------------------------------------------------------------
# Parts 13/14 - required opener proportions
# ---------------------------------------------------------------------------

CONFIDENCE_LEVELS: Tuple[float, ...] = (0.50, 0.75, 0.80, 0.90, 0.95)

#: The two candidates the brief singles out. Promoted to their own columns so
#: the cohort can be ranked without unpacking JSON. Internal names only.
HEADLINE_REALIZATION_TARGET = 0.80
HEADLINE_CONVERGENCE_TOLERANCE = 0.20
HEADLINE_CONFIDENCE = 0.80


# ---------------------------------------------------------------------------
# Part 15 - pack-count research grid
# ---------------------------------------------------------------------------
# Real quantities first (1/3/6/9/11/18/36 are live product pack counts in the
# cohort), then a broader research grid. Product pack counts resolved from the
# database are UNIONED into this grid at runtime - this tuple is the research
# floor, never the authority on what a product contains.

BASE_PACK_GRID: Tuple[int, ...] = (
    1, 2, 3, 4, 5, 6, 8, 9, 10, 11, 12, 18, 24, 36, 50, 72, 100, 150, 250,
    500, 750, 1000,
)

#: Beyond BASE_PACK_GRID the search extends geometrically until a horizon is
#: found or the cap is hit. 1.5x keeps the grid dense enough that a stable
#: horizon is not reported at a wildly coarser resolution than it was found.
EXTENSION_GROWTH_FACTOR = 1.5

#: Hard ceiling on the search. A set that has not converged by 100k packs has
#: emphatically answered the research question; grinding further buys nothing.
#: Reported as horizon_status='exceeds_search_cap', never as a number.
PACK_GRID_SEARCH_CAP = 100_000


# ---------------------------------------------------------------------------
# Part 24 - adaptive precision
# ---------------------------------------------------------------------------

STAGE_COARSE = "coarse"
STAGE_REFINE = "refine"
STAGE_CONFIRM = "confirm"

#: Sessions per estimate in the coarse stage over BASE_PACK_GRID.
COARSE_SESSION_COUNT = 50_000

#: Sessions per estimate once the search extends past BASE_PACK_GRID. Lower,
#: because that stage only has to LOCATE a crossing; the crossing is never
#: reported from it.
EXTENSION_SESSION_COUNT = 20_000

#: Sessions per estimate in the refinement stage (dense grid around a candidate).
REFINE_SESSION_COUNT = 100_000

#: Sessions per estimate in the confirmation stage. Every reported horizon is a
#: confirmation-stage number, drawn from an INDEPENDENT seed stream.
CONFIRM_SESSION_COUNT = 250_000

#: Upper bound on confirmation work per set, in pack draws. A horizon deep in
#: the tens of thousands would otherwise make one set cost more than the rest of
#: the cohort combined. When the budget binds, the session count is reduced and
#: the ACTUAL count is persisted with the row, so the widened Wilson interval is
#: visible rather than implied.
CONFIRM_DRAW_BUDGET = 6_000_000_000

#: Index-block memory ceiling for the session kernel, in bytes.
SESSION_INDEX_BLOCK_BYTES = 64 * 1024 * 1024


# ---------------------------------------------------------------------------
# Horizon stability rule (Part 14 + the monotonicity warning)
# ---------------------------------------------------------------------------
# A stable horizon must hold across a band ABOVE the crossing, not just at it.
# The band is multiplicative because these curves are smooth in log N, not in N.

STABILITY_BAND_FACTOR = 2.0
STABILITY_MIN_BAND_POINTS = 3


# ---------------------------------------------------------------------------
# Part 4 - outcome tail quantiles (rank-based, see distribution.py)
# ---------------------------------------------------------------------------

OUTCOME_TAIL_QUANTILES: Tuple[float, ...] = (0.10, 0.05, 0.01)


# ---------------------------------------------------------------------------
# Part 5 - cost-normalized return-ratio buckets
# ---------------------------------------------------------------------------
# RESEARCH DEFAULTS, not locked product thresholds. The underlying percentiles
# are persisted as first-class columns precisely so no downstream reading
# depends on these edges surviving.
#
# These are NOT a replacement for
# ``simulations/value_threshold_bins.DEFAULT_VALUE_THRESHOLD_BUCKETS``, which is
# an absolute-DOLLAR contract and is left completely untouched. A dollar bucket
# cannot answer "what fraction of openers recovered half their money" across
# products whose packs cost $5.45 and $28.92.

RETURN_RATIO_BUCKETS: Tuple[Tuple[float, float | None], ...] = (
    (0.00, 0.25),
    (0.25, 0.50),
    (0.50, 0.75),
    (0.75, 1.00),
    (1.00, 1.50),
    (1.50, 2.00),
    (2.00, 5.00),
    (5.00, None),
)


# ---------------------------------------------------------------------------
# Part 10 - economically meaningful hit thresholds
# ---------------------------------------------------------------------------
# P(pack contains at least one single card worth >= m x pack cost). Rarity
# independent on purpose: it asks whether the opener reached an economically
# meaningful layer, which is a different question from which rarity printed it.

ECONOMIC_HIT_COST_MULTIPLES: Tuple[float, ...] = (0.25, 0.50, 0.75, 1.00, 2.00, 5.00)


# ---------------------------------------------------------------------------
# Part 18/19 - counterfactual scenarios
# ---------------------------------------------------------------------------

TOP_CARD_ABLATION_DEPTHS: Tuple[int, ...] = (1, 5, 10)
WINSORIZATION_QUANTILES: Tuple[float, ...] = (0.01,)
PRICE_SHOCK_FACTORS: Tuple[float, ...] = (-0.10, -0.25, -0.50)
PRICE_SHOCK_GROUP_DEPTHS: Tuple[int, ...] = (1, 5)


# ---------------------------------------------------------------------------
# Tier A <-> Tier B reconciliation
# ---------------------------------------------------------------------------
# Tier B is an INDEPENDENT sample from the same model, so its mean differs from
# Tier A's by Monte Carlo error and nothing else. That makes the tolerance a
# measurement question, not a taste question:
#
#     EV_A and EV_B are independent estimates of the same mu, each with standard
#     error sigma/sqrt(n). Their difference therefore has standard error
#     sigma * sqrt(1/n_A + 1/n_B), and
#
#         z = (EV_B - EV_A) / (sigma * sqrt(1/n_A + 1/n_B))
#
#     is a standard normal under "same model, same prices". The tolerance is a
#     z-threshold, so it AUTOMATICALLY scales with each set's own volatility
#     instead of imposing one dollar or percentage figure on a cohort whose CV
#     spans 1.9 to 11.7.
#
# 5.0 is chosen because a two-sided |z| > 5 has probability ~5.7e-7 under the
# null: at 22 sets x ~4 checked statistics per day it will essentially never fire
# by chance, so a firing means a real divergence (wrong prices, wrong config,
# instrumentation altering the sampling path) rather than bad luck. The measured
# cohort-wide |z| distribution is persisted so this threshold can be revisited
# against evidence rather than argued about.
RECONCILIATION_Z_TOLERANCE = 5.0

#: Absolute relative floor. Guards the degenerate case sigma -> 0, where the
#: z-test's denominator vanishes and any difference at all looks infinite.
RECONCILIATION_RELATIVE_FLOOR = 0.005

#: Quantiles cross-checked alongside the mean. A mean that reconciles while P50
#: or P95 does not would indicate the instrumentation changed the SHAPE of the
#: distribution, which the mean alone cannot detect.
RECONCILIATION_QUANTILES: Tuple[float, ...] = (0.50, 0.95)

RECONCILIATION_STATUS_PASS = "reconciled"
RECONCILIATION_STATUS_FAIL = "reconciliation_failed"
RECONCILIATION_STATUS_UNAVAILABLE = "tier_b_not_run"


# ---------------------------------------------------------------------------
# Tier B simulation size
# ---------------------------------------------------------------------------
#: Matches the authoritative run exactly, so the reconciliation z-test compares
#: like with like and card-level expected copies carry the same precision the
#: published mean does.
TIER_B_PACK_COUNT = 1_000_000
