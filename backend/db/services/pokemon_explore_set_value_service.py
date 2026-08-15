from __future__ import annotations

import hashlib
import json
from datetime import date, datetime, timedelta, timezone
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence

from backend.db.clients.supabase_client import public_read_client
from backend.desirability.public_analytics_policy import is_public_analytics_eligible

TABLE = "pokemon_explore_set_value_snapshot_latest"
WINDOWS = (("1D", 1), ("7D", 7), ("30D", 30), ("3M", 90), ("6M", 180), ("1Y", 365), ("lifetime", None))
MAX_TREND_POINTS = 48


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
            target_date = (date.fromisoformat(latest["date"]) - timedelta(days=days - 1)).isoformat()
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
        canonical = _points(canonical_histories.get(set_id) or [])
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
        windows = compute_window_movements(canonical)
        current = canonical[-1]
        published.append({
            "setId": set_id,
            "canonicalKey": pokemon_set.get("canonical_key"),
            "name": pokemon_set.get("name"),
            "era": pokemon_set.get("era") or pokemon_set.get("era_name"),
            "logoUrl": pokemon_set.get("logo_image_url"),
            "symbolUrl": pokemon_set.get("symbol_image_url"),
            "currentSetValue": current["value"],
            "setValueAsOf": current["date"],
            "pricedCardCount": (prepared[-1] if prepared else {}).get("pricedCardCount"),
            "totalCardCount": (prepared[-1] if prepared else {}).get("totalCardCount"),
            "windows": windows,
            "trend": compact_trend(canonical, preserve_dates=[window["startDate"] for window in windows.values()] + [current["date"]]),
            "historyStartDate": canonical[0]["date"],
            "historyEndDate": current["date"],
            "historyPointCount": len(canonical),
        })
        generation.append(f"{set_id}|{current['date']}|{current['value']:.6f}|{len(canonical)}")
    diagnostics = {"eligibleSetCount": len(eligible), "publishedSetCount": len(published), "missingSets": missing, "staleSets": stale, "mismatchedSets": mismatched}
    if missing or stale or mismatched or len(published) != len(eligible):
        raise ExploreSetValueUnavailable("eligible Market Set Value sources are incomplete or disagree", diagnostics=diagnostics)
    published.sort(key=lambda row: (-row["currentSetValue"], str(row["name"] or row["setId"])))
    built_at = built_at or datetime.now(timezone.utc).isoformat()
    fingerprint = hashlib.sha256("\n".join([target_market_date, *sorted(generation)]).encode()).hexdigest()
    payload = {"sets": published, "meta": {"snapshot": {"builtAt": built_at, "marketDate": target_market_date}, "source": "canonical_standard_set_value_history", "windowSemantics": "marketDeltaWindows_v1", "trendPointLimit": MAX_TREND_POINTS, "warnings": []}}
    return {"tcg": "pokemon", "scope": "market", "payload_json": payload, "market_date": target_market_date, "set_count": len(published), "source_generation_fingerprint": fingerprint, "payload_size_bytes": len(json.dumps(payload, separators=(",", ":")).encode()), "_diagnostics": diagnostics}


def read_explore_set_value_snapshot(*, client: Any = None) -> Dict[str, Any]:
    active = client or public_read_client
    rows = list((active.table(TABLE).select("payload_json,market_date,updated_at,payload_size_bytes").eq("tcg", "pokemon").eq("scope", "market").limit(1).execute()).data or [])
    if not rows:
        raise ExploreSetValueUnavailable("global Market Set Value snapshot is unavailable")
    payload = dict(rows[0].get("payload_json") or {})
    payload["meta"] = {**(payload.get("meta") or {}), "source": TABLE, "payloadSizeBytes": rows[0].get("payload_size_bytes")}
    return payload


def upsert_explore_set_value_snapshot(row: Mapping[str, Any], *, client: Any) -> None:
    persisted = {key: value for key, value in row.items() if not str(key).startswith("_")}
    client.table(TABLE).upsert(persisted, on_conflict="tcg,scope").execute()
