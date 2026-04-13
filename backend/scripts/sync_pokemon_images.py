import argparse
import json
import os
import sys
from dotenv import load_dotenv

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..')))


DEFAULT_SETS = ["Prismatic Evolutions", "Scarlet and Violet 151"]

REQUIRED_ENV_VARS = [
    "SUPABASE_URL",
    "SUPABASE_SERVICE_ROLE_KEY",
    "POKEMON_TCG_API_KEY",
]


def load_backend_env() -> None:
    env_path = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '.env'))
    load_dotenv(env_path, override=True)

    key = os.getenv("POKEMON_TCG_API_KEY")
    print("SCRIPT FILE:", __file__)
    print("ENV PATH:", env_path)
    print("KEY LOADED:", bool(key), "len=", len(key) if key else 0, "start=", repr(key[:4]) if key else None, "end=", repr(key[-4:]) if key else None)


def validate_required_env() -> None:
    missing = [var for var in REQUIRED_ENV_VARS if not os.getenv(var)]
    if missing:
        raise RuntimeError(
            "Missing required environment variable(s): "
            + ", ".join(missing)
        )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Sync Pokemon TCG image URLs into card_variants")
    parser.add_argument(
        "--sets",
        nargs="+",
        default=DEFAULT_SETS,
        help="Exact internal set names to sync",
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Write updates to the database. Omit this flag to run in dry-run mode.",
    )
    return parser


def main() -> int:
    args = build_parser().parse_args()
    dry_run = not args.apply

    load_backend_env()
    validate_required_env()

    from backend.db.services.pokemon_tcg_image_sync_service import PokemonTCGImageSyncService

    service = PokemonTCGImageSyncService()
    exit_code = 0

    for set_name in args.sets:
        print(f"[SYNC] Starting image sync for {set_name} (dry_run={dry_run})")
        try:
            result = service.sync_set(set_name=set_name, dry_run=dry_run)
            print(json.dumps(result, indent=2))
        except Exception as exc:
            exit_code = 1
            print(f"[ERROR] Failed to sync {set_name}: {exc}")

    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
