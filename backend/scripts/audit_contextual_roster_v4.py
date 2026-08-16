"""Read-only same-cohort and expanded-cohort audits for contextual roster V4."""
from __future__ import annotations

import json
import statistics
from datetime import datetime, timezone
from pathlib import Path

from backend.db.services.contextual_set_desirability_service import build_contextual_desirability_bundle
from backend.db.services.collector_appeal_service import get_collector_appeal_bundle
from backend.db.services.explore_rip_statistics_service import get_rip_statistics_targets_payload
from backend.db.services.universal_set_desirability_service import get_universal_desirability_bundle
from backend.db.clients.supabase_client import public_read_client
from backend.desirability.collector_appeal import compute_collector_appeal_v4
from backend.desirability.weighted_rip import compute_overall_rip_v8, spearman


def _rank(rows, key):
    ordered = sorted((r for r in rows if r.get(key) is not None), key=lambda r: (-r[key], r["set_id"]))
    return {r["set_id"]: index for index, r in enumerate(ordered, 1)}


def _metrics(rows, prefix):
    usable = [r for r in rows if r.get(f"old_{prefix}") is not None and r.get(f"new_{prefix}") is not None]
    old_rank, new_rank = _rank(usable, f"old_{prefix}"), _rank(usable, f"new_{prefix}")
    for row in usable:
        row[f"old_{prefix}_rank"] = old_rank[row["set_id"]]
        row[f"new_{prefix}_rank"] = new_rank[row["set_id"]]
        row[f"{prefix}_rank_delta"] = old_rank[row["set_id"]] - new_rank[row["set_id"]]
        row[f"{prefix}_delta"] = round(row[f"new_{prefix}"] - row[f"old_{prefix}"], 4)
    old_order = [x[0] for x in sorted(old_rank.items(), key=lambda x: x[1])]
    new_order = [x[0] for x in sorted(new_rank.items(), key=lambda x: x[1])]
    deltas = [abs(r[f"{prefix}_rank_delta"]) for r in usable]
    return {"ranked_count": len(usable),
            "score_spearman": spearman([r[f"old_{prefix}"] for r in usable], [r[f"new_{prefix}"] for r in usable]),
            "rank_spearman": spearman([old_rank[r["set_id"]] for r in usable], [new_rank[r["set_id"]] for r in usable]),
            "top5_overlap": len(set(old_order[:5]) & set(new_order[:5])),
            "top10_overlap": len(set(old_order[:10]) & set(new_order[:10])),
            "mean_absolute_rank_delta": sum(deltas) / len(deltas) if deltas else None,
            "max_rank_delta": max(deltas) if deltas else None,
            "largest_up": [r["set"] for r in sorted(usable, key=lambda r: r[f"{prefix}_rank_delta"], reverse=True)[:5]],
            "largest_down": [r["set"] for r in sorted(usable, key=lambda r: r[f"{prefix}_rank_delta"])[:5]]}


def _build_report(rows, *, label, requested_ids):
    selected = [dict(row) for row in rows if row["set_id"] in requested_ids]
    summary = {prefix: _metrics(selected, prefix) for prefix in ("roster", "collector", "overall")}
    unavailable = [{"set_id": r["set_id"], "set": r["set"], "reason": r.get("candidate_reason")} for r in selected if r.get("new_roster") is None]
    unresolved = sorted((r.get("chase_evidence") or {}).get("unresolved_ev_share") for r in selected
                        if (r.get("chase_evidence") or {}).get("unresolved_ev_share") is not None)
    def percentile(fraction):
        if not unresolved:
            return None
        index = fraction * (len(unresolved) - 1); low = int(index); high = min(low + 1, len(unresolved) - 1)
        return unresolved[low] + (unresolved[high] - unresolved[low]) * (index - low)
    mapping = {"unresolvedEvShare": {"min": min(unresolved) if unresolved else None,
                                      "median": statistics.median(unresolved) if unresolved else None,
                                      "p90": percentile(.90), "p95": percentile(.95),
                                      "max": max(unresolved) if unresolved else None},
               "reliabilityGateMaxUnresolvedEvShare": .10}
    return {"label": label, "requested_cohort_size": len(requested_ids), "evaluated_set_count": len(selected),
            "candidate_rankable_count": sum(r.get("new_roster") is not None for r in selected),
            "candidate_unavailable": unavailable, "mappingCoverage": mapping,
            "summary": summary, "rows": selected}


def main():
    candidate = build_contextual_desirability_bundle()["payloads"]
    current_roster = get_universal_desirability_bundle()["payloads"]
    current_collector = get_collector_appeal_bundle()["payloads"]
    production = get_rip_statistics_targets_payload()
    targets = {str(row.get("target_id")): row for row in production.get("targets") or []}
    public_ids = set((((production.get("meta") or {}).get("publicAnalyticsCohort") or {}).get("overallRanked") or {}).get("rankedSetIds") or [])
    run_ids = [row.get("source_calculation_run_id") for row in candidate.values() if row.get("source_calculation_run_id")]
    metric_rows = (public_read_client.table("simulation_derived_metrics")
                   .select("calculation_run_id,financial_rip_v3_score")
                   .in_("calculation_run_id", run_ids).execute()).data or []
    financial_by_run = {str(row.get("calculation_run_id")): row.get("financial_rip_v3_score") for row in metric_rows}
    rows = []
    for set_id, v4 in candidate.items():
        current = targets.get(set_id) or {}
        old_roster = (current_roster.get(set_id) or {}).get("score")
        opening = current_collector.get(set_id) or {}
        old_collector = (opening.get("collectorAppeal") or {}).get("score")
        frequency = (opening.get("desirableOutcomeFrequency") or {}).get("rawValue")
        new_unit = compute_collector_appeal_v4(v4["score"] / 100.0, frequency) if v4.get("score") is not None else None
        new_collector = new_unit * 100.0 if new_unit is not None else None
        financial = financial_by_run.get(str(v4.get("source_calculation_run_id")))
        old_overall = compute_overall_rip_v8(financial, old_collector).get("score")
        new_overall = compute_overall_rip_v8(financial, new_collector).get("score")
        rows.append({"set_id": set_id, "set": v4.get("set_name"), "old_roster": old_roster,
                     "new_roster": v4.get("score"), "old_collector": old_collector,
                     "new_collector": new_collector, "old_overall": old_overall,
                     "new_overall": new_overall, "candidate_reason": v4.get("reason"),
                     "meaningful_subject_count": sum(x.get("role") == "meaningful_chase" for x in v4.get("modeled_pokemon", [])),
                     "strength_slot_order": [{"name": x.get("subject_name"),
                                               "pokemonReferenceId": x.get("pokemon_reference_id"),
                                               "desirabilityScore": x.get("subject_demand"),
                                               "slotWeight": x.get("slot_weight")}
                                              for x in v4.get("top_subjects", [])],
                     "modeled_pokemon": v4.get("modeled_pokemon", []), "chase_evidence": v4.get("chase_evidence")})
    generated = datetime.now(timezone.utc).isoformat()
    production_report = _build_report(rows, label="same_public_v8_22_set_cohort_model_change_only", requested_ids=public_ids)
    research_ids = {set_id for set_id, row in candidate.items() if row.get("source_calculation_run_id")}
    research_report = _build_report(rows, label="expanded_34_set_research_cohort_model_change_plus_cohort_expansion", requested_ids=research_ids)
    for report, name in ((production_report, "contextual_roster_v4_production_cohort_audit.json"),
                         (research_report, "contextual_roster_v4_research_cohort_audit.json")):
        report["generated_at"] = generated
        path = Path("logs") / name
        path.write_text(json.dumps(report, indent=2), encoding="utf-8")
        print(path)
        print(json.dumps({"label": report["label"], "requested": report["requested_cohort_size"],
                          "rankable": report["candidate_rankable_count"], "summary": report["summary"]}, indent=2))


if __name__ == "__main__":
    main()
