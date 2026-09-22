from __future__ import annotations

from dataclasses import dataclass
import time
from typing import Any, Callable, Dict, Iterable, Optional

import requests

from backend.scripts.bootstrap_pokemon_set_configs import API_URL
from backend.db.clients.scrydex_pokemon_client import ScrydexPokemonClient
from backend.services.tcgplayer_set_catalog_service import normalize_name, token_overlap_score

REQUIRED_FIELDS = (
    "id", "name", "series", "releaseDate", "printedTotal", "total", "ptcgoCode", "images",
)
RETRYABLE_STATUS_CODES = frozenset({408, 425, 429, 500, 502, 503, 504})


@dataclass(frozen=True)
class MetadataResolution:
    status: str
    set_data: Optional[Dict[str, Any]]
    diagnostics: Dict[str, Any]


def _project(row: Dict[str, Any]) -> Dict[str, Any]:
    images = row.get("images") or {}
    return {
        "id": row.get("id"), "name": row.get("name"), "series": row.get("series"),
        "releaseDate": row.get("releaseDate"), "printedTotal": row.get("printedTotal"),
        "total": row.get("total"), "ptcgoCode": row.get("ptcgoCode"),
        "images": {"symbol": images.get("symbol"), "logo": images.get("logo")},
    }


def _fetch_legacy_targeted_sets(
    name: str,
    api_key: str,
    *,
    timeout_seconds: float = 15.0,
    session: Optional[requests.Session] = None,
    max_attempts: int = 3,
    sleep: Callable[[float], None] = time.sleep,
) -> list[Dict[str, Any]]:
    """Fetch a bounded metadata candidate set with transient retries.

    Metadata resolution is one of the first onboarding steps. A single provider
    500 must not defer an otherwise valid set until the next scheduler cycle.
    Keyless access remains rate-safe by using >=2.1s between transient retries.
    """
    client = session or requests.Session()
    headers = {"Accept": "application/json", "User-Agent": "EVRCalculator/1.0"}
    cleaned_key = str(api_key or "").strip()
    if cleaned_key:
        headers["X-Api-Key"] = cleaned_key

    attempts = max(1, int(max_attempts or 1))
    keyless_floor = 2.1 if not cleaned_key else 0.0
    last_exception: Optional[BaseException] = None

    for attempt in range(1, attempts + 1):
        try:
            response = client.get(
                API_URL,
                params={"q": f'name:"{name}"', "pageSize": 50},
                headers=headers,
                timeout=timeout_seconds,
            )
        except (requests.Timeout, requests.ConnectionError) as exc:
            last_exception = exc
            if attempt >= attempts:
                raise
            delay = max(keyless_floor, float(2 ** (attempt - 1)))
            sleep(delay)
            continue

        if response.status_code in RETRYABLE_STATUS_CODES and attempt < attempts:
            retry_after = response.headers.get("Retry-After")
            try:
                parsed_retry_after = float(retry_after) if retry_after is not None else None
            except (TypeError, ValueError):
                parsed_retry_after = None
            delay = parsed_retry_after if parsed_retry_after is not None else float(2 ** (attempt - 1))
            delay = min(30.0, max(keyless_floor, delay))
            sleep(delay)
            continue

        response.raise_for_status()
        return [_project(row) for row in response.json().get("data", [])]

    if last_exception is not None:
        raise last_exception
    return []



def fetch_targeted_sets(
    name: str,
    api_key: str,
    *,
    timeout_seconds: float = 15.0,
    session: Optional[requests.Session] = None,
    max_attempts: int = 3,
    sleep: Callable[[float], None] = time.sleep,
    scrydex_client: Optional[ScrydexPokemonClient] = None,
) -> list[Dict[str, Any]]:
    """Resolve new-set metadata from legacy PokemonTCG, then Scrydex on miss.

    Supplying an explicit HTTP session without a Scrydex client preserves the
    old isolated-test/diagnostic contract and never opens a surprise second
    network boundary. Normal production calls have no explicit session and
    therefore self-heal when a newly released expansion exists only in Scrydex.
    """
    legacy_error: Optional[BaseException] = None
    try:
        rows = _fetch_legacy_targeted_sets(
            name,
            api_key,
            timeout_seconds=timeout_seconds,
            session=session,
            max_attempts=max_attempts,
            sleep=sleep,
        )
        if rows:
            return rows
    except (requests.RequestException, requests.HTTPError) as exc:
        legacy_error = exc

    if session is not None and scrydex_client is None:
        if legacy_error is not None:
            raise legacy_error
        return []

    provider = scrydex_client or ScrydexPokemonClient()
    try:
        return [provider.resolve_set(name)]
    except Exception:
        if legacy_error is not None:
            raise legacy_error
        return []

def resolve_set_metadata(
    tcgplayer_name: str, rows: Iterable[Dict[str, Any]], *,
    expected_api_id: Optional[str] = None,
) -> MetadataResolution:
    candidates = [_project(row) for row in rows]
    target = normalize_name(tcgplayer_name)
    exact = [row for row in candidates if normalize_name(str(row.get("name") or "")) == target]
    if expected_api_id:
        conflicting = [row for row in exact if str(row.get("id")) != str(expected_api_id)]
        exact = [row for row in exact if str(row.get("id")) == str(expected_api_id)]
        if conflicting and not exact:
            return MetadataResolution(
                "identity_conflict", None,
                {"expected_api_id": expected_api_id, "conflicting": conflicting},
            )
    if len(exact) == 1:
        return MetadataResolution("resolved", exact[0], {"match": "normalized_exact"})
    if len(exact) > 1:
        return MetadataResolution("ambiguous", None, {"credible_matches": exact})

    scored = [
        (token_overlap_score(tcgplayer_name, str(row.get("name") or "")), row)
        for row in candidates
    ]
    credible = [row for score, row in scored if score >= 0.85]
    # Fuzzy evidence can identify a review candidate, but never authorizes source generation.
    if credible:
        return MetadataResolution("ambiguous", None, {"credible_matches": credible, "match": "fuzzy_review"})
    return MetadataResolution("not_found", None, {"candidate_count": len(candidates)})
