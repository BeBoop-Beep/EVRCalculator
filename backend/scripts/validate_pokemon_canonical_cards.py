from __future__ import annotations

import argparse
import json
import os
import re
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

import requests
from dotenv import load_dotenv

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))


API_BASE_URL = "https://api.pokemontcg.io/v2"
CANONICAL_TABLE = "pokemon_canonical_cards"
MATERIAL_COUNT_DIFF = 25
HIGHLIGHT_SET_PATTERNS = (
    re.compile(r"ascend(?:ed|ing)\s+heroes", re.IGNORECASE),
    re.compile(r"perfect\s+order", re.IGNORECASE),
)


class PokemonCanonicalValidationError(RuntimeError):
    pass


def load_backend_env() -> None:
    env_path = Path(__file__).resolve().parents[1] / ".env"
    load_dotenv(env_path, override=False)


def require_env() -> None:
    missing = [
        name
        for name in ("SUPABASE_URL", "SUPABASE_SERVICE_ROLE_KEY", "POKEMON_TCG_API_KEY")
        if not os.getenv(name)
    ]
    if missing:
        raise PokemonCanonicalValidationError(
            "Missing required environment variable(s): " + ", ".join(missing)
        )


def get_supabase_client():
    from backend.db.clients.supabase_client import supabase

    return supabase


def request_api_card_count(api_set_id: str) -> int:
    response = requests.get(
        f"{API_BASE_URL}/cards",
        params={
            "q": f"set.id:{api_set_id}",
            "page": 1,
            "pageSize": 1,
        },
        headers={
            "Accept": "application/json",
            "X-Api-Key": os.environ["POKEMON_TCG_API_KEY"],
            "User-Agent": "EVRCalculator/1.0",
        },
        timeout=30,
    )
    if response.status_code in {401, 403}:
        raise PokemonCanonicalValidationError(
            "Pokemon TCG API rejected the request. Verify POKEMON_TCG_API_KEY."
        )
    if response.status_code == 429:
        retry_after = response.headers.get("Retry-After")
        raise PokemonCanonicalValidationError(
            f"Pokemon TCG API rate limit exceeded. Retry after {retry_after or 'the cooldown window'}."
        )
    response.raise_for_status()
    payload = response.json()
    if not isinstance(payload, dict) or "totalCount" not in payload:
        raise PokemonCanonicalValidationError(
            f"Unexpected Pokemon TCG API count response for set {api_set_id!r}"
        )
    return int(payload["totalCount"])


def count_table_rows(table_name: str, set_id: str) -> int:
    client = get_supabase_client()
    result = (
        client.table(table_name)
        .select("id", count="exact")
        .eq("set_id", set_id)
        .execute()
    )
    count = getattr(result, "count", None)
    if count is not None:
        return int(count)
    return len(result.data or [])


def to_optional_int(value: Any) -> Optional[int]:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def is_highlight_set(set_row: Dict[str, Any]) -> bool:
    haystack = " ".join(
        str(set_row.get(key) or "")
        for key in ("name", "canonical_key", "pokemon_api_set_id")
    )
    return any(pattern.search(haystack) for pattern in HIGHLIGHT_SET_PATTERNS)


def load_sets() -> List[Dict[str, Any]]:
    result = (
        get_supabase_client()
        .table("sets")
        .select("*")
        .not_.is_("pokemon_api_set_id", "null")
        .order("release_date")
        .order("name")
        .execute()
    )
    return list(result.data or [])


def validate_sets(limit: Optional[int] = None) -> Dict[str, Any]:
    rows = load_sets()
    if limit is not None:
        rows = rows[:limit]

    validations: List[Dict[str, Any]] = []
    missing_canonical: List[Dict[str, Any]] = []
    api_count_mismatches: List[Dict[str, Any]] = []
    local_metadata_mismatches: List[Dict[str, Any]] = []
    material_legacy_count_differences: List[Dict[str, Any]] = []
    highlighted_sets: List[Dict[str, Any]] = []

    for set_row in rows:
        set_id = str(set_row.get("id") or "").strip()
        api_set_id = str(set_row.get("pokemon_api_set_id") or "").strip()
        if not set_id or not api_set_id:
            continue

        canonical_count = count_table_rows(CANONICAL_TABLE, set_id)
        legacy_cards_count = count_table_rows("cards", set_id)
        api_card_count = request_api_card_count(api_set_id)

        metadata_counts = {
            "printed_total": to_optional_int(set_row.get("printed_total")),
            "total_cards": to_optional_int(set_row.get("total_cards")),
            "official_card_count": to_optional_int(set_row.get("official_card_count")),
        }

        row = {
            "set_id": set_id,
            "name": set_row.get("name"),
            "canonical_key": set_row.get("canonical_key"),
            "pokemon_api_set_id": api_set_id,
            "canonical_count": canonical_count,
            "api_card_count": api_card_count,
            "legacy_cards_count": legacy_cards_count,
            **metadata_counts,
        }
        validations.append(row)

        if canonical_count <= 0:
            missing_canonical.append(row)
        if canonical_count != api_card_count:
            api_count_mismatches.append(row)
        if any(
            count is not None and count != canonical_count
            for count in metadata_counts.values()
        ):
            local_metadata_mismatches.append(row)
        if abs(legacy_cards_count - canonical_count) >= MATERIAL_COUNT_DIFF:
            material_legacy_count_differences.append(row)
        if is_highlight_set(set_row):
            highlighted_sets.append(row)

    return {
        "summary": {
            "sets_checked": len(validations),
            "sets_missing_canonical_cards": len(missing_canonical),
            "api_count_mismatches": len(api_count_mismatches),
            "local_metadata_mismatches": len(local_metadata_mismatches),
            "material_legacy_count_differences": len(material_legacy_count_differences),
            "highlighted_sets_found": len(highlighted_sets),
        },
        "missing_canonical_cards": missing_canonical,
        "api_count_mismatches": api_count_mismatches,
        "local_metadata_mismatches": local_metadata_mismatches,
        "material_legacy_count_differences": material_legacy_count_differences,
        "highlighted_sets": highlighted_sets,
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Validate Pokemon canonical checklist-card ingestion"
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Optional number of sets to validate from the ordered set list",
    )
    return parser


def main() -> int:
    args = build_parser().parse_args()
    load_backend_env()
    require_env()
    report = validate_sets(limit=args.limit)
    print(json.dumps(report, indent=2, sort_keys=True))
    failures = (
        report["summary"]["sets_missing_canonical_cards"]
        + report["summary"]["api_count_mismatches"]
    )
    return 1 if failures else 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except PokemonCanonicalValidationError as exc:
        print(f"[canonical-validate][ERROR] {exc}", file=sys.stderr)
        raise SystemExit(1)
