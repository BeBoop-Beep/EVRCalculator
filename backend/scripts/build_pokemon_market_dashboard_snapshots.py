from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from backend.db.services.pokemon_set_market_service import PokemonSetMarketError
from backend.scripts.pokemon_snapshot_builders import (
    DEFAULT_DASHBOARD_DAYS,
    DEFAULT_DASHBOARD_WINDOW,
    add_target_set_args,
    build_market_dashboard_snapshot_rows,
    get_client,
    resolve_target_sets,
    should_commit,
    upsert_row,
    upsert_rows,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Build Pokemon set market dashboard snapshots")
    add_target_set_args(parser)
    parser.add_argument("--days", type=int, default=DEFAULT_DASHBOARD_DAYS, help="History days to include")
    parser.add_argument("--window", default=DEFAULT_DASHBOARD_WINDOW, help="Snapshot window key")
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
    client = get_client()
    commit = should_commit(args)
    built_count = 0
    skipped_count = 0
    failed_count = 0

    for set_row in resolve_target_sets(client, args):
        logging.info("building market dashboard snapshot %s", _set_label(set_row))
        try:
            dashboard_row, top_chase_history_rows = build_market_dashboard_snapshot_rows(
                set_row,
                days=args.days,
                window=args.window,
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
            built_count += 1
        except Exception as exc:
            if _is_missing_data_error(exc):
                skipped_count += 1
                logging.warning(
                    "skipping market dashboard snapshot %s code=%s message=%s",
                    _set_label(set_row),
                    _error_code(exc),
                    _error_message(exc),
                )
                continue
            failed_count += 1
            logging.exception(
                "failed market dashboard snapshot %s code=%s message=%s",
                _set_label(set_row),
                _error_code(exc),
                _error_message(exc),
            )

    summary = f"market dashboard snapshot summary built={built_count} skipped={skipped_count} failed={failed_count}"
    logging.info(summary)
    print(summary)


if __name__ == "__main__":
    main()
