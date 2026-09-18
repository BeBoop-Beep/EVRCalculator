"""Fail-closed preparation of current-day public-rollout Set Value candidates."""

from __future__ import annotations

from typing import Any

from backend.db.services.price_storage_v2_integration import public_root_materialization
from backend.db.services.pokemon_market_rollout_cohort import (
    MARKET_ROOT_AUTHORITY_TABLE_CUTOVER_DATE,
    resolve_market_root_ids,
)
from backend.domain.pokemon.market_index import MARKET_INDEX_METHODOLOGY_VERSION

AUTHORITY_SYNC_RPC = "sync_pokemon_market_root_authority_v1"
CANDIDATE_PREPARATION_RPC = "prepare_pokemon_market_candidate_rollout_set_values_v1"
# Deliberately NOT queried on the current-day candidate/materialization path:
# this valuation-backed view scans get_pokemon_market_root_set_card_prices_latest_v1(NULL)
# over the global root universe and measured ~7.86s in production, leaving no
# PostgREST budget for the candidate RPC itself. Post-cutover membership comes
# from pokemon_market_root_authority through resolve_market_root_ids(); the
# structural era-rollout resolver below is retained only for frozen pre-cutover
# history.
ROLLOUT_VIEW = "pokemon_market_public_rollout_root_sets_v1"
ERA_ROLLOUT_VIEW = "pokemon_market_public_era_rollout_v1"
SETS_TABLE = "sets"
HISTORY_TABLE = "pokemon_set_value_daily_history"
MARKET_INDEX_TABLE = "pokemon_market_index_daily_history"
FINALIZED_INDEX_KEYS = frozenset({"raw", "top10"})
CANDIDATE_SOURCES = {
    "standard": "canonical_root_set_public_rollout_candidate_v1",
    "top10": "canonical_root_top10_public_rollout_candidate_v1",
}
FINAL_SOURCES = {
    "standard": frozenset({
        "canonical_root_set_public_rollout_v1",
        "canonical_root_standard_backfill_v1",
        "price_storage_v2_transition_anchor_v1",
        "price_storage_v2_serving_compatibility_v1",
    }),
    "top10": frozenset({
        "canonical_root_top10_public_rollout_v1",
        "canonical_root_top10_backfill_v1",
        "price_storage_v2_transition_anchor_v1",
        "price_storage_v2_serving_compatibility_v1",
    }),
}


def _rows(result: Any) -> list[dict[str, Any]]:
    return [dict(row) for row in ((getattr(result, "data", None) if result else None) or [])]


def sync_market_root_authority(client: Any, market_date: str) -> dict[str, Any]:
    """Insert any newly trackable root sets into current Market authority.

    The RPC is deliberately insert-only: once a root joins Market authority it
    never disappears merely because certification/freshness later regresses.
    """
    day = str(market_date or "")[:10]
    response = client.rpc(AUTHORITY_SYNC_RPC, {"p_market_date": day}).execute()
    payload = getattr(response, "data", None)
    if not isinstance(payload, dict):
        raise RuntimeError("Market root authority sync returned a non-object response")
    if payload.get("status") != "complete":
        raise RuntimeError("Market root authority sync did not complete")
    if str(payload.get("marketDate") or "")[:10] != day:
        raise RuntimeError("Market root authority sync returned wrong marketDate")
    if int(payload.get("structuralRootCount") or 0) < 1:
        raise RuntimeError("Market root authority sync returned an empty structural cohort")
    missing_structural_count = payload.get("missingStructuralRootCount")
    if missing_structural_count is None or int(missing_structural_count) != 0:
        raise RuntimeError("Market root authority sync left structural roots missing")
    if int(payload.get("activeAuthorityRootCount") or 0) < int(payload.get("structuralRootCount") or 0):
        raise RuntimeError("Market root authority sync active count is below structural count")
    return payload


def _legacy_staged_rollout_root_ids(client: Any, day: str) -> list[str]:
    """Resolve the frozen pre-Sep-10 rollout cohort structurally."""
    era_rows = _rows(
        client.table(ERA_ROLLOUT_VIEW)
        .select("era_id,activated_market_date,enabled")
        .eq("enabled", True)
        .lte("activated_market_date", day)
        .execute()
    )
    era_ids = sorted({str(row["era_id"]) for row in era_rows if row.get("era_id")})
    if not era_ids:
        raise RuntimeError(f"public rollout root cohort is empty for {day}")

    roots: set[str] = set()
    for offset in range(0, len(era_ids), 100):
        batch = era_ids[offset:offset + 100]
        set_rows = _rows(
            client.table(SETS_TABLE)
            .select("id,era_id,release_date,parent_opening_set_id,catalog_only,ready_for_daily_scrape")
            .in_("era_id", batch)
            .execute()
        )
        for row in set_rows:
            if row.get("parent_opening_set_id") is not None:
                continue
            if bool(row.get("catalog_only")):
                continue
            if not bool(row.get("ready_for_daily_scrape")):
                continue
            release_date = row.get("release_date")
            if release_date and str(release_date)[:10] > day:
                continue
            if row.get("id"):
                roots.add(str(row["id"]))

    if not roots:
        raise RuntimeError(f"public rollout root cohort is empty for {day}")
    return sorted(roots)


def staged_rollout_root_ids(client: Any, market_date: str) -> list[str]:
    """Resolve expected rollout roots from the correct date authority.

    Sep 10+ Market membership is frozen in ``pokemon_market_root_authority`` and
    must never be recomputed from certification or era-rollout surfaces. Earlier
    dates retain the historical structural resolver so published history is not
    reinterpreted under a later authority universe.
    """
    day = str(market_date)[:10]
    if day >= MARKET_ROOT_AUTHORITY_TABLE_CUTOVER_DATE:
        roots = resolve_market_root_ids(client, market_date=day)
        if not roots:
            raise RuntimeError(f"public rollout root cohort is empty for {day}")
        return roots
    return _legacy_staged_rollout_root_ids(client, day)


def _index_constituent_ids(value: Any) -> list[str] | None:
    """Extract one exact set-id list from a persisted Market index basket."""
    if not isinstance(value, list):
        return None
    ids: list[str] = []
    for item in value:
        if not isinstance(item, dict):
            return None
        set_id = item.get("setId") or item.get("set_id")
        if not set_id:
            return None
        ids.append(str(set_id))
    return ids


def finalized_market_index_materialization(
    client: Any, market_date: str, *, root_ids: list[str],
) -> dict[str, Any]:
    """Return whether both canonical Pokemon indexes froze this exact root set.

    Count equality alone is insufficient: a wrong basket can have the right
    cardinality. The finalized-day shortcut therefore requires the canonical
    Pokemon methodology and exact constituent identity for Raw and Top-10.
    """
    day = str(market_date)[:10]
    rows = _rows(
        client.table(MARKET_INDEX_TABLE)
        .select("index_key,market_date,set_count,constituents_json,tcg,methodology_version")
        .eq("tcg", "pokemon")
        .eq("methodology_version", MARKET_INDEX_METHODOLOGY_VERSION)
        .eq("market_date", day)
        .in_("index_key", sorted(FINALIZED_INDEX_KEYS))
        .execute()
    )
    grouped: dict[str, list[dict[str, Any]]] = {
        key: [] for key in FINALIZED_INDEX_KEYS
    }
    for row in rows:
        key = str(row.get("index_key") or "")
        if key in grouped:
            grouped[key].append(row)

    expected_ids = set(root_ids)
    expected_count = len(expected_ids)
    ready = expected_count == len(root_ids) and expected_count > 0
    observed_counts: dict[str, int] = {}
    observed_constituent_counts: dict[str, int | None] = {}
    exact_constituents: dict[str, bool] = {}

    for key in sorted(FINALIZED_INDEX_KEYS):
        matches = grouped[key]
        if len(matches) != 1:
            ready = False
            observed_counts[key] = 0
            observed_constituent_counts[key] = None
            exact_constituents[key] = False
            continue
        row = matches[0]
        set_count = int(row.get("set_count") if row.get("set_count") is not None else -1)
        constituent_ids = _index_constituent_ids(row.get("constituents_json"))
        constituent_count = len(constituent_ids) if constituent_ids is not None else None
        exact = (
            constituent_ids is not None
            and constituent_count == expected_count
            and len(set(constituent_ids)) == expected_count
            and set(constituent_ids) == expected_ids
        )
        observed_counts[key] = set_count
        observed_constituent_counts[key] = constituent_count
        exact_constituents[key] = exact
        if set_count != expected_count or not exact:
            ready = False

    return {
        "ready": ready,
        "marketDate": day,
        "tcg": "pokemon",
        "methodologyVersion": MARKET_INDEX_METHODOLOGY_VERSION,
        "expectedRootCount": expected_count,
        "observedIndexKeys": sorted(key for key, values in grouped.items() if values),
        "observedRowCounts": {key: len(values) for key, values in sorted(grouped.items())},
        "observedSetCounts": observed_counts,
        "observedConstituentCounts": observed_constituent_counts,
        "exactConstituents": exact_constituents,
    }


def _history_rows(
    client: Any,
    market_date: str,
    root_ids: list[str],
) -> list[dict[str, Any]]:
    day = str(market_date)[:10]
    source_rows: list[dict[str, Any]] = []
    for offset in range(0, len(root_ids), 100):
        source_rows.extend(_rows(
            client.table(HISTORY_TABLE)
            .select("set_id,value_scope,snapshot_date,source")
            .in_("set_id", root_ids[offset:offset + 100])
            .eq("snapshot_date", day)
            .in_("value_scope", ["standard", "top10"])
            .execute()
        ))
    return source_rows


def rollout_candidate_materialization(
    client: Any, market_date: str, *, root_ids: list[str] | None = None,
) -> dict[str, Any]:
    """Diagnostic full-root materialization under canonical candidate/final provenance."""
    day = str(market_date)[:10]
    if root_ids is None:
        root_ids = staged_rollout_root_ids(client, day)
    return public_root_materialization(
        root_ids,
        _history_rows(client, day, root_ids),
        day,
        allow_candidate=True,
    )


def candidate_write_materialization(
    client: Any, market_date: str, *, root_ids: list[str],
) -> dict[str, Any]:
    """Reconcile candidate writes while recognizing already-finalized rows."""
    rows = _history_rows(client, market_date, root_ids)
    candidates: dict[str, set[str]] = {"standard": set(), "top10": set()}
    finalized: dict[str, set[str]] = {"standard": set(), "top10": set()}
    for row in rows:
        scope = str(row.get("value_scope") or "")
        if scope not in CANDIDATE_SOURCES:
            continue
        set_id = str(row.get("set_id") or "")
        if not set_id:
            continue
        source = str(row.get("source") or "")
        if source == CANDIDATE_SOURCES[scope]:
            candidates[scope].add(set_id)
        elif source in FINAL_SOURCES[scope]:
            finalized[scope].add(set_id)

    accepted = {
        scope: candidates[scope] | finalized[scope]
        for scope in CANDIDATE_SOURCES
    }
    return {
        "standardCandidateRootIds": sorted(candidates["standard"]),
        "top10CandidateRootIds": sorted(candidates["top10"]),
        "standardProtectedFinalRootIds": sorted(finalized["standard"]),
        "top10ProtectedFinalRootIds": sorted(finalized["top10"]),
        "standardAcceptedRootIds": sorted(accepted["standard"]),
        "top10AcceptedRootIds": sorted(accepted["top10"]),
        "standardCandidateCount": len(candidates["standard"]),
        "top10CandidateCount": len(candidates["top10"]),
        "standardProtectedFinalCount": len(finalized["standard"]),
        "top10ProtectedFinalCount": len(finalized["top10"]),
        "standardAcceptedCount": len(accepted["standard"]),
        "top10AcceptedCount": len(accepted["top10"]),
        "top10SubsetOfStandard": candidates["top10"].issubset(candidates["standard"]),
        "top10AcceptedSubsetOfStandardAccepted": accepted["top10"].issubset(accepted["standard"]),
    }


def prepare_market_rollout_candidate(
    client: Any, market_date: str, *, commit: bool,
) -> dict[str, Any]:
    """Prepare candidate root rows before Quality, or inspect without writes."""
    day = str(market_date or "")[:10]
    if len(day) != 10:
        raise ValueError("an explicit candidate market date is required")

    authority_sync = None
    if commit:
        # Authority growth happens before resolving the canonical cohort. The
        # sync is structural and insert-only; the resolver then reads the actual
        # frozen authority table rather than recomputing membership itself.
        authority_sync = sync_market_root_authority(client, day)

    root_ids = staged_rollout_root_ids(client, day)
    if not commit:
        materialization = rollout_candidate_materialization(client, day, root_ids=root_ids)
        return {
            "status": "dry_run",
            "marketDate": day,
            "candidatePreparationWouldTarget": day,
            "candidatePreparationRequired": not materialization["ready"],
            "rolloutRootCount": len(root_ids),
            "rpcInvoked": False,
            "materialization": materialization,
        }

    finalized = finalized_market_index_materialization(client, day, root_ids=root_ids)
    if finalized["ready"]:
        return {
            "status": "already_finalized",
            "marketDate": day,
            "candidateDate": day,
            "rolloutRootCount": len(root_ids),
            "expectedRootCount": len(root_ids),
            "rpcInvoked": False,
            "candidatePreparationSkipped": True,
            "authoritySync": authority_sync,
            "finalizedMarket": finalized,
            "reason": "Raw and Top-10 Market indexes already froze the exact canonical authority cohort",
        }

    response = client.rpc(
        CANDIDATE_PREPARATION_RPC, {"p_market_date": day},
    ).execute()
    payload = getattr(response, "data", None)
    if not isinstance(payload, dict):
        raise RuntimeError("candidate preparation returned a non-object response")
    if payload.get("status") != "complete":
        raise RuntimeError("candidate preparation did not complete")
    for key in ("marketDate", "candidateDate"):
        if str(payload.get(key) or "")[:10] != day:
            raise RuntimeError(f"candidate preparation returned wrong {key}")

    expected = len(root_ids)
    rollout_count = int(
        payload.get("rolloutRootCount")
        if payload.get("rolloutRootCount") is not None else -1
    )
    standard_count = int(
        payload.get("standardRowsUpserted")
        if payload.get("standardRowsUpserted") is not None else -1
    )
    top10_count = int(
        payload.get("top10RowsUpserted")
        if payload.get("top10RowsUpserted") is not None else -1
    )
    if rollout_count < 0 or rollout_count > expected:
        raise RuntimeError("candidate preparation rollout root count mismatch")
    if standard_count < 0 or standard_count > rollout_count:
        raise RuntimeError("candidate preparation Standard row count mismatch")
    if top10_count < 0 or top10_count > rollout_count:
        raise RuntimeError("candidate preparation Top10 row count mismatch")

    candidate_writes = candidate_write_materialization(client, day, root_ids=root_ids)
    if standard_count != rollout_count and candidate_writes["standardProtectedFinalCount"] == 0:
        raise RuntimeError("candidate preparation Standard row count mismatch")
    if candidate_writes["standardCandidateCount"] != standard_count:
        raise RuntimeError("candidate preparation Standard write receipt mismatch")
    if candidate_writes["top10CandidateCount"] != top10_count:
        raise RuntimeError("candidate preparation Top10 write receipt mismatch")
    if candidate_writes["standardAcceptedCount"] != rollout_count:
        raise RuntimeError("candidate preparation Standard accepted-root coverage mismatch")
    if not candidate_writes["top10AcceptedSubsetOfStandardAccepted"]:
        raise RuntimeError("candidate preparation Top10 accepted roots are outside Standard accepted roots")

    materialization = rollout_candidate_materialization(client, day, root_ids=root_ids)
    return {
        **payload,
        "expectedRootCount": expected,
        "rpcInvoked": True,
        "authoritySync": authority_sync,
        "candidateWrites": candidate_writes,
        "materialization": materialization,
    }
