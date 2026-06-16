from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path
from typing import Any

from dotenv import load_dotenv

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.append(str(REPO_ROOT))

from backend.desirability.composite import build_composite_report  # noqa: E402
from backend.desirability.repository import PokemonDesirabilityRepository  # noqa: E402


logger = logging.getLogger(__name__)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Build Pokemon Desirability Composite V1 from favoritepokemon fan popularity "
            "and Google Trends current 30-day relative search interest."
        )
    )
    mode_group = parser.add_mutually_exclusive_group()
    mode_group.add_argument("--dry-run", action="store_true", help="Preview without writing composite rows")
    mode_group.add_argument("--commit", action="store_true", help="Write composite rows to Supabase")
    parser.add_argument("--min-coverage", type=float, default=0.95)
    parser.add_argument("--log-level", default="INFO")
    return parser


def main() -> int:
    args = build_parser().parse_args()
    logging.basicConfig(level=getattr(logging, args.log_level.upper(), logging.INFO), format="%(levelname)s %(message)s")
    load_dotenv(REPO_ROOT / "backend" / ".env", override=False)

    dry_run = not args.commit
    if args.dry_run:
        dry_run = True

    try:
        repository = PokemonDesirabilityRepository()
        report = build_composite_report(
            repository=repository,
            dry_run=dry_run,
            min_coverage=args.min_coverage,
        )
    except Exception as exc:
        logger.exception("Pokemon desirability composite build failed gracefully")
        report = {
            "status": "failed_gracefully",
            "dry_run": dry_run,
            "error": f"{type(exc).__name__}: {exc}",
            "measurement_note": (
                "Google Trends component is current 30-day relative search interest, "
                "not absolute search volume or long-term popularity."
            ),
        }

    print(json.dumps(_jsonable(report), indent=2))
    return 0


def _jsonable(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(key): _jsonable(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_jsonable(item) for item in value]
    if isinstance(value, tuple):
        return [_jsonable(item) for item in value]
    if isinstance(value, set):
        return sorted(_jsonable(item) for item in value)
    return value


if __name__ == "__main__":
    raise SystemExit(main())
