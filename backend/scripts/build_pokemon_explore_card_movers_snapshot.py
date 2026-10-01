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
    build_global_mixed_movers_row,
    read_mixed_market_movers_authority,
    upsert_explore_card_movers_snapshot,
)
from backend.db.services.publication_gate import add_publication_gate_args, enforce_cli_publication_gate
from backend.scripts.pokemon_snapshot_builders import get_client


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(
        description="Build the fixed 7D mixed card + sealed Market movers snapshot"
    )
    mode = result.add_mutually_exclusive_group(required=True)
    mode.add_argument("--dry-run", action="store_true")
    mode.add_argument("--commit", action="store_true")
    add_publication_gate_args(result)
    return result


def build(*, client, market_date: str, commit: bool) -> dict:
    authority = read_mixed_market_movers_authority(
        market_date=market_date,
        client=client,
    )
    row = build_global_mixed_movers_row(
        authority,
        target_market_date=market_date,
    )
    if commit:
        upsert_explore_card_movers_snapshot(row, client=client)
    return row


def main() -> None:
    args = parser().parse_args()
    client = get_client()
    gate = enforce_cli_publication_gate(
        client,
        commit=bool(args.commit),
        market_date=args.market_date,
        override=args.force_publish,
        entry_point="Explore mixed Market movers snapshot",
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
