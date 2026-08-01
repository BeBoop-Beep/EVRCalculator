from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Iterable, Optional

import requests

from backend.scripts.bootstrap_pokemon_set_configs import API_URL
from backend.services.tcgplayer_set_catalog_service import normalize_name, token_overlap_score

REQUIRED_FIELDS = (
    "id", "name", "series", "releaseDate", "printedTotal", "total", "ptcgoCode", "images",
)


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


def fetch_targeted_sets(
    name: str, api_key: str, *, timeout_seconds: float = 15.0,
    session: Optional[requests.Session] = None,
) -> list[Dict[str, Any]]:
    if not api_key:
        raise RuntimeError("Missing POKEMON_TCG_API_KEY environment variable")
    client = session or requests.Session()
    response = client.get(
        API_URL,
        params={"q": f'name:"{name}"', "pageSize": 50},
        headers={"Accept": "application/json", "X-Api-Key": api_key, "User-Agent": "EVRCalculator/1.0"},
        timeout=timeout_seconds,
    )
    response.raise_for_status()
    return [_project(row) for row in response.json().get("data", [])]


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
