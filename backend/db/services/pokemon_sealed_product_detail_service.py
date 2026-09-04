"""Narrow public contract for one canonical Pokemon sealed-product page."""

from __future__ import annotations

from typing import Any, Dict, Iterable, List, Mapping, Optional
from urllib.parse import quote

from backend.db.clients.supabase_client import service_read_client
from backend.db.services.pokemon_public_snapshot_service import (
    DEFAULT_RANKINGS_SCOPE,
    _rankings_publication_identity_mismatches,
)
from backend.db.services.pokemon_set_sealed_market_snapshot_service import (
    MOVEMENT_WINDOWS,
    normalize_daily_history,
    movement,
    read_snapshot,
)
from backend.db.services.pokemon_sets_catalog_service import _slugify as canonical_set_route_slug
from backend.domain.pokemon.entertainment_cost import entertainment_cost_contract
from backend.domain.pokemon.sealed_product_classifier import FAMILY_LABELS, classify_sealed_product
from backend.domain.pokemon.sealed_product_comparison_scope import (
    COMPARABLE_FAMILIES,
    sealed_product_comparison_scope_contract,
)
from backend.desirability.scoring_config import OVERALL_RIP_V12_VERSION

CONTRACT_VERSION = "pokemon-sealed-product-detail-v1"
SAME_SET_LIMIT = 10
DETAIL_FIELDS = (
    "calculation_run_id,sealed_product_id,product_family,product_market_cost,price_as_of,"
    "expected_value,median_value,p05_value,p95_value,p99_value,chance_to_recover_cost,"
    "expected_loss_when_losing,median_loss_when_losing,total_value_to_cost_ratio,pack_count,"
    "random_pack_count,guaranteed_component_count,guaranteed_component_market_value,"
    "accessory_value_included,composition_version,composition_id,distribution_model_version"
)
FAMILY_ORDER = {
    family: index
    for index, family in enumerate(
        (
            "loose_booster_pack", "sleeved_booster_pack", "booster_bundle",
            "elite_trainer_box", "half_booster_box",
            "pokemon_center_elite_trainer_box", "booster_box", "enhanced_booster_box",
        )
    )
}


class PokemonSealedProductDetailError(Exception):
    def __init__(self, status_code: int, message: str, code: str) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.message = message
        self.code = code


def _rows(query: Any) -> List[Dict[str, Any]]:
    return list(query.execute().data or [])


def _text(value: Any) -> Optional[str]:
    value = str(value or "").strip()
    return value or None


def _product_href(product_id: Any) -> Optional[str]:
    value = _text(product_id)
    return f"/sealed-products/{quote(value, safe='')}" if value else None


def _published_rankings(client: Any) -> Dict[str, Any]:
    rows = _rows(
        client.table("pokemon_explore_rankings_snapshot_latest")
        .select(
            "product_family_rankings:ranking_payload_json->productFamilyRankings,"
            "meta:ranking_payload_json->meta,updated_at"
        )
        .eq("tcg", "pokemon")
        .eq("scope", DEFAULT_RANKINGS_SCOPE)
        .limit(1)
    )
    if not rows:
        return {"payload": {}, "updatedAt": None, "current": False}
    if isinstance(rows[0].get("product_family_rankings"), dict):
        payload = {
            "productFamilyRankings": rows[0]["product_family_rankings"],
            "meta": rows[0].get("meta") if isinstance(rows[0].get("meta"), dict) else {},
        }
    elif isinstance(rows[0].get("ranking_payload_json"), dict):
        payload = rows[0]["ranking_payload_json"]
    else:
        return {"payload": {}, "updatedAt": None, "current": False}
    return {
        "payload": payload,
        "updatedAt": rows[0].get("updated_at"),
        "current": not _rankings_publication_identity_mismatches(payload),
    }


def _ranking_rows(payload: Mapping[str, Any]) -> Iterable[Dict[str, Any]]:
    families = (payload.get("productFamilyRankings") or {}).get("families") or {}
    for family, block in families.items():
        for row in block.get("products") or []:
            if isinstance(row, dict):
                yield {**row, "productFamily": row.get("productFamily") or family}


def _market_contract(history: List[Dict[str, Any]]) -> Dict[str, Any]:
    if not history:
        return {
            "available": False, "currentPrice": None, "marketDate": None,
            "source": None, "history": [], "movements": {},
            "reason": "market_history_unavailable",
        }
    current = history[-1]
    return {
        "available": True,
        "currentPrice": current["marketPrice"],
        "marketDate": current["date"],
        "source": current.get("source"),
        "history": history,
        "movements": {key: movement(history, key) for key in MOVEMENT_WINDOWS},
        "reason": None,
    }


def _prepared_market_contract(product: Mapping[str, Any]) -> Dict[str, Any]:
    """Adapt one canonical prepared set-market product without recomputing it."""
    history = list(product.get("history") or [])
    if not history:
        return _market_contract([])
    return {
        "available": True,
        "currentPrice": product.get("currentPrice"),
        "marketDate": product.get("priceAsOf"),
        "source": product.get("source"),
        "history": history,
        "movements": dict(product.get("movements") or {}),
        "reason": None,
    }


def _prepared_markets(snapshot: Optional[Mapping[str, Any]]) -> Dict[str, Dict[str, Any]]:
    """Index every prepared product population published by the set snapshot."""
    indexed: Dict[str, Dict[str, Any]] = {}
    if not snapshot:
        return indexed
    for population in ("products", "setPageConsumerTopProducts"):
        for product in snapshot.get(population) or []:
            product_id = _text(product.get("sealedProductId"))
            if product_id:
                indexed[product_id] = _prepared_market_contract(product)
    return indexed


def _public_rip_contract_v11_shadow(ranking: Optional[Mapping[str, Any]]) -> Optional[Dict[str, Any]]:
    """SHADOW-only V11 wrapper carrying Overall RIP V12 for this product.

    NOT canonical: `canonical_public_rip_contract_version()` still resolves to
    V10, and this block never feeds `overallRipLeaderScore`/`publicTier`/
    `familyRank` above - those stay sourced from the persisted V10 ranking
    exactly as before this change. Every number here is a pure passthrough of
    `overall_rip_v12_payload`, already computed and authority-checked once by
    `sealed_product_rip_finalization_service._overall_rip_v12_for` (Financial
    RIP V4 + Chase Accessibility V1 + Collector Appeal V5) - this function
    performs no Overall RIP arithmetic of its own, matching
    `public_rip_contract_v11.build_public_rip_contract_v11`'s shape exactly so
    the SAME shared frontend selector/component
    (`overallRipExplanationHierarchySelector.mjs` /
    `OverallRipExplanationHierarchy.jsx`) can render it without a second
    implementation.
    """
    overall_v12 = dict((ranking or {}).get("overallRipV12") or {})
    if not overall_v12:
        return None
    return {
        "contractVersion": "public_rip_contract_v11",
        "overallRipV12": {
            "score": overall_v12.get("score"),
            "status": overall_v12.get("status"),
            "statusReason": overall_v12.get("statusReason"),
            "rankable": bool(overall_v12.get("rankable")),
            "version": overall_v12.get("version") or OVERALL_RIP_V12_VERSION,
            "components": overall_v12.get("components") or {},
            "missingInputs": overall_v12.get("missingInputs") or [],
            # SHADOW, NOT canonical. Never read by ranking order, never
            # substituted into the canonical overallRipLeaderScore slot above.
            "canonical": False,
        },
        "overallRipV12Composition": {
            "version": overall_v12.get("version") or OVERALL_RIP_V12_VERSION,
            "inputs": {
                "financialRip": "financial_rip_v4",
                "chaseAccessibility": "chase_accessibility_v1",
                "collectorAppeal": "collector_appeal_v5",
            },
            # Read verbatim from the persisted payload rather than
            # re-imported constants, so this can never silently drift from
            # the exact weights `compute_overall_rip_v12` actually used.
            "weights": dict(overall_v12.get("weights") or {}),
            "effectiveWeights": dict(overall_v12.get("effectiveWeights") or {}),
        },
    }


def _rip_contract(
    ranking: Optional[Mapping[str, Any]], detail: Optional[Mapping[str, Any]], family: str
) -> Dict[str, Any]:
    scope = sealed_product_comparison_scope_contract()
    base = {
        "available": False,
        "reason": "unsupported_product_family" if family not in COMPARABLE_FAMILIES else "not_in_current_published_rankings",
        "calculationRunId": None,
        "overallRipLeaderScore": None, "financialRipLeaderScore": None,
        "collectorAppealScore": None, "collectorAppealTier": None, "publicTier": None,
        "familyRank": None, "familySize": None,
        "overallRipVersion": None, "financialRipVersion": None, "collectorAppealVersion": None,
        "expectedValue": None, "medianValue": None, "p05Value": None,
        "p95Value": None, "p99Value": None, "chanceToRecoverCost": None,
        "expectedLossWhenLosing": None, "medianLossWhenLosing": None,
        "totalValueToCostRatio": None,
        "entertainmentCost": None, "composition": None,
        "comparisonScope": scope["comparisonScope"],
        "comparisonScopeVersion": scope["comparisonScopeVersion"],
        "setEvRepresentativeness": None,
        # SHADOW, NOT canonical - see `_public_rip_contract_v11_shadow`.
        "publicRipContractV11": None,
    }
    if not ranking:
        return base
    run_id = _text(ranking.get("calculationRunId"))
    if not detail:
        return {**base, "reason": "authoritative_result_unavailable", "calculationRunId": run_id}
    # Inherited from the SET's own confirmed EV realization horizon, already
    # published on this same product-family-rankings row (see
    # product_family_rankings_service._compact_set_ev_representativeness).
    # No new table read: only accepted when it carries the exact same run id
    # this product's own RIP result was just validated against - never a
    # different or stale run.
    set_ev_representativeness = ranking.get("setEvRepresentativeness")
    if not isinstance(set_ev_representativeness, Mapping) or _text(set_ev_representativeness.get("calculationRunId")) != run_id:
        set_ev_representativeness = None
    composition = {
        "packCount": detail.get("pack_count"),
        "randomPackCount": detail.get("random_pack_count"),
        "guaranteedComponentCount": detail.get("guaranteed_component_count"),
        "guaranteedComponentMarketValue": detail.get("guaranteed_component_market_value"),
        "accessoryValueIncluded": detail.get("accessory_value_included"),
        "compositionVersion": detail.get("composition_version"),
        "compositionId": detail.get("composition_id"),
        "distributionModelVersion": detail.get("distribution_model_version"),
    }
    entertainment = entertainment_cost_contract(
        purchase_price=detail.get("product_market_cost"),
        expected_value=detail.get("expected_value"),
        pack_count=detail.get("pack_count"),
        guaranteed_component_included=detail.get("guaranteed_component_market_value") is not None,
    )
    return {
        **base,
        "available": True,
        "reason": None,
        "calculationRunId": run_id,
        "overallRipLeaderScore": ranking.get("overallRipLeaderScore"),
        "financialRipLeaderScore": ranking.get("financialRipLeaderScore"),
        "collectorAppealScore": ranking.get("collectorAppealScore"),
        "collectorAppealTier": ranking.get("collectorAppealTier"),
        "publicTier": ranking.get("publicTier"),
        "familyRank": ranking.get("familyRank"),
        "familySize": ranking.get("familySize") or ranking.get("familyCohortSize"),
        "overallRipVersion": ranking.get("overallRipVersion"),
        "financialRipVersion": ranking.get("financialRipVersion"),
        "collectorAppealVersion": ranking.get("collectorAppealVersion"),
        "expectedValue": detail.get("expected_value"),
        "medianValue": detail.get("median_value"),
        "p05Value": detail.get("p05_value"),
        "p95Value": detail.get("p95_value"),
        "p99Value": detail.get("p99_value"),
        "chanceToRecoverCost": detail.get("chance_to_recover_cost"),
        "expectedLossWhenLosing": detail.get("expected_loss_when_losing"),
        "medianLossWhenLosing": detail.get("median_loss_when_losing"),
        "totalValueToCostRatio": detail.get("total_value_to_cost_ratio"),
        "entertainmentCost": entertainment,
        "composition": composition,
        "setEvRepresentativeness": set_ev_representativeness,
        "publicRipContractV11": _public_rip_contract_v11_shadow(ranking),
        # Top-level V10 shape `canonicalRipV7.mjs`'s `resolveCanonicalRipV7`
        # already knows how to read (its "topLevelV10" fallback branch) - a
        # pure re-labeling of the SAME leader/rank/tier fields already
        # returned above, so `OverallRipExplanationHierarchy` can render the
        # canonical 90/10 explanation without a second implementation. No new
        # data, no arithmetic: this is the identical shape the Set RIP /
        # Explore surfaces already produce for this same reader.
        "overallRipV10": {
            "leaderNormalizedScore": ranking.get("overallRipLeaderScore"),
            "rank": ranking.get("familyRank"),
            "tier": ranking.get("publicTier"),
            "cohortSize": ranking.get("familySize") or ranking.get("familyCohortSize"),
            "status": "ready" if ranking.get("overallRipLeaderScore") is not None else "unavailable",
        },
        "financialRipV4": {
            "leaderNormalizedScore": ranking.get("financialRipLeaderScore"),
        },
    }


def _comparison_row(
    product: Mapping[str, Any], family: str, market: Mapping[str, Any], ranking: Optional[Mapping[str, Any]]
) -> Dict[str, Any]:
    return {
        "sealedProductId": str(product["id"]), "name": product.get("name"),
        "setName": ranking.get("setName") if ranking else None,
        "productType": product.get("product_type"), "productFamily": family,
        "productFamilyLabel": FAMILY_LABELS.get(family, family.replace("_", " ").title()),
        "imageUrl": product.get("image_large_url") or product.get("image_small_url"),
        "currentPrice": market.get("currentPrice"), "marketDate": market.get("marketDate"),
        "href": _product_href(product.get("id")), "rankable": bool(ranking),
        "familyRank": ranking.get("familyRank") if ranking else None,
        "familySize": (ranking.get("familySize") or ranking.get("familyCohortSize")) if ranking else None,
        "overallRipLeaderScore": ranking.get("overallRipLeaderScore") if ranking else None,
        "publicTier": ranking.get("publicTier") if ranking else None,
    }


def get_pokemon_sealed_product_detail_payload(product_id: str, client: Any = None) -> Dict[str, Any]:
    """Return real identity/market data and RIP only from the current publication."""
    active = client or service_read_client
    requested = _text(product_id)
    products = _rows(
        active.table("sealed_products")
        .select("id,set_id,name,product_type,image_small_url,image_large_url")
        .eq("id", requested or "")
        .limit(1)
    )
    if not products:
        raise PokemonSealedProductDetailError(404, "Pokemon sealed product not found", "POKEMON_SEALED_PRODUCT_NOT_FOUND")
    product = products[0]
    set_id = str(product["set_id"])
    sets = _rows(
        active.table("sets")
        .select("id,name,canonical_key,hero_image_url,logo_image_url,symbol_image_url")
        .eq("id", set_id).limit(1)
    )
    if not sets:
        raise PokemonSealedProductDetailError(404, "Pokemon set not found", "POKEMON_SET_NOT_FOUND")
    set_row = sets[0]
    set_products = _rows(
        active.table("sealed_products")
        .select("id,set_id,name,product_type,image_small_url,image_large_url")
        .eq("set_id", set_id)
    )
    snapshot = read_snapshot(active, set_id)
    markets = _prepared_markets(snapshot)
    canonical_product_id = str(product["id"])
    market = markets.get(canonical_product_id)
    market_from_snapshot = market is not None
    if market is None:
        # A real catalog product may legitimately be absent from the current
        # prepared snapshot. Keep this fallback narrow: one identity, never the
        # former set-wide observation reconstruction.
        observations = _rows(
            active.table("sealed_product_price_observations")
            .select("id,sealed_product_id,market_price,currency,source,captured_at")
            .eq("sealed_product_id", canonical_product_id)
        )
        market = _market_contract(normalize_daily_history(observations))
        markets[canonical_product_id] = market
    identity = classify_sealed_product(product.get("name"))
    family = identity["productFamily"]

    publication = _published_rankings(active)
    published_rows = list(_ranking_rows(publication["payload"])) if publication["current"] else []
    ranking_by_id = {str(row.get("sealedProductId")): row for row in published_rows if row.get("sealedProductId")}
    ranking = ranking_by_id.get(str(product["id"]))
    detail = None
    if ranking and _text(ranking.get("calculationRunId")):
        details = _rows(
            active.table("simulation_sealed_product_results").select(DETAIL_FIELDS)
            .eq("sealed_product_id", str(product["id"]))
            .eq("calculation_run_id", str(ranking["calculationRunId"]))
            .limit(1)
        )
        detail = details[0] if details else None
    rip = _rip_contract(ranking, detail, family)
    if not publication["current"] and family in COMPARABLE_FAMILIES:
        rip["reason"] = "current_rankings_publication_unavailable"

    same_set = []
    for candidate in set_products:
        candidate_id = str(candidate.get("id") or "")
        if not candidate_id or candidate_id == str(product["id"]):
            continue
        candidate_identity = classify_sealed_product(candidate.get("name"))
        same_set.append(_comparison_row(
            candidate, candidate_identity["productFamily"],
            markets.get(candidate_id, _market_contract([])), ranking_by_id.get(candidate_id),
        ))
    same_set.sort(key=lambda row: (
        0 if row["rankable"] else 1,
        FAMILY_ORDER.get(row["productFamily"], len(FAMILY_ORDER)),
        str(row.get("name") or "").casefold(), row["sealedProductId"],
    ))
    same_set = same_set[:SAME_SET_LIMIT]

    same_family: List[Dict[str, Any]] = []
    if ranking:
        cohort = sorted(
            (row for row in published_rows if row.get("productFamily") == family),
            key=lambda row: (int(row.get("familyRank") or 10**9), str(row.get("sealedProductId") or "")),
        )
        current_index = next((i for i, row in enumerate(cohort) if str(row.get("sealedProductId")) == str(product["id"])), None)
        selected: List[Dict[str, Any]] = []
        if current_index is not None:
            selected.extend(cohort[max(0, current_index - 2):current_index])
            selected.extend(cohort[current_index + 1:current_index + 3])
            if cohort and all(row.get("sealedProductId") != cohort[0].get("sealedProductId") for row in selected) and len(selected) < 5:
                selected.append(cohort[0])
        seen = set()
        catalog = {str(row.get("id")): row for row in set_products}
        for row in selected:
            candidate_id = str(row.get("sealedProductId") or "")
            if not candidate_id or candidate_id == str(product["id"]) or candidate_id in seen:
                continue
            seen.add(candidate_id)
            candidate = catalog.get(candidate_id) or {
                "id": candidate_id, "name": row.get("productName"), "product_type": None,
                "image_small_url": row.get("productImageUrl"), "image_large_url": None,
            }
            same_family.append(_comparison_row(candidate, family, markets.get(candidate_id, _market_contract([])), row))
            if len(same_family) == 5:
                break

    canonical_key = _text(set_row.get("canonical_key"))
    slug = canonical_key or canonical_set_route_slug(str(set_row.get("name") or set_id))
    return {
        "set": {
            "id": set_id, "slug": slug, "canonicalKey": canonical_key,
            "name": set_row.get("name"), "heroImageUrl": set_row.get("hero_image_url"),
            "logoImageUrl": set_row.get("logo_image_url"), "symbolImageUrl": set_row.get("symbol_image_url"),
        },
        "product": {
            "id": str(product["id"]), "name": product.get("name"),
            "productType": product.get("product_type"), "productFamily": family,
            "productFamilyLabel": identity["productFamilyLabel"],
            "imageUrl": product.get("image_large_url") or product.get("image_small_url"),
            "imageSmallUrl": product.get("image_small_url"), "imageLargeUrl": product.get("image_large_url"),
        },
        "market": market,
        "rip": rip,
        "comparisons": {"sameSet": same_set, "sameFamily": same_family},
        "meta": {
            "contractVersion": CONTRACT_VERSION,
            "canonicalPath": _product_href(product["id"]),
            "marketSource": (
                "pokemon_set_sealed_market_snapshot_latest"
                if market_from_snapshot
                else "sealed_product_price_observations"
            ),
            "rankingSource": "pokemon_explore_rankings_snapshot_latest",
            "rankingPublicationCurrent": publication["current"],
            "rankingPublicationUpdatedAt": publication["updatedAt"],
            "classificationVersion": identity["classificationVersion"],
        },
    }
