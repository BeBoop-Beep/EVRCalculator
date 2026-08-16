"""Stage 2 sealed-product selection, pricing and composition.

WHERE THIS SITS
---------------
    finished pack vector X            (unchanged, produced once per set)
      -> shared K-pack bootstrap Y_K  (unchanged engine, new values of K)
      -> + exact guaranteed promo value G
      -> build_financial_rip_v3(Y_K + G, product market cost)
      -> the SAME simulation_sealed_product_results row model
      -> the SAME batch Collector Appeal / Overall RIP finalizer

Nothing in ``backend/simulations`` is touched, no pull rate moves, no scoring
formula is reimplemented, and the loose-pack simulator still runs exactly once
per set. Stage 2's whole contribution is deciding WHICH products are eligible,
proving what is inside them, valuing the certain part, and handing the composed
vector to the existing scorer.

ELIGIBILITY IS DATA, NOT NAMING
-------------------------------
A SKU is Stage 2 scorable if and only if it has an active VERIFIED composition
row keyed on its own ``sealed_product_id``. The classifier proposes candidates -
it is good at "this is an ETB" - but it cannot know which promo a particular
artwork variant guarantees, and it will happily classify a case or a two-box
listing into a Stage 2 family. Composition, not the name, decides. That is why
cases and ``[Set of 2]`` listings need no exclusion rule here: nobody researched
a composition for them, so they are never eligible, and the manifest records why.

EVERY REJECTION IS NAMED
------------------------
There are no silent omissions. A Stage 2 family SKU that is not scored carries
exactly one machine-readable reason, and the set of reasons is closed:

    unresolved_composition                          no verified composition row
    guaranteed_component_market_price_unavailable   a promo has no valid price
    missing_product_market_price                    the SKU has no price of its own
"""

from __future__ import annotations

import logging
import time
from typing import Any, Dict, List, Mapping, Optional, Sequence

import numpy as np

from backend.calculations.evr.guaranteed_component_value import (
    GUARANTEED_COMPONENT_MODEL_VERSION,
    compose_stage2_distribution,
)
from backend.domain.pokemon.sealed_product_classifier import classify_sealed_product
from backend.domain.pokemon.sealed_product_stage2_composition import (
    ACCESSORY_VALUE_INCLUDED,
    COLLECTOR_APPEAL_SCOPE,
    REASON_MISSING_PRODUCT_PRICE,
    REASON_MISSING_PROMO_PRICE,
    REASON_NO_VERIFIED_COMPOSITION,
    STAGE2_COMPOSITION_CONTRACT_VERSION,
    STAGE2_FAMILIES,
    is_stage2_family,
    parse_composition_row,
    stage2_composition_scope_contract,
)

logger = logging.getLogger(__name__)

STAGE2_SERVICE_VERSION = "sealed-product-rip-stage2-v1"


def _resolve_family(product: Mapping[str, Any]) -> str:
    """The snapshot's classifier verdict, or the SAME canonical classifier.

    Identical to the Stage 1 helper by design: two ways of deciding a product's
    family is one too many, and this must agree with Stage 1 about which
    products it is NOT claiming.
    """
    family = str(product.get("productFamily") or "").strip()
    if family:
        return family
    return str(classify_sealed_product(product.get("name")).get("productFamily"))


def _positive_price(value: Any) -> Optional[float]:
    try:
        price = float(value)
    except (TypeError, ValueError):
        return None
    if not np.isfinite(price) or price <= 0.0:
        return None
    return price


def select_stage2_products(
    snapshot_payload: Optional[Mapping[str, Any]],
    *,
    compositions_fn=None,
) -> Dict[str, Any]:
    """Split a sealed market snapshot into Stage 2 candidates and named skips.

    ``compositions_fn`` takes a list of sealed product ids and returns verified
    composition rows. Injected so selection is testable without a database and so
    the caller controls how many round trips a set costs.
    """
    if compositions_fn is None:
        from backend.db.repositories.sealed_product_compositions_repository import (
            get_verified_compositions_for_products as compositions_fn,  # type: ignore[misc]
        )

    products = (snapshot_payload or {}).get("products") or []
    family_by_id: Dict[str, str] = {}
    product_by_id: Dict[str, Mapping[str, Any]] = {}

    for product in products:
        if not isinstance(product, Mapping):
            continue
        family = _resolve_family(product)
        if not is_stage2_family(family):
            # Not a Stage 2 product. Stage 1 reports its own families; this path
            # stays silent about them rather than double-counting every SKU.
            continue
        product_id = product.get("sealedProductId")
        if product_id is None:
            continue
        family_by_id[str(product_id)] = family
        product_by_id[str(product_id)] = product

    if not product_by_id:
        return {"candidates": [], "skipped": [], "familyCandidateCount": 0}

    composition_rows = compositions_fn(sorted(product_by_id))
    compositions = {
        str(row["sealed_product_id"]): parse_composition_row(row) for row in composition_rows
    }

    candidates: List[Dict[str, Any]] = []
    skipped: List[Dict[str, Any]] = []

    for product_id, product in product_by_id.items():
        family = family_by_id[product_id]
        composition = compositions.get(product_id)
        if composition is None:
            # Cases, [Set of 2] listings, unverified retailer variants and any
            # SKU nobody has researched all land here. One reason, no guessing.
            skipped.append(
                {
                    "sealedProductId": product_id,
                    "name": product.get("name"),
                    "productFamily": family,
                    "reason": REASON_NO_VERIFIED_COMPOSITION,
                }
            )
            continue

        price = _positive_price(product.get("currentPrice"))
        if price is None:
            skipped.append(
                {
                    "sealedProductId": product_id,
                    "name": product.get("name"),
                    "productFamily": family,
                    "reason": REASON_MISSING_PRODUCT_PRICE,
                    "currentPrice": product.get("currentPrice"),
                }
            )
            continue

        candidates.append(
            {
                "sealed_product_id": product_id,
                "name": product.get("name"),
                "product_family": family,
                "composition": composition,
                "product_market_cost": price,
                "price_as_of": product.get("priceAsOf"),
                "price_source": product.get("source"),
            }
        )

    return {
        "candidates": candidates,
        "skipped": skipped,
        "familyCandidateCount": len(product_by_id),
    }


def price_stage2_candidates(
    candidates: Sequence[Mapping[str, Any]],
    *,
    pricing_fn=None,
    client: Any = None,
) -> Dict[str, Any]:
    """Attach guaranteed-component prices, dropping candidates that lack any.

    Prices are looked up ONCE for the whole batch of distinct variants rather
    than per candidate: two ETB artwork variants of the same set frequently
    guarantee overlapping printings, and a PC ETB shares its ordinary promo with
    the standard ETB.
    """
    if pricing_fn is None:
        from backend.db.services.guaranteed_component_pricing_service import (
            price_guaranteed_components as pricing_fn,  # type: ignore[misc]
        )

    started = time.perf_counter()
    priced_candidates: List[Dict[str, Any]] = []
    skipped: List[Dict[str, Any]] = []

    for candidate in candidates:
        composition = candidate["composition"]
        result = pricing_fn(composition.guaranteed_card_components, client=client)
        if result["missing"]:
            # A single unpriced guaranteed card makes the WHOLE product
            # unscorable. Valuing the rest would publish a number that is
            # confidently too low while looking complete.
            skipped.append(
                {
                    "sealedProductId": candidate["sealed_product_id"],
                    "name": candidate.get("name"),
                    "productFamily": candidate["product_family"],
                    "reason": REASON_MISSING_PROMO_PRICE,
                    "missingComponents": result["missing"],
                }
            )
            continue
        priced_candidates.append({**candidate, "priced_components": result["priced"]})

    return {
        "candidates": priced_candidates,
        "skipped": skipped,
        "elapsedMs": round((time.perf_counter() - started) * 1000.0, 3),
    }


def required_pack_counts(candidates: Sequence[Mapping[str, Any]]) -> List[int]:
    """The distinct K values Stage 2 needs from the shared bootstrap.

    Returned so the orchestrator can request Stage 1's and Stage 2's counts in
    ONE call. That is what makes an Enhanced Booster Box reuse the standard
    Booster Box's Y36 instead of generating a second, RNG-different copy of the
    same distribution.
    """
    return sorted({int(c["composition"].total_pack_count) for c in candidates})


def compose_stage2_product(
    candidate: Mapping[str, Any],
    random_distribution: Any,
) -> Dict[str, Any]:
    """The composed outcome vector and composition economics for one SKU.

    ``random_distribution`` is the SHARED K-pack vector. It is not modified: two
    ETB variants with the same pack count and different promos both read it, and
    the composition returns a new array each time.
    """
    composed = compose_stage2_distribution(random_distribution, candidate["priced_components"])
    return composed


def stage2_row_fields(
    candidate: Mapping[str, Any],
    composition_meta: Mapping[str, Any],
) -> Dict[str, Any]:
    """The Stage 2-specific columns of a result row.

    These record what was SCORED, not what is in the box - the composition tables
    remain authoritative for contents. ``composition_id`` and
    ``composition_version`` are what let a historical score be attributed to the
    exact research that produced it.
    """
    composition = candidate["composition"]
    return {
        "composition_id": composition.composition_id,
        "composition_version": composition.composition_version,
        "random_pack_count": int(composition.total_pack_count),
        "random_pack_expected_value": composition_meta.get("randomPackExpectedValue"),
        "guaranteed_component_count": int(composition_meta.get("guaranteedCardCount") or 0),
        "guaranteed_component_market_value": composition_meta.get("totalGuaranteedValue"),
        "guaranteed_value_share_of_expected_value": composition_meta.get(
            "guaranteedValueShareOfExpectedValue"
        ),
        "accessory_value_included": ACCESSORY_VALUE_INCLUDED,
    }


def stage2_scope_contract() -> Dict[str, Any]:
    """Stage 2's disclosure block for summaries and reports."""
    return {
        "stage2ServiceVersion": STAGE2_SERVICE_VERSION,
        "guaranteedComponentModelVersion": GUARANTEED_COMPONENT_MODEL_VERSION,
        **stage2_composition_scope_contract(),
    }
