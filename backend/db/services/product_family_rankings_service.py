"""Canonical, family-isolated sealed-product rankings for the global snapshot."""

from __future__ import annotations

from typing import Any, Dict, Mapping, Sequence

from backend.db.clients.supabase_client import public_read_client
from backend.db.services.sealed_product_rip_finalization_service import resolve_finalization_cohort
from backend.desirability.collector_appeal import COLLECTOR_APPEAL_V5_VERSION
from backend.desirability.scoring_config import (
    CANONICAL_FINANCIAL_RIP_VERSION,
    CANONICAL_OVERALL_RIP_VERSION,
)
from backend.domain.pokemon.sealed_product_classifier import FAMILY_LABELS
from backend.domain.pokemon.sealed_product_comparison_scope import (
    COMPARABLE_FAMILIES,
    sealed_product_comparison_scope_contract,
)

RESULT_FIELDS = (
    "calculation_run_id,sealed_product_id,set_id,product_family,product_name,pack_count,"
    "random_pack_count,guaranteed_component_count,product_market_cost,price_as_of,"
    "expected_value,median_value,p05_value,p95_value,p99_value,chance_to_recover_cost,"
    "total_value_to_cost_ratio,financial_rip_v3_score,financial_rip_v3_version,"
    "collector_appeal_score,collector_appeal_version,overall_rip_score,overall_rip_version,"
    "overall_rip_rankable"
)


def _number(value: Any, default: float) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _rank_key(row: Mapping[str, Any]) -> tuple:
    """One-family canonical order. This comparator must never receive mixed families."""
    return (
        -_number(row.get("overall_rip_score"), float("-inf")),
        -_number(row.get("financial_rip_v3_score"), float("-inf")),
        -_number(row.get("chance_to_recover_cost"), float("-inf")),
        _number(row.get("product_market_cost"), float("inf")),
        str(row.get("sealed_product_id") or ""),
    )


def _canonical(row: Mapping[str, Any]) -> bool:
    return bool(row.get("overall_rip_rankable")) and all(
        (
            row.get("financial_rip_v3_version") == CANONICAL_FINANCIAL_RIP_VERSION,
            row.get("collector_appeal_version") == COLLECTOR_APPEAL_V5_VERSION,
            row.get("overall_rip_version") == CANONICAL_OVERALL_RIP_VERSION,
        )
    )


def _project(row: Mapping[str, Any], identity: Mapping[str, Any], rank: int, size: int) -> Dict[str, Any]:
    market = _number(row.get("product_market_cost"), 0.0)
    expected = _number(row.get("expected_value"), 0.0)
    ratio = expected / market if market > 0 else None
    family = str(row.get("product_family"))
    return {
        "sealedProductId": row.get("sealed_product_id"),
        "productName": row.get("product_name"),
        "setId": row.get("set_id"),
        "setCanonicalKey": identity.get("canonical_key") or identity.get("canonicalKey"),
        "setName": identity.get("name"),
        "setImage": identity.get("logo_image_url") or identity.get("logoImageUrl") or identity.get("symbol_image_url"),
        "productFamily": family,
        "productFamilyLabel": FAMILY_LABELS.get(family, family.replace("_", " ").title()),
        "familyRank": rank,
        "familySize": size,
        "marketPrice": row.get("product_market_cost"),
        "overallRipScore": row.get("overall_rip_score"),
        "overallRipVersion": row.get("overall_rip_version"),
        "financialRipScore": row.get("financial_rip_v3_score"),
        "financialRipVersion": row.get("financial_rip_v3_version"),
        "collectorAppealScore": row.get("collector_appeal_score"),
        "collectorAppealVersion": row.get("collector_appeal_version"),
        "expectedValue": row.get("expected_value"),
        "medianValue": row.get("median_value"),
        "p05Value": row.get("p05_value"),
        "p95Value": row.get("p95_value"),
        "p99Value": row.get("p99_value"),
        "chanceToRecoverCost": row.get("chance_to_recover_cost"),
        "totalValueToCostRatio": row.get("total_value_to_cost_ratio"),
        "modelBreakEven": row.get("expected_value"),
        "modeledReturnRatio": ratio,
        "modeledReturnPercent": 100 * ratio if ratio is not None else None,
        "modelEdgePercent": 100 * (ratio - 1) if ratio is not None else None,
        "packCount": row.get("pack_count"),
        "randomPackCount": row.get("random_pack_count"),
        "guaranteedComponentCount": row.get("guaranteed_component_count"),
        "calculationRunId": row.get("calculation_run_id"),
        "priceAsOf": row.get("price_as_of"),
    }


def build_product_family_rankings(
    client: Any = None, *, market_date: Any, set_targets: Sequence[Mapping[str, Any]]
) -> Dict[str, Any]:
    """Build rankings only from result rows belonging to publication-current runs."""
    client = client or public_read_client
    identities = {
        str(target.get("set_id") or target.get("target_id")): target
        for target in set_targets
        if target.get("set_id") or target.get("target_id")
    }
    if not identities:
        return {
            **sealed_product_comparison_scope_contract(),
            "source": "simulation_sealed_product_results_current_canonical_runs",
            "partialToCurrentlyScoredProducts": True,
            "families": {},
        }
    canonical_keys = [str(t.get("canonical_key")) for t in identities.values() if t.get("canonical_key")]
    cohort = resolve_finalization_cohort(
        client, market_date=market_date, canonical_keys=canonical_keys, unsupported_keys=()
    )
    if cohort.get("error"):
        raise RuntimeError(f"Cannot build product-family rankings: {cohort['error']}")
    current_run_ids = sorted(set((cohort.get("runIdBySetId") or {}).values()))
    rows = []
    if current_run_ids:
        rows = list(
            client.table("simulation_sealed_product_results")
            .select(RESULT_FIELDS)
            .in_("calculation_run_id", current_run_ids)
            .execute().data or []
        )

    scored_by_family: Dict[str, int] = {}
    rankable_by_family: Dict[str, list] = {}
    for row in rows:
        family = str(row.get("product_family") or "")
        if family not in COMPARABLE_FAMILIES:
            continue
        scored_by_family[family] = scored_by_family.get(family, 0) + 1
        if _canonical(row):
            rankable_by_family.setdefault(family, []).append(row)

    families: Dict[str, Any] = {}
    for family in sorted(rankable_by_family):
        ordered = sorted(rankable_by_family[family], key=_rank_key)
        size = len(ordered)
        products = [
            _project(row, identities.get(str(row.get("set_id")), {}), index, size)
            for index, row in enumerate(ordered, 1)
        ]
        families[family] = {
            "family": family,
            "label": FAMILY_LABELS.get(family, family.replace("_", " ").title()),
            "currentlyScoredCount": scored_by_family.get(family, 0),
            "currentlyRankableCount": size,
            "count": size,
            "products": products,
        }

    return {
        **sealed_product_comparison_scope_contract(),
        "source": "simulation_sealed_product_results_current_canonical_runs",
        "partialToCurrentlyScoredProducts": True,
        "families": families,
    }
