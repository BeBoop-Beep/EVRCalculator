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


def _run_step(label: str, args: list[str]) -> bool:
    """Run one snapshot step. Returns whether it succeeded; never raises.

    The steps are ordered but NOT dependent: Explore rankings reads the RIP
    statistics view and the desirability component rows, and set pages read their
    own sources. None of them read the market dashboard. Aborting the pipeline on
    the first non-zero exit therefore let one older set's market dashboard failure
    withhold the rankings and set-page snapshots entirely - which is what happened:
    the run died at rankings and set pages never executed at all.

    So each step runs regardless, and the pipeline reports a non-zero exit at the
    end. Failing loudly and failing early are different things; only the first is
    wanted here.
    """
    logging.info("snapshot step start: %s", label)
    result = subprocess.run([sys.executable, *args], cwd=REPO_ROOT)
    if result.returncode != 0:
        logging.error(
            "snapshot step FAILED: %s (exit=%s). Continuing with the remaining steps; "
            "this step's snapshot is unchanged.",
            label, result.returncode,
        )
        return False
    logging.info("snapshot step complete: %s", label)
    return True


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    args = build_parser().parse_args()
    mode_flag = "--commit" if args.commit else "--dry-run"

    steps: list[tuple[str, list[str]]] = [
        (
            "coordinated set cards and market dashboards",
            [
                "backend/scripts/build_pokemon_set_market_snapshots.py",
                "--all",
                mode_flag,
                "--days",
                str(args.days),
                "--window",
                args.window,
            ],
        ),
        (
            "explore rankings",
            ["backend/scripts/build_pokemon_explore_rankings_snapshot.py", "--all", mode_flag],
        ),
        (
            "set pages",
            ["backend/scripts/build_pokemon_set_page_snapshots.py", "--all", mode_flag],
        ),
    ]

    failed = [label for label, step_args in steps if not _run_step(label, step_args)]
    if failed:
        logging.error("snapshot pipeline finished with %s failed step(s): %s", len(failed), ", ".join(failed))
        raise SystemExit(1)
    logging.info("snapshot pipeline finished: all %s steps succeeded", len(steps))
    # The "desirability validation" step is retired: it patched the legacy
    # rank-alignment evidence payload into set-page snapshots, and that public
    # section was replaced by Opening Experience (Collector Appeal). The script
    # remains in backend/scripts for research use; it is just no longer part of
    # the production snapshot pipeline.


if __name__ == "__main__":
    main()
