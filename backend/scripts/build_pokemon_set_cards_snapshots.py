from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from backend.scripts.pokemon_snapshot_builders import (
    add_target_set_args,
    build_cards_snapshot_row,
    get_client,
    resolve_target_sets,
    should_commit,
    upsert_row,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Build Pokemon set cards checklist snapshots")
    add_target_set_args(parser)
    return parser


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    args = build_parser().parse_args()
    client = get_client()
    commit = should_commit(args)

    for set_row in resolve_target_sets(client, args):
        logging.info("building cards snapshot set_id=%s name=%s", set_row.get("id"), set_row.get("name"))
        row = build_cards_snapshot_row(set_row)
        upsert_row(
            client,
            "pokemon_set_cards_snapshot_latest",
            row,
            on_conflict="set_id",
            commit=commit,
        )


if __name__ == "__main__":
    main()
