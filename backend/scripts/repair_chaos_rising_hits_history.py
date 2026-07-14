from __future__ import annotations

import argparse
import json
import logging
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from backend.scripts.pokemon_snapshot_builders import (
    DEFAULT_DASHBOARD_DAYS,
    build_coordinated_set_market_snapshot_rows,
    get_client,
    resolve_set_row,
    upsert_row,
    upsert_rows,
)
from backend.scripts.set_value_scope_invariants import audit_set_value_scope_rows


logger = logging.getLogger("repair_chaos_rising_hits_history")

CHAOS_RISING_SET_ID = "5bdbfae1-3f2e-44e7-b8c9-1035ad45b896"
TARGET_SCOPE = "hits"
TARGET_DATES = ("2026-06-16", "2026-06-17", "2026-06-18", "2026-06-19")
REPLACEMENT_SOURCE_DATE = "2026-06-20"
REPLACEMENT_VALUE = 968.34
REPAIR_SOURCE = "historical_correction:hits:carried_backward_from:2026-06-20:known_valid"


def _target_rows(client: Any) -> List[Dict[str, Any]]:
    return list(
        client.table("pokemon_set_value_daily_history")
        .select(
            "id,set_id,snapshot_date,value_scope,set_value,priced_card_count,total_card_count,"
            "canonical_card_count,linked_card_count,included_card_count,coverage_pct,source,updated_at"
        )
        .eq("set_id", CHAOS_RISING_SET_ID)
        .eq("value_scope", TARGET_SCOPE)
        .in_("snapshot_date", list(TARGET_DATES))
        .order("snapshot_date")
        .execute()
        .data
        or []
    )


def build_repair_plan(rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    by_date = {str(row.get("snapshot_date"))[:10]: row for row in rows}
    plan: List[Dict[str, Any]] = []
    for date_key in TARGET_DATES:
        row = by_date.get(date_key)
        if row is None:
            raise RuntimeError(f"Missing targeted Chaos Rising Hits row for {date_key}")
        old_value = float(row.get("set_value"))
        would_change = old_value != REPLACEMENT_VALUE or row.get("source") != REPAIR_SOURCE
        plan.append(
            {
                "rowId": row.get("id"),
                "setId": CHAOS_RISING_SET_ID,
                "set": "chaosRising",
                "scope": TARGET_SCOPE,
                "date": date_key,
                "oldValue": old_value,
                "replacementValue": REPLACEMENT_VALUE,
                "replacementSourceDate": REPLACEMENT_SOURCE_DATE,
                "source": REPAIR_SOURCE,
                "wouldChange": would_change,
            }
        )
    return plan


def apply_repair_plan(client: Any, plan: List[Dict[str, Any]], *, commit: bool) -> int:
    if not commit:
        return 0
    changed = 0
    updated_at = datetime.now(timezone.utc).isoformat()
    for item in plan:
        if not item["wouldChange"]:
            continue
        result = (
            client.table("pokemon_set_value_daily_history")
            .update({"set_value": REPLACEMENT_VALUE, "source": REPAIR_SOURCE, "updated_at": updated_at})
            .eq("id", item["rowId"])
            .eq("set_id", CHAOS_RISING_SET_ID)
            .eq("value_scope", TARGET_SCOPE)
            .eq("snapshot_date", item["date"])
            .execute()
        )
        rows = list(result.data or [])
        if len(rows) != 1:
            raise RuntimeError(f"Repair updated {len(rows)} rows for {item['date']}; expected exactly one")
        changed += 1
    return changed


def _existing_dashboard_windows(client: Any) -> List[Dict[str, Any]]:
    return list(
        client.table("pokemon_set_market_dashboard_snapshot_latest")
        .select("window_key,snapshot_days:payload_json->days,set_value_histories_json")
        .eq("set_id", CHAOS_RISING_SET_ID)
        .order("window_key")
        .execute()
        .data
        or []
    )


def _window_needs_rebuild(row: Dict[str, Any]) -> bool:
    histories = row.get("set_value_histories_json") if isinstance(row.get("set_value_histories_json"), dict) else {}
    hits = histories.get("hits") if isinstance(histories.get("hits"), list) else []
    values_by_date = {
        str(point.get("date") or point.get("snapshot_date") or point.get("snapshotDate"))[:10]: float(
            point.get("setValue") if point.get("setValue") is not None else point.get("set_value")
        )
        for point in hits
        if isinstance(point, dict) and (point.get("date") or point.get("snapshot_date") or point.get("snapshotDate"))
    }
    return any(values_by_date.get(date_key) != REPLACEMENT_VALUE for date_key in TARGET_DATES)


def rebuild_existing_dashboards(client: Any, set_row: Dict[str, Any], *, force: bool, commit: bool) -> List[str]:
    rebuilt: List[str] = []
    for existing in _existing_dashboard_windows(client):
        window = str(existing.get("window_key") or "365d")
        if not force and not _window_needs_rebuild(existing):
            continue
        try:
            days = int(existing.get("snapshot_days") or "")
        except (TypeError, ValueError):
            digits = "".join(character for character in window if character.isdigit())
            days = int(digits) if digits else DEFAULT_DASHBOARD_DAYS
        cards_row, dashboard_row, top_chase_history_rows = build_coordinated_set_market_snapshot_rows(
            set_row,
            days=days,
            window=window,
            client=client,
        )
        upsert_row(
            client,
            "pokemon_set_cards_snapshot_latest",
            cards_row,
            on_conflict="set_id",
            commit=commit,
        )
        upsert_rows(
            client,
            "pokemon_set_top_chase_card_daily_history",
            top_chase_history_rows,
            on_conflict="set_id,snapshot_date,rank",
            commit=commit,
        )
        upsert_row(
            client,
            "pokemon_set_market_dashboard_snapshot_latest",
            dashboard_row,
            on_conflict="set_id,window_key",
            commit=commit,
        )
        rebuilt.append(window)
    return rebuilt


def _post_repair_audit(client: Any) -> Dict[str, Any]:
    rows = list(
        client.table("pokemon_set_value_daily_history")
        .select("set_id,snapshot_date,value_scope,set_value")
        .eq("set_id", CHAOS_RISING_SET_ID)
        .order("snapshot_date")
        .execute()
        .data
        or []
    )
    return audit_set_value_scope_rows(rows)


def main() -> int:
    parser = argparse.ArgumentParser(description="Repair the four corrupt Chaos Rising Hits history rows")
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--dry-run", action="store_true", help="Report exact changes without writing (default)")
    mode.add_argument("--commit", action="store_true", help="Apply the repair and rebuild existing dashboard windows")
    parser.add_argument("--verbose", action="store_true")
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO if args.verbose else logging.WARNING, format="%(levelname)s %(message)s")

    client = get_client()
    set_row = resolve_set_row(client, CHAOS_RISING_SET_ID)
    plan = build_repair_plan(_target_rows(client))
    changed = apply_repair_plan(client, plan, commit=bool(args.commit))
    rebuilt = rebuild_existing_dashboards(
        client,
        set_row,
        force=changed > 0,
        commit=bool(args.commit),
    ) if args.commit else []
    report = {
        "mode": "commit" if args.commit else "dry-run",
        "set": {
            "id": CHAOS_RISING_SET_ID,
            "canonicalKey": set_row.get("canonical_key"),
            "name": set_row.get("name"),
        },
        "scope": TARGET_SCOPE,
        "rowsTargeted": len(plan),
        "rowsChanged": changed,
        "snapshotWindowsRebuilt": rebuilt,
        "rows": plan,
        "audit": _post_repair_audit(client) if args.commit else None,
    }
    print(json.dumps(report, indent=2, sort_keys=True, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
