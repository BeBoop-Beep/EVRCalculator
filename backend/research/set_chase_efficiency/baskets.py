"""Chase-basket construction, and the eligibility rules behind it.

WHY SEVERAL DEFINITIONS AND NOT ONE
-----------------------------------
Stage I deliberately refuses to pick a canonical "chase". Three families are
built for every set so the study can ask whether an economically meaningful
chase universe EMERGES rather than being asserted:

* ``top_k``   - rank by market value, take the K best. Scale-free, but K is
                arbitrary and the study has to show whether it matters.
* ``value_threshold`` - an absolute dollar floor. Economically legible, but not
                comparable across sets whose packs cost $5 and $30.
* ``cost_multiple``   - value as a multiple of what one pack costs. This is the
                only family that is dimensionless in the buyer's own currency,
                which is why it is included even though nothing yet says it wins.

Rarity labels are NOT a basket family. "Special illustration rare" is a
print-run label, not a statement that anyone wants the card, and the brief
forbids it as the sole definition of chase.

EXCLUSIONS ARE DATA
-------------------
Nothing is dropped silently. Every card the simulator can draw is either a
member of the eligible universe or carries a reason code in
``ELIGIBILITY_REASONS``, and the counts are published with the results.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Sequence, Tuple

#: Every reason a drawable card can fail to enter the eligible chase universe.
ELIGIBILITY_REASONS = {
    "missing_card_variant_identity":
        "the simulator can draw this row but it carries no card_variant_id, so "
        "the pull cannot be tied to a tradeable printing",
    "non_positive_market_price":
        "no usable current near-mint market price; a $0 card cannot be the "
        "economic reason someone opens a set",
    "unreachable_in_simulation":
        "registered in a sampling pool but never drawn in the whole run, so its "
        "modelled probability is indistinguishable from zero at this sample size",
    "price_basis_not_current_market_date":
        "the price backing this row was captured on a different market date "
        "than the run being studied",
}

#: Top-K levels the Chase Frontier is built across.
FRONTIER_K = (1, 3, 5, 10, 15, 20)

#: Absolute dollar floors. Chosen AFTER inspecting the observed universe (see
#: the Stage-I report); they bracket the whole populated range rather than
#: sitting all on one side of it.
VALUE_THRESHOLDS = (10.0, 20.0, 30.0, 50.0, 100.0, 200.0)

#: Value as a multiple of one pack's acquisition cost.
COST_MULTIPLES = (2.0, 5.0, 10.0, 25.0)


@dataclass(frozen=True)
class ChaseCandidate:
    """One exact printing the simulator can actually draw."""

    entity_id: int
    card_variant_id: Optional[str]
    card_id: Optional[str]
    card_name: Optional[str]
    card_number: Optional[str]
    printing_type: Optional[str]
    rarity_key: Optional[str]
    price: float
    price_captured_at: Optional[str]
    price_source: Optional[str]
    pull_count: int

    def as_payload(self) -> Dict[str, Any]:
        return {
            "entityId": self.entity_id,
            "cardVariantId": self.card_variant_id,
            "cardId": self.card_id,
            "cardName": self.card_name,
            "cardNumber": self.card_number,
            "printingType": self.printing_type,
            "rarityKey": self.rarity_key,
            "marketPrice": self.price,
            "priceCapturedAt": self.price_captured_at,
            "priceSource": self.price_source,
            "pullCount": self.pull_count,
        }


@dataclass(frozen=True)
class Basket:
    """A named set of qualifying chase candidates."""

    definition_family: str
    definition_key: str
    definition_parameter: float
    members: Tuple[ChaseCandidate, ...]
    #: Set when the definition could not be honoured (e.g. Top-20 on a set with
    #: 12 eligible cards). A supported=False basket is REPORTED, never scored.
    supported: bool = True
    unsupported_reason: Optional[str] = None

    @property
    def entity_ids(self) -> Tuple[int, ...]:
        return tuple(member.entity_id for member in self.members)

    def as_payload(self) -> Dict[str, Any]:
        return {
            "definitionFamily": self.definition_family,
            "definitionKey": self.definition_key,
            "definitionParameter": self.definition_parameter,
            "chaseCount": len(self.members),
            "supported": self.supported,
            "unsupportedReason": self.unsupported_reason,
            "qualifyingCardVariantIds": [m.card_variant_id for m in self.members],
        }


def partition_universe(
    candidates: Sequence[Dict[str, Any]],
    *,
    market_date: Optional[str] = None,
) -> Tuple[List[ChaseCandidate], List[Dict[str, Any]]]:
    """Split every drawable row into the eligible universe and the excluded.

    ``market_date`` is compared against each row's own price capture date. It is
    a REPORTED exclusion rather than a hard filter of the run, because a set
    whose prices all failed the date check would otherwise vanish from the study
    with no visible reason.
    """
    eligible: List[ChaseCandidate] = []
    excluded: List[Dict[str, Any]] = []
    for row in candidates:
        reason: Optional[str] = None
        variant_id = row.get("card_variant_id")
        price = row.get("price")
        try:
            price = float(price)
        except (TypeError, ValueError):
            price = None
        captured = row.get("price_captured_at")
        captured_day = str(captured)[:10] if captured else None
        if not variant_id:
            reason = "missing_card_variant_identity"
        elif price is None or price <= 0.0:
            reason = "non_positive_market_price"
        elif int(row.get("pull_count") or 0) <= 0:
            reason = "unreachable_in_simulation"
        elif market_date and captured_day and captured_day != str(market_date)[:10]:
            reason = "price_basis_not_current_market_date"
        if reason is not None:
            excluded.append({
                "entityId": row.get("entity_id"),
                "cardVariantId": variant_id,
                "cardName": row.get("card_name"),
                "cardNumber": row.get("card_number"),
                "marketPrice": price,
                "pullCount": int(row.get("pull_count") or 0),
                "priceCapturedAt": captured_day,
                "reason": reason,
            })
            continue
        eligible.append(ChaseCandidate(
            entity_id=int(row["entity_id"]),
            card_variant_id=str(variant_id),
            card_id=row.get("card_id"),
            card_name=row.get("card_name"),
            card_number=row.get("card_number"),
            printing_type=row.get("printing_type"),
            rarity_key=row.get("rarity_key"),
            price=price,
            price_captured_at=captured_day,
            price_source=row.get("price_source"),
            pull_count=int(row.get("pull_count") or 0),
        ))
    return eligible, excluded


def _ordered(universe: Sequence[ChaseCandidate]) -> List[ChaseCandidate]:
    """Most valuable first, with a deterministic tie-break.

    Ties on price are common at the cheap end and would otherwise make Top-K
    membership depend on dict ordering, which would silently break run-to-run
    reproducibility of the frontier.
    """
    return sorted(
        universe,
        key=lambda c: (-c.price, str(c.card_variant_id or ""), c.entity_id),
    )


def build_baskets(
    universe: Sequence[ChaseCandidate],
    *,
    pack_cost: Optional[float],
    frontier_k: Sequence[int] = FRONTIER_K,
    value_thresholds: Sequence[float] = VALUE_THRESHOLDS,
    cost_multiples: Sequence[float] = COST_MULTIPLES,
) -> List[Basket]:
    """Every research basket for one set, in a stable order."""
    ordered = _ordered(universe)
    baskets: List[Basket] = []

    for k in frontier_k:
        if len(ordered) >= k:
            baskets.append(Basket("top_k", f"top_{k}", float(k), tuple(ordered[:k])))
        else:
            baskets.append(Basket(
                "top_k", f"top_{k}", float(k), tuple(),
                supported=False,
                unsupported_reason=f"only {len(ordered)} eligible chase cards in the set",
            ))

    for threshold in value_thresholds:
        members = tuple(c for c in ordered if c.price >= threshold)
        baskets.append(Basket(
            "value_threshold", f"value_gte_{int(threshold)}", float(threshold), members,
            supported=bool(members),
            unsupported_reason=None if members else "no eligible card reaches this value floor",
        ))

    for multiple in cost_multiples:
        if pack_cost is None or pack_cost <= 0:
            baskets.append(Basket(
                "cost_multiple", f"value_gte_{int(multiple)}x_pack", float(multiple), tuple(),
                supported=False,
                unsupported_reason="no usable pack-equivalent acquisition cost",
            ))
            continue
        floor = multiple * pack_cost
        members = tuple(c for c in ordered if c.price >= floor)
        baskets.append(Basket(
            "cost_multiple", f"value_gte_{int(multiple)}x_pack", float(multiple), members,
            supported=bool(members),
            unsupported_reason=None if members else "no eligible card reaches this cost multiple",
        ))

    return baskets
