"""Read-only diagnostic: audits every Pokemon set's slim-contract health.

Calls the same public service functions that back the frontend's slim
endpoints (shell, overview, market/top-chase, market/movers, cards/page,
cards/validation, pull-rates, insights) for every Pokemon set, and reports
whether each contract has usable data and whether its payload size/status is
healthy. This is a diagnostic pass only — see Phase 5B task notes: it never
rebuilds a snapshot, never writes to the database, and never changes
scoring/math. A future phase decides the safest backfill/rebuild path for
anything this script finds missing.

READ_ONLY_AUDIT = True — every call below is a read (SELECT-equivalent via
the existing service layer). No inserts/updates/deletes/RPCs/snapshot
builders are invoked.

Usage:
    python backend/scripts/audit_pokemon_set_slim_contract_health.py
    python backend/scripts/audit_pokemon_set_slim_contract_health.py --limit 10
    python backend/scripts/audit_pokemon_set_slim_contract_health.py --set-ids perfect-order,shrouded-fable
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
import time
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

READ_ONLY_AUDIT = True  # This script must never insert/update/delete/rebuild.

MOVERS_WINDOWS = ("1D", "7D", "30D")

# Matches the budgets each slim contract's own service module enforces
# (PULL_RATES_PAYLOAD_BUDGET_BYTES, INSIGHTS_PAYLOAD_BUDGET_BYTES, and the
# *_under_*kb tests for overview/top-chase/movers/cards/shell).
PAYLOAD_BUDGETS_BYTES: Dict[str, int] = {
    "shell": 75_000,
    "overview": 250_000,
    "top_chase": 250_000,
    "movers": 150_000,
    "cards_page": 250_000,
    "cards_validation": 250_000,
    "pull_rates": 150_000,
    "insights": 400_000,
}

CONTRACT_LABELS: Dict[str, str] = {
    "shell": "shell",
    "overview": "overview",
    "top_chase": "market/top-chase",
    "movers": "market/movers",
    "cards_page": "cards/page",
    "cards_validation": "cards/validation",
    "pull_rates": "pull-rates",
    "insights": "insights",
}

CSV_FIELDNAMES: List[str] = [
    "set_id",
    "set_name",
    "canonical_key",
    "pokemon_api_set_id",
    "era",
    "has_shell",
    "shell_bytes",
    "has_overview",
    "overview_history_points",
    "overview_performance_points",
    "overview_bytes",
    "has_top_chase",
    "top_chase_count",
    "top_chase_history_card_count",
    "top_chase_bytes",
    "has_movers_1d",
    "has_movers_7d",
    "has_movers_30d",
    "mover_count_1d",
    "mover_count_7d",
    "mover_count_30d",
    "movers_bytes",
    "has_cards_page",
    "cards_page_count",
    "cards_total_count",
    "cards_page_bytes",
    "has_cards_validation",
    "validation_card_count",
    "validation_correlation_n",
    "cards_validation_bytes",
    "has_pull_rates",
    "pull_rates_bytes",
    "has_insights",
    "insights_distribution_bins",
    "insights_simulation_drivers",
    "insights_bytes",
    "health_status",
    "warnings",
]


# ---------------------------------------------------------------------------
# Pure helpers — no DB/network access, unit-tested in
# backend/tests/unit/scripts/test_audit_pokemon_set_slim_contract_health.py
# ---------------------------------------------------------------------------


def measure_payload_bytes(payload: Any) -> int:
    """Serialize payload the same way the API would and return its byte size."""
    if payload is None:
        return 0
    return len(json.dumps(payload, default=str).encode("utf-8"))


def classify_health_status(*, has_data: bool, byte_size: int, budget_bytes: int, errored: bool = False) -> str:
    """Classify a single contract's health as one pure, deterministic label.

    Priority: a fetch error always wins (nothing else is trustworthy), then
    over-budget (a real problem even if data is present), then empty (no
    usable data yet), then healthy.
    """
    if errored:
        return "error"
    if budget_bytes > 0 and byte_size > budget_bytes:
        return "over_budget"
    if not has_data:
        return "empty"
    return "healthy"


def classify_missing_data_warning(contract_key: str, has_data: bool) -> Optional[str]:
    """Return a human-readable warning when a contract has no usable data."""
    if has_data:
        return None
    label = CONTRACT_LABELS.get(contract_key, contract_key)
    return f"{label} has no usable data for this set"


def classify_budget_violation(contract_key: str, byte_size: int, budget_bytes: int) -> Optional[str]:
    """Return a human-readable warning when a contract exceeds its payload budget."""
    if budget_bytes <= 0 or byte_size <= budget_bytes:
        return None
    label = CONTRACT_LABELS.get(contract_key, contract_key)
    return f"{label} payload is {byte_size:,}B, over its {budget_bytes:,}B budget"


def worst_sets_by_missing_contracts(rows: List[Dict[str, Any]], *, top_n: int = 10) -> List[Tuple[str, int]]:
    """Pure ranking helper: (set_name, missing_contract_count) sorted worst-first."""
    scored = [(row.get("set_name") or row.get("set_id") or "?", int(row.get("missing_contract_count") or 0)) for row in rows]
    scored.sort(key=lambda entry: entry[1], reverse=True)
    return scored[:top_n]


# ---------------------------------------------------------------------------
# Per-contract fetchers — each wraps one real service-function call so the
# audit reflects exactly what the live endpoint would return. Every call is
# read-only; none of these functions insert/update/delete/rebuild anything.
# ---------------------------------------------------------------------------


def _safe_call(fn: Callable[..., Any], *args: Any, **kwargs: Any) -> Tuple[Optional[Dict[str, Any]], Optional[str]]:
    try:
        return fn(*args, **kwargs), None
    except Exception as exc:  # noqa: BLE001 - diagnostic tool, report and continue
        return None, f"{type(exc).__name__}: {exc}"


def _audit_shell(services: Dict[str, Any], set_id: str) -> Dict[str, Any]:
    payload, error = _safe_call(services["shell"].get_pokemon_set_shell_snapshot_payload, set_id)
    has_data = bool(payload) and bool(payload.get("summary")) if payload else False
    byte_size = measure_payload_bytes(payload)
    return {"payload": payload, "error": error, "has_data": has_data, "bytes": byte_size}


def _audit_overview(services: Dict[str, Any], set_id: str) -> Dict[str, Any]:
    payload, error = _safe_call(services["overview"].get_pokemon_set_overview_snapshot_payload, set_id)
    histories_by_scope = (payload or {}).get("setValueHistoriesByScope") or {}
    standard_history = histories_by_scope.get("standard") or []
    performance_history = (payload or {}).get("performanceVsCostHistory") or []
    has_data = len(standard_history) > 0 or any(len(v or []) > 0 for v in histories_by_scope.values())
    byte_size = measure_payload_bytes(payload)
    return {
        "payload": payload,
        "error": error,
        "has_data": has_data,
        "bytes": byte_size,
        "history_points": len(standard_history),
        "performance_points": len(performance_history),
    }


def _audit_top_chase(services: Dict[str, Any], set_id: str) -> Dict[str, Any]:
    payload, error = _safe_call(
        services["top_chase"].get_pokemon_set_top_chase_snapshot_payload, set_id, window="30D", limit=10
    )
    cards = (payload or {}).get("topChaseCards") or []
    histories = (payload or {}).get("topChaseCardHistories") or {}
    history_card_count = sum(1 for points in histories.values() if points)
    has_data = len(cards) > 0
    byte_size = measure_payload_bytes(payload)
    return {
        "payload": payload,
        "error": error,
        "has_data": has_data,
        "bytes": byte_size,
        "count": len(cards),
        "history_card_count": history_card_count,
    }


def _audit_movers(services: Dict[str, Any], set_id: str) -> Dict[str, Any]:
    per_window: Dict[str, Dict[str, Any]] = {}
    for window in MOVERS_WINDOWS:
        payload, error = _safe_call(
            services["movers"].get_pokemon_set_market_movers_payload, set_id, window=window, limit=5
        )
        market_movers = (payload or {}).get("marketMovers") or {}
        heating = market_movers.get("heatingUp") or []
        cooling = market_movers.get("coolingOff") or []
        count = len(heating) + len(cooling)
        per_window[window] = {
            "payload": payload,
            "error": error,
            "has_data": count > 0,
            "bytes": measure_payload_bytes(payload),
            "count": count,
        }
    # A single representative byte size (30D, the default window) drives the
    # movers budget check — three windows' worth of near-identical structure
    # would otherwise triple-count against one budget.
    representative_bytes = per_window["30D"]["bytes"]
    combined_error = "; ".join(w["error"] for w in per_window.values() if w["error"]) or None
    return {"per_window": per_window, "bytes": representative_bytes, "error": combined_error}


def _audit_cards_page(services: Dict[str, Any], set_id: str) -> Dict[str, Any]:
    payload, error = _safe_call(
        services["cards_page"].get_pokemon_set_cards_page_snapshot_payload, set_id, page=1, page_size=60
    )
    cards = (payload or {}).get("cards") or []
    pagination = (payload or {}).get("pagination") or {}
    total_cards = pagination.get("totalCards")
    has_data = len(cards) > 0
    byte_size = measure_payload_bytes(payload)
    return {
        "payload": payload,
        "error": error,
        "has_data": has_data,
        "bytes": byte_size,
        "count": len(cards),
        "total_count": total_cards if total_cards is not None else len(cards),
    }


def _audit_cards_validation(services: Dict[str, Any], set_id: str) -> Dict[str, Any]:
    payload, error = _safe_call(
        services["cards_validation"].get_pokemon_set_card_validation_snapshot_payload,
        set_id,
        max_cards=300,
        include_plot_rows=True,
    )
    cards = (payload or {}).get("cards") or []
    correlation = (payload or {}).get("cardAppealMarketPriceCorrelation") or {}
    has_data = len(cards) > 0
    byte_size = measure_payload_bytes(payload)
    return {
        "payload": payload,
        "error": error,
        "has_data": has_data,
        "bytes": byte_size,
        "card_count": len(cards),
        "correlation_n": correlation.get("n"),
    }


def _audit_pull_rates(services: Dict[str, Any], set_id: str) -> Dict[str, Any]:
    payload, error = _safe_call(services["pull_rates"].get_pokemon_set_pull_rates_snapshot_payload, set_id)
    has_data = bool((payload or {}).get("pullRates"))
    byte_size = measure_payload_bytes(payload)
    return {"payload": payload, "error": error, "has_data": has_data, "bytes": byte_size}


def _audit_insights(services: Dict[str, Any], set_id: str) -> Dict[str, Any]:
    payload, error = _safe_call(services["insights"].get_pokemon_set_insights_snapshot_payload, set_id)
    summary = (payload or {}).get("summary") or {}
    outcome_distribution = (payload or {}).get("outcomeDistribution") or {}
    distribution_bins = outcome_distribution.get("distributionBins") or []
    simulation_drivers = (payload or {}).get("simulationDrivers") or []
    has_data = bool(summary)
    byte_size = measure_payload_bytes(payload)
    return {
        "payload": payload,
        "error": error,
        "has_data": has_data,
        "bytes": byte_size,
        "distribution_bins": len(distribution_bins),
        "simulation_drivers": len(simulation_drivers),
    }


def _default_services() -> Dict[str, Any]:
    from backend.db.services import pokemon_public_snapshot_service as snapshot_service
    from backend.db.services import pokemon_set_market_service as market_service

    return {
        "shell": snapshot_service,
        "overview": snapshot_service,
        "top_chase": snapshot_service,
        "movers": market_service,
        "cards_page": snapshot_service,
        "cards_validation": snapshot_service,
        "pull_rates": snapshot_service,
        "insights": snapshot_service,
    }


def audit_set(set_row: Dict[str, Any], *, services: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """Audit every slim contract for one Pokemon set. Read-only."""
    services = services or _default_services()
    set_id = str(set_row.get("id") or "")

    shell = _audit_shell(services, set_id)
    overview = _audit_overview(services, set_id)
    top_chase = _audit_top_chase(services, set_id)
    movers = _audit_movers(services, set_id)
    cards_page = _audit_cards_page(services, set_id)
    cards_validation = _audit_cards_validation(services, set_id)
    pull_rates = _audit_pull_rates(services, set_id)
    insights = _audit_insights(services, set_id)

    movers_1d = movers["per_window"]["1D"]
    movers_7d = movers["per_window"]["7D"]
    movers_30d = movers["per_window"]["30D"]

    contract_results = {
        "shell": shell,
        "overview": overview,
        "top_chase": top_chase,
        "movers": {"has_data": movers_30d["has_data"], "bytes": movers["bytes"], "error": movers["error"]},
        "cards_page": cards_page,
        "cards_validation": cards_validation,
        "pull_rates": pull_rates,
        "insights": insights,
    }

    warnings: List[str] = []
    missing_contract_count = 0
    contract_statuses: Dict[str, str] = {}
    for contract_key, result in contract_results.items():
        errored = bool(result.get("error"))
        has_data = bool(result.get("has_data"))
        byte_size = int(result.get("bytes") or 0)
        budget = PAYLOAD_BUDGETS_BYTES[contract_key]
        status = classify_health_status(has_data=has_data, byte_size=byte_size, budget_bytes=budget, errored=errored)
        contract_statuses[contract_key] = status
        if errored:
            warnings.append(f"{CONTRACT_LABELS[contract_key]} fetch failed: {result['error']}")
            missing_contract_count += 1
        else:
            missing_warning = classify_missing_data_warning(contract_key, has_data)
            if missing_warning:
                warnings.append(missing_warning)
                missing_contract_count += 1
            budget_warning = classify_budget_violation(contract_key, byte_size, budget)
            if budget_warning:
                warnings.append(budget_warning)

    overall_status = "healthy"
    if any(status == "error" for status in contract_statuses.values()):
        overall_status = "error"
    elif any(status == "over_budget" for status in contract_statuses.values()):
        overall_status = "over_budget"
    elif any(status == "empty" for status in contract_statuses.values()):
        overall_status = "degraded"

    return {
        "set_id": set_id,
        "set_name": set_row.get("name"),
        "canonical_key": set_row.get("canonical_key"),
        "pokemon_api_set_id": set_row.get("pokemon_api_set_id"),
        "era": set_row.get("era_name") or set_row.get("era"),
        "has_shell": shell["has_data"],
        "shell_bytes": shell["bytes"],
        "has_overview": overview["has_data"],
        "overview_history_points": overview.get("history_points", 0),
        "overview_performance_points": overview.get("performance_points", 0),
        "overview_bytes": overview["bytes"],
        "has_top_chase": top_chase["has_data"],
        "top_chase_count": top_chase.get("count", 0),
        "top_chase_history_card_count": top_chase.get("history_card_count", 0),
        "top_chase_bytes": top_chase["bytes"],
        "has_movers_1d": movers_1d["has_data"],
        "has_movers_7d": movers_7d["has_data"],
        "has_movers_30d": movers_30d["has_data"],
        "mover_count_1d": movers_1d["count"],
        "mover_count_7d": movers_7d["count"],
        "mover_count_30d": movers_30d["count"],
        "movers_bytes": movers["bytes"],
        "has_cards_page": cards_page["has_data"],
        "cards_page_count": cards_page.get("count", 0),
        "cards_total_count": cards_page.get("total_count", 0),
        "cards_page_bytes": cards_page["bytes"],
        "has_cards_validation": cards_validation["has_data"],
        "validation_card_count": cards_validation.get("card_count", 0),
        "validation_correlation_n": cards_validation.get("correlation_n"),
        "cards_validation_bytes": cards_validation["bytes"],
        "has_pull_rates": pull_rates["has_data"],
        "pull_rates_bytes": pull_rates["bytes"],
        "has_insights": insights["has_data"],
        "insights_distribution_bins": insights.get("distribution_bins", 0),
        "insights_simulation_drivers": insights.get("simulation_drivers", 0),
        "insights_bytes": insights["bytes"],
        "health_status": overall_status,
        "warnings": "; ".join(warnings),
        "missing_contract_count": missing_contract_count,
        "_contract_statuses": contract_statuses,
    }


# ---------------------------------------------------------------------------
# Orchestration
# ---------------------------------------------------------------------------


def _load_sets(*, limit: Optional[int], set_ids: Optional[List[str]]) -> List[Dict[str, Any]]:
    from backend.db.services.pokemon_sets_catalog_service import get_pokemon_sets_catalog_payload

    catalog = get_pokemon_sets_catalog_payload()
    sets = list(catalog.get("sets") or [])

    if set_ids:
        wanted = {value.strip().lower() for value in set_ids if value.strip()}
        sets = [
            set_row
            for set_row in sets
            if str(set_row.get("id") or "").lower() in wanted
            or str(set_row.get("canonical_key") or "").lower() in wanted
            or str(set_row.get("slug") or "").lower() in wanted
            or str(set_row.get("pokemon_api_set_id") or "").lower() in wanted
        ]

    if limit is not None:
        sets = sets[:limit]

    return sets


def run_audit(*, limit: Optional[int] = None, set_ids: Optional[List[str]] = None, verbose: bool = True) -> List[Dict[str, Any]]:
    assert READ_ONLY_AUDIT is True, "This diagnostic must never run with mutations enabled."

    sets = _load_sets(limit=limit, set_ids=set_ids)
    services = _default_services()
    rows: List[Dict[str, Any]] = []
    total = len(sets)
    for index, set_row in enumerate(sets, start=1):
        started = time.perf_counter()
        row = audit_set(set_row, services=services)
        elapsed_ms = round((time.perf_counter() - started) * 1000, 1)
        rows.append(row)
        if verbose:
            print(f"[{index}/{total}] {row['set_name']} ({row['set_id']}) - {row['health_status']} - {elapsed_ms}ms")
    return rows


def write_outputs(rows: List[Dict[str, Any]], *, csv_path: Path, json_path: Path) -> None:
    csv_path.parent.mkdir(parents=True, exist_ok=True)
    json_path.parent.mkdir(parents=True, exist_ok=True)

    with csv_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=CSV_FIELDNAMES, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow(row)

    json_rows = [{key: value for key, value in row.items() if not key.startswith("_")} for row in rows]
    with json_path.open("w", encoding="utf-8") as handle:
        json.dump(json_rows, handle, indent=2, default=str)


def print_summary(rows: List[Dict[str, Any]]) -> None:
    total = len(rows)
    print("\n=== Pokemon set slim-contract health summary ===")
    print(f"Total sets checked: {total}")

    print("\nHealthy contract counts (has usable data, within budget):")
    for contract_key, label in CONTRACT_LABELS.items():
        healthy_count = sum(1 for row in rows if row["_contract_statuses"].get(contract_key) == "healthy")
        print(f"  {label:20s} {healthy_count}/{total}")

    print("\nWorst 10 sets by missing contract count:")
    for name, missing_count in worst_sets_by_missing_contracts(rows, top_n=10):
        if missing_count > 0:
            print(f"  {name:35s} missing {missing_count} contract(s)")

    print("\nLargest payload per contract:")
    byte_field_by_contract = {
        "shell": "shell_bytes",
        "overview": "overview_bytes",
        "top_chase": "top_chase_bytes",
        "movers": "movers_bytes",
        "cards_page": "cards_page_bytes",
        "cards_validation": "cards_validation_bytes",
        "pull_rates": "pull_rates_bytes",
        "insights": "insights_bytes",
    }
    for contract_key, label in CONTRACT_LABELS.items():
        field = byte_field_by_contract[contract_key]
        largest = max(rows, key=lambda row: row.get(field) or 0, default=None)
        if largest:
            print(f"  {label:20s} {largest.get(field, 0):>10,}B  ({largest['set_name']})")

    missing_top_chase = [row["set_name"] for row in rows if not row["has_top_chase"]]
    missing_overview = [row["set_name"] for row in rows if not row["has_overview"]]
    missing_insights = [row["set_name"] for row in rows if not row["has_insights"]]
    print(f"\nSets missing top-chase data: {len(missing_top_chase)}/{total}")
    print(f"Sets missing overview histories: {len(missing_overview)}/{total}")
    print(f"Sets missing insights data: {len(missing_insights)}/{total}")

    over_budget_count = sum(
        1 for row in rows if any(status == "over_budget" for status in row["_contract_statuses"].values())
    )
    print(f"Sets with at least one contract over its payload budget: {over_budget_count}/{total}")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Audit slim-contract data health for every Pokemon set (read-only).")
    parser.add_argument("--limit", type=int, default=None, help="Only audit the first N sets (useful for a fast smoke run).")
    parser.add_argument(
        "--set-ids",
        default=None,
        help="Comma-separated set ids/canonical keys/slugs/pokemon_api_set_ids to limit the audit to.",
    )
    parser.add_argument(
        "--csv-path",
        default=str(REPO_ROOT / "backend" / "logs" / "pokemon_set_slim_contract_health.csv"),
        help="Output CSV path.",
    )
    parser.add_argument(
        "--json-path",
        default=str(REPO_ROOT / "backend" / "logs" / "pokemon_set_slim_contract_health.json"),
        help="Output JSON path.",
    )
    parser.add_argument("--quiet", action="store_true", help="Suppress the per-set progress lines.")
    return parser


def main() -> int:
    args = build_parser().parse_args()
    set_ids = [value for value in (args.set_ids.split(",") if args.set_ids else [])]

    started = time.perf_counter()
    rows = run_audit(limit=args.limit, set_ids=set_ids or None, verbose=not args.quiet)
    elapsed_s = round(time.perf_counter() - started, 1)

    write_outputs(rows, csv_path=Path(args.csv_path), json_path=Path(args.json_path))
    print_summary(rows)
    print(f"\nWrote {len(rows)} rows to {args.csv_path} and {args.json_path} in {elapsed_s}s.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
