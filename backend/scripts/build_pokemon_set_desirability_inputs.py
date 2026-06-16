from __future__ import annotations

import argparse
import json
import logging
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

from dotenv import load_dotenv

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))

from backend.desirability.normalization import normalize_pokemon_name_key  # noqa: E402
from backend.desirability.composite import COMPOSITE_SCORING_VERSION  # noqa: E402
from backend.desirability.set_components import SCORING_VERSION as COMPONENT_SCORING_VERSION  # noqa: E402
from backend.desirability.rip_desirability import SCORING_VERSION as OPENING_SCORING_VERSION  # noqa: E402
from backend.scripts.build_pokemon_card_desirability_links import (  # noqa: E402
    DEFAULT_HIT_POLICY_VERSION,
    PokemonCardDesirabilityLinksRepository,
    build_links_report,
)
from backend.scripts.build_pokemon_set_desirability_component_scores import (  # noqa: E402
    PokemonSetDesirabilityComponentsRepository,
    build_component_scores_report,
)
from backend.scripts.build_pokemon_set_hit_desirability_summaries import (  # noqa: E402
    DEFAULT_AGGREGATION_VERSION,
    PokemonSetHitDesirabilitySummariesRepository,
    build_set_hit_desirability_summaries_report,
)
from backend.scripts.build_set_rip_desirability_prototype import (  # noqa: E402
    OPENING_DESIRABILITY_TABLE,
    RipDesirabilityPrototypeRepository,
    build_opening_desirability_persistence_rows,
    build_report,
)
from backend.scripts.run_pokemon_set_scrape import (  # noqa: E402
    build_valid_set_key_registry,
    normalize_set_key_filter,
)

logger = logging.getLogger(__name__)

FALLBACK_SOURCE = "tcgplayer_cards_fallback"
FALLBACK_MATCH_METHOD = "name_exact_or_alias"
UPSERT_BATCH_SIZE = 250

CARD_SUFFIX_RE = re.compile(r"\b(ex|gx|vmax|vstar|v|break|lv\.?\s*x|star|prime|legend)\b", flags=re.IGNORECASE)
STANDALONE_EX_RE = re.compile(r"\bex\b", flags=re.IGNORECASE)
TRAINER_LIKE_KEYWORDS = (
    "trainer",
    "supporter",
    "stadium",
    "item",
    "tool",
    "ball",
    "retrieval",
    "net",
    "card",
    "energy",
)


class SetDesirabilityInputsError(RuntimeError):
    pass


def load_backend_env() -> None:
    env_path = Path(__file__).resolve().parents[1] / ".env"
    load_dotenv(env_path, override=False)


def get_supabase_client():
    from backend.db.clients.supabase_client import supabase

    return supabase


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Build set-level Pokemon desirability inputs from canonical cards through opening desirability snapshots."
    )
    selector = parser.add_mutually_exclusive_group(required=True)
    selector.add_argument("--set", dest="set_key", help="sets.canonical_key to process")
    selector.add_argument("--all", action="store_true", help="Process all sets")

    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--dry-run", action="store_true", help="Preview changes only (default)")
    mode.add_argument("--commit", action="store_true", help="Write changes to Supabase")

    parser.add_argument("--log-level", default="INFO")
    return parser


def main() -> int:
    args = build_parser().parse_args()
    logging.basicConfig(level=getattr(logging, args.log_level.upper(), logging.INFO), format="%(levelname)s %(message)s")
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)
    load_backend_env()

    dry_run = not args.commit
    if args.dry_run:
        dry_run = True

    report = build_set_desirability_inputs_report(
        set_key=args.set_key,
        process_all=bool(args.all),
        dry_run=dry_run,
    )
    print(json.dumps(report, indent=2, sort_keys=True))
    status = str(report.get("status") or "")
    return 0 if status in {"dry_run", "committed"} else 1


def build_set_desirability_inputs_report(*, set_key: Optional[str], process_all: bool, dry_run: bool) -> Dict[str, Any]:
    client = get_supabase_client()
    registry = build_valid_set_key_registry()
    resolved_set_key = None
    if set_key:
        resolution = normalize_set_key_filter(set_key, registry)
        resolved_set_key = resolution.get("resolved_set_key_filter")
        if not resolved_set_key:
            raise SetDesirabilityInputsError(f"Unknown set key {set_key!r}")

    sets = _list_sets(client, set_key=resolved_set_key, process_all=process_all)
    if not sets:
        return {
            "status": "no_sets_found",
            "dry_run": dry_run,
            "requested_set_key": set_key,
            "resolved_set_key": resolved_set_key,
        }

    set_reports: List[Dict[str, Any]] = []
    for set_row in sets:
        set_reports.append(_process_single_set(client=client, set_row=set_row, dry_run=dry_run))

    selected_set_ids = [str(row.get("id")) for row in sets if row.get("id") is not None]
    selected_set_key = resolved_set_key if resolved_set_key else None

    links_report = _build_links(selected_set_key=selected_set_key, process_all=process_all, dry_run=dry_run)
    summaries_report = _build_summaries(selected_set_key=selected_set_key, process_all=process_all, dry_run=dry_run)
    components_report = _build_components(selected_set_key=selected_set_key, process_all=process_all, dry_run=dry_run)
    opening_report = _build_opening(selected_set_ids=selected_set_ids, dry_run=dry_run)

    return {
        "status": "dry_run" if dry_run else "committed",
        "dry_run": dry_run,
        "requested_set_key": set_key,
        "resolved_set_key": resolved_set_key,
        "sets_processed": len(set_reports),
        "canonical_fallback": {
            "rows_seen_in_cards": sum(int(r.get("cards_rows") or 0) for r in set_reports),
            "rows_preexisting_canonical": sum(int(r.get("preexisting_canonical_rows") or 0) for r in set_reports),
            "rows_missing_before": sum(int(r.get("rows_missing_before") or 0) for r in set_reports),
            "rows_upsert_planned": sum(int(r.get("rows_upsert_planned") or 0) for r in set_reports),
            "rows_upserted": sum(int(r.get("rows_upserted") or 0) for r in set_reports),
            "rows_skipped_missing_required": sum(int(r.get("rows_skipped_missing_required") or 0) for r in set_reports),
        },
        "set_reports": set_reports,
        "links_report": links_report,
        "hit_summaries_report": summaries_report,
        "component_scores_report": components_report,
        "opening_desirability_report": opening_report,
    }


def _process_single_set(*, client: Any, set_row: Dict[str, Any], dry_run: bool) -> Dict[str, Any]:
    set_id = str(set_row.get("id") or "")
    canonical_key = str(set_row.get("canonical_key") or "")
    if not set_id:
        raise SetDesirabilityInputsError("Encountered set row without id")

    cards = _list_cards_for_set(client, set_id)
    canonical_rows = _list_canonical_for_set(client, set_id)
    existing_by_api_id = {
        str(row.get("pokemon_tcg_api_card_id")): row
        for row in canonical_rows
        if row.get("pokemon_tcg_api_card_id") is not None
    }
    existing_by_key = {
        _canonical_identity(str(row.get("number") or ""), str(row.get("name") or "")): row
        for row in canonical_rows
    }

    references = _list_pokemon_reference(client)
    reference_lookup = _build_reference_lookup(references)

    rows_to_upsert: List[Dict[str, Any]] = []
    skipped_missing_required = 0
    matched_pokemon_cards = 0
    non_pokemon_cards = 0
    unmatched_non_trainer_cards = 0
    sample_unmatched_non_trainer_cards: List[Dict[str, str]] = []

    for card in cards:
        printed_number = str(card.get("card_number") or "").strip()
        number = _canonical_number(printed_number)
        name = str(card.get("name") or "").strip()
        if not number or not name:
            skipped_missing_required += 1
            continue

        api_card_id = str(card.get("pokemon_tcg_api_id") or "").strip() or _fallback_api_card_id(
            set_id=set_id,
            number=printed_number,
            name=name,
        )

        key = _canonical_identity(number, name)
        existing = existing_by_api_id.get(api_card_id) or existing_by_key.get(key)

        if existing and str(existing.get("source") or "") not in {"", FALLBACK_SOURCE}:
            continue

        non_pokemon_supertype = _infer_non_pokemon_supertype(name)
        matched_reference = None
        if non_pokemon_supertype is None:
            matched_reference = _match_reference_for_card_name(name=name, reference_lookup=reference_lookup)

        if non_pokemon_supertype:
            supertype = non_pokemon_supertype
            non_pokemon_cards += 1
        elif matched_reference:
            supertype = "Pokémon"
            matched_pokemon_cards += 1
        else:
            supertype = None
            unmatched_non_trainer_cards += 1
            if len(sample_unmatched_non_trainer_cards) < 10:
                sample_unmatched_non_trainer_cards.append(
                    {
                        "name": name,
                        "card_number": printed_number,
                    }
                )

        subtypes = _infer_subtypes(name) if non_pokemon_supertype is None else []
        pokedex_numbers = [int(matched_reference["pokedex_number"])] if matched_reference else []

        rows_to_upsert.append(
            {
                "set_id": set_id,
                "pokemon_tcg_api_card_id": api_card_id,
                "name": name,
                "supertype": supertype,
                "subtypes": subtypes,
                "rarity": str(card.get("rarity") or "").strip() or None,
                "number": number,
                "printed_number": printed_number,
                "artist": None,
                "pokemon_tcg_api_set_id": str(set_row.get("pokemon_api_set_id") or "").strip() or None,
                "national_pokedex_numbers": pokedex_numbers,
                "image_small_url": str(card.get("image_small_url") or "").strip() or None,
                "image_large_url": str(card.get("image_large_url") or "").strip() or None,
                "source": FALLBACK_SOURCE,
                "source_payload": {
                    "source_table": "public.cards",
                    "source_card_id": card.get("id"),
                    "match_method": FALLBACK_MATCH_METHOD,
                    "matched_pokedex_number": matched_reference.get("pokedex_number") if matched_reference else None,
                },
            }
        )

    rows_upserted = 0
    if not dry_run and rows_to_upsert:
        rows_upserted = _upsert_canonical_rows(client, rows_to_upsert)

    return {
        "set_id": set_id,
        "set_name": set_row.get("name"),
        "set_canonical_key": canonical_key,
        "cards_rows": len(cards),
        "preexisting_canonical_rows": len(canonical_rows),
        "rows_missing_before": max(0, len(cards) - len(canonical_rows)),
        "rows_upsert_planned": len(rows_to_upsert),
        "rows_upserted": rows_upserted,
        "rows_skipped_missing_required": skipped_missing_required,
        "matched_pokemon_cards": matched_pokemon_cards,
        "non_pokemon_cards": non_pokemon_cards,
        "unmatched_non_trainer_cards": unmatched_non_trainer_cards,
        "sample_unmatched_non_trainer_cards": sample_unmatched_non_trainer_cards,
    }


def _build_links(*, selected_set_key: Optional[str], process_all: bool, dry_run: bool) -> Dict[str, Any]:
    return build_links_report(
        repository=PokemonCardDesirabilityLinksRepository(),
        set_key=selected_set_key,
        process_all=bool(process_all and not selected_set_key),
        hit_policy_version=DEFAULT_HIT_POLICY_VERSION,
        dry_run=dry_run,
    )


def _build_summaries(*, selected_set_key: Optional[str], process_all: bool, dry_run: bool) -> Dict[str, Any]:
    return build_set_hit_desirability_summaries_report(
        repository=PokemonSetHitDesirabilitySummariesRepository(),
        set_key=selected_set_key,
        process_all=bool(process_all and not selected_set_key),
        aggregation_version=DEFAULT_AGGREGATION_VERSION,
        hit_policy_version=DEFAULT_HIT_POLICY_VERSION,
        composite_scoring_version=COMPOSITE_SCORING_VERSION,
        min_composite_coverage=0.95,
        dry_run=dry_run,
    )


def _build_components(*, selected_set_key: Optional[str], process_all: bool, dry_run: bool) -> Dict[str, Any]:
    _ = process_all
    return build_component_scores_report(
        repository=PokemonSetDesirabilityComponentsRepository(),
        set_id=None,
        canonical_key=selected_set_key,
        limit=None,
        force=False,
        scoring_version=COMPONENT_SCORING_VERSION,
        hit_policy_version=DEFAULT_HIT_POLICY_VERSION,
        composite_scoring_version=COMPOSITE_SCORING_VERSION,
        min_composite_coverage=0.95,
        dry_run=dry_run,
    )


def _build_opening(*, selected_set_ids: Sequence[str], dry_run: bool) -> Dict[str, Any]:
    repository = RipDesirabilityPrototypeRepository()
    report = build_report(
        repository=repository,
        scoring_version=COMPONENT_SCORING_VERSION,
        hit_policy_version=DEFAULT_HIT_POLICY_VERSION,
        composite_scoring_version=COMPOSITE_SCORING_VERSION,
        limit=None,
    )
    rows = [
        row
        for row in list(report.get("rows") or [])
        if str(row.get("set_id") or "") in set(selected_set_ids)
    ]

    if dry_run:
        return {
            "committed": False,
            "target_table": OPENING_DESIRABILITY_TABLE,
            "rows_available_in_report": len(report.get("rows") or []),
            "rows_selected": len(rows),
            "rows_to_write": 0,
            "rows_that_would_be_persisted": len(rows),
            "written_rows_returned": 0,
            "scoring_version": OPENING_SCORING_VERSION,
        }

    payload = build_opening_desirability_persistence_rows(rows, scoring_version=OPENING_SCORING_VERSION)
    deduped_payload = _filter_existing_opening_rows(repository=repository, rows=payload)
    written = _insert_opening_rows(repository=repository, rows=deduped_payload)
    return {
        "committed": True,
        "target_table": OPENING_DESIRABILITY_TABLE,
        "rows_available_in_report": len(report.get("rows") or []),
        "rows_selected": len(rows),
        "rows_to_write": len(deduped_payload),
        "rows_that_would_be_persisted": len(rows),
        "written_rows_returned": written,
        "scoring_version": OPENING_SCORING_VERSION,
    }


def _insert_opening_rows(*, repository: RipDesirabilityPrototypeRepository, rows: Sequence[Dict[str, Any]]) -> int:
    if not rows:
        return 0
    written = 0
    for chunk in _chunked(list(rows), UPSERT_BATCH_SIZE):
        response = repository.client.table(OPENING_DESIRABILITY_TABLE).insert(list(chunk)).execute()
        written += len(response.data or [])
    return written


def _filter_existing_opening_rows(*, repository: RipDesirabilityPrototypeRepository, rows: Sequence[Dict[str, Any]]) -> List[Dict[str, Any]]:
    set_ids = sorted({str(row.get("set_id")) for row in rows if row.get("set_id") is not None})
    if not set_ids:
        return []

    existing_rows: List[Dict[str, Any]] = []
    for chunk in _chunked(set_ids, 200):
        result = (
            repository.client.table(OPENING_DESIRABILITY_TABLE)
            .select("set_id,scoring_version,source_v2_component_row_id,source_rip_calculation_run_id")
            .in_("set_id", list(chunk))
            .eq("scoring_version", OPENING_SCORING_VERSION)
            .execute()
        )
        existing_rows.extend(result.data or [])

    existing_signatures = {
        _opening_signature(
            set_id=row.get("set_id"),
            scoring_version=row.get("scoring_version"),
            source_v2_component_row_id=row.get("source_v2_component_row_id"),
            source_rip_calculation_run_id=row.get("source_rip_calculation_run_id"),
        )
        for row in existing_rows
    }

    filtered: List[Dict[str, Any]] = []
    for row in rows:
        signature = _opening_signature(
            set_id=row.get("set_id"),
            scoring_version=row.get("scoring_version"),
            source_v2_component_row_id=row.get("source_v2_component_row_id"),
            source_rip_calculation_run_id=row.get("source_rip_calculation_run_id"),
        )
        if signature in existing_signatures:
            continue
        filtered.append(row)
    return filtered


def _opening_signature(*, set_id: Any, scoring_version: Any, source_v2_component_row_id: Any, source_rip_calculation_run_id: Any) -> Tuple[str, str, str, str]:
    return (
        str(set_id or ""),
        str(scoring_version or ""),
        str(source_v2_component_row_id or ""),
        str(source_rip_calculation_run_id or ""),
    )


def _list_sets(client: Any, *, set_key: Optional[str], process_all: bool) -> List[Dict[str, Any]]:
    query = client.table("sets").select("id,name,canonical_key,pokemon_api_set_id").order("name")
    if set_key:
        query = query.eq("canonical_key", set_key)
    elif not process_all:
        raise SetDesirabilityInputsError("Choose --set or --all")
    result = query.execute()
    return list(result.data or [])


def _list_cards_for_set(client: Any, set_id: str) -> List[Dict[str, Any]]:
    result = (
        client.table("cards")
        .select("id,set_id,name,rarity,card_number,pokemon_tcg_api_id,image_small_url,image_large_url")
        .eq("set_id", set_id)
        .order("card_number")
        .order("name")
        .execute()
    )
    return list(result.data or [])


def _list_canonical_for_set(client: Any, set_id: str) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    start = 0
    page_size = 1000
    while True:
        result = (
            client.table("pokemon_canonical_cards")
            .select("id,set_id,pokemon_tcg_api_card_id,name,number,source")
            .eq("set_id", set_id)
            .range(start, start + page_size - 1)
            .execute()
        )
        page = list(result.data or [])
        rows.extend(page)
        if len(page) < page_size:
            break
        start += page_size
    return rows


def _list_pokemon_reference(client: Any) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    start = 0
    page_size = 1000
    while True:
        result = (
            client.table("pokemon_reference")
            .select("id,pokedex_number,canonical_name,display_name")
            .range(start, start + page_size - 1)
            .execute()
        )
        page = list(result.data or [])
        rows.extend(page)
        if len(page) < page_size:
            break
        start += page_size
    return rows


def _build_reference_lookup(references: Sequence[Dict[str, Any]]) -> Dict[str, Dict[str, Any]]:
    lookup: Dict[str, Dict[str, Any]] = {}
    for row in references:
        for field in ("display_name", "canonical_name"):
            key = normalize_pokemon_name_key(row.get(field))
            if not key:
                continue
            lookup.setdefault(key, row)
    return lookup


def _match_reference_for_card_name(*, name: str, reference_lookup: Dict[str, Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    normalized = normalize_pokemon_name_key(name)
    if not normalized:
        return None

    alias_lookup = {
        "keldeo": "keldeo ordinary",
        "deoxys": "deoxys normal",
        "meowstic": "meowstic male",
        "pumpkaboo": "pumpkaboo average",
        "pyroar": "pyroar male",
        "gourgeist": "gourgeist average",
    }

    candidate = _strip_name_tokens(normalized)
    if candidate in alias_lookup:
        alias_row = reference_lookup.get(alias_lookup[candidate])
        if alias_row:
            return alias_row

    exact = reference_lookup.get(candidate)
    if exact:
        return exact

    return None


def _strip_name_tokens(value: str) -> str:
    cleaned = value
    cleaned = CARD_SUFFIX_RE.sub(" ", cleaned)
    cleaned = re.sub(r"\bmega\b", " ", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    return cleaned


def _infer_non_pokemon_supertype(name: str) -> Optional[str]:
    normalized = normalize_pokemon_name_key(name)
    if not normalized:
        return None
    for keyword in TRAINER_LIKE_KEYWORDS:
        if keyword in normalized:
            if keyword == "energy":
                return "Energy"
            return "Trainer"
    return None


def _fallback_api_card_id(*, set_id: str, number: str, name: str) -> str:
    normalized_name = normalize_pokemon_name_key(name) or "unknown"
    return f"fallback:{set_id}:{number}:{normalized_name}"


def _canonical_identity(number: str, name: str) -> Tuple[str, str]:
    return (_canonical_number(number), name.strip().lower())


def _canonical_number(card_number: str) -> str:
    value = str(card_number or "").strip()
    if not value:
        return ""

    left = value.split("/", 1)[0].strip()
    if left.isdigit():
        return str(int(left))
    return left


def _infer_subtypes(name: str) -> List[str]:
    subtypes: List[str] = []
    if "mega" in str(name or "").lower():
        subtypes.append("MEGA")
    if STANDALONE_EX_RE.search(str(name or "")):
        subtypes.append("ex")
    return subtypes


def _upsert_canonical_rows(client: Any, rows: Sequence[Dict[str, Any]]) -> int:
    if not rows:
        return 0
    now = datetime.now(timezone.utc).isoformat()
    payload = [dict(row, updated_at=now) for row in rows]
    written = 0
    for chunk in _chunked(payload, UPSERT_BATCH_SIZE):
        result = (
            client.table("pokemon_canonical_cards")
            .upsert(list(chunk), on_conflict="pokemon_tcg_api_card_id")
            .execute()
        )
        written += len(result.data or [])
    return written


def _chunked(values: Sequence[Any], size: int) -> Iterable[Sequence[Any]]:
    for index in range(0, len(values), size):
        yield values[index:index + size]


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except SetDesirabilityInputsError as exc:
        print(f"[pokemon-set-desirability-inputs][ERROR] {exc}", file=sys.stderr)
        raise SystemExit(1)
