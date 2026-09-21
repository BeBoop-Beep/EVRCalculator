"""Bounded operator recovery for a blocked Price Storage V2 market date.

This command is intentionally narrow:
- it may rearm one explicitly named terminal row only when its persisted error
  matches an operator-supplied substring;
- the rearm preserves four consumed attempts, granting exactly one new queue
  attempt after a reviewed code/database fix;
- it refuses to proceed while any other terminal projection row remains;
- it advances only through the canonical staged application worker and exits
  nonzero if a new terminal failure appears or readiness is not reached within
  the bounded round count.

It does not publish public snapshots. Publication remains owned by the normal
post-scrape publication watchdog/wrapper after this projection gate is ready.
"""

from __future__ import annotations

import argparse
import json
import time
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from backend.db.clients.supabase_client import create_service_role_client
from backend.db.services.price_storage_v2_projection_gate import (
    advance_price_projection_once,
    evaluate_price_projection_gate,
)


QUEUE_TABLE = "price_storage_v2_shadow_queue"


def _queue_rows(client: Any, market_date: str) -> List[Dict[str, Any]]:
    return list(
        client.table(QUEUE_TABLE)
        .select("id,set_id,status,attempts,last_error,source_completed_at,started_at,completed_at,updated_at")
        .eq("market_date", market_date)
        .execute().data
        or []
    )


def _terminal_rows(rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    return [
        row
        for row in rows
        if str(row.get("status") or "").strip().lower() == "failed"
        and int(row.get("attempts") or 0) >= 5
    ]


def _rearm_exact_terminal(
    client: Any,
    *,
    market_date: str,
    set_id: str,
    expected_error_substring: str,
) -> Dict[str, Any]:
    rows = [
        row
        for row in _queue_rows(client, market_date)
        if str(row.get("set_id") or "") == str(set_id)
    ]
    if len(rows) != 1:
        raise RuntimeError(
            f"expected exactly one queue row for set_id={set_id}, found {len(rows)}"
        )

    row = rows[0]
    status = str(row.get("status") or "").strip().lower()
    attempts = int(row.get("attempts") or 0)
    error = str(row.get("last_error") or "")

    if status == "complete":
        return {"action": "already_complete", "row": row}
    if status in {"pending", "processing"}:
        return {"action": "already_retryable_or_active", "row": row}

    if status != "failed" or attempts < 5:
        raise RuntimeError(
            "refusing terminal rearm for unexpected queue state: "
            + json.dumps(row, default=str, sort_keys=True)
        )

    needle = str(expected_error_substring or "").strip()
    if not needle or needle.lower() not in error.lower():
        raise RuntimeError(
            "refusing terminal rearm because persisted error does not match "
            f"expected substring {needle!r}: "
            + json.dumps(row, default=str, sort_keys=True)
        )

    now = datetime.now(timezone.utc).isoformat()
    result = (
        client.table(QUEUE_TABLE)
        .update(
            {
                "status": "pending",
                "attempts": 4,
                "started_at": None,
                "completed_at": None,
                "last_error": (
                    "operator rearm after reviewed projection fix; "
                    f"previous_error={error[:1200]}"
                ),
                "updated_at": now,
            }
        )
        .eq("id", row["id"])
        .eq("status", "failed")
        .eq("attempts", attempts)
        .execute()
    )
    changed = list(result.data or [])
    if len(changed) != 1:
        raise RuntimeError("compare-and-set terminal rearm lost race")
    return {"action": "rearmed_one_final_attempt", "row": changed[0]}


def recover_projection(
    *,
    market_date: str,
    rearm_terminal_set_id: Optional[str],
    expected_error_substring: Optional[str],
    process_limit: int,
    max_rounds: int,
    sleep_seconds: float,
) -> Dict[str, Any]:
    client = create_service_role_client()

    rearm_report = None
    if rearm_terminal_set_id:
        rearm_report = _rearm_exact_terminal(
            client,
            market_date=market_date,
            set_id=rearm_terminal_set_id,
            expected_error_substring=str(expected_error_substring or ""),
        )
        print("targeted_rearm=" + json.dumps(rearm_report, default=str, sort_keys=True))

    terminal = _terminal_rows(_queue_rows(client, market_date))
    if terminal:
        print("terminal_rows_before_advance=" + json.dumps(terminal, default=str, sort_keys=True))
        raise RuntimeError("terminal projection rows remain before bounded advance")

    last_after: Dict[str, Any] = {}
    for round_number in range(1, max(1, int(max_rounds)) + 1):
        report = advance_price_projection_once(
            client,
            market_date,
            process_limit=max(1, min(int(process_limit), 20)),
        )
        after = dict(report.get("after") or {})
        last_after = after
        process_result = report.get("process_result") or {}
        print(
            "projection_round="
            + json.dumps(
                {
                    "round": round_number,
                    "processed": process_result.get("processed"),
                    "completed": process_result.get("completed"),
                    "failed": process_result.get("failed"),
                    "after": after,
                },
                default=str,
                sort_keys=True,
            )
        )

        if int(after.get("terminal_failed_set_count") or 0) > 0:
            terminal = _terminal_rows(_queue_rows(client, market_date))
            print(
                "terminal_rows_after_advance="
                + json.dumps(terminal, default=str, sort_keys=True)
            )
            raise RuntimeError("terminal projection failure detected")

        if bool(after.get("ready")):
            return {
                "market_date": market_date,
                "ready": True,
                "rounds": round_number,
                "rearm": rearm_report,
                "after": after,
            }

        if sleep_seconds > 0:
            time.sleep(float(sleep_seconds))

    final_decision = evaluate_price_projection_gate(client, market_date)
    final_payload = final_decision.to_dict()
    print("projection_final=" + json.dumps(final_payload, default=str, sort_keys=True))
    return {
        "market_date": market_date,
        "ready": bool(final_decision.ready),
        "rounds": max(1, int(max_rounds)),
        "rearm": rearm_report,
        "after": final_payload,
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--market-date", required=True)
    parser.add_argument("--rearm-terminal-set-id")
    parser.add_argument("--expected-error-substring")
    parser.add_argument("--process-limit", type=int, default=10)
    parser.add_argument("--max-rounds", type=int, default=30)
    parser.add_argument("--sleep-seconds", type=float, default=5.0)
    return parser


def main(argv: Optional[List[str]] = None) -> int:
    args = build_parser().parse_args(argv)
    if args.rearm_terminal_set_id and not args.expected_error_substring:
        raise SystemExit("--expected-error-substring is required with --rearm-terminal-set-id")

    report = recover_projection(
        market_date=str(args.market_date)[:10],
        rearm_terminal_set_id=args.rearm_terminal_set_id,
        expected_error_substring=args.expected_error_substring,
        process_limit=args.process_limit,
        max_rounds=args.max_rounds,
        sleep_seconds=args.sleep_seconds,
    )
    print("recovery_summary=" + json.dumps(report, default=str, sort_keys=True))
    return 0 if report.get("ready") else 2


if __name__ == "__main__":
    raise SystemExit(main())
