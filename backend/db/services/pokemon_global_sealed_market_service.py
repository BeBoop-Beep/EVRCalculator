"""Build the canonical global Sealed Market from prepared set-level products.

The input snapshots are the existing set-level sealed authority: their
``products`` arrays have already passed the canonical overview-eligibility
classifier and contain normalized daily USD histories.  This module combines
those underlying SKUs into one basket; it never combines set-level indexes.
"""

from __future__ import annotations

from typing import Any, Iterable, Mapping, Sequence

from backend.db.services.pokemon_set_sealed_market_snapshot_service import (
    build_sealed_segment_history,
)
from backend.domain.pokemon.market_index import deterministic_fingerprint


class GlobalSealedMarketUnavailable(RuntimeError):
    pass


def _product_through(product: Mapping[str, Any], through_date: str) -> dict[str, Any] | None:
    history = [
        dict(point) for point in product.get("history") or []
        if str(point.get("date") or "")[:10] <= through_date
    ]
    if not history:
        return None
    latest = history[-1]
    return {
        **dict(product),
        "history": history,
        "currentPrice": latest.get("marketPrice"),
        "priceAsOf": latest.get("date"),
    }


def build_global_sealed_market(
    snapshot_payloads: Iterable[Mapping[str, Any]], *, market_date: str
) -> dict[str, Any]:
    """Return one global aggregate built directly from eligible sealed SKUs."""
    products: list[dict[str, Any]] = []
    seen_ids: set[str] = set()
    source_sets = 0
    for payload in snapshot_payloads:
        source_sets += 1
        for raw_product in payload.get("products") or []:
            product = _product_through(raw_product, market_date)
            if product is None:
                continue
            product_id = str(product.get("sealedProductId") or "").strip()
            if not product_id or product_id in seen_ids:
                raise GlobalSealedMarketUnavailable("sealed product ids must be present and globally unique")
            seen_ids.add(product_id)
            products.append(product)

    # Tracked Value is an as-of-market-date forward fill (bounded by the same
    # canonical freshness threshold). The index remains observed-only because
    # the shared helper never invents index observations on a fill-only day.
    aggregate = build_sealed_segment_history(products, through_date=market_date)
    if not aggregate or not aggregate.get("marketIndex"):
        raise GlobalSealedMarketUnavailable("global eligible Sealed Market history is unavailable")
    if str(aggregate.get("valueAsOf") or "")[:10] != market_date:
        raise GlobalSealedMarketUnavailable("global Sealed Market does not reach the promoted market date")

    index = aggregate["marketIndex"]
    current_segment_id = index.get("currentSegmentId")
    full_history = list(index.get("history") or [])
    current_history = [
        point for point in full_history
        if point.get("chainSegmentId") == current_segment_id
    ]
    return {
        "basketValue": aggregate["currentValue"],
        "indexValue": index["currentValue"],
        "historyStartDate": index.get("trackingSince"),
        "changes": dict(index.get("movements") or {}),
        # The comparison chart is scoped to the current continuous segment so
        # it cannot draw a false crash between independently based segments.
        "trend": [[point["date"], point["indexValue"]] for point in current_history],
        "history": full_history,
        "metadata": {
            "eligibleProductCount": aggregate.get("productCount"),
            "contributingProductCount": aggregate.get("contributingProductCount"),
            "observationCount": sum(len(product.get("history") or []) for product in products),
            "trackingStart": index.get("trackingSince"),
            "currentSegmentId": current_segment_id,
            "historyPointCount": len(full_history),
            "sourceSetCount": source_sets,
        },
        "sourceGenerationFingerprint": deterministic_fingerprint([
            market_date,
            *sorted(
                f"{product['sealedProductId']}:{product['history'][-1]['date']}:{product['history'][-1]['marketPrice']}:{len(product['history'])}"
                for product in products
            ),
        ]),
    }


def read_global_sealed_source_snapshots(
    client: Any, set_ids: Sequence[str]
) -> list[dict[str, Any]]:
    """Read every prepared set snapshot in bounded batches (no product queries)."""
    rows: list[dict[str, Any]] = []
    for offset in range(0, len(set_ids), 20):
        page = list((client.table("pokemon_set_sealed_market_snapshot_latest")
            .select("set_id,payload_json,market_date,source_generation_fingerprint")
            .in_("set_id", list(set_ids[offset:offset + 20])).execute()).data or [])
        rows.extend(dict(row) for row in page)
    found = {str(row.get("set_id")) for row in rows}
    missing = sorted(set(set_ids) - found)
    if missing:
        raise GlobalSealedMarketUnavailable(
            f"prepared sealed snapshots are missing for {len(missing)} eligible sets"
        )
    return rows
