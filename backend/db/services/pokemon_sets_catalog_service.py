from __future__ import annotations

import logging
import re
import time
from collections import Counter
from typing import Any, Dict, List, Optional

from backend.db.clients.supabase_client import public_read_client

logger = logging.getLogger(__name__)

TCG_NAME_CANDIDATES = ("Pokemon", "Pok\u00e9mon")


class PokemonSetsCatalogError(Exception):
    def __init__(self, status_code: int, message: str, code: str) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.message = message
        self.code = code


def _to_optional_str(value: Any) -> Optional[str]:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _to_optional_int(value: Any) -> Optional[int]:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return None
    return parsed


def _slugify(value: str) -> str:
    lowered = str(value or "").strip().lower()
    lowered = re.sub(r"\s+", "-", lowered)
    lowered = re.sub(r"[^\w-]+", "", lowered)
    lowered = re.sub(r"-{2,}", "-", lowered)
    return lowered.strip("-")


def _resolve_pokemon_tcg_id() -> Optional[str]:
    for candidate in TCG_NAME_CANDIDATES:
        try:
            result = (
                public_read_client.table("tcgs")
                .select("id,name")
                .eq("name", candidate)
                .limit(1)
                .execute()
            )
            rows = result.data or []
            if rows:
                resolved = _to_optional_str(rows[0].get("id"))
                if resolved:
                    return resolved
        except Exception as exc:
            logger.warning("[pokemon-sets-catalog] tcg lookup failed for candidate=%s error=%s", candidate, exc)

    try:
        fallback_result = (
            public_read_client.table("tcgs")
            .select("id,name")
            .ilike("name", "pokemon")
            .limit(1)
            .execute()
        )
        fallback_rows = fallback_result.data or []
        if fallback_rows:
            return _to_optional_str(fallback_rows[0].get("id"))
    except Exception as exc:
        logger.warning("[pokemon-sets-catalog] tcg fallback lookup failed error=%s", exc)

    return None


def _resolve_card_count(set_row: Dict[str, Any]) -> Optional[int]:
    for key in ("official_card_count", "printed_total", "total_cards", "card_count"):
        value = _to_optional_int(set_row.get(key))
        if value is not None and value >= 0:
            return value
    return None


def _load_canonical_card_counts(set_ids: List[str]) -> Dict[str, int]:
    if not set_ids:
        return {}

    counts: Counter[str] = Counter()
    page_size = 1000

    for index in range(0, len(set_ids), 100):
        chunk = set_ids[index:index + 100]
        offset = 0
        while True:
            query = (
                public_read_client.table("pokemon_canonical_cards")
                .select("set_id")
                .in_("set_id", chunk)
            )
            if hasattr(query, "range"):
                query = query.range(offset, offset + page_size - 1)
            result = query.execute()
            rows = list(result.data or [])
            for row in rows:
                row_set_id = _to_optional_str(row.get("set_id"))
                if row_set_id:
                    counts[row_set_id] += 1
            if len(rows) < page_size:
                break
            offset += page_size

    return dict(counts)


def get_pokemon_sets_catalog_payload() -> Dict[str, Any]:
    total_started = time.perf_counter()
    warnings: List[str] = []
    sources: Dict[str, str] = {}

    tcg_id_started = time.perf_counter()
    tcg_id = _resolve_pokemon_tcg_id()
    tcg_id_ms = (time.perf_counter() - tcg_id_started) * 1000

    if not tcg_id:
        raise PokemonSetsCatalogError(
            status_code=404,
            message="Pokemon TCG was not found",
            code="POKEMON_TCG_NOT_FOUND",
        )

    sets_started = time.perf_counter()
    try:
        sets_result = (
            public_read_client.table("sets")
            .select("*")
            .eq("tcg_id", tcg_id)
            .order("release_date", desc=True)
            .order("name")
            .execute()
        )
        raw_sets = list(sets_result.data or [])
        sources["sets"] = "OK"
    except Exception:
        logger.exception("[pokemon-sets-catalog] sets query failed tcg_id=%s", tcg_id)
        raise PokemonSetsCatalogError(
            status_code=500,
            message="Failed to load Pokemon sets",
            code="POKEMON_SETS_QUERY_FAILED",
        )
    sets_ms = (time.perf_counter() - sets_started) * 1000

    set_ids = [
        str(set_row.get("id"))
        for set_row in raw_sets
        if set_row.get("id") is not None
    ]
    canonical_counts_started = time.perf_counter()
    try:
        canonical_card_counts = _load_canonical_card_counts(set_ids)
        sources["pokemon_canonical_cards"] = "OK"
    except Exception as exc:
        logger.warning("[pokemon-sets-catalog] canonical card count lookup failed error=%s", exc)
        warnings.append("Failed to load canonical checklist counts for one or more sets")
        canonical_card_counts = {}
        sources["pokemon_canonical_cards"] = "FAILED"
    canonical_counts_ms = (time.perf_counter() - canonical_counts_started) * 1000

    era_lookup: Dict[str, Dict[str, Any]] = {}
    era_ids = sorted(
        {
            str(set_row.get("era_id"))
            for set_row in raw_sets
            if set_row.get("era_id") is not None
        }
    )

    eras_started = time.perf_counter()
    if era_ids:
        try:
            era_result = (
                public_read_client.table("eras")
                .select("id,name")
                .in_("id", era_ids)
                .execute()
            )
            era_lookup = {
                str(era_row.get("id")): era_row
                for era_row in (era_result.data or [])
                if era_row.get("id") is not None
            }
            sources["eras"] = "OK"
        except Exception as exc:
            logger.warning("[pokemon-sets-catalog] eras lookup failed error=%s", exc)
            warnings.append("Failed to load era metadata for one or more sets")
            sources["eras"] = "FAILED"
    else:
        sources["eras"] = "SKIPPED"
    eras_ms = (time.perf_counter() - eras_started) * 1000

    sets: List[Dict[str, Any]] = []
    for set_row in raw_sets:
        set_id = _to_optional_str(set_row.get("id"))
        if not set_id:
            continue

        name = _to_optional_str(set_row.get("name")) or set_id
        canonical_key = _to_optional_str(set_row.get("canonical_key"))
        pokemon_api_set_id = _to_optional_str(set_row.get("pokemon_api_set_id"))
        era_id = _to_optional_str(set_row.get("era_id"))
        era_name = _to_optional_str((era_lookup.get(era_id) or {}).get("name")) if era_id else None
        # Canonical checklist count is the frontend card-count source of truth.
        # Do not fall back to public.cards/card_variants here; those rows can be
        # marketplace or variant inflated.
        resolved_card_count = canonical_card_counts.get(set_id, 0)
        official_card_count = _to_optional_int(set_row.get("official_card_count"))
        printed_total = _to_optional_int(set_row.get("printed_total"))
        total_cards = _to_optional_int(set_row.get("total_cards"))

        resolved_slug = canonical_key or _slugify(name) or _slugify(set_id)

        sets.append(
            {
                "id": set_id,
                "name": name,
                "slug": resolved_slug,
                "canonical_key": canonical_key,
                "era_id": era_id,
                "era": era_name,
                "era_name": era_name,
                "series": _to_optional_str(set_row.get("series")),
                "release_date": _to_optional_str(set_row.get("release_date")),
                "card_count": resolved_card_count,
                "official_card_count": official_card_count,
                "printed_total": printed_total,
                "total_cards": total_cards,
                "set_code": _to_optional_str(set_row.get("set_code"))
                or _to_optional_str(set_row.get("abbreviation"))
                or pokemon_api_set_id,
                "pokemon_api_set_id": pokemon_api_set_id,
                "logo_url": _to_optional_str(set_row.get("logo_image_url")),
                "symbol_url": _to_optional_str(set_row.get("symbol_image_url")),
                "image_url": _to_optional_str(set_row.get("hero_image_url")),
                "logo_image_url": _to_optional_str(set_row.get("logo_image_url")),
                "symbol_image_url": _to_optional_str(set_row.get("symbol_image_url")),
                "hero_image_url": _to_optional_str(set_row.get("hero_image_url")),
            }
        )

    return {
        "sets": sets,
        "meta": {
            "warnings": warnings,
            "sources": sources,
            "timings": {
                "tcg_id_lookup_ms": round(tcg_id_ms, 3),
                "sets_query_ms": round(sets_ms, 3),
                "eras_query_ms": round(eras_ms, 3),
                "canonical_card_counts_query_ms": round(canonical_counts_ms, 3),
                "total_backend_ms": round((time.perf_counter() - total_started) * 1000, 3),
            },
        },
    }
