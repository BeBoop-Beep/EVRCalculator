from __future__ import annotations

import argparse
import logging
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from backend.db.services.publication_gate import (
    GATE_DEFERRED_EXIT_CODE,
    add_publication_gate_args,
    enforce_cli_publication_gate,
)
from backend.scripts.pokemon_snapshot_builders import get_client


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Build all public Pokemon snapshots in dependency order")
    mode_group = parser.add_mutually_exclusive_group()
    mode_group.add_argument("--dry-run", action="store_true", help="Build/log without writing where supported")
    mode_group.add_argument("--commit", action="store_true", help="Write snapshot rows")
    parser.add_argument("--days", type=int, default=365, help="Market dashboard history days")
    parser.add_argument("--window", default="365d", help="Market dashboard window key")
    add_publication_gate_args(parser)
    return parser


def _run_step(label: str, args: list[str]) -> int:
    """Run one snapshot step. Returns its process exit code; never raises.

    The steps are ordered but NOT dependent: Explore rankings reads the RIP
    statistics view and the desirability component rows, and set pages read their
    own sources. None of them read the market dashboard. Aborting the pipeline on
    the first non-zero exit therefore let one older set's market dashboard failure
    withhold the rankings and set-page snapshots entirely - which is what happened:
    the run died at rankings and set pages never executed at all.

    So each step runs regardless, and the pipeline reports a non-zero exit at the
    end. Failing loudly and failing early are different things; only the first is
    wanted here. A child that DEFERS on a closed gate (exit 3) is reported
    distinctly from a genuine build failure.
    """
    logging.info("snapshot step start: %s", label)
    result = subprocess.run([sys.executable, *args], cwd=REPO_ROOT)
    if result.returncode == GATE_DEFERRED_EXIT_CODE:
        logging.warning("snapshot step DEFERRED by publication gate: %s (exit=3)", label)
    elif result.returncode != 0:
        logging.error(
            "snapshot step FAILED: %s (exit=%s). Continuing with the remaining steps; "
            "this step's snapshot is unchanged.",
            label, result.returncode,
        )
    else:
        logging.info("snapshot step complete: %s", label)
    return result.returncode


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    args = build_parser().parse_args()
    commit = bool(args.commit)
    mode_flag = "--commit" if commit else "--dry-run"

    # Batch-cohort gate: evaluate ONCE for the whole publication invocation. A
    # closed gate in --commit mode defers the entire build (dedicated exit code,
    # no children spawned, nothing written). Dry-run reports the decision and
    # continues read-only.
    gate = enforce_cli_publication_gate(
        get_client(),
        commit=commit,
        market_date=args.market_date,
        override=args.force_publish,
        entry_point="full public snapshot build",
    )
    if not gate.proceed:
        raise SystemExit(gate.exit_code)

    # Forward the gate context so a directly-invoked child stays consistent
    # (e.g. a manual override propagates to every step).
    gate_forward: list[str] = []
    if args.market_date:
        gate_forward += ["--market-date", args.market_date]
    if args.force_publish:
        gate_forward.append("--force-publish")

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
                *gate_forward,
            ],
        ),
        (
            "explore rankings",
            ["backend/scripts/build_pokemon_explore_rankings_snapshot.py", "--all", mode_flag, *gate_forward],
        ),
        (
            "set pages",
            ["backend/scripts/build_pokemon_set_page_snapshots.py", "--all", mode_flag, *gate_forward],
        ),
    ]

    results = [(label, _run_step(label, step_args)) for label, step_args in steps]
    deferred = [label for label, code in results if code == GATE_DEFERRED_EXIT_CODE]
    failed = [label for label, code in results if code not in (0, GATE_DEFERRED_EXIT_CODE)]
    if deferred:
        logging.warning(
            "snapshot pipeline DEFERRED by publication gate on %s step(s): %s",
            len(deferred), ", ".join(deferred),
        )
        raise SystemExit(GATE_DEFERRED_EXIT_CODE)
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
