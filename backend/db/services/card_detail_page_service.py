"""Service for aggregating backend-first card detail page payloads."""

from __future__ import annotations

import logging
import time
from typing import Any, Dict, List, Optional, Tuple

from backend.db.clients.supabase_client import public_read_client

logger = logging.getLogger(__name__)

RAW_HISTORY_QUERY_LIMIT = 2000
MAX_RAW_HISTORY_POINTS_TOTAL = 500


class CardDetailPageError(Exception):
    """Structured error for card detail page reads."""

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


def _to_number(value: Any) -> Optional[float]:
    try:
        parsed = float(value)
        if parsed != parsed:
            return None
        return parsed
    except (TypeError, ValueError):
        return None


def _to_optional_str(value: Any) -> Optional[str]:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _condition_sort_key(row: Dict[str, Any]) -> Tuple[int, str]:
    name = str(row.get("condition") or "").strip().lower()
    if not name:
        return (2, "")
    if "near mint" in name or name == "nm":
        return (0, name)
    return (1, name)


def _graded_sort_key(row: Dict[str, Any]) -> Tuple[str, float, str]:
    company = str(row.get("grading_company_name") or "").strip().lower()
    grade_value = _to_number(row.get("grade_value"))
    special_label = str(row.get("special_label") or "").strip().lower()
    return (company, -(grade_value if grade_value is not None else -1.0), special_label)


def _resolve_images(variant_row: Dict[str, Any], card_row: Dict[str, Any]) -> Dict[str, Any]:
    variant_small = _to_optional_str(variant_row.get("image_small_url"))
    variant_large = _to_optional_str(variant_row.get("image_large_url"))
    card_small = _to_optional_str(card_row.get("image_small_url"))
    card_large = _to_optional_str(card_row.get("image_large_url"))

    image_small = variant_small or card_small
    image_large = variant_large or card_large or image_small

    if variant_small or variant_large:
        source = "card_variant"
    elif card_small or card_large:
        source = "card"
    else:
        source = "fallback"

    return {
        "image_small_url": image_small,
        "image_large_url": image_large,
        "image_source": source,
        "fallback_used": source == "fallback",
    }


def _is_usd_currency(value: Any) -> bool:
    text = _to_optional_str(value)
    if text is None:
        return True
    return text.upper() in {"USD", "US DOLLAR", "US_DOLLAR"}


def _date_key(value: Any) -> Optional[str]:
    text = _to_optional_str(value)
    if not text:
        return None
    if len(text) >= 10:
        return text[:10]
    return text


def _compute_series_delta(points: List[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    if len(points) < 2:
        return None

    first = points[0]
    last = points[-1]
    first_price = _to_number(first.get("market_price"))
    last_price = _to_number(last.get("market_price"))
    if first_price is None or last_price is None:
        return None

    absolute = last_price - first_price
    percent = (absolute / first_price * 100.0) if first_price != 0 else None
    return {
        "absolute": round(absolute, 4),
        "percent": round(percent, 4) if percent is not None else None,
        "from_date": first.get("date"),
        "to_date": last.get("date"),
    }


def _load_price_history(
    card_variant_id: str,
    condition_prices: List[Dict[str, Any]],
    graded_prices: List[Dict[str, Any]],
    sources: Dict[str, str],
    warnings: List[str],
) -> Dict[str, Any]:
    raw_history: List[Dict[str, Any]] = []
    graded_history: List[Dict[str, Any]] = []

    condition_lookup: Dict[str, str] = {}
    condition_filter_values: List[Any] = []
    for row in condition_prices:
        raw_condition_id = row.get("condition_id")
        condition_id = _to_optional_str(raw_condition_id)
        if not condition_id:
            continue
        condition_lookup[condition_id] = _to_optional_str(row.get("condition")) or "Condition"
        condition_filter_values.append(raw_condition_id)

    condition_ids = sorted(condition_lookup.keys())
    if condition_filter_values:
        try:
            raw_result = (
                public_read_client.table("card_variant_price_observations")
                .select("condition_id,market_price,high_price,low_price,currency,source,captured_at")
                .eq("card_variant_id", card_variant_id)
                .in_("condition_id", condition_filter_values)
                .order("captured_at", desc=True)
                .limit(RAW_HISTORY_QUERY_LIMIT)
                .execute()
            )
            raw_rows = raw_result.data or []

            deduped_daily: Dict[Tuple[str, str], Dict[str, Any]] = {}
            for row in raw_rows:
                condition_id = _to_optional_str(row.get("condition_id"))
                if not condition_id or condition_id not in condition_lookup:
                    continue
                if not _is_usd_currency(row.get("currency")):
                    continue
                date_key = _date_key(row.get("captured_at"))
                if not date_key:
                    continue
                if _to_number(row.get("market_price")) is None:
                    continue
                deduped_daily.setdefault((condition_id, date_key), row)

            grouped_points: Dict[str, List[Dict[str, Any]]] = {condition_id: [] for condition_id in condition_ids}
            for (condition_id, _), row in deduped_daily.items():
                grouped_points.setdefault(condition_id, []).append(
                    {
                        "date": _date_key(row.get("captured_at")),
                        "market_price": row.get("market_price"),
                        "high_price": row.get("high_price"),
                        "low_price": row.get("low_price"),
                        "source": row.get("source"),
                    }
                )

            non_empty_condition_ids = [cid for cid, points in grouped_points.items() if points]
            if non_empty_condition_ids:
                per_condition_cap = max(1, MAX_RAW_HISTORY_POINTS_TOTAL // len(non_empty_condition_ids))
            else:
                per_condition_cap = MAX_RAW_HISTORY_POINTS_TOTAL

            for condition_id in condition_ids:
                points = grouped_points.get(condition_id) or []
                points.sort(key=lambda point: str(point.get("date") or ""))
                if len(points) > per_condition_cap:
                    points = points[-per_condition_cap:]
                if not points:
                    continue
                raw_history.append(
                    {
                        "condition_id": condition_id,
                        "condition": condition_lookup.get(condition_id) or "Condition",
                        "points": points,
                        "delta": _compute_series_delta(points),
                    }
                )

            sources["card_variant_price_observations"] = "OK" if raw_history else "NO_ROW"
        except Exception as exc:
            logger.warning(
                "[card-detail-page] raw price history lookup failed card_variant_id=%s error=%s",
                card_variant_id,
                exc,
            )
            warnings.append("Failed to load raw price history")
            sources["card_variant_price_observations"] = "FAILED"
    else:
        sources["card_variant_price_observations"] = "SKIPPED_NO_CONDITIONS"

    # No graded historical observation source is currently wired in this codebase.
    # Keep graded history explicit and empty until a dedicated graded observations path exists.
    sources["graded_price_history"] = "UNAVAILABLE_NO_OBSERVATION_TABLE"
    if graded_prices:
        warnings.append("Graded price history is unavailable: no graded observation table is currently wired")

    return {
        "raw": raw_history,
        "graded": graded_history,
    }


def _select_era_row(era_id: Any, sources: Dict[str, str], warnings: List[str]) -> Optional[Dict[str, Any]]:
    if era_id is None:
        sources["eras"] = "SKIPPED_NO_ERA_ID"
        return None

    for select_clause in ("id,name,canonical_key", "id,name"):
        try:
            result = (
                public_read_client.table("eras")
                .select(select_clause)
                .eq("id", era_id)
                .limit(1)
                .execute()
            )
            row = _first_row(result)
            if row:
                sources["eras"] = "OK"
                return row
        except Exception as exc:
            logger.warning("[card-detail-page] era lookup failed era_id=%s select=%s error=%s", era_id, select_clause, exc)

    warnings.append("Failed to load era metadata")
    sources["eras"] = "FAILED"
    return None


def _load_simulation_context(
    card_variant_id: str,
    set_id: Optional[str],
    sources: Dict[str, str],
    warnings: List[str],
) -> Optional[Dict[str, Any]]:
    try:
        preferred_rows: List[Dict[str, Any]] = []
        if set_id:
            preferred_result = (
                public_read_client.table("explore_rip_statistics_latest")
                .select(
                    "set_id,calculation_run_id,run_at,"
                    "pack_score,relative_pack_score,pack_tier,profit_tier,safety_tier,stability_tier"
                )
                .eq("set_id", set_id)
                .order("run_at", desc=True)
                .limit(30)
                .execute()
            )
            preferred_rows = preferred_result.data or []
            sources["explore_rip_statistics_latest"] = "OK" if preferred_rows else "NO_ROW"
        else:
            sources["explore_rip_statistics_latest"] = "SKIPPED_NO_SET_ID"

        preferred_run_order = [
            str(row.get("calculation_run_id"))
            for row in preferred_rows
            if row.get("calculation_run_id") is not None
        ]

        sim_rows: List[Dict[str, Any]] = []
        if preferred_run_order:
            sim_result = (
                public_read_client.table("simulation_input_cards_with_near_mint_price")
                .select(
                    "calculation_run_id,card_id,card_variant_id,condition_id,card_name,rarity_bucket,"
                    "price_used,effective_pull_rate,ev_contribution,current_near_mint_price"
                )
                .eq("card_variant_id", card_variant_id)
                .in_("calculation_run_id", preferred_run_order)
                .execute()
            )
            sim_rows = sim_result.data or []

        if not sim_rows:
            fallback_result = (
                public_read_client.table("simulation_input_cards_with_near_mint_price")
                .select(
                    "calculation_run_id,card_id,card_variant_id,condition_id,card_name,rarity_bucket,"
                    "price_used,effective_pull_rate,ev_contribution,current_near_mint_price"
                )
                .eq("card_variant_id", card_variant_id)
                .limit(30)
                .execute()
            )
            sim_rows = fallback_result.data or []

        if not sim_rows:
            warnings.append("Simulation context unavailable for this card variant")
            sources["simulation_input_cards_with_near_mint_price"] = "NO_ROW"
            return None

        sources["simulation_input_cards_with_near_mint_price"] = "OK"

        run_priority = {run_id: idx for idx, run_id in enumerate(preferred_run_order)}

        sim_rows.sort(
            key=lambda row: (
                run_priority.get(str(row.get("calculation_run_id")), 10_000),
                str(row.get("calculation_run_id") or ""),
            )
        )
        selected_sim = sim_rows[0]
        run_id = _to_optional_str(selected_sim.get("calculation_run_id"))

        ranking_row = None
        if run_id and set_id:
            ranking_result = (
                public_read_client.table("set_pack_score_rankings_latest")
                .select(
                    "target_id,calculation_run_id,pack_score,relative_pack_score,pack_tier,"
                    "profit_tier,safety_tier,stability_tier"
                )
                .eq("target_id", set_id)
                .eq("calculation_run_id", run_id)
                .limit(1)
                .execute()
            )
            ranking_row = _first_row(ranking_result)
            sources["set_pack_score_rankings_latest"] = "OK" if ranking_row else "NO_ROW"
        else:
            sources["set_pack_score_rankings_latest"] = "SKIPPED_MISSING_KEYS"

        rip_row = None
        if run_id and set_id:
            rip_result = (
                public_read_client.table("explore_rip_statistics_latest")
                .select(
                    "set_id,calculation_run_id,pack_score,relative_pack_score,pack_tier,"
                    "profit_tier,safety_tier,stability_tier"
                )
                .eq("set_id", set_id)
                .eq("calculation_run_id", run_id)
                .limit(1)
                .execute()
            )
            rip_row = _first_row(rip_result)

        ranking_source = ranking_row or rip_row or {}

        return {
            "calculation_run_id": run_id,
            "set_id": set_id,
            "rarity_bucket": selected_sim.get("rarity_bucket"),
            "price_used": selected_sim.get("price_used"),
            "current_near_mint_price": selected_sim.get("current_near_mint_price"),
            "effective_pull_rate": selected_sim.get("effective_pull_rate"),
            "ev_contribution": selected_sim.get("ev_contribution"),
            "pack_score": ranking_source.get("pack_score"),
            "relative_pack_score": ranking_source.get("relative_pack_score"),
            "pack_tier": ranking_source.get("pack_tier"),
            "profit_tier": ranking_source.get("profit_tier"),
            "safety_tier": ranking_source.get("safety_tier"),
            "stability_tier": ranking_source.get("stability_tier"),
        }
    except Exception as exc:
        logger.warning("[card-detail-page] simulation context failed card_variant_id=%s error=%s", card_variant_id, exc)
        warnings.append("Failed to load simulation context")
        sources["simulation_input_cards_with_near_mint_price"] = "FAILED"
        return None


def _load_user_inventory_state(
    card_variant_id: str,
    viewer_user_id: Optional[str],
    sources: Dict[str, str],
    warnings: List[str],
) -> Dict[str, Any]:
    state = {
        "is_authenticated": False,
        "card_holdings": [],
        "graded_holdings": [],
    }

    if not viewer_user_id:
        sources["user_inventory_state"] = "SKIPPED_UNAUTHENTICATED"
        return state

    state["is_authenticated"] = True

    try:
        card_holdings_result = (
            public_read_client.table("user_card_holdings")
            .select("id,card_variant_id,condition_id,quantity")
            .eq("user_id", viewer_user_id)
            .eq("card_variant_id", card_variant_id)
            .execute()
        )
        card_rows = card_holdings_result.data or []
        state["card_holdings"] = [
            {
                "holding_id": row.get("id"),
                "card_variant_id": row.get("card_variant_id"),
                "condition_id": row.get("condition_id"),
                "quantity": row.get("quantity"),
            }
            for row in card_rows
        ]
    except Exception as exc:
        logger.warning(
            "[card-detail-page] card holdings lookup failed user_id=%s card_variant_id=%s error=%s",
            viewer_user_id,
            card_variant_id,
            exc,
        )
        warnings.append("Failed to load card holdings")

    try:
        graded_variant_result = (
            public_read_client.table("graded_card_variants")
            .select("id")
            .eq("card_variant_id", card_variant_id)
            .execute()
        )
        graded_variant_ids = [
            str(row.get("id"))
            for row in (graded_variant_result.data or [])
            if row.get("id") is not None
        ]

        if graded_variant_ids:
            graded_holdings_result = (
                public_read_client.table("user_graded_card_holdings")
                .select("id,graded_card_variant_id,quantity")
                .eq("user_id", viewer_user_id)
                .in_("graded_card_variant_id", graded_variant_ids)
                .execute()
            )
            graded_rows = graded_holdings_result.data or []
        else:
            graded_rows = []

        state["graded_holdings"] = [
            {
                "holding_id": row.get("id"),
                "graded_card_variant_id": row.get("graded_card_variant_id"),
                "quantity": row.get("quantity"),
            }
            for row in graded_rows
        ]

        sources["user_inventory_state"] = "OK"
    except Exception as exc:
        logger.warning(
            "[card-detail-page] graded holdings lookup failed user_id=%s card_variant_id=%s error=%s",
            viewer_user_id,
            card_variant_id,
            exc,
        )
        warnings.append("Failed to load graded holdings")
        sources["user_inventory_state"] = "PARTIAL_FAILURE"

    return state


def get_card_detail_page_payload(card_variant_id: str, viewer_user_id: Optional[str] = None) -> Dict[str, Any]:
    total_started = time.perf_counter()

    requested_card_variant_id = str(card_variant_id or "").strip()
    if not requested_card_variant_id:
        raise CardDetailPageError(
            status_code=400,
            message="card_variant_id is required",
            code="INVALID_CARD_VARIANT_ID",
        )

    warnings: List[str] = []
    sources: Dict[str, str] = {}
    timings: Dict[str, float] = {
        "identity_ms": 0.0,
        "variant_options_ms": 0.0,
        "condition_prices_ms": 0.0,
        "graded_prices_ms": 0.0,
        "price_history_ms": 0.0,
        "simulation_context_ms": 0.0,
        "user_inventory_state_ms": 0.0,
        "total_backend_ms": 0.0,
    }

    identity_started = time.perf_counter()
    variant_result = (
        public_read_client.table("card_variants")
        .select("id,card_id,printing_type,special_type,edition,image_small_url,image_large_url")
        .eq("id", requested_card_variant_id)
        .limit(1)
        .execute()
    )
    variant_row = _first_row(variant_result)
    if not variant_row:
        raise CardDetailPageError(
            status_code=404,
            message="Card variant not found",
            code="CARD_VARIANT_NOT_FOUND",
        )
    sources["card_variants"] = "OK"

    card_id = variant_row.get("card_id")
    card_result = (
        public_read_client.table("cards")
        .select("id,set_id,name,rarity,card_number,image_small_url,image_large_url")
        .eq("id", card_id)
        .limit(1)
        .execute()
    )
    card_row = _first_row(card_result)
    if not card_row:
        raise CardDetailPageError(
            status_code=500,
            message="Card detail lookup failed for selected variant",
            code="CARD_LOOKUP_FAILED",
        )
    sources["cards"] = "OK"

    set_id = card_row.get("set_id")
    set_row: Dict[str, Any] = {}
    if set_id is not None:
        try:
            set_result = (
                public_read_client.table("sets")
                .select(
                    "id,name,canonical_key,release_date,era_id,logo_image_url,symbol_image_url,hero_image_url"
                )
                .eq("id", set_id)
                .limit(1)
                .execute()
            )
            set_row = _first_row(set_result) or {}
            sources["sets"] = "OK" if set_row else "NO_ROW"
        except Exception as exc:
            logger.warning("[card-detail-page] set lookup failed set_id=%s error=%s", set_id, exc)
            warnings.append("Failed to load set metadata")
            sources["sets"] = "FAILED"
    else:
        sources["sets"] = "SKIPPED_NO_SET_ID"

    era_row = _select_era_row(set_row.get("era_id"), sources, warnings)
    timings["identity_ms"] = _duration_ms(identity_started)

    variant_options_started = time.perf_counter()
    variant_options: List[Dict[str, Any]] = []
    try:
        sibling_result = (
            public_read_client.table("card_variants")
            .select("id,printing_type,special_type,edition,image_small_url,image_large_url")
            .eq("card_id", card_id)
            .order("id", desc=False)
            .execute()
        )
        sibling_rows = sibling_result.data or []
        variant_options = [
            {
                "card_variant_id": row.get("id"),
                "printing_type": row.get("printing_type"),
                "special_type": row.get("special_type"),
                "edition": row.get("edition"),
                "image_small_url": row.get("image_small_url"),
                "image_large_url": row.get("image_large_url"),
            }
            for row in sibling_rows
        ]
        sources["variant_options"] = "OK"
    except Exception as exc:
        logger.warning("[card-detail-page] variant options lookup failed card_id=%s error=%s", card_id, exc)
        warnings.append("Failed to load variant options")
        sources["variant_options"] = "FAILED"
    timings["variant_options_ms"] = _duration_ms(variant_options_started)

    condition_prices_started = time.perf_counter()
    condition_prices: List[Dict[str, Any]] = []
    try:
        condition_result = (
            public_read_client.table("card_market_usd_latest_by_condition")
            .select(
                "card_id,set_id,set_name,card_name,card_number,rarity,variant_id,printing_type,special_type,edition,"
                "condition_id,condition,market_price,high_price,low_price,currency,source,captured_at,created_at"
            )
            .eq("variant_id", requested_card_variant_id)
            .execute()
        )
        condition_rows = condition_result.data or []
        condition_rows.sort(key=_condition_sort_key)
        condition_prices = [
            {
                "condition_id": row.get("condition_id"),
                "condition": row.get("condition"),
                "market_price": row.get("market_price"),
                "high_price": row.get("high_price"),
                "low_price": row.get("low_price"),
                "currency": row.get("currency"),
                "source": row.get("source"),
                "captured_at": row.get("captured_at"),
                "created_at": row.get("created_at"),
            }
            for row in condition_rows
        ]
        sources["card_market_usd_latest_by_condition"] = "OK"
    except Exception as exc:
        logger.warning(
            "[card-detail-page] condition prices lookup failed card_variant_id=%s error=%s",
            requested_card_variant_id,
            exc,
        )
        warnings.append("Failed to load condition prices")
        sources["card_market_usd_latest_by_condition"] = "FAILED"
    timings["condition_prices_ms"] = _duration_ms(condition_prices_started)

    graded_prices_started = time.perf_counter()
    graded_prices: List[Dict[str, Any]] = []
    try:
        graded_result = (
            public_read_client.table("graded_card_market_latest")
            .select(
                "card_id,variant_id,graded_card_variant_id,grade_value,special_label,grading_company_id,"
                "grading_company_name,market_price,low_price,high_price,created_at"
            )
            .eq("variant_id", requested_card_variant_id)
            .execute()
        )
        graded_rows = graded_result.data or []
        graded_rows.sort(key=_graded_sort_key)
        graded_prices = [
            {
                "graded_card_variant_id": row.get("graded_card_variant_id"),
                "grade_value": row.get("grade_value"),
                "special_label": row.get("special_label"),
                "grading_company_id": row.get("grading_company_id"),
                "grading_company_name": row.get("grading_company_name"),
                "market_price": row.get("market_price"),
                "low_price": row.get("low_price"),
                "high_price": row.get("high_price"),
                "created_at": row.get("created_at"),
            }
            for row in graded_rows
        ]
        sources["graded_card_market_latest"] = "OK"
    except Exception as exc:
        logger.warning(
            "[card-detail-page] graded prices lookup failed card_variant_id=%s error=%s",
            requested_card_variant_id,
            exc,
        )
        warnings.append("Failed to load graded prices")
        sources["graded_card_market_latest"] = "FAILED"
    timings["graded_prices_ms"] = _duration_ms(graded_prices_started)

    price_history_started = time.perf_counter()
    price_history = _load_price_history(
        card_variant_id=requested_card_variant_id,
        condition_prices=condition_prices,
        graded_prices=graded_prices,
        sources=sources,
        warnings=warnings,
    )
    timings["price_history_ms"] = _duration_ms(price_history_started)

    simulation_started = time.perf_counter()
    simulation_context = _load_simulation_context(
        card_variant_id=requested_card_variant_id,
        set_id=_to_optional_str(set_row.get("id") or set_id),
        sources=sources,
        warnings=warnings,
    )
    timings["simulation_context_ms"] = _duration_ms(simulation_started)

    inventory_started = time.perf_counter()
    user_inventory_state = _load_user_inventory_state(
        card_variant_id=requested_card_variant_id,
        viewer_user_id=viewer_user_id,
        sources=sources,
        warnings=warnings,
    )
    timings["user_inventory_state_ms"] = _duration_ms(inventory_started)

    images = _resolve_images(variant_row, card_row)

    response_payload = {
        "identity": {
            "card_variant_id": variant_row.get("id"),
            "card_id": card_row.get("id"),
            "name": card_row.get("name"),
            "card_number": card_row.get("card_number"),
            "rarity": card_row.get("rarity"),
            "printing_type": variant_row.get("printing_type"),
            "special_type": variant_row.get("special_type"),
            "edition": variant_row.get("edition"),
        },
        "images": images,
        "set": {
            "set_id": set_row.get("id") or set_id,
            "set_name": set_row.get("name"),
            "canonical_key": set_row.get("canonical_key"),
            "release_date": set_row.get("release_date"),
            "era_id": set_row.get("era_id"),
            "era_name": (era_row or {}).get("name"),
            "logo_image_url": set_row.get("logo_image_url"),
            "symbol_image_url": set_row.get("symbol_image_url"),
            "hero_image_url": set_row.get("hero_image_url"),
        },
        "variant_options": variant_options,
        "condition_prices": condition_prices,
        "graded_prices": graded_prices,
        "price_history": price_history,
        "simulation_context": simulation_context,
        "user_inventory_state": user_inventory_state,
        "meta": {
            "request": {
                "card_variant_id": requested_card_variant_id,
            },
            "sources": sources,
            "warnings": warnings,
            "timings": timings,
        },
    }

    timings["total_backend_ms"] = _duration_ms(total_started)
    return response_payload
