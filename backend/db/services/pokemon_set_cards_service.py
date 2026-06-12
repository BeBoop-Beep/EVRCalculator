from __future__ import annotations

import logging
import re
import time
from typing import Any, Dict, List, Optional, Tuple

from backend.db.clients.supabase_client import public_read_client

logger = logging.getLogger(__name__)


class PokemonSetCardsError(Exception):
    def __init__(self, status_code: int, message: str, code: str) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.message = message
        self.code = code


def _to_optional_str(value: Any) -> Optional[str]:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _to_optional_float(value: Any) -> Optional[float]:
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return None
    return parsed if parsed >= 0 else None


def _normalize_name(value: Any) -> Optional[str]:
    raw = _to_optional_str(value)
    if not raw:
        return None
    return re.sub(r"\s+", " ", raw).strip().lower()


def _normalize_number(value: Any) -> Optional[str]:
    raw = _to_optional_str(value)
    if not raw:
        return None
    return raw.replace(" ", "").lower()


def _resolve_card_number(card: Dict[str, Any]) -> Optional[str]:
    return (
        _to_optional_str(card.get("card_number"))
        or _to_optional_str(card.get("collector_number"))
        or _to_optional_str(card.get("number"))
    )


def _resolve_image_small(card: Dict[str, Any]) -> Optional[str]:
    return (
        _to_optional_str(card.get("image_small_url"))
        or _to_optional_str(card.get("small_image_url"))
        or _to_optional_str(card.get("image_url"))
    )


def _resolve_image_large(card: Dict[str, Any]) -> Optional[str]:
    return (
        _to_optional_str(card.get("image_large_url"))
        or _to_optional_str(card.get("large_image_url"))
        or _to_optional_str(card.get("image_url"))
    )


def _resolve_market_price(card: Dict[str, Any]) -> Optional[float]:
    for key in ("market_price", "estimated_market_price"):
        value = _to_optional_float(card.get(key))
        if value is not None:
            return value
    return None


def _card_quality_score(card: Dict[str, Any]) -> int:
    score = 0
    if _resolve_image_small(card) or _resolve_image_large(card):
        score += 3
    if _resolve_market_price(card) is not None:
        score += 2
    if _to_optional_str(card.get("rarity")):
        score += 1
    if _resolve_card_number(card):
        score += 1
    if _to_optional_str(card.get("name")):
        score += 1
    return score


def _build_dedupe_key(set_id: str, card: Dict[str, Any]) -> str:
    # Prefer API-native card identity when available.
    pokemon_tcg_api_id = _to_optional_str(card.get("pokemon_tcg_api_id"))
    if pokemon_tcg_api_id:
        return f"pokemon_tcg_api_id:{pokemon_tcg_api_id}"

    normalized_number = _normalize_number(_resolve_card_number(card))
    normalized_name = _normalize_name(card.get("name"))
    if normalized_number and normalized_name:
        return f"set_id+card_number+normalized_name:{set_id}:{normalized_number}:{normalized_name}"

    if normalized_number:
        return f"set_id+card_number:{set_id}:{normalized_number}"

    if normalized_name:
        return f"set_id+normalized_name:{set_id}:{normalized_name}"

    return f"cards.id:{_to_optional_str(card.get('id')) or ''}"


def _sort_key(card: Dict[str, Any]) -> Tuple[int, Any, Any, str]:
    number = _resolve_card_number(card)
    if number:
        compact = number.replace(" ", "")
        front = compact.split("/", 1)[0]
        numeric_match = re.fullmatch(r"(\d+)([a-zA-Z]*)", front)
        if numeric_match:
            suffix = numeric_match.group(2).lower()
            return (0, int(numeric_match.group(1)), suffix, compact.lower())

        mixed_match = re.search(r"(\d+)", front)
        if mixed_match:
            return (1, int(mixed_match.group(1)), front.lower(), compact.lower())

        return (2, front.lower(), "", compact.lower())

    name = _to_optional_str(card.get("name")) or ""
    return (3, name.lower(), "", "")


def get_pokemon_set_cards_payload(set_id: str) -> Dict[str, Any]:
    total_started = time.perf_counter()
    resolved_set_id = _to_optional_str(set_id)
    if not resolved_set_id:
        raise PokemonSetCardsError(
            status_code=400,
            message="set_id is required",
            code="POKEMON_SET_ID_REQUIRED",
        )

    try:
        set_result = (
            public_read_client.table("sets")
            .select("id,name,canonical_key,pokemon_api_set_id")
            .eq("id", resolved_set_id)
            .maybe_single()
            .execute()
        )
        set_row = set_result.data if set_result else None
    except Exception:
        logger.exception("[pokemon-set-cards] set lookup failed set_id=%s", resolved_set_id)
        raise PokemonSetCardsError(
            status_code=500,
            message="Failed to load set metadata",
            code="POKEMON_SET_LOOKUP_FAILED",
        )

    if not set_row:
        raise PokemonSetCardsError(
            status_code=404,
            message="Pokemon set not found",
            code="POKEMON_SET_NOT_FOUND",
        )

    cards_started = time.perf_counter()
    try:
        cards_result = (
            public_read_client.table("pokemon_canonical_cards")
            .select(
                "id,set_id,pokemon_tcg_api_card_id,name,supertype,subtypes,rarity,"
                "number,printed_number,national_pokedex_numbers,image_small_url,image_large_url"
            )
            .eq("set_id", resolved_set_id)
            .execute()
        )
        raw_cards = list(cards_result.data or [])
    except Exception:
        logger.exception("[pokemon-set-cards] cards query failed set_id=%s", resolved_set_id)
        raise PokemonSetCardsError(
            status_code=500,
            message="Failed to load canonical cards for set",
            code="POKEMON_SET_CARDS_QUERY_FAILED",
        )
    cards_ms = (time.perf_counter() - cards_started) * 1000

    cards: List[Dict[str, Any]] = []
    for card in raw_cards:
        cards.append(
            {
                "id": _to_optional_str(card.get("id")),
                "name": _to_optional_str(card.get("name")),
                "set_id": _to_optional_str(card.get("set_id")) or resolved_set_id,
                "set_name": _to_optional_str(set_row.get("name")),
                "pokemon_tcg_api_card_id": _to_optional_str(card.get("pokemon_tcg_api_card_id")),
                "card_number": _to_optional_str(card.get("number")),
                "number": _to_optional_str(card.get("number")),
                "printed_number": _to_optional_str(card.get("printed_number")),
                "rarity": _to_optional_str(card.get("rarity")),
                "supertype": _to_optional_str(card.get("supertype")),
                "subtypes": card.get("subtypes") if isinstance(card.get("subtypes"), list) else [],
                "national_pokedex_numbers": (
                    card.get("national_pokedex_numbers")
                    if isinstance(card.get("national_pokedex_numbers"), list)
                    else []
                ),
                "image_small_url": _resolve_image_small(card),
                "image_large_url": _resolve_image_large(card),
                "market_price": None,
                "tcgplayer_product_id": None,
            }
        )

    cards.sort(key=_sort_key)

    return {
        "set": {
            "id": _to_optional_str(set_row.get("id")) or resolved_set_id,
            "name": _to_optional_str(set_row.get("name")),
            "slug": _to_optional_str(set_row.get("canonical_key")),
            "pokemon_api_set_id": _to_optional_str(set_row.get("pokemon_api_set_id")),
        },
        "cards": cards,
        "meta": {
            "dedupe": {
                "strategy": "none: pokemon_canonical_cards is already the checklist source",
                "input_count": len(raw_cards),
                "output_count": len(cards),
                "removed_duplicates": 0,
            },
            "sources": {
                "cards": "pokemon_canonical_cards",
            },
            "timings": {
                "cards_query_ms": round(cards_ms, 3),
                "total_backend_ms": round((time.perf_counter() - total_started) * 1000, 3),
            },
        },
    }
