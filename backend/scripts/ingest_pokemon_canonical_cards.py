from __future__ import annotations

import argparse
import json
import os
import sys
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Set

import requests
from dotenv import load_dotenv

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))


API_BASE_URL = "https://api.pokemontcg.io/v2"
API_PAGE_SIZE = 250
UPSERT_BATCH_SIZE = 100
REQUEST_DELAY_SECONDS = 0.1
API_MAX_RETRIES = 3
API_BACKOFF_SECONDS = 2.0
CANONICAL_TABLE = "pokemon_canonical_cards"
SET_SELECT = "*"


class PokemonCanonicalIngestionError(RuntimeError):
    pass


@dataclass
class SetIngestSummary:
    local_set_id: str
    local_set_name: str
    canonical_key: Optional[str]
    pokemon_api_set_id: Optional[str]
    api_returned_card_count: int = 0
    rows_inserted: int = 0
    rows_updated: int = 0
    rows_skipped: int = 0
    local_printed_total: Optional[int] = None
    local_total_cards: Optional[int] = None
    local_official_card_count: Optional[int] = None
    api_printed_total: Optional[int] = None
    api_total: Optional[int] = None
    warnings: List[str] = None
    status: str = "pending"

    def as_dict(self) -> Dict[str, Any]:
        return {
            "local_set_id": self.local_set_id,
            "local_set_name": self.local_set_name,
            "canonical_key": self.canonical_key,
            "pokemon_api_set_id": self.pokemon_api_set_id,
            "api_returned_card_count": self.api_returned_card_count,
            "rows_inserted": self.rows_inserted,
            "rows_updated": self.rows_updated,
            "rows_skipped": self.rows_skipped,
            "local_printed_total": self.local_printed_total,
            "local_total_cards": self.local_total_cards,
            "local_official_card_count": self.local_official_card_count,
            "api_printed_total": self.api_printed_total,
            "api_total": self.api_total,
            "warnings": self.warnings or [],
            "status": self.status,
        }


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
        raise PokemonCanonicalIngestionError(
            "Missing required environment variable(s): " + ", ".join(missing)
        )


def build_headers() -> Dict[str, str]:
    return {
        "Accept": "application/json",
        "X-Api-Key": os.environ["POKEMON_TCG_API_KEY"],
        "User-Agent": "EVRCalculator/1.0",
    }


def request_json(path: str, params: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    last_error: Optional[Exception] = None
    for attempt in range(1, API_MAX_RETRIES + 1):
        try:
            response = requests.get(
                f"{API_BASE_URL}{path}",
                params=params or {},
                headers=build_headers(),
                timeout=30,
            )
        except requests.RequestException as exc:
            last_error = exc
            if attempt < API_MAX_RETRIES:
                time.sleep(API_BACKOFF_SECONDS * attempt)
                continue
            raise PokemonCanonicalIngestionError(
                f"Pokemon TCG API request failed after {API_MAX_RETRIES} attempts: {exc}"
            ) from exc

        if response.status_code >= 500 and attempt < API_MAX_RETRIES:
            time.sleep(API_BACKOFF_SECONDS * attempt)
            continue
        break
    else:
        raise PokemonCanonicalIngestionError(
            f"Pokemon TCG API request failed after {API_MAX_RETRIES} attempts: {last_error}"
        )

    if response.status_code in {401, 403}:
        raise PokemonCanonicalIngestionError(
            "Pokemon TCG API rejected the request. Verify POKEMON_TCG_API_KEY."
        )
    if response.status_code == 429:
        retry_after = response.headers.get("Retry-After")
        raise PokemonCanonicalIngestionError(
            f"Pokemon TCG API rate limit exceeded. Retry after {retry_after or 'the cooldown window'}."
        )
    try:
        response.raise_for_status()
    except requests.RequestException as exc:
        raise PokemonCanonicalIngestionError(f"Pokemon TCG API request failed: {exc}") from exc

    payload = response.json()
    if not isinstance(payload, dict):
        raise PokemonCanonicalIngestionError("Pokemon TCG API returned a non-object JSON payload")
    return payload


def fetch_api_set(api_set_id: str) -> Dict[str, Any]:
    payload = request_json(f"/sets/{api_set_id}")
    data = payload.get("data")
    if not isinstance(data, dict):
        raise PokemonCanonicalIngestionError(
            f"Unexpected Pokemon TCG API set response shape for set {api_set_id!r}"
        )
    return data


def fetch_cards_for_api_set(api_set_id: str) -> List[Dict[str, Any]]:
    cards: List[Dict[str, Any]] = []
    seen_ids: Set[str] = set()
    page = 1
    total_count: Optional[int] = None
    max_pages = 500

    while page <= max_pages:
        payload = request_json(
            "/cards",
            {
                "q": f"set.id:{api_set_id}",
                "page": page,
                "pageSize": API_PAGE_SIZE,
                "orderBy": "id",
            },
        )
        data = payload.get("data")
        if not isinstance(data, list):
            raise PokemonCanonicalIngestionError(
                f"Unexpected Pokemon TCG API cards response shape for set {api_set_id!r}"
            )

        raw_total_count = payload.get("totalCount")
        if raw_total_count is not None:
            try:
                total_count = int(raw_total_count)
            except (TypeError, ValueError) as exc:
                raise PokemonCanonicalIngestionError(
                    f"Unexpected totalCount value for set {api_set_id!r}: {raw_total_count!r}"
                ) from exc

        for card in data:
            if not isinstance(card, dict):
                raise PokemonCanonicalIngestionError(
                    f"Unexpected card item shape for set {api_set_id!r}"
                )
            card_id = str(card.get("id") or "").strip()
            if not card_id:
                raise PokemonCanonicalIngestionError(
                    f"Pokemon TCG API returned a card without id for set {api_set_id!r}"
                )
            if card_id in seen_ids:
                continue
            seen_ids.add(card_id)
            cards.append(card)

        if not data:
            break
        if total_count is not None and len(cards) >= total_count:
            break
        if len(data) < API_PAGE_SIZE and total_count is None:
            break

        page += 1
        if REQUEST_DELAY_SECONDS > 0:
            time.sleep(REQUEST_DELAY_SECONDS)

    if page > max_pages:
        raise PokemonCanonicalIngestionError(
            f"Pagination safety guard exceeded for Pokemon TCG API set {api_set_id!r}"
        )
    if total_count is not None and len(cards) != total_count:
        raise PokemonCanonicalIngestionError(
            f"Pokemon TCG API count mismatch for {api_set_id!r}: fetched {len(cards)} of {total_count}"
        )
    return cards


def to_optional_int(value: Any) -> Optional[int]:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def to_str_list(value: Any) -> List[str]:
    if not isinstance(value, list):
        return []
    return [str(item).strip() for item in value if str(item).strip()]


def to_int_list(value: Any) -> List[int]:
    if not isinstance(value, list):
        return []
    parsed: List[int] = []
    for item in value:
        number = to_optional_int(item)
        if number is not None:
            parsed.append(number)
    return parsed


def build_printed_number(number: Optional[str], printed_total: Optional[int]) -> Optional[str]:
    if not number:
        return None
    if printed_total is None:
        return number
    return f"{number}/{printed_total}"


def build_canonical_row(
    *,
    local_set_id: str,
    api_set_id: str,
    api_printed_total: Optional[int],
    card: Dict[str, Any],
) -> Dict[str, Any]:
    images = card.get("images") if isinstance(card.get("images"), dict) else {}
    set_payload = card.get("set") if isinstance(card.get("set"), dict) else {}
    api_card_id = str(card.get("id") or "").strip()
    name = str(card.get("name") or "").strip()
    number = str(card.get("number") or "").strip() or None

    if not api_card_id or not name:
        raise PokemonCanonicalIngestionError(
            f"Cannot build canonical row with api_card_id={api_card_id!r} name={name!r}"
        )

    return {
        "set_id": local_set_id,
        "pokemon_tcg_api_card_id": api_card_id,
        "name": name,
        "supertype": str(card.get("supertype") or "").strip() or None,
        "subtypes": to_str_list(card.get("subtypes")),
        "rarity": str(card.get("rarity") or "").strip() or None,
        "number": number,
        "printed_number": build_printed_number(number, api_printed_total),
        "artist": str(card.get("artist") or "").strip() or None,
        "pokemon_tcg_api_set_id": str(set_payload.get("id") or api_set_id).strip() or api_set_id,
        "national_pokedex_numbers": to_int_list(card.get("nationalPokedexNumbers")),
        "image_small_url": str(images.get("small") or "").strip() or None,
        "image_large_url": str(images.get("large") or "").strip() or None,
        "source": "pokemon_tcg_api",
        "source_payload": card,
    }


def chunked(values: Sequence[Dict[str, Any]], size: int) -> Iterable[Sequence[Dict[str, Any]]]:
    for index in range(0, len(values), size):
        yield values[index:index + size]


def get_supabase_client():
    from backend.db.clients.supabase_client import supabase

    return supabase


def load_existing_api_card_ids(client: Any, api_card_ids: Sequence[str]) -> Set[str]:
    existing: Set[str] = set()
    if not api_card_ids:
        return existing

    for chunk_start in range(0, len(api_card_ids), UPSERT_BATCH_SIZE):
        chunk = list(api_card_ids[chunk_start:chunk_start + UPSERT_BATCH_SIZE])
        result = (
            client.table(CANONICAL_TABLE)
            .select("pokemon_tcg_api_card_id")
            .in_("pokemon_tcg_api_card_id", chunk)
            .execute()
        )
        for row in result.data or []:
            card_id = str(row.get("pokemon_tcg_api_card_id") or "").strip()
            if card_id:
                existing.add(card_id)
    return existing


def select_target_sets(args: argparse.Namespace) -> List[Dict[str, Any]]:
    client = get_supabase_client()
    if args.all:
        result = (
            client.table("sets")
            .select(SET_SELECT)
            .not_.is_("pokemon_api_set_id", "null")
            .order("release_date")
            .order("name")
            .execute()
        )
        return list(result.data or [])

    if args.set_key:
        result = (
            client.table("sets")
            .select(SET_SELECT)
            .eq("canonical_key", args.set_key)
            .execute()
        )
        return list(result.data or [])

    if args.pokemon_api_set_id:
        result = (
            client.table("sets")
            .select(SET_SELECT)
            .eq("pokemon_api_set_id", args.pokemon_api_set_id)
            .execute()
        )
        return list(result.data or [])

    raise PokemonCanonicalIngestionError(
        "Provide exactly one target selector: --set-key, --pokemon-api-set-id, or --all"
    )


def write_rows(client: Any, rows: Sequence[Dict[str, Any]]) -> None:
    now_utc = datetime.now(timezone.utc).isoformat()
    timestamped_rows = [dict(row, updated_at=now_utc) for row in rows]
    for batch in chunked(timestamped_rows, UPSERT_BATCH_SIZE):
        result = (
            client.table(CANONICAL_TABLE)
            .upsert(list(batch), on_conflict="pokemon_tcg_api_card_id")
            .execute()
        )
        if result is None:
            raise PokemonCanonicalIngestionError("Canonical card upsert returned no response")


def ingest_set(set_row: Dict[str, Any], *, commit: bool, force_refresh: bool) -> SetIngestSummary:
    local_set_id = str(set_row.get("id") or "").strip()
    pokemon_api_set_id = str(set_row.get("pokemon_api_set_id") or "").strip() or None
    summary = SetIngestSummary(
        local_set_id=local_set_id,
        local_set_name=str(set_row.get("name") or local_set_id).strip(),
        canonical_key=str(set_row.get("canonical_key") or "").strip() or None,
        pokemon_api_set_id=pokemon_api_set_id,
        local_printed_total=to_optional_int(set_row.get("printed_total")),
        local_total_cards=to_optional_int(set_row.get("total_cards")),
        local_official_card_count=to_optional_int(set_row.get("official_card_count")),
        warnings=[],
    )

    if not local_set_id:
        summary.status = "skipped"
        summary.warnings.append("Local set row is missing id")
        return summary

    if not pokemon_api_set_id:
        summary.status = "skipped"
        summary.warnings.append("Local set is missing pokemon_api_set_id")
        return summary

    api_set = fetch_api_set(pokemon_api_set_id)
    summary.api_printed_total = to_optional_int(api_set.get("printedTotal"))
    summary.api_total = to_optional_int(api_set.get("total"))

    api_cards = fetch_cards_for_api_set(pokemon_api_set_id)
    summary.api_returned_card_count = len(api_cards)

    rows = [
        build_canonical_row(
            local_set_id=local_set_id,
            api_set_id=pokemon_api_set_id,
            api_printed_total=summary.api_printed_total,
            card=card,
        )
        for card in api_cards
    ]

    api_card_ids = [row["pokemon_tcg_api_card_id"] for row in rows]
    existing_ids = load_existing_api_card_ids(get_supabase_client(), api_card_ids)
    insert_rows = [row for row in rows if row["pokemon_tcg_api_card_id"] not in existing_ids]
    update_rows = [
        row
        for row in rows
        if row["pokemon_tcg_api_card_id"] in existing_ids
    ] if force_refresh else []

    summary.rows_inserted = len(insert_rows)
    summary.rows_updated = len(update_rows)
    summary.rows_skipped = len(rows) - summary.rows_inserted - summary.rows_updated

    for local_key, local_count in (
        ("sets.printed_total", summary.local_printed_total),
        ("sets.total_cards", summary.local_total_cards),
        ("sets.official_card_count", summary.local_official_card_count),
    ):
        if local_count is not None and local_count != len(rows):
            summary.warnings.append(
                f"{local_key}={local_count} differs from API card count={len(rows)}"
            )

    if summary.api_total is not None and summary.api_total != len(rows):
        summary.warnings.append(
            f"Pokemon API set total={summary.api_total} differs from fetched card count={len(rows)}"
        )

    if commit:
        write_rows(get_supabase_client(), [*insert_rows, *update_rows])
        summary.status = "committed"
    else:
        summary.status = "dry_run"

    return summary


def validate_args(args: argparse.Namespace) -> None:
    selectors = [bool(args.set_key), bool(args.pokemon_api_set_id), bool(args.all)]
    if sum(selectors) != 1:
        raise PokemonCanonicalIngestionError(
            "Choose exactly one of --set-key, --pokemon-api-set-id, or --all"
        )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Ingest canonical Pokemon checklist cards from the Pokemon TCG API"
    )
    parser.add_argument("--set-key", help="Local sets.canonical_key to ingest")
    parser.add_argument("--pokemon-api-set-id", help="Pokemon TCG API set id to ingest")
    parser.add_argument("--all", action="store_true", help="Ingest all sets with pokemon_api_set_id")
    parser.add_argument("--commit", action="store_true", help="Write rows. Omit for dry-run.")
    parser.add_argument(
        "--force-refresh",
        action="store_true",
        help="Update existing canonical rows instead of skipping them",
    )
    return parser


def main() -> int:
    args = build_parser().parse_args()
    validate_args(args)
    load_backend_env()
    require_env()

    target_sets = select_target_sets(args)
    if not target_sets:
        raise PokemonCanonicalIngestionError("No local sets matched the requested selector")

    print(
        f"[canonical-ingest] targets={len(target_sets)} "
        f"commit={bool(args.commit)} force_refresh={bool(args.force_refresh)}"
    )

    summaries: List[SetIngestSummary] = []
    for set_row in target_sets:
        try:
            summary = ingest_set(
                set_row,
                commit=bool(args.commit),
                force_refresh=bool(args.force_refresh),
            )
            summaries.append(summary)
            print(json.dumps(summary.as_dict(), indent=2, sort_keys=True))
        except PokemonCanonicalIngestionError:
            raise
        except Exception as exc:
            raise PokemonCanonicalIngestionError(
                f"Failed ingesting set {set_row.get('name') or set_row.get('id')}: {exc}"
            ) from exc

    skipped_identity = [
        item.as_dict()
        for item in summaries
        if any("pokemon_api_set_id" in warning for warning in (item.warnings or []))
    ]
    rollup = {
        "sets_seen": len(summaries),
        "sets_committed": sum(1 for item in summaries if item.status == "committed"),
        "sets_dry_run": sum(1 for item in summaries if item.status == "dry_run"),
        "sets_skipped": sum(1 for item in summaries if item.status == "skipped"),
        "cards_returned_by_api": sum(item.api_returned_card_count for item in summaries),
        "rows_inserted": sum(item.rows_inserted for item in summaries),
        "rows_updated": sum(item.rows_updated for item in summaries),
        "rows_skipped": sum(item.rows_skipped for item in summaries),
        "sets_missing_pokemon_api_set_id": skipped_identity,
    }
    print("[canonical-ingest] rollup")
    print(json.dumps(rollup, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except PokemonCanonicalIngestionError as exc:
        print(f"[canonical-ingest][ERROR] {exc}", file=sys.stderr)
        raise SystemExit(1)
