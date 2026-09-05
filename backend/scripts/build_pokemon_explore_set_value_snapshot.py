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
    read_initial_selected_set_movers,
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

MARKET_READY_VIEW = "pokemon_market_root_set_market_ready_v1"
CANONICAL_HISTORY_RPC = "get_pokemon_market_root_set_value_daily_history_bulk_v1"
CANONICAL_HISTORY_START = "1999-01-01"
CANONICAL_HISTORY_SET_BATCH = 4


def _attach_initial_selected_set_movers(client, row: dict) -> None:
    """Publish the #1 Set Value target's canonical 7D movers, never full Cards."""
    payload = row.get("payload_json") or {}
    published_sets = payload.get("sets") or []
    if not published_sets:
        return
    contract = read_initial_selected_set_movers(client, published_sets[0])
    payload["initialSelectedSetMovers"] = contract
    items = contract.get("items") or []
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
    """Current market-domain Set Value cohort, independent of RIP/simulation.

    The global Market snapshot remains one-row-per-set today, so it publishes
    the certified ``standard`` scope. Vintage First/Unlimited/Shadowless scopes
    remain separately available in the canonical authority until the frontend
    receives an explicit edition-scope selector instead of silently mixing them.
    """
    rows = list((
        client.table(MARKET_READY_VIEW)
        .select(
            "set_id,set_name,canonical_key,era_name,release_date,logo_image_url,"
            "symbol_image_url,market_scope,canonical_market_date,market_publication_ready,"
            "current_certification_status"
        )
        .eq("market_scope", "standard")
        .eq("market_publication_ready", True)
        .eq("canonical_market_date", str(market_date)[:10])
        .order("release_date")
        .execute()
    ).data or [])
    return [
        {
            "id": row.get("set_id"),
            "name": row.get("set_name"),
            "canonical_key": row.get("canonical_key"),
            "era": row.get("era_name"),
            "release_date": row.get("release_date"),
            "logo_image_url": row.get("logo_image_url"),
            "symbol_image_url": row.get("symbol_image_url"),
            "market_scope": row.get("market_scope"),
            "market_publication_ready": bool(row.get("market_publication_ready")),
            "current_certification_status": row.get("current_certification_status"),
        }
        for row in rows
        if row.get("set_id")
    ]


def _load_canonical_histories(client, set_ids, *, through_date: str):
    """Canonical parent/subset-aware Set Value history for the Market cohort.

    The per-root DB function is the mathematical authority. The bulk RPC merely
    batches it; small set batches keep PostgREST responses below row limits.
    Historical dates that fail their own constituent certification are omitted
    instead of silently drawing an incomplete basket into the trend.
    """
    grouped = defaultdict(list)
    limit_date = str(through_date)[:10]
    for offset in range(0, len(set_ids), CANONICAL_HISTORY_SET_BATCH):
        batch = set_ids[offset:offset + CANONICAL_HISTORY_SET_BATCH]
        response = client.rpc(
            CANONICAL_HISTORY_RPC,
            {
                "p_root_set_ids": batch,
                "p_start_date": CANONICAL_HISTORY_START,
                "p_end_date": limit_date,
            },
        ).execute()
        for row in list(response.data or []):
            if str(row.get("market_scope") or "") != "standard":
                continue
            if row.get("certified_on_date") is not True:
                continue
            grouped[str(row.get("set_id"))].append({
                "set_id": row.get("set_id"),
                "snapshot_date": row.get("market_date"),
                "set_value": row.get("set_value"),
            })
    for rows in grouped.values():
        rows.sort(key=lambda row: str(row.get("snapshot_date") or ""))
    return grouped


def build(*, client, market_date: str, commit: bool, market_index_history=None, market_overview=None) -> dict:
    # Broad Set Value publication cohort: current, certified market data only.
    sets = _load_sets(client, market_date=market_date)
    set_ids = [str(row["id"]) for row in sets]
    if not set_ids:
        raise ExploreSetValueUnavailable(
            "no certified-current standard Set Value scopes are available",
            diagnostics={"marketDate": str(market_date)[:10]},
        )

    dashboards = []
    # Set dashboard rows are optional/additive for Cards Market Index data;
    # they are not Set Value authority. Absence cannot shrink this cohort.
    for offset in range(0, len(set_ids), 20):
        result = (client.table("pokemon_set_market_dashboard_snapshot_latest")
            .select("set_id,window_key,set_value_histories_json,latest_market_date,updated_at,cardsMarket:payload_json->cardsMarket")
            .eq("window_key", "365d").in_("set_id", set_ids[offset:offset + 20]).execute())
        dashboards.extend(result.data or [])

    histories = _load_canonical_histories(client, set_ids, through_date=market_date)

    # The global Market Overview/index is a separate, already-published contract
    # with its own cohort and strict parity audit. Expanding Set Value coverage
    # must not silently redefine Raw/Top-Chase/Sealed index constituents here.
    overview = market_overview
    if overview is None:
        history = market_index_history
        if history is None:
            history = read_index_history(client, through_date=market_date)
        overview_sets = resolve_canonical_overview_sets(client, market_date=market_date)
        overview_set_ids = [str(row["id"]) for row in overview_sets]
        overview = build_canonical_market_overview(
            client,
            market_date=market_date,
            history=history,
            set_ids=overview_set_ids,
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
    print(json.dumps({
        "status": "validated",
        **row["_diagnostics"],
        "payloadSizeBytes": row["payload_size_bytes"],
        "sourceGenerationFingerprint": row["source_generation_fingerprint"],
    }, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
