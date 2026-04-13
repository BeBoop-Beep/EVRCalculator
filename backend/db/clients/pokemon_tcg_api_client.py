import json
import os
import time
from typing import Dict, Generator, Optional

import requests


DEFAULT_BASE_URL = "https://api.pokemontcg.io/v2"
DEFAULT_PAGE_SIZE = 250
DEFAULT_SELECT_FIELDS = "id,name,number,images.small,images.large,set.id,set.name"


class PokemonTCGAPIError(RuntimeError):
    """Raised when the Pokemon TCG API request cannot be completed successfully."""


class PokemonTCGAPIClient:
    def __init__(self, api_key: Optional[str] = None, base_url: Optional[str] = None):
        self.api_key = api_key or os.getenv("POKEMON_TCG_API_KEY")
        if not self.api_key:
            raise RuntimeError("Missing POKEMON_TCG_API_KEY environment variable")

        self.base_url = (base_url or os.getenv("POKEMON_TCG_BASE_URL") or DEFAULT_BASE_URL).rstrip("/")

    def resolve_set(self, set_name: str) -> Dict[str, str]:
        response = self._request_json(
            "/sets",
            {
                "q": f'name:\"{set_name}\"',
                "select": "id,name",
                "pageSize": 10,
            },
        )
        data = response.get("data") or []
        if not data:
            raise PokemonTCGAPIError(f"Pokemon TCG API returned no set for name '{set_name}'")

        exact_match = next(
            (item for item in data if (item.get("name") or "").strip().lower() == set_name.strip().lower()),
            None,
        )
        if exact_match:
            return exact_match

        if len(data) == 1:
            return data[0]

        raise PokemonTCGAPIError(f"Pokemon TCG API returned multiple sets for '{set_name}'")

    def iter_cards_for_set(
        self,
        set_id: str,
        page_size: int = DEFAULT_PAGE_SIZE,
        select_fields: str = DEFAULT_SELECT_FIELDS,
        rate_limit_delay: float = 0.1,
    ) -> Generator[Dict[str, Optional[str]], None, None]:
        page = 1

        while True:
            response = self._request_json(
                "/cards",
                {
                    "q": f"set.id:{set_id}",
                    "page": page,
                    "pageSize": min(page_size, DEFAULT_PAGE_SIZE),
                    "orderBy": "number",
                    # "select": select_fields,
                },
            )
            cards = response.get("data") or []
            if not cards:
                break

            for card in cards:
                yield self._normalize_card(card)

            total_count = response.get("totalCount") or 0
            page_size_value = response.get("pageSize") or page_size
            if page * page_size_value >= total_count:
                break

            page += 1
            if rate_limit_delay > 0:
                time.sleep(rate_limit_delay)

    def _normalize_card(self, card: Dict[str, object]) -> Dict[str, Optional[str]]:
        images = card.get("images") or {}
        set_data = card.get("set") or {}
        return {
            "pokemon_tcg_api_id": card.get("id"),
            "set_id": set_data.get("id"),
            "set_name": set_data.get("name"),
            "number": card.get("number"),
            "name": card.get("name"),
            "image_small_url": images.get("small"),
            "image_large_url": images.get("large"),
        }

    def _request_json(self, path: str, params: Dict[str, object]) -> Dict[str, object]:
        try:
            response = requests.get(
                f"{self.base_url}{path}",
                params=params,
                headers={
                    "Accept": "application/json",
                    "X-Api-Key": self.api_key,
                    "User-Agent": "EVRCalculator/1.0",
                },
                timeout=30,
            )

            if response.status_code == 429:
                retry_after = response.headers.get("Retry-After")
                raise PokemonTCGAPIError(
                    f"Pokemon TCG API rate limit exceeded. Retry after {retry_after or 'the cooldown window'}."
                )
            if response.status_code in {401, 403}:
                raise PokemonTCGAPIError(
                    "Pokemon TCG API request was rejected. Verify the POKEMON_TCG_API_KEY value."
                )

            response.raise_for_status()
            return response.json()

        except requests.RequestException as exc:
            raise PokemonTCGAPIError(f"Pokemon TCG API request failed: {exc}") from exc