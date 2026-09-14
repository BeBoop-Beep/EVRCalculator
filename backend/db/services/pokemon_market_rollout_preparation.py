"""Fail-closed preparation of current-day public-rollout Set Value candidates."""

from __future__ import annotations

from typing import Any

from backend.db.services.price_storage_v2_integration import public_root_materialization

CANDIDATE_PREPARATION_RPC = "prepare_pokemon_market_candidate_rollout_set_values_v1"
# Deliberately NOT queried on the current-day candidate/materialization path:
# this valuation-backed view scans get_pokemon_market_root_set_card_prices_latest_v1(NULL)
# over the global root universe and measured ~7.86s in production, leaving no
# PostgREST budget for the (already cheap, ~356ms) candidate RPC itself.
# Membership must come from structural rollout authority instead -- see
# staged_rollout_root_ids() below. This constant is retained only because
# pokemon_market_rollout_cohort.py legitimately still reads this view for
# immutable pre-cutover historical cohort reconstruction.
ROLLOUT_VIEW = "pokemon_market_public_rollout_root_sets_v1"
ERA_ROLLOUT_VIEW = "pokemon_market_public_era_rollout_v1"
SETS_TABLE = "sets"
HISTORY_TABLE = "pokemon_set_value_daily_history"


def _rows(result: Any) -> list[dict[str, Any]]:
    return [dict(row) for row in ((getattr(result, "data", None) if result else None) or [])]


def staged_rollout_root_ids(client: Any, market_date: str) -> list[str]:
    """Resolve the expected current-day rollout root cohort structurally.

    Mirrors the membership predicate baked into the optimized SQL RPCs
    (``sets`` JOIN ``pokemon_market_public_era_rollout_v1``): it never reads
    the valuation-backed ``pokemon_market_public_rollout_root_sets_v1`` view,
    so it never pays for pricing the global root universe just to find out
    which roots are expected. Membership is structural; whether a root is
    actually priced is decided separately by materialization checks.
    """
    day = str(market_date)[:10]
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


def rollout_candidate_materialization(
    client: Any, market_date: str, *, root_ids: list[str] | None = None,
) -> dict[str, Any]:
    day = str(market_date)[:10]
    if root_ids is None:
        root_ids = staged_rollout_root_ids(client, day)
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
    return public_root_materialization(root_ids, source_rows, day, allow_candidate=True)


def prepare_market_rollout_candidate(
    client: Any, market_date: str, *, commit: bool,
) -> dict[str, Any]:
    """Prepare candidate root pairs before Quality, or inspect without writes."""
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
    expected = len(root_ids)
    if int(payload.get("rolloutRootCount") or -1) != expected:
        raise RuntimeError("candidate preparation rollout root count mismatch")
    if int(payload.get("standardRowsUpserted") or -1) != expected:
        raise RuntimeError("candidate preparation Standard row count mismatch")
    if int(payload.get("top10RowsUpserted") or -1) != expected:
        raise RuntimeError("candidate preparation Top10 row count mismatch")

    materialization = rollout_candidate_materialization(client, day, root_ids=root_ids)
    if not materialization["ready"]:
        raise RuntimeError(
            "candidate preparation left incomplete public-rollout materialization"
        )
    if materialization["provenanceState"] != "candidate":
        raise RuntimeError(
            "candidate preparation did not leave candidate provenance"
        )
    return {**payload, "rpcInvoked": True, "materialization": materialization}
