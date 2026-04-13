import argparse
import json
import os
import sys
from pathlib import Path

from dotenv import load_dotenv

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))


DEFAULT_REPORT_PATH = Path("backend/constants/tcg/pokemon/pokemon_era_set_sync_report.json")


def load_backend_env() -> None:
    env_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".env"))
    load_dotenv(env_path, override=False)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Sync Pokemon era/set metadata from constants into the database")
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Write inserts and updates to the database. Omit to run in dry-run mode.",
    )
    parser.add_argument(
        "--report-path",
        default=str(DEFAULT_REPORT_PATH),
        help="Path to write the JSON sync report.",
    )
    return parser


def main() -> int:
    args = build_parser().parse_args()
    load_backend_env()

    from backend.db.services.pokemon_era_set_sync_service import sync_pokemon_era_and_set_metadata

    report = sync_pokemon_era_and_set_metadata(
        apply_changes=bool(args.apply),
        report_path=Path(args.report_path),
    )
    print(json.dumps(report["summary"], indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())