"""Bounded scheduled recheck of already-known Pokemon set onboarding identities.

Dry-run makes NO DB mutation and NO Git mutation: it only reads due identities
(list_pokemon_set_onboarding_rechecks_v2) and queries TCGplayer for current
availability, reporting what a commit run would reconcile.
"""

from __future__ import annotations

import argparse
import json
import os
import sys

_PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

from backend.scripts.run_pokemon_set_scrape import _load_backend_env
from backend.services.pokemon_set_onboarding_recheck_service import (
    DEFAULT_RECHECK_INTERVAL_HOURS,
    SOURCE_SYSTEM,
    run_recheck,
)


def main() -> int:
    parser = argparse.ArgumentParser()
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--dry-run", action="store_true")
    mode.add_argument("--commit", action="store_true")
    parser.add_argument("--source-system", default=SOURCE_SYSTEM)
    parser.add_argument("--limit", type=int, default=25, help="Max due identities to check.")
    parser.add_argument(
        "--max-provider-requests", type=int, default=None,
        help="Independent ceiling on outbound provider requests; defaults to 2x --limit.",
    )
    parser.add_argument("--provider-timeout-seconds", type=float, default=10.0)
    parser.add_argument(
        "--recheck-interval-hours", type=float, default=DEFAULT_RECHECK_INTERVAL_HOURS,
        help="Hours until the next scheduled recheck for identities checked this run.",
    )
    parser.add_argument("--as-of", default=None, help="ISO timestamp override for 'now' (testing).")
    args = parser.parse_args()
    _load_backend_env()

    result = run_recheck(
        commit=args.commit, source_system=args.source_system, limit=max(1, args.limit),
        provider_timeout_seconds=max(0.1, args.provider_timeout_seconds),
        recheck_interval_hours=max(0.1, args.recheck_interval_hours),
        max_provider_requests=args.max_provider_requests, as_of=args.as_of,
    )
    print(json.dumps(result, indent=2, default=str))
    return 0 if result.get("status") == "ok" else 2


if __name__ == "__main__":
    raise SystemExit(main())
