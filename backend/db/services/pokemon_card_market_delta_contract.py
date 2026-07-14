from __future__ import annotations

"""Canonical public Pokemon card market-delta calculations.

All public card surfaces use ``inclusive_calendar_dates_v1``:

* 1D compares the previous distinct UTC market date with the current date.
* N-day windows use ``end date - (N - 1)`` as their target start date.
* The baseline is the latest usable observation on or before that target.
* When history does not reach the target, the earliest usable point inside the
  window is used and the movement is explicitly marked partial.

The returned amount/percent describe displayable raw movement. ``reliable`` is
separate and is intended for Market Movers eligibility.
"""

from datetime import date, datetime, timedelta, timezone
from typing import Any, Dict, Iterable, List, Optional


WINDOW_CONVENTION = "inclusive_calendar_dates_v1"
MIN_HISTORY_SPAN_DAYS = {1: 1, 7: 3, 30: 14}
MAX_HISTORY_SPAN_DAYS = {1: 3, 7: 10, 30: 45}
MIN_CURRENT_PRICE = 1.0
MIN_ABSOLUTE_CHANGE = 0.25
MAX_ABSOLUTE_PERCENT = 300.0


def _text(value: Any) -> Optional[str]:
    if value is None:
        return None
    resolved = str(value).strip()
    return resolved or None


def utc_date_key(value: Any) -> Optional[str]:
    if isinstance(value, datetime):
        parsed = value
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed.astimezone(timezone.utc).date().isoformat()
    if isinstance(value, date):
        return value.isoformat()
    resolved = _text(value)
    if not resolved:
        return None
    try:
        parsed = datetime.fromisoformat(resolved.replace("Z", "+00:00"))
    except ValueError:
        try:
            return date.fromisoformat(resolved[:10]).isoformat()
        except (TypeError, ValueError):
            return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc).date().isoformat()


def _number(value: Any) -> Optional[float]:
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return None
    return parsed if parsed > 0 else None


def _observation_rows(observations: Iterable[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Collapse observations to the latest usable value on each UTC date."""
    by_date: Dict[str, Dict[str, Any]] = {}
    for index, observation in enumerate(observations or []):
        source_date = utc_date_key(
            observation.get("captured_at")
            or observation.get("capturedAt")
            or observation.get("source_date")
            or observation.get("sourceDate")
            or observation.get("date")
        )
        price = _number(
            observation.get("market_price")
            if "market_price" in observation
            else observation.get("marketPrice", observation.get("price"))
        )
        if not source_date or price is None:
            continue
        timestamp = _text(observation.get("captured_at") or observation.get("capturedAt")) or source_date
        candidate = {
            **observation,
            "market_price": price,
            "source_date": source_date,
            "_sort": (timestamp, index),
        }
        existing = by_date.get(source_date)
        if existing is None or candidate["_sort"] >= existing["_sort"]:
            by_date[source_date] = candidate
    return [by_date[key] for key in sorted(by_date)]


def calculate_pokemon_card_market_delta(
    *,
    observations: Iterable[Dict[str, Any]],
    selected_current_price: Any,
    selected_variant_id: Any,
    selected_condition_id: Any,
    latest_market_date: Any,
    requested_window_days: int,
    selected_current_source_date: Any = None,
    selected_current_source: Any = None,
) -> Dict[str, Any]:
    """Return the shared Cards, Market Movers, and Top Chase delta contract."""
    window_days = max(1, int(requested_window_days))
    end_date = utc_date_key(latest_market_date)
    selected_price = _number(selected_current_price)
    selected_source_date = utc_date_key(selected_current_source_date) or end_date
    rows = _observation_rows(observations)

    if end_date:
        rows = [row for row in rows if row["source_date"] <= end_date]

    # The canonical selected-price layer owns the public current price. Treat it
    # as the effective endpoint on the canonical market date while retaining its
    # real source date separately for carry-forward diagnostics.
    end = None
    if end_date and selected_price is not None:
        end = {
            "market_price": selected_price,
            "source_date": end_date,
            "actual_source_date": selected_source_date,
            "source": selected_current_source,
        }
    elif rows:
        end = rows[-1]
        end_date = end["source_date"]

    target_start_date = None
    start = None
    full_window_coverage = False
    if end and end_date:
        if window_days == 1:
            prior_rows = [row for row in rows if row["source_date"] < end_date]
            if prior_rows:
                start = prior_rows[-1]
                target_start_date = start["source_date"]
                full_window_coverage = True
        else:
            target_start_date = (
                date.fromisoformat(end_date) - timedelta(days=window_days - 1)
            ).isoformat()
            before_or_on_target = [row for row in rows if row["source_date"] <= target_start_date]
            if before_or_on_target:
                start = before_or_on_target[-1]
                full_window_coverage = True
            else:
                inside_window = [
                    row for row in rows
                    if target_start_date < row["source_date"] < end_date
                ]
                if inside_window:
                    start = inside_window[0]

    start_price = _number((start or {}).get("market_price"))
    current_price = _number((end or {}).get("market_price"))
    start_date = utc_date_key((start or {}).get("source_date"))
    end_source_date = utc_date_key((end or {}).get("actual_source_date") or (end or {}).get("source_date"))
    coverage_days = (
        (date.fromisoformat(end_date) - date.fromisoformat(start_date)).days
        if start_date and end_date
        else None
    )
    has_usable_pair = bool(
        start_price is not None
        and current_price is not None
        and start_date
        and end_date
        and start_date < end_date
    )
    is_partial_window = bool(has_usable_pair and not full_window_coverage)
    min_span = MIN_HISTORY_SPAN_DAYS.get(window_days, max(1, window_days // 2))
    max_span = MAX_HISTORY_SPAN_DAYS.get(window_days, window_days + 15)
    enough_history = bool(
        has_usable_pair
        and full_window_coverage
        and coverage_days is not None
        and min_span <= coverage_days <= max_span
    )
    change_amount = round(current_price - start_price, 2) if has_usable_pair else None
    change_percent = (
        round((change_amount / start_price) * 100, 2)
        if change_amount is not None and start_price
        else None
    )
    reliable = bool(
        enough_history
        and current_price is not None
        and current_price >= MIN_CURRENT_PRICE
        and change_amount is not None
        and abs(change_amount) >= MIN_ABSOLUTE_CHANGE
        and change_percent is not None
        and abs(change_percent) <= MAX_ABSOLUTE_PERCENT
    )
    if reliable:
        reliability = "reliable"
    elif is_partial_window:
        reliability = "partial_window"
    elif not has_usable_pair:
        reliability = "unavailable"
    elif not enough_history:
        reliability = "insufficient_history"
    else:
        reliability = "guardrailed"

    return {
        "window": f"{window_days}D",
        "windowDays": window_days,
        "windowConvention": WINDOW_CONVENTION,
        "targetStartDate": target_start_date,
        "startDate": start_date,
        "endDate": end_date,
        "startingPrice": round(start_price, 2) if start_price is not None else None,
        "currentPrice": round(current_price, 2) if current_price is not None else None,
        "changeAmount": change_amount,
        "changePercent": change_percent,
        "fullWindowCoverage": full_window_coverage,
        "isPartialWindow": is_partial_window,
        "windowCoverageDays": coverage_days,
        "requestedWindowDays": window_days,
        "enoughHistory": enough_history,
        "reliable": reliable,
        "reliability": reliability,
        "startSourceDate": start_date,
        "endSourceDate": end_source_date,
        "cardVariantId": _text(selected_variant_id),
        "conditionId": _text(selected_condition_id),
        "historyPointCount": len(rows),
        "startCarriedForward": bool(start_date and target_start_date and start_date < target_start_date),
        "endCarriedForward": bool(end_source_date and end_date and end_source_date < end_date),
        "source": _text((end or {}).get("source")),
    }
