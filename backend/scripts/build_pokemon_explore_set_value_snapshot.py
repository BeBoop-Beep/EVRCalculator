from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys
from collections import defaultdict
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from backend.db.services.pokemon_explore_set_value_service import (
    ExploreSetValueUnavailable,
    build_global_set_value_row,
    upsert_explore_set_value_snapshot,
)
from backend.db.services.market_publication_gate import (
    MarketForcePublishRejected, enforce_market_publication_gate,
)
from backend.db.services.publication_gate import add_publication_gate_args, enforce_cli_publication_gate
from backend.db.services.pokemon_market_index_service import read_index_history
from backend.db.services.canonical_market_overview import (
    build_canonical_market_overview,
    resolve_canonical_overview_sets,
)
from backend.scripts.pokemon_snapshot_builders import get_client


INITIAL_SELECTED_SET_MOVERS_LIMIT = 10
INITIAL_SELECTED_SET_MOVER_FIELDS = (
    "canonicalCardId", "cardVariantId", "conditionId", "setId", "name",
    "rarity", "cardNumber", "imageSmallUrl", "marketPrice", "changeAmount",
    "changePercent", "window", "windowDays", "startDate", "endDate",
    "reliable", "reliability", "fullWindowCoverage", "isPartialWindow",
)


def _attach_initial_selected_set_movers(client, row: dict) -> None:
    """Publish the #1 Set Value target's canonical 7D movers, never full Cards."""
    payload = row.get("payload_json") or {}
    published_sets = payload.get("sets") or []
    if not published_sets:
        return
    selected = published_sets[0]
    set_id = str(selected.get("setId") or "")
    result = (client.table("pokemon_set_cards_snapshot_latest")
        .select("updated_at,snapshot_meta:payload_json->meta->snapshot,items:payload_json->canonicalMarketMoversByWindow->7D->all")
        .eq("set_id", set_id).execute())
    source = (result.data or [{}])[0]
    items = [
        {key: card.get(key) for key in INITIAL_SELECTED_SET_MOVER_FIELDS if card.get(key) is not None}
        for card in (source.get("items") or [])[:INITIAL_SELECTED_SET_MOVERS_LIMIT]
        if isinstance(card, dict)
    ]
    snapshot = source.get("snapshot_meta") if isinstance(source.get("snapshot_meta"), dict) else {}
    payload["initialSelectedSetMovers"] = {
        "setId": set_id,
        "window": "7D",
        "marketDate": snapshot.get("marketAsOfDate") or selected.get("setValueAsOf"),
        "items": items,
        "meta": {"source": "canonical_cards_published_movers"},
    }
    encoded = json.dumps(payload, separators=(",", ":")).encode()
    row["payload_size_bytes"] = len(encoded)
    mover_identity = "\n".join(
        f"{card.get('canonicalCardId')}|{card.get('cardVariantId')}|{card.get('conditionId')}"
        for card in items
    )
    row["source_generation_fingerprint"] = hashlib.sha256(
        f"{row.get('source_generation_fingerprint')}\n{mover_identity}".encode()
    ).hexdigest()


def publisher_build_sha() -> str:
    configured = (os.getenv("PUBLICATION_BUILD_SHA") or os.getenv("GIT_SHA") or "").strip()
    if configured:
        return configured[:40]
    try:
        return subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=REPO_ROOT, text=True, timeout=5
        ).strip()[:40]
    except (OSError, subprocess.SubprocessError):
        return "unknown"


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(description="Build the compact global Market Set Value snapshot")
    mode = result.add_mutually_exclusive_group(required=True)
    mode.add_argument("--dry-run", action="store_true")
    mode.add_argument("--commit", action="store_true")
    add_publication_gate_args(result)
    return result


def _load_sets(client, *, market_date: str):
    """The Market cohort. Delegates so the audit resolves the SAME set rows."""
    return resolve_canonical_overview_sets(client, market_date=market_date)


def _load_canonical_histories(client, set_ids, *, through_date: str):
    """Canonical Set Value history as of ``through_date`` - a point-in-time read.

    The upper bound is applied server-side. A promoted build for D must not be
    made stale by observations that arrived for D+1: without this bound a build
    for 2026-08-17 loaded rows through 2026-08-18 and every set was rejected
    as stale because canonical[-1] was the future date.
    """
    grouped = defaultdict(list)
    page_size = 1000
    start = 0
    limit_date = str(through_date)[:10]
    while True:
        rows = list((client.table("pokemon_set_value_daily_history")
            .select("set_id,snapshot_date,set_value").in_("set_id", set_ids)
            .eq("value_scope", "standard").lte("snapshot_date", limit_date)
            .order("snapshot_date", desc=False)
            .order("set_id", desc=False)
            .range(start, start + page_size - 1).execute()).data or [])
        for row in rows:
            grouped[str(row.get("set_id"))].append(row)
        if len(rows) < page_size:
            break
        start += page_size
    return grouped


def build(*, client, market_date: str, commit: bool, market_index_history=None, market_overview=None) -> dict:
    sets = _load_sets(client, market_date=market_date)
    set_ids = [str(row["id"]) for row in sets]
    dashboards = []
    # One bounded query per batch, never one request per set. Read only the
    # split Set Value column plus the one prepared Cards Market path; raw
    # dashboard payload_json is intentionally absent.
    for offset in range(0, len(set_ids), 20):
        result = (client.table("pokemon_set_market_dashboard_snapshot_latest")
            .select("set_id,window_key,set_value_histories_json,latest_market_date,updated_at,cardsMarket:payload_json->cardsMarket")
            .eq("window_key", "365d").in_("set_id", set_ids[offset:offset + 20]).execute())
        dashboards.extend(result.data or [])
    histories = _load_canonical_histories(client, set_ids, through_date=market_date)
    overview = market_overview
    if overview is None:
        history = market_index_history
        if history is None:
            history = read_index_history(client, through_date=market_date)
        # ONE construction, shared with the publication parity audit. Additive
        # Market contracts are added in canonical_market_overview, never here,
        # so the audit can never fall behind the publisher again.
        overview = build_canonical_market_overview(
            client, market_date=market_date, history=history, set_ids=set_ids,
        )
    row = build_global_set_value_row(
        sets, dashboards, histories, target_market_date=market_date,
        market_overview=overview, publisher_build_sha=publisher_build_sha(),
    )
    _attach_initial_selected_set_movers(client, row)
    if commit:
        upsert_explore_set_value_snapshot(row, client=client)
    return row


def main() -> None:
    args = parser().parse_args()
    client = get_client()
    try:
        gate = enforce_market_publication_gate(
            client, commit=bool(args.commit), market_date=args.market_date,
            force_publish=bool(args.force_publish),
            entry_point="Global Market Set Value snapshot")
    except MarketForcePublishRejected as exc:
        print(str(exc))
        raise SystemExit(2) from exc
    if not gate.proceed:
        raise SystemExit(gate.exit_code)
    market_date = args.market_date or gate.decision.market_date
    if not market_date:
        raise SystemExit("A promoted --market-date is required")
    try:
        row = build(client=client, market_date=str(market_date)[:10], commit=bool(args.commit))
    except ExploreSetValueUnavailable as exc:
        print(json.dumps({"status": "blocked", "reason": str(exc), **exc.diagnostics}, indent=2, sort_keys=True))
        raise SystemExit(1) from exc
    print(json.dumps({"status": "validated", **row["_diagnostics"], "payloadSizeBytes": row["payload_size_bytes"], "sourceGenerationFingerprint": row["source_generation_fingerprint"]}, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
