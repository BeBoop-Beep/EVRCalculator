from __future__ import annotations

import hashlib
import json
import math
from datetime import date, timedelta
from typing import Any, Iterable, Mapping, Sequence

MARKET_INDEX_CONTRACT_VERSION = "pokemon-market-index-v1"
MARKET_INDEX_METHODOLOGY_VERSION = "chain_linked_common_cohort_v1"
MARKET_INDEX_BASE_VALUE = 100.0
MARKET_INDEX_TRACKING_START_DATE = "2026-04-23"
MARKET_COMPARISON_WINDOW_CONTRACT_VERSION = "true_elapsed_lookback_v5"
RAW_INDEX_KEY = "raw"
CHASE_INDEX_KEY = "top10"
INDEX_KEYS = (RAW_INDEX_KEY, CHASE_INDEX_KEY)
WINDOWS = (("1D", 1), ("7D", 7), ("30D", 30), ("3M", 90), ("6M", 180), ("1Y", 365), ("SinceTracking", None))

#: Window keys whose target may legitimately predate a market's history and
#: which are therefore allowed to report a truthful "since first available"
#: partial rather than disappearing from the timeframe control.
PARTIAL_ELIGIBLE_WINDOW_KEYS = frozenset({"6M", "1Y"})


def resolve_market_window_target(market_date: str, window_key: str) -> str | None:
    """THE one definition of the date a fixed window reaches back to.

    ``market_date - N`` TRUE ELAPSED CALENDAR DAYS. A 7D window ending on
    2026-08-25 targets 2026-08-18, which is seven elapsed days back — not
    2026-08-19, which is what an inclusive ``days - 1`` count produces and
    which is the off-by-one this helper exists to make impossible to
    reintroduce. ``SinceTracking``/All has no fixed target and returns None.

    Both the family-window resolver (``resolve_window_baselines``) and the
    shared-comparison domain (``build_comparison_windows``) route through
    here, so "7D" cannot mean two different spans in one publication again.
    """
    lookback = dict(WINDOWS).get(window_key)
    if window_key not in dict(WINDOWS):
        raise MarketIndexError(f"unknown market window key: {window_key}")
    if lookback is None:
        return None
    return (date.fromisoformat(str(market_date)[:10]) - timedelta(days=lookback)).isoformat()


class MarketIndexError(ValueError):
    pass


def deterministic_fingerprint(value: Any) -> str:
    encoded = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def _constituent_map(observation: Mapping[str, Any]) -> dict[str, Mapping[str, Any]]:
    rows = observation.get("constituents") or ()
    result: dict[str, Mapping[str, Any]] = {}
    for row in rows:
        set_id = str(row.get("setId") or row.get("set_id") or "").strip()
        value = float(row.get("setValue") if row.get("setValue") is not None else row.get("set_value"))
        if not set_id or set_id in result or not math.isfinite(value) or value <= 0:
            raise MarketIndexError("constituents require unique set ids and finite positive values")
        result[set_id] = row
    if not result:
        raise MarketIndexError("an index observation requires at least one constituent")
    return result


def build_chain_linked_history(observations: Iterable[Mapping[str, Any]]) -> list[dict[str, Any]]:
    """Build a chain-linked series from complete, point-in-time observations."""
    ordered = sorted((dict(row) for row in observations), key=lambda row: str(row["marketDate"]))
    output: list[dict[str, Any]] = []
    previous_values: dict[str, Mapping[str, Any]] | None = None
    previous_index = MARKET_INDEX_BASE_VALUE
    previous_date: str | None = None
    seen_dates: set[str] = set()
    for observation in ordered:
        market_date = str(observation["marketDate"])[:10]
        if market_date in seen_dates:
            raise MarketIndexError(f"duplicate market date: {market_date}")
        seen_dates.add(market_date)
        values = _constituent_map(observation)
        basket_value = sum(float(row.get("setValue", row.get("set_value"))) for row in values.values())
        if previous_values is None:
            daily_return = None
            index_value = MARKET_INDEX_BASE_VALUE
            common_ids: list[str] = []
        else:
            common_ids = sorted(previous_values.keys() & values.keys())
            if not common_ids:
                raise MarketIndexError(f"{market_date} has no common cohort with {previous_date}")
            previous_common = sum(float(previous_values[key].get("setValue", previous_values[key].get("set_value"))) for key in common_ids)
            current_common = sum(float(values[key].get("setValue", values[key].get("set_value"))) for key in common_ids)
            if previous_common <= 0:
                raise MarketIndexError("previous common-cohort basket must be positive")
            daily_return = current_common / previous_common - 1.0
            index_value = previous_index * (1.0 + daily_return)
        constituents = sorted((dict(row) for row in values.values()), key=lambda row: str(row.get("setId") or row.get("set_id")))
        output.append({**observation, "marketDate": market_date, "basketValue": basket_value,
                       "normalizedIndexValue": index_value, "dailyReturn": daily_return,
                       "previousMarketDate": previous_date, "commonSetIds": common_ids,
                       "constituents": constituents})
        previous_values, previous_index, previous_date = values, index_value, market_date
    return output


def resolve_partial_window_coverage(
    key: str,
    *,
    target: str | None,
    start: str | None,
    earliest: str,
    latest: str,
) -> tuple[str | None, str, bool]:
    """Whether a window with no full-length baseline may report a truthful partial.

    Shared by ``compute_strict_window_movements`` (Cards Market Index) and
    ``compute_market_breadth`` so a 6M/1Y window that predates a market's
    history reports the SAME effective start, coverage, and
    ``isSinceFirstAvailable`` flag whether it is asked for an index return or a
    breadth classification. Short windows never fall back here: only
    ``PARTIAL_ELIGIBLE_WINDOW_KEYS`` may substitute the earliest observation
    for a missing baseline.

    Returns ``(effective_start, coverage, is_since_first_available)``.
    """
    is_partial = bool(
        start is None and key in PARTIAL_ELIGIBLE_WINDOW_KEYS and target is not None and earliest > target and earliest < latest
    )
    if is_partial:
        return earliest, "partial", True
    if start is None:
        return None, "unavailable", False
    return start, "full", False


def compute_strict_window_movements(points: Sequence[Mapping[str, Any]]) -> dict[str, dict[str, Any]]:
    normalized = sorted(({"date": str(row.get("date") or row.get("marketDate"))[:10],
                          "value": float(row.get("value") if row.get("value") is not None else row.get("normalizedIndexValue"))}
                         for row in points), key=lambda row: row["date"])
    if not normalized:
        return {}
    latest = normalized[-1]
    # Window baselines come from the shared resolver so that this index's idea
    # of "30D" and Market Breadth's idea of "30D" are the same span by
    # construction rather than by two implementations agreeing to agree.
    value_by_date = {row["date"]: row["value"] for row in normalized}
    baselines = resolve_window_baselines([row["date"] for row in normalized])
    result: dict[str, dict[str, Any]] = {}
    earliest = normalized[0]["date"]
    for key, resolved in baselines.items():
        target = resolved["targetStartDate"]
        start = resolved["startDate"]
        # PARTIAL LONG WINDOWS, stated honestly. A market with four months of
        # history genuinely cannot report a full 1Y, but dropping 6M/1Y from
        # the control entirely is a worse answer than reporting the real span
        # and SAYING it is partial. The percentage is still a real return
        # between two real observations; only its span is shorter than the
        # label's nominal one, and `isSinceFirstAvailable` says so. Short
        # windows never fall back: a 7D that silently became "since the start"
        # would be a fabricated 7D.
        start, coverage, is_partial = resolve_partial_window_coverage(
            key, target=target, start=start, earliest=earliest, latest=latest["date"]
        )
        if start is None:
            result[key] = {"available": False, "percent": None, "startDate": None,
                           "endDate": latest["date"], "targetStartDate": target,
                           "coverage": "unavailable", "isSinceFirstAvailable": False}
        else:
            result[key] = {"available": True, "percent": (latest["value"] / value_by_date[start] - 1.0) * 100.0,
                           "startDate": start, "endDate": latest["date"],
                           "targetStartDate": target,
                           "coverage": "partial" if is_partial else "full",
                           "isSinceFirstAvailable": is_partial}
    return result


def build_comparison_windows(
    market_date: str,
    family_dates: Sequence[Sequence[str]],
) -> dict[str, dict[str, Any]]:
    """Build the one calendar domain used by the cross-market comparison.

    Fixed windows are inclusive. 1D remains a strict calendar-day domain but
    is selectable when any family has both real boundary observations. Long
    windows that predate common history fall back to the first common date.
    ``SinceTracking``/All always begins at that first common date.
    """
    end = date.fromisoformat(str(market_date)[:10])
    date_sets = [{str(value)[:10] for value in values if value} for values in family_dates]
    common_dates = set.intersection(*date_sets) if date_sets and all(date_sets) else set()
    common_start = min(common_dates) if common_dates else None
    end_key = end.isoformat()
    result: dict[str, dict[str, Any]] = {}
    for key, days in WINDOWS:
        # TRUE ELAPSED LOOKBACKS, from the one canonical resolver. This used to
        # compute `end - (days - 1)` inline — an inclusive day COUNT — so 7D
        # only reached six elapsed days back while the family windows next to
        # it reached seven. Both now ask the same function.
        target = common_start if days is None else resolve_market_window_target(end_key, key)
        is_partial_long_window = bool(
            key in {"6M", "1Y"} and target and common_start and common_start > target
        )
        display_start = common_start if is_partial_long_window else target
        if key == "1D":
            available = any(target in dates and end_key in dates for dates in date_sets)
        else:
            available = bool(display_start and display_start in common_dates and end_key in common_dates)
        result[key] = {
            "targetStartDate": target,
            "displayStartDate": display_start,
            "displayEndDate": end_key,
            "available": available,
            "coverage": "partial" if available and is_partial_long_window else "full" if available else "unavailable",
            "isSinceFirstAvailable": is_partial_long_window,
        }
    return result


def compute_comparison_window_movements(
    points: Sequence[Mapping[str, Any]],
    comparison_windows: Mapping[str, Mapping[str, Any]],
) -> dict[str, dict[str, Any]]:
    """Compute returns solely from real observations inside shared domains."""
    normalized = sorted(({
        "date": str(row.get("date") or row.get("marketDate"))[:10],
        "value": float(row.get("value") if row.get("value") is not None else row.get("normalizedIndexValue")),
    } for row in points), key=lambda row: row["date"])
    result: dict[str, dict[str, Any]] = {}
    for key, window in comparison_windows.items():
        display_start = str(window.get("displayStartDate") or "")[:10]
        display_end = str(window.get("displayEndDate") or "")[:10]
        value_by_date = {row["date"]: row["value"] for row in normalized}
        available = (window.get("available") is True
                     and display_start in value_by_date and display_end in value_by_date)
        actual_start = display_start if available else None
        actual_end = display_end if available else None
        coverage = str(window.get("coverage") or "full") if available else "unavailable"
        percent = ((value_by_date[display_end] / value_by_date[display_start] - 1.0) * 100.0
                   if available else None)
        result[key] = {
            "available": available,
            "percent": percent,
            "startDate": actual_start if available else None,
            "endDate": actual_end if available else display_end,
            "actualStartDate": actual_start if available else None,
            "actualEndDate": actual_end if available else None,
            "targetStartDate": window.get("targetStartDate"),
            "coverage": coverage,
            "isSinceFirstAvailable": bool(window.get("isSinceFirstAvailable")) if available else False,
        }
    return result


def resolve_one_day_comparison_close(
    points: Sequence[Mapping[str, Any]], *, target_date: str, market_date: str
) -> dict[str, Any]:
    """Resolve a truthful previous-close comparison for one calendar day.

    The current close must be a real observation. The previous close may be
    carried only from exactly one day before ``target_date`` and only inside
    the current close's chain segment. Nothing returned here is canonical
    history or suitable for any window other than 1D.
    """
    target = date.fromisoformat(str(target_date)[:10])
    end = date.fromisoformat(str(market_date)[:10])
    if target != end - timedelta(days=1):
        raise MarketIndexError("1D comparison target must be market_date - 1 calendar day")

    normalized = sorted(({
        "date": str(row.get("date") or row.get("marketDate"))[:10],
        "value": float(row.get("value") if row.get("value") is not None else row.get("indexValue", row.get("normalizedIndexValue"))),
        "chainSegmentId": row.get("chainSegmentId"),
    } for row in points), key=lambda row: row["date"])
    by_date = {row["date"]: row for row in normalized}
    target_key, end_key = target.isoformat(), end.isoformat()
    current = by_date.get(end_key)
    unavailable = {
        "available": False, "percent": None, "startDate": None,
        "endDate": end_key, "targetStartDate": target_key,
        "coverage": "unavailable", "isCarriedForwardBaseline": False,
        "baselineSourceDate": None, "comparisonTrend": [],
    }
    if current is None:
        return unavailable

    baseline = by_date.get(target_key)
    carried = False
    if baseline is None:
        source_key = (target - timedelta(days=1)).isoformat()
        baseline = by_date.get(source_key)
        carried = baseline is not None
    if baseline is None or baseline["value"] == 0:
        return unavailable
    if baseline.get("chainSegmentId") != current.get("chainSegmentId"):
        return unavailable

    source_date = baseline["date"]
    comparison = [
        {"date": target_key, "value": baseline["value"],
         "isObserved": not carried, "isCarriedForward": carried,
         "sourceDate": source_date},
        {"date": end_key, "value": current["value"],
         "isObserved": True, "isCarriedForward": False,
         "sourceDate": end_key},
    ]
    return {
        "available": True,
        "percent": (current["value"] / baseline["value"] - 1.0) * 100.0,
        "startDate": target_key,
        "endDate": end_key,
        "actualStartDate": target_key,
        "actualEndDate": end_key,
        "targetStartDate": target_key,
        "coverage": "carried_previous_close" if carried else "full",
        "isCarriedForwardBaseline": carried,
        "baselineSourceDate": source_date,
        "comparisonTrend": comparison,
    }


def resolve_window_baselines(ordered_dates: Sequence[str]) -> dict[str, dict[str, Any]]:
    """Resolve the baseline date for every ``WINDOWS`` key over ``ordered_dates``.

    THIS IS THE SINGLE DEFINITION OF WHAT "7D"/"30D"/"All" MEAN for every
    consumer of this module. It was extracted verbatim out of
    ``compute_strict_window_movements`` (which now calls it) so that a second
    consumer — Market Breadth, which needs the same period endpoints but
    classifies constituents instead of dividing index levels — cannot drift
    into its own interpretation of the same window label. A window means the
    same span of history whether you ask the index how far it moved or ask
    breadth how many cards participated.

    ``ordered_dates`` must be ascending ISO dates. Named multi-day windows use
    true elapsed-day lookbacks: a 7D window ending on August 24 targets August
    17. The baseline is the newest actually-present observation on or before
    that target. Returns, per window key:
    ``targetStartDate`` (the date the window nominally reaches back to),
    ``startDate`` (the newest actually-present date at or before it, or None
    when history does not reach back that far), ``endDate`` and ``available``.

    "1D" is deliberately the PREVIOUS PRESENT POINT rather than
    ``latest - 1 day``: with non-daily history a literal calendar yesterday is
    frequently absent, and the meaningful comparison is against the last day
    the market was actually observed. ``days is None`` ("SinceTracking"/"All")
    resolves to the earliest available point.
    """
    if not ordered_dates:
        return {}
    latest = str(ordered_dates[-1])[:10]
    result: dict[str, dict[str, Any]] = {}
    for key, days in WINDOWS:
        if key == "1D":
            target = str(ordered_dates[-2])[:10] if len(ordered_dates) > 1 else None
            start = target
        elif days is None:
            target, start = None, str(ordered_dates[0])[:10]
        else:
            target = resolve_market_window_target(latest, key)
            start = next((str(value)[:10] for value in reversed(ordered_dates) if str(value)[:10] <= target), None)
            if str(ordered_dates[0])[:10] > target:
                start = None
        result[key] = {"targetStartDate": target, "startDate": start,
                       "endDate": latest, "available": start is not None}
    return result


def build_chain_linked_history_with_segments(observations: Iterable[Mapping[str, Any]]) -> list[dict[str, Any]]:
    """Chain-link ``observations``, tolerating days that share no constituent
    with the prior surviving day rather than raising — and tagging every
    resulting row with which continuous CHAIN SEGMENT it belongs to.

    ``build_chain_linked_history`` above is the unforked global methodology,
    and its contract is to RAISE ``MarketIndexError`` when two consecutive
    observations share no common cohort. That is the right contract for the
    global cross-set index, whose 30+ constituents make a zero-overlap day
    implausible. It is the wrong contract for a SINGLE set's basket, where a
    zero-overlap day is realistic (a sealed set may track one or two SKUs; a
    card set may have a day whose only priced cards are entirely different
    from the previous day's). Rather than fork the domain function's error
    behavior, a cohort break here starts a NEW chain segment at the base
    value: the index legitimately cannot say anything about the market's
    movement across a day with no shared constituent, so it says nothing
    about that one transition instead of fabricating one or discarding the
    entire history.

    SEGMENT TAGGING IS NOT COSMETIC. Every row carries ``chainSegmentId`` (a
    0-based counter, incrementing once per break) and ``segmentStartDate``. A
    caller that naively fed rows from two different segments into one window
    return would compute exactly the fabricated cross-break "return" this
    function exists to prevent (segment A's last 119.40 read against segment
    B's fresh 100.00 baseline as a manufactured -16.25% move). Callers must
    confine window returns to a single segment; do not strip these tags.

    This function was promoted from the Sealed snapshot service (where it
    lived as ``_chain_link_with_cohort_breaks``) so the Cards Market Index
    consumes the identical segmentation rather than growing a second, silently
    divergent copy. Sealed still calls it under its original private name.
    """
    all_rows: list[dict[str, Any]] = []
    segment: list[Mapping[str, Any]] = []
    segment_id = 0
    for observation in observations:
        segment.append(observation)
        try:
            build_chain_linked_history(segment)
        except MarketIndexError:
            # This observation broke the chain with the rest of the current
            # segment. Flush everything before it under the CURRENT segment
            # id, then start a new segment id at this single observation (a
            # fresh baseline).
            if len(segment) > 1:
                finished = build_chain_linked_history(segment[:-1])
                start_date = finished[0]["marketDate"]
                for row in finished:
                    row["chainSegmentId"] = segment_id
                    row["segmentStartDate"] = start_date
                all_rows.extend(finished)
                segment_id += 1
            segment = [observation]
    if segment:
        finished = build_chain_linked_history(segment)
        start_date = finished[0]["marketDate"]
        for row in finished:
            row["chainSegmentId"] = segment_id
            row["segmentStartDate"] = start_date
        all_rows.extend(finished)
    return all_rows
