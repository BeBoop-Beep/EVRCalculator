from __future__ import annotations

import hashlib
import logging
from datetime import date, timedelta
from typing import Any, Dict, Optional
from uuid import UUID, uuid4

from backend.scripts.pokemon_snapshot_builders import (
    DEFAULT_RANKINGS_LIMIT,
    attach_daily_rip_rank_movements,
    build_explore_rankings_snapshot_row,
)

logger = logging.getLogger(__name__)


def publication_contract(row):
    payload = row["ranking_payload_json"]
    meta = payload.get("meta") or {}
    cohort = meta.get("publicAnalyticsCohort") or {}
    versions = meta.get("ripWeightsConfig") or {}
    market_date = str((meta.get("comparisonSnapshots") or {}).get("currentMarketDate") or "")[:10]
    ranked_count = int((cohort.get("overallRanked") or {}).get("rankedSetCount") or 0)
    financial_count = int(cohort.get("eligibleSetCount") or 0)
    targets = [target for target in payload.get("targets") or [] if (target.get("rip") or {}).get("rank") is not None]
    ca7_versions = sorted({
        str(((target.get("openingExperience") or {}).get("collectorAppeal") or {}).get("version"))
        for target in targets
        if ((target.get("openingExperience") or {}).get("collectorAppeal") or {}).get("version")
    })
    overall_version = (versions.get("overallRip") or {}).get("version")
    financial_version = (versions.get("financialRip") or {}).get("version")
    cohort_version = cohort.get("version")
    built_at = (meta.get("snapshot") or {}).get("builtAt")
    problems = []
    if not market_date:
        problems.append("missing market date")
    if not built_at:
        problems.append("missing built timestamp")
    if ranked_count <= 0 or len(targets) != ranked_count:
        problems.append(f"incomplete Overall RIP cohort expected={ranked_count} actual={len(targets)}")
    if financial_count <= 0:
        problems.append("missing Financial RIP cohort count")
    if len(ca7_versions) != 1:
        problems.append(f"incompatible CA7 versions={ca7_versions}")
    if any((target.get("ripCore") or {}).get("rank") is None for target in targets):
        problems.append("missing Financial RIP rank")
    if not overall_version or not financial_version:
        problems.append("missing RIP scoring version")
    if not cohort_version:
        problems.append("missing cohort version")
    if problems:
        raise RuntimeError("Refusing to publish Explore RIP leaderboard: " + "; ".join(problems))
    ids = sorted(str(target.get("set_id") or target.get("target_id")) for target in targets)
    snapshot = {
        "id": str(uuid4()), "market_date": market_date,
        "built_at": built_at,
        "eligible_cohort_count": ranked_count, "cohort_version": cohort_version,
        "cohort_fingerprint": hashlib.sha256("\n".join(ids).encode()).hexdigest(),
        "overall_rip_version": overall_version, "financial_rip_version": financial_version,
        "ca7_version": ca7_versions[0], "diagnostics": {"set_ids": ids},
    }
    rows = [{
        "set_id": target.get("set_id") or target.get("target_id"),
        "set_canonical_key": target.get("canonical_key") or target.get("slug"),
        "overall_rip_score": (target.get("rip") or {}).get("score"),
        "overall_rip_rank": (target.get("rip") or {}).get("rank"),
        "financial_rip_score": (target.get("ripCore") or {}).get("score"),
        "financial_rip_rank": (target.get("ripCore") or {}).get("rank"),
        "overall_ranked_cohort_count": ranked_count,
        "financial_ranked_cohort_count": financial_count,
        "simulation_calculation_run_id": target.get("calculation_run_id"),
        "source_market_date": market_date, "pack_price": target.get("pack_cost"),
    } for target in targets]
    return snapshot, rows


def previous_calendar_day_payload(client: Any, market_date: str) -> Optional[Dict[str, Any]]:
    previous_date = (date.fromisoformat(market_date) - timedelta(days=1)).isoformat()
    result = (client.table("pokemon_public_rip_leaderboard_snapshots").select("payload_json")
              .eq("market_date", previous_date).eq("publication_status", "complete")
              .limit(1).execute())
    rows = list(result.data or [])
    return rows[0].get("payload_json") if rows else None


def _reuse_publication_id(client: Any, snapshot: Dict[str, Any]) -> None:
    query = client.table("pokemon_public_rip_leaderboard_snapshots").select("id")
    for field in ("market_date", "cohort_version", "overall_rip_version", "financial_rip_version", "ca7_version"):
        query = query.eq(field, snapshot[field])
    rows = list(query.limit(1).execute().data or [])
    if rows and rows[0].get("id"):
        snapshot["id"] = str(rows[0]["id"])


def _stable_uuid(value: Any, *, label: str) -> str:
    if not value:
        raise RuntimeError(f"Refusing to publish Explore RIP leaderboard: {label} is missing")
    try:
        return str(UUID(str(value)))
    except (TypeError, ValueError, AttributeError) as exc:
        raise RuntimeError(
            f"Refusing to publish Explore RIP leaderboard: {label} is not a valid UUID"
        ) from exc


def validate_publication_payload(
    row: Dict[str, Any], snapshot: Dict[str, Any], history_rows: list[Dict[str, Any]]
) -> None:
    """Catch malformed publication parameters before invoking the authoritative RPC."""
    payload = row.get("ranking_payload_json")
    targets = payload.get("targets") if isinstance(payload, dict) else None
    if not isinstance(targets, list):
        raise RuntimeError("Refusing to publish Explore RIP leaderboard: latest targets must be an array")
    expected = int(snapshot.get("eligible_cohort_count") or 0)
    ranked_targets = [
        target for target in targets
        if isinstance(target, dict) and (target.get("rip") or {}).get("rank") is not None
    ]
    if expected <= 0 or len(ranked_targets) != expected:
        raise RuntimeError(
            "Refusing to publish Explore RIP leaderboard: ranked target count "
            f"expected={expected} actual={len(ranked_targets)}"
        )
    if len(history_rows) != expected:
        raise RuntimeError(
            "Refusing to publish Explore RIP leaderboard: history row count "
            f"expected={expected} actual={len(history_rows)}"
        )
    ranked_ids = [
        _stable_uuid(target.get("set_id") or target.get("target_id"), label="ranked target set ID")
        for target in ranked_targets
    ]
    history_ids = [
        _stable_uuid(history.get("set_id"), label="history row set ID")
        for history in history_rows
    ]
    if len(set(ranked_ids)) != len(ranked_ids):
        raise RuntimeError("Refusing to publish Explore RIP leaderboard: duplicate ranked target set IDs")
    if len(set(history_ids)) != len(history_ids):
        raise RuntimeError("Refusing to publish Explore RIP leaderboard: duplicate history row set IDs")
    if set(ranked_ids) != set(history_ids):
        raise RuntimeError("Refusing to publish Explore RIP leaderboard: ranked target/history set IDs differ")
    snapshot_meta = ((payload.get("meta") or {}).get("snapshot") or {})
    publication_id = snapshot_meta.get("publicationId")
    if not publication_id:
        raise RuntimeError("Refusing to publish Explore RIP leaderboard: publicationId is missing")
    if str(publication_id) != str(snapshot.get("id")):
        raise RuntimeError("Refusing to publish Explore RIP leaderboard: publicationId does not match snapshot")
    market_date = snapshot_meta.get("marketDate")
    if not market_date:
        raise RuntimeError("Refusing to publish Explore RIP leaderboard: marketDate is missing")
    if str(market_date) != str(snapshot.get("market_date")):
        raise RuntimeError("Refusing to publish Explore RIP leaderboard: marketDate does not match snapshot")


def publish_explore_rip_rankings_snapshot(
    client: Any, *, limit: int = DEFAULT_RANKINGS_LIMIT,
    market_date: Optional[str] = None, commit: bool = True,
) -> Dict[str, Any]:
    """Build, validate, enrich, and atomically publish the canonical RIP leaderboard."""
    row = build_explore_rankings_snapshot_row(limit=limit)
    snapshot, history_rows = publication_contract(row)
    if market_date and snapshot["market_date"] != market_date:
        raise RuntimeError(
            f"Refusing to backdate Explore RIP leaderboard: built market date "
            f"{snapshot['market_date']} does not match requested {market_date}"
        )
    previous = previous_calendar_day_payload(client, snapshot["market_date"])
    row["ranking_payload_json"] = attach_daily_rip_rank_movements(row["ranking_payload_json"], previous)
    if commit:
        _reuse_publication_id(client, snapshot)
    row["ranking_payload_json"].setdefault("meta", {}).setdefault("snapshot", {}).update({
        "publicationId": snapshot["id"], "marketDate": snapshot["market_date"],
    })
    validate_publication_payload(row, snapshot, history_rows)
    if not commit:
        logger.info("[dry-run] validated complete RIP publication market_date=%s rows=%s",
                    snapshot["market_date"], len(history_rows))
        return row
    client.rpc("publish_pokemon_public_rip_leaderboard", {
        "p_snapshot": snapshot, "p_rows": history_rows, "p_latest": row,
    }).execute()
    return row
