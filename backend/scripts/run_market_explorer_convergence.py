"""Bounded autonomous convergence for Market Explorer V2.

This worker advances exactly one logical prerequisite stage per invocation. It
does not rebuild the canonical Market snapshots; those remain owned by the
post-scrape publisher. The worker only converges Market Explorer authorities
after a READY/LEGACY_VERIFIED market date exists.

Stages, in order:
  1. card_v2       - refresh metadata + advance a small batch of stale tracked sets
  2. sealed_daily  - materialize only the missing normalized sealed date range
  3. sealed_meta   - refresh normalized current sealed metadata
  4. rarity        - materialize/certify the missing rarity date range
  5. prepared      - advance at most one maintained cache / prepared generation
  6. surface_v2    - atomically build/validate/promote the coherent V2 generation

Every stage delegates to an existing canonical RPC or publisher. Direct writes
to serving tables are intentionally absent.
"""
from __future__ import annotations

import argparse
import json
from dataclasses import asdict, dataclass
from datetime import date, timedelta
from typing import Any, Callable, Mapping, Sequence

from backend.db.clients.supabase_client import create_service_role_client
from backend.db.services.pokemon_market_explorer_query_service import resolve_tracked_set_ids
from backend.scripts.publish_market_explorer_daily_projection import (
    V2_COVERAGE_TABLE,
    V2_RETENTION_DAYS,
    publish_set_v2,
)
from backend.scripts.run_market_explorer_daily_publication import (
    CURRENT_METADATA_REFRESH_RPC,
    resolve_latest_approved_market_date,
)
from backend.scripts.run_market_explorer_maintained_cache_prewarm import run_prewarm

APPROVED_STATUSES = {"READY", "LEGACY_VERIFIED"}
DEFAULT_CARD_SET_BATCH = 8

PREPARED_SERVING_TABLE = "pokemon_market_explorer_prepared_serving_v1"
PREPARED_GENERATIONS_TABLE = "pokemon_market_explorer_prepared_generations_v1"
SEALED_DAILY_TABLE = "pokemon_market_explorer_sealed_daily_v1"
SEALED_METADATA_TABLE = "pokemon_market_explorer_sealed_current_metadata_v1"
RARITY_CERT_TABLE = "pokemon_market_explorer_rarity_coverage_certification_v1"
SURFACE_SERVING_TABLE = "pokemon_market_explorer_surface_serving_v2"
SURFACE_GENERATIONS_TABLE = "pokemon_market_explorer_surface_generations_v2"

SEALED_DAILY_RPC = "refresh_pokemon_market_explorer_sealed_daily_v1"
SEALED_METADATA_RPC = "refresh_pokemon_market_explorer_sealed_current_metadata_v1"
RARITY_DAILY_RPC = "refresh_pokemon_market_explorer_rarity_daily_coverage_v1"
RARITY_CERT_RPC = "certify_pokemon_market_explorer_rarity_coverage_v1"
SURFACE_PUBLISH_RPC = "publish_pokemon_market_explorer_surface_current_v2"


@dataclass(frozen=True)
class ConvergenceSnapshot:
    target_market_date: str
    tracked_set_count: int
    stale_card_set_ids: tuple[str, ...]
    card_min_through: str | None
    card_max_through: str | None
    sealed_daily_through: str | None
    sealed_metadata_through: str | None
    rarity_certified_through: str | None
    prepared_through: str | None
    surface_v2_through: str | None


@dataclass
class ConvergenceReport:
    status: str
    stage: str
    target_market_date: str
    before: dict[str, Any]
    result: dict[str, Any] | None = None
    after: dict[str, Any] | None = None
    error: str | None = None


def _day(value: Any) -> str | None:
    text = str(value or "")[:10]
    try:
        return date.fromisoformat(text).isoformat()
    except ValueError:
        return None


def _max_date(client: Any, table: str, column: str) -> str | None:
    rows = list(
        client.table(table).select(column).not_.is_(column, "null")
        .order(column, desc=True).limit(1).execute().data or []
    )
    return _day((rows[0] if rows else {}).get(column))


def _prepared_serving_date(client: Any) -> str | None:
    rows = list(
        client.table(PREPARED_SERVING_TABLE)
        .select("generation_id").eq("singleton", True).limit(1).execute().data or []
    )
    generation_id = (rows[0] if rows else {}).get("generation_id")
    if not generation_id:
        return None
    generations = list(
        client.table(PREPARED_GENERATIONS_TABLE)
        .select("comparison_as_of,status").eq("generation_id", generation_id)
        .limit(1).execute().data or []
    )
    row = generations[0] if generations else {}
    return _day(row.get("comparison_as_of")) if row.get("status") == "serving" else None


def _surface_serving_date(client: Any) -> str | None:
    rows = list(
        client.table(SURFACE_SERVING_TABLE)
        .select("generation_id").eq("singleton", 1).limit(1).execute().data or []
    )
    generation_id = (rows[0] if rows else {}).get("generation_id")
    if not generation_id:
        return None
    generations = list(
        client.table(SURFACE_GENERATIONS_TABLE)
        .select("market_date,state").eq("generation_id", generation_id)
        .limit(1).execute().data or []
    )
    row = generations[0] if generations else {}
    return _day(row.get("market_date")) if row.get("state") == "VALIDATED" else None


def _coverage_rows(client: Any) -> list[dict[str, Any]]:
    return list(
        client.table(V2_COVERAGE_TABLE)
        .select("set_id,computed_through")
        .limit(1000).execute().data or []
    )


def load_snapshot(client: Any, target_market_date: str | None = None) -> ConvergenceSnapshot:
    target = _day(target_market_date) if target_market_date else resolve_latest_approved_market_date(client)
    if not target:
        raise RuntimeError("no approved Pokemon market date exists")

    quality = list(
        client.table("pokemon_market_date_quality").select("status")
        .eq("tcg", "pokemon").eq("market_date", target).limit(1).execute().data or []
    )
    if not quality or str(quality[0].get("status") or "") not in APPROVED_STATUSES:
        raise RuntimeError(f"market date {target} is not READY/LEGACY_VERIFIED")

    tracked = sorted({str(value) for value in resolve_tracked_set_ids(client)})
    coverage = {
        str(row.get("set_id")): _day(row.get("computed_through"))
        for row in _coverage_rows(client)
        if row.get("set_id")
    }
    stale = tuple(set_id for set_id in tracked if (coverage.get(set_id) or "") < target)
    dates = [coverage.get(set_id) for set_id in tracked if coverage.get(set_id)]

    rarity = list(
        client.table(RARITY_CERT_TABLE).select("certified_through")
        .eq("singleton", True).limit(1).execute().data or []
    )
    rarity_through = _day((rarity[0] if rarity else {}).get("certified_through"))

    return ConvergenceSnapshot(
        target_market_date=target,
        tracked_set_count=len(tracked),
        stale_card_set_ids=stale,
        card_min_through=min(dates) if dates else None,
        card_max_through=max(dates) if dates else None,
        sealed_daily_through=_max_date(client, SEALED_DAILY_TABLE, "market_date"),
        sealed_metadata_through=_max_date(client, SEALED_METADATA_TABLE, "latest_market_date"),
        rarity_certified_through=rarity_through,
        prepared_through=_prepared_serving_date(client),
        surface_v2_through=_surface_serving_date(client),
    )


def choose_stage(snapshot: ConvergenceSnapshot) -> str:
    target = snapshot.target_market_date
    if snapshot.stale_card_set_ids:
        return "card_v2"
    if (snapshot.sealed_daily_through or "") < target:
        return "sealed_daily"
    if (snapshot.sealed_metadata_through or "") < target:
        return "sealed_meta"
    if (snapshot.rarity_certified_through or "") < target:
        return "rarity"
    if (snapshot.prepared_through or "") < target:
        return "prepared"
    if (snapshot.surface_v2_through or "") < target:
        return "surface_v2"
    return "current"


def _next_day(value: str | None, target: str) -> str:
    if not value:
        return target
    start = date.fromisoformat(value) + timedelta(days=1)
    resolved_target = date.fromisoformat(target)
    return min(start, resolved_target).isoformat()


def _run_card_stage(
    client: Any,
    snapshot: ConvergenceSnapshot,
    *,
    card_set_batch: int,
) -> dict[str, Any]:
    selected = list(snapshot.stale_card_set_ids[: max(1, int(card_set_batch))])
    client.rpc(CURRENT_METADATA_REFRESH_RPC, {"p_set_ids": selected}).execute()
    reports = []
    for set_id in selected:
        result = publish_set_v2(
            client,
            set_id=set_id,
            through_date=snapshot.target_market_date,
            retention_days=V2_RETENTION_DAYS,
        )
        reports.append({
            "setId": set_id,
            "status": result.get("status"),
            "mode": result.get("mode"),
            "reconciled": result.get("reconciled"),
        })
    return {
        "selectedSetCount": len(selected),
        "remainingBefore": len(snapshot.stale_card_set_ids),
        "reports": reports,
    }


def _run_sealed_daily_stage(client: Any, snapshot: ConvergenceSnapshot) -> dict[str, Any]:
    target = snapshot.target_market_date
    start = _next_day(snapshot.sealed_daily_through, target)
    response = client.rpc(
        SEALED_DAILY_RPC,
        {"p_from": start, "p_through": target},
    ).execute()
    return dict(response.data or {})


def _run_sealed_meta_stage(client: Any) -> dict[str, Any]:
    response = client.rpc(SEALED_METADATA_RPC, {}).execute()
    return dict(response.data or {})


def _run_rarity_stage(client: Any, snapshot: ConvergenceSnapshot) -> dict[str, Any]:
    target = snapshot.target_market_date
    if snapshot.rarity_certified_through:
        start = _next_day(snapshot.rarity_certified_through, target)
    else:
        # Bootstrap remains deliberately bounded to the latest 14 approved calendar days.
        # Certification will fail closed if older accepted dates were never materialized.
        start = (date.fromisoformat(target) - timedelta(days=13)).isoformat()

    response = client.rpc(
        RARITY_DAILY_RPC,
        {"p_from": start, "p_through": target},
    ).execute()
    materialized = dict(response.data or {})
    certified_response = client.rpc(
        RARITY_CERT_RPC,
        {"p_through": target},
    ).execute()
    return {
        "materialized": materialized,
        "certification": dict(certified_response.data or {}),
    }


def _run_prepared_stage(
    client: Any,
    snapshot: ConvergenceSnapshot,
    *,
    prewarm_runner: Callable[..., dict[str, Any]] = run_prewarm,
) -> dict[str, Any]:
    return dict(
        prewarm_runner(
            client,
            market_date=snapshot.target_market_date,
            max_caches=1,
            commit=True,
        )
        or {}
    )


def _run_surface_stage(client: Any) -> dict[str, Any]:
    response = client.rpc(SURFACE_PUBLISH_RPC, {}).execute()
    return dict(response.data or {})


def run_convergence(
    client: Any,
    *,
    market_date: str | None = None,
    commit: bool,
    card_set_batch: int = DEFAULT_CARD_SET_BATCH,
    prewarm_runner: Callable[..., dict[str, Any]] = run_prewarm,
) -> dict[str, Any]:
    before = load_snapshot(client, market_date)
    stage = choose_stage(before)
    report = ConvergenceReport(
        status="current" if stage == "current" else ("planned" if not commit else "running"),
        stage=stage,
        target_market_date=before.target_market_date,
        before=asdict(before),
    )
    if stage == "current" or not commit:
        return asdict(report)

    try:
        if stage == "card_v2":
            result = _run_card_stage(client, before, card_set_batch=card_set_batch)
        elif stage == "sealed_daily":
            result = _run_sealed_daily_stage(client, before)
        elif stage == "sealed_meta":
            result = _run_sealed_meta_stage(client)
        elif stage == "rarity":
            result = _run_rarity_stage(client, before)
        elif stage == "prepared":
            result = _run_prepared_stage(client, before, prewarm_runner=prewarm_runner)
        elif stage == "surface_v2":
            result = _run_surface_stage(client)
        else:  # pragma: no cover - choose_stage is exhaustive
            raise RuntimeError(f"unknown convergence stage {stage!r}")
    except Exception as exc:  # noqa: BLE001
        report.status = "failed"
        report.error = f"{type(exc).__name__}: {exc}"
        return asdict(report)

    report.result = dict(result or {})
    after = load_snapshot(client, before.target_market_date)
    report.after = asdict(after)
    report.status = "current" if choose_stage(after) == "current" else "advanced"
    return asdict(report)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--dry-run", action="store_true")
    mode.add_argument("--commit", action="store_true")
    parser.add_argument("--market-date", default=None)
    parser.add_argument(
        "--card-set-batch",
        type=int,
        default=DEFAULT_CARD_SET_BATCH,
        help="Maximum stale card-V2 sets to advance in one tick (default: 8).",
    )
    return parser


def main() -> int:
    args = build_parser().parse_args()
    report = run_convergence(
        create_service_role_client(),
        market_date=args.market_date,
        commit=bool(args.commit),
        card_set_batch=max(1, min(int(args.card_set_batch), 20)),
    )
    print(json.dumps(report, indent=2, sort_keys=True, default=str))
    return 1 if report.get("status") == "failed" else 0


if __name__ == "__main__":
    raise SystemExit(main())
