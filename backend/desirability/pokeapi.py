from __future__ import annotations

import logging
import time
from typing import Any, Dict, Iterable, List, Optional

import requests


logger = logging.getLogger(__name__)

POKEAPI_LIST_URL = "https://pokeapi.co/api/v2/pokemon?limit={limit}"
POKEAPI_DETAIL_URL = "https://pokeapi.co/api/v2/pokemon/{id}/"
DEFAULT_POKEMON_LIMIT = 1025


GENERATION_RANGES = (
    (1, 151, 1),
    (152, 251, 2),
    (252, 386, 3),
    (387, 493, 4),
    (494, 649, 5),
    (650, 721, 6),
    (722, 809, 7),
    (810, 905, 8),
    (906, 1025, 9),
)


class PokeAPIClient:
    def __init__(self, session: Optional[requests.Session] = None, timeout_seconds: float = 20.0):
        self.session = session or requests.Session()
        self.timeout_seconds = timeout_seconds

    def fetch_reference_rows(
        self,
        limit: int = DEFAULT_POKEMON_LIMIT,
        delay_seconds: float = 0.05,
    ) -> List[Dict[str, Any]]:
        logger.info("Fetching canonical Pokemon list from PokeAPI limit=%s", limit)
        list_response = self.session.get(
            POKEAPI_LIST_URL.format(limit=limit),
            timeout=self.timeout_seconds,
            headers={"User-Agent": "EVRCalculator-pokemon-desirability/1.0"},
        )
        list_response.raise_for_status()
        results = list_response.json().get("results") or []

        rows: List[Dict[str, Any]] = []
        for index, item in enumerate(results, start=1):
            pokemon_id = _extract_id_from_url(item.get("url")) or index
            if pokemon_id > limit:
                logger.info("Skipping Pokemon id=%s beyond configured limit=%s", pokemon_id, limit)
                continue

            detail = self.fetch_pokemon_detail(pokemon_id)
            rows.append(build_reference_row(detail))

            if delay_seconds > 0 and index < len(results):
                time.sleep(delay_seconds)

        logger.info("Fetched %s canonical Pokemon rows from PokeAPI", len(rows))
        return rows

    def fetch_pokemon_detail(self, pokemon_id: int) -> Dict[str, Any]:
        response = self.session.get(
            POKEAPI_DETAIL_URL.format(id=pokemon_id),
            timeout=self.timeout_seconds,
            headers={"User-Agent": "EVRCalculator-pokemon-desirability/1.0"},
        )
        response.raise_for_status()
        return response.json()


def build_reference_row(detail: Dict[str, Any]) -> Dict[str, Any]:
    pokedex_number = int(detail["id"])
    canonical_name = str(detail.get("name") or "").strip()
    sprites = detail.get("sprites") or {}
    other_sprites = sprites.get("other") or {}
    official_artwork = other_sprites.get("official-artwork") or {}

    return {
        "pokedex_number": pokedex_number,
        "canonical_name": canonical_name,
        "display_name": _display_name(canonical_name),
        "api_source": "pokeapi",
        "api_url": POKEAPI_DETAIL_URL.format(id=pokedex_number),
        "sprite_url": official_artwork.get("front_default") or sprites.get("front_default"),
        "generation": generation_for_pokedex_number(pokedex_number),
    }


def build_reference_upsert_payload(rows: Iterable[Dict[str, Any]]) -> List[Dict[str, Any]]:
    deduped: Dict[int, Dict[str, Any]] = {}
    for row in rows:
        pokedex_number = row.get("pokedex_number")
        if pokedex_number is None:
            continue
        deduped[int(pokedex_number)] = {
            "pokedex_number": int(pokedex_number),
            "canonical_name": row.get("canonical_name"),
            "display_name": row.get("display_name") or _display_name(row.get("canonical_name")),
            "api_source": row.get("api_source") or "pokeapi",
            "api_url": row.get("api_url") or POKEAPI_DETAIL_URL.format(id=int(pokedex_number)),
            "sprite_url": row.get("sprite_url"),
            "generation": row.get("generation") or generation_for_pokedex_number(int(pokedex_number)),
        }
    return [deduped[key] for key in sorted(deduped)]


def generation_for_pokedex_number(pokedex_number: int) -> Optional[int]:
    for low, high, generation in GENERATION_RANGES:
        if low <= pokedex_number <= high:
            return generation
    return None


def _extract_id_from_url(url: Optional[str]) -> Optional[int]:
    if not url:
        return None
    try:
        return int(str(url).rstrip("/").rsplit("/", 1)[-1])
    except ValueError:
        return None


def _display_name(canonical_name: Optional[str]) -> Optional[str]:
    if not canonical_name:
        return None
    return " ".join(part.capitalize() for part in str(canonical_name).replace("-", " ").split())

