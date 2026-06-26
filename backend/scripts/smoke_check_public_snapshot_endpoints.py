from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path
from typing import Any, Dict, Optional, Tuple

import requests

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from backend.scripts.pokemon_snapshot_builders import get_client, resolve_set_row


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Smoke-check public snapshot endpoints for a Pokemon set")
    parser.add_argument("--set-id", required=True, help="Set id/canonical key/pokemon api set id")
    parser.add_argument("--base-url", default="http://127.0.0.1:8000", help="Backend base URL")
    return parser.parse_args()


def _get_json(url: str, timeout: int = 12) -> Tuple[int, float, Optional[Dict[str, Any]], str]:
    started = time.perf_counter()
    response = requests.get(url, timeout=timeout)
    elapsed_ms = (time.perf_counter() - started) * 1000.0
    body_text = response.text or ""
    payload = None
    try:
        payload = response.json()
    except Exception:
        payload = None
    return response.status_code, elapsed_ms, payload, body_text


def _payload_key_counts(payload: Optional[Dict[str, Any]]) -> Dict[str, int]:
    if not isinstance(payload, dict):
        return {}
    return {
        "top_hits": len(payload.get("top_hits") or []),
        "targets": len(payload.get("targets") or []),
        "cards": len(payload.get("cards") or []),
        "history": len(payload.get("history") or []),
    }


def _print_result(label: str, status: int, elapsed_ms: float, payload: Optional[Dict[str, Any]]) -> None:
    counts = _payload_key_counts(payload)
    print(
        json.dumps(
            {
                "endpoint": label,
                "status": status,
                "elapsedMs": round(elapsed_ms, 2),
                "keyCounts": counts,
            }
        )
    )


def _has_db_top_hits(set_id: str) -> bool:
    client = get_client()
    row = (
        client.table("pokemon_set_page_snapshot_latest")
        .select("set_id,payload_json")
        .eq("set_id", set_id)
        .limit(1)
        .execute()
    )
    rows = list(row.data or [])
    if not rows:
        return False
    payload = rows[0].get("payload_json") if isinstance(rows[0].get("payload_json"), dict) else {}
    return bool(payload.get("top_hits"))


def main() -> None:
    args = _parse_args()
    base_url = args.base_url.rstrip("/")
    set_input = str(args.set_id).strip()

    client = get_client()
    set_row = resolve_set_row(client, set_input)
    set_id = str(set_row["id"])
    db_has_top_hits = _has_db_top_hits(set_id)

    failures = []

    set_page_url = f"{base_url}/tcgs/pokemon/sets/{set_input}/page"
    targets_url = f"{base_url}/explore/rip-statistics/targets?limit=150"
    cards_url = f"{base_url}/tcgs/pokemon/sets/{set_input}/cards"
    dashboard_url = f"{base_url}/tcgs/pokemon/sets/{set_input}/market/dashboard?window=365d"

    status, elapsed_ms, payload, body = _get_json(set_page_url)
    _print_result("set_page", status, elapsed_ms, payload)
    if status >= 500:
        failures.append(f"set_page status={status}")
    if elapsed_ms > 1500:
        failures.append(f"set_page slow elapsedMs={round(elapsed_ms, 2)}")
    if not isinstance(payload, dict) or not isinstance(payload.get("summary"), dict):
        failures.append("set_page missing summary")
    if db_has_top_hits and not (isinstance(payload, dict) and (payload.get("top_hits") or [])):
        failures.append("set_page missing top_hits while DB snapshot has top_hits")

    status, elapsed_ms, payload, body = _get_json(targets_url)
    _print_result("targets", status, elapsed_ms, payload)
    if status >= 500:
        failures.append(f"targets status={status}")

    status, elapsed_ms, payload, body = _get_json(cards_url)
    _print_result("cards", status, elapsed_ms, payload)
    if status in (500, 504):
        failures.append(f"cards status={status}")

    status, elapsed_ms, payload, body = _get_json(dashboard_url)
    _print_result("market_dashboard", status, elapsed_ms, payload)
    if status >= 500:
        failures.append(f"market_dashboard status={status}")
    if elapsed_ms > 5000:
        failures.append(f"market_dashboard slow elapsedMs={round(elapsed_ms, 2)}")

    if failures:
        print("smoke_check_public_snapshot_endpoints: FAILED")
        for failure in failures:
            print(f"- {failure}")
        raise SystemExit(1)

    print("smoke_check_public_snapshot_endpoints: PASSED")


if __name__ == "__main__":
    main()
