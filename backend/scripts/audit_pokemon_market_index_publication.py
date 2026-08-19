from __future__ import annotations

import argparse
import json
import math
import sys
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from backend.db.services.pokemon_market_index_service import build_market_index_history, build_market_overview, read_index_history
from backend.domain.pokemon.market_index import INDEX_KEYS, deterministic_fingerprint
from backend.scripts.pokemon_snapshot_builders import get_client


def _numeric_equal(left: Any, right: Any, tolerance: float = 1e-9) -> bool:
    try:
        a, b = float(left), float(right)
        return math.isfinite(a) and math.isfinite(b) and math.isclose(a, b, rel_tol=tolerance, abs_tol=tolerance)
    except (TypeError, ValueError):
        return False


def _compare_json(expected: Any, actual: Any, path: str, failures: list[str]) -> None:
    if isinstance(expected, dict):
        if not isinstance(actual, dict): failures.append(f"{path} type mismatch"); return
        if set(expected) != set(actual):
            # Name the difference. A published snapshot that predates an
            # additive contract extension (e.g. the tracked-value
            # `basketChanges` fields) otherwise reports only "keys mismatch",
            # which reads as corruption rather than "republish is pending".
            missing = sorted(set(expected) - set(actual)); extra = sorted(set(actual) - set(expected))
            failures.append(f"{path} keys mismatch (missing from actual: {missing}; unexpected in actual: {extra})")
            return
        for key in sorted(expected): _compare_json(expected[key], actual[key], f"{path}.{key}", failures)
    elif isinstance(expected, list):
        if not isinstance(actual, list) or len(expected) != len(actual): failures.append(f"{path} length/type mismatch"); return
        for index, (wanted, found) in enumerate(zip(expected, actual)): _compare_json(wanted, found, f"{path}[{index}]", failures)
    elif isinstance(expected, (int, float)) and not isinstance(expected, bool):
        if not _numeric_equal(expected, actual): failures.append(f"{path} numeric mismatch")
    elif expected != actual:
        failures.append(f"{path} mismatch")


def audit(client: Any, market_date: str) -> dict[str, Any]:
    expected_history = build_market_index_history(client, through_date=market_date)
    persisted_history = read_index_history(client, through_date=market_date)
    expected = {(str(row["market_date"])[:10], row["index_key"]): row for row in expected_history}
    actual = {(str(row["market_date"])[:10], row["index_key"]): row for row in persisted_history}
    failures: list[str] = []
    missing = sorted(set(expected) - set(actual)); unexpected = sorted(set(actual) - set(expected))
    if missing: failures.append(f"missing persisted history rows: {missing}")
    if unexpected: failures.append(f"unexpected persisted history rows: {unexpected}")
    for identity in sorted(set(expected) & set(actual)):
        wanted, found = expected[identity], actual[identity]
        prefix = f"{identity[0]} {identity[1]}"
        for field in ("basket_value", "normalized_index_value", "daily_return"):
            if wanted.get(field) is None or found.get(field) is None:
                if wanted.get(field) != found.get(field): failures.append(f"{prefix} {field} mismatch")
            elif not _numeric_equal(wanted[field], found[field]): failures.append(f"{prefix} {field} mismatch")
        for field in ("previous_market_date", "set_count", "card_count", "cohort_fingerprint", "source_generation_fingerprint"):
            if str(wanted.get(field)) != str(found.get(field)): failures.append(f"{prefix} {field} mismatch")
        if deterministic_fingerprint(wanted.get("constituents_json") or []) != deterministic_fingerprint(found.get("constituents_json") or []):
            failures.append(f"{prefix} constituents mismatch")
    try:
        expected_overview = build_market_overview(expected_history, market_date=market_date)
    except Exception as exc:
        failures.append(f"expected overview invalid: {exc}"); expected_overview = None
    try:
        persisted_overview = build_market_overview(persisted_history, market_date=market_date)
    except Exception as exc:
        failures.append(f"persisted overview invalid: {exc}"); persisted_overview = None
    if expected_overview is not None and persisted_overview is not None:
        _compare_json(expected_overview, persisted_overview, "persistedOverview", failures)
    latest = list(client.table("pokemon_explore_set_value_snapshot_latest").select("market_date,payload_json").eq("tcg", "pokemon").eq("scope", "market").limit(1).execute().data or [])
    public = (latest[0].get("payload_json") or {}).get("marketOverview") if latest else None
    if expected_overview is None or public is None:
        failures.append("public/expected marketOverview missing")
    else:
        # Both dimensions of every family are covered: `changes` (chain-linked
        # price performance) and `basketChanges` (literal tracked-basket
        # dollars). The recursive comparison below already walks them, but an
        # explicit presence check turns "the publisher is running old code"
        # into its own unambiguous failure line.
        for family_key in ("raw", "topChase"):
            family = public.get(family_key)
            if not isinstance(family, dict):
                failures.append(f"marketOverview.{family_key} missing from public payload"); continue
            for field in ("changes", "basketChanges"):
                if not isinstance(family.get(field), dict) or not family[field]:
                    failures.append(f"marketOverview.{family_key}.{field} absent from public payload (republish required)")
        _compare_json(expected_overview, public, "marketOverview", failures)
    return {"status": "passed" if not failures else "failed", "marketDate": market_date, "indexRows": len(actual), "failures": failures}


def main() -> None:
    parser = argparse.ArgumentParser(); parser.add_argument("--market-date", required=True); args = parser.parse_args()
    result = audit(get_client(), args.market_date); print(json.dumps(result, indent=2, sort_keys=True))
    raise SystemExit(0 if result["status"] == "passed" else 1)


if __name__ == "__main__": main()
