"""Fail-closed preparation of current-day public-rollout Set Value candidates."""

from __future__ import annotations

from typing import Any

from backend.db.services.price_storage_v2_integration import public_root_materialization
from backend.db.services.pokemon_market_rollout_cohort import (
    MARKET_ROOT_AUTHORITY_TABLE_CUTOVER_DATE,
    resolve_market_root_ids,
)

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
CANDIDATE_SOURCES = {
    "standard": "canonical_root_set_public_rollout_candidate_v1",
    "top10": "canonical_root_top10_public_rollout_candidate_v1",
}


def _rows(result: Any) -> list[dict[str, Any]]:
    return [dict(row) for row in ((getattr(result, "data", None) if result else None) or [])]


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
    """Resolve the expected rollout root cohort from the correct date authority.

    Sep 10+ Market membership is frozen in ``pokemon_market_root_authority`` and
    must never be recomputed from the legacy era-rollout surface. Earlier dates
    retain the historical structural resolver so already-published history is
    not reinterpreted.
    """
    day = str(market_date)[:10]
    if day >= MARKET_ROOT_AUTHORITY_TABLE_CUTOVER_DATE:
        roots = resolve_market_root_ids(client, market_date=day)
        if not roots:
            raise RuntimeError(f"public rollout root cohort is empty for {day}")
        return roots
    return _legacy_staged_rollout_root_ids(client, day)


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
    """Diagnostic full-root materialization under canonical candidate/final provenance.

    After the Sep-10 root-authority expansion some active roots can remain on
    generic valuation provenance while Quality still evaluates them as current.
    Therefore this report is informative on the commit path; it is not itself
    the post-cutover membership gate.
    """
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
    """Reconcile the candidate rows the RPC claims it wrote inside authority.

    The SQL RPC intentionally writes only roots meeting its live coverage
    predicates. Non-written authority roots are handled by the immediately
    following Market Date Quality gate, which requires current Standard/Top-10
    valuation rows for the full authority cohort regardless of provenance.
    """
    rows = _history_rows(client, market_date, root_ids)
    by_scope: dict[str, set[str]] = {"standard": set(), "top10": set()}
    for row in rows:
        scope = str(row.get("value_scope") or "")
        if scope not in CANDIDATE_SOURCES:
            continue
        if row.get("source") != CANDIDATE_SOURCES[scope]:
            continue
        if row.get("set_id"):
            by_scope[scope].add(str(row["set_id"]))
    return {
        "standardCandidateRootIds": sorted(by_scope["standard"]),
        "top10CandidateRootIds": sorted(by_scope["top10"]),
        "standardCandidateCount": len(by_scope["standard"]),
        "top10CandidateCount": len(by_scope["top10"]),
        "top10SubsetOfStandard": by_scope["top10"].issubset(by_scope["standard"]),
    }


def prepare_market_rollout_candidate(
    client: Any, market_date: str, *, commit: bool,
) -> dict[str, Any]:
    """Prepare candidate root rows before Quality, or inspect without writes."""
    day = str(market_date or "")[:10]
    if len(day) != 10:
        raise ValueError("an explicit candidate market date is required")
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

    # The authority cohort is intentionally larger than the subset the SQL
    # materializer can write on a given day. Validate the RPC's counts as a
    # bounded write receipt, then verify those exact candidate rows exist.
    # Full-cohort valuation completeness is enforced immediately afterward by
    # Market Date Quality; duplicating that gate here with stricter provenance
    # rules would incorrectly reject valid authority members.
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
    if standard_count != rollout_count:
        raise RuntimeError("candidate preparation Standard row count mismatch")
    if top10_count < 0 or top10_count > standard_count:
        raise RuntimeError("candidate preparation Top10 row count mismatch")

    candidate_writes = candidate_write_materialization(client, day, root_ids=root_ids)
    if candidate_writes["standardCandidateCount"] != standard_count:
        raise RuntimeError("candidate preparation Standard write receipt mismatch")
    if candidate_writes["top10CandidateCount"] != top10_count:
        raise RuntimeError("candidate preparation Top10 write receipt mismatch")
    if not candidate_writes["top10SubsetOfStandard"]:
        raise RuntimeError("candidate preparation Top10 roots are outside Standard candidates")

    # Keep the stricter provenance report visible for diagnostics without using
    # it to redefine post-cutover Market membership. Generic current-day rows
    # for non-candidate authority roots are adjudicated by Market Date Quality.
    materialization = rollout_candidate_materialization(client, day, root_ids=root_ids)
    return {
        **payload,
        "expectedRootCount": expected,
        "rpcInvoked": True,
        "candidateWrites": candidate_writes,
        "materialization": materialization,
    }
