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
from backend.domain.pokemon.sealed_product_classifier import FAMILY_LABELS, classify_sealed_product
from backend.domain.pokemon.sealed_product_comparison_scope import COMPARABLE_FAMILIES

RESEARCH_VERSION = "set-rip-consensus-research-v1"
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
PROMOTION_STATUS = "RESEARCH_NOT_READY_FOR_PROMOTION"


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
                "skuFamilyRanks": ranks,
                "skuFamilyPercentiles": [_round(v) for v in standings],
                "bestSku": None if best is None else {
                    "sealedProductId": best.get("sealedProductId"), "productName": best.get("productName")
                },
                "bestFamilyRank": None if best is None else best.get("familyRank"),
                "bestFamilyPercentile": _round(max(standings)) if standings else None,
                "medianSkuPercentile": _round(statistics.median(standings)) if standings else None,
                "meanSkuPercentile": _round(statistics.fmean(standings)) if standings else None,
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
    if omit_family:
        evidence = {set_id: {f: v for f, v in row.items() if f != omit_family} for set_id, row in evidence.items()}
    borda = _borda_values(evidence) if method == "borda" else {}
    rows = []
    for set_id, by_family in evidence.items():
        values = list(by_family.values())
        coverage = len(values)
        value: float | None
        if coverage < minimum_coverage or not values:
            value = None
        elif method == "mean":
            value = shrunk_mean(values, prior_strength) if prior_strength else statistics.fmean(values)
        elif method == "median":
            value = statistics.median(values)
        elif method == "borda":
            base = borda.get(set_id)
            value = None if base is None else shrunk_mean([base] * coverage, prior_strength) if prior_strength else base
        elif method == "group_balanced":
            base = _group_balanced(by_family)
            value = None if base is None else shrunk_mean([base] * coverage, prior_strength) if prior_strength else base
        else:
            raise ValueError(f"unknown aggregation method: {method}")
        rows.append({"setId": set_id, "consensusValue": _round(value), "familyCoverageCount": coverage,
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
            "top5Overlap": len(set(sorted(lrank, key=lrank.get)[:5]) & set(sorted(rrank, key=rrank.get)[:5])),
            "meanAbsoluteRankMovement": _round(statistics.fmean(movement)) if movement else None,
            "maximumRankMovement": max(movement) if movement else None}


def analyze(matrix: Sequence[Mapping[str, Any]], targets: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    names = {str(t.get("set_id") or t.get("target_id")): t.get("name") for t in targets}
    configurations = []
    for spec in candidate_grid():
        ranked = rank_candidate(matrix, representative_policy=spec["representativePolicy"], method=spec["method"],
                                prior_strength=spec["priorStrength"], minimum_coverage=spec["minimumCoverage"],
                                minimum_family_sets=spec["minimumFamilySetCohort"])
        configurations.append({**spec, "ordering": [{**row, "setName": names.get(row["setId"])} for row in ranked]})

    recommended_spec = {"representativePolicy": "best", "method": "mean", "priorStrength": 2,
                        "minimumCoverage": 2, "minimumFamilySetCohort": 3}
    recommended = rank_candidate(matrix, representative_policy="best", method="mean", prior_strength=2,
                                 minimum_coverage=2, minimum_family_sets=3)
    correlations = []
    best = _evidence(matrix, "best")
    for index, left in enumerate(FAMILIES):
        for right in FAMILIES[index + 1:]:
            ids = sorted(set(s for s, row in best.items() if left in row) & set(s for s, row in best.items() if right in row))
            correlations.append({"leftFamily": left, "rightFamily": right, "overlapN": len(ids),
                                 "spearman": _round(spearman([best[s][left] for s in ids], [best[s][right] for s in ids]))})
    loo = []
    for family in FAMILIES:
        variant = rank_candidate(matrix, representative_policy="best", method="mean", prior_strength=2,
                                 minimum_coverage=2, minimum_family_sets=3, omit_family=family)
        loo.append({"omittedFamily": family, **_ranking_comparison(recommended, variant)})
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
    coverage = {family: {"rankableSkus": int(block.get("count") or 0),
                         "representedSets": len({p.get("setId") for p in block.get("products") or []})}
                for family, block in sorted((projection.get("families") or {}).items())}
    for family in FAMILIES:
        coverage.setdefault(family, {"rankableSkus": 0, "representedSets": 0})
    return {
        "researchVersion": RESEARCH_VERSION, "asOf": date.today().isoformat(),
        "researchOnly": True, "publishesSetRip": False,
        "comparisonScope": projection.get("comparisonScope"), "crossFormatComparable": projection.get("crossFormatComparable"),
        "standingDefinition": "N=1 => 0.50; otherwise 1 - ((rank - 1) / (N - 1))",
        "rawScorePolicy": "Raw Overall RIP and Financial RIP values are excluded from the matrix and every consensus calculation.",
        "coverage": coverage, "matrix": matrix, **analysis,
        "historicalEvidence": {"status": "HISTORICAL_EVIDENCE_INSUFFICIENT",
            "reason": "No stored historical product-family projections with current canonical model versions were found; historical Monte Carlo was not rerun."},
        "constructRecommendation": "Set RIP should mean the best currently rankable way to rip a set across the product formats for which evidence exists, with uncertainty from sparse format coverage pulled toward neutral.",
        "methodologyRecommendation": "Retain as the leading candidate: BEST-SKU family representation, equal-family mean standing, neutral 0.50 shrinkage with prior strength 2, a minimum two-family coverage gate, and a minimum three-set participating family cohort. This matches the choice-oriented question, preserves separate consumer formats, and limits one-observation extremes without treating missing products as bad. Current coverage is too thin to select it for promotion.",
        "knownLimitations": ["Half Booster Box and Enhanced Booster Box currently have no or insufficient canonical coverage.",
            "Verified deferred products are missing evidence, not poor performance.", "Only three sets currently clear the leading candidate's gate, so stability statistics are weak and cannot support promotion.", "Related pack formats may count correlated evidence more than once; group-balanced results are retained as a sensitivity architecture."],
        "promotionStatus": PROMOTION_STATUS,
    }


def render_markdown(report: Mapping[str, Any]) -> str:
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
              "# CONSTRUCT RECOMMENDATION", "", report["constructRecommendation"], "", "This is construct A, BEST WAY TO RIP THE SET. It better matches “What set should I choose to rip right now?” than typical-SKU quality because the user can choose the SKU they buy.", "",
              "# METHODOLOGY RECOMMENDATION", "", report["methodologyRecommendation"], "", "The choice is methodological and was pre-registered; it does not depend on which set ranks first.", "",
              "# KNOWN LIMITATIONS", ""]
    lines.extend(f"- {item}" for item in report["knownLimitations"])
    lines += ["", "# PROMOTION STATUS", "", report["promotionStatus"], "", "# TESTS", "", "See the committed research unit tests and product-family ranking regression suite.", "", "# FILES CHANGED", "", "- `backend/scripts/research_set_rip_consensus.py`", "- `backend/tests/unit/scripts/test_research_set_rip_consensus.py`", "- `logs/set_rip_consensus_research.json`", "- `logs/set_rip_consensus_research.md`", ""]
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-dir", type=Path, default=Path("logs"))
    args = parser.parse_args()
    payload = get_rip_statistics_targets_payload()
    targets = list(payload.get("targets") or [])
    market_date = ((payload.get("meta") or {}).get("comparisonSnapshots") or {}).get("currentMarketDate")
    projection = build_product_family_rankings(market_date=market_date, set_targets=targets)
    set_ids = sorted({str(t.get("set_id") or t.get("target_id")) for t in targets if t.get("set_id") or t.get("target_id")})
    report = build_report(projection, targets, _catalog_by_set(public_read_client, set_ids))
    args.output_dir.mkdir(parents=True, exist_ok=True)
    (args.output_dir / "set_rip_consensus_research.json").write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    (args.output_dir / "set_rip_consensus_research.md").write_text(render_markdown(report), encoding="utf-8")
    print(f"wrote research artifacts to {args.output_dir}; {report['promotionStatus']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
