"""Ingest exact stamped box-topper variants by stable TCGplayer product identity.

This is intentionally a tiny, reviewed registry rather than a name-based card
scrape.  TCGplayer lists these enhanced-box toppers in Miscellaneous Cards &
Products, outside the normal expansion price-guide feeds.  The provider product
ID is therefore the durable identity; the local card and treatment are asserted
and checked before any write.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
from typing import Any, Dict

import requests

from backend.Scraper.helpers.card_helper import build_external_variant_key

from backend.db.clients.supabase_client import supabase
from backend.db.repositories.card_variant_repository import (
    get_card_variant_by_card_and_type,
    get_card_variant_external_identity,
    insert_card_variant,
    link_card_variant_external_identity,
)
from backend.db.repositories.card_variant_prices_repository import insert_card_variant_price
from backend.db.services.guaranteed_component_pricing_service import (
    get_latest_near_mint_prices,
    resolve_near_mint_condition_id,
)

STAMPED_PRODUCTS: Dict[str, Dict[str, str]] = {
    "623594": {
        "card_id": "68372a3f-bf23-401d-bbc9-dc7dfdfd1b67",
        "ordinary_variant_id": "e4d37898-c561-4b7b-85e2-d88e1caf71e1",
        "name": "N's Reshiram - 167/159 (Journey Together Stamped)",
        "special_type": "journey-together-stamped",
    },
    "654703": {
        "card_id": "e74d54df-a328-419a-b618-83c3639e7750",
        "ordinary_variant_id": "ba7e74fb-58d2-4801-bed6-8e89d8ab812d",
        "name": "Bulbasaur - 133/132 (Mega Evolution Stamped)",
        "special_type": "mega-evolution-stamped",
    },
}

def _external_identity_payload(product_id: str, spec: Dict[str, str]) -> Dict[str, Any]:
    return {
        "provider": "tcgplayer", "external_product_id": product_id,
        "external_variant_key": build_external_variant_key(
            None, "holo", spec["special_type"]),
        "external_catalog_key": "miscellaneous-cards-and-products",
        "source_reference": f"https://www.tcgplayer.com/product/{product_id}",
        "source_payload": {"productName": spec["name"],
                           "treatment": spec["special_type"]},
    }


def _current_nm_market_price(product_id: str) -> float:
    url = f"https://infinite-api.tcgplayer.com/price/history/{product_id}/detailed?range=quarter"
    response = requests.get(url, timeout=30)
    response.raise_for_status()
    rows = response.json().get("result") or []
    nm = [r for r in rows if r.get("condition") == "Near Mint" and r.get("language") == "English"]
    if len(nm) != 1 or not nm[0].get("buckets"):
        raise RuntimeError(f"TCGplayer product {product_id} has no unique English NM price history")
    price = float(nm[0]["buckets"][0]["marketPrice"])
    if price <= 0:
        raise RuntimeError(f"TCGplayer product {product_id} has no positive current NM market price")
    return price


def ingest(*, commit: bool) -> Dict[str, Any]:
    results = []
    near_mint_id = resolve_near_mint_condition_id(supabase)
    today = dt.date.today().isoformat()
    for product_id, spec in STAMPED_PRODUCTS.items():
        identity = get_card_variant_external_identity("tcgplayer", product_id)
        variant = None
        if identity:
            variant = supabase.table("card_variants").select("*").eq("id", identity["card_variant_id"]).single().execute().data
        else:
            variant = get_card_variant_by_card_and_type(
                spec["card_id"], "holo", spec["special_type"], None
            )
        if variant:
            actual = (str(variant["card_id"]), variant.get("printing_type"), variant.get("special_type"))
            expected = (spec["card_id"], "holo", spec["special_type"])
            if actual != expected:
                raise RuntimeError(f"TCGplayer product {product_id} treatment collision: {actual} != {expected}")

        price = _current_nm_market_price(product_id)
        if not commit:
            results.append({"productId": product_id, "variantId": variant and variant["id"], "price": price, "action": "would_ingest"})
            continue

        variant_id = str(variant["id"]) if variant else str(insert_card_variant({
            "card_id": spec["card_id"], "printing_type": "holo",
            "special_type": spec["special_type"], "edition": None,
        }))
        if variant_id == spec["ordinary_variant_id"]:
            raise RuntimeError(f"TCGplayer product {product_id} resolved to the ordinary printing")
        link_card_variant_external_identity(
            variant_id, _external_identity_payload(product_id, spec))
        current = get_latest_near_mint_prices([variant_id]).get(variant_id)
        if not current or str(current.get("captured_at"))[:10] != today or float(current["market_price"]) != price:
            insert_card_variant_price({
                "card_variant_id": variant_id, "condition_id": near_mint_id,
                "market_price": price, "currency": "USD", "source": "TCGPlayer",
                "captured_at": today, "high_price": None, "low_price": None,
            })
        results.append({"productId": product_id, "variantId": variant_id, "price": price, "action": "ingested"})
    return {"mode": "commit" if commit else "dry_run", "products": results}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--commit", action="store_true")
    args = parser.parse_args()
    print(json.dumps(ingest(commit=args.commit), indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
