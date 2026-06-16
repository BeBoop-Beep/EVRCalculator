from __future__ import annotations

import argparse
import json
import logging
import os
import sys
from collections import Counter, defaultdict
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

from dotenv import load_dotenv

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))

from backend.calculations.utils.rarity_classification import (  # noqa: E402
    is_hit_card,
    normalize_rarity_key,
)
from backend.desirability.normalization import normalize_pokemon_name_key  # noqa: E402
from backend.scripts.run_pokemon_set_scrape import build_valid_set_key_registry  # noqa: E402


logger = logging.getLogger(__name__)


LINK_TABLE = "pokemon_card_desirability_links"
DEFAULT_HIT_POLICY_VERSION = "pokemon_card_desirability_hit_policy_v1"
POKEDEX_MATCH_METHOD = "national_pokedex_numbers"
FALLBACK_MATCH_METHOD = "normalized_name_fallback"
POKEDEX_MATCH_CONFIDENCE = Decimal("1.0")
FALLBACK_MATCH_CONFIDENCE = Decimal("0.85")
FALLBACK_SOURCE = "pokemon_canonical_cards.name"
POKEDEX_SOURCE = "pokemon_canonical_cards.national_pokedex_numbers"
UPSERT_BATCH_SIZE = 500

FALLBACK_HIT_RARITY_KEYS = frozenset(
    {
        "rare_holo",
        "rare_ultra",
        "illustration_rare",
        "rare_secret",
        "rare_rainbow",
        "ultra_rare",
        "rare_holo_ex",
        "double_rare",
        "rare_holo_v",
        "special_illustration_rare",
        "rare_holo_gx",
        "rare_shiny",
        "shiny_rare",
        "rare_holo_vmax",
        "trainer_gallery_rare_holo",
        "hyper_rare",
        "rare_holo_lv_x",
        "rare_holo_lv.x",
        "rare_holo_vstar",
        "rare_shiny_gx",
        "ace_spec_rare",
        "rare_break",
        "rare_prism_star",
        "rare_prime",
        "classic_collection",
        "rare_holo_star",
        "legend",
        "rare_shining",
        "radiant_rare",
        "rare_ace",
        "shiny_ultra_rare",
        "amazing_rare",
        "mega_attack_rare",
        "mega_hyper_rare",
        "black_white_rare",
    }
)

CARD_SUFFIX_KEYS = frozenset(
    {
        "ex",
        "gx",
        "v",
        "vmax",
        "vstar",
        "break",
        "prime",
        "legend",
        "lv x",
        "star",
    }
)


class PokemonCardDesirabilityLinksError(RuntimeError):
    pass


class PokemonCardDesirabilityLinksRepository:
    def __init__(self, client: Optional[Any] = None):
        if client is None:
            from backend.db.clients.supabase_client import supabase

            client = supabase
        self.client = client

    def list_sets(self, *, set_key: Optional[str]) -> List[Dict[str, Any]]:
        query = self.client.table("sets").select("id,name,canonical_key").order("name")
        if set_key:
            query = query.eq("canonical_key", set_key)
        result = query.execute()
        return list(result.data or [])

    def list_pokemon_references(self) -> List[Dict[str, Any]]:
        return _paged_select(
            self.client.table("pokemon_reference")
            .select("id,pokedex_number,canonical_name,display_name,generation")
            .order("pokedex_number")
        )

    def list_canonical_cards(self, set_ids: Sequence[str]) -> List[Dict[str, Any]]:
        rows: List[Dict[str, Any]] = []
        for chunk in _chunked(list(set_ids), 200):
            page_rows = _paged_select(
                self.client.table("pokemon_canonical_cards")
                .select(
                    "id,set_id,pokemon_tcg_api_card_id,name,supertype,subtypes,rarity,"
                    "number,printed_number,national_pokedex_numbers"
                )
                .in_("set_id", chunk)
                .order("number")
                .order("name")
            )
            rows.extend(page_rows)
        return rows

    def list_existing_links(self, card_ids: Sequence[str]) -> List[Dict[str, Any]]:
        rows: List[Dict[str, Any]] = []
        for chunk in _chunked(list(card_ids), 200):
            page_rows = _paged_select(
                self.client.table(LINK_TABLE)
                .select("id,pokemon_canonical_card_id,pokemon_reference_id")
                .in_("pokemon_canonical_card_id", chunk)
            )
            rows.extend(page_rows)
        return rows

    def upsert_links(self, rows: Sequence[Dict[str, Any]]) -> List[Dict[str, Any]]:
        written: List[Dict[str, Any]] = []
        if not rows:
            return written
        for chunk in _chunked(list(rows), UPSERT_BATCH_SIZE):
            result = (
                self.client.table(LINK_TABLE)
                .upsert(chunk, on_conflict="pokemon_canonical_card_id,pokemon_reference_id")
                .execute()
            )
            written.extend(result.data or [])
        return written


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Build canonical Pokemon card to Pokemon desirability-reference links."
    )
    selector_group = parser.add_mutually_exclusive_group(required=True)
    selector_group.add_argument("--set-key", help="sets.canonical_key to process")
    selector_group.add_argument("--all", action="store_true", help="Process all sets")

    mode_group = parser.add_mutually_exclusive_group()
    mode_group.add_argument("--dry-run", action="store_true", help="Preview without writing links")
    mode_group.add_argument("--commit", action="store_true", help="Write links to Supabase")

    parser.add_argument(
        "--hit-policy-version",
        default=DEFAULT_HIT_POLICY_VERSION,
        help="Version label stored on generated link rows",
    )
    parser.add_argument(
        "--include-rare-holo",
        action="store_true",
        default=True,
        help="Retained for CLI clarity; Rare Holo is included by the default policy.",
    )
    parser.add_argument("--log-level", default="INFO")
    return parser


def load_backend_env() -> None:
    env_path = Path(__file__).resolve().parents[1] / ".env"
    load_dotenv(env_path, override=False)


def main() -> int:
    args = build_parser().parse_args()
    logging.basicConfig(level=getattr(logging, args.log_level.upper(), logging.INFO), format="%(levelname)s %(message)s")
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)
    load_backend_env()

    dry_run = not args.commit
    if args.dry_run:
        dry_run = True

    repository = PokemonCardDesirabilityLinksRepository()
    report = build_links_report(
        repository=repository,
        set_key=args.set_key,
        process_all=bool(args.all),
        hit_policy_version=args.hit_policy_version,
        dry_run=dry_run,
    )
    print(json.dumps(_jsonable(report), indent=2, sort_keys=True))
    return 0 if report.get("status") in {"dry_run", "committed"} else 1


def build_links_report(
    *,
    repository: Any,
    set_key: Optional[str],
    process_all: bool,
    hit_policy_version: str,
    dry_run: bool,
) -> Dict[str, Any]:
    if not set_key and not process_all:
        raise PokemonCardDesirabilityLinksError("Choose --set-key or --all")

    registry = build_valid_set_key_registry()
    set_resolution = _resolve_set_key(set_key, registry) if set_key else None
    resolved_set_key = set_resolution.get("resolved_set_key_filter") if set_resolution else None
    if set_key and not resolved_set_key:
        raise PokemonCardDesirabilityLinksError(
            f"Unknown set key {set_key!r}. Available keys include: {registry.get('valid_keys', [])[:20]}"
        )

    sets = repository.list_sets(set_key=resolved_set_key)
    if not sets:
        return {
            "status": "no_sets_found",
            "dry_run": dry_run,
            "requested_set_key": set_key,
            "resolved_set_key": resolved_set_key,
            "hit_policy_version": hit_policy_version,
        }

    set_by_id = {str(row.get("id")): row for row in sets if row.get("id") is not None}
    cards = repository.list_canonical_cards(sorted(set_by_id.keys()))
    for card in cards:
        set_row = set_by_id.get(str(card.get("set_id"))) or {}
        card["set_canonical_key"] = set_row.get("canonical_key")
        card["set_name"] = set_row.get("name")

    references = repository.list_pokemon_references()
    link_result = build_link_rows(
        cards=cards,
        references=references,
        config_map=registry.get("config_map", {}),
        hit_policy_version=hit_policy_version,
    )

    generated_rows = link_result["rows"]
    existing_links = repository.list_existing_links(
        [str(row.get("id")) for row in cards if row.get("id")]
    ) if generated_rows else []
    existing_keys = {
        (str(row.get("pokemon_canonical_card_id")), int(row.get("pokemon_reference_id")))
        for row in existing_links
        if row.get("pokemon_canonical_card_id") is not None and row.get("pokemon_reference_id") is not None
    }
    generated_keys = {
        (str(row.get("pokemon_canonical_card_id")), int(row.get("pokemon_reference_id")))
        for row in generated_rows
    }
    insert_count = len(generated_keys - existing_keys)
    update_count = len(generated_keys & existing_keys)
    skipped_count = max(0, len(generated_rows) - insert_count - update_count)

    written_rows: List[Dict[str, Any]] = []
    if not dry_run:
        timestamp = datetime.now(timezone.utc).isoformat()
        payload = [dict(row, updated_at=timestamp) for row in generated_rows]
        written_rows = repository.upsert_links(payload)

    per_set_summary = _build_per_set_summary(cards, generated_rows, link_result)
    diagnostics = {
        **link_result["diagnostics"],
        "links_generated": len(generated_rows),
        "links_inserted": 0 if dry_run else insert_count,
        "links_updated": 0 if dry_run else update_count,
        "links_skipped": skipped_count,
        "existing_links_seen": len(existing_links),
        "written_rows_returned": len(written_rows),
        "per_set_summary": per_set_summary if process_all else per_set_summary[:1],
    }

    return {
        "status": "dry_run" if dry_run else "committed",
        "dry_run": dry_run,
        "requested_set_key": set_key,
        "resolved_set_key": resolved_set_key,
        "sets_processed": len(sets),
        "hit_policy_version": hit_policy_version,
        "diagnostics": diagnostics,
        "samples": link_result["samples"],
    }


def build_link_rows(
    *,
    cards: Sequence[Dict[str, Any]],
    references: Sequence[Dict[str, Any]],
    config_map: Dict[str, Any],
    hit_policy_version: str,
) -> Dict[str, Any]:
    references_by_pokedex = {
        int(row["pokedex_number"]): row
        for row in references
        if row.get("pokedex_number") is not None and row.get("id") is not None
    }
    reference_candidates = _build_reference_candidates(references)

    rows: List[Dict[str, Any]] = []
    cards_linked_by_pokedex: set[str] = set()
    cards_linked_by_fallback: set[str] = set()
    multi_pokemon_card_ids: set[str] = set()
    unmatched_missing_pokedex: List[Dict[str, Any]] = []
    ambiguous_fallback: List[Dict[str, Any]] = []
    excluded_non_pokemon_hit_rows: List[Dict[str, Any]] = []
    included_hit_link_rarity_counts: Counter[str] = Counter()
    excluded_rarity_counts: Counter[str] = Counter()

    total_pokemon_cards = 0
    total_non_pokemon_cards = 0
    total_hit_rarity_cards = 0
    total_pokemon_hit_eligible_cards = 0

    for card in cards:
        card_id = str(card.get("id") or "").strip()
        if not card_id:
            continue

        is_pokemon = _is_pokemon_card(card)
        is_hit = is_hit_eligible_card(card, config_map)
        if is_pokemon:
            total_pokemon_cards += 1
        else:
            total_non_pokemon_cards += 1

        if _has_hit_rarity(card, config_map):
            total_hit_rarity_cards += 1
            if not is_pokemon:
                excluded_non_pokemon_hit_rows.append(_card_sample(card, reason="non_pokemon_hit_rarity"))
                excluded_rarity_counts[_rarity_label(card)] += 1

        if not is_pokemon:
            continue

        if is_hit:
            total_pokemon_hit_eligible_cards += 1

        pokedex_numbers = _pokedex_numbers(card)
        match_rows: List[Dict[str, Any]] = []
        if pokedex_numbers:
            match_rows = _rows_from_pokedex_numbers(
                card=card,
                references_by_pokedex=references_by_pokedex,
                hit_policy_version=hit_policy_version,
                is_hit=is_hit,
            )
            if match_rows:
                cards_linked_by_pokedex.add(card_id)
            if len(match_rows) > 1:
                multi_pokemon_card_ids.add(card_id)
        else:
            fallback = find_fallback_reference_match(card, reference_candidates)
            if fallback["status"] == "matched":
                reference = fallback["reference"]
                match_rows = [
                    _build_link_row(
                        card=card,
                        reference=reference,
                        link_position=1,
                        link_count=1,
                        contribution_weight=Decimal("1.0"),
                        match_method=FALLBACK_MATCH_METHOD,
                        match_confidence=FALLBACK_MATCH_CONFIDENCE,
                        is_hit=is_hit,
                        hit_policy_version=hit_policy_version,
                        source=FALLBACK_SOURCE,
                        notes=fallback.get("notes"),
                    )
                ]
                cards_linked_by_fallback.add(card_id)
            elif fallback["status"] == "ambiguous":
                ambiguous_fallback.append(
                    {
                        **_card_sample(card, reason="ambiguous_fallback"),
                        "candidate_names": [
                            candidate.get("display_name")
                            for candidate in fallback.get("candidates", [])
                        ],
                    }
                )
            else:
                unmatched_missing_pokedex.append(_card_sample(card, reason="missing_pokedex_unmatched"))

        for row in match_rows:
            rows.append(row)
            if row["is_hit_eligible"]:
                included_hit_link_rarity_counts[_rarity_label(card)] += 1

    diagnostics = {
        "total_canonical_cards_scanned": len(cards),
        "total_pokemon_cards_scanned": total_pokemon_cards,
        "total_non_pokemon_cards_skipped": total_non_pokemon_cards,
        "total_hit_rarity_cards": total_hit_rarity_cards,
        "total_pokemon_hit_eligible_cards": total_pokemon_hit_eligible_cards,
        "cards_linked_by_pokedex_number": len(cards_linked_by_pokedex),
        "cards_linked_by_fallback_name": len(cards_linked_by_fallback),
        "unmatched_pokemon_cards_missing_pokedex_numbers": len(unmatched_missing_pokedex),
        "ambiguous_fallback_candidates": len(ambiguous_fallback),
        "multi_pokemon_cards_linked": len(multi_pokemon_card_ids),
        "excluded_non_pokemon_hit_rarity_rows": len(excluded_non_pokemon_hit_rows),
        "rarity_distribution_for_included_hit_eligible_links": dict(sorted(included_hit_link_rarity_counts.items())),
        "rarity_distribution_for_excluded_rows": dict(sorted(excluded_rarity_counts.items())),
    }
    samples = {
        "unmatched_pokemon_cards_missing_pokedex_numbers": unmatched_missing_pokedex[:50],
        "ambiguous_fallback_candidates": ambiguous_fallback[:50],
        "excluded_non_pokemon_hit_rarity_rows": excluded_non_pokemon_hit_rows[:50],
    }
    return {"rows": rows, "diagnostics": diagnostics, "samples": samples}


def is_hit_eligible_card(card: Dict[str, Any], config_map: Dict[str, Any]) -> bool:
    return _is_pokemon_card(card) and _has_hit_rarity(card, config_map)


def find_fallback_reference_match(
    card: Dict[str, Any],
    reference_candidates: Sequence[Dict[str, Any]],
) -> Dict[str, Any]:
    card_key = normalize_pokemon_name_key(card.get("name"))
    if not card_key:
        return {"status": "unmatched", "candidates": []}

    stripped_card_key = _strip_card_suffixes(card_key)
    candidates: List[Dict[str, Any]] = []
    for reference in reference_candidates:
        keys = reference.get("match_keys") or []
        for key in keys:
            if not key:
                continue
            if stripped_card_key == key or _contains_word_phrase(stripped_card_key, key):
                candidates.append({**reference, "_matched_key": key, "_matched_key_length": len(key)})
                break

    if not candidates:
        return {"status": "unmatched", "candidates": []}

    max_length = max(int(candidate.get("_matched_key_length") or 0) for candidate in candidates)
    strongest = [
        candidate
        for candidate in candidates
        if int(candidate.get("_matched_key_length") or 0) == max_length
    ]
    unique_by_reference = {
        int(candidate["id"]): candidate
        for candidate in strongest
        if candidate.get("id") is not None
    }
    if len(unique_by_reference) == 1:
        reference = next(iter(unique_by_reference.values()))
        return {
            "status": "matched",
            "reference": reference,
            "candidates": strongest,
            "notes": f"fallback matched normalized card name {card_key!r} to {reference.get('display_name')!r}",
        }
    return {"status": "ambiguous", "candidates": strongest}


def _rows_from_pokedex_numbers(
    *,
    card: Dict[str, Any],
    references_by_pokedex: Dict[int, Dict[str, Any]],
    hit_policy_version: str,
    is_hit: bool,
) -> List[Dict[str, Any]]:
    numbers = _pokedex_numbers(card)
    references = [
        references_by_pokedex[number]
        for number in numbers
        if number in references_by_pokedex
    ]
    link_count = len(references)
    if link_count <= 0:
        return []
    contribution_weight = Decimal("1") / Decimal(link_count)
    return [
        _build_link_row(
            card=card,
            reference=reference,
            link_position=index,
            link_count=link_count,
            contribution_weight=contribution_weight,
            match_method=POKEDEX_MATCH_METHOD,
            match_confidence=POKEDEX_MATCH_CONFIDENCE,
            is_hit=is_hit,
            hit_policy_version=hit_policy_version,
            source=POKEDEX_SOURCE,
            notes=None,
        )
        for index, reference in enumerate(references, start=1)
    ]


def _build_link_row(
    *,
    card: Dict[str, Any],
    reference: Dict[str, Any],
    link_position: int,
    link_count: int,
    contribution_weight: Decimal,
    match_method: str,
    match_confidence: Decimal,
    is_hit: bool,
    hit_policy_version: str,
    source: str,
    notes: Optional[str],
) -> Dict[str, Any]:
    return {
        "pokemon_canonical_card_id": str(card["id"]),
        "pokemon_reference_id": int(reference["id"]),
        "pokedex_number": int(reference["pokedex_number"]),
        "link_position": int(link_position),
        "link_count": int(link_count),
        "contribution_weight": float(round(contribution_weight, 8)),
        "match_method": match_method,
        "match_confidence": float(match_confidence),
        "is_hit_eligible": bool(is_hit),
        "hit_policy_version": hit_policy_version,
        "excluded_reason": None,
        "source": source,
        "notes": notes,
    }


def _build_reference_candidates(references: Sequence[Dict[str, Any]]) -> List[Dict[str, Any]]:
    candidates: List[Dict[str, Any]] = []
    for reference in references:
        keys = set()
        for field in ("display_name", "canonical_name"):
            key = normalize_pokemon_name_key(reference.get(field))
            if key:
                keys.add(key)
        if not keys:
            continue
        candidates.append({**reference, "match_keys": sorted(keys, key=len, reverse=True)})
    return candidates


def _contains_word_phrase(haystack: str, needle: str) -> bool:
    return f" {needle} " in f" {haystack} "


def _strip_card_suffixes(card_key: str) -> str:
    tokens = card_key.split()
    while tokens:
        last = tokens[-1]
        last_two = " ".join(tokens[-2:]) if len(tokens) >= 2 else ""
        if last_two in CARD_SUFFIX_KEYS:
            tokens = tokens[:-2]
            continue
        if last in CARD_SUFFIX_KEYS:
            tokens = tokens[:-1]
            continue
        break
    return " ".join(tokens)


def _is_pokemon_card(card: Dict[str, Any]) -> bool:
    return normalize_pokemon_name_key(card.get("supertype")) == "pokemon"


def _has_hit_rarity(card: Dict[str, Any], config_map: Dict[str, Any]) -> bool:
    rarity = str(card.get("rarity") or "").strip()
    if not rarity:
        return False
    rarity_key = normalize_rarity_key(rarity)
    config = _config_for_card(card, config_map)
    if config is not None:
        try:
            if is_hit_card({"rarity": rarity}, config):
                return True
        except Exception:
            logger.debug("Falling back to generic hit rarity policy for rarity=%r", rarity, exc_info=True)
    return rarity_key in FALLBACK_HIT_RARITY_KEYS


def _config_for_card(card: Dict[str, Any], config_map: Dict[str, Any]) -> Optional[Any]:
    key = str(card.get("set_canonical_key") or "").strip()
    if not key:
        return None
    return config_map.get(key)


def _pokedex_numbers(card: Dict[str, Any]) -> List[int]:
    value = card.get("national_pokedex_numbers")
    if not isinstance(value, list):
        return []
    numbers: List[int] = []
    for item in value:
        try:
            number = int(item)
        except (TypeError, ValueError):
            continue
        if number not in numbers:
            numbers.append(number)
    return numbers


def _card_sample(card: Dict[str, Any], *, reason: str) -> Dict[str, Any]:
    return {
        "id": card.get("id"),
        "name": card.get("name"),
        "set_id": card.get("set_id"),
        "set_name": card.get("set_name"),
        "canonical_key": card.get("set_canonical_key"),
        "number": card.get("number"),
        "rarity": card.get("rarity"),
        "supertype": card.get("supertype"),
        "subtypes": card.get("subtypes") if isinstance(card.get("subtypes"), list) else [],
        "reason": reason,
    }


def _rarity_label(card: Dict[str, Any]) -> str:
    return str(card.get("rarity") or "<null>").strip() or "<null>"


def _build_per_set_summary(
    cards: Sequence[Dict[str, Any]],
    generated_rows: Sequence[Dict[str, Any]],
    link_result: Dict[str, Any],
) -> List[Dict[str, Any]]:
    _ = link_result
    cards_by_set: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
    links_by_card: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
    for card in cards:
        cards_by_set[str(card.get("set_id"))].append(card)
    for row in generated_rows:
        links_by_card[str(row.get("pokemon_canonical_card_id"))].append(row)

    summaries: List[Dict[str, Any]] = []
    for set_id, set_cards in sorted(cards_by_set.items(), key=lambda item: str((item[1][0] or {}).get("set_name") or "")):
        set_name = set_cards[0].get("set_name")
        canonical_key = set_cards[0].get("set_canonical_key")
        linked_cards = {
            str(card.get("id"))
            for card in set_cards
            if links_by_card.get(str(card.get("id")))
        }
        summaries.append(
            {
                "set_id": set_id,
                "set_name": set_name,
                "canonical_key": canonical_key,
                "cards_scanned": len(set_cards),
                "pokemon_cards": sum(1 for card in set_cards if _is_pokemon_card(card)),
                "hit_eligible_pokemon_cards": sum(
                    1
                    for card in set_cards
                    if any(row.get("is_hit_eligible") for row in links_by_card.get(str(card.get("id")), []))
                ),
                "linked_cards": len(linked_cards),
                "links_generated": sum(len(links_by_card.get(str(card.get("id")), [])) for card in set_cards),
            }
        )
    return summaries


def _resolve_set_key(set_key: Optional[str], registry: Dict[str, Any]) -> Dict[str, Any]:
    from backend.scripts.run_pokemon_set_scrape import normalize_set_key_filter

    return normalize_set_key_filter(set_key, registry)


def _paged_select(query: Any, *, page_size: int = 1000) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    start = 0
    while True:
        result = query.range(start, start + page_size - 1).execute()
        page_rows = list(result.data or [])
        rows.extend(page_rows)
        if len(page_rows) < page_size:
            break
        start += page_size
    return rows


def _chunked(values: Sequence[Any], size: int) -> Iterable[Sequence[Any]]:
    for index in range(0, len(values), size):
        yield values[index:index + size]


def _jsonable(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(key): _jsonable(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_jsonable(item) for item in value]
    if isinstance(value, tuple):
        return [_jsonable(item) for item in value]
    if isinstance(value, set):
        return sorted(_jsonable(item) for item in value)
    if isinstance(value, Decimal):
        return float(value)
    return value


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except PokemonCardDesirabilityLinksError as exc:
        print(f"[pokemon-card-desirability-links][ERROR] {exc}", file=sys.stderr)
        raise SystemExit(1)
