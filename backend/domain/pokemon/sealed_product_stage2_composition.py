"""Stage 2 sealed-product composition contract.

WHAT STAGE 2 ADDS
-----------------
Stage 1 models products whose entire opening is random: a booster box IS
thirty-six pack outcomes and nothing else. Stage 2 models products that are a
random part PLUS a certainty:

    product opening = K same-set booster pack outcomes + exact guaranteed cards

Three families qualify:

    elite_trainer_box                    typically  9 packs + 1 promo
    pokemon_center_elite_trainer_box     typically 11 packs + 2 promos
    enhanced_booster_box                 typically 36 packs + 1 promo

Those are BASELINE PATTERNS and this module never applies them. Pokemon's own
support documentation states the packs inside boxed products are the same packs
sold individually with the same pull rates, so Stage 2 changes nothing about how
a pack opens - but WHICH promo a given SKU guarantees varies by SKU, and that is
not derivable from a name.

WHY FAMILY-KEYED RESOLUTION IS NOT AVAILABLE HERE
--------------------------------------------------
Stage 1 could safely key composition on the classified family because family
membership determined the whole opening. It does not in Stage 2. One set's live
inventory routinely contains several ETBs that share a family and a pack count
while guaranteeing different, differently-priced promos, alongside cases and
multi-box listings that are not single retail openings at all::

    "<Set> Elite Trainer Box [Art A]"            9 packs + promo A
    "<Set> Elite Trainer Box [Art B]"            9 packs + promo B      <- differs
    "<Set> Elite Trainer Box Case"               not one opening
    "<Set> Elite Trainer Boxes [Set of 2]"       not one opening

So Stage 2 composition resolves from ``sealed_product_id`` against verified
database rows, and eligibility is a property of DATA:

    has an ACTIVE VERIFIED composition -> eligible
    otherwise                          -> not Stage 2 scorable

Name tokens can propose candidates for research. They never decide composition,
and this module contains no substring rule that does.

WHAT THIS MODULE IS
-------------------
Pure shape and policy. It parses composition rows into a validated value object
and answers "is this scorable, and if not, why not" in machine-readable terms.
It performs no I/O, holds no SQL, and resolves no prices - those belong to the
repository and the pricing service respectively, so this contract stays testable
without a database.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Mapping, Optional, Sequence, Tuple

STAGE2_COMPOSITION_CONTRACT_VERSION = "sealed-product-composition-stage2-v1"

#: The exact families Stage 2 opens. `booster_box` is absent because a standard
#: booster box has no guaranteed card and is already complete in Stage 1;
#: `enhanced_booster_box` is present and remains a SEPARATE family from it.
STAGE2_FAMILIES = frozenset(
    {
        "elite_trainer_box",
        "pokemon_center_elite_trainer_box",
        "enhanced_booster_box",
    }
)

#: Only this status is scorable. A researched-but-unconfirmed composition can be
#: stored and reported without ever reaching a score.
COMPOSITION_STATUS_VERIFIED = "verified"

# Machine-readable outcomes. Every Stage 2 SKU that is not scored carries exactly
# one of these, so a manifest never has to say "missing" without saying why.
REASON_NO_VERIFIED_COMPOSITION = "unresolved_composition"
REASON_UNRESOLVED_PROMO_IDENTITY = "unresolved_promo_identity"
REASON_MISSING_PROMO_PRICE = "guaranteed_component_market_price_unavailable"
REASON_MISSING_PRODUCT_PRICE = "missing_product_market_price"
REASON_NOT_STAGE2_FAMILY = "not_a_stage2_family"
REASON_MIXED_SET_UNSUPPORTED = "mixed_set_composition_unsupported_in_stage2"

#: Stage 2 assigns financial value to CARDS ONLY. Sleeves, dice, energy packs,
#: condition markers, dividers, the storage box, the player's guide, code cards
#: and coins are real contents with real resale value that this model does not
#: attempt to price. Disclosed on every result rather than left to be discovered.
ACCESSORY_VALUE_INCLUDED = False
ACCESSORY_VALUE_REASON = (
    "Stage 2 models collectible card value only; accessory resale value is not included."
)

#: Collector Appeal is INHERITED from the set and is not adjusted for guaranteed
#: promos. The promo changes Financial RIP - it has guaranteed monetary value -
#: but no promo-specific Collector Appeal construct exists or is invented here.
COLLECTOR_APPEAL_SCOPE = "set_level_inherited_guaranteed_promos_not_included"


@dataclass(frozen=True)
class GuaranteedCardComponent:
    """One exact printing a product is guaranteed to contain.

    ``card_variant_id`` is the identity that matters. ``canonical_card_id`` is
    carried when it exists but is never used to find a price: the canonical
    checklist cannot distinguish a Pokemon Center-stamped promo from the ordinary
    printing, and Stage 2 must.
    """

    card_variant_id: str
    quantity: int
    component_role: str
    canonical_card_id: Optional[str] = None
    display_name: Optional[str] = None

    def as_payload(self) -> Dict[str, Any]:
        return {
            "cardVariantId": self.card_variant_id,
            "canonicalCardId": self.canonical_card_id,
            "quantity": int(self.quantity),
            "componentRole": self.component_role,
            "displayName": self.display_name,
        }


@dataclass(frozen=True)
class PackComponent:
    """Booster packs from one source set."""

    set_id: str
    pack_count: int


@dataclass(frozen=True)
class Stage2ProductComposition:
    """The verified contents of one Stage 2 SKU."""

    sealed_product_id: str
    composition_id: str
    composition_version: str
    product_family: str
    pack_components: Tuple[PackComponent, ...]
    guaranteed_card_components: Tuple[GuaranteedCardComponent, ...]
    source_type: str
    source_reference: str
    verified_at: Any
    notes: Optional[str] = None

    @property
    def total_pack_count(self) -> int:
        return sum(component.pack_count for component in self.pack_components)

    @property
    def random_pack_set_id(self) -> str:
        """The single set the random packs come from.

        Stage 2 is same-set only, which ``parse_composition_row`` enforces, so
        there is exactly one pack component and this is unambiguous. Stage 3
        mixed-set products will have several and must not use this accessor.
        """
        return self.pack_components[0].set_id

    @property
    def guaranteed_card_count(self) -> int:
        return sum(component.quantity for component in self.guaranteed_card_components)

    def as_payload(self) -> Dict[str, Any]:
        return {
            "compositionId": self.composition_id,
            "compositionVersion": self.composition_version,
            "compositionContractVersion": STAGE2_COMPOSITION_CONTRACT_VERSION,
            "productFamily": self.product_family,
            "randomPackCount": self.total_pack_count,
            "randomPackSetId": self.random_pack_set_id,
            "guaranteedCardCount": self.guaranteed_card_count,
            "guaranteedComponents": [c.as_payload() for c in self.guaranteed_card_components],
            "sourceType": self.source_type,
            "sourceReference": self.source_reference,
            "verifiedAt": str(self.verified_at) if self.verified_at is not None else None,
            "accessoryValueIncluded": ACCESSORY_VALUE_INCLUDED,
            "accessoryValueReason": ACCESSORY_VALUE_REASON,
            "collectorAppealScope": COLLECTOR_APPEAL_SCOPE,
        }


class CompositionContractError(ValueError):
    """A composition row that violates the Stage 2 contract.

    Raised rather than returned: a stored composition that is structurally
    impossible (no packs, zero quantity, two source sets) is a data defect to be
    fixed, not an expected outcome to be counted in a manifest.
    """


def parse_composition_row(row: Mapping[str, Any]) -> Stage2ProductComposition:
    """Build a validated composition from one joined database row.

    The row is expected to carry the header fields plus ``packComponents`` and
    ``guaranteedCardComponents`` sequences. Validation is strict on purpose: this
    is the last point before a composition becomes a published dollar figure.
    """
    family = str(row.get("product_family") or "").strip()

    pack_rows = list(row.get("packComponents") or ())
    if not pack_rows:
        raise CompositionContractError(
            f"composition {row.get('id')} has no pack components; a Stage 2 product opens packs."
        )
    if len(pack_rows) > 1:
        # Not a defect in the data model - the schema supports it for Stage 3 -
        # but Stage 2 consumes ONE set's finished pack vector and has no defined
        # outcome for packs it never simulated.
        raise CompositionContractError(
            f"composition {row.get('id')} spans {len(pack_rows)} source sets; "
            f"Stage 2 is same-set only ({REASON_MIXED_SET_UNSUPPORTED})."
        )

    packs = tuple(
        PackComponent(set_id=str(p["set_id"]), pack_count=int(p["pack_count"])) for p in pack_rows
    )
    for pack in packs:
        if pack.pack_count < 1:
            raise CompositionContractError(
                f"composition {row.get('id')} declares pack_count={pack.pack_count}."
            )

    cards = tuple(
        GuaranteedCardComponent(
            card_variant_id=str(c["card_variant_id"]),
            quantity=int(c.get("quantity") or 1),
            component_role=str(c.get("component_role") or ""),
            canonical_card_id=(str(c["canonical_card_id"]) if c.get("canonical_card_id") else None),
            display_name=c.get("display_name"),
        )
        for c in (row.get("guaranteedCardComponents") or ())
    )
    for card in cards:
        if card.quantity < 1:
            raise CompositionContractError(
                f"composition {row.get('id')} declares quantity={card.quantity}."
            )

    seen = [c.card_variant_id for c in cards]
    if len(set(seen)) != len(seen):
        # The database enforces this too; asserting it here means the invariant
        # survives fixtures, seeds and any future non-DB source.
        raise CompositionContractError(
            f"composition {row.get('id')} lists the same printing twice; use quantity instead."
        )

    return Stage2ProductComposition(
        sealed_product_id=str(row["sealed_product_id"]),
        composition_id=str(row["id"]),
        composition_version=str(row["composition_version"]),
        product_family=family,
        pack_components=packs,
        guaranteed_card_components=cards,
        source_type=str(row.get("source_type") or ""),
        source_reference=str(row.get("source_reference") or ""),
        verified_at=row.get("verified_at"),
        notes=row.get("notes"),
    )


def is_stage2_family(product_family: Any) -> bool:
    return str(product_family or "").strip() in STAGE2_FAMILIES


def stage2_composition_scope_contract() -> Dict[str, Any]:
    """Stage 2's own disclosure block, attached to every summary."""
    return {
        "stage2CompositionContractVersion": STAGE2_COMPOSITION_CONTRACT_VERSION,
        "stage2Families": sorted(STAGE2_FAMILIES),
        "compositionAuthority": "sealed_product_id",
        "accessoryValueIncluded": ACCESSORY_VALUE_INCLUDED,
        "accessoryValueReason": ACCESSORY_VALUE_REASON,
        "collectorAppealScope": COLLECTOR_APPEAL_SCOPE,
    }
