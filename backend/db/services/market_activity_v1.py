"""Bounded internal readers for the immutable FMA-1 projection.

This module deliberately imports no pricing provider or Explorer query builder.
All three reads validate the activity generation and roster independently; page
cursors are validated by the frozen domain implementation.
"""
from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone
from typing import Any, Mapping

from backend.domain.pokemon.market_activity import (
    DEFAULT_POLICY,
    CONTRACT_VERSION,
    _constituent_row,
    decode_cursor,
    encode_cursor,
    fingerprint,
    reevaluate_capabilities,
    reasons,
    roster_contract,
)

GENERATION_TABLE = "market_activity_generations_v1"
ROSTER_TABLE = "market_activity_rosters_v1"
MEMBER_TABLE = "market_activity_roster_members_v1"
DETAIL_TABLE = "market_activity_instrument_payloads_v1"
GROUP_TABLE = "market_activity_group_payloads_v1"
MAX_PAGE_SIZE = 100


def _rows(result: Any) -> list[dict[str, Any]]:
    value = getattr(result, "data", result)
    return [dict(row) for row in (value or [])]


def _one(query: Any) -> dict[str, Any] | None:
    rows = _rows(query.execute())
    return rows[0] if rows else None


def _generation(client: Any, generation_id: str) -> dict[str, Any] | None:
    return _one(client.table(GENERATION_TABLE).select("*").eq(
        "activity_generation_id", generation_id).limit(1))


def _roster(client: Any, generation_id: str, market_key: str) -> dict[str, Any] | None:
    return _one(client.table(ROSTER_TABLE).select("*").eq(
        "activity_generation_id", generation_id).eq("market_key", market_key).limit(1))


def _unavailable(kind: str, request: Mapping[str, Any], why: str) -> dict[str, Any]:
    now = datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    return {
        "kind": kind, "contractVersion": "market_activity_v1.1",
        "versions": {}, "policy": DEFAULT_POLICY.as_contract(), "request": dict(request),
        "evaluatedAt": now, "activityGenerationId": None,
        "availability": {"state": "UNAVAILABLE", "reasons": reasons(why)},
        "evidenceFingerprint": fingerprint({"request": request, "reason": why}),
    }


def _validate(client: Any, request: Mapping[str, Any], kind: str) -> tuple[dict[str, Any] | None, dict[str, Any] | None, dict[str, Any] | None]:
    generation_id = str(request.get("activityGenerationId") or "")
    generation = _generation(client, generation_id)
    if not generation:
        return None, None, _unavailable(kind, request, "ACTIVITY_GENERATION_MISMATCH")
    if generation.get("state") == "RETIRED" or generation.get("serving_state") == "RETIRED":
        return generation, None, _unavailable(kind, request, "ACTIVITY_GENERATION_EXPIRED")
    if generation.get("state") != "VALIDATED" or generation.get("serving_state") not in ("SERVING", "RETAINED"):
        return generation, None, _unavailable(kind, request, "ACTIVITY_GENERATION_MISMATCH")
    roster = _roster(client, generation_id, str(request.get("marketKey") or ""))
    if not roster or roster.get("roster_revision") != request.get("rosterRef"):
        return generation, roster, _unavailable(kind, request, "ROSTER_REVISION_MISMATCH")
    return generation, roster, None


def read_instrument_activity(client: Any, request: Mapping[str, Any], *, evaluated_at: datetime | None = None) -> dict[str, Any]:
    generation, _, error = _validate(client, request, "instrumentDetail")
    if error:
        return error
    row = _one(client.table(DETAIL_TABLE).select("payload").eq(
        "activity_generation_id", generation["activity_generation_id"]).eq(
        "instrument_key", request.get("instrumentKey")).limit(1))
    if not row:
        return _unavailable("instrumentDetail", request, "INSTRUMENT_NOT_IN_ROSTER")
    payload = deepcopy(row["payload"])
    payload["request"] = dict(request)
    payload["capabilities"] = reevaluate_capabilities(
        payload.get("capabilities") or {}, at=evaluated_at or datetime.now(timezone.utc))
    return payload


def read_group_activity(client: Any, request: Mapping[str, Any]) -> dict[str, Any]:
    generation, roster, error = _validate(client, request, "groupActivity")
    if error:
        return error
    row = _one(client.table(GROUP_TABLE).select("payload").eq(
        "activity_generation_id", generation["activity_generation_id"]).eq(
        "market_key", request["marketKey"]).eq("window_days", int(request.get("windowDays") or 30)).limit(1))
    if not row:
        return _unavailable("groupActivity", request, "INVALID_MARKET_KEY")
    payload = deepcopy(row["payload"])
    payload["request"] = dict(request)
    return payload


def read_constituent_activity_page(client: Any, request: Mapping[str, Any]) -> dict[str, Any]:
    generation, roster, error = _validate(client, request, "constituentActivityPage")
    if error:
        return error
    limit = int(request.get("limit") or 50)
    if not 1 <= limit <= MAX_PAGE_SIZE:
        raise ValueError("1 <= limit <= 100 is required")
    after_rank = 0
    if request.get("cursor"):
        try:
            after_rank = int(decode_cursor(request["cursor"])["k"])
        except (ValueError, KeyError, TypeError):
            return _unavailable("constituentActivityPage", request, "CURSOR_INVALID")
    # Fetch the complete roster (bounded batches) because cursor validation is
    # defined against its immutable denominator, not only the requested page.
    members: list[dict[str, Any]] = []
    offset = 0
    while offset < int(roster["roster_denominator"]):
        batch = _rows(client.table(MEMBER_TABLE).select("rank,instrument_key,card_variant_id").eq(
            "activity_generation_id", generation["activity_generation_id"]).eq(
            "market_key", request["marketKey"]).order("rank").range(offset, offset + 499).execute())
        members.extend(batch)
        if len(batch) < 500:
            break
        offset += len(batch)
    details: dict[str, Any] = {}
    for member in members:
        row = _one(client.table(DETAIL_TABLE).select("payload").eq(
            "activity_generation_id", generation["activity_generation_id"]).eq(
            "instrument_key", member["instrument_key"]).limit(1))
        details[member["instrument_key"]] = (row or {}).get("payload") or {}
    expected_cursor = {"v": "fma_cursor_v1", "a": str(request["activityGenerationId"]).lower(),
                       "r": fingerprint(request["rosterRef"]), "m": request["marketKey"],
                       "d": str(request["asOf"])[:10], "w": int(request.get("windowDays") or 30),
                       "k": after_rank}
    if request.get("cursor") and decode_cursor(request["cursor"]) != expected_cursor:
        return _unavailable("constituentActivityPage", request, "CURSOR_MISMATCH")
    if after_rank < 0 or after_rank >= len(members):
        return _unavailable("constituentActivityPage", request, "CURSOR_INVALID")
    selected = [m for m in members if m["rank"] > after_rank][:limit]
    rows = [_constituent_row(m["rank"], details[m["instrument_key"]], int(request.get("windowDays") or 30))
            for m in selected]
    last = rows[-1]["rank"] if rows else after_rank
    next_cursor = encode_cursor({**expected_cursor, "k": last}) if rows and last < len(members) else None
    evaluated = generation.get("validated_at") or generation["evidence_cutoff"]
    return {"kind": "constituentActivityPage", "contractVersion": CONTRACT_VERSION,
            "versions": next(iter(details.values())).get("versions", {}) if details else {},
            "policy": generation["policy"], "request": dict(request), "evaluatedAt": evaluated,
            "activityGenerationId": generation["activity_generation_id"],
            "availability": {"state": "AVAILABLE", "reasons": []},
            "evidenceFingerprint": fingerprint({"generation": generation["activity_generation_id"],
                                                "members": members, "windowDays": expected_cursor["w"]}),
            "roster": roster_contract(revision=roster["roster_revision"],
                                      roster_as_of=roster["roster_as_of"],
                                      roster_denominator=roster["roster_denominator"]),
            "page": {"afterRank": after_rank, "limit": limit, "totalCount": len(members),
                     "nextCursor": next_cursor}, "rows": rows}


__all__ = ["read_group_activity", "read_constituent_activity_page", "read_instrument_activity"]
