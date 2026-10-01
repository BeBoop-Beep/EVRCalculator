"""Read-only, frontend-ready contracts for the Rankings redesign.

The service deliberately projects prepared/current authorities.  It does not
calculate ranking models, scan simulation outcomes, or expose lineage fields.
"""
from __future__ import annotations

from datetime import date
from typing import Any, Dict, Iterable, Mapping, Optional, Sequence

from backend.rankings.public_relative import benchmark_relative_tier
from backend.domain.pokemon.sealed_product_classifier import classify_sealed_product


BENCHMARK_REFERENCE_SCORE = 5.0


def _rows(response: Any) -> list[dict[str, Any]]:
    return list(getattr(response, "data", None) or [])


def _all_rows(query_factory: Any, *, page_size: int = 1000) -> list[dict[str, Any]]:
    """Exhaust a PostgREST range without silently accepting its row cap."""
    result: list[dict[str, Any]] = []
    offset = 0
    while True:
        page = _rows(query_factory().range(offset, offset + page_size - 1).execute())
        result.extend(page)
        if len(page) < page_size:
            return result
        offset += page_size


def _number(value: Any) -> Optional[float]:
    return None if value is None else float(value)


def _day(value: Any) -> Optional[str]:
    return str(value)[:10] if value is not None else None


def benchmark_presentation(score: Any, *, rank: Any = None, cohort_size: Any = None,
                           tier: Optional[str] = None,
                           reference: float = BENCHMARK_REFERENCE_SCORE) -> dict[str, Any]:
    value = _number(score)
    delta = None if value is None else value - reference
    position = None if delta is None else ("at" if abs(delta) < 1e-9 else "above" if delta > 0 else "below")
    return {
        "score": value,
        "rank": rank,
        "cohortSize": cohort_size,
        # Benchmark scores are centered at 5.0: a neutral 4.75-5.25 band is C
        # whatever the rank, so the tier needs score AND cohort position.
        "tier": tier or benchmark_relative_tier(value, rank, cohort_size, reference),
        "benchmarkReferenceScore": reference,
        "deltaVsBenchmark": delta,
        "benchmarkPosition": position,
    }


def benchmark_reference() -> dict[str, Any]:
    return {"label": "Pokémon Overall Average", "score": BENCHMARK_REFERENCE_SCORE, "iconKey": "pokemon"}


def read_financial_history_page(client: Any, *, entities: Sequence[Mapping[str, str]],
                                start_date: date, end_date: date, limit: int,
                                after: Optional[Mapping[str, Any]] = None) -> dict[str, Any]:
    """Read the exact history with a DB-bounded keyset query per entity type."""
    selected: list[dict[str, Any]] = []
    columns = ("market_date,entity_type,entity_id,absolute_financial_rip_score,"
               "overall_financial_rip_reference,absolute_delta_vs_overall,rank,"
               "cohort_size,financial_model_version")
    for entity_type in ("set", "era"):
        ids = sorted({str(item["entity_id"]) for item in entities if item["entity_type"] == entity_type})
        if not ids:
            continue
        query = (client.table("pokemon_financial_rip_history_rows_v1").select(columns)
                 .eq("entity_type", entity_type).in_("entity_id", ids)
                 .gte("market_date", start_date.isoformat()).lte("market_date", end_date.isoformat()))
        if after:
            cursor_date = _day(after.get("marketDate")) or ""
            cursor_type = str(after.get("entityType") or "")
            cursor_id = str(after.get("entityId") or "")
            if entity_type < cursor_type:
                query = query.gt("market_date", cursor_date)
            elif entity_type > cursor_type:
                query = query.gte("market_date", cursor_date)
            else:
                query = query.or_(
                    f"market_date.gt.{cursor_date},and(market_date.eq.{cursor_date},entity_id.gt.{cursor_id})"
                )
        selected.extend(_rows(query.order("market_date").order("entity_id").limit(limit + 1).execute()))
    selected.sort(key=lambda row: (_day(row.get("market_date")) or "", row.get("entity_type") or "", str(row.get("entity_id") or "")))
    page = selected[:limit]
    has_more = len(selected) > limit
    projected = [{
        "marketDate": _day(row.get("market_date")), "entityType": row.get("entity_type"),
        "entityId": str(row.get("entity_id")),
        "absoluteFinancialRipScore": _number(row.get("absolute_financial_rip_score")),
        "overallFinancialRipReference": _number(row.get("overall_financial_rip_reference")),
        "absoluteDeltaVsOverall": _number(row.get("absolute_delta_vs_overall")),
        "rank": row.get("rank"), "cohortSize": row.get("cohort_size"),
        "financialModelVersion": row.get("financial_model_version"),
    } for row in page]
    oldest = _rows(client.table("pokemon_financial_rip_history_publications_v1")
                   .select("market_date").order("market_date").limit(1).execute())
    newest = _rows(client.table("pokemon_financial_rip_history_publications_v1")
                   .select("market_date").order("market_date", desc=True).limit(1).execute())
    next_cursor = None
    if has_more and projected:
        last = projected[-1]
        next_cursor = {key: last[key] for key in ("marketDate", "entityType", "entityId")}
    return {
        "contractVersion": "financial-rip-history-v2", "status": "available",
        "historyAvailableFrom": _day(oldest[0].get("market_date")) if oldest else None,
        "historyAvailableThrough": _day(newest[0].get("market_date")) if newest else None,
        "rows": projected, "hasMore": has_more, "nextCursor": next_cursor,
    }


def read_financial_cohort(client: Any) -> dict[str, Any]:
    latest = _rows(client.table("pokemon_financial_rip_history_publications_v1")
                   .select("market_date").order("market_date", desc=True).limit(1).execute())
    market_date = _day(latest[0]["market_date"]) if latest else None
    rows = _rows(client.table("pokemon_financial_rip_history_rows_v1").select("entity_type,entity_id")
                 .eq("market_date", market_date).eq("entity_type", "set").execute()) if market_date else []
    set_ids = sorted({str(row["entity_id"]) for row in rows})
    sets = _rows(client.table("sets").select("id,name,canonical_key,era_id").in_("id", set_ids).execute()) if set_ids else []
    era_ids = sorted({str(row["era_id"]) for row in sets if row.get("era_id")})
    eras = _rows(client.table("eras").select("id,name,canonical_key").in_("id", era_ids).execute()) if era_ids else []
    by_era: dict[str, list[dict[str, Any]]] = {str(row["id"]): [] for row in eras}
    for row in sets:
        by_era.setdefault(str(row.get("era_id")), []).append({
            "setId": str(row["id"]), "setName": row.get("name"), "canonicalKey": row.get("canonical_key")})
    return {"contractVersion": "financial-rip-cohort-v1", "marketDate": market_date, "eras": [{
        "eraId": str(era["id"]), "eraName": era.get("name"), "canonicalKey": era.get("canonical_key"),
        "sets": sorted(by_era.get(str(era["id"]), []), key=lambda item: item.get("setName") or ""),
    } for era in sorted(eras, key=lambda item: item.get("name") or "")]}


def read_card_facets(client: Any, *, lens: str) -> dict[str, Any]:
    rows = _rows(client.table("pokemon_card_ranking_facets_current_v1").select(
        "lens,source_authority_id,source_model_version,as_of_date,dimension_type,facet_key,display_name,entity_id,parent_entity_id"
    ).eq("lens", lens).order("dimension_type").order("display_name").execute())
    if not rows:
        return {"contractVersion": "card-ranking-facets-v1", "status": "unavailable", "lens": lens,
                "eras": [], "sets": [], "rarities": [], "subjectTypes": []}
    first = rows[0]
    eras = [{"eraId": str(row["entity_id"]), "eraName": row.get("display_name"), "canonicalKey": row.get("facet_key")}
            for row in rows if row.get("dimension_type") == "era"]
    sets = [{"setId": str(row["entity_id"]), "setName": row.get("display_name"), "canonicalKey": row.get("facet_key"),
             "eraId": str(row["parent_entity_id"]) if row.get("parent_entity_id") else None}
            for row in rows if row.get("dimension_type") == "set"]
    return {
        "contractVersion": "card-ranking-facets-v1", "status": "available", "lens": lens,
        "sourceAuthorityId": str(first.get("source_authority_id")),
        "sourceModelVersion": first.get("source_model_version"), "asOfDate": _day(first.get("as_of_date")),
        "eras": eras, "sets": sets,
        "rarities": [{"key": row.get("facet_key"), "name": row.get("display_name")} for row in rows if row.get("dimension_type") == "rarity"],
        "subjectTypes": [row.get("facet_key") for row in rows if row.get("dimension_type") == "subject_type"],
    }


def _freshness(source: Optional[str], reference: Optional[str]) -> str:
    if not source or not reference:
        return "unavailable"
    return "same_day" if source == reference else "older" if source < reference else "newer"


def read_pack_economics(client: Any) -> dict[str, Any]:
    latest = _rows(client.table("pokemon_rip_stats_snapshot_latest").select("market_date,payload_json").limit(1).execute())
    if not latest:
        return {"contractVersion": "rankings-pack-economics-v1", "status": "unavailable", "sets": []}
    opening_date = _day(latest[0].get("market_date"))
    economics = (latest[0].get("payload_json") or {}).get("openingEconomics") or {}
    opening_sets = economics.get("sets") or []
    opening_set_ids = sorted({str(row.get("setId")) for row in opening_sets if row.get("setId")})
    set_artwork = {str(row["id"]): row for row in _rows(client.table("sets").select(
        "id,logo_image_url,symbol_image_url"
    ).in_("id", opening_set_ids).execute())} if opening_set_ids else {}
    best_pointer = _rows(client.table("budget_product_best_open_price_latest").select(
        "snapshot_id,source_budget_snapshot_id,source_market_date"
    ).limit(1).execute())
    best_date = _day(best_pointer[0].get("source_market_date")) if best_pointer else None
    best_rows = _rows(client.table("budget_product_best_open_price_rows").select(
        "sealed_product_id,set_id,product_family,source_calculation_run_id,current_market_price,current_quantity,"
        "current_actual_committed_capital,status,best_open_price,price_gap_dollars,price_gap_percent"
    ).eq("snapshot_id", best_pointer[0]["snapshot_id"]).execute()) if best_pointer else []
    product_ids = sorted({str(row["sealed_product_id"]) for row in best_rows})
    products = {str(row["id"]): row for row in _rows(client.table("sealed_products").select("id,set_id,name")
                .in_("id", product_ids).execute())} if product_ids else {}
    source_run_ids = sorted({str(row["source_calculation_run_id"]) for row in best_rows
                             if row.get("source_calculation_run_id")})
    exact_economics_rows = _rows(client.table("simulation_sealed_product_results").select(
        "calculation_run_id,sealed_product_id,set_id,product_family,pack_count,random_pack_count,"
        "product_market_cost,price_as_of,expected_value,chance_to_recover_cost"
    ).in_("sealed_product_id", product_ids).in_("calculation_run_id", source_run_ids).execute()
    ) if product_ids and source_run_ids else []
    exact_economics = {(str(row["sealed_product_id"]), str(row["calculation_run_id"])): row
                       for row in exact_economics_rows}
    best_by_set_family: dict[tuple[str, str], list[dict[str, Any]]] = {}
    products_by_set: dict[str, list[dict[str, Any]]] = {}
    for row in best_rows:
        product_id = str(row["sealed_product_id"])
        run_id = str(row.get("source_calculation_run_id") or "")
        exact = exact_economics.get((product_id, run_id), {})
        pack_count = _number(exact.get("random_pack_count") if exact.get("random_pack_count") is not None
                             else exact.get("pack_count"))
        unit_price = _number(exact.get("product_market_cost") if exact else row.get("current_market_price"))
        expected_value = _number(exact.get("expected_value"))
        average_cost = unit_price / pack_count if unit_price is not None and pack_count else None
        expected_per_pack = expected_value / pack_count if expected_value is not None and pack_count else None
        item = {"sealedProductId": product_id, "productName": products.get(product_id, {}).get("name"),
                "setId": str(row.get("set_id")), "familyKey": row.get("product_family"),
                "familyName": row.get("product_family"), "packCount": pack_count,
                "purchaseQuantity": _number(row.get("current_quantity")),
                "actualCommittedCapital": _number(row.get("current_actual_committed_capital")),
                "unitPrice": unit_price, "averagePackCostPerPack": average_cost,
                "expectedValuePerPack": expected_per_pack,
                "modeledReturnOnSpend": (expected_value / unit_price
                                          if expected_value is not None and unit_price else None),
                "chanceToRecoverCost": _number(exact.get("chance_to_recover_cost")),
                "entertainmentCostPerPack": (average_cost - expected_per_pack
                                              if average_cost is not None and expected_per_pack is not None else None),
                "economicsAvailabilityStatus": "available" if exact else "unavailable",
                "economicsSourceMarketDate": _day(exact.get("price_as_of")),
                "sourceCalculationRunId": run_id or None,
                "marketPrice": _number(row.get("current_market_price")), "bestOpenPrice": _number(row.get("best_open_price")),
                "bestOpenStatus": row.get("status"), "bestOpenPriceGapDollars": _number(row.get("price_gap_dollars")),
                "bestOpenPriceGapPercent": _number(row.get("price_gap_percent")), "bestOpenSourceMarketDate": best_date,
                "bestOpenMarketSourceDate": best_date,
                "bestOpenFreshnessStatus": _freshness(best_date, opening_date)}
        best_by_set_family.setdefault((str(row["set_id"]), str(row.get("product_family") or "")), []).append(item)
        products_by_set.setdefault(str(row["set_id"]), []).append(item)
    def econ(source: Mapping[str, Any]) -> dict[str, Any]:
        return {"averagePackCostPerPack": _number(source.get("averageCostPerPack")),
                "expectedValuePerPack": _number(source.get("averageModelBreakEvenPerPack")),
                "modeledReturnOnSpend": _number(source.get("modeledReturnOnSpend")),
                "chanceToRecoverCost": _number(source.get("chanceToRecoverCost")),
                "entertainmentCostPerPack": _number(source.get("entertainmentCostPerPack") if source.get("entertainmentCostPerPack") is not None
                                                     else source.get("averageEntertainmentCostPerPack"))}
    projected_sets = []
    for row in opening_sets:
        set_id = str(row.get("setId")); families = []
        artwork = set_artwork.get(set_id, {})
        for family in row.get("familyEconomics") or row.get("families") or row.get("productFamilies") or []:
            family_key = str(family.get("familyKey") or family.get("productFamily") or family.get("family") or "")
            family_products = best_by_set_family.get((set_id, family_key), [])
            families.append({"familyKey": family_key, "familyName": family.get("familyName") or family_key,
                             "productCount": family.get("productCount") or family.get("productSkuCount") or len(family_products), **econ(family),
                             "bestOpenDisplayMode": "single" if len(family_products) == 1 else "multiple",
                             "products": family_products})
        projected_sets.append({"setId": set_id, "setName": row.get("setName"), "canonicalKey": row.get("setCanonicalKey"),
                               "logoImageUrl": artwork.get("logo_image_url"), "symbolImageUrl": artwork.get("symbol_image_url"),
                               "era": {"eraId": row.get("eraId"), "eraName": row.get("eraName")},
                               "productFamilyCount": row.get("productFamilyCount") or len(families),
                               "productCount": row.get("productCount") or row.get("productSkuCount"), **econ(row), "openingEconomicsMarketDate": opening_date,
                               "families": families,
                               "products": sorted(products_by_set.get(set_id, []),
                                                  key=lambda product: ((product.get("productName") or "").casefold(),
                                                                       product["sealedProductId"]))})
    return {"contractVersion": "rankings-pack-economics-v1", "status": "available",
            "openingEconomicsMarketDate": opening_date, "bestOpenSourceMarketDate": best_date,
            "bestOpenFreshnessStatus": _freshness(best_date, opening_date), "sets": projected_sets}


def read_public_pack_economics_preview(client: Any) -> dict[str, Any]:
    """Public Set-level counts and average pack cost; no component economics."""
    latest = _rows(client.table("pokemon_rip_stats_snapshot_latest")
                   .select("market_date,payload_json").limit(1).execute())
    if not latest:
        return {"contractVersion": "rankings-pack-economics-preview-v1", "status": "unavailable", "sets": []}
    market_date = _day(latest[0].get("market_date"))
    source = ((latest[0].get("payload_json") or {}).get("openingEconomics") or {}).get("sets") or []
    set_ids = sorted({str(row.get("setId")) for row in source if row.get("setId")})
    sets = _rows(client.table("sets").select(
        "id,name,canonical_key,era_id,logo_image_url,symbol_image_url"
    ).in_("id", set_ids).execute()) if set_ids else []
    by_set = {str(row["id"]): row for row in sets}
    era_ids = sorted({str(row.get("era_id")) for row in sets if row.get("era_id")})
    eras = {str(row["id"]): row for row in _rows(client.table("eras")
            .select("id,name,canonical_key").in_("id", era_ids).execute())} if era_ids else {}
    projected = []
    for row in source:
        set_id = str(row.get("setId"))
        identity = by_set.get(set_id, {})
        era = eras.get(str(identity.get("era_id") or row.get("eraId")), {})
        projected.append({
            "setId": set_id,
            "setName": identity.get("name") or row.get("setName"),
            "canonicalKey": identity.get("canonical_key") or row.get("setCanonicalKey"),
            "logoImageUrl": identity.get("logo_image_url"),
            "symbolImageUrl": identity.get("symbol_image_url"),
            "era": {"eraId": str(identity.get("era_id") or row.get("eraId") or "") or None,
                    "eraName": era.get("name") or row.get("eraName"),
                    "canonicalKey": era.get("canonical_key")},
            "productFamilyCount": row.get("productFamilyCount") or len(row.get("familyEconomics") or []),
            "productCount": row.get("productCount") or row.get("productSkuCount"),
            "averagePackCostPerPack": _number(row.get("averageCostPerPack")),
            "openingEconomicsMarketDate": market_date,
        })
    projected.sort(key=lambda row: ((row.get("setName") or "").casefold(), row["setId"]))
    return {"contractVersion": "rankings-pack-economics-preview-v1", "status": "available",
            "openingEconomicsMarketDate": market_date, "sets": projected}


def read_public_product_catalogue(client: Any) -> dict[str, Any]:
    """Alphabetical sealed-product identities independent of ranking membership."""
    products = _all_rows(lambda: client.table("sealed_products").select(
        "id,set_id,name,product_type,image_small_url,image_large_url"
    ).order("name").order("id"))
    set_ids = sorted({str(row.get("set_id")) for row in products if row.get("set_id")})
    sets = _rows(client.table("sets").select("id,name,canonical_key,era_id")
                 .in_("id", set_ids).execute()) if set_ids else []
    by_set = {str(row["id"]): row for row in sets}
    era_ids = sorted({str(row.get("era_id")) for row in sets if row.get("era_id")})
    eras = {str(row["id"]): row for row in _rows(client.table("eras")
            .select("id,name,canonical_key").in_("id", era_ids).execute())} if era_ids else {}
    rows = []
    for product in products:
        identity = classify_sealed_product(product.get("name"))
        set_row = by_set.get(str(product.get("set_id")), {})
        era = eras.get(str(set_row.get("era_id")), {})
        rows.append({
            "sealedProductId": str(product["id"]), "productName": product.get("name"),
            "productType": product.get("product_type"),
            "familyKey": identity["productFamily"], "familyName": identity["productFamilyLabel"],
            "setId": str(product.get("set_id") or "") or None, "setName": set_row.get("name"),
            "setCanonicalKey": set_row.get("canonical_key"),
            "era": {"eraId": str(set_row.get("era_id") or "") or None,
                    "eraName": era.get("name"), "canonicalKey": era.get("canonical_key")},
            "imageSmallUrl": product.get("image_small_url"), "imageLargeUrl": product.get("image_large_url"),
        })
    rows.sort(key=lambda row: ((row.get("productName") or "").casefold(), row["sealedProductId"]))
    return {"contractVersion": "rankings-product-catalogue-v1", "status": "available", "rows": rows}


def project_product_contract(payload: Mapping[str, Any], *, view: str,
                             best_open_products: Optional[Mapping[str, Mapping[str, Any]]] = None,
                             product_benchmark: Optional[Mapping[str, Any]] = None) -> dict[str, Any]:
    """Split the existing single prepared Product read without another DB pass."""
    if view not in {"scores", "economics"}:
        raise ValueError("view must be scores or economics")
    best_meta = payload.get("bestOpenPrice") or {}
    source_date = _day(best_meta.get("sourceMarketDate"))
    market_date = _day(payload.get("marketDate") or (payload.get("authority") or {}).get("marketDate"))
    authority = payload.get("authority") or {}
    benchmark_available = bool(product_benchmark and product_benchmark.get("status") == "available")
    benchmark_rows = {str(row.get("sealedProductId")): row for row in
                      (product_benchmark or {}).get("rows") or []} if benchmark_available else {}
    score_contract = ({
        "scoreKind": "benchmark", "scoreScale": "0-10",
        "metricVersion": product_benchmark.get("metricVersion"), "benchmarkAvailable": True,
        "publicationId": product_benchmark.get("publicationId"),
        "calibrationVersion": product_benchmark.get("calibrationVersion"),
        "overallReference": product_benchmark.get("overallReference"),
    } if benchmark_available else {
        "scoreKind": "absolute", "scoreScale": "0-100",
        "metricVersion": authority.get("overallRipVersion"), "benchmarkAvailable": False,
        "publicationId": None, "calibrationVersion": None,
        "overallReference": {"status": "unavailable", "value": None,
                             "reason": "product_benchmark_publication_pending"},
    })
    projected = []
    for row in payload.get("rows") or []:
        identity = {"sealedProductId": row.get("sealedProductId"), "productName": row.get("productName"),
                    "setId": row.get("setId"), "setName": row.get("setName"),
                    "setCanonicalKey": row.get("setCanonicalKey"), "familyKey": row.get("productFamily"),
                    "familyName": row.get("productFamilyLabel"), "packCount": row.get("packCount")}
        if view == "scores":
            benchmark_row = benchmark_rows.get(str(row.get("sealedProductId")), {})
            score_value = (_number(benchmark_row.get("benchmarkScore")) if benchmark_available
                           else _number(row.get("overallRipScore")))
            item = {**identity,
                    "rank": benchmark_row.get("rank") if benchmark_available else row.get("budgetRank"),
                    "rankScope": "benchmark" if benchmark_available else "full_market",
                    "cohortSize": benchmark_row.get("cohortSize") if benchmark_available else row.get("budgetCohortSize"),
                    "ripScore": {"scoreKind": score_contract["scoreKind"], "scoreScale": score_contract["scoreScale"],
                                 "scoreValue": score_value, "metricVersion": score_contract["metricVersion"],
                                 "benchmarkAvailable": benchmark_available,
                                 "benchmarkValue": score_value if benchmark_available else None,
                                 "benchmarkReference": score_contract["overallReference"] if benchmark_available else None,
                                 "benchmarkRank": benchmark_row.get("rank") if benchmark_available else None,
                                 "benchmarkCohortSize": benchmark_row.get("cohortSize") if benchmark_available else None,
                                 "publicationId": score_contract["publicationId"],
                                 "calibrationVersion": score_contract["calibrationVersion"]},
                    "financialRip": row.get("financialRipScore"),
                    "setChaseAccessibility": row.get("chaseAccessibility"),
                    "parentSetCollector": row.get("collectorAppealScore")}
        else:
            unit_price = _number(row.get("unitPrice")); expected = _number(row.get("expectedValue"))
            quantity = _number(row.get("quantity")) or 1.0
            pack_count = _number(row.get("packCount"))
            expected_per_pack = (expected / (quantity * pack_count)
                                 if expected is not None and pack_count and quantity else None)
            exact_best = (best_open_products or {}).get(str(row.get("sealedProductId")), {})
            exact_date = _day(exact_best.get("bestOpenSourceMarketDate")) or source_date
            item = {**identity, "unitPrice": unit_price,
                    "bestOpenPrice": _number(exact_best.get("bestOpenPrice") if exact_best else row.get("bestOpenPrice")),
                    "bestOpenMarketPrice": _number(exact_best.get("bestOpenMarketPrice")) if exact_best else None,
                    "bestOpenMarketSourceDate": _day(exact_best.get("bestOpenMarketSourceDate")) if exact_best else None,
                    "bestOpenStatus": exact_best.get("bestOpenStatus") if exact_best else row.get("bestOpenPriceStatus"),
                    "bestOpenPriceGapDollars": _number(exact_best.get("bestOpenPriceGapDollars")) if exact_best else None,
                    "bestOpenPriceGapPercent": _number(exact_best.get("bestOpenPriceGapPercent")) if exact_best else None,
                    "bestOpenSourceMarketDate": exact_date,
                    "bestOpenFreshnessStatus": exact_best.get("bestOpenFreshnessStatus") if exact_best else _freshness(exact_date, market_date),
                    "expectedValuePerPack": expected_per_pack,
                    "modeledReturnOnSpend": _number(row.get("averageReturn")) if row.get("averageReturn") is not None
                                            else expected / (unit_price * quantity) if expected is not None and unit_price else None,
                    "chanceToRecoverCost": _number(row.get("chanceToRecoverCost"))}
        projected.append(item)
    result = {"contractVersion": f"rankings-products-{view}-v2", "status": "available" if payload.get("available") else "unavailable",
              "marketDate": market_date, "view": view, "rows": projected}
    if view == "scores":
        result["scoreContract"] = score_contract
    return result


def read_product_best_open_map(client: Any, *, reference_date: Optional[str] = None) -> dict[str, dict[str, Any]]:
    """Read the exact Product Best-Open authority directly, without Set hierarchy work."""
    pointer = _rows(client.table("budget_product_best_open_price_latest")
                    .select("snapshot_id,source_market_date").limit(1).execute())
    if not pointer:
        return {}
    source_date = _day(pointer[0].get("source_market_date"))
    rows = _rows(client.table("budget_product_best_open_price_rows").select(
        "sealed_product_id,current_market_price,status,best_open_price,price_gap_dollars,price_gap_percent"
    ).eq("snapshot_id", pointer[0]["snapshot_id"]).execute())
    return {str(row["sealed_product_id"]): {
        "bestOpenPrice": _number(row.get("best_open_price")),
        "bestOpenMarketPrice": _number(row.get("current_market_price")),
        "bestOpenMarketSourceDate": source_date, "bestOpenStatus": row.get("status"),
        "bestOpenPriceGapDollars": _number(row.get("price_gap_dollars")),
        "bestOpenPriceGapPercent": _number(row.get("price_gap_percent")),
        "bestOpenSourceMarketDate": source_date,
        "bestOpenFreshnessStatus": _freshness(source_date, _day(reference_date)),
    } for row in rows}


def read_scorecards(client: Any, *, entity_type: str, benchmark_key: str,
                    calibration_version: str) -> dict[str, Any]:
    if entity_type not in {"set", "era"}:
        raise ValueError("entity_type must be set or era")
    publications = _rows(client.table("pokemon_rip_benchmark_publications_v1")
                         .select("id,market_date").eq("benchmark_key", benchmark_key)
                         .eq("calibration_version", calibration_version).eq("publication_status", "published")
                         .order("market_date", desc=True).limit(1).execute())
    if not publications:
        return {"contractVersion": "rankings-scorecards-v1", "status": "unavailable", "rows": []}
    rows = _rows(client.table("pokemon_rip_benchmark_rows_v1").select(
        "entity_id,metric_key,benchmark_score,rank,cohort_size,benchmark_status"
    ).eq("publication_id", publications[0]["id"]).eq("entity_type", entity_type)
                 .in_("metric_key", ["overall", "financial", "collector", "chase"]).execute())
    ids = sorted({str(row["entity_id"]) for row in rows})
    identities = _rows(client.table("sets" if entity_type == "set" else "eras")
                       .select("id,name,canonical_key" + (",era_id,logo_image_url,symbol_image_url" if entity_type == "set" else ""))
                       .in_("id", ids).execute()) if ids else []
    names = {str(row["id"]): row for row in identities}
    era_names: dict[str, dict[str, Any]] = {}
    modeled_counts: dict[str, int] = {}
    if entity_type == "set":
        era_ids = sorted({str(row["era_id"]) for row in identities if row.get("era_id")})
        era_names = {str(row["id"]): row for row in _rows(
            client.table("eras").select("id,name,canonical_key").in_("id", era_ids).execute()
        )} if era_ids else {}
    else:
        financial_sets = _rows(client.table("pokemon_rip_benchmark_rows_v1").select("entity_id")
                               .eq("publication_id", publications[0]["id"]).eq("entity_type", "set")
                               .eq("metric_key", "financial").execute())
        financial_set_ids = sorted({str(row["entity_id"]) for row in financial_sets})
        modeled_sets = _rows(client.table("sets").select("id,era_id").in_("id", financial_set_ids).execute()) if financial_set_ids else []
        for set_row in modeled_sets:
            key = str(set_row.get("era_id")); modeled_counts[key] = modeled_counts.get(key, 0) + 1
    grouped: dict[str, dict[str, Any]] = {}
    for row in rows:
        entity_id = str(row["entity_id"]); identity = names.get(entity_id, {})
        base = {"entityId": entity_id, "name": identity.get("name"), "canonicalKey": identity.get("canonical_key")}
        if entity_type == "set":
            era = era_names.get(str(identity.get("era_id")), {})
            base["era"] = {"eraId": str(identity.get("era_id")), "eraName": era.get("name"),
                           "canonicalKey": era.get("canonical_key")}
            base["logoImageUrl"] = identity.get("logo_image_url")
            base["symbolImageUrl"] = identity.get("symbol_image_url")
        else:
            base["modeledSetCount"] = modeled_counts.get(entity_id, 0)
        item = grouped.setdefault(entity_id, base)
        item[row["metric_key"]] = benchmark_presentation(row.get("benchmark_score"), rank=row.get("rank"),
                                                           cohort_size=row.get("cohort_size"))
    return {"contractVersion": "rankings-scorecards-v1", "status": "available",
            "marketDate": _day(publications[0]["market_date"]), "entityType": entity_type,
            "benchmarkReference": benchmark_reference(), "rows": sorted(grouped.values(), key=lambda row: (row.get("overall") or {}).get("rank") or 999999)}


def read_public_headlines(client: Any, *, entity_type: str, benchmark_key: str,
                          calibration_version: str) -> dict[str, Any]:
    """Narrow public Overall-only Era/Set contract."""
    if entity_type not in {"set", "era"}:
        raise ValueError("entity_type must be set or era")
    publications = _rows(client.table("pokemon_rip_benchmark_publications_v1")
                         .select("id,market_date,benchmark_key,calibration_version,overall_model_version")
                         .eq("benchmark_key", benchmark_key).eq("calibration_version", calibration_version)
                         .eq("publication_status", "published").order("market_date", desc=True).limit(1).execute())
    if not publications:
        return {"contractVersion": "rankings-public-headlines-v1", "status": "unavailable", "rows": []}
    publication = publications[0]
    raw = _rows(client.table("pokemon_rip_benchmark_rows_v1").select(
        "entity_id,benchmark_score,rank,cohort_size,benchmark_status,benchmark_reason"
    ).eq("publication_id", publication["id"]).eq("entity_type", entity_type)
                .eq("metric_key", "overall").execute())
    ids = sorted({str(row["entity_id"]) for row in raw})
    columns = "id,name,canonical_key" + (",era_id,logo_image_url,symbol_image_url" if entity_type == "set" else "")
    identities = _rows(client.table("sets" if entity_type == "set" else "eras")
                       .select(columns).in_("id", ids).execute()) if ids else []
    by_id = {str(row["id"]): row for row in identities}
    era_names = {}
    if entity_type == "set":
        era_ids = sorted({str(row.get("era_id")) for row in identities if row.get("era_id")})
        era_names = {str(row["id"]): row for row in _rows(client.table("eras")
                     .select("id,name,canonical_key").in_("id", era_ids).execute())} if era_ids else {}
    modeled_counts: dict[str, int] = {}
    if entity_type == "era":
        all_sets = _rows(client.table("sets").select("id,era_id").execute())
        for set_row in all_sets:
            key = str(set_row.get("era_id")); modeled_counts[key] = modeled_counts.get(key, 0) + 1
    rows = []
    for row in raw:
        entity_id = str(row["entity_id"]); identity = by_id.get(entity_id, {})
        item = {"entityId": entity_id, "name": identity.get("name"),
                "canonicalKey": identity.get("canonical_key"),
                "overall": {**benchmark_presentation(row.get("benchmark_score"), rank=row.get("rank"),
                                                       cohort_size=row.get("cohort_size")),
                            "status": row.get("benchmark_status"), "statusReason": row.get("benchmark_reason")}}
        if entity_type == "set":
            era = era_names.get(str(identity.get("era_id")), {})
            item.update({"logoImageUrl": identity.get("logo_image_url"), "symbolImageUrl": identity.get("symbol_image_url"),
                         "era": {"eraId": str(identity.get("era_id") or "") or None, "eraName": era.get("name"),
                                 "canonicalKey": era.get("canonical_key")}})
        else:
            item["modeledSetCount"] = modeled_counts.get(entity_id, 0)
        rows.append(item)
    rows.sort(key=lambda item: ((item.get("overall") or {}).get("rank") or 999999, (item.get("name") or "").casefold()))
    return {"contractVersion": "rankings-public-headlines-v1", "status": "available",
            "publicationId": str(publication["id"]), "marketDate": _day(publication.get("market_date")),
            "benchmarkKey": publication.get("benchmark_key") or benchmark_key,
            "calibrationVersion": publication.get("calibration_version") or calibration_version,
            "overallModelVersion": publication.get("overall_model_version"), "entityType": entity_type,
            "benchmarkReference": benchmark_reference(), "rows": rows}


def read_overview_v2(client: Any, *, legacy_headlines: Mapping[str, Any]) -> dict[str, Any]:
    opening_rows = _rows(client.table("pokemon_rip_stats_snapshot_latest").select("market_date,payload_json").limit(1).execute())
    opening = ((opening_rows[0].get("payload_json") or {}).get("openingEconomics") or {}) if opening_rows else {}
    global_economics = opening.get("global") or {}
    population = opening.get("population") or {}
    set_rows = opening.get("sets") or []
    lowest = min((row for row in set_rows if row.get("averageCostPerPack") is not None),
                 key=lambda row: float(row["averageCostPerPack"]), default=None)
    financial = _rows(client.table("pokemon_financial_rip_history_publications_v1")
                      .select("market_date,overall_financial_rip_reference,financial_model_version")
                      .order("market_date", desc=True).limit(1).execute())
    current = financial[0] if financial else {}
    def headline(item: Any) -> Any:
        if not item:
            return None
        return {**{key: item.get(key) for key in ("entityId", "name", "canonicalKey") if key in item},
                "score": benchmark_presentation(item.get("benchmarkScore"), rank=item.get("rank"), cohort_size=item.get("cohortSize"))}
    top_era = headline(legacy_headlines.get("topEra"))
    top_set = headline(legacy_headlines.get("topSet"))
    if top_set and top_set.get("entityId"):
        identity_rows = _rows(client.table("sets").select("id,logo_image_url,symbol_image_url")
                              .eq("id", top_set["entityId"]).limit(1).execute())
        if identity_rows:
            top_set["logoImageUrl"] = identity_rows[0].get("logo_image_url")
            top_set["symbolImageUrl"] = identity_rows[0].get("symbol_image_url")
    if top_era:
        top_era["modeledSetCount"] = sum(1 for row in set_rows if str(row.get("eraId")) == str(top_era.get("entityId")))
    return {"contractVersion": "rankings-overview-v2", "status": legacy_headlines.get("status"),
            "marketDate": legacy_headlines.get("marketDate"), "topSet": top_set,
            "topEra": top_era,
            "lowestAveragePackCost": None if not lowest else {"setId": lowest.get("setId"), "setName": lowest.get("setName"),
                "canonicalKey": lowest.get("setCanonicalKey"), "averagePackCost": _number(lowest.get("averageCostPerPack"))},
            "modeledCoverage": {"setCount": population.get("setCount"), "productCount": population.get("productSkuCount"),
                                "productFamilyCount": population.get("productFamilyCount")},
            "openingEconomics": {"marketDate": _day(opening_rows[0].get("market_date")) if opening_rows else None,
                "overallExpectedValuePerPack": _number(global_economics.get("averageModelBreakEvenPerPack")),
                "averagePackCostPerPack": _number(global_economics.get("averageCostPerPack")),
                "modeledReturnOnSpend": _number(global_economics.get("modeledReturnOnSpend")),
                "chanceToRecoverCost": _number(global_economics.get("chanceToRecoverCost")),
                "entertainmentCostPerPack": _number(global_economics.get("entertainmentCostPerPack")
                                                     if global_economics.get("entertainmentCostPerPack") is not None
                                                     else global_economics.get("averageEntertainmentCostPerPack"))},
            "overallFinancialRip": None if not financial else {"absoluteScore": _number(current.get("overall_financial_rip_reference")),
                "marketDate": _day(current.get("market_date")), "financialModelVersion": current.get("financial_model_version"),
                "definitionKey": "equal_set_absolute_financial_rip_reference_v1"}}
