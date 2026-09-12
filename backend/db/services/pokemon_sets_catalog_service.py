from __future__ import annotations

import logging
import re
import time
from collections import Counter
from typing import Any, Dict, List, Optional

from backend.db.clients.supabase_client import create_short_timeout_service_client, service_read_client
from backend.db.services.data_service_health import is_transient_data_service_error
from backend.db.services.public_read_retry import run_public_read_with_retry

logger = logging.getLogger(__name__)

TCG_NAME_CANDIDATES = ("Pokemon", "Pok\u00e9mon")


class PokemonSetsCatalogError(Exception):
    def __init__(
        self,
        status_code: int,
        message: str,
        code: str,
        *,
        retry_after_seconds: Optional[int] = None,
    ) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.message = message
        self.code = code
        self.retry_after_seconds = retry_after_seconds


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


def _resolve_pokemon_tcg_id(client: Any) -> Optional[str]:
    lookup_failed = False
    for candidate in TCG_NAME_CANDIDATES:
        try:
            result = (
                client.table("tcgs")
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
            if is_transient_data_service_error(exc):
                raise
            lookup_failed = True

    try:
        fallback_result = (
            client.table("tcgs")
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
        if is_transient_data_service_error(exc):
            raise
        lookup_failed = True

    if lookup_failed:
        raise PokemonSetsCatalogError(
            status_code=500,
            message="Failed to resolve Pokemon TCG",
            code="POKEMON_TCG_LOOKUP_FAILED",
        )

    return None


# NOTE: `series`, `official_card_count`, `printed_total`, `total_cards`, and
# `set_code` are NOT columns on the canonical `public.sets` table (verified
# against backend/db/migrations and every other reader of the `sets` table --
# see backend/db/services/pokemon_market_rollout_cohort.py's
# `_CORE_SET_COLUMNS`, backend/db/services/pokemon_scrape_runtime_preflight.py,
# and backend/db/services/pokemon_era_set_sync_service.py's use of
# `abbreviation`). Selecting any of them causes PostgREST to fail the whole
# query with 42703 (`column sets.<name> does not exist`), which is what took
# GET /tcgs/pokemon/sets down. Card count is sourced from the
# get_pokemon_canonical_card_counts_by_set RPC below, era name comes from the
# `eras` lookup table, and set code is derived from `abbreviation` /
# `pokemon_api_set_id` -- none of those need a same-named column on `sets`.
#
# `is_subset` is selected so the catalog can filter to canonical ROOT sets
# only (COALESCE(is_subset, false) = false), matching the same root-set
# membership semantics as the decoupled get_pokemon_set_route_directory RPC.
# This is catalog scope, not RIP/Rankings eligibility -- do not add any
# simulation-support or Rankings-membership filtering here.
_SETS_PROJECTION = (
    "id,name,canonical_key,pokemon_api_set_id,era_id,release_date,"
    "abbreviation,is_subset,"
    "logo_image_url,symbol_image_url,hero_image_url"
)


def _load_canonical_card_counts(set_ids: List[str]) -> Dict[str, int]:
    """Aggregate per-set canonical card counts via a single SQL GROUP BY RPC.

    This intentionally avoids paging through pokemon_canonical_cards in
    Python: DB work here scales with the number of requested sets (one
    result row per set with a canonical card), not with the size of the
    canonical card corpus. See migration
    20260904120000_add_pokemon_canonical_card_counts_by_set_rpc.sql.
    """
    if not set_ids:
        return {}

    counts: Dict[str, int] = {}

    # Batch defensively so a single RPC call payload/response stays small even
    # if the catalog grows to many thousands of sets; each batch is still one
    # DB round trip returning at most one row per set (never per card).
    batch_size = 500
    for index in range(0, len(set_ids), batch_size):
        chunk = set_ids[index:index + batch_size]
        result = (
            service_read_client.rpc(
                "get_pokemon_canonical_card_counts_by_set",
                {"p_set_ids": chunk},
            ).execute()
        )
        rows = list(result.data or [])
        for row in rows:
            row_set_id = _to_optional_str(row.get("set_id"))
            row_count = _to_optional_int(row.get("card_count"))
            if row_set_id and row_count is not None:
                counts[row_set_id] = row_count

    return counts


def _load_primary_sets(client: Any, tcg_id: str) -> List[Dict[str, Any]]:
    # Canonical root-set membership: COALESCE(is_subset, false) = false. This
    # is catalog scope only -- it must NOT be narrowed further by RIP/
    # simulation support or Rankings/market publication readiness. A set can
    # have a valid canonical catalog entry with no supported RIP simulation;
    # that must not 404 or disappear from this listing.
    result = (
        client.table("sets")
        .select(_SETS_PROJECTION)
        .eq("tcg_id", tcg_id)
        .or_("is_subset.is.null,is_subset.eq.false")
        .order("release_date", desc=True)
        .order("name")
        .execute()
    )
    return list(result.data or [])


def get_pokemon_sets_catalog_payload() -> Dict[str, Any]:
    total_started = time.perf_counter()
    warnings: List[str] = []
    sources: Dict[str, str] = {}

    tcg_id_started = time.perf_counter()
    try:
        tcg_id = run_public_read_with_retry(
            _resolve_pokemon_tcg_id,
            operation_name="pokemon_sets_catalog_tcg_lookup",
            initial_client=service_read_client,
            client_factory=create_short_timeout_service_client,
        )
    except PokemonSetsCatalogError:
        raise
    except Exception as exc:
        if is_transient_data_service_error(exc):
            raise PokemonSetsCatalogError(
                status_code=503,
                message="Pokemon catalog is temporarily unavailable",
                code="POKEMON_CATALOG_TEMPORARILY_UNAVAILABLE",
                retry_after_seconds=30,
            ) from exc
        raise PokemonSetsCatalogError(
            status_code=500,
            message="Failed to resolve Pokemon TCG",
            code="POKEMON_TCG_LOOKUP_FAILED",
        ) from exc
    tcg_id_ms = (time.perf_counter() - tcg_id_started) * 1000

    if not tcg_id:
        raise PokemonSetsCatalogError(
            status_code=404,
            message="Pokemon TCG was not found",
            code="POKEMON_TCG_NOT_FOUND",
        )

    sets_started = time.perf_counter()
    try:
        raw_sets = run_public_read_with_retry(
            lambda client: _load_primary_sets(client, tcg_id),
            operation_name="pokemon_sets_catalog_primary_sets",
            initial_client=service_read_client,
            client_factory=create_short_timeout_service_client,
        )
        sources["sets"] = "OK"
    except Exception as exc:
        logger.exception("[pokemon-sets-catalog] sets query failed tcg_id=%s", tcg_id)
        if is_transient_data_service_error(exc):
            raise PokemonSetsCatalogError(
                status_code=503,
                message="Pokemon catalog is temporarily unavailable",
                code="POKEMON_CATALOG_TEMPORARILY_UNAVAILABLE",
                retry_after_seconds=30,
            ) from exc
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
                service_read_client.table("eras")
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
                # `series` is not a canonical `sets` column; era is the
                # source of truth for grouping. Left present (null) only for
                # backward-compatible payload shape.
                "series": None,
                "release_date": _to_optional_str(set_row.get("release_date")),
                "card_count": resolved_card_count,
                # Card totals are resolved entirely from the canonical
                # checklist RPC above (`card_count`); `sets` carries no
                # official/printed/total card-count columns.
                "official_card_count": None,
                "printed_total": None,
                "total_cards": None,
                "set_code": _to_optional_str(set_row.get("abbreviation"))
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
