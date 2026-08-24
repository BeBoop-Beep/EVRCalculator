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
from backend.domain.pokemon.market_index import (
    MARKET_INDEX_BASE_VALUE,
    build_chain_linked_history_with_segments,
    compute_strict_window_movements,
)

SNAPSHOT_CONTRACT_VERSION = "pokemon-set-sealed-market-v3"
WINDOW_DAYS = {"7D": 7, "30D": 30, "3M": 90, "6M": 180, "1Y": 365}
MOVEMENT_WINDOWS = ("1D", "7D", "30D", "3M", "6M", "1Y", "lifetime")
# Retained as product-family metadata for consumers; product ordering itself is
# now driven by current market price rather than by family.
FAMILY_PRIORITY = {
    "booster_box": 0,
    "half_booster_box": 1,
    "enhanced_booster_box": 2,
    "elite_trainer_box": 3,
    "pokemon_center_elite_trainer_box": 4,
    "booster_bundle": 5,
    "loose_booster_pack": 6,
    "sleeved_booster_pack": 7,
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


# Sealed price freshness allowance for Tracked Value forward-fill.
#
# DERIVED FROM MEASURED CADENCE, not chosen arbitrarily (no existing canonical
# freshness convention was found anywhere in the codebase for market prices —
# audited across services/scripts referencing "stale"/"freshness"; the closest
# analogues, e.g. pokemon_set_market_service's mover-baseline span tolerance,
# govern a different question, "how far back is an acceptable comparison
# baseline", not "how old before a price stops describing today").
#
# Measured across 8 representative production sets / 48+ eligible sealed
# products: median observation interval 1 day, 90th percentile 1 day, 99th
# percentile 3 days, single historical outlier 15 days (a one-time gap shared
# across many sets on the same date, already resolved). Every eligible product
# in every audited set had a same-day observation at audit time — there is no
# live stale-product case today. This threshold exists to bound the FUTURE
# failure mode (an abandoned product's last price silently inflating Tracked
# Value forever), set comfortably above the worst normal gap ever observed
# (10x the P99, 2x the one historical anomaly) so it never trims a legitimate
# short scrape gap, confirmed to be a no-op against all current production
# data (every product's freshest observation is 0 days old as of this audit).
SEALED_PRICE_FRESHNESS_DAYS = 30


def _forward_filled_daily_series(history: List[Dict[str, Any]], start: str, end: str) -> Dict[str, float]:
    """Carry each product's last observed price forward across every day in
    range — but only while that price is still within the freshness
    allowance. A sealed product is not observed every calendar day, and its
    market value does not cease to exist on the days between observations
    (that is what forward-filling is for), but a price that has gone
    ``SEALED_PRICE_FRESHNESS_DAYS`` without a fresh observation stops
    describing today's market and stops contributing to CURRENT Tracked
    Value. The historical fact that it once had that price is untouched —
    this only governs how far a stale last-known price projects forward.
    """
    by_day: Dict[str, float] = {}
    cursor = date.fromisoformat(start)
    end_date = date.fromisoformat(end)
    index = 0
    last: Optional[float] = None
    last_date: Optional[date] = None
    while cursor <= end_date:
        key = cursor.isoformat()
        while index < len(history) and history[index]["date"] <= key:
            last = history[index]["marketPrice"]
            last_date = date.fromisoformat(history[index]["date"])
            index += 1
        if last is not None and (cursor - last_date).days <= SEALED_PRICE_FRESHNESS_DAYS:
            by_day[key] = last
        cursor += timedelta(days=1)
    return by_day


def _observed_cohort_constituents(basket: List[Dict[str, Any]], end: str) -> List[Dict[str, Any]]:
    """One chain-link observation per day, built ONLY from genuinely observed prices.

    METHODOLOGY DECISION (measured, not assumed — see the density audit in
    docs referenced from the sealed-hardening pass): each day's constituent
    set is whatever eligible products were GENUINELY observed that day — never
    forward-filled, never zero-filled. This is deliberately looser than
    requiring the full current eligible basket to report every day.

    That full-basket requirement was tried first and measured against six
    representative sets (pitchBlack, destinedRivals, prismaticEvolutions,
    surgingSparks, shroudedFable, baseSetShadowless): on every set with more
    than one day of real history, full-completeness days matched
    any-observation days almost exactly (within 0-2 days out of 100+), so it
    was not losing meaningful density TODAY. But it has an unbounded-blast-
    radius failure mode that the audit data cannot rule out for the future: if
    even ONE still-eligible product stops receiving fresh observations (a
    dead scrape source, a delisted SKU nobody reclassified), the full-basket
    rule silences the ENTIRE set's index from that day forward, forever — a
    single stale product taking down every other product's legitimate price
    history. That failure mode is proven by
    test_market_index_excludes_days_after_a_still_eligible_sku_stops_reporting
    against the OLD rule.

    The observed-cohort rule removes that single point of failure while
    matching the old rule's output on every day where the full basket WAS
    observed (which is nearly always, per the audit): a day with one missing
    product still contributes an index observation from the OTHER products
    that were genuinely priced, and the chain-linked common-cohort algorithm
    (unchanged, unforked) determines the return from whatever cohort is common
    to two consecutive observed days. No price is ever invented for the
    missing day; the missing product simply does not contribute a data point
    on a day it was not priced.
    """
    by_date: Dict[str, Dict[str, float]] = {}
    for product in basket:
        for point in product["history"]:
            if point["date"] <= end:
                by_date.setdefault(point["date"], {})[str(product["sealedProductId"])] = point["marketPrice"]

    observations = []
    for day in sorted(by_date):
        prices = by_date[day]
        if prices:
            observations.append(
                {
                    "marketDate": day,
                    "constituents": [
                        {"setId": product_id, "setValue": prices[product_id]} for product_id in sorted(prices)
                    ],
                }
            )
    return observations


def _chain_link_with_cohort_breaks(observations: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Sealed's name for the shared chain-segment wrapper.

    The implementation that used to live here was PROMOTED VERBATIM into
    ``backend.domain.pokemon.market_index.build_chain_linked_history_with_segments``
    so the Cards Market Index consumes the identical segmentation instead of
    growing a second, silently divergent copy of it. Behaviour is unchanged;
    this alias is kept so Sealed's call sites and tests read as before. See the
    domain function for why a cohort break starts a new segment rather than
    raising, and why the ``chainSegmentId``/``segmentStartDate`` tags must not
    be stripped upstream.
    """
    return build_chain_linked_history_with_segments(observations)


def build_sealed_segment_history(
    products: List[Dict[str, Any]], *, through_date: Optional[str] = None
) -> Optional[Dict[str, Any]]:
    """The set-level Sealed segment: Tracked Value and Market Index, kept separate.

    TRACKED VALUE answers "what is the eligible sealed basket worth right now".
    It is a forward-filled running sum of every eligible product's latest known
    price, starting the day the FIRST eligible product began reporting. It is
    explicitly allowed to move when the eligible universe changes — a newly
    tracked $150 SKU legitimately adds ~$150 to the basket the day it enters.

    MARKET INDEX answers "how has the underlying sealed market actually
    performed", chain-linked via the same common-cohort methodology the global
    Raw Card Market / Top 10 Chase Market indexes use
    (``backend.domain.pokemon.market_index.build_chain_linked_history``). A
    constituent entering or leaving the eligible universe cannot move the
    index by itself: each day's return is computed only from the cohort common
    to that day and the previous day, so a same-day entry/exit is excluded
    from that day's return rather than counted as a price change. This is the
    same function backing the global indexes, called here with each eligible
    sealed product as one constituent instead of one set — the algorithm does
    not care what a constituent represents, only that it has a stable id and a
    positive value.

    Returns None when there is nothing to aggregate; callers omit the lens
    rather than publishing a zero.
    """
    basket = [product for product in products if product.get("history")]
    if not basket:
        return None

    tracked_start = min(product["history"][0]["date"] for product in basket)
    latest_observation_date = max(product["history"][-1]["date"] for product in basket)
    end = max(latest_observation_date, str(through_date)[:10]) if through_date else latest_observation_date
    if tracked_start > end:
        return None

    # Tracked Value: lenient, forward-filled, starts as soon as ANY eligible
    # product has a price. This is deliberately looser than the index below.
    filled = [_forward_filled_daily_series(product["history"], tracked_start, end) for product in basket]
    tracked_history: List[Dict[str, Any]] = []
    cursor = date.fromisoformat(tracked_start)
    end_date = date.fromisoformat(end)
    while cursor <= end_date:
        key = cursor.isoformat()
        day_values = [series[key] for series in filled if key in series]
        if day_values:
            tracked_history.append({"date": key, "marketPrice": round(sum(day_values), 2), "isObserved": True})
        cursor += timedelta(days=1)
    if not tracked_history:
        return None

    # Market Index: strict, chain-linked, common-cohort. May legitimately start
    # later than Tracked Value and may have fewer points — every point it does
    # have is a day every eligible constituent was genuinely observed.
    index_observations = _observed_cohort_constituents(basket, end)
    index_history = _chain_link_with_cohort_breaks(index_observations) if index_observations else []

    # WINDOW RETURNS MUST NEVER CROSS A CHAIN-SEGMENT BREAK. A chain break means
    # the index legitimately cannot say anything about the market's movement
    # across that gap — the two index levels either side of it are not
    # mathematically linked. compute_strict_window_movements has no concept of
    # a segment boundary; feeding it the FULL multi-segment history would let a
    # 7D/30D/etc. window silently span a break and manufacture a return like
    # "119.40 -> 100.00 = -16.25%" that no real price data supports. Window
    # returns are therefore computed ONLY over the CURRENT (latest) segment's
    # points. "All"/SinceTracking under this rule means "since the current
    # segment began" — not since the first point ever recorded, which may
    # belong to a disconnected earlier segment.
    current_segment_id = index_history[-1]["chainSegmentId"] if index_history else None
    current_segment_points = [
        {"date": row["marketDate"], "value": row["normalizedIndexValue"]}
        for row in index_history
        if row["chainSegmentId"] == current_segment_id
    ]
    index_points = current_segment_points
    index_movements = compute_strict_window_movements(index_points) if index_points else {}

    # Catalog eligibility (len(basket)) versus CURRENT aggregate eligibility
    # (contributingProductCount): a product stays catalog-eligible forever —
    # it is never declassified for going stale — but only counts toward
    # today's Tracked Value while its last price is within the freshness
    # allowance. On every set audited when this policy was introduced, the
    # two counts were identical (nothing was stale); they are expected to
    # diverge only if a product's scrape source genuinely goes dark.
    contributing_product_count = sum(
        1
        for product in basket
        if product["history"] and (date.fromisoformat(end) - date.fromisoformat(product["history"][-1]["date"])).days <= SEALED_PRICE_FRESHNESS_DAYS
    )

    return {
        "currentValue": tracked_history[-1]["marketPrice"],
        "valueAsOf": tracked_history[-1]["date"],
        "trackingSince": tracked_start,
        "productCount": len(basket),
        "contributingProductCount": contributing_product_count,
        "history": tracked_history,
        "movements": {key: movement(tracked_history, key) for key in MOVEMENT_WINDOWS},
        "marketIndex": {
            "currentValue": index_points[-1]["value"] if index_points else None,
            "baseValue": MARKET_INDEX_BASE_VALUE,
            # Scoped to the CURRENT segment only — see the window-returns
            # comment above. "Since this reading has been continuously
            # comparable", not "since the very first index point ever".
            "trackingSince": index_points[0]["date"] if index_points else None,
            "currentSegmentId": current_segment_id,
            # The full multi-segment history, WITH segment tags on every row.
            # A frontend line chart can later use chainSegmentId to render each
            # segment as its own line with a visible gap between them, rather
            # than drawing one continuous line through a break that has no
            # market meaning. isNewSegment marks each segment's first point —
            # exactly where "no legitimate return exists relative to the
            # previous segment" applies.
            "history": [
                {
                    "date": row["marketDate"],
                    "indexValue": row["normalizedIndexValue"],
                    "chainSegmentId": row["chainSegmentId"],
                    "segmentStartDate": row["segmentStartDate"],
                    "isNewSegment": row["marketDate"] == row["segmentStartDate"],
                }
                for row in index_history
            ],
            # Window returns for the CURRENT segment only (see above). "All"/
            # SinceTracking resolves to "since this segment began" per the
            # chain-break hardening — a UI exposing "All" for this index reads
            # movements["SinceTracking"], not a span across every segment.
            "movements": index_movements,
        }
        if index_points
        else None,
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
        # The set-level sealed lens. Derived once, here, so every consumer
        # reads the same canonical aggregate instead of each one summing the
        # per-product histories its own way.
        "setMarket": build_sealed_segment_history(payload_products),
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
    # Snapshots persisted before setMarket existed still serve it: the series
    # is a pure function of products[] already in the payload, so deriving it
    # here is identical to what the builder stores. This deliberately avoids a
    # SNAPSHOT_CONTRACT_VERSION bump, which would change every fingerprint and
    # force a republication run this change does not need.
    if payload.get("setMarket") is None:
        payload["setMarket"] = build_sealed_segment_history(list(payload.get("products") or []))
    payload.setdefault("meta", {}).update(
        {"source": "pokemon_set_sealed_market_snapshot_latest", "updatedAt": rows[0].get("updated_at")}
    )
    return payload


def upsert_snapshot(client: Any, row: Dict[str, Any]) -> Any:
    if not isinstance(row.get("payload_json"), dict):
        raise ValueError("validated payload_json is required")
    return client.table("pokemon_set_sealed_market_snapshot_latest").upsert(row, on_conflict="tcg,set_id").execute()
