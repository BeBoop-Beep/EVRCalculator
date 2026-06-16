from __future__ import annotations

import argparse
import json
import logging
import os
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence

from dotenv import load_dotenv

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))

from backend.scripts.build_pokemon_card_desirability_links import (  # noqa: E402
    DEFAULT_HIT_POLICY_VERSION,
    LINK_TABLE,
    build_valid_set_key_registry,
    is_hit_eligible_card,
)
from backend.desirability.normalization import normalize_pokemon_name_key  # noqa: E402
from backend.scripts.run_pokemon_set_scrape import normalize_set_key_filter  # noqa: E402


class PokemonCardDesirabilityLinksValidationError(RuntimeError):
    pass


def load_backend_env() -> None:
    env_path = Path(__file__).resolve().parents[1] / ".env"
    load_dotenv(env_path, override=False)


def get_supabase_client():
    from backend.db.clients.supabase_client import supabase

    return supabase


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Validate canonical Pokemon card desirability link coverage."
    )
    selector_group = parser.add_mutually_exclusive_group(required=True)
    selector_group.add_argument("--set-key", help="sets.canonical_key to validate")
    selector_group.add_argument("--all", action="store_true", help="Validate all sets")
    parser.add_argument(
        "--hit-policy-version",
        default=DEFAULT_HIT_POLICY_VERSION,
        help="Hit policy version expected on current links",
    )
    return parser


def main() -> int:
    args = build_parser().parse_args()
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)
    load_backend_env()
    report = validate_links(
        set_key=args.set_key,
        process_all=bool(args.all),
        hit_policy_version=args.hit_policy_version,
    )
    print(json.dumps(report, indent=2, sort_keys=True))
    failures = report["summary"]["pokemon_cards_with_pokedex_but_no_link"]
    failures += report["summary"]["pokemon_hit_eligible_cards_with_no_link"]
    failures += report["summary"]["links_with_missing_reference_rows"]
    failures += report["summary"]["cards_with_bad_contribution_weight_sum"]
    failures += report["summary"]["duplicate_link_position_issues"]
    return 1 if failures else 0


def validate_links(
    *,
    set_key: Optional[str],
    process_all: bool,
    hit_policy_version: str,
) -> Dict[str, Any]:
    if not set_key and not process_all:
        raise PokemonCardDesirabilityLinksValidationError("Choose --set-key or --all")

    client = get_supabase_client()
    registry = build_valid_set_key_registry()
    resolved_set_key = None
    if set_key:
        resolution = normalize_set_key_filter(set_key, registry)
        resolved_set_key = resolution.get("resolved_set_key_filter")
        if not resolved_set_key:
            raise PokemonCardDesirabilityLinksValidationError(f"Unknown set key {set_key!r}")

    sets = _load_sets(client, resolved_set_key)
    set_by_id = {str(row.get("id")): row for row in sets if row.get("id") is not None}
    cards = _load_cards(client, sorted(set_by_id.keys()))
    for card in cards:
        set_row = set_by_id.get(str(card.get("set_id"))) or {}
        card["set_canonical_key"] = set_row.get("canonical_key")
        card["set_name"] = set_row.get("name")

    links = _load_links(client, [str(card.get("id")) for card in cards if card.get("id")])
    references = _load_references(client)
    reference_ids = {int(row["id"]) for row in references if row.get("id") is not None}
    config_map = registry.get("config_map", {})

    links_by_card: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
    position_counts: Counter[tuple[str, int]] = Counter()
    for link in links:
        card_id = str(link.get("pokemon_canonical_card_id"))
        links_by_card[card_id].append(link)
        if link.get("link_position") is not None:
            position_counts[(card_id, int(link["link_position"]))] += 1

    pokemon_cards_with_pokedex_but_no_link = []
    pokemon_hit_eligible_cards_with_no_link = []
    links_with_missing_reference_rows = []
    cards_with_bad_contribution_weight_sum = []
    duplicate_link_position_issues = []
    multi_pokemon_cards = []
    fallback_created_links = []
    hit_counts_by_set_and_rarity: Counter[tuple[str, str, str]] = Counter()

    for card in cards:
        card_id = str(card.get("id") or "")
        card_links = links_by_card.get(card_id, [])
        is_pokemon = normalize_pokemon_name_key(card.get("supertype")) == "pokemon"
        has_pokedex = bool(card.get("national_pokedex_numbers"))
        is_hit = is_hit_eligible_card(card, config_map)

        if is_pokemon and has_pokedex and not card_links:
            pokemon_cards_with_pokedex_but_no_link.append(_card_sample(card))
        if is_hit and not card_links:
            pokemon_hit_eligible_cards_with_no_link.append(_card_sample(card))

        if card_links:
            weight_sum = sum(_to_float(link.get("contribution_weight")) or 0.0 for link in card_links)
            if abs(weight_sum - 1.0) > 0.0001:
                cards_with_bad_contribution_weight_sum.append(
                    {**_card_sample(card), "weight_sum": round(weight_sum, 8), "link_count": len(card_links)}
                )
            if len(card_links) > 1:
                multi_pokemon_cards.append(
                    {**_card_sample(card), "link_count": len(card_links), "weight_sum": round(weight_sum, 8)}
                )

        for link in card_links:
            reference_id = link.get("pokemon_reference_id")
            if reference_id is None or int(reference_id) not in reference_ids:
                links_with_missing_reference_rows.append({"card": _card_sample(card), "link": link})
            if str(link.get("match_method") or "") == "normalized_name_fallback":
                fallback_created_links.append({"card": _card_sample(card), "link": link})
            if link.get("is_hit_eligible"):
                hit_counts_by_set_and_rarity[
                    (
                        str(card.get("set_canonical_key") or card.get("set_id") or ""),
                        str(card.get("set_name") or ""),
                        str(card.get("rarity") or "<null>"),
                    )
                ] += 1

    for (card_id, position), count in position_counts.items():
        if count > 1:
            duplicate_link_position_issues.append(
                {"pokemon_canonical_card_id": card_id, "link_position": position, "count": count}
            )

    hit_counts_rows = [
        {
            "canonical_key": key[0],
            "set_name": key[1],
            "rarity": key[2],
            "hit_eligible_links": count,
        }
        for key, count in sorted(hit_counts_by_set_and_rarity.items())
    ]

    return {
        "status": "validated",
        "requested_set_key": set_key,
        "resolved_set_key": resolved_set_key,
        "hit_policy_version": hit_policy_version,
        "summary": {
            "sets_checked": len(sets),
            "canonical_cards_checked": len(cards),
            "links_checked": len(links),
            "pokemon_cards_with_pokedex_but_no_link": len(pokemon_cards_with_pokedex_but_no_link),
            "pokemon_hit_eligible_cards_with_no_link": len(pokemon_hit_eligible_cards_with_no_link),
            "links_with_missing_reference_rows": len(links_with_missing_reference_rows),
            "cards_with_bad_contribution_weight_sum": len(cards_with_bad_contribution_weight_sum),
            "duplicate_link_position_issues": len(duplicate_link_position_issues),
            "multi_pokemon_cards": len(multi_pokemon_cards),
            "fallback_created_links": len(fallback_created_links),
        },
        "samples": {
            "pokemon_cards_with_pokedex_but_no_link": pokemon_cards_with_pokedex_but_no_link[:50],
            "pokemon_hit_eligible_cards_with_no_link": pokemon_hit_eligible_cards_with_no_link[:50],
            "links_with_missing_reference_rows": links_with_missing_reference_rows[:25],
            "cards_with_bad_contribution_weight_sum": cards_with_bad_contribution_weight_sum[:50],
            "duplicate_link_position_issues": duplicate_link_position_issues[:50],
            "multi_pokemon_cards_and_weights": multi_pokemon_cards[:50],
            "fallback_created_links": fallback_created_links[:50],
        },
        "hit_eligible_link_counts_by_set_and_rarity": hit_counts_rows,
    }


def _load_sets(client: Any, set_key: Optional[str]) -> List[Dict[str, Any]]:
    query = client.table("sets").select("id,name,canonical_key").order("name")
    if set_key:
        query = query.eq("canonical_key", set_key)
    return _paged_select(query)


def _load_cards(client: Any, set_ids: Sequence[str]) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    for chunk in _chunked(set_ids, 200):
        rows.extend(
            _paged_select(
                client.table("pokemon_canonical_cards")
                .select("id,set_id,name,supertype,subtypes,rarity,number,national_pokedex_numbers")
                .in_("set_id", list(chunk))
                .order("number")
                .order("name")
            )
        )
    return rows


def _load_links(client: Any, card_ids: Sequence[str]) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    for chunk in _chunked(card_ids, 200):
        rows.extend(
            _paged_select(
                client.table(LINK_TABLE)
                .select(
                    "id,pokemon_canonical_card_id,pokemon_reference_id,pokedex_number,"
                    "link_position,link_count,contribution_weight,match_method,match_confidence,"
                    "is_hit_eligible,hit_policy_version,source,notes"
                )
                .in_("pokemon_canonical_card_id", list(chunk))
            )
        )
    return rows


def _load_references(client: Any) -> List[Dict[str, Any]]:
    return _paged_select(client.table("pokemon_reference").select("id,pokedex_number"))


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


def _to_float(value: Any) -> Optional[float]:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _card_sample(card: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "id": card.get("id"),
        "name": card.get("name"),
        "set_id": card.get("set_id"),
        "set_name": card.get("set_name"),
        "canonical_key": card.get("set_canonical_key"),
        "number": card.get("number"),
        "rarity": card.get("rarity"),
        "supertype": card.get("supertype"),
    }


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except PokemonCardDesirabilityLinksValidationError as exc:
        print(f"[pokemon-card-desirability-links-validate][ERROR] {exc}", file=sys.stderr)
        raise SystemExit(1)
