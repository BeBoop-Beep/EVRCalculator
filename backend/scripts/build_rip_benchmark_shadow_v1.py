"""Build the source-certified Benchmark V1 shadow report.  Read-only by design."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from backend.benchmarking.shadow_v1 import calibration_analysis, certify_set_cohort
from backend.db.services.rip_release import bundle_for_model
from backend.domain.pokemon.rip_benchmark_v1 import BenchmarkError


def _one(query: Any, label: str) -> dict[str, Any]:
    rows = list(query.limit(2).execute().data or [])
    if len(rows) != 1:
        raise BenchmarkError(f"missing or ambiguous {label}")
    return dict(rows[0])


def _pointer(client: Any) -> dict[str, Any]:
    return _one(client.table("pokemon_overall_rip_current_publication")
                .select("publication_run_id,rankings_generation_id,set_page_generation_id")
                .eq("scope", "pokemon"), "active release pointer")


def build(client: Any) -> dict[str, Any]:
    before = _pointer(client)
    release = _one(client.table("pokemon_overall_rip_publication_runs")
        .select("id,model_version,status,market_date,financial_version,chase_version,collector_version,collector_run_id")
        .eq("id", before["publication_run_id"]), "active release")
    if release.get("status") != "published":
        raise BenchmarkError("active release is not published")
    bundle = bundle_for_model(release["model_version"])
    rankings = _one(client.table("pokemon_explore_rankings_snapshot_latest")
        .select("ranking_payload_json,updated_at").eq("tcg", "pokemon").eq("scope", "rip-statistics"),
        "Rankings snapshot")
    cohort = certify_set_cohort(rankings, {**release, "overall_version": release["model_version"],
        "score_source_policy": bundle.overall_source})
    opening_latest = _one(client.table("pokemon_rip_stats_snapshot_latest")
        .select("market_date,source_run_fingerprint").eq("tcg", "pokemon").eq("scope", "rip-stats"),
        "latest Opening Economics pointer")
    opening = _one(client.table("pokemon_rip_stats_snapshots")
        .select("id,market_date,contract_version,methodology_version,weighting_version,cohort_fingerprint,source_run_fingerprint,payload_json,published_at")
        .eq("publication_status", "published").eq("market_date", opening_latest["market_date"])
        .eq("source_run_fingerprint", opening_latest["source_run_fingerprint"]), "latest Opening Economics V3")
    economics = (opening.get("payload_json") or {}).get("openingEconomics") or {}
    method = economics.get("methodology") or {}
    if (economics.get("status") != "available" or economics.get("marketDate") != opening.get("market_date")
            or economics.get("contractVersion") != "pokemon-rip-stats-v3"
            or economics.get("basis") != "all_modeled_products_per_pack_equivalent"
            or method.get("version") != "hierarchical_product_per_pack_empirical_v1"
            or method.get("weightingVersion") != "equal-set_equal-family_equal-sku-v1"):
        raise BenchmarkError("latest Opening Economics source is not the exact V3 contract")
    after = _pointer(client)
    rankings_after = _one(client.table("pokemon_explore_rankings_snapshot_latest")
        .select("updated_at").eq("tcg", "pokemon").eq("scope", "rip-statistics"), "Rankings recheck")
    if before != after or rankings.get("updated_at") != rankings_after.get("updated_at"):
        raise BenchmarkError("source pointer changed during shadow assembly")
    analysis = calibration_analysis(cohort.rows)
    return {
        "artifact_version": "rip_benchmark_shadow_calibration_v1",
        "status": "source_certified_shadow_not_approved",
        "production_publish_enabled": False,
        "active_release": {**release, "score_source_policy": bundle.overall_source,
                           "pointer": before},
        "set_cohort": {"entity_count": 22, "row_count": len(cohort.rows),
                       "source_market_date": cohort.market_date,
                       "rankings_publication_id": cohort.publication_id,
                       "source_fingerprint": cohort.source_fingerprint,
                       "rows": list(cohort.rows)},
        "opening_economics_v3": {
            "snapshot_id": opening["id"], "market_date": opening["market_date"],
            "contract_version": economics["contractVersion"], "basis": economics["basis"],
            "methodology": method, "source_run_fingerprint": opening["source_run_fingerprint"],
            "global": economics.get("global"), "sets": economics.get("sets"), "eras": economics.get("eras"),
        },
        "era_model_contract": {"status": "unavailable_era_model_contract",
                               "opening_economics_evidence_available": True},
        "calibration": analysis,
        "decision": {"approved": False, "selected_scale": None,
                     "required_next_step": "human review and explicit calibration approval"},
    }


def markdown(artifact: dict[str, Any]) -> str:
    def fmt(value: Any) -> str:
        try:
            return f"{float(value):.4f}".rstrip("0").rstrip(".")
        except (TypeError, ValueError):
            return str(value)
    lines = ["# RIP Benchmark V1 shadow calibration", "",
        "**Decision: no calibration is approved or selected. No benchmark rows were published.**", "",
        f"Canonical model cohort: 22 sets / {artifact['set_cohort']['row_count']} metric observations, "
        f"source date `{artifact['set_cohort']['source_market_date']}`.", "",
        f"Opening Economics V3 evidence is independently dated `{artifact['opening_economics_v3']['market_date']}`; "
        "it does not forward-fill the model scores.", "",
        "Era model pillars are `unavailable_era_model_contract`; era financial evidence remains independently available.", ""]
    for metric, data in artifact["calibration"]["metrics"].items():
        lines += [f"## {metric.title()}", "",
            f"Raw mean/reference `{fmt(data['raw_mean'])}`; median `{fmt(data['raw_median'])}`; "
            f"range `{fmt(data['raw_min'])}`–`{fmt(data['raw_max'])}`; P10/P25/P75/P90 "
            f"`{fmt(data['raw_p10'])}` / `{fmt(data['raw_p25'])}` / `{fmt(data['raw_p75'])}` / `{fmt(data['raw_p90'])}`.", "",
            "| Scale | Score range | Clip 0 / 10 | Distinct 0.1 | Monotonic violations | Rank inversions | ±1% scores | ±2% scores | ±5% scores |",
            "|---:|---:|---:|---:|---:|---:|---:|---:|---:|"]
        for c in data["candidates"]:
            s = c["sensitivity_at_benchmark"]
            lines.append(f"| {fmt(c['scale'])} | {fmt(c['score_min'])}–{fmt(c['score_max'])} | "
                f"{fmt(c['percent_clipped_at_0'])}% / {fmt(c['percent_clipped_at_10'])}% | "
                f"{c['distinct_displayed_one_decimal_scores']} | {c['monotonicity_violations']} | "
                f"{c['rank_inversions']} | {fmt(s['minus_1pct'])} / {fmt(s['plus_1pct'])} | "
                f"{fmt(s['minus_2pct'])} / {fmt(s['plus_2pct'])} | {fmt(s['minus_5pct'])} / {fmt(s['plus_5pct'])} |")
        lines += ["", "Every candidate anchors the exact benchmark at `5.0`.", ""]
    lines += ["## Candidate consequences", "", artifact["calibration"]["consequences"], "",
        "These are options for review, not a silent production selection.", ""]
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path,
                        default=Path("backend/artifacts/rip_benchmark_v1"))
    args = parser.parse_args(argv)
    from backend.db.clients.supabase_client import create_short_timeout_service_client
    artifact = build(create_short_timeout_service_client())
    args.output_dir.mkdir(parents=True, exist_ok=True)
    stem = f"shadow_calibration_{artifact['set_cohort']['source_market_date']}"
    json_path, md_path = args.output_dir / f"{stem}.json", args.output_dir / f"{stem}.md"
    json_path.write_text(json.dumps(artifact, indent=2, sort_keys=True, default=str) + "\n", encoding="utf-8")
    md_path.write_text(markdown(artifact), encoding="utf-8")
    print(json.dumps({"status": artifact["status"], "json": str(json_path), "report": str(md_path),
                      "production_publish_enabled": False}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
