from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from backend.db.services.pokemon_explore_card_movers_service import (
    ExploreCardMoversUnavailable,
    build_global_card_movers_row,
    upsert_explore_card_movers_snapshot,
)
from backend.db.services.publication_gate import add_publication_gate_args, enforce_cli_publication_gate
from backend.desirability.public_analytics_policy import is_public_analytics_eligible
from backend.scripts.pokemon_snapshot_builders import get_client


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(description="Build the fixed 7D global Explore card-movers snapshot")
    mode = result.add_mutually_exclusive_group(required=True)
    mode.add_argument("--dry-run", action="store_true")
    mode.add_argument("--commit", action="store_true")
    add_publication_gate_args(result)
    return result


def build(*, client, market_date: str, commit: bool) -> dict:
    ranking_rows = list(
        client.table("pokemon_explore_rankings_snapshot_latest")
        .select("ranking_payload_json").eq("tcg", "pokemon").eq("scope", "rip-statistics")
        .limit(1).execute().data or []
    )
    ranking_payload = ranking_rows[0].get("ranking_payload_json") if ranking_rows else {}
    sets = [
        row for row in ((ranking_payload or {}).get("targets") or [])
        if is_public_analytics_eligible(row)
    ]
    set_ids = [str(row.get("set_id") or row.get("id")) for row in sets if row.get("set_id") or row.get("id")]
    snapshots = []
    # Dashboard payloads are intentionally large; small bounded batches avoid
    # PostgREST statement timeouts while still preventing per-set fan-out.
    for offset in range(0, len(set_ids), 8):
        page = (client.table("pokemon_set_market_dashboard_snapshot_latest")
                .select("set_id,payload_json,latest_market_date,updated_at")
                .eq("window_key", "365d")
                .in_("set_id", set_ids[offset:offset + 8]).execute())
        snapshots.extend(page.data or [])
    row = build_global_card_movers_row(sets, snapshots, target_market_date=market_date)
    if commit:
        upsert_explore_card_movers_snapshot(row, client=client)
    return row


def main() -> None:
    args = parser().parse_args()
    client = get_client()
    gate = enforce_cli_publication_gate(
        client, commit=bool(args.commit), market_date=args.market_date,
        override=args.force_publish, entry_point="Explore card movers snapshot",
    )
    if not gate.proceed:
        raise SystemExit(gate.exit_code)
    market_date = args.market_date or gate.decision.market_date
    if not market_date:
        raise SystemExit("A promoted --market-date is required")
    try:
        row = build(client=client, market_date=str(market_date)[:10], commit=bool(args.commit))
    except ExploreCardMoversUnavailable as exc:
        print(json.dumps({
            "mode": "commit" if args.commit else "dry-run",
            "status": "blocked",
            "reason": str(exc),
            **exc.diagnostics,
        }, indent=2, sort_keys=True))
        raise SystemExit(1) from exc
    print(json.dumps({
        "mode": "commit" if args.commit else "dry-run",
        "status": "validated",
        **row["_diagnostics"],
        "sourceGenerationFingerprint": row["source_generation_fingerprint"],
    }, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
