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

from backend.db.services.pokemon_market_index_service import (
    build_market_index_history, read_index_history,
    read_raw_index_history_for_audit,
)
from backend.domain.pokemon.market_index import INDEX_KEYS, deterministic_fingerprint
from backend.db.services.canonical_market_overview import (
    build_canonical_market_overview, resolve_canonical_overview_sets,
)
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
            # DO NOT stop here. Returning made one missing additive key mask
            # every difference beneath it — a stale snapshot reported only its
            # top-level mismatch while the prepared `currentConstituents` drift
            # underneath went unseen. Keep walking what both sides DO share.
        for key in sorted(set(expected) & set(actual)):
            _compare_json(expected[key], actual[key], f"{path}.{key}", failures)
    elif isinstance(expected, list):
        if not isinstance(actual, list) or len(expected) != len(actual): failures.append(f"{path} length/type mismatch"); return
        for index, (wanted, found) in enumerate(zip(expected, actual)): _compare_json(wanted, found, f"{path}[{index}]", failures)
    elif isinstance(expected, (int, float)) and not isinstance(expected, bool):
        if not _numeric_equal(expected, actual): failures.append(f"{path} numeric mismatch")
    elif expected != actual:
        failures.append(f"{path} mismatch")


def _prepared_segment_collections(overview: Any) -> list[tuple[str, dict]]:
    """Every published prepared-segment collection in one overview.

    Returns (path, segments-mapping) pairs so a caller can speak in the exact
    contract path a reader would look up, rather than "some segment somewhere".
    """
    result: list[tuple[str, dict]] = []
    if not isinstance(overview, dict):
        return result
    sealed = (overview.get("sealedSegments") or {}).get("segments")
    if isinstance(sealed, dict):
        result.append(("marketOverview.sealedSegments.segments", sealed))
    card_segments = overview.get("cardSegments")
    if isinstance(card_segments, dict):
        for parent_key, parent in card_segments.items():
            if not isinstance(parent, dict):
                continue
            segments = parent.get("segments")
            if isinstance(segments, dict):
                result.append((f"marketOverview.cardSegments.{parent_key}.segments", segments))
    return result


def _prepared_constituent_failures(expected: Any, public: Any) -> list[str]:
    """Name prepared segments whose `currentConstituents` the publisher dropped.

    The recursive comparison would eventually surface this as a keys mismatch,
    but only as one line per segment buried among structural noise. Prepared
    constituent transparency is a user-facing promise ("what is inside SIR?"),
    so a snapshot that predates it gets its own unambiguous verdict naming the
    exact segments and the exact remedy.
    """
    published: dict[str, dict] = {path: segments for path, segments in _prepared_segment_collections(public)}
    failures: list[str] = []
    for path, expected_segments in _prepared_segment_collections(expected):
        actual_segments = published.get(path) or {}
        stale = sorted(
            key
            for key, segment in expected_segments.items()
            if isinstance(segment, dict)
            and segment.get("available") is True
            and "currentConstituents" in segment
            and "currentConstituents" not in (actual_segments.get(key) or {})
        )
        if stale:
            failures.append(
                f"{path}[{', '.join(stale)}].currentConstituents absent from public payload "
                "(builder emits prepared constituent summaries; republish required)"
            )
    return failures


def audit(client: Any, market_date: str) -> dict[str, Any]:
    expected_history = build_market_index_history(client, through_date=market_date)
    # Parity is compared ACCEPTED-vs-ACCEPTED. Both sides are quality-scoped, so
    # a retained-but-unaccepted row (e.g. the 2026-08-18 DEGRADED legacy row) is
    # evidence, not a parity failure.
    persisted_history = read_index_history(client, through_date=market_date)
    # Audit keeps sight of what the public view withholds.
    raw_history = read_raw_index_history_for_audit(client, through_date=market_date)
    retained_unaccepted = sorted(
        {str(row["market_date"])[:10] for row in raw_history}
        - {str(row["market_date"])[:10] for row in persisted_history})
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
    latest = list(client.table("pokemon_explore_set_value_snapshot_latest").select("market_date,payload_json").eq("tcg", "pokemon").eq("scope", "market").limit(1).execute().data or [])
    public = (latest[0].get("payload_json") or {}).get("marketOverview") if latest else None
    # The cohort and the overview are BOTH resolved through the publisher's own
    # authority (canonical_market_overview). The audit deliberately enumerates
    # no contract keys of its own: a key it forgot is precisely the drift that
    # made this audit report a false `cardSegments` mismatch against a healthy
    # snapshot, which in turn hid the real missing `currentConstituents`.
    set_ids = [str(row["id"]) for row in resolve_canonical_overview_sets(client, market_date=market_date)]
    try:
        expected_overview = build_canonical_market_overview(
            client, market_date=market_date, history=expected_history, set_ids=set_ids,
        )
    except Exception as exc:
        failures.append(f"expected overview invalid: {exc}"); expected_overview = None
    try:
        persisted_overview = build_canonical_market_overview(
            client, market_date=market_date, history=persisted_history, set_ids=set_ids,
        )
    except Exception as exc:
        failures.append(f"persisted overview invalid: {exc}"); persisted_overview = None
    if expected_overview is not None and persisted_overview is not None:
        _compare_json(expected_overview, persisted_overview, "persistedOverview", failures)
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
        failures.extend(_prepared_constituent_failures(expected_overview, public))
        _compare_json(expected_overview, public, "marketOverview", failures)
    return {"status": "passed" if not failures else "failed", "marketDate": market_date,
            "indexRows": len(actual), "failures": failures,
            # Retained as evidence, withheld from the public view. Informational:
            # these are not failures.
            "retainedUnacceptedDates": retained_unaccepted}


def main() -> None:
    parser = argparse.ArgumentParser(); parser.add_argument("--market-date", required=True); args = parser.parse_args()
    result = audit(get_client(), args.market_date); print(json.dumps(result, indent=2, sort_keys=True))
    raise SystemExit(0 if result["status"] == "passed" else 1)


if __name__ == "__main__": main()
