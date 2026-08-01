"""Detect provider sets without registering them as public application sets."""

from __future__ import annotations

import argparse
import json
import os
import sys

_PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

from backend.scripts.run_pokemon_set_scrape import _load_backend_env
from backend.services.pokemon_new_set_discovery_service import discover_new_sets


def main() -> int:
    parser = argparse.ArgumentParser()
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--dry-run", action="store_true")
    mode.add_argument("--commit", action="store_true")
    parser.add_argument("--json", action="store_true", help="Emit machine-readable JSON only.")
    parser.add_argument("--min-confidence", type=float, default=0.90)
    parser.add_argument("--max-new", type=int, default=12)
    parser.add_argument("--provider-timeout-seconds", type=float, default=10.0)
    args = parser.parse_args()
    _load_backend_env()
    result = discover_new_sets(
        commit=args.commit, min_confidence=args.min_confidence, max_new=max(1, args.max_new),
        provider_timeout_seconds=max(0.1, args.provider_timeout_seconds),
    )
    print(json.dumps(result, indent=2, default=str))
    return 0 if result.get("status") == "ok" else 2


if __name__ == "__main__":
    raise SystemExit(main())
