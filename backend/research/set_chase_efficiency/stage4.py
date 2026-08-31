"""Stage IV: evaluate objective Chase Tier candidates against set economics.

One 1,000,000-pack decomposition per set answers every candidate tier system,
because a tier is just a different mask over the same recorded draws. Nothing
here re-simulates per rule.

WHAT IS CHEAP AND WHAT IS NOT
-----------------------------
Two facts shape the whole design:

* Tier MEMBERSHIP depends only on prices, so shocking prices and re-selecting
  costs nothing. Price-shock and temporal membership stability are therefore
  measured exhaustively.
* Any-hit probability and the Beat-the-Buy distribution depend on the pack
  DRAWS, so each distinct membership set costs three chunked passes over a
  million packs. Those are cached by membership fingerprint, because the same
  card set recurs constantly across rules, shock trials and market dates.

Chase EV is the exception that makes temporal work practical: it is LINEAR in
price, ``sum over members of (expected copies per pack) * price``, so it can be
recomputed under any price vector with no simulation at all.
"""

from __future__ import annotations

from collections import Counter
from typing import Any, Dict, List, Mapping, Optional, Sequence, Tuple

import numpy as np

from .baskets import ChaseCandidate, partition_universe
from .chase_metrics import beat_the_buy, chase_cost_gap, chase_ev
from .chase_universe import depth_statistics
from .metrics import binomial_standard_error, hit_count_distribution, horizon_block
from .runner import DEFAULT_PACK_COUNT, entity_identities, simulate_set
from .tiers import (
    TierSystem,
    candidate_rules,
    candidate_systems,
    jaccard,
    ordered,
    shocked_cards,
)
from .version import SET_CHASE_EFFICIENCY_RESEARCH_VERSION

STAGE4_VERSION = "stage4-objective-chase-tiers-v1"

#: Independent price-shock magnitudes (per-card noise).
SHOCK_MAGNITUDES: Tuple[float, ...] = (0.02, 0.05, 0.10, 0.20)

#: Joint (market-wide level) shock magnitudes.
JOINT_SHOCK_MAGNITUDES: Tuple[float, ...] = (0.05, 0.10, 0.20)

#: Pack-cost shock magnitudes. Only rules with an economic floor can react.
PACK_COST_SHOCKS: Tuple[float, ...] = (0.05, 0.10, 0.20)

#: Trials per shock magnitude. Enough to separate "never moves" from "moves
#: occasionally" without a second simulation.
SHOCK_TRIALS = 20


#: Reason code for a printing whose tradeable identity cannot be resolved.
REASON_AMBIGUOUS_IDENTITY = "ambiguous_variant_identity_duplicate"

BASE_PRICE_COLUMN = "Price ($)"


def drop_ambiguous_identities(identities: Sequence[Mapping[str, Any]]
                              ) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    """Enforce one tradeable identity per ``card_variant_id`` within a set.

    ``EVRInputPreparationService`` echoes the BASE variant id into
    ``reverse_variant_id`` for cards that have no separate reverse printing. The
    simulator still registers a reverse-column sampling entity for some of those
    rows, so two economically distinct entities end up claiming the same
    ``card_variant_id`` at different prices. That is 8 entities across 3 sets
    (Shrouded Fable 6, Perfect Order 1, Scarlet and Violet Base Set 1) out of
    7,530.

    Tiers are published per tradeable card, so an entity whose identity is
    ambiguous cannot be tiered: it would appear twice in one tier at two
    different prices. The BASE-column entity keeps the id - that is the id's
    real owner - and the reverse-column claimant is excluded with a reason.

    This is deliberately Stage-IV local. The same collision exists upstream in
    ``entity_identities``, but repairing it there would change Stage-I and
    Stage-II results and leave their published artifacts inconsistent with the
    code that produced them. Recorded here as a follow-up instead.
    """
    counts: Counter = Counter(str(row.get("card_variant_id") or "") for row in identities)
    kept: List[Dict[str, Any]] = []
    dropped: List[Dict[str, Any]] = []
    for row in identities:
        variant = str(row.get("card_variant_id") or "")
        if variant and counts[variant] > 1 and row.get("price_column") != BASE_PRICE_COLUMN:
            dropped.append({
                "entityId": row.get("entity_id"),
                "cardVariantId": variant,
                "cardName": row.get("card_name"),
                "priceColumn": row.get("price_column"),
                "price": row.get("price"),
                "reason": REASON_AMBIGUOUS_IDENTITY,
            })
            continue
        kept.append(dict(row))
    return kept, dropped


class _EconomicsCache:
    """Evaluate a membership set once, however many rules select it.

    Keyed by the frozen entity-id set. Across ~60 rules x 21 sets the same
    membership recurs constantly - three percentile rules often land on the
    identical cards - and each evaluation is three passes over a million packs.
    """

    def __init__(self, decomposition: Any, prices: np.ndarray,
                 full_pack_values: np.ndarray, pack_cost: Optional[float],
                 pack_count: int) -> None:
        self._decomposition = decomposition
        self._prices = prices
        self._full = full_pack_values
        self._pack_cost = pack_cost
        self._pack_count = pack_count
        self._cache: Dict[frozenset, Dict[str, Any]] = {}
        self.evaluations = 0
        self.cache_hits = 0

    def economics(self, members: Sequence[ChaseCandidate]) -> Dict[str, Any]:
        key = frozenset(member.entity_id for member in members)
        cached = self._cache.get(key)
        if cached is not None:
            self.cache_hits += 1
            return cached
        self.evaluations += 1
        result = self._evaluate(members)
        self._cache[key] = result
        return result

    def _evaluate(self, members: Sequence[ChaseCandidate]) -> Dict[str, Any]:
        if not members:
            return {"supported": False, "reason": "empty tier",
                    "chaseCount": 0, "anyChaseProbability": None}
        mask = np.zeros(self._decomposition.entity_count, dtype=bool)
        mask[np.asarray([m.entity_id for m in members], dtype=np.int64)] = True
        masked = np.where(mask, self._prices, 0.0)
        counts = np.rint(
            self._decomposition.pack_values(mask.astype(np.float64))).astype(np.int64)
        totals = self._decomposition.pack_values(masked)
        best = self._decomposition.pack_max_entity_value(masked)
        qualifying = counts > 0

        distribution = hit_count_distribution(counts)
        p_s = distribution["pAtLeastOne"]
        ev_block = chase_ev(qualifying_totals=totals, pack_cost=self._pack_cost,
                            full_pack_values=self._full)
        btb = beat_the_buy(qualifying=qualifying, chase_values=best,
                           probability=p_s, pack_cost=self._pack_cost)
        gap = chase_cost_gap(qualifying=qualifying, chase_values=best,
                             pack_cost=self._pack_cost)
        pull_counts = self._decomposition.pull_counts()
        contributions = [float(pull_counts[m.entity_id]) * m.price / self._pack_count
                         for m in members]
        probabilities = [float(pull_counts[m.entity_id]) / self._pack_count
                         for m in members]
        return {
            "supported": True,
            "reason": None,
            "chaseCount": len(members),
            "minimumQualifyingValue": min(m.price for m in members),
            "maximumQualifyingValue": max(m.price for m in members),
            "anyChaseProbability": p_s,
            "anyChaseProbabilityStandardError": binomial_standard_error(
                p_s, self._pack_count),
            "expectedPacksPerHit": None if not p_s else round(1.0 / p_s, 9),
            "hitCountDistribution": distribution,
            "chaseEv": ev_block,
            "beatTheBuy": btb,
            "chaseCostGap": gap,
            "horizons": horizon_block(p_s, self._pack_cost),
            "depth": depth_statistics(members, ev_contributions=contributions,
                                      hit_probabilities=probabilities),
        }


def linear_chase_ev(members: Sequence[ChaseCandidate], *, pull_counts: np.ndarray,
                    pack_count: int, prices_by_entity: Mapping[int, float]) -> float:
    """Chase EV under an ARBITRARY price vector, with no simulation.

    ``E[total qualifying value per pack] = sum_i E[copies of i per pack] * V_i``
    and expected copies is a property of the draws, not of prices. This is what
    makes multi-date temporal analysis affordable.
    """
    return float(sum(
        (float(pull_counts[member.entity_id]) / pack_count)
        * float(prices_by_entity.get(member.entity_id, member.price))
        for member in members
    ))


def _membership(members: Sequence[ChaseCandidate]) -> List[int]:
    return sorted(member.entity_id for member in members)


def evaluate_systems(
    *,
    eligible: Sequence[ChaseCandidate],
    pack_cost: Optional[float],
    cache: _EconomicsCache,
    systems: Sequence[TierSystem],
) -> List[Dict[str, Any]]:
    """Core, Extended and Core+Extended economics for every candidate system."""
    results: List[Dict[str, Any]] = []
    for system in systems:
        applied = system.apply(eligible, pack_cost)
        core, extended = applied["core"], applied["extended"]
        core_economics = cache.economics(core)
        union_economics = cache.economics(extended)
        results.append({
            "systemKey": system.key,
            "describe": system.describe,
            "coreRule": system.core.key,
            "extendedRule": system.extended.key,
            "nestingViolations": applied["nestingViolations"],
            "coreCount": len(core),
            "extendedTotalCount": len(extended),
            "extendedOnlyCount": len(applied["extendedOnly"]),
            "coreMembership": _membership(core),
            "extendedMembership": _membership(extended),
            "coreCards": [
                {"cardName": c.card_name, "cardNumber": c.card_number,
                 "cardVariantId": c.card_variant_id, "marketPrice": c.price}
                for c in core
            ],
            "extendedOnlyCards": [
                {"cardName": c.card_name, "cardNumber": c.card_number,
                 "cardVariantId": c.card_variant_id, "marketPrice": c.price}
                for c in applied["extendedOnly"]
            ],
            "core": core_economics,
            "coreAndExtended": union_economics,
            "boundary": {
                "coreMinimumValue": min((c.price for c in core), default=None),
                "highestExcludedFromCore": next(
                    (c.price for c in ordered(eligible)
                     if c.entity_id not in {m.entity_id for m in core}), None),
                "extendedMinimumValue": min((c.price for c in extended), default=None),
                "highestExcludedFromExtended": next(
                    (c.price for c in ordered(eligible)
                     if c.entity_id not in {m.entity_id for m in extended}), None),
            },
        })
    return results


def evaluate_single_rules(
    *,
    eligible: Sequence[ChaseCandidate],
    pack_cost: Optional[float],
    cache: _EconomicsCache,
) -> List[Dict[str, Any]]:
    """Phase 3/4/6/7 single-tier grid, with full economics for each rule."""
    rows: List[Dict[str, Any]] = []
    ranked = ordered(eligible)
    for rule in candidate_rules():
        members = rule.select(eligible, pack_cost)
        economics = cache.economics(members)
        chosen = {m.entity_id for m in members}
        rows.append({
            "family": rule.family,
            "ruleKey": rule.key,
            "describe": rule.describe,
            "parameters": rule.parameters,
            "selectedK": len(members),
            "selectedFraction": (round(len(members) / len(ranked), 6)
                                 if ranked else None),
            "membership": _membership(members),
            "minimumQualifyingValue": min((m.price for m in members), default=None),
            "maximumExcludedValue": next(
                (c.price for c in ranked if c.entity_id not in chosen), None),
            "economics": economics,
        })
    return rows


def price_shock_stability(
    *,
    eligible: Sequence[ChaseCandidate],
    pack_cost: Optional[float],
    systems: Sequence[TierSystem],
    seed_base: int,
) -> Dict[str, Any]:
    """Membership churn under independent, joint and pack-cost shocks.

    Membership is the right thing to measure exhaustively here: it is free to
    recompute, and every downstream metric is a deterministic function of it.
    A rule whose membership does not move cannot have unstable economics.
    """
    baseline = {}
    for system in systems:
        applied = system.apply(eligible, pack_cost)
        baseline[system.key] = {
            "core": _membership(applied["core"]),
            "extended": _membership(applied["extended"]),
        }

    def summarise(trials: Dict[str, Dict[str, List[float]]]) -> Dict[str, Any]:
        return {
            key: {
                "coreJaccardMean": (round(float(np.mean(values["core"])), 6)
                                    if values["core"] else None),
                "coreJaccardMin": (round(float(np.min(values["core"])), 6)
                                   if values["core"] else None),
                "extendedJaccardMean": (round(float(np.mean(values["extended"])), 6)
                                        if values["extended"] else None),
                "coreKMin": min(values["coreK"]) if values["coreK"] else None,
                "coreKMax": max(values["coreK"]) if values["coreK"] else None,
                "coreMigrationsMean": (round(float(np.mean(values["migrations"])), 6)
                                       if values["migrations"] else None),
            }
            for key, values in trials.items()
        }

    def run(magnitudes: Sequence[float], *, joint: bool,
            shock_cost: bool = False) -> Dict[str, Any]:
        out: Dict[str, Any] = {}
        for magnitude in magnitudes:
            trials: Dict[str, Dict[str, List[float]]] = {
                system.key: {"core": [], "extended": [], "coreK": [], "migrations": []}
                for system in systems
            }
            for trial in range(SHOCK_TRIALS):
                seed = seed_base + int(magnitude * 1000) * 100 + trial
                if shock_cost:
                    rng = np.random.default_rng(seed)
                    factor = 1.0 + float(rng.uniform(-magnitude, magnitude))
                    cards, cost = list(eligible), (pack_cost or 0) * factor
                else:
                    cards = shocked_cards(eligible, magnitude=magnitude,
                                          seed=seed, joint=joint)
                    cost = pack_cost
                for system in systems:
                    applied = system.apply(cards, cost)
                    core_ids = _membership(applied["core"])
                    base = baseline[system.key]
                    trials[system.key]["core"].append(jaccard(base["core"], core_ids) or 0.0)
                    trials[system.key]["extended"].append(
                        jaccard(base["extended"], _membership(applied["extended"])) or 0.0)
                    trials[system.key]["coreK"].append(len(core_ids))
                    # Cards that left Core but stayed in Extended, or vice versa.
                    trials[system.key]["migrations"].append(
                        len(set(base["core"]) ^ set(core_ids)))
            out[f"{int(magnitude * 100)}pct"] = summarise(trials)
        return out

    return {
        "trialsPerMagnitude": SHOCK_TRIALS,
        "independentPriceShock": run(SHOCK_MAGNITUDES, joint=False),
        "jointPriceShock": run(JOINT_SHOCK_MAGNITUDES, joint=True),
        "packCostShock": run(PACK_COST_SHOCKS, joint=False, shock_cost=True),
    }


def analyse_set_stage4(
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
    historical_prices: Optional[Mapping[str, Mapping[str, float]]] = None,
) -> Dict[str, Any]:
    """One set: eligible universe, single-rule grid, tier systems, stability."""
    run = simulate_set(config=config, dataframe=dataframe,
                       calculation_run_id=calculation_run_id,
                       canonical_key=canonical_key, pack_count=pack_count)
    decomposition = run["decomposition"]
    raw_identities = entity_identities(decomposition, run["dataframe"])
    identities, ambiguous = drop_ambiguous_identities(raw_identities)
    eligible, excluded = partition_universe(identities, market_date=market_date)
    prices = decomposition.price_vector()
    pull_counts = decomposition.pull_counts()

    cache = _EconomicsCache(decomposition, prices, run["values"], pack_cost, pack_count)
    systems = candidate_systems()

    single_rules = evaluate_single_rules(eligible=eligible, pack_cost=pack_cost,
                                         cache=cache)
    tier_systems = evaluate_systems(eligible=eligible, pack_cost=pack_cost,
                                    cache=cache, systems=systems)
    stability = price_shock_stability(eligible=eligible, pack_cost=pack_cost,
                                      systems=systems,
                                      seed_base=run["seed"] % 100_000)

    temporal = None
    if historical_prices:
        temporal = temporal_stability(
            eligible=eligible, pack_cost=pack_cost, systems=systems,
            historical_prices=historical_prices, pull_counts=pull_counts,
            pack_count=pack_count)

    ranked = ordered(eligible)
    return {
        "setId": set_id,
        "setName": set_name,
        "canonicalKey": canonical_key,
        "calculationRunId": calculation_run_id,
        "marketDate": market_date,
        "researchVersion": SET_CHASE_EFFICIENCY_RESEARCH_VERSION,
        "stage": STAGE4_VERSION,
        "simulation": {
            "seed": run["seed"], "packCount": run["packCount"],
            "simulationSeconds": run["simulationSeconds"],
            "decompositionMaxAbsError": run["decompositionMaxAbsError"],
            "simulatedMeanPackValue": run["simulatedMeanPackValue"],
            "economicsEvaluations": cache.evaluations,
            "economicsCacheHits": cache.cache_hits,
        },
        "acquisitionCost": {"packEquivalentCost": pack_cost, **dict(pack_cost_basis)},
        "universe": {
            "drawablePrintings": len(raw_identities),
            "eligiblePrintings": len(eligible),
            "excludedPrintings": len(excluded) + len(ambiguous),
            "excludedByReason": dict(sorted(Counter(
                [r["reason"] for r in excluded] + [r["reason"] for r in ambiguous]).items())),
            "ambiguousIdentities": ambiguous,
            "distinctIdentities": len({(set_id, c.card_variant_id) for c in eligible}),
            "topPrices": [round(c.price, 2) for c in ranked[:25]],
            "medianPrice": (round(float(np.median([c.price for c in ranked])), 4)
                            if ranked else None),
            "upperQuartilePrice": (round(float(np.quantile([c.price for c in ranked], 0.75)), 4)
                                   if ranked else None),
        },
        "singleRules": single_rules,
        "tierSystems": tier_systems,
        "priceShockStability": stability,
        "temporalStability": temporal,
    }


def temporal_stability(
    *,
    eligible: Sequence[ChaseCandidate],
    pack_cost: Optional[float],
    systems: Sequence[TierSystem],
    historical_prices: Mapping[str, Mapping[str, float]],
    pull_counts: np.ndarray,
    pack_count: int,
) -> Dict[str, Any]:
    """Apply each tier system at every historical market date.

    Membership turnover, Core<->Extended transitions and Jaccard through time.
    Chase EV is recomputed via the linear identity, so no re-simulation is
    needed; any-hit probability is NOT recomputed here and is reported as a
    known limitation rather than approximated.
    """
    dates = sorted(historical_prices)
    if len(dates) < 2:
        return {"status": "INSUFFICIENT_HISTORY", "dates": len(dates)}

    by_variant = {c.card_variant_id: c for c in eligible}
    per_system: Dict[str, Any] = {}
    for system in systems:
        memberships: List[Tuple[str, List[int], List[int]]] = []
        ev_series: List[Optional[float]] = []
        for date in dates:
            prices = historical_prices[date]
            repriced = [
                ChaseCandidate(
                    entity_id=c.entity_id, card_variant_id=c.card_variant_id,
                    card_id=c.card_id, card_name=c.card_name,
                    card_number=c.card_number, printing_type=c.printing_type,
                    rarity_key=c.rarity_key,
                    price=float(prices.get(c.card_variant_id, c.price)),
                    price_captured_at=date, price_source=c.price_source,
                    pull_count=c.pull_count)
                for c in eligible
            ]
            applied = system.apply(repriced, pack_cost)
            memberships.append((date, _membership(applied["core"]),
                                _membership(applied["extended"])))
            prices_by_entity = {c.entity_id: c.price for c in repriced}
            ev = linear_chase_ev(applied["extended"], pull_counts=pull_counts,
                                 pack_count=pack_count,
                                 prices_by_entity=prices_by_entity)
            ev_series.append(round(ev / pack_cost, 6) if pack_cost else None)

        core_jaccards, extended_jaccards = [], []
        core_to_extended, extended_to_non = 0, 0
        for (_, core_a, ext_a), (_, core_b, ext_b) in zip(memberships, memberships[1:]):
            core_jaccards.append(jaccard(core_a, core_b) or 0.0)
            extended_jaccards.append(jaccard(ext_a, ext_b) or 0.0)
            # Demoted out of Core but still inside Extended on the next date.
            core_to_extended += len((set(core_a) - set(core_b)) & set(ext_b))
            extended_to_non += len(set(ext_a) - set(ext_b))
        first_core, last_core = memberships[0][1], memberships[-1][1]
        usable_ev = [value for value in ev_series if value is not None]
        per_system[system.key] = {
            "dates": len(dates),
            "coreKFirst": len(first_core),
            "coreKLast": len(last_core),
            "coreKMin": min(len(row[1]) for row in memberships),
            "coreKMax": max(len(row[1]) for row in memberships),
            "consecutiveCoreJaccardMean": round(float(np.mean(core_jaccards)), 6),
            "consecutiveCoreJaccardMin": round(float(np.min(core_jaccards)), 6),
            "consecutiveExtendedJaccardMean": round(float(np.mean(extended_jaccards)), 6),
            "endpointCoreJaccard": jaccard(first_core, last_core),
            "coreToExtendedTransitions": core_to_extended,
            "extendedToNonChaseTransitions": extended_to_non,
            "chaseEvReturnFirst": ev_series[0],
            "chaseEvReturnLast": ev_series[-1],
            "chaseEvReturnMin": min(usable_ev) if usable_ev else None,
            "chaseEvReturnMax": max(usable_ev) if usable_ev else None,
        }
    return {
        "status": "SCORED",
        "dateCount": len(dates),
        "firstDate": dates[0],
        "lastDate": dates[-1],
        "limitation": (
            "Any-hit probability and Beat-the-Buy are NOT recomputed per date: "
            "they require a pass over the pack draws per membership set. Chase EV "
            "Return is exact via the linear identity."
        ),
        "systems": per_system,
    }
