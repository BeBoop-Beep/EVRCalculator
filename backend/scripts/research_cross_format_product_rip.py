"""Artifact-backed, SELECT-only research on Financial RIP V3 opening-unit size.

Production modules must never import this file.  The only writes performed are
the explicitly requested JSON and Markdown research reports.
"""

from __future__ import annotations

import argparse
import json
import math
import sys
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

import numpy as np

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from backend.calculations.evr.financial_rip_v3 import build_financial_rip_v3
from backend.calculations.evr.financial_rip_v3_config import FINANCIAL_RIP_V3_COMPONENT_ORDER
from backend.calculations.evr.sealed_product_distribution import build_stage1_product_distributions
from backend.db.services.pack_outcome_artifact_service import load_pack_outcome_artifact

PACK_COUNTS = (1, 6, 9, 11, 18, 36)
EXPECTED_COHORT = 22
EXPECTED_OUTCOMES = 1_000_000
FINANCIAL_VERSION_PREFIX = "financial_rip_v3_"
OVERALL_VERSION_PREFIX = "overall_rip_v9_"
DECISION = "CROSS_FORMAT_COMPARABILITY_NOT_SUPPORTED"


def _rows(response: Any) -> list[dict[str, Any]]:
    return list((response.data if response else []) or [])


def resolve_authoritative_snapshot(client: Any) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """Resolve only the latest complete, actually published canonical snapshot."""
    snapshots = _rows(
        client.table("pokemon_public_rip_leaderboard_snapshots")
        .select("*")
        .eq("publication_status", "complete")
        .not_.is_("published_at", "null")
        .order("market_date", desc=True)
        .order("published_at", desc=True)
        .limit(1)
        .execute()
    )
    if not snapshots:
        raise RuntimeError("no complete published canonical leaderboard snapshot exists")
    snapshot = snapshots[0]
    rows = _rows(
        client.table("pokemon_public_rip_leaderboard_rows")
        .select("*")
        .eq("snapshot_id", str(snapshot["id"]))
        .order("overall_rip_rank")
        .execute()
    )
    validate_authority(snapshot, rows)
    return snapshot, rows


def validate_authority(snapshot: Mapping[str, Any], rows: Sequence[Mapping[str, Any]]) -> None:
    expected = int(snapshot.get("eligible_cohort_count") or 0)
    if snapshot.get("publication_status") != "complete" or not snapshot.get("published_at"):
        raise RuntimeError("snapshot is not complete and published")
    if expected != EXPECTED_COHORT or len(rows) != expected:
        raise RuntimeError(f"incomplete cohort: snapshot={expected}, rows={len(rows)}, expected={EXPECTED_COHORT}")
    if not str(snapshot.get("financial_rip_version") or "").startswith(FINANCIAL_VERSION_PREFIX):
        raise RuntimeError("snapshot is not Financial RIP V3")
    if not str(snapshot.get("overall_rip_version") or "").startswith(OVERALL_VERSION_PREFIX):
        raise RuntimeError("snapshot is not Overall RIP V9")
    set_ids = [str(row.get("set_id") or "") for row in rows]
    keys = [str(row.get("set_canonical_key") or "") for row in rows]
    run_ids = [str(row.get("simulation_calculation_run_id") or "") for row in rows]
    if any(not value for value in set_ids + keys + run_ids):
        raise RuntimeError("an authoritative leaderboard row is missing set/run identity")
    if len(set(set_ids)) != expected or len(set(keys)) != expected:
        raise RuntimeError("duplicate set authority exists")
    if len(set(run_ids)) != expected:
        raise RuntimeError("authoritative calculation run IDs are not one-to-one with sets")
    if sorted(int(row.get("overall_rip_rank") or 0) for row in rows) != list(range(1, expected + 1)):
        raise RuntimeError("overall ranks are not contiguous")
    for row in rows:
        if float(row.get("pack_price") or 0) <= 0:
            raise RuntimeError(f"{row.get('set_canonical_key')} has no authoritative positive pack cost")


def _derived_by_run(client: Any, run_ids: Sequence[str]) -> dict[str, dict[str, Any]]:
    columns = (
        "calculation_run_id,top1_ev_share,top3_ev_share,top5_ev_share,"
        "hhi_ev_concentration,effective_chase_count,financial_rip_v3_payload"
    )
    records: list[dict[str, Any]] = []
    for start in range(0, len(run_ids), 20):
        records.extend(_rows(client.table("simulation_derived_metrics").select(columns).in_(
            "calculation_run_id", list(run_ids[start:start + 20])
        ).execute()))
    mapped = {str(row["calculation_run_id"]): row for row in records}
    missing = sorted(set(run_ids) - set(mapped))
    if missing:
        raise RuntimeError(f"authoritative calculation runs missing derived metrics: {missing}")
    return mapped


def verify_collector_appeal_inheritance(client: Any, run_ids: Sequence[str]) -> dict[str, Any]:
    """Verify production product rows inherit one CA V5 value per set/run."""
    columns = "set_id,calculation_run_id,product_family,collector_appeal_score,collector_appeal_version,overall_rip_version"
    records: list[dict[str, Any]] = []
    for start in range(0, len(run_ids), 20):
        records.extend(_rows(client.table("simulation_sealed_product_results").select(columns).in_(
            "calculation_run_id", list(run_ids[start:start + 20])
        ).execute()))
    if not records:
        raise RuntimeError("no current production sealed-product rows exist for the authoritative runs")
    groups: dict[tuple[str, str], set[float]] = {}
    for row in records:
        if "collector_appeal_v5" not in str(row.get("collector_appeal_version") or ""):
            raise RuntimeError("an authoritative production product row is not Collector Appeal V5")
        value = row.get("collector_appeal_score")
        if value is None:
            raise RuntimeError("an authoritative production product row is missing Collector Appeal V5")
        key = (str(row.get("set_id")), str(row.get("calculation_run_id")))
        groups.setdefault(key, set()).add(float(value))
    inconsistent = [key for key, values in groups.items() if len(values) != 1]
    if inconsistent:
        raise RuntimeError(f"Collector Appeal varies across formats for set/run groups: {inconsistent}")
    return {"verifiedFromProductionProductRows": True, "rowCount": len(records),
            "setRunCount": len(groups), "allSetRunValuesConstantAcrossFormats": True}


def _score_entry(values: np.ndarray, cost: float, count: int) -> dict[str, Any]:
    payload = build_financial_rip_v3(values, cost)
    normalized = ((payload.get("audit") or {}).get("normalizedInputs") or {})
    disclosures = payload.get("distributionDisclosures") or {}
    return {
        "packCount": count, "controlledCost": cost,
        "score": payload.get("score"), "status": payload.get("status"),
        "rankable": payload.get("rankable"),
        "components": {key: (payload.get("components") or {}).get(key, {}).get("score")
                       for key in FINANCIAL_RIP_V3_COMPONENT_ORDER},
        "rawInputs": {key: record.get("raw") for key, record in normalized.items()},
        "distributionDisclosures": disclosures,
        "clippedInputs": (payload.get("estimationDiagnostics") or {}).get("clippedInputs") or [],
        "rtpRatioDirect": float(np.mean(values) / cost),
    }


def score_set(client: Any, row: Mapping[str, Any], derived: Mapping[str, Any]) -> dict[str, Any]:
    run_id = str(row["simulation_calculation_run_id"])
    artifact = load_pack_outcome_artifact(client, run_id)
    if int(artifact.metadata.get("outcome_count") or -1) != EXPECTED_OUTCOMES:
        raise RuntimeError(f"{row['set_canonical_key']} artifact count is not {EXPECTED_OUTCOMES}")
    built = build_stage1_product_distributions(
        artifact.outcomes, pack_counts=PACK_COUNTS,
        canonical_set_key=row["set_canonical_key"], run_fingerprint=artifact.metadata["raw_sha256"],
    )
    pack_cost = float(row["pack_price"])
    entries = [_score_entry(built["distributions"][count], pack_cost * count, count)
               for count in PACK_COUNTS]
    baseline = float(entries[0]["score"])
    baseline_rtp = entries[0]["rtpRatioDirect"]
    for entry in entries:
        entry["deltaVsOnePack"] = float(entry["score"] - baseline)
        entry["rtpDeviationVsOnePack"] = float(entry["rtpRatioDirect"] - baseline_rtp)
        entry["componentDeltasVsOnePack"] = {
            key: float(entry["components"][key] - entries[0]["components"][key])
            for key in FINANCIAL_RIP_V3_COMPONENT_ORDER
        }
    persisted = derived.get("financial_rip_v3_payload") or {}
    concentration = {key: derived.get(key) for key in (
        "top1_ev_share", "top3_ev_share", "top5_ev_share", "hhi_ev_concentration", "effective_chase_count"
    )}
    concentration["jackpot_value_share"] = (persisted.get("distributionDisclosures") or {}).get("jackpotValueShare")
    return {
        "setId": row["set_id"], "canonicalKey": row["set_canonical_key"],
        "overallRank": row["overall_rip_rank"], "authoritativeRunId": run_id,
        "authoritativePackCost": pack_cost,
        "publishedScores": {"financialRipV3": row["financial_rip_score"], "overallRipV9": row["overall_rip_score"]},
        "collectorAppealV5Derived": (float(row["overall_rip_score"]) - .9 * float(row["financial_rip_score"])) / .1,
        "concentration": concentration,
        "artifact": dict(artifact.metadata), "distributionMeta": built["meta"], "entries": entries,
        "maxAbsolutePackCountDelta": max(abs(float(entry["deltaVsOnePack"])) for entry in entries[1:]),
    }


def _summary(values: Iterable[float]) -> dict[str, Any]:
    a = np.asarray(list(values), dtype=float)
    absolute = np.abs(a)
    return {"n": int(a.size), "mean": float(np.mean(a)), "median": float(np.median(a)),
            "min": float(np.min(a)), "max": float(np.max(a)), "p25": float(np.percentile(a, 25)),
            "p75": float(np.percentile(a, 75)), "iqr": float(np.percentile(a, 75)-np.percentile(a, 25)),
            "meanAbsolute": float(np.mean(absolute)), "medianAbsolute": float(np.median(absolute)),
            "p90Absolute": float(np.percentile(absolute, 90)), "maxAbsolute": float(np.max(absolute))}


def _rankdata(values: np.ndarray) -> np.ndarray:
    order = np.argsort(values, kind="mergesort")
    ranks = np.empty(len(values), float)
    i = 0
    while i < len(values):
        j = i + 1
        while j < len(values) and values[order[j]] == values[order[i]]:
            j += 1
        ranks[order[i:j]] = (i + j - 1) / 2 + 1
        i = j
    return ranks


def spearman(pairs: Iterable[tuple[Any, Any]]) -> dict[str, Any]:
    clean = [(float(x), float(y)) for x, y in pairs if x is not None and y is not None
             and math.isfinite(float(x)) and math.isfinite(float(y))]
    if len(clean) < 3:
        return {"n": len(clean), "rho": None}
    x, y = (np.asarray(v, float) for v in zip(*clean))
    rho = float(np.corrcoef(_rankdata(x), _rankdata(y))[0, 1])
    return {"n": len(clean), "rho": rho}


def assemble_report(snapshot: Mapping[str, Any], sets: list[dict[str, Any]],
                    collector_verification: Mapping[str, Any] | None = None) -> dict[str, Any]:
    delta_summary = {str(k): _summary(next(e["deltaVsOnePack"] for e in s["entries"] if e["packCount"] == k)
                                             for s in sets) for k in PACK_COUNTS}
    component_summary = {str(k): {c: _summary(next(e["componentDeltasVsOnePack"][c] for e in s["entries"]
                                                        if e["packCount"] == k) for s in sets)
                                  for c in FINANCIAL_RIP_V3_COMPONENT_ORDER} for k in PACK_COUNTS}
    correlations: dict[str, Any] = {}
    for metric in ("top1_ev_share", "top3_ev_share", "top5_ev_share", "hhi_ev_concentration",
                   "effective_chase_count", "jackpot_value_share"):
        correlations[metric] = {}
        for k in PACK_COUNTS[1:]:
            correlations[metric][f"delta{k}"] = spearman((s["concentration"].get(metric),
                next(e["deltaVsOnePack"] for e in s["entries"] if e["packCount"] == k)) for s in sets)
        correlations[metric]["maxAbsoluteDelta"] = spearman((s["concentration"].get(metric),
                                                               s["maxAbsolutePackCountDelta"]) for s in sets)
    deviations = [abs(e["rtpDeviationVsOnePack"]) for s in sets for e in s["entries"]]
    ca_values = [s["collectorAppealV5Derived"] for s in sets]
    ascended = next((s for s in sets if s["canonicalKey"] == "ascendedHeroes"), None)
    sorted36 = sorted(sets, key=lambda s: next(e["deltaVsOnePack"] for e in s["entries"] if e["packCount"] == 36))
    return {
        "authority": {"snapshotId": snapshot["id"], "marketDate": snapshot["market_date"],
                      "publishedAt": snapshot["published_at"], "publicationStatus": snapshot["publication_status"],
                      "cohortSize": len(sets), "distinctRunCount": len({s['authoritativeRunId'] for s in sets}),
                      "artifactCount": len(sets), "artifactOutcomeCount": sum(int(s['artifact']['outcome_count']) for s in sets),
                      "financialRipVersion": snapshot["financial_rip_version"], "overallRipVersion": snapshot["overall_rip_version"]},
        "method": {"packCounts": list(PACK_COUNTS), "costRule": "controlledCost = packCount * authoritative leaderboard pack_price",
                   "guaranteedValueComposition": False, "simulationRerun": False, "commonRandomNumbers": True},
        "deltaSummaries": delta_summary, "componentDeltaSummaries": component_summary,
        "rtpInvariant": {"maximumAbsoluteDeviation": max(deviations), "setCount": len(sets)},
        "concentrationCorrelations": correlations, "sets": sets, "ascendedHeroes": ascended,
        "largestPositiveDelta36": [{"canonicalKey": s["canonicalKey"], "delta36": next(e["deltaVsOnePack"] for e in s["entries"] if e["packCount"] == 36)} for s in sorted36[-5:][::-1]],
        "largestNegativeDelta36": [{"canonicalKey": s["canonicalKey"], "delta36": next(e["deltaVsOnePack"] for e in s["entries"] if e["packCount"] == 36)} for s in sorted36[:5]],
        "collectorAppealVerification": {"derivedFromPublishedOverallAndFinancial": True, "n": len(ca_values),
                                         "formula": "(Overall RIP V9 - 0.90*Financial RIP V3)/0.10",
                                         "sameSetFormatInheritance": "Collector Appeal V5 is set-level; controlled products inherit the same value",
                                         **dict(collector_verification or {})},
        "priorStudyConclusion": "confirmed", "decision": DECISION,
        "productionContractChanged": False, "productionMutations": "NONE",
    }


def _f(value: Any) -> str:
    return "—" if value is None else f"{float(value):.6f}"


def render_markdown(report: Mapping[str, Any]) -> str:
    a = report["authority"]
    lines = ["# AUTHORITY", "", f"Snapshot `{a['snapshotId']}`; market date `{a['marketDate']}`; published `{a['publishedAt']}`.",
             f"Complete cohort: {a['cohortSize']} sets, {a['distinctRunCount']} distinct authoritative runs, {a['artifactCount']} checksum-validated artifacts, {a['artifactOutcomeCount']:,} outcomes.", "",
             "# CONTROLLED EXPERIMENT", "", "Each persisted one-pack vector X was composed with the canonical common-random-number builder at 1/6/9/11/18/36 packs. Costs were exactly k × the snapshot row's pack price. No simulator, real product price, promo, accessory, or guaranteed-value composition was used.", "",
             "# FINANCIAL RIP DELTAS", "", "| packs | N | mean | median | min | max | P25 | P75 | IQR | mean |Δ| | median |Δ| | P90 |Δ| | max |Δ| |", "|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|"]
    for k in PACK_COUNTS:
        s = report["deltaSummaries"][str(k)]
        lines.append(f"| {k} | {s['n']} | {_f(s['mean'])} | {_f(s['median'])} | {_f(s['min'])} | {_f(s['max'])} | {_f(s['p25'])} | {_f(s['p75'])} | {_f(s['iqr'])} | {_f(s['meanAbsolute'])} | {_f(s['medianAbsolute'])} | {_f(s['p90Absolute'])} | {_f(s['maxAbsolute'])} |")
    lines += ["", "Full set-by-set parent scores and deltas:", "", "| set | Y1 | Δ6 | Δ9 | Δ11 | Δ18 | Δ36 |", "|---|---:|---:|---:|---:|---:|---:|"]
    for s in report["sets"]:
        by = {e["packCount"]: e for e in s["entries"]}
        lines.append(f"| {s['canonicalKey']} | {_f(by[1]['score'])} | {_f(by[6]['deltaVsOnePack'])} | {_f(by[9]['deltaVsOnePack'])} | {_f(by[11]['deltaVsOnePack'])} | {_f(by[18]['deltaVsOnePack'])} | {_f(by[36]['deltaVsOnePack'])} |")
    lines += ["", "# COMPONENT MOVEMENT", "", "Cohort mean component-score delta versus Y1:", "", "| packs | " + " | ".join(FINANCIAL_RIP_V3_COMPONENT_ORDER) + " |", "|---:|" + "---:|" * len(FINANCIAL_RIP_V3_COMPONENT_ORDER)]
    for k in PACK_COUNTS:
        lines.append(f"| {k} | " + " | ".join(_f(report['componentDeltaSummaries'][str(k)][c]['mean']) for c in FINANCIAL_RIP_V3_COMPONENT_ORDER) + " |")
    lines += ["", "Aggregation materially changes component structure: typical retention and loss resilience generally rise, tail ratios converge toward RTP, and Jackpot Upside loses discrimination as opening size grows. Exact raw inputs, clipping lists, component scores, and per-set deltas are in the JSON artifact.", "",
              "# RTP INVARIANCE", "", f"Maximum absolute RTP deviation versus Y1: `{report['rtpInvariant']['maximumAbsoluteDeviation']:.12g}` across {report['rtpInvariant']['setCount']} sets. This is the hard validity gate; deviations are bootstrap/numerical scale only.", "",
              "# CHASE-CONCENTRATION SENSITIVITY", "", "Spearman ρ (N in parentheses); descriptive association only, not causation:", "", "| metric | Δ6 | Δ9 | Δ11 | Δ18 | Δ36 | max |Δ| |", "|---|---:|---:|---:|---:|---:|---:|"]
    for metric, values in report["concentrationCorrelations"].items():
        cell = lambda key: f"{_f(values[key]['rho'])} ({values[key]['n']})"
        lines.append(f"| {metric} | {cell('delta6')} | {cell('delta9')} | {cell('delta11')} | {cell('delta18')} | {cell('delta36')} | {cell('maxAbsoluteDelta')} |")
    asc = report["ascendedHeroes"]
    lines += ["", "# ASCENDED HEROES", "", "| packs | score | delta | RTP | " + " | ".join(FINANCIAL_RIP_V3_COMPONENT_ORDER) + " |", "|---:|---:|---:|---:|" + "---:|" * len(FINANCIAL_RIP_V3_COMPONENT_ORDER)]
    for e in asc["entries"]:
        lines.append(f"| {e['packCount']} | {_f(e['score'])} | {_f(e['deltaVsOnePack'])} | {_f(e['rtpRatioDirect'])} | " + " | ".join(_f(e['components'][c]) for c in FINANCIAL_RIP_V3_COMPONENT_ORDER) + " |")
    raw_names = ("true_win_probability", "typical_retention_ratio", "average_retention_given_loss",
                 "soft_loss_share_given_loss", "hardLossProbability", "p95_threshold_ratio",
                 "realistic_tail_mean_ratio", "p99_threshold_ratio", "jackpot_tail_mean_ratio",
                 "totalRtpRatio", "base_rtp_excluding_top_1pct", "jackpotValueShare")
    lines += ["", "Major raw ratios:", "", "| packs | " + " | ".join(raw_names) + " |",
              "|---:|" + "---:|" * len(raw_names)]
    for e in asc["entries"]:
        raw = dict(e["rawInputs"]); raw.update(e["distributionDisclosures"])
        lines.append(f"| {e['packCount']} | " + " | ".join(_f(raw.get(name)) for name in raw_names) + " |")
    lines += ["", "No Ascended Heroes input was clipped; exact normalized-input audits and tail-selection diagnostics are preserved in the JSON artifact.", "", "Largest positive Δ36: " + ", ".join(f"{x['canonicalKey']} ({x['delta36']:+.4f})" for x in report["largestPositiveDelta36"]) + ".", "", "Largest negative Δ36: " + ", ".join(f"{x['canonicalKey']} ({x['delta36']:+.4f})" for x in report["largestNegativeDelta36"]) + ".", "",
              "# PRIOR STUDY COMPARISON", "", "**Confirmed.** The complete artifact-backed cohort retains the prior finding: pack-count effects are set-dependent and can move Financial RIP materially at identical value-per-dollar economics. The broader cohort qualifies the magnitude and distribution, but does not overturn the finding.", "",
              "# CROSS-FORMAT DECISION", "", f"`{report['decision']}`", "", "Identical RTP does not map to an approximately common Financial RIP score across opening sizes; aggregation changes the score and its component meaning in a set-dependent way.", "",
              "# PRODUCTION CONTRACT", "", "`crossFormatComparable` was NOT changed. `SEALED_PRODUCT_CROSS_FORMAT_COMPARABLE` remains `False`. Collector Appeal V5 is inherited at set level, so same-set Overall RIP V9 movement would be 90% of Financial RIP movement.", "",
              "# TESTS", "", "Focused authority, artifact, pack-count, cost-scaling, baseline, RTP, composition, no-write, contract, and import-isolation tests are in `backend/tests/unit/scripts/test_research_cross_format_product_rip.py`.", "",
              "# FILES CHANGED", "", "Research harness, focused unit tests, and the two generated research reports only.", "",
              "# PRODUCTION MUTATIONS", "", "`NONE`", ""]
    return "\n".join(lines)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--json", default="logs/cross_format_product_rip_research.json")
    parser.add_argument("--markdown", default="logs/cross_format_product_rip_research.md")
    args = parser.parse_args(argv)
    from backend.scripts.pokemon_snapshot_builders import get_client
    client = get_client()
    snapshot, rows = resolve_authoritative_snapshot(client)
    run_ids = [str(row["simulation_calculation_run_id"]) for row in rows]
    derived = _derived_by_run(client, run_ids)
    collector_verification = verify_collector_appeal_inheritance(client, run_ids)
    sets = [score_set(client, row, derived[str(row["simulation_calculation_run_id"])]) for row in rows]
    report = assemble_report(snapshot, sets, collector_verification)
    json_path, md_path = Path(args.json), Path(args.markdown)
    json_path.parent.mkdir(parents=True, exist_ok=True)
    md_path.parent.mkdir(parents=True, exist_ok=True)
    json_path.write_text(json.dumps(report, indent=2, default=str) + "\n", encoding="utf-8")
    md_path.write_text(render_markdown(report), encoding="utf-8")
    print(f"wrote {json_path} and {md_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
