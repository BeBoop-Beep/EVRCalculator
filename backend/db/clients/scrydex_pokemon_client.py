from __future__ import annotations

import logging
import os
import re
import time
from typing import Any, Dict, Iterator, List, Optional

import requests

logger = logging.getLogger(__name__)

SCRYDEX_BASE_URL = "https://api.scrydex.com/pokemon/v1/en"
SCRYDEX_PAGE_SIZE = 100
SCRYDEX_MAX_RETRIES = 4
SCRYDEX_CONNECT_TIMEOUT = 8.0
SCRYDEX_READ_TIMEOUT = 45.0
SCRYDEX_KEYLESS_PAGE_DELAY_SECONDS = 2.1


class ScrydexPokemonError(RuntimeError):
    def __init__(self, message: str, *, status_code: Optional[int] = None) -> None:
        super().__init__(message)
        self.status_code = status_code


def _text(value: Any) -> Optional[str]:
    text = str(value or "").strip()
    return text or None


def _front_image(images: Any) -> Dict[str, Any]:
    if isinstance(images, dict):
        return images
    if not isinstance(images, list):
        return {}
    for row in images:
        if isinstance(row, dict) and str(row.get("type") or "").strip().lower() == "front":
            return row
    return next((row for row in images if isinstance(row, dict)), {})


def project_expansion_to_pokemontcg(expansion: Dict[str, Any]) -> Dict[str, Any]:
    """Project one Scrydex expansion into the legacy PokemonTCG set shape.

    Existing onboarding/config code intentionally consumes one provider-neutral
    compatibility shape. Keeping the projection here avoids teaching every
    downstream consumer a second field vocabulary.
    """
    return {
        "id": expansion.get("id"),
        "name": expansion.get("name"),
        "series": expansion.get("series"),
        "ptcgoCode": expansion.get("code"),
        "printedTotal": expansion.get("printed_total")
        if expansion.get("printed_total") is not None
        else expansion.get("printedTotal"),
        "total": expansion.get("total"),
        "releaseDate": (
            str(expansion.get("release_date") or expansion.get("releaseDate") or "").replace("/", "-")
            or None
        ),
        "images": {
            "symbol": expansion.get("symbol"),
            "logo": expansion.get("logo"),
        },
    }


def project_card_to_pokemontcg(card: Dict[str, Any], *, fallback_set_id: str) -> Dict[str, Any]:
    """Project one Scrydex card into the legacy PokemonTCG card shape."""
    expansion = card.get("expansion") if isinstance(card.get("expansion"), dict) else {}
    image = _front_image(card.get("images"))
    return {
        "id": card.get("id"),
        "name": card.get("name"),
        "number": card.get("number"),
        "printedNumber": card.get("printed_number") or card.get("printedNumber"),
        "supertype": card.get("supertype"),
        "subtypes": card.get("subtypes") if isinstance(card.get("subtypes"), list) else [],
        "rarity": card.get("rarity"),
        "artist": card.get("artist"),
        "nationalPokedexNumbers": (
            card.get("national_pokedex_numbers")
            if isinstance(card.get("national_pokedex_numbers"), list)
            else card.get("nationalPokedexNumbers")
            if isinstance(card.get("nationalPokedexNumbers"), list)
            else []
        ),
        "images": {
            "small": image.get("small"),
            "large": image.get("large") or image.get("medium"),
        },
        "set": {
            "id": expansion.get("id") or fallback_set_id,
            "name": expansion.get("name"),
            "series": expansion.get("series"),
            "printedTotal": expansion.get("printed_total")
            if expansion.get("printed_total") is not None
            else expansion.get("printedTotal"),
            "total": expansion.get("total"),
            "releaseDate": (
                str(expansion.get("release_date") or expansion.get("releaseDate") or "").replace("/", "-")
                or None
            ),
        },
    }


class ScrydexPokemonClient:
    """Bounded English-Pokemon Scrydex reader used as the current metadata fallback.

    The legacy pokemontcg.io source remains supported elsewhere. Scrydex is used
    when a newly released expansion/card checklist is not yet available there.
    Authentication is optional; when both SCRYDEX_API_KEY and SCRYDEX_TEAM_ID
    are present they are sent together, otherwise the documented keyless path is
    used with a conservative inter-page delay.
    """

    def __init__(
        self,
        *,
        api_key: Optional[str] = None,
        team_id: Optional[str] = None,
        base_url: str = SCRYDEX_BASE_URL,
        session: Optional[requests.Session] = None,
        sleep=time.sleep,
    ) -> None:
        self.api_key = _text(api_key) or _text(os.getenv("SCRYDEX_API_KEY"))
        self.team_id = _text(team_id) or _text(os.getenv("SCRYDEX_TEAM_ID"))
        self.base_url = base_url.rstrip("/")
        self.session = session or requests.Session()
        self.sleep = sleep

    def _headers(self) -> Dict[str, str]:
        headers = {"Accept": "application/json", "User-Agent": "EVRCalculator/1.0"}
        # Scrydex authenticated requests require BOTH values. Sending a legacy
        # PokemonTCG key as though it were a Scrydex credential can turn an
        # otherwise-valid keyless request into a 401, so partial credentials
        # deliberately fall back to anonymous access.
        if self.api_key and self.team_id:
            headers["X-Api-Key"] = self.api_key
            headers["X-Team-ID"] = self.team_id
        return headers

    def _request_json(self, path: str, params: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        last_error: Optional[Exception] = None
        for attempt in range(1, SCRYDEX_MAX_RETRIES + 1):
            try:
                response = self.session.get(
                    f"{self.base_url}{path}",
                    params=params or {},
                    headers=self._headers(),
                    timeout=(SCRYDEX_CONNECT_TIMEOUT, SCRYDEX_READ_TIMEOUT),
                )
            except requests.RequestException as exc:
                last_error = exc
                if attempt < SCRYDEX_MAX_RETRIES:
                    self.sleep(float(2 ** (attempt - 1)))
                    continue
                raise ScrydexPokemonError(
                    f"Scrydex request failed after {SCRYDEX_MAX_RETRIES} attempts: {type(exc).__name__}"
                ) from exc

            if response.status_code == 429 and attempt < SCRYDEX_MAX_RETRIES:
                retry_after = response.headers.get("Retry-After")
                try:
                    delay = min(float(retry_after), 30.0) if retry_after else float(2 ** (attempt - 1))
                except (TypeError, ValueError):
                    delay = float(2 ** (attempt - 1))
                self.sleep(delay)
                continue
            if response.status_code >= 500 and attempt < SCRYDEX_MAX_RETRIES:
                self.sleep(float(2 ** (attempt - 1)))
                continue
            if response.status_code >= 400:
                raise ScrydexPokemonError(
                    f"Scrydex request failed HTTP {response.status_code} path={path}",
                    status_code=response.status_code,
                )
            try:
                payload = response.json()
            except ValueError as exc:
                raise ScrydexPokemonError(f"Scrydex returned invalid JSON for path={path}") from exc
            if not isinstance(payload, dict):
                raise ScrydexPokemonError(f"Scrydex returned a non-object payload for path={path}")
            return payload

        raise ScrydexPokemonError(f"Scrydex request failed: {last_error}")

    def get_set(self, set_id: str) -> Dict[str, Any]:
        payload = self._request_json(f"/expansions/{set_id}")
        data = payload.get("data")
        if not isinstance(data, dict):
            raise ScrydexPokemonError(f"Unexpected Scrydex expansion payload for {set_id!r}")
        return project_expansion_to_pokemontcg(data)

    def resolve_set(self, set_name: str) -> Dict[str, Any]:
        raw_name = str(set_name or "").strip()
        # TCGplayer prefixes current Mega Evolution catalog names with ME/ME##,
        # while Scrydex stores the official expansion name without that provider
        # prefix (e.g. "ME: 30th Celebration" -> "30th Celebration").
        search_name = re.sub(
            r"^ME(?:\\d+(?:\\.\\d+)?)?\\s*:\\s*",
            "",
            raw_name,
            flags=re.IGNORECASE,
        ).strip() or raw_name
        target = " ".join(search_name.casefold().split())
        payload = self._request_json(
            "/expansions",
            {
                "q": f'name:"{search_name}"',
                "page": 1,
                "pageSize": 50,
                "select": "id,name,series,code,total,printed_total,release_date,logo,symbol",
            },
        )
        rows = payload.get("data")
        if not isinstance(rows, list):
            raise ScrydexPokemonError(f"Unexpected Scrydex expansion search payload for {set_name!r}")
        projected = [project_expansion_to_pokemontcg(row) for row in rows if isinstance(row, dict)]
        exact = [
            row for row in projected
            if " ".join(str(row.get("name") or "").strip().casefold().split()) == target
        ]
        if len(exact) == 1:
            return exact[0]
        if len(projected) == 1:
            return projected[0]
        raise ScrydexPokemonError(
            f"Could not uniquely resolve Scrydex expansion {set_name!r}; candidates={len(projected)}"
        )

    def fetch_cards_for_set(self, set_id: str) -> List[Dict[str, Any]]:
        cards: List[Dict[str, Any]] = []
        seen: set[str] = set()
        page = 1
        total_count: Optional[int] = None
        while page <= 500:
            payload = self._request_json(
                f"/expansions/{set_id}/cards",
                {
                    "page": page,
                    "pageSize": SCRYDEX_PAGE_SIZE,
                    "orderBy": "id",
                    "select": (
                        "id,name,number,printed_number,rarity,supertype,subtypes,"
                        "national_pokedex_numbers,artist,images,expansion"
                    ),
                },
            )
            rows = payload.get("data")
            if not isinstance(rows, list):
                raise ScrydexPokemonError(f"Unexpected Scrydex card payload for set {set_id!r}")
            raw_total = payload.get("totalCount")
            if raw_total is not None:
                try:
                    total_count = int(raw_total)
                except (TypeError, ValueError) as exc:
                    raise ScrydexPokemonError(
                        f"Unexpected Scrydex totalCount for set {set_id!r}: {raw_total!r}"
                    ) from exc
            for raw in rows:
                if not isinstance(raw, dict):
                    raise ScrydexPokemonError(f"Unexpected Scrydex card item for set {set_id!r}")
                projected = project_card_to_pokemontcg(raw, fallback_set_id=set_id)
                card_id = _text(projected.get("id"))
                if not card_id:
                    raise ScrydexPokemonError(f"Scrydex card missing id for set {set_id!r}")
                if card_id in seen:
                    continue
                seen.add(card_id)
                cards.append(projected)
            if not rows or (total_count is not None and len(cards) >= total_count):
                break
            page += 1
            if not (self.api_key and self.team_id):
                self.sleep(SCRYDEX_KEYLESS_PAGE_DELAY_SECONDS)

        if page > 500:
            raise ScrydexPokemonError(f"Scrydex pagination safety guard exceeded for {set_id!r}")
        if total_count is not None and len(cards) != total_count:
            raise ScrydexPokemonError(
                f"Scrydex count mismatch for {set_id!r}: fetched {len(cards)} of {total_count}"
            )
        return cards

    def iter_image_cards_for_set(self, set_id: str) -> Iterator[Dict[str, Any]]:
        for card in self.fetch_cards_for_set(set_id):
            images = card.get("images") if isinstance(card.get("images"), dict) else {}
            set_payload = card.get("set") if isinstance(card.get("set"), dict) else {}
            yield {
                "pokemon_tcg_api_id": card.get("id"),
                "set_id": set_payload.get("id") or set_id,
                "set_name": set_payload.get("name"),
                "number": card.get("number"),
                "name": card.get("name"),
                "image_small_url": images.get("small"),
                "image_large_url": images.get("large"),
            }
