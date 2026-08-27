from __future__ import annotations

import hashlib
import json
from datetime import date, datetime, timedelta, timezone
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence

from backend.db.clients.supabase_client import service_read_client
from backend.domain.pokemon.market_index import resolve_market_window_target
from backend.desirability.public_analytics_policy import is_public_analytics_eligible

TABLE = "pokemon_explore_set_value_snapshot_latest"
# The Set Market's window vocabulary. The last key is named "lifetime" rather
# than "SinceTracking" because a Set Value series has no chain segments to
# track from - it is simply that Set's own complete published history - but the
# FIXED windows mean exactly what they mean on the global Market, and are
# resolved by the same helper rather than by a local date formula.
WINDOWS = (("1D", 1), ("7D", 7), ("30D", 30), ("3M", 90), ("6M", 180), ("1Y", 365), ("lifetime", None))

#: `lifetime` here is the Set's own history start; the canonical resolver names
#: the equivalent global key `SinceTracking`. Only the fixed keys are looked up.
_CANONICAL_WINDOW_KEY = {"1D": "1D", "7D": "7D", "30D": "30D", "3M": "3M", "6M": "6M", "1Y": "1Y"}
MAX_TREND_POINTS = 48
MAX_RECENT_DAILY_TREND_POINTS = 30


class ExploreSetValueUnavailable(Exception):
    def __init__(self, message: str, *, diagnostics: Optional[Dict[str, Any]] = None) -> None:
        super().__init__(message)
        self.diagnostics = diagnostics or {}


def _text(value: Any) -> Optional[str]:
    value = str(value or "").strip()
    return value or None


def _number(value: Any) -> Optional[float]:
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return None
    return parsed if parsed > 0 else None


def _points(rows: Iterable[Mapping[str, Any]]) -> List[Dict[str, Any]]:
    by_date: Dict[str, float] = {}
    for row in rows:
        date_key = _text(row.get("date") or row.get("snapshot_date"))
        raw_value = row.get("setValue")
        if raw_value is None:
            raw_value = row.get("set_value")
        if raw_value is None:
            raw_value = row.get("value")
        value = _number(raw_value)
        if date_key and value is not None:
            by_date[date_key[:10]] = value
    return [{"date": key, "value": by_date[key]} for key in sorted(by_date)]


def _points_through(rows: Iterable[Mapping[str, Any]], through_date: str) -> List[Dict[str, Any]]:
    """Canonical points clamped to a point-in-time view: ``date <= through_date``.

    Defense in depth for direct callers that hand in a broader history than the
    CLI loader does. Observations after the target date must never make an
    otherwise valid historical build look stale. A MISSING target-date
    observation must still block, so this only drops future points - it never
    substitutes an earlier date for the required exact one.
    """
    limit = _text(through_date)[:10]
    points = _points(rows)
    if not limit:
        return points
    return [point for point in points if point["date"] <= limit]


def compute_window_movements(points: Sequence[Mapping[str, Any]]) -> Dict[str, Dict[str, Any]]:
    rows = _points(points)
    if len(rows) < 2:
        return {}
    latest = rows[-1]
    result: Dict[str, Dict[str, Any]] = {}
    for key, days in WINDOWS:
        partial = False
        if key == "1D":
            baseline = rows[-2]
            target_date = baseline["date"]
        elif days is None:
            baseline = rows[0]
            target_date = None
        else:
            # TRUE ELAPSED LOOKBACK, from the ONE canonical resolver. This used
            # to compute `latest - (days - 1)` here - an inclusive day COUNT -
            # so the Set Market's "7D" reached six elapsed days while the same
            # label on the global Market and on this Set's own Cards/Sealed
            # index reached seven. One label, three surfaces, one span.
            target_date = resolve_market_window_target(latest["date"], _CANONICAL_WINDOW_KEY[key])
            if rows[0]["date"] > target_date:
                baseline = rows[0]
                partial = True
            else:
                baseline = next((row for row in reversed(rows) if row["date"] <= target_date), rows[0])
        amount = latest["value"] - baseline["value"]
        result[key] = {
            "amount": amount,
            "percent": amount / baseline["value"] * 100,
            "startDate": baseline["date"],
            "endDate": latest["date"],
            "targetStartDate": target_date,
            "coverage": "partial" if partial else "full",
            "isSinceFirstAvailable": partial or days is None,
        }
    return result


def compact_trend(points: Sequence[Mapping[str, Any]], limit: int = MAX_TREND_POINTS, preserve_dates: Iterable[str] = ()) -> List[List[Any]]:
    rows = _points(points)
    if len(rows) <= limit:
        return [[row["date"], row["value"]] for row in rows]
    preserve = set(preserve_dates)
    selected = {0, len(rows) - 1, *[index for index, row in enumerate(rows) if row["date"] in preserve]}
    bucket_count = max(1, (limit - 2) // 2)
    for bucket in range(bucket_count):
        start = 1 + ((len(rows) - 2) * bucket // bucket_count)
        end = 1 + ((len(rows) - 2) * (bucket + 1) // bucket_count)
        chunk = list(enumerate(rows[start:end], start=start))
        if chunk:
            selected.add(min(chunk, key=lambda item: item[1]["value"])[0])
            selected.add(max(chunk, key=lambda item: item[1]["value"])[0])
    ordered = sorted(selected)
    if len(ordered) > limit:
        required = {0, len(rows) - 1, *[index for index, row in enumerate(rows) if row["date"] in preserve]}
        optional = [index for index in ordered if index not in required]
        optional_slots = max(0, limit - len(required))
        sampled = optional[::max(1, len(optional) // max(1, optional_slots))][:optional_slots]
        ordered = sorted(required | set(sampled))
    return [[rows[index]["date"], rows[index]["value"]] for index in ordered]


def build_global_set_value_row(
    sets: Iterable[Mapping[str, Any]],
    dashboard_snapshots: Sequence[Mapping[str, Any]],
    canonical_histories: Mapping[str, Sequence[Mapping[str, Any]]],
    *,
    target_market_date: str,
    built_at: Optional[str] = None,
    market_overview: Optional[Mapping[str, Any]] = None,
) -> Dict[str, Any]:
    eligible = [dict(row) for row in sets if row.get("supports_opening_simulation", True) is True and is_public_analytics_eligible(row)]
    # UI windows are slices, never snapshot row selectors. Ignore stale short
    # rows entirely and choose only the prepared long/current family.
    dashboard_by_set = {
        str(row.get("set_id")): row
        for row in dashboard_snapshots
        if str(row.get("window_key") or "365d").lower() == "365d"
    }
    missing, stale, mismatched, published = [], [], [], []
    generation = []
    for pokemon_set in eligible:
        set_id = str(pokemon_set.get("id") or pokemon_set.get("set_id") or "")
        dashboard = dashboard_by_set.get(set_id)
        canonical = _points_through(canonical_histories.get(set_id) or [], target_market_date)
        histories = dashboard.get("set_value_histories_json") if dashboard else None
        prepared = _points((histories or {}).get("standard") if isinstance(histories, Mapping) else [])
        if not dashboard or not canonical or not prepared:
            missing.append(set_id)
            continue
        dashboard_date = _text(dashboard.get("latest_market_date"))
        if dashboard_date != target_market_date or canonical[-1]["date"] != target_market_date:
            stale.append({"setId": set_id, "dashboardDate": dashboard_date, "canonicalDate": canonical[-1]["date"]})
            continue
        if prepared[-1]["date"] != canonical[-1]["date"] or abs(prepared[-1]["value"] - canonical[-1]["value"]) > 0.005:
            mismatched.append({"setId": set_id, "prepared": prepared[-1], "canonical": canonical[-1]})
            continue
        cards_market = dashboard.get("cardsMarket") if isinstance(dashboard.get("cardsMarket"), Mapping) else {}
        prepared_index = cards_market.get("marketIndex") if isinstance(cards_market.get("marketIndex"), Mapping) else None
        if prepared_index is not None and _text(prepared_index.get("asOf")) != target_market_date:
            stale.append({"setId": set_id, "dashboardDate": dashboard_date,
                          "indexDate": _text(prepared_index.get("asOf"))})
            continue
        windows = compute_window_movements(canonical)
        current = canonical[-1]
        published_row = {
            "setId": set_id,
            "canonicalKey": pokemon_set.get("canonical_key"),
            "name": pokemon_set.get("name"),
            "era": pokemon_set.get("era") or pokemon_set.get("era_name"),
            "logoUrl": pokemon_set.get("logo_image_url"),
            "symbolUrl": pokemon_set.get("symbol_image_url"),
            "currentSetValue": current["value"],
            "setValueAsOf": current["date"],
            # pricedCardCount/totalCardCount are deliberately NOT published. They
            # were read off `prepared[-1]`, but `_points()` normalizes every point
            # to {date, value} and strips that metadata, so both keys were always
            # None. No consumer reads them, so the compact snapshot omits them
            # rather than advertising two permanently-null fields.
            "windows": windows,
            "trend": compact_trend(canonical, preserve_dates=[window["startDate"] for window in windows.values()] + [current["date"]]),
            "recentDailyTrend": [[row["date"], row["value"]] for row in canonical[-MAX_RECENT_DAILY_TREND_POINTS:]],
            "historyStartDate": canonical[0]["date"],
            "historyEndDate": current["date"],
            "historyPointCount": len(canonical),
        }
        # Additive/backward-compatible: old dashboard rows have no Cards
        # Market contract and simply omit this field. Never substitute 100.
        if prepared_index is not None:
            published_row["marketIndex"] = {
                "currentValue": prepared_index.get("currentValue"),
                "baseValue": prepared_index.get("baseValue"),
                "asOf": prepared_index.get("asOf"),
                "movements": prepared_index.get("movements") if isinstance(prepared_index.get("movements"), Mapping) else {},
            }
        published.append(published_row)
        index_value = prepared_index.get("currentValue") if prepared_index is not None else None
        generation.append(f"{set_id}|{current['date']}|{current['value']:.6f}|{len(canonical)}|{index_value}")
    diagnostics = {"eligibleSetCount": len(eligible), "publishedSetCount": len(published), "missingSets": missing, "staleSets": stale, "mismatchedSets": mismatched}
    if missing or stale or mismatched or len(published) != len(eligible):
        raise ExploreSetValueUnavailable("eligible Market Set Value sources are incomplete or disagree", diagnostics=diagnostics)
    published.sort(key=lambda row: (-row["currentSetValue"], str(row["name"] or row["setId"])))
    built_at = built_at or datetime.now(timezone.utc).isoformat()
    index_generation = str((market_overview or {}).get("sourceGenerationFingerprint") or "")
    fingerprint = hashlib.sha256("\n".join([target_market_date, *sorted(generation), index_generation]).encode()).hexdigest()
    payload = {"marketOverview": dict(market_overview) if market_overview is not None else None,
               "sets": published, "meta": {"snapshot": {"builtAt": built_at, "marketDate": target_market_date}, "source": "canonical_standard_set_value_history", "windowSemantics": "marketDeltaWindows_v1", "trendPointLimit": MAX_TREND_POINTS, "recentDailyTrendPointLimit": MAX_RECENT_DAILY_TREND_POINTS, "warnings": []}}
    return {"tcg": "pokemon", "scope": "market", "payload_json": payload, "market_date": target_market_date, "set_count": len(published), "source_generation_fingerprint": fingerprint, "payload_size_bytes": len(json.dumps(payload, separators=(",", ":")).encode()), "_diagnostics": diagnostics}


def read_explore_set_value_snapshot(*, client: Any = None) -> Dict[str, Any]:
    active = client or service_read_client
    rows = list((active.table(TABLE).select("payload_json,market_date,updated_at,payload_size_bytes").eq("tcg", "pokemon").eq("scope", "market").limit(1).execute()).data or [])
    if not rows:
        raise ExploreSetValueUnavailable("global Market Set Value snapshot is unavailable")
    payload = dict(rows[0].get("payload_json") or {})
    payload["meta"] = {**(payload.get("meta") or {}), "source": TABLE, "payloadSizeBytes": rows[0].get("payload_size_bytes")}
    return payload


def upsert_explore_set_value_snapshot(row: Mapping[str, Any], *, client: Any) -> None:
    persisted = {key: value for key, value in row.items() if not str(key).startswith("_")}
    client.table(TABLE).upsert(persisted, on_conflict="tcg,scope").execute()
