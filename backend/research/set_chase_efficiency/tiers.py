"""Objective, percentage-based Chase Tier candidate rules.

THE CHANGE OF DIRECTION
-----------------------
Stage III built a human-labeling experiment to discover what a "chase" IS.
That apparatus is preserved and remains available, but it is no longer the
gate. This stage asks a narrower and more tractable question:

    Can inDex define Core / Extended chase tiers that are objective,
    reproducible, economically meaningful and stable across sets - WITHOUT
    claiming a universal cultural definition of "chase"?

The bar is internal consistency, not cultural truth. A rule that is
transparent, scale-free and stable under market noise is publishable even if
nobody can prove it matches what a collector means by the word.

WHAT COUNTS AS A CANDIDATE
--------------------------
Four families, deliberately spanning different assumptions:

* ``count_percentile``   - top q% of the eligible printings by value. Purely
                           ordinal, so it cannot notice that a "chase" is worth
                           less than the pack it came from.
* ``percentile_floor``   - the same, intersected with an economic floor
                           expressed in pack costs. The floor is what stops an
                           expensive-sealed set from manufacturing fake chases.
* ``price_distribution`` - where the card sits in the SHAPE of the price
                           distribution (robust z on log price, multiples of the
                           median or upper quartile) rather than in its rank.
* ``relative_to_top``    - value as a fraction of the set's best card. Scale
                           free by construction, and expected to collapse on
                           hero-chase sets, which is why it is tested.

HHI IS NOT ALLOWED TO CHOOSE A TIER
-----------------------------------
Stage II showed effective chase count is circular as a selector: it is computed
FROM a basket, so using it to CHOOSE the basket moves the answer by up to 17
cards depending on the reference pool. Here HHI is computed only AFTER a tier is
fixed, as a description of that tier's depth. Nothing in this module reads it.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Sequence, Tuple

import numpy as np

from .baskets import ChaseCandidate

#: Card-count percentiles under test. Spans "one or two cards" to "a fifth of
#: the set", which brackets every plausible chase pool seen in Stages I-II.
COUNT_PERCENTILES: Tuple[float, ...] = (0.025, 0.05, 0.075, 0.10, 0.15, 0.20)

#: Discrete rounding modes. Which one is used changes K by one card on small
#: sets, which is the difference between a one-card and a two-card Core tier.
ROUNDING_MODES: Tuple[str, ...] = ("floor", "round", "ceil")

#: Economic floors, as multiples of the pack-equivalent acquisition cost.
#: ``0.0`` means no floor and is included so the floor's effect is measurable
#: rather than assumed.
COST_FLOORS: Tuple[float, ...] = (0.0, 1.0, 2.0, 3.0, 5.0, 10.0)

#: Fractions of the top card's value, for the scale-free family.
TOP_CARD_FRACTIONS: Tuple[float, ...] = (0.10, 0.20, 0.25, 0.33, 0.50)

#: A tier must contain at least this many cards to exist at all. Prevents a
#: percentile from silently producing an empty Core on a small set.
MINIMUM_TIER_SIZE = 1


def ordered(cards: Sequence[ChaseCandidate]) -> List[ChaseCandidate]:
    """Most valuable first, with a deterministic tie-break.

    Ties are common in the cheap tail and would otherwise make tier membership
    depend on dict ordering, destroying run-to-run reproducibility.
    """
    return sorted(cards, key=lambda c: (-c.price, str(c.card_variant_id or ""), c.entity_id))


def discrete_k(fraction: float, population: int, *, mode: str = "ceil",
               minimum: int = MINIMUM_TIER_SIZE) -> int:
    """How many cards a percentage actually selects.

    ``ceil`` is the default because ``floor`` produces ZERO cards for any set
    where ``fraction * N < 1`` - a 2.5% Core tier on a 200-card set is 5 cards,
    but on a 30-card set floor gives 0. A tier rule that can silently return an
    empty Core is not a tier rule, so the minimum is clamped rather than left to
    the caller to notice.
    """
    if population <= 0:
        return 0
    raw = fraction * population
    if mode == "floor":
        value = int(math.floor(raw))
    elif mode == "round":
        # Half-up, not banker's rounding: round(2.5) is 2 in Python, which would
        # make an even-numbered K silently smaller than an odd-numbered one.
        value = int(math.floor(raw + 0.5))
    elif mode == "ceil":
        value = int(math.ceil(raw))
    else:
        raise ValueError(f"unknown rounding mode {mode!r}")
    return max(minimum, min(value, population))


@dataclass(frozen=True)
class TierRule:
    """One objective, reproducible rule for selecting a tier."""

    family: str
    key: str
    describe: str
    selector: Callable[[Sequence[ChaseCandidate], Optional[float]], List[ChaseCandidate]]
    parameters: Dict[str, Any] = field(default_factory=dict)

    def select(self, cards: Sequence[ChaseCandidate],
               pack_cost: Optional[float]) -> List[ChaseCandidate]:
        return self.selector(cards, pack_cost)


# ---------------------------------------------------------------------------
# Family 1 + 2: card-count percentile, with and without an economic floor
# ---------------------------------------------------------------------------

def count_percentile_rule(fraction: float, *, mode: str = "ceil",
                          cost_floor: float = 0.0) -> TierRule:
    def selector(cards, pack_cost):
        ranked = ordered(cards)
        k = discrete_k(fraction, len(ranked), mode=mode)
        chosen = ranked[:k]
        if cost_floor > 0.0:
            if not pack_cost or pack_cost <= 0:
                return []
            threshold = cost_floor * pack_cost
            chosen = [c for c in chosen if c.price >= threshold]
        return chosen

    floor_label = "" if cost_floor <= 0 else f"_ge{int(cost_floor)}xC"
    family = "count_percentile" if cost_floor <= 0 else "percentile_floor"
    percent = f"{fraction * 100:g}"
    return TierRule(
        family=family,
        key=f"top{percent}pct_{mode}{floor_label}",
        describe=(f"top {percent}% of eligible printings by value ({mode} rounding)"
                  + (f", and worth at least {cost_floor:g}x pack cost" if cost_floor > 0 else "")),
        selector=selector,
        parameters={"fraction": fraction, "rounding": mode, "costFloor": cost_floor},
    )


# ---------------------------------------------------------------------------
# Family 3: position in the SHAPE of the price distribution
# ---------------------------------------------------------------------------

def log_zscore_rule(threshold: float) -> TierRule:
    """Cards whose log price is a robust outlier against the set's own body.

    Median/MAD rather than mean/sd: the chase cards ARE the outliers and would
    otherwise inflate the very dispersion they are being tested against.
    """
    def selector(cards, pack_cost):
        ranked = ordered(cards)
        prices = np.array([c.price for c in ranked], dtype=np.float64)
        if prices.size < 8:
            return []
        logs = np.log(prices)
        median = float(np.median(logs))
        mad = float(np.median(np.abs(logs - median)))
        if mad <= 0:
            return []
        scores = 0.6745 * (logs - median) / mad
        return [card for card, score in zip(ranked, scores) if score >= threshold]

    return TierRule(
        family="price_distribution",
        key=f"log_zscore_ge{threshold:g}",
        describe=f"log-price robust z-score (median/MAD) at least {threshold:g}",
        selector=selector,
        parameters={"threshold": threshold},
    )


def multiple_of_quantile_rule(quantile: float, multiple: float) -> TierRule:
    """Value at least ``multiple`` times the set's own median or upper quartile.

    Scale-free within a set and, unlike a rank rule, sensitive to how spread out
    the distribution actually is.
    """
    def selector(cards, pack_cost):
        ranked = ordered(cards)
        prices = np.array([c.price for c in ranked], dtype=np.float64)
        if prices.size < 4:
            return []
        anchor = float(np.quantile(prices, quantile))
        if anchor <= 0:
            return []
        threshold = multiple * anchor
        return [card for card in ranked if card.price >= threshold]

    label = "median" if abs(quantile - 0.5) < 1e-9 else f"q{int(quantile * 100)}"
    return TierRule(
        family="price_distribution",
        key=f"ge{multiple:g}x_{label}",
        describe=f"value at least {multiple:g}x the set's {label} price",
        selector=selector,
        parameters={"quantile": quantile, "multiple": multiple},
    )


# ---------------------------------------------------------------------------
# Family 4: relative to the top card
# ---------------------------------------------------------------------------

def relative_to_top_rule(fraction: float) -> TierRule:
    """Value at least ``fraction`` of the set's best card.

    Expected to FAIL on hero-chase sets: when the top card is an extreme
    outlier, even 10% of it excludes everything else. Included precisely so that
    failure is measured rather than assumed.
    """
    def selector(cards, pack_cost):
        ranked = ordered(cards)
        if not ranked:
            return []
        threshold = fraction * ranked[0].price
        return [card for card in ranked if card.price >= threshold]

    return TierRule(
        family="relative_to_top",
        key=f"ge{int(fraction * 100)}pct_of_top",
        describe=f"value at least {fraction * 100:g}% of the set's top card",
        selector=selector,
        parameters={"fraction": fraction},
    )


# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------

def candidate_rules() -> List[TierRule]:
    """Every single-tier rule under test, in a stable order."""
    rules: List[TierRule] = []
    for fraction in COUNT_PERCENTILES:
        for mode in ROUNDING_MODES:
            rules.append(count_percentile_rule(fraction, mode=mode))
    # The floor matrix uses ceil rounding only: the rounding question is settled
    # independently above, and crossing both would triple the matrix without
    # asking anything new.
    for fraction in COUNT_PERCENTILES:
        for floor in COST_FLOORS:
            if floor <= 0.0:
                continue
            rules.append(count_percentile_rule(fraction, mode="ceil", cost_floor=floor))
    for threshold in (2.0, 2.5, 3.0, 3.5):
        rules.append(log_zscore_rule(threshold))
    for multiple in (5.0, 10.0, 25.0, 50.0):
        rules.append(multiple_of_quantile_rule(0.5, multiple))
    for multiple in (3.0, 5.0, 10.0, 20.0):
        rules.append(multiple_of_quantile_rule(0.75, multiple))
    for fraction in TOP_CARD_FRACTIONS:
        rules.append(relative_to_top_rule(fraction))
    return rules


def rules_by_key() -> Dict[str, TierRule]:
    return {rule.key: rule for rule in candidate_rules()}


# ---------------------------------------------------------------------------
# Two-tier systems
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class TierSystem:
    """A Core rule and an Extended rule, with Core required to nest inside."""

    key: str
    core: TierRule
    extended: TierRule
    describe: str = ""

    def apply(self, cards: Sequence[ChaseCandidate],
              pack_cost: Optional[float]) -> Dict[str, Any]:
        """Select both tiers and REPAIR any nesting violation, reporting it.

        ``CORE ⊆ EXTENDED`` is a contract, not an aspiration: a Core card that
        is not an Extended card would make "Core + Extended" ambiguous and would
        silently double-count that card in any union metric. Where a rule pair
        violates it - an economic floor on Extended can exclude a card the Core
        percentile admitted - the union is taken and the violation is recorded,
        so the pairing can be judged on how often it needs repairing.
        """
        core = self.core.select(cards, pack_cost)
        extended = self.extended.select(cards, pack_cost)
        core_ids = {c.entity_id for c in core}
        extended_ids = {c.entity_id for c in extended}
        violations = sorted(core_ids - extended_ids)
        if violations:
            by_id = {c.entity_id: c for c in cards}
            extended = ordered(list(extended) + [by_id[i] for i in violations])
        return {
            "core": ordered(core),
            "extended": ordered(extended),
            "nestingViolations": len(violations),
            "extendedOnly": ordered([c for c in extended
                                     if c.entity_id not in core_ids]),
        }


#: The named families the brief asks for, plus a systematic search around them.
def candidate_systems() -> List[TierSystem]:
    named = [
        TierSystem("A_pct_only", count_percentile_rule(0.05),
                   count_percentile_rule(0.15),
                   "Core top 5%, Extended top 15%, no economic floor"),
        TierSystem("B_pct_floor", count_percentile_rule(0.05, cost_floor=5.0),
                   count_percentile_rule(0.15, cost_floor=2.0),
                   "Core top 5% and >=5xC, Extended top 15% and >=2xC"),
        TierSystem("C_tight", count_percentile_rule(0.025, cost_floor=5.0),
                   count_percentile_rule(0.10, cost_floor=2.0),
                   "Core top 2.5% and >=5xC, Extended top 10% and >=2xC"),
        TierSystem("D_wide", count_percentile_rule(0.10, cost_floor=5.0),
                   count_percentile_rule(0.20, cost_floor=2.0),
                   "Core top 10% and >=5xC, Extended top 20% and >=2xC"),
    ]
    # Systematic search: every (core percentile, extended percentile) pair where
    # the Core is strictly tighter, crossed with a small set of floor pairings.
    search: List[TierSystem] = []
    for core_fraction in (0.025, 0.05, 0.075, 0.10):
        for extended_fraction in (0.10, 0.15, 0.20):
            if extended_fraction <= core_fraction:
                continue
            for core_floor, extended_floor in ((0.0, 0.0), (2.0, 1.0), (3.0, 1.0),
                                               (5.0, 2.0), (10.0, 3.0)):
                key = (f"S_c{core_fraction * 100:g}f{core_floor:g}"
                       f"_e{extended_fraction * 100:g}f{extended_floor:g}")
                search.append(TierSystem(
                    key,
                    count_percentile_rule(core_fraction, cost_floor=core_floor),
                    count_percentile_rule(extended_fraction, cost_floor=extended_floor),
                    f"Core top {core_fraction * 100:g}%"
                    + (f" and >={core_floor:g}xC" if core_floor else "")
                    + f", Extended top {extended_fraction * 100:g}%"
                    + (f" and >={extended_floor:g}xC" if extended_floor else ""),
                ))
    # One representative from each non-percentile family, so the scorecard can
    # compare across families rather than only within the percentile grid.
    alternatives = [
        TierSystem("Z_logz", log_zscore_rule(3.0), log_zscore_rule(2.0),
                   "Core log-z>=3.0, Extended log-z>=2.0"),
        TierSystem("Z_median", multiple_of_quantile_rule(0.5, 25.0),
                   multiple_of_quantile_rule(0.5, 10.0),
                   "Core >=25x median, Extended >=10x median"),
        TierSystem("Z_top", relative_to_top_rule(0.33), relative_to_top_rule(0.10),
                   "Core >=33% of top card, Extended >=10% of top card"),
    ]
    return named + search + alternatives


def jaccard(left: Sequence[int], right: Sequence[int]) -> Optional[float]:
    a, b = set(left), set(right)
    if not a and not b:
        return None
    union = a | b
    return round(len(a & b) / len(union), 6) if union else None


def shocked_cards(cards: Sequence[ChaseCandidate], *, magnitude: float,
                  seed: int, joint: bool = False) -> List[ChaseCandidate]:
    """The same printings under a price shock.

    ``joint=True`` moves every card by the SAME factor - a market-wide level
    shift, which a scale-free rule should be completely immune to and a rule
    with an absolute floor should not be. ``joint=False`` shocks each card
    independently, which is the ordinary noise case.
    """
    rng = np.random.default_rng(seed)
    common = 1.0 + float(rng.uniform(-magnitude, magnitude)) if joint else None
    out: List[ChaseCandidate] = []
    for card in cards:
        factor = common if joint else 1.0 + float(rng.uniform(-magnitude, magnitude))
        out.append(ChaseCandidate(
            entity_id=card.entity_id, card_variant_id=card.card_variant_id,
            card_id=card.card_id, card_name=card.card_name,
            card_number=card.card_number, printing_type=card.printing_type,
            rarity_key=card.rarity_key, price=max(card.price * factor, 1e-6),
            price_captured_at=card.price_captured_at, price_source=card.price_source,
            pull_count=card.pull_count))
    return out
