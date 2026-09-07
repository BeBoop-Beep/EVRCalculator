"""Explicit member/root contracts for the opt-in Price Storage V2 integration.

Importing this module never changes production routing. The comparison client is
read-only; the coordinator writes only to the new isolated SQL publishers.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal, InvalidOperation
from typing import Any, Iterable, Mapping, Sequence

LEGACY_HISTORY = "pokemon_set_value_daily_history"
MEMBER_HISTORY = "pokemon_member_set_value_daily_history_v2"
ROOT_HISTORY = "pokemon_root_set_value_daily_history_v2"
MEMBER_RPC = "publish_price_storage_v2_member_run"
ROOT_RPC = "publish_price_storage_v2_root_run"
PREVIEW_RPC = "preview_price_storage_v2_scoped_values"
PUBLIC_ROOT_SOURCES = {
    "standard": frozenset({"canonical_root_set_public_rollout_v1"}),
    "top10": frozenset({"canonical_root_top10_public_rollout_v1"}),
}
SCOPES = frozenset({"standard", "hits", "top10"})


class ScopeContractError(ValueError):
    """Incompatible scope, source generation, or incomplete input."""


def market_day(value: str) -> str:
    if not isinstance(value, str) or len(value) != 10:
        raise ScopeContractError("market_date must be an explicit YYYY-MM-DD date")
    try:
        if date.fromisoformat(value).isoformat() != value:
            raise ValueError(value)
    except ValueError as exc:
        raise ScopeContractError("invalid market_date") from exc
    return value


def amount(value: Any) -> Decimal:
    if value is None or isinstance(value, bool):
        raise ScopeContractError("missing price is not zero")
    try:
        result = Decimal(str(value))
    except InvalidOperation as exc:
        raise ScopeContractError("invalid numeric price") from exc
    if not result.is_finite() or result < 0:
        raise ScopeContractError("price must be finite and non-negative")
    return result


def public_root_materialization(
    root_ids: Iterable[str], rows: Iterable[Mapping[str, Any]], day: str,
) -> dict[str, Any]:
    """Existence alone is insufficient: member/generic rollout rows are not public roots."""
    day = market_day(day)
    roots = {str(value) for value in root_ids}
    pairs: set[tuple[str, str]] = set()
    duplicates: set[tuple[str, str]] = set()
    seen: set[tuple[str, str]] = set()
    for row in rows:
        key = (str(row.get("set_id")), str(row.get("value_scope")))
        if key[0] not in roots or key[1] not in PUBLIC_ROOT_SOURCES:
            continue
        if key in seen:
            duplicates.add(key)
        seen.add(key)
        if (row.get("snapshot_date") == day
                and row.get("source") in PUBLIC_ROOT_SOURCES[key[1]]):
            pairs.add(key)
    expected = {(root, scope) for root in roots for scope in PUBLIC_ROOT_SOURCES}
    missing = sorted(expected - pairs)
    return {
        "ready": not missing and not duplicates,
        "rootCount": len(roots),
        "materializedPairCount": len(pairs),
        "missingRootScopePairs": [list(pair) for pair in missing],
        "duplicatePairs": [list(pair) for pair in sorted(duplicates)],
    }


@dataclass(frozen=True)
class ScopedRun:
    run_id: int
    root_set_id: str
    market_date: str


def publish_isolated_run(client: Any, run: ScopedRun, *, commit: bool = False,
                         order: Sequence[str] = ("member", "root")) -> dict[str, Any]:
    """Explicit opt-in only. Each SQL RPC revalidates evidence and a disabled-by-default gate.

    The independent writes are resumable, not advertised as one atomic publish.
    No call here writes legacy history, public snapshots, or public index tables.
    """
    day = market_day(run.market_date)
    if isinstance(run.run_id, bool) or not isinstance(run.run_id, int) or run.run_id <= 0:
        raise ScopeContractError("positive run_id required")
    if tuple(sorted(order)) != ("member", "root"):
        raise ScopeContractError("order must contain member and root exactly once")
    if not commit:
        return {"status": "dry_run", "market_date": day, "run_id": run.run_id,
                "writes": 0, "public_routing_changed": False}
    results: dict[str, Any] = {}
    for scope in order:
        rpc = MEMBER_RPC if scope == "member" else ROOT_RPC
        result = client.rpc(rpc, {"p_run_id": run.run_id,
                                 "p_root_set_id": run.root_set_id,
                                 "p_market_date": day}).execute().data
        if not isinstance(result, dict) or result.get("status") not in {"complete", "noop"}:
            raise ScopeContractError(f"{scope} isolated publisher did not complete")
        results[scope] = result
    return {"status": "complete", "results": results, "public_routing_changed": False}


def root_source_rows(preview: Mapping[str, Any], root_id: str, day: str) -> list[dict[str, Any]]:
    """Convert a validated preview into the index builder's source shape, never member rows."""
    day = market_day(day)
    context = preview.get("context") or {}
    if preview.get("status") != "parity_passed":
        raise ScopeContractError(str(preview.get("reason") or "preview not accepted"))
    if context.get("root_set_id") != root_id or context.get("market_date") != day:
        raise ScopeContractError("preview root/date mismatch")
    if preview.get("publication_authorized") is not False:
        raise ScopeContractError("comparison preview must not authorize publication")
    evidence = context.get("source_evidence") or []
    expected_members = set(context.get("member_set_ids") or [])
    receipt_ids = [row.get("set_id") for row in evidence]
    if (not expected_members or root_id not in expected_members
            or set(receipt_ids) != expected_members or len(receipt_ids) != len(expected_members)):
        raise ScopeContractError("missing or duplicate member completion evidence")
    for row in evidence:
        if (row.get("source_ready") is not True or row.get("job_status") != "completed"
                or row.get("shadow_status") != "complete"
                or not row.get("source_completed_at")
                or row.get("source_completed_at") != row.get("shadow_source_completed_at")):
            raise ScopeContractError("incomplete or superseded source receipt")
    comparison = preview.get("comparison") or {}
    zero_fields = ("raw_only_rows", "v2_only_rows", "duplicate_raw_keys", "duplicate_v2_keys",
                   "live_root_only_rows", "proposed_root_only_rows", "missing_prices", "needs_review_cards")
    if any(type(comparison.get(field)) is not int or comparison[field] != 0 for field in zero_fields):
        raise ScopeContractError("preview comparison is missing or has differences")
    output: dict[str, dict[str, Any]] = {}
    for row in preview.get("candidate_values") or []:
        if row.get("universe_scope") != "root":
            continue
        if row.get("set_id") != root_id or row.get("market_scope") != "standard":
            raise ScopeContractError("wrong root or edition scope in candidate")
        scope = row.get("value_scope")
        if scope not in SCOPES or scope in output:
            raise ScopeContractError("unknown or duplicate candidate scope")
        count = row.get("priced_card_count")
        expected = row.get("expected_card_count")
        if (type(count) is not int or type(expected) is not int or count < 0
                or count != expected or (scope == "top10" and count > 10)):
            raise ScopeContractError("candidate coverage/count contract failed")
        value = None if scope == "hits" and count == 0 and row.get("set_value") is None else amount(row.get("set_value"))
        if scope != "hits" and count == 0:
            raise ScopeContractError("nonempty Standard and Top10 baskets are required")
        output[scope] = {
            "set_id": root_id, "snapshot_date": day, "value_scope": scope,
            "set_value": None if value is None else str(value), "priced_card_count": count, "total_card_count": expected,
            "source": "price_storage_v2_combined_root_candidate", "updated_at": None,
        }
    if set(output) != SCOPES:
        raise ScopeContractError("three root value scopes are required")
    return [output[scope] for scope in sorted(output)]


def economic_index_projection(rows: Iterable[Mapping[str, Any]]) -> list[dict[str, Any]]:
    """Exclude only expected source-storage provenance changes, not economic fields."""
    result = []
    for row in rows:
        copy = dict(row)
        copy.pop("source_generation_fingerprint", None)
        constituents = []
        for item in copy.get("constituents_json") or []:
            item = dict(item)
            item.pop("source", None)
            item.pop("sourceUpdatedAt", None)
            constituents.append(item)
        copy["constituents_json"] = sorted(constituents, key=lambda item: item["setId"])
        result.append(copy)
    return sorted(result, key=lambda row: (row["index_key"], row["market_date"]))


def compare_index_outputs(legacy: Iterable[Mapping[str, Any]],
                          candidate: Iterable[Mapping[str, Any]]) -> dict[str, Any]:
    old = economic_index_projection(legacy)
    new = economic_index_projection(candidate)
    return {"status": "pass" if old == new and old else "blocked",
            "legacy_rows": len(old), "candidate_rows": len(new),
            "economic_outputs_equal": old == new and bool(old),
            "ignored_fields": ["source_generation_fingerprint", "constituents_json.source",
                               "constituents_json.sourceUpdatedAt"],
            "publication_authorized": False}
