"""Repair missing Market-root Set Value rows for one promoted market date.

This is the post-scrape safety net for a very specific failure mode: card-price
persistence succeeds, but the best-effort derived Set Value refresh triggered
from Cards ingestion exhausts its transient retries (typically SQLSTATE 57014).
The scrape job is intentionally allowed to finish because the source prices are
already durable; publication, however, cannot advance until every canonical
Market root has both Standard and Top-10 Set Value rows for the target date.

The repair is bounded and idempotent:
- it only targets canonical Market roots,
- it only refreshes sets missing an accepted scope row for the requested date,
- each RPC is bounded to exactly that date,
- transient data-service failures are retried with a fresh Supabase client,
- the command rechecks coverage after every pass and fails closed if gaps remain.
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
import time
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, Sequence, Set

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.db.clients.supabase_client import create_service_role_client
from backend.db.services.market_date_quality import REQUIRED_VALUE_SCOPES
from backend.db.services.pokemon_market_rollout_cohort import resolve_market_root_ids
from backend.db.services.supabase_persistence_retry import run_supabase_with_transient_retry

logger = logging.getLogger("repair_missing_market_set_value_history")

SOURCE_TABLE = "pokemon_set_value_daily_history"
REFRESH_RPC = "refresh_pokemon_set_value_daily_history"
READ_CHUNK_SIZE = 20
DEFAULT_MAX_PASSES = 3
DEFAULT_RETRY_ATTEMPTS = 5


def _clean_ids(values: Iterable[Any]) -> List[str]:
    return sorted({str(value).strip() for value in values if str(value or "").strip()})


def _read_present_scopes(
    client: Any,
    *,
    market_date: str,
    set_ids: Sequence[str],
) -> Dict[str, Set[str]]:
    present: Dict[str, Set[str]] = {set_id: set() for set_id in set_ids}
    scopes = list(REQUIRED_VALUE_SCOPES)
    for offset in range(0, len(set_ids), READ_CHUNK_SIZE):
        chunk = list(set_ids[offset:offset + READ_CHUNK_SIZE])

        def read_page(fresh_client: Any, _attempt: int):
            return (
                fresh_client.table(SOURCE_TABLE)
                .select("set_id,value_scope,set_value,priced_card_count")
                .in_("set_id", chunk)
                .in_("value_scope", scopes)
                .eq("snapshot_date", market_date)
                .execute()
            )

        result = run_supabase_with_transient_retry(
            read_page,
            operation_name=f"market_set_value_coverage_{offset // READ_CHUNK_SIZE}",
            max_attempts=DEFAULT_RETRY_ATTEMPTS,
        )
        for row in list(result.data or []):
            set_id = str(row.get("set_id") or "")
            scope = str(row.get("value_scope") or "")
            try:
                value = float(row.get("set_value") or 0)
                count = int(row.get("priced_card_count") or 0)
            except (TypeError, ValueError):
                continue
            if set_id in present and scope in REQUIRED_VALUE_SCOPES and value > 0 and count > 0:
                present[set_id].add(scope)
    return present


def missing_market_root_set_ids(
    client: Any,
    *,
    market_date: str,
    set_ids: Sequence[str] | None = None,
) -> List[str]:
    roots = _clean_ids(set_ids if set_ids is not None else resolve_market_root_ids(
        client, market_date=market_date
    ))
    if not roots:
        raise RuntimeError(f"no canonical Market roots resolved for {market_date}")
    present = _read_present_scopes(client, market_date=market_date, set_ids=roots)
    required = set(REQUIRED_VALUE_SCOPES)
    return [set_id for set_id in roots if present.get(set_id, set()) != required]


def _refresh_one(set_id: str, market_date: str) -> int:
    def refresh(client: Any, _attempt: int):
        return client.rpc(
            REFRESH_RPC,
            {
                "p_set_id": set_id,
                "p_start_date": market_date,
                "p_end_date": market_date,
            },
        ).execute()

    result = run_supabase_with_transient_retry(
        refresh,
        operation_name=f"repair_market_set_value_{set_id}",
        max_attempts=DEFAULT_RETRY_ATTEMPTS,
    )
    try:
        return int(result.data or 0)
    except (TypeError, ValueError):
        return 0


def repair_missing_market_set_values(
    client: Any,
    *,
    market_date: str,
    commit: bool,
    max_passes: int = DEFAULT_MAX_PASSES,
    sleep_seconds: float = 2.0,
    set_ids: Sequence[str] | None = None,
) -> Dict[str, Any]:
    target = str(market_date)[:10]
    roots = _clean_ids(set_ids if set_ids is not None else resolve_market_root_ids(
        client, market_date=target
    ))
    if not roots:
        raise RuntimeError(f"no canonical Market roots resolved for {target}")

    before = missing_market_root_set_ids(client, market_date=target, set_ids=roots)
    refreshed_rows = 0
    failures: List[Mapping[str, str]] = []
    passes_run = 0

    if commit:
        remaining = list(before)
        for pass_index in range(1, max(1, int(max_passes)) + 1):
            if not remaining:
                break
            passes_run = pass_index
            logger.info(
                "repair pass=%s market_date=%s missing_sets=%s",
                pass_index, target, len(remaining),
            )
            for set_id in remaining:
                try:
                    refreshed_rows += _refresh_one(set_id, target)
                except Exception as exc:
                    failures.append({
                        "set_id": set_id,
                        "pass": str(pass_index),
                        "error": str(exc),
                    })
                    logger.warning(
                        "set value repair failed set_id=%s pass=%s error=%s",
                        set_id, pass_index, exc,
                    )
            remaining = missing_market_root_set_ids(
                client, market_date=target, set_ids=roots
            )
            if remaining and pass_index < max(1, int(max_passes)):
                time.sleep(max(0.0, float(sleep_seconds)))

    after = missing_market_root_set_ids(client, market_date=target, set_ids=roots)
    report = {
        "market_date": target,
        "root_count": len(roots),
        "required_scopes": list(REQUIRED_VALUE_SCOPES),
        "missing_before_count": len(before),
        "missing_before_set_ids": before,
        "missing_after_count": len(after),
        "missing_after_set_ids": after,
        "refreshed_rows": refreshed_rows,
        "passes_run": passes_run,
        "failure_count": len(failures),
        "failures": failures[-20:],
        "mode": "commit" if commit else "dry_run",
        "ok": (not after) if commit else True,
    }
    return report


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--market-date", required=True)
    parser.add_argument("--commit", action="store_true")
    parser.add_argument("--max-passes", type=int, default=DEFAULT_MAX_PASSES)
    parser.add_argument("--sleep-seconds", type=float, default=2.0)
    return parser


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    args = build_parser().parse_args()
    client = create_service_role_client()
    try:
        report = repair_missing_market_set_values(
            client,
            market_date=args.market_date,
            commit=bool(args.commit),
            max_passes=args.max_passes,
            sleep_seconds=args.sleep_seconds,
        )
    except Exception as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, indent=2, sort_keys=True))
        return 1
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
