"""Candidate definitions of "which cards in this set are actually chases".

WHY THIS MODULE EXISTS
----------------------
Stage I proved the aggregate Chase Efficiency form degenerate and, in passing,
showed that fixed Top-K is not a defensible chase definition: the Top-K ranking
at K=1 and K=20 correlate at only rho=0.516, so K was choosing the answer. This
module holds every candidate REPLACEMENT rule, so they can be compared on equal
terms rather than one being assumed.

The families, and what each one is betting on:

* ``fixed_k``          - the Stage-I baseline, retained only as a control.
* ``economic``         - value as a multiple of one pack's cost. Dimensionless
                         in the buyer's own currency and the only family that is
                         directly comparable across a $4.74 set and a $29.81 one.
* ``price_boundary``   - the set's own price distribution has a gap, and the gap
                         is the chase line. Makes no cross-set assumption at all.
* ``hhi_adaptive``     - effective chase count, rounded, IS the chase count.

THE CIRCULARITY IN ``hhi_adaptive``, STATED UP FRONT
----------------------------------------------------
Effective chase count is computed FROM a basket, so using it to CHOOSE the
basket needs a reference pool to start from. There is no neutral choice: the
full eligible universe is hundreds of near-worthless commons and drives HHI to
near zero, while any narrow pool has already made most of the decision. This
module therefore computes the adaptive K from SEVERAL reference pools and
reports the spread, because the spread is the finding.
"""

from __future__ import annotations

import math
from typing import Any, Callable, Dict, List, Optional, Sequence, Tuple

import numpy as np

from .baskets import ChaseCandidate

#: Top-K controls carried over from Stage I.
FIXED_K = (3, 5, 10)

#: Value-to-pack-cost multiples. These answer "is this card worth enough
#: relative to one pack to plausibly BE the reason someone opens packs".
COST_MULTIPLES = (2.0, 5.0, 10.0, 20.0)

#: Reference pools the adaptive-K rules are allowed to start from. Each is a
#: different prior about how wide a chase pool could possibly be.
REFERENCE_POOLS = ("top_20", "top_25", "gte_1x_cost", "gte_2x_cost")

#: Only the upper tail is searched for a price boundary. A gap between the $0.06
#: and $0.11 commons is enormous in log terms and means nothing economically.
BOUNDARY_SEARCH_DEPTH = 30


def ordered_universe(universe: Sequence[ChaseCandidate]) -> List[ChaseCandidate]:
    """Most valuable first, deterministic tie-break."""
    return sorted(universe, key=lambda c: (-c.price, str(c.card_variant_id or ""), c.entity_id))


# ---------------------------------------------------------------------------
# Depth statistics
# ---------------------------------------------------------------------------

def _hhi(weights: Sequence[float]) -> Tuple[Optional[float], Optional[float]]:
    values = np.asarray([float(w) for w in weights], dtype=np.float64)
    values = values[np.isfinite(values) & (values > 0)]
    total = float(values.sum())
    if values.size == 0 or total <= 0:
        return None, None
    shares = values / total
    hhi = float((shares ** 2).sum())
    return hhi, (1.0 / hhi if hhi > 0 else None)


def depth_statistics(
    members: Sequence[ChaseCandidate],
    *,
    ev_contributions: Sequence[float],
    hit_probabilities: Sequence[float],
) -> Dict[str, Any]:
    """The three concentration concepts, measured side by side.

    They are NOT interchangeable and the study needs to see where they diverge:

    * value      - how lopsided the price list is. Ignores reachability, so a
                   $1,500 card nobody can pull still dominates it.
    * ev         - how lopsided the per-pack expected chase value is. Carries
                   both price and reachability, which is why it is the honest
                   answer to "how many cards effectively produce this chase".
    * probability- how lopsided ACCESS is. A set can be value-concentrated and
                   probability-flat at the same time; that combination is what
                   a single-hero set looks like from the buyer's side.
    """
    value_hhi, value_effective = _hhi([m.price for m in members])
    ev_hhi, ev_effective = _hhi(ev_contributions)
    probability_hhi, probability_effective = _hhi(hit_probabilities)
    return {
        "memberCount": len(members),
        "valueHhi": value_hhi,
        "effectiveValueCount": value_effective,
        "evHhi": ev_hhi,
        "effectiveEvCount": ev_effective,
        "probabilityHhi": probability_hhi,
        "effectiveProbabilityCount": probability_effective,
    }


# ---------------------------------------------------------------------------
# Price-boundary detection
# ---------------------------------------------------------------------------

def largest_log_gap(universe: Sequence[ChaseCandidate], *,
                    depth: int = BOUNDARY_SEARCH_DEPTH,
                    minimum_price: float = 1.0) -> Dict[str, Any]:
    """K at the biggest multiplicative price drop in the upper tail.

    Log space, not dollars: the economically meaningful discontinuity is "the
    next card is a third of the price", not "the next card is $40 cheaper",
    which would always fire at the top of an expensive set.
    """
    ordered = [c for c in ordered_universe(universe) if c.price >= minimum_price]
    window = ordered[: max(depth, 2)]
    if len(window) < 2:
        return {"k": None, "reason": "fewer than two cards above the price floor",
                "boundaryRatio": None}
    ratios = [
        (math.log(window[i].price) - math.log(window[i + 1].price), i + 1)
        for i in range(len(window) - 1)
    ]
    best_gap, k = max(ratios, key=lambda item: (item[0], -item[1]))
    return {
        "k": k,
        "boundaryLogGap": round(best_gap, 6),
        "boundaryRatio": round(math.exp(best_gap), 4),
        "reason": None,
    }


def modified_zscore_outliers(universe: Sequence[ChaseCandidate], *,
                             threshold: float = 3.5,
                             minimum_price: float = 1.0) -> Dict[str, Any]:
    """Cards whose log price is a robust outlier against the set's own body.

    Median/MAD rather than mean/sd, because the chase cards ARE the outliers and
    would otherwise inflate the very dispersion they are being tested against.
    """
    prices = [c.price for c in ordered_universe(universe) if c.price >= minimum_price]
    if len(prices) < 8:
        return {"k": None, "reason": "too few priced cards for a robust dispersion estimate"}
    logs = np.log(np.asarray(prices, dtype=np.float64))
    median = float(np.median(logs))
    mad = float(np.median(np.abs(logs - median)))
    if mad <= 0:
        return {"k": None, "reason": "zero median absolute deviation"}
    scores = 0.6745 * (logs - median) / mad
    k = int(np.count_nonzero(scores >= threshold))
    return {"k": k or None, "threshold": threshold,
            "reason": None if k else "no card clears the outlier threshold"}


def log_price_two_cluster(universe: Sequence[ChaseCandidate], *,
                          minimum_price: float = 1.0,
                          iterations: int = 100) -> Dict[str, Any]:
    """1-D two-means split of log prices; the upper cluster is the chase pool.

    Deterministic: seeded by the min/max of the log-price vector rather than
    randomly, so the same set always produces the same split.
    """
    prices = [c.price for c in ordered_universe(universe) if c.price >= minimum_price]
    if len(prices) < 4:
        return {"k": None, "reason": "too few priced cards to cluster"}
    logs = np.sort(np.log(np.asarray(prices, dtype=np.float64)))
    low, high = float(logs[0]), float(logs[-1])
    if high - low < 1e-9:
        return {"k": None, "reason": "log prices are degenerate"}
    for _ in range(iterations):
        boundary = (low + high) / 2.0
        lower, upper = logs[logs < boundary], logs[logs >= boundary]
        if lower.size == 0 or upper.size == 0:
            break
        new_low, new_high = float(lower.mean()), float(upper.mean())
        if abs(new_low - low) < 1e-12 and abs(new_high - high) < 1e-12:
            break
        low, high = new_low, new_high
    boundary = (low + high) / 2.0
    k = int(np.count_nonzero(logs >= boundary))
    return {"k": k or None, "clusterBoundaryPrice": round(float(np.exp(boundary)), 4),
            "reason": None if k else "upper cluster is empty"}


# ---------------------------------------------------------------------------
# Universe construction
# ---------------------------------------------------------------------------

def _take(universe: Sequence[ChaseCandidate], k: Optional[int]) -> Tuple[ChaseCandidate, ...]:
    ordered = ordered_universe(universe)
    if not k or k <= 0:
        return tuple()
    return tuple(ordered[: min(int(k), len(ordered))])


def reference_pool(universe: Sequence[ChaseCandidate], name: str,
                   pack_cost: Optional[float]) -> Tuple[ChaseCandidate, ...]:
    ordered = ordered_universe(universe)
    if name == "top_20":
        return tuple(ordered[:20])
    if name == "top_25":
        return tuple(ordered[:25])
    if name in ("gte_1x_cost", "gte_2x_cost"):
        if not pack_cost or pack_cost <= 0:
            return tuple()
        multiple = 1.0 if name == "gte_1x_cost" else 2.0
        return tuple(c for c in ordered if c.price >= multiple * pack_cost)
    raise ValueError(f"unknown reference pool {name}")


def candidate_universes(
    universe: Sequence[ChaseCandidate],
    *,
    pack_cost: Optional[float],
    ev_contribution_for: Callable[[ChaseCandidate], float],
    hit_probability_for: Callable[[ChaseCandidate], float],
) -> List[Dict[str, Any]]:
    """Every candidate chase universe for one set, with its provenance.

    Each entry records HOW it was selected and WHY it might be empty, so an
    unselectable set is visible in the comparison table rather than absent.
    """
    ordered = ordered_universe(universe)
    results: List[Dict[str, Any]] = []

    def emit(family: str, key: str, members: Sequence[ChaseCandidate],
             detail: Optional[Dict[str, Any]] = None) -> None:
        results.append({
            "family": family,
            "key": key,
            "members": tuple(members),
            "detail": detail or {},
        })

    for k in FIXED_K:
        emit("fixed_k", f"top_{k}", _take(ordered, k) if len(ordered) >= k else tuple(),
             {"requestedK": k, "available": len(ordered)})

    for multiple in COST_MULTIPLES:
        if not pack_cost or pack_cost <= 0:
            emit("economic", f"gte_{int(multiple)}x_cost", tuple(),
                 {"reason": "no usable pack-equivalent cost"})
            continue
        floor = multiple * pack_cost
        emit("economic", f"gte_{int(multiple)}x_cost",
             tuple(c for c in ordered if c.price >= floor),
             {"multiple": multiple, "priceFloor": round(floor, 4)})

    gap = largest_log_gap(ordered)
    emit("price_boundary", "largest_log_gap", _take(ordered, gap.get("k")), gap)
    zscore = modified_zscore_outliers(ordered)
    emit("price_boundary", "robust_zscore", _take(ordered, zscore.get("k")), zscore)
    cluster = log_price_two_cluster(ordered)
    emit("price_boundary", "log_price_2means", _take(ordered, cluster.get("k")), cluster)

    for pool_name in REFERENCE_POOLS:
        pool = reference_pool(ordered, pool_name, pack_cost)
        if not pool:
            for weighting in ("value", "ev"):
                emit("hhi_adaptive", f"{weighting}_hhi_{pool_name}", tuple(),
                     {"referencePool": pool_name, "reason": "reference pool is empty"})
            continue
        stats = depth_statistics(
            pool,
            ev_contributions=[ev_contribution_for(c) for c in pool],
            hit_probabilities=[hit_probability_for(c) for c in pool],
        )
        for weighting, effective in (("value", stats["effectiveValueCount"]),
                                     ("ev", stats["effectiveEvCount"])):
            k = None if effective is None else max(1, int(round(effective)))
            emit("hhi_adaptive", f"{weighting}_hhi_{pool_name}", _take(ordered, k), {
                "referencePool": pool_name,
                "referencePoolSize": len(pool),
                "effectiveCount": effective,
                "kFloor": None if effective is None else max(1, int(math.floor(effective))),
                "kRound": k,
                "kCeil": None if effective is None else max(1, int(math.ceil(effective))),
            })

    return results


# ---------------------------------------------------------------------------
# Boundary description and stability
# ---------------------------------------------------------------------------

def boundary_description(universe: Sequence[ChaseCandidate],
                         members: Sequence[ChaseCandidate]) -> Dict[str, Any]:
    """What the selection rule actually cut, in dollars.

    ``boundaryRatio`` is the multiplicative step at the cut. A rule that slices
    through a flat run of similarly priced cards produces a ratio near 1.0 and
    is, by construction, an arbitrary cut - which is the whole question.
    """
    ordered = ordered_universe(universe)
    chosen = {m.entity_id for m in members}
    included = [c for c in ordered if c.entity_id in chosen]
    excluded = [c for c in ordered if c.entity_id not in chosen]
    lowest = included[-1].price if included else None
    highest_excluded = excluded[0].price if excluded else None
    ratio = None
    if lowest and highest_excluded and highest_excluded > 0:
        ratio = round(lowest / highest_excluded, 4)
    return {
        "k": len(included),
        "lowestSelectedValue": lowest,
        "highestExcludedValue": highest_excluded,
        "boundaryRatio": ratio,
        "boundaryGapDollars": (None if lowest is None or highest_excluded is None
                               else round(lowest - highest_excluded, 4)),
    }


def perturbed_universe(universe: Sequence[ChaseCandidate], *, magnitude: float,
                       seed: int) -> List[ChaseCandidate]:
    """The same cards under an independent multiplicative price shock.

    Used to ask whether a selection rule is measuring the set's structure or
    the noise in a single day's prices. Shocks are per-card and seeded, so a
    stability figure is reproducible.
    """
    rng = np.random.default_rng(seed)
    shocked: List[ChaseCandidate] = []
    for candidate in universe:
        factor = 1.0 + float(rng.uniform(-magnitude, magnitude))
        shocked.append(ChaseCandidate(
            entity_id=candidate.entity_id,
            card_variant_id=candidate.card_variant_id,
            card_id=candidate.card_id,
            card_name=candidate.card_name,
            card_number=candidate.card_number,
            printing_type=candidate.printing_type,
            rarity_key=candidate.rarity_key,
            price=max(candidate.price * factor, 1e-6),
            price_captured_at=candidate.price_captured_at,
            price_source=candidate.price_source,
            pull_count=candidate.pull_count,
        ))
    return shocked


def jaccard(a: Sequence[int], b: Sequence[int]) -> Optional[float]:
    """Overlap of two selected card sets. ``None`` when both are empty."""
    left, right = set(a), set(b)
    if not left and not right:
        return None
    union = left | right
    return round(len(left & right) / len(union), 6) if union else None
