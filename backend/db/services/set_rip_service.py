"""Production Set RIP V1 built from canonical product-family rankings."""

from __future__ import annotations

import statistics
from collections import defaultdict
from typing import Any, Dict, Mapping, Sequence

from backend.desirability.scoring_config import (
    CANONICAL_FINANCIAL_RIP_VERSION,
    CANONICAL_OVERALL_RIP_VERSION,
    canonical_collector_appeal_version,
)
from backend.rankings.public_relative import public_relative_rip_tier

METHODOLOGY_VERSION = "set_rip_v1_mean_sku_mean_family_unshrunk_cov2_cohort3_missing_omit"
MINIMUM_PARTICIPATING_FAMILIES = 2
MINIMUM_REPRESENTED_SETS_PER_FAMILY = 3


def sku_relative_standing(family_rank: int, family_size: int) -> float:
    if family_size < 1 or family_rank < 1 or family_rank > family_size:
        raise ValueError("family rank must be within a positive family cohort")
    return 0.5 if family_size == 1 else 1.0 - ((family_rank - 1) / (family_size - 1))


def _text(value: Any) -> str:
    return str(value or "").strip()


def _ranked_targets(targets: Sequence[Mapping[str, Any]]) -> list[Mapping[str, Any]]:
    return [target for target in targets if
            (target.get("overallRipV10") or {}).get("rank") is not None or
            (((target.get("publicRipContractV10") or {}).get("overallRip") or {}).get("rank") is not None)]


def build_set_rip(product_family_rankings: Mapping[str, Any], *,
                  set_targets: Sequence[Mapping[str, Any]]) -> Dict[str, Any]:
    """Build the frozen Set RIP contract without a research dependency."""
    targets = list(set_targets)
    ranked_targets = _ranked_targets(targets)
    target_by_id = {_text(target.get("set_id") or target.get("target_id")): target for target in targets}
    if not ranked_targets:
        raise ValueError("Set RIP requires ranked set targets")
    if product_family_rankings.get("runAuthority") != "set_targets.calculation_run_id":
        raise ValueError("Set RIP requires canonical set_targets.calculation_run_id authority")
    if int(product_family_rankings.get("authorityTargetCount") or 0) != len(ranked_targets):
        raise ValueError("Set RIP product-family projection is incomplete for the ranked target cohort")

    evidence: dict[str, dict[str, list[float]]] = defaultdict(lambda: defaultdict(list))
    display_evidence: dict[str, dict[str, list[Dict[str, Any]]]] = defaultdict(lambda: defaultdict(list))
    eligible_family_counts: dict[str, int] = {}
    for family, block in sorted((product_family_rankings.get("families") or {}).items()):
        products = list(block.get("products") or [])
        family_size = int(block.get("count") or 0)
        if family_size != len(products) or int(block.get("currentlyRankableCount") or 0) != len(products):
            raise ValueError(f"Set RIP product-family projection is incomplete for {family}")
        represented_sets = {_text(product.get("setId")) for product in products} - {""}
        for product in products:
            set_id = _text(product.get("setId"))
            target = target_by_id.get(set_id)
            if target is None:
                raise ValueError(f"Set RIP product {product.get('sealedProductId')} has no ranked owning target")
            if not _text(target.get("calculation_run_id")) or _text(product.get("calculationRunId")) != _text(target.get("calculation_run_id")):
                raise ValueError(f"Set RIP run authority mismatch for set_id={set_id}")
            versions = (product.get("financialRipVersion"), product.get("collectorAppealVersion"), product.get("overallRipVersion"))
            canonical = (CANONICAL_FINANCIAL_RIP_VERSION, canonical_collector_appeal_version(), CANONICAL_OVERALL_RIP_VERSION)
            if versions != canonical:
                raise ValueError(f"Set RIP canonical score version mismatch for set_id={set_id}, family={family}")
            standing = sku_relative_standing(int(product.get("familyRank")), family_size)
            display_evidence[set_id][family].append({
                "standing": standing,
                "marketPrice": product.get("marketPrice"),
                "sealedProductId": product.get("sealedProductId"),
            })
            if len(represented_sets) >= MINIMUM_REPRESENTED_SETS_PER_FAMILY:
                evidence[set_id][family].append(standing)
        if len(represented_sets) >= MINIMUM_REPRESENTED_SETS_PER_FAMILY:
            eligible_family_counts[family] = len(represented_sets)

    standings: dict[str, dict[str, float]] = defaultdict(dict)
    for set_id, families in evidence.items():
        for family, values in families.items():
            standings[family][set_id] = round(statistics.fmean(values), 6)

    display_standings: dict[str, dict[str, float]] = defaultdict(dict)
    for set_id, families in display_evidence.items():
        for family, products in families.items():
            display_standings[family][set_id] = round(
                statistics.fmean(product["standing"] for product in products), 6
            )

    family_standing: dict[str, dict[str, Dict[str, Any]]] = defaultdict(dict)
    for family, by_set in standings.items():
        ordered = sorted(by_set.items(), key=lambda item: (-item[1], item[0]))
        cohort_size = len(ordered)
        for rank, (set_id, mean_standing) in enumerate(ordered, 1):
            score = round(mean_standing * 100, 6)
            family_standing[set_id][family] = {
                "meanStanding": mean_standing,
                "score": score,
                "tier": public_relative_rip_tier(score),
                "rank": rank,
                "cohortSize": cohort_size,
            }

    display_family_standing: dict[str, dict[str, Dict[str, Any]]] = defaultdict(dict)
    for family, by_set in display_standings.items():
        ordered = sorted(by_set.items(), key=lambda item: (-item[1], item[0]))
        cohort_size = len(ordered)
        for rank, (set_id, mean_standing) in enumerate(ordered, 1):
            score = round(mean_standing * 100, 6)
            display_family_standing[set_id][family] = {
                "meanStanding": mean_standing,
                "score": score,
                "tier": public_relative_rip_tier(score),
                "rank": rank,
                "cohortSize": cohort_size,
            }

    rows = []
    for set_id, target in target_by_id.items():
        family_scores = [{"family": family, "skuCount": len(values),
                          **family_standing[set_id][family]}
                         for family, values in sorted(evidence.get(set_id, {}).items())]
        display_family_scores = []
        for family, products in sorted(display_evidence.get(set_id, {}).items()):
            prices = [float(product["marketPrice"]) for product in products
                      if isinstance(product.get("marketPrice"), (int, float))
                      and float(product["marketPrice"]) > 0]
            display_family_scores.append({
                "family": family,
                "skuCount": len(products),
                "minMarketPrice": min(prices) if prices else None,
                "maxMarketPrice": max(prices) if prices else None,
                "productIds": [product["sealedProductId"] for product in products
                               if product.get("sealedProductId")],
                **display_family_standing[set_id][family],
            })
        rankable = len(family_scores) >= MINIMUM_PARTICIPATING_FAMILIES
        score = round(statistics.fmean(item["meanStanding"] for item in family_scores) * 100, 6) if rankable else None
        rows.append({"setId": set_id, "setName": target.get("name"), "score": score,
                     "tier": public_relative_rip_tier(score), "rank": None,
                     "rankable": rankable, "methodologyVersion": METHODOLOGY_VERSION,
                     "participatingFamilyCount": len(family_scores),
                     "participatingFamilies": [item["family"] for item in family_scores],
                     "skuEvidenceCount": sum(item["skuCount"] for item in family_scores),
                     "familyScores": family_scores, "displayFamilyScores": display_family_scores})

    ranked = sorted((row for row in rows if row["rankable"]), key=lambda row: (-row["score"], row["setId"]))
    cohort_size = len(ranked)
    for rank, row in enumerate(ranked, 1):
        row["rank"] = rank
        row["cohortSize"] = cohort_size
    for row in rows:
        if not row["rankable"]:
            row["cohortSize"] = cohort_size
    unavailable = sorted((row for row in rows if not row["rankable"]), key=lambda row: row["setId"])
    return {"methodologyVersion": METHODOLOGY_VERSION, "runAuthority": "set_targets.calculation_run_id",
            "minimumParticipatingFamilies": MINIMUM_PARTICIPATING_FAMILIES,
            "minimumRepresentedSetsPerFamily": MINIMUM_REPRESENTED_SETS_PER_FAMILY,
            "eligibleFamilyRepresentedSetCounts": eligible_family_counts,
            "rankedSetCount": len(ranked), "targetCount": len(rows), "sets": ranked + unavailable}


def attach_set_rip_to_targets(targets: Sequence[Mapping[str, Any]],
                              set_rip: Mapping[str, Any]) -> list[Dict[str, Any]]:
    by_id = {str(row["setId"]): row for row in set_rip.get("sets") or []}
    attached = []
    for target in targets:
        set_id = _text(target.get("set_id") or target.get("target_id"))
        row = by_id.get(set_id)
        if row is None:
            raise ValueError(f"Set RIP result missing target set_id={set_id}")
        attached.append({**target, "setRipV1": {key: value for key, value in row.items() if key not in {"setId", "setName"}}})
    return attached
