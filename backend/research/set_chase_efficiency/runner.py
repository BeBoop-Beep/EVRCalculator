"""Per-set Set Chase Efficiency research run.

WHAT THIS DOES, ONCE PER SET
----------------------------
1. Rebuilds the authoritative simulation inputs through the SAME services the
   production run uses (``_resolve_set_config`` + ``EVRInputPreparationService``),
   so this is not a second opinion about what the inputs were.
2. Re-simulates the set with ``PackDecompositionRecorder`` attached. The
   recorder is strictly observational: it consumes no randomness and changes no
   sampling decision (``test_recorder_does_not_perturb_sampling``).
3. Derives EVERY basket's probability, conditional value and concentration from
   that ONE decomposition. Nothing is re-simulated per basket, and no basket
   probability is ever assembled from per-card odds.

WHY RE-SIMULATE AT ALL
----------------------
The authoritative run stores per-card marginals
(``simulation_card_variant_pull_rates``) and per-pack TOTALS
(``simulation_pack_outcome_artifacts``) but never which cards shared a pack.
P(at least one of a basket) is not recoverable from marginals: several chase
cards compete for the same slot, so their per-pack hit events are negatively
dependent and summing or independence-combining the marginals is wrong in a
direction that grows with basket size. The joint is only observable by watching
packs, so packs are watched.

WHAT THIS IS NOT
----------------
Not production. Nothing here writes to a production table, changes a score, or
is read by an API. An independent seeded sample from the authoritative model is
not the authoritative run, and its mean is not the published mean.
"""

from __future__ import annotations

import hashlib
import time
from collections import Counter, defaultdict
from typing import Any, Dict, List, Mapping, Optional, Sequence, Tuple

import numpy as np

from .baskets import Basket, build_baskets, partition_universe
from .metrics import (
    binomial_standard_error,
    chase_efficiency,
    concentration,
    conditional_value_statistics,
    hit_count_distribution,
    horizon_block,
)
from .version import (
    SET_CHASE_EFFICIENCY_CALCULATION_VERSION,
    SET_CHASE_EFFICIENCY_PROBABILITY_SOURCE,
    SET_CHASE_EFFICIENCY_RESEARCH_VERSION,
)

BASE_PRICE_COLUMN = "Price ($)"
REVERSE_PRICE_COLUMN = "Reverse Variant Price ($)"

#: Packs simulated per set. 1,000,000 matches the authoritative run's own
#: sample size, which keeps the Monte Carlo error on a Top-1 basket (often
#: p ~ 1/1500) at a level the study can report honestly rather than one it has
#: to apologise for.
DEFAULT_PACK_COUNT = 1_000_000


def research_seed(parts: Sequence[Any]) -> int:
    """Deterministic seed from the run's identity.

    The same authoritative run re-simulates to the same vector forever, so a
    frontier is reproducible rather than merely repeatable-ish.
    """
    payload = "|".join(str(part) for part in parts).encode("utf-8")
    return int.from_bytes(hashlib.sha256(payload).digest()[:8], "big") % (2 ** 63)


def _text(value: Any) -> Optional[str]:
    if value is None:
        return None
    try:
        if value != value:  # NaN
            return None
    except Exception:  # pragma: no cover - non-comparable objects
        pass
    text = str(value).strip()
    return text or None


def entity_identities(decomposition: Any, dataframe: Any) -> List[Dict[str, Any]]:
    """Attach tradeable card identity to every sampling entity.

    The recorder deliberately knows nothing about variants; it keys entities by
    ``(source_row_index, price_column)``. That pair IS the exact printing: the
    base price column is the card's own variant, the reverse column is its
    reverse-holo variant, and they carry different prices and different
    identifiers. This mapping is the same one
    ``VariantPullSummaryRecorder`` performs inside the production run.
    """
    rows: Dict[int, Dict[str, Any]] = {}
    for index, row in dataframe.iterrows():
        source = row.get("__source_row_index__", index)
        if source is None:
            continue
        try:
            rows[int(source)] = row.to_dict()
        except (TypeError, ValueError):
            continue

    pull_counts = decomposition.pull_counts()
    identities: List[Dict[str, Any]] = []
    for entity in decomposition.entities:
        row = rows.get(entity.source_row_index) if entity.source_row_index is not None else None
        row = row or {}
        reverse = entity.price_column == REVERSE_PRICE_COLUMN
        identities.append({
            "entity_id": entity.entity_id,
            "card_variant_id": _text(row.get("reverse_variant_id" if reverse else "card_variant_id")),
            "card_id": _text(row.get("card_id")),
            "card_name": entity.card_name or _text(row.get("Card Name")),
            "card_number": entity.card_number or _text(row.get("Card Number")),
            "printing_type": _text(row.get("reverse_printing_type" if reverse else "printing_type")),
            "rarity_key": entity.rarity_key,
            "price_column": entity.price_column,
            "price": float(entity.price),
            "price_source": _text(row.get("reverse_price_source" if reverse else "price_source")),
            "price_captured_at": _text(row.get("reverse_captured_at" if reverse else "captured_at")),
            "pull_count": int(pull_counts[entity.entity_id]),
        })
    return identities


def _basket_vectors(decomposition: Any, entity_ids: Sequence[int],
                    prices: np.ndarray) -> Tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Per-pack (qualifying copies, qualifying total value, best qualifying value).

    All three are produced by re-valuing the SAME recorded draw sequence under a
    masked price vector, so they cannot disagree with each other or with the
    presence indicator. Counting is just re-valuation with every qualifying card
    priced at 1.
    """
    mask = np.zeros(decomposition.entity_count, dtype=bool)
    if len(entity_ids):
        mask[np.asarray(entity_ids, dtype=np.int64)] = True
    masked_prices = np.where(mask, prices, 0.0)
    counts = decomposition.pack_values(mask.astype(np.float64))
    totals = decomposition.pack_values(masked_prices)
    best = decomposition.pack_max_entity_value(masked_prices)
    return np.rint(counts).astype(np.int64), totals, best


def evaluate_basket(
    *,
    decomposition: Any,
    prices: np.ndarray,
    basket: Basket,
    pack_cost: Optional[float],
) -> Dict[str, Any]:
    """Everything Stage I asks of one (set x basket) pair.

    Three conditional value interpretations are kept, not one, because an
    opening can contain more than one qualifying chase and they answer
    different questions:

    * ``total``  - the whole qualifying haul. What the chaser walks away with.
    * ``best``   - the single best qualifying card. What they were chasing.
    * ``count``  - how many qualified, kept so neither of the above hides it.
    """
    payload: Dict[str, Any] = basket.as_payload()
    if not basket.supported or not basket.members:
        payload.update({
            "probabilityAtLeastOne": None,
            "excludedFromScoring": True,
            "excludedReason": basket.unsupported_reason or "empty basket",
        })
        return payload

    counts, totals, best = _basket_vectors(decomposition, basket.entity_ids, prices)
    distribution = hit_count_distribution(counts)
    p_s = distribution["pAtLeastOne"]
    qualified = counts > 0

    conditional_total = conditional_value_statistics(totals[qualified])
    conditional_best = conditional_value_statistics(best[qualified])
    conditional_count = conditional_value_statistics(counts[qualified].astype(np.float64))

    pull_counts = decomposition.pull_counts()
    member_contribution = [
        float(pull_counts[member.entity_id]) * member.price
        for member in basket.members
    ]

    def ce(value: Optional[float]) -> Optional[float]:
        return chase_efficiency(conditional_value=value, pack_cost=pack_cost, probability=p_s)

    expected_packs_per_hit = None
    if p_s:
        expected_packs_per_hit = round(1.0 / p_s, 12)

    payload.update({
        "probabilityAtLeastOne": p_s,
        "probabilityStandardError": binomial_standard_error(p_s, distribution["packs"]),
        "hitCountDistribution": distribution,
        "expectedPacksPerQualifyingChase": expected_packs_per_hit,
        "conditionalValueTotal": conditional_total,
        "conditionalValueBest": conditional_best,
        "conditionalQualifyingCount": conditional_count,
        "acquisitionCostPerPack": pack_cost,
        "chaseEfficiency": {
            "meanTotal": ce(conditional_total["mean"]),
            "medianTotal": ce(conditional_total["median"]),
            "winsorizedMeanTotal": ce(conditional_total["winsorizedMean"]),
            "trimmedMeanTotal": ce(conditional_total["trimmedMean"]),
            "meanBest": ce(conditional_best["mean"]),
            "medianBest": ce(conditional_best["median"]),
        },
        "horizons": horizon_block(p_s, pack_cost),
        "concentration": concentration(member_contribution),
        "members": [
            {**member.as_payload(), "totalValueDelivered": round(contribution, 12)}
            for member, contribution in zip(basket.members, member_contribution)
        ],
        "excludedFromScoring": False,
        "excludedReason": None,
    })
    return payload


def simulate_set(
    *,
    config: Any,
    dataframe: Any,
    calculation_run_id: str,
    canonical_key: str,
    pack_count: int = DEFAULT_PACK_COUNT,
) -> Dict[str, Any]:
    """Run the authoritative V2 model once with the decomposition recorder on."""
    from backend.research.ev_representativeness.recorder import PackDecompositionRecorder
    from backend.simulations.monteCarloSimV2 import (
        make_simulate_pack_fn_v2,
        validate_pack_state_model,
    )
    from backend.simulations.utils.extractScarletAndVioletCardGroups import (
        extract_scarletandviolet_card_groups,
    )

    started = time.perf_counter()
    simulation_input = dataframe.copy()
    if "__source_row_index__" not in simulation_input.columns:
        simulation_input["__source_row_index__"] = simulation_input.index
    card_groups = extract_scarletandviolet_card_groups(config, simulation_input)
    validate_pack_state_model(config, card_groups)

    seed = research_seed([
        SET_CHASE_EFFICIENCY_RESEARCH_VERSION, calculation_run_id, canonical_key, pack_count,
    ])
    rng = np.random.default_rng(seed)
    recorder = PackDecompositionRecorder(expected_packs=pack_count)
    rarity_pull_counts: Dict[str, int] = defaultdict(int)
    rarity_value_totals: Dict[str, float] = defaultdict(float)

    simulate_one_pack = make_simulate_pack_fn_v2(
        common_cards=card_groups["common"],
        uncommon_cards=card_groups["uncommon"],
        rare_cards=card_groups["rare"],
        hit_cards=card_groups["hit"],
        reverse_pool=card_groups["reverse"],
        slots_per_rarity=config.SLOTS_PER_RARITY,
        config=config,
        df=simulation_input,
        rarity_pull_counts=rarity_pull_counts,
        rarity_value_totals=rarity_value_totals,
        pack_logs=None,
        rng=rng,
        research_recorder=recorder,
    )

    values = np.empty(pack_count, dtype=np.float64)
    for index in range(pack_count):
        values[index] = float(simulate_one_pack())
    decomposition = recorder.finalize()

    # COMPLETENESS GATE. A recorder that missed draws would understate every
    # basket probability with no other symptom, so this is checked before any
    # basket is evaluated rather than after.
    rebuilt = decomposition.pack_values()
    max_error = float(np.max(np.abs(rebuilt - values))) if values.size else 0.0
    if max_error > 1e-6:
        raise RuntimeError(
            f"{canonical_key}: recorded decomposition does not reproduce the simulated "
            f"pack values (max abs error {max_error:.9f}); basket probabilities would be "
            "measured off an incomplete draw record"
        )

    return {
        "decomposition": decomposition,
        "values": values,
        "seed": seed,
        "packCount": pack_count,
        "simulationSeconds": round(time.perf_counter() - started, 3),
        "decompositionMaxAbsError": max_error,
        "simulatedMeanPackValue": round(float(values.mean()), 6),
        "dataframe": simulation_input,
    }


def analyse_set(
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
    """One complete set-level Stage-I result, raw components and all."""
    run = simulate_set(
        config=config, dataframe=dataframe, calculation_run_id=calculation_run_id,
        canonical_key=canonical_key, pack_count=pack_count,
    )
    decomposition = run["decomposition"]
    identities = entity_identities(decomposition, run["dataframe"])
    eligible, excluded = partition_universe(identities, market_date=market_date)
    prices = decomposition.price_vector()

    baskets = build_baskets(eligible, pack_cost=pack_cost)
    evaluated = [
        evaluate_basket(decomposition=decomposition, prices=prices, basket=basket,
                        pack_cost=pack_cost)
        for basket in baskets
    ]

    eligible_prices = sorted((c.price for c in eligible), reverse=True)
    exclusion_counts: Dict[str, int] = defaultdict(int)
    for row in excluded:
        exclusion_counts[row["reason"]] += 1

    return {
        "setId": set_id,
        "setName": set_name,
        "canonicalKey": canonical_key,
        "calculationRunId": calculation_run_id,
        "marketDate": market_date,
        "researchVersion": SET_CHASE_EFFICIENCY_RESEARCH_VERSION,
        "calculationVersion": SET_CHASE_EFFICIENCY_CALCULATION_VERSION,
        "probabilitySource": SET_CHASE_EFFICIENCY_PROBABILITY_SOURCE,
        "simulation": {
            "seed": run["seed"],
            "packCount": run["packCount"],
            "simulationSeconds": run["simulationSeconds"],
            "decompositionMaxAbsError": run["decompositionMaxAbsError"],
            "simulatedMeanPackValue": run["simulatedMeanPackValue"],
        },
        "acquisitionCost": {
            "packEquivalentCost": pack_cost,
            **dict(pack_cost_basis),
        },
        "coverage": {
            "drawableEntities": len(identities),
            "eligibleChaseUniverse": len(eligible),
            "excludedEntities": len(excluded),
            "excludedByReason": dict(sorted(exclusion_counts.items())),
            "eligiblePriceMax": eligible_prices[0] if eligible_prices else None,
            "eligiblePriceMedian": (
                float(np.median(eligible_prices)) if eligible_prices else None
            ),
            "eligiblePriceMin": eligible_prices[-1] if eligible_prices else None,
            "eligibleAtOrAbove": {
                str(int(t)): sum(1 for p in eligible_prices if p >= t)
                for t in (5, 10, 20, 30, 50, 100, 200, 500)
            },
            "priceCaptureDates": dict(sorted(
                Counter(c.price_captured_at for c in eligible).items(),
                key=lambda item: str(item[0]),
            )),
        },
        "excludedEntities": excluded,
        "baskets": evaluated,
    }
