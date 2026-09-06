from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from backend.db.services.market_date_quality import market_index_accepted_dates
from backend.db.services.market_publication_gate import (
    MarketForcePublishRejected,
    add_market_gate_args,
    enforce_market_publication_gate,
)
from backend.db.services.pokemon_market_index_service import (
    build_market_index_history,
    persist_index_rows,
)
from backend.db.services.pokemon_market_rollout_cohort import resolve_market_root_cohort
from backend.db.services.pokemon_market_rollout_index import (
    build_rollout_market_index_rows,
    persist_rollout_market_index_rows,
)
from backend.domain.pokemon.market_index import (
    CHASE_INDEX_KEY,
    INDEX_KEYS,
    MARKET_INDEX_CONTRACT_VERSION,
    MARKET_INDEX_METHODOLOGY_VERSION,
    RAW_INDEX_KEY,
)
from backend.scripts.pokemon_snapshot_builders import get_client

# This RPC uses the public-era rollout authority only. The older generic
# rollout RPC intentionally remains available for Price Storage V2 workflows,
# but must not expand the global Market cohort.
ROLLOUT_REFRESH_RPC = "refresh_pokemon_market_public_rollout_daily_snapshots_v1"
PUBLIC_ROLLOUT_TABLE = "pokemon_market_public_era_rollout_v1"
SOURCE_TABLE = "pokemon_set_value_daily_history"


def parser():
    p = argparse.ArgumentParser(description="Build chain-linked Pokemon Market index history")
    mode = p.add_mutually_exclusive_group(required=True)
    mode.add_argument("--dry-run", action="store_true")
    mode.add_argument("--commit", action="store_true")
    p.add_argument("--market-date")
    p.add_argument("--backfill", action="store_true")
    p.add_argument("--from-date")
    add_market_gate_args(p)
    p.add_argument(
        "--force-publish",
        action="store_true",
        help="Rejected for Market publication; Market Date Quality cannot be overridden",
    )
    return p


def _rollout_source_materialization(client, market_date: str) -> dict:
    """Cheap prerequisite check for staged public-era daily source rows.

    The rollout refresh RPC can be relatively expensive because it derives
    canonical parent/subset Set Value and Top-10 rows. Do not rerun it inside
    the index publisher when both source scopes are already materialized for
    every active rollout root. This keeps index publication idempotent and
    avoids paying for the same canonical rebuild twice in one market day.
    """
    day = str(market_date)[:10]
    era_rows = list(
        client.table(PUBLIC_ROLLOUT_TABLE)
        .select("era_id,activated_market_date")
        .eq("enabled", True)
        .lte("activated_market_date", day)
        .execute().data or []
    )
    era_ids = sorted({str(row.get("era_id")) for row in era_rows if row.get("era_id")})
    if not era_ids:
        return {"ready": True, "rootCount": 0, "materializedPairCount": 0}

    set_rows = list(
        client.table("sets")
        .select("id,era_id,parent_opening_set_id,catalog_only,ready_for_daily_scrape,release_date")
        .in_("era_id", era_ids)
        .execute().data or []
    )
    root_ids = sorted({
        str(row["id"])
        for row in set_rows
        if row.get("id")
        and not row.get("parent_opening_set_id")
        and row.get("catalog_only") is not True
        and row.get("ready_for_daily_scrape") is True
        and (not row.get("release_date") or str(row.get("release_date"))[:10] <= day)
    })
    if not root_ids:
        return {"ready": True, "rootCount": 0, "materializedPairCount": 0}

    source_rows = list(
        client.table(SOURCE_TABLE)
        .select("set_id,value_scope")
        .in_("set_id", root_ids)
        .eq("snapshot_date", day)
        .in_("value_scope", ["standard", "top10"])
        .execute().data or []
    )
    pairs = {
        (str(row.get("set_id")), str(row.get("value_scope")))
        for row in source_rows
        if row.get("set_id") and row.get("value_scope")
    }
    ready = all(
        (set_id, "standard") in pairs and (set_id, "top10") in pairs
        for set_id in root_ids
    )
    return {
        "ready": ready,
        "rootCount": len(root_ids),
        "materializedPairCount": len(pairs),
    }


def build(client, *, market_date=None, backfill=False, from_date=None, commit=False, accepted_dates=None):
    # Historical/backfill behavior remains the legacy full-history builder.
    # Normal daily publication is incremental once staged era rollout is active:
    # existing history stays immutable and the activation-day cohort change is
    # neutralized explicitly instead of being misreported as price performance.
    rollout_refresh = None
    if market_date and not backfill:
        materialization = _rollout_source_materialization(client, str(market_date)[:10])
        if commit and not materialization["ready"]:
            response = client.rpc(
                ROLLOUT_REFRESH_RPC,
                {"p_market_date": str(market_date)[:10]},
            ).execute()
            rollout_refresh = getattr(response, "data", None)
        else:
            rollout_refresh = {
                "status": "already_materialized" if materialization["ready"] else "dry_run",
                **materialization,
            }
        rows = build_rollout_market_index_rows(client, market_date=str(market_date)[:10])
        persisted = persist_rollout_market_index_rows(client, rows) if commit else 0
    else:
        rows = build_market_index_history(
            client,
            through_date=market_date,
            accepted_dates=accepted_dates,
        )
        if from_date:
            rows = [row for row in rows if row["market_date"] >= from_date]
        persisted = persist_index_rows(client, rows) if commit else 0

    latest = {
        key: next((row for row in reversed(rows) if row["index_key"] == key), None)
        for key in INDEX_KEYS
    }
    source_fp = "|".join(
        str(latest[key].get("source_generation_fingerprint"))
        for key in INDEX_KEYS
        if latest[key]
    )
    eligible = resolve_market_root_cohort(client, market_date=market_date)
    return {
        "contractVersion": MARKET_INDEX_CONTRACT_VERSION,
        "methodologyVersion": MARKET_INDEX_METHODOLOGY_VERSION,
        "indexKeys": list(INDEX_KEYS),
        "firstDate": min((row["market_date"] for row in rows), default=None),
        "lastDate": max((row["market_date"] for row in rows), default=None),
        "rowsBuilt": len(rows),
        "rowsPersisted": persisted,
        "eligibleSetCountCurrent": len(eligible),
        "rawCurrentBasketValue": latest[RAW_INDEX_KEY].get("basket_value") if latest[RAW_INDEX_KEY] else None,
        "rawCurrentCardCount": latest[RAW_INDEX_KEY].get("card_count") if latest[RAW_INDEX_KEY] else None,
        "chaseCurrentBasketValue": latest[CHASE_INDEX_KEY].get("basket_value") if latest[CHASE_INDEX_KEY] else None,
        "chaseCurrentCardCount": latest[CHASE_INDEX_KEY].get("card_count") if latest[CHASE_INDEX_KEY] else None,
        "sourceGenerationFingerprint": source_fp,
        "rolloutRefresh": rollout_refresh,
        "warnings": [],
        "errors": [],
    }


def main():
    args = parser().parse_args()
    client = get_client()
    try:
        gate = enforce_market_publication_gate(
            client,
            commit=bool(args.commit),
            market_date=args.market_date,
            force_publish=bool(args.force_publish),
            entry_point="Pokemon Market index history",
        )
    except MarketForcePublishRejected as exc:
        print(json.dumps({"errors": [str(exc)]}, sort_keys=True))
        raise SystemExit(2) from exc
    if not gate.proceed:
        raise SystemExit(gate.exit_code)

    try:
        accepted = market_index_accepted_dates(client, through_date=args.market_date)
    except Exception as exc:
        print(json.dumps({"errors": [
            f"Market Date Quality history unavailable ({exc}); refusing to run "
            f"chain-link math without it"
        ]}, sort_keys=True))
        raise SystemExit(3) from exc
    if gate.decision.market_date:
        accepted.add(str(gate.decision.market_date)[:10])

    market_date = args.market_date or gate.decision.market_date
    try:
        summary = build(
            client,
            market_date=market_date,
            backfill=args.backfill,
            from_date=args.from_date,
            commit=args.commit,
            accepted_dates=accepted,
        )
    except Exception as exc:
        print(json.dumps({"errors": [str(exc)]}, sort_keys=True))
        raise SystemExit(1) from exc
    summary["marketQualityStatus"] = gate.decision.status
    print(json.dumps(summary, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
