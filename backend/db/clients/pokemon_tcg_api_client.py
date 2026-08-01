import logging
import math
import os
import random
import time
from dataclasses import dataclass
from typing import Any, Callable, Dict, Generator, List, Optional, Sequence, Set, Tuple

import requests

logger = logging.getLogger(__name__)


DEFAULT_BASE_URL = "https://api.pokemontcg.io/v2"
DEFAULT_PAGE_SIZE = 100

# Fields the image synchroniser actually consumes (see ``_normalize_card``).
#
# NOTE: the API does *not* support dotted sub-field selection. Asking for
# "images.small,images.large,set.id,set.name" is accepted with a 200 but returns
# ``images: null`` and ``set: null``, which would silently blank every image URL.
# Selecting the parent objects is the only spelling that returns the data, and it
# still trims a card from ~1543 to ~589 bytes by dropping attacks, legalities,
# tcgplayer pricing, etc.
DEFAULT_SELECT_FIELDS = "id,name,number,images,set"

DEFAULT_CONNECT_TIMEOUT = 10.0
DEFAULT_READ_TIMEOUT = 60.0
DEFAULT_MAX_ATTEMPTS = 4
DEFAULT_BACKOFF_BASE_SECONDS = 1.0
DEFAULT_MAX_RETRY_AFTER_SECONDS = 30.0

# Statuses worth asking again for. The provider behind api.pokemontcg.io returns
# 500 intermittently on identical requests, so these are the difference between a
# working sync and a dead one.
RETRYABLE_STATUS_CODES = frozenset({408, 425, 429, 500, 502, 503, 504})

# Never retried: the answer will not change, and retrying an auth failure just
# burns the rate limit.
AUTH_STATUS_CODES = frozenset({401, 403})

_SENSITIVE_PARAM_HINTS = ("key", "auth", "token", "secret", "password")


class PokemonTCGAPIError(RuntimeError):
    """Raised when a Pokemon TCG API request cannot be completed successfully.

    Carries structured context so callers can branch on ``status_code`` or
    ``retryable`` instead of substring-matching the message. Never holds the API
    key: request parameters are sanitised and headers are not stored.
    """

    def __init__(
        self,
        message: str,
        *,
        status_code: Optional[int] = None,
        path: Optional[str] = None,
        params: Optional[Dict[str, Any]] = None,
        attempts: int = 1,
        retryable: bool = False,
        original: Optional[BaseException] = None,
    ):
        super().__init__(message)
        self.status_code = status_code
        self.path = path
        self.params = sanitize_params(params)
        self.attempts = attempts
        self.retryable = retryable
        self.original = original


def sanitize_params(params: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    """Drop anything credential-shaped so errors and logs stay safe to print."""
    if not params:
        return {}
    return {
        key: value
        for key, value in params.items()
        if not any(hint in str(key).lower() for hint in _SENSITIVE_PARAM_HINTS)
    }


@dataclass(frozen=True)
class PaginationStrategy:
    """One bounded way to walk a set's cards."""

    page_size: int
    order_by: Optional[str]

    @property
    def label(self) -> str:
        return f"pageSize={self.page_size},orderBy={self.order_by or 'none'}"


def _env_float(name: str, default: float) -> float:
    raw = os.getenv(name)
    if raw is None or not str(raw).strip():
        return default
    try:
        return float(raw)
    except (TypeError, ValueError):
        logger.warning("Ignoring non-numeric %s=%r; using %s", name, raw, default)
        return default


def _env_int(name: str, default: int) -> int:
    return int(_env_float(name, float(default)))


class PokemonTCGAPIClient:
    def __init__(
        self,
        api_key: Optional[str] = None,
        base_url: Optional[str] = None,
        *,
        session: Optional[Any] = None,
        connect_timeout: Optional[float] = None,
        read_timeout: Optional[float] = None,
        max_attempts: Optional[int] = None,
        backoff_base_seconds: Optional[float] = None,
        max_retry_after_seconds: Optional[float] = None,
        sleep: Callable[[float], None] = time.sleep,
        jitter: Callable[[float, float], float] = random.uniform,
    ):
        self.api_key = api_key or os.getenv("POKEMON_TCG_API_KEY")
        if not self.api_key:
            raise RuntimeError("Missing POKEMON_TCG_API_KEY environment variable")

        self.base_url = (base_url or os.getenv("POKEMON_TCG_BASE_URL") or DEFAULT_BASE_URL).rstrip("/")

        self.connect_timeout = (
            connect_timeout
            if connect_timeout is not None
            else _env_float("POKEMON_TCG_CONNECT_TIMEOUT", DEFAULT_CONNECT_TIMEOUT)
        )
        self.read_timeout = (
            read_timeout
            if read_timeout is not None
            else _env_float("POKEMON_TCG_READ_TIMEOUT", DEFAULT_READ_TIMEOUT)
        )
        self.max_attempts = max(
            1,
            max_attempts
            if max_attempts is not None
            else _env_int("POKEMON_TCG_MAX_ATTEMPTS", DEFAULT_MAX_ATTEMPTS),
        )
        self.backoff_base_seconds = (
            backoff_base_seconds
            if backoff_base_seconds is not None
            else _env_float("POKEMON_TCG_BACKOFF_BASE_SECONDS", DEFAULT_BACKOFF_BASE_SECONDS)
        )
        self.max_retry_after_seconds = (
            max_retry_after_seconds
            if max_retry_after_seconds is not None
            else _env_float("POKEMON_TCG_MAX_RETRY_AFTER_SECONDS", DEFAULT_MAX_RETRY_AFTER_SECONDS)
        )

        self._session = session if session is not None else requests
        self._sleep = sleep
        self._jitter = jitter

        # Rolling counter so completion diagnostics can report retry pressure.
        self.request_retries = 0

    # ------------------------------------------------------------------
    # Set resolution
    # ------------------------------------------------------------------

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

    # ------------------------------------------------------------------
    # Card pagination
    # ------------------------------------------------------------------

    @staticmethod
    def _pagination_strategies(page_size: int) -> Sequence[PaginationStrategy]:
        """Bounded, ordered fallbacks tried after request retries are exhausted."""
        primary = min(int(page_size or DEFAULT_PAGE_SIZE), DEFAULT_PAGE_SIZE)
        strategies = [
            PaginationStrategy(page_size=primary, order_by="id"),
            PaginationStrategy(page_size=50, order_by="id"),
            PaginationStrategy(page_size=50, order_by=None),
        ]
        # Drop duplicates while preserving order (e.g. caller already passed 50).
        seen: Set[Tuple[int, Optional[str]]] = set()
        unique: List[PaginationStrategy] = []
        for strategy in strategies:
            key = (strategy.page_size, strategy.order_by)
            if key not in seen:
                seen.add(key)
                unique.append(strategy)
        return unique

    def iter_cards_for_set(
        self,
        set_id: str,
        page_size: int = DEFAULT_PAGE_SIZE,
        select_fields: str = DEFAULT_SELECT_FIELDS,
        rate_limit_delay: float = 0.1,
    ) -> Generator[Dict[str, Optional[str]], None, None]:
        """Yield every unique card in a set, or raise.

        Completeness is judged against the API's own ``totalCount``. A strategy
        that stalls below that total is treated as failed, and the next bounded
        strategy restarts from page one; ``seen_ids`` is carried across restarts
        so no card is emitted twice. If every strategy fails the generator raises
        rather than presenting a partial set as success.
        """
        seen_ids: Set[str] = set()
        known_total_count: Optional[int] = None
        duplicates_suppressed = 0
        pages_requested = 0
        retries_at_start = self.request_retries

        attempted_labels: List[str] = []
        last_failure: Optional[str] = None

        for strategy in self._pagination_strategies(page_size):
            attempted_labels.append(strategy.label)
            page = 1
            strategy_complete = False
            strategy_failed_reason: Optional[str] = None

            while True:
                params: Dict[str, object] = {
                    "q": f"set.id:{set_id}",
                    "page": page,
                    "pageSize": strategy.page_size,
                    "select": select_fields,
                }
                if strategy.order_by:
                    params["orderBy"] = strategy.order_by

                try:
                    response = self._request_json(
                        "/cards", params, page=page, page_size=strategy.page_size
                    )
                except PokemonTCGAPIError as exc:
                    strategy_failed_reason = (
                        f"page {page} failed after {exc.attempts} attempt(s): {exc}"
                    )
                    break

                pages_requested += 1

                raw_cards = response.get("data") or []
                page_total_count = response.get("totalCount") or 0

                if known_total_count is None and page_total_count:
                    known_total_count = page_total_count

                # Safety limit is recomputed per strategy because it depends on
                # the active page size.
                max_pages = (
                    math.ceil(known_total_count / strategy.page_size) + 5
                    if known_total_count
                    else None
                )

                new_cards = []
                duplicates_this_page = 0
                for card in raw_cards:
                    card_id = card.get("id")
                    if card_id and card_id in seen_ids:
                        duplicates_this_page += 1
                        continue
                    if card_id:
                        seen_ids.add(card_id)
                    new_cards.append(card)

                duplicates_suppressed += duplicates_this_page

                first_id = raw_cards[0].get("id") if raw_cards else None
                last_id = raw_cards[-1].get("id") if raw_cards else None

                logger.info(
                    "[TCG API] set=%r page=%d pageSize=%d strategy=%r returned=%d new_unique=%d "
                    "unique_total=%d totalCount=%s duplicates=%d first=%r last=%r",
                    set_id, page, strategy.page_size, strategy.label, len(raw_cards),
                    len(new_cards), len(seen_ids), page_total_count, duplicates_this_page,
                    first_id, last_id,
                )
                print(
                    f"[TCG API] set={set_id!r} page={page} pageSize={strategy.page_size} "
                    f"strategy={strategy.label!r} returned={len(raw_cards)} "
                    f"new_unique={len(new_cards)} unique_total={len(seen_ids)} "
                    f"totalCount={page_total_count} duplicates={duplicates_this_page} "
                    f"first={first_id!r} last={last_id!r}"
                )

                for card in new_cards:
                    yield self._normalize_card(card)

                # Complete: we hold every unique card the API says exists.
                if known_total_count and len(seen_ids) >= known_total_count:
                    strategy_complete = True
                    break

                # The set is genuinely empty.
                if not known_total_count and not raw_cards:
                    strategy_complete = True
                    break

                # Ran out of rows below the reported total: this strategy stalled.
                if not raw_cards or len(raw_cards) < strategy.page_size:
                    strategy_failed_reason = (
                        f"pagination stalled on page {page} with "
                        f"{len(seen_ids)}/{known_total_count} unique cards"
                    )
                    break

                if max_pages is not None and page >= max_pages:
                    strategy_failed_reason = (
                        f"page safety guard hit at page {page} (max {max_pages}) with "
                        f"{len(seen_ids)}/{known_total_count} unique cards"
                    )
                    break

                page += 1
                if rate_limit_delay > 0:
                    self._sleep(rate_limit_delay)

            if strategy_complete:
                logger.info(
                    "[TCG API] completed set=%r unique_cards=%d reported_total=%s "
                    "pages_requested=%d request_retries=%d pagination_strategy=%r "
                    "duplicates_suppressed=%d",
                    set_id, len(seen_ids), known_total_count, pages_requested,
                    self.request_retries - retries_at_start, strategy.label,
                    duplicates_suppressed,
                )
                print(
                    f"[TCG API] completed set={set_id!r} unique_cards={len(seen_ids)} "
                    f"reported_total={known_total_count} pages_requested={pages_requested} "
                    f"request_retries={self.request_retries - retries_at_start} "
                    f"pagination_strategy={strategy.label!r} "
                    f"duplicates_suppressed={duplicates_suppressed}"
                )
                return

            last_failure = strategy_failed_reason
            logger.warning(
                "[TCG API] strategy failed set=%r strategy=%r unique_so_far=%d "
                "reported_total=%s reason=%s",
                set_id, strategy.label, len(seen_ids), known_total_count, strategy_failed_reason,
            )

        raise PokemonTCGAPIError(
            f"Could not fetch all cards for set {set_id!r}: "
            f"{len(seen_ids)}/{known_total_count} unique cards after trying "
            f"{len(attempted_labels)} pagination strategies "
            f"[{'; '.join(attempted_labels)}]. Final cause: {last_failure}",
            path="/cards",
            params={"q": f"set.id:{set_id}"},
            attempts=len(attempted_labels),
            retryable=True,
        )

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

    # ------------------------------------------------------------------
    # HTTP
    # ------------------------------------------------------------------

    def _retry_delay(self, attempt: int) -> float:
        """Exponential backoff with a little jitter: ~1s, ~2s, ~4s."""
        base = self.backoff_base_seconds * (2 ** (attempt - 1))
        return max(0.0, base + self._jitter(0.0, base * 0.1))

    def _retry_after_delay(self, response: Any, attempt: int) -> float:
        """Honour a sane numeric ``Retry-After``; otherwise fall back to backoff."""
        raw = None
        try:
            raw = response.headers.get("Retry-After")
        except AttributeError:
            raw = None
        if raw is not None:
            try:
                seconds = float(str(raw).strip())
            except (TypeError, ValueError):
                seconds = None
            if seconds is not None and seconds >= 0:
                return min(seconds, self.max_retry_after_seconds)
        return self._retry_delay(attempt)

    def _request_json(
        self,
        path: str,
        params: Dict[str, object],
        *,
        page: Optional[int] = None,
        page_size: Optional[int] = None,
    ) -> Dict[str, object]:
        safe_params = sanitize_params(params)
        last_error: Optional[PokemonTCGAPIError] = None

        for attempt in range(1, self.max_attempts + 1):
            status_code: Optional[int] = None
            category: str
            original: Optional[BaseException] = None
            response = None

            try:
                response = self._session.get(
                    f"{self.base_url}{path}",
                    params=params,
                    headers={
                        "Accept": "application/json",
                        "X-Api-Key": self.api_key,
                        "User-Agent": "EVRCalculator/1.0",
                    },
                    timeout=(self.connect_timeout, self.read_timeout),
                )
            except (requests.Timeout, requests.ConnectionError) as exc:
                category = type(exc).__name__
                original = exc
            except requests.RequestException as exc:
                # Anything else from requests is treated as permanent.
                raise PokemonTCGAPIError(
                    f"Pokemon TCG API request to {path} failed: {exc}",
                    path=path,
                    params=safe_params,
                    attempts=attempt,
                    retryable=False,
                    original=exc,
                ) from exc
            else:
                status_code = response.status_code

                if status_code in AUTH_STATUS_CODES:
                    raise PokemonTCGAPIError(
                        f"Pokemon TCG API rejected the request to {path} with "
                        f"HTTP {status_code}. Verify the POKEMON_TCG_API_KEY value.",
                        status_code=status_code,
                        path=path,
                        params=safe_params,
                        attempts=attempt,
                        retryable=False,
                    )

                if status_code not in RETRYABLE_STATUS_CODES:
                    if status_code >= 400:
                        raise PokemonTCGAPIError(
                            f"Pokemon TCG API request to {path} failed with HTTP {status_code}.",
                            status_code=status_code,
                            path=path,
                            params=safe_params,
                            attempts=attempt,
                            retryable=False,
                        )
                    try:
                        return response.json()
                    except ValueError as exc:
                        raise PokemonTCGAPIError(
                            f"Pokemon TCG API returned invalid JSON from {path} "
                            f"(HTTP {status_code}): {exc}",
                            status_code=status_code,
                            path=path,
                            params=safe_params,
                            attempts=attempt,
                            retryable=False,
                            original=exc,
                        ) from exc

                category = f"HTTP {status_code}"

            # --- retryable failure path ---
            last_error = PokemonTCGAPIError(
                f"Pokemon TCG API request to {path} failed ({category}) "
                f"after {attempt} attempt(s).",
                status_code=status_code,
                path=path,
                params=safe_params,
                attempts=attempt,
                retryable=True,
                original=original,
            )

            if attempt >= self.max_attempts:
                break

            if status_code == 429:
                delay = self._retry_after_delay(response, attempt)
            else:
                delay = self._retry_delay(attempt)

            self.request_retries += 1
            logger.warning(
                "[TCG API] retrying path=%s page=%s pageSize=%s error=%s "
                "attempt=%d/%d next_delay=%.2fs",
                path, page, page_size, category, attempt, self.max_attempts, delay,
            )
            self._sleep(delay)

        assert last_error is not None
        raise last_error
