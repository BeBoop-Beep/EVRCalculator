"""Price-independent, lookahead-safe contracts for longitudinal RIP research."""
from __future__ import annotations

from datetime import date, datetime
import hashlib
import json
from typing import Any, Iterable, Mapping, Optional, Sequence

QUALITY_READY = "READY"
QUALITY_PARTIAL = "PARTIAL"
QUALITY_UNAVAILABLE = "UNAVAILABLE"
QUALITY_RECONSTRUCTED = "RECONSTRUCTED_VALIDATED"
QUALITY_BLOCKED = "BLOCKED_SOURCE_GAP"
ANALYTIC_QUALITY = frozenset({QUALITY_READY, QUALITY_RECONSTRUCTED})


def canonical_hash(value: Any) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"), default=str).encode()).hexdigest()


def cohort_identity(set_ids: Iterable[str]) -> dict[str, Any]:
    ids = sorted(set(map(str, set_ids)))
    return {"eligibleSetIds": ids, "cohortCount": len(ids), "cohortFingerprint": canonical_hash(ids)}


def select_as_of_source(runs: Sequence[Mapping[str, Any]], *, source_name: str,
                        as_of: date, timeframe: Optional[str] = None) -> Optional[Mapping[str, Any]]:
    eligible = []
    for run in runs:
        if run.get("source_name") != source_name or run.get("status") != "success":
            continue
        if timeframe is not None and (run.get("raw_payload_json") or {}).get("timeframe") != timeframe:
            continue
        captured = datetime.fromisoformat(str(run["captured_at"]).replace("Z", "+00:00")).date()
        if captured <= as_of:
            eligible.append((captured, str(run.get("id")), run))
    return max(eligible, default=(None, None, None))[2]


def source_effective_periods(runs: Sequence[Mapping[str, Any]], max_age_days: int) -> list[dict[str, Any]]:
    ordered = sorted(runs, key=lambda r: (str(r["captured_at"]), str(r.get("id"))))
    result = []
    for index, run in enumerate(ordered):
        start = datetime.fromisoformat(str(run["captured_at"]).replace("Z", "+00:00")).date()
        natural_end = date.fromordinal(start.toordinal() + max_age_days)
        next_start = (datetime.fromisoformat(str(ordered[index + 1]["captured_at"]).replace("Z", "+00:00")).date()
                      if index + 1 < len(ordered) else None)
        end = min(natural_end, date.fromordinal(next_start.toordinal() - 1)) if next_start else natural_end
        result.append({"sourceRunId": str(run.get("id")), "sourceObservationDate": start.isoformat(),
                       "effectiveFrom": start.isoformat(), "effectiveUntil": end.isoformat()})
    return result


def historical_v7_availability(as_of: date, selections: Mapping[str, Any]) -> dict[str, Any]:
    required = ("pokemon_trends", "trainer_12m", "trainer_5y", "artist_12m", "artist_5y", "playability")
    missing = [key for key in required if not selections.get(key)]
    if missing:
        return {"collectorAvailable": False, "qualityStatus": QUALITY_BLOCKED,
                "unavailableReasons": [f"{key}_unavailable" for key in missing]}
    future = [key for key in required if datetime.fromisoformat(str(selections[key]["captured_at"]).replace("Z", "+00:00")).date() > as_of]
    if future:
        raise ValueError(f"future source leakage: {future}")
    return {"collectorAvailable": True, "qualityStatus": QUALITY_RECONSTRUCTED,
            "unavailableReasons": [], "sourceRunIds": [str(selections[k]["id"]) for k in required]}


def historical_features(points: Sequence[Mapping[str, Any]], *, as_of: date, value_key: str) -> dict[str, Any]:
    eligible = [p for p in points if date.fromisoformat(str(p["as_of_date"])) <= as_of and p.get("quality_status") in ANALYTIC_QUALITY]
    if any(date.fromisoformat(str(p["as_of_date"])) > as_of for p in eligible):
        raise ValueError("future observation entered feature window")
    values = [float(p[value_key]) for p in eligible if p.get(value_key) is not None]
    if not values:
        return {"n": 0, "available": False}
    ordered = sorted(eligible, key=lambda p: str(p["as_of_date"]))
    peak = max(values); current = float(ordered[-1][value_key])
    return {"n": len(values), "available": True, "current": current,
            "mean": sum(values) / len(values), "median": sorted(values)[len(values)//2],
            "peakToCurrentDrawdown": (peak-current)/peak if peak else None}


def history_identity(row: Mapping[str, Any]) -> tuple[str, str, str]:
    return str(row["set_id"]), str(row["as_of_date"]), str(row["collector_model_version"])


def assert_idempotent(rows: Sequence[Mapping[str, Any]]) -> None:
    identities = [history_identity(row) for row in rows]
    if len(identities) != len(set(identities)):
        raise ValueError("duplicate date/set/model historical identity")
