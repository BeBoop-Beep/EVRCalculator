from __future__ import annotations

import logging
import os
import random
import re
import time
from typing import Any, Callable, Dict, Generator, Optional, Set

import requests

logger = logging.getLogger(__name__)

DEFAULT_BASE_URL = "https://api.scrydex.com/pokemon/v1/en"
DEFAULT_PAGE_SIZE = 100
DEFAULT_CONNECT_TIMEOUT = 10.0
DEFAULT_READ_TIMEOUT = 60.0
DEFAULT_MAX_ATTEMPTS = 4
DEFAULT_BACKOFF_BASE_SECONDS = 1.0
DEFAULT_KEYLESS_DELAY_SECONDS = 2.1
RETRYABLE_STATUS_CODES = frozenset({408, 425, 429, 500, 502, 503, 504})


class ScrydexPokemonAPIError(RuntimeError):
    def __init__(
        self,
        message: str,
        *,
        status_code: Optional[int] = None,
        retryable: bool = False,
        original: Optional[BaseException] = None,
    ) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.retryable = retryable
        self.original = original


def _canonical_expansion_name(value: Any) -> str:
    text = str(value or "").strip().casefold()
    # Internal modern configs sometimes keep the provider-facing "ME:" prefix;
    # Scrydex names the same English expansions without that series prefix.
    text = re.sub(r"^(?:me|mega\s+evolution)\s*[:\-]\s*", "", text)
    return " ".join(re.sub(r"[^a-z0-9]+", " ", text).split())


def _front_image(images: Any) -> Dict[str, Any]:
    if isinstance(images, dict):
        return images
    if not isinstance(images, list):
        return {}
    for image in images:
        if isinstance(image, dict) and str(image.get("type") or "").casefold() == "front":
            return image
    return next((image for image in images if isinstance(image, dict)), {})


class ScrydexPokemonClient:
    """Small Scrydex adapter exposing the same card-image interface as PokemonTCGAPIClient.

    Authentication is optional. When SCRYDEX_API_KEY and SCRYDEX_TEAM_ID are both
    configured they are sent; otherwise requests use Scrydex's reduced-rate
    unauthenticated access and are deliberately throttled.
    """

    def __init__(
        self,
        api_key: Optional[str] = None,
        team_id: Optional[str] = None,
        base_url: Optional[str] = None,
        *,
        session: Optional[Any] = None,
        connect_timeout: float = DEFAULT_CONNECT_TIMEOUT,
        read_timeout: float = DEFAULT_READ_TIMEOUT,
        max_attempts: int = DEFAULT_MAX_ATTEMPTS,
        backoff_base_seconds: float = DEFAULT_BACKOFF_BASE_SECONDS,
        sleep: Callable[[float], None] = time.sleep,
        jitter: Callable[[float, float], float] = random.uniform,
    ) -> None:
        self.api_key = str(api_key or os.getenv("SCRYDEX_API_KEY") or "").strip() or None
        self.team_id = str(team_id or os.getenv("SCRYDEX_TEAM_ID") or "").strip() or None
        self.base_url = (base_url or os.getenv("SCRYDEX_POKEMON_BASE_URL") or DEFAULT_BASE_URL).rstrip("/")
        self.connect_timeout = float(connect_timeout)
        self.read_timeout = float(read_timeout)
        self.max_attempts = max(1, int(max_attempts))
        self.backoff_base_seconds = float(backoff_base_seconds)
        self._session = session if session is not None else requests
        self._sleep = sleep
        self._jitter = jitter
        self.request_retries = 0

    @property
    def authenticated(self) -> bool:
        return bool(self.api_key and self.team_id)

    def _headers(self) -> Dict[str, str]:
        headers = {"Accept": "application/json", "User-Agent": "EVRCalculator/1.0"}
        if self.authenticated:
            headers["X-Api-Key"] = str(self.api_key)
            headers["X-Team-ID"] = str(self.team_id)
        return headers

    def _retry_delay(self, attempt: int) -> float:
        base = self.backoff_base_seconds * (2 ** (attempt - 1))
        delay = max(0.0, base + self._jitter(0.0, base * 0.1))
        if not self.authenticated:
            delay = max(delay, DEFAULT_KEYLESS_DELAY_SECONDS)
        return delay

    def _request_json(self, path: str, params: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        last_error: Optional[BaseException] = None
        for attempt in range(1, self.max_attempts + 1):
            response = None
            try:
                response = self._session.get(
                    f"{self.base_url}{path}",
                    params=params or {},
                    headers=self._headers(),
                    timeout=(self.connect_timeout, self.read_timeout),
                )
            except (requests.Timeout, requests.ConnectionError) as exc:
                last_error = exc
                if attempt >= self.max_attempts:
                    raise ScrydexPokemonAPIError(
                        f"Scrydex request to {path} failed after {attempt} attempts: {exc}",
                        retryable=True,
                        original=exc,
                    ) from exc
                self.request_retries += 1
                self._sleep(self._retry_delay(attempt))
                continue
            except requests.RequestException as exc:
                raise ScrydexPokemonAPIError(
                    f"Scrydex request to {path} failed: {exc}", original=exc
                ) from exc

            status = int(response.status_code)
            if status in RETRYABLE_STATUS_CODES and attempt < self.max_attempts:
                self.request_retries += 1
                retry_after = response.headers.get("Retry-After")
                try:
                    delay = float(retry_after) if retry_after is not None else self._retry_delay(attempt)
                except (TypeError, ValueError):
                    delay = self._retry_delay(attempt)
                self._sleep(max(DEFAULT_KEYLESS_DELAY_SECONDS if not self.authenticated else 0.0, min(delay, 30.0)))
                continue
            if status >= 400:
                raise ScrydexPokemonAPIError(
                    f"Scrydex request to {path} failed with HTTP {status}.",
                    status_code=status,
                    retryable=status in RETRYABLE_STATUS_CODES,
                )
            try:
                payload = response.json()
            except ValueError as exc:
                raise ScrydexPokemonAPIError(
                    f"Scrydex returned invalid JSON from {path}: {exc}", original=exc
                ) from exc
            if not isinstance(payload, dict):
                raise ScrydexPokemonAPIError(f"Scrydex returned a non-object payload from {path}")
            return payload

        raise ScrydexPokemonAPIError(
            f"Scrydex request to {path} failed: {last_error}", retryable=True, original=last_error
        )

    def resolve_set(self, set_name: str) -> Dict[str, str]:
        canonical = _canonical_expansion_name(set_name)
        if not canonical:
            raise ScrydexPokemonAPIError("Scrydex expansion name is required")

        # Phrase search is intentionally broader than exact search because punctuation
        # differs between some provider/internal names (e.g. "30th Celebration:
        # Classic Collection"). We still accept ONLY one normalized exact identity.
        payload = self._request_json(
            "/expansions",
            {
                "q": f'name:"{canonical}"',
                "page": 1,
                "pageSize": 50,
                "select": "id,name,series,total,printed_total,release_date,logo,symbol",
            },
        )
        rows = [row for row in (payload.get("data") or []) if isinstance(row, dict)]
        exact = [row for row in rows if _canonical_expansion_name(row.get("name")) == canonical]
        if len(exact) != 1:
            raise ScrydexPokemonAPIError(
                f"Scrydex expansion resolution for {set_name!r} expected one exact match; found {len(exact)}"
            )
        row = exact[0]
        return {"id": str(row.get("id") or ""), "name": str(row.get("name") or "")}

    def iter_cards_for_set(
        self,
        set_id: str,
        page_size: int = DEFAULT_PAGE_SIZE,
        rate_limit_delay: float = 0.1,
    ) -> Generator[Dict[str, Optional[str]], None, None]:
        safe_page_size = max(1, min(int(page_size or DEFAULT_PAGE_SIZE), DEFAULT_PAGE_SIZE))
        delay = max(float(rate_limit_delay or 0.0), DEFAULT_KEYLESS_DELAY_SECONDS if not self.authenticated else 0.0)
        page = 1
        seen_ids: Set[str] = set()
        reported_total: Optional[int] = None

        while True:
            payload = self._request_json(
                f"/expansions/{set_id}/cards",
                {
                    "page": page,
                    "pageSize": safe_page_size,
                    "select": "id,name,number,rarity,artist,images,expansion",
                },
            )
            rows = payload.get("data") or []
            if not isinstance(rows, list):
                raise ScrydexPokemonAPIError(
                    f"Scrydex returned an invalid cards payload for expansion {set_id!r}"
                )
            if payload.get("totalCount") is not None:
                try:
                    reported_total = int(payload.get("totalCount"))
                except (TypeError, ValueError) as exc:
                    raise ScrydexPokemonAPIError(
                        f"Scrydex returned invalid totalCount for expansion {set_id!r}"
                    ) from exc

            new_count = 0
            for raw in rows:
                if not isinstance(raw, dict):
                    continue
                card_id = str(raw.get("id") or "").strip()
                if not card_id or card_id in seen_ids:
                    continue
                seen_ids.add(card_id)
                new_count += 1
                image = _front_image(raw.get("images"))
                expansion = raw.get("expansion") if isinstance(raw.get("expansion"), dict) else {}
                yield {
                    "pokemon_tcg_api_id": card_id,
                    "set_id": str(expansion.get("id") or set_id),
                    "set_name": str(expansion.get("name") or ""),
                    "number": str(raw.get("number") or "").strip() or None,
                    "name": str(raw.get("name") or "").strip() or None,
                    "rarity": str(raw.get("rarity") or "").strip() or None,
                    "artist": str(raw.get("artist") or "").strip() or None,
                    "image_small_url": str(image.get("small") or "").strip() or None,
                    "image_large_url": str(image.get("large") or image.get("medium") or "").strip() or None,
                    "metadata_provider": "scrydex",
                }

            if reported_total is not None and len(seen_ids) >= reported_total:
                return
            if not rows:
                if reported_total not in (None, 0) and len(seen_ids) < reported_total:
                    raise ScrydexPokemonAPIError(
                        f"Scrydex pagination stalled for {set_id!r}: {len(seen_ids)}/{reported_total}"
                    )
                return
            if len(rows) < safe_page_size and reported_total is None:
                return
            if new_count == 0:
                raise ScrydexPokemonAPIError(
                    f"Scrydex pagination repeated without progress for {set_id!r} on page {page}"
                )
            page += 1
            if page > 500:
                raise ScrydexPokemonAPIError(f"Scrydex pagination safety guard exceeded for {set_id!r}")
            if delay > 0:
                self._sleep(delay)
