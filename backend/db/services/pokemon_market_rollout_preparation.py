"""Fail-closed preparation of current-day public-rollout Set Value candidates."""

from __future__ import annotations

from typing import Any

from backend.db.services.price_storage_v2_integration import public_root_materialization

CANDIDATE_PREPARATION_RPC = "prepare_pokemon_market_candidate_rollout_set_values_v1"
ROLLOUT_VIEW = "pokemon_market_public_rollout_root_sets_v1"
HISTORY_TABLE = "pokemon_set_value_daily_history"


def _rows(result: Any) -> list[dict[str, Any]]:
    return [dict(row) for row in ((getattr(result, "data", None) if result else None) or [])]


def staged_rollout_root_ids(client: Any, market_date: str) -> list[str]:
    day = str(market_date)[:10]
    rows = _rows(
        client.table(ROLLOUT_VIEW)
        .select("set_id,release_date,activated_market_date")
        .lte("activated_market_date", day)
        .execute()
    )
    roots = sorted({
        str(row["set_id"])
        for row in rows
        if row.get("set_id")
        and (not row.get("release_date") or str(row["release_date"])[:10] <= day)
    })
    if not roots:
        raise RuntimeError(f"public rollout root cohort is empty for {day}")
    return roots


def rollout_candidate_materialization(client: Any, market_date: str) -> dict[str, Any]:
    day = str(market_date)[:10]
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
        materialization = rollout_candidate_materialization(client, day)
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

    materialization = rollout_candidate_materialization(client, day)
    if not materialization["ready"]:
        raise RuntimeError(
            "candidate preparation left incomplete public-rollout materialization"
        )
    if materialization["provenanceState"] != "candidate":
        raise RuntimeError(
            "candidate preparation did not leave candidate provenance"
        )
    return {**payload, "rpcInvoked": True, "materialization": materialization}
