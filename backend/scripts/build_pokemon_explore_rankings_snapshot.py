from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from backend.scripts.pokemon_snapshot_builders import (
    DEFAULT_RANKINGS_LIMIT,
    build_explore_rankings_snapshot_row,
    get_client,
    should_commit,
    upsert_row,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Build Pokemon Explore rankings snapshot")
    parser.add_argument("--all", action="store_true", help="Build the Pokemon RIP Statistics rankings snapshot")
    parser.add_argument("--set-id", help="Accepted for scheduler interface parity; ignored for global rankings")
    mode_group = parser.add_mutually_exclusive_group()
    mode_group.add_argument("--dry-run", action="store_true", help="Build and log without writing")
    mode_group.add_argument("--commit", action="store_true", help="Upsert snapshot row")
    parser.add_argument("--limit", type=int, default=DEFAULT_RANKINGS_LIMIT)
    return parser


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    args = build_parser().parse_args()
    if not args.all and not args.set_id:
        raise SystemExit("One of --all or --set-id is required")
    client = get_client()
    row = build_explore_rankings_snapshot_row(limit=args.limit)
    upsert_row(
        client,
        "pokemon_explore_rankings_snapshot_latest",
        row,
        on_conflict="tcg,scope",
        commit=should_commit(args),
    )


if __name__ == "__main__":
    main()
