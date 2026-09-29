"""Privacy-safe normalization and summaries for bounded active-supply evidence."""
from __future__ import annotations

import hashlib
import hmac
from datetime import datetime
from decimal import Decimal, InvalidOperation
from typing import Any, Mapping, Sequence


def _money(value: Any, *, required: bool = True) -> Decimal | None:
    if value is None and not required:
        return None
    try:
        out = Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError) as exc:
        raise ValueError("invalid listing money") from exc
    if not out.is_finite() or out < 0 or out.as_tuple().exponent < -2:
        raise ValueError("invalid listing money")
    return out.quantize(Decimal("0.01"))


def seller_hash(value: Any, secret: str) -> str:
    raw = str(value or "").strip()
    if not raw:
        raise ValueError("seller identity missing")
    if len(secret) < 32:
        raise ValueError("seller hash key must contain at least 32 characters")
    digest = hmac.new(secret.encode(), raw.encode(), hashlib.sha256).hexdigest()
    return f"hmac-sha256:v1:{digest}"


def _timestamp(value: Any) -> str | None:
    text = str(value or "").strip()
    if not text:
        return None
    try:
        datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError("invalid listing timestamp") from exc
    return text


def normalize_listing(
    row: Mapping[str, Any], *, rank: int, seller_hash_key: str
) -> dict[str, Any]:
    listing_id = row.get("id") or row.get("listing_id")
    if listing_id is None:
        raise ValueError("listing id missing")
    seller = row.get("seller") if isinstance(row.get("seller"), Mapping) else {}
    seller_identity = (
        seller.get("id") or seller.get("seller_id") or seller.get("name")
        or row.get("seller_id") or row.get("seller_name")
    )
    item = _money(row.get("price"))
    shipping = _money(row.get("shipping_price"), required=False) or Decimal("0.00")
    quantity = int(row.get("quantity") or 1)
    if quantity <= 0:
        raise ValueError("invalid listing quantity")
    currency = str(row.get("currency") or "USD").upper()
    if len(currency) != 3:
        raise ValueError("invalid listing currency")
    # Deliberately curate this payload. Never copy provider rows because they may
    # acquire raw seller identifiers without a code review.
    safe_payload = {
        "printing": row.get("printing"),
        "condition": row.get("condition"),
        "language": row.get("language"),
        "seller_rating": seller.get("rating") or row.get("seller_rating"),
        "seller_sales_count": seller.get("sales_count") or row.get("seller_sales_count"),
    }
    return {
        "source_listing_id": str(listing_id),
        "source_seller_id": seller_hash(seller_identity, seller_hash_key),
        "quantity": quantity,
        "item_price": str(item),
        "shipping_price": str(shipping),
        "landed_price": str(item + shipping),
        "currency": currency,
        "source_rank": int(rank),
        "listing_updated_at": _timestamp(row.get("updated_at")),
        "provider_snapshot_at": _timestamp(row.get("snapshot_at")),
        "seller_rating": safe_payload["seller_rating"],
        "seller_sales_count": safe_payload["seller_sales_count"],
        "source_payload": {k: v for k, v in safe_payload.items() if v is not None},
    }


def _percentile(values: Sequence[Decimal], fraction: Decimal) -> Decimal | None:
    if not values:
        return None
    ordered = sorted(values)
    position = (len(ordered) - 1) * fraction
    low = int(position)
    high = min(low + 1, len(ordered) - 1)
    weight = position - low
    return (ordered[low] + (ordered[high] - ordered[low]) * weight).quantize(Decimal("0.01"))


def summarize(listings: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    prices = [Decimal(str(row["landed_price"])) for row in listings]
    quantities = [int(row["quantity"]) for row in listings]
    seller_qty: dict[str, int] = {}
    for row, quantity in zip(listings, quantities):
        seller = str(row["source_seller_id"])
        seller_qty[seller] = seller_qty.get(seller, 0) + quantity
    total_qty = sum(quantities)
    median = _percentile(prices, Decimal("0.5"))
    deviations = [abs(price - median) for price in prices] if median is not None else []
    lowest = min(prices) if prices else None
    bands = {"at_lowest": 0, "within_5pct": 0, "within_10pct": 0, "within_25pct": 0}
    if lowest is not None:
        for price, quantity in zip(prices, quantities):
            if price == lowest:
                bands["at_lowest"] += quantity
            if price <= lowest * Decimal("1.05"):
                bands["within_5pct"] += quantity
            if price <= lowest * Decimal("1.10"):
                bands["within_10pct"] += quantity
            if price <= lowest * Decimal("1.25"):
                bands["within_25pct"] += quantity
    concentration = (
        sum((Decimal(q) / Decimal(total_qty)) ** 2 for q in seller_qty.values())
        if total_qty else None
    )
    return {
        "captured_listing_count": len(listings),
        "captured_quantity": total_qty,
        "distinct_seller_count": len(seller_qty),
        "seller_concentration_hhi": str(concentration.quantize(Decimal("0.000001"))) if concentration is not None else None,
        "lowest_landed_ask": str(lowest) if lowest is not None else None,
        "median_landed_ask": str(median) if median is not None else None,
        "landed_ask_q1": str(_percentile(prices, Decimal("0.25"))) if prices else None,
        "landed_ask_q3": str(_percentile(prices, Decimal("0.75"))) if prices else None,
        "landed_ask_mad": str(_percentile(deviations, Decimal("0.5"))) if deviations else None,
        "price_depth_bands": bands,
    }
