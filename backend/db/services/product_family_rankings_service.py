"""Canonical, family-isolated sealed-product rankings for the global snapshot."""

from __future__ import annotations

from typing import Any, Dict, Mapping, Sequence

from backend.db.clients.supabase_client import service_read_client
from backend.desirability.composite import assign_composite_tier
from backend.rankings.public_relative import compute_public_relative_scores, public_product_rank_tier
from backend.desirability.scoring_config import (
    CANONICAL_FINANCIAL_RIP_VERSION,
    CANONICAL_OVERALL_RIP_VERSION,
    canonical_collector_appeal_version,
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
    "financial_rip_v4_score,financial_rip_v4_version,"
    "collector_appeal_score,collector_appeal_version,overall_rip_score,overall_rip_version,"
    "overall_rip_rankable,overall_rip_v10_score,overall_rip_v10_version,overall_rip_v10_rankable"
)


def _number(value: Any, default: float) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _rank_key(row: Mapping[str, Any]) -> tuple:
    """One-family canonical order. This comparator must never receive mixed families."""
    return (
        -_number(row.get("overall_rip_v10_score"), float("-inf")),
        -_number(row.get("financial_rip_v4_score"), float("-inf")),
        -_number(row.get("chance_to_recover_cost"), float("-inf")),
        _number(row.get("product_market_cost"), float("inf")),
        str(row.get("sealed_product_id") or ""),
    )


def _canonical(row: Mapping[str, Any]) -> bool:
    return bool(row.get("overall_rip_v10_rankable")) and all(
        (
            row.get("financial_rip_v4_version") == CANONICAL_FINANCIAL_RIP_VERSION,
            row.get("collector_appeal_version") == canonical_collector_appeal_version(),
            row.get("overall_rip_v10_version") == CANONICAL_OVERALL_RIP_VERSION,
        )
    )


def _text(value: Any) -> str:
    return str(value or "").strip()


def _ranked_targets(set_targets: Sequence[Mapping[str, Any]]) -> list[Mapping[str, Any]]:
    """Use canonical ranked targets when rank blocks are present; keep plain test/input rows usable."""
    has_rank_contract = any(
        "overallRipV10" in target or "publicRipContractV10" in target for target in set_targets
    )
    if not has_rank_contract:
        return list(set_targets)
    return [
        target for target in set_targets
        if (target.get("overallRipV10") or {}).get("rank") is not None
        or (((target.get("publicRipContractV10") or {}).get("overallRip") or {}).get("rank") is not None)
    ]


def _target_run_authority(
    set_targets: Sequence[Mapping[str, Any]],
) -> tuple[Dict[str, str], Dict[str, Mapping[str, Any]]]:
    """Validate and return the exact public set -> calculation-run authority."""
    run_by_set: Dict[str, str] = {}
    identities: Dict[str, Mapping[str, Any]] = {}
    problems = []
    for index, target in enumerate(_ranked_targets(set_targets)):
        if not isinstance(target, Mapping):
            problems.append(f"target[{index}] is not an object")
            continue
        set_id = _text(target.get("set_id"))
        canonical_key = _text(target.get("canonical_key"))
        run_id = _text(target.get("calculation_run_id"))
        label = canonical_key or set_id or f"target[{index}]"
        if not set_id:
            problems.append(f"{label}: set_id is missing")
        if not canonical_key:
            problems.append(f"{label}: canonical_key is missing")
        if not run_id:
            problems.append(f"{label}: calculation_run_id is missing")
        if not set_id or not canonical_key or not run_id:
            continue
        previous = run_by_set.get(set_id)
        if previous is not None and previous != run_id:
            problems.append(
                f"{canonical_key}: conflicting calculation_run_id authority for set_id={set_id}: "
                f"{previous} != {run_id}"
            )
            continue
        run_by_set[set_id] = run_id
        identities[set_id] = target
    if problems:
        raise ValueError("Invalid product-family target run authority: " + "; ".join(problems))
    return run_by_set, identities


def _project(row: Mapping[str, Any], identity: Mapping[str, Any], rank: int, size: int,
             overall_relative: Any = None, financial_relative: Any = None) -> Dict[str, Any]:
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
        # Reuses the ONE canonical absolute-score tier bucketer already in the
        # repo (S>=90, A>=75, B>=55, C>=35, D>=15, else F — desirability
        # composite tiers), rather than inventing new cutoffs for this
        # context. Derived server-side from the same overall_rip_v10_score
        # that produced this row's rank, so rank and tier always describe the
        # identical cohort/score.
        "familyTier": public_product_rank_tier(rank, size),
        "publicTier": public_product_rank_tier(rank, size),
        "modelTier": assign_composite_tier(_number(row.get("overall_rip_v10_score"), 0.0)),
        "marketPrice": row.get("product_market_cost"),
        "overallRipScore": row.get("overall_rip_v10_score"),
        "overallRipAbsoluteScore": row.get("overall_rip_v10_score"),
        "overallRipRelativeScore": overall_relative,
        "overallRipVersion": row.get("overall_rip_v10_version"),
        "financialRipScore": row.get("financial_rip_v4_score"),
        "financialRipAbsoluteScore": row.get("financial_rip_v4_score"),
        "financialRipRelativeScore": financial_relative,
        "financialRipVersion": row.get("financial_rip_v4_version"),
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
    client: Any = None, *, set_targets: Sequence[Mapping[str, Any]]
) -> Dict[str, Any]:
    """Build rankings only from each public target's exact calculation run."""
    client = client or service_read_client
    run_id_by_set_id, identities = _target_run_authority(set_targets)
    if not identities:
        return {
            **sealed_product_comparison_scope_contract(),
            "source": "simulation_sealed_product_results_current_canonical_runs",
            "partialToCurrentlyScoredProducts": True,
            "families": {},
        }
    current_run_ids = sorted(set(run_id_by_set_id.values()))
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
        set_id = _text(row.get("set_id"))
        if not set_id or _text(row.get("calculation_run_id")) != run_id_by_set_id.get(set_id):
            continue
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
        overall_relative = compute_public_relative_scores(
            ordered, id_getter=lambda row: row.get("sealed_product_id"),
            score_getter=lambda row: row.get("overall_rip_v10_score"),
        )
        financial_relative = compute_public_relative_scores(
            ordered, id_getter=lambda row: row.get("sealed_product_id"),
            score_getter=lambda row: row.get("financial_rip_v4_score"),
        )
        products = [
            _project(row, identities.get(str(row.get("set_id")), {}), index, size,
                     overall_relative.get(str(row.get("sealed_product_id"))),
                     financial_relative.get(str(row.get("sealed_product_id"))))
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
        "runAuthority": "set_targets.calculation_run_id",
        "authorityTargetCount": len(run_id_by_set_id),
        "families": families,
    }
