"""PROPOSED capture job: append today's appeal scores to the history tables.

Pairs with backend/db/migrations/046_PROPOSED_desirability_daily_history.sql.
NEITHER IS APPLIED. Both are proposals attached to the collector-appeal study,
which found that every longitudinal research question is blocked by the absence
of appeal history rather than by method.

Runs DRY BY DEFAULT and prints what it would insert. ``--commit`` performs the
append, and fails loudly if the proposed migration has not been applied rather
than silently doing nothing.

Design notes that matter for the research this unblocks:

  * APPEND-ONLY. The point is to stop overwriting. Re-running on the same day is
    idempotent via ON CONFLICT DO NOTHING - it must never update an existing row,
    because a changed historical value would silently invalidate any walk-forward
    result computed from it.
  * captured_at (now) is recorded separately from observed_on (what the source
    describes). Forecasting must filter on captured_at.
  * Google Trends renormalizes per request, so the anchor term and timeframe are
    recorded with every row. Series with different anchors are not comparable.
  * Nothing is written unless the source row actually exists. A missing score is
    an absent row, never a zero.

Cadence recommendation is in the results doc: daily for desirability, weekly for
trends. The binding constraint on the forecasting work is calendar time, so the
value of starting is almost entirely in starting early.
"""

from __future__ import annotations

import argparse
import logging
import os
import sys
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any, Dict, List

from dotenv import load_dotenv

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))

logger = logging.getLogger(__name__)

DESIRABILITY_HISTORY_TABLE = "pokemon_desirability_score_daily_history"
TREND_HISTORY_TABLE = "pokemon_trend_score_weekly_history"
COMPOSITE_TABLE = "pokemon_desirability_composite_scores"
TREND_TABLE = "pokemon_trend_scores"


def _paged(query, page: int = 1000) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    offset = 0
    while True:
        chunk = query.range(offset, offset + page - 1).execute().data or []
        rows.extend(chunk)
        if len(chunk) < page:
            return rows
        offset += page


def build_desirability_rows(client, observed_on: date) -> List[Dict[str, Any]]:
    source = _paged(
        client.table(COMPOSITE_TABLE).select(
            "pokemon_reference_id,scoring_version,desirability_score,desirability_rank,"
            "desirability_tier,fan_popularity_score,current_trend_score,score_components_json"
        )
    )
    rows: List[Dict[str, Any]] = []
    for row in source:
        if row.get("pokemon_reference_id") is None:
            continue
        rows.append({
            "pokemon_reference_id": row["pokemon_reference_id"],
            "observed_on": observed_on.isoformat(),
            "scoring_version": row.get("scoring_version"),
            "desirability_score": row.get("desirability_score"),
            "desirability_rank": row.get("desirability_rank"),
            "desirability_tier": row.get("desirability_tier"),
            "fan_popularity_score": row.get("fan_popularity_score"),
            "current_trend_score": row.get("current_trend_score"),
            "score_components_json": row.get("score_components_json"),
            "captured_at": datetime.now(timezone.utc).isoformat(),
            "is_backfilled": False,
        })
    return rows


def build_trend_rows(client, observed_week: date) -> List[Dict[str, Any]]:
    snapshots = {
        row["id"]: row
        for row in _paged(
            client.table("pokemon_trend_source_snapshots").select(
                "id,source_name,timeframe,geo,anchor_term,status"
            )
        )
    }
    source = _paged(
        client.table(TREND_TABLE).select(
            "pokemon_reference_id,source_name,relative_search_interest_score,"
            "normalized_rank,confidence,scoring_version,primary_snapshot_id"
        )
    )
    rows: List[Dict[str, Any]] = []
    for row in source:
        if row.get("pokemon_reference_id") is None:
            continue
        snapshot = snapshots.get(row.get("primary_snapshot_id")) or {}
        # A rate-limited capture is not an observation. Recording it as one would
        # inject a fake trough into every momentum series computed later.
        if str(snapshot.get("status") or "").startswith("rate_limited"):
            continue
        rows.append({
            "pokemon_reference_id": row["pokemon_reference_id"],
            "observed_week": observed_week.isoformat(),
            "source_name": row.get("source_name") or "unknown",
            "timeframe": snapshot.get("timeframe") or "unknown",
            "geo": snapshot.get("geo") or "",
            "anchor_term": snapshot.get("anchor_term") or "",
            "relative_search_interest_score": row.get("relative_search_interest_score"),
            "normalized_rank": row.get("normalized_rank"),
            "confidence": row.get("confidence"),
            "scoring_version": row.get("scoring_version"),
            "captured_at": datetime.now(timezone.utc).isoformat(),
            "is_backfilled": False,
            "source_snapshot_id": row.get("primary_snapshot_id"),
        })
    return rows


def append(client, table: str, rows: List[Dict[str, Any]], *, commit: bool) -> int:
    if not rows:
        logger.warning("%s: nothing to append", table)
        return 0
    if not commit:
        logger.info("[DRY RUN] would append %s rows to %s", len(rows), table)
        logger.info("[DRY RUN] first row: %s", rows[0])
        return 0
    written = 0
    for start in range(0, len(rows), 500):
        chunk = rows[start:start + 500]
        # Append-only: never update an existing (subject, date) row. A changed
        # historical value would silently invalidate anything computed from it.
        client.table(table).upsert(chunk, on_conflict=",".join(_conflict_keys(table)),
                                   ignore_duplicates=True).execute()
        written += len(chunk)
    logger.info("%s: appended %s rows", table, written)
    return written


def _conflict_keys(table: str) -> List[str]:
    if table == DESIRABILITY_HISTORY_TABLE:
        return ["pokemon_reference_id", "observed_on", "scoring_version"]
    if table == TREND_HISTORY_TABLE:
        return ["pokemon_reference_id", "observed_week", "source_name", "timeframe", "geo", "anchor_term"]
    raise ValueError(table)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--commit", action="store_true",
                        help="Actually append. Omit for a dry run (the default).")
    parser.add_argument("--observed-on", default=None, help="ISO date; defaults to today (UTC).")
    parser.add_argument("--log-level", default="INFO")
    args = parser.parse_args()

    logging.basicConfig(level=getattr(logging, args.log_level.upper(), logging.INFO),
                        format="%(levelname)s %(message)s")
    logging.getLogger("httpx").setLevel(logging.WARNING)
    load_dotenv(Path(__file__).resolve().parents[1] / ".env", override=False)

    observed_on = (
        date.fromisoformat(args.observed_on) if args.observed_on
        else datetime.now(timezone.utc).date()
    )

    if args.commit:
        from backend.db.clients.supabase_client import service_write_client as get_client
    else:
        from backend.db.clients.supabase_client import public_read_client as get_client
    client = get_client

    if args.commit:
        try:
            client.table(DESIRABILITY_HISTORY_TABLE).select("observed_on").limit(1).execute()
        except Exception as error:  # noqa: BLE001
            logger.error(
                "History tables are missing. Apply migration 046 first - refusing to run so "
                "this cannot appear to succeed while capturing nothing. (%s)", error
            )
            return 2

    desirability = build_desirability_rows(client, observed_on)
    trends = build_trend_rows(client, observed_on)

    logger.info("Desirability rows: %s | trend rows: %s | observed_on=%s",
                len(desirability), len(trends), observed_on)
    append(client, DESIRABILITY_HISTORY_TABLE, desirability, commit=args.commit)
    append(client, TREND_HISTORY_TABLE, trends, commit=args.commit)

    if not args.commit:
        print("\nDRY RUN. Nothing was written. Re-run with --commit once migration 046 is applied.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
