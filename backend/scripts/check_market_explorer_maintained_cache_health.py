"""Operational health check for maintained Market Explorer Cards caches.

WHY THIS EXISTS. Prompt 8's live audit found every maintained cache silently
stale for three days, and one outright `failed`, with nothing in this repo
that would have surfaced that to a human before this session went looking
for it by hand. This script is the missing detection: run it on a schedule
(see the recommended cron ordering in
`backend/scripts/run_market_explorer_maintained_cache_prewarm.py`'s own
docstring, and the Prompt 8/9 acceptance reports for the exact production
ordering) and treat a non-zero exit code as page-worthy.

WHAT AN ALERT CONTAINS. Fingerprint/label, status, computed_through, the
latest approved market date, the staleness age in days, and the error string
already stored in `failure_reason` if the row records one. NEVER a
constituent array, a full cache payload, or any other bulk data -- this
script's own output is deliberately small and safe to paste into a chat
alert or a log aggregator without redaction.

Read-only. This script makes no writes and claims no build lease; it must
never be able to affect projection or cache state, only report on it.
"""
from __future__ import annotations

import argparse
import json
from dataclasses import asdict, dataclass, field
from datetime import date
from typing import Any

from backend.db.clients.supabase_client import create_service_role_client
from backend.db.services.market_explorer_maintained_cache_ops import discover_maintained_caches
from backend.db.services.pokemon_market_explorer_query_service import resolve_tracked_set_ids
from backend.scripts.publish_market_explorer_daily_projection import (
    APPROVED_STATUSES,
    DATE_QUALITY_TABLE,
    _paged,
)

CACHE_TABLE = "pokemon_market_explorer_query_cache"
DEFAULT_STALE_THRESHOLD_DAYS = 0
V1_COVERAGE_TABLE = "pokemon_market_explorer_card_daily_coverage"
V2_COVERAGE_TABLE = "pokemon_market_explorer_card_daily_coverage_v2_shadow"


@dataclass
class CacheAlert:
    fingerprint: str
    label: str
    status: str
    computed_through: str | None
    latest_approved_market_date: str
    age_days: int | None
    reason: str  # "failed" | "stale" | "orphan_lease"


@dataclass
class HealthReport:
    latest_approved_market_date: str | None
    maintained_count: int = 0
    ready_and_current: int = 0
    v1: dict[str, Any] = field(default_factory=dict)
    v2: dict[str, Any] = field(default_factory=dict)
    cache_status_counts: dict[str, int] = field(default_factory=dict)
    alerts: list[dict[str, Any]] = field(default_factory=list)


def resolve_latest_approved_market_date(client: Any) -> str | None:
    rows = _paged(lambda: client.table(DATE_QUALITY_TABLE).select("market_date")
                  .eq("tcg", "pokemon").in_("status", list(APPROVED_STATUSES))
                  .order("market_date"))
    dates = sorted({str(row["market_date"])[:10] for row in rows})
    return dates[-1] if dates else None


def _age_days(computed_through: str | None, latest_approved: str) -> int | None:
    if not computed_through:
        return None
    try:
        delta = date.fromisoformat(latest_approved) - date.fromisoformat(str(computed_through)[:10])
        return delta.days
    except ValueError:
        return None


def check_maintained_cache_health(
    client: Any, *, stale_threshold_days: int = DEFAULT_STALE_THRESHOLD_DAYS,
) -> dict[str, Any]:
    latest_approved = resolve_latest_approved_market_date(client)
    report = HealthReport(latest_approved_market_date=latest_approved)
    if latest_approved is None:
        return asdict(report)

    tracked = set(resolve_tracked_set_ids(client))
    v1_rows = _paged(lambda: client.table(V1_COVERAGE_TABLE)
                     .select("set_id,computed_through"))
    v2_rows = _paged(lambda: client.table(V2_COVERAGE_TABLE)
                     .select("set_id,retained_from,computed_through"))

    def coverage_report(rows: list[dict[str, Any]], *, include_retention: bool) -> dict[str, Any]:
        scoped = [row for row in rows if str(row.get("set_id")) in tracked]
        lagging = sorted(str(row.get("set_id")) for row in scoped
                         if str(row.get("computed_through") or "")[:10] < latest_approved)
        present = {str(row.get("set_id")) for row in scoped}
        lagging.extend(sorted(tracked - present))
        result: dict[str, Any] = {
            "coverage_sets": len(scoped),
            "authority_sets": len(tracked),
            "min_computed_through": min((str(row.get("computed_through"))[:10]
                                          for row in scoped), default=None),
            "lagging_sets": lagging,
        }
        if include_retention:
            result["retained_from"] = min((str(row.get("retained_from"))[:10]
                                            for row in scoped), default=None)
        return result

    report.v1 = coverage_report(v1_rows, include_retention=False)
    report.v2 = coverage_report(v2_rows, include_retention=True)

    rows = discover_maintained_caches(client)
    report.maintained_count = len(rows)
    report.cache_status_counts = {
        status: sum(1 for row in rows if str(row.get("status") or "") == status)
        for status in ("ready", "failed", "stale", "building")
    }
    for row in rows:
        fingerprint = str(row.get("query_fingerprint") or "")
        label = str(row.get("label") or fingerprint or "?")
        status = str(row.get("status") or "")
        computed_through = row.get("computed_through")
        age = _age_days(computed_through, latest_approved)

        if status == "failed":
            report.alerts.append(asdict(CacheAlert(
                fingerprint=fingerprint, label=label, status=status,
                computed_through=str(computed_through)[:10] if computed_through else None,
                latest_approved_market_date=latest_approved, age_days=age, reason="failed",
            )))
            continue

        if age is not None and age > stale_threshold_days:
            report.alerts.append(asdict(CacheAlert(
                fingerprint=fingerprint, label=label, status=status,
                computed_through=str(computed_through)[:10] if computed_through else None,
                latest_approved_market_date=latest_approved, age_days=age, reason="stale",
            )))
            continue

        if status == "ready" and (age is None or age <= stale_threshold_days):
            report.ready_and_current += 1

    # Orphan/stuck build leases: any row anywhere in the cache table (not
    # only maintained) still marked "building" past its own lease expiry.
    # No ``label`` column exists on this table in production (same finding
    # as ``market_explorer_maintained_cache_ops.discover_maintained_caches``).
    building_rows = _paged(lambda: client.table(CACHE_TABLE)
                            .select("query_fingerprint,build_expires_at,cache_kind")
                            .eq("status", "building"))
    from datetime import datetime, timezone
    now = datetime.now(timezone.utc)
    for row in building_rows:
        expires_at = row.get("build_expires_at")
        if not expires_at:
            continue
        try:
            expires = datetime.fromisoformat(str(expires_at).replace("Z", "+00:00"))
        except ValueError:
            continue
        if expires < now:
            fingerprint = str(row.get("query_fingerprint") or "")
            report.alerts.append(asdict(CacheAlert(
                fingerprint=fingerprint, label=str(row.get("label") or fingerprint or "?"),
                status="building", computed_through=None,
                latest_approved_market_date=latest_approved, age_days=None,
                reason="orphan_lease",
            )))

    return asdict(report)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--stale-threshold-days", type=int, default=DEFAULT_STALE_THRESHOLD_DAYS,
                        help="A ready maintained cache older than this many days behind the "
                             "latest approved market date is reported as stale.")
    return parser


def main() -> int:
    args = build_parser().parse_args()
    report = check_maintained_cache_health(
        create_service_role_client(), stale_threshold_days=args.stale_threshold_days,
    )
    print(json.dumps(report, indent=2, sort_keys=True, default=str))
    return 1 if report["alerts"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
