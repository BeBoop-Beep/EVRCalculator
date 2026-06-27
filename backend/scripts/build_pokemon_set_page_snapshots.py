from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from backend.db.services.explore_page_service import ExplorePageError
from backend.scripts.pokemon_snapshot_builders import (
    add_target_set_args,
    build_set_page_snapshot_row,
    get_client,
    resolve_target_sets,
    should_commit,
    upsert_row,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Build page-ready Pokemon set page snapshots")
    add_target_set_args(parser)
    return parser


def _set_label(set_row: dict) -> str:
    return f"set_id={set_row.get('id')} name={set_row.get('name')}"


def _is_missing_data_error(exc: Exception) -> bool:
    if isinstance(exc, ExplorePageError):
        return (
            getattr(exc, "status_code", None) == 404
            or getattr(exc, "code", None) == "TARGET_NOT_FOUND"
            or "no simulation data" in str(getattr(exc, "message", exc)).lower()
        )
    return "no simulation data" in str(exc).lower()


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
        logging.info("building set page snapshot %s", _set_label(set_row))
        try:
            row = build_set_page_snapshot_row(set_row, client=client)
            upsert_row(
                client,
                "pokemon_set_page_snapshot_latest",
                row,
                on_conflict="set_id",
                commit=commit,
            )
            built_count += 1
        except ExplorePageError as exc:
            if _is_missing_data_error(exc):
                skipped_count += 1
                logging.warning(
                    "skipping set page snapshot %s code=%s message=%s",
                    _set_label(set_row),
                    _error_code(exc),
                    _error_message(exc),
                )
                continue
            failed_count += 1
            logging.exception(
                "failed set page snapshot %s code=%s message=%s",
                _set_label(set_row),
                _error_code(exc),
                _error_message(exc),
            )
        except Exception as exc:
            if _is_missing_data_error(exc):
                skipped_count += 1
                logging.warning(
                    "skipping set page snapshot %s code=%s message=%s",
                    _set_label(set_row),
                    _error_code(exc),
                    _error_message(exc),
                )
                continue
            failed_count += 1
            logging.exception(
                "failed set page snapshot %s code=%s message=%s",
                _set_label(set_row),
                _error_code(exc),
                _error_message(exc),
            )

    summary = f"set page snapshot summary built={built_count} skipped={skipped_count} failed={failed_count}"
    logging.info(summary)
    print(summary)


if __name__ == "__main__":
    main()
