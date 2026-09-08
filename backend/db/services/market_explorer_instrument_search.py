"""Bounded search over Market Explorer's canonical eligible instruments."""

from __future__ import annotations

from typing import Any

from backend.db.services.pokemon_global_sealed_market_service import collect_global_sealed_products

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
        snapshots = list((client.table("pokemon_set_sealed_market_snapshot_latest")
                          .select("set_id,market_date,payload_json").eq("tcg", "pokemon")
                          .order("set_id").execute()).data or [])
        latest = max((str(row.get("market_date") or "")[:10] for row in snapshots), default="")
        products, _ = collect_global_sealed_products(
            [row.get("payload_json") or {} for row in snapshots], market_date=latest,
        )
        set_names = {str((row.get("payload_json") or {}).get("set", {}).get("id") or row.get("set_id")):
                     (row.get("payload_json") or {}).get("set", {}).get("name") for row in snapshots}
        set_id_by_product = {}
        for row in snapshots:
            payload = row.get("payload_json") or {}
            owning_set_id = str(payload.get("set", {}).get("id") or row.get("set_id") or "")
            for product in payload.get("products") or []:
                set_id_by_product[str(product.get("sealedProductId") or "")] = owning_set_id
        for product in products:
            name = str(product.get("name") or "")
            if needle.casefold() not in name.casefold():
                continue
            product_id = str(product.get("sealedProductId") or "")
            set_id = set_id_by_product.get(product_id, "")
            results.append({
                "asset": "sealed", "instrumentId": product_id,
                "name": name, "label": name, "setId": set_id,
                "setName": set_names.get(set_id), "imageUrl": product.get("imageUrl"),
                "productType": product.get("productFamily"),
                "productFamily": product.get("productFamily"),
                "variantLabel": product.get("variantLabel"),
            })

    results = [row for row in results if row.get("instrumentId")]
    results.sort(key=lambda row: (str(row.get("name") or "").casefold(), row["asset"], row["instrumentId"]))
    return {"query": needle, "asset": asset, "limit": cap, "items": results[:cap]}
