"""Publication-bound, paginated Product Rankings read service.

This path deliberately avoids the large Explore ``productFamilyRankings`` JSON.
Ranking authority comes from the active RIP release and the published budget
ranking pointer; identity comes from relational product/set tables.  Exact SKU
economics is loaded only after a page has been selected.
"""
from __future__ import annotations

from math import ceil
from functools import cmp_to_key
from typing import Any, Mapping, Optional

from backend.desirability.chase_accessibility_overall_score import chase_accessibility_overall_score
from backend.domain.pokemon.sealed_product_classifier import FAMILY_LABELS, classify_sealed_product
from backend.db.services.budget_product_ranking_service import (
    load_full_market_ranking, load_latest_snapshot, resolve_generic_budget_cohort_size,
    resolve_generic_budget_rank, resolve_generic_overall_score,
)
from backend.db.services.rankings_redesign_contract_service import _day, _freshness, _number


SCORE_SORTS = {"rank", "productName", "ripScore", "financialRip", "chaseScore", "collectorAppeal"}
ECONOMICS_SORTS = {"productName", "unitPrice", "bestOpenPrice", "expectedValuePerPack", "modeledReturnOnSpend", "chanceToRecoverCost"}


def _rows(response: Any) -> list[dict[str, Any]]:
    return list(getattr(response, "data", None) or [])


def _family(row: Mapping[str, Any]) -> tuple[str, str]:
    key = str(row.get("product_family") or "")
    return key, FAMILY_LABELS.get(key, key.replace("_", " ").title())


def read_product_authority(client: Any, *, release: Any) -> dict[str, Any]:
    """Resolve and validate the canonical Full Market cohort once."""
    kwargs = {} if release.ranking_method_version == "budget_product_ranking_v1" else {
        "ranking_method_version": release.ranking_method_version,
    }
    snapshot = load_latest_snapshot(client, **kwargs)
    if not snapshot:
        return {"available": False, "reason": "no_published_authority", "rows": []}
    if snapshot.get("ranking_method_version") != release.ranking_method_version:
        return {"available": False, "reason": "ranking_method_mismatch", "rows": []}
    ranked = load_full_market_ranking(client, source_snapshot=snapshot)
    if not ranked.get("available"):
        return {"available": False, "reason": ranked.get("reason"), "rows": []}
    raw = ranked.get("rows") or []
    ids = sorted({str(row["sealed_product_id"]) for row in raw})
    products = {str(row["id"]): row for row in _rows(client.table("sealed_products").select(
        "id,set_id,name,product_type,image_small_url,image_large_url"
    ).in_("id", ids).execute())} if ids else {}
    set_ids = sorted({str(row.get("set_id")) for row in raw if row.get("set_id")})
    sets = {str(row["id"]): row for row in _rows(client.table("sets").select(
        "id,name,canonical_key"
    ).in_("id", set_ids).execute())} if set_ids else {}
    projected = []
    for row in raw:
        product_id = str(row["sealed_product_id"]); product = products.get(product_id, {})
        set_row = sets.get(str(row.get("set_id")), {}); family_key, family_name = _family(row)
        chase_raw = _number(row.get("chase_accessibility_raw"))
        projected.append({
            "sealedProductId": product_id, "productName": product.get("name"),
            "setId": str(row.get("set_id") or "") or None, "setName": set_row.get("name"),
            "setCanonicalKey": set_row.get("canonical_key"), "familyKey": family_key,
            "familyName": family_name, "productImageUrl": product.get("image_small_url") or product.get("image_large_url"),
            "rank": resolve_generic_budget_rank(row, snapshot),
            "cohortSize": resolve_generic_budget_cohort_size(row, snapshot),
            "ripScore": {"scoreKind": "absolute", "scoreScale": "0-100",
                         "scoreValue": _number(resolve_generic_overall_score(row, snapshot)),
                         "metricVersion": snapshot.get("overall_rip_version")},
            "financialRip": _number(row.get("financial_rip_v4_score")),
            "chaseScore": None if chase_raw is None else chase_accessibility_overall_score(chase_raw),
            "chaseAccessibilityRaw": chase_raw,
            "collectorAppeal": _number(row.get("collector_appeal_score")),
            "sourceCalculationRunId": str(row.get("source_calculation_run_id") or "") or None,
        })
    if projected and any(not row.get("productName") for row in projected):
        return {"available": False, "reason": "product_identity_incomplete", "rows": []}
    authority = ranked.get("authority") or {}
    return {"available": bool(projected), "reason": None, "rows": projected,
            "authority": authority, "snapshotId": str(snapshot["id"]),
            "marketDate": _day(authority.get("marketDate") or snapshot.get("market_date")),
            "publicationIdentity": (str(snapshot["id"]), str(snapshot.get("published_at")),
                                    str(snapshot.get("cohort_fingerprint")))}


def _sort_value(row: Mapping[str, Any], key: str) -> Any:
    if key == "ripScore": return (row.get("ripScore") or {}).get("scoreValue")
    return row.get(key)


def _filter_sort(rows: list[dict[str, Any]], *, search: Optional[str], family: Optional[str],
                 sort: str, direction: str) -> list[dict[str, Any]]:
    needle = (search or "").strip().casefold()
    filtered = [row for row in rows if (not family or family == "all" or row.get("familyKey") == family)
                and (not needle or any(needle in str(row.get(key) or "").casefold()
                                       for key in ("productName", "setName", "familyName")))]
    reverse = direction == "desc"
    def compare(left: Mapping[str, Any], right: Mapping[str, Any]) -> int:
        a, b = _sort_value(left, sort), _sort_value(right, sort)
        a = a.casefold() if isinstance(a, str) else a
        b = b.casefold() if isinstance(b, str) else b
        primary = (a > b) - (a < b)
        if primary: return -primary if reverse else primary
        # Canonical Full Market rank is always the deterministic tie-break;
        # changing direction never manufactures a reverse Chase/Collector rank.
        tie_a = (left.get("rank") or 10**9, str(left.get("sealedProductId")))
        tie_b = (right.get("rank") or 10**9, str(right.get("sealedProductId")))
        return (tie_a > tie_b) - (tie_a < tie_b)
    available = [row for row in filtered if _sort_value(row, sort) is not None]
    missing = [row for row in filtered if _sort_value(row, sort) is None]
    available.sort(key=cmp_to_key(compare))
    missing.sort(key=lambda row: (row.get("rank") or 10**9, str(row.get("sealedProductId"))))
    return available + missing


def _page(rows: list[dict[str, Any]], page: int, page_size: int) -> tuple[list[dict[str, Any]], dict[str, int]]:
    total = len(rows); total_pages = max(1, ceil(total / page_size)); page = min(page, total_pages)
    start = (page - 1) * page_size
    return rows[start:start + page_size], {"page": page, "pageSize": page_size, "total": total, "totalPages": total_pages}


def _exact_economics(client: Any, page_rows: list[dict[str, Any]]) -> dict[tuple[str, str], dict[str, Any]]:
    ids = [row["sealedProductId"] for row in page_rows]
    run_ids = sorted({row["sourceCalculationRunId"] for row in page_rows if row.get("sourceCalculationRunId")})
    if not ids or not run_ids: return {}
    rows = _rows(client.table("simulation_sealed_product_results").select(
        "sealed_product_id,calculation_run_id,product_market_cost,pack_count,expected_value,"
        "chance_to_recover_cost,price_as_of"
    ).in_("sealed_product_id", ids).in_("calculation_run_id", run_ids).execute())
    return {(str(row["sealed_product_id"]), str(row["calculation_run_id"])): row for row in rows}


def _best_open(client: Any, page_rows: list[dict[str, Any]], reference_date: Optional[str]) -> dict[str, dict[str, Any]]:
    ids = [row["sealedProductId"] for row in page_rows]
    if not ids: return {}
    pointer = _rows(client.table("budget_product_best_open_price_latest").select(
        "snapshot_id,source_market_date"
    ).limit(1).execute())
    if not pointer: return {}
    source_date = _day(pointer[0].get("source_market_date"))
    rows = _rows(client.table("budget_product_best_open_price_rows").select(
        "sealed_product_id,source_calculation_run_id,current_market_price,status,best_open_price,"
        "price_gap_dollars,price_gap_percent"
    ).eq("snapshot_id", pointer[0]["snapshot_id"]).in_("sealed_product_id", ids).execute())
    expected_runs = {row["sealedProductId"]: row.get("sourceCalculationRunId") for row in page_rows}
    return {str(row["sealed_product_id"]): {
        "bestOpenPrice": _number(row.get("best_open_price")), "bestOpenMarketPrice": _number(row.get("current_market_price")),
        "bestOpenStatus": row.get("status"), "bestOpenPriceGapDollars": _number(row.get("price_gap_dollars")),
        "bestOpenPriceGapPercent": _number(row.get("price_gap_percent")), "bestOpenSourceMarketDate": source_date,
        "bestOpenMarketSourceDate": source_date, "bestOpenFreshnessStatus": _freshness(source_date, reference_date),
    } for row in rows if str(row.get("source_calculation_run_id") or "") == str(expected_runs.get(str(row["sealed_product_id"])) or "")}


def query_product_rankings(client: Any, authority: Mapping[str, Any], *, view: str, page: int = 1,
                           page_size: int = 25, search: Optional[str] = None, family: Optional[str] = None,
                           sort: Optional[str] = None, direction: str = "asc") -> dict[str, Any]:
    allowed = SCORE_SORTS if view == "scores" else ECONOMICS_SORTS
    sort = sort or ("rank" if view == "scores" else "productName")
    if sort not in allowed or direction not in {"asc", "desc"}: raise ValueError("invalid Product sort")
    base = list(authority.get("rows") or [])
    # Unit price is intentionally not sourced from the budget strategy.  It is
    # populated from exact simulation evidence below, after page selection.
    ordered = _filter_sort(base, search=search, family=family, sort=sort, direction=direction)
    # Economics sorts require exact fields. The cohort is small (138), but the
    # enrichment contract remains page-first for normal/default requests. For
    # exact-field sorts, load one bounded cohort batch so sorting is truthful.
    if view == "economics" and sort != "productName":
        exact_all = _exact_economics(client, ordered)
        for row in ordered:
            exact = exact_all.get((row["sealedProductId"], str(row.get("sourceCalculationRunId") or "")))
            if exact: _apply_exact(row, exact)
        ordered = _filter_sort(ordered, search=None, family=None, sort=sort, direction=direction)
    selected, meta = _page(ordered, page, page_size)
    if view == "economics":
        exact = _exact_economics(client, selected)
        best = _best_open(client, selected, authority.get("marketDate"))
        output = []
        for base_row in selected:
            row = {key: base_row.get(key) for key in ("sealedProductId", "productName", "setId", "setName", "setCanonicalKey", "familyKey", "familyName", "productImageUrl")}
            evidence = exact.get((base_row["sealedProductId"], str(base_row.get("sourceCalculationRunId") or "")))
            if evidence: _apply_exact(row, evidence)
            row.update(best.get(base_row["sealedProductId"], {})); output.append(row)
        selected = output
    facets = sorted(({"value": key, "label": label} for key, label in
                     {(row["familyKey"], row["familyName"]) for row in base}), key=lambda item: item["label"])
    return {"contractVersion": f"rankings-products-{view}-v3", "status": "available", "view": view,
            "marketDate": authority.get("marketDate"), **meta, "families": facets, "rows": selected,
            "scoreContract": {"scoreKind": "absolute", "scoreScale": "0-100",
                              "metricVersion": (authority.get("authority") or {}).get("overallRipVersion"),
                              "benchmarkAvailable": False} if view == "scores" else None}


def _apply_exact(row: dict[str, Any], exact: Mapping[str, Any]) -> None:
    price = _number(exact.get("product_market_cost")); packs = _number(exact.get("pack_count")); ev = _number(exact.get("expected_value"))
    row.update({"unitPrice": price, "expectedValuePerPack": ev / packs if ev is not None and packs else None,
                "modeledReturnOnSpend": ev / price if ev is not None and price else None,
                "chanceToRecoverCost": _number(exact.get("chance_to_recover_cost")),
                "economicsSourceMarketDate": _day(exact.get("price_as_of"))})


def read_public_product_catalogue_page(client: Any, *, page: int = 1, page_size: int = 25,
                                       search: Optional[str] = None, family: Optional[str] = None) -> dict[str, Any]:
    """Paginated identity-only catalogue. The bounded ~1.8k identity scan is
    required because family classification is derived from canonical names;
    only the selected page crosses the HTTP boundary."""
    products = _rows(client.table("sealed_products").select(
        "id,set_id,name,product_type,image_small_url,image_large_url"
    ).order("name").order("id").limit(5000).execute())
    set_ids = sorted({str(row.get("set_id")) for row in products if row.get("set_id")})
    sets = {str(row["id"]): row for row in _rows(client.table("sets").select(
        "id,name,canonical_key"
    ).in_("id", set_ids).execute())} if set_ids else {}
    rows = []
    for product in products:
        classified = classify_sealed_product(product.get("name")); set_row = sets.get(str(product.get("set_id")), {})
        rows.append({"sealedProductId": str(product["id"]), "productName": product.get("name"),
                     "productType": product.get("product_type"), "familyKey": classified["productFamily"],
                     "familyName": classified["productFamilyLabel"], "setId": str(product.get("set_id") or "") or None,
                     "setName": set_row.get("name"), "setCanonicalKey": set_row.get("canonical_key"),
                     "imageSmallUrl": product.get("image_small_url"), "imageLargeUrl": product.get("image_large_url")})
    rows.sort(key=lambda row: ((row.get("productName") or "").casefold(), row["sealedProductId"]))
    facets = sorted(({"value": key, "label": label} for key, label in
                     {(row["familyKey"], row["familyName"]) for row in rows}), key=lambda item: item["label"])
    filtered = _filter_sort(rows, search=search, family=family, sort="productName", direction="asc")
    selected, meta = _page(filtered, page, page_size)
    return {"contractVersion": "rankings-product-catalogue-v2", "status": "available", **meta,
            "families": facets, "rows": selected}
