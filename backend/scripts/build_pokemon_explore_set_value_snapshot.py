from __future__ import annotations

import argparse
import json
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
from backend.db.services.pokemon_market_index_service import build_market_overview, read_index_history
from backend.db.services.pokemon_global_sealed_market_service import (
    build_global_sealed_market,
    build_global_sealed_segments,
    read_global_sealed_source_snapshots,
)
from backend.db.services.pokemon_global_card_market_segments_service import (
    build_card_segments_payload,
    build_global_card_segments,
    load_global_card_constituent_rows,
    read_canonical_card_rarities,
)
from backend.desirability.public_analytics_policy import is_public_analytics_eligible
from backend.scripts.pokemon_snapshot_builders import get_client


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(description="Build the compact global Market Set Value snapshot")
    mode = result.add_mutually_exclusive_group(required=True)
    mode.add_argument("--dry-run", action="store_true")
    mode.add_argument("--commit", action="store_true")
    add_publication_gate_args(result)
    return result


def _load_sets(client, *, market_date: str):
    rows = list(client.table("sets").select("id,canonical_key,name,era_id,release_date,logo_image_url,symbol_image_url,supports_opening_simulation").execute().data or [])
    eligible = [row for row in rows if row.get("supports_opening_simulation") is True
                and is_public_analytics_eligible(row)
                and (not row.get("release_date") or str(row["release_date"])[:10] <= market_date)]
    era_ids = sorted({str(row.get("era_id")) for row in eligible if row.get("era_id")})
    eras = {}
    if era_ids:
        eras = {str(row.get("id")): row.get("name") for row in (client.table("eras").select("id,name").in_("id", era_ids).execute().data or [])}
    return [{**row, "era": eras.get(str(row.get("era_id")))} for row in eligible]


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
    # split Set Value column; raw dashboard payload_json is intentionally absent.
    for offset in range(0, len(set_ids), 20):
        result = (client.table("pokemon_set_market_dashboard_snapshot_latest")
            .select("set_id,window_key,set_value_histories_json,latest_market_date,updated_at")
            .eq("window_key", "365d").in_("set_id", set_ids[offset:offset + 20]).execute())
        dashboards.extend(result.data or [])
    histories = _load_canonical_histories(client, set_ids, through_date=market_date)
    overview = market_overview
    if overview is None:
        history = market_index_history
        if history is None:
            history = read_index_history(client, through_date=market_date)
        sealed_rows = read_global_sealed_source_snapshots(client, set_ids)
        sealed_payloads = [dict(row.get("payload_json") or {}) for row in sealed_rows]
        sealed_market = build_global_sealed_market(sealed_payloads, market_date=market_date)
        # Sealed product-family submarkets, built from the SAME constituent
        # universe the parent used and republishing the parent verbatim.
        sealed_segments = build_global_sealed_segments(
            sealed_payloads, market_date=market_date, total=sealed_market
        )
        # Card-rarity submarkets of the Raw Card Market, built from canonical
        # per-card constituents over the window Raw itself already covers. A
        # failure here must not take the whole Market snapshot down: the
        # segments are additive, so they degrade to unavailable.
        card_segments = None
        try:
            raw_history_start = min(
                (str(row.get("market_date"))[:10] for row in history
                 if str(row.get("index_key")) == "raw"),
                default=market_date,
            )
            rarity_by_card = read_canonical_card_rarities(client, set_ids)
            constituent_rows = load_global_card_constituent_rows(
                client, set_ids, start_date=raw_history_start, end_date=market_date,
            )
            raw_card_segments = build_global_card_segments(
                constituent_rows, rarity_by_card, market_date=market_date,
                parent_basket_value=None,
            )
            card_segments = build_card_segments_payload(raw_card_segments)
        except Exception as exc:  # noqa: BLE001 - additive analytics only
            print(f"card segments unavailable: {exc}")
            card_segments = build_card_segments_payload(None)
        overview = build_market_overview(
            history, market_date=market_date,
            sealed_market=sealed_market, sealed_segments=sealed_segments,
            card_segments=card_segments,
        )
        if card_segments and isinstance(card_segments.get("raw"), dict):
            # The parent's published basket value is the reconciliation anchor,
            # and it is read from the built overview rather than recomputed.
            card_segments["raw"].setdefault("reconciliation", {})
            card_segments["raw"]["reconciliation"]["parentBasketValue"] = (
                overview.get("raw", {}).get("basketValue")
            )
    row = build_global_set_value_row(sets, dashboards, histories, target_market_date=market_date, market_overview=overview)
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
