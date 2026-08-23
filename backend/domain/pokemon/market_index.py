from __future__ import annotations

import hashlib
import json
import math
from datetime import date, timedelta
from typing import Any, Iterable, Mapping, Sequence

MARKET_INDEX_CONTRACT_VERSION = "pokemon-market-index-v1"
MARKET_INDEX_METHODOLOGY_VERSION = "chain_linked_common_cohort_v1"
MARKET_INDEX_BASE_VALUE = 100.0
RAW_INDEX_KEY = "raw"
CHASE_INDEX_KEY = "top10"
INDEX_KEYS = (RAW_INDEX_KEY, CHASE_INDEX_KEY)
WINDOWS = (("1D", 1), ("7D", 7), ("30D", 30), ("3M", 90), ("6M", 180), ("1Y", 365), ("SinceTracking", None))


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
    for key, resolved in baselines.items():
        target = resolved["targetStartDate"]
        start = resolved["startDate"]
        if start is None:
            result[key] = {"available": False, "percent": None, "startDate": None,
                           "endDate": latest["date"], "targetStartDate": target, "coverage": "unavailable"}
        else:
            result[key] = {"available": True, "percent": (latest["value"] / value_by_date[start] - 1.0) * 100.0,
                           "startDate": start, "endDate": latest["date"],
                           "targetStartDate": target, "coverage": "full"}
    return result


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

    ``ordered_dates`` must be ascending ISO dates. Returns, per window key:
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
            target = (date.fromisoformat(latest) - timedelta(days=days - 1)).isoformat()
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
