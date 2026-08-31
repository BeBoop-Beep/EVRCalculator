"""Stage V-C per-set orchestration: one decomposition, many products.

RESEARCH ONLY.

THE CONTROLLED-COMPARISON ARCHITECTURE
--------------------------------------
A set is simulated exactly ONCE, with ``PackDecompositionRecorder`` attached.
Every product belonging to that set is then evaluated against those SAME
recorded pack paths. Nothing is re-simulated per product.

That is not merely an optimisation. If each product were simulated separately,
two products with identical economics would differ by Monte Carlo noise, and the
Phase-17 pathological tests ("identical cost per pack, 1 pack vs 36 packs must
show identical per-pack economics") could not be stated as exact identities.
Holding the pack paths fixed means the ONLY thing that varies between two
products of one set is what Stage V-C claims varies: their acquisition cost, and
therefore their tier membership and their product construction.

WHAT IS INHERITED, AND WHAT IS NOT
----------------------------------
Inherited from Stages I-IV, unchanged: the simulator, the decomposition
recorder, the entity-identity contract, the eligibility exclusions, and every
per-pack statistic.

NOT inherited: the chase universe. Each product derives its own Core and
Extended baskets from its own pack-equivalent cost. Set-level inheritance is the
error this stage exists to eliminate, and there is no code path here that can
apply one set-wide basket to several products.
"""

from __future__ import annotations

from collections import defaultdict
from typing import Any, Dict, List, Mapping, Optional, Sequence

import numpy as np

from backend.research.product_chase_economics import contract as tier_contract
from backend.research.product_chase_economics.metrics import (
    accessibility,
    aggregate_to_product,
    product_chase_ev,
    whole_product_journey,
)
from backend.research.product_chase_economics.version import (
    PRODUCT_CHASE_ECONOMICS_VERSION,
)
from backend.research.set_chase_efficiency.chase_metrics import (
    beat_the_buy,
    chase_cost_gap,
    chase_ev,
)
from backend.research.set_chase_efficiency.metrics import (
    binomial_standard_error,
    concentration,
    conditional_value_statistics,
    hit_count_distribution,
)
from backend.research.set_chase_efficiency.runner import (
    _basket_vectors,
    entity_identities,
    simulate_set,
)
from backend.research.set_chase_efficiency.baskets import partition_universe


def _skew_days(product_date: Any, card_date: Any) -> Optional[int]:
    """Whole days between the product-cost date and the card-price date."""
    from datetime import date
    try:
        a = date.fromisoformat(str(product_date)[:10])
        b = date.fromisoformat(str(card_date)[:10])
    except (TypeError, ValueError):
        return None
    return abs((b - a).days)


def _structural(members: Sequence[Any], pull_counts: Any) -> Dict[str, Any]:
    """Literal count plus both concentration views.

    Two different HHIs are kept because they answer different questions and
    Stage IV required both to be published:

    * VALUE concentration weights each member by its price alone - how top-heavy
      is the chase *list*.
    * CHASE-EV concentration weights by total value actually delivered across
      the run (pull count x price) - how top-heavy is the chase *experience*.
      Its effective count is what the programme calls **Chase Depth**.
    """
    prices = [float(m.price) for m in members]
    delivered = [float(pull_counts[m.entity_id]) * float(m.price) for m in members]
    value_block = concentration(prices)
    ev_block = concentration(delivered)
    return {
        "literalChaseCount": len(members),
        "valueConcentration": value_block,
        "effectiveValueCount": value_block.get("effectiveChaseCount"),
        "chaseEvConcentration": ev_block,
        "chaseDepth": ev_block.get("effectiveChaseCount"),
    }


def evaluate_product_basket(*, decomposition: Any, prices: np.ndarray,
                            entities: Sequence[Any], entity_ids: Sequence[int],
                            pack_cost: float, product_cost: float,
                            random_pack_count: int, full_pack_values: np.ndarray,
                            pack_independent: bool) -> Dict[str, Any]:
    """Every Stage V-C statistic for ONE product-specific basket."""
    if not entity_ids:
        # Phase 17 case G. An empty Core is a legal economic verdict - "no card
        # in this set is worth three packs OF THIS PRODUCT" - and is reported as
        # a measured zero, never as missing data.
        return {
            "supported": True,
            "empty": True,
            "literalChaseCount": 0,
            "chaseDepth": None,
            "packProbability": 0.0,
            "productProbability": {"supported": True, "probabilityAtLeastOne": 0.0,
                                   "assumption": "model_consistent_iid"},
            "reason": "no card qualifies at this product's cost",
        }

    counts, totals, best = _basket_vectors(decomposition, entity_ids, prices)
    distribution = hit_count_distribution(counts)
    p_pack = distribution["pAtLeastOne"]
    qualified = counts > 0

    ev = chase_ev(qualifying_totals=totals, pack_cost=pack_cost,
                  full_pack_values=full_pack_values)
    product_ev = product_chase_ev(
        pack_chase_ev=ev.get("chaseEv"), random_pack_count=random_pack_count,
        product_cost=product_cost, full_pack_ev=ev.get("fullPackEv"))
    product_probability = aggregate_to_product(
        pack_probability=p_pack, random_pack_count=random_pack_count,
        pack_independent=pack_independent)

    return {
        "supported": True,
        "empty": False,
        "reason": None,
        **_structural(entities, decomposition.pull_counts()),
        "packProbability": p_pack,
        "packProbabilityStandardError": binomial_standard_error(p_pack, distribution["packs"]),
        "hitCountDistribution": distribution,
        "productProbability": product_probability,
        "conditionalValueTotal": conditional_value_statistics(totals[qualified]),
        "conditionalValueBest": conditional_value_statistics(best[qualified]),
        "chaseEv": ev,
        "productChaseEv": product_ev,
        "accessibility": accessibility(
            pack_probability=p_pack,
            product_probability=product_probability.get("probabilityAtLeastOne"),
            pack_cost=pack_cost, product_cost=product_cost,
            random_pack_count=random_pack_count),
        "costGapPackGranular": chase_cost_gap(
            qualifying=qualified, chase_values=totals, pack_cost=pack_cost),
        "costGapWholeProduct": whole_product_journey(
            qualifying=qualified, chase_values=totals,
            product_cost=product_cost, random_pack_count=random_pack_count),
        "beatTheBuyPackGranular": beat_the_buy(
            qualifying=qualified, chase_values=totals,
            probability=p_pack, pack_cost=pack_cost),
    }


def analyse_set_products(*, config: Any, dataframe: Any, set_id: str,
                         set_name: Optional[str], canonical_key: str,
                         calculation_run_id: str, market_date: str,
                         products: Sequence[Mapping[str, Any]],
                         pack_count: int,
                         price_basis_date: Optional[str] = None) -> Dict[str, Any]:
    """One set simulated once; every one of its products scored natively.

    ``market_date`` dates the PRODUCT costs (the authoritative run's
    ``price_as_of``). ``price_basis_date`` dates the CARD prices the simulator
    was fed. They are usually the same day and are kept separate because they
    are not guaranteed to be: card prices are re-scraped continuously while a
    run's product costs are fixed at the moment it executed. Judging card
    eligibility against the product date would then exclude the entire universe.
    Both dates are reported on the artifact so any skew is visible rather than
    silently absorbed.
    """
    run = simulate_set(config=config, dataframe=dataframe,
                       calculation_run_id=calculation_run_id,
                       canonical_key=canonical_key, pack_count=pack_count)
    decomposition = run["decomposition"]
    identities = entity_identities(decomposition, run["dataframe"])
    basis_day = str(price_basis_date or market_date)[:10]
    eligible, excluded = partition_universe(identities, market_date=basis_day)
    prices = decomposition.price_vector()
    full_pack_values = decomposition.pack_values(prices)

    exclusion_counts: Dict[str, int] = defaultdict(int)
    for row in excluded:
        exclusion_counts[row["reason"]] += 1
    excluded_prices = [float(r.get("price") or 0.0) for r in excluded]

    scored: List[Dict[str, Any]] = []
    unsupported: List[Dict[str, Any]] = []
    for product in products:
        pack_cost = tier_contract.pack_equivalent_cost(
            product_market_cost=product.get("product_market_cost"),
            random_pack_count=product.get("random_pack_count"))
        reason = None
        if tier_contract.finite_positive(product.get("product_market_cost")) is None:
            reason = "no_product_market_cost"
        elif tier_contract.finite_positive(product.get("random_pack_count")) is None:
            reason = "no_random_pack_count"
        elif not (product.get("composition_id") or product.get("composition_version")
                  or product.get("stage1_all_random")):
            reason = "unverified_composition"
        elif pack_cost is None:
            reason = "no_random_pack_count"
        if reason is not None:
            unsupported.append({
                "sealedProductId": product.get("sealed_product_id"),
                "productName": product.get("product_name"),
                "productFamily": product.get("product_family"),
                "reason": reason,
                "reasonText": tier_contract.PRODUCT_EXCLUSION_REASONS[reason],
            })
            continue

        pack_independent = bool(product.get("pack_independence_assumption", True))
        basket = tier_contract.product_basket(eligible, pack_cost)
        core_entities = [e for e in eligible if int(e.entity_id) in set(basket["coreEntityIds"])]
        ext_entities = [e for e in eligible if int(e.entity_id) in set(basket["extendedEntityIds"])]
        product_cost = float(product["product_market_cost"])
        n_packs = int(round(float(product["random_pack_count"])))

        scored.append({
            "sealedProductId": product.get("sealed_product_id"),
            "productName": product.get("product_name"),
            "productFamily": product.get("product_family"),
            "productMarketCost": product_cost,
            "randomPackCount": n_packs,
            "packIndependenceAssumption": pack_independent,
            "tierContract": {
                "packEquivalentCost": basket["packEquivalentCost"],
                "coreMultiple": tier_contract.CORE_MULTIPLE,
                "extendedMultiple": tier_contract.EXTENDED_MULTIPLE,
                "coreThreshold": basket["coreThreshold"],
                "extendedThreshold": basket["extendedThreshold"],
            },
            "membership": {
                "coreCount": basket["coreCount"],
                "extendedCount": basket["extendedCount"],
                "coreCardVariantIds": basket["coreCardVariantIds"],
                "extendedCardVariantIds": basket["extendedCardVariantIds"],
                "corePrices": basket["corePrices"][:25],
            },
            "core": evaluate_product_basket(
                decomposition=decomposition, prices=prices, entities=core_entities,
                entity_ids=basket["coreEntityIds"], pack_cost=basket["packEquivalentCost"],
                product_cost=product_cost, random_pack_count=n_packs,
                full_pack_values=full_pack_values, pack_independent=pack_independent),
            "coreAndExtended": evaluate_product_basket(
                decomposition=decomposition, prices=prices, entities=ext_entities,
                entity_ids=basket["extendedEntityIds"], pack_cost=basket["packEquivalentCost"],
                product_cost=product_cost, random_pack_count=n_packs,
                full_pack_values=full_pack_values, pack_independent=pack_independent),
        })

    return {
        "setId": set_id,
        "setName": set_name,
        "canonicalKey": canonical_key,
        "calculationRunId": calculation_run_id,
        "marketDate": market_date,
        "cardPriceBasisDate": basis_day,
        "priceBasisSkewDays": _skew_days(market_date, basis_day),
        "researchVersion": PRODUCT_CHASE_ECONOMICS_VERSION,
        "simulation": {"seed": run["seed"], "packCount": run["packCount"],
                       "entityCount": decomposition.entity_count},
        "universe": {
            "drawablePrintings": len(identities),
            "eligiblePrintings": len(eligible),
            "excludedPrintings": len(excluded),
            "excludedByReason": dict(exclusion_counts),
            "highestExcludedValue": max(excluded_prices) if excluded_prices else None,
            "distinctEligibleIdentities": len({e.card_variant_id for e in eligible}),
        },
        "products": scored,
        "unsupportedProducts": unsupported,
    }
