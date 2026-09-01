"""Stage V-C research version identifiers."""

from __future__ import annotations

#: Bump when any Stage V-C metric definition changes.
PRODUCT_CHASE_ECONOMICS_VERSION = "product-chase-economics-stage5c-v1"

#: The coupled tier contract, recorded on every artifact so a published number
#: can never be read without the rule that produced it.
PRODUCT_CHASE_TIER_CONTRACT = (
    "core=3x, extended=1x of product_market_cost/random_pack_count"
)
