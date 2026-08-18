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
    result: dict[str, dict[str, Any]] = {}
    for key, days in WINDOWS:
        if key == "1D":
            target = normalized[-2]["date"] if len(normalized) > 1 else None
            baseline = normalized[-2] if len(normalized) > 1 else None
        elif days is None:
            target, baseline = None, normalized[0]
        else:
            target = (date.fromisoformat(latest["date"]) - timedelta(days=days - 1)).isoformat()
            baseline = next((row for row in reversed(normalized) if row["date"] <= target), None)
            if normalized[0]["date"] > target:
                baseline = None
        if baseline is None:
            result[key] = {"available": False, "percent": None, "startDate": None,
                           "endDate": latest["date"], "targetStartDate": target, "coverage": "unavailable"}
        else:
            result[key] = {"available": True, "percent": (latest["value"] / baseline["value"] - 1.0) * 100.0,
                           "startDate": baseline["date"], "endDate": latest["date"],
                           "targetStartDate": target, "coverage": "full"}
    return result
