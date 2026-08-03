"""Audit this runtime's set-key registry against the database daily cohort.

Run this ON THE SCRAPER VM after every deployment, and before synchronizing set
metadata into the database. It answers, for the process that will actually run
the scrape: can this runtime resolve every canonical key the database expects?

Exit codes:
    0  registry and cohort agree
    1  at least one mismatch, or the authority could not be read

Usage:
    python backend/scripts/audit_pokemon_scrape_runtime.py
    python backend/scripts/audit_pokemon_scrape_runtime.py --json
"""

from __future__ import annotations

import argparse
import logging
import os
import sys

_PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

from backend.db.services.pokemon_scrape_runtime_preflight import (
    format_preflight_json,
    run_runtime_preflight,
)
from backend.scripts.run_pokemon_set_scrape import _load_backend_env

logging.basicConfig(level=logging.INFO, format="%(message)s")
logger = logging.getLogger(__name__)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--json",
        dest="as_json",
        action="store_true",
        help="Emit the structured report as JSON on stdout.",
    )
    args = parser.parse_args()

    _load_backend_env()
    report = run_runtime_preflight()

    if args.as_json:
        print(format_preflight_json(report))
    else:
        for line in report.report_lines():
            logger.info("%s", line)

    return 0 if report.ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
