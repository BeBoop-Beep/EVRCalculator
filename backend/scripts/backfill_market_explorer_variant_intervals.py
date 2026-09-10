"""Rebuild Market Explorer V2 price intervals in bounded set batches.

The V1 interval table was retired on 2026-09-09. V2 interval reconstruction is
set-scoped because it is derived from the canonical V2 event stream plus the
current Market Explorer instrument metadata. This CLI therefore rebuilds whole
sets, verifies the resulting V2 interval row count, and never references the
retired interval or daily-state relations.

Dry-run is the default-safe mode. Writes require ``--commit``.
"""
from __future__ import annotations

import argparse
import json
import logging
import time
from dataclasses import asdict, dataclass
from typing import Any, Iterable, Iterator, Sequence

from backend.db.clients.supabase_client import create_service_role_client
from backend.db.services.pokemon_market_explorer_query_service import resolve_tracked_set_ids

LOG = logging.getLogger("market_explorer_v2_interval_backfill")

V2_REBUILD_RPC = "rebuild_pokemon_market_price_intervals_v2_shadow_for_sets"
V2_INTERVAL_TABLE = "pokemon_market_price_intervals_v2_shadow"
V2_COVERAGE_TABLE = "pokemon_market_explorer_card_daily_coverage_v2_shadow"
SETS_TABLE = "sets"


@dataclass
class Summary:
    dry_run: bool
    sets_attempted: int = 0
    batches_attempted: int = 0
    batches_succeeded: int = 0
    sets_succeeded: int = 0
    interval_rows_created: int = 0
    failures: int = 0
    resume_cursor: str | None = None
    elapsed_seconds: float = 0.0


def chunks(rows: Sequence[str], size: int) -> Iterator[list[str]]:
    for start in range(0, len(rows), size):
        yield list(rows[start:start + size])


def encode_cursor(set_id: str) -> str:
    return str(set_id)


def decode_cursor(value: str | None) -> str | None:
    if not value:
        return None
    return str(value).split(":", 1)[0].strip() or None


def _paged(query_factory: Any, *, page_size: int = 1000) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    start = 0
    while True:
        page = list(query_factory().range(start, start + page_size - 1).execute().data or [])
        rows.extend(page)
        if len(page) < page_size:
            return rows
        start += page_size


def load_set_ids(
    client: Any,
    requested: Iterable[str],
    era_ids: Iterable[str] = (),
    *,
    exclude_covered: bool = False,
) -> list[str]:
    tracked = set(resolve_tracked_set_ids(client))
    selected = {str(value) for value in requested if value}
    if selected:
        resolved = sorted(selected & tracked)
    else:
        eras = sorted({str(value) for value in era_ids if value})
        if eras:
            rows = _paged(
                lambda: client.table(SETS_TABLE).select("id,era_id").in_("era_id", eras).order("id")
            )
            resolved = sorted(tracked & {str(row["id"]) for row in rows if row.get("id")})
        else:
            resolved = sorted(tracked)

    if exclude_covered and resolved:
        covered = _paged(
            lambda: client.table(V2_COVERAGE_TABLE)
            .select("set_id")
            .in_("set_id", resolved)
            .order("set_id")
        )
        covered_ids = {str(row["set_id"]) for row in covered if row.get("set_id")}
        resolved = [set_id for set_id in resolved if set_id not in covered_ids]
    return resolved


def interval_row_count(client: Any, set_ids: Sequence[str]) -> int:
    if not set_ids:
        return 0
    rows = _paged(
        lambda: client.table(V2_INTERVAL_TABLE)
        .select("card_variant_id,valid_from")
        .in_("set_id", list(set_ids))
        .order("set_id")
        .order("card_variant_id")
        .order("valid_from")
    )
    return len(rows)


def rebuild_interval_batch(client: Any, set_ids: Sequence[str]) -> int:
    response = client.rpc(V2_REBUILD_RPC, {"p_set_ids": list(set_ids)}).execute()
    result = dict(response.data or {})
    if int(result.get("set_count") or 0) != len(set_ids):
        raise RuntimeError(
            f"V2 interval rebuild reported set_count={result.get('set_count')} for {len(set_ids)} requested sets"
        )
    inserted = int(result.get("interval_rows") or 0)
    actual = interval_row_count(client, set_ids)
    if inserted != actual:
        raise RuntimeError(
            f"V2 interval rebuild returned {inserted} rows but exact post-write count is {actual}"
        )
    return actual


def run_backfill(
    client: Any,
    *,
    commit: bool,
    batch_size: int,
    set_ids: Sequence[str] = (),
    era_ids: Sequence[str] = (),
    exclude_covered: bool = False,
    resume_after: str | None = None,
) -> dict[str, Any]:
    started = time.monotonic()
    summary = Summary(dry_run=not commit)
    cursor = decode_cursor(resume_after)
    scopes = load_set_ids(client, set_ids, era_ids, exclude_covered=exclude_covered)
    if cursor:
        scopes = [set_id for set_id in scopes if set_id > cursor]

    summary.sets_attempted = len(scopes)
    for batch in chunks(scopes, batch_size):
        summary.batches_attempted += 1
        batch_started = time.monotonic()
        try:
            rows = rebuild_interval_batch(client, batch) if commit else 0
            summary.interval_rows_created += rows
            summary.batches_succeeded += 1
            summary.sets_succeeded += len(batch)
            summary.resume_cursor = encode_cursor(batch[-1])
            LOG.info(json.dumps({
                "event": "v2_interval_batch_complete",
                "setCount": len(batch),
                "intervalRows": rows,
                "resumeCursor": summary.resume_cursor,
                "elapsedSeconds": round(time.monotonic() - batch_started, 3),
                "dryRun": not commit,
            }, sort_keys=True))
        except Exception as exc:  # noqa: BLE001 - stop at first failed bounded batch
            summary.failures += 1
            LOG.error(json.dumps({
                "event": "v2_interval_batch_failed",
                "setIds": batch,
                "error": str(exc),
                "retryable": True,
            }, sort_keys=True))
            summary.elapsed_seconds = round(time.monotonic() - started, 3)
            return asdict(summary)

    summary.elapsed_seconds = round(time.monotonic() - started, 3)
    return asdict(summary)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--dry-run", action="store_true", help="Plan V2 set batches; perform no writes.")
    mode.add_argument("--commit", action="store_true", help="Rebuild V2 intervals for each bounded set batch.")
    parser.add_argument("--batch-size", type=int, default=8, help="Sets per V2 rebuild transaction (default: 8).")
    parser.add_argument("--set-id", action="append", default=[], help="Limit to a tracked set UUID; repeatable.")
    parser.add_argument("--era-id", action="append", default=[], help="Limit to tracked sets in an era; repeatable.")
    parser.add_argument("--exclude-covered", action="store_true",
                        help="Skip sets already represented in V2 daily coverage.")
    parser.add_argument("--resume-after", help="Resume after the last successful set UUID. Legacy SET:VARIANT cursors are accepted by using their set portion.")
    parser.add_argument("--variant-id", action="append", default=[],
                        help="Retired V1 option; V2 interval rebuilding is set-scoped and rejects variant-only execution.")
    return parser


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    args = build_parser().parse_args()
    if args.batch_size < 1:
        raise SystemExit("--batch-size must be positive")
    if args.variant_id:
        raise SystemExit("--variant-id is no longer supported: V2 interval rebuilding is set-scoped; use --set-id")
    report = run_backfill(
        create_service_role_client(),
        commit=bool(args.commit),
        batch_size=args.batch_size,
        set_ids=args.set_id,
        era_ids=args.era_id,
        exclude_covered=args.exclude_covered,
        resume_after=args.resume_after,
    )
    print(json.dumps(report, indent=2, sort_keys=True))
    return 1 if report["failures"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
