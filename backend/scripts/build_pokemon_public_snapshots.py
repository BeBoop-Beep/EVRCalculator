from __future__ import annotations

import argparse
import logging
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Build all public Pokemon snapshots in dependency order")
    mode_group = parser.add_mutually_exclusive_group()
    mode_group.add_argument("--dry-run", action="store_true", help="Build/log without writing where supported")
    mode_group.add_argument("--commit", action="store_true", help="Write snapshot rows")
    parser.add_argument("--days", type=int, default=365, help="Market dashboard history days")
    parser.add_argument("--window", default="365d", help="Market dashboard window key")
    return parser


def _run_step(label: str, args: list[str]) -> None:
    logging.info("snapshot step start: %s", label)
    subprocess.run([sys.executable, *args], cwd=REPO_ROOT, check=True)
    logging.info("snapshot step complete: %s", label)


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    args = build_parser().parse_args()
    mode_flag = "--commit" if args.commit else "--dry-run"

    _run_step(
        "explore rankings",
        ["backend/scripts/build_pokemon_explore_rankings_snapshot.py", "--all", mode_flag],
    )
    _run_step(
        "set cards",
        ["backend/scripts/build_pokemon_set_cards_snapshots.py", "--all", mode_flag],
    )
    _run_step(
        "set pages",
        ["backend/scripts/build_pokemon_set_page_snapshots.py", "--all", mode_flag],
    )
    _run_step(
        "market dashboards",
        [
            "backend/scripts/build_pokemon_market_dashboard_snapshots.py",
            "--all",
            mode_flag,
            "--days",
            str(args.days),
            "--window",
            args.window,
        ],
    )
    _run_step(
        "desirability validation",
        ["backend/scripts/build_pokemon_desirability_validation_snapshot.py", mode_flag],
    )


if __name__ == "__main__":
    main()
