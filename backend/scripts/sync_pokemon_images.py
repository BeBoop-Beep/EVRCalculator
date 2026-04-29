import argparse
import json
import os
import sys
from typing import List, Optional
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
        default=None,
        help="Exact internal set names to sync",
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Write updates to the database. Omit this flag to run in dry-run mode.",
    )
    return parser


def get_target_sets(explicit_sets: Optional[List[str]]) -> List[str]:
    if explicit_sets:
        return explicit_sets

    try:
        from backend.db.clients.supabase_client import supabase

        response = (
            supabase.table("sets")
            .select("name,release_date,pokemon_api_set_id")
            .not_.is_("pokemon_api_set_id", "null")
            .execute()
        )
        rows = response.data if response and response.data else []

        candidate_sets = [
            row
            for row in rows
            if row.get("name") and str(row.get("pokemon_api_set_id") or "").strip()
        ]

        if not candidate_sets:
            print("[WARN] Dynamic set lookup returned no sets with pokemon_api_set_id; falling back to DEFAULT_SETS")
            return DEFAULT_SETS

        candidate_sets.sort(
            key=lambda row: (
                row.get("release_date") is None,
                str(row.get("release_date") or ""),
                str(row.get("name") or "").casefold(),
            )
        )

        resolved_names = [str(row.get("name")).strip() for row in candidate_sets if str(row.get("name")).strip()]
        if not resolved_names:
            print("[WARN] Dynamic set lookup returned only empty set names; falling back to DEFAULT_SETS")
            return DEFAULT_SETS

        return resolved_names
    except Exception as exc:
        print(f"[WARN] Failed dynamic set lookup ({exc}); falling back to DEFAULT_SETS")
        return DEFAULT_SETS


def main() -> int:
    args = build_parser().parse_args()
    dry_run = not args.apply

    load_backend_env()
    validate_required_env()

    target_sets = get_target_sets(args.sets)
    print(f"[SYNC] Resolved {len(target_sets)} target set(s)")

    from backend.db.services.pokemon_tcg_image_sync_service import PokemonTCGImageSyncService

    service = PokemonTCGImageSyncService()
    exit_code = 0

    for set_name in target_sets:
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
