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
from backend.db.services.publication_gate import add_publication_gate_args, enforce_cli_publication_gate
from backend.desirability.public_analytics_policy import is_public_analytics_eligible
from backend.scripts.pokemon_snapshot_builders import get_client


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(description="Build the compact global Market Set Value snapshot")
    mode = result.add_mutually_exclusive_group(required=True)
    mode.add_argument("--dry-run", action="store_true")
    mode.add_argument("--commit", action="store_true")
    add_publication_gate_args(result)
    return result


def _load_sets(client):
    rows = list(client.table("sets").select("id,canonical_key,name,era_id,logo_image_url,symbol_image_url,supports_opening_simulation").execute().data or [])
    eligible = [row for row in rows if row.get("supports_opening_simulation") is True and is_public_analytics_eligible(row)]
    era_ids = sorted({str(row.get("era_id")) for row in eligible if row.get("era_id")})
    eras = {}
    if era_ids:
        eras = {str(row.get("id")): row.get("name") for row in (client.table("eras").select("id,name").in_("id", era_ids).execute().data or [])}
    return [{**row, "era": eras.get(str(row.get("era_id")))} for row in eligible]


def _load_canonical_histories(client, set_ids):
    grouped = defaultdict(list)
    page_size = 1000
    start = 0
    while True:
        rows = list((client.table("pokemon_set_value_daily_history")
            .select("set_id,snapshot_date,set_value").in_("set_id", set_ids)
            .eq("value_scope", "standard").order("snapshot_date", desc=False)
            .range(start, start + page_size - 1).execute()).data or [])
        for row in rows:
            grouped[str(row.get("set_id"))].append(row)
        if len(rows) < page_size:
            break
        start += page_size
    return grouped


def build(*, client, market_date: str, commit: bool) -> dict:
    sets = _load_sets(client)
    set_ids = [str(row["id"]) for row in sets]
    dashboards = []
    # One bounded query per batch, never one request per set. Read only the
    # split Set Value column; raw dashboard payload_json is intentionally absent.
    for offset in range(0, len(set_ids), 20):
        result = (client.table("pokemon_set_market_dashboard_snapshot_latest")
            .select("set_id,window_key,set_value_histories_json,latest_market_date,updated_at")
            .eq("window_key", "365d").in_("set_id", set_ids[offset:offset + 20]).execute())
        dashboards.extend(result.data or [])
    histories = _load_canonical_histories(client, set_ids)
    row = build_global_set_value_row(sets, dashboards, histories, target_market_date=market_date)
    if commit:
        upsert_explore_set_value_snapshot(row, client=client)
    return row


def main() -> None:
    args = parser().parse_args()
    client = get_client()
    gate = enforce_cli_publication_gate(client, commit=bool(args.commit), market_date=args.market_date, override=args.force_publish, entry_point="Global Market Set Value snapshot")
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
