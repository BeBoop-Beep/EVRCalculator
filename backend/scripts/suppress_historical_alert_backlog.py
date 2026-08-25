"""Explicitly suppress historical alert delivery without deleting incident rows."""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from backend.db.clients.supabase_client import supabase


def _timestamp(value: str) -> str:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise argparse.ArgumentTypeError("--before must include a timezone")
    return parsed.astimezone(timezone.utc).isoformat()


def load_candidates(client: Any, before: str) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    offset = 0
    while True:
        page = list((client.table("alert_events")
                     .select("id,alert_type,severity,created_at")
                     .eq("sent", False).is_("suppressed_at", "null")
                     .lt("created_at", before).order("created_at", desc=False)
                     .range(offset, offset + 999).execute()).data or [])
        rows.extend(page)
        if len(page) < 1000:
            return rows
        offset += 1000


def summarize(rows: list[dict[str, Any]], before: str) -> dict[str, Any]:
    dates = [str(row.get("created_at")) for row in rows if row.get("created_at")]
    breakdown = Counter(f"{row.get('alert_type', 'unknown')}|{row.get('severity', 'unknown')}" for row in rows)
    return {"before": before, "row_count": len(rows), "oldest": min(dates) if dates else None,
            "newest": max(dates) if dates else None, "breakdown": dict(sorted(breakdown.items()))}


def suppress(client: Any, rows: list[dict[str, Any]], *, reason: str) -> int:
    ids = [row["id"] for row in rows]
    suppressed_at = datetime.now(timezone.utc).isoformat()
    updated = 0
    for start in range(0, len(ids), 100):
        chunk = ids[start:start + 100]
        result = (client.table("alert_events")
                  .update({"suppressed_at": suppressed_at, "suppression_reason": reason})
                  .in_("id", chunk).eq("sent", False).is_("suppressed_at", "null").execute())
        updated += len(result.data or [])
    return updated


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--before", required=True, type=_timestamp)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--dry-run", action="store_true")
    mode.add_argument("--commit", action="store_true")
    parser.add_argument("--reason", default="historical backlog suppressed before Slack activation")
    args = parser.parse_args()
    rows = load_candidates(supabase, args.before)
    report = summarize(rows, args.before)
    report["mode"] = "commit" if args.commit else "dry-run"
    report["updated"] = suppress(supabase, rows, reason=args.reason) if args.commit else 0
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
