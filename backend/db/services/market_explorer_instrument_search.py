"""Bounded search over Market Explorer's canonical eligible instruments."""

from __future__ import annotations

from typing import Any

MIN_QUERY_LENGTH = 2
MAX_RESULTS = 50


def search_market_explorer_instruments(client: Any, *, q: str, asset: str = "all",
                                       limit: int = 20) -> dict[str, Any]:
    needle = str(q or "").strip()
    if len(needle) < MIN_QUERY_LENGTH:
        raise ValueError(f"q must contain at least {MIN_QUERY_LENGTH} characters")
    if asset not in ("all", "cards", "sealed"):
        raise ValueError("asset must be all, cards, or sealed")
    cap = max(1, min(int(limit), MAX_RESULTS))
    results: list[dict[str, Any]] = []

    if asset in ("all", "cards"):
        rows = list((client.table("pokemon_market_explorer_card_current_metadata")
                     .select("card_variant_id,set_id,card_name,card_number,rarity,edition,printing_type,special_type,image_url")
                     .ilike("card_name", f"%{needle}%")
                     .order("card_name").order("card_variant_id").limit(cap).execute()).data or [])
        set_ids = sorted({str(row.get("set_id") or "") for row in rows} - {""})
        set_rows = list((client.table("sets").select("id,name").in_("id", set_ids).execute()).data or []) if set_ids else []
        set_names = {str(row.get("id")): row.get("name") for row in set_rows}
        results.extend({
            "asset": "cards", "instrumentId": str(row["card_variant_id"]),
            "name": row.get("card_name"), "label": row.get("card_name"),
            "setId": str(row.get("set_id") or ""),
            "setName": set_names.get(str(row.get("set_id") or "")),
            "imageUrl": row.get("image_url"), "cardNumber": row.get("card_number"),
            "rarity": row.get("rarity"), "edition": row.get("edition"),
            "printingType": row.get("printing_type"), "specialType": row.get("special_type"),
        } for row in rows)

    if asset in ("all", "sealed"):
        products = list((client.rpc("search_pokemon_market_explorer_sealed_instruments", {
            "p_query": needle, "p_limit": cap,
        }).execute()).data or [])
        for product in products:
            name = str(product.get("product_name") or "")
            product_id = str(product.get("sealed_product_id") or "")
            set_id = str(product.get("set_id") or "")
            results.append({
                "asset": "sealed", "instrumentId": product_id,
                "name": name, "label": name, "setId": set_id,
                "setName": product.get("set_name"), "imageUrl": product.get("image_url"),
                "productType": product.get("product_family"),
                "productFamily": product.get("product_family"),
                "variantLabel": product.get("variant_label"),
            })

    results = [row for row in results if row.get("instrumentId")]
    results.sort(key=lambda row: (str(row.get("name") or "").casefold(), row["asset"], row["instrumentId"]))
    return {"query": needle, "asset": asset, "limit": cap, "items": results[:cap]}
