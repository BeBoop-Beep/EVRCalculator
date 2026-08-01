from __future__ import annotations

import argparse
import hashlib
import logging
import sys
from datetime import date, timedelta
from uuid import uuid4
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from backend.db.services.publication_gate import (
    add_publication_gate_args,
    enforce_cli_publication_gate,
)
from backend.scripts.pokemon_snapshot_builders import (
    DEFAULT_RANKINGS_LIMIT,
    build_explore_rankings_snapshot_row,
    attach_daily_rip_rank_movements,
    get_client,
    should_commit,
    upsert_row,
)


def _publication_contract(row):
    payload = row["ranking_payload_json"]
    meta = payload.get("meta") or {}
    cohort = meta.get("publicAnalyticsCohort") or {}
    versions = meta.get("ripWeightsConfig") or {}
    market_date = str((meta.get("comparisonSnapshots") or {}).get("currentMarketDate") or "")[:10]
    ranked_count = int((cohort.get("overallRanked") or {}).get("rankedSetCount") or 0)
    targets = [
        target for target in payload.get("targets") or []
        if (target.get("rip") or {}).get("rank") is not None
    ]
    ca7_versions = sorted({
        str((((target.get("openingExperience") or {}).get("collectorAppeal") or {}).get("version")))
        for target in targets
        if (((target.get("openingExperience") or {}).get("collectorAppeal") or {}).get("version"))
    })
    problems = []
    if not market_date:
        problems.append("missing market date")
    if ranked_count <= 0 or len(targets) != ranked_count:
        problems.append(f"incomplete Overall RIP cohort expected={ranked_count} actual={len(targets)}")
    if len(ca7_versions) != 1:
        problems.append(f"incompatible CA7 versions={ca7_versions}")
    if any((target.get("ripCore") or {}).get("rank") is None for target in targets):
        problems.append("missing Financial RIP rank")
    if problems:
        raise RuntimeError("Refusing to publish Explore RIP leaderboard: " + "; ".join(problems))
    ids = sorted(str(target.get("set_id") or target.get("target_id")) for target in targets)
    snapshot = {
        "id": str(uuid4()),
        "market_date": market_date,
        "built_at": (meta.get("snapshot") or {}).get("builtAt"),
        "eligible_cohort_count": ranked_count,
        "cohort_version": cohort.get("version"),
        "cohort_fingerprint": hashlib.sha256("\n".join(ids).encode()).hexdigest(),
        "overall_rip_version": (versions.get("overallRip") or {}).get("version"),
        "financial_rip_version": (versions.get("financialRip") or {}).get("version"),
        "ca7_version": ca7_versions[0],
        "diagnostics": {"set_ids": ids},
    }
    history_rows = [{
        "set_id": target.get("set_id") or target.get("target_id"),
        "set_canonical_key": target.get("canonical_key") or target.get("slug"),
        "overall_rip_score": (target.get("rip") or {}).get("score"),
        "overall_rip_rank": (target.get("rip") or {}).get("rank"),
        "financial_rip_score": (target.get("ripCore") or {}).get("score"),
        "financial_rip_rank": (target.get("ripCore") or {}).get("rank"),
        "overall_ranked_cohort_count": ranked_count,
        "financial_ranked_cohort_count": cohort.get("eligibleSetCount"),
        "simulation_calculation_run_id": target.get("calculation_run_id"),
        "source_market_date": market_date,
        "pack_price": target.get("pack_cost"),
    } for target in targets]
    return snapshot, history_rows


def _previous_calendar_day_payload(client, market_date):
    previous_date = (date.fromisoformat(market_date) - timedelta(days=1)).isoformat()
    result = (
        client.table("pokemon_public_rip_leaderboard_snapshots")
        .select("payload_json")
        .eq("market_date", previous_date)
        .eq("publication_status", "complete")
        .limit(1)
        .execute()
    )
    rows = list(result.data or [])
    return rows[0].get("payload_json") if rows else None


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Build Pokemon Explore rankings snapshot")
    parser.add_argument("--all", action="store_true", help="Build the Pokemon RIP Statistics rankings snapshot")
    parser.add_argument("--set-id", help="Accepted for scheduler interface parity; ignored for global rankings")
    mode_group = parser.add_mutually_exclusive_group()
    mode_group.add_argument("--dry-run", action="store_true", help="Build and log without writing")
    mode_group.add_argument("--commit", action="store_true", help="Upsert snapshot row")
    parser.add_argument("--limit", type=int, default=DEFAULT_RANKINGS_LIMIT)
    add_publication_gate_args(parser)
    return parser


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    args = build_parser().parse_args()
    client = get_client()
    commit = should_commit(args)

    # Batch-cohort gate: evaluated once per invocation. A closed gate in --commit
    # mode defers with the dedicated exit code and writes nothing.
    gate = enforce_cli_publication_gate(
        client,
        commit=commit,
        market_date=args.market_date,
        override=args.force_publish,
        entry_point="explore rankings snapshot",
    )
    if not gate.proceed:
        raise SystemExit(gate.exit_code)

    row = build_explore_rankings_snapshot_row(limit=args.limit)
    snapshot, history_rows = _publication_contract(row)
    previous_payload = _previous_calendar_day_payload(client, snapshot["market_date"])
    row["ranking_payload_json"] = attach_daily_rip_rank_movements(
        row["ranking_payload_json"], previous_payload
    )
    row["ranking_payload_json"].setdefault("meta", {}).setdefault("snapshot", {}).update({
        "publicationId": snapshot["id"],
        "marketDate": snapshot["market_date"],
    })
    if not commit:
        logging.info("[dry-run] validated complete RIP publication market_date=%s rows=%s",
                     snapshot["market_date"], len(history_rows))
        return
    client.rpc("publish_pokemon_public_rip_leaderboard", {
        "p_snapshot": snapshot,
        "p_rows": history_rows,
        "p_latest": row,
    }).execute()


if __name__ == "__main__":
    main()
