"""Subject-level membership, fallback, and denominator sensitivity audit."""
import json
import statistics
from pathlib import Path

from backend.db.services.contextual_set_desirability_service import build_contextual_desirability_bundle
from backend.db.services.universal_set_desirability_service import get_universal_desirability_bundle
from backend.desirability.weighted_rip import spearman


CANDIDATES = [
    (0.005, 0, "all_positive_modeled_card_ev"),
    (0.01, 0, "all_positive_modeled_card_ev"),
    (0.02, 0, "all_positive_modeled_card_ev"),
    (0.03, 0, "all_positive_modeled_card_ev"),
    (0.01, 1, "all_positive_modeled_card_ev"),
    (0.01, 2, "all_positive_modeled_card_ev"),
    (0.01, 3, "all_positive_modeled_card_ev"),
    (0.01, 0, "mapped_pokemon_positive_ev"),
]


def _rank(rows, key):
    return {r["set_id"]: i for i, r in enumerate(sorted(rows, key=lambda x: (-x[key], x["set_id"])), 1)}


def _subject_detail(row):
    return {"name": row.get("name"), "role": row.get("role"),
            "subjectEvShare": row.get("subjectEvShare"), "desirabilityScore": row.get("desirabilityScore"),
            "representativeCard": row.get("representativeCard")}


def main():
    v3 = get_universal_desirability_bundle(force_refresh=True)["payloads"]
    reports = []
    baseline_membership = None
    for threshold, fallback, denominator in CANDIDATES:
        payloads = build_contextual_desirability_bundle(
            min_subject_share=threshold, minimum_subject_fallback=fallback,
            denominator=denominator, max_unresolved_ev_share=.10,
        )["payloads"]
        evaluated = [r for r in payloads.values() if r.get("source_calculation_run_id")]
        rows = [{"set_id": r["set_id"], "set": r["set_name"], "v3": (v3.get(r["set_id"]) or {}).get("score"),
                 "v4": r.get("score"), "meaningful": sum(x.get("role") == "meaningful_chase" for x in r.get("modeled_pokemon", []))}
                for r in evaluated]
        usable = [r for r in rows if r["v3"] is not None and r["v4"] is not None]
        old_rank, new_rank = _rank(usable, "v3"), _rank(usable, "v4")
        counts = [r["meaningful"] for r in usable]
        old_order = sorted(old_rank, key=old_rank.get); new_order = sorted(new_rank, key=new_rank.get)
        movers = [{"set": r["set"], "oldRank": old_rank[r["set_id"]], "newRank": new_rank[r["set_id"]],
                   "rankDelta": old_rank[r["set_id"]] - new_rank[r["set_id"]]}
                  for r in usable]
        membership = {r["set_id"]: {x["pokemonReferenceId"] for x in r.get("modeled_pokemon", []) if x.get("role") == "meaningful_chase"} for r in evaluated}
        if threshold == .01 and fallback == 0 and denominator == "all_positive_modeled_card_ev":
            baseline_membership = membership
        cases = {}
        for name in ("Paldea Evolved", "Ascended Heroes", "Journey Together"):
            row = next(r for r in evaluated if r.get("set_name") == name)
            modeled = row.get("modeled_pokemon", [])
            strength_refs = {x.get("pokemon_reference_id") for x in row.get("top_subjects", [])}
            cases[name] = {"score": row.get("score"),
                           "meaningfulPokemon": [_subject_detail(x) for x in modeled if x.get("role") == "meaningful_chase"],
                           "supportingPokemon": [_subject_detail(x) for x in modeled if x.get("role") == "supporting_roster"],
                           "pikachuRole": next((x.get("role") for x in modeled if x.get("name") == "Pikachu"), None),
                           "strengthSlotOrder": [x.get("subject_name") for x in row.get("top_subjects", [])],
                           "strengthSlotReferenceIds": sorted(x for x in strength_refs if x is not None)}
        reports.append({"subjectEvShareThreshold": threshold, "minimumSubjectFallback": fallback,
                        "denominator": denominator, "evaluatedCohortSize": len(evaluated), "rankableCohortSize": len(usable),
                        "meaningfulSubjectCount": {"median": statistics.median(counts) if counts else None,
                                                   "min": min(counts) if counts else None, "max": max(counts) if counts else None,
                                                   "bySet": {r["set"]: r["meaningful"] for r in rows}},
                        "scoreSpearmanVsV3": spearman([r["v3"] for r in usable], [r["v4"] for r in usable]),
                        "rankSpearmanVsV3": spearman([old_rank[r["set_id"]] for r in usable], [new_rank[r["set_id"]] for r in usable]),
                        "top5OverlapVsV3": len(set(old_order[:5]) & set(new_order[:5])),
                        "top10OverlapVsV3": len(set(old_order[:10]) & set(new_order[:10])),
                        "meanAbsoluteRankDeltaVsV3": sum(abs(x["rankDelta"]) for x in movers) / len(movers),
                        "largestUp": sorted(movers, key=lambda x: x["rankDelta"], reverse=True)[:5],
                        "largestDown": sorted(movers, key=lambda x: x["rankDelta"])[:5],
                        "membership": {k: sorted(v) for k, v in membership.items()}, "sanityCases": cases})
    if baseline_membership is not None:
        for report in reports:
            membership = report.pop("membership")
            report["membershipChangesVsSelectedAllEv1Pct"] = sum(
                set(membership.get(set_id, [])) != refs for set_id, refs in baseline_membership.items()
            )
    path = Path("logs/contextual_roster_v4_subject_sensitivity.json")
    path.write_text(json.dumps(reports, indent=2), encoding="utf-8")
    print(path)
    print(json.dumps([{k: r[k] for k in ("subjectEvShareThreshold", "minimumSubjectFallback", "denominator",
                                         "rankableCohortSize", "meaningfulSubjectCount", "scoreSpearmanVsV3",
                                         "top5OverlapVsV3", "top10OverlapVsV3", "meanAbsoluteRankDeltaVsV3",
                                         "membershipChangesVsSelectedAllEv1Pct")} for r in reports], indent=2))


if __name__ == "__main__":
    main()
