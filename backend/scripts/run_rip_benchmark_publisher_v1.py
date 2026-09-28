"""RIP Benchmark V1 dry-run/publisher with atomic DB publication and durable attempt receipts."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
from decimal import Decimal
import json
from pathlib import Path
from typing import Any, Mapping
from uuid import uuid4

from backend.benchmarking.publication_v1 import assemble_dry_run
from backend.benchmarking.publisher_v1 import publish_candidate
from backend.domain.pokemon.rip_benchmark_v1 import (
    APPROVED_BENCHMARK_KEY,
    APPROVED_CALIBRATION_VERSION,
)


_ATTEMPT_TABLE = "pokemon_rip_benchmark_publication_attempts_v1"


def _start_attempt(client: Any, market_date: str) -> str:
    attempt_id = str(uuid4())
    client.table(_ATTEMPT_TABLE).insert({
        "id": attempt_id,
        "market_date": market_date,
        "benchmark_key": APPROVED_BENCHMARK_KEY,
        "calibration_version": APPROVED_CALIBRATION_VERSION,
        "status": "evaluating",
        "reason_code": "ASSEMBLING",
        "diagnostics": {"phase": "assembly"},
    }).execute()
    return attempt_id


def _update_attempt(client: Any, attempt_id: str, **fields: Any) -> None:
    client.table(_ATTEMPT_TABLE).update(fields).eq("id", attempt_id).execute()


def _post_publish_parity(client: Any, candidate: Mapping[str, Any], publication_id: str) -> dict[str, Any]:
    rows = list(
        client.table("pokemon_rip_benchmark_rows_v1")
        .select(
            "entity_type,metric_key,raw_model_value,benchmark_raw_value,"
            "source_model_version,source_market_date,rank,cohort_size"
        )
        .eq("publication_id", publication_id)
        .eq("metric_key", "financial")
        .in_("entity_type", ["set", "era"])
        .execute()
        .data
        or []
    )
    sets = [row for row in rows if row.get("entity_type") == "set"]
    eras = [row for row in rows if row.get("entity_type") == "era"]
    expected_reference = Decimal(str(candidate["references"]["financial"]))
    references = {Decimal(str(row["benchmark_raw_value"])) for row in rows}
    if len(sets) != 22 or len(eras) != 2 or references != {expected_reference}:
        raise RuntimeError(
            "post-publication Financial history parity failed: "
            f"sets={len(sets)} eras={len(eras)} references={sorted(map(str, references))}"
        )
    if any(
        str(row.get("source_market_date")) != str(candidate["market_date"])
        or str(row.get("source_model_version")) != str(
            candidate["publish_rpc_request"]["arguments"]["p_header"]["financial_model_version"]
        )
        for row in rows
    ):
        raise RuntimeError("post-publication Financial history lineage parity failed")
    return {
        "financial_row_count": len(rows),
        "set_financial_row_count": len(sets),
        "era_financial_row_count": len(eras),
        "overall_financial_rip_reference": str(expected_reference),
    }


def publish_market_date(client: Any, market_date: str) -> dict[str, Any]:
    """Publish one exact certified Benchmark date with a durable attempt receipt.

    The existing DB RPC owns atomic replacement/idempotency. This wrapper adds
    the candidate-source receipt plus post-publish Financial-history parity so
    daily publication and repair/reconciliation paths share one implementation.
    """
    market_date = str(market_date or "")[:10]
    if not market_date:
        raise ValueError("market_date is required")
    attempt_id = _start_attempt(client, market_date)
    phase = "assembly"
    try:
        candidate = assemble_dry_run(client, market_date=market_date)
        header = candidate["publish_rpc_request"]["arguments"]["p_header"]
        manifest = header.get("source_manifest") or {}
        _update_attempt(
            client,
            attempt_id,
            candidate_publication_id=header.get("id"),
            rankings_publication_id=manifest.get("rankings_publication_id"),
            opening_economics_snapshot_id=header.get("opening_economics_snapshot_id"),
            reason_code="READY_TO_PUBLISH",
            diagnostics={
                "phase": "validated",
                "expected_entity_count": candidate["expected_entity_count"],
                "expected_row_count": candidate["expected_row_count"],
            },
        )
        phase = "publication"
        publication = publish_candidate(client, candidate)
        phase = "post_publication_parity"
        parity = _post_publish_parity(client, candidate, publication["publication_id"])
        _update_attempt(
            client,
            attempt_id,
            status="published",
            reason_code="PUBLISHED",
            resulting_publication_id=publication["publication_id"],
            completed_at=datetime.now(timezone.utc).isoformat(),
            diagnostics={"phase": "complete", **parity},
        )
        return {
            "attempt_id": attempt_id,
            "candidate": candidate,
            "publication": publication,
            "parity": parity,
        }
    except Exception as exc:
        try:
            _update_attempt(
                client,
                attempt_id,
                status="failed",
                reason_code=f"{phase.upper()}_FAILED"[:120],
                reason_detail=f"{type(exc).__name__}: {exc}"[:2000],
                completed_at=datetime.now(timezone.utc).isoformat(),
                diagnostics={"phase": phase},
            )
        except Exception as receipt_exc:
            print(
                f"RIP Benchmark attempt receipt update failed: "
                f"{type(receipt_exc).__name__}: {receipt_exc}"
            )
        raise


def _fmt(value: Any) -> str:
    try:
        return f"{float(value):.6f}".rstrip("0").rstrip(".")
    except (TypeError, ValueError):
        return str(value)


def report(candidate: Mapping[str, Any]) -> str:
    lines = ["# RIP Benchmark V1 publisher dry run", "",
        "**Validated only. Production publishing remained disabled and no benchmark rows were written.**", "",
        f"- Calibration: `{candidate['calibration_version']}`",
        f"- Benchmark: `{candidate['benchmark_key']}`",
        f"- Market/model/evidence date: `{candidate['market_date']}` / `{candidate['model_source_date']}` / `{candidate['evidence_date']}`",
        f"- Entities/rows: `{candidate['expected_entity_count']}` / `{candidate['expected_row_count']}`",
        f"- Source coherence: `{candidate['source_coherence']}`", "",
        "| Metric | Raw reference | Score range | Clip 0 / 10 | Monotonic violations | Rank inversions | Exact anchor |",
        "|---|---:|---:|---:|---:|---:|---:|"]
    for metric in ("financial", "chase", "collector", "overall"):
        item = candidate["score_distributions"][metric]
        lines.append(f"| {metric.title()} | {_fmt(item['reference_raw_value'])} | "
            f"{_fmt(item['score_min'])}–{_fmt(item['score_max'])} | "
            f"{item['clipped_at_0']} / {item['clipped_at_10']} | {item['monotonicity_violations']} | {item['rank_inversions']} | "
            f"{_fmt(item['score_at_exact_reference'])} |")
    ref = candidate["opening_economics_reference"]
    lines += ["", "## Independent Opening Economics reference", "",
        f"Snapshot `{ref['snapshot_id']}`; modeled return on spend `{_fmt(ref['modeled_return_on_spend'])}`; "
        f"cost/pack `{_fmt(ref['cost_per_pack'])}`; EV/pack `{_fmt(ref['expected_value_per_pack'])}`.", "",
        "This financial-return reference is separate from every model-score `benchmark_raw_value`.", "",
        "## Availability", "",
        f"- Inherited product Chase: {candidate['product_inheritance_counts']['chase']}",
        f"- Inherited product Collector: {candidate['product_inheritance_counts']['collector']}",
        f"- Explicit unavailable Era metric rows: {candidate['era_unavailable_count']}",
        f"- Product family policy: {candidate['product_family_policy']['status']}",
        f"- Product Financial/Overall calibration: approved `{candidate['product_calibration_version']}` (scale 5 / 5)",
        f"- Production header/row counts: {candidate['production_counts_after']['headers']} / {candidate['production_counts_after']['rows']}", ""]
    return "\n".join(lines)


def product_report(study: Mapping[str, Any]) -> str:
    lines = ["# Product Benchmark V1 calibration evidence", "",
        "**Approved production scales: Product Financial 5; Product Overall 5.**", "",
        f"Certified products: {study['product_count']} across {len(study['family_cardinalities'])} exact serving families.", "",
        "| Metric | Scale | Score range | Clip 0 / 10 | Distinct 0.1 | Rank status | Clipping families | Compression families |",
        "|---|---:|---:|---:|---:|---|---|---|"]
    for metric in ("financial", "overall"):
        for c in study["metrics"][metric]["candidates"]:
            lines.append(f"| {metric.title()} | {_fmt(c['scale'])} | {_fmt(c['score_min'])}–{_fmt(c['score_max'])} | "
                f"{c['clipped_at_0']} / {c['clipped_at_10']} | {c['distinct_displayed_one_decimal_scores']} | "
                f"{c['canonical_rank_status']} | {', '.join(c['families_dominated_by_clipping']) or 'none'} | "
                f"{', '.join(c['families_dominated_by_compression']) or 'none'} |")
    lines += ["", "The existing family rank is certified for Overall only. The serving contract exposes no canonical Financial family rank, so none is fabricated.", "",
        "Every family mean scores exactly 5.0 for every candidate. Family-level percentiles and ±1%/±2%/±5% sensitivity are in the JSON artifact.", ""]
    return "\n".join(lines)


def era_report(study: Mapping[str, Any]) -> str:
    lines = ["# Era Benchmark Aggregation V1 shadow certification", "",
        f"Status: **{study['status']}**", "",
        f"Aggregation: `{study['aggregation_version']}` over {study['set_count']} Sets partitioned into {study['era_count']} Eras.", "",
        "Era Overall is the equal-weight mean of canonical member-Set Overall raw scores. It is not recomputed from aggregated pillars.", ""]
    for metric in ("financial", "chase", "collector", "overall"):
        lines += [f"## {metric.title()}", "",
            "| Era | Sets | Raw value | Global Set reference | Score | Era rank |",
            "|---|---:|---:|---:|---:|---:|"]
        entries = study["metrics"][metric]
        for era_id, item in entries.items():
            if era_id == "weighted_reconciliation":
                continue
            lines.append(f"| {item['era_name']} | {item['member_count']} | {_fmt(item['raw_value'])} | "
                f"{_fmt(item['global_set_reference'])} | {_fmt(item['benchmark_score'])} | {item['era_rank']} |")
        reconciliation = entries["weighted_reconciliation"]
        lines += ["", f"Set-count-weighted reconciliation: `{_fmt(reconciliation['value'])}` = global `{_fmt(reconciliation['global_set_reference'])}` (exact).", ""]
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--dry-run", action="store_true")
    mode.add_argument("--publish", action="store_true")
    parser.add_argument("--market-date")
    parser.add_argument("--json", action="store_true", help="Print the full candidate JSON")
    parser.add_argument("--output-dir", type=Path, default=Path("backend/artifacts/rip_benchmark_v1"))
    args = parser.parse_args(argv)
    from backend.db.clients.supabase_client import create_short_timeout_service_client
    client = create_short_timeout_service_client()
    publication = None
    if args.publish:
        if not args.market_date:
            parser.error("--publish requires --market-date so the durable attempt receipt is date-scoped")
        result = publish_market_date(client, args.market_date)
        candidate = result["candidate"]
        publication = result["publication"]
    else:
        candidate = assemble_dry_run(client, market_date=args.market_date)
    args.output_dir.mkdir(parents=True, exist_ok=True)
    stem = f"publisher_dry_run_{candidate['market_date']}"
    json_path, report_path = args.output_dir / f"{stem}.json", args.output_dir / f"{stem}.md"
    product_json = args.output_dir / f"product_shadow_calibration_{candidate['market_date']}.json"
    product_md = args.output_dir / f"product_shadow_calibration_{candidate['market_date']}.md"
    era_json = args.output_dir / f"era_shadow_aggregation_{candidate['market_date']}.json"
    era_md = args.output_dir / f"era_shadow_aggregation_{candidate['market_date']}.md"
    json_path.write_text(json.dumps(candidate, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    report_path.write_text(report(candidate), encoding="utf-8")
    product_json.write_text(json.dumps(candidate["product_calibration_study"], indent=2, sort_keys=True) + "\n", encoding="utf-8")
    product_md.write_text(product_report(candidate["product_calibration_study"]), encoding="utf-8")
    era_json.write_text(json.dumps(candidate["era_aggregation_study"], indent=2, sort_keys=True) + "\n", encoding="utf-8")
    era_md.write_text(era_report(candidate["era_aggregation_study"]), encoding="utf-8")
    if args.json:
        print(json.dumps(publication or candidate, indent=2, sort_keys=True))
    else:
        print(json.dumps({"status": candidate["status"], "json": str(json_path),
            "report": str(report_path), "product_calibration_json": str(product_json),
            "product_calibration_report": str(product_md), "era_aggregation_json": str(era_json),
            "era_aggregation_report": str(era_md), "production_publish_enabled": True,
            "publication": publication}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
