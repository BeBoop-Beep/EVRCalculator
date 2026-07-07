"""Optional local smoke check for the Pokemon set slim-contract endpoints.

Hits a small, fixed list of local sets against a running backend (default
http://127.0.0.1:8000) and prints status code, payload bytes, and key data
counts for each of the 8 slim contracts. Never touches the forbidden legacy
endpoints (full /market/dashboard, full /cards, /page) — this script exists
to prove the slim contracts alone are enough, not to exercise the legacy
ones. Read-only: plain GET requests only.

Not required for production or CI — a convenience for local dev/debugging.

Usage:
    python backend/scripts/smoke_check_pokemon_set_slim_endpoints.py
    python backend/scripts/smoke_check_pokemon_set_slim_endpoints.py --base-url http://127.0.0.1:8000
    python backend/scripts/smoke_check_pokemon_set_slim_endpoints.py --set-ids perfect-order,shrouded-fable
"""

from __future__ import annotations

import argparse
import json
import time
from typing import Any, Dict, List, Optional, Tuple

import requests

DEFAULT_SET_IDS = ("perfect-order", "shrouded-fable", "prismatic-evolutions", "ascended-heroes")

# The only endpoints this script is allowed to call — matches the slim
# contracts every normal set-detail tab uses. Deliberately does NOT include
# /market/dashboard, /cards (full), or /page.
SLIM_ENDPOINTS: List[Tuple[str, str]] = [
    ("shell", "/tcgs/pokemon/sets/{set_id}/shell"),
    ("overview", "/tcgs/pokemon/sets/{set_id}/overview?window=365d"),
    ("top_chase", "/tcgs/pokemon/sets/{set_id}/market/top-chase?window=30D&limit=10"),
    ("movers", "/tcgs/pokemon/sets/{set_id}/market/movers?window=30D&limit=5"),
    ("cards_page", "/tcgs/pokemon/sets/{set_id}/cards/page?page=1&page_size=60"),
    ("cards_validation", "/tcgs/pokemon/sets/{set_id}/cards/validation"),
    ("pull_rates", "/tcgs/pokemon/sets/{set_id}/pull-rates"),
    ("insights", "/tcgs/pokemon/sets/{set_id}/insights"),
]

FORBIDDEN_ENDPOINTS_NOT_CALLED = (
    "/market/dashboard (full)",
    "/cards (full, unpaginated)",
    "/page (full legacy snapshot)",
)


def _key_counts(contract: str, payload: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    if not isinstance(payload, dict):
        return {}
    if contract == "overview":
        histories = payload.get("setValueHistoriesByScope") or {}
        return {
            "historyPoints": len(histories.get("standard") or []),
            "performancePoints": len(payload.get("performanceVsCostHistory") or []),
        }
    if contract == "top_chase":
        return {"topChaseCards": len(payload.get("topChaseCards") or [])}
    if contract == "movers":
        market_movers = payload.get("marketMovers") or {}
        return {
            "heatingUp": len(market_movers.get("heatingUp") or []),
            "coolingOff": len(market_movers.get("coolingOff") or []),
        }
    if contract in ("cards_page",):
        pagination = payload.get("pagination") or {}
        return {"cardsOnPage": len(payload.get("cards") or []), "totalCards": pagination.get("totalCards")}
    if contract == "cards_validation":
        correlation = payload.get("cardAppealMarketPriceCorrelation") or {}
        return {"cards": len(payload.get("cards") or []), "correlationN": correlation.get("n")}
    if contract == "pull_rates":
        return {"hasPullRates": bool(payload.get("pullRates"))}
    if contract == "insights":
        outcome_distribution = payload.get("outcomeDistribution") or {}
        return {
            "distributionBins": len(outcome_distribution.get("distributionBins") or []),
            "simulationDrivers": len(payload.get("simulationDrivers") or []),
        }
    return {}


def check_set(base_url: str, set_id: str, *, timeout: int = 15) -> List[Dict[str, Any]]:
    results = []
    for contract, path_template in SLIM_ENDPOINTS:
        url = f"{base_url}{path_template.format(set_id=set_id)}"
        started = time.perf_counter()
        try:
            response = requests.get(url, timeout=timeout)
            elapsed_ms = round((time.perf_counter() - started) * 1000, 1)
            status = response.status_code
            byte_size = len(response.content or b"")
            try:
                payload = response.json()
            except Exception:
                payload = None
        except Exception as exc:  # noqa: BLE001 - smoke check, report and continue
            elapsed_ms = round((time.perf_counter() - started) * 1000, 1)
            status = None
            byte_size = 0
            payload = None
            results.append(
                {
                    "set_id": set_id,
                    "contract": contract,
                    "status": status,
                    "elapsedMs": elapsed_ms,
                    "bytes": byte_size,
                    "error": str(exc),
                    "keyCounts": {},
                }
            )
            continue

        results.append(
            {
                "set_id": set_id,
                "contract": contract,
                "status": status,
                "elapsedMs": elapsed_ms,
                "bytes": byte_size,
                "error": None,
                "keyCounts": _key_counts(contract, payload),
            }
        )
    return results


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Optional local smoke check: hit the 8 slim Pokemon set contracts for a small set list."
    )
    parser.add_argument("--base-url", default="http://127.0.0.1:8000", help="Backend base URL.")
    parser.add_argument(
        "--set-ids",
        default=",".join(DEFAULT_SET_IDS),
        help="Comma-separated set ids/canonical keys/slugs to check.",
    )
    return parser.parse_args()


def main() -> int:
    args = build_parser()
    base_url = args.base_url.rstrip("/")
    set_ids = [value.strip() for value in args.set_ids.split(",") if value.strip()]

    all_results: List[Dict[str, Any]] = []
    for set_id in set_ids:
        print(f"\n=== {set_id} ===")
        results = check_set(base_url, set_id)
        all_results.extend(results)
        for result in results:
            print(json.dumps(result))

    failures = [row for row in all_results if row["error"] or (row["status"] is not None and row["status"] >= 500)]

    print("\n=== Forbidden endpoints (never called by this smoke check) ===")
    for endpoint in FORBIDDEN_ENDPOINTS_NOT_CALLED:
        print(f"  NOT called: {endpoint}")

    print(f"\nChecked {len(set_ids)} set(s) x {len(SLIM_ENDPOINTS)} contracts = {len(all_results)} requests.")
    print(f"Failures (5xx or request error): {len(failures)}")
    for failure in failures:
        print(f"  {failure['set_id']} / {failure['contract']}: status={failure['status']} error={failure['error']}")

    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
