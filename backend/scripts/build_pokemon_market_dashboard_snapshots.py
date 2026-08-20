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
from backend.db.services.market_publication_gate import (
    MarketForcePublishRejected, enforce_market_publication_gate,
)
from backend.db.services.publication_gate import (
    add_publication_gate_args,
    enforce_cli_publication_gate,
)
from backend.db.services.set_publication_revalidation import notify_set_publication
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
    add_publication_gate_args(parser)
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


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    args = build_parser().parse_args()
    commit = should_commit(args)

    # Market Date Quality is the authority for Market artifacts. It is
    # evaluated on the canonical Market cohort alone: an unrelated non-Market
    # failure in the 167-set batch must not hold the Market surface hostage.
    try:
        gate = enforce_market_publication_gate(
            get_client(),
            commit=commit,
            market_date=args.market_date,
            force_publish=bool(args.force_publish),
            entry_point="cards + market dashboard snapshots",
        )
    except MarketForcePublishRejected as exc:
        print(str(exc))
        return 2
    if not gate.proceed:
        return gate.exit_code

    built_count = 0
    skipped_count = 0
    failed_count = 0
    revalidated: set[str] = set()

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
            # Cards + Top Chase history + dashboard all committed for this set:
            # invalidate the frontend seed cache exactly once, and never on a
            # dry-run or after a partial coordinated write.
            notify_set_publication(set_row, window=args.window, commit=commit, seen=revalidated)
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
    # Graceful skips (documented missing-data sets) keep the run successful;
    # a genuine failure must not be hidden by the sets that did succeed,
    # because build_pokemon_public_snapshots.py trusts this exit code.
    return 1 if failed_count else 0


if __name__ == "__main__":
    raise SystemExit(main())
