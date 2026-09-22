from __future__ import annotations

import os
import re
import time
from typing import Any, Dict, Iterator, List, Optional

import requests

TCGDEX_BASE_URL = "https://api.tcgdex.net/v2/en"
TCGDEX_CONNECT_TIMEOUT = 8.0
TCGDEX_READ_TIMEOUT = 45.0
TCGDEX_MAX_ATTEMPTS = 4
TCGDEX_RETRYABLE_STATUS_CODES = frozenset({408, 425, 429, 500, 502, 503, 504})


class TCGdexError(RuntimeError):
    def __init__(self, message: str, *, status_code: Optional[int] = None, path: Optional[str] = None) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.path = path


def _text(value: Any) -> str:
    return str(value or "").strip()


def _normalize_name(value: Any) -> str:
    name = _text(value)
    name = re.sub(r"^ME(?:\d+(?:\.\d+)?)?\s*:\s*", "", name, flags=re.IGNORECASE)
    name = re.sub(r"[^a-z0-9]+", " ", name.casefold())
    return " ".join(name.split())


def _token_score(left: str, right: str) -> float:
    a = set(_normalize_name(left).split())
    b = set(_normalize_name(right).split())
    if not a or not b:
        return 0.0
    return len(a & b) / max(len(a), len(b))


def _asset_url(base: Any, *, quality: str = "low") -> Optional[str]:
    raw = _text(base)
    if not raw:
        return None
    quality = "high" if quality == "high" else "low"
    return f"{raw.rstrip('/')}/{quality}.webp"


def _set_asset_url(base: Any) -> Optional[str]:
    raw = _text(base)
    if not raw:
        return None
    return f"{raw.rstrip('/')}.webp"


def _pokedex_numbers(card: Dict[str, Any]) -> List[int]:
    raw = card.get("dexId")
    if raw is None:
        return []
    values = raw if isinstance(raw, list) else [raw]
    result: List[int] = []
    for value in values:
        try:
            result.append(int(value))
        except (TypeError, ValueError):
            continue
    return result


def _supertype(category: Any) -> Optional[str]:
    value = _text(category)
    if not value:
        return None
    if value.casefold() == "pokemon":
        return "Pokémon"
    if value.casefold() == "trainer":
        return "Trainer"
    if value.casefold() == "energy":
        return "Energy"
    return value


def _subtypes(card: Dict[str, Any]) -> List[str]:
    values: List[str] = []
    stage = _text(card.get("stage"))
    suffix = _text(card.get("suffix"))
    if stage:
        values.append(stage)
    if suffix and suffix.casefold() not in {value.casefold() for value in values}:
        values.append(suffix)
    return values


class TCGdexPokemonClient:
    """Bounded reader for TCGdex's public English REST API.

    TCGdex is the free metadata/artwork fallback for newly scraped sets. It
    deliberately does not populate legacy PokemonTCG identity columns because
    those columns participate in joins against PokemonTCG/Scrydex identifiers.
    TCGdex identity stays in diagnostics/source payloads while local matching is
    performed with set-local number/name identity.
    """

    def __init__(
        self,
        *,
        base_url: Optional[str] = None,
        session: Optional[Any] = None,
        sleep=time.sleep,
        detail_delay_seconds: Optional[float] = None,
    ) -> None:
        self.base_url = (base_url or os.getenv("TCGDEX_BASE_URL") or TCGDEX_BASE_URL).rstrip("/")
        self.session = session or requests.Session()
        self.sleep = sleep
        if detail_delay_seconds is None:
            try:
                detail_delay_seconds = float(os.getenv("TCGDEX_DETAIL_DELAY_SECONDS", "0.02"))
            except (TypeError, ValueError):
                detail_delay_seconds = 0.02
        self.detail_delay_seconds = max(0.0, float(detail_delay_seconds))

    def _request_json(self, path: str) -> Any:
        last_error: Optional[BaseException] = None
        for attempt in range(1, TCGDEX_MAX_ATTEMPTS + 1):
            try:
                response = self.session.get(
                    f"{self.base_url}{path}",
                    headers={"Accept": "application/json", "User-Agent": "EVRCalculator/1.0"},
                    timeout=(TCGDEX_CONNECT_TIMEOUT, TCGDEX_READ_TIMEOUT),
                )
            except (requests.Timeout, requests.ConnectionError) as exc:
                last_error = exc
                if attempt >= TCGDEX_MAX_ATTEMPTS:
                    raise TCGdexError(
                        f"TCGdex request failed after {attempt} attempts: {type(exc).__name__}",
                        path=path,
                    ) from exc
                self.sleep(float(2 ** (attempt - 1)))
                continue

            if response.status_code in TCGDEX_RETRYABLE_STATUS_CODES:
                if attempt >= TCGDEX_MAX_ATTEMPTS:
                    raise TCGdexError(
                        f"TCGdex request failed HTTP {response.status_code} after {attempt} attempts",
                        status_code=response.status_code,
                        path=path,
                    )
                retry_after = response.headers.get("Retry-After")
                try:
                    delay = float(retry_after) if retry_after else float(2 ** (attempt - 1))
                except (TypeError, ValueError):
                    delay = float(2 ** (attempt - 1))
                self.sleep(min(max(delay, 0.0), 30.0))
                continue

            if response.status_code >= 400:
                raise TCGdexError(
                    f"TCGdex request failed HTTP {response.status_code} path={path}",
                    status_code=response.status_code,
                    path=path,
                )
            try:
                return response.json()
            except ValueError as exc:
                raise TCGdexError(f"TCGdex returned invalid JSON path={path}", path=path) from exc

        raise TCGdexError(f"TCGdex request failed: {last_error}", path=path)

    def list_sets(self) -> List[Dict[str, Any]]:
        payload = self._request_json("/sets")
        if not isinstance(payload, list):
            raise TCGdexError("TCGdex /sets returned a non-list payload", path="/sets")
        return [dict(row) for row in payload if isinstance(row, dict)]

    def resolve_set(self, set_name: str) -> Dict[str, Any]:
        wanted = _normalize_name(set_name)
        rows = self.list_sets()
        exact = [row for row in rows if _normalize_name(row.get("name")) == wanted]
        if len(exact) == 1:
            return exact[0]
        if len(exact) > 1:
            raise TCGdexError(f"TCGdex set name is ambiguous: {set_name!r}")

        scored = sorted(
            ((_token_score(set_name, str(row.get("name") or "")), row) for row in rows),
            key=lambda item: item[0],
            reverse=True,
        )
        best_score, best = scored[0] if scored else (0.0, None)
        second_score = scored[1][0] if len(scored) > 1 else 0.0
        if best is None or best_score < 0.70 or best_score - second_score < 0.10:
            raise TCGdexError(
                f"Could not uniquely resolve TCGdex set {set_name!r}; "
                f"best_score={best_score:.3f} second_score={second_score:.3f}"
            )
        return best

    def get_set(self, set_id: str) -> Dict[str, Any]:
        payload = self._request_json(f"/sets/{set_id}")
        if not isinstance(payload, dict):
            raise TCGdexError(
                f"TCGdex set detail returned a non-object for {set_id!r}",
                path=f"/sets/{set_id}",
            )
        return dict(payload)

    def resolve_set_detail(self, set_name: str) -> Dict[str, Any]:
        brief = self.resolve_set(set_name)
        set_id = _text(brief.get("id"))
        if not set_id:
            raise TCGdexError(f"TCGdex set {set_name!r} has no id")
        return self.get_set(set_id)

    def set_metadata(self, set_name: str) -> Dict[str, Any]:
        detail = self.resolve_set_detail(set_name)
        counts = detail.get("cardCount") if isinstance(detail.get("cardCount"), dict) else {}
        serie = detail.get("serie") if isinstance(detail.get("serie"), dict) else {}
        return {
            "provider": "tcgdex",
            "tcgdex_set_id": detail.get("id"),
            "name": detail.get("name"),
            "series": serie.get("name"),
            "release_date": detail.get("releaseDate"),
            "printed_total": counts.get("official"),
            "total": counts.get("total"),
            "logo_image_url": _set_asset_url(detail.get("logo")),
            "symbol_image_url": _set_asset_url(detail.get("symbol")),
        }

    def iter_image_cards_for_set_name(self, set_name: str) -> Iterator[Dict[str, Any]]:
        detail = self.resolve_set_detail(set_name)
        cards = detail.get("cards")
        if not isinstance(cards, list):
            raise TCGdexError(
                f"TCGdex set {set_name!r} has no card checklist",
                path=f"/sets/{detail.get('id')}",
            )
        for card in cards:
            if not isinstance(card, dict):
                continue
            yield {
                "pokemon_tcg_api_id": None,
                "tcgdex_card_id": card.get("id"),
                "provider": "tcgdex",
                "set_id": detail.get("id"),
                "set_name": detail.get("name"),
                "number": card.get("localId"),
                "name": card.get("name"),
                "image_small_url": _asset_url(card.get("image"), quality="low"),
                "image_large_url": _asset_url(card.get("image"), quality="high"),
            }

    def fetch_card_details_for_set_name(self, set_name: str) -> List[Dict[str, Any]]:
        detail = self.resolve_set_detail(set_name)
        briefs = detail.get("cards")
        if not isinstance(briefs, list):
            raise TCGdexError(f"TCGdex set {set_name!r} has no card checklist")

        result: List[Dict[str, Any]] = []
        for index, brief in enumerate(briefs):
            if not isinstance(brief, dict) or not _text(brief.get("id")):
                raise TCGdexError(f"TCGdex set {set_name!r} contains a card without id")
            raw = self._request_json(f"/cards/{brief['id']}")
            if not isinstance(raw, dict):
                raise TCGdexError(f"TCGdex card detail returned a non-object for {brief['id']!r}")
            image_base = raw.get("image") or brief.get("image")
            result.append({
                "provider": "tcgdex",
                "tcgdex_card_id": raw.get("id") or brief.get("id"),
                "name": raw.get("name") or brief.get("name"),
                "number": raw.get("localId") or brief.get("localId"),
                "printed_number": raw.get("localId") or brief.get("localId"),
                "supertype": _supertype(raw.get("category")),
                "subtypes": _subtypes(raw),
                "rarity": raw.get("rarity"),
                "artist": raw.get("illustrator"),
                "national_pokedex_numbers": _pokedex_numbers(raw),
                "image_small_url": _asset_url(image_base, quality="low"),
                "image_large_url": _asset_url(image_base, quality="high"),
                "source_payload": raw,
            })
            if index < len(briefs) - 1 and self.detail_delay_seconds > 0:
                self.sleep(self.detail_delay_seconds)

        if len(result) != len(briefs):
            raise TCGdexError(
                f"TCGdex detail count mismatch for {set_name!r}: {len(result)}/{len(briefs)}"
            )
        return result
