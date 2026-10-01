"""Read-only, exact single-instrument Market Explorer projection.

This is intentionally not the Exact Basket builder. It accepts one stable
catalogue identity, verifies it against the canonical Explorer authorities and
returns that instrument's already-published price history.
"""
from __future__ import annotations

from datetime import date
from typing import Any
from uuid import UUID


class DirectInstrumentError(ValueError):
    def __init__(self, code: str, message: str, status_code: int = 400) -> None:
        super().__init__(message)
        self.code, self.message, self.status_code = code, message, status_code


def _rows(result: Any) -> list[dict[str, Any]]:
    return [dict(row) for row in (getattr(result, "data", None) or [])]


def _execute(query: Any) -> list[dict[str, Any]]:
    return _rows(query.execute())


def _uuid(value: str) -> str:
    try:
        return str(UUID(str(value)))
    except (TypeError, ValueError) as exc:
        raise DirectInstrumentError("DIRECT_INSTRUMENT_ID_INVALID", "A valid instrument ID is required.") from exc


def _indexed(points: list[dict[str, Any]]) -> list[dict[str, Any]]:
    positive = [(str(row["date"])[:10], float(row["price"])) for row in points
                if row.get("price") is not None and float(row["price"]) > 0]
    if not positive:
        return []
    base = positive[0][1]
    return [{"date": day, "rawPrice": price, "indexValue": price / base * 100.0}
            for day, price in positive]


def _card(client: Any, instrument_id: str) -> dict[str, Any]:
    metadata = _execute(client.table("pokemon_market_explorer_card_current_metadata")
                        .select("*").eq("card_variant_id", instrument_id).limit(1))
    if not metadata:
        raise DirectInstrumentError("DIRECT_INSTRUMENT_UNKNOWN", "Card instrument is not in the canonical catalogue.", 404)
    item = metadata[0]
    history = _execute(client.table("pokemon_market_explorer_card_daily_states_v2_shadow")
                       .select("market_date,market_price,set_id")
                       .eq("card_variant_id", instrument_id).order("market_date"))
    points = [{"date": row.get("market_date"), "price": row.get("market_price")} for row in history]
    set_rows = _execute(client.table("sets").select("name").eq("id", item.get("set_id")).limit(1))
    set_name = set_rows[0].get("name") if set_rows else None
    row = {
        "rank": 1, "canonicalCardId": item.get("canonical_card_id"),
        "cardVariantId": instrument_id, "cardName": item.get("card_name"),
        "setName": set_name, "rarity": item.get("rarity"),
        "edition": item.get("edition"), "printingType": item.get("printing_type"),
        "specialType": item.get("special_type"),
        "marketPrice": float(points[-1]["price"]) if points else None,
        "imageUrl": item.get("image_url"), "changes": {},
    }
    return {"asset": "cards", "label": item.get("card_name"), "setName": set_name,
            "imageUrl": item.get("image_url"), "constituent": row, "points": points}


def _sealed(client: Any, instrument_id: str) -> dict[str, Any]:
    metadata = _execute(client.table("pokemon_market_explorer_sealed_current_metadata_v1")
                        .select("*").eq("sealed_product_id", instrument_id).limit(1))
    if not metadata:
        raise DirectInstrumentError("DIRECT_INSTRUMENT_UNKNOWN", "Sealed product is not in the canonical catalogue.", 404)
    item = metadata[0]
    history = _execute(client.table("sealed_product_price_observations")
                       .select("captured_at,market_price,currency,source,id")
                       .eq("sealed_product_id", instrument_id)
                       .order("captured_at").order("id"))
    by_day: dict[str, float] = {}
    for observation in history:
        if str(observation.get("currency") or "USD").strip().upper() != "USD":
            continue
        price = observation.get("market_price")
        if price is not None and float(price) > 0:
            by_day[str(observation.get("captured_at"))[:10]] = float(price)
    points = [{"date": day, "price": price} for day, price in sorted(by_day.items())]
    row = {
        "rank": 1, "sealedProductId": instrument_id,
        "productName": item.get("name"), "setName": item.get("set_name"),
        "productFamily": item.get("product_family"),
        "productFamilyLabel": item.get("product_family_label"),
        "variantLabel": item.get("variant_label"),
        "marketPrice": float(points[-1]["price"]) if points else None,
        "imageUrl": item.get("image_small_url") or item.get("image_large_url"),
        "changes": {},
    }
    return {"asset": "sealed", "label": item.get("name"), "setName": item.get("set_name"),
            "imageUrl": row["imageUrl"], "constituent": row, "points": points}


def read_direct_instrument(client: Any, asset: str, instrument_id: str,
                           start_date: date | None = None) -> dict[str, Any]:
    asset = str(asset or "").strip().lower()
    if asset not in ("cards", "sealed"):
        raise DirectInstrumentError("DIRECT_INSTRUMENT_ASSET_UNSUPPORTED", "Direct view supports Cards and Sealed only.")
    identity = _uuid(instrument_id)
    source = _card(client, identity) if asset == "cards" else _sealed(client, identity)
    history = _indexed(source.pop("points"))
    if start_date is not None:
        history = [point for point in history if point["date"] >= start_date.isoformat()]
    if not history:
        raise DirectInstrumentError("DIRECT_INSTRUMENT_HISTORY_UNAVAILABLE", "No canonical price history is available.", 404)
    constituent = source.pop("constituent")
    return {
        "kind": "directInstrument", "seriesKey": f"direct:{asset}:{identity}",
        "instrumentId": identity, **source, "asOf": history[-1]["date"],
        "currentPrice": history[-1]["rawPrice"], "historyStart": history[0]["date"],
        "historyEnd": history[-1]["date"], "history": history,
        "inspectability": {"kind": "single_item", "totalCount": 1},
        "constituents": {"idField": "cardVariantId" if asset == "cards" else "sealedProductId",
                         "totalCount": 1, "isComplete": True, "asOf": history[-1]["date"],
                         "topConstituents": [constituent]},
    }


__all__ = ["DirectInstrumentError", "read_direct_instrument"]
