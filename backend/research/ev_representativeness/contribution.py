"""Parts 6-10: who actually generates the EV.

Three different questions, three different authorities, deliberately not mixed:

  * **Part 8, rarity-level contribution** comes from the ALREADY PERSISTED
    ``simulation_pull_summary``, which the audit verified reconciles to the
    published mean exactly (8.532834580000712 vs 8.53283458 on
    prismaticEvolutions). It is the simulator's own decomposition of the
    authoritative run. Nothing here recomputes it.

  * **Parts 6, 7, 9, 10 - card-level contribution, collective hit frequency,
    economically-meaningful hit frequency** require per-card and per-pack detail
    the authoritative run does not record. They come from a Tier B seeded
    re-simulation via ``PackDecomposition``.

  * **Part 9 additionally gets an independent cross-check** derived from the pack
    state model itself (``collective_hit_probability_from_state_model``), so the
    empirical figure is corroborated by the model that produced it rather than
    standing alone.

WHAT IS NEVER DONE HERE
-----------------------
``P(card) * price`` is never used, and neither is
``simulation_input_cards.ev_contribution``. Both are the ANALYTIC model
``Price / Effective_Pull_Rate``, measured 47% below the simulator's own mean.
They answer a different question and substituting one for the other would put a
number in the "simulator says" column that the simulator does not say.

Collective probabilities are likewise never obtained by summing individual card
odds: the three variable slots are governed by a pack-state distribution with
mutual exclusions and a without-replacement rule, so those events are not
independent and the sum would be wrong in a direction that flatters attainable
rarities.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence, Tuple

import numpy as np

from .recorder import PackDecomposition, SamplingEntity
from .version import ECONOMIC_HIT_COST_MULTIPLES


# ---------------------------------------------------------------------------
# Part 6 / 7 - card-level EV contribution and concentration
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class CardContribution:
    """One sampling entity's measured economic role in the opening."""

    entity_id: int
    source_row_index: Optional[int]
    price_column: str
    card_name: Optional[str]
    card_number: Optional[str]
    rarity_key: str
    price_used: float
    observed_pull_count: int
    expected_copies_per_pack: float
    ev_contribution_per_pack: float
    ev_share: Optional[float]
    ev_rank: int

    def as_payload(self) -> Dict[str, Any]:
        return {
            "entityId": self.entity_id,
            "sourceRowIndex": self.source_row_index,
            "priceColumn": self.price_column,
            "cardName": self.card_name,
            "cardNumber": self.card_number,
            "rarityKey": self.rarity_key,
            "priceUsed": self.price_used,
            "observedPullCount": self.observed_pull_count,
            "expectedCopiesPerPack": self.expected_copies_per_pack,
            "evContributionPerPack": self.ev_contribution_per_pack,
            "evShare": self.ev_share,
            "evRank": self.ev_rank,
        }


@dataclass(frozen=True)
class CardConcentration:
    """Part 7: how few cards the opening economy rests on."""

    card_count: int
    contributing_card_count: int
    total_ev_per_pack: float
    top1_ev_share: Optional[float]
    top5_ev_share: Optional[float]
    top10_ev_share: Optional[float]
    hhi: Optional[float]
    effective_card_count: Optional[float]

    def as_payload(self) -> Dict[str, Any]:
        return {
            "cardCount": self.card_count,
            "contributingCardCount": self.contributing_card_count,
            "totalEvPerPack": self.total_ev_per_pack,
            "top1EvShare": self.top1_ev_share,
            "top5EvShare": self.top5_ev_share,
            "top10EvShare": self.top10_ev_share,
            "hhi": self.hhi,
            "effectiveCardCount": self.effective_card_count,
        }


def compute_card_contributions(
    decomposition: PackDecomposition,
    *,
    prices: Optional[np.ndarray] = None,
) -> List[CardContribution]:
    """Part 6: expected copies per pack and EV contribution, per sampling entity.

    ``expected_copies_per_pack`` is the simulator's own realized frequency -
    total times this entity was drawn, divided by packs opened. It therefore
    already contains the pack-state distribution, the slot structure, the
    without-replacement exclusion and both special-pack entry paths, because it
    is a count of what actually happened rather than a model of what should.

    The identity that makes this trustworthy is checked by the caller:
    ``sum(ev_contribution_per_pack)`` must equal the run's own simulated mean.
    """
    entities = decomposition.entities
    pack_count = decomposition.pack_count
    if pack_count <= 0:
        raise ValueError("decomposition contains no packs")

    counts = decomposition.pull_counts()
    price_vector = (
        decomposition.price_vector() if prices is None else np.asarray(prices, dtype=np.float64)
    )
    if price_vector.size != len(entities):
        raise ValueError("price vector length does not match the registered entity count")

    contributions = counts * price_vector / float(pack_count)
    total = float(contributions.sum())

    order = np.argsort(-contributions, kind="stable")
    rank_by_entity = np.empty(len(entities), dtype=np.int64)
    rank_by_entity[order] = np.arange(1, len(entities) + 1)

    results: List[CardContribution] = []
    for entity in entities:
        index = entity.entity_id
        contribution = float(contributions[index])
        results.append(
            CardContribution(
                entity_id=index,
                source_row_index=entity.source_row_index,
                price_column=entity.price_column,
                card_name=entity.card_name,
                card_number=entity.card_number,
                rarity_key=entity.rarity_key,
                price_used=float(price_vector[index]),
                observed_pull_count=int(counts[index]),
                expected_copies_per_pack=float(counts[index]) / float(pack_count),
                ev_contribution_per_pack=contribution,
                ev_share=(contribution / total) if total > 0.0 else None,
                ev_rank=int(rank_by_entity[index]),
            )
        )
    results.sort(key=lambda item: item.ev_rank)
    return results


def compute_card_concentration(
    contributions: Sequence[CardContribution],
) -> CardConcentration:
    """Part 7: top-1/5/10 EV share, HHI and effective card count.

    HHI is ``sum(share^2)`` over all cards, matching
    ``derived_metrics._compute_hhi_from_ev_contributions``'s definition so the
    two numbers mean the same thing - they simply run on different inputs (that
    one on the analytic contributions, this one on the simulator's). Reporting
    both side by side is the point; silently replacing one with the other is not.

    ``effective_card_count = 1 / HHI`` is the standard inverse-HHI reading: the
    number of EQUALLY-sized contributors that would produce the same
    concentration. Treated as a supporting diagnostic, given no public name.
    """
    values = np.array(
        [max(0.0, item.ev_contribution_per_pack) for item in contributions], dtype=np.float64
    )
    total = float(values.sum())
    card_count = int(values.size)
    contributing = int(np.count_nonzero(values > 0.0))

    if total <= 0.0 or card_count == 0:
        return CardConcentration(
            card_count=card_count,
            contributing_card_count=contributing,
            total_ev_per_pack=total,
            top1_ev_share=None,
            top5_ev_share=None,
            top10_ev_share=None,
            hhi=None,
            effective_card_count=None,
        )

    ordered = np.sort(values)[::-1]
    shares = values / total
    hhi = float(np.sum(shares * shares))

    def _top(n: int) -> float:
        return float(ordered[: min(n, card_count)].sum() / total)

    return CardConcentration(
        card_count=card_count,
        contributing_card_count=contributing,
        total_ev_per_pack=total,
        top1_ev_share=_top(1),
        top5_ev_share=_top(5),
        top10_ev_share=_top(10),
        hhi=hhi,
        effective_card_count=(1.0 / hhi) if hhi > 0.0 else None,
    )


# ---------------------------------------------------------------------------
# Part 8 - rarity-level contribution, from the persisted authoritative run
# ---------------------------------------------------------------------------

def rarity_contributions_from_pull_summary(
    rows: Iterable[Mapping[str, Any]],
    *,
    packs_simulated: int,
    simulated_mean: float,
) -> Dict[str, Any]:
    """Part 8 from ``simulation_pull_summary`` - the authoritative decomposition.

    ``simulation_pull_summary`` holds, per rarity bucket, how many cards of that
    bucket the run pulled and what they were collectively worth. Divided by the
    pack count those are exactly "expected copies per pack" and "EV contribution
    per pack", and they sum to the run's mean by construction.

    The reconciliation is returned rather than asserted, because a caller
    comparing rows fetched at different times should be able to SEE the identity
    hold rather than trust that it did.

    NOTE ON WHAT THIS CANNOT ANSWER: expected copies per pack is not
    P(at least one). For a bucket that can appear twice in a pack the two differ,
    and copies is always the larger. ``collective_hit_probability_*`` below
    answer the probability question properly; this function does not guess at it.
    """
    packs = int(packs_simulated)
    if packs <= 0:
        raise ValueError("packs_simulated must be positive")

    buckets: List[Dict[str, Any]] = []
    total_ev = 0.0
    for row in rows:
        pulled = int(row.get("pulled_count") or 0)
        sampled_total = float(row.get("total_sampled_value") or 0.0)
        total_ev += sampled_total / packs
        buckets.append(
            {
                "rarityKey": str(row.get("rarity_bucket")),
                "pulledCount": pulled,
                "expectedCopiesPerPack": pulled / packs,
                "evContributionPerPack": sampled_total / packs,
                "averageValueWhenHit": (sampled_total / pulled) if pulled > 0 else None,
            }
        )

    for bucket in buckets:
        bucket["evShare"] = (
            bucket["evContributionPerPack"] / total_ev if total_ev > 0.0 else None
        )
    buckets.sort(key=lambda item: -item["evContributionPerPack"])

    mean = float(simulated_mean)
    return {
        "source": "simulation_pull_summary",
        "packsSimulated": packs,
        "buckets": buckets,
        "totalEvPerPack": total_ev,
        "simulatedMean": mean,
        "reconciliationAbsolute": total_ev - mean,
        "reconciliationRelative": ((total_ev - mean) / mean) if mean > 0.0 else None,
    }


def rarity_contributions_from_decomposition(
    decomposition: PackDecomposition,
    contributions: Sequence[CardContribution],
) -> Dict[str, Any]:
    """The same Part 8 shape, aggregated from Tier B.

    Used as a CROSS-CHECK of the persisted authoritative decomposition, never as
    a replacement for it. Where the two disagree beyond Monte Carlo error, that
    is evidence the Tier B re-simulation is not reproducing the authoritative
    run's configuration, which is exactly what the reconciliation gate is for.
    """
    pack_count = decomposition.pack_count
    aggregate: Dict[str, Dict[str, float]] = {}
    for item in contributions:
        bucket = aggregate.setdefault(
            item.rarity_key, {"pulled": 0.0, "ev": 0.0}
        )
        bucket["pulled"] += item.observed_pull_count
        bucket["ev"] += item.ev_contribution_per_pack

    total_ev = sum(bucket["ev"] for bucket in aggregate.values())
    buckets = [
        {
            "rarityKey": key,
            "pulledCount": int(bucket["pulled"]),
            "expectedCopiesPerPack": bucket["pulled"] / pack_count,
            "evContributionPerPack": bucket["ev"],
            "evShare": (bucket["ev"] / total_ev) if total_ev > 0.0 else None,
            "averageValueWhenHit": (
                (bucket["ev"] * pack_count / bucket["pulled"]) if bucket["pulled"] > 0 else None
            ),
        }
        for key, bucket in aggregate.items()
    ]
    buckets.sort(key=lambda item: -item["evContributionPerPack"])
    return {
        "source": "tier_b_decomposition",
        "packsSimulated": pack_count,
        "buckets": buckets,
        "totalEvPerPack": total_ev,
    }


# ---------------------------------------------------------------------------
# Part 9 - collective hit frequency
# ---------------------------------------------------------------------------

def collective_hit_probability_empirical(
    decomposition: PackDecomposition,
    rarity_groups: Mapping[str, Sequence[str]],
) -> Dict[str, Any]:
    """P(pack contains at least one card in each named rarity group).

    Counted directly off the sampled paths, so the mutual exclusivity of pack
    states, the without-replacement rule across the three variable slots, and
    both special-pack entry paths are all honoured exactly. No independence
    assumption is made anywhere, because none is needed: the events are simply
    observed.

    ``rarity_groups`` maps a label to the rarity keys it covers, so a caller can
    ask for a single layer ("special illustration rare") or a union
    ("any premium rarity") with the same call.
    """
    rarity_keys = decomposition.rarity_keys()
    pack_count = decomposition.pack_count
    results: Dict[str, Any] = {}
    for label, members in rarity_groups.items():
        wanted = {str(member) for member in members}
        mask = np.array([str(key) in wanted for key in rarity_keys], dtype=bool)
        if not mask.any():
            results[label] = {
                "probabilityAtLeastOne": 0.0,
                "expectedCopiesPerPack": 0.0,
                "memberRarities": sorted(wanted),
                "reachable": False,
            }
            continue
        presence = decomposition.pack_entity_presence(mask)
        counts = decomposition.pull_counts()
        results[label] = {
            "probabilityAtLeastOne": float(np.count_nonzero(presence)) / pack_count,
            "expectedCopiesPerPack": float(counts[mask].sum()) / pack_count,
            "memberRarities": sorted(wanted),
            "reachable": True,
        }
    return {"source": "tier_b_decomposition", "packsSimulated": pack_count, "groups": results}


def collective_hit_probability_from_state_model(
    *,
    state_probabilities: Mapping[str, float],
    coerced_state_outcomes: Mapping[str, Mapping[str, str]],
    rarity_groups: Mapping[str, Sequence[str]],
    normal_path_probability: float = 1.0,
) -> Dict[str, Any]:
    """The same probability, derived from the pack state model itself.

    For each pack state the model already fixes which token lands in each of the
    three variable slots, so "does this state contain rarity r" is a lookup, not
    an estimate::

        P(any r | normal pack) = sum over states of P(state) * [r in state]

    scaled by P(normal pack) from the run's own path counts.

    THIS IS A LOWER BOUND on the total, not the whole answer: god and demi-god
    packs can also produce these rarities and are not described by a pack state.
    It is published as a cross-check on the empirical figure - the empirical must
    be at least this large, and close to it whenever the special-pack paths are
    rare - rather than as a competing number.
    """
    total = sum(float(value) for value in state_probabilities.values())
    if total <= 0.0:
        raise ValueError("state probabilities must sum to a positive value")

    results: Dict[str, Any] = {}
    for label, members in rarity_groups.items():
        wanted = {str(member).strip().lower() for member in members}
        probability = 0.0
        matching_states: List[str] = []
        for state, weight in state_probabilities.items():
            outcomes = coerced_state_outcomes.get(state, {})
            tokens = {str(token).strip().lower() for token in outcomes.values()}
            if tokens & wanted:
                probability += float(weight) / total
                matching_states.append(state)
        results[label] = {
            "probabilityAtLeastOneGivenNormalPack": probability,
            "probabilityAtLeastOne": probability * float(normal_path_probability),
            "matchingStateCount": len(matching_states),
            "memberRarities": sorted(wanted),
        }
    return {
        "source": "pack_state_model",
        "normalPathProbability": float(normal_path_probability),
        "isLowerBound": True,
        "boundReason": "special-pack entry paths are not described by a pack state",
        "groups": results,
    }


# ---------------------------------------------------------------------------
# Part 10 - economically meaningful hit frequency
# ---------------------------------------------------------------------------

def economic_hit_frequencies(
    decomposition: PackDecomposition,
    *,
    pack_cost: float,
    prices: Optional[np.ndarray] = None,
    cost_multiples: Sequence[float] = ECONOMIC_HIT_COST_MULTIPLES,
) -> Dict[str, Any]:
    """P(pack contains at least one SINGLE card worth >= m x pack cost).

    Rarity-independent by design, and a sensitivity grid rather than one chosen
    threshold, because the interesting result is the SHAPE of the decay - a set
    where P(>=1x cost) is 12% but P(>=5x cost) is 11% has a completely different
    opening feel from one where those are 30% and 2%, even at identical EV.

    The quantity is the maximum single-card value in the pack, NOT the pack
    total. Four commons adding to the pack price is not the opener reaching an
    economically meaningful layer of the card distribution; one card worth the
    pack price is.
    """
    cost = float(pack_cost)
    if not math.isfinite(cost) or cost <= 0.0:
        raise ValueError(f"economic hit frequencies require a positive pack cost; got {pack_cost}")

    best = decomposition.pack_max_entity_value(prices)
    pack_count = decomposition.pack_count
    thresholds: List[Dict[str, Any]] = []
    for multiple in cost_multiples:
        threshold = float(multiple) * cost
        hits = int(np.count_nonzero(best >= threshold))
        thresholds.append(
            {
                "costMultiple": float(multiple),
                "thresholdValue": threshold,
                "probability": hits / pack_count,
                "packsWithHit": hits,
                "oneInEveryNPacks": (pack_count / hits) if hits > 0 else None,
            }
        )
    return {
        "packCost": cost,
        "packsSimulated": pack_count,
        "definition": "max_single_card_value_in_pack",
        "thresholds": thresholds,
        "meanBestCardValue": float(best.mean()),
        "medianBestCardValue": float(np.median(best)),
    }
