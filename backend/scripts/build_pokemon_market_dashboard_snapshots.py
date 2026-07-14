from __future__ import annotations

import argparse
import logging
import sys
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from backend.db.services.pokemon_set_market_service import PokemonSetMarketError
from backend.db.services.data_service_health import is_transient_data_service_error
from backend.scripts.snapshot_query_retry import run_snapshot_operation_with_retry
from backend.scripts.pokemon_snapshot_builders import (
    DEFAULT_DASHBOARD_DAYS,
    DEFAULT_DASHBOARD_WINDOW,
    add_target_set_args,
    build_coordinated_set_market_snapshot_rows,
    get_client,
    refresh_canonical_card_market_prices_for_set,
    resolve_target_sets,
    should_commit,
    snapshot_service_client_scope,
    upsert_row,
    upsert_rows,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Build coordinated Pokemon Cards and Market Dashboard snapshots"
    )
    add_target_set_args(parser)
    parser.add_argument("--days", type=int, default=DEFAULT_DASHBOARD_DAYS, help="History days to include")
    parser.add_argument("--window", default=DEFAULT_DASHBOARD_WINDOW, help="Snapshot window key")
    parser.add_argument(
        "--delay-seconds",
        type=float,
        default=0.35,
        help="Delay between sets for --all builds; use 0 to disable pacing",
    )
    parser.add_argument(
        "--max-consecutive-transient-failures",
        type=int,
        default=3,
        help="Stop an --all build after this many consecutive exhausted transient failures",
    )
    return parser


def _set_label(set_row: dict) -> str:
    return f"set_id={set_row.get('id')} name={set_row.get('name')}"


def _is_missing_data_error(exc: Exception) -> bool:
    if isinstance(exc, PokemonSetMarketError):
        return (
            getattr(exc, "status_code", None) == 404
            or "not found" in str(getattr(exc, "message", exc)).lower()
            or "no " in str(getattr(exc, "message", exc)).lower()
        )
    return False


def _error_code(exc: Exception) -> str:
    return str(getattr(exc, "code", type(exc).__name__))


def _error_message(exc: Exception) -> str:
    return str(getattr(exc, "message", exc))


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    args = build_parser().parse_args()
    commit = should_commit(args)
    built_count = 0
    skipped_count = 0
    failed_count = 0

    target_sets = run_snapshot_operation_with_retry(
        lambda fresh_client: resolve_target_sets(fresh_client, args),
        operation_name="resolve market dashboard snapshot targets",
        client_factory=get_client,
    )
    consecutive_transient_failures = 0
    transient_threshold = max(1, int(args.max_consecutive_transient_failures))

    for index, set_row in enumerate(target_sets):
        logging.info("building market dashboard snapshot %s", _set_label(set_row))
        try:
            def build_and_write(fresh_client):
                with snapshot_service_client_scope(fresh_client):
                    refresh_canonical_card_market_prices_for_set(
                        fresh_client,
                        str(set_row["id"]),
                        commit=commit,
                    )
                    cards_row, dashboard_row, top_chase_history_rows = build_coordinated_set_market_snapshot_rows(
                        set_row,
                        days=args.days,
                        window=args.window,
                        client=fresh_client,
                    )
                    upsert_row(
                        fresh_client,
                        "pokemon_set_cards_snapshot_latest",
                        cards_row,
                        on_conflict="set_id",
                        commit=commit,
                    )
                    upsert_rows(
                        fresh_client,
                        "pokemon_set_top_chase_card_daily_history",
                        top_chase_history_rows,
                        on_conflict="set_id,snapshot_date,rank",
                        commit=commit,
                    )
                    upsert_row(
                        fresh_client,
                        "pokemon_set_market_dashboard_snapshot_latest",
                        dashboard_row,
                        on_conflict="set_id,window_key",
                        commit=commit,
                    )

            run_snapshot_operation_with_retry(
                build_and_write,
                operation_name="build market dashboard snapshot",
                set_id=str(set_row.get("id") or ""),
                client_factory=get_client,
            )
            built_count += 1
            consecutive_transient_failures = 0
        except Exception as exc:
            if _is_missing_data_error(exc):
                skipped_count += 1
                logging.warning(
                    "skipping market dashboard snapshot %s code=%s message=%s",
                    _set_label(set_row),
                    _error_code(exc),
                    _error_message(exc),
                )
                consecutive_transient_failures = 0
            else:
                failed_count += 1
                logging.exception(
                    "failed market dashboard snapshot %s code=%s message=%s",
                    _set_label(set_row),
                    _error_code(exc),
                    _error_message(exc),
                )
                if is_transient_data_service_error(exc):
                    consecutive_transient_failures += 1
                    if args.all and consecutive_transient_failures >= transient_threshold:
                        logging.error(
                            "stopping all-set market dashboard build after %s consecutive transient failures",
                            consecutive_transient_failures,
                        )
                        break
                else:
                    consecutive_transient_failures = 0

        if args.all and index < len(target_sets) - 1 and args.delay_seconds > 0:
            time.sleep(max(0.0, float(args.delay_seconds)))

    summary = f"market dashboard snapshot summary built={built_count} skipped={skipped_count} failed={failed_count}"
    logging.info(summary)
    print(summary)


if __name__ == "__main__":
    main()
