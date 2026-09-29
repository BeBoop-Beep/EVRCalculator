"""Small dependency-free client for the PkmnPrices data API.

Only server-side callers should construct this client.  Authentication is sent
through X-API-Key and never appears in URLs, logs, exceptions, or repr output.
"""
from __future__ import annotations

import json
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from typing import Any, Callable, Mapping

BASE_URL = "https://api.pkmnprices.com"
USER_AGENT = "inDex-PkmnPrices/1"
RETRYABLE_STATUS = {429, 500, 502, 503, 504}


@dataclass(frozen=True)
class PkmnPricesAPIError(RuntimeError):
    status: int
    code: str
    message: str

    def __str__(self) -> str:
        return f"PkmnPrices API error status={self.status} code={self.code}"


class PkmnPricesClient:
    def __init__(
        self,
        api_key: str,
        *,
        base_url: str = BASE_URL,
        opener: Callable[..., Any] | None = None,
        sleep: Callable[[float], None] = time.sleep,
        max_retries: int = 2,
        timeout: float = 30.0,
    ) -> None:
        if not api_key:
            raise ValueError("PkmnPrices API key is required")
        self._api_key = api_key
        self.base_url = base_url.rstrip("/")
        self._opener = opener or urllib.request.urlopen
        self._sleep = sleep
        self.max_retries = max(0, int(max_retries))
        self.timeout = float(timeout)
        self.request_attempt_count = 0
        self.successful_request_count = 0
        self.credits_charged = 0
        self.credits_limit: int | None = None
        self.rate_remaining: int | None = None

    def __repr__(self) -> str:
        return f"PkmnPricesClient(base_url={self.base_url!r}, api_key=<redacted>)"

    def _url(self, path: str, params: Mapping[str, Any] | None = None) -> str:
        query = {
            key: ("true" if value is True else "false" if value is False else str(value))
            for key, value in (params or {}).items()
            if value is not None
        }
        suffix = "?" + urllib.parse.urlencode(query) if query else ""
        return self.base_url + "/" + path.lstrip("/") + suffix

    @staticmethod
    def _error(exc: urllib.error.HTTPError) -> PkmnPricesAPIError:
        code = "http_error"
        message = "provider request failed"
        try:
            payload = json.loads(exc.read().decode("utf-8", errors="replace"))
            detail = payload.get("error") or {}
            code = str(detail.get("code") or code)
            message = str(detail.get("message") or message)
        except Exception:
            pass
        return PkmnPricesAPIError(int(exc.code), code, message)

    def get(self, path: str, params: Mapping[str, Any] | None = None) -> dict[str, Any]:
        request = urllib.request.Request(
            self._url(path, params),
            headers={
                "X-API-Key": self._api_key,
                "Accept": "application/json",
                "User-Agent": USER_AGENT,
            },
        )
        for attempt in range(self.max_retries + 1):
            try:
                self.request_attempt_count += 1
                with self._opener(request, timeout=self.timeout) as response:
                    status = int(getattr(response, "status", 200))
                    payload = json.load(response)
                    headers = getattr(response, "headers", {}) or {}
                    charged = headers.get("x-credits-charged") if hasattr(headers, "get") else None
                    limit = headers.get("x-credits-limit") if hasattr(headers, "get") else None
                    remaining = headers.get("x-rate-remaining") if hasattr(headers, "get") else None
                if status != 200:
                    raise PkmnPricesAPIError(status, "unexpected_status", "unexpected provider response")
                if not isinstance(payload, dict):
                    raise PkmnPricesAPIError(status, "invalid_payload", "provider payload is not an object")
                self.successful_request_count += 1
                try:
                    if charged is not None:
                        self.credits_charged += max(0, int(charged))
                    if limit is not None:
                        self.credits_limit = int(limit)
                    if remaining is not None:
                        self.rate_remaining = int(remaining)
                except (TypeError, ValueError):
                    # Provider accounting headers are observability only; malformed
                    # values must not corrupt evidence collection.
                    pass
                return payload
            except urllib.error.HTTPError as exc:
                error = self._error(exc)
                if error.status not in RETRYABLE_STATUS or attempt >= self.max_retries:
                    raise error from None
            except (urllib.error.URLError, TimeoutError):
                if attempt >= self.max_retries:
                    raise
            self._sleep(float(2 ** attempt))
        raise RuntimeError("unreachable")

    def cards_by_tcgplayer_id(
        self,
        tcgplayer_product_id: str | int,
        *,
        language: str = "English",
        per_page: int = 5,
    ) -> list[dict[str, Any]]:
        payload = self.get(
            "/v1/cards",
            {
                "tcg_player_id": str(tcgplayer_product_id),
                "language": language,
                "per_page": max(1, min(int(per_page), 100)),
                "page": 1,
            },
        )
        rows = payload.get("data") or []
        if not isinstance(rows, list):
            raise PkmnPricesAPIError(200, "invalid_payload", "cards data is not an array")
        return [dict(row) for row in rows if isinstance(row, dict)]

    def card(self, provider_card_id: str | int, *, currency: str = "usd") -> dict[str, Any]:
        payload = self.get(f"/v1/cards/{urllib.parse.quote(str(provider_card_id), safe='')}", {"currency": currency})
        return dict(payload)

    def ebay_sold_page(
        self,
        provider_card_id: str | int,
        *,
        graded: bool | None = False,
        variant: str | None = None,
        since: str | None = None,
        sort: str = "date_desc",
        limit: int = 20,
        cursor: str | None = None,
    ) -> dict[str, Any]:
        return self.get(
            f"/v1/cards/{urllib.parse.quote(str(provider_card_id), safe='')}/listings/ebay",
            {
                "graded": graded,
                "variant": variant,
                "since": since,
                "sort": sort,
                "limit": max(1, min(int(limit), 20)),
                "cursor": cursor,
            },
        )

    def ebay_sold_collection(
        self,
        provider_card_id: str | int,
        *,
        graded: bool | None = False,
        variant: str | None = None,
        since: str | None = None,
        max_items: int = 200,
    ) -> dict[str, Any]:
        """Collect a bounded cursor walk and report whether older rows remain."""
        rows: list[dict[str, Any]] = []
        cursor: str | None = None
        has_more = False
        next_cursor: str | None = None
        while len(rows) < max(0, int(max_items)):
            remaining = int(max_items) - len(rows)
            if remaining <= 0:
                break
            payload = self.ebay_sold_page(
                provider_card_id,
                graded=graded,
                variant=variant,
                since=since,
                limit=min(20, remaining),
                cursor=cursor,
            )
            data = payload.get("data") or []
            if not isinstance(data, list):
                raise PkmnPricesAPIError(200, "invalid_payload", "sold data is not an array")
            rows.extend(dict(row) for row in data if isinstance(row, dict))
            page = payload.get("pagination") or {}
            has_more = bool(page.get("has_more"))
            next_value = page.get("next_cursor")
            next_cursor = str(next_value) if next_value else None
            if not has_more:
                break
            if not next_cursor or next_cursor == cursor:
                raise PkmnPricesAPIError(200, "invalid_pagination", "sold pagination cursor did not advance")
            if len(rows) >= int(max_items):
                break
            cursor = next_cursor
        return {
            "rows": rows,
            "has_more": has_more,
            "next_cursor": next_cursor if has_more else None,
        }

    def ebay_sold(
        self,
        provider_card_id: str | int,
        *,
        graded: bool | None = False,
        variant: str | None = None,
        since: str | None = None,
        max_items: int = 200,
    ) -> list[dict[str, Any]]:
        return list(
            self.ebay_sold_collection(
                provider_card_id,
                graded=graded,
                variant=variant,
                since=since,
                max_items=max_items,
            )["rows"]
        )
