import json
import logging
import math
import os
import time
from typing import Dict, Generator, Optional, Set

import requests

logger = logging.getLogger(__name__)


DEFAULT_BASE_URL = "https://api.pokemontcg.io/v2"
DEFAULT_PAGE_SIZE = 100
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
        unique_yielded = 0
        known_total_count: Optional[int] = None
        max_pages: Optional[int] = None
        seen_ids: Set[str] = set()
        use_order_by: Optional[str] = "id"  # prefer stable id ordering; None = no orderBy

        while True:
            requested_page_size = min(page_size, DEFAULT_PAGE_SIZE)
            params: Dict[str, object] = {
                "q": f"set.id:{set_id}",
                "page": page,
                "pageSize": requested_page_size,
                # "select": select_fields,
            }
            if use_order_by:
                params["orderBy"] = use_order_by

            try:
                response = self._request_json("/cards", params)
            except PokemonTCGAPIError as exc:
                exc_str = str(exc)
                # Retry with smaller page size on 404
                if requested_page_size > 50 and "404" in exc_str:
                    requested_page_size = 50
                    params["pageSize"] = 50
                    response = self._request_json("/cards", params)
                # orderBy=id not supported → retry without orderBy
                elif use_order_by and ("400" in exc_str or "invalid" in exc_str.lower()):
                    use_order_by = None
                    params.pop("orderBy", None)
                    response = self._request_json("/cards", params)
                else:
                    raise

            raw_cards = response.get("data") or []
            page_total_count = response.get("totalCount") or 0

            if known_total_count is None and page_total_count:
                known_total_count = page_total_count
                max_pages = math.ceil(known_total_count / requested_page_size) + 5

            # De-duplicate: only yield cards with unseen IDs
            new_cards = []
            duplicates_this_page = 0
            for card in raw_cards:
                card_id = card.get("id")
                if card_id and card_id in seen_ids:
                    duplicates_this_page += 1
                else:
                    if card_id:
                        seen_ids.add(card_id)
                    new_cards.append(card)

            first_id = raw_cards[0].get("id") if raw_cards else None
            last_id = raw_cards[-1].get("id") if raw_cards else None

            logger.info(
                "[TCG API] set=%r page=%d pageSize=%d returned=%d new_unique=%d "
                "unique_yielded=%d totalCount=%d duplicates=%d first=%r last=%r orderBy=%r",
                set_id, page, requested_page_size, len(raw_cards), len(new_cards),
                unique_yielded + len(new_cards), page_total_count, duplicates_this_page,
                first_id, last_id, use_order_by,
            )
            print(
                f"[TCG API] set={set_id!r} page={page} pageSize={requested_page_size} "
                f"returned={len(raw_cards)} new_unique={len(new_cards)} "
                f"unique_yielded={unique_yielded + len(new_cards)} totalCount={page_total_count} "
                f"duplicates={duplicates_this_page} first={first_id!r} last={last_id!r}"
            )

            for card in new_cards:
                yield self._normalize_card(card)

            unique_yielded += len(new_cards)

            # Stop: empty page from API
            if not raw_cards:
                break

            # Stop: have all unique cards the API reports
            if known_total_count and unique_yielded >= known_total_count:
                break

            # Stop: short page AND no new unique cards → true end of set
            if len(raw_cards) < requested_page_size and not new_cards:
                break

            # Stop: short page with some new cards → keep going unless we have all
            if len(raw_cards) < requested_page_size and known_total_count and unique_yielded >= known_total_count:
                break

            # Safety guard: too many pages means unstable pagination
            if max_pages is not None and page >= max_pages:
                raise PokemonTCGAPIError(
                    f"Pagination safety guard exceeded for set {set_id!r}: "
                    f"reached page {page} (max {max_pages}) with only "
                    f"{unique_yielded}/{known_total_count} unique cards. "
                    f"Possible unstable ordering from the API."
                )

            page += 1
            if rate_limit_delay > 0:
                time.sleep(rate_limit_delay)
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