from __future__ import annotations

import concurrent.futures as _cf
import logging
import time
from typing import Any, Dict, List, Optional, Tuple
from uuid import UUID

from backend.db.clients.supabase_client import public_read_client
from backend.db.services.collection_portfolio_service import (
    _build_price_lookup,
    _extract_market_price,
    _get_card_market_price,
    _load_lightweight_fallback_items,
    _normalize_public_summary_snapshot,
    _to_number,
    _unavailable_public_summary,
)
from backend.db.services.public_identity_service import normalize_profile_username, resolve_public_user_by_username

logger = logging.getLogger(__name__)


class PublicProfilePageError(Exception):
    def __init__(self, status_code: int, message: str, code: str) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.message = message
        self.code = code


def _first_row(result: Any) -> Optional[Dict[str, Any]]:
    data = getattr(result, "data", None)
    if isinstance(data, list):
        return data[0] if data else None
    if isinstance(data, dict):
        return data
    return None


def _duration_ms(started: float) -> float:
    return round((time.perf_counter() - started) * 1000.0, 3)


def _summary_indicates_holdings(summary: Optional[Dict[str, Any]]) -> bool:
    if not isinstance(summary, dict):
        return False
    return any(_to_number(summary.get(key), 0.0) > 0.0 for key in ("cards_count", "sealed_count", "graded_count"))


def _enrich_items_with_prices(
    items: List[Dict[str, Any]],
    db_client: Any,
    timeout_s: float = 1.5,
) -> Tuple[List[Dict[str, Any]], List[str]]:
    """Batch price lookup for lightweight fallback items.

    Fires up to 3 concurrent price queries (one per collectible type) using only
    the IDs present in the item list. Updates market_price and estimated_value
    in-place. Returns (enriched_items, warnings).

    Price tables used (same as private collection path):
      cards    -> card_market_usd_latest_by_condition (variant_id, condition_id)
      sealed   -> sealed_product_market_usd_latest    (sealed_product_id)
      graded   -> graded_card_market_latest            (graded_card_variant_id)
    """
    if not items:
        return items, []

    enrichment_warnings: List[str] = []

    card_items = [i for i in items if i.get("collectible_type") == "card"]
    sealed_items = [i for i in items if i.get("collectible_type") == "sealed_product"]
    graded_items = [i for i in items if i.get("collectible_type") == "graded_card"]

    card_variant_ids = list({str(i["collectible_id"]) for i in card_items if i.get("collectible_id")})
    sealed_product_ids = list({str(i["collectible_id"]) for i in sealed_items if i.get("collectible_id")})
    graded_variant_ids = list({str(i["collectible_id"]) for i in graded_items if i.get("collectible_id")})

    card_price_map: Dict[str, float] = {}
    sealed_price_map: Dict[str, float] = {}
    graded_price_map: Dict[str, float] = {}

    def _fetch_card_prices() -> Dict[str, float]:
        if not card_variant_ids:
            return {}
        try:
            resp = db_client.table("card_market_usd_latest_by_condition").select(
                "variant_id,condition_id,market_price"
            ).in_("variant_id", card_variant_ids).execute()
            return _build_price_lookup(resp.data or [], "variant_id", "condition_id")
        except Exception:
            logger.exception("[public-profile-price] card price fetch failed")
            return {}

    def _fetch_sealed_prices() -> Dict[str, float]:
        if not sealed_product_ids:
            return {}
        try:
            resp = db_client.table("sealed_product_market_usd_latest").select(
                "sealed_product_id,market_price"
            ).in_("sealed_product_id", sealed_product_ids).execute()
            return _build_price_lookup(resp.data or [], "sealed_product_id")
        except Exception:
            logger.exception("[public-profile-price] sealed price fetch failed")
            return {}

    def _fetch_graded_prices() -> Dict[str, float]:
        if not graded_variant_ids:
            return {}
        try:
            resp = db_client.table("graded_card_market_latest").select(
                "graded_card_variant_id,market_price"
            ).in_("graded_card_variant_id", graded_variant_ids).execute()
            return _build_price_lookup(resp.data or [], "graded_card_variant_id")
        except Exception:
            logger.exception("[public-profile-price] graded price fetch failed")
            return {}

    t_price_start = time.perf_counter()
    with _cf.ThreadPoolExecutor(max_workers=3) as executor:
        f_card = executor.submit(_fetch_card_prices)
        f_sealed = executor.submit(_fetch_sealed_prices)
        f_graded = executor.submit(_fetch_graded_prices)
        try:
            card_price_map = f_card.result(timeout=timeout_s)
        except Exception:
            enrichment_warnings.append("Card price lookup failed or timed out")
        try:
            sealed_price_map = f_sealed.result(timeout=max(0.001, timeout_s - (time.perf_counter() - t_price_start)))
        except Exception:
            enrichment_warnings.append("Sealed price lookup failed or timed out")
        try:
            graded_price_map = f_graded.result(timeout=max(0.001, timeout_s - (time.perf_counter() - t_price_start)))
        except Exception:
            enrichment_warnings.append("Graded price lookup failed or timed out")

    price_elapsed = round((time.perf_counter() - t_price_start) * 1000, 3)
    logger.info(
        "[public-profile-price] enrichment done cards=%s sealed=%s graded=%s elapsed_ms=%.3f warnings=%s",
        len(card_price_map), len(sealed_price_map), len(graded_price_map),
        price_elapsed, enrichment_warnings,
    )

    # Apply prices in-place
    for item in items:
        ctype = item.get("collectible_type")
        cid = item.get("collectible_id")
        if cid is None:
            continue
        price = 0.0
        if ctype == "card":
            cid_s = str(cid)
            condition_id = item.get("condition_id")
            # Try exact variant+condition first, then variant+null condition.
            price = _get_card_market_price(card_price_map, cid_s, condition_id)
        elif ctype == "sealed_product":
            price = sealed_price_map.get(str(cid), 0.0)
        elif ctype == "graded_card":
            price = graded_price_map.get(str(cid), 0.0)
        qty = _to_number(item.get("quantity"), 1.0)
        item["market_price"] = price
        item["estimated_value"] = round(price * qty, 4)
        # Keep internal lookup keys out of the public payload shape.
        if "condition_id" in item:
            item.pop("condition_id", None)

    return items, enrichment_warnings


def _query_public_profile_row(public_user_id: str) -> Dict[str, Any]:
    profile_select_candidates = [
        "id,username,display_name,avatar_url,bio,is_profile_public,location,favorite_tcg_id,created_at,view_count,profile_view_count,views_count",
        "id,username,display_name,avatar_url,bio,is_profile_public,location,favorite_tcg_id,created_at,view_count",
        "id,username,display_name,avatar_url,bio,is_profile_public,location,favorite_tcg_id,created_at",
    ]

    for select_clause in profile_select_candidates:
        try:
            result = (
                public_read_client.table("users")
                .select(select_clause)
                .eq("id", public_user_id)
                .limit(1)
                .execute()
            )
            row = _first_row(result)
            if isinstance(row, dict):
                return row
            logger.warning(
                "[public-profile-page] users query returned 0 rows user_id=%s select=%r",
                public_user_id,
                select_clause,
            )
        except Exception:
            logger.exception(
                "[public-profile-page] users query failed user_id=%s select=%r",
                public_user_id,
                select_clause,
            )

    raise PublicProfilePageError(status_code=500, message="Unable to fetch public profile", code="PROFILE_QUERY_FAILED")


def get_public_profile_page_payload(
    username: str,
    include_collection_items: bool = True,
    viewer_user_id: Optional[str] = None,
) -> Dict[str, Any]:
    total_started = time.perf_counter()
    warnings: list[str] = []
    timings: Dict[str, float] = {
        "username_resolution_ms": 0.0,
        "profile_query_ms": 0.0,
        "favorite_tcg_lookup_ms": 0.0,
        "summary_snapshot_lookup_ms": 0.0,
        "market_view_item_lookup_ms": 0.0,
        "lightweight_fallback_ms": 0.0,
        "price_enrichment_ms": 0.0,
        "total_backend_ms": 0.0,
    }

    requested_username = str(username or "").strip()
    if not requested_username:
        raise PublicProfilePageError(status_code=404, message="Public profile not found", code="PROFILE_NOT_FOUND")

    resolve_started = time.perf_counter()
    public_user, trace = resolve_public_user_by_username(
        requested_username,
        db_client=public_read_client,
    )
    timings["username_resolution_ms"] = _duration_ms(resolve_started)

    if not public_user or not public_user.get("id"):
        raise PublicProfilePageError(status_code=404, message="Public profile not found", code="PROFILE_NOT_FOUND")

    profile_started = time.perf_counter()
    profile = normalize_profile_username(_query_public_profile_row(str(public_user.get("id"))))
    timings["profile_query_ms"] = _duration_ms(profile_started)

    if not profile:
        raise PublicProfilePageError(status_code=404, message="Public profile not found", code="PROFILE_NOT_FOUND")

    if profile.get("is_profile_public") is False:
        if not viewer_user_id or str(viewer_user_id) != str(profile.get("id")):
            raise PublicProfilePageError(status_code=404, message="Public profile not found", code="PROFILE_NOT_FOUND")

    favorite_tcg_name = None
    favorite_tcg_id = profile.get("favorite_tcg_id")
    favorite_started = time.perf_counter()
    if favorite_tcg_id:
        try:
            tcg_result = (
                public_read_client.table("tcgs")
                .select("id,name")
                .eq("id", favorite_tcg_id)
                .limit(1)
                .execute()
            )
            tcg_row = _first_row(tcg_result)
            favorite_tcg_name = tcg_row.get("name") if isinstance(tcg_row, dict) else None
        except Exception:
            logger.exception(
                "[public-profile-page] favorite tcg lookup failed username=%s favorite_tcg_id=%s",
                requested_username,
                favorite_tcg_id,
            )
            warnings.append("Favorite TCG lookup failed")
    timings["favorite_tcg_lookup_ms"] = _duration_ms(favorite_started)

    summary_started = time.perf_counter()
    summary_source = "collection_summary_service.snapshot"
    try:
        from backend.db.services.collection_summary_service import get_user_collection_summary_snapshot

        snapshot_summary = get_user_collection_summary_snapshot(UUID(str(profile.get("id"))))
        if isinstance(snapshot_summary, dict) and snapshot_summary.get("row_found"):
            collection_summary = _normalize_public_summary_snapshot(snapshot_summary)
        else:
            collection_summary = _unavailable_public_summary()
            summary_source = "collection_summary_service.snapshot_unavailable"
            warnings.append("Collection summary snapshot unavailable")
    except Exception:
        logger.exception(
            "[public-profile-page] summary snapshot lookup failed username=%s user_id=%s",
            requested_username,
            profile.get("id"),
        )
        raise PublicProfilePageError(status_code=500, message="Unable to fetch public profile summary", code="SUMMARY_QUERY_FAILED")
    timings["summary_snapshot_lookup_ms"] = _duration_ms(summary_started)

    collection_items: list[Dict[str, Any]] = []
    items_source = "not_requested"

    if include_collection_items:
        # Market view (user_collection_items_with_market) is currently too slow for
        # synchronous public requests (~33s). Skip it entirely and use the lightweight
        # fallback as the primary source until the view performance is resolved.
        timings["market_view_item_lookup_ms"] = 0.0
        warnings.append("Market view skipped for performance — estimated_value may be unavailable")

        fallback_started = time.perf_counter()
        try:
            fallback_items, fallback_source = _load_lightweight_fallback_items(
                user_id=str(profile.get("id")),
                timeout_s=2.5,
                db_client=public_read_client,
            )
            collection_items = fallback_items
            items_source = fallback_source
            if fallback_source in {"fallback_failed", "partial_lightweight_fallback"}:
                warnings.append("Lightweight fallback collection item lookup was partial or failed")
        except Exception:
            logger.exception(
                "[public-profile-page] lightweight fallback failed username=%s user_id=%s",
                requested_username,
                profile.get("id"),
            )
            warnings.append("Lightweight fallback collection item lookup failed")
            items_source = "fallback_failed"
        timings["lightweight_fallback_ms"] = _duration_ms(fallback_started)

        # Enrich items with fast batched price lookups (concurrent, capped at 1.5s)
        if collection_items:
            price_started = time.perf_counter()
            try:
                collection_items, price_warnings = _enrich_items_with_prices(
                    collection_items,
                    db_client=public_read_client,
                    timeout_s=1.5,
                )
                warnings.extend(price_warnings)
                # If enrichment had failures, replace the stale market-skip warning
                if price_warnings:
                    warnings = [
                        w for w in warnings
                        if w != "Market view skipped for performance — estimated_value may be unavailable"
                    ]
                    warnings.insert(0, "Market view skipped for performance — estimated_value may be unavailable")
            except Exception:
                logger.exception(
                    "[public-profile-page] price enrichment failed username=%s user_id=%s",
                    requested_username, profile.get("id"),
                )
                warnings.append("Price enrichment failed — estimated_value may be unavailable")
            timings["price_enrichment_ms"] = _duration_ms(price_started)

    timings["total_backend_ms"] = _duration_ms(total_started)

    logger.info(
        "[public-profile-page] payload_ready username=%s profile_source=%s summary_source=%s items_source=%s item_count=%s timings=%s warnings=%s trace=%s",
        requested_username,
        "users",
        summary_source,
        items_source,
        len(collection_items),
        timings,
        warnings,
        {
            "lookup_strategy": trace.get("lookup_strategy") if isinstance(trace, dict) else None,
            "row_found": trace.get("row_found") if isinstance(trace, dict) else None,
        },
    )

    return {
        "profile": {
            **profile,
            "favorite_tcg_name": favorite_tcg_name,
        },
        "collection_summary": collection_summary,
        "collection_items": collection_items if include_collection_items else [],
        "meta": {
            "profile_source": "users",
            "summary_source": summary_source,
            "items_source": items_source,
            "warnings": warnings,
            "timings": timings,
        },
    }
