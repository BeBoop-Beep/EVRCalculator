from __future__ import annotations

import argparse
import logging
import sys
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
    get_client,
    should_commit,
)
from backend.scripts.pokemon_explore_rankings_publisher import (
    previous_calendar_day_payload as _previous_calendar_day_payload,
    publication_contract as _publication_contract,
    publish_explore_rip_rankings_snapshot,
)


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

    publish_explore_rip_rankings_snapshot(
        client, limit=args.limit, market_date=args.market_date, commit=commit
    )


if __name__ == "__main__":
    main()
