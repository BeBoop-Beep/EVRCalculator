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
    _versions,
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
SERVING_TABLE = "market_activity_serving_v1"
SURFACE_SERVING_TABLE = "pokemon_market_explorer_surface_serving_v2"


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
    response = {
        "kind": kind, "contractVersion": "market_activity_v1.1",
        "versions": _versions(), "policy": DEFAULT_POLICY.as_contract(), "request": dict(request),
        "evaluatedAt": now, "activityGenerationId": None,
        "availability": {"state": "UNAVAILABLE", "reasons": reasons(why)},
        "evidenceFingerprint": fingerprint({"request": request, "reason": why}),
    }
    if kind == "groupActivity":
        response.update({"label": "Activity for current constituents", "roster": None,
                         "coverage": None, "totals": None, "series": None})
    elif kind == "constituentActivityPage":
        response.update({"roster": None, "page": None, "rows": []})
    elif kind == "instrumentDetail":
        disabled = {"available": False, "reasons": reasons(why)}
        expiring = {**disabled, "expiresAt": None}
        response.update({
            "instrument": None, "roster": None, "sales": None, "asks": None,
            "peers": None, "series": None,
            "capabilities": {
                "saleCount": disabled, "observedSales": disabled,
                "salePriceSummary": disabled, "activityPercentile": disabled,
                "currentAsks": expiring, "askDepth": expiring, "landedAsk": expiring,
                "supplyTurnover": disabled, "inferredSalesFromListings": disabled,
            },
        })
    return response


def _execute_rows(query: Any) -> list[dict[str, Any]]:
    return _rows(query.execute())


def discover_activity_capabilities(
    client: Any, markets: list[Mapping[str, Any]], window_days: int,
) -> dict[str, Any]:
    """Resolve the current Activity authority for a bounded market batch.

    The implementation is constant-call: serving pointer, current generation,
    Explorer surface pointer, roster batch, and group-payload batch.  It never
    invokes a builder or derives an evidence fingerprint from metadata.
    """
    unavailable = lambda item, why: {
        "available": False, "marketKey": item.get("marketKey"),
        "activityGenerationId": None, "rosterRef": None,
        "evidenceFingerprint": None, "asOf": None, "windowDays": window_days,
        "tier": "RAW", "reasons": [why],
    }
    result = {str(item.get("focusKey")): unavailable(item, "ACTIVITY_GENERATION_MISMATCH")
              for item in markets}
    serving = _one(client.table(SERVING_TABLE).select("activity_generation_id").eq("singleton", 1).limit(1))
    generation_id = (serving or {}).get("activity_generation_id")
    if not generation_id:
        return {"contractVersion": CONTRACT_VERSION, "capabilities": result}
    generation = _one(client.table(GENERATION_TABLE).select(
        "activity_generation_id,as_of,surface_generation_id,roster_ref,state,serving_state"
    ).eq("activity_generation_id", generation_id).limit(1))
    if not generation or generation.get("state") != "VALIDATED" or generation.get("serving_state") != "SERVING":
        return {"contractVersion": CONTRACT_VERSION, "capabilities": result}
    current_surface = _one(client.table(SURFACE_SERVING_TABLE).select("generation_id").eq("singleton", 1).limit(1))
    pinned_surface = generation.get("surface_generation_id")
    if pinned_surface and str((current_surface or {}).get("generation_id")) != str(pinned_surface):
        return {"contractVersion": CONTRACT_VERSION, "capabilities": result}
    keys = [str(item["marketKey"]) for item in markets]
    rosters = _execute_rows(client.table(ROSTER_TABLE).select(
        "activity_generation_id,market_key,roster_revision"
    ).eq("activity_generation_id", generation_id).in_("market_key", keys))
    groups = _execute_rows(client.table(GROUP_TABLE).select(
        "activity_generation_id,market_key,window_days,payload"
    ).eq("activity_generation_id", generation_id).eq("window_days", window_days).in_("market_key", keys))
    roster_by_key = {row["market_key"]: row for row in rosters}
    group_by_key = {row["market_key"]: row for row in groups}
    for item in markets:
        focus_key, market_key = str(item["focusKey"]), str(item["marketKey"])
        roster = roster_by_key.get(market_key)
        if not roster or roster.get("roster_revision") != item.get("rosterRef"):
            result[focus_key] = unavailable(item, "ROSTER_REVISION_MISMATCH")
            continue
        group = group_by_key.get(market_key)
        payload = (group or {}).get("payload")
        if not isinstance(payload, Mapping):
            result[focus_key] = unavailable(item, "INVALID_MARKET_KEY")
            continue
        evidence = payload.get("evidenceFingerprint")
        if (not isinstance(evidence, str) or len(evidence) != 64
                or any(char not in "0123456789abcdef" for char in evidence)):
            result[focus_key] = unavailable(item, "INVALID_EVIDENCE_ROW")
            continue
        result[focus_key] = {
            "available": True, "marketKey": market_key,
            "activityGenerationId": str(generation_id),
            "rosterRef": roster["roster_revision"], "evidenceFingerprint": evidence,
            "asOf": str(generation["as_of"]), "windowDays": window_days,
            "tier": "RAW", "reasons": [],
        }
    return {"contractVersion": CONTRACT_VERSION, "capabilities": result}


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
    total = int(roster["roster_denominator"])
    expected_cursor = {"v": "fma_cursor_v1", "a": str(request["activityGenerationId"]).lower(),
                       "r": fingerprint(request["rosterRef"]), "m": request["marketKey"],
                       "d": str(request["asOf"])[:10], "w": int(request.get("windowDays") or 30),
                       "k": after_rank}
    if request.get("cursor") and decode_cursor(request["cursor"]) != expected_cursor:
        return _unavailable("constituentActivityPage", request, "CURSOR_MISMATCH")
    if after_rank < 0 or after_rank >= total:
        return _unavailable("constituentActivityPage", request, "CURSOR_INVALID")
    page_rows = _rows(client.rpc("get_market_activity_constituent_page_v1", {
        "p_activity_generation_id": generation["activity_generation_id"], "p_market_key": request["marketKey"],
        "p_after_rank": after_rank, "p_limit": limit}).execute())
    rows = [_constituent_row(row["rank"], row["payload"], int(request.get("windowDays") or 30))
            for row in page_rows]
    last = rows[-1]["rank"] if rows else after_rank
    next_cursor = encode_cursor({**expected_cursor, "k": last}) if rows and last < total else None
    evaluated = generation.get("validated_at") or generation["evidence_cutoff"]
    return {"kind": "constituentActivityPage", "contractVersion": CONTRACT_VERSION,
            "versions": (page_rows[0]["payload"].get("versions", {}) if page_rows else {}),
            "policy": generation["policy"], "request": dict(request), "evaluatedAt": evaluated,
            "activityGenerationId": generation["activity_generation_id"],
            "availability": {"state": "AVAILABLE", "reasons": []},
            "evidenceFingerprint": fingerprint({"generation": generation["activity_generation_id"],
                                                "rosterRef": roster["roster_revision"],
                                                "afterRank": after_rank, "windowDays": expected_cursor["w"]}),
            "roster": roster_contract(revision=roster["roster_revision"],
                                      roster_as_of=roster["roster_as_of"],
                                      roster_denominator=roster["roster_denominator"]),
            "page": {"afterRank": after_rank, "limit": limit, "totalCount": total,
                     "nextCursor": next_cursor}, "rows": rows}


__all__ = ["discover_activity_capabilities", "read_group_activity",
           "read_constituent_activity_page", "read_instrument_activity"]
