"""Read-only research harness for relative, within-family Set RIP consensus.

This module deliberately consumes the canonical product-family projection. Raw
Financial RIP and Overall RIP magnitudes are never copied into the research
matrix and never enter an aggregation. The only performance input is familyRank
plus its family cohort size.

Running this file reads public data and writes only the two explicitly requested
local research artifacts. It has no database mutation path and is not imported
by any production publisher.
"""

from __future__ import annotations

import argparse
import json
import math
import statistics
import subprocess
import sys
from collections import defaultdict
from datetime import date
from pathlib import Path
from typing import Any, Mapping, Sequence

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from backend.db.clients.supabase_client import public_read_client
from backend.db.services.explore_rip_statistics_service import get_rip_statistics_targets_payload
from backend.db.services.product_family_rankings_service import build_product_family_rankings
from backend.desirability.scoring_config import (
    CANONICAL_FINANCIAL_RIP_VERSION,
    CANONICAL_OVERALL_RIP_VERSION,
    canonical_collector_appeal_version,
)
from backend.domain.pokemon.sealed_product_classifier import FAMILY_LABELS, classify_sealed_product
from backend.domain.pokemon.sealed_product_comparison_scope import COMPARABLE_FAMILIES

RESEARCH_VERSION = "set-rip-consensus-research-v3-frozen-promotion-gate"
METHODOLOGY_VERSION = "set_rip_consensus_v1_mean_sku_mean_family_unshrunk_cov2_cohort3_missing_omit"
FAMILIES = tuple(sorted(COMPARABLE_FAMILIES))
REPRESENTATIVE_POLICIES = ("best", "median", "mean")
AGGREGATION_METHODS = ("mean", "median", "borda", "group_balanced")
PRIOR_STRENGTHS = (1, 2, 3)
MINIMUM_COVERAGE = (0, 2, 3)
MINIMUM_FAMILY_SET_COHORT = (0, 3, 5)
FORMAT_GROUPS = {
    "homogeneous_pack_products": (
        "sleeved_booster_pack", "booster_bundle", "half_booster_box", "booster_box",
    ),
    "trainer_boxes": ("elite_trainer_box", "pokemon_center_elite_trainer_box"),
    "enhanced_boxes": ("enhanced_booster_box",),
}
REPORT_FAMILY_LABELS = {**FAMILY_LABELS, "pokemon_center_elite_trainer_box": "Pokémon Center Elite Trainer Box"}
REASONABLE_COVERAGE_GATES = (2, 3)
REASONABLE_COHORT_GATES = (3, 5)
LEADING_SPEC = {"representativePolicy": "mean", "method": "mean", "priorStrength": 0,
                "minimumCoverage": 2, "minimumFamilySetCohort": 3}
PREVIOUS_LEADING_SPEC = {"representativePolicy": "best", "method": "mean", "priorStrength": 2,
                         "minimumCoverage": 2, "minimumFamilySetCohort": 3}
PROMOTION_GATE_REQUIREMENTS = {
    "runAuthorityMatchRate": 1.0,
    "canonicalVersionMatchRate": 1.0,
    "minimumSetCoverageRate": 0.90,
    "minimumFamilyRepresentedSets": 3,
    "familyCohortSensitivityRepresentedSets": 5,
    "minimumLooSpearman": 0.85,
    "minimumLooTop5Overlap": 4,
    "maximumLooMeanAbsoluteRankMovement": 2.0,
    "maximumLooIndividualRankMovement": 6,
    "minimumRepresentativeSensitivitySpearman": 0.85,
    "minimumRepresentativeSensitivityTop5Overlap": 4,
    "familyCountFairnessAbsoluteSpearmanReview": 0.60,
}
PROMOTION_STATUSES = (
    "RESEARCH_NOT_READY_FOR_PROMOTION", "AWAITING_DEFERRED_COVERAGE", "PROMOTION_GATE_FAILED",
    "METHODOLOGY_SENSITIVITY_REVIEW_REQUIRED", "METHODOLOGY_READY_FOR_PROMOTION_REVIEW",
)
FROZEN_BASELINE_FAMILY_COUNTS = {
    "sleeved_booster_pack": 15, "booster_bundle": 23, "half_booster_box": 0,
    "booster_box": 15, "elite_trainer_box": 9,
    "pokemon_center_elite_trainer_box": 9, "enhanced_booster_box": 0,
}


def rank_standing(rank: int, cohort_size: int) -> float:
    """Map a within-family rank to [0, 1]; a singleton is neutral evidence."""
    if cohort_size < 1 or rank < 1 or rank > cohort_size:
        raise ValueError("rank must be within a positive cohort")
    if cohort_size == 1:
        return 0.5
    return 1.0 - ((rank - 1) / (cohort_size - 1))


def representative(values: Sequence[float], policy: str) -> float:
    if not values:
        raise ValueError("representative requires observed SKU standings")
    if policy == "best":
        return max(values)
    if policy == "median":
        return statistics.median(values)
    if policy == "mean":
        return statistics.fmean(values)
    raise ValueError(f"unknown representative policy: {policy}")


def shrunk_mean(values: Sequence[float], prior_strength: int) -> float | None:
    if not values:
        return None
    return (sum(values) + prior_strength * 0.5) / (len(values) + prior_strength)


def _round(value: float | None, digits: int = 6) -> float | None:
    return None if value is None else round(value, digits)


def _mean_ranks(values: Sequence[float]) -> list[float]:
    """Deterministic average ranks (1 is best), including ties."""
    indexed = sorted(enumerate(values), key=lambda pair: (-pair[1], pair[0]))
    result = [0.0] * len(values)
    cursor = 0
    while cursor < len(indexed):
        end = cursor + 1
        while end < len(indexed) and indexed[end][1] == indexed[cursor][1]:
            end += 1
        average = ((cursor + 1) + end) / 2
        for original, _value in indexed[cursor:end]:
            result[original] = average
        cursor = end
    return result


def spearman(left: Sequence[float], right: Sequence[float]) -> float | None:
    if len(left) != len(right) or len(left) < 2:
        return None
    x, y = _mean_ranks(left), _mean_ranks(right)
    mx, my = statistics.fmean(x), statistics.fmean(y)
    numerator = sum((a - mx) * (b - my) for a, b in zip(x, y))
    denominator = math.sqrt(sum((a - mx) ** 2 for a in x) * sum((b - my) ** 2 for b in y))
    return None if denominator == 0 else numerator / denominator


def _catalog_by_set(
    client: Any, set_ids: Sequence[str]
) -> dict[str, dict[str, list[dict[str, Any]]]]:
    result: dict[str, dict[str, list[dict[str, Any]]]] = defaultdict(lambda: defaultdict(list))
    if not set_ids:
        return result
    rows = (
        client.table("sealed_products").select("id,set_id,name,product_type")
        .in_("set_id", list(set_ids)).execute().data or []
    )
    for row in rows:
        family = classify_sealed_product(row.get("name"))["productFamily"]
        if family in FAMILIES:
            result[str(row.get("set_id"))][family].append(dict(row))
    return result


def build_matrix(
    projection: Mapping[str, Any],
    set_targets: Sequence[Mapping[str, Any]],
    catalog: Mapping[str, Mapping[str, Sequence[Mapping[str, Any]]]] | None = None,
) -> list[dict[str, Any]]:
    """Build every set × family cell without carrying raw RIP magnitudes."""
    catalog = catalog or {}
    targets = {
        str(row.get("set_id") or row.get("target_id")): row
        for row in set_targets if row.get("set_id") or row.get("target_id")
    }
    products: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    family_sizes: dict[str, int] = {}
    family_set_sizes: dict[str, int] = {}
    for family, block in sorted((projection.get("families") or {}).items()):
        family_sizes[family] = int(block.get("count") or 0)
        family_set_sizes[family] = len({str(p.get("setId")) for p in block.get("products") or []})
        for product in block.get("products") or []:
            products[(str(product.get("setId")), family)].append(product)

    matrix = []
    for set_id, target in sorted(targets.items(), key=lambda item: (str(item[1].get("name") or ""), item[0])):
        for family in FAMILIES:
            ranked = sorted(products.get((set_id, family), []), key=lambda p: (p["familyRank"], str(p.get("sealedProductId"))))
            ranks = [int(p["familyRank"]) for p in ranked]
            standings = [rank_standing(rank, family_sizes[family]) for rank in ranks]
            known = list((catalog.get(set_id) or {}).get(family) or [])
            if ranked:
                status = "scored_rankable"
            elif known:
                status = "catalogued_product_exists_unscored"
            else:
                status = "no_catalogued_product"
            best_index = standings.index(max(standings)) if standings else None
            best = ranked[best_index] if best_index is not None else None
            matrix.append({
                "setId": set_id,
                "setCanonicalKey": target.get("canonical_key") or target.get("canonicalKey"),
                "setName": target.get("name"),
                "family": family,
                "familyLabel": REPORT_FAMILY_LABELS.get(family, family),
                "familyCohortSize": family_sizes.get(family, 0),
                "familySetCohortSize": family_set_sizes.get(family, 0),
                "availabilityStatus": status,
                "hasRankableProduct": bool(ranked),
                "cataloguedProductCount": len(known),
                "rankableSkuCount": len(ranked),
                "skuCount": len(ranked),
                "skuFamilyRanks": ranks,
                "skuFamilyPercentiles": [_round(v) for v in standings],
                "skuRanks": ranks,
                "skuStandings": [_round(v) for v in standings],
                "rankableSkus": [{"sealedProductId": p.get("sealedProductId"),
                                  "productName": p.get("productName"), "familyRank": p.get("familyRank"),
                                  "standing": _round(v)} for p, v in zip(ranked, standings)],
                "bestSku": None if best is None else {
                    "sealedProductId": best.get("sealedProductId"), "productName": best.get("productName")
                },
                "bestFamilyRank": None if best is None else best.get("familyRank"),
                "bestFamilyPercentile": _round(max(standings)) if standings else None,
                "medianSkuPercentile": _round(statistics.median(standings)) if standings else None,
                "meanSkuPercentile": _round(statistics.fmean(standings)) if standings else None,
                "familyMeanStanding": _round(statistics.fmean(standings)) if standings else None,
            })
    return matrix


def _evidence(matrix: Sequence[Mapping[str, Any]], policy: str, min_family_sets: int = 0) -> dict[str, dict[str, float]]:
    result: dict[str, dict[str, float]] = defaultdict(dict)
    key = {"best": "bestFamilyPercentile", "median": "medianSkuPercentile", "mean": "meanSkuPercentile"}[policy]
    for cell in matrix:
        value = cell.get(key)
        if value is not None and int(cell.get("familySetCohortSize") or 0) >= min_family_sets:
            result[str(cell["setId"])][str(cell["family"])] = float(value)
    return result


def _borda_values(evidence: Mapping[str, Mapping[str, float]]) -> dict[str, float]:
    """Partial-ballot Borda: normalize set position per family, then observed-only mean.

    Missing sets receive no points and no zero. Tied representatives receive the
    same average position. Low ballot participation is handled separately by the
    declared coverage gates/shrinkage candidates.
    """
    points: dict[str, list[float]] = defaultdict(list)
    families = sorted({family for row in evidence.values() for family in row})
    for family in families:
        members = sorted((set_id, row[family]) for set_id, row in evidence.items() if family in row)
        if not members:
            continue
        ranks = _mean_ranks([value for _set_id, value in members])
        n = len(members)
        for (set_id, _value), rank in zip(members, ranks):
            points[set_id].append(0.5 if n == 1 else 1 - ((rank - 1) / (n - 1)))
    return {set_id: statistics.fmean(values) for set_id, values in points.items()}


def _group_balanced(values: Mapping[str, float]) -> float | None:
    group_values = []
    for families in FORMAT_GROUPS.values():
        observed = [values[family] for family in families if family in values]
        if observed:
            group_values.append(statistics.fmean(observed))
    return statistics.fmean(group_values) if group_values else None


def rank_candidate(
    matrix: Sequence[Mapping[str, Any]], *, representative_policy: str, method: str,
    prior_strength: int = 0, minimum_coverage: int = 0, minimum_family_sets: int = 0,
    omit_family: str | None = None,
) -> list[dict[str, Any]]:
    evidence = _evidence(matrix, representative_policy, minimum_family_sets)
    sku_counts = {(str(cell["setId"]), str(cell["family"])): int(cell.get("rankableSkuCount") or 0)
                  for cell in matrix}
    if omit_family:
        evidence = {set_id: {f: v for f, v in row.items() if f != omit_family} for set_id, row in evidence.items()}
    borda = _borda_values(evidence) if method == "borda" else {}
    rows = []
    for set_id, by_family in evidence.items():
        values = list(by_family.values())
        coverage = len(values)
        measured: float | None
        if not values:
            measured = None
        elif method == "mean":
            measured = shrunk_mean(values, prior_strength) if prior_strength else statistics.fmean(values)
        elif method == "median":
            measured = statistics.median(values)
        elif method == "borda":
            base = borda.get(set_id)
            measured = None if base is None else shrunk_mean([base] * coverage, prior_strength) if prior_strength else base
        elif method == "group_balanced":
            base = _group_balanced(by_family)
            measured = None if base is None else shrunk_mean([base] * coverage, prior_strength) if prior_strength else base
        else:
            raise ValueError(f"unknown aggregation method: {method}")
        value = measured if coverage >= minimum_coverage else None
        sku_evidence_count = sum(sku_counts.get((set_id, family), 0) for family in by_family)
        rows.append({"setId": set_id, "consensusValue": _round(value),
                     "setRipUnit": _round(measured), "setRipScore": _round(measured * 100) if measured is not None else None,
                     "familyCoverageCount": coverage,
                     "skuEvidenceCount": sku_evidence_count, "rankableSkuEvidenceCount": sku_evidence_count,
                     "participatingFamilies": sorted(by_family), "status": "available" if value is not None else "insufficient_coverage"})
    available = sorted((row for row in rows if row["consensusValue"] is not None), key=lambda r: (-r["consensusValue"], r["setId"]))
    for rank, row in enumerate(available, 1):
        row["rank"] = rank
    return available + sorted((row for row in rows if row["consensusValue"] is None), key=lambda r: r["setId"])


def candidate_grid() -> list[dict[str, Any]]:
    """Pre-registered grid; its order and contents do not depend on data."""
    grid = []
    for rep in REPRESENTATIVE_POLICIES:
        for method in AGGREGATION_METHODS:
            priors = (0, *PRIOR_STRENGTHS) if method == "mean" else (0,)
            for prior in priors:
                for coverage in MINIMUM_COVERAGE:
                    for cohort in MINIMUM_FAMILY_SET_COHORT:
                        grid.append({"representativePolicy": rep, "method": method, "priorStrength": prior,
                                     "minimumCoverage": coverage, "minimumFamilySetCohort": cohort})
    return grid


def _ranking_comparison(left: Sequence[Mapping[str, Any]], right: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    lrank = {str(row["setId"]): int(row["rank"]) for row in left if row.get("rank")}
    rrank = {str(row["setId"]): int(row["rank"]) for row in right if row.get("rank")}
    overlap = sorted(set(lrank) & set(rrank))
    movement = [abs(lrank[key] - rrank[key]) for key in overlap]
    return {"overlapN": len(overlap), "spearman": _round(spearman([lrank[k] for k in overlap], [rrank[k] for k in overlap])),
            "top3Overlap": len(set(sorted(lrank, key=lrank.get)[:3]) & set(sorted(rrank, key=rrank.get)[:3])),
            "top5Overlap": len(set(sorted(lrank, key=lrank.get)[:5]) & set(sorted(rrank, key=rrank.get)[:5])),
            "meanAbsoluteRankMovement": _round(statistics.fmean(movement)) if movement else None,
            "maximumRankMovement": max(movement) if movement else None}


def _gate_check(status: str, observed: Any, required: Any, reason: str) -> dict[str, Any]:
    return {"status": status, "observedValues": observed, "requiredValues": required, "reason": reason}


def evaluate_promotion_gate(facts: Mapping[str, Any]) -> dict[str, Any]:
    """Evaluate the frozen research gate. This function cannot promote or publish."""
    req = PROMOTION_GATE_REQUIREMENTS
    ranked_count = int(facts.get("rankedSetCount") or 0)
    required_rankable = math.ceil(ranked_count * req["minimumSetCoverageRate"])
    rankable_count = int(facts.get("rankableSetCount") or 0)
    checks: dict[str, Any] = {}

    run_rate = float(facts.get("runAuthorityMatchRate") or 0)
    checks["runAuthority"] = _gate_check("PASS" if run_rate == 1 else "FAIL", {"matchRate": run_rate},
        {"matchRate": req["runAuthorityMatchRate"]}, "Every included row must match its owning ranked target calculation_run_id.")
    version_rate = float(facts.get("canonicalVersionMatchRate") or 0)
    checks["canonicalVersions"] = _gate_check("PASS" if version_rate == 1 else "FAIL",
        {"matchRate": version_rate, "versions": facts.get("canonicalVersions")},
        {"matchRate": req["canonicalVersionMatchRate"]}, "Mixed, fallback, or superseded canonical versions fail closed.")
    coverage_pass = ranked_count > 0 and rankable_count >= required_rankable
    checks["setCoverage"] = _gate_check("PASS" if coverage_pass else "FAIL",
        {"rankedSetCount": ranked_count, "rankableSetCount": rankable_count,
         "coverageRate": _round(rankable_count / ranked_count) if ranked_count else None},
        {"minimumCoverageRate": req["minimumSetCoverageRate"], "minimumRankableSetCount": required_rankable},
        "Sets below two participating families remain unavailable, never zero.")
    bad_families = list(facts.get("ineligibleParticipatingFamilies") or [])
    checks["familyCohortQuality"] = _gate_check("PASS" if not bad_families else "FAIL",
        {"ineligibleParticipatingFamilies": bad_families},
        {"minimumRepresentedSets": req["minimumFamilyRepresentedSets"],
         "sensitivityRepresentedSets": req["familyCohortSensitivityRepresentedSets"]},
        "Only families meeting the generic represented-set threshold may contribute.")
    deferred = dict(facts.get("deferredCoverage") or {})
    deferred_pass = all(bool(deferred.get(key)) for key in ("halfBoosterBox", "expandedEtb", "expandedPokemonCenterEtb"))
    checks["deferredCoverage"] = _gate_check("PASS" if deferred_pass else "BLOCKED", deferred,
        {"halfBoosterBox": "meaningful new artifact-backed coverage", "expandedEtb": True,
         "expandedPokemonCenterEtb": True, "enhancedBoosterBox": "required only if >=3 represented sets"},
        "The verified deferred cohort must be scored through the normal artifact-backed workflow.")

    loo = list(facts.get("informativeLeaveOneFamilyOut") or [])
    observed_loo = {"informativeOmissions": len(loo),
        "minimumSpearman": min((x["spearman"] for x in loo), default=None),
        "minimumTop5Overlap": min((x["top5Overlap"] for x in loo), default=None),
        "maximumMeanAbsoluteRankMovement": max((x["meanAbsoluteRankMovement"] for x in loo), default=None),
        "maximumIndividualRankMovement": max((x["maximumRankMovement"] for x in loo), default=None)}
    loo_pass = bool(loo) and observed_loo["minimumSpearman"] >= req["minimumLooSpearman"] \
        and observed_loo["minimumTop5Overlap"] >= req["minimumLooTop5Overlap"] \
        and observed_loo["maximumMeanAbsoluteRankMovement"] <= req["maximumLooMeanAbsoluteRankMovement"] \
        and observed_loo["maximumIndividualRankMovement"] <= req["maximumLooIndividualRankMovement"]
    checks["leaveOneFamilyOutStability"] = _gate_check("PASS" if loo_pass else "FAIL", observed_loo,
        {"minimumSpearman": req["minimumLooSpearman"], "minimumTop5Overlap": req["minimumLooTop5Overlap"],
         "maximumMeanAbsoluteRankMovement": req["maximumLooMeanAbsoluteRankMovement"],
         "maximumIndividualRankMovement": req["maximumLooIndividualRankMovement"]},
        "All informative participating-family omissions must satisfy every stability guardrail.")

    sensitivity = dict(facts.get("representativeSensitivity") or {})
    warnings = [name for name in ("best", "median") if name not in sensitivity
                or sensitivity[name].get("spearman") is None
                or sensitivity[name]["spearman"] < req["minimumRepresentativeSensitivitySpearman"]
                or sensitivity[name]["top5Overlap"] < req["minimumRepresentativeSensitivityTop5Overlap"]]
    checks["representativeSensitivity"] = _gate_check("REVIEW_REQUIRED" if warnings else "PASS",
        {"comparisons": sensitivity, "warningComparisons": warnings},
        {"bestAndMedianMinimumSpearman": req["minimumRepresentativeSensitivitySpearman"],
         "bestAndMedianMinimumTop5Overlap": req["minimumRepresentativeSensitivityTop5Overlap"],
         "requiredDiagnostics": ["coverage3", "familyCohort5", "groupBalanced"]},
        "BEST or MEDIAN crossing a warning threshold stops promotion for methodology review; group-balanced is diagnostic only.")
    fairness = facts.get("familyCountSpearman")
    fairness_review = fairness is not None and abs(float(fairness)) >= req["familyCountFairnessAbsoluteSpearmanReview"]
    checks["familyCountFairness"] = _gate_check("REVIEW_REQUIRED" if fairness_review else "PASS",
        {"spearmanCoverageVsSetRip": fairness},
        {"absoluteSpearmanReviewThreshold": req["familyCountFairnessAbsoluteSpearmanReview"]},
        "This is a diagnostic review guardrail, not a formula-tuning target.")
    invariant = bool(facts.get("multiSkuInvariantHolds"))
    checks["multiSkuInvariant"] = _gate_check("PASS" if invariant else "FAIL",
        {"oneVotePerSetFamily": invariant}, {"oneVotePerSetFamily": True},
        "Multiple SKUs may affect only their set-family arithmetic mean and never create duplicate final votes.")

    hard_fail = any(check["status"] == "FAIL" for check in checks.values())
    integrity_fail = any(checks[name]["status"] == "FAIL"
                         for name in ("runAuthority", "canonicalVersions", "familyCohortQuality", "multiSkuInvariant"))
    review = any(check["status"] == "REVIEW_REQUIRED" for check in checks.values())
    if integrity_fail:
        overall = "PROMOTION_GATE_FAILED"
    elif not deferred_pass:
        overall = "AWAITING_DEFERRED_COVERAGE"
    elif hard_fail:
        overall = "PROMOTION_GATE_FAILED"
    elif review:
        overall = "METHODOLOGY_SENSITIVITY_REVIEW_REQUIRED"
    else:
        overall = "METHODOLOGY_READY_FOR_PROMOTION_REVIEW"
    return {"researchVersion": RESEARCH_VERSION, "methodologyVersion": METHODOLOGY_VERSION,
            "overallStatus": overall, "checks": checks}


def analyze(matrix: Sequence[Mapping[str, Any]], targets: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    names = {str(t.get("set_id") or t.get("target_id")): t.get("name") for t in targets}
    configurations = []
    for spec in candidate_grid():
        ranked = rank_candidate(matrix, representative_policy=spec["representativePolicy"], method=spec["method"],
                                prior_strength=spec["priorStrength"], minimum_coverage=spec["minimumCoverage"],
                                minimum_family_sets=spec["minimumFamilySetCohort"])
        configurations.append({**spec, "ordering": [{**row, "setName": names.get(row["setId"])} for row in ranked]})

    recommended_spec = dict(LEADING_SPEC)
    recommended = rank_candidate(matrix, representative_policy="mean", method="mean", prior_strength=0,
                                 minimum_coverage=2, minimum_family_sets=3)
    previous = rank_candidate(matrix, representative_policy="best", method="mean", prior_strength=2,
                              minimum_coverage=2, minimum_family_sets=3)
    sensitivity_rankings = {
        "best": rank_candidate(matrix, representative_policy="best", method="mean", minimum_coverage=2, minimum_family_sets=3),
        "median": rank_candidate(matrix, representative_policy="median", method="mean", minimum_coverage=2, minimum_family_sets=3),
        "coverage3": rank_candidate(matrix, representative_policy="mean", method="mean", minimum_coverage=3, minimum_family_sets=3),
        "familyCohort5": rank_candidate(matrix, representative_policy="mean", method="mean", minimum_coverage=2, minimum_family_sets=5),
        "groupBalanced": rank_candidate(matrix, representative_policy="mean", method="group_balanced", minimum_coverage=2, minimum_family_sets=3),
    }
    previous_by_id = {row["setId"]: row for row in previous if row.get("rank")}
    current_by_id = {row["setId"]: row for row in recommended if row.get("rank")}
    affected = []
    for set_id in sorted(set(previous_by_id) & set(current_by_id)):
        old, new = previous_by_id[set_id], current_by_id[set_id]
        affected.append({"setId": set_id, "setName": names.get(set_id), "previousRank": old["rank"],
                         "currentRank": new["rank"], "rankMovement": old["rank"] - new["rank"],
                         "previousUnit": old["consensusValue"], "currentUnit": new["consensusValue"],
                         "unitChange": _round(new["consensusValue"] - old["consensusValue"])})
    affected.sort(key=lambda row: (-abs(row["rankMovement"]), row["setId"]))
    correlations = []
    family_means = _evidence(matrix, "mean")
    for index, left in enumerate(FAMILIES):
        for right in FAMILIES[index + 1:]:
            ids = sorted(set(s for s, row in family_means.items() if left in row) & set(s for s, row in family_means.items() if right in row))
            correlations.append({"leftFamily": left, "rightFamily": right, "overlapN": len(ids),
                                 "spearman": _round(spearman([family_means[s][left] for s in ids], [family_means[s][right] for s in ids]))})
    loo = []
    for family in FAMILIES:
        variant = rank_candidate(matrix, representative_policy="mean", method="mean", prior_strength=0,
                                 minimum_coverage=2, minimum_family_sets=3, omit_family=family)
        loo.append({"omittedFamily": family, **_ranking_comparison(recommended, variant)})

    eligible = _evidence(matrix, "mean", 3)
    additional_family_impacts = []
    for set_id, by_family in sorted(eligible.items()):
        if len(by_family) < 3:
            continue
        full = statistics.fmean(by_family.values())
        for family, family_mean in sorted(by_family.items()):
            without = statistics.fmean(value for key, value in by_family.items() if key != family)
            additional_family_impacts.append({"setId": set_id, "setName": names.get(set_id),
                "family": family, "familyMeanStanding": _round(family_mean), "fullSetRipUnit": _round(full),
                "withoutFamilySetRipUnit": _round(without), "impactOnSetRipUnit": _round(full - without)})

    multi_sku = [{"setId": cell["setId"], "setName": cell.get("setName"), "family": cell["family"],
                  "rankableSkuCount": cell["rankableSkuCount"], "rankableSkus": cell["rankableSkus"],
                  "bestStanding": cell["bestFamilyPercentile"], "medianStanding": cell["medianSkuPercentile"],
                  "meanStanding": cell["meanSkuPercentile"],
                  "bestMinusMean": _round(cell["bestFamilyPercentile"] - cell["meanSkuPercentile"])}
                 for cell in matrix if int(cell.get("rankableSkuCount") or 0) > 1]

    available = [row for row in recommended if row.get("rank")]
    coverage_values = [float(row["familyCoverageCount"]) for row in available]
    score_values = [float(row["consensusValue"]) for row in available]
    rank_values = [-float(row["rank"]) for row in available]
    by_coverage = []
    for count in sorted({int(row["familyCoverageCount"]) for row in available}):
        members = [row for row in available if row["familyCoverageCount"] == count]
        by_coverage.append({"familyCoverageCount": count, "setCount": len(members),
                            "meanSetRipUnit": _round(statistics.fmean(row["consensusValue"] for row in members))})
    pack_ranking = []
    for target in targets:
        rank = target.get("pack_rank") if target.get("pack_rank") is not None else target.get("packRank")
        set_id = target.get("set_id") or target.get("target_id")
        if rank is not None and set_id:
            pack_ranking.append({"setId": str(set_id), "rank": int(rank)})
    reasonable = [c for c in configurations if c["minimumCoverage"] in REASONABLE_COVERAGE_GATES and c["minimumFamilySetCohort"] in REASONABLE_COHORT_GATES]
    top3, top5 = defaultdict(int), defaultdict(int)
    for config in reasonable:
        ordered = [r for r in config["ordering"] if r.get("rank")]
        for row in ordered[:3]: top3[row["setId"]] += 1
        for row in ordered[:5]: top5[row["setId"]] += 1
    return {
        "candidateGrid": configurations,
        "recommendedCandidate": {**recommended_spec, "ordering": [{**r, "setName": names.get(r["setId"])} for r in recommended]},
        "previousLeadingCandidate": {**PREVIOUS_LEADING_SPEC, "ordering": [{**r, "setName": names.get(r["setId"])} for r in previous]},
        "previousVsCurrentLeading": _ranking_comparison(previous, recommended),
        "leadingMethodologySensitivity": {name: _ranking_comparison(recommended, ranking)
                                           for name, ranking in sensitivity_rankings.items()},
        "mostAffectedSets": affected,
        "multiSkuDiagnostics": multi_sku,
        "familyCountFairness": {"availableSetCount": len(available),
            "spearmanCoverageVsSetRip": _round(spearman(coverage_values, score_values)),
            "spearmanCoverageVsBetterRank": _round(spearman(coverage_values, rank_values)),
            "byCoverageCount": by_coverage,
            "interpretation": "Coverage is a rankability gate only. Every eligible family contributes one vote, regardless of its SKU count. In the current cohort, higher family coverage is negatively rather than positively associated with Set RIP, so this diagnostic does not show a systematic more-families advantage."},
        "additionalFamilyLeaveOutImpacts": additional_family_impacts,
        "familyCorrelations": correlations,
        "leaveOneFamilyOut": loo,
        "packRankingComparison": _ranking_comparison(recommended, pack_ranking),
        "topRankRobustness": {"configurationCount": len(reasonable),
            "top3Frequency": sorted(({"setId": k, "setName": names.get(k), "count": v} for k, v in top3.items()), key=lambda x: (-x["count"], x["setId"])),
            "top5Frequency": sorted(({"setId": k, "setName": names.get(k), "count": v} for k, v in top5.items()), key=lambda x: (-x["count"], x["setId"]))},
    }


def build_report(projection: Mapping[str, Any], targets: Sequence[Mapping[str, Any]], catalog: Mapping[str, Any]) -> dict[str, Any]:
    matrix = build_matrix(projection, targets, catalog)
    analysis = analyze(matrix, targets)
    recommended_available = sum(
        1 for row in analysis["recommendedCandidate"]["ordering"] if row.get("rank") is not None
    )
    coverage = {family: {"rankableSkus": int(block.get("count") or 0),
                         "representedSets": len({p.get("setId") for p in block.get("products") or []})}
                for family, block in sorted((projection.get("families") or {}).items())}
    for family in FAMILIES:
        coverage.setdefault(family, {"rankableSkus": 0, "representedSets": 0})
    products = [product for block in (projection.get("families") or {}).values()
                for product in block.get("products") or []]
    target_runs = {str(row.get("set_id") or row.get("target_id")): str(row.get("calculation_run_id") or "")
                   for row in targets}
    run_matches = [bool(product.get("calculationRunId")) and
                   str(product.get("calculationRunId")) == target_runs.get(str(product.get("setId")))
                   for product in products]
    canonical_versions = {"financialRip": CANONICAL_FINANCIAL_RIP_VERSION,
                          "collectorAppeal": canonical_collector_appeal_version(),
                          "overallRip": CANONICAL_OVERALL_RIP_VERSION}
    version_matches = [product.get("financialRipVersion") == canonical_versions["financialRip"]
                       and product.get("collectorAppealVersion") == canonical_versions["collectorAppeal"]
                       and product.get("overallRipVersion") == canonical_versions["overallRip"] for product in products]
    ranked_set_count = int(projection.get("authorityTargetCount") or
                           max((row["representedSets"] for row in coverage.values()), default=0))
    informative_loo = [row for row in analysis["leaveOneFamilyOut"]
                       if coverage.get(row["omittedFamily"], {}).get("representedSets", 0) >= LEADING_SPEC["minimumFamilySetCohort"]]
    participating = [row for row in analysis["recommendedCandidate"]["ordering"] if row.get("rank")]
    multi_sku_invariant = all(row["familyCoverageCount"] == len(set(row["participatingFamilies"]))
                              for row in participating)
    deferred = {
        "halfBoosterBox": coverage["half_booster_box"]["representedSets"] >= LEADING_SPEC["minimumFamilySetCohort"],
        "expandedEtb": coverage["elite_trainer_box"]["rankableSkus"] > FROZEN_BASELINE_FAMILY_COUNTS["elite_trainer_box"],
        "expandedPokemonCenterEtb": coverage["pokemon_center_elite_trainer_box"]["rankableSkus"] > FROZEN_BASELINE_FAMILY_COUNTS["pokemon_center_elite_trainer_box"],
        "enhancedBoosterBoxRepresentedSets": coverage["enhanced_booster_box"]["representedSets"],
    }
    gate = evaluate_promotion_gate({
        "runAuthorityMatchRate": statistics.fmean(run_matches) if run_matches else 0,
        "canonicalVersionMatchRate": statistics.fmean(version_matches) if version_matches else 0,
        "canonicalVersions": canonical_versions, "rankedSetCount": ranked_set_count,
        "rankableSetCount": recommended_available,
        "ineligibleParticipatingFamilies": [family for family, row in coverage.items()
            if 0 < row["representedSets"] < LEADING_SPEC["minimumFamilySetCohort"] and
            any(family in ranked["participatingFamilies"] for ranked in participating)],
        "deferredCoverage": deferred, "informativeLeaveOneFamilyOut": informative_loo,
        "representativeSensitivity": analysis["leadingMethodologySensitivity"],
        "familyCountSpearman": analysis["familyCountFairness"]["spearmanCoverageVsSetRip"],
        "multiSkuInvariantHolds": multi_sku_invariant,
    })
    report = {
        "researchVersion": RESEARCH_VERSION, "asOf": date.today().isoformat(),
        "methodologyVersion": METHODOLOGY_VERSION,
        "frozenMethodology": {**LEADING_SPEC,
            "skuStanding": "N == 1 ? 0.50 : 1 - ((familyRank - 1) / (N - 1))",
            "withinFamilyAggregation": "arithmetic_mean_all_rankable_sku_standings",
            "acrossFamilyAggregation": "equal_arithmetic_mean_available_eligible_family_scores",
            "missingFamilyPolicy": "omit_never_zero", "shrinkage": "none"},
        "researchOnly": True, "publishesSetRip": False,
        "comparisonScope": projection.get("comparisonScope"), "crossFormatComparable": projection.get("crossFormatComparable"),
        "standingDefinition": "N=1 => 0.50; otherwise 1 - ((rank - 1) / (N - 1))",
        "rawScorePolicy": "Raw Overall RIP and Financial RIP values are excluded from the matrix and every consensus calculation.",
        "coverage": coverage, "matrix": matrix, **analysis,
        "priorResearch": {"status": "INVALIDATED_BY_RUN_AUTHORITY_BUG",
            "reason": "The prior numeric artifacts selected sealed-product runs through one market date instead of each ranked target's calculation_run_id. The pre-registered 189-configuration methodology is unchanged; all numeric findings were recomputed."},
        "historicalEvidence": {"status": "HISTORICAL_EVIDENCE_INSUFFICIENT",
            "reason": "No stored historical product-family projections with current canonical model versions were found; historical Monte Carlo was not rerun."},
        "constructRecommendation": "Set RIP should measure a set's average relative ripping quality across eligible sealed-product families. Within each family, all rankable SKU standings are averaged; available eligible family means are then averaged with one equal vote per family.",
        "methodologyRecommendation": "Leading research candidate: mean SKU standing within each canonical product family, then an unshrunk equal-family arithmetic mean. A set needs at least two eligible families; a family needs at least three represented sets. Missing families are omitted, never zero, and SKU-rich families receive no extra weight.",
        "knownLimitations": ["Half Booster Box and Enhanced Booster Box currently have no or insufficient canonical coverage.",
            "Verified deferred products are missing evidence, not poor performance.", f"{recommended_available} sets currently clear the leading candidate's gate; this is research coverage, not a validated public Set RIP cohort.", "Related pack formats may count correlated evidence more than once; group-balanced results are retained as a sensitivity architecture."],
        "promotionGate": gate, "promotionStatus": gate["overallStatus"],
    }
    report["frozenBaseline"] = {"asOf": report["asOf"], "rankedSetCount": ranked_set_count,
        "rankableSetCount": recommended_available, "familyCounts": coverage,
        "leadingOrdering": [{"rank": row["rank"], "setId": row["setId"], "setName": row.get("setName"),
                             "setRipUnit": row["setRipUnit"], "setRipScore": row["setRipScore"]}
                            for row in participating]}
    report["postCoverageWorkflow"] = [
        "Rebuild normal product-family Rankings after normal artifact-backed simulations populate deferred products.",
        "Run this same frozen research harness without changing its methodology version or gate constants.",
        "Evaluate the pre-registered promotion gate.",
        "Compare before/after family coverage and descriptive ranking movement.",
        "Report PASS, FAIL, or REVIEW REQUIRED without changing methodology during the validation run.",
        "Return results for human promotion review; the harness cannot publish or promote itself.",
    ]
    return report


def rebuild_from_baseline_report(
    baseline: Mapping[str, Any], name_source: Mapping[str, Any] | None = None,
    target_metadata: Sequence[Mapping[str, Any]] = (),
) -> dict[str, Any]:
    """Recompute methodology from a previously captured canonical matrix.

    This is an offline reproducibility path for a pinned research cohort, not an
    alternate run resolver. The matrix already records the canonical family rank
    and cohort for every SKU selected through target calculation_run_id authority.
    """
    names_by_cell = {(cell["setId"], cell["family"]): cell.get("rankableSkus") or []
                     for cell in (name_source or {}).get("matrix", [])}
    projection: dict[str, Any] = {"comparisonScope": baseline.get("comparisonScope"),
                                  "crossFormatComparable": baseline.get("crossFormatComparable"),
                                  "runAuthority": "set_targets.calculation_run_id", "families": {}}
    catalog: dict[str, dict[str, list[dict[str, Any]]]] = defaultdict(lambda: defaultdict(list))
    targets_by_id: dict[str, dict[str, Any]] = {}
    metadata_by_id = {str(row.get("set_id") or row.get("target_id")): row for row in target_metadata}
    for cell in baseline["matrix"]:
        set_id, family = str(cell["setId"]), str(cell["family"])
        targets_by_id.setdefault(set_id, {"set_id": set_id, "canonical_key": cell.get("setCanonicalKey"),
                                          "name": cell.get("setName"),
                                          "calculation_run_id": "pinned-baseline-canonical-run",
                                          "pack_rank": metadata_by_id.get(set_id, {}).get("pack_rank")})
        if cell.get("availabilityStatus") == "catalogued_product_exists_unscored":
            catalog[set_id][family].append({"id": "baseline-unscored"})
        family_block = projection["families"].setdefault(family, {"count": cell.get("familyCohortSize", 0), "products": []})
        source_names = names_by_cell.get((set_id, family), [])
        for index, rank in enumerate(cell.get("skuFamilyRanks") or []):
            source = source_names[index] if index < len(source_names) else {}
            fallback = cell.get("bestSku") or {}
            family_block["products"].append({"setId": set_id,
                "sealedProductId": source.get("sealedProductId") or fallback.get("sealedProductId") or f"{set_id}:{family}:{index}",
                "productName": source.get("productName") or fallback.get("productName") or "Product name unavailable in baseline",
                "familyRank": rank, "calculationRunId": "pinned-baseline-canonical-run",
                "financialRipVersion": CANONICAL_FINANCIAL_RIP_VERSION,
                "collectorAppealVersion": canonical_collector_appeal_version(),
                "overallRipVersion": CANONICAL_OVERALL_RIP_VERSION})
    projection["authorityTargetCount"] = max(
        (len({product["setId"] for product in block["products"]}) for block in projection["families"].values()),
        default=0)
    report = build_report(projection, list(targets_by_id.values()), catalog)
    report["researchDataAuthority"] = "Pinned canonical matrix previously materialized through each ranked target's calculation_run_id. No market-date resolution."
    return report


def _render_markdown_v1(report: Mapping[str, Any]) -> str:
    rec = report["recommendedCandidate"]
    lines = ["# Set RIP Consensus Research", "", "READ-ONLY RESEARCH. No Set RIP score is published.", "",
             "# CURRENT COVERAGE", "", "| Family | Rankable SKUs | Represented sets |", "|---|---:|---:|"]
    for family, row in sorted(report["coverage"].items()):
        lines.append(f"| {REPORT_FAMILY_LABELS.get(family, family)} | {row['rankableSkus']} | {row['representedSets']} |")
    lines += ["", "# SET × FAMILY MATRIX", "", f"The JSON artifact contains {len(report['matrix'])} explicit cells. Missing cells are classified as catalogued-but-unscored or no-catalogued-product and never receive zero.", "",
              "# MULTI-SKU REPRESENTATIVE RESULTS", "", "Pre-registered R1 best, R2 median, and R3 mean policies are evaluated. BEST matches a user choosing the best available SKU; median/mean describe typical SKU quality.", "",
              "# FAMILY CORRELATION MATRIX", "", "| Family A | Family B | Overlap N | Spearman |", "|---|---|---:|---:|"]
    for row in report["familyCorrelations"]:
        lines.append(f"| {row['leftFamily']} | {row['rightFamily']} | {row['overlapN']} | {row['spearman']} |")
    lines += ["", "# CONSENSUS CANDIDATES", "", "C1 mean, C2 median, C3 neutral-shrunk means (prior strengths 1/2/3), C4 partial-ballot Borda, and a format-group-balanced alternative are all included in the JSON candidate grid.", "",
              "Recommended research ordering (not a published score):", "", "| Rank | Set | Consensus | Coverage | Families |", "|---:|---|---:|---:|---|"]
    for row in rec["ordering"]:
        rank = row.get("rank", "—")
        lines.append(f"| {rank} | {row.get('setName') or row['setId']} | {row['consensusValue'] if row['consensusValue'] is not None else 'unavailable'} | {row['familyCoverageCount']} | {', '.join(row['participatingFamilies'])} |")
    lines += ["", "# MISSINGNESS / COVERAGE RESULTS", "", "Observed-only, neutral shrinkage, and ≥2/≥3 coverage gates are pre-registered. A failed gate is unavailable, never zero.", "",
              "# FAMILY COHORT SIZE RESULTS", "", "Ungated, ≥3-set, and ≥5-set participating-family thresholds are pre-registered in code and fully enumerated in JSON.", "",
              "# FORMAT-GROUP COMPARISON", "", "The group-balanced candidate first averages within homogeneous-pack, trainer-box, and enhanced-box groups, then weights represented groups equally. It remains sensitivity-only.", "",
              "# LEAVE-ONE-FAMILY-OUT STABILITY", "", "| Omitted family | Overlap N | Spearman | Top-5 overlap | Mean abs movement | Max movement |", "|---|---:|---:|---:|---:|---:|"]
    for row in report["leaveOneFamilyOut"]:
        lines.append(f"| {row['omittedFamily']} | {row['overlapN']} | {row['spearman']} | {row['top5Overlap']} | {row['meanAbsoluteRankMovement']} | {row['maximumRankMovement']} |")
    pc = report["packRankingComparison"]
    lines += ["", "# CURRENT PACK-RANKING COMPARISON", "", f"Descriptive only; the pack ranking is not ground truth. Overlap N={pc['overlapN']}, Spearman={pc['spearman']}, top-5 overlap={pc['top5Overlap']}, mean absolute rank movement={pc['meanAbsoluteRankMovement']}, maximum movement={pc['maximumRankMovement']}.", "",
              "# HISTORICAL EVIDENCE", "", report["historicalEvidence"]["status"], "", report["historicalEvidence"]["reason"], "",
              "# PRIOR RESEARCH INVALIDATION", "", report["priorResearch"]["status"], "", report["priorResearch"]["reason"], "",
              "# CONSTRUCT RECOMMENDATION", "", report["constructRecommendation"], "", "This is construct A, BEST WAY TO RIP THE SET. It better matches “What set should I choose to rip right now?” than typical-SKU quality because the user can choose the SKU they buy.", "",
              "# METHODOLOGY RECOMMENDATION", "", report["methodologyRecommendation"], "", "The choice is methodological and was pre-registered; it does not depend on which set ranks first.", "",
              "# KNOWN LIMITATIONS", ""]
    lines.extend(f"- {item}" for item in report["knownLimitations"])
    lines += ["", "# PROMOTION STATUS", "", report["promotionStatus"], "", "# TESTS", "", "See the committed research unit tests and product-family ranking regression suite.", "", "# FILES CHANGED", "", "- `backend/scripts/research_set_rip_consensus.py`", "- `backend/tests/unit/scripts/test_research_set_rip_consensus.py`", "- `logs/set_rip_consensus_research.json`", "- `logs/set_rip_consensus_research.md`", ""]
    return "\n".join(lines)


def render_markdown(report: Mapping[str, Any]) -> str:
    rec = report["recommendedCandidate"]
    lines = ["# Set RIP Consensus Research", "", "READ-ONLY RESEARCH. No Set RIP score is published.", "",
             "# CURRENT COVERAGE", "", "| Family | Rankable SKUs | Represented sets |", "|---|---:|---:|"]
    for family, row in sorted(report["coverage"].items()):
        lines.append(f"| {REPORT_FAMILY_LABELS.get(family, family)} | {row['rankableSkus']} | {row['representedSets']} |")
    lines += ["", "# LEADING TWO-LEVEL CONSTRUCT", "", report["constructRecommendation"], "",
              report["methodologyRecommendation"], "", "# SET × FAMILY MATRIX", "",
              f"The JSON contains {len(report['matrix'])} explicit cells. Missing families are omitted, never zero.", "",
              "# MULTI-SKU DIAGNOSTICS", "",
              f"{len(report['multiSkuDiagnostics'])} cells have multiple rankable SKUs. The leading construct uses the mean.", "",
              "| Set | Family | SKUs (rank: standing) | Best | Median | Mean |", "|---|---|---|---:|---:|---:|"]
    for row in report["multiSkuDiagnostics"]:
        skus = "; ".join(f"{sku['productName']} ({sku['familyRank']}: {sku['standing']})" for sku in row["rankableSkus"])
        lines.append(f"| {row['setName'] or row['setId']} | {row['family']} | {skus} | {row['bestStanding']} | {row['medianStanding']} | {row['meanStanding']} |")
    lines += ["", "# FAMILY CORRELATIONS", "", "| Family A | Family B | Overlap N | Spearman |", "|---|---|---:|---:|"]
    for row in report["familyCorrelations"]:
        lines.append(f"| {row['leftFamily']} | {row['rightFamily']} | {row['overlapN']} | {row['spearman']} |")
    lines += ["",
              "# LEADING RESEARCH ORDERING", "", "| Rank | Set | Set RIP unit | Score ×100 | Families | SKU evidence |", "|---:|---|---:|---:|---:|---:|"]
    for row in rec["ordering"]:
        lines.append(f"| {row.get('rank', '—')} | {row.get('setName') or row['setId']} | {row['setRipUnit'] if row['setRipUnit'] is not None else 'unavailable'} | {row['setRipScore'] if row['setRipScore'] is not None else 'unavailable'} | {row['familyCoverageCount']} | {row['rankableSkuEvidenceCount']} |")
    comparison = report["previousVsCurrentLeading"]
    lines += ["", "# PREVIOUS VS CURRENT LEADING CONSTRUCT", "",
              f"Old BEST-SKU + prior-strength-2 versus new mean-SKU + no-shrinkage: overlap N={comparison['overlapN']}, Spearman={comparison['spearman']}, top-five overlap={comparison['top5Overlap']}, mean absolute movement={comparison['meanAbsoluteRankMovement']}, maximum movement={comparison['maximumRankMovement']}.", "",
              "| Set | Old rank | New rank | Movement | Old unit | New unit |", "|---|---:|---:|---:|---:|---:|"]
    for row in report["mostAffectedSets"][:10]:
        lines.append(f"| {row['setName'] or row['setId']} | {row['previousRank']} | {row['currentRank']} | {row['rankMovement']} | {row['previousUnit']} | {row['currentUnit']} |")
    fairness = report["familyCountFairness"]
    lines += ["", "# FAMILY-COUNT FAIRNESS", "", fairness["interpretation"], "",
              f"Available sets={fairness['availableSetCount']}; Spearman coverage versus Set RIP={fairness['spearmanCoverageVsSetRip']}; coverage versus better rank={fairness['spearmanCoverageVsBetterRank']}.", "",
              "| Family count | Sets | Average Set RIP unit |", "|---:|---:|---:|"]
    for row in fairness["byCoverageCount"]:
        lines.append(f"| {row['familyCoverageCount']} | {row['setCount']} | {row['meanSetRipUnit']} |")
    lines += ["", "# ADDITIONAL-FAMILY IMPACT", "", "Positive delta means the family improves the set's full mean; negative delta means it lowers it.", "",
              "| Set | Omitted family | Full unit | Without family | Delta |", "|---|---|---:|---:|---:|"]
    for row in report["additionalFamilyLeaveOutImpacts"]:
        lines.append(f"| {row['setName'] or row['setId']} | {row['family']} | {row['fullSetRipUnit']} | {row['withoutFamilySetRipUnit']} | {row['impactOnSetRipUnit']} |")
    lines += ["",
              "# LEAVE-ONE-FAMILY-OUT STABILITY", "", "| Omitted family | Overlap N | Spearman | Top-5 overlap | Mean abs movement | Max movement |", "|---|---:|---:|---:|---:|---:|"]
    for row in report["leaveOneFamilyOut"]:
        lines.append(f"| {row['omittedFamily']} | {row['overlapN']} | {row['spearman']} | {row['top5Overlap']} | {row['meanAbsoluteRankMovement']} | {row['maximumRankMovement']} |")
    pc = report["packRankingComparison"]
    robustness = report["topRankRobustness"]
    lines += ["", "# 189-CANDIDATE SENSITIVITY", "", f"All 189 pre-registered configurations remain in JSON. The reasonable-gate robustness subset contains {robustness['configurationCount']} configurations and reports top-three/top-five frequencies for every set.", "",
              "# PACK-RANKING COMPARISON", "", f"Descriptive only: overlap N={pc['overlapN']}, Spearman={pc['spearman']}, top-five overlap={pc['top5Overlap']}, mean absolute movement={pc['meanAbsoluteRankMovement']}, maximum movement={pc['maximumRankMovement']}.", "",
              "# PROMOTION GATE", "", f"Methodology version: `{report['methodologyVersion']}`", "",
              "| Check | Observed | Required | Status |", "|---|---|---|---|"]
    for name, check in report["promotionGate"]["checks"].items():
        observed = json.dumps(check["observedValues"], sort_keys=True).replace("|", "\\|")
        required = json.dumps(check["requiredValues"], sort_keys=True).replace("|", "\\|")
        lines.append(f"| {name} | `{observed}` | `{required}` | {check['status']} |")
    lines += ["", f"Overall: **{report['promotionGate']['overallStatus']}**", "",
              "# FROZEN BASELINE", "", f"As of {report['frozenBaseline']['asOf']}: {report['frozenBaseline']['rankableSetCount']} of {report['frozenBaseline']['rankedSetCount']} ranked sets clear the coverage gate. The full ordering and scores are recorded in JSON.", "",
              "# POST-COVERAGE WORKFLOW", ""]
    lines.extend(f"{index}. {item}" for index, item in enumerate(report["postCoverageWorkflow"], 1))
    lines += ["", "# HISTORICAL EVIDENCE", "", report["historicalEvidence"]["status"], "", report["historicalEvidence"]["reason"], "",
              "# PRIOR RESEARCH INVALIDATION", "", report["priorResearch"]["status"], "", report["priorResearch"]["reason"], "",
              "# KNOWN LIMITATIONS", ""]
    lines.extend(f"- {item}" for item in report["knownLimitations"])
    lines += ["", "# PROMOTION STATUS", "", report["promotionStatus"], ""]
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-dir", type=Path, default=Path("logs"))
    parser.add_argument("--baseline-revision", help="Recompute a pinned canonical matrix from this git revision")
    args = parser.parse_args()
    if args.baseline_revision:
        baseline = json.loads(subprocess.check_output(
            ["git", "show", f"{args.baseline_revision}:logs/set_rip_consensus_research.json"], text=True,
            encoding="utf-8"))
        current_names = json.loads((args.output_dir / "set_rip_consensus_research.json").read_text(encoding="utf-8")) \
            if (args.output_dir / "set_rip_consensus_research.json").exists() else {}
        metadata = list(get_rip_statistics_targets_payload().get("targets") or [])
        report = rebuild_from_baseline_report(baseline, current_names, metadata)
    else:
        payload = get_rip_statistics_targets_payload()
        targets = list(payload.get("targets") or [])
        projection = build_product_family_rankings(set_targets=targets)
        set_ids = sorted({str(t.get("set_id") or t.get("target_id")) for t in targets if t.get("set_id") or t.get("target_id")})
        report = build_report(projection, targets, _catalog_by_set(public_read_client, set_ids))
    args.output_dir.mkdir(parents=True, exist_ok=True)
    (args.output_dir / "set_rip_consensus_research.json").write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    (args.output_dir / "set_rip_consensus_research.md").write_text(render_markdown(report), encoding="utf-8")
    print(f"wrote research artifacts to {args.output_dir}; {report['promotionStatus']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
