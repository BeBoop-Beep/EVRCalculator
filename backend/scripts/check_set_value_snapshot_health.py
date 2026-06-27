from __future__ import annotations

import argparse
import json
import sys
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from backend.scripts.pokemon_snapshot_builders import (
    DEFAULT_DASHBOARD_WINDOW,
    get_client,
    list_pokemon_sets,
    resolve_set_row,
)
from backend.scripts.repair_set_value_market_day_dates import (
    MARKET_DAY_UTC_OFFSET,
    MARKET_DAY_TIMEZONE,
    latest_observation_utc_for_set,
    market_day_date_key,
)

SET_VALUE_SCOPES = ("standard", "hits", "top10")
DEFAULT_MAX_HITS_TO_STANDARD_RATIO = 1.05
DEFAULT_EXTREME_HITS_VALUE_THRESHOLD = 100000.0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Check Pokemon set value snapshot freshness")
    parser.add_argument("--set-id", help="Optional set id, canonical key, or Pokemon API set id")
    parser.add_argument("--window", default=DEFAULT_DASHBOARD_WINDOW, help="Market dashboard window key")
    parser.add_argument(
        "--max-hits-standard-ratio",
        type=float,
        default=DEFAULT_MAX_HITS_TO_STANDARD_RATIO,
        help="Flag hits set_value above this multiple of standard set_value. Default: 1.05.",
    )
    parser.add_argument(
        "--extreme-hits-threshold",
        type=float,
        default=DEFAULT_EXTREME_HITS_VALUE_THRESHOLD,
        help="Flag hits set_value above this absolute value. Default: 100000.",
    )
    parser.add_argument("--strict", action="store_true", help="Exit non-zero when stale snapshots exist")
    parser.add_argument("--json", action="store_true", dest="as_json", help="Emit JSON")
    return parser


def _date_key(value: Any) -> Optional[str]:
    text = str(value or "").strip()
    if not text:
        return None
    if len(text) >= 10:
        candidate = text[:10]
    else:
        candidate = text
    try:
        date.fromisoformat(candidate)
    except ValueError:
        return None
    return candidate


def _days_behind(raw_date: Optional[str], dashboard_date: Optional[str]) -> Optional[int]:
    raw = _date_key(raw_date)
    dashboard = _date_key(dashboard_date)
    if not raw or not dashboard:
        return None
    return (date.fromisoformat(raw) - date.fromisoformat(dashboard)).days


def _latest_raw_date_for_scope(client: Any, set_id: str, scope: str) -> Optional[str]:
    result = (
        client.table("pokemon_set_value_daily_history")
        .select("snapshot_date")
        .eq("set_id", set_id)
        .eq("value_scope", scope)
        .order("snapshot_date", desc=True)
        .limit(1)
        .execute()
    )
    rows = list(result.data or [])
    return _date_key(rows[0].get("snapshot_date")) if rows else None


def _to_float(value: Any) -> Optional[float]:
    try:
        if value is None:
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


def _to_int(value: Any) -> Optional[int]:
    try:
        if value is None:
            return None
        return int(value)
    except (TypeError, ValueError):
        return None


def _latest_raw_metrics_by_scope(client: Any, set_id: str) -> Dict[str, Dict[str, Any]]:
    try:
        result = (
            client.table("pokemon_set_value_daily_history")
            .select("snapshot_date,value_scope,set_value,priced_card_count")
            .eq("set_id", set_id)
            .in_("value_scope", list(SET_VALUE_SCOPES))
            .order("snapshot_date", desc=True)
            .limit(30)
            .execute()
        )
    except Exception:
        return {}

    metrics: Dict[str, Dict[str, Any]] = {}
    for row in result.data or []:
        scope = str(row.get("value_scope") or "")
        if scope not in SET_VALUE_SCOPES or scope in metrics:
            continue
        metrics[scope] = {
            "snapshot_date": _date_key(row.get("snapshot_date")),
            "set_value": _to_float(row.get("set_value")),
            "priced_card_count": _to_int(row.get("priced_card_count")),
        }
    return metrics


def _read_dashboard_row(client: Any, set_id: str, window: str) -> Optional[Dict[str, Any]]:
    result = (
        client.table("pokemon_set_market_dashboard_snapshot_latest")
        .select("set_id,window_key,latest_market_date,set_value_histories_json,payload_json,updated_at")
        .eq("set_id", set_id)
        .eq("window_key", window)
        .limit(1)
        .execute()
    )
    rows = list(result.data or [])
    return rows[0] if rows else None


def _latest_dashboard_history_date(row: Optional[Dict[str, Any]], scope: str) -> Optional[str]:
    if not row:
        return None
    histories = row.get("set_value_histories_json")
    if not isinstance(histories, dict):
        payload = row.get("payload_json") if isinstance(row.get("payload_json"), dict) else {}
        histories = payload.get("setValueHistoriesByScope") or payload.get("set_value_histories_by_scope") or {}
    history = histories.get(scope) if isinstance(histories, dict) else []
    dates = [
        _date_key((point or {}).get("date") or (point or {}).get("snapshotDate") or (point or {}).get("snapshot_date"))
        for point in (history if isinstance(history, list) else [])
        if isinstance(point, dict)
    ]
    return max((value for value in dates if value), default=None)


def _set_rows(client: Any, set_id: Optional[str]) -> List[Dict[str, Any]]:
    if set_id:
        return [resolve_set_row(client, set_id)]
    return list_pokemon_sets(client)


def _local_current_date() -> str:
    return (datetime.now(timezone.utc) + MARKET_DAY_UTC_OFFSET).date().isoformat()


def _is_after(left: Optional[str], right: Optional[str]) -> bool:
    left_key = _date_key(left)
    right_key = _date_key(right)
    return bool(left_key and right_key and left_key > right_key)


def _issue_row(
    set_row: Dict[str, Any],
    *,
    scope: str,
    reason: str,
    latest_raw_observation_utc: Optional[str],
    latest_observation_local_date: Optional[str],
    latest_set_value_snapshot_date: Optional[str],
    latest_market_dashboard_date: Optional[str],
    dashboard_history_date: Optional[str] = None,
    standard_value: Optional[float] = None,
    hits_value: Optional[float] = None,
    standard_priced_card_count: Optional[int] = None,
    hits_priced_card_count: Optional[int] = None,
) -> Dict[str, Any]:
    return {
        "canonical_key": set_row.get("canonical_key"),
        "name": set_row.get("name"),
        "set_id": str(set_row.get("id") or ""),
        "scope": scope,
        "reason": reason,
        "latest_raw_observation_utc": latest_raw_observation_utc,
        "latest_observation_local_date": latest_observation_local_date,
        "latest_set_value_snapshot_date": latest_set_value_snapshot_date,
        "latest_market_dashboard_date": latest_market_dashboard_date,
        "dashboard_history_date": dashboard_history_date,
        "standard_value": standard_value,
        "hits_value": hits_value,
        "standard_priced_card_count": standard_priced_card_count,
        "hits_priced_card_count": hits_priced_card_count,
    }


def analyze_set_value_snapshot_health(
    client: Any,
    *,
    set_id: Optional[str] = None,
    window: str = DEFAULT_DASHBOARD_WINDOW,
    local_current_date: Optional[str] = None,
    max_hits_standard_ratio: float = DEFAULT_MAX_HITS_TO_STANDARD_RATIO,
    extreme_hits_threshold: float = DEFAULT_EXTREME_HITS_VALUE_THRESHOLD,
) -> Dict[str, Any]:
    issue_rows: List[Dict[str, Any]] = []
    total_sets_with_raw_history = 0
    current_local_date = _date_key(local_current_date) or _local_current_date()

    for set_row in _set_rows(client, set_id):
        resolved_set_id = str(set_row.get("id") or "")
        if not resolved_set_id:
            continue
        dashboard_row = _read_dashboard_row(client, resolved_set_id, window)
        latest_market_date = _date_key((dashboard_row or {}).get("latest_market_date"))
        latest_raw_observation_utc = latest_observation_utc_for_set(client, resolved_set_id)
        latest_observation_local_date = market_day_date_key(latest_raw_observation_utc)
        raw_dates_by_scope = {
            scope: _latest_raw_date_for_scope(client, resolved_set_id, scope)
            for scope in SET_VALUE_SCOPES
        }
        raw_metrics_by_scope = _latest_raw_metrics_by_scope(client, resolved_set_id)
        if any(raw_dates_by_scope.values()):
            total_sets_with_raw_history += 1

        if _is_after(latest_market_date, current_local_date):
            issue_rows.append(
                _issue_row(
                    set_row,
                    scope="dashboard",
                    reason="market dashboard latest_market_date is after local current date",
                    latest_raw_observation_utc=latest_raw_observation_utc,
                    latest_observation_local_date=latest_observation_local_date,
                    latest_set_value_snapshot_date=max((date for date in raw_dates_by_scope.values() if date), default=None),
                    latest_market_dashboard_date=latest_market_date,
                )
            )
        elif latest_observation_local_date and latest_market_date and latest_market_date != latest_observation_local_date:
            issue_rows.append(
                _issue_row(
                    set_row,
                    scope="dashboard",
                    reason="market dashboard latest_market_date does not match latest observation local date",
                    latest_raw_observation_utc=latest_raw_observation_utc,
                    latest_observation_local_date=latest_observation_local_date,
                    latest_set_value_snapshot_date=max((date for date in raw_dates_by_scope.values() if date), default=None),
                    latest_market_dashboard_date=latest_market_date,
                )
            )

        for scope, raw_latest_date in raw_dates_by_scope.items():
            dashboard_scope_date = _latest_dashboard_history_date(dashboard_row, scope)
            if _is_after(raw_latest_date, current_local_date):
                issue_rows.append(
                    _issue_row(
                        set_row,
                        scope=scope,
                        reason="set value snapshot_date is after local current date",
                        latest_raw_observation_utc=latest_raw_observation_utc,
                        latest_observation_local_date=latest_observation_local_date,
                        latest_set_value_snapshot_date=raw_latest_date,
                        latest_market_dashboard_date=latest_market_date,
                        dashboard_history_date=dashboard_scope_date,
                    )
                )
                continue

            if raw_latest_date and latest_observation_local_date and raw_latest_date != latest_observation_local_date:
                issue_rows.append(
                    _issue_row(
                        set_row,
                        scope=scope,
                        reason="set value snapshot_date does not match latest observation local date",
                        latest_raw_observation_utc=latest_raw_observation_utc,
                        latest_observation_local_date=latest_observation_local_date,
                        latest_set_value_snapshot_date=raw_latest_date,
                        latest_market_dashboard_date=latest_market_date,
                        dashboard_history_date=dashboard_scope_date,
                    )
                )
                continue

            if not raw_latest_date:
                continue

            comparison_date = dashboard_scope_date or latest_market_date
            behind = _days_behind(raw_latest_date, comparison_date)
            if dashboard_row is None or comparison_date is None or (behind is not None and behind > 0):
                issue_rows.append(
                    _issue_row(
                        set_row,
                        scope=scope,
                        reason="market dashboard history is behind set value daily history",
                        latest_raw_observation_utc=latest_raw_observation_utc,
                        latest_observation_local_date=latest_observation_local_date,
                        latest_set_value_snapshot_date=raw_latest_date,
                        latest_market_dashboard_date=latest_market_date,
                        dashboard_history_date=dashboard_scope_date,
                    )
                )

        standard_metrics = raw_metrics_by_scope.get("standard") or {}
        hits_metrics = raw_metrics_by_scope.get("hits") or {}
        standard_value = _to_float(standard_metrics.get("set_value"))
        hits_value = _to_float(hits_metrics.get("set_value"))
        standard_priced_count = _to_int(standard_metrics.get("priced_card_count"))
        hits_priced_count = _to_int(hits_metrics.get("priced_card_count"))
        hits_snapshot_date = _date_key(hits_metrics.get("snapshot_date")) or raw_dates_by_scope.get("hits")

        if hits_value is not None and standard_value is not None and standard_value > 0:
            ratio = hits_value / standard_value
            if ratio > max_hits_standard_ratio:
                issue_rows.append(
                    _issue_row(
                        set_row,
                        scope="hits",
                        reason="hits set_value is implausibly above standard set_value",
                        latest_raw_observation_utc=latest_raw_observation_utc,
                        latest_observation_local_date=latest_observation_local_date,
                        latest_set_value_snapshot_date=hits_snapshot_date,
                        latest_market_dashboard_date=latest_market_date,
                        standard_value=standard_value,
                        hits_value=hits_value,
                        standard_priced_card_count=standard_priced_count,
                        hits_priced_card_count=hits_priced_count,
                    )
                )

        if (
            hits_priced_count is not None
            and standard_priced_count is not None
            and hits_priced_count > standard_priced_count
        ):
            issue_rows.append(
                _issue_row(
                    set_row,
                    scope="hits",
                    reason="hits priced_card_count exceeds standard priced_card_count",
                    latest_raw_observation_utc=latest_raw_observation_utc,
                    latest_observation_local_date=latest_observation_local_date,
                    latest_set_value_snapshot_date=hits_snapshot_date,
                    latest_market_dashboard_date=latest_market_date,
                    standard_value=standard_value,
                    hits_value=hits_value,
                    standard_priced_card_count=standard_priced_count,
                    hits_priced_card_count=hits_priced_count,
                )
            )

        if hits_value is not None and hits_value > extreme_hits_threshold:
            issue_rows.append(
                _issue_row(
                    set_row,
                    scope="hits",
                    reason="hits set_value exceeds extreme threshold",
                    latest_raw_observation_utc=latest_raw_observation_utc,
                    latest_observation_local_date=latest_observation_local_date,
                    latest_set_value_snapshot_date=hits_snapshot_date,
                    latest_market_dashboard_date=latest_market_date,
                    standard_value=standard_value,
                    hits_value=hits_value,
                    standard_priced_card_count=standard_priced_count,
                    hits_priced_card_count=hits_priced_count,
                )
            )

    issue_set_keys = {row["set_id"] for row in issue_rows}
    issue_rows.sort(
        key=lambda row: (
            str(row.get("reason") or ""),
            str(row.get("canonical_key") or ""),
            str(row.get("scope") or ""),
        )
    )

    return {
        "market_day_timezone": MARKET_DAY_TIMEZONE,
        "local_current_date": current_local_date,
        "total_sets_with_raw_history": total_sets_with_raw_history,
        "issue_set_count": len(issue_set_keys),
        "issue_scope_count": len(issue_rows),
        "stale_set_count": len(issue_set_keys),
        "stale_scope_count": len(issue_rows),
        "worst_days_behind": 0,
        "issues": issue_rows[:25],
        "stale_sets": issue_rows[:25],
    }


def print_text_report(report: Dict[str, Any]) -> None:
    issue_set_count = report.get("issue_set_count", report.get("stale_set_count", 0))
    issue_scope_count = report.get("issue_scope_count", report.get("stale_scope_count", 0))
    issues = report.get("issues", report.get("stale_sets", []))
    print(f"total_sets_with_raw_history = {report['total_sets_with_raw_history']}")
    print(f"market_day_timezone = {report.get('market_day_timezone')}")
    print(f"local_current_date = {report.get('local_current_date')}")
    print(f"issue_set_count = {issue_set_count}")
    print(f"issue_scope_count = {issue_scope_count}")
    print("first 25 issue set scopes:")
    for row in issues:
        print(
            "  "
            f"{row.get('canonical_key')} | {row.get('name')} | {row.get('scope')} | "
            f"reason={row.get('reason')} | latest_raw_utc={row.get('latest_raw_observation_utc')} | "
            f"latest_local={row.get('latest_observation_local_date')} | "
            f"set_value={row.get('latest_set_value_snapshot_date')} | "
            f"dashboard={row.get('latest_market_dashboard_date')} | "
            f"standard_value={row.get('standard_value')} | hits_value={row.get('hits_value')}"
        )


def main() -> None:
    args = build_parser().parse_args()
    report = analyze_set_value_snapshot_health(
        get_client(),
        set_id=args.set_id,
        window=args.window,
        max_hits_standard_ratio=args.max_hits_standard_ratio,
        extreme_hits_threshold=args.extreme_hits_threshold,
    )
    if args.as_json:
        print(json.dumps(report, indent=2, sort_keys=True))
    else:
        print_text_report(report)
    if args.strict and report["stale_set_count"] > 0:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
