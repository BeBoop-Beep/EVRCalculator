from __future__ import annotations

import logging
import time
from datetime import date, datetime, timedelta, timezone
from typing import Any, Dict, Iterable, List, Optional, Tuple

from backend.db.clients.supabase_client import public_read_client

logger = logging.getLogger(__name__)

DEFAULT_TOP_MARKET_CARDS_LIMIT = 10
MAX_TOP_MARKET_CARDS_LIMIT = 50
DEFAULT_SET_VALUE_HISTORY_DAYS = 7
MAX_SET_VALUE_HISTORY_DAYS = 1825
TOP_CHASE_HISTORY_DAYS = 30
_IN_CHUNK_SIZE = 500
_DELTA_KEYS = ("1D", "7D", "30D", "3M", "6M", "1Y", "lifetime")

# TODO(pokemon-market-deltas): Replace ad hoc history reads with a daily snapshot
# machine shared across cards, sets, and sealed products. A future
# pokemon_set_value_snapshots table should be generated from the same canonical
# simulation-derived set-value logic used here and include:
# set_id, snapshot_date, set_value, card_count, source_calculation_run_id,
# delta_1d, delta_7d, delta_30d, delta_3m, delta_6m, delta_1y,
# delta_pct_1d, delta_pct_7d, delta_pct_30d, delta_pct_3m, delta_pct_6m,
# delta_pct_1y, created_at, updated_at.


class PokemonSetMarketError(Exception):
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


def _to_optional_float(value: Any) -> Optional[float]:
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return None
    return parsed if parsed > 0 else None


def _to_optional_int(value: Any) -> Optional[int]:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return None
    return parsed


def _sanitize_limit(value: Any) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return DEFAULT_TOP_MARKET_CARDS_LIMIT
    return max(1, min(parsed, MAX_TOP_MARKET_CARDS_LIMIT))


def _sanitize_days(value: Any) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return DEFAULT_SET_VALUE_HISTORY_DAYS
    return max(1, min(parsed, MAX_SET_VALUE_HISTORY_DAYS))


def _chunk(values: List[str], size: int = _IN_CHUNK_SIZE) -> Iterable[List[str]]:
    for idx in range(0, len(values), size):
        yield values[idx : idx + size]


def _normalize_text(value: Any) -> str:
    return " ".join(str(value or "").strip().lower().split())


def _normalize_number(value: Any) -> str:
    compact = str(value or "").strip().replace(" ", "").lower()
    if "/" in compact:
        compact = compact.split("/", 1)[0]
    stripped = compact.lstrip("0")
    return stripped or compact


def _card_match_keys(name: Any, number: Any) -> List[str]:
    normalized_name = _normalize_text(name)
    normalized_number = _normalize_number(number)
    if not normalized_name or not normalized_number:
        return []
    return [
        f"name+number:{normalized_name}:{normalized_number}",
        f"name+raw_number:{normalized_name}:{str(number or '').strip().replace(' ', '').lower()}",
    ]


def _parse_date(value: Any) -> Optional[str]:
    if not value:
        return None
    if isinstance(value, datetime):
        return value.astimezone(timezone.utc).date().isoformat()
    text = str(value).strip()
    if not text:
        return None
    if len(text) >= 10 and text[4] == "-" and text[7] == "-":
        return text[:10]
    try:
        return datetime.fromisoformat(text.replace("Z", "+00:00")).date().isoformat()
    except ValueError:
        return None


def _parse_datetime(value: Any) -> Optional[datetime]:
    if not value:
        return None
    if isinstance(value, datetime):
        parsed = value
    else:
        text = str(value).strip()
        if not text:
            return None
        try:
            parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
        except ValueError:
            return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _delta_placeholder() -> Dict[str, None]:
    return {key: None for key in _DELTA_KEYS}


def _first_row(result) -> Optional[Dict[str, Any]]:
    if result and result.data:
        return result.data[0]
    return None


def _resolve_set_row(set_id: str) -> Dict[str, Any]:
    resolved_set_id = _to_optional_str(set_id)
    if not resolved_set_id:
        raise PokemonSetMarketError(400, "set_id is required", "POKEMON_SET_ID_REQUIRED")

    filters = (
        ("id", resolved_set_id),
        ("canonical_key", resolved_set_id),
        ("pokemon_api_set_id", resolved_set_id),
    )
    for field, value in filters:
        try:
            result = (
                public_read_client.table("sets")
                .select("id,name,canonical_key,pokemon_api_set_id")
                .eq(field, value)
                .limit(1)
                .execute()
            )
            row = _first_row(result)
            if row:
                return row
        except Exception:
            logger.warning("[pokemon-set-market] set lookup failed field=%s set_id=%s", field, resolved_set_id)

    raise PokemonSetMarketError(404, "Pokemon set not found", "POKEMON_SET_NOT_FOUND")


def _load_near_mint_condition_id(warnings: List[str], sources: Dict[str, str]) -> Optional[str]:
    try:
        result = (
            public_read_client.table("conditions")
            .select("id,name")
            .eq("name", "Near Mint")
            .limit(1)
            .execute()
        )
        row = _first_row(result)
        condition_id = _to_optional_str((row or {}).get("id"))
        if condition_id:
            sources["conditions"] = "OK"
            return condition_id
        sources["conditions"] = "NO_NEAR_MINT_ROW"
        warnings.append("Near Mint condition row is unavailable; market price history is not available.")
    except Exception as exc:
        sources["conditions"] = "FAILED"
        warnings.append("Failed to resolve Near Mint condition for card market prices.")
        logger.warning("[pokemon-set-market] condition lookup failed: %s", exc)
    return None


def _load_canonical_cards(set_id: str, sources: Dict[str, str]) -> List[Dict[str, Any]]:
    result = (
        public_read_client.table("pokemon_canonical_cards")
        .select(
            "id,set_id,pokemon_tcg_api_card_id,name,rarity,number,printed_number,"
            "image_small_url,image_large_url"
        )
        .eq("set_id", set_id)
        .execute()
    )
    rows = list(result.data or [])
    sources["pokemon_canonical_cards"] = "OK"
    return rows


def _load_legacy_cards(set_id: str, sources: Dict[str, str]) -> List[Dict[str, Any]]:
    result = (
        public_read_client.table("cards")
        .select("id,set_id,name,rarity,card_number,image_small_url,image_large_url,pokemon_tcg_api_id")
        .eq("set_id", set_id)
        .execute()
    )
    rows = list(result.data or [])
    sources["cards"] = "OK"
    return rows


def _load_variants(legacy_card_ids: List[str], sources: Dict[str, str]) -> List[Dict[str, Any]]:
    if not legacy_card_ids:
        sources["card_variants"] = "NO_CARD_IDS"
        return []

    rows: List[Dict[str, Any]] = []
    for card_id_chunk in _chunk(legacy_card_ids):
        result = (
            public_read_client.table("card_variants")
            .select("id,card_id,pokemon_tcg_api_id,image_small_url,image_large_url")
            .in_("card_id", card_id_chunk)
            .execute()
        )
        rows.extend(result.data or [])
    sources["card_variants"] = "OK"
    return rows


def _load_latest_price_rows(
    variant_ids: List[str],
    condition_id: Optional[str],
    sources: Dict[str, str],
) -> List[Dict[str, Any]]:
    if not variant_ids or not condition_id:
        sources["card_market_usd_latest_by_condition"] = "NO_VARIANTS_OR_CONDITION"
        return []

    rows: List[Dict[str, Any]] = []
    for variant_id_chunk in _chunk(variant_ids):
        result = (
            public_read_client.table("card_market_usd_latest_by_condition")
            .select("variant_id,condition_id,market_price,source,captured_at")
            .in_("variant_id", variant_id_chunk)
            .eq("condition_id", condition_id)
            .execute()
        )
        rows.extend(result.data or [])
    sources["card_market_usd_latest_by_condition"] = "OK"
    return rows


def _load_price_observation_rows(
    variant_ids: List[str],
    condition_id: Optional[str],
    days: int,
    sources: Dict[str, str],
) -> List[Dict[str, Any]]:
    if not variant_ids or not condition_id:
        sources["card_variant_price_observations"] = "NO_VARIANTS_OR_CONDITION"
        return []

    since = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
    rows: List[Dict[str, Any]] = []
    for variant_id_chunk in _chunk(variant_ids):
        result = (
            public_read_client.table("card_variant_price_observations")
            .select("card_variant_id,condition_id,market_price,source,captured_at")
            .in_("card_variant_id", variant_id_chunk)
            .eq("condition_id", condition_id)
            .gte("captured_at", since)
            .order("captured_at", desc=False)
            .execute()
        )
        rows.extend(result.data or [])
    sources["card_variant_price_observations"] = "OK"
    return rows


def _build_market_context(set_row: Dict[str, Any], warnings: List[str], sources: Dict[str, str]) -> Dict[str, Any]:
    set_id = _to_optional_str(set_row.get("id")) or ""
    canonical_cards = _load_canonical_cards(set_id, sources)
    legacy_cards = _load_legacy_cards(set_id, sources)

    canonical_by_id = {
        str(card["id"]): card
        for card in canonical_cards
        if card.get("id") is not None
    }
    canonical_by_api_id = {
        str(card["pokemon_tcg_api_card_id"]): card
        for card in canonical_cards
        if card.get("pokemon_tcg_api_card_id") is not None
    }
    canonical_by_match_key: Dict[str, Dict[str, Any]] = {}
    for card in canonical_cards:
        for key in _card_match_keys(card.get("name"), card.get("number")) + _card_match_keys(
            card.get("name"), card.get("printed_number")
        ):
            canonical_by_match_key.setdefault(key, card)

    legacy_card_to_canonical_id: Dict[str, str] = {}
    for legacy_card in legacy_cards:
        canonical = None
        api_id = _to_optional_str(legacy_card.get("pokemon_tcg_api_id"))
        if api_id:
            canonical = canonical_by_api_id.get(api_id)
        if canonical is None:
            for key in _card_match_keys(legacy_card.get("name"), legacy_card.get("card_number")):
                canonical = canonical_by_match_key.get(key)
                if canonical is not None:
                    break
        if canonical and legacy_card.get("id") is not None:
            legacy_card_to_canonical_id[str(legacy_card["id"])] = str(canonical["id"])

    legacy_card_ids = [str(card["id"]) for card in legacy_cards if card.get("id") is not None]
    variants = _load_variants(legacy_card_ids, sources)

    variant_to_canonical_id: Dict[str, str] = {}
    variant_rows_by_id: Dict[str, Dict[str, Any]] = {}
    for variant in variants:
        variant_id = _to_optional_str(variant.get("id"))
        if not variant_id:
            continue
        variant_rows_by_id[variant_id] = variant
        canonical_id = legacy_card_to_canonical_id.get(str(variant.get("card_id")))
        variant_api_id = _to_optional_str(variant.get("pokemon_tcg_api_id"))
        if variant_api_id and variant_api_id in canonical_by_api_id:
            canonical_id = str(canonical_by_api_id[variant_api_id]["id"])
        if canonical_id:
            variant_to_canonical_id[variant_id] = canonical_id

    condition_id = _load_near_mint_condition_id(warnings, sources)

    if canonical_cards and legacy_cards and not variant_to_canonical_id:
        warnings.append("No canonical checklist cards could be matched to priced card variants.")

    return {
        "set": {
            "id": _to_optional_str(set_row.get("id")),
            "name": _to_optional_str(set_row.get("name")),
            "slug": _to_optional_str(set_row.get("canonical_key")),
            "pokemon_api_set_id": _to_optional_str(set_row.get("pokemon_api_set_id")),
        },
        "canonical_by_id": canonical_by_id,
        "variant_to_canonical_id": variant_to_canonical_id,
        "variant_rows_by_id": variant_rows_by_id,
        "variant_ids": sorted(variant_to_canonical_id.keys()),
        "condition_id": condition_id,
    }


def _public_market_card(
    *,
    card: Dict[str, Any],
    price: float,
    captured_at: Any,
    source: Any,
    variant: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    image_url = (
        _to_optional_str(card.get("image_small_url"))
        or _to_optional_str(card.get("image_large_url"))
        or _to_optional_str((variant or {}).get("image_small_url"))
        or _to_optional_str((variant or {}).get("image_large_url"))
    )
    return {
        "cardId": _to_optional_str(card.get("id")),
        "card_id": _to_optional_str(card.get("id")),
        "setId": _to_optional_str(card.get("set_id")),
        "set_id": _to_optional_str(card.get("set_id")),
        "name": _to_optional_str(card.get("name")),
        "imageUrl": image_url,
        "image_url": image_url,
        "imageSmallUrl": _to_optional_str(card.get("image_small_url")) or _to_optional_str((variant or {}).get("image_small_url")),
        "imageLargeUrl": _to_optional_str(card.get("image_large_url")) or _to_optional_str((variant or {}).get("image_large_url")),
        "rarity": _to_optional_str(card.get("rarity")),
        "setNumber": _to_optional_str(card.get("printed_number")) or _to_optional_str(card.get("number")),
        "set_number": _to_optional_str(card.get("printed_number")) or _to_optional_str(card.get("number")),
        "estimatedMarketPrice": round(price, 2),
        "estimated_market_price": round(price, 2),
        "marketPrice": round(price, 2),
        "priceUpdatedAt": _to_optional_str(captured_at),
        "price_updated_at": _to_optional_str(captured_at),
        "source": _to_optional_str(source),
        "provider": _to_optional_str(source),
        "deltas": _delta_placeholder(),
    }


def _load_latest_combined_set_run(set_id: str, sources: Dict[str, str]) -> Optional[Dict[str, Any]]:
    try:
        result = (
            public_read_client.table("calculation_runs")
            .select("id,created_at,target_type,target_id,valuation_method")
            .eq("target_type", "set")
            .eq("valuation_method", "combined")
            .eq("target_id", set_id)
            .order("created_at", desc=True)
            .limit(1)
            .execute()
        )
        sources["calculation_runs_latest_combined"] = "OK"
        return _first_row(result)
    except Exception as exc:
        sources["calculation_runs_latest_combined"] = "FAILED"
        logger.warning("[pokemon-set-market] latest combined run lookup failed set_id=%s: %s", set_id, exc)
        return None


def _load_simulation_input_card_rows(
    run_id: str,
    limit: int,
    sources: Dict[str, str],
) -> List[Dict[str, Any]]:
    try:
        result = (
            public_read_client.table("simulation_input_cards")
            .select(
                "card_id,card_variant_id,condition_id,card_name,rarity_bucket,"
                "price_source,price_used,captured_at"
            )
            .eq("calculation_run_id", run_id)
            .order("price_used", desc=True)
            .limit(limit)
            .execute()
        )
        sources["simulation_input_cards"] = "OK"
        return list(result.data or [])
    except Exception as exc:
        sources["simulation_input_cards"] = "FAILED"
        logger.warning("[pokemon-set-market] simulation input cards lookup failed run_id=%s: %s", run_id, exc)
        return []


def _load_simulation_card_image_context(
    rows: List[Dict[str, Any]],
    sources: Dict[str, str],
) -> Tuple[Dict[str, Dict[str, Any]], Dict[str, Dict[str, Any]]]:
    variant_ids = sorted(
        {
            str(row.get("card_variant_id"))
            for row in rows
            if row.get("card_variant_id") is not None
        }
    )
    direct_card_ids = sorted(
        {
            str(row.get("card_id"))
            for row in rows
            if row.get("card_id") is not None
        }
    )

    variant_lookup: Dict[str, Dict[str, Any]] = {}
    if variant_ids:
        try:
            variant_result = (
                public_read_client.table("card_variants")
                .select("id,card_id,image_small_url,image_large_url,pokemon_tcg_api_id")
                .in_("id", variant_ids)
                .execute()
            )
            variant_lookup = {
                str(row.get("id")): row
                for row in (variant_result.data or [])
                if row.get("id") is not None
            }
            sources["card_variants_for_simulation_inputs"] = "OK"
        except Exception as exc:
            sources["card_variants_for_simulation_inputs"] = "FAILED"
            logger.warning("[pokemon-set-market] card variant enrichment failed: %s", exc)
    else:
        sources["card_variants_for_simulation_inputs"] = "SKIPPED_NO_VARIANTS"

    derived_card_ids = {
        str(row.get("card_id"))
        for row in variant_lookup.values()
        if row.get("card_id") is not None
    }
    all_card_ids = sorted(set(direct_card_ids) | derived_card_ids)

    card_lookup: Dict[str, Dict[str, Any]] = {}
    if all_card_ids:
        try:
            card_result = (
                public_read_client.table("cards")
                .select("id,set_id,name,rarity,card_number,image_small_url,image_large_url,pokemon_tcg_api_id")
                .in_("id", all_card_ids)
                .execute()
            )
            card_lookup = {
                str(row.get("id")): row
                for row in (card_result.data or [])
                if row.get("id") is not None
            }
            sources["cards_for_simulation_inputs"] = "OK"
        except Exception as exc:
            sources["cards_for_simulation_inputs"] = "FAILED"
            logger.warning("[pokemon-set-market] card enrichment failed: %s", exc)
    else:
        sources["cards_for_simulation_inputs"] = "SKIPPED_NO_CARDS"

    return variant_lookup, card_lookup


def _daily_bucket_dates(end_date: date, days: int) -> List[date]:
    start_date = end_date - timedelta(days=max(days - 1, 0))
    return [start_date + timedelta(days=offset) for offset in range(days)]


def _inclusive_daily_bucket_dates(start_date: date, end_date: date) -> List[date]:
    if end_date < start_date:
        return []
    return [start_date + timedelta(days=offset) for offset in range((end_date - start_date).days + 1)]


def _load_variant_price_history(
    rows: List[Dict[str, Any]],
    days: int,
    sources: Dict[str, str],
    warnings: Optional[List[str]] = None,
) -> Tuple[Dict[str, List[Dict[str, Any]]], Dict[str, Dict[str, Any]], Dict[str, Any]]:
    condition_by_variant: Dict[str, str] = {}
    for row in rows:
        variant_id = _to_optional_str(row.get("card_variant_id"))
        condition_id = _to_optional_str(row.get("condition_id"))
        if variant_id and condition_id:
            condition_by_variant[variant_id] = condition_id

    variant_ids = sorted(condition_by_variant.keys())
    if not variant_ids:
        sources["card_variant_price_observations_for_chase_trends"] = "SKIPPED_NO_VARIANTS_OR_CONDITIONS"
        if warnings is not None:
            warnings.append("Top chase card trend history is unavailable because simulation input variants or conditions are missing.")
        return {}, {}, {}

    history_by_variant: Dict[str, Dict[str, Dict[str, Any]]] = {}
    matching_observation_count_by_variant: Dict[str, int] = {}
    matching_observation_dates: List[date] = []
    condition_ids = sorted(set(condition_by_variant.values()))
    try:
        for variant_id_chunk in _chunk(variant_ids):
            query = (
                public_read_client.table("card_variant_price_observations")
                .select("card_variant_id,condition_id,market_price,source,captured_at")
                .in_("card_variant_id", variant_id_chunk)
                .order("captured_at", desc=True)
                .limit(5000)
            )
            if condition_ids:
                query = query.in_("condition_id", condition_ids)
            result = query.execute()
            for row in result.data or []:
                variant_id = _to_optional_str(row.get("card_variant_id"))
                condition_id = _to_optional_str(row.get("condition_id"))
                price = _to_optional_float(row.get("market_price"))
                date_key = _parse_date(row.get("captured_at"))
                expected_condition_id = condition_by_variant.get(variant_id or "")
                if (
                    not variant_id
                    or not expected_condition_id
                    or condition_id != expected_condition_id
                    or price is None
                    or not date_key
                ):
                    continue
                try:
                    parsed_observation_date = date.fromisoformat(date_key)
                except ValueError:
                    continue
                matching_observation_count_by_variant[variant_id] = matching_observation_count_by_variant.get(variant_id, 0) + 1
                matching_observation_dates.append(parsed_observation_date)
                existing = history_by_variant.setdefault(variant_id, {}).get(date_key)
                captured_at = _to_optional_str(row.get("captured_at"))
                captured_dt = _parse_datetime(captured_at)
                existing_dt = _parse_datetime((existing or {}).get("captured_at"))
                if existing is None or (
                    captured_dt is not None
                    and (existing_dt is None or captured_dt > existing_dt)
                ):
                    history_by_variant[variant_id][date_key] = {
                        "date": date_key,
                        "price": round(price, 2),
                        "marketPrice": round(price, 2),
                        "conditionId": condition_id,
                        "condition_id": condition_id,
                        "source": _to_optional_str(row.get("source")),
                        "provider": _to_optional_str(row.get("source")),
                        "captured_at": captured_at,
                        "isCarriedForward": False,
                        "is_carried_forward": False,
                        "sourceDate": date_key,
                        "source_date": date_key,
                    }
        sources["card_variant_price_observations_for_chase_trends"] = "OK"
    except Exception as exc:
        sources["card_variant_price_observations_for_chase_trends"] = "FAILED"
        if warnings is not None:
            warnings.append("Failed to load top chase card price history.")
        logger.warning("[pokemon-set-market] chase price history lookup failed: %s", exc)
        return {}, {}, {}

    if not matching_observation_dates:
        if warnings is not None:
            warnings.append("No matching-condition top chase card price history exists in card_variant_price_observations yet.")
        return {}, {}, {}

    window_end_date = max(matching_observation_dates)
    window_start_date = window_end_date - timedelta(days=max(days - 1, 0))
    bucket_dates = _inclusive_daily_bucket_dates(window_start_date, window_end_date)
    window_meta = {
        "asOfDate": window_end_date.isoformat(),
        "windowStart": window_start_date.isoformat(),
        "windowEnd": window_end_date.isoformat(),
        "windowDays": len(bucket_dates),
    }

    normalized: Dict[str, List[Dict[str, Any]]] = {}
    diagnostics: Dict[str, Dict[str, Any]] = {}
    for variant_id in variant_ids:
        points = history_by_variant.get(variant_id, {})
        sorted_dates = sorted(points.keys())
        buckets: List[Dict[str, Any]] = []
        carried_point: Optional[Dict[str, Any]] = None
        for date_key in sorted_dates:
            parsed_date = date.fromisoformat(date_key)
            if parsed_date < window_start_date:
                carried_point = points[date_key]
                continue
            break

        for bucket_date in bucket_dates:
            date_key = bucket_date.isoformat()
            observed_point = points.get(date_key)
            if observed_point:
                carried_point = observed_point
                buckets.append(observed_point)
            elif carried_point:
                buckets.append({
                    **carried_point,
                    "date": date_key,
                    "isCarriedForward": True,
                    "is_carried_forward": True,
                    "sourceDate": carried_point.get("date"),
                    "source_date": carried_point.get("date"),
                })
            else:
                buckets.append({
                    "date": date_key,
                    "price": None,
                    "marketPrice": None,
                    "conditionId": condition_by_variant.get(variant_id),
                    "condition_id": condition_by_variant.get(variant_id),
                    "source": None,
                    "provider": None,
                    "captured_at": None,
                    "isCarriedForward": True,
                    "is_carried_forward": True,
                    "sourceDate": None,
                    "source_date": None,
                })

        normalized[variant_id] = buckets
        valid_prices = [
            _to_optional_float(point.get("price"))
            for point in buckets
            if _to_optional_float(point.get("price")) is not None
        ]
        first_price = valid_prices[0] if valid_prices else None
        last_price = valid_prices[-1] if valid_prices else None
        computed_delta_amount = round(last_price - first_price, 2) if first_price is not None and last_price is not None else None
        computed_delta_percent = (
            round(((last_price - first_price) / first_price) * 100, 2)
            if first_price is not None and last_price is not None and first_price != 0
            else None
        )
        diagnostics[variant_id] = {
            "historyPointCount": len(buckets),
            "historyStartDate": buckets[0].get("date") if buckets else None,
            "historyEndDate": buckets[-1].get("date") if buckets else None,
            "firstHistoryDate": buckets[0].get("date") if buckets else None,
            "lastHistoryDate": buckets[-1].get("date") if buckets else None,
            "firstHistoryPrice": first_price,
            "lastHistoryPrice": last_price,
            "latestHistoryPrice": last_price,
            "latestHistoryDate": buckets[-1].get("date") if buckets else None,
            "conditionIdUsed": condition_by_variant.get(variant_id),
            "sourceUsed": next((_to_optional_str(point.get("source")) for point in reversed(buckets) if _to_optional_str(point.get("source"))), None),
            "matchingConditionObservationCount": matching_observation_count_by_variant.get(variant_id, 0),
            "computedDeltaAmount": computed_delta_amount,
            "computedDeltaPercent": computed_delta_percent,
        }

    if warnings is not None and not any(
        any(_to_optional_float(point.get("price")) is not None for point in history)
        for history in normalized.values()
    ):
        warnings.append("No matching-condition top chase card price history exists in card_variant_price_observations yet.")

    return normalized, diagnostics, window_meta


def _delta_from_history(history: List[Dict[str, Any]], period_key: str = "lifetime") -> Dict[str, Optional[float]]:
    deltas = _delta_placeholder()
    valid_prices = [
        _to_optional_float(point.get("price"))
        for point in history
        if _to_optional_float(point.get("price")) is not None
    ]
    if len(valid_prices) < 2:
        return deltas
    first_price = valid_prices[0]
    last_price = valid_prices[-1]
    pct_delta = round(((last_price - first_price) / first_price) * 100, 2)
    if period_key in deltas:
        deltas[period_key] = pct_delta
    deltas["lifetime"] = pct_delta
    return deltas


def _public_simulation_card(
    *,
    row: Dict[str, Any],
    variant_lookup: Dict[str, Dict[str, Any]],
    card_lookup: Dict[str, Dict[str, Any]],
    price_history: List[Dict[str, Any]],
    history_period_key: str,
    trend_diagnostics: Optional[Dict[str, Any]] = None,
) -> Optional[Dict[str, Any]]:
    price = _to_optional_float(row.get("price_used"))
    if price is None:
        return None

    variant_id = _to_optional_str(row.get("card_variant_id"))
    direct_card_id = _to_optional_str(row.get("card_id"))
    variant = variant_lookup.get(variant_id or "")
    card_id = direct_card_id or _to_optional_str((variant or {}).get("card_id"))
    card = card_lookup.get(card_id or "")
    image_small = _to_optional_str((variant or {}).get("image_small_url")) or _to_optional_str((card or {}).get("image_small_url"))
    image_large = _to_optional_str((variant or {}).get("image_large_url")) or _to_optional_str((card or {}).get("image_large_url"))
    image_url = image_small or image_large
    rarity = _to_optional_str((card or {}).get("rarity")) or _to_optional_str(row.get("rarity_bucket"))
    card_number = _to_optional_str((card or {}).get("card_number"))
    latest_history_price = (trend_diagnostics or {}).get("latestHistoryPrice")
    latest_history_date = (trend_diagnostics or {}).get("latestHistoryDate")
    computed_delta_amount = (trend_diagnostics or {}).get("computedDeltaAmount")
    computed_delta_percent = (trend_diagnostics or {}).get("computedDeltaPercent")
    diagnostics = {
        "cardName": _to_optional_str(row.get("card_name")) or _to_optional_str((card or {}).get("name")),
        "cardVariantId": variant_id,
        "conditionIdUsed": (trend_diagnostics or {}).get("conditionIdUsed"),
        "historyPointCount": (trend_diagnostics or {}).get("historyPointCount", len(price_history)),
        "firstHistoryDate": (trend_diagnostics or {}).get("firstHistoryDate"),
        "lastHistoryDate": (trend_diagnostics or {}).get("lastHistoryDate"),
        "firstHistoryPrice": (trend_diagnostics or {}).get("firstHistoryPrice"),
        "lastHistoryPrice": (trend_diagnostics or {}).get("lastHistoryPrice"),
        "displayedPrice": round(price, 2),
        "latestHistoryPrice": latest_history_price,
        "latestHistoryDate": latest_history_date,
        "sourceUsed": (trend_diagnostics or {}).get("sourceUsed"),
        "computedDeltaAmount": computed_delta_amount,
        "computedDeltaPercent": computed_delta_percent,
        "displayedHistoryPriceMismatch": (
            latest_history_price is not None
            and abs(round(price, 2) - float(latest_history_price)) >= 0.01
        ),
    }

    return {
        "cardId": card_id,
        "card_id": card_id,
        "cardVariantId": variant_id,
        "card_variant_id": variant_id,
        "setId": _to_optional_str((card or {}).get("set_id")),
        "set_id": _to_optional_str((card or {}).get("set_id")),
        "name": _to_optional_str(row.get("card_name")) or _to_optional_str((card or {}).get("name")),
        "imageUrl": image_url,
        "image_url": image_url,
        "imageSmallUrl": image_small,
        "imageLargeUrl": image_large,
        "rarity": rarity,
        "setNumber": card_number,
        "set_number": card_number,
        "estimatedMarketPrice": round(price, 2),
        "estimated_market_price": round(price, 2),
        "marketPrice": round(price, 2),
        "priceUsed": round(price, 2),
        "price_used": round(price, 2),
        "priceUpdatedAt": _to_optional_str(row.get("captured_at")),
        "price_updated_at": _to_optional_str(row.get("captured_at")),
        "source": _to_optional_str(row.get("price_source")),
        "provider": _to_optional_str(row.get("price_source")),
        "priceHistory": price_history,
        "price_history": price_history,
        "deltas": _delta_from_history(price_history, history_period_key),
        "historyPointCount": (trend_diagnostics or {}).get("historyPointCount", len(price_history)),
        "historyStartDate": (trend_diagnostics or {}).get("historyStartDate"),
        "historyEndDate": (trend_diagnostics or {}).get("historyEndDate"),
        "conditionIdUsed": (trend_diagnostics or {}).get("conditionIdUsed"),
        "matchingConditionObservationCount": (trend_diagnostics or {}).get("matchingConditionObservationCount"),
        "historyDiagnostics": diagnostics,
        "history_diagnostics": diagnostics,
    }


def _load_simulation_top_market_cards_payload(
    set_row: Dict[str, Any],
    limit: int,
    warnings: List[str],
    sources: Dict[str, str],
) -> Optional[Dict[str, Any]]:
    set_id = _to_optional_str(set_row.get("id")) or ""
    run_row = _load_latest_combined_set_run(set_id, sources)
    run_id = _to_optional_str((run_row or {}).get("id"))
    if not run_id:
        warnings.append("No latest combined simulation run is available for top chase cards.")
        return None

    rows = _load_simulation_input_card_rows(run_id, limit, sources)
    if not rows:
        warnings.append("No simulation input card prices are available for the latest combined run.")
        return None

    variant_lookup, card_lookup = _load_simulation_card_image_context(rows, sources)
    history_by_variant, trend_diagnostics_by_variant, trend_window_meta = _load_variant_price_history(
        rows,
        TOP_CHASE_HISTORY_DAYS,
        sources,
        warnings,
    )

    cards: List[Dict[str, Any]] = []
    for row in rows:
        variant_id = _to_optional_str(row.get("card_variant_id"))
        public_card = _public_simulation_card(
            row=row,
            variant_lookup=variant_lookup,
            card_lookup=card_lookup,
            price_history=history_by_variant.get(variant_id or "", []),
            history_period_key=f"{TOP_CHASE_HISTORY_DAYS}D",
            trend_diagnostics=trend_diagnostics_by_variant.get(variant_id or ""),
        )
        if public_card:
            cards.append(public_card)

    cards.sort(key=lambda card: card.get("estimatedMarketPrice") or 0, reverse=True)

    return {
        "set": {
            "id": _to_optional_str(set_row.get("id")),
            "name": _to_optional_str(set_row.get("name")),
            "slug": _to_optional_str(set_row.get("canonical_key")),
            "pokemon_api_set_id": _to_optional_str(set_row.get("pokemon_api_set_id")),
        },
        "cards": cards[:limit],
        "run": {
            "id": run_id,
            "created_at": _to_optional_str((run_row or {}).get("created_at")),
        },
        "price_basis": "latest combined simulation_input_cards.price_used with matching simulation_input_cards.condition_id for trends",
        "trend_days": TOP_CHASE_HISTORY_DAYS,
        "trend_window": trend_window_meta,
        "trend_diagnostics": [
            card.get("historyDiagnostics")
            for card in cards[:limit]
            if card.get("historyDiagnostics")
        ],
    }


def get_pokemon_set_top_market_cards_payload(set_id: str, limit: Any = None) -> Dict[str, Any]:
    started = time.perf_counter()
    warnings: List[str] = []
    sources: Dict[str, str] = {}
    set_row = _resolve_set_row(set_id)
    clamped_limit = _sanitize_limit(limit)

    simulation_payload = _load_simulation_top_market_cards_payload(set_row, clamped_limit, warnings, sources)
    if simulation_payload is not None:
        return {
            "set": simulation_payload["set"],
            "cards": simulation_payload["cards"],
            "meta": {
                "limit": clamped_limit,
                "run": simulation_payload["run"],
                "priceBasis": simulation_payload["price_basis"],
                "trendDays": simulation_payload["trend_days"],
                "asOfDate": (simulation_payload.get("trend_window") or {}).get("asOfDate"),
                "windowStart": (simulation_payload.get("trend_window") or {}).get("windowStart"),
                "windowEnd": (simulation_payload.get("trend_window") or {}).get("windowEnd"),
                "windowDays": (simulation_payload.get("trend_window") or {}).get("windowDays"),
                "trendGranularity": "daily",
                "trendGrouping": "one latest matching-condition observation per card variant per UTC calendar day",
                "deltaAvailability": "card_variant_price_observations_for_latest_simulation_inputs",
                "diagnostics": simulation_payload.get("trend_diagnostics") or [],
                "sources": sources,
                "warnings": warnings,
                "timings": {"total_backend_ms": round((time.perf_counter() - started) * 1000, 3)},
            },
        }

    context = _build_market_context(set_row, warnings, sources)

    latest_rows = _load_latest_price_rows(context["variant_ids"], context["condition_id"], sources)
    best_by_card: Dict[str, Dict[str, Any]] = {}
    for row in latest_rows:
        variant_id = _to_optional_str(row.get("variant_id"))
        canonical_id = context["variant_to_canonical_id"].get(variant_id or "")
        price = _to_optional_float(row.get("market_price"))
        if not canonical_id or price is None:
            continue

        existing = best_by_card.get(canonical_id)
        if existing is None or price > existing["price"]:
            best_by_card[canonical_id] = {
                "price": price,
                "captured_at": row.get("captured_at"),
                "source": row.get("source"),
                "variant_id": variant_id,
            }

    cards: List[Dict[str, Any]] = []
    for canonical_id, price_info in best_by_card.items():
        card = context["canonical_by_id"].get(canonical_id)
        if not card:
            continue
        variant = context["variant_rows_by_id"].get(_to_optional_str(price_info.get("variant_id")) or "")
        cards.append(
            _public_market_card(
                card=card,
                price=price_info["price"],
                captured_at=price_info.get("captured_at"),
                source=price_info.get("source"),
                variant=variant,
            )
        )

    cards.sort(key=lambda row: row["estimatedMarketPrice"], reverse=True)

    return {
        "set": context["set"],
        "cards": cards[:clamped_limit],
        "meta": {
            "limit": clamped_limit,
            "priceBasis": "latest Near Mint card_variant_price_observations via card_market_usd_latest_by_condition",
            "deltaAvailability": "unavailable_without_card_price_history",
            "sources": sources,
            "warnings": warnings,
            "timings": {"total_backend_ms": round((time.perf_counter() - started) * 1000, 3)},
        },
    }


def _load_simulation_set_value_history(
    set_id: str,
    days: int,
    warnings: List[str],
    sources: Dict[str, str],
) -> List[Dict[str, Any]]:
    run_limit = min(5000, max(days * 12, days + 90, 250))
    try:
        runs_result = (
            public_read_client.table("calculation_runs")
            .select("id,created_at,target_type,target_id,valuation_method")
            .eq("target_type", "set")
            .eq("valuation_method", "combined")
            .eq("target_id", set_id)
            .order("created_at", desc=True)
            .limit(run_limit)
            .execute()
        )
        run_rows = list(runs_result.data or [])
        sources["calculation_runs_set_value_history"] = "OK"
    except Exception as exc:
        sources["calculation_runs_set_value_history"] = "FAILED"
        warnings.append("Failed to load calculation run history for set value trend.")
        logger.warning("[pokemon-set-market] calculation run history failed set_id=%s: %s", set_id, exc)
        return []

    run_ids = [
        str(row.get("id"))
        for row in run_rows
        if row.get("id") is not None
    ]
    if not run_ids:
        warnings.append("No combined calculation run history is available for this set.")
        return []

    derived_by_run_id: Dict[str, Dict[str, Any]] = {}
    try:
        for run_id_chunk in _chunk(run_ids):
            derived_result = (
                public_read_client.table("simulation_derived_metrics")
                .select("calculation_run_id,simulated_set_value,simulated_set_value_card_count")
                .in_("calculation_run_id", run_id_chunk)
                .execute()
            )
            for row in derived_result.data or []:
                run_id = _to_optional_str(row.get("calculation_run_id"))
                if run_id:
                    derived_by_run_id[run_id] = row
        sources["simulation_derived_metrics_set_value_history"] = "OK"
    except Exception as exc:
        sources["simulation_derived_metrics_set_value_history"] = "FAILED"
        warnings.append("Failed to load simulation-derived set value history.")
        logger.warning("[pokemon-set-market] derived set value history failed set_id=%s: %s", set_id, exc)
        return []

    valid_rows: List[Tuple[date, Optional[datetime], Dict[str, Any], Dict[str, Any], float]] = []
    for run_row in run_rows:
        run_id = _to_optional_str(run_row.get("id"))
        derived_row = derived_by_run_id.get(run_id or "")
        value = _to_optional_float((derived_row or {}).get("simulated_set_value"))
        created_at = _to_optional_str(run_row.get("created_at"))
        date_key = _parse_date(created_at)
        if not run_id or value is None or not date_key:
            continue
        try:
            parsed_date = date.fromisoformat(date_key)
        except ValueError:
            continue
        valid_rows.append((parsed_date, _parse_datetime(created_at), run_row, derived_row, value))

    if not valid_rows:
        warnings.append("No simulation-derived set value points are available for this set.")
        return []

    latest_date = max(row[0] for row in valid_rows)
    start_date = latest_date - timedelta(days=max(days - 1, 0))
    latest_by_day: Dict[str, Dict[str, Any]] = {}
    prior_point: Optional[Dict[str, Any]] = None

    for parsed_date, created_dt, run_row, derived_row, value in valid_rows:
        run_id = _to_optional_str(run_row.get("id"))
        card_count = _to_optional_int((derived_row or {}).get("simulated_set_value_card_count"))
        created_at = _to_optional_str(run_row.get("created_at"))
        date_key = parsed_date.isoformat()
        point = {
            "date": date_key,
            "setValue": round(value, 2),
            "set_value": round(value, 2),
            "cardCountPriced": card_count,
            "card_count_priced": card_count,
            "source": "simulation_derived_metrics",
            "provider": "simulation_derived_metrics",
            "calculationRunId": run_id,
            "calculation_run_id": run_id,
            "createdAt": created_at,
            "created_at": created_at,
            "isCarriedForward": False,
            "is_carried_forward": False,
            "sourceDate": date_key,
            "source_date": date_key,
        }
        if parsed_date < start_date:
            prior_dt = _parse_datetime((prior_point or {}).get("createdAt"))
            if prior_point is None or (created_dt is not None and (prior_dt is None or created_dt > prior_dt)):
                prior_point = point
            continue
        if parsed_date > latest_date:
            continue
        existing_dt = _parse_datetime((latest_by_day.get(date_key) or {}).get("createdAt"))
        if created_dt is not None and existing_dt is not None and created_dt <= existing_dt:
            continue
        latest_by_day[date_key] = point

    history: List[Dict[str, Any]] = []
    carried_point = prior_point
    for bucket_date in _daily_bucket_dates(latest_date, days):
        date_key = bucket_date.isoformat()
        observed_point = latest_by_day.get(date_key)
        if observed_point:
            carried_point = observed_point
            history.append(observed_point)
        elif carried_point:
            history.append({
                **carried_point,
                "date": date_key,
                "isCarriedForward": True,
                "is_carried_forward": True,
                "sourceDate": carried_point.get("date"),
                "source_date": carried_point.get("date"),
            })
        else:
            history.append({
                "date": date_key,
                "setValue": None,
                "set_value": None,
                "cardCountPriced": None,
                "card_count_priced": None,
                "source": "simulation_derived_metrics",
                "provider": "simulation_derived_metrics",
                "calculationRunId": None,
                "calculation_run_id": None,
                "createdAt": None,
                "created_at": None,
                "isCarriedForward": True,
                "is_carried_forward": True,
                "sourceDate": None,
                "source_date": None,
            })

    if not history:
        warnings.append("No simulation-derived set value points are available for this set.")

    return history


def get_pokemon_set_value_history_payload(set_id: str, days: Any = None) -> Dict[str, Any]:
    started = time.perf_counter()
    warnings: List[str] = []
    sources: Dict[str, str] = {}
    set_row = _resolve_set_row(set_id)
    clamped_days = _sanitize_days(days)

    history = _load_simulation_set_value_history(
        _to_optional_str(set_row.get("id")) or "",
        clamped_days,
        warnings,
        sources,
    )

    return {
        "set": {
            "id": _to_optional_str(set_row.get("id")),
            "name": _to_optional_str(set_row.get("name")),
            "slug": _to_optional_str(set_row.get("canonical_key")),
            "pokemon_api_set_id": _to_optional_str(set_row.get("pokemon_api_set_id")),
        },
        "history": history,
        "meta": {
            "days": clamped_days,
            "asOfDate": history[-1].get("date") if history else None,
            "windowStart": history[0].get("date") if history else None,
            "windowEnd": history[-1].get("date") if history else None,
            "windowDays": len(history),
            "priceBasis": "combined calculation_runs joined to simulation_derived_metrics.simulated_set_value",
            "historyGranularity": "daily",
            "historyGrouping": "one latest combined calculation run per UTC calendar day",
            "sources": sources,
            "warnings": warnings,
            "timings": {"total_backend_ms": round((time.perf_counter() - started) * 1000, 3)},
        },
    }
