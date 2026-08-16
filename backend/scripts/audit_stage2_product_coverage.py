"""Stage 2 target-cohort manifest.

Answers, for the CURRENT simulation-supported cohort and from real data only:
which Elite Trainer Box, Pokemon Center Elite Trainer Box and Enhanced Booster
Box SKUs exist, which have a verified composition, which of those can actually be
priced, and - for every SKU that cannot be scored - exactly why.

READ-ONLY. It writes nothing, scores nothing and simulates nothing. Its output is
the "no silent omissions" record: every candidate SKU appears in it exactly once
with exactly one status.

    python -m backend.scripts.audit_stage2_product_coverage
    python -m backend.scripts.audit_stage2_product_coverage --json
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from collections import Counter, defaultdict
from typing import Any, Dict, List

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))

from backend.db.clients.supabase_client import supabase  # noqa: E402
from backend.db.repositories.sealed_product_compositions_repository import (  # noqa: E402
    get_verified_compositions_for_products,
)
from backend.db.services.guaranteed_component_pricing_service import (  # noqa: E402
    get_latest_near_mint_prices,
)
from backend.domain.pokemon.sealed_product_classifier import classify_sealed_product  # noqa: E402
from backend.domain.pokemon.sealed_product_stage2_composition import (  # noqa: E402
    REASON_MISSING_PROMO_PRICE,
    REASON_NO_VERIFIED_COMPOSITION,
    STAGE2_FAMILIES,
    parse_composition_row,
)

# Statuses a candidate can hold. Closed set: a SKU with no status is a bug in
# this script, not an absent product.
STATUS_SUPPORTED_VERIFIED = "supported_verified"
STATUS_EXCLUDED_CASE = "excluded_case"
STATUS_EXCLUDED_SET_OF_MULTIPLE = "excluded_set_of_multiple"
STATUS_UNRESOLVED_COMPOSITION = "unresolved_composition"
STATUS_MISSING_PROMO_PRICE = REASON_MISSING_PROMO_PRICE
STATUS_MISSING_PRODUCT_PRICE = "missing_product_market_price"


def _supported_sets() -> List[Dict[str, Any]]:
    response = (
        supabase.table("sets")
        .select("id,canonical_key,name,release_date")
        .eq("supports_opening_simulation", True)
        .order("release_date")
        .execute()
    )
    return list(response.data or [])


def _sealed_products(set_ids: List[str]) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    # Chunked because the supported cohort is large enough for a single `in_`
    # filter to produce an unreasonable URL.
    for start in range(0, len(set_ids), 25):
        response = (
            supabase.table("sealed_products")
            .select("id,set_id,name")
            .in_("set_id", set_ids[start : start + 25])
            .execute()
        )
        rows.extend(list(response.data or []))
    return rows


def _latest_market_prices(product_ids: List[str]) -> Dict[str, Dict[str, Any]]:
    """Current sealed market price per SKU, from the canonical sealed source."""
    prices: Dict[str, Dict[str, Any]] = {}
    for start in range(0, len(product_ids), 50):
        response = (
            supabase.table("sealed_product_market_usd_latest")
            .select("sealed_product_id,market_price,captured_at,source")
            .in_("sealed_product_id", product_ids[start : start + 50])
            .execute()
        )
        for row in list(response.data or []):
            prices[str(row["sealed_product_id"])] = row
    return prices


def build_manifest() -> Dict[str, Any]:
    sets = _supported_sets()
    set_by_id = {str(row["id"]): row for row in sets}
    products = _sealed_products(sorted(set_by_id))

    candidates: List[Dict[str, Any]] = []
    for product in products:
        classification = classify_sealed_product(product.get("name"))
        family = str(classification["productFamily"])
        name = str(product.get("name") or "")
        lowered = name.lower()

        # A case or multi-box listing is classified into its own family, but it
        # is reported here rather than dropped: "we saw it and it is not one
        # retail opening" is information, and silence is not.
        if family not in STAGE2_FAMILIES:
            if "elite trainer box" in lowered or "enhanced booster" in lowered:
                status = (
                    STATUS_EXCLUDED_CASE
                    if classification["isCase"]
                    else STATUS_EXCLUDED_SET_OF_MULTIPLE
                )
                candidates.append(
                    {
                        "set": set_by_id[str(product["set_id"])]["canonical_key"],
                        "sealedProductId": str(product["id"]),
                        "name": name,
                        "family": family,
                        "status": status,
                    }
                )
            continue

        candidates.append(
            {
                "set": set_by_id[str(product["set_id"])]["canonical_key"],
                "sealedProductId": str(product["id"]),
                "name": name,
                "family": family,
                "status": None,
            }
        )

    open_ids = [c["sealedProductId"] for c in candidates if c["status"] is None]
    compositions = {
        str(row["sealed_product_id"]): parse_composition_row(row)
        for row in get_verified_compositions_for_products(open_ids)
    }
    market_prices = _latest_market_prices(open_ids)

    # One batched price lookup for every guaranteed printing in the cohort.
    variant_ids = sorted(
        {
            component.card_variant_id
            for composition in compositions.values()
            for component in composition.guaranteed_card_components
        }
    )
    promo_prices = get_latest_near_mint_prices(variant_ids) if variant_ids else {}

    for candidate in candidates:
        if candidate["status"] is not None:
            continue
        product_id = candidate["sealedProductId"]
        composition = compositions.get(product_id)
        if composition is None:
            candidate["status"] = STATUS_UNRESOLVED_COMPOSITION
            continue

        candidate["compositionVersion"] = composition.composition_version
        candidate["packCount"] = composition.total_pack_count
        candidate["packSetId"] = composition.random_pack_set_id
        candidate["sourceType"] = composition.source_type
        candidate["sourceReference"] = composition.source_reference
        candidate["verifiedAt"] = str(composition.verified_at)
        candidate["guaranteedComponents"] = [
            {
                **component.as_payload(),
                "marketPrice": (promo_prices.get(component.card_variant_id) or {}).get(
                    "market_price"
                ),
                "capturedAt": str(
                    (promo_prices.get(component.card_variant_id) or {}).get("captured_at")
                ),
            }
            for component in composition.guaranteed_card_components
        ]

        unpriced = [
            component.card_variant_id
            for component in composition.guaranteed_card_components
            if component.card_variant_id not in promo_prices
        ]
        if unpriced:
            candidate["status"] = STATUS_MISSING_PROMO_PRICE
            candidate["unpricedComponents"] = unpriced
            continue

        market = market_prices.get(product_id)
        if not market or not market.get("market_price"):
            candidate["status"] = STATUS_MISSING_PRODUCT_PRICE
            continue

        candidate["sealedMarketPrice"] = float(market["market_price"])
        candidate["guaranteedValue"] = sum(
            promo_prices[c.card_variant_id]["market_price"] * c.quantity
            for c in composition.guaranteed_card_components
        )
        candidate["status"] = STATUS_SUPPORTED_VERIFIED

    by_family: Dict[str, Counter] = defaultdict(Counter)
    for candidate in candidates:
        by_family[candidate["family"]][candidate["status"]] += 1

    return {
        "supportedSetCount": len(sets),
        "candidateCount": len(candidates),
        "byFamily": {family: dict(counts) for family, counts in sorted(by_family.items())},
        "statusTotals": dict(Counter(c["status"] for c in candidates)),
        "candidates": sorted(candidates, key=lambda c: (c["set"], c["name"])),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--json", action="store_true", help="emit the full manifest as JSON")
    args = parser.parse_args()

    manifest = build_manifest()
    if args.json:
        print(json.dumps(manifest, indent=2, default=str))
        return 0

    print(f"supported sets: {manifest['supportedSetCount']}")
    print(f"stage 2 candidate SKUs: {manifest['candidateCount']}")
    print("\nby family:")
    for family, counts in manifest["byFamily"].items():
        print(f"  {family}")
        for status, count in sorted(counts.items(), key=lambda item: str(item[0])):
            print(f"      {status}: {count}")
    print("\ntotals by status:")
    for status, count in sorted(manifest["statusTotals"].items(), key=lambda i: str(i[0])):
        print(f"  {status}: {count}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
