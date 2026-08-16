"""Add a product's GUARANTEED card value to its random opening distribution.

THE WHOLE OPERATION
-------------------
A Stage 2 product's opening is a random part plus a certainty::

    Y_product[i] = Y_random[i] + G       for every i

``G`` is a CONSTANT. The card is guaranteed - it is in every box - so it is not
sampled, has no odds, and never enters the pack simulator. Adding it is a
translation of the whole distribution, which is why this module is twelve lines
of arithmetic and a great deal of explanation about what must NOT happen to it.

WHAT MUST NOT HAPPEN
--------------------
* The promo must not be drawn. Giving a guaranteed card a probability would
  understate its value in exactly the boxes where it is the only certainty.
* The promo must not be inserted into ``X``. ``X`` is the finished loose-pack
  outcome vector; a booster pack does not contain the ETB promo, and polluting
  ``X`` would corrupt every Stage 1 product built from the same vector.
* ``Y_random`` must not be mutated. Several SKUs legitimately share one random
  distribution - two ETB artwork variants have the same 9 packs and different
  promos - so an in-place add would silently apply the first SKU's promo to
  every subsequent one. The shared vector is read-only and this returns a NEW
  array.

WHY A TRANSLATION IS NOT A SHORTCUT FOR THE SCORE
--------------------------------------------------
Because ``Y_product`` is a shift of ``Y_random``, it is tempting to shift the
statistics too. Some do shift: the mean, the median and every percentile move by
exactly ``G``, and the standard deviation does not move at all. The ones that
matter do NOT: the probability of recovering cost, expected loss given a loss and
Financial RIP V3 all depend on where the COST sits relative to the distribution,
and the shift moves the distribution relative to a cost that stays put. So
nothing downstream reconstructs a Stage 2 score from a Stage 1 one - the composed
vector goes to ``build_financial_rip_v3`` intact, like any other.
"""

from __future__ import annotations

from typing import Any, Dict, Mapping, Sequence

import numpy as np

GUARANTEED_COMPONENT_MODEL_VERSION = "fixed_guaranteed_component_offset_v1"


class GuaranteedComponentError(ValueError):
    """A guaranteed component that cannot be valued truthfully."""


def total_guaranteed_value(priced_components: Sequence[Mapping[str, Any]]) -> float:
    """Sum ``quantity * market_price`` over every guaranteed component.

    Every component must already carry a finite, strictly positive price. A
    missing price is NOT zero: a promo whose market price is unavailable is an
    unknown quantity, and treating it as free would publish a product's value as
    strictly lower than it is while looking like a measurement. Callers resolve
    that upstream and skip the product; reaching here without a price is a
    contract violation.
    """
    if not priced_components:
        raise GuaranteedComponentError(
            "A Stage 2 product has at least one guaranteed component; none were supplied."
        )

    total = 0.0
    for component in priced_components:
        price = component.get("market_price")
        quantity = component.get("quantity", 1)
        try:
            price_value = float(price)
            quantity_value = int(quantity)
        except (TypeError, ValueError) as exc:
            raise GuaranteedComponentError(
                f"guaranteed component {component.get('card_variant_id')} has non-numeric "
                f"price/quantity ({price!r}, {quantity!r})."
            ) from exc

        if not np.isfinite(price_value) or price_value <= 0.0:
            # Explicitly including 0.0: a zero market price is not a valid
            # observation of a card's worth, it is an absent one.
            raise GuaranteedComponentError(
                f"guaranteed component {component.get('card_variant_id')} has a non-positive or "
                f"non-finite market price ({price_value!r}); it must be skipped, not valued at zero."
            )
        if quantity_value < 1:
            raise GuaranteedComponentError(
                f"guaranteed component {component.get('card_variant_id')} has quantity "
                f"{quantity_value}; a guaranteed card appears at least once."
            )
        total += price_value * quantity_value

    return total


def add_guaranteed_components(
    random_distribution: Any,
    guaranteed_market_value: float,
) -> np.ndarray:
    """``random_distribution + guaranteed_market_value`` as a NEW array.

    The input is never modified and never returned - callers share one random
    distribution across SKUs and rely on that.
    """
    values = np.asarray(random_distribution, dtype=np.float64)
    if values.ndim != 1 or values.size == 0:
        raise GuaranteedComponentError(
            f"random distribution must be a non-empty 1-D vector; got shape {values.shape}."
        )
    if not np.all(np.isfinite(values)):
        raise GuaranteedComponentError("random distribution contains non-finite values.")

    offset = float(guaranteed_market_value)
    if not np.isfinite(offset) or offset <= 0.0:
        raise GuaranteedComponentError(
            f"guaranteed value must be finite and positive; got {offset!r}."
        )

    # `values + offset` already allocates, so this is a new array by construction
    # rather than by a defensive copy. Stated because it is load-bearing.
    composed = values + offset
    return composed


def compose_stage2_distribution(
    random_distribution: Any,
    priced_components: Sequence[Mapping[str, Any]],
) -> Dict[str, Any]:
    """The composed vector plus the metadata that explains how it was built.

    Returns ``{"values": ndarray, "meta": {...}}``. The metadata separates random
    pack value from guaranteed value on purpose: conflating them would hide that
    a product's expected value can be dominated by a single certain card, which
    is precisely the thing a Stage 2 reader needs to see.
    """
    guaranteed_value = total_guaranteed_value(priced_components)
    random_values = np.asarray(random_distribution, dtype=np.float64)
    composed = add_guaranteed_components(random_values, guaranteed_value)

    random_expected_value = float(random_values.mean())
    composed_expected_value = float(composed.mean())

    return {
        "values": composed,
        "meta": {
            "guaranteedComponentModelVersion": GUARANTEED_COMPONENT_MODEL_VERSION,
            "randomPackExpectedValue": random_expected_value,
            "totalGuaranteedValue": guaranteed_value,
            "guaranteedCardCount": sum(int(c.get("quantity", 1)) for c in priced_components),
            "guaranteedComponentCount": len(priced_components),
            "expectedValue": composed_expected_value,
            # How much of the product's expected value is certain rather than
            # gambled. A high share means the "opening" is mostly a purchase.
            "guaranteedValueShareOfExpectedValue": (
                guaranteed_value / composed_expected_value if composed_expected_value > 0 else None
            ),
            "guaranteedComponents": [
                {
                    "cardVariantId": c.get("card_variant_id"),
                    "componentRole": c.get("component_role"),
                    "quantity": int(c.get("quantity", 1)),
                    "marketPrice": float(c["market_price"]),
                    "capturedAt": str(c["captured_at"]) if c.get("captured_at") else None,
                    "source": c.get("source"),
                    "displayName": c.get("display_name"),
                }
                for c in priced_components
            ],
        },
    }
