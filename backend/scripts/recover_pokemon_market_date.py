"""Fail-fast recovery of explicit, already-scraped Pokémon market dates."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from datetime import date, timedelta
from typing import Any, Dict, List, Optional, Sequence

from backend.db.clients.supabase_client import supabase


def _dates(start: str, end: str) -> List[str]:
    first, last = date.fromisoformat(start), date.fromisoformat(end)
    if first > last:
        raise ValueError("start-date must not be after end-date")
    return [(first + timedelta(days=offset)).isoformat() for offset in range((last - first).days + 1)]


def verify_complete_batch(client: Any, market_date: str) -> Dict[str, Any]:
    rows = list((client.table("pokemon_scrape_batches")
                 .select("id,market_date,status,expected_set_count,succeeded_set_count,missing_set_count,"
                         "promoted_at,runtime_git_sha,runtime_registry_hash")
                 .eq("market_date", market_date).limit(1).execute()).data or [])
    if not rows:
        raise RuntimeError(f"no scrape batch exists for {market_date}")
    batch = rows[0]
    if (batch.get("status") != "complete" or int(batch.get("missing_set_count") or 0) != 0
            or int(batch.get("succeeded_set_count") or 0) < int(batch.get("expected_set_count") or 0)):
        raise RuntimeError(f"scrape batch for {market_date} is not complete: {batch}")
    return batch


def _run(command: List[str], runner: Any) -> Dict[str, Any]:
    completed = runner(command, capture_output=True, text=True, check=False)
    if completed.returncode != 0:
        raise RuntimeError(f"command failed ({completed.returncode}): {' '.join(command)}\n{completed.stdout[-1000:]}\n{completed.stderr[-1000:]}")
    try:
        payload = json.loads(completed.stdout)
    except (TypeError, json.JSONDecodeError):
        payload = {"stdout": completed.stdout[-2000:]}
    return {"command": command, "exit_code": completed.returncode, "result": payload}


def recover_range(client: Any, *, start: str, end: str, commit: bool,
                  runner: Any = subprocess.run) -> Dict[str, Any]:
    results = []
    for market_date in _dates(start, end):
        batch = verify_complete_batch(client, market_date)
        if not commit:
            results.append({"market_date": market_date, "batch_complete": True, "mode": "dry_run"})
            continue
        repair = _run([sys.executable, "backend/scripts/repair_pokemon_set_value_history.py",
                       "--start-date", market_date, "--end-date", market_date, "--all", "--commit"], runner)
        snapshots = _run([sys.executable, "backend/scripts/refresh_stale_public_snapshots.py",
                          "--market-date", market_date, "--commit", "--strict"], runner)
        audit = _run([sys.executable, "backend/scripts/audit_pokemon_market_publication.py",
                      "--market-date", market_date, "--phase", "post-scrape", "--json"], runner)
        audit_result = audit.get("result") if isinstance(audit.get("result"), dict) else {}
        results.append({"market_date": market_date, "batch_complete": True,
                        "runtime_git_sha": batch.get("runtime_git_sha"),
                        "runtime_registry_hash": batch.get("runtime_registry_hash"),
                        "set_value_refreshed": True,
                        "reconciliation": repair["result"].get("reconciliation_after"),
                        "quality_status": audit_result.get("quality_status"),
                        "publication_status": "passed" if audit_result.get("passed") else "failed",
                        "snapshot_dates": audit_result.get("snapshot_dates") or audit_result.get("actual_dates"),
                        "snapshots": snapshots, "publication_audit": audit, "repair": repair})
    return {"ok": True, "mode": "commit" if commit else "dry_run", "dates": results}


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--market-date")
    parser.add_argument("--start-date")
    parser.add_argument("--end-date")
    parser.add_argument("--commit", action="store_true")
    args = parser.parse_args(argv)
    start = args.market_date or args.start_date
    end = args.market_date or args.end_date
    if not start or not end:
        parser.error("provide --market-date or both --start-date and --end-date")
    try:
        report = recover_range(supabase, start=start, end=end, commit=args.commit)
    except Exception as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, indent=2))
        return 1
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
