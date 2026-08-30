"""Stage-II per-set analysis: chase universes x (Chase EV, Beat-the-Buy, Gap, Depth).

Reuses Stage I's simulation harness unchanged (``simulate_set``,
``entity_identities``, ``partition_universe``). One 1,000,000-pack decomposition
per set answers every candidate universe, because a universe is just a different
mask over the same recorded draws.
"""

from __future__ import annotations

from collections import Counter
from typing import Any, Dict, List, Mapping, Optional, Sequence

import numpy as np

from .baskets import ChaseCandidate, partition_universe
from .chase_metrics import beat_the_buy, chase_cost_gap, chase_ev
from .chase_universe import (
    boundary_description,
    candidate_universes,
    depth_statistics,
    jaccard,
    largest_log_gap,
    log_price_two_cluster,
    modified_zscore_outliers,
    ordered_universe,
    perturbed_universe,
)
from .metrics import binomial_standard_error, hit_count_distribution
from .runner import DEFAULT_PACK_COUNT, entity_identities, simulate_set
from .version import SET_CHASE_EFFICIENCY_RESEARCH_VERSION

#: Price-shock magnitudes the selection rules are stress-tested at.
PERTURBATION_MAGNITUDES = (0.05, 0.10)

#: Independent shock draws per magnitude. Enough to separate a rule that never
#: moves from one that moves occasionally, without a second simulation.
PERTURBATION_TRIALS = 25

#: Basket sizes the anti-degeneration sweep walks. Deliberately runs far past
#: any plausible chase universe and out to the whole eligible set: Stage I's
#: metric was rejected because it kept climbing all the way out, and the only
#: way to show Beat-the-Buy does not is to take it to the same place.
DEGENERATION_K = (1, 2, 3, 5, 7, 10, 15, 20, 30, 50, 75, 100, 150, 200)


def _universe_vectors(decomposition: Any, prices: np.ndarray,
                      entity_ids: Sequence[int]) -> Dict[str, np.ndarray]:
    """Per-pack qualifying (count, total value, best value) for one universe."""
    mask = np.zeros(decomposition.entity_count, dtype=bool)
    if len(entity_ids):
        mask[np.asarray(list(entity_ids), dtype=np.int64)] = True
    masked = np.where(mask, prices, 0.0)
    counts = np.rint(decomposition.pack_values(mask.astype(np.float64))).astype(np.int64)
    return {
        "counts": counts,
        "totals": decomposition.pack_values(masked),
        "best": decomposition.pack_max_entity_value(masked),
        "qualifying": counts > 0,
    }


def evaluate_universe(
    *,
    decomposition: Any,
    prices: np.ndarray,
    full_pack_values: np.ndarray,
    universe: Mapping[str, Any],
    eligible: Sequence[ChaseCandidate],
    pack_cost: Optional[float],
    pull_counts: np.ndarray,
    pack_count: int,
) -> Dict[str, Any]:
    """Every Stage-II measure for one (set x chase universe) pair."""
    members: Sequence[ChaseCandidate] = universe["members"]
    payload: Dict[str, Any] = {
        "family": universe["family"],
        "key": universe["key"],
        "detail": universe["detail"],
        "k": len(members),
        "memberEntityIds": [m.entity_id for m in members],
        "members": [
            {"cardName": m.card_name, "cardNumber": m.card_number,
             "cardVariantId": m.card_variant_id, "marketPrice": m.price,
             "printingType": m.printing_type}
            for m in members
        ],
        **boundary_description(eligible, members),
    }
    if not members:
        payload.update({
            "supported": False,
            "unsupportedReason": universe["detail"].get("reason") or "empty chase universe",
            "anyChaseProbability": None, "chaseEv": None, "beatTheBuyBest": None,
        })
        return payload

    vectors = _universe_vectors(decomposition, prices, [m.entity_id for m in members])
    distribution = hit_count_distribution(vectors["counts"])
    p_s = distribution["pAtLeastOne"]

    ev_contributions = [float(pull_counts[m.entity_id]) * m.price / pack_count
                        for m in members]
    hit_probabilities = [float(pull_counts[m.entity_id]) / pack_count for m in members]

    payload.update({
        "supported": True,
        "unsupportedReason": None,
        "anyChaseProbability": p_s,
        "anyChaseProbabilityStandardError": binomial_standard_error(p_s, pack_count),
        "hitCountDistribution": distribution,
        "chaseEvBlock": chase_ev(qualifying_totals=vectors["totals"], pack_cost=pack_cost,
                                 full_pack_values=full_pack_values),
        # Definition A: the best qualifying card in the successful pack. "Did I
        # beat buying the best chase I actually hit?"
        "beatTheBuyBest": beat_the_buy(
            qualifying=vectors["qualifying"], chase_values=vectors["best"],
            probability=p_s, pack_cost=pack_cost),
        # Definition B: the whole qualifying haul from that pack. Differs only
        # where multi-hit mechanics exist.
        "beatTheBuyTotal": beat_the_buy(
            qualifying=vectors["qualifying"], chase_values=vectors["totals"],
            probability=p_s, pack_cost=pack_cost),
        "chaseCostGapBest": chase_cost_gap(
            qualifying=vectors["qualifying"], chase_values=vectors["best"],
            pack_cost=pack_cost),
        "chaseCostGapTotal": chase_cost_gap(
            qualifying=vectors["qualifying"], chase_values=vectors["totals"],
            pack_cost=pack_cost),
        "depth": depth_statistics(members, ev_contributions=ev_contributions,
                                  hit_probabilities=hit_probabilities),
        "memberContributions": [
            {"cardName": m.card_name, "marketPrice": m.price,
             "hitProbability": round(hp, 12), "chaseEvContribution": round(ev, 12)}
            for m, ev, hp in zip(members, ev_contributions, hit_probabilities)
        ],
    })
    return payload


def degeneration_sweep(
    *,
    decomposition: Any,
    prices: np.ndarray,
    full_pack_values: np.ndarray,
    eligible: Sequence[ChaseCandidate],
    pack_cost: Optional[float],
    pack_count: int,
) -> List[Dict[str, Any]]:
    """Beat-the-Buy and Chase EV as the basket is widened to the whole set.

    THE ANTI-DEGENERATION TEST. Stage I's metric was rejected because widening
    the basket raised it without bound until it became EV over cost. A candidate
    Chase Efficiency measure must NOT do that. Chase EV is swept alongside
    precisely because Chase EV *should* keep rising - it is an EV metric - so
    the two curves in the same table make the distinction visible rather than
    asserted.
    """
    ordered = ordered_universe(eligible)
    rows: List[Dict[str, Any]] = []
    for k in (*DEGENERATION_K, len(ordered)):
        if k > len(ordered) or any(row["k"] == k for row in rows):
            continue
        members = ordered[:k]
        vectors = _universe_vectors(decomposition, prices, [m.entity_id for m in members])
        distribution = hit_count_distribution(vectors["counts"])
        p_s = distribution["pAtLeastOne"]
        rows.append({
            "k": k,
            "lowestSelectedValue": members[-1].price,
            "anyChaseProbability": p_s,
            "chaseEvBlock": chase_ev(qualifying_totals=vectors["totals"],
                                     pack_cost=pack_cost,
                                     full_pack_values=full_pack_values),
            "beatTheBuyBest": beat_the_buy(qualifying=vectors["qualifying"],
                                           chase_values=vectors["best"],
                                           probability=p_s, pack_cost=pack_cost),
            "beatTheBuyTotal": beat_the_buy(qualifying=vectors["qualifying"],
                                            chase_values=vectors["totals"],
                                            probability=p_s, pack_cost=pack_cost),
            "chaseCostGapBest": chase_cost_gap(qualifying=vectors["qualifying"],
                                               chase_values=vectors["best"],
                                               pack_cost=pack_cost),
        })
    return rows


def selection_stability(
    eligible: Sequence[ChaseCandidate],
    *,
    pack_cost: Optional[float],
    ev_contribution_for,
    hit_probability_for,
    seed_base: int,
) -> Dict[str, Any]:
    """How much each selection rule moves under independent price shocks.

    A rule whose chosen card set survives a +/-10% shock is measuring the set's
    structure. A rule that reshuffles is measuring one day's noise, and no
    amount of elegance rescues it.
    """
    baseline = {entry["key"]: [m.entity_id for m in entry["members"]]
                for entry in candidate_universes(
                    eligible, pack_cost=pack_cost,
                    ev_contribution_for=ev_contribution_for,
                    hit_probability_for=hit_probability_for)}
    results: Dict[str, Any] = {}
    for magnitude in PERTURBATION_MAGNITUDES:
        overlaps: Dict[str, List[float]] = {key: [] for key in baseline}
        sizes: Dict[str, List[int]] = {key: [] for key in baseline}
        for trial in range(PERTURBATION_TRIALS):
            shocked = perturbed_universe(
                eligible, magnitude=magnitude, seed=seed_base + trial)
            for entry in candidate_universes(
                    shocked, pack_cost=pack_cost,
                    ev_contribution_for=ev_contribution_for,
                    hit_probability_for=hit_probability_for):
                ids = [m.entity_id for m in entry["members"]]
                sizes[entry["key"]].append(len(ids))
                score = jaccard(baseline.get(entry["key"], []), ids)
                if score is not None:
                    overlaps[entry["key"]].append(score)
        results[f"{int(magnitude * 100)}pct"] = {
            key: {
                "meanJaccard": (round(float(np.mean(values)), 6) if values else None),
                "minJaccard": (round(float(np.min(values)), 6) if values else None),
                "baselineK": len(baseline.get(key, [])),
                "kMin": min(sizes[key]) if sizes[key] else None,
                "kMax": max(sizes[key]) if sizes[key] else None,
            }
            for key, values in overlaps.items()
        }
    return results


def core_and_extended(universes: Sequence[Mapping[str, Any]],
                      *, families: Sequence[str] = ("economic", "price_boundary", "hhi_adaptive"),
                      core_agreement: float = 0.75) -> Dict[str, Any]:
    """Cards every defensible rule agrees on, versus cards only some select.

    Fixed-K is excluded from the vote deliberately: Stage I already showed it is
    not a defensible rule, and letting three arbitrary K values vote three times
    would let the discredited family decide the outcome.
    """
    voters = [entry for entry in universes
              if entry["family"] in families and entry.get("supported")]
    if not voters:
        return {"voters": 0, "core": [], "extended": [], "coreAgreementThreshold": core_agreement}
    tally: Counter = Counter()
    names: Dict[int, Dict[str, Any]] = {}
    for entry in voters:
        for member in entry["members"]:
            key = member["cardVariantId"] or member["cardName"]
            tally[key] += 1
            names.setdefault(key, member)
    total = len(voters)
    core, extended = [], []
    for key, count in tally.most_common():
        row = {**names[key], "selectedBy": count, "selectionRate": round(count / total, 4)}
        (core if count / total >= core_agreement else extended).append(row)
    return {
        "voters": total,
        "coreAgreementThreshold": core_agreement,
        "coreCount": len(core),
        "extendedCount": len(extended),
        "core": core,
        "extended": extended,
    }


def analyse_set_stage2(
    *,
    config: Any,
    dataframe: Any,
    set_id: str,
    set_name: Optional[str],
    canonical_key: str,
    calculation_run_id: str,
    market_date: str,
    pack_cost: Optional[float],
    pack_cost_basis: Mapping[str, Any],
    pack_count: int = DEFAULT_PACK_COUNT,
) -> Dict[str, Any]:
    run = simulate_set(config=config, dataframe=dataframe,
                       calculation_run_id=calculation_run_id,
                       canonical_key=canonical_key, pack_count=pack_count)
    decomposition = run["decomposition"]
    identities = entity_identities(decomposition, run["dataframe"])
    eligible, excluded = partition_universe(identities, market_date=market_date)
    prices = decomposition.price_vector()
    pull_counts = decomposition.pull_counts()
    full_values = run["values"]

    def ev_contribution_for(candidate: ChaseCandidate) -> float:
        return float(pull_counts[candidate.entity_id]) * candidate.price / pack_count

    def hit_probability_for(candidate: ChaseCandidate) -> float:
        return float(pull_counts[candidate.entity_id]) / pack_count

    universes = candidate_universes(
        eligible, pack_cost=pack_cost,
        ev_contribution_for=ev_contribution_for,
        hit_probability_for=hit_probability_for)

    evaluated = [
        evaluate_universe(
            decomposition=decomposition, prices=prices, full_pack_values=full_values,
            universe=universe, eligible=eligible, pack_cost=pack_cost,
            pull_counts=pull_counts, pack_count=pack_count)
        for universe in universes
    ]

    ordered = ordered_universe(eligible)
    return {
        "setId": set_id,
        "setName": set_name,
        "canonicalKey": canonical_key,
        "calculationRunId": calculation_run_id,
        "marketDate": market_date,
        "researchVersion": SET_CHASE_EFFICIENCY_RESEARCH_VERSION,
        "simulation": {
            "seed": run["seed"], "packCount": run["packCount"],
            "simulationSeconds": run["simulationSeconds"],
            "decompositionMaxAbsError": run["decompositionMaxAbsError"],
            "simulatedMeanPackValue": run["simulatedMeanPackValue"],
        },
        "acquisitionCost": {"packEquivalentCost": pack_cost, **dict(pack_cost_basis)},
        "coverage": {
            "drawableEntities": len(identities),
            "eligibleChaseUniverse": len(eligible),
            "excludedEntities": len(excluded),
            "excludedByReason": dict(sorted(Counter(r["reason"] for r in excluded).items())),
            "topPrices": [round(c.price, 2) for c in ordered[:25]],
        },
        "priceBoundaryDiagnostics": {
            "largestLogGap": largest_log_gap(eligible),
            "robustZscore": modified_zscore_outliers(eligible),
            "logPrice2Means": log_price_two_cluster(eligible),
        },
        "universes": evaluated,
        "degenerationSweep": degeneration_sweep(
            decomposition=decomposition, prices=prices, full_pack_values=full_values,
            eligible=eligible, pack_cost=pack_cost, pack_count=pack_count),
        "coreExtended": core_and_extended(evaluated),
        "selectionStability": selection_stability(
            eligible, pack_cost=pack_cost,
            ev_contribution_for=ev_contribution_for,
            hit_probability_for=hit_probability_for,
            seed_base=run["seed"] % 100_000),
    }
