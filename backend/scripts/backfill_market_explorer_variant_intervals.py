"""Publish Market Explorer variant intervals in bounded, resumable batches.

Dry-run is the default-safe mode. Writes require ``--commit`` and use only the
service-role client. Progress is a deterministic ``SET_UUID:VARIANT_UUID``
cursor printed after every successful batch; pass it back with ``--resume-after``.
"""
from __future__ import annotations

import argparse
import json
import logging
import time
from dataclasses import asdict, dataclass
from typing import Any, Iterable, Iterator, Sequence

from backend.db.clients.supabase_client import create_service_role_client


LOG = logging.getLogger("market_explorer_variant_backfill")
AUTHORITY_RPC = "get_pokemon_canonical_card_variant_authority"
REFRESH_RPC = "refresh_pokemon_card_variant_market_price_intervals"
INTERVAL_TABLE = "pokemon_card_variant_market_price_intervals"


@dataclass
class Summary:
    dry_run: bool
    sets_attempted: int = 0
    batches_attempted: int = 0
    batches_succeeded: int = 0
    variants_attempted: int = 0
    variants_succeeded: int = 0
    variants_with_history: int = 0
    interval_rows_created: int = 0
    empty_history_variants: int = 0
    failures: int = 0
    resume_cursor: str | None = None
    elapsed_seconds: float = 0.0


def chunks(rows: Sequence[str], size: int) -> Iterator[list[str]]:
    for start in range(0, len(rows), size):
        yield list(rows[start:start + size])


def encode_cursor(set_id: str, variant_id: str) -> str:
    return f"{set_id}:{variant_id}"


def decode_cursor(value: str | None) -> tuple[str, str] | None:
    if not value:
        return None
    parts = value.split(":", 1)
    if len(parts) != 2 or not all(parts):
        raise ValueError("--resume-after must be SET_UUID:VARIANT_UUID")
    return parts[0], parts[1]


def after_cursor(set_id: str, variant_id: str, cursor: tuple[str, str] | None) -> bool:
    return cursor is None or (set_id, variant_id) > cursor


def _paged(query_factory, *, page_size: int = 1000) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    start = 0
    while True:
        page = list(query_factory().range(start, start + page_size - 1).execute().data or [])
        rows.extend(page)
        if len(page) < page_size:
            return rows
        start += page_size


def load_set_ids(client: Any, requested: Iterable[str], era_ids: Iterable[str] = (),
                 *, exclude_covered: bool = False) -> list[str]:
    selected = sorted(set(requested))
    if selected:
        return selected
    eras = sorted(set(era_ids))
    def query():
        request = client.table("sets").select("id").order("id")
        return request.in_("era_id", eras) if eras else request
    rows = _paged(query)
    resolved = sorted(str(row["id"]) for row in rows)
    if exclude_covered and resolved:
        covered = _paged(lambda: client.table("pokemon_market_explorer_card_daily_coverage")
                         .select("set_id").in_("set_id", resolved).order("set_id"))
        covered_ids = {str(row["set_id"]) for row in covered}
        resolved = [set_id for set_id in resolved if set_id not in covered_ids]
    return resolved


def load_variant_ids_for_set(client: Any, set_id: str) -> list[str]:
    rows = _paged(lambda: client.rpc(AUTHORITY_RPC, {"p_set_ids": [set_id]}))
    return sorted({str(row["card_variant_id"]) for row in rows if row.get("card_variant_id")})


def interval_reconciliation(client: Any, variant_ids: Sequence[str]) -> tuple[int, int]:
    rows = _paged(lambda: (client.table(INTERVAL_TABLE)
                           .select("observation_id,card_variant_id")
                           .in_("card_variant_id", list(variant_ids))
                           .order("observation_id")))
    represented = {str(row["card_variant_id"]) for row in rows}
    return len(rows), len(variant_ids) - len(represented)


def run_backfill(
    client: Any,
    *,
    commit: bool,
    batch_size: int,
    set_ids: Sequence[str] = (),
    era_ids: Sequence[str] = (),
    exclude_covered: bool = False,
    variant_ids: Sequence[str] = (),
    resume_after: str | None = None,
) -> dict[str, Any]:
    started = time.monotonic()
    summary = Summary(dry_run=not commit)
    cursor = decode_cursor(resume_after)
    explicit_variants = sorted(set(variant_ids))
    scopes = (load_set_ids(client, set_ids, era_ids, exclude_covered=exclude_covered)
              if not explicit_variants else ["explicit"])

    for set_id in scopes:
        variants = explicit_variants if explicit_variants else load_variant_ids_for_set(client, set_id)
        variants = [variant_id for variant_id in variants if after_cursor(set_id, variant_id, cursor)]
        if not variants:
            continue
        summary.sets_attempted += 1
        for batch in chunks(variants, batch_size):
            summary.batches_attempted += 1
            summary.variants_attempted += len(batch)
            batch_started = time.monotonic()
            try:
                if commit:
                    response = client.rpc(REFRESH_RPC, {"p_card_variant_ids": batch}).execute()
                    inserted = int(response.data or 0)
                    observed_rows, empty = interval_reconciliation(client, batch)
                    if observed_rows != inserted:
                        raise RuntimeError(
                            f"refresh returned {inserted} rows but reconciliation found {observed_rows}"
                        )
                    summary.interval_rows_created += inserted
                    summary.empty_history_variants += empty
                    summary.variants_with_history += len(batch) - empty
                summary.batches_succeeded += 1
                summary.variants_succeeded += len(batch)
                summary.resume_cursor = encode_cursor(set_id, batch[-1])
                LOG.info(json.dumps({
                    "event": "batch_complete", "setId": set_id,
                    "variantCount": len(batch), "resumeCursor": summary.resume_cursor,
                    "elapsedSeconds": round(time.monotonic() - batch_started, 3),
                    "dryRun": not commit,
                }, sort_keys=True))
            except Exception as exc:
                summary.failures += 1
                LOG.error(json.dumps({
                    "event": "batch_failed", "setId": set_id, "variantIds": batch,
                    "error": str(exc), "retryable": True,
                }, sort_keys=True))
                # Stop at the first failed batch. The cursor therefore remains
                # the last durable success and cannot skip a failed scope.
                summary.elapsed_seconds = round(time.monotonic() - started, 3)
                return asdict(summary)

    summary.elapsed_seconds = round(time.monotonic() - started, 3)
    return asdict(summary)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--dry-run", action="store_true", help="Plan batches; perform no writes.")
    mode.add_argument("--commit", action="store_true", help="Execute bounded service-role refresh RPCs.")
    parser.add_argument("--batch-size", type=int, default=100, help="Variants per transaction (default: 100).")
    parser.add_argument("--set-id", action="append", default=[], help="Limit to a set UUID; repeatable.")
    parser.add_argument("--era-id", action="append", default=[], help="Resolve all set UUIDs in an era; repeatable.")
    parser.add_argument("--exclude-covered", action="store_true",
                        help="Skip sets already present in daily projection coverage.")
    parser.add_argument("--variant-id", action="append", default=[], help="Retry exact variant UUIDs; repeatable.")
    parser.add_argument("--resume-after", help="Skip through the printed SET_UUID:VARIANT_UUID cursor.")
    return parser


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    args = build_parser().parse_args()
    if args.batch_size < 1:
        raise SystemExit("--batch-size must be positive")
    report = run_backfill(
        create_service_role_client(), commit=bool(args.commit), batch_size=args.batch_size,
        set_ids=args.set_id, era_ids=args.era_id, exclude_covered=args.exclude_covered,
        variant_ids=args.variant_id,
        resume_after=args.resume_after,
    )
    print(json.dumps(report, indent=2, sort_keys=True))
    return 1 if report["failures"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
