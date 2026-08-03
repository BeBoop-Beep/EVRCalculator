"""Build and persist prepared per-set sealed market snapshots."""

from __future__ import annotations

import hashlib
import json
import math
from datetime import date, datetime, timedelta, timezone
from typing import Any, Dict, Iterable, List, Optional

from backend.domain.pokemon.sealed_product_classifier import (
    CLASSIFICATION_VERSION,
    classify_sealed_product,
)

SNAPSHOT_CONTRACT_VERSION = "pokemon-set-sealed-market-v3"
WINDOW_DAYS = {"7D": 7, "30D": 30, "3M": 90, "6M": 180, "1Y": 365}
MOVEMENT_WINDOWS = ("1D", "7D", "30D", "3M", "6M", "1Y", "lifetime")
# Retained as product-family metadata for consumers; product ordering itself is
# now driven by current market price rather than by family.
FAMILY_PRIORITY = {
    "booster_box": 0,
    "enhanced_booster_box": 1,
    "elite_trainer_box": 2,
    "pokemon_center_elite_trainer_box": 3,
    "booster_bundle": 4,
    "booster_pack": 5,
    "sleeved_booster_pack": 6,
}


def product_sort_key(item: Dict[str, Any]) -> tuple:
    """Order sealed products most expensive first.

    Missing or non-positive prices are handled explicitly rather than being
    left to float comparison, so they sort last instead of ordering on NaN.
    Ties break deterministically on the concise family label, the full product
    name, then the product id.
    """
    try:
        price = float(item.get("currentPrice"))
    except (TypeError, ValueError):
        price = None
    has_price = price is not None and price == price and price > 0
    label = item.get("variantLabel") or item.get("productFamilyLabel") or ""
    return (
        0 if has_price else 1,
        -price if has_price else 0.0,
        str(label),
        str(item.get("name") or ""),
        str(item.get("sealedProductId") or ""),
    )


def _date_key(value: Any) -> Optional[str]:
    if isinstance(value, (date, datetime)):
        return value.date().isoformat() if isinstance(value, datetime) else value.isoformat()
    text = str(value or "").strip()
    try:
        return datetime.fromisoformat(text.replace("Z", "+00:00")).date().isoformat()
    except (TypeError, ValueError):
        return None


def normalize_daily_history(rows: Iterable[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Choose the latest canonical-source observation for each calendar day."""
    by_day: Dict[str, Dict[str, Any]] = {}
    for row in rows:
        if str(row.get("currency") or "USD").upper() != "USD":
            continue
        day = _date_key(row.get("captured_at") or row.get("observation_date"))
        try:
            price = float(row.get("market_price"))
        except (TypeError, ValueError):
            continue
        if not day or not math.isfinite(price) or price <= 0:
            continue
        candidate = {
            "date": day,
            "marketPrice": round(price, 2),
            "source": str(row.get("source") or "UNKNOWN").upper(),
            "isObserved": True,
            "_captured": str(row.get("captured_at") or day),
            "_id": str(row.get("id") or ""),
        }
        current = by_day.get(day)
        # The canonical latest view selects the newest observation. Preserve
        # that same latest timestamp/id rule without averaging sources.
        if current is None or (candidate["_captured"], candidate["_id"]) > (current["_captured"], current["_id"]):
            by_day[day] = candidate
    return [
        {key: value for key, value in by_day[day].items() if not key.startswith("_")}
        for day in sorted(by_day)
    ]


def movement(history: List[Dict[str, Any]], window: str) -> Dict[str, Any]:
    if not history:
        return {"status": "unavailable", "comparisonStatus": "unavailable", "historyPointCount": 0}
    end = history[-1]
    end_date = date.fromisoformat(end["date"])
    if window == "1D":
        requested = history[-2]["date"] if len(history) >= 2 else None
        start = history[-2] if len(history) >= 2 else None
    elif window == "lifetime":
        requested = history[0]["date"]
        start = history[0]
    else:
        requested = (end_date - timedelta(days=WINDOW_DAYS[window])).isoformat()
        candidates = [point for point in history if point["date"] <= requested]
        start = candidates[-1] if candidates else history[0]
    if not start:
        return {
            "status": "unavailable",
            "comparisonStatus": "baseline_unavailable",
            "requestedStartDate": requested,
            "actualStartDate": None,
            "endDate": end["date"],
            "endPrice": end["marketPrice"],
            "currentPrice": end["marketPrice"],
            "historyPointCount": len(history),
            "fullWindowCoverage": False,
            "coverageDays": 0,
        }
    if start["date"] == end["date"]:
        return {
            "status": "unavailable",
            "comparisonStatus": "baseline_unavailable",
            "requestedStartDate": requested,
            "actualStartDate": None,
            "endDate": end["date"],
            "endPrice": end["marketPrice"],
            "currentPrice": end["marketPrice"],
            "historyPointCount": len(history),
            "fullWindowCoverage": False,
            "coverageDays": 0,
        }
    coverage_days = (end_date - date.fromisoformat(start["date"])).days
    full_coverage = window in ("1D", "lifetime") or history[0]["date"] <= requested
    partial = not full_coverage
    visible_point_count = sum(start["date"] <= point["date"] <= end["date"] for point in history)
    amount = round(end["marketPrice"] - start["marketPrice"], 2)
    percent = round(amount / start["marketPrice"] * 100, 2)
    return {
        "amount": amount,
        "amountChange": amount,
        "percent": percent,
        "percentChange": percent,
        "startPrice": start["marketPrice"],
        "endPrice": end["marketPrice"],
        "currentPrice": end["marketPrice"],
        "requestedStartDate": requested,
        "actualStartDate": start["date"],
        "endDate": end["date"],
        "status": "available",
        "comparisonStatus": "since_first_available" if partial else "available",
        "isSinceFirstAvailable": partial or window == "lifetime",
        "historyPointCount": visible_point_count,
        "fullWindowCoverage": full_coverage,
        "coverageDays": coverage_days,
    }


def fingerprint(set_id: str, products: List[Dict[str, Any]], observation_rows: Iterable[Dict[str, Any]]) -> str:
    latest: Dict[str, tuple] = {}
    eligible_ids = {str(product["id"]) for product in products}
    for row in observation_rows:
        product_id = str(row.get("sealed_product_id"))
        if product_id in eligible_ids:
            token = (str(row.get("captured_at") or ""), str(row.get("id") or ""))
            latest[product_id] = max(latest.get(product_id, ("", "")), token)
    canonical = [str(set_id), CLASSIFICATION_VERSION, SNAPSHOT_CONTRACT_VERSION]
    canonical.extend(sorted(eligible_ids))
    canonical.extend(f"{key}:{value[0]}:{value[1]}" for key, value in sorted(latest.items()))
    return hashlib.sha256("|".join(canonical).encode()).hexdigest()


def build_snapshot(set_row: Dict[str, Any], raw_products: List[Dict[str, Any]], observations: List[Dict[str, Any]]) -> Dict[str, Any]:
    classified = [(product, classify_sealed_product(product.get("name"))) for product in raw_products]
    eligible = [(product, identity) for product, identity in classified if identity["isOverviewEligible"]]
    observations_by_product: Dict[str, List[Dict[str, Any]]] = {}
    for row in observations:
        observations_by_product.setdefault(str(row.get("sealed_product_id")), []).append(row)
    payload_products = []
    for product, identity in eligible:
        history = normalize_daily_history(observations_by_product.get(str(product["id"]), []))
        if not history:
            continue
        current = history[-1]
        payload_products.append(
            {
                "sealedProductId": str(product["id"]),
                "name": product.get("name"),
                **{key: identity[key] for key in ("productFamily", "productFamilyLabel", "variantLabel")},
                "currentPrice": current["marketPrice"],
                "priceAsOf": current["date"],
                "source": current["source"],
                "movements": {key: movement(history, key) for key in MOVEMENT_WINDOWS},
                "history": history,
            }
        )
    payload_products.sort(key=product_sort_key)
    now = datetime.now(timezone.utc).isoformat()
    market_date = max((item["priceAsOf"] for item in payload_products), default=None)
    eligible_products = [product for product, _ in eligible]
    source_fingerprint = fingerprint(str(set_row["id"]), eligible_products, observations)
    payload = {
        "set": {"id": str(set_row["id"]), "canonicalKey": set_row.get("canonical_key"), "name": set_row.get("name")},
        "marketDate": market_date,
        # products is published price-descending, so the head is the most
        # expensive valid product and the API order matches what the UI shows.
        "defaultProductId": payload_products[0]["sealedProductId"] if payload_products else None,
        "products": payload_products,
        "meta": {
            "snapshotContractVersion": SNAPSHOT_CONTRACT_VERSION,
            "classificationVersion": CLASSIFICATION_VERSION,
            "source": "sealed_product_price_observations",
            "builtAt": now,
            "eligibleProductCount": len(eligible),
            "excludedProductCount": len(raw_products) - len(eligible),
            "warnings": [],
        },
    }
    return {
        "tcg": "pokemon",
        "set_id": str(set_row["id"]),
        "payload_json": payload,
        "market_date": market_date,
        "product_count": len(payload_products),
        "source_updated_at": max((str(row.get("captured_at") or "") for row in observations), default=None) or None,
        "source_generation_fingerprint": source_fingerprint,
        "classification_version": CLASSIFICATION_VERSION,
    }


def read_snapshot(client: Any, set_id: str) -> Optional[Dict[str, Any]]:
    result = client.table("pokemon_set_sealed_market_snapshot_latest").select(
        "set_id,payload_json,market_date,product_count,source_updated_at,source_generation_fingerprint,classification_version,updated_at"
    ).eq("set_id", set_id).limit(1).execute()
    rows = list(result.data or [])
    if not rows:
        return None
    payload = dict(rows[0]["payload_json"])
    payload.setdefault("meta", {}).update(
        {"source": "pokemon_set_sealed_market_snapshot_latest", "updatedAt": rows[0].get("updated_at")}
    )
    return payload


def upsert_snapshot(client: Any, row: Dict[str, Any]) -> Any:
    if not isinstance(row.get("payload_json"), dict):
        raise ValueError("validated payload_json is required")
    return client.table("pokemon_set_sealed_market_snapshot_latest").upsert(row, on_conflict="tcg,set_id").execute()
