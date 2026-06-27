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
DEFAULT_TOP_CHASE_HISTORY_DAYS = 365
MAX_TOP_CHASE_HISTORY_DAYS = 365
DEFAULT_CARD_MOVERS_WINDOW_DAYS = 30
DEFAULT_CARD_MOVERS_LIMIT = 5
CARD_MOVERS_HISTORY_LOOKBACK_DAYS = 45
CARD_MOVERS_MIN_CURRENT_PRICE = 1.00
CARD_MOVERS_MIN_ABSOLUTE_MOVE = 0.25
CARD_MOVERS_MIN_HISTORY_SPAN_DAYS = 14
CARD_MOVERS_MAX_ABS_PERCENT_CHANGE = 300.0
_IN_CHUNK_SIZE = 500
_DELTA_KEYS = ("1D", "7D", "30D", "3M", "6M", "1Y", "lifetime")
SET_VALUE_SCOPES = ("standard", "hits", "top10")
DEFAULT_SET_VALUE_SCOPE = "standard"
SET_VALUE_SCOPE_LABELS = {
    "standard": "Standard",
    "hits": "Hits",
    "top10": "Top 10",
}

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


def _sanitize_value_scope(value: Any) -> str:
    normalized = str(value or "").strip().lower().replace("_", "").replace("-", "")
    aliases = {
        "": DEFAULT_SET_VALUE_SCOPE,
        "standard": "standard",
        "all": "standard",
        "hits": "hits",
        "hit": "hits",
        "top10": "top10",
        "topten": "top10",
    }
    return aliases.get(normalized, DEFAULT_SET_VALUE_SCOPE)


def _sanitize_top_chase_history_days(value: Any) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return DEFAULT_TOP_CHASE_HISTORY_DAYS
    return max(1, min(parsed, MAX_TOP_CHASE_HISTORY_DAYS))


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


def _load_price_observation_rows_for_window(
    *,
    variant_ids: List[str],
    condition_id: Optional[str],
    start_date: date,
    end_date: date,
    sources: Dict[str, str],
    source_key: str,
) -> List[Dict[str, Any]]:
    if not variant_ids or not condition_id:
        sources[source_key] = "NO_VARIANTS_OR_CONDITION"
        return []

    rows: List[Dict[str, Any]] = []
    for variant_id_chunk in _chunk(variant_ids):
        result = (
            public_read_client.table("card_variant_price_observations")
            .select("card_variant_id,condition_id,market_price,source,captured_at")
            .in_("card_variant_id", variant_id_chunk)
            .eq("condition_id", condition_id)
            .gt("market_price", 0)
            .gte("captured_at", start_date.isoformat())
            .lt("captured_at", end_date.isoformat())
            .order("captured_at", desc=False)
            .execute()
        )
        rows.extend(result.data or [])
    sources[source_key] = "OK"
    return rows


def _load_conditioned_latest_price_rows(
    variant_ids: List[str],
    condition_by_variant: Dict[str, str],
    sources: Dict[str, str],
) -> List[Dict[str, Any]]:
    if not variant_ids or not condition_by_variant:
        sources["card_market_usd_latest_by_condition_for_movers"] = "NO_VARIANTS_OR_CONDITIONS"
        return []

    rows: List[Dict[str, Any]] = []
    condition_ids = sorted(set(condition_by_variant.values()))
    for variant_id_chunk in _chunk(variant_ids):
        query = (
            public_read_client.table("card_market_usd_latest_by_condition")
            .select("variant_id,condition_id,market_price,source,captured_at")
            .in_("variant_id", variant_id_chunk)
        )
        if condition_ids:
            query = query.in_("condition_id", condition_ids)
        result = query.execute()
        for row in result.data or []:
            variant_id = _to_optional_str(row.get("variant_id"))
            condition_id = _to_optional_str(row.get("condition_id"))
            if variant_id and condition_id == condition_by_variant.get(variant_id):
                rows.append(row)
    sources["card_market_usd_latest_by_condition_for_movers"] = "OK"
    return rows


def _load_conditioned_price_observation_rows(
    variant_ids: List[str],
    condition_by_variant: Dict[str, str],
    days: int,
    sources: Dict[str, str],
) -> List[Dict[str, Any]]:
    if not variant_ids or not condition_by_variant:
        sources["card_variant_price_observations_for_movers"] = "NO_VARIANTS_OR_CONDITIONS"
        return []

    since = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
    rows: List[Dict[str, Any]] = []
    condition_ids = sorted(set(condition_by_variant.values()))
    for variant_id_chunk in _chunk(variant_ids):
        query = (
            public_read_client.table("card_variant_price_observations")
            .select("card_variant_id,condition_id,market_price,source,captured_at")
            .in_("card_variant_id", variant_id_chunk)
            .order("captured_at", desc=False)
            .limit(10000)
        )
        if condition_ids:
            query = query.in_("condition_id", condition_ids)
        result = query.execute()
        for row in result.data or []:
            variant_id = _to_optional_str(row.get("card_variant_id"))
            condition_id = _to_optional_str(row.get("condition_id"))
            if variant_id and condition_id == condition_by_variant.get(variant_id):
                rows.append(row)
    sources["card_variant_price_observations_for_movers"] = "OK"
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
        "legacy_card_to_canonical_id": legacy_card_to_canonical_id,
        "variant_to_canonical_id": variant_to_canonical_id,
        "variant_rows_by_id": variant_rows_by_id,
        "variant_ids": sorted(variant_to_canonical_id.keys()),
        "condition_id": condition_id,
    }


def _movement_label(amount: Optional[float]) -> Optional[str]:
    if amount is None:
        return None
    if amount > 0:
        return "heating_up"
    if amount < 0:
        return "cooling_off"
    return "flat"


def _public_card_movement(
    *,
    canonical_card: Dict[str, Any],
    variant_id: str,
    condition_id: Optional[str],
    current_price: float,
    current_source: Any,
    current_captured_at: Any,
    first_point: Dict[str, Any],
    last_point: Dict[str, Any],
    observation_count: int,
    window_days: int,
) -> Optional[Dict[str, Any]]:
    first_price = _to_optional_float(first_point.get("market_price"))
    last_observed_price = _to_optional_float(last_point.get("market_price"))
    if first_price is None or last_observed_price is None or current_price <= 0:
        return None

    first_date_key = _parse_date(first_point.get("captured_at"))
    last_date_key = _parse_date(last_point.get("captured_at") or current_captured_at)
    if not first_date_key or not last_date_key:
        return None

    try:
        history_span_days = (date.fromisoformat(last_date_key) - date.fromisoformat(first_date_key)).days
    except ValueError:
        history_span_days = 0

    amount = round(current_price - first_price, 2)
    percent = round((amount / first_price) * 100, 2) if first_price else None
    enough_history = observation_count >= 2 and history_span_days >= CARD_MOVERS_MIN_HISTORY_SPAN_DAYS
    passes_guardrails = (
        enough_history
        and current_price >= CARD_MOVERS_MIN_CURRENT_PRICE
        and abs(amount) >= CARD_MOVERS_MIN_ABSOLUTE_MOVE
        and percent is not None
        and abs(percent) <= CARD_MOVERS_MAX_ABS_PERCENT_CHANGE
    )
    if not passes_guardrails:
        return None

    score = round((abs(amount) * 0.72) + (min(abs(percent), 100.0) * current_price * 0.0028), 4)
    signed_score = score if amount > 0 else -score if amount < 0 else 0.0
    label = _movement_label(amount)
    image_url = _to_optional_str(canonical_card.get("image_small_url")) or _to_optional_str(canonical_card.get("image_large_url"))
    card_number = _to_optional_str(canonical_card.get("printed_number")) or _to_optional_str(canonical_card.get("number"))

    return {
        "cardId": _to_optional_str(canonical_card.get("id")),
        "card_id": _to_optional_str(canonical_card.get("id")),
        "cardVariantId": variant_id,
        "card_variant_id": variant_id,
        "setId": _to_optional_str(canonical_card.get("set_id")),
        "set_id": _to_optional_str(canonical_card.get("set_id")),
        "name": _to_optional_str(canonical_card.get("name")),
        "rarity": _to_optional_str(canonical_card.get("rarity")),
        "setNumber": card_number,
        "set_number": card_number,
        "cardNumber": card_number,
        "card_number": card_number,
        "imageUrl": image_url,
        "image_url": image_url,
        "imageSmallUrl": _to_optional_str(canonical_card.get("image_small_url")),
        "imageLargeUrl": _to_optional_str(canonical_card.get("image_large_url")),
        "currentPrice": round(current_price, 2),
        "current_price": round(current_price, 2),
        "marketPrice": round(current_price, 2),
        "market_price": round(current_price, 2),
        "change30dAmount": amount,
        "change_30d_amount": amount,
        "change30dPercent": percent,
        "change_30d_percent": percent,
        "movementScore": signed_score,
        "movement_score": signed_score,
        "movementLabel": label,
        "movement_label": label,
        "enoughHistory": enough_history,
        "enough_history": enough_history,
        "confidence": "medium" if observation_count >= 3 else "low",
        "windowDays": window_days,
        "window_days": window_days,
        "historyPointCount": observation_count,
        "history_point_count": observation_count,
        "historyStartDate": first_date_key,
        "history_start_date": first_date_key,
        "historyEndDate": last_date_key,
        "history_end_date": last_date_key,
        "conditionIdUsed": condition_id,
        "condition_id_used": condition_id,
        "source": _to_optional_str(current_source),
        "provider": _to_optional_str(current_source),
        "priceUpdatedAt": _to_optional_str(current_captured_at),
        "price_updated_at": _to_optional_str(current_captured_at),
    }


def _build_card_movements_from_context(
    context: Dict[str, Any],
    *,
    window_days: int = DEFAULT_CARD_MOVERS_WINDOW_DAYS,
    warnings: Optional[List[str]] = None,
    sources: Optional[Dict[str, str]] = None,
) -> List[Dict[str, Any]]:
    movement_sources = sources if sources is not None else {}
    near_mint_condition_id = _to_optional_str(context.get("condition_id"))
    variant_ids = list(context.get("variant_ids") or [])
    if not near_mint_condition_id or not variant_ids:
        if warnings is not None:
            warnings.append("Card movement is unavailable because Near Mint variant pricing is missing.")
        return []

    condition_by_variant = {variant_id: near_mint_condition_id for variant_id in variant_ids}
    latest_rows = _load_conditioned_latest_price_rows(variant_ids, condition_by_variant, movement_sources)
    observation_rows = _load_conditioned_price_observation_rows(
        variant_ids,
        condition_by_variant,
        max(window_days + 1, CARD_MOVERS_HISTORY_LOOKBACK_DAYS),
        movement_sources,
    )

    latest_by_variant: Dict[str, Dict[str, Any]] = {}
    for row in latest_rows:
        variant_id = _to_optional_str(row.get("variant_id"))
        price = _to_optional_float(row.get("market_price"))
        if not variant_id or price is None:
            continue
        existing = latest_by_variant.get(variant_id)
        existing_dt = _parse_datetime((existing or {}).get("captured_at"))
        row_dt = _parse_datetime(row.get("captured_at"))
        if existing is None or (row_dt is not None and (existing_dt is None or row_dt > existing_dt)):
            latest_by_variant[variant_id] = row

    observations_by_variant: Dict[str, List[Dict[str, Any]]] = {}
    for row in observation_rows:
        variant_id = _to_optional_str(row.get("card_variant_id"))
        price = _to_optional_float(row.get("market_price"))
        captured_at = _parse_datetime(row.get("captured_at"))
        if not variant_id or price is None or captured_at is None:
            continue
        observations_by_variant.setdefault(variant_id, []).append(row)

    best_by_canonical: Dict[str, Dict[str, Any]] = {}
    for variant_id, latest_row in latest_by_variant.items():
        canonical_id = (context.get("variant_to_canonical_id") or {}).get(variant_id)
        canonical_card = (context.get("canonical_by_id") or {}).get(canonical_id or "")
        current_price = _to_optional_float(latest_row.get("market_price"))
        if not canonical_id or not canonical_card or current_price is None:
            continue

        observations = sorted(
            observations_by_variant.get(variant_id, []),
            key=lambda row: _to_optional_str(row.get("captured_at")) or "",
        )
        if len(observations) < 2:
            continue
        latest_dt = _parse_datetime(latest_row.get("captured_at")) or _parse_datetime(observations[-1].get("captured_at"))
        if latest_dt is None:
            continue
        window_start_dt = latest_dt - timedelta(days=window_days)
        baseline_point = None
        last_before_window = None
        window_observations: List[Dict[str, Any]] = []
        for observation in observations:
            observed_dt = _parse_datetime(observation.get("captured_at"))
            if observed_dt is None:
                continue
            if observed_dt < window_start_dt:
                last_before_window = observation
                continue
            if baseline_point is None:
                baseline_point = observation
            window_observations.append(observation)
        if baseline_point is None:
            baseline_point = last_before_window
        latest_point = {
            "card_variant_id": variant_id,
            "condition_id": _to_optional_str(latest_row.get("condition_id")) or near_mint_condition_id,
            "market_price": current_price,
            "source": latest_row.get("source"),
            "captured_at": latest_row.get("captured_at"),
        }
        latest_point_dt = _parse_datetime(latest_point.get("captured_at"))
        last_window_dt = _parse_datetime(window_observations[-1].get("captured_at")) if window_observations else None
        if latest_point_dt is not None and (last_window_dt is None or latest_point_dt > last_window_dt):
            window_observations.append(latest_point)
        if baseline_point is None or not window_observations:
            continue
        history_points_for_confidence = [baseline_point, *window_observations]
        movement = _public_card_movement(
            canonical_card=canonical_card,
            variant_id=variant_id,
            condition_id=_to_optional_str(latest_row.get("condition_id")) or near_mint_condition_id,
            current_price=current_price,
            current_source=latest_row.get("source"),
            current_captured_at=latest_row.get("captured_at"),
            first_point=baseline_point,
            last_point=window_observations[-1],
            observation_count=len(history_points_for_confidence),
            window_days=window_days,
        )
        if movement is None:
            continue

        existing = best_by_canonical.get(canonical_id)
        if existing is None or abs(movement["movementScore"]) > abs(existing["movementScore"]):
            best_by_canonical[canonical_id] = movement

    return list(best_by_canonical.values())


def build_pokemon_set_card_movement_payload(
    set_id: str,
    *,
    limit: int = DEFAULT_CARD_MOVERS_LIMIT,
    window_days: int = DEFAULT_CARD_MOVERS_WINDOW_DAYS,
) -> Dict[str, Any]:
    warnings: List[str] = []
    sources: Dict[str, str] = {}
    set_row = _resolve_set_row(set_id)
    context = _build_market_context(set_row, warnings, sources)
    movements = _build_card_movements_from_context(
        context,
        window_days=window_days,
        warnings=warnings,
        sources=sources,
    )
    heating = sorted(
        [movement for movement in movements if movement.get("change30dAmount", 0) > 0],
        key=lambda movement: movement.get("movementScore") or 0,
        reverse=True,
    )
    cooling = sorted(
        [movement for movement in movements if movement.get("change30dAmount", 0) < 0],
        key=lambda movement: movement.get("movementScore") or 0,
    )

    return {
        "set": context.get("set"),
        "window": f"{window_days}D",
        "window_key": f"{window_days}D",
        "windowDays": window_days,
        "window_days": window_days,
        "movements": movements,
        "marketMovers": {
            "window": f"{window_days}D",
            "windowDays": window_days,
            "heatingUp": heating[:limit],
            "heating_up": heating[:limit],
            "coolingOff": cooling[:limit],
            "cooling_off": cooling[:limit],
            "all": movements,
        },
        "market_movers": {
            "window": f"{window_days}D",
            "window_days": window_days,
            "heating_up": heating[:limit],
            "cooling_off": cooling[:limit],
            "all": movements,
        },
        "meta": {
            "limit": limit,
            "windowDays": window_days,
            "window_days": window_days,
            "guardrails": {
                "minimumCurrentPrice": CARD_MOVERS_MIN_CURRENT_PRICE,
                "minimumAbsoluteMove": CARD_MOVERS_MIN_ABSOLUTE_MOVE,
                "minimumHistorySpanDays": CARD_MOVERS_MIN_HISTORY_SPAN_DAYS,
                "maximumAbsolutePercentChange": CARD_MOVERS_MAX_ABS_PERCENT_CHANGE,
            },
            "priceBasis": "Near Mint card_variant_price_observations and card_market_usd_latest_by_condition mapped to canonical Pokemon cards",
            "sources": sources,
            "warnings": warnings,
        },
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


def _canonical_id_for_simulation_row(
    row: Dict[str, Any],
    market_context: Dict[str, Any],
) -> Optional[str]:
    variant_id = _to_optional_str(row.get("card_variant_id"))
    direct_card_id = _to_optional_str(row.get("card_id"))
    variant_to_canonical_id = market_context.get("variant_to_canonical_id") or {}
    legacy_card_to_canonical_id = market_context.get("legacy_card_to_canonical_id") or {}
    return (
        _to_optional_str(variant_to_canonical_id.get(variant_id or ""))
        or _to_optional_str(legacy_card_to_canonical_id.get(direct_card_id or ""))
    )


def _load_canonical_top_chase_price_history(
    rows: List[Dict[str, Any]],
    days: int,
    market_context: Dict[str, Any],
    sources: Dict[str, str],
    warnings: Optional[List[str]] = None,
) -> Tuple[Dict[str, List[Dict[str, Any]]], Dict[str, Dict[str, Any]], Dict[str, Any]]:
    display_variant_to_canonical_id: Dict[str, str] = {}
    for row in rows:
        display_variant_id = _to_optional_str(row.get("card_variant_id"))
        canonical_id = _canonical_id_for_simulation_row(row, market_context)
        if display_variant_id and canonical_id:
            display_variant_to_canonical_id[display_variant_id] = canonical_id

    if not display_variant_to_canonical_id:
        sources["card_variant_price_observations_for_chase_trends"] = "NO_CANONICAL_CARD_MATCH"
        if warnings is not None:
            warnings.append("Top chase card trend history could not be linked to canonical checklist cards.")
        return {}, {}, {}

    variant_to_canonical_id: Dict[str, str] = dict(market_context.get("variant_to_canonical_id") or {})
    target_canonical_ids = set(display_variant_to_canonical_id.values())
    canonical_variant_ids = sorted(
        variant_id
        for variant_id, canonical_id in variant_to_canonical_id.items()
        if canonical_id in target_canonical_ids
    )
    condition_id = _to_optional_str(market_context.get("condition_id"))
    if not canonical_variant_ids or not condition_id:
        sources["card_variant_price_observations_for_chase_trends"] = "NO_CANONICAL_VARIANTS_OR_CONDITION"
        if warnings is not None:
            warnings.append("Top chase card trend history is unavailable because canonical variants or Near Mint condition are missing.")
        return {}, {}, {}

    latest_date: Optional[date] = None
    for row in rows:
        parsed = _parse_date(row.get("captured_at"))
        if parsed:
            try:
                parsed_date = date.fromisoformat(parsed)
            except ValueError:
                continue
            latest_date = parsed_date if latest_date is None or parsed_date > latest_date else latest_date
    if latest_date is None:
        latest_date = datetime.now(timezone.utc).date()

    window_start_date = latest_date - timedelta(days=max(days - 1, 0))
    window_end_exclusive = latest_date + timedelta(days=1)
    observation_rows = _load_price_observation_rows_for_window(
        variant_ids=canonical_variant_ids,
        condition_id=condition_id,
        start_date=window_start_date,
        end_date=window_end_exclusive,
        sources=sources,
        source_key="card_variant_price_observations_for_chase_trends",
    )

    points_by_canonical_date: Dict[str, Dict[str, Dict[str, Any]]] = {}
    captured_at_by_canonical_date: Dict[str, Dict[str, str]] = {}
    observation_count_by_canonical: Dict[str, int] = {}
    observation_count_by_canonical_date: Dict[str, Dict[str, int]] = {}
    observation_dates: List[date] = []
    for observation in observation_rows:
        source_variant_id = _to_optional_str(observation.get("card_variant_id"))
        canonical_id = _to_optional_str(variant_to_canonical_id.get(source_variant_id or ""))
        captured_at = _to_optional_str(observation.get("captured_at"))
        date_key = _parse_date(captured_at)
        price = _to_optional_float(observation.get("market_price"))
        if not canonical_id or not date_key or price is None:
            continue
        try:
            observation_dates.append(date.fromisoformat(date_key))
        except ValueError:
            continue
        observation_count_by_canonical[canonical_id] = observation_count_by_canonical.get(canonical_id, 0) + 1
        daily_counts = observation_count_by_canonical_date.setdefault(canonical_id, {})
        daily_counts[date_key] = daily_counts.get(date_key, 0) + 1
        existing_captured_at = captured_at_by_canonical_date.setdefault(canonical_id, {}).get(date_key)
        if existing_captured_at and captured_at and captured_at <= existing_captured_at:
            continue
        captured_at_by_canonical_date[canonical_id][date_key] = captured_at or date_key
        points_by_canonical_date.setdefault(canonical_id, {})[date_key] = {
            "date": date_key,
            "price": round(price, 2),
            "marketPrice": round(price, 2),
            "market_price": round(price, 2),
            "conditionId": condition_id,
            "condition_id": condition_id,
            "source": _to_optional_str(observation.get("source")),
            "provider": _to_optional_str(observation.get("source")),
            "captured_at": captured_at,
            "sourceVariantId": source_variant_id,
            "source_variant_id": source_variant_id,
            "sourceDate": date_key,
            "source_date": date_key,
            "isObserved": True,
            "is_observed": True,
            "isCarriedForward": False,
            "is_carried_forward": False,
            "dailyObservationCount": daily_counts[date_key],
            "daily_observation_count": daily_counts[date_key],
        }

    if not observation_dates:
        if warnings is not None:
            warnings.append("No canonical Near Mint top chase card price history exists in card_variant_price_observations yet.")
        return {}, {}, {}

    window_end_date = max(observation_dates)
    if window_end_date > latest_date:
        window_end_date = latest_date
    bucket_start_date = window_end_date - timedelta(days=max(days - 1, 0))
    bucket_dates = _inclusive_daily_bucket_dates(bucket_start_date, window_end_date)
    window_meta = {
        "asOfDate": window_end_date.isoformat(),
        "windowStart": bucket_start_date.isoformat(),
        "windowEnd": window_end_date.isoformat(),
        "windowDays": len(bucket_dates),
    }

    normalized: Dict[str, List[Dict[str, Any]]] = {}
    diagnostics: Dict[str, Dict[str, Any]] = {}
    variants_by_canonical: Dict[str, List[str]] = {}
    for variant_id, canonical_id in variant_to_canonical_id.items():
        if canonical_id in target_canonical_ids:
            variants_by_canonical.setdefault(canonical_id, []).append(variant_id)

    row_name_by_display_variant = {
        _to_optional_str(row.get("card_variant_id")) or "": _to_optional_str(row.get("card_name"))
        for row in rows
    }
    for display_variant_id, canonical_id in display_variant_to_canonical_id.items():
        points = points_by_canonical_date.get(canonical_id, {})
        sorted_dates = sorted(points.keys())
        buckets: List[Dict[str, Any]] = []
        carried_point: Optional[Dict[str, Any]] = None
        for date_key in sorted_dates:
            parsed_date = date.fromisoformat(date_key)
            if parsed_date < bucket_start_date:
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
                buckets.append(
                    {
                        **carried_point,
                        "date": date_key,
                        "sourceDate": carried_point.get("date"),
                        "source_date": carried_point.get("date"),
                        "isObserved": False,
                        "is_observed": False,
                        "isCarriedForward": True,
                        "is_carried_forward": True,
                        "dailyObservationCount": 0,
                        "daily_observation_count": 0,
                    }
                )
            else:
                buckets.append(
                    {
                        "date": date_key,
                        "price": None,
                        "marketPrice": None,
                        "market_price": None,
                        "conditionId": condition_id,
                        "condition_id": condition_id,
                        "source": None,
                        "provider": None,
                        "captured_at": None,
                        "sourceDate": None,
                        "source_date": None,
                        "isObserved": False,
                        "is_observed": False,
                        "isCarriedForward": True,
                        "is_carried_forward": True,
                        "dailyObservationCount": 0,
                        "daily_observation_count": 0,
                    }
                )

        normalized[display_variant_id] = buckets
        valid_prices = [
            _to_optional_float(point.get("price"))
            for point in buckets
            if _to_optional_float(point.get("price")) is not None
        ]
        actual_dates = [point.get("date") for point in buckets if point.get("isObserved")]
        first_price = valid_prices[0] if valid_prices else None
        last_price = valid_prices[-1] if valid_prices else None
        computed_delta_amount = round(last_price - first_price, 2) if first_price is not None and last_price is not None else None
        computed_delta_percent = (
            round(((last_price - first_price) / first_price) * 100, 2)
            if first_price is not None and last_price is not None and first_price != 0
            else None
        )
        chosen_daily_prices = [
            {
                "date": point.get("date"),
                "marketPrice": point.get("marketPrice"),
                "sourceVariantId": point.get("sourceVariantId"),
                "isObserved": bool(point.get("isObserved")),
            }
            for point in buckets
            if point.get("marketPrice") is not None
        ]
        diagnostics[display_variant_id] = {
            "canonicalCardId": canonical_id,
            "canonical_card_id": canonical_id,
            "cardName": row_name_by_display_variant.get(display_variant_id),
            "variantCount": len(variants_by_canonical.get(canonical_id, [])),
            "variant_count": len(variants_by_canonical.get(canonical_id, [])),
            "dailyObservationCount": observation_count_by_canonical.get(canonical_id, 0),
            "daily_observation_count": observation_count_by_canonical.get(canonical_id, 0),
            "chosenDailyPrices": chosen_daily_prices[-10:],
            "chosen_daily_prices": chosen_daily_prices[-10:],
            "actualObservedDateCount": len(actual_dates),
            "actual_observed_date_count": len(actual_dates),
            "historyPointCount": len(buckets),
            "historyStartDate": buckets[0].get("date") if buckets else None,
            "historyEndDate": buckets[-1].get("date") if buckets else None,
            "firstHistoryDate": buckets[0].get("date") if buckets else None,
            "lastHistoryDate": buckets[-1].get("date") if buckets else None,
            "firstHistoryPrice": first_price,
            "lastHistoryPrice": last_price,
            "latestHistoryPrice": last_price,
            "latestHistoryDate": buckets[-1].get("date") if buckets else None,
            "conditionIdUsed": condition_id,
            "sourceUsed": next((_to_optional_str(point.get("source")) for point in reversed(buckets) if _to_optional_str(point.get("source"))), None),
            "matchingConditionObservationCount": observation_count_by_canonical.get(canonical_id, 0),
            "computedDeltaAmount": computed_delta_amount,
            "computedDeltaPercent": computed_delta_percent,
        }

    logger.info(
        "[pokemon-set-market] canonical top chase history set_id=%s cards=%s variants=%s observations=%s window=%s..%s",
        (market_context.get("set") or {}).get("id"),
        len(display_variant_to_canonical_id),
        len(canonical_variant_ids),
        sum(observation_count_by_canonical.values()),
        window_meta.get("windowStart"),
        window_meta.get("windowEnd"),
    )

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
    display_price = round(float(latest_history_price), 2) if latest_history_price is not None else round(price, 2)
    display_price_updated_at = _to_optional_str(latest_history_date) or _to_optional_str(row.get("captured_at"))
    computed_delta_amount = (trend_diagnostics or {}).get("computedDeltaAmount")
    computed_delta_percent = (trend_diagnostics or {}).get("computedDeltaPercent")
    diagnostics = {
        "canonicalCardId": (trend_diagnostics or {}).get("canonicalCardId"),
        "canonical_card_id": (trend_diagnostics or {}).get("canonical_card_id") or (trend_diagnostics or {}).get("canonicalCardId"),
        "cardName": _to_optional_str(row.get("card_name")) or _to_optional_str((card or {}).get("name")),
        "cardVariantId": variant_id,
        "variantCount": (trend_diagnostics or {}).get("variantCount"),
        "variant_count": (trend_diagnostics or {}).get("variant_count"),
        "dailyObservationCount": (trend_diagnostics or {}).get("dailyObservationCount"),
        "daily_observation_count": (trend_diagnostics or {}).get("daily_observation_count"),
        "chosenDailyPrices": (trend_diagnostics or {}).get("chosenDailyPrices"),
        "chosen_daily_prices": (trend_diagnostics or {}).get("chosen_daily_prices"),
        "actualObservedDateCount": (trend_diagnostics or {}).get("actualObservedDateCount"),
        "actual_observed_date_count": (trend_diagnostics or {}).get("actual_observed_date_count"),
        "conditionIdUsed": (trend_diagnostics or {}).get("conditionIdUsed"),
        "historyPointCount": (trend_diagnostics or {}).get("historyPointCount", len(price_history)),
        "firstHistoryDate": (trend_diagnostics or {}).get("firstHistoryDate"),
        "lastHistoryDate": (trend_diagnostics or {}).get("lastHistoryDate"),
        "firstHistoryPrice": (trend_diagnostics or {}).get("firstHistoryPrice"),
        "lastHistoryPrice": (trend_diagnostics or {}).get("lastHistoryPrice"),
        "displayedPrice": display_price,
        "latestHistoryPrice": latest_history_price,
        "latestHistoryDate": latest_history_date,
        "sourceUsed": (trend_diagnostics or {}).get("sourceUsed"),
        "computedDeltaAmount": computed_delta_amount,
        "computedDeltaPercent": computed_delta_percent,
        "displayedHistoryPriceMismatch": (
            latest_history_price is not None
            and abs(display_price - float(latest_history_price)) >= 0.01
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
        "estimatedMarketPrice": display_price,
        "estimated_market_price": display_price,
        "marketPrice": display_price,
        "priceUsed": display_price,
        "price_used": display_price,
        "priceUpdatedAt": display_price_updated_at,
        "price_updated_at": display_price_updated_at,
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
        "canonicalCardId": (trend_diagnostics or {}).get("canonicalCardId"),
        "canonical_card_id": (trend_diagnostics or {}).get("canonical_card_id") or (trend_diagnostics or {}).get("canonicalCardId"),
        "variantCount": (trend_diagnostics or {}).get("variantCount"),
        "variant_count": (trend_diagnostics or {}).get("variant_count"),
        "dailyObservationCount": (trend_diagnostics or {}).get("dailyObservationCount"),
        "daily_observation_count": (trend_diagnostics or {}).get("daily_observation_count"),
        "historyDiagnostics": diagnostics,
        "history_diagnostics": diagnostics,
    }


def _load_simulation_top_market_cards_payload(
    set_row: Dict[str, Any],
    limit: int,
    history_days: int,
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
    market_context = _build_market_context(set_row, warnings, sources)
    history_by_variant, trend_diagnostics_by_variant, trend_window_meta = _load_canonical_top_chase_price_history(
        rows,
        history_days,
        market_context,
        sources,
        warnings,
    )
    if not history_by_variant:
        history_by_variant, trend_diagnostics_by_variant, trend_window_meta = _load_variant_price_history(
            rows,
            history_days,
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
            history_period_key=f"{history_days}D",
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
        "trend_days": history_days,
        "trend_window": trend_window_meta,
        "trend_diagnostics": [
            card.get("historyDiagnostics")
            for card in cards[:limit]
            if card.get("historyDiagnostics")
        ],
    }


def get_pokemon_set_top_market_cards_payload(set_id: str, limit: Any = None, days: Any = None) -> Dict[str, Any]:
    started = time.perf_counter()
    warnings: List[str] = []
    sources: Dict[str, str] = {}
    set_row = _resolve_set_row(set_id)
    clamped_limit = _sanitize_limit(limit)
    clamped_days = _sanitize_top_chase_history_days(days)

    simulation_payload = _load_simulation_top_market_cards_payload(set_row, clamped_limit, clamped_days, warnings, sources)
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


def _public_set_value_history_point(
    row: Dict[str, Any],
    *,
    is_carried_forward: bool = False,
    source_date: Optional[str] = None,
) -> Dict[str, Any]:
    snapshot_date = _parse_date(row.get("snapshot_date") or row.get("date"))
    set_value = _to_optional_float(row.get("set_value") or row.get("setValue"))
    priced_card_count = _to_optional_int(row.get("priced_card_count") or row.get("cardCountPriced") or row.get("card_count_priced"))
    total_card_count = _to_optional_int(row.get("total_card_count") or row.get("totalCardCount"))
    created_at = _to_optional_str(row.get("created_at") or row.get("createdAt"))
    updated_at = _to_optional_str(row.get("updated_at") or row.get("updatedAt"))
    source = _to_optional_str(row.get("source")) or "pokemon_set_value_daily_history"
    value_scope = _sanitize_value_scope(row.get("value_scope") or row.get("valueScope"))

    return {
        "date": snapshot_date,
        "valueScope": value_scope,
        "value_scope": value_scope,
        "setValue": round(set_value, 2) if set_value is not None else None,
        "set_value": round(set_value, 2) if set_value is not None else None,
        "cardCountPriced": priced_card_count,
        "card_count_priced": priced_card_count,
        "totalCardCount": total_card_count,
        "total_card_count": total_card_count,
        "source": source,
        "provider": source,
        "calculationRunId": None,
        "calculation_run_id": None,
        "createdAt": created_at,
        "created_at": created_at,
        "updatedAt": updated_at,
        "updated_at": updated_at,
        "isCarriedForward": is_carried_forward,
        "is_carried_forward": is_carried_forward,
        "sourceDate": source_date or snapshot_date,
        "source_date": source_date or snapshot_date,
    }


def _load_available_set_value_scopes(set_id: str, sources: Dict[str, str]) -> List[Dict[str, Any]]:
    try:
        result = (
            public_read_client.table("pokemon_set_value_daily_history")
                .select("value_scope,snapshot_date")
                .eq("set_id", set_id)
                .order("snapshot_date", desc=True)
                .execute()
        )
        sources["pokemon_set_value_daily_history_scopes"] = "OK"
    except Exception as exc:
        sources["pokemon_set_value_daily_history_scopes"] = "FAILED"
        logger.warning("[pokemon-set-market] daily set value scopes lookup failed set_id=%s: %s", set_id, exc)
        return []

    latest_by_scope: Dict[str, str] = {}
    for row in result.data or []:
        scope = _sanitize_value_scope(row.get("value_scope"))
        date_key = _parse_date(row.get("snapshot_date"))
        if not date_key:
            continue
        existing = latest_by_scope.get(scope)
        if existing is None or date_key > existing:
            latest_by_scope[scope] = date_key

    return [
        {
            "key": scope,
            "label": SET_VALUE_SCOPE_LABELS.get(scope, scope),
            "latestDate": latest_by_scope[scope],
        }
        for scope in SET_VALUE_SCOPES
        if scope in latest_by_scope
    ]


def _load_market_set_value_history(
    set_id: str,
    days: int,
    value_scope: str,
    warnings: List[str],
    sources: Dict[str, str],
) -> List[Dict[str, Any]]:
    try:
        latest_result = (
            public_read_client.table("pokemon_set_value_daily_history")
                .select("snapshot_date")
                .eq("set_id", set_id)
                .eq("value_scope", value_scope)
                .order("snapshot_date", desc=True)
                .limit(1)
                .execute()
        )
        latest_row = _first_row(latest_result)
        sources["pokemon_set_value_daily_history_latest"] = "OK"
    except Exception as exc:
        sources["pokemon_set_value_daily_history_latest"] = "FAILED"
        warnings.append("Failed to load daily set value market history.")
        logger.warning("[pokemon-set-market] daily set value latest lookup failed set_id=%s: %s", set_id, exc)
        return []

    latest_date_key = _parse_date((latest_row or {}).get("snapshot_date"))
    if not latest_date_key:
        warnings.append("No daily market set value history is available for this set.")
        return []

    try:
        latest_date = date.fromisoformat(latest_date_key)
    except ValueError:
        warnings.append("Daily market set value history has an invalid latest snapshot date.")
        return []

    start_date = latest_date - timedelta(days=max(days - 1, 0))
    try:
        history_result = (
            public_read_client.table("pokemon_set_value_daily_history")
                .select("snapshot_date,value_scope,set_value,priced_card_count,total_card_count,source,created_at,updated_at")
                .eq("set_id", set_id)
                .eq("value_scope", value_scope)
                .gte("snapshot_date", start_date.isoformat())
                .order("snapshot_date", desc=False)
                .execute()
        )
        raw_rows = list(history_result.data or [])
        sources["pokemon_set_value_daily_history"] = "OK"
    except Exception as exc:
        sources["pokemon_set_value_daily_history"] = "FAILED"
        warnings.append("Failed to load daily set value market history.")
        logger.warning("[pokemon-set-market] daily set value history failed set_id=%s: %s", set_id, exc)
        return []

    actual_by_day: Dict[str, Dict[str, Any]] = {}
    for row in raw_rows:
        date_key = _parse_date(row.get("snapshot_date"))
        value = _to_optional_float(row.get("set_value"))
        if not date_key or value is None:
            continue
        actual_by_day[date_key] = _public_set_value_history_point(row)

    if not actual_by_day:
        warnings.append("No daily market set value points are available for this set in the requested range.")
        return []

    try:
        first_actual_date = date.fromisoformat(min(actual_by_day.keys()))
    except ValueError:
        warnings.append("Daily market set value history has an invalid snapshot date.")
        return []

    history: List[Dict[str, Any]] = []
    carried_point: Optional[Dict[str, Any]] = None
    for bucket_date in _inclusive_daily_bucket_dates(first_actual_date, latest_date):
        date_key = bucket_date.isoformat()
        observed_point = actual_by_day.get(date_key)
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

    return history


def get_pokemon_set_value_history_payload(set_id: str, days: Any = None, value_scope: Any = None) -> Dict[str, Any]:
    started = time.perf_counter()
    warnings: List[str] = []
    sources: Dict[str, str] = {}
    set_row = _resolve_set_row(set_id)
    clamped_days = _sanitize_days(days)
    selected_scope = _sanitize_value_scope(value_scope)
    resolved_set_id = _to_optional_str(set_row.get("id")) or ""
    available_scopes = _load_available_set_value_scopes(resolved_set_id, sources)

    history = _load_market_set_value_history(
        resolved_set_id,
        clamped_days,
        selected_scope,
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
            "valueScope": selected_scope,
            "value_scope": selected_scope,
            "availableScopes": available_scopes,
            "available_scopes": available_scopes,
            "asOfDate": history[-1].get("date") if history else None,
            "windowStart": history[0].get("date") if history else None,
            "windowEnd": history[-1].get("date") if history else None,
            "windowDays": len(history),
            "priceBasis": "Near Mint card_variant_price_observations rolled up into pokemon_set_value_daily_history",
            "freshnessDependency": "Updates when card price observations are inserted or updated and the daily set value history refresh runs; simulator runs are not required.",
            "dateField": "pokemon_set_value_daily_history.snapshot_date",
            "valueField": "pokemon_set_value_daily_history.set_value",
            "historyGranularity": "daily",
            "historyGrouping": "one latest-known Near Mint card market price per card per UTC calendar day, summed by set",
            "sources": sources,
            "warnings": warnings,
            "timings": {"total_backend_ms": round((time.perf_counter() - started) * 1000, 3)},
        },
    }
