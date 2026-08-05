"""Uncertainty scenarios for the Collector Appeal validation. RESEARCH ONLY.

WHY THIS EXISTS
---------------
A deterministic score difference is not a finding. Two sets 0.4 points apart on
Overall RIP are reported as ranks 7 and 8, and that ordering is presented to a
user as knowledge - but if a 10% error in modeled pull rates or a 5% move in
card prices flips them in half of all draws, the ordering was never knowledge.
This module produces the draws that let the report say which orderings survive
plausible input error and which are an artifact of point estimates.

DETERMINISM
-----------
Every routine takes an explicit seed or ``random.Random``. Nothing reads the
global RNG. Identical seeds must reproduce identical draws, because an
uncertainty interval that cannot be reproduced is not evidence.

WHAT IS DELIBERATELY NOT IMPLEMENTED
------------------------------------
**Tail-mean reconstruction from stored percentiles.** Financial RIP V3's
Realistic Upside and Jackpot Upside need conditional MEANS over exact empirical
rank buckets. A percentile is a threshold, and no arithmetic over P50/P95/P99
recovers the mean of the mass above one. :func:`financial_draws_from_outcomes`
therefore requires the genuine outcome vector and REFUSES to work from stored
summary statistics - see :data:`PERCENTILE_RECONSTRUCTION_REFUSAL`. Approximating
here would publish a number that looks like a measurement and is not, and it
would do so inside the very analysis meant to quantify how much we can trust the
measurements.

SHOCKS ARE GROUPED, NOT INDEPENDENT
-----------------------------------
Independent per-card noise is the wrong error model and it is optimistic in a
specific way: averaging many independent shocks cancels them, so a set with 40
eligible cards would look far more stable than a set with 4 purely because of
card count. Real errors are shared - the pull model assigns ONE probability per
(set, rarity), so an error in that assignment moves every card of that rarity
together. Card prices move together within a market source and update cohort.
Both are shocked by GROUP here.
"""

from __future__ import annotations

import math
import random
from typing import Any, Callable, Dict, List, Mapping, Optional, Sequence, Tuple

from backend.desirability.collector_appeal import compute_dual_path_depth
from backend.desirability.desirable_outcome_frequency import (
    compute_desirable_outcome_frequency,
)

UNCERTAINTY_VERSION = "collector_appeal_validation_uncertainty_v1"

PERCENTILE_RECONSTRUCTION_REFUSAL = (
    "Financial RIP V3 uncertainty requires the original per-pack outcome vector. "
    "Conditional tail means (the 95-99 band mean, the top-1% mean) cannot be "
    "reconstructed from stored P50/P95/P99 values: a percentile is a threshold, "
    "and no arithmetic over thresholds recovers the mean of the mass above one. "
    "Sets without a retained outcome vector are reported as unavailable for "
    "financial uncertainty rather than approximated."
)

# Pre-registered scenario magnitudes. Fixed before results were examined.
PULL_RATE_SHOCK_SCENARIOS: Tuple[float, ...] = (0.10, 0.20, 0.30)
CARD_PRICE_CV_SCENARIOS: Tuple[float, ...] = (0.05, 0.10, 0.20)
PACK_COST_SHOCK_SCENARIOS: Tuple[float, ...] = (0.05, 0.10)
MISSING_CARD_RANDOM_SHARES: Tuple[float, ...] = (0.05, 0.10)

MISSING_CARD_TARGETED_MODES: Tuple[str, ...] = (
    "highest_demand",
    "highest_probability",
    "rarest",
)

DEFAULT_COMBINED_DRAWS = 500


def _finite(value: Any) -> Optional[float]:
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return None
    return parsed if math.isfinite(parsed) else None


def _lognormal_multiplier(rng: random.Random, cv: float) -> float:
    """A positive multiplicative shock with approximately the requested CV.

    Lognormal, not normal: a probability or a price shocked by a normal draw can
    go negative, and clamping a negative draw at zero silently turns a symmetric
    error model into a biased one. Sigma is derived exactly from the requested
    coefficient of variation, and the median is set to 1.0 so the shock does not
    drift the cohort's central tendency while claiming to represent error.
    """
    if cv <= 0:
        return 1.0
    sigma = math.sqrt(math.log(1.0 + cv * cv))
    # mu = -sigma^2/2 makes E[multiplier] = 1; using median 1 instead would bias
    # the mean upward by exp(sigma^2/2), inflating every shocked quantity.
    mu = -0.5 * sigma * sigma
    return math.exp(rng.gauss(mu, sigma))


# ---------------------------------------------------------------------------
# D. Pull-rate uncertainty
# ---------------------------------------------------------------------------

def _group_key(card: Mapping[str, Any]) -> str:
    """The unit a pull-rate error actually moves.

    ``build_subject_index`` assigns probability and slot from ONE lookup keyed by
    (set, rarity), so every card of a rarity shares a single modeled number. The
    coherent error unit is therefore (slot_group, rarity), not the card.
    """
    return f"{card.get('slot_group') or '__unknown__'}::{card.get('rarity') or '__unknown__'}"


def shock_pull_rates(
    subjects: Sequence[Mapping[str, Any]],
    *,
    rng: random.Random,
    magnitude: float,
) -> List[Dict[str, Any]]:
    """Apply one coherent multiplicative shock per (slot, rarity) group.

    Preserves, in this order:
      * strictly positive probabilities (a lognormal multiplier cannot be <= 0),
      * per-card probability <= 1,
      * SLOT TOTALS <= 1 across the eligible cards of a slot - enforced by
        proportionally rescaling a slot whose shocked total exceeds 1, which
        keeps the within-slot mutual exclusivity the union formula depends on.
        Clamping cards individually would not: three cards at 0.5 each are
        individually legal and jointly impossible in one exclusive slot.

    ``magnitude`` is a coefficient of variation, so 0.30 means "roughly +/-30%
    typical error", not a hard bound.
    """
    multipliers: Dict[str, float] = {}
    shocked: List[Dict[str, Any]] = []

    for subject in subjects:
        cards: List[Dict[str, Any]] = []
        for card in subject.get("cards") or []:
            probability = _finite(card.get("pull_probability"))
            if probability is None or probability <= 0:
                cards.append(dict(card))
                continue
            key = _group_key(card)
            if key not in multipliers:
                multipliers[key] = _lognormal_multiplier(rng, magnitude)
            new_card = dict(card)
            new_card["pull_probability"] = min(1.0, probability * multipliers[key])
            cards.append(new_card)
        new_subject = dict(subject)
        new_subject["cards"] = cards
        shocked.append(new_subject)

    _rescale_overfull_slots(shocked)
    return shocked


def _rescale_overfull_slots(subjects: Sequence[Dict[str, Any]]) -> None:
    """Scale a slot's cards down proportionally when their total exceeds 1.

    Mutates in place. Operates on the union of eligible cards across subjects,
    because that is the set the union probability is computed over.
    """
    totals: Dict[str, float] = {}
    for subject in subjects:
        for card in subject.get("cards") or []:
            probability = _finite(card.get("pull_probability"))
            if probability is None or probability <= 0:
                continue
            slot = str(card.get("slot_group") or "__unknown__")
            totals[slot] = totals.get(slot, 0.0) + probability

    overfull = {slot: total for slot, total in totals.items() if total > 1.0}
    if not overfull:
        return
    for subject in subjects:
        for card in subject.get("cards") or []:
            probability = _finite(card.get("pull_probability"))
            if probability is None or probability <= 0:
                continue
            slot = str(card.get("slot_group") or "__unknown__")
            if slot in overfull:
                card["pull_probability"] = probability / overfull[slot]


# ---------------------------------------------------------------------------
# E. Missing-card treatment
# ---------------------------------------------------------------------------

def remove_cards(
    subjects: Sequence[Mapping[str, Any]],
    *,
    mode: str,
    rng: Optional[random.Random] = None,
    share: float = 0.0,
) -> List[Dict[str, Any]]:
    """Drop eligible cards under one pre-registered removal mode.

    Nothing is imputed. A removed card is GONE, and if enough are gone that the
    set no longer clears the coverage policy, the recomputation returns
    unavailable and the set is reported as unavailable IN THAT DRAW - never
    backfilled with a fabricated card or a substituted probability. Imputing
    here would answer the question "how robust is this score to missing data?"
    with data we invented to fill the gap.

    Modes: ``random`` (with ``share``), ``highest_demand``, ``highest_probability``,
    ``rarest``.
    """
    flat: List[Tuple[int, int, Mapping[str, Any]]] = []
    for s_index, subject in enumerate(subjects):
        for c_index, card in enumerate(subject.get("cards") or []):
            if _finite(card.get("pull_probability")):
                flat.append((s_index, c_index, card))
    if not flat:
        return [dict(s) for s in subjects]

    drop: set = set()
    if mode == "random":
        count = int(round(share * len(flat)))
        if count > 0:
            picks = (rng or random.Random(0)).sample(range(len(flat)), min(count, len(flat)))
            drop = {(flat[i][0], flat[i][1]) for i in picks}
    elif mode == "highest_demand":
        # Demand is a SUBJECT property, so this removes the highest-demand
        # subject's most probable printing - the card a collector is most likely
        # to be chasing.
        best = max(
            flat,
            key=lambda item: (
                _finite(subjects[item[0]].get("subject_demand")) or 0.0,
                _finite(item[2].get("pull_probability")) or 0.0,
            ),
        )
        drop = {(best[0], best[1])}
    elif mode == "highest_probability":
        best = max(flat, key=lambda item: _finite(item[2].get("pull_probability")) or 0.0)
        drop = {(best[0], best[1])}
    elif mode == "rarest":
        best = min(flat, key=lambda item: _finite(item[2].get("pull_probability")) or 1.0)
        drop = {(best[0], best[1])}
    else:
        raise ValueError(f"unknown removal mode {mode!r}")

    out: List[Dict[str, Any]] = []
    for s_index, subject in enumerate(subjects):
        new_subject = dict(subject)
        new_subject["cards"] = [
            dict(card)
            for c_index, card in enumerate(subject.get("cards") or [])
            if (s_index, c_index) not in drop
        ]
        out.append(new_subject)
    return out


# ---------------------------------------------------------------------------
# Recomputing H and P under a perturbation
# ---------------------------------------------------------------------------

def recompute_structural(subjects: Sequence[Mapping[str, Any]]) -> Dict[str, Optional[float]]:
    """H and P for a perturbed subject index, through the PRODUCTION functions.

    Both are recomputed - not just H. Pull-rate shocks and card removals change
    the dual-path structure too (the easiest and rarest printings can change
    identity), and holding P fixed while shocking H would understate the joint
    movement and overstate how independent the two terms are.

    Returns None for either value when the perturbation pushed the set below its
    coverage policy. That is a real outcome of the draw, not an error.
    """
    frequency = compute_desirable_outcome_frequency(subjects)
    depth = compute_dual_path_depth(subjects)
    return {
        "h": frequency.get("rawValue"),
        "p": (depth or {}).get("value"),
        "hStatus": frequency.get("status"),
        "hStatusReason": frequency.get("statusReason"),
    }


# ---------------------------------------------------------------------------
# A. Simulation outcome uncertainty
# ---------------------------------------------------------------------------

def financial_draws_from_outcomes(
    outcomes: Optional[Sequence[float]],
    pack_cost: Any,
    *,
    draws: int,
    seed: int,
    pack_cost_shock: float = 0.0,
    price_shock_cv: float = 0.0,
    min_simulation_count: Optional[int] = None,
) -> Dict[str, Any]:
    """Bootstrap Financial RIP V3 over the ORIGINAL outcome vector.

    Resamples the per-pack outcome vector with replacement and recomputes V3
    from scratch on each resample, through the production engine. This is the
    permitted alternative to rerunning simulations under multiple seeds, and it
    is only valid BECAUSE the real vector is used: see
    :data:`PERCENTILE_RECONSTRUCTION_REFUSAL` for why the stored-percentile
    shortcut is refused.

    ``price_shock_cv`` applies ONE lognormal multiplier to the whole vector per
    draw, not an independent shock per pack. Per-pack independent noise would
    average away across 10,000+ packs and report near-zero price sensitivity;
    a set's card prices move together, so the shock is shared.

    ``pack_cost_shock`` perturbs C uniformly within +/- the given fraction,
    keeping it strictly positive.

    Returns ``available=False`` with a reason when no outcome vector exists,
    which is the expected state for every set until simulations are rerun after
    migration 060.
    """
    from backend.calculations.evr.financial_rip_v3 import build_financial_rip_v3
    from backend.calculations.evr.financial_rip_v3_config import (
        FINANCIAL_RIP_V3_MIN_SIMULATION_COUNT,
    )

    cost = _finite(pack_cost)
    if not outcomes or cost is None or cost <= 0:
        return {
            "available": False,
            "reason": "no_retained_outcome_vector" if not outcomes else "invalid_pack_cost",
            "detail": PERCENTILE_RECONSTRUCTION_REFUSAL,
            "scores": [],
        }

    values = [v for v in (_finite(x) for x in outcomes) if v is not None]
    if not values:
        return {
            "available": False,
            "reason": "no_finite_outcomes",
            "detail": PERCENTILE_RECONSTRUCTION_REFUSAL,
            "scores": [],
        }

    minimum = (
        int(min_simulation_count)
        if min_simulation_count is not None
        else FINANCIAL_RIP_V3_MIN_SIMULATION_COUNT
    )
    rng = random.Random(seed)
    n = len(values)
    scores: List[float] = []
    unavailable = 0

    for _ in range(int(draws)):
        resampled = [values[rng.randrange(n)] for _ in range(n)]
        if price_shock_cv > 0:
            multiplier = _lognormal_multiplier(rng, price_shock_cv)
            resampled = [v * multiplier for v in resampled]
        draw_cost = cost
        if pack_cost_shock > 0:
            draw_cost = max(1e-6, cost * (1.0 + rng.uniform(-pack_cost_shock, pack_cost_shock)))
        result = build_financial_rip_v3(
            resampled, draw_cost, min_simulation_count=minimum
        )
        score = _finite(result.get("score"))
        if score is None:
            unavailable += 1
            continue
        scores.append(score)

    return {
        "available": bool(scores),
        "reason": None if scores else "all_draws_unavailable",
        "draws": int(draws),
        "seed": int(seed),
        "unavailableDraws": unavailable,
        "priceShockCv": price_shock_cv,
        "packCostShock": pack_cost_shock,
        "scores": scores,
    }


# ---------------------------------------------------------------------------
# F. Combined scenario draws
# ---------------------------------------------------------------------------

def combined_appeal_draws(
    subjects_by_set: Mapping[str, Sequence[Mapping[str, Any]]],
    d_by_set: Mapping[str, Optional[float]],
    *,
    draws: int = DEFAULT_COMBINED_DRAWS,
    seed: int,
    pull_rate_cv: float = 0.20,
    missing_card_share: float = 0.05,
    candidate: Optional[Callable[[Any, Any, Any], Optional[float]]] = None,
) -> Dict[str, List[Optional[float]]]:
    """Paired Collector Appeal draws across sets under combined perturbations.

    PAIRING IS THE POINT. Draw i applies the SAME rng stream position to every
    set, so a scenario that is harsh on modeled pull rates is harsh across the
    cohort at once. Downstream, :func:`validation_stats.pairwise_dominance` and
    :func:`validation_stats.rank_stability_bands` compare sets within a draw;
    unpaired marginals would let shared error masquerade as separation and would
    make every set look more distinguishable than it is.

    Returns ``{set_id: [score_or_None per draw]}``. None marks a draw where the
    perturbation pushed the set below its coverage policy - carried through
    rather than dropped, so a set that survives only 60% of draws is visible as
    such instead of quietly having a tighter interval than its peers.
    """
    from backend.research.collector_appeal_candidates import compute_primary

    score_fn = candidate or compute_primary
    keys = sorted(subjects_by_set)
    out: Dict[str, List[Optional[float]]] = {key: [] for key in keys}

    for draw_index in range(int(draws)):
        for key in keys:
            # Seeded per (draw, set) so a set's stream does not depend on how
            # many sets precede it - adding a set to the cohort must not change
            # another set's draws, or two runs on different cohorts would be
            # incomparable.
            rng = random.Random(f"{seed}:{draw_index}:{key}")
            subjects = subjects_by_set[key]
            perturbed = shock_pull_rates(subjects, rng=rng, magnitude=pull_rate_cv)
            if missing_card_share > 0:
                perturbed = remove_cards(
                    perturbed, mode="random", rng=rng, share=missing_card_share
                )
            structural = recompute_structural(perturbed)
            out[key].append(
                score_fn(d_by_set.get(key), structural["h"], structural["p"])
            )
    return out


def scenario_registry() -> Dict[str, Any]:
    """The pre-registered scenario grid, published into the manifest."""
    return {
        "version": UNCERTAINTY_VERSION,
        "pullRateShockCv": list(PULL_RATE_SHOCK_SCENARIOS),
        "cardPriceCv": list(CARD_PRICE_CV_SCENARIOS),
        "packCostShock": list(PACK_COST_SHOCK_SCENARIOS),
        "missingCardRandomShares": list(MISSING_CARD_RANDOM_SHARES),
        "missingCardTargetedModes": list(MISSING_CARD_TARGETED_MODES),
        "defaultCombinedDraws": DEFAULT_COMBINED_DRAWS,
        "shockGrouping": "(slot_group, rarity) for pull rates; whole-vector for card price",
        "percentileReconstruction": PERCENTILE_RECONSTRUCTION_REFUSAL,
        "cardPriceVolatilitySource": (
            "Empirical volatility is preferred when the repository has sufficient "
            "recent observations; the CV scenarios above are clearly-labelled "
            "stress assumptions used when it does not."
        ),
    }
