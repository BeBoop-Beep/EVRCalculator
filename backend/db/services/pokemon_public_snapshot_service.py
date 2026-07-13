from __future__ import annotations

import json
import logging
import math
import re
import time
from datetime import date, datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

from backend.db.clients.supabase_client import public_read_client
from backend.desirability.card_appeal import (
    calculate_adjusted_card_appeal,
    calculate_scarcity_score,
    get_treatment_score,
    normalize_pull_probability,
)
from backend.desirability.set_components import build_card_appeal_correlation_dataset
from backend.desirability.set_validation import build_desirability_validation_payload, build_opening_set_audit, is_opening_set_row
from backend.db.services.explore_page_service import ExplorePageError
from backend.db.services.explore_rip_statistics_service import (
    ExploreRipStatisticsTargetsError,
    get_rip_statistics_targets_payload,
)
from backend.db.services.pokemon_set_cards_service import PokemonSetCardsError, get_pokemon_set_cards_payload
from backend.db.services.pokemon_set_market_service import (
    DEFAULT_CARD_MOVERS_LIMIT,
    DEFAULT_MARKET_MOVERS_WINDOW,
    DEFAULT_SET_VALUE_HISTORY_DAYS,
    DEFAULT_TOP_MARKET_CARDS_LIMIT,
    MARKET_MOVERS_WINDOWS,
    MAX_TOP_MARKET_CARDS_LIMIT,
    SET_VALUE_SCOPE_LABELS,
    SET_VALUE_SCOPES,
    PokemonSetMarketError,
    get_pokemon_set_top_market_cards_payload,
    get_pokemon_set_value_history_payload,
    resolve_pokemon_set_identifier,
)

logger = logging.getLogger(__name__)

DEFAULT_DASHBOARD_WINDOW = "365d"
DEFAULT_TOP_CHASE_DASHBOARD_WINDOW = "30d"
TOP_CHASE_HISTORY_SOURCE_WINDOW_DAYS = 365
TOP_CHASE_NEAR_MINT_CONDITION_ID = "4f8d1181-670e-4aea-937c-4d98d2e531a6"
TOP_CHASE_HISTORY_SOURCE = "card_variant_price_observations"
DEFAULT_RANKINGS_SCOPE = "rip-statistics"
DEFAULT_RANKINGS_LIMIT = 100
MAX_RANKINGS_LIMIT = 200
MIN_LIMIT = 1
RANKINGS_STALE_THRESHOLD_SECONDS = 300
RANKINGS_STALE_WARNING = "rankings snapshot is stale relative to set page snapshot"


def _to_optional_str(value: Any) -> Optional[str]:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _to_optional_datetime(value: Any) -> Optional[datetime]:
    text = _to_optional_str(value)
    if not text:
        return None
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _normalize_market_dashboard_window_key(value: Any, *, default: str = DEFAULT_DASHBOARD_WINDOW) -> str:
    return (_to_optional_str(value) or default).lower()


def _to_optional_float(value: Any) -> Optional[float]:
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return None
    return parsed if math.isfinite(parsed) else None


_UUID_RE = re.compile(
    r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$",
    re.IGNORECASE,
)


def _looks_like_uuid(value: str) -> bool:
    return bool(_UUID_RE.match(value))


def _first_row(result: Any) -> Optional[Dict[str, Any]]:
    if result and result.data:
        return result.data[0]
    return None


def _sanitize_limit(value: Any, *, default: int, max_value: int) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return default
    return max(MIN_LIMIT, min(parsed, max_value))


def _sanitize_days(value: Any, *, default: int = DEFAULT_SET_VALUE_HISTORY_DAYS) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return default
    return max(1, min(parsed, 1825))


def _sanitize_top_limit(value: Any) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return DEFAULT_TOP_MARKET_CARDS_LIMIT
    return max(1, min(parsed, 50))


def _sanitize_market_movers_window_key(value: Any) -> str:
    text = str(value or "").strip().upper()
    return text if text in MARKET_MOVERS_WINDOWS else DEFAULT_MARKET_MOVERS_WINDOW


def _sanitize_market_movers_limit(value: Any) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return DEFAULT_CARD_MOVERS_LIMIT
    return max(1, min(parsed, MAX_TOP_MARKET_CARDS_LIMIT))


_MARKET_MOVERS_WINDOW_DAYS_BY_KEY = {"1D": 1, "7D": 7, "30D": 30}


def _sanitize_scope(value: Any) -> str:
    normalized = str(value or "").strip().lower().replace("_", "").replace("-", "")
    aliases = {
        "": "standard",
        "standard": "standard",
        "all": "standard",
        "hits": "hits",
        "hit": "hits",
        "top10": "top10",
        "topten": "top10",
    }
    return aliases.get(normalized, "standard")


def _parse_date_key(value: Any) -> Optional[str]:
    if isinstance(value, date) and not isinstance(value, datetime):
        return value.isoformat()
    text = _to_optional_str(value)
    if not text:
        return None
    if len(text) >= 10 and text[4] == "-" and text[7] == "-":
        return text[:10]
    try:
        return datetime.fromisoformat(text.replace("Z", "+00:00")).date().isoformat()
    except ValueError:
        return None


def _market_dashboard_window_days(window: Any, days: Any = None) -> int:
    text = _normalize_market_dashboard_window_key(window)
    match = re.match(r"^(\d+)\s*d$", text)
    if match:
        return _sanitize_days(match.group(1), default=365)
    return _sanitize_days(days, default=365)


def _is_missing_snapshot_relation_error(exc: Exception) -> bool:
    payload = getattr(exc, "args", ())
    text = " ".join(str(part) for part in payload)
    for attr in ("code", "message", "details"):
        value = getattr(exc, attr, None)
        if value:
            text = f"{text} {value}"
    text = text.lower()
    return (
        "42p01" in text
        or "does not exist" in text
        or "could not find the table" in text
        or "relation" in text and "pokemon_set_market_dashboard_snapshot_latest" in text
    )


def _card_id_key(card: Dict[str, Any]) -> Optional[str]:
    return (
        _to_optional_str(card.get("id"))
        or _to_optional_str(card.get("cardId"))
        or _to_optional_str(card.get("card_id"))
    )


def _movement_card_id_key(movement: Dict[str, Any]) -> Optional[str]:
    return _to_optional_str(movement.get("cardId")) or _to_optional_str(movement.get("card_id"))


def _movement_fields(movement: Dict[str, Any], window: str = "30D") -> Dict[str, Any]:
    current_price = movement.get("currentPrice", movement.get("current_price"))
    change_amount = movement.get("change30dAmount", movement.get("change_30d_amount"))
    change_percent = movement.get("change30dPercent", movement.get("change_30d_percent"))
    movement_score = movement.get("movementScore", movement.get("movement_score"))
    movement_label = movement.get("movementLabel", movement.get("movement_label"))
    enough_history = movement.get("enoughHistory", movement.get("enough_history"))
    confidence = movement.get("confidence")
    normalized_window = str(window or "30D").upper()
    window_suffix = normalized_window.lower()
    window_fields = {
        f"change{window_suffix}Amount": change_amount,
        f"change{window_suffix}Percent": change_percent,
        f"movement{window_suffix}": {
            "currentPrice": current_price,
            "changeAmount": change_amount,
            "changePercent": change_percent,
            "score": movement_score,
            "label": movement_label,
            "enoughHistory": enough_history,
            "confidence": confidence,
        },
    }
    if normalized_window != "30D":
        return window_fields
    return {
        "currentPrice": current_price,
        "current_price": current_price,
        "marketPrice": current_price,
        "market_price": current_price,
        "change30dAmount": change_amount,
        "change_30d_amount": change_amount,
        "change30dPercent": change_percent,
        "change_30d_percent": change_percent,
        "movementScore": movement_score,
        "movement_score": movement_score,
        "movementLabel": movement_label,
        "movement_label": movement_label,
        "enoughHistory": enough_history,
        "enough_history": enough_history,
        "confidence": confidence,
        "movement30d": {
            "currentPrice": current_price,
            "current_price": current_price,
            "changeAmount": change_amount,
            "change_amount": change_amount,
            "changePercent": change_percent,
            "change_percent": change_percent,
            "score": movement_score,
            "movementScore": movement_score,
            "movement_score": movement_score,
            "label": movement_label,
            "movementLabel": movement_label,
            "movement_label": movement_label,
            "enoughHistory": enough_history,
            "enough_history": enough_history,
            "confidence": confidence,
        },
    }


def enrich_cards_payload_with_movements(
    payload: Dict[str, Any],
    movement_payload: Dict[str, Any],
    window: str = "30D",
) -> Dict[str, Any]:
    movements = list(movement_payload.get("movements") or [])
    if not movements:
        return payload

    movement_by_card_id = {
        key: movement
        for movement in movements
        for key in [_movement_card_id_key(movement)]
        if key
    }
    cards = []
    for card in list(payload.get("cards") or []):
        card_payload = dict(card or {})
        movement = movement_by_card_id.get(_card_id_key(card_payload) or "")
        if movement:
            card_payload.update(_movement_fields(movement, window=window))
        cards.append(card_payload)

    meta = dict(payload.get("meta") or {})
    market_movement_meta = {
        "window": movement_payload.get("window") or movement_payload.get("window_key") or "30D",
        "windowDays": movement_payload.get("windowDays") or movement_payload.get("window_days"),
        "source": "pokemon_set_card_movement_payload",
        "guardrails": (movement_payload.get("meta") or {}).get("guardrails"),
    }
    meta["marketMovement"] = market_movement_meta
    meta["market_movement"] = market_movement_meta
    return {**payload, "cards": cards, "meta": meta}


def _latest_composite_scores_for_references(reference_ids: List[int]) -> Dict[int, Dict[str, Any]]:
    clean_ids = sorted({reference_id for reference_id in reference_ids if reference_id is not None})
    if not clean_ids:
        return {}

    try:
        response = (
            public_read_client.table("pokemon_desirability_composite_scores")
            .select("pokemon_reference_id,pokedex_number,pokemon_name,desirability_score,created_at")
            .in_("pokemon_reference_id", clean_ids)
            .order("created_at", desc=True)
            .execute()
        )
    except Exception:
        logger.warning("[pokemon-snapshot] card desirability score lookup failed", exc_info=True)
        return {}

    scores_by_reference: Dict[int, Dict[str, Any]] = {}
    for row in response.data or []:
        try:
            reference_id = int(row.get("pokemon_reference_id"))
        except (TypeError, ValueError):
            continue
        scores_by_reference.setdefault(reference_id, row)
    return scores_by_reference


def _correlation(xs: List[float], ys: List[float]) -> Optional[float]:
    if len(xs) != len(ys) or len(xs) < 3:
        return None
    mean_x = sum(xs) / len(xs)
    mean_y = sum(ys) / len(ys)
    numerator = sum((x - mean_x) * (y - mean_y) for x, y in zip(xs, ys))
    denom_x = math.sqrt(sum((x - mean_x) ** 2 for x in xs))
    denom_y = math.sqrt(sum((y - mean_y) ** 2 for y in ys))
    denominator = denom_x * denom_y
    if denominator <= 0:
        return None
    return numerator / denominator


def _rank_values(values: List[float]) -> List[float]:
    indexed = sorted(enumerate(values), key=lambda item: item[1])
    ranks = [0.0] * len(values)
    index = 0
    while index < len(indexed):
        end = index
        while end + 1 < len(indexed) and indexed[end + 1][1] == indexed[index][1]:
            end += 1
        avg_rank = (index + 1 + end + 1) / 2.0
        for ranked_index in range(index, end + 1):
            ranks[indexed[ranked_index][0]] = avg_rank
        index = end + 1
    return ranks


def _pearson_pairs(pairs: List[tuple[float, float]]) -> Optional[float]:
    if len(pairs) < 3:
        return None
    corr = _correlation([pair[0] for pair in pairs], [pair[1] for pair in pairs])
    return round(corr, 6) if corr is not None else None


def _spearman_pairs(pairs: List[tuple[float, float]]) -> Optional[float]:
    if len(pairs) < 3:
        return None
    ranked_x = _rank_values([pair[0] for pair in pairs])
    ranked_y = _rank_values([pair[1] for pair in pairs])
    corr = _correlation(ranked_x, ranked_y)
    return round(corr, 6) if corr is not None else None


def _correlation_interpretation(value: Optional[float]) -> str:
    if value is None:
        return "insufficient_data"
    if value < 0.50:
        return "healthy_separation"
    if value <= 0.70:
        return "watch_carefully"
    return "likely_overlap"


def _correlation_card_price(card: Dict[str, Any], prices_by_card: Optional[Dict[str, Any]]) -> Optional[float]:
    price_info = (prices_by_card or {}).get(str(card.get("id"))) if card.get("id") is not None else None
    if isinstance(price_info, dict):
        price = _to_optional_float(
            price_info.get("market_price")
            if price_info.get("market_price") is not None
            else price_info.get("marketPrice")
        )
        if price is not None and price > 0:
            return price
    price = _to_optional_float(
        card.get("marketPrice")
        if card.get("marketPrice") is not None
        else card.get("market_price")
        if card.get("market_price") is not None
        else card.get("currentPrice")
        if card.get("currentPrice") is not None
        else card.get("current_price")
    )
    return price if price is not None and price > 0 else None


def _build_card_appeal_market_price_correlation(
    *,
    cards: List[Dict[str, Any]],
    links: List[Dict[str, Any]],
    scores_by_reference: Dict[int, Dict[str, Any]],
    prices_by_card: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    dataset = build_card_appeal_correlation_dataset(
        cards=cards,
        links=links,
        scores_by_reference=scores_by_reference,
        prices_by_card=prices_by_card,
    )
    pairs = [
        (
            _to_optional_float(row.get("subject_desirability_score")) or 0.0,
            _to_optional_float(row.get("market_price")) or 0.0,
        )
        for row in dataset.get("rows") or []
        if _to_optional_float(row.get("subject_desirability_score")) is not None
        and _to_optional_float(row.get("market_price")) is not None
    ]
    pure_rows_by_card = {
        str(row.get("pokemon_canonical_card_id")): row
        for row in dataset.get("rows") or []
        if row.get("pokemon_canonical_card_id") is not None
    }
    rows = []
    for row in dataset.get("rows") or []:
        market_price = _to_optional_float(row.get("market_price"))
        subject_score = _to_optional_float(row.get("subject_desirability_score"))
        if market_price is None or subject_score is None:
            continue
        rows.append(
            {
                "pokemon_canonical_card_id": row.get("pokemon_canonical_card_id"),
                "pokemonCanonicalCardId": row.get("pokemon_canonical_card_id"),
                "card_name": row.get("card_name"),
                "cardName": row.get("card_name"),
                "name": row.get("card_name"),
                "printed_number": row.get("printed_number"),
                "printedNumber": row.get("printed_number"),
                "rarity": row.get("rarity"),
                "market_price": market_price,
                "marketPrice": market_price,
                "subject_desirability_score": subject_score,
                "subjectDesirabilityScore": subject_score,
                "pokemonDesirabilityScore": subject_score,
                "treatment_score": _to_optional_float(get_treatment_score(row.get("rarity"))),
                "treatmentScore": _to_optional_float(get_treatment_score(row.get("rarity"))),
                "card_appeal_score": calculate_adjusted_card_appeal(
                    subject_score,
                    get_treatment_score(row.get("rarity")),
                    None,
                ),
                "cardAppealScore": calculate_adjusted_card_appeal(
                    subject_score,
                    get_treatment_score(row.get("rarity")),
                    None,
                ),
                "is_hit_eligible": bool(row.get("is_hit_eligible")),
                "isHitEligible": bool(row.get("is_hit_eligible")),
            }
        )
    plot_rows = []
    for card in cards:
        if not isinstance(card, dict):
            continue
        card_id = _to_optional_str(card.get("id"))
        if not card_id:
            continue
        market_price = _correlation_card_price(card, prices_by_card)
        if market_price is None:
            continue
        pure_row = pure_rows_by_card.get(card_id)
        subject_score = _to_optional_float((pure_row or {}).get("subject_desirability_score"))
        treatment_score = _to_optional_float(get_treatment_score(card.get("rarity")))
        card_appeal_score = calculate_adjusted_card_appeal(subject_score, treatment_score, None)
        if subject_score is None and treatment_score is None and card_appeal_score is None:
            continue
        is_hit_eligible = bool((pure_row or {}).get("is_hit_eligible"))
        plot_rows.append(
            {
                "pokemon_canonical_card_id": card_id,
                "pokemonCanonicalCardId": card_id,
                "card_name": card.get("name"),
                "cardName": card.get("name"),
                "name": card.get("name"),
                "printed_number": card.get("printed_number") or card.get("number"),
                "printedNumber": card.get("printed_number") or card.get("number"),
                "rarity": card.get("rarity"),
                "market_price": market_price,
                "marketPrice": market_price,
                "subject_desirability_score": subject_score,
                "subjectDesirabilityScore": subject_score,
                "pokemonDesirabilityScore": subject_score,
                "treatment_score": treatment_score,
                "treatmentScore": treatment_score,
                "card_appeal_score": card_appeal_score,
                "cardAppealScore": card_appeal_score,
                "adjusted_card_appeal_score": card_appeal_score,
                "adjustedCardAppealScore": card_appeal_score,
                "has_pure_demand_score": subject_score is not None,
                "hasPureDemandScore": subject_score is not None,
                "has_treatment_score": treatment_score is not None,
                "hasTreatmentScore": treatment_score is not None,
                "has_card_appeal_score": card_appeal_score is not None,
                "hasCardAppealScore": card_appeal_score is not None,
                "is_hit_eligible": is_hit_eligible,
                "isHitEligible": is_hit_eligible,
            }
        )
    pure_available_count = sum(1 for row in plot_rows if row.get("subject_desirability_score") is not None)
    treatment_available_count = sum(1 for row in plot_rows if row.get("treatment_score") is not None)
    card_appeal_available_count = sum(1 for row in plot_rows if row.get("card_appeal_score") is not None)
    pearson = _pearson_pairs(pairs)
    spearman = _spearman_pairs(pairs)
    max_abs = max(abs(pearson or 0.0), abs(spearman or 0.0)) if pairs else None
    return {
        **(dataset.get("diagnostics") or {}),
        "n": len(pairs),
        "pearson": pearson,
        "spearman": spearman,
        "interpretation": _correlation_interpretation(max_abs),
        "sample_source": "canonical_checklist_cards",
        "rows": rows,
        "plot_rows": plot_rows,
        "plotRows": plot_rows,
        "plotted_count": len(plot_rows),
        "plottedCount": len(plot_rows),
        "metric_diagnostics": {
            "purePokemonDemand": {
                **(dataset.get("diagnostics") or {}),
                "sample_source": "canonical_checklist_cards",
                "included_policy": "canonical priced cards with a desirability link and linked Pokemon desirability score",
            },
            "cardAppeal": {
                "canonical_count": (dataset.get("diagnostics") or {}).get("canonical_count"),
                "priced_count": (dataset.get("diagnostics") or {}).get("priced_count"),
                "pure_demand_available_count": pure_available_count,
                "treatment_available_count": treatment_available_count,
                "card_appeal_available_count": card_appeal_available_count,
                "included_count": card_appeal_available_count,
                "excluded_missing_card_appeal_count": max(0, ((dataset.get("diagnostics") or {}).get("priced_count") or 0) - card_appeal_available_count),
                "sample_source": "canonical_priced_cards_with_card_appeal_score",
                "included_policy": "canonical priced cards with pure Pokemon demand and treatment score",
            },
            "treatmentScore": {
                "canonical_count": (dataset.get("diagnostics") or {}).get("canonical_count"),
                "priced_count": (dataset.get("diagnostics") or {}).get("priced_count"),
                "treatment_available_count": treatment_available_count,
                "included_count": treatment_available_count,
                "excluded_missing_treatment_count": max(0, ((dataset.get("diagnostics") or {}).get("priced_count") or 0) - treatment_available_count),
                "sample_source": "canonical_priced_cards_with_treatment_score",
                "included_policy": "canonical priced cards with treatment score",
            },
        },
        "metricDiagnostics": {
            "purePokemonDemand": {
                **(dataset.get("diagnostics") or {}),
                "sampleSource": "canonical_checklist_cards",
                "includedPolicy": "canonical priced cards with a desirability link and linked Pokemon desirability score",
            },
            "cardAppeal": {
                "canonicalCount": (dataset.get("diagnostics") or {}).get("canonical_count"),
                "pricedCount": (dataset.get("diagnostics") or {}).get("priced_count"),
                "pureDemandAvailableCount": pure_available_count,
                "treatmentAvailableCount": treatment_available_count,
                "cardAppealAvailableCount": card_appeal_available_count,
                "includedCount": card_appeal_available_count,
                "excludedMissingCardAppealCount": max(0, ((dataset.get("diagnostics") or {}).get("priced_count") or 0) - card_appeal_available_count),
                "sampleSource": "canonical_priced_cards_with_card_appeal_score",
                "includedPolicy": "canonical priced cards with pure Pokemon demand and treatment score",
            },
            "treatmentScore": {
                "canonicalCount": (dataset.get("diagnostics") or {}).get("canonical_count"),
                "pricedCount": (dataset.get("diagnostics") or {}).get("priced_count"),
                "treatmentAvailableCount": treatment_available_count,
                "includedCount": treatment_available_count,
                "excludedMissingTreatmentCount": max(0, ((dataset.get("diagnostics") or {}).get("priced_count") or 0) - treatment_available_count),
                "sampleSource": "canonical_priced_cards_with_treatment_score",
                "includedPolicy": "canonical priced cards with treatment score",
            },
        },
    }


def _legacy_card_appeal_market_price_correlation(payload: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    validation = payload.get("cardDesirabilityValidation") or payload.get("card_desirability_validation") or {}
    cards = validation.get("cards") if isinstance(validation, dict) else payload.get("cards")
    if not isinstance(cards, list):
        return None
    pairs = []
    for card in cards:
        if not isinstance(card, dict):
            continue
        x = _to_optional_float(
            card.get("pokemonDesirabilityScore")
            if card.get("pokemonDesirabilityScore") is not None
            else card.get("pokemon_desirability_score")
        )
        y = _to_optional_float(
            card.get("marketPrice")
            if card.get("marketPrice") is not None
            else card.get("market_price")
            if card.get("market_price") is not None
            else card.get("currentPrice")
        )
        if x is not None and y is not None and y > 0:
            pairs.append((x, y))
    pearson = _pearson_pairs(pairs)
    spearman = _spearman_pairs(pairs)
    max_abs = max(abs(pearson or 0.0), abs(spearman or 0.0)) if pairs else None
    return {
        "canonical_count": None,
        "priced_count": None,
        "linked_count": None,
        "scored_linked_count": None,
        "included_count": len(pairs),
        "excluded_unpriced_count": None,
        "excluded_unlinked_count": None,
        "excluded_missing_score_count": None,
        "included_policy": "legacy display sample with market price and Pokemon desirability score",
        "n": len(pairs),
        "pearson": pearson,
        "spearman": spearman,
        "interpretation": _correlation_interpretation(max_abs),
        "sample_source": "legacy_display_sample",
    }


def _apply_card_appeal_plot_hit_flags(
    correlation: Dict[str, Any],
    validation_cards: List[Dict[str, Any]],
) -> Dict[str, Any]:
    if not isinstance(correlation, dict):
        return correlation
    priced_hit_ids = {
        str(card.get("cardId") or card.get("card_id"))
        for card in validation_cards
        if (card.get("cardId") or card.get("card_id")) is not None
        and bool(card.get("isHitEligible") or card.get("is_hit_eligible"))
        and (_to_optional_float(card.get("marketPrice") or card.get("market_price")) is not None)
    }
    if not priced_hit_ids:
        return correlation

    def update_rows(rows: Any) -> List[Dict[str, Any]]:
        updated = []
        for row in rows or []:
            if not isinstance(row, dict):
                continue
            card_id = row.get("pokemon_canonical_card_id") or row.get("pokemonCanonicalCardId")
            is_hit = str(card_id) in priced_hit_ids if card_id is not None else False
            updated.append({**row, "is_hit_eligible": is_hit, "isHitEligible": is_hit})
        return updated

    updated_rows = update_rows(correlation.get("rows"))
    updated_plot_rows = update_rows(correlation.get("plotRows") or correlation.get("plot_rows") or correlation.get("rows"))

    return {
        **correlation,
        "rows": updated_rows,
        "plot_rows": updated_plot_rows,
        "plotRows": updated_plot_rows,
        "hit_plot_count": len(priced_hit_ids),
        "hitPlotCount": len(priced_hit_ids),
    }


def _resolve_pull_probability(card: Dict[str, Any]) -> tuple[Optional[float], Optional[str]]:
    for key in ("pullRate", "pull_rate", "pullProbability", "pull_probability"):
        probability = normalize_pull_probability(card.get(key))
        if probability is not None:
            return probability, key
    for key in ("pullRateOneInX", "pull_rate_one_in_x", "specificCardOddsDenominator", "specific_card_odds_denominator"):
        denominator = _to_optional_float(card.get(key))
        if denominator is not None and denominator > 0:
            return 1.0 / denominator, key
    return None, None


def _apply_card_validation_fields(card: Dict[str, Any], *, total_market_value: float) -> Dict[str, Any]:
    card_payload = dict(card or {})
    pokemon_score = _to_optional_float(
        card_payload.get("pokemonDesirabilityScore")
        if card_payload.get("pokemonDesirabilityScore") is not None
        else card_payload.get("pokemon_desirability_score")
        if card_payload.get("pokemon_desirability_score") is not None
        else card_payload.get("cardDesirabilityScore")
        if card_payload.get("cardDesirabilityScore") is not None
        else card_payload.get("card_desirability_score")
    )
    treatment_score = get_treatment_score(card_payload.get("rarity"))
    pull_probability, pull_source = _resolve_pull_probability(card_payload)
    scarcity_score = calculate_scarcity_score(pull_probability)
    adjusted_score = calculate_adjusted_card_appeal(pokemon_score, treatment_score, scarcity_score)
    market_price = _to_optional_float(
        card_payload.get("marketPrice")
        if card_payload.get("marketPrice") is not None
        else card_payload.get("market_price")
        if card_payload.get("market_price") is not None
        else card_payload.get("currentPrice")
        if card_payload.get("currentPrice") is not None
        else card_payload.get("current_price")
    )
    set_value_share = (
        round(market_price / total_market_value, 6)
        if market_price is not None and total_market_value > 0
        else None
    )

    card_payload.update(
        {
            "treatmentScore": treatment_score,
            "treatment_score": treatment_score,
            "scarcityScore": scarcity_score,
            "scarcity_score": scarcity_score,
            "adjustedCardAppealScore": adjusted_score,
            "adjusted_card_appeal_score": adjusted_score,
            "pullRate": pull_probability,
            "pull_rate": pull_probability,
            "pullRateSource": pull_source,
            "pull_rate_source": pull_source,
            "setValueShare": set_value_share,
            "set_value_share": set_value_share,
        }
    )
    return card_payload


def enrich_cards_payload_with_desirability(
    payload: Dict[str, Any],
    *,
    prices_by_card: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    cards = list(payload.get("cards") or [])
    card_ids = [_card_id_key(card) for card in cards if isinstance(card, dict)]
    clean_card_ids = sorted({card_id for card_id in card_ids if card_id})

    links_by_card: Dict[str, List[Dict[str, Any]]] = {}
    reference_ids: List[int] = []
    card_link_rows: List[Dict[str, Any]] = []
    if clean_card_ids:
        try:
            links_result = (
                public_read_client.table("pokemon_card_desirability_links")
                .select(
                    "pokemon_canonical_card_id,pokemon_reference_id,pokedex_number,link_position,"
                    "link_count,contribution_weight,match_confidence,is_hit_eligible"
                )
                .in_("pokemon_canonical_card_id", clean_card_ids)
                .execute()
            )
            for link in links_result.data or []:
                card_id = _to_optional_str(link.get("pokemon_canonical_card_id"))
                if not card_id:
                    continue
                card_link_rows.append(link)
                try:
                    reference_id = int(link.get("pokemon_reference_id"))
                except (TypeError, ValueError):
                    reference_id = None
                if reference_id is not None:
                    reference_ids.append(reference_id)
                links_by_card.setdefault(card_id, []).append(link)
        except Exception:
            logger.warning("[pokemon-snapshot] card desirability link lookup failed", exc_info=True)

    scores_by_reference = _latest_composite_scores_for_references(reference_ids)
    card_appeal_correlation = _build_card_appeal_market_price_correlation(
        cards=cards,
        links=card_link_rows,
        scores_by_reference=scores_by_reference,
        prices_by_card=prices_by_card,
    )
    market_prices = [
        _to_optional_float(card.get("marketPrice") if card.get("marketPrice") is not None else card.get("market_price"))
        for card in cards
        if isinstance(card, dict)
    ]
    total_market_value = sum(price for price in market_prices if price is not None and price > 0)

    enriched_cards: List[Dict[str, Any]] = []
    enriched_count = 0
    hit_eligible_count = 0
    priced_linked_count = 0
    excluded_non_pokemon_count = 0

    for card in cards:
        card_payload = dict(card or {})
        card_id = _card_id_key(card_payload)
        card_links = links_by_card.get(card_id or "", [])
        linked_pokemon: List[Dict[str, Any]] = []
        weighted_score = 0.0
        total_weight = 0.0
        is_hit_eligible = False
        for link in card_links:
            try:
                reference_id = int(link.get("pokemon_reference_id"))
            except (TypeError, ValueError):
                continue
            score_row = scores_by_reference.get(reference_id)
            score = _to_optional_float((score_row or {}).get("desirability_score"))
            weight = _to_optional_float(link.get("contribution_weight")) or 0.0
            if score is None or weight <= 0:
                continue
            is_hit_eligible = is_hit_eligible or bool(link.get("is_hit_eligible"))
            weighted_score += score * weight
            total_weight += weight
            linked_pokemon.append(
                {
                    "pokemonName": _to_optional_str((score_row or {}).get("pokemon_name")),
                    "pokemon_name": _to_optional_str((score_row or {}).get("pokemon_name")),
                    "pokemonReferenceId": reference_id,
                    "pokemon_reference_id": reference_id,
                    "pokedexNumber": link.get("pokedex_number") or (score_row or {}).get("pokedex_number"),
                    "pokedex_number": link.get("pokedex_number") or (score_row or {}).get("pokedex_number"),
                    "desirabilityScore": round(score, 2),
                    "desirability_score": round(score, 2),
                    "contributionWeight": weight,
                    "contribution_weight": weight,
                    "matchConfidence": link.get("match_confidence"),
                    "match_confidence": link.get("match_confidence"),
                }
            )

        if total_weight > 0:
            card_score = round(weighted_score / total_weight, 2)
            card_payload.update(
                {
                    "cardDesirabilityScore": card_score,
                    "card_desirability_score": card_score,
                    "pokemonDesirabilityScore": card_score,
                    "pokemon_desirability_score": card_score,
                    "linkedPokemon": linked_pokemon,
                    "linked_pokemon": linked_pokemon,
                    "linkedPokemonName": ", ".join(
                        entry.get("pokemonName") for entry in linked_pokemon if entry.get("pokemonName")
                    )
                    or None,
                    "linked_pokemon_name": ", ".join(
                        entry.get("pokemonName") for entry in linked_pokemon if entry.get("pokemonName")
                    )
                    or None,
                    "isHitEligible": is_hit_eligible,
                    "is_hit_eligible": is_hit_eligible,
                }
            )
            enriched_count += 1
            if _to_optional_float(card_payload.get("marketPrice") or card_payload.get("market_price")) is not None:
                priced_linked_count += 1
            if is_hit_eligible:
                hit_eligible_count += 1
        else:
            excluded_non_pokemon_count += 1

        enriched_cards.append(_apply_card_validation_fields(card_payload, total_market_value=total_market_value))

    validation_cards = [
        {
            "cardId": card.get("id") or card.get("cardId") or card.get("card_id"),
            "cardVariantId": card.get("cardVariantId") or card.get("card_variant_id"),
            "name": card.get("name"),
            "rarity": card.get("rarity"),
            "imageUrl": card.get("imageUrl") or card.get("image_url"),
            "marketPrice": card.get("marketPrice") or card.get("market_price") or card.get("currentPrice"),
            "pokemonName": card.get("linkedPokemonName") or card.get("linked_pokemon_name"),
            "pokemonDesirabilityScore": card.get("pokemonDesirabilityScore"),
            "treatmentScore": card.get("treatmentScore"),
            "scarcityScore": card.get("scarcityScore"),
            "adjustedCardAppealScore": card.get("adjustedCardAppealScore"),
            "pullRate": card.get("pullRate"),
            "pullRateSource": card.get("pullRateSource"),
            "setValueShare": card.get("setValueShare"),
            "isHitEligible": card.get("isHitEligible"),
        }
        for card in enriched_cards
    ]
    card_appeal_correlation = _apply_card_appeal_plot_hit_flags(card_appeal_correlation, validation_cards)

    meta = dict(payload.get("meta") or {})
    desirability_meta = {
        "source": "pokemon_card_desirability_links+pokemon_desirability_composite_scores",
        "scoringVersion": "card_appeal_v1",
        "valueScope": "visible_near_mint_market_price",
        "priceSource": "pokemon_set_cards_snapshot.marketPrice",
        "totalCards": len(cards),
        "linkedPokemonCards": enriched_count,
        "pricedLinkedPokemonCards": priced_linked_count,
        "excludedNonPokemonCards": excluded_non_pokemon_count,
        "hitEligibleCardCount": hit_eligible_count,
        "enrichedCardCount": enriched_count,
        "total_cards": len(cards),
        "linked_pokemon_cards": enriched_count,
        "priced_linked_pokemon_cards": priced_linked_count,
        "excluded_non_pokemon_cards": excluded_non_pokemon_count,
        "hit_eligible_card_count": hit_eligible_count,
        "enriched_card_count": enriched_count,
    }
    meta["cardDesirability"] = desirability_meta
    meta["card_desirability"] = desirability_meta
    meta["cardAppealMarketPriceCorrelation"] = card_appeal_correlation
    meta["card_appeal_market_price_correlation"] = card_appeal_correlation
    return {
        **payload,
        "cards": enriched_cards,
        "cardAppealMarketPriceCorrelation": card_appeal_correlation,
        "card_appeal_market_price_correlation": card_appeal_correlation,
        "cardDesirabilityValidation": {
            "cards": validation_cards,
            "meta": {
                **desirability_meta,
                "cardAppealMarketPriceCorrelation": card_appeal_correlation,
                "generatedAt": datetime.now(timezone.utc).isoformat(),
            },
        },
        "card_desirability_validation": {
            "cards": validation_cards,
            "meta": {
                **desirability_meta,
                "card_appeal_market_price_correlation": card_appeal_correlation,
                "generated_at": datetime.now(timezone.utc).isoformat(),
            },
        },
        "meta": meta,
    }


def _latest_standard_set_value_from_histories(histories_by_scope: Any) -> Dict[str, Any]:
    if not isinstance(histories_by_scope, dict):
        return {}
    history = histories_by_scope.get("standard") or histories_by_scope.get("checklist") or []
    if not isinstance(history, list):
        return {}

    latest: Dict[str, Any] = {}
    latest_date: Optional[str] = None
    for point in history:
        if not isinstance(point, dict):
            continue
        value = _to_optional_float(point.get("setValue") or point.get("set_value") or point.get("value"))
        if value is None or value <= 0:
            continue
        date_key = _parse_date_key(point.get("date") or point.get("snapshot_date") or point.get("sourceDate") or point.get("source_date"))
        if latest_date is not None and date_key is not None and date_key < latest_date:
            continue
        latest = {"value": round(value, 2), "date": date_key}
        if date_key:
            latest_date = date_key

    return latest


def _load_latest_checklist_set_values(set_ids: List[str]) -> Dict[str, Dict[str, Any]]:
    clean_ids = sorted({_to_optional_str(set_id) for set_id in set_ids if _to_optional_str(set_id)})
    if not clean_ids:
        return {}

    window_priority = {
        DEFAULT_TOP_CHASE_DASHBOARD_WINDOW: 0,
        DEFAULT_DASHBOARD_WINDOW: 1,
    }
    try:
        result = (
            public_read_client.table("pokemon_set_market_dashboard_snapshot_latest")
            .select("set_id,window_key,set_value_histories_json,latest_market_date,updated_at")
            .in_("set_id", clean_ids)
            .in_("window_key", [DEFAULT_TOP_CHASE_DASHBOARD_WINDOW, DEFAULT_DASHBOARD_WINDOW])
            .execute()
        )
    except Exception as exc:
        if _is_missing_snapshot_relation_error(exc):
            logger.warning("[pokemon-snapshot] checklist set value snapshot relation missing; continuing without enrichment")
        else:
            logger.warning("[pokemon-snapshot] checklist set value enrichment failed", exc_info=True)
        return {}

    values: Dict[str, Dict[str, Any]] = {}
    for row in result.data or []:
        set_id = _to_optional_str(row.get("set_id"))
        if not set_id:
            continue
        latest = _latest_standard_set_value_from_histories(row.get("set_value_histories_json"))
        value = _to_optional_float(latest.get("value"))
        if value is None:
            continue
        candidate = {
            "value": round(value, 2),
            "date": latest.get("date") or _parse_date_key(row.get("latest_market_date")),
            "updated_at": _to_optional_str(row.get("updated_at")),
            "window_key": _to_optional_str(row.get("window_key")),
        }
        existing = values.get(set_id)
        if existing is None or window_priority.get(candidate["window_key"], 99) < window_priority.get(existing.get("window_key"), 99):
            values[set_id] = candidate

    return values


def _slim_set_value_history_point(point: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """Project one raw set-value history point down to the 4 fields the shell's
    title-card sparkline actually reads (date, setValue, sourceDate,
    isCarriedForward). The source row (set_value_histories_json, shared with the
    Overview market dashboard) stores ~20 dual-cased fields per point (source,
    provider, createdAt/created_at, valueScope/value_scope, totalCardCount,
    cardCountPriced, calculationRunId, ...) that no shell consumer reads — see
    Phase 5C audit. Only the shell response is slimmed; the underlying snapshot
    row is untouched.
    """
    if not isinstance(point, dict):
        return None
    date_key = _to_optional_str(point.get("date"))
    if not date_key:
        return None
    value = _to_optional_float(point.get("setValue") if "setValue" in point else point.get("set_value"))
    source_date = (
        _to_optional_str(point.get("sourceDate") if "sourceDate" in point else point.get("source_date")) or date_key
    )
    return {
        "date": date_key,
        "setValue": value,
        "sourceDate": source_date,
        "isCarriedForward": bool(point.get("isCarriedForward") or point.get("is_carried_forward")),
    }


def _load_shell_checklist_set_value_history(set_id: str) -> Dict[str, Any]:
    """Fetch the standard-scope checklist set value point series for the shell header.

    Reuses the same pokemon_set_market_dashboard_snapshot_latest table that backs the
    Overview market dashboard, but selects only the small set_value_histories_json
    column so the shell payload stays lightweight (no top-chase-card/market-mover
    data). This is what lets the title-card set value + sparkline render immediately
    on every tab instead of only once the Overview dashboard has been fetched.
    """
    resolved = _to_optional_str(set_id)
    if not resolved:
        return {}

    try:
        result = (
            public_read_client.table("pokemon_set_market_dashboard_snapshot_latest")
            .select("window_key,set_value_histories_json")
            .eq("set_id", resolved)
            .in_("window_key", [DEFAULT_TOP_CHASE_DASHBOARD_WINDOW, DEFAULT_DASHBOARD_WINDOW])
            .execute()
        )
    except Exception as exc:
        if _is_missing_snapshot_relation_error(exc):
            logger.warning(
                "[pokemon-snapshot] shell checklist set value snapshot relation missing; continuing without enrichment"
            )
        else:
            logger.warning(
                "[pokemon-snapshot] shell checklist set value history load failed set_id=%s", resolved, exc_info=True
            )
        return {}

    rows = result.data or []
    if not rows:
        return {}

    window_priority = {DEFAULT_TOP_CHASE_DASHBOARD_WINDOW: 0, DEFAULT_DASHBOARD_WINDOW: 1}
    best_row = min(rows, key=lambda row: window_priority.get(_to_optional_str(row.get("window_key")), 99))
    histories = best_row.get("set_value_histories_json")
    standard_history = histories.get("standard") if isinstance(histories, dict) else None
    if not isinstance(standard_history, list) or not standard_history:
        return {}

    slim_history = [
        slim_point
        for slim_point in (_slim_set_value_history_point(point) for point in standard_history)
        if slim_point is not None
    ]
    if not slim_history:
        return {}

    return {"standard": slim_history}


def _enrich_rankings_payload_with_checklist_set_values(payload: Dict[str, Any]) -> Dict[str, Any]:
    targets = list(payload.get("targets") or [])
    if not targets:
        return payload

    set_ids = [
        _to_optional_str(target.get("set_id") or target.get("id") or target.get("target_id"))
        for target in targets
    ]
    value_lookup = _load_latest_checklist_set_values([set_id for set_id in set_ids if set_id])
    if not value_lookup:
        return payload

    enriched_targets: List[Dict[str, Any]] = []
    for target in targets:
        target_payload = dict(target or {})
        set_id = _to_optional_str(target_payload.get("set_id") or target_payload.get("id") or target_payload.get("target_id"))
        latest_value = value_lookup.get(set_id or "")
        if latest_value:
            target_payload.update(
                {
                    "checklistSetValue": latest_value.get("value"),
                    "checklist_set_value": latest_value.get("value"),
                    "currentChecklistSetValue": latest_value.get("value"),
                    "current_checklist_set_value": latest_value.get("value"),
                    "checklistSetValueAsOf": latest_value.get("date"),
                    "checklist_set_value_as_of": latest_value.get("date"),
                }
            )
            market_payload = dict(target_payload.get("market") or {})
            market_payload.update(
                {
                    "checklistSetValue": latest_value.get("value"),
                    "checklist_set_value": latest_value.get("value"),
                    "asOf": latest_value.get("date"),
                    "as_of": latest_value.get("date"),
                    "source": "pokemon_set_market_dashboard_snapshot_latest",
                }
            )
            target_payload["market"] = market_payload
        enriched_targets.append(target_payload)

    meta = dict(payload.get("meta") or {})
    sources = dict(meta.get("sources") or {})
    sources["checklist_set_value_enrichment"] = "pokemon_set_market_dashboard_snapshot_latest"
    meta["sources"] = sources
    return {**payload, "targets": enriched_targets, "meta": meta}


def _resolve_set_row(set_id: str) -> Dict[str, Any]:
    # Shared with page/shell/cards/market-dashboard/value-history/top-cards —
    # see pokemon_set_market_service.resolve_pokemon_set_identifier for the
    # implementation. Must pass this module's own public_read_client
    # explicitly: resolve_pokemon_set_identifier's default client is looked up
    # from pokemon_set_market_service's globals, not the caller's, so a bare
    # alias would silently bypass a public_read_client monkeypatch made here.
    return resolve_pokemon_set_identifier(set_id, client=public_read_client)


def _snapshot_meta(row: Dict[str, Any], source: str) -> Dict[str, Any]:
    return {
        "source": source,
        "snapshot": {
            "asOf": _to_optional_str(row.get("as_of")),
            "sourceUpdatedAt": _to_optional_str(row.get("source_updated_at")),
            "updatedAt": _to_optional_str(row.get("updated_at")),
            "isStaleFallback": True,
        },
    }


def _merge_snapshot_meta(payload: Dict[str, Any], row: Dict[str, Any], source: str) -> Dict[str, Any]:
    meta = dict(payload.get("meta") or {})
    snapshot = dict(meta.get("snapshot") or {})
    snapshot.update(_snapshot_meta(row, source)["snapshot"])
    meta["snapshot"] = snapshot
    return {**payload, "meta": meta}


def _with_desirability_validation(payload: Dict[str, Any], set_id: str) -> Dict[str, Any]:
    if isinstance(payload.get("desirabilityValidation"), dict) or isinstance(payload.get("desirability_validation"), dict):
        return payload
    try:
        rankings = get_pokemon_explore_rankings_snapshot_payload(limit=DEFAULT_RANKINGS_LIMIT)
        validation = build_desirability_validation_payload(
            set_id=set_id,
            set_payload=payload,
            target_rows=rankings.get("targets") or [],
        )
    except Exception:
        logger.warning("[pokemon-snapshot] desirability validation fallback failed set_id=%s", set_id, exc_info=True)
        return payload
    meta = dict(payload.get("meta") or {})
    sources = dict(meta.get("sources") or {})
    sources["desirability_validation"] = "runtime_from_rankings_snapshot"
    meta["sources"] = sources
    return {
        **payload,
        "desirabilityValidation": validation,
        "desirability_validation": validation,
        "meta": meta,
    }


def _mark_missing_simulation_drivers_without_live_repair(payload: Dict[str, Any]) -> Dict[str, Any]:
    if not isinstance(payload, dict) or payload.get("top_hits"):
        return payload

    meta = payload.get("meta") if isinstance(payload.get("meta"), dict) else {}
    sources = meta.get("sources") if isinstance(meta.get("sources"), dict) else {}
    if sources.get("simulation_input_cards") not in {"FAILED", "NO_ROWS"}:
        return payload

    merged_meta = dict(meta)
    merged_warnings = [
        warning
        for warning in list(meta.get("warnings") or [])
        if "top hits" not in str(warning).lower() and "simulation drivers unavailable" not in str(warning).lower()
    ]
    debug_warnings = list(meta.get("debugWarnings") or meta.get("debug_warnings") or [])
    debug_warnings.append(
        "Simulation Drivers are unavailable in this set page snapshot; skipped live repair during route render."
    )
    merged_sources = dict(sources)
    merged_sources["simulation_input_cards"] = sources.get("simulation_input_cards") or "MISSING"
    merged_meta["sources"] = merged_sources
    merged_meta["warnings"] = merged_warnings
    merged_meta["debugWarnings"] = debug_warnings
    merged_meta["debug_warnings"] = debug_warnings
    merged_meta["simulationDriversRepairSkipped"] = {
        "source": "pokemon_set_page_snapshot_latest",
        "reason": f"snapshot simulation_input_cards={sources.get('simulation_input_cards')}",
        "policy": "no_live_assembly_during_route_render",
    }

    return {
        **payload,
        "meta": merged_meta,
    }


def _with_missing_desirability_validation_warning(payload: Dict[str, Any]) -> Dict[str, Any]:
    if not isinstance(payload, dict):
        return payload
    if isinstance(payload.get("desirabilityValidation"), dict) or isinstance(payload.get("desirability_validation"), dict):
        return payload
    meta = dict(payload.get("meta") or {})
    warnings = list(meta.get("warnings") or [])
    warning = "Desirability validation is missing in this snapshot; request path skipped runtime rebuild."
    if warning not in warnings:
        warnings.append(warning)
    meta["warnings"] = warnings
    return {
        **payload,
        "meta": meta,
    }


def _load_rankings_snapshot_updated_at() -> Optional[str]:
    try:
        result = (
            public_read_client.table("pokemon_explore_rankings_snapshot_latest")
            .select("updated_at")
            .eq("tcg", "pokemon")
            .eq("scope", DEFAULT_RANKINGS_SCOPE)
            .limit(1)
            .execute()
        )
    except Exception:
        logger.warning("[pokemon-snapshot] rankings freshness lookup failed", exc_info=True)
        return None
    return _to_optional_str((_first_row(result) or {}).get("updated_at"))


def _with_rankings_freshness_warning(payload: Dict[str, Any], row: Dict[str, Any]) -> Dict[str, Any]:
    meta = dict(payload.get("meta") or {})
    completeness = (
        meta.get("snapshotCompleteness")
        if isinstance(meta.get("snapshotCompleteness"), dict)
        else meta.get("snapshot_completeness")
        if isinstance(meta.get("snapshot_completeness"), dict)
        else {}
    )
    rankings_updated_at = _to_optional_str(completeness.get("explore_rankings_snapshot_updated_at"))
    if not rankings_updated_at:
        rankings_updated_at = _load_rankings_snapshot_updated_at()

    set_updated_at = _to_optional_str(row.get("updated_at"))
    set_updated_dt = _to_optional_datetime(set_updated_at)
    rankings_updated_dt = _to_optional_datetime(rankings_updated_at)
    if not set_updated_dt or not rankings_updated_dt:
        return payload
    if (set_updated_dt - rankings_updated_dt).total_seconds() <= RANKINGS_STALE_THRESHOLD_SECONDS:
        return payload

    warnings = list(meta.get("warnings") or [])
    if RANKINGS_STALE_WARNING not in warnings:
        warnings.append(RANKINGS_STALE_WARNING)
    snapshot = dict(meta.get("snapshot") or {})
    snapshot["exploreRankingsUpdatedAt"] = rankings_updated_at
    snapshot["explore_rankings_updated_at"] = rankings_updated_at
    meta["warnings"] = warnings
    meta["snapshot"] = snapshot
    return {**payload, "meta": meta}


def _build_missing_set_page_snapshot_payload(set_row: Dict[str, Any], elapsed_ms: float) -> Dict[str, Any]:
    resolved_set_id = _to_optional_str(set_row.get("id"))
    canonical_key = _to_optional_str(set_row.get("canonical_key"))
    pokemon_api_set_id = _to_optional_str(set_row.get("pokemon_api_set_id"))
    name = _to_optional_str(set_row.get("name")) or resolved_set_id or "Pokemon set"
    now_iso = datetime.now(timezone.utc).isoformat()

    return {
        "summary": {
            "target_id": resolved_set_id,
            "set_id": resolved_set_id,
            "name": name,
            "canonical_key": canonical_key,
            "pokemon_api_set_id": pokemon_api_set_id,
            "pack_score": None,
            "relative_pack_score": None,
        },
        "rankings": [],
        "rip_statistics": {"pack_paths": {}, "normal_pack_states": {}},
        "percentiles": [],
        "distribution_bins": [],
        "threshold_bins": [],
        "top_hits": [],
        "history_trend": [],
        "openingDesirability": None,
        "pull_rate_assumptions": None,
        "interpretation": {},
        "meta": {
            "warnings": [
                "Pokemon set page snapshot is missing; rendered fallback shell instead of live assembly.",
            ],
            "errors": [
                {
                    "code": "POKEMON_SET_PAGE_SNAPSHOT_MISSING",
                    "status": 200,
                    "elapsedMs": elapsed_ms,
                    "setId": resolved_set_id,
                }
            ],
            "fallback": True,
            "stale": False,
            "sources": {
                "setPage": "fallback_missing_pokemon_set_page_snapshot_latest",
            },
            "snapshot": {
                "source": "fallback_missing_pokemon_set_page_snapshot_latest",
                "updatedAt": now_iso,
                "isStaleFallback": False,
            },
            "timings": {
                "snapshot_read_ms": elapsed_ms,
            },
        },
    }


def get_pokemon_set_page_snapshot_payload(set_id: str) -> Dict[str, Any]:
    started = time.perf_counter()
    resolved = _to_optional_str(set_id)
    if not resolved:
        raise ExplorePageError(400, "set_id is required", "POKEMON_SET_PAGE_ID_REQUIRED")
    is_uuid = _looks_like_uuid(resolved)
    logger.info("[pokemon-snapshot] page snapshot start set_id=%s uuid_fast_path=%s", resolved, is_uuid)

    set_row: Optional[Dict[str, Any]] = None
    set_resolve_ms: Optional[float] = None

    if is_uuid:
        resolved_set_id = resolved
    else:
        t_resolve = time.perf_counter()
        set_row = _resolve_set_row(resolved)
        resolved_set_id = str(set_row["id"])
        set_resolve_ms = round((time.perf_counter() - t_resolve) * 1000, 3)
        logger.info(
            "[pokemon-snapshot] page snapshot set resolved set_id=%s resolved_set_id=%s resolve_ms=%s",
            resolved,
            resolved_set_id,
            set_resolve_ms,
        )

    try:
        t_query = time.perf_counter()
        logger.info("[pokemon-snapshot] page snapshot query start set_id=%s", resolved_set_id)
        result = (
            public_read_client.table("pokemon_set_page_snapshot_latest")
            .select("set_id,payload_json,as_of,source_updated_at,updated_at")
            .eq("set_id", resolved_set_id)
            .limit(1)
            .execute()
        )
        query_ms = round((time.perf_counter() - t_query) * 1000, 3)
        row = _first_row(result)
        payload_type = type((row or {}).get("payload_json")).__name__
        logger.info(
            "[pokemon-snapshot] page snapshot query done set_id=%s query_ms=%s row_present=%s payload_type=%s",
            resolved_set_id,
            query_ms,
            bool(row),
            payload_type,
        )
        if row and isinstance(row.get("payload_json"), dict):
            payload = _merge_snapshot_meta(row["payload_json"], row, "pokemon_set_page_snapshot_latest")
            payload = _mark_missing_simulation_drivers_without_live_repair(payload)
            payload = _with_missing_desirability_validation_warning(payload)
            timings = dict((payload.get("meta") or {}).get("timings") or {})
            if set_resolve_ms is not None:
                timings["set_resolve_ms"] = set_resolve_ms
            timings["snapshot_query_ms"] = query_ms
            timings["snapshot_read_ms"] = round((time.perf_counter() - started) * 1000, 3)
            payload["meta"] = {**(payload.get("meta") or {}), "timings": timings}
            logger.info(
                "[pokemon-snapshot] set page snapshot read set_id=%s elapsed_ms=%s",
                resolved_set_id,
                timings["snapshot_read_ms"],
            )
            return payload
    except Exception as exc:
        elapsed_ms = round((time.perf_counter() - started) * 1000, 3)
        logger.exception(
            "[pokemon-snapshot] set page snapshot read failed set_id=%s elapsed_ms=%s exc_type=%s exc=%s",
            resolved_set_id,
            elapsed_ms,
            type(exc).__name__,
            exc,
        )
        raise ExplorePageError(500, "Failed to read Pokemon set page snapshot", "POKEMON_SET_PAGE_SNAPSHOT_FAILED")

    elapsed_ms = round((time.perf_counter() - started) * 1000, 3)
    logger.warning(
        "[pokemon-snapshot] missing set page snapshot; returning fallback shell set_id=%s elapsed_ms=%s",
        resolved_set_id,
        elapsed_ms,
    )
    if set_row is None:
        try:
            t_lazy = time.perf_counter()
            set_row = _resolve_set_row(resolved_set_id)
            logger.debug(
                "[pokemon-snapshot] lazy set resolve for missing page snapshot set_id=%s elapsed_ms=%.1f",
                resolved_set_id,
                (time.perf_counter() - t_lazy) * 1000,
            )
        except Exception:
            set_row = {"id": resolved_set_id}
    return _build_missing_set_page_snapshot_payload(set_row, elapsed_ms)


_TRACKED_LENS_SUMMARY_FIELDS = (
    "relative_experience_score",
    "relative_chase_potential_score",
    "relative_biggest_upside_score",
    "relative_average_return_score",
    "experience_rank",
    "chase_potential_rank",
    "biggest_upside_rank",
    "mean_value_to_cost_rank",
    "experience_tier",
    "chase_potential_tier",
    "biggest_upside_tier",
    "mean_value_to_cost_tier",
)
_TRACKED_LENS_PAYLOAD_PREFIX = "tracked_lens_"
_SHELL_SNAPSHOT_COLUMNS = (
    "set_id,set_identity_json,title_card_json,rip_summary_json,"
    "market_summary_json,risk_summary_json,concentration_json,"
    "desirability_summary_json,set_intelligence_json,as_of,source_updated_at,updated_at,"
    + ",".join(
        f"{_TRACKED_LENS_PAYLOAD_PREFIX}{field}:payload_json->summary->{field}"
        for field in _TRACKED_LENS_SUMMARY_FIELDS
    )
)


def _normalize_set_identity(set_identity_json: Dict[str, Any]) -> Dict[str, Any]:
    identity = set_identity_json if isinstance(set_identity_json, dict) else {}
    return {
        "id": _to_optional_str(identity.get("id")),
        "name": _to_optional_str(identity.get("name")),
        "slug": _to_optional_str(identity.get("slug")),
        "pokemon_api_set_id": _to_optional_str(identity.get("pokemon_api_set_id")),
        "release_date": _to_optional_str(identity.get("release_date")),
        "logo_image_url": _to_optional_str(identity.get("logo_image_url")),
        "symbol_image_url": _to_optional_str(identity.get("symbol_image_url")),
        "hero_image_url": _to_optional_str(identity.get("hero_image_url")),
    }


def _build_shell_payload_from_row(
    row: Dict[str, Any], *, set_value_histories_by_scope: Optional[Dict[str, Any]] = None
) -> Dict[str, Any]:
    """Build the slim shell/header snapshot (camelCase only, no raw column
    passthrough) from a pokemon_set_page_snapshot_latest row.

    title_card_json/rip_summary_json/market_summary_json/risk_summary_json/
    concentration_json/desirability_summary_json are the small header columns
    the full /page snapshot builder writes (see
    backend/scripts/pokemon_snapshot_builders.py); they are only ever read
    here to flatten into `summary` below. No shell consumer reads them as
    standalone top-level keys (or their snake_case siblings), so — unlike the
    legacy /page payload — they are not re-exposed individually. This is most
    of the reduction versus the pre-Phase-5C shape, without dropping any field
    a frontend consumer relies on (see Phase 5C audit).
    """
    set_identity = row.get("set_identity_json") if isinstance(row.get("set_identity_json"), dict) else {}
    title_card = row.get("title_card_json") if isinstance(row.get("title_card_json"), dict) else {}
    rip_summary = row.get("rip_summary_json") if isinstance(row.get("rip_summary_json"), dict) else {}
    # Older rows can have a rip_summary_json written before the supplementary
    # lens fields were added to that split column, even though
    # payload_json.summary already contains the authoritative values. The
    # query projects only these exact JSON paths (not the multi-MB payload_json
    # blob), and those persisted values win whenever they are present.
    tracked_lens_summary = {
        field: row.get(f"{_TRACKED_LENS_PAYLOAD_PREFIX}{field}")
        for field in _TRACKED_LENS_SUMMARY_FIELDS
        if row.get(f"{_TRACKED_LENS_PAYLOAD_PREFIX}{field}") is not None
    }
    market_summary = row.get("market_summary_json") if isinstance(row.get("market_summary_json"), dict) else {}
    risk_summary = row.get("risk_summary_json") if isinstance(row.get("risk_summary_json"), dict) else {}
    concentration = row.get("concentration_json") if isinstance(row.get("concentration_json"), dict) else {}
    # set_intelligence_json holds the full RIP interpretation payload (recommendation
    # badge/summary + opening-experience/chase/upside lenses) so the shell can render
    # the same recommendation the full /page payload shows, without pulling payload_json.
    interpretation = (
        row.get("set_intelligence_json") if isinstance(row.get("set_intelligence_json"), dict) else {}
    )
    summary = {
        **concentration,
        **risk_summary,
        **market_summary,
        **rip_summary,
        **tracked_lens_summary,
        **title_card,
    }
    histories_by_scope = set_value_histories_by_scope if isinstance(set_value_histories_by_scope, dict) else {}

    return {
        "set": _normalize_set_identity(set_identity),
        "summary": summary,
        "interpretation": interpretation,
        "setValueHistoriesByScope": histories_by_scope,
        "meta": {},
    }


def _build_missing_shell_snapshot_payload(set_row: Dict[str, Any], elapsed_ms: float) -> Dict[str, Any]:
    resolved_set_id = _to_optional_str(set_row.get("id"))
    name = _to_optional_str(set_row.get("name")) or resolved_set_id or "Pokemon set"
    now_iso = datetime.now(timezone.utc).isoformat()

    return {
        "set": {
            "id": resolved_set_id,
            "name": name,
            "slug": _to_optional_str(set_row.get("canonical_key")),
            "pokemon_api_set_id": _to_optional_str(set_row.get("pokemon_api_set_id")),
        },
        "summary": {},
        "interpretation": {},
        "setValueHistoriesByScope": {},
        "meta": {
            "warnings": [
                "Pokemon set shell snapshot is missing; rendered fallback shell.",
            ],
            "fallback": True,
            "sources": {"shell": "fallback_missing_pokemon_set_page_snapshot_latest"},
            "snapshot": {
                "source": "fallback_missing_pokemon_set_page_snapshot_latest",
                "updatedAt": now_iso,
                "isStaleFallback": False,
            },
            "timings": {"snapshot_read_ms": elapsed_ms},
        },
    }


def get_pokemon_set_shell_snapshot_payload(set_id: str) -> Dict[str, Any]:
    """Return the lightweight header/title-card snapshot for a Pokemon set.

    Selects only the small split columns on pokemon_set_page_snapshot_latest —
    never payload_json — so the initial set page render can fetch a shell
    without pulling the full (often multi-megabyte) RIP payload.
    """
    started = time.perf_counter()
    resolved = _to_optional_str(set_id)
    if not resolved:
        raise ExplorePageError(400, "set_id is required", "POKEMON_SET_SHELL_ID_REQUIRED")
    is_uuid = _looks_like_uuid(resolved)
    logger.info("[pokemon-snapshot] shell snapshot start set_id=%s uuid_fast_path=%s", resolved, is_uuid)

    set_row: Optional[Dict[str, Any]] = None
    set_resolve_ms: Optional[float] = None

    if is_uuid:
        resolved_set_id = resolved
    else:
        t_resolve = time.perf_counter()
        set_row = _resolve_set_row(resolved)
        resolved_set_id = str(set_row["id"])
        set_resolve_ms = round((time.perf_counter() - t_resolve) * 1000, 3)
        logger.info(
            "[pokemon-snapshot] shell snapshot set resolved set_id=%s resolved_set_id=%s resolve_ms=%s",
            resolved,
            resolved_set_id,
            set_resolve_ms,
        )

    try:
        t_query = time.perf_counter()
        result = (
            public_read_client.table("pokemon_set_page_snapshot_latest")
            .select(_SHELL_SNAPSHOT_COLUMNS)
            .eq("set_id", resolved_set_id)
            .limit(1)
            .execute()
        )
        query_ms = round((time.perf_counter() - t_query) * 1000, 3)
        row = _first_row(result)
    except Exception as exc:
        elapsed_ms = round((time.perf_counter() - started) * 1000, 3)
        logger.exception(
            "[pokemon-snapshot] shell snapshot read failed set_id=%s elapsed_ms=%s exc_type=%s exc=%s",
            resolved_set_id,
            elapsed_ms,
            type(exc).__name__,
            exc,
        )
        raise ExplorePageError(500, "Failed to read Pokemon set shell snapshot", "POKEMON_SET_SHELL_SNAPSHOT_FAILED")

    if row:
        t_set_value = time.perf_counter()
        set_value_histories_by_scope = _load_shell_checklist_set_value_history(resolved_set_id)
        set_value_ms = round((time.perf_counter() - t_set_value) * 1000, 3)
        payload = _build_shell_payload_from_row(row, set_value_histories_by_scope=set_value_histories_by_scope)
        meta = dict(payload.get("meta") or {})
        snapshot_meta = _snapshot_meta(row, "pokemon_set_page_snapshot_latest")
        meta["snapshot"] = {"source": snapshot_meta["source"], **snapshot_meta["snapshot"]}
        payload["meta"] = meta
        timings = dict((payload.get("meta") or {}).get("timings") or {})
        if set_resolve_ms is not None:
            timings["set_resolve_ms"] = set_resolve_ms
        timings["snapshot_query_ms"] = query_ms
        timings["set_value_history_query_ms"] = set_value_ms
        timings["snapshot_read_ms"] = round((time.perf_counter() - started) * 1000, 3)
        payload["meta"] = {**(payload.get("meta") or {}), "timings": timings}
        logger.info(
            "[pokemon-snapshot] shell snapshot read set_id=%s elapsed_ms=%s",
            resolved_set_id,
            timings["snapshot_read_ms"],
        )
        return payload

    elapsed_ms = round((time.perf_counter() - started) * 1000, 3)
    logger.warning(
        "[pokemon-snapshot] missing shell snapshot; returning fallback shell set_id=%s elapsed_ms=%s",
        resolved_set_id,
        elapsed_ms,
    )
    if set_row is None:
        try:
            set_row = _resolve_set_row(resolved_set_id)
        except Exception:
            set_row = {"id": resolved_set_id}
    return _build_missing_shell_snapshot_payload(set_row, elapsed_ms)


def get_pokemon_explore_rankings_snapshot_payload(limit: Any = DEFAULT_RANKINGS_LIMIT) -> Dict[str, Any]:
    clamped_limit = _sanitize_limit(limit, default=DEFAULT_RANKINGS_LIMIT, max_value=MAX_RANKINGS_LIMIT)
    try:
        result = (
            public_read_client.table("pokemon_explore_rankings_snapshot_latest")
            .select("tcg,scope,ranking_payload_json,default_target_json,updated_at")
            .eq("tcg", "pokemon")
            .eq("scope", DEFAULT_RANKINGS_SCOPE)
            .limit(1)
            .execute()
        )
        row = _first_row(result)
    except Exception:
        logger.exception("[pokemon-snapshot] explore rankings snapshot read failed")
        raise ExploreRipStatisticsTargetsError(
            status_code=500,
            message="Failed to read RIP Statistics targets snapshot",
            code="RIP_STATISTICS_TARGETS_SNAPSHOT_FAILED",
        )

    if row and isinstance(row.get("ranking_payload_json"), dict):
        payload = row["ranking_payload_json"]
        enrichment_warning = None
        try:
            payload = _enrich_rankings_payload_with_checklist_set_values(payload)
        except Exception:
            logger.warning(
                "[pokemon-snapshot] checklist set value enrichment failed; serving persisted rankings snapshot",
                exc_info=True,
            )
            enrichment_warning = (
                "Checklist set value enrichment failed; served persisted rankings snapshot without enrichment."
            )

        raw_targets = list(payload.get("targets") or [])
        targets = [target for target in raw_targets if is_opening_set_row(target)][:clamped_limit]
        meta = dict(payload.get("meta") or {})
        if enrichment_warning:
            warnings = list(meta.get("warnings") or [])
            if enrichment_warning not in warnings:
                warnings.append(enrichment_warning)
            meta["warnings"] = warnings
            sources = dict(meta.get("sources") or {})
            sources["checklist_set_value_enrichment"] = "FAILED_OPTIONAL"
            meta["sources"] = sources
        opening_set_audit = build_opening_set_audit(raw_targets)
        request = dict(meta.get("request") or {})
        request["limit"] = clamped_limit
        snapshot = dict(meta.get("snapshot") or {})
        snapshot.update(
            {
                "source": "pokemon_explore_rankings_snapshot_latest",
                "updatedAt": _to_optional_str(row.get("updated_at")),
                "isStaleFallback": True,
            }
        )
        meta["request"] = request
        meta["snapshot"] = snapshot
        meta["openingSetAudit"] = opening_set_audit
        meta["opening_set_audit"] = opening_set_audit
        return {
            **payload,
            "targets": targets,
            "default_target": payload.get("default_target") or row.get("default_target_json") or None,
            "meta": meta,
        }

    logger.warning("[pokemon-snapshot] missing explore rankings snapshot; falling back to live target assembly")
    payload = _enrich_rankings_payload_with_checklist_set_values(get_rip_statistics_targets_payload(limit=clamped_limit))
    meta = dict(payload.get("meta") or {})
    warnings = list(meta.get("warnings") or [])
    warnings.append("Explore rankings snapshot is missing; served live fallback data.")
    meta["warnings"] = warnings
    meta["snapshot"] = {
        "source": "live_fallback_missing_pokemon_explore_rankings_snapshot_latest",
        "updatedAt": datetime.now(timezone.utc).isoformat(),
        "isStaleFallback": False,
    }
    return {**payload, "meta": meta}


def get_pokemon_set_cards_snapshot_payload(set_id: str) -> Dict[str, Any]:
    started = time.perf_counter()
    resolved = _to_optional_str(set_id)
    if not resolved:
        raise PokemonSetCardsError(400, "set_id is required", "POKEMON_SET_CARDS_ID_REQUIRED")
    is_uuid = _looks_like_uuid(resolved)
    logger.info("[pokemon-snapshot] cards snapshot start set_id=%s uuid_fast_path=%s", resolved, is_uuid)

    set_resolve_ms: Optional[float] = None

    if is_uuid:
        resolved_set_id = resolved
    else:
        t_resolve = time.perf_counter()
        set_row = _resolve_set_row(resolved)
        resolved_set_id = str(set_row["id"])
        set_resolve_ms = round((time.perf_counter() - t_resolve) * 1000, 3)
        logger.info(
            "[pokemon-snapshot] cards snapshot set resolved set_id=%s resolved_set_id=%s resolve_ms=%s",
            resolved,
            resolved_set_id,
            set_resolve_ms,
        )

    try:
        t_query = time.perf_counter()
        logger.info("[pokemon-snapshot] cards snapshot query start set_id=%s", resolved_set_id)
        result = (
            public_read_client.table("pokemon_set_cards_snapshot_latest")
            .select("set_id,payload_json,card_count,updated_at")
            .eq("set_id", resolved_set_id)
            .limit(1)
            .execute()
        )
        query_ms = round((time.perf_counter() - t_query) * 1000, 3)
        row = _first_row(result)
        payload_type = type((row or {}).get("payload_json")).__name__
        logger.info(
            "[pokemon-snapshot] cards snapshot query done set_id=%s query_ms=%s row_present=%s payload_type=%s",
            resolved_set_id,
            query_ms,
            bool(row),
            payload_type,
        )
        if row and isinstance(row.get("payload_json"), dict):
            payload = row["payload_json"]
            meta = dict(payload.get("meta") or {})
            card_validation = payload.get("cardDesirabilityValidation") or payload.get("card_desirability_validation") or {}
            card_validation_cards = card_validation.get("cards") if isinstance(card_validation, dict) else []
            correlation = (
                payload.get("cardAppealMarketPriceCorrelation")
                or payload.get("card_appeal_market_price_correlation")
                or meta.get("cardAppealMarketPriceCorrelation")
                or meta.get("card_appeal_market_price_correlation")
            )
            if not isinstance(correlation, dict):
                correlation = _legacy_card_appeal_market_price_correlation(payload)
            meta["cardDesirabilityValidation"] = {
                "precomputed": True,
                "rowCount": len(card_validation_cards) if isinstance(card_validation_cards, list) else 0,
                "source": "pokemon_set_cards_snapshot_latest.payload_json",
            }
            meta["card_desirability_validation"] = {
                "precomputed": True,
                "row_count": len(card_validation_cards) if isinstance(card_validation_cards, list) else 0,
                "source": "pokemon_set_cards_snapshot_latest.payload_json",
            }
            snapshot = dict(meta.get("snapshot") or {})
            snapshot.update(
                {
                    "source": "pokemon_set_cards_snapshot_latest",
                    "updatedAt": _to_optional_str(row.get("updated_at")),
                    "cardCount": row.get("card_count"),
                    "isStaleFallback": True,
                }
            )
            meta["snapshot"] = snapshot
            if correlation:
                meta["cardAppealMarketPriceCorrelation"] = correlation
                meta["card_appeal_market_price_correlation"] = correlation
            timings = dict(meta.get("timings") or {})
            if set_resolve_ms is not None:
                timings["set_resolve_ms"] = set_resolve_ms
            timings["snapshot_query_ms"] = query_ms
            timings["snapshot_read_ms"] = round((time.perf_counter() - started) * 1000, 3)
            meta["timings"] = timings
            logger.info(
                "[pokemon-snapshot] cards snapshot read set_id=%s elapsed_ms=%s",
                resolved_set_id,
                timings["snapshot_read_ms"],
            )
            return {
                **payload,
                "cardAppealMarketPriceCorrelation": correlation,
                "card_appeal_market_price_correlation": correlation,
                "meta": meta,
            }
    except Exception as exc:
        elapsed_ms = round((time.perf_counter() - started) * 1000, 3)
        logger.exception(
            "[pokemon-snapshot] cards snapshot read failed set_id=%s elapsed_ms=%s exc_type=%s exc=%s",
            resolved_set_id,
            elapsed_ms,
            type(exc).__name__,
            exc,
        )
        raise PokemonSetCardsError(500, "Failed to read Pokemon set cards snapshot", "POKEMON_SET_CARDS_SNAPSHOT_FAILED")

    elapsed_ms = round((time.perf_counter() - started) * 1000, 3)
    logger.warning(
        "[pokemon-snapshot] missing cards snapshot; falling back to canonical cards set_id=%s elapsed_ms=%s",
        resolved_set_id,
        elapsed_ms,
    )
    payload = get_pokemon_set_cards_payload(resolved_set_id)
    meta = dict(payload.get("meta") or {})
    warnings = list(meta.get("warnings") or [])
    warnings.append("Pokemon set cards snapshot is missing; served canonical checklist fallback data.")
    meta["warnings"] = warnings
    meta["cardDesirabilityValidation"] = {
        "precomputed": False,
        "rowCount": 0,
        "source": None,
    }
    meta["card_desirability_validation"] = {
        "precomputed": False,
        "row_count": 0,
        "source": None,
    }
    meta["snapshot"] = {
        "source": "live_fallback_missing_pokemon_set_cards_snapshot_latest",
        "updatedAt": datetime.now(timezone.utc).isoformat(),
        "isStaleFallback": False,
    }
    return {**payload, "meta": meta}


_CARDS_PAGE_SNAPSHOT_COLUMNS = "set_id,cards_json,card_count,updated_at"
DEFAULT_CARDS_PAGE_SIZE = 60
MAX_CARDS_PAGE_SIZE = 120
CARDS_PAGE_SORT_OPTIONS = (
    "set-number",
    "name",
    "rarity",
    "market-price-desc",
    "market-price-asc",
    "7d-movers",
    "30d-gainers",
    "30d-decliners",
)
CARDS_PAGE_MOVEMENT_SORTS = ("7d-movers", "30d-gainers", "30d-decliners")
CARDS_PAGE_MOVEMENT_FILTERS = ("all", "heating", "cooling")
_CARD_NUMBER_PATTERN = re.compile(r"^(\d+)([a-zA-Z]*)$")
_CARD_NUMBER_MIXED_PATTERN = re.compile(r"(\d+)")


def _snake_to_camel(key: str) -> str:
    parts = key.split("_")
    return parts[0] + "".join(part.capitalize() for part in parts[1:])


def _to_camel_case_only(value: Any) -> Any:
    """Recursively project a dict/list tree to camelCase-only keys.

    The underlying pokemon_set_cards_snapshot_latest.cards_json rows carry
    the same dual camelCase/snake_case keys the legacy /cards payload does
    (enrich_cards_payload_with_desirability/_movement_fields write both on
    purpose for older frontend call sites). This new slim contract is
    camelCase-only, so for every snake_case key we drop it if a camelCase
    sibling already exists on the same dict, otherwise promote it to its
    camelCase form. Does not touch the underlying enrichment data itself —
    scoring/math and legacy /cards responses are unaffected.
    """
    if isinstance(value, dict):
        result: Dict[str, Any] = {}
        for key, inner_value in value.items():
            if not isinstance(key, str) or "_" not in key:
                camel_key = key
            else:
                camel_key = _snake_to_camel(key)
                if camel_key in value and camel_key != key:
                    continue
            result[camel_key] = _to_camel_case_only(inner_value)
        return result
    if isinstance(value, list):
        return [_to_camel_case_only(item) for item in value]
    return value


def _sanitize_cards_page(value: Any) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return 1
    return max(1, parsed)


def _sanitize_cards_page_size(value: Any) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return DEFAULT_CARDS_PAGE_SIZE
    return max(1, min(parsed, MAX_CARDS_PAGE_SIZE))


def _sanitize_cards_sort(value: Any) -> str:
    normalized = (_to_optional_str(value) or "").strip().lower()
    return normalized if normalized in CARDS_PAGE_SORT_OPTIONS else "set-number"


def _sanitize_cards_movement_sort(value: Any) -> Optional[str]:
    text = _to_optional_str(value)
    if not text:
        return None
    normalized = text.strip().lower()
    return normalized if normalized in CARDS_PAGE_MOVEMENT_SORTS else None


def _sanitize_cards_movement_filter(value: Any) -> str:
    normalized = (_to_optional_str(value) or "all").strip().lower()
    return normalized if normalized in CARDS_PAGE_MOVEMENT_FILTERS else "all"


def _cards_page_number_sort_key(card: Dict[str, Any]) -> tuple:
    number = _to_optional_str(card.get("cardNumber")) or _to_optional_str(card.get("printedNumber"))
    if number:
        compact = number.replace(" ", "")
        front = compact.split("/", 1)[0]
        numeric_match = _CARD_NUMBER_PATTERN.fullmatch(front)
        if numeric_match:
            suffix = numeric_match.group(2).lower()
            return (0, int(numeric_match.group(1)), suffix, compact.lower())
        mixed_match = _CARD_NUMBER_MIXED_PATTERN.search(front)
        if mixed_match:
            return (1, int(mixed_match.group(1)), front.lower(), compact.lower())
        return (2, front.lower(), "", compact.lower())
    name = _to_optional_str(card.get("name")) or ""
    return (3, name.lower(), "", "")


def _cards_page_stable_tie_key(card: Dict[str, Any]) -> tuple:
    return (
        _cards_page_number_sort_key(card),
        (_to_optional_str(card.get("id")) or _to_optional_str(card.get("cardId")) or "").lower(),
        (_to_optional_str(card.get("name")) or "").lower(),
    )


def _cards_page_movement_sign_value(card: Dict[str, Any], percent_field: str, amount_field: str) -> float:
    percent = _to_optional_float(card.get(percent_field))
    if percent is not None:
        return percent
    return _to_optional_float(card.get(amount_field)) or 0


def _cards_page_has_reliable_movement(card: Dict[str, Any], effective_sort: str) -> bool:
    if effective_sort == "7d-movers":
        movement = card.get("movement7d") if isinstance(card.get("movement7d"), dict) else {}
        explicit = card.get("movement7dReliable")
    else:
        movement = card.get("movement30d") if isinstance(card.get("movement30d"), dict) else {}
        explicit = card.get("movement30dReliable")
    if explicit is not None:
        return bool(explicit)
    if movement.get("reliable") is not None:
        return bool(movement.get("reliable"))
    # Backward-compatible snapshots predate the reliability field. A finite
    # percentage plus enoughHistory was their complete valid-movement signal.
    enough_history = movement.get("enoughHistory", card.get("enoughHistory"))
    if enough_history is not None:
        return bool(enough_history)
    percent_field = "change7dPercent" if effective_sort == "7d-movers" else "change30dPercent"
    return _to_optional_float(card.get(percent_field)) is not None


def _apply_cards_page_filters_and_sort(
    cards: List[Dict[str, Any]],
    *,
    query: Optional[str],
    rarity: Optional[str],
    movement_filter: str,
    sort: str,
    movement_sort: Optional[str],
) -> List[Dict[str, Any]]:
    filtered = list(cards)

    if query:
        query_lower = query.strip().lower()
        filtered = [card for card in filtered if query_lower in (_to_optional_str(card.get("name")) or "").lower()]

    if rarity:
        rarity_lower = rarity.strip().lower()
        filtered = [card for card in filtered if (_to_optional_str(card.get("rarity")) or "").strip().lower() == rarity_lower]

    effective_sort = movement_sort if movement_sort in CARDS_PAGE_MOVEMENT_SORTS else sort
    movement_percent_field = "change7dPercent" if effective_sort == "7d-movers" else "change30dPercent"
    movement_amount_field = "change7dAmount" if effective_sort == "7d-movers" else "change30dAmount"

    if movement_filter == "heating":
        filtered = [
            card for card in filtered
            if _cards_page_has_reliable_movement(card, effective_sort)
            and _cards_page_movement_sign_value(card, movement_percent_field, movement_amount_field) > 0
        ]
    elif movement_filter == "cooling":
        filtered = [
            card for card in filtered
            if _cards_page_has_reliable_movement(card, effective_sort)
            and _cards_page_movement_sign_value(card, movement_percent_field, movement_amount_field) < 0
        ]

    if effective_sort == "name":
        filtered.sort(key=lambda card: (_to_optional_str(card.get("name")) or "").lower())
    elif effective_sort == "rarity":
        filtered.sort(key=lambda card: ((_to_optional_str(card.get("rarity")) or "").lower(), _cards_page_number_sort_key(card)))
    elif effective_sort == "market-price-desc":
        filtered.sort(key=lambda card: (-(_to_optional_float(card.get("marketPrice")) if _to_optional_float(card.get("marketPrice")) is not None else -1.0), _cards_page_number_sort_key(card)))
    elif effective_sort == "market-price-asc":
        filtered.sort(key=lambda card: ((_to_optional_float(card.get("marketPrice")) if _to_optional_float(card.get("marketPrice")) is not None else float("inf")), _cards_page_number_sort_key(card)))
    elif effective_sort == "7d-movers":
        filtered.sort(
            key=lambda card: (
                not _cards_page_has_reliable_movement(card, effective_sort),
                _to_optional_float(card.get("change7dPercent")) is None,
                -abs(_to_optional_float(card.get("change7dPercent")) or 0),
                _cards_page_stable_tie_key(card),
            )
        )
    elif effective_sort == "30d-gainers":
        filtered.sort(key=lambda card: (-(_to_optional_float(card.get("change30dAmount")) if _to_optional_float(card.get("change30dAmount")) is not None else float("-inf")), _cards_page_number_sort_key(card)))
    elif effective_sort == "30d-decliners":
        filtered.sort(key=lambda card: ((_to_optional_float(card.get("change30dAmount")) if _to_optional_float(card.get("change30dAmount")) is not None else float("inf")), _cards_page_number_sort_key(card)))
    else:
        filtered.sort(key=_cards_page_number_sort_key)

    return filtered


def get_pokemon_set_cards_page_snapshot_payload(
    set_id: str,
    page: Any = 1,
    page_size: Any = DEFAULT_CARDS_PAGE_SIZE,
    sort: Any = "set-number",
    query: Any = None,
    rarity: Any = None,
    movement_filter: Any = None,
    movement_sort: Any = None,
) -> Dict[str, Any]:
    """Return a single paginated slice of a Pokemon set's checklist cards
    (camelCase only, no duplicate snake_case aliases).

    Reads only pokemon_set_cards_snapshot_latest.cards_json — never
    payload_json (which also carries cardDesirabilityValidation/
    cardAppealMarketPriceCorrelation, Insights-only data this endpoint does
    not need). cards_json already carries the fully enriched (movement +
    desirability) per-card fields the legacy /cards payload does; this
    function only slices/filters/sorts/re-keys it, it never recomputes
    scoring. Target response size is well under 250KB thanks to pagination
    plus dropping the duplicate snake_case keys.
    """
    started = time.perf_counter()
    resolved = _to_optional_str(set_id)
    if not resolved:
        raise PokemonSetCardsError(400, "set_id is required", "POKEMON_SET_CARDS_ID_REQUIRED")

    is_uuid = _looks_like_uuid(resolved)
    set_row: Optional[Dict[str, Any]] = None
    if is_uuid:
        resolved_set_id = resolved
    else:
        set_row = _resolve_set_row(resolved)
        resolved_set_id = str(set_row["id"])

    page_value = _sanitize_cards_page(page)
    page_size_value = _sanitize_cards_page_size(page_size)
    sort_value = _sanitize_cards_sort(sort)
    movement_sort_value = _sanitize_cards_movement_sort(movement_sort)
    movement_filter_value = _sanitize_cards_movement_filter(movement_filter)
    query_value = _to_optional_str(query)
    rarity_value = _to_optional_str(rarity)

    t_query = time.perf_counter()
    row: Optional[Dict[str, Any]] = None
    try:
        result = (
            public_read_client.table("pokemon_set_cards_snapshot_latest")
            .select(_CARDS_PAGE_SNAPSHOT_COLUMNS)
            .eq("set_id", resolved_set_id)
            .limit(1)
            .execute()
        )
        row = _first_row(result)
    except Exception as exc:
        logger.warning(
            "[pokemon-snapshot] cards page snapshot read failed set_id=%s exc=%s",
            resolved_set_id,
            exc,
            exc_info=True,
        )
        row = None
    query_ms = round((time.perf_counter() - t_query) * 1000, 3)

    raw_cards = row.get("cards_json") if row and isinstance(row.get("cards_json"), list) else []
    resolved_row_set_id = _to_optional_str((row or {}).get("set_id")) or resolved_set_id
    identity_row = set_row or {"id": resolved_row_set_id}
    set_identity = {
        "id": _to_optional_str(identity_row.get("id")) or resolved_row_set_id,
        "name": _to_optional_str(identity_row.get("name")),
        "slug": _to_optional_str(identity_row.get("canonical_key")),
        "canonicalKey": _to_optional_str(identity_row.get("canonical_key")),
    }

    camel_cards = [_to_camel_case_only(card) for card in raw_cards if isinstance(card, dict)]
    available_rarities = sorted(
        {rarity_name for card in camel_cards for rarity_name in [_to_optional_str(card.get("rarity"))] if rarity_name}
    )

    filtered_cards = _apply_cards_page_filters_and_sort(
        camel_cards,
        query=query_value,
        rarity=rarity_value,
        movement_filter=movement_filter_value,
        sort=sort_value,
        movement_sort=movement_sort_value,
    )

    total_cards = len(filtered_cards)
    total_pages = max(1, math.ceil(total_cards / page_size_value)) if total_cards else 1
    clamped_page = min(page_value, total_pages)
    start_index = (clamped_page - 1) * page_size_value
    page_cards = filtered_cards[start_index : start_index + page_size_value]

    warnings: List[str] = []
    if not row:
        warnings.append("Pokemon set cards page snapshot is missing; served empty fallback payload.")

    timings = {
        "snapshotQueryMs": query_ms,
        "snapshotReadMs": round((time.perf_counter() - started) * 1000, 3),
    }
    payload = {
        "set": set_identity,
        "cards": page_cards,
        "pagination": {
            "page": clamped_page,
            "pageSize": page_size_value,
            "totalCards": total_cards,
            "totalPages": total_pages,
            "hasNextPage": clamped_page < total_pages,
            "hasPreviousPage": clamped_page > 1,
        },
        "filters": {
            "availableRarities": available_rarities,
            "availableSorts": list(CARDS_PAGE_SORT_OPTIONS),
            "movementWindow": "7D" if (movement_sort_value or sort_value) == "7d-movers" else "30D",
            "sort": sort_value,
            "movementSort": movement_sort_value,
            "movementFilter": movement_filter_value,
            "query": query_value,
            "rarity": rarity_value,
        },
        "meta": {
            "warnings": warnings,
            "snapshot": {
                "source": "pokemon_set_cards_snapshot_latest.cards_json"
                if row
                else "empty_fallback_missing_pokemon_set_cards_snapshot_latest",
                "updatedAt": _to_optional_str((row or {}).get("updated_at")),
                "isStaleFallback": bool(row),
            },
            "timings": timings,
        },
    }
    logger.info(
        "[pokemon-snapshot] cards page snapshot read complete set_id=%s page=%s page_size=%s total_cards=%s query_ms=%s total_ms=%s",
        resolved_set_id,
        clamped_page,
        page_size_value,
        total_cards,
        query_ms,
        timings["snapshotReadMs"],
    )
    return payload


DEFAULT_CARD_VALIDATION_MAX_CARDS = 300
MAX_CARD_VALIDATION_MAX_CARDS = 500
CARD_VALIDATION_PAYLOAD_BUDGET_BYTES = 250_000
_CARD_VALIDATION_SNAPSHOT_COLUMNS = "set_id,payload_json,card_count,updated_at"


def _sanitize_card_validation_max_cards(value: Any) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return DEFAULT_CARD_VALIDATION_MAX_CARDS
    return max(1, min(parsed, MAX_CARD_VALIDATION_MAX_CARDS))


def _sanitize_include_plot_rows(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    text = _to_optional_str(value)
    if text is None:
        return True
    return text.strip().lower() not in {"false", "0", "no"}


def _card_validation_supertype_lookup(full_cards: List[Dict[str, Any]]) -> Dict[str, Dict[str, Any]]:
    # The trimmed cardDesirabilityValidation.cards rows don't carry
    # supertype/printedNumber (they were only ever meant for the validation
    # chart's score fields), but CardDesirabilityMarketValidationCard's
    # non-Pokemon exclusion diagnostics need supertype. The full enriched
    # `cards` array in the same payload_json row still has it — read it
    # in-memory only to backfill those two fields, never returned as-is.
    lookup: Dict[str, Dict[str, Any]] = {}
    for card in full_cards:
        if not isinstance(card, dict):
            continue
        card_id = _to_optional_str(card.get("id") or card.get("cardId") or card.get("card_id"))
        if not card_id or card_id in lookup:
            continue
        lookup[card_id] = {
            "supertype": _to_optional_str(card.get("supertype")),
            "printedNumber": _to_optional_str(
                card.get("printedNumber") or card.get("printed_number") or card.get("number")
            ),
        }
    return lookup


def _card_validation_row(card: Dict[str, Any], supertype_lookup: Dict[str, Dict[str, Any]]) -> Dict[str, Any]:
    card_id = _to_optional_str(card.get("cardId") or card.get("card_id") or card.get("id"))
    extra = supertype_lookup.get(card_id or "", {})
    return {
        "cardId": card_id,
        "cardVariantId": _to_optional_str(card.get("cardVariantId") or card.get("card_variant_id")),
        "name": _to_optional_str(card.get("name")),
        "rarity": _to_optional_str(card.get("rarity")),
        "supertype": extra.get("supertype"),
        "printedNumber": extra.get("printedNumber"),
        "imageUrl": _to_optional_str(card.get("imageUrl") or card.get("image_url")),
        "marketPrice": _to_optional_float(
            card.get("marketPrice") if card.get("marketPrice") is not None else card.get("market_price")
        ),
        "linkedPokemonName": _to_optional_str(card.get("pokemonName") or card.get("pokemon_name")),
        "pokemonDesirabilityScore": _to_optional_float(card.get("pokemonDesirabilityScore")),
        "treatmentScore": _to_optional_float(card.get("treatmentScore")),
        "scarcityScore": _to_optional_float(card.get("scarcityScore")),
        "adjustedCardAppealScore": _to_optional_float(card.get("adjustedCardAppealScore")),
        "pullRate": _to_optional_float(card.get("pullRate")),
        "pullRateSource": _to_optional_str(card.get("pullRateSource")),
        "setValueShare": _to_optional_float(card.get("setValueShare")),
        "isHitEligible": bool(card.get("isHitEligible")),
    }


def _empty_card_validation_payload(
    *,
    set_row: Dict[str, Any],
    warnings: Optional[List[str]] = None,
    fallback_source: str,
) -> Dict[str, Any]:
    return {
        "set": {
            "id": _to_optional_str(set_row.get("id")),
            "name": _to_optional_str(set_row.get("name")),
            "slug": _to_optional_str(set_row.get("canonical_key")),
            "canonicalKey": _to_optional_str(set_row.get("canonical_key")),
        },
        "cards": [],
        "cardAppealMarketPriceCorrelation": None,
        "diagnostics": {
            "canonicalCount": 0,
            "pricedCount": 0,
            "linkedCount": 0,
            "includedCount": 0,
            "excludedUnpricedCount": 0,
            "excludedUnlinkedCount": 0,
            "excludedMissingScoreCount": 0,
            "sampleSource": "canonical_checklist_cards",
        },
        "meta": {
            "source": fallback_source,
            "updatedAt": datetime.now(timezone.utc).isoformat(),
            "warnings": list(warnings or []),
        },
    }


def _card_validation_payload_size(payload: Dict[str, Any]) -> int:
    return len(json.dumps(payload, default=str).encode("utf-8"))


def _enforce_card_validation_payload_budget(payload: Dict[str, Any]) -> bool:
    """Progressively trim plotRows/rows (then cards) until the serialized
    payload fits CARD_VALIDATION_PAYLOAD_BUDGET_BYTES. diagnostics/meta are
    never trimmed. Returns True if anything was trimmed beyond the
    max_cards-based slice the caller already applied.
    """
    correlation = payload.get("cardAppealMarketPriceCorrelation")
    truncated = False
    while _card_validation_payload_size(payload) > CARD_VALIDATION_PAYLOAD_BUDGET_BYTES:
        trimmed_this_round = False
        if isinstance(correlation, dict):
            plot_rows = correlation.get("plotRows")
            if isinstance(plot_rows, list) and plot_rows:
                correlation["plotRows"] = plot_rows[: max(1, len(plot_rows) // 2)]
                trimmed_this_round = True
                truncated = True
            rows = correlation.get("rows")
            if isinstance(rows, list) and rows:
                correlation["rows"] = rows[: max(1, len(rows) // 2)]
                trimmed_this_round = True
                truncated = True
        if not trimmed_this_round:
            cards = payload.get("cards")
            if isinstance(cards, list) and len(cards) > 1:
                payload["cards"] = cards[: max(1, len(cards) // 2)]
                trimmed_this_round = True
                truncated = True
        if not trimmed_this_round:
            break
    return truncated


def get_pokemon_set_card_validation_snapshot_payload(
    set_id: str,
    max_cards: Any = DEFAULT_CARD_VALIDATION_MAX_CARDS,
    include_plot_rows: Any = True,
) -> Dict[str, Any]:
    """Return the slim Insights card-validation snapshot (camelCase only) for
    a Pokemon set: just enough card rows + cardAppealMarketPriceCorrelation
    for CardDesirabilityMarketValidationCard, without the full checklist
    `cards` array or payload_json that the legacy /cards contract carries.

    Reads pokemon_set_cards_snapshot_latest.payload_json (the same row the
    legacy /cards endpoint reads) but only to pull
    cardDesirabilityValidation.cards and cardAppealMarketPriceCorrelation out
    of it. The full enriched `cards` array on that row is read in-memory only
    to backfill supertype/printedNumber (missing from the trimmed validation
    rows) and is never included in the response.
    """
    started = time.perf_counter()
    resolved = _to_optional_str(set_id)
    if not resolved:
        raise PokemonSetCardsError(400, "set_id is required", "POKEMON_SET_CARDS_VALIDATION_ID_REQUIRED")

    max_cards_value = _sanitize_card_validation_max_cards(max_cards)
    include_plot_rows_value = _sanitize_include_plot_rows(include_plot_rows)

    is_uuid = _looks_like_uuid(resolved)
    set_row: Optional[Dict[str, Any]] = None
    if is_uuid:
        resolved_set_id = resolved
    else:
        set_row = _resolve_set_row(resolved)
        resolved_set_id = str(set_row["id"])

    t_query = time.perf_counter()
    row: Optional[Dict[str, Any]] = None
    try:
        result = (
            public_read_client.table("pokemon_set_cards_snapshot_latest")
            .select(_CARD_VALIDATION_SNAPSHOT_COLUMNS)
            .eq("set_id", resolved_set_id)
            .limit(1)
            .execute()
        )
        row = _first_row(result)
    except Exception as exc:
        logger.warning(
            "[pokemon-snapshot] card validation snapshot read failed set_id=%s exc=%s",
            resolved_set_id,
            exc,
            exc_info=True,
        )
        row = None
    query_ms = round((time.perf_counter() - t_query) * 1000, 3)

    if not row or not isinstance(row.get("payload_json"), dict):
        logger.info(
            "[pokemon-snapshot] card validation snapshot missing set_id=%s elapsed_ms=%s",
            resolved_set_id,
            round((time.perf_counter() - started) * 1000, 3),
        )
        return _empty_card_validation_payload(
            set_row=set_row or {"id": resolved_set_id},
            warnings=["Pokemon set card validation snapshot is missing; served empty fallback payload."],
            fallback_source="empty_fallback_missing_pokemon_set_cards_snapshot_latest",
        )

    payload_json = row["payload_json"]
    resolved_row_set_id = _to_optional_str(row.get("set_id")) or resolved_set_id
    identity_row = set_row or {"id": resolved_row_set_id}
    set_identity = {
        "id": _to_optional_str(identity_row.get("id")) or resolved_row_set_id,
        "name": _to_optional_str(identity_row.get("name")),
        "slug": _to_optional_str(identity_row.get("canonical_key")),
        "canonicalKey": _to_optional_str(identity_row.get("canonical_key")),
    }

    full_cards = payload_json.get("cards") if isinstance(payload_json.get("cards"), list) else []
    supertype_lookup = _card_validation_supertype_lookup(full_cards)

    validation = payload_json.get("cardDesirabilityValidation") or payload_json.get("card_desirability_validation") or {}
    validation_cards = validation.get("cards") if isinstance(validation, dict) else []
    if not isinstance(validation_cards, list):
        validation_cards = []
    total_validation_cards = len(validation_cards)
    cards_truncated = total_validation_cards > max_cards_value
    limited_validation_cards = validation_cards[:max_cards_value]
    cards = [
        _card_validation_row(card, supertype_lookup)
        for card in limited_validation_cards
        if isinstance(card, dict)
    ]

    correlation_raw = (
        payload_json.get("cardAppealMarketPriceCorrelation")
        or payload_json.get("card_appeal_market_price_correlation")
        or (payload_json.get("meta") or {}).get("cardAppealMarketPriceCorrelation")
        or (payload_json.get("meta") or {}).get("card_appeal_market_price_correlation")
    )
    correlation = _to_camel_case_only(correlation_raw) if isinstance(correlation_raw, dict) else None

    total_plot_rows = 0
    plot_rows_truncated = False
    if isinstance(correlation, dict):
        raw_plot_rows = correlation.get("plotRows") if isinstance(correlation.get("plotRows"), list) else []
        total_plot_rows = len(raw_plot_rows)
        if not include_plot_rows_value:
            correlation["plotRows"] = []
            correlation["rows"] = []
        else:
            if total_plot_rows > max_cards_value:
                plot_rows_truncated = True
            correlation["plotRows"] = raw_plot_rows[:max_cards_value]
            raw_rows = correlation.get("rows") if isinstance(correlation.get("rows"), list) else []
            correlation["rows"] = raw_rows[:max_cards_value]

    diagnostics = {
        "canonicalCount": correlation.get("canonicalCount") if isinstance(correlation, dict) else None,
        "pricedCount": correlation.get("pricedCount") if isinstance(correlation, dict) else None,
        "linkedCount": correlation.get("linkedCount") if isinstance(correlation, dict) else None,
        "includedCount": correlation.get("includedCount") if isinstance(correlation, dict) else total_validation_cards,
        "excludedUnpricedCount": correlation.get("excludedUnpricedCount") if isinstance(correlation, dict) else None,
        "excludedUnlinkedCount": correlation.get("excludedUnlinkedCount") if isinstance(correlation, dict) else None,
        "excludedMissingScoreCount": correlation.get("excludedMissingScoreCount") if isinstance(correlation, dict) else None,
        "sampleSource": (correlation.get("sampleSource") if isinstance(correlation, dict) else None)
        or "canonical_checklist_cards",
    }

    meta: Dict[str, Any] = {
        "source": "pokemon_set_cards_snapshot_latest",
        "updatedAt": _to_optional_str(row.get("updated_at")),
        "warnings": [],
        "timings": {
            "snapshotQueryMs": query_ms,
            "snapshotReadMs": round((time.perf_counter() - started) * 1000, 3),
        },
    }

    payload = {
        "set": set_identity,
        "cards": cards,
        "cardAppealMarketPriceCorrelation": correlation,
        "diagnostics": diagnostics,
        "meta": meta,
    }

    budget_truncated = _enforce_card_validation_payload_budget(payload)
    if cards_truncated or plot_rows_truncated or budget_truncated:
        meta["truncated"] = True
        meta["totalCards"] = total_validation_cards
        meta["totalPlotRows"] = total_plot_rows

    logger.info(
        "[pokemon-snapshot] card validation snapshot read complete set_id=%s cards=%s query_ms=%s total_ms=%s",
        resolved_set_id,
        len(payload["cards"]),
        query_ms,
        meta["timings"]["snapshotReadMs"],
    )

    return payload


def _top_chase_variant_ids(cards: List[Dict[str, Any]]) -> List[str]:
    variant_ids: List[str] = []
    seen: set[str] = set()
    for card in cards:
        if not isinstance(card, dict):
            continue
        variant_id = _to_optional_str(card.get("cardVariantId")) or _to_optional_str(card.get("card_variant_id"))
        if variant_id and variant_id not in seen:
            seen.add(variant_id)
            variant_ids.append(variant_id)
    return variant_ids


def _top_chase_history_for_card(card: Dict[str, Any], histories: Dict[str, List[Dict[str, Any]]]) -> List[Dict[str, Any]]:
    for key in (
        card.get("cardVariantId"),
        card.get("card_variant_id"),
        card.get("cardId"),
        card.get("card_id"),
        card.get("id"),
    ):
        normalized = _to_optional_str(key)
        if normalized and isinstance(histories.get(normalized), list):
            return histories[normalized]
    return []


def _compact_top_chase_observation_rows(rows: List[Dict[str, Any]]) -> Dict[str, List[Dict[str, Any]]]:
    point_by_variant_date: Dict[str, Dict[str, Dict[str, Any]]] = {}
    captured_at_by_variant_date: Dict[str, Dict[str, str]] = {}
    for row in rows:
        variant_id = _to_optional_str(row.get("card_variant_id"))
        captured_at = _to_optional_str(row.get("captured_at") or row.get("capturedAt"))
        captured_date = _parse_date_key(captured_at)
        price = _to_optional_float(row.get("market_price") if "market_price" in row else row.get("marketPrice"))
        if not variant_id or not captured_date or price is None or price <= 0:
            continue
        existing_captured_at = captured_at_by_variant_date.setdefault(variant_id, {}).get(captured_date)
        if existing_captured_at and captured_at and captured_at <= existing_captured_at:
            continue
        captured_at_by_variant_date[variant_id][captured_date] = captured_at or captured_date
        point_by_variant_date.setdefault(variant_id, {})[captured_date] = {
            "date": captured_date,
            "marketPrice": round(price, 2),
            "market_price": round(price, 2),
            "sourceDate": captured_date,
            "source_date": captured_date,
            "isObserved": True,
            "is_observed": True,
        }

    return {
        variant_id: [points[date_key] for date_key in sorted(points.keys())]
        for variant_id, points in point_by_variant_date.items()
        if points
    }


def _compact_top_chase_history_points(points: Any) -> List[Dict[str, Any]]:
    compact_points: Dict[str, Dict[str, Any]] = {}
    for point in list(points or []):
        if not isinstance(point, dict):
            continue
        date_key = _parse_date_key(point.get("date") or point.get("snapshot_date") or point.get("capturedAt") or point.get("captured_at"))
        price = _to_optional_float(point.get("marketPrice") if "marketPrice" in point else point.get("market_price", point.get("price")))
        if not date_key or price is None:
            continue
        source_date = _parse_date_key(point.get("sourceDate") or point.get("source_date")) or date_key
        compact_points[date_key] = {
            "date": date_key,
            "marketPrice": round(price, 2),
            "market_price": round(price, 2),
            "sourceDate": source_date,
            "source_date": source_date,
        }
    return [compact_points[date_key] for date_key in sorted(compact_points.keys())]


def _existing_top_chase_histories(
    payload: Dict[str, Any],
    row: Dict[str, Any],
) -> Dict[str, List[Dict[str, Any]]]:
    for candidate in (
        payload.get("topChaseCardHistories"),
        payload.get("top_chase_card_histories"),
        row.get("top_chase_card_histories_json"),
    ):
        if not isinstance(candidate, dict):
            continue
        histories = {
            str(key): compact_history
            for key, value in candidate.items()
            if key is not None
            and isinstance(value, list)
            and (compact_history := _compact_top_chase_history_points(value))
        }
        if histories:
            return histories
    return {}


def _top_chase_history_counts(histories: Dict[str, List[Dict[str, Any]]]) -> List[int]:
    return [len(history) for history in histories.values() if isinstance(history, list)]


def _top_chase_histories_cover_source_window(
    histories: Dict[str, List[Dict[str, Any]]],
    *,
    variant_ids: List[str],
    source_window_days: int,
) -> bool:
    if not variant_ids:
        return bool(histories)
    for variant_id in variant_ids:
        history = histories.get(variant_id)
        if not isinstance(history, list) or len(history) < source_window_days:
            return False
    return True


def _normalize_match_text(value: Any) -> str:
    return " ".join(str(value or "").strip().lower().split())


def _normalize_card_number(value: Any) -> str:
    compact = str(value or "").strip().replace(" ", "").lower()
    if "/" in compact:
        compact = compact.split("/", 1)[0]
    stripped = compact.lstrip("0")
    return stripped or compact


def _top_chase_card_match_keys(name: Any, number: Any) -> List[str]:
    normalized_name = _normalize_match_text(name)
    normalized_number = _normalize_card_number(number)
    if not normalized_name or not normalized_number:
        return []
    return [
        f"name+number:{normalized_name}:{normalized_number}",
        f"name+raw_number:{normalized_name}:{str(number or '').strip().replace(' ', '').lower()}",
    ]


def _query_snapshot_rows(table_name: str, configure_query) -> List[Dict[str, Any]]:
    result = configure_query(public_read_client.table(table_name)).execute()
    return list(result.data or [])


def _build_top_chase_canonical_history_context(
    *,
    set_id: str,
    cards: List[Dict[str, Any]],
) -> Dict[str, Any]:
    canonical_cards = _query_snapshot_rows(
        "pokemon_canonical_cards",
        lambda query: query.select("id,set_id,pokemon_tcg_api_card_id,name,number,printed_number").eq("set_id", set_id),
    )
    legacy_cards = _query_snapshot_rows(
        "cards",
        lambda query: query.select("id,set_id,name,card_number,pokemon_tcg_api_id").eq("set_id", set_id),
    )
    legacy_card_ids = [str(card["id"]) for card in legacy_cards if card.get("id") is not None]
    variant_rows = (
        _query_snapshot_rows(
            "card_variants",
            lambda query: query.select("id,card_id,pokemon_tcg_api_id").in_("card_id", legacy_card_ids),
        )
        if legacy_card_ids
        else []
    )

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
        for key in _top_chase_card_match_keys(card.get("name"), card.get("number")) + _top_chase_card_match_keys(
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
            for key in _top_chase_card_match_keys(legacy_card.get("name"), legacy_card.get("card_number")):
                canonical = canonical_by_match_key.get(key)
                if canonical is not None:
                    break
        if canonical and legacy_card.get("id") is not None:
            legacy_card_to_canonical_id[str(legacy_card["id"])] = str(canonical["id"])

    variant_to_canonical_id: Dict[str, str] = {}
    for variant in variant_rows:
        variant_id = _to_optional_str(variant.get("id"))
        if not variant_id:
            continue
        canonical_id = legacy_card_to_canonical_id.get(str(variant.get("card_id")))
        variant_api_id = _to_optional_str(variant.get("pokemon_tcg_api_id"))
        if variant_api_id and variant_api_id in canonical_by_api_id:
            canonical_id = str(canonical_by_api_id[variant_api_id]["id"])
        if canonical_id in canonical_by_id:
            variant_to_canonical_id[variant_id] = canonical_id

    display_key_to_canonical_id: Dict[str, str] = {}
    for card in cards:
        display_key = _to_optional_str(card.get("cardVariantId")) or _to_optional_str(card.get("card_variant_id")) or _to_optional_str(card.get("cardId")) or _to_optional_str(card.get("card_id")) or _to_optional_str(card.get("id"))
        variant_id = _to_optional_str(card.get("cardVariantId")) or _to_optional_str(card.get("card_variant_id"))
        card_id = _to_optional_str(card.get("cardId")) or _to_optional_str(card.get("card_id")) or _to_optional_str(card.get("id"))
        canonical_id = (
            variant_to_canonical_id.get(variant_id or "")
            or legacy_card_to_canonical_id.get(card_id or "")
            or (card_id if card_id in canonical_by_id else None)
        )
        if display_key and canonical_id:
            display_key_to_canonical_id[display_key] = canonical_id

    target_canonical_ids = set(display_key_to_canonical_id.values())
    return {
        "canonical_by_id": canonical_by_id,
        "variant_to_canonical_id": variant_to_canonical_id,
        "display_key_to_canonical_id": display_key_to_canonical_id,
        "variant_ids": sorted(
            variant_id
            for variant_id, canonical_id in variant_to_canonical_id.items()
            if canonical_id in target_canonical_ids
        ),
    }


def _compact_top_chase_canonical_observation_rows(
    rows: List[Dict[str, Any]],
    *,
    variant_to_canonical_id: Dict[str, str],
    display_key_to_canonical_id: Dict[str, str],
) -> Dict[str, List[Dict[str, Any]]]:
    point_by_canonical_date: Dict[str, Dict[str, Dict[str, Any]]] = {}
    captured_at_by_canonical_date: Dict[str, Dict[str, str]] = {}
    daily_counts_by_canonical_date: Dict[str, Dict[str, int]] = {}
    for row in rows:
        variant_id = _to_optional_str(row.get("card_variant_id"))
        canonical_id = _to_optional_str(variant_to_canonical_id.get(variant_id or ""))
        captured_at = _to_optional_str(row.get("captured_at") or row.get("capturedAt"))
        captured_date = _parse_date_key(captured_at)
        price = _to_optional_float(row.get("market_price") if "market_price" in row else row.get("marketPrice"))
        if not canonical_id or not captured_date or price is None or price <= 0:
            continue
        daily_counts = daily_counts_by_canonical_date.setdefault(canonical_id, {})
        daily_counts[captured_date] = daily_counts.get(captured_date, 0) + 1
        existing_captured_at = captured_at_by_canonical_date.setdefault(canonical_id, {}).get(captured_date)
        if existing_captured_at and captured_at and captured_at <= existing_captured_at:
            continue
        captured_at_by_canonical_date[canonical_id][captured_date] = captured_at or captured_date
        point_by_canonical_date.setdefault(canonical_id, {})[captured_date] = {
            "date": captured_date,
            "marketPrice": round(price, 2),
            "market_price": round(price, 2),
            "sourceDate": captured_date,
            "source_date": captured_date,
            "sourceVariantId": variant_id,
            "source_variant_id": variant_id,
            "dailyObservationCount": daily_counts[captured_date],
            "daily_observation_count": daily_counts[captured_date],
            "isObserved": True,
            "is_observed": True,
            "isCarriedForward": False,
            "is_carried_forward": False,
        }

    histories: Dict[str, List[Dict[str, Any]]] = {}
    for display_key, canonical_id in display_key_to_canonical_id.items():
        points = point_by_canonical_date.get(canonical_id, {})
        if points:
            histories[display_key] = [points[date_key] for date_key in sorted(points.keys())]
    return histories


def _load_top_chase_observation_histories(
    *,
    set_id: str,
    cards: Optional[List[Dict[str, Any]]] = None,
    variant_ids: List[str],
    latest_date_key: Optional[str],
    window_days: int,
) -> Dict[str, List[Dict[str, Any]]]:
    if not variant_ids:
        return {}

    resolved_latest_date_key = latest_date_key
    if not resolved_latest_date_key:
        try:
            latest_result = (
                public_read_client.table("card_variant_price_observations")
                .select("captured_at")
                .in_("card_variant_id", variant_ids)
                .eq("condition_id", TOP_CHASE_NEAR_MINT_CONDITION_ID)
                .gt("market_price", 0)
                .order("captured_at", desc=True)
                .limit(1)
                .execute()
            )
            resolved_latest_date_key = _parse_date_key((_first_row(latest_result) or {}).get("captured_at"))
        except Exception as exc:
            logger.warning(
                "[pokemon-snapshot] top chase observation history latest lookup failed set_id=%s error=%s",
                set_id,
                exc,
                exc_info=True,
            )
            return {}

    try:
        latest_date = date.fromisoformat(str(resolved_latest_date_key))
    except (TypeError, ValueError):
        return {}

    start_date = latest_date - timedelta(days=max(window_days - 1, 0))
    end_date = latest_date + timedelta(days=1)
    canonical_context: Dict[str, Any] = {}
    try:
        canonical_context = _build_top_chase_canonical_history_context(
            set_id=set_id,
            cards=list(cards or []),
        )
    except Exception as exc:
        logger.warning(
            "[pokemon-snapshot] canonical top chase history context failed set_id=%s error=%s",
            set_id,
            exc,
            exc_info=True,
        )
        canonical_context = {}

    canonical_variant_ids = list(canonical_context.get("variant_ids") or [])
    if canonical_variant_ids:
        try:
            latest_result = (
                public_read_client.table("card_variant_price_observations")
                .select("captured_at")
                .in_("card_variant_id", canonical_variant_ids)
                .eq("condition_id", TOP_CHASE_NEAR_MINT_CONDITION_ID)
                .gt("market_price", 0)
                .order("captured_at", desc=True)
                .limit(1)
                .execute()
            )
            canonical_latest_date_key = _parse_date_key((_first_row(latest_result) or {}).get("captured_at"))
            if canonical_latest_date_key:
                canonical_latest_date = date.fromisoformat(canonical_latest_date_key)
                if canonical_latest_date > latest_date:
                    latest_date = canonical_latest_date
                    start_date = latest_date - timedelta(days=max(window_days - 1, 0))
                    end_date = latest_date + timedelta(days=1)
            history_result = (
                public_read_client.table("card_variant_price_observations")
                .select("card_variant_id,captured_at,market_price")
                .in_("card_variant_id", canonical_variant_ids)
                .eq("condition_id", TOP_CHASE_NEAR_MINT_CONDITION_ID)
                .gt("market_price", 0)
                .gte("captured_at", start_date.isoformat())
                .lt("captured_at", end_date.isoformat())
                .order("captured_at", desc=False)
                .execute()
            )
            histories = _compact_top_chase_canonical_observation_rows(
                list(history_result.data or []),
                variant_to_canonical_id=dict(canonical_context.get("variant_to_canonical_id") or {}),
                display_key_to_canonical_id=dict(canonical_context.get("display_key_to_canonical_id") or {}),
            )
            if histories:
                return histories
        except Exception as exc:
            logger.warning(
                "[pokemon-snapshot] canonical top chase observation history hydration failed set_id=%s variants=%s error=%s",
                set_id,
                len(canonical_variant_ids),
                exc,
                exc_info=True,
            )

    try:
        history_result = (
            public_read_client.table("card_variant_price_observations")
            .select("card_variant_id,captured_at,market_price")
            .in_("card_variant_id", variant_ids)
            .eq("condition_id", TOP_CHASE_NEAR_MINT_CONDITION_ID)
            .gt("market_price", 0)
            .gte("captured_at", start_date.isoformat())
            .lt("captured_at", end_date.isoformat())
            .order("captured_at", desc=False)
            .execute()
        )
    except Exception as exc:
        logger.warning(
            "[pokemon-snapshot] top chase observation history hydration failed set_id=%s variants=%s error=%s",
            set_id,
            len(variant_ids),
            exc,
            exc_info=True,
        )
        return {}

    return _compact_top_chase_observation_rows(list(history_result.data or []))


def _attach_top_chase_histories(
    payload: Dict[str, Any],
    histories: Dict[str, List[Dict[str, Any]]],
    *,
    source_window_days: int = TOP_CHASE_HISTORY_SOURCE_WINDOW_DAYS,
) -> Dict[str, Any]:
    counts = _top_chase_history_counts(histories)
    observed_dates = [
        str(point.get("date"))[:10]
        for history in histories.values()
        if isinstance(history, list)
        for point in history
        if _parse_date_key(point.get("date"))
    ]

    source_cards = (
        payload.get("topChaseCards")
        if isinstance(payload.get("topChaseCards"), list)
        else payload.get("top_chase_cards")
    )
    cards: List[Dict[str, Any]] = []
    for card in list(source_cards or []):
        if not isinstance(card, dict):
            continue
        next_card = {key: value for key, value in card.items() if key not in {"priceHistory", "price_history"}}
        history = _top_chase_history_for_card(next_card, histories)
        if history:
            next_card["priceHistory"] = history
            next_card["price_history"] = history
            latest_price_point = next(
                (
                    point
                    for point in reversed(history)
                    if _to_optional_float(point.get("marketPrice") if "marketPrice" in point else point.get("market_price")) is not None
                    and not bool(point.get("isCarriedForward") or point.get("is_carried_forward"))
                ),
                None,
            )
            if latest_price_point:
                latest_price = round(
                    _to_optional_float(
                        latest_price_point.get("marketPrice")
                        if "marketPrice" in latest_price_point
                        else latest_price_point.get("market_price")
                    )
                    or 0,
                    2,
                )
                next_card["marketPrice"] = latest_price
                next_card["estimatedMarketPrice"] = latest_price
                next_card["estimated_market_price"] = latest_price
                next_card["priceUsed"] = latest_price
                next_card["price_used"] = latest_price
                latest_date = _parse_date_key(
                    latest_price_point.get("date")
                    or latest_price_point.get("sourceDate")
                    or latest_price_point.get("source_date")
                )
                if latest_date:
                    next_card["priceUpdatedAt"] = latest_date
                    next_card["price_updated_at"] = latest_date
        cards.append(next_card)

    next_payload = dict(payload)
    next_payload["topChaseCardHistories"] = histories
    next_payload["top_chase_card_histories"] = histories
    next_payload["topChaseCards"] = cards
    next_payload["top_chase_cards"] = cards
    meta = dict(next_payload.get("meta") or {})
    meta["topChaseHistorySource"] = TOP_CHASE_HISTORY_SOURCE
    meta["topChaseHistorySourceWindowDays"] = source_window_days
    meta["topChaseHistoryMinPoints"] = min(counts) if counts else 0
    meta["topChaseHistoryMaxPoints"] = max(counts) if counts else 0
    meta["topChaseHistoryFirstObservedDate"] = min(observed_dates) if observed_dates else None
    meta["topChaseHistoryLatestObservedDate"] = max(observed_dates) if observed_dates else None
    meta["topChaseHistoryHydratedFromDailyTable"] = False
    next_payload["meta"] = meta
    return next_payload


def _hydrate_market_dashboard_top_chase_histories(
    payload: Dict[str, Any],
    row: Dict[str, Any],
    *,
    set_id: str,
    window: str,
    days: Any = None,
    allow_live_query: bool = True,
) -> Dict[str, Any]:
    top_cards = (
        payload.get("topChaseCards")
        if isinstance(payload.get("topChaseCards"), list)
        else payload.get("top_chase_cards")
    )
    cards = [card for card in list(top_cards or []) if isinstance(card, dict)]
    variant_ids = _top_chase_variant_ids(cards)

    # Prefer stored histories from the snapshot — avoids expensive live observation queries.
    # Only fall back to live card_variant_price_observations if stored histories are absent
    # and live queries are permitted (non-UUID fast path).
    histories = _existing_top_chase_histories(payload, row)
    if not histories and variant_ids:
        if allow_live_query:
            logger.info(
                "[pokemon-snapshot] no stored top chase histories; loading from observations set_id=%s variant_count=%s",
                set_id,
                len(variant_ids),
            )
            histories = _load_top_chase_observation_histories(
                set_id=set_id,
                cards=cards,
                variant_ids=variant_ids,
                latest_date_key=_parse_date_key(
                    row.get("latest_market_date") or payload.get("latestMarketDate") or payload.get("latest_market_date")
                ),
                window_days=TOP_CHASE_HISTORY_SOURCE_WINDOW_DAYS,
            )
        else:
            logger.info(
                "[pokemon-snapshot] no stored top chase histories; skipping live observation query (uuid fast path) set_id=%s variant_count=%s",
                set_id,
                len(variant_ids),
            )
    return _attach_top_chase_histories(
        payload,
        histories,
        source_window_days=TOP_CHASE_HISTORY_SOURCE_WINDOW_DAYS,
    )


_MARKET_DASHBOARD_SNAPSHOT_COLUMNS = (
    "set_id,window_key,set_value_histories_json,performance_vs_cost_history_json,"
    "top_chase_cards_json,top_chase_card_histories_json,available_scopes_json,"
    "latest_market_date,updated_at,payload_json"
)

_EMPTY_MARKET_MOVERS: Dict[str, Any] = {"heatingUp": [], "coolingOff": [], "all": []}


def _build_market_dashboard_payload_from_row(
    row: Dict[str, Any],
    *,
    set_row: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    resolved_set_id = _to_optional_str(row.get("set_id"))
    identity_row = set_row or {"id": resolved_set_id}
    set_identity = {
        "id": _to_optional_str(identity_row.get("id")) or resolved_set_id,
        "name": _to_optional_str(identity_row.get("name")),
        "slug": _to_optional_str(identity_row.get("canonical_key")),
        "pokemon_api_set_id": _to_optional_str(identity_row.get("pokemon_api_set_id")),
    }
    histories_by_scope = row.get("set_value_histories_json") if isinstance(row.get("set_value_histories_json"), dict) else {}
    performance_vs_cost_history = (
        row.get("performance_vs_cost_history_json") if isinstance(row.get("performance_vs_cost_history_json"), list) else []
    )
    top_chase_cards = row.get("top_chase_cards_json") if isinstance(row.get("top_chase_cards_json"), list) else []
    available_scopes = row.get("available_scopes_json") if isinstance(row.get("available_scopes_json"), list) else []
    window_key = _to_optional_str(row.get("window_key"))
    latest_market_date = _parse_date_key(row.get("latest_market_date"))

    stored_payload = row.get("payload_json") if isinstance(row.get("payload_json"), dict) else {}
    market_movers = stored_payload.get("marketMovers")
    if not isinstance(market_movers, dict):
        market_movers = stored_payload.get("market_movers")
    if not isinstance(market_movers, dict):
        market_movers = _EMPTY_MARKET_MOVERS

    market_movers_by_window = stored_payload.get("marketMoversByWindow")
    if not isinstance(market_movers_by_window, dict):
        market_movers_by_window = stored_payload.get("market_movers_by_window")
    if not isinstance(market_movers_by_window, dict):
        # Older snapshot rows predate per-window movers; fall back to the 30D
        # compatibility field so the 30D tab still works until the next rebuild.
        market_movers_by_window = {"30D": market_movers}

    return {
        "set": set_identity,
        "window": window_key,
        "window_key": window_key,
        "setValueHistoriesByScope": histories_by_scope,
        "set_value_histories_by_scope": histories_by_scope,
        "performanceVsCostHistory": performance_vs_cost_history,
        "performance_vs_cost_history": performance_vs_cost_history,
        "topChaseCards": top_chase_cards,
        "top_chase_cards": top_chase_cards,
        "marketMovers": market_movers,
        "market_movers": market_movers,
        "marketMoversByWindow": market_movers_by_window,
        "market_movers_by_window": market_movers_by_window,
        "availableScopes": available_scopes,
        "available_scopes": available_scopes,
        "latestMarketDate": latest_market_date,
        "latest_market_date": latest_market_date,
        "meta": {"warnings": []},
    }


def _read_market_dashboard_snapshot(
    set_id: str,
    window: str = DEFAULT_DASHBOARD_WINDOW,
    days: Any = None,
    *,
    set_row: Optional[Dict[str, Any]] = None,
    allow_live_history_hydration: bool = True,
) -> Optional[Dict[str, Any]]:
    t0 = time.perf_counter()
    resolved_window = _normalize_market_dashboard_window_key(window)
    try:
        result = (
            public_read_client.table("pokemon_set_market_dashboard_snapshot_latest")
            .select(_MARKET_DASHBOARD_SNAPSHOT_COLUMNS)
            .eq("set_id", set_id)
            .eq("window_key", resolved_window)
            .limit(1)
            .execute()
        )
        query_ms = round((time.perf_counter() - t0) * 1000, 3)
    except Exception as exc:
        if _is_missing_snapshot_relation_error(exc):
            logger.warning(
                "[pokemon-snapshot] market dashboard snapshot relation missing set_id=%s window=%s snapshot_read_status=missing_relation fallback_used=true elapsed_ms=%.1f",
                set_id,
                resolved_window,
                (time.perf_counter() - t0) * 1000,
            )
            return None
        raise

    row = _first_row(result)
    if not row:
        logger.info(
            "[pokemon-snapshot] market dashboard snapshot missing row set_id=%s window=%s snapshot_read_status=missing_row fallback_used=true query_ms=%s",
            set_id,
            resolved_window,
            query_ms,
        )
        return None

    logger.info(
        "[pokemon-snapshot] market dashboard snapshot query done set_id=%s window=%s query_ms=%s row_present=true",
        set_id,
        resolved_window,
        query_ms,
    )
    t_hydrate = time.perf_counter()
    payload = _hydrate_market_dashboard_top_chase_histories(
        _build_market_dashboard_payload_from_row(row, set_row=set_row),
        row,
        set_id=set_id,
        window=resolved_window,
        days=days,
        allow_live_query=allow_live_history_hydration,
    )
    hydrate_ms = round((time.perf_counter() - t_hydrate) * 1000, 3)
    meta = dict(payload.get("meta") or {})
    snapshot = dict(meta.get("snapshot") or {})
    snapshot.update(
        {
            "source": "pokemon_set_market_dashboard_snapshot_latest",
            "window": row.get("window_key"),
            "updatedAt": _to_optional_str(row.get("updated_at")),
            "latestMarketDate": _parse_date_key(row.get("latest_market_date")),
            "isStaleFallback": True,
        }
    )
    timings = dict(meta.get("timings") or {})
    timings["snapshot_query_ms"] = query_ms
    timings["hydration_ms"] = hydrate_ms
    timings["snapshot_read_ms"] = round((time.perf_counter() - t0) * 1000, 3)
    meta["snapshot"] = snapshot
    meta["timings"] = timings
    logger.info(
        "[pokemon-snapshot] market dashboard snapshot read complete set_id=%s window=%s query_ms=%s hydrate_ms=%s total_ms=%s",
        set_id,
        resolved_window,
        query_ms,
        hydrate_ms,
        timings["snapshot_read_ms"],
    )
    return {**payload, "meta": meta}


def _load_simulation_performance_history_live(set_id: str) -> List[Dict[str, Any]]:
    """Load simulation performance history from calculation_history_trend + simulation_run_summary."""
    try:
        result = (
            public_read_client.table("calculation_history_trend")
            .select(
                "snapshot_date,calculation_run_id,run_created_at,"
                "simulated_mean_pack_value_vs_pack_cost,simulated_median_pack_value_vs_pack_cost,"
                "p95_value_to_cost_ratio"
            )
            .eq("target_type", "set")
            .eq("target_id", set_id)
            .order("snapshot_date", desc=False)
            .execute()
        )
        rows = list(result.data or [])
    except Exception:
        logger.warning("[pokemon-snapshot] simulation performance history load failed set_id=%s", set_id, exc_info=True)
        return []

    run_ids = sorted({str(row["calculation_run_id"]) for row in rows if row.get("calculation_run_id")})
    summary_lookup: Dict[str, Dict[str, Any]] = {}
    if run_ids:
        try:
            summary_result = (
                public_read_client.table("simulation_run_summary")
                .select("calculation_run_id,pack_cost,mean_value,median_value")
                .in_("calculation_run_id", run_ids)
                .execute()
            )
            for summary_row in list(summary_result.data or []):
                run_id_key = _to_optional_str(summary_row.get("calculation_run_id"))
                if run_id_key:
                    summary_lookup[run_id_key] = summary_row
        except Exception:
            logger.warning("[pokemon-snapshot] simulation run summary join failed set_id=%s", set_id, exc_info=True)

    points: List[Dict[str, Any]] = []
    for row in rows:
        date_key = _parse_date_key(row.get("snapshot_date"))
        if not date_key:
            continue
        run_id = _to_optional_str(row.get("calculation_run_id"))
        run_created_at = _to_optional_str(row.get("run_created_at"))
        mean_ratio = _to_optional_float(row.get("simulated_mean_pack_value_vs_pack_cost"))
        median_ratio = _to_optional_float(row.get("simulated_median_pack_value_vs_pack_cost"))
        p95_ratio = _to_optional_float(row.get("p95_value_to_cost_ratio"))
        summary = summary_lookup.get(run_id or "") or {}
        pack_cost = _to_optional_float(summary.get("pack_cost"))
        mean_value = _to_optional_float(summary.get("mean_value"))
        median_value = _to_optional_float(summary.get("median_value"))
        points.append({
            "date": date_key,
            "snapshot_date": date_key,
            "sourceDate": date_key,
            "source_date": date_key,
            "calculationRunId": run_id,
            "calculation_run_id": run_id,
            "runCreatedAt": run_created_at,
            "run_created_at": run_created_at,
            "packCost": pack_cost,
            "pack_cost": pack_cost,
            "meanValue": mean_value,
            "mean_value": mean_value,
            "medianValue": median_value,
            "median_value": median_value,
            "meanValueToCostRatio": mean_ratio,
            "mean_value_to_cost_ratio": mean_ratio,
            "simulatedMeanPackValueVsPackCost": mean_ratio,
            "simulated_mean_pack_value_vs_pack_cost": mean_ratio,
            "medianValueToCostRatio": median_ratio,
            "median_value_to_cost_ratio": median_ratio,
            "simulatedMedianPackValueVsPackCost": median_ratio,
            "simulated_median_pack_value_vs_pack_cost": median_ratio,
            "p95ValueToCostRatio": p95_ratio,
            "p95_value_to_cost_ratio": p95_ratio,
            "source": "calculation_history_trend+simulation_run_summary",
            "provider": "calculation_history_trend+simulation_run_summary",
            "isCarriedForward": False,
            "is_carried_forward": False,
        })
    return points


def _empty_market_dashboard_payload(
    *,
    set_row: Dict[str, Any],
    window: str,
    warnings: Optional[List[str]] = None,
    fallback_source: str,
) -> Dict[str, Any]:
    resolved_window = _normalize_market_dashboard_window_key(window)
    histories_by_scope: Dict[str, List[Dict[str, Any]]] = {scope: [] for scope in SET_VALUE_SCOPES}
    available_scopes: List[Dict[str, Any]] = [
        {"key": scope, "label": SET_VALUE_SCOPE_LABELS.get(scope, scope), "latestDate": None}
        for scope in SET_VALUE_SCOPES
    ]
    return {
        "set": {
            "id": _to_optional_str(set_row.get("id")),
            "name": _to_optional_str(set_row.get("name")),
            "slug": _to_optional_str(set_row.get("canonical_key")),
            "pokemon_api_set_id": _to_optional_str(set_row.get("pokemon_api_set_id")),
        },
        "window": resolved_window,
        "window_key": resolved_window,
        "setValueHistoriesByScope": histories_by_scope,
        "set_value_histories_by_scope": histories_by_scope,
        "performanceVsCostHistory": [],
        "performance_vs_cost_history": [],
        "topChaseCards": [],
        "top_chase_cards": [],
        "availableScopes": available_scopes,
        "available_scopes": available_scopes,
        "latestMarketDate": None,
        "latest_market_date": None,
        "meta": {
            "warnings": list(warnings or []),
            "snapshot": {
                "source": fallback_source,
                "updatedAt": datetime.now(timezone.utc).isoformat(),
                "isStaleFallback": False,
            },
        },
    }


def get_pokemon_set_market_dashboard_snapshot_payload(
    set_id: str,
    window: str = DEFAULT_DASHBOARD_WINDOW,
    days: Any = None,
) -> Dict[str, Any]:
    started = time.perf_counter()
    resolved = _to_optional_str(set_id)
    if not resolved:
        raise PokemonSetMarketError(400, "set_id is required", "POKEMON_SET_MARKET_ID_REQUIRED")
    is_uuid = _looks_like_uuid(resolved)
    logger.info(
        "[pokemon-snapshot] market dashboard snapshot start set_id=%s window=%s uuid_fast_path=%s",
        resolved,
        window,
        is_uuid,
    )

    set_row: Optional[Dict[str, Any]] = None
    set_resolve_ms: Optional[float] = None

    resolved_window = _normalize_market_dashboard_window_key(window)
    resolved_days = _sanitize_days(days, default=DEFAULT_SET_VALUE_HISTORY_DAYS)

    if is_uuid:
        resolved_set_id = resolved
    else:
        t_resolve = time.perf_counter()
        set_row = _resolve_set_row(resolved)
        resolved_set_id = str(set_row["id"])
        set_resolve_ms = round((time.perf_counter() - t_resolve) * 1000, 3)
        logger.info(
            "[pokemon-snapshot] market dashboard set resolved set_id=%s resolved_set_id=%s window=%s resolve_ms=%s",
            resolved,
            resolved_set_id,
            resolved_window,
            set_resolve_ms,
        )

    try:
        t_snapshot = time.perf_counter()
        logger.info(
            "[pokemon-snapshot] market dashboard snapshot query start set_id=%s window=%s",
            resolved_set_id,
            resolved_window,
        )
        payload = _read_market_dashboard_snapshot(
            resolved_set_id,
            resolved_window,
            days=_market_dashboard_window_days(resolved_window, days),
            set_row=set_row,
            allow_live_history_hydration=not is_uuid,
        )
        snapshot_ms = round((time.perf_counter() - t_snapshot) * 1000, 3)
        if payload is not None:
            logger.info(
                "[pokemon-snapshot] market dashboard snapshot read set_id=%s resolved_set_id=%s window=%s "
                "snapshot_read_status=hit fallback_used=false uuid_fast_path=%s resolve_ms=%s snapshot_ms=%s total_ms=%s",
                resolved,
                resolved_set_id,
                resolved_window,
                is_uuid,
                set_resolve_ms,
                snapshot_ms,
                round((time.perf_counter() - started) * 1000, 3),
            )
            return payload
    except Exception as exc:
        elapsed_ms = round((time.perf_counter() - started) * 1000, 3)
        logger.warning(
            "[pokemon-snapshot] market dashboard snapshot read failed set_id=%s resolved_set_id=%s window=%s "
            "snapshot_read_status=failed fallback_used=true uuid_fast_path=%s exc_type=%s exc=%s elapsed_ms=%s",
            resolved,
            resolved_set_id,
            resolved_window,
            is_uuid,
            type(exc).__name__,
            exc,
            elapsed_ms,
            exc_info=True,
        )
        if is_uuid:
            raise PokemonSetMarketError(500, "Failed to read Pokemon market dashboard snapshot", "POKEMON_SET_MARKET_SNAPSHOT_FAILED")

    # UUID fast path: snapshot miss → return fast empty, no live assembly
    if is_uuid:
        elapsed_ms = round((time.perf_counter() - started) * 1000, 3)
        logger.warning(
            "[pokemon-snapshot] market dashboard missing snapshot uuid fast path returning empty set_id=%s window=%s elapsed_ms=%s",
            resolved_set_id,
            resolved_window,
            elapsed_ms,
        )
        return _empty_market_dashboard_payload(
            set_row={"id": resolved_set_id},
            window=resolved_window,
            warnings=["Pokemon market dashboard snapshot is missing; served empty fallback payload."],
            fallback_source="empty_fallback_missing_pokemon_set_market_dashboard_snapshot_latest",
        )

    # Non-UUID path: live assembly fallback (set_row is already resolved above)
    logger.warning("[pokemon-snapshot] missing market dashboard snapshot; falling back to live market assembly set_id=%s", resolved_set_id)
    histories_by_scope: Dict[str, List[Dict[str, Any]]] = {}
    warnings: List[str] = ["Pokemon market dashboard snapshot is missing; served live fallback data."]
    for scope in SET_VALUE_SCOPES:
        try:
            value_payload = get_pokemon_set_value_history_payload(resolved_set_id, days=resolved_days, value_scope=scope)
            histories_by_scope[scope] = list(value_payload.get("history") or [])
            warnings.extend((value_payload.get("meta") or {}).get("warnings") or [])
        except Exception as exc:
            histories_by_scope[scope] = []
            warnings.append(f"Pokemon set value history is unavailable for {scope}; served remaining market data.")
            logger.warning(
                "[pokemon-snapshot] live market dashboard value history fallback failed set_id=%s resolved_set_id=%s window=%s scope=%s error=%s",
                resolved,
                resolved_set_id,
                resolved_window,
                scope,
                exc,
                exc_info=True,
            )
    try:
        top_payload = get_pokemon_set_top_market_cards_payload(resolved_set_id, limit=10, days=resolved_days)
        warnings.extend((top_payload.get("meta") or {}).get("warnings") or [])
    except Exception as exc:
        assert set_row is not None
        top_payload = {
            "set": {
                "id": _to_optional_str(set_row.get("id")),
                "name": _to_optional_str(set_row.get("name")),
                "slug": _to_optional_str(set_row.get("canonical_key")),
                "pokemon_api_set_id": _to_optional_str(set_row.get("pokemon_api_set_id")),
            },
            "cards": [],
            "meta": {},
        }
        warnings.append("Pokemon top chase card market data is unavailable; served set value history only.")
        logger.warning(
            "[pokemon-snapshot] live market dashboard top cards fallback failed set_id=%s resolved_set_id=%s window=%s error=%s",
            resolved,
            resolved_set_id,
            resolved_window,
            exc,
            exc_info=True,
        )

    latest_market_date = None
    for history in histories_by_scope.values():
        for point in history:
            point_date = _parse_date_key(point.get("date"))
            if point_date and (latest_market_date is None or point_date > latest_market_date):
                latest_market_date = point_date

    perf_history: List[Dict[str, Any]] = []
    try:
        perf_history = _load_simulation_performance_history_live(resolved_set_id)
    except Exception as exc:
        warnings.append("Simulation performance history is unavailable for this set.")
        logger.warning(
            "[pokemon-snapshot] live fallback simulation performance history failed set_id=%s error=%s",
            resolved_set_id,
            exc,
            exc_info=True,
        )
    if not perf_history:
        warnings.append("Simulation performance history is unavailable for this set.")

    has_set_value_history = any(len(history) > 0 for history in histories_by_scope.values())
    top_chase_cards = top_payload.get("cards") or []
    assert set_row is not None
    if not has_set_value_history and not top_chase_cards:
        return _empty_market_dashboard_payload(
            set_row=set_row,
            window=resolved_window,
            warnings=[
                *warnings,
                "Pokemon market dashboard data is unavailable; served an empty fallback payload.",
            ],
            fallback_source="empty_fallback_missing_pokemon_set_market_dashboard_snapshot_latest",
        )

    available_scopes = []
    for scope in SET_VALUE_SCOPES:
        scope_dates = []
        for point in histories_by_scope.get(scope, []):
            point_date = _parse_date_key(point.get("date"))
            if point_date:
                scope_dates.append(point_date)
        available_scopes.append(
            {
                "key": scope,
                "label": SET_VALUE_SCOPE_LABELS.get(scope, scope),
                "latestDate": max(scope_dates) if scope_dates else None,
            }
        )
    return {
        "set": top_payload.get("set"),
        "window": resolved_window,
        "window_key": resolved_window,
        "setValueHistoriesByScope": histories_by_scope,
        "set_value_histories_by_scope": histories_by_scope,
        "performanceVsCostHistory": perf_history,
        "performance_vs_cost_history": perf_history,
        "topChaseCards": top_chase_cards,
        "top_chase_cards": top_chase_cards,
        "availableScopes": available_scopes,
        "available_scopes": available_scopes,
        "latestMarketDate": latest_market_date,
        "latest_market_date": latest_market_date,
        "meta": {
            "warnings": warnings,
            "snapshot": {
                "source": "live_fallback_missing_pokemon_set_market_dashboard_snapshot_latest",
                "updatedAt": datetime.now(timezone.utc).isoformat(),
                "isStaleFallback": False,
            },
        },
    }


_OVERVIEW_SNAPSHOT_COLUMNS = (
    "set_id,window_key,set_value_histories_json,performance_vs_cost_history_json,"
    "available_scopes_json,latest_market_date,updated_at"
)


def _build_overview_payload_from_row(row: Dict[str, Any], *, set_row: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """Build the slim Overview-tab payload (camelCase only) from a
    pokemon_set_market_dashboard_snapshot_latest row.

    Reads only the split JSON columns — payload_json is never selected or read
    (the large monolithic column would dominate the query cost; current
    snapshot rows always populate the split columns). A missing split column
    yields an empty structure, and topChaseCards/topChaseCardHistories/
    marketMovers/marketMoversByWindow are never built here at all.
    """
    resolved_set_id = _to_optional_str(row.get("set_id"))
    identity_row = set_row or {"id": resolved_set_id}
    set_identity = {
        "id": _to_optional_str(identity_row.get("id")) or resolved_set_id,
        "name": _to_optional_str(identity_row.get("name")),
        "slug": _to_optional_str(identity_row.get("canonical_key")),
        "pokemonApiSetId": _to_optional_str(identity_row.get("pokemon_api_set_id")),
    }

    histories_by_scope = row.get("set_value_histories_json")
    if not isinstance(histories_by_scope, dict):
        histories_by_scope = {}

    performance_vs_cost_history = row.get("performance_vs_cost_history_json")
    if not isinstance(performance_vs_cost_history, list):
        performance_vs_cost_history = []

    available_scopes = row.get("available_scopes_json")
    if not isinstance(available_scopes, list):
        available_scopes = []

    return {
        "set": set_identity,
        "window": _to_optional_str(row.get("window_key")),
        "setValueHistoriesByScope": histories_by_scope,
        "performanceVsCostHistory": performance_vs_cost_history,
        "availableScopes": available_scopes,
        "latestMarketDate": _parse_date_key(row.get("latest_market_date")),
        "meta": {"warnings": []},
    }


def _empty_overview_payload(
    *,
    set_row: Dict[str, Any],
    window: str,
    warnings: Optional[List[str]] = None,
    fallback_source: str,
) -> Dict[str, Any]:
    resolved_window = _normalize_market_dashboard_window_key(window)
    histories_by_scope: Dict[str, List[Dict[str, Any]]] = {scope: [] for scope in SET_VALUE_SCOPES}
    available_scopes: List[Dict[str, Any]] = [
        {"key": scope, "label": SET_VALUE_SCOPE_LABELS.get(scope, scope), "latestDate": None}
        for scope in SET_VALUE_SCOPES
    ]
    return {
        "set": {
            "id": _to_optional_str(set_row.get("id")),
            "name": _to_optional_str(set_row.get("name")),
            "slug": _to_optional_str(set_row.get("canonical_key")),
            "pokemonApiSetId": _to_optional_str(set_row.get("pokemon_api_set_id")),
        },
        "window": resolved_window,
        "setValueHistoriesByScope": histories_by_scope,
        "performanceVsCostHistory": [],
        "availableScopes": available_scopes,
        "latestMarketDate": None,
        "meta": {
            "warnings": list(warnings or []),
            "snapshot": {
                "source": fallback_source,
                "updatedAt": datetime.now(timezone.utc).isoformat(),
                "isStaleFallback": False,
            },
        },
    }


def get_pokemon_set_overview_snapshot_payload(
    set_id: str,
    window: str = DEFAULT_DASHBOARD_WINDOW,
) -> Dict[str, Any]:
    """Return the slim Overview-tab snapshot (Set Value Trend + Performance vs
    Cost + scopes/latestMarketDate) for a Pokemon set.

    Reads pokemon_set_market_dashboard_snapshot_latest, selecting only the
    split set_value_histories_json / performance_vs_cost_history_json /
    available_scopes_json / latest_market_date columns (never payload_json).
    Never includes topChaseCards, topChaseCardHistories, marketMovers, or
    marketMoversByWindow — see get_pokemon_set_market_dashboard_snapshot_payload
    for those. Public contract is camelCase only.
    """
    started = time.perf_counter()
    resolved = _to_optional_str(set_id)
    if not resolved:
        raise PokemonSetMarketError(400, "set_id is required", "POKEMON_SET_MARKET_ID_REQUIRED")

    is_uuid = _looks_like_uuid(resolved)
    resolved_window = _normalize_market_dashboard_window_key(window)

    set_row: Optional[Dict[str, Any]] = None
    if is_uuid:
        resolved_set_id = resolved
    else:
        set_row = resolve_pokemon_set_identifier(resolved, client=public_read_client)
        resolved_set_id = str(set_row["id"])

    t_query = time.perf_counter()
    row: Optional[Dict[str, Any]] = None
    try:
        result = (
            public_read_client.table("pokemon_set_market_dashboard_snapshot_latest")
            .select(_OVERVIEW_SNAPSHOT_COLUMNS)
            .eq("set_id", resolved_set_id)
            .eq("window_key", resolved_window)
            .limit(1)
            .execute()
        )
        row = _first_row(result)
    except Exception as exc:
        logger.warning(
            "[pokemon-snapshot] overview snapshot read failed set_id=%s window=%s exc=%s",
            resolved_set_id,
            resolved_window,
            exc,
            exc_info=True,
        )
        row = None
    query_ms = round((time.perf_counter() - t_query) * 1000, 3)

    if not row:
        elapsed_ms = round((time.perf_counter() - started) * 1000, 3)
        logger.info(
            "[pokemon-snapshot] overview snapshot missing set_id=%s window=%s elapsed_ms=%s",
            resolved_set_id,
            resolved_window,
            elapsed_ms,
        )
        return _empty_overview_payload(
            set_row=set_row or {"id": resolved_set_id},
            window=resolved_window,
            warnings=["Pokemon overview snapshot is missing; served empty fallback payload."],
            fallback_source="empty_fallback_missing_pokemon_set_market_dashboard_snapshot_latest",
        )

    payload = _build_overview_payload_from_row(row, set_row=set_row)
    meta = dict(payload.get("meta") or {})
    meta["snapshot"] = {
        "source": "pokemon_set_market_dashboard_snapshot_latest",
        "window": row.get("window_key"),
        "updatedAt": _to_optional_str(row.get("updated_at")),
        "latestMarketDate": _parse_date_key(row.get("latest_market_date")),
        "isStaleFallback": True,
    }
    meta["timings"] = {
        "snapshotQueryMs": query_ms,
        "snapshotReadMs": round((time.perf_counter() - started) * 1000, 3),
    }
    payload["meta"] = meta
    logger.info(
        "[pokemon-snapshot] overview snapshot read complete set_id=%s window=%s query_ms=%s total_ms=%s",
        resolved_set_id,
        resolved_window,
        query_ms,
        meta["timings"]["snapshotReadMs"],
    )
    return payload


_TOP_CHASE_SNAPSHOT_COLUMNS = (
    "set_id,window_key,top_chase_cards_json,top_chase_card_histories_json,"
    "latest_market_date,updated_at"
)


def _top_chase_row_latest_date(row: Optional[Dict[str, Any]]) -> Optional[str]:
    if not isinstance(row, dict):
        return None
    return _parse_date_key(row.get("latest_market_date"))


def _pick_fresher_top_chase_row(
    requested_row: Optional[Dict[str, Any]],
    canonical_row: Optional[Dict[str, Any]],
) -> tuple[Optional[Dict[str, Any]], bool, Optional[str]]:
    """Choose which stored dashboard row the slim /market/top-chase endpoint
    serves, returning (chosen_row, used_fallback_window, fallback_reason).

    Prefer the requested-window row, but fall back to the canonical 365d row
    when the requested row is missing OR staler than it (a strictly older
    latest_market_date, or none at all). ISO date keys compare correctly as
    strings. This keeps Top Chase reading the freshest stored data — the same
    fresh 365d row Market Movers reads — so a lagging per-window rebuild can
    never leave Top Chase serving a stale price/history the mover view has
    already moved past.
    """
    if requested_row is None:
        if canonical_row is None:
            return None, False, None
        return canonical_row, True, "missing_requested_window_row"
    if canonical_row is None:
        return requested_row, False, None
    requested_date = _top_chase_row_latest_date(requested_row)
    canonical_date = _top_chase_row_latest_date(canonical_row)
    if canonical_date and (requested_date is None or canonical_date > requested_date):
        return canonical_row, True, "requested_window_row_stale"
    return requested_row, False, None


def _slice_top_chase_history(history: Any, *, days: int) -> List[Dict[str, Any]]:
    if not isinstance(history, list) or not history:
        return []
    dated_points: List[tuple[str, Dict[str, Any]]] = []
    for point in history:
        if not isinstance(point, dict):
            continue
        date_key = _parse_date_key(point.get("date"))
        if date_key:
            dated_points.append((date_key, point))
    if not dated_points:
        return []
    dated_points.sort(key=lambda entry: entry[0])
    end_date_key = dated_points[-1][0]
    try:
        end_date = date.fromisoformat(end_date_key)
    except ValueError:
        return [point for _, point in dated_points[-days:]]
    start_date = end_date - timedelta(days=max(days - 1, 0))
    return [
        point
        for date_key, point in dated_points
        if date.fromisoformat(date_key) >= start_date
    ]


def _top_chase_card_history_keys(card: Dict[str, Any]) -> List[str]:
    return [
        key
        for key in (
            _to_optional_str(card.get("cardVariantId")),
            _to_optional_str(card.get("card_variant_id")),
            _to_optional_str(card.get("cardId")),
            _to_optional_str(card.get("card_id")),
            _to_optional_str(card.get("id")),
        )
        if key
    ]


# Some market-dashboard-built rows (notably 365d rows — see Phase 5E) embed a
# full per-card price history directly on each top_chase_cards_json entry,
# duplicating the same days already served by the separate, already-windowed
# topChaseCardHistories dict below. For a set with 10 chase cards this alone
# can push a single 30-day request past 700KB. The frontend client
# (pokemonSetMarketClient.js's chooseTopChaseHistory) already falls back to
# topChaseCardHistories whenever a card's embedded history is empty, so
# dropping these keys here changes only response size, never which
# history/ranking data ultimately reaches the UI.
_TOP_CHASE_CARD_REDUNDANT_HISTORY_KEYS = (
    "priceHistory",
    "price_history",
    "historyDiagnostics",
    "history_diagnostics",
)


def _strip_redundant_top_chase_card_history_fields(card: Dict[str, Any]) -> Dict[str, Any]:
    if not isinstance(card, dict):
        return card
    return {key: value for key, value in card.items() if key not in _TOP_CHASE_CARD_REDUNDANT_HISTORY_KEYS}


def _empty_top_chase_payload(
    *,
    set_row: Dict[str, Any],
    window: str,
    warnings: Optional[List[str]] = None,
    fallback_source: str,
) -> Dict[str, Any]:
    resolved_window = _normalize_market_dashboard_window_key(window, default=DEFAULT_TOP_CHASE_DASHBOARD_WINDOW)
    return {
        "set": {
            "id": _to_optional_str(set_row.get("id")),
            "name": _to_optional_str(set_row.get("name")),
            "slug": _to_optional_str(set_row.get("canonical_key")),
            "pokemonApiSetId": _to_optional_str(set_row.get("pokemon_api_set_id")),
        },
        "window": resolved_window,
        "topChaseCards": [],
        "topChaseCardHistories": {},
        "latestMarketDate": None,
        "meta": {
            "warnings": list(warnings or []),
            "snapshot": {
                "source": fallback_source,
                "updatedAt": datetime.now(timezone.utc).isoformat(),
                "isStaleFallback": False,
            },
        },
    }


def get_pokemon_set_top_chase_snapshot_payload(
    set_id: str,
    window: str = DEFAULT_TOP_CHASE_DASHBOARD_WINDOW,
    limit: Any = None,
) -> Dict[str, Any]:
    """Return the slim Top Chase Cards snapshot (camelCase only) for a Pokemon set.

    Reads only set_id, window_key, top_chase_cards_json,
    top_chase_card_histories_json, latest_market_date, and updated_at from
    pokemon_set_market_dashboard_snapshot_latest — never the full dashboard
    payload (get_pokemon_set_market_dashboard_snapshot_payload), and never
    setValueHistoriesByScope/performanceVsCostHistory/availableScopes/
    marketMovers/marketMoversByWindow. topChaseCardHistories is sliced down to
    the requested window (default 30 days) instead of the full 365-day source
    history, keeping the response well under the 250KB budget.

    Phase 5D found the market dashboard snapshot builder has, for most sets,
    only ever been run with the 365d window — top_chase_cards_json/
    top_chase_card_histories_json are already fully populated there, just
    filed under a window_key this endpoint's default ("30d") never matches.
    Phase 5E: if the requested-window row is missing, fall back to reading
    the 365d row (still a single extra indexed read, never a rebuild/write)
    and serve its already-stored cards/histories unchanged.

    Freshness fix (Ascended Heroes): the fallback also triggers when the
    requested-window row EXISTS but is STALE — its latest_market_date is older
    than the canonical 365d row's. A lagging per-window rebuild can leave, say,
    the 30d row frozen weeks behind (stale card price + carried-forward/absent
    history) while the 365d row is current. Market Movers already reads the
    fresh 365d row, so serving the stale 30d row here made Top Chase contradict
    Market Movers for the same card. Serving whichever row is fresher keeps the
    two in agreement and never lets stale stored data override current data.

    The response still reports the requested window; meta.snapshot records
    whether a fallback row was used and why (missing vs stale) so callers/
    diagnostics can tell the cases apart.
    """
    started = time.perf_counter()
    resolved = _to_optional_str(set_id)
    if not resolved:
        raise PokemonSetMarketError(400, "set_id is required", "POKEMON_SET_MARKET_ID_REQUIRED")

    is_uuid = _looks_like_uuid(resolved)
    resolved_window = _normalize_market_dashboard_window_key(window, default=DEFAULT_TOP_CHASE_DASHBOARD_WINDOW)
    window_days = _market_dashboard_window_days(resolved_window)
    limit_value = _sanitize_top_limit(limit)

    set_row: Optional[Dict[str, Any]] = None
    if is_uuid:
        resolved_set_id = resolved
    else:
        set_row = resolve_pokemon_set_identifier(resolved, client=public_read_client)
        resolved_set_id = str(set_row["id"])

    def _read_top_chase_row(window_key: str) -> Optional[Dict[str, Any]]:
        result = (
            public_read_client.table("pokemon_set_market_dashboard_snapshot_latest")
            .select(_TOP_CHASE_SNAPSHOT_COLUMNS)
            .eq("set_id", resolved_set_id)
            .eq("window_key", window_key)
            .limit(1)
            .execute()
        )
        return _first_row(result)

    t_query = time.perf_counter()
    row: Optional[Dict[str, Any]] = None
    used_fallback_window = False
    fallback_reason: Optional[str] = None
    try:
        requested_row = _read_top_chase_row(resolved_window)
        if resolved_window == DEFAULT_DASHBOARD_WINDOW:
            # The requested window IS the canonical 365d row — there is nothing
            # fresher to compare it against, so serve it directly.
            row = requested_row
        else:
            # Read the canonical 365d row too and serve whichever is fresher —
            # this is what stops a stale-but-present requested-window row (the
            # Ascended Heroes 30d case) from overriding fresher 365d data. Both
            # reads are single indexed lookups on (set_id, window_key); no
            # per-card raw-observation scan is added by this comparison.
            canonical_row = _read_top_chase_row(DEFAULT_DASHBOARD_WINDOW)
            row, used_fallback_window, fallback_reason = _pick_fresher_top_chase_row(
                requested_row, canonical_row
            )
    except Exception as exc:
        logger.warning(
            "[pokemon-snapshot] top chase snapshot read failed set_id=%s window=%s exc=%s",
            resolved_set_id,
            resolved_window,
            exc,
            exc_info=True,
        )
        row = None
        used_fallback_window = False
        fallback_reason = None
    query_ms = round((time.perf_counter() - t_query) * 1000, 3)

    if not row:
        logger.info(
            "[pokemon-snapshot] top chase snapshot missing set_id=%s window=%s elapsed_ms=%s",
            resolved_set_id,
            resolved_window,
            round((time.perf_counter() - started) * 1000, 3),
        )
        return _empty_top_chase_payload(
            set_row=set_row or {"id": resolved_set_id},
            window=resolved_window,
            warnings=["Pokemon top chase snapshot is missing; served empty fallback payload."],
            fallback_source="empty_fallback_missing_pokemon_set_market_dashboard_snapshot_latest",
        )

    if used_fallback_window:
        logger.info(
            "[pokemon-snapshot] top chase snapshot used fallback window set_id=%s requested_window=%s source_window=%s reason=%s",
            resolved_set_id,
            resolved_window,
            row.get("window_key"),
            fallback_reason,
        )

    resolved_row_set_id = _to_optional_str(row.get("set_id")) or resolved_set_id
    identity_row = set_row or {"id": resolved_row_set_id}
    set_identity = {
        "id": _to_optional_str(identity_row.get("id")) or resolved_row_set_id,
        "name": _to_optional_str(identity_row.get("name")),
        "slug": _to_optional_str(identity_row.get("canonical_key")),
        "pokemonApiSetId": _to_optional_str(identity_row.get("pokemon_api_set_id")),
    }

    top_chase_cards = [
        _strip_redundant_top_chase_card_history_fields(card)
        for card in list(row.get("top_chase_cards_json") or [])[:limit_value]
    ]
    raw_histories = row.get("top_chase_card_histories_json")
    histories_by_key = raw_histories if isinstance(raw_histories, dict) else {}
    kept_keys = {key for card in top_chase_cards for key in _top_chase_card_history_keys(card)}
    top_chase_card_histories = {
        key: _slice_top_chase_history(history, days=window_days)
        for key, history in histories_by_key.items()
        if key in kept_keys
    }

    # Phase 5F (Gate 2): a small number of sets (e.g. Ascended Heroes) have a
    # dashboard row — 30d or 365d — whose top_chase_cards_json is populated
    # but whose top_chase_card_histories_json is empty for every one of those
    # cards (distinct from the Phase 5E whole-row-missing case). When that
    # happens, fall back to the same scoped card_variant_price_observations
    # read the full market-dashboard payload already uses
    # (_load_top_chase_observation_histories), limited to this row's own
    # variant IDs — never a broad/unscoped observation scan, never a write.
    hydrated_from_observations = False
    if top_chase_cards and not any(len(history) > 0 for history in top_chase_card_histories.values()):
        observation_variant_ids = _top_chase_variant_ids(top_chase_cards)
        if observation_variant_ids:
            observation_histories = _load_top_chase_observation_histories(
                set_id=resolved_set_id,
                cards=top_chase_cards,
                variant_ids=observation_variant_ids,
                latest_date_key=_parse_date_key(row.get("latest_market_date")),
                window_days=TOP_CHASE_HISTORY_SOURCE_WINDOW_DAYS,
            )
            sliced_observation_histories = {
                key: _slice_top_chase_history(history, days=window_days)
                for key, history in observation_histories.items()
                if key in kept_keys
            }
            if any(len(history) > 0 for history in sliced_observation_histories.values()):
                top_chase_card_histories = sliced_observation_histories
                hydrated_from_observations = True

    # The card price column reads top_chase_cards_json's own marketPrice/
    # currentPrice — the price the snapshot builder computed for the served row.
    # We deliberately do NOT overwrite it with the latest history point: history
    # can be stale/carried-forward, and dragging the price onto it makes the
    # price column MORE stale, not less. Freshness is handled upstream by serving
    # the fresher row (_pick_fresher_top_chase_row), so the served row's card
    # price and its history already reflect the same current market truth.
    top_chase_history_latest_observed_date = max(
        (
            date_key
            for history in top_chase_card_histories.values()
            if isinstance(history, list)
            for point in history
            for date_key in [_parse_date_key(point.get("date"))]
            if date_key
        ),
        default=None,
    )
    latest_market_date = _parse_date_key(row.get("latest_market_date"))
    histories_stale = bool(
        latest_market_date
        and top_chase_history_latest_observed_date != latest_market_date
    )

    # When the persisted history reaches the declared market date, make the
    # displayed current price use that same terminal point. This is safe for a
    # carried point because its sourceDate remains distinct in the history.
    if not histories_stale and latest_market_date:
        aligned_cards: List[Dict[str, Any]] = []
        for card in top_chase_cards:
            history = next(
                (top_chase_card_histories.get(key) for key in _top_chase_card_history_keys(card) if top_chase_card_histories.get(key)),
                None,
            )
            terminal = history[-1] if isinstance(history, list) and history else None
            terminal_price = _to_optional_float((terminal or {}).get("marketPrice", (terminal or {}).get("market_price")))
            aligned = dict(card)
            if terminal_price is not None and _parse_date_key((terminal or {}).get("date")) == latest_market_date:
                aligned["marketPrice"] = terminal_price
                aligned["currentPrice"] = terminal_price
                aligned["priceUpdatedAt"] = latest_market_date
                aligned["historyEndDate"] = latest_market_date
                aligned["priceSourceDate"] = _parse_date_key((terminal or {}).get("sourceDate") or (terminal or {}).get("source_date"))
            aligned_cards.append(aligned)
        top_chase_cards = aligned_cards

    history_point_counts = [len(history) for history in top_chase_card_histories.values()]

    timings = {
        "snapshotQueryMs": query_ms,
        "snapshotReadMs": round((time.perf_counter() - started) * 1000, 3),
    }
    warnings: List[str] = []
    if used_fallback_window:
        stale_or_missing = "stale" if fallback_reason == "requested_window_row_stale" else "missing"
        warnings.append(
            f"Top chase snapshot for window {resolved_window} is {stale_or_missing}; served the "
            f"fresher {DEFAULT_DASHBOARD_WINDOW} window's stored cards/histories instead."
        )
    if top_chase_cards and not any(count > 0 for count in history_point_counts):
        warnings.append(
            "Top chase card price histories are missing in the stored snapshot and no raw price "
            "observations were found for these cards; served cards without price history."
        )
    elif histories_stale:
        warnings.append(
            f"Top chase history is stale: latestMarketDate={latest_market_date}, "
            f"historyEndDate={top_chase_history_latest_observed_date}."
        )
    payload = {
        "set": set_identity,
        # Always echo the requested window back — the caller asked for 30D and
        # should see 30D, regardless of which stored window row served it.
        "window": resolved_window,
        "topChaseCards": top_chase_cards,
        "topChaseCardHistories": top_chase_card_histories,
        "latestMarketDate": latest_market_date,
        "meta": {
            "limit": limit_value,
            "warnings": warnings,
            # The card price column comes from the served row's own stored
            # top_chase_cards_json (never dragged onto the history) — the served
            # row is the freshest of the requested/canonical rows, so priceBasis
            # + priceSourceWindowKey together say exactly which stored row's
            # current price the caller is seeing.
            "priceBasis": "pokemon_set_market_dashboard_snapshot_latest.top_chase_cards_json",
            "priceSourceWindowKey": _to_optional_str(row.get("window_key")) or resolved_window,
            "topChaseHistorySource": (
                TOP_CHASE_HISTORY_SOURCE
                if hydrated_from_observations
                else "pokemon_set_market_dashboard_snapshot_latest.top_chase_card_histories_json"
            ),
            "topChaseHistoryHydratedFromObservations": hydrated_from_observations,
            "topChaseHistorySourceLatestObservedDate": top_chase_history_latest_observed_date,
            "historyEndDate": top_chase_history_latest_observed_date,
            "historiesStale": histories_stale,
            "topChaseHistoryMinPoints": min(history_point_counts) if history_point_counts else 0,
            "topChaseHistoryMaxPoints": max(history_point_counts) if history_point_counts else 0,
            "snapshot": {
                "source": "pokemon_set_market_dashboard_snapshot_latest",
                "window": row.get("window_key"),
                "requestedWindow": resolved_window,
                "sourceWindow": _to_optional_str(row.get("window_key")) or resolved_window,
                "usedFallbackWindow": used_fallback_window,
                **({"fallbackReason": fallback_reason} if used_fallback_window and fallback_reason else {}),
                "updatedAt": _to_optional_str(row.get("updated_at")),
                "latestMarketDate": latest_market_date,
                "historyEndDate": top_chase_history_latest_observed_date,
                "isStaleFallback": histories_stale,
            },
            "timings": timings,
        },
    }
    logger.info(
        "[pokemon-snapshot] top chase snapshot read complete set_id=%s window=%s query_ms=%s total_ms=%s",
        resolved_set_id,
        resolved_window,
        query_ms,
        timings["snapshotReadMs"],
    )
    return payload


def _empty_market_movers_payload(
    *,
    set_row: Dict[str, Any],
    window: str,
    window_days: int,
    warnings: Optional[List[str]] = None,
    fallback_source: str,
) -> Dict[str, Any]:
    return {
        "set": {
            "id": _to_optional_str(set_row.get("id")),
            "name": _to_optional_str(set_row.get("name")),
            "slug": _to_optional_str(set_row.get("canonical_key")),
            "pokemon_api_set_id": _to_optional_str(set_row.get("pokemon_api_set_id")),
        },
        "window": window,
        "windowDays": window_days,
        "marketMovers": {
            "window": window,
            "windowDays": window_days,
            "heatingUp": [],
            "coolingOff": [],
        },
        "meta": {
            "limit": DEFAULT_CARD_MOVERS_LIMIT,
            "warnings": list(warnings or []),
            "snapshot": {
                "source": fallback_source,
                "sourceField": None,
                "window": window,
                "usedReadModel": False,
                "updatedAt": datetime.now(timezone.utc).isoformat(),
                "isStaleFallback": False,
            },
        },
    }


def get_pokemon_set_market_movers_snapshot_payload(
    set_id: str,
    window: str = DEFAULT_MARKET_MOVERS_WINDOW,
    limit: Any = None,
) -> Dict[str, Any]:
    """Return the slim Market Movers snapshot (camelCase only) for a Pokemon set.

    Reads only set_id, window_key, latest_market_date, updated_at, and the
    heatingUp/coolingOff sub-arrays of the single requested mover window out
    of payload_json->marketMoversByWindow (via two PostgREST JSON-path
    selects), so neither the ~3MB monolithic payload_json blob nor the
    unused "all" movements list (Phase 5.8 Gate 4: never read by
    MarketMoversModule/hasMarketMoverRows, only ever passed through as a
    default-empty shape field) is pulled over the wire — only the exact
    heatingUp/coolingOff cards this endpoint serves. The stored snapshot
    payload itself is untouched; this only narrows what this one reader
    selects out of it. The full /market/dashboard contract still serves
    "all" unchanged (get_pokemon_set_market_dashboard_snapshot_payload reads
    payload_json directly, a separate code path).

    marketMoversByWindow is precomputed by
    scripts/pokemon_snapshot_builders.py (build_market_dashboard_snapshot_rows)
    from the exact same build_pokemon_set_card_movement_payload used by the
    live /market/movers read path — same scores, labels, thresholds, order —
    just computed once at snapshot-build time instead of on every request.
    Never falls back to that live aggregation: a missing snapshot serves a
    safe empty payload, matching the sibling slim endpoints
    (get_pokemon_set_top_chase_snapshot_payload,
    get_pokemon_set_overview_snapshot_payload) instead of recomputing.

    The dashboard snapshot's own window_key column (e.g. "365d"/"30d")
    identifies which dashboard build variant a row is, independent of the
    1D/7D/30D mover window requested here — every row's
    marketMoversByWindow already contains all three mover windows together.
    The "365d" row is the one the builder keeps fully populated in practice,
    so it's tried first; "30d" is a fallback for sets that only have an
    older/partial row under that key.
    """
    started = time.perf_counter()
    resolved = _to_optional_str(set_id)
    if not resolved:
        raise PokemonSetMarketError(400, "set_id is required", "POKEMON_SET_MARKET_ID_REQUIRED")

    is_uuid = _looks_like_uuid(resolved)
    resolved_window = _sanitize_market_movers_window_key(window)
    window_days = _MARKET_MOVERS_WINDOW_DAYS_BY_KEY[resolved_window]
    limit_value = _sanitize_market_movers_limit(limit)

    set_row: Optional[Dict[str, Any]] = None
    if is_uuid:
        resolved_set_id = resolved
    else:
        set_row = resolve_pokemon_set_identifier(resolved, client=public_read_client)
        resolved_set_id = str(set_row["id"])

    select_fields = (
        f"set_id,window_key,latest_market_date,updated_at,"
        f"heating:payload_json->marketMoversByWindow->{resolved_window}->heatingUp,"
        f"cooling:payload_json->marketMoversByWindow->{resolved_window}->coolingOff"
    )

    def _read_movers_row(window_key: str) -> Optional[Dict[str, Any]]:
        result = (
            public_read_client.table("pokemon_set_market_dashboard_snapshot_latest")
            .select(select_fields)
            .eq("set_id", resolved_set_id)
            .eq("window_key", window_key)
            .limit(1)
            .execute()
        )
        row = _first_row(result)
        # A row whose marketMoversByWindow never had this window at all
        # resolves both paths to SQL NULL (None here). A row with a
        # legitimately empty side (e.g. no cards met the heating-up
        # guardrails this window) still resolves that side to `[]`, not
        # None — so either key being present is enough to call this "found".
        if row and (row.get("heating") is not None or row.get("cooling") is not None):
            return row
        return None

    t_query = time.perf_counter()
    row: Optional[Dict[str, Any]] = None
    used_fallback_window = False
    try:
        row = _read_movers_row(DEFAULT_DASHBOARD_WINDOW)
        if not row:
            row = _read_movers_row(DEFAULT_TOP_CHASE_DASHBOARD_WINDOW)
            if row:
                used_fallback_window = True
    except Exception as exc:
        logger.warning(
            "[pokemon-snapshot] market movers snapshot read failed set_id=%s window=%s exc=%s",
            resolved_set_id,
            resolved_window,
            exc,
            exc_info=True,
        )
        row = None
    query_ms = round((time.perf_counter() - t_query) * 1000, 3)

    if not row:
        logger.info(
            "[pokemon-snapshot] market movers snapshot missing set_id=%s window=%s elapsed_ms=%s",
            resolved_set_id,
            resolved_window,
            round((time.perf_counter() - started) * 1000, 3),
        )
        return _empty_market_movers_payload(
            set_row=set_row or {"id": resolved_set_id},
            window=resolved_window,
            window_days=window_days,
            warnings=["Pokemon market movers snapshot is missing; served empty fallback payload."],
            fallback_source="empty_fallback_missing_pokemon_set_market_dashboard_snapshot_latest",
        )

    if used_fallback_window:
        logger.info(
            "[pokemon-snapshot] market movers snapshot used fallback row window_key set_id=%s mover_window=%s row_window_key=%s",
            resolved_set_id,
            resolved_window,
            row.get("window_key"),
        )

    resolved_row_set_id = _to_optional_str(row.get("set_id")) or resolved_set_id
    identity_row = set_row or {"id": resolved_row_set_id}
    set_identity = {
        "id": _to_optional_str(identity_row.get("id")) or resolved_row_set_id,
        "name": _to_optional_str(identity_row.get("name")),
        "slug": _to_optional_str(identity_row.get("canonical_key")),
        "pokemon_api_set_id": _to_optional_str(identity_row.get("pokemon_api_set_id")),
    }

    heating_up = row.get("heating") if isinstance(row.get("heating"), list) else []
    cooling_off = row.get("cooling") if isinstance(row.get("cooling"), list) else []

    timings = {
        "snapshotQueryMs": query_ms,
        "snapshotReadMs": round((time.perf_counter() - started) * 1000, 3),
    }
    warnings: List[str] = []
    if used_fallback_window:
        warnings.append(
            f"Market movers snapshot row for window_key {DEFAULT_DASHBOARD_WINDOW} is missing; served the "
            f"{DEFAULT_TOP_CHASE_DASHBOARD_WINDOW} row's stored movers instead."
        )

    payload = {
        "set": set_identity,
        "window": resolved_window,
        "windowDays": window_days,
        "marketMovers": {
            "window": resolved_window,
            "windowDays": window_days,
            "heatingUp": heating_up[:limit_value],
            "coolingOff": cooling_off[:limit_value],
        },
        "meta": {
            "limit": limit_value,
            "warnings": warnings,
            "priceBasis": "pokemon_set_market_dashboard_snapshot_latest.payload_json.marketMoversByWindow",
            "snapshot": {
                "source": "pokemon_set_market_dashboard_snapshot_latest",
                "sourceField": "payload_json.marketMoversByWindow.heatingUp/coolingOff",
                "window": resolved_window,
                "usedReadModel": True,
                "rowWindowKey": row.get("window_key"),
                "usedFallbackWindow": used_fallback_window,
                **({"fallbackReason": "missing_365d_row"} if used_fallback_window else {}),
                "updatedAt": _to_optional_str(row.get("updated_at")),
                "latestMarketDate": _parse_date_key(row.get("latest_market_date")),
                "isStaleFallback": True,
            },
            "timings": timings,
        },
    }
    logger.info(
        "[pokemon-snapshot] market movers snapshot read complete set_id=%s window=%s query_ms=%s total_ms=%s",
        resolved_set_id,
        resolved_window,
        query_ms,
        timings["snapshotReadMs"],
    )
    return payload


def get_pokemon_set_top_market_cards_snapshot_payload(
    set_id: str,
    limit: Any = None,
    days: Any = None,
) -> Dict[str, Any]:
    del days
    set_row = _resolve_set_row(set_id)
    resolved_set_id = str(set_row["id"])
    limit_value = _sanitize_top_limit(limit)
    dashboard = get_pokemon_set_market_dashboard_snapshot_payload(resolved_set_id)
    cards = list(dashboard.get("topChaseCards") or dashboard.get("top_chase_cards") or [])[:limit_value]
    return {
        "set": dashboard.get("set"),
        "cards": cards,
        "meta": {
            **(dashboard.get("meta") or {}),
            "limit": limit_value,
            "priceBasis": "pokemon_set_market_dashboard_snapshot_latest.top_chase_cards_json",
        },
    }


def get_pokemon_set_value_history_snapshot_payload(
    set_id: str,
    days: Any = None,
    value_scope: Any = None,
) -> Dict[str, Any]:
    return get_pokemon_set_value_history_payload(set_id=set_id, days=days, value_scope=value_scope)


_PULL_RATES_SNAPSHOT_COLUMNS = "set_id,payload_json,updated_at"
PULL_RATES_PAYLOAD_BUDGET_BYTES = 150_000


def _empty_pull_rates_payload(
    *,
    set_row: Dict[str, Any],
    warnings: Optional[List[str]] = None,
    fallback_source: str,
) -> Dict[str, Any]:
    return {
        "set": {
            "id": _to_optional_str(set_row.get("id")),
            "name": _to_optional_str(set_row.get("name")),
            "slug": _to_optional_str(set_row.get("canonical_key")),
            "canonicalKey": _to_optional_str(set_row.get("canonical_key")),
        },
        "pullRates": None,
        "packPaths": [],
        "rarityBuckets": [],
        "assumptions": {},
        "sources": [],
        "meta": {
            "source": fallback_source,
            "updatedAt": datetime.now(timezone.utc).isoformat(),
            "warnings": list(warnings or []),
        },
    }


def _pull_rates_payload_size(payload: Dict[str, Any]) -> int:
    return len(json.dumps(payload, default=str).encode("utf-8"))


def _enforce_pull_rates_payload_budget(payload: Dict[str, Any]) -> bool:
    """Progressively trim pullRates group/flat rows until the serialized
    payload fits PULL_RATES_PAYLOAD_BUDGET_BYTES. Pull rate assumptions are a
    small, config-derived table so this should almost never trigger in
    practice — it exists purely as a safety net, not a normal code path.
    """
    pull_rates = payload.get("pullRates")
    if not isinstance(pull_rates, dict):
        return False

    truncated = False
    while _pull_rates_payload_size(payload) > PULL_RATES_PAYLOAD_BUDGET_BYTES:
        trimmed_this_round = False
        groups = pull_rates.get("groups")
        if isinstance(groups, list) and groups:
            largest_group = max(groups, key=lambda group: len(group.get("rows") or []) if isinstance(group, dict) else 0)
            rows = largest_group.get("rows") if isinstance(largest_group, dict) else None
            if isinstance(rows, list) and len(rows) > 1:
                largest_group["rows"] = rows[: max(1, len(rows) // 2)]
                trimmed_this_round = True
                truncated = True
        if not trimmed_this_round:
            flat_rows = pull_rates.get("rows")
            if isinstance(flat_rows, list) and len(flat_rows) > 1:
                pull_rates["rows"] = flat_rows[: max(1, len(flat_rows) // 2)]
                trimmed_this_round = True
                truncated = True
        if not trimmed_this_round:
            break
    return truncated


# Gate 3 (Phase 5G): pokemon_set_page_snapshot_latest has no dedicated split
# column for pull-rate assumptions today — _PULL_RATES_SNAPSHOT_COLUMNS below
# deliberately does not select "pull_rate_assumptions_json" because that
# column does not exist yet; selecting an unknown column raises a hard
# Postgrest error (42703) that would take down this endpoint entirely. This
# resolver still checks for it defensively so the split column is preferred
# the moment both a migration adds it and _PULL_RATES_SNAPSHOT_COLUMNS is
# updated to select it — until then this branch is always a no-op in
# production. The real per-set gap this task found (11/171 sets) is that
# payload_json.pull_rate_assumptions is genuinely null in the persisted
# snapshot row, not that this reader fails to find data that already exists;
# see the Gate 3 report for detail.
def _resolve_pull_rate_assumptions_source(
    row: Dict[str, Any],
) -> "tuple[Optional[Dict[str, Any]], str, bool]":
    """Resolve pull-rate assumptions from whichever already-persisted source
    has them, in priority order: split column, payload_json.pullRateAssumptions
    (camelCase), payload_json.pull_rate_assumptions (snake_case). Never derives
    or recalculates a value — only picks among sources that already exist.
    Returns (assumptions_or_none, source_field, used_payload_json_fallback).
    """
    split_column = row.get("pull_rate_assumptions_json")
    if isinstance(split_column, dict) and split_column:
        return split_column, "pull_rate_assumptions_json", False

    payload_json = row.get("payload_json") if isinstance(row.get("payload_json"), dict) else {}

    camel = payload_json.get("pullRateAssumptions")
    if isinstance(camel, dict) and camel:
        return camel, "payload_json.pullRateAssumptions", True

    snake = payload_json.get("pull_rate_assumptions")
    if isinstance(snake, dict) and snake:
        return snake, "payload_json.pull_rate_assumptions", True

    return None, "none", False


def get_pokemon_set_pull_rates_snapshot_payload(set_id: str) -> Dict[str, Any]:
    """Return the slim Pull Rates-tab snapshot (camelCase only) for a Pokemon set.

    Reads only pokemon_set_page_snapshot_latest.payload_json (there is no
    split column for pull_rate_assumptions) to extract the
    PullRateAssumptionsCard-compatible pull_rate_assumptions/pullRateAssumptions
    block, camelCase-projects it, and discards everything else — never cards,
    marketDashboard/topChase/marketMovers, rankings, percentiles, or top_hits.
    """
    started = time.perf_counter()
    resolved = _to_optional_str(set_id)
    if not resolved:
        raise PokemonSetMarketError(400, "set_id is required", "POKEMON_SET_PULL_RATES_ID_REQUIRED")

    is_uuid = _looks_like_uuid(resolved)
    set_row: Optional[Dict[str, Any]] = None
    if is_uuid:
        resolved_set_id = resolved
    else:
        set_row = _resolve_set_row(resolved)
        resolved_set_id = str(set_row["id"])

    t_query = time.perf_counter()
    row: Optional[Dict[str, Any]] = None
    try:
        result = (
            public_read_client.table("pokemon_set_page_snapshot_latest")
            .select(_PULL_RATES_SNAPSHOT_COLUMNS)
            .eq("set_id", resolved_set_id)
            .limit(1)
            .execute()
        )
        row = _first_row(result)
    except Exception as exc:
        logger.warning(
            "[pokemon-snapshot] pull rates snapshot read failed set_id=%s exc=%s",
            resolved_set_id,
            exc,
            exc_info=True,
        )
        row = None
    query_ms = round((time.perf_counter() - t_query) * 1000, 3)

    if not row or not isinstance(row.get("payload_json"), dict):
        logger.info(
            "[pokemon-snapshot] pull rates snapshot missing set_id=%s elapsed_ms=%s",
            resolved_set_id,
            round((time.perf_counter() - started) * 1000, 3),
        )
        return _empty_pull_rates_payload(
            set_row=set_row or {"id": resolved_set_id},
            warnings=["Pokemon set pull rates snapshot is missing; served empty fallback payload."],
            fallback_source="empty_fallback_missing_pokemon_set_page_snapshot_latest",
        )

    resolved_row_set_id = _to_optional_str(row.get("set_id")) or resolved_set_id
    identity_row = set_row or {"id": resolved_row_set_id}
    set_identity = {
        "id": _to_optional_str(identity_row.get("id")) or resolved_row_set_id,
        "name": _to_optional_str(identity_row.get("name")),
        "slug": _to_optional_str(identity_row.get("canonical_key")),
        "canonicalKey": _to_optional_str(identity_row.get("canonical_key")),
    }

    raw_pull_rates, pull_rates_source_field, used_payload_json_fallback = _resolve_pull_rate_assumptions_source(row)
    pull_rates = _to_camel_case_only(raw_pull_rates) if isinstance(raw_pull_rates, dict) else None

    warnings: List[str] = []
    if not pull_rates:
        warnings.append("Pull rate assumptions are not available for this set yet.")

    meta: Dict[str, Any] = {
        "source": "pokemon_set_page_snapshot_latest",
        "updatedAt": _to_optional_str(row.get("updated_at")),
        "warnings": warnings,
        "snapshot": {
            "source": "pokemon_set_page_snapshot_latest",
            "sourceField": pull_rates_source_field,
            "usedPayloadJsonFallback": used_payload_json_fallback,
        },
        "timings": {
            "snapshotQueryMs": query_ms,
            "snapshotReadMs": round((time.perf_counter() - started) * 1000, 3),
        },
    }

    payload = {
        "set": set_identity,
        "pullRates": pull_rates,
        "packPaths": [],
        "rarityBuckets": [],
        "assumptions": {},
        "sources": [],
        "meta": meta,
    }

    if _enforce_pull_rates_payload_budget(payload):
        meta["truncated"] = True

    logger.info(
        "[pokemon-snapshot] pull rates snapshot read complete set_id=%s query_ms=%s total_ms=%s",
        resolved_set_id,
        query_ms,
        meta["timings"]["snapshotReadMs"],
    )
    return payload


_INSIGHTS_SNAPSHOT_COLUMNS = "set_id,payload_json,updated_at"
INSIGHTS_PAYLOAD_BUDGET_BYTES = 400_000
# Ordered largest-first-ish; history_trend (~365 daily points) is the section
# most likely to ever need trimming in practice.
_INSIGHTS_TRIMMABLE_LIST_PATHS = (
    ("historyTrend",),
    ("rarityContribution",),
    ("simulationDrivers",),
    ("outcomeDistribution", "distributionBins"),
    ("outcomeDistribution", "thresholdBins"),
    ("outcomeDistribution", "percentiles"),
)


def _empty_insights_payload(
    *,
    set_row: Dict[str, Any],
    warnings: Optional[List[str]] = None,
    fallback_source: str,
) -> Dict[str, Any]:
    return {
        "set": {
            "id": _to_optional_str(set_row.get("id")),
            "name": _to_optional_str(set_row.get("name")),
            "slug": _to_optional_str(set_row.get("canonical_key")),
            "canonicalKey": _to_optional_str(set_row.get("canonical_key")),
        },
        "summary": {},
        "recommendation": {},
        "ripScore": {},
        "interpretation": {},
        "ripStatistics": {},
        "outcomeDistribution": {"percentiles": [], "distributionBins": [], "thresholdBins": []},
        "simulationDrivers": [],
        "rarityContribution": [],
        "historyTrend": [],
        "desirability": {},
        "desirabilityValidation": {},
        "meta": {
            "source": fallback_source,
            "updatedAt": datetime.now(timezone.utc).isoformat(),
            "warnings": list(warnings or []),
        },
    }


def _insights_payload_size(payload: Dict[str, Any]) -> int:
    return len(json.dumps(payload, default=str).encode("utf-8"))


def _get_nested(payload: Dict[str, Any], path: tuple) -> Any:
    node: Any = payload
    for key in path:
        if not isinstance(node, dict):
            return None
        node = node.get(key)
    return node


def _set_nested(payload: Dict[str, Any], path: tuple, value: Any) -> None:
    node = payload
    for key in path[:-1]:
        node = node.setdefault(key, {})
    node[path[-1]] = value


def _enforce_insights_payload_budget(payload: Dict[str, Any]) -> Dict[str, int]:
    """Progressively halve the largest trimmable arrays until the serialized
    payload fits INSIGHTS_PAYLOAD_BUDGET_BYTES, recording each section's
    original row count instead of silently dropping rows. Diagnostics (meta)
    are never touched. Should almost never trigger in practice — pull rate
    assumptions/cards/market data (the historically large sections) were
    already excluded from this contract entirely.
    """
    truncated_counts: Dict[str, int] = {}
    while _insights_payload_size(payload) > INSIGHTS_PAYLOAD_BUDGET_BYTES:
        trimmed_this_round = False
        for path in _INSIGHTS_TRIMMABLE_LIST_PATHS:
            rows = _get_nested(payload, path)
            if isinstance(rows, list) and len(rows) > 1:
                key = ".".join(path)
                truncated_counts.setdefault(key, len(rows))
                _set_nested(payload, path, rows[: max(1, len(rows) // 2)])
                trimmed_this_round = True
                break
        if not trimmed_this_round:
            break
    return truncated_counts


def get_pokemon_set_insights_snapshot_payload(set_id: str) -> Dict[str, Any]:
    """Return the slim Insights-tab snapshot (camelCase only) for a Pokemon set.

    Reads only pokemon_set_page_snapshot_latest.payload_json (there is no
    split column for Insights fields yet) and extracts just the sections the
    Insights tab renders: summary, interpretation (recommendation badge +
    pillar/section metas the RIP breakdown and evidence panels read),
    rip_statistics (pack paths/normal pack states), percentiles/
    distribution_bins/threshold_bins (opening outcomes chart), top_hits
    (simulation drivers), rankings (per-rarity value/rarity contribution
    rows), history_trend, openingDesirability, and desirabilityValidation
    (the set-level proof/comparison row only — never per-card validation
    rows). Never includes cards, market_dashboard/topChaseCards/
    marketMovers, pull_rate_assumptions (owned by /pull-rates), or
    cardDesirabilityValidation per-card rows (owned by /cards/validation).
    Public contract is camelCase only — see _to_camel_case_only.

    ripScoreBreakdown/decisionSignals are intentionally not precomputed here:
    the frontend selectors (selectRipScoreBreakdown/selectDecisionSignals/
    selectTrendScores) already derive them from `summary` alone, and
    duplicating that logic here would be a second, driftable copy of the same
    analytics rather than a direct adapter.
    """
    started = time.perf_counter()
    resolved = _to_optional_str(set_id)
    if not resolved:
        raise PokemonSetMarketError(400, "set_id is required", "POKEMON_SET_INSIGHTS_ID_REQUIRED")

    is_uuid = _looks_like_uuid(resolved)
    set_row: Optional[Dict[str, Any]] = None
    if is_uuid:
        resolved_set_id = resolved
    else:
        set_row = _resolve_set_row(resolved)
        resolved_set_id = str(set_row["id"])

    t_query = time.perf_counter()
    row: Optional[Dict[str, Any]] = None
    try:
        result = (
            public_read_client.table("pokemon_set_page_snapshot_latest")
            .select(_INSIGHTS_SNAPSHOT_COLUMNS)
            .eq("set_id", resolved_set_id)
            .limit(1)
            .execute()
        )
        row = _first_row(result)
    except Exception as exc:
        logger.warning(
            "[pokemon-snapshot] insights snapshot read failed set_id=%s exc=%s",
            resolved_set_id,
            exc,
            exc_info=True,
        )
        row = None
    query_ms = round((time.perf_counter() - t_query) * 1000, 3)

    if not row or not isinstance(row.get("payload_json"), dict):
        logger.info(
            "[pokemon-snapshot] insights snapshot missing set_id=%s elapsed_ms=%s",
            resolved_set_id,
            round((time.perf_counter() - started) * 1000, 3),
        )
        return _empty_insights_payload(
            set_row=set_row or {"id": resolved_set_id},
            warnings=["Pokemon set insights snapshot is missing; served empty fallback payload."],
            fallback_source="empty_fallback_missing_pokemon_set_page_snapshot_latest",
        )

    payload_json = row["payload_json"]
    resolved_row_set_id = _to_optional_str(row.get("set_id")) or resolved_set_id
    identity_row = set_row or {"id": resolved_row_set_id}
    set_identity = {
        "id": _to_optional_str(identity_row.get("id")) or resolved_row_set_id,
        "name": _to_optional_str(identity_row.get("name")),
        "slug": _to_optional_str(identity_row.get("canonical_key")),
        "canonicalKey": _to_optional_str(identity_row.get("canonical_key")),
    }

    raw_summary = payload_json.get("summary")
    raw_interpretation = payload_json.get("interpretation")
    raw_rip_statistics = payload_json.get("rip_statistics")
    raw_percentiles = payload_json.get("percentiles")
    raw_distribution_bins = payload_json.get("distribution_bins")
    raw_threshold_bins = payload_json.get("threshold_bins")
    raw_top_hits = payload_json.get("top_hits")
    raw_rankings = payload_json.get("rankings")
    raw_history_trend = payload_json.get("history_trend")
    raw_desirability = payload_json.get("openingDesirability")
    if not isinstance(raw_desirability, dict):
        raw_desirability = payload_json.get("opening_desirability")
    raw_desirability_validation = payload_json.get("desirabilityValidation")
    if not isinstance(raw_desirability_validation, dict):
        raw_desirability_validation = payload_json.get("desirability_validation")

    summary_camel = _to_camel_case_only(raw_summary) if isinstance(raw_summary, dict) else {}
    interpretation_camel = _to_camel_case_only(raw_interpretation) if isinstance(raw_interpretation, dict) else {}
    rip_statistics_camel = _to_camel_case_only(raw_rip_statistics) if isinstance(raw_rip_statistics, dict) else {}
    desirability_camel = _to_camel_case_only(raw_desirability) if isinstance(raw_desirability, dict) else {}
    desirability_validation_camel = (
        _to_camel_case_only(raw_desirability_validation) if isinstance(raw_desirability_validation, dict) else {}
    )

    interpretation_meta = interpretation_camel.get("meta") if isinstance(interpretation_camel.get("meta"), dict) else {}
    pack_score_meta = interpretation_meta.get("packScore") if isinstance(interpretation_meta.get("packScore"), dict) else {}

    rip_score_value = summary_camel.get("relativePackScore")
    if rip_score_value is None:
        rip_score_value = summary_camel.get("packScore")

    warnings: List[str] = []
    if not summary_camel:
        warnings.append("RIP summary is not available for this set yet.")
    if not isinstance(raw_top_hits, list) or not raw_top_hits:
        warnings.append("Simulation drivers (top hits) are not available for this set yet.")

    payload = {
        "set": set_identity,
        "summary": summary_camel,
        "recommendation": {
            "label": pack_score_meta.get("label"),
            "summary": pack_score_meta.get("summary"),
        },
        "ripScore": {
            "score": rip_score_value,
            "rank": summary_camel.get("packRank"),
            "tier": summary_camel.get("packTier"),
        },
        "interpretation": interpretation_camel,
        "ripStatistics": rip_statistics_camel,
        "outcomeDistribution": {
            "percentiles": _to_camel_case_only(raw_percentiles) if isinstance(raw_percentiles, list) else [],
            "distributionBins": _to_camel_case_only(raw_distribution_bins) if isinstance(raw_distribution_bins, list) else [],
            "thresholdBins": _to_camel_case_only(raw_threshold_bins) if isinstance(raw_threshold_bins, list) else [],
        },
        "simulationDrivers": _to_camel_case_only(raw_top_hits) if isinstance(raw_top_hits, list) else [],
        "rarityContribution": _to_camel_case_only(raw_rankings) if isinstance(raw_rankings, list) else [],
        "historyTrend": _to_camel_case_only(raw_history_trend) if isinstance(raw_history_trend, list) else [],
        "desirability": desirability_camel,
        "desirabilityValidation": desirability_validation_camel,
        "meta": {
            "source": "pokemon_set_page_snapshot_latest",
            "updatedAt": _to_optional_str(row.get("updated_at")),
            "warnings": warnings,
            "timings": {
                "snapshotQueryMs": query_ms,
                "snapshotReadMs": round((time.perf_counter() - started) * 1000, 3),
            },
        },
    }

    truncated_counts = _enforce_insights_payload_budget(payload)
    if truncated_counts:
        payload["meta"]["truncated"] = True
        payload["meta"]["truncatedOriginalCounts"] = truncated_counts

    logger.info(
        "[pokemon-snapshot] insights snapshot read complete set_id=%s query_ms=%s total_ms=%s",
        resolved_set_id,
        query_ms,
        payload["meta"]["timings"]["snapshotReadMs"],
    )
    return payload


def _fetch_insights_snapshot_row(set_id: str):
    """Shared row-fetch step for the full/critical/secondary Insights
    payloads below — one indexed read against pokemon_set_page_snapshot_latest,
    keyed by set_id. Extracted so the critical/secondary split shares it
    instead of duplicating the query logic; the full payload above is left
    inlined and untouched to keep its blast radius at zero.

    Returns (row, set_row, resolved_set_id, query_ms, started). `row` is None
    when the snapshot is missing/unreadable — callers fall back to their own
    empty-payload shape in that case.
    """
    started = time.perf_counter()
    resolved = _to_optional_str(set_id)
    if not resolved:
        raise PokemonSetMarketError(400, "set_id is required", "POKEMON_SET_INSIGHTS_ID_REQUIRED")

    is_uuid = _looks_like_uuid(resolved)
    set_row: Optional[Dict[str, Any]] = None
    if is_uuid:
        resolved_set_id = resolved
    else:
        set_row = _resolve_set_row(resolved)
        resolved_set_id = str(set_row["id"])

    t_query = time.perf_counter()
    row: Optional[Dict[str, Any]] = None
    try:
        result = (
            public_read_client.table("pokemon_set_page_snapshot_latest")
            .select(_INSIGHTS_SNAPSHOT_COLUMNS)
            .eq("set_id", resolved_set_id)
            .limit(1)
            .execute()
        )
        row = _first_row(result)
    except Exception as exc:
        logger.warning(
            "[pokemon-snapshot] insights snapshot read failed set_id=%s exc=%s",
            resolved_set_id,
            exc,
            exc_info=True,
        )
        row = None
    query_ms = round((time.perf_counter() - t_query) * 1000, 3)
    return row, set_row, resolved_set_id, query_ms, started


def _resolve_insights_set_identity(row: Dict[str, Any], set_row: Optional[Dict[str, Any]], resolved_set_id: str) -> Dict[str, Any]:
    resolved_row_set_id = _to_optional_str(row.get("set_id")) or resolved_set_id
    identity_row = set_row or {"id": resolved_row_set_id}
    return {
        "id": _to_optional_str(identity_row.get("id")) or resolved_row_set_id,
        "name": _to_optional_str(identity_row.get("name")),
        "slug": _to_optional_str(identity_row.get("canonical_key")),
        "canonicalKey": _to_optional_str(identity_row.get("canonical_key")),
    }


def _empty_insights_critical_payload(
    *, set_row: Dict[str, Any], warnings: Optional[List[str]] = None, fallback_source: str
) -> Dict[str, Any]:
    return {
        "set": {
            "id": _to_optional_str(set_row.get("id")),
            "name": _to_optional_str(set_row.get("name")),
            "slug": _to_optional_str(set_row.get("canonical_key")),
            "canonicalKey": _to_optional_str(set_row.get("canonical_key")),
        },
        "summary": {},
        "recommendation": {},
        "ripScore": {},
        "interpretation": {},
        "meta": {
            "source": fallback_source,
            "updatedAt": datetime.now(timezone.utc).isoformat(),
            "warnings": list(warnings or []),
        },
    }


def _empty_insights_secondary_payload(
    *, set_row: Dict[str, Any], warnings: Optional[List[str]] = None, fallback_source: str
) -> Dict[str, Any]:
    return {
        "set": {
            "id": _to_optional_str(set_row.get("id")),
            "name": _to_optional_str(set_row.get("name")),
            "slug": _to_optional_str(set_row.get("canonical_key")),
            "canonicalKey": _to_optional_str(set_row.get("canonical_key")),
        },
        "ripStatistics": {},
        "outcomeDistribution": {"percentiles": [], "distributionBins": [], "thresholdBins": []},
        "simulationDrivers": [],
        "rarityContribution": [],
        "historyTrend": [],
        "desirability": {},
        "desirabilityValidation": {},
        "meta": {
            "source": fallback_source,
            "updatedAt": datetime.now(timezone.utc).isoformat(),
            "warnings": list(warnings or []),
        },
    }


def get_pokemon_set_insights_critical_snapshot_payload(set_id: str) -> Dict[str, Any]:
    """Priority 1-3 slice of the Insights tab: RIP Score hero, pillar cards
    (interpretation), and the recommendation/"what usually happens" copy.
    Shares _fetch_insights_snapshot_row with the secondary/full variants —
    the same one cheap indexed read, no duplicate query logic. See
    get_pokemon_set_insights_snapshot_payload above for the full-payload
    docstring; this is a strict subset of the same fields, none of which are
    ever budget-trimmed (see _INSIGHTS_TRIMMABLE_LIST_PATHS).
    """
    row, set_row, resolved_set_id, query_ms, started = _fetch_insights_snapshot_row(set_id)

    if not row or not isinstance(row.get("payload_json"), dict):
        logger.info(
            "[pokemon-snapshot] insights critical snapshot missing set_id=%s elapsed_ms=%s",
            resolved_set_id,
            round((time.perf_counter() - started) * 1000, 3),
        )
        return _empty_insights_critical_payload(
            set_row=set_row or {"id": resolved_set_id},
            warnings=["Pokemon set insights snapshot is missing; served empty fallback payload."],
            fallback_source="empty_fallback_missing_pokemon_set_page_snapshot_latest",
        )

    payload_json = row["payload_json"]
    set_identity = _resolve_insights_set_identity(row, set_row, resolved_set_id)

    raw_summary = payload_json.get("summary")
    raw_interpretation = payload_json.get("interpretation")
    summary_camel = _to_camel_case_only(raw_summary) if isinstance(raw_summary, dict) else {}
    interpretation_camel = _to_camel_case_only(raw_interpretation) if isinstance(raw_interpretation, dict) else {}

    interpretation_meta = interpretation_camel.get("meta") if isinstance(interpretation_camel.get("meta"), dict) else {}
    pack_score_meta = interpretation_meta.get("packScore") if isinstance(interpretation_meta.get("packScore"), dict) else {}

    rip_score_value = summary_camel.get("relativePackScore")
    if rip_score_value is None:
        rip_score_value = summary_camel.get("packScore")

    warnings: List[str] = []
    if not summary_camel:
        warnings.append("RIP summary is not available for this set yet.")

    payload = {
        "set": set_identity,
        "summary": summary_camel,
        "recommendation": {
            "label": pack_score_meta.get("label"),
            "summary": pack_score_meta.get("summary"),
        },
        "ripScore": {
            "score": rip_score_value,
            "rank": summary_camel.get("packRank"),
            "tier": summary_camel.get("packTier"),
        },
        "interpretation": interpretation_camel,
        "meta": {
            "source": "pokemon_set_page_snapshot_latest",
            "updatedAt": _to_optional_str(row.get("updated_at")),
            "warnings": warnings,
            "timings": {
                "snapshotQueryMs": query_ms,
                "snapshotReadMs": round((time.perf_counter() - started) * 1000, 3),
            },
        },
    }

    logger.info(
        "[pokemon-snapshot] insights critical snapshot read complete set_id=%s query_ms=%s total_ms=%s",
        resolved_set_id,
        query_ms,
        payload["meta"]["timings"]["snapshotReadMs"],
    )
    return payload


def get_pokemon_set_insights_secondary_snapshot_payload(set_id: str) -> Dict[str, Any]:
    """Priority 4-5 slice of the Insights tab: charts/distributions (outcome
    distribution, simulation drivers, rarity contribution, history trend) and
    deep diagnostics (desirability/desirabilityValidation). Shares
    _fetch_insights_snapshot_row with the critical/full variants. Reuses
    _enforce_insights_payload_budget unchanged — its trimmable paths
    (historyTrend, rarityContribution, simulationDrivers, outcomeDistribution.*)
    already fall entirely inside this payload.
    """
    row, set_row, resolved_set_id, query_ms, started = _fetch_insights_snapshot_row(set_id)

    if not row or not isinstance(row.get("payload_json"), dict):
        logger.info(
            "[pokemon-snapshot] insights secondary snapshot missing set_id=%s elapsed_ms=%s",
            resolved_set_id,
            round((time.perf_counter() - started) * 1000, 3),
        )
        return _empty_insights_secondary_payload(
            set_row=set_row or {"id": resolved_set_id},
            warnings=["Pokemon set insights snapshot is missing; served empty fallback payload."],
            fallback_source="empty_fallback_missing_pokemon_set_page_snapshot_latest",
        )

    payload_json = row["payload_json"]
    set_identity = _resolve_insights_set_identity(row, set_row, resolved_set_id)

    raw_rip_statistics = payload_json.get("rip_statistics")
    raw_percentiles = payload_json.get("percentiles")
    raw_distribution_bins = payload_json.get("distribution_bins")
    raw_threshold_bins = payload_json.get("threshold_bins")
    raw_top_hits = payload_json.get("top_hits")
    raw_rankings = payload_json.get("rankings")
    raw_history_trend = payload_json.get("history_trend")
    raw_desirability = payload_json.get("openingDesirability")
    if not isinstance(raw_desirability, dict):
        raw_desirability = payload_json.get("opening_desirability")
    raw_desirability_validation = payload_json.get("desirabilityValidation")
    if not isinstance(raw_desirability_validation, dict):
        raw_desirability_validation = payload_json.get("desirability_validation")

    rip_statistics_camel = _to_camel_case_only(raw_rip_statistics) if isinstance(raw_rip_statistics, dict) else {}
    desirability_camel = _to_camel_case_only(raw_desirability) if isinstance(raw_desirability, dict) else {}
    desirability_validation_camel = (
        _to_camel_case_only(raw_desirability_validation) if isinstance(raw_desirability_validation, dict) else {}
    )

    warnings: List[str] = []
    if not isinstance(raw_top_hits, list) or not raw_top_hits:
        warnings.append("Simulation drivers (top hits) are not available for this set yet.")

    payload = {
        "set": set_identity,
        "ripStatistics": rip_statistics_camel,
        "outcomeDistribution": {
            "percentiles": _to_camel_case_only(raw_percentiles) if isinstance(raw_percentiles, list) else [],
            "distributionBins": _to_camel_case_only(raw_distribution_bins) if isinstance(raw_distribution_bins, list) else [],
            "thresholdBins": _to_camel_case_only(raw_threshold_bins) if isinstance(raw_threshold_bins, list) else [],
        },
        "simulationDrivers": _to_camel_case_only(raw_top_hits) if isinstance(raw_top_hits, list) else [],
        "rarityContribution": _to_camel_case_only(raw_rankings) if isinstance(raw_rankings, list) else [],
        "historyTrend": _to_camel_case_only(raw_history_trend) if isinstance(raw_history_trend, list) else [],
        "desirability": desirability_camel,
        "desirabilityValidation": desirability_validation_camel,
        "meta": {
            "source": "pokemon_set_page_snapshot_latest",
            "updatedAt": _to_optional_str(row.get("updated_at")),
            "warnings": warnings,
            "timings": {
                "snapshotQueryMs": query_ms,
                "snapshotReadMs": round((time.perf_counter() - started) * 1000, 3),
            },
        },
    }

    truncated_counts = _enforce_insights_payload_budget(payload)
    if truncated_counts:
        payload["meta"]["truncated"] = True
        payload["meta"]["truncatedOriginalCounts"] = truncated_counts

    logger.info(
        "[pokemon-snapshot] insights secondary snapshot read complete set_id=%s query_ms=%s total_ms=%s",
        resolved_set_id,
        query_ms,
        payload["meta"]["timings"]["snapshotReadMs"],
    )
    return payload
