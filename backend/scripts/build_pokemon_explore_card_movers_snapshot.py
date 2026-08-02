from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from backend.db.services.pokemon_explore_card_movers_service import (
    build_global_card_movers_row,
    upsert_explore_card_movers_snapshot,
)
from backend.db.services.publication_gate import add_publication_gate_args, enforce_cli_publication_gate
from backend.scripts.pokemon_snapshot_builders import get_client


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(description="Build the fixed 7D global Explore card-movers snapshot")
    mode = result.add_mutually_exclusive_group(required=True)
    mode.add_argument("--dry-run", action="store_true")
    mode.add_argument("--commit", action="store_true")
    add_publication_gate_args(result)
    return result


def build(*, client, market_date: str, commit: bool) -> dict:
    sets = list(client.table("sets").select("id,name,canonical_key,era_id").execute().data or [])
    set_ids = [str(row["id"]) for row in sets]
    snapshots = []
    for offset in range(0, len(set_ids), 200):
        page = (client.table("pokemon_set_market_dashboard_snapshot_latest")
                .select("set_id,payload_json,latest_market_date,updated_at")
                .eq("window_key", "365d")
                .in_("set_id", set_ids[offset:offset + 200]).execute())
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
    row = build(client=client, market_date=str(market_date)[:10], commit=bool(args.commit))
    print(json.dumps({
        "mode": "commit" if args.commit else "dry-run",
        "marketDate": row["market_date"], **row["payload_json"]["meta"]["coverage"],
        "movementContractVersion": row["payload_json"]["meta"]["movementContractVersion"],
        "windowConvention": row["payload_json"]["meta"]["windowConvention"],
        "sourceGenerationFingerprint": row["source_generation_fingerprint"],
    }, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
