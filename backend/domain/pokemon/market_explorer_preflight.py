"""Typed translation of the DB Filtered Cards preflight RPC.

WHAT THIS IS. `preflight_pokemon_market_explorer_filtered_cards_v1` (added by
the migrations under backend/db/migrations/20260910*) is a cheap, read-only
"how many cards/sets would this filtered query match" check. This module owns
NOTHING about how that count is computed -- the SQL predicates are the single
source of truth -- it only translates the RPC's row into a stable
application-level contract and a typed readiness/outcome code.

WHY A SEPARATE LAYER. The RPC's column names and its `preflight_status`
enum are a database implementation detail (a one-word status the SQL author
found convenient). The rest of the app -- and in particular the endpoint that
maps outcomes to `useMarketExplorerQueries.js`'s typed codes -- should depend
on a small, documented, versioned Python contract instead of leaking SQL
column names or that enum directly across the API boundary.

WHAT THIS DOES NOT DO. It does not call the database, does not build a Market
Index, does not transport constituent IDs, and does not rank anything. The
caller is responsible for resolving Era -> Set IDs through the existing
canonical authority and invoking the RPC; this module only shapes the result.
"""

from __future__ import annotations

from typing import Any, Mapping

#: Preflight readiness/outcome codes. These are intentionally NOT the same
#: strings as the SQL `preflight_status` enum (empty/ready/projection_lagging/
#: ...) -- that enum is a database implementation detail. A translation table
#: keeps the two free to evolve independently.
PREFLIGHT_READY = "PREFLIGHT_READY"
PREFLIGHT_EMPTY = "PREFLIGHT_EMPTY"
PREFLIGHT_CURRENT_ONLY = "PREFLIGHT_CURRENT_ONLY"
PREFLIGHT_DISCONNECTED_HISTORY = "PREFLIGHT_DISCONNECTED_HISTORY"
PREFLIGHT_HISTORY_UNAVAILABLE = "PREFLIGHT_HISTORY_UNAVAILABLE"
PREFLIGHT_PROJECTION_LAGGING = "PREFLIGHT_PROJECTION_LAGGING"
PREFLIGHT_NO_APPROVED_DATE = "PREFLIGHT_NO_APPROVED_DATE"
PREFLIGHT_INVALID_SCOPE = "PREFLIGHT_INVALID_SCOPE"
PREFLIGHT_UNKNOWN = "PREFLIGHT_UNKNOWN"

#: SQL `preflight_status` -> this module's readiness code. Every status the
#: live RPC (section see 20260910204843_optimize_market_explorer_filtered_cards_preflight.sql)
#: can return is listed explicitly; an unmapped value degrades to UNKNOWN
#: rather than silently reading as ready or as empty.
_SQL_STATUS_TO_READINESS = {
    "ready": PREFLIGHT_READY,
    "empty": PREFLIGHT_EMPTY,
    "current_only": PREFLIGHT_CURRENT_ONLY,
    "disconnected_current_segment": PREFLIGHT_DISCONNECTED_HISTORY,
    "history_probe_unavailable": PREFLIGHT_HISTORY_UNAVAILABLE,
    "projection_lagging": PREFLIGHT_PROJECTION_LAGGING,
    "no_approved_market_date": PREFLIGHT_NO_APPROVED_DATE,
    "invalid_scope": PREFLIGHT_INVALID_SCOPE,
}

#: This module's readiness code -> the typed query outcome the frontend's
#: MARKET_QUERY_OUTCOME already understands (frontend/hooks/explore/
#: useMarketExplorerQueries.js). PROJECTION LAG NEVER MAPS TO EMPTY: a lagging
#: projection is an explicit readiness/unavailable state, never a reported
#: zero-match result.
READINESS_TO_QUERY_OUTCOME = {
    PREFLIGHT_READY: None,  # Not an outcome by itself; the caller proceeds to build.
    PREFLIGHT_EMPTY: "QUERY_EMPTY_NOW",
    PREFLIGHT_CURRENT_ONLY: "QUERY_NO_HISTORY",
    PREFLIGHT_DISCONNECTED_HISTORY: "QUERY_NO_HISTORY",
    PREFLIGHT_HISTORY_UNAVAILABLE: "QUERY_UNAVAILABLE",
    PREFLIGHT_PROJECTION_LAGGING: "QUERY_UNAVAILABLE",
    PREFLIGHT_NO_APPROVED_DATE: "QUERY_UNAVAILABLE",
    PREFLIGHT_INVALID_SCOPE: "QUERY_INVALID",
    PREFLIGHT_UNKNOWN: "QUERY_UNAVAILABLE",
}


class MarketExplorerPreflightError(ValueError):
    """The RPC row could not be translated into the typed contract."""


def _bool(value: Any) -> bool:
    return bool(value) if value is not None else False


def translate_preflight_row(row: Mapping[str, Any]) -> dict[str, Any]:
    """Translate one raw RPC row into the stable application-level contract.

    Field names below are the camelCase application contract; the RPC's own
    (snake_case) column names are read defensively so a harmless rename on
    either side does not silently produce None everywhere.
    """
    if not isinstance(row, Mapping):
        raise MarketExplorerPreflightError("preflight row must be a mapping")

    sql_status = str(row.get("preflight_status") or "").strip().lower()
    readiness = _SQL_STATUS_TO_READINESS.get(sql_status, PREFLIGHT_UNKNOWN)
    query_outcome = READINESS_TO_QUERY_OUTCOME[readiness]

    return {
        "matchingConstituentCount": row.get("matching_constituent_count"),
        "matchingSetCount": row.get("matching_set_count"),
        "comparisonAsOf": row.get("comparison_as_of"),
        "previousApprovedMarketDate": row.get("previous_approved_market_date"),
        "previousMatchingConstituentCount": row.get("previous_matching_constituent_count"),
        "previousMatchingSetCount": row.get("previous_matching_set_count"),
        "commonConstituentCount": row.get("common_constituent_count"),
        "currentChainLinkReady": _bool(row.get("current_chain_link_ready")),
        "scopeSetCount": row.get("scope_set_count"),
        "scopeProjectionReadySetCount": row.get("scope_projection_ready_set_count"),
        "scopeProjectionMissingSetCount": row.get("scope_projection_missing_set_count"),
        "scopeProjectionReady": _bool(row.get("scope_projection_ready")),
        "historyProbeProjectionReady": _bool(row.get("history_probe_projection_ready")),
        "projectionRetainedFrom": row.get("projection_retained_from"),
        "projectionComputedThrough": row.get("projection_computed_through"),
        "preflightStatus": sql_status or None,
        "readiness": readiness,
        "queryOutcome": query_outcome,
    }


def resolve_query_outcome_for_preflight(row: Mapping[str, Any]) -> str | None:
    """Convenience accessor: the typed QUERY_* outcome, or None if ready to build."""
    return translate_preflight_row(row)["queryOutcome"]
