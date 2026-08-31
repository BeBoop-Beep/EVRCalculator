"""Operator-only retention and historical-repair invalidation for L2 cache.

No job is scheduled by Effort 1H.  Normal forward publication is refreshed
lazily by the planner.  A recovery workflow that changes a market date at or
before cached history must run ``--invalidate-from YYYY-MM-DD --commit`` only
after interval publication succeeds and before the repaired date is declared
usable.  Without ``--commit`` every operation is a read-only preview.
"""

from __future__ import annotations

import argparse
from datetime import datetime, timedelta, timezone
from typing import Any

CACHE_TABLE = "pokemon_market_explorer_query_cache"
INVALIDATE_RPC = "invalidate_pokemon_market_explorer_query_cache"


def maintain(client: Any, *, invalidate_from: str | None = None,
             retention_days: int | None = None, commit: bool = False) -> dict:
    report = {"commit": commit, "invalidateFrom": invalidate_from,
              "retentionDays": retention_days, "invalidated": 0, "deleted": 0}
    if invalidate_from:
        query = (client.table(CACHE_TABLE).select("id", count="exact", head=True)
                 .gte("computed_through", invalidate_from).eq("status", "ready"))
        preview = query.execute()
        report["invalidated"] = int(preview.count or 0)
        if commit:
            report["invalidated"] = int(client.rpc(INVALIDATE_RPC, {
                "p_changed_market_date": invalidate_from,
            }).execute().data or 0)

    if retention_days is not None:
        if retention_days < 60:
            raise ValueError("retention_days must be at least 60")
        cutoff = (datetime.now(timezone.utc) - timedelta(days=retention_days)).isoformat()
        # Prepared/maintained entries are never custom-cache cleanup targets.
        query = (client.table(CACHE_TABLE).select("id", count="exact", head=True)
                 .eq("cache_kind", "custom").lt("updated_at", cutoff)
                 .or_(f"last_requested_at.is.null,last_requested_at.lt.{cutoff}"))
        preview = query.execute()
        report["deleted"] = int(preview.count or 0)
        if commit and report["deleted"]:
            (client.table(CACHE_TABLE).delete().eq("cache_kind", "custom")
             .lt("updated_at", cutoff)
             .or_(f"last_requested_at.is.null,last_requested_at.lt.{cutoff}").execute())
    return report


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--invalidate-from")
    parser.add_argument("--retention-days", type=int)
    parser.add_argument("--commit", action="store_true")
    args = parser.parse_args()
    from backend.db.clients.supabase_client import create_service_role_client
    print(maintain(create_service_role_client(), invalidate_from=args.invalidate_from,
                   retention_days=args.retention_days, commit=args.commit))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
