"""Build the canonical global Sealed Market from prepared set-level products.

The input snapshots are the existing set-level sealed authority: their
``products`` arrays have already passed the canonical overview-eligibility
classifier and contain normalized daily USD histories.  This module combines
those underlying SKUs into one basket; it never combines set-level indexes.
"""

from __future__ import annotations

from datetime import date, timedelta
from typing import Any, Iterable, Mapping, Sequence

from backend.db.services.pokemon_set_sealed_market_snapshot_service import (
    build_sealed_segment_history,
)
from backend.domain.pokemon.market_index import (
    deterministic_fingerprint,
    resolve_one_day_comparison_close,
)
from backend.domain.pokemon.prepared_constituent_summary import (
    summarize_sealed_segment_constituents,
)
from backend.domain.pokemon.sealed_market_segments import (
    RESIDUAL_SEGMENT_KEY,
    RESIDUAL_SEGMENT_LABEL,
    SEALED_SEGMENT_DEFINITIONS,
    SEALED_SEGMENT_TOTAL_KEY,
    partition_products_by_segment,
    segment_definition_metadata,
)


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


def collect_global_sealed_products(
    snapshot_payloads: Iterable[Mapping[str, Any]], *, market_date: str
) -> tuple[list[dict[str, Any]], int]:
    """The ONE eligible global sealed constituent universe, as of ``market_date``.

    Extracted so the parent aggregate and every product-family submarket are
    built from a byte-identical constituent set. A submarket that collected its
    own products could silently disagree with the parent about eligibility,
    which is exactly the drift the reconciliation guarantee rules out.
    """
    products: list[dict[str, Any]] = []
    seen_ids: set[str] = set()
    source_sets = 0
    for payload in snapshot_payloads:
        source_sets += 1
        # The owning set is on the SNAPSHOT, not on the product. Stamping it
        # here is what lets any downstream consumer name a product's set
        # without re-reading the snapshot it came from. Additive only.
        owning_set = payload.get("set") or {}
        owning_set_id = str(owning_set.get("id") or "")
        owning_set_name = str(owning_set.get("name") or "")
        for raw_product in payload.get("products") or []:
            product = _product_through(raw_product, market_date)
            if product is None:
                continue
            product.setdefault("setId", owning_set_id)
            product.setdefault("setName", owning_set_name)
            product_id = str(product.get("sealedProductId") or "").strip()
            if not product_id or product_id in seen_ids:
                raise GlobalSealedMarketUnavailable("sealed product ids must be present and globally unique")
            seen_ids.add(product_id)
            products.append(product)
    return products, source_sets


def build_global_sealed_market(
    snapshot_payloads: Iterable[Mapping[str, Any]], *, market_date: str
) -> dict[str, Any]:
    """Return one global aggregate built directly from eligible sealed SKUs."""
    products, source_sets = collect_global_sealed_products(
        snapshot_payloads, market_date=market_date
    )

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
    target_date = (date.fromisoformat(market_date) - timedelta(days=1)).isoformat()
    one_day_comparison = resolve_one_day_comparison_close(
        current_history, target_date=target_date, market_date=market_date
    )
    return {
        "basketValue": aggregate["currentValue"],
        "indexValue": index["currentValue"],
        "historyStartDate": index.get("trackingSince"),
        "changes": dict(index.get("movements") or {}),
        # The comparison chart is scoped to the current continuous segment so
        # it cannot draw a false crash between independently based segments.
        "trend": [[point["date"], point["indexValue"]] for point in current_history],
        # Comparison-only previous-close points. Canonical ``trend`` and
        # ``history`` remain observed-only.
        "oneDayComparison": one_day_comparison,
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


def _segment_series(
    products: list[dict[str, Any]], *, market_date: str
) -> dict[str, Any] | None:
    """Build ONE product-family submarket from its own constituent SKUs.

    Identical methodology to the parent: the same ``build_sealed_segment_history``
    over this family's SKUs, so the index is chain-linked over the common cohort
    with segment breaks preserved, and Tracked Value is the same
    freshness-bounded forward fill. Returns None when the family has nothing to
    aggregate, so the caller publishes the segment as unavailable rather than a
    zero.
    """
    if not products:
        return None
    aggregate = build_sealed_segment_history(products, through_date=market_date)
    if not aggregate or not aggregate.get("marketIndex"):
        return None
    index = aggregate["marketIndex"]
    current_segment_id = index.get("currentSegmentId")
    full_history = list(index.get("history") or [])
    current_history = [
        point for point in full_history
        if point.get("chainSegmentId") == current_segment_id
    ]
    if not current_history:
        return None
    return {
        "basketValue": aggregate["currentValue"],
        "indexValue": index["currentValue"],
        "historyStartDate": index.get("trackingSince"),
        # The family's OWN window movements, measured from its own tracking
        # start. build_market_overview later adds the shared-comparison
        # `changes`; these stay family-specific and are never overwritten.
        "familyChanges": dict(index.get("movements") or {}),
        # Tracked Value is a SEPARATE published series from the index: it is
        # the literal dollar basket and deliberately DOES move when a product
        # enters or leaves the family. Kept beside the index, never merged
        # into it. (The parent deliberately does not publish these, so adding
        # submarkets cannot change the parent payload.)
        "trackedValueHistory": [
            {"date": point["date"], "value": point["marketPrice"]}
            for point in (aggregate.get("history") or [])
        ],
        "basketChanges": dict(aggregate.get("movements") or {}),
        "trend": [[point["date"], point["indexValue"]] for point in current_history],
        "history": full_history,
        "valueAsOf": aggregate.get("valueAsOf"),
        # WHAT IS IN THIS INDEX. The current roster only — no historical
        # observations. Published so a user can inspect a prepared segment's
        # composition without running the dynamic query engine, which is the
        # expensive path quick segments exist to avoid.
        "currentConstituents": summarize_sealed_segment_constituents(
            [
                {
                    "sealedProductId": product.get("sealedProductId"),
                    "productName": product.get("name"),
                    "variantLabel": product.get("variantLabel"),
                    "setId": product.get("setId"),
                    "setName": product.get("setName"),
                    "productFamily": product.get("productFamily"),
                    "productFamilyLabel": product.get("productFamilyLabel"),
                    "marketPrice": product.get("currentPrice"),
                    "imageUrl": product.get("imageUrl"),
                }
                for product in products
            ],
            as_of=aggregate.get("valueAsOf"),
        ),
        "metadata": {
            "eligibleProductCount": aggregate.get("productCount"),
            "contributingProductCount": aggregate.get("contributingProductCount"),
            "trackingStart": index.get("trackingSince"),
            "currentSegmentId": current_segment_id,
            "historyPointCount": len(full_history),
        },
    }


def build_global_sealed_segments(
    snapshot_payloads: Iterable[Mapping[str, Any]],
    *,
    market_date: str,
    total: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Publish the Sealed Market as a parent plus its product-family submarkets.

    ``total`` is the already-built parent (``build_global_sealed_market``) and is
    republished here VERBATIM as the ``total`` segment. It is never recomputed,
    so adding submarkets cannot move the parent by a cent.

    Every published segment is built from the same global constituent universe
    the parent used, partitioned by canonical ``productFamily``. Because the
    partition is disjoint and exhaustive over overview-eligible families,
    segment Tracked Values plus the residual reconcile to the parent's.
    """
    products, _source_sets = collect_global_sealed_products(
        snapshot_payloads, market_date=market_date
    )
    grouped = partition_products_by_segment(products)

    segments: dict[str, Any] = {}
    if total is not None:
        segments[SEALED_SEGMENT_TOTAL_KEY] = {
            **dict(total),
            "key": SEALED_SEGMENT_TOTAL_KEY,
            "label": "Total Sealed",
            "isParent": True,
            "available": True,
        }

    for definition in SEALED_SEGMENT_DEFINITIONS:
        key = str(definition["key"])
        series = _segment_series(grouped.get(key) or [], market_date=market_date)
        if series is None:
            segments[key] = {
                "key": key,
                "label": definition["label"],
                "isParent": False,
                "available": False,
                "unavailableReason": "no eligible constituent history",
                "productFamilies": list(definition["productFamilies"]),
                "isComposite": bool(definition["isComposite"]),
                "definition": definition["definition"],
            }
            continue
        segments[key] = {
            **series,
            "key": key,
            "label": definition["label"],
            "isParent": False,
            "available": True,
            "productFamilies": list(definition["productFamilies"]),
            "isComposite": bool(definition["isComposite"]),
            "definition": definition["definition"],
        }

    # The residual is REPORTED, not published as a selectable market: it is a
    # leftover bucket, not a coherent submarket. Reporting its value is what
    # makes parent/child reconciliation an exact statement instead of an
    # approximate one.
    residual_products = grouped.get(RESIDUAL_SEGMENT_KEY) or []
    residual_series = _segment_series(residual_products, market_date=market_date)
    published_basket = sum(
        float(segments[str(definition["key"])].get("basketValue") or 0.0)
        for definition in SEALED_SEGMENT_DEFINITIONS
        if segments[str(definition["key"])].get("available") is True
    )
    residual_basket = float((residual_series or {}).get("basketValue") or 0.0)
    parent_basket = float((total or {}).get("basketValue") or 0.0) if total is not None else None

    return {
        "segments": segments,
        "definitions": segment_definition_metadata(),
        "reconciliation": {
            "parentBasketValue": parent_basket,
            "publishedSegmentBasketValue": round(published_basket, 2),
            "residual": {
                "key": RESIDUAL_SEGMENT_KEY,
                "label": RESIDUAL_SEGMENT_LABEL,
                "basketValue": round(residual_basket, 2) if residual_series else 0.0,
                "productCount": len(residual_products),
                "productFamilies": sorted(
                    {str(product.get("productFamily")) for product in residual_products}
                ),
            },
            "eligibleProductCount": len(products),
            "segmentedProductCount": sum(
                len(grouped.get(str(definition["key"])) or [])
                for definition in SEALED_SEGMENT_DEFINITIONS
            ),
        },
        "sourceGenerationFingerprint": deterministic_fingerprint([
            market_date,
            *sorted(
                f"{key}:{len(value)}:" + ",".join(sorted(
                    str(product.get("sealedProductId")) for product in value
                ))
                for key, value in grouped.items()
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
