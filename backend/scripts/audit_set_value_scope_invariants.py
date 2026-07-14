from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Dict, List

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from backend.scripts.pokemon_snapshot_builders import get_client
from backend.scripts.set_value_scope_invariants import audit_set_value_scope_rows


def _all_rows(client: Any) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    start = 0
    while True:
        page = list(
            client.table("pokemon_set_value_daily_history")
            .select("set_id,snapshot_date,value_scope,set_value")
            .order("set_id")
            .order("snapshot_date")
            .range(start, start + 999)
            .execute()
            .data
            or []
        )
        rows.extend(page)
        if len(page) < 1000:
            return rows
        start += 1000


def main() -> int:
    parser = argparse.ArgumentParser(description="Audit persisted Pokemon Set Value scope invariants")
    parser.add_argument("--strict", action="store_true", help="Exit non-zero when hard failures exist")
    args = parser.parse_args()
    report = audit_set_value_scope_rows(_all_rows(get_client()))
    print(json.dumps(report, indent=2, sort_keys=True, default=str))
    return 1 if args.strict and report["hardFailureCount"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
