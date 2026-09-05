"""Refresh and audit the canonical Pokemon Set Value / Top-10 authority.

This is a market-domain job, separate from RIP/opening publication. Run it
after the daily card-price scrape and before public Market snapshots are rebuilt.

Dry-run is the default. ``--commit`` refreshes current physical-variant metadata
first, then the variant-price interval authority, and finally audits current
Set Value / Top-10 certification. Certification always uses the latest
READY/LEGACY_VERIFIED Pokemon market date, never wall-clock time.

Examples:
    python -m backend.scripts.run_pokemon_market_set_authority --commit
    python -m backend.scripts.run_pokemon_market_set_authority \
        --set-name "Boundaries Crossed" --show-blockers
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from collections import Counter, defaultdict
from typing import Any, Iterable, Sequence

from backend.db.clients.supabase_client import create_service_role_client
from backend.db.services.pokemon_market_explorer_query_service import resolve_tracked_set_ids

READY_VIEW = "pokemon_market_root_set_market_ready_v1"
BLOCKER_RPC = "get_pokemon_market_root_set_current_blockers_v1"
CURRENT_METADATA_REFRESH_RPC = "refresh_pokemon_market_explorer_card_current_metadata"
INTERVAL_REFRESH_RPC = "refresh_pokemon_card_variant_market_price_intervals_for_sets"
DATE_QUALITY_TABLE = "pokemon_market_date_quality"
SETS_TABLE = "sets"
DEFAULT_SET_CHUNK_SIZE = 8


def _chunks(values: Sequence[str], size: int) -> Iterable[list[str]]:
    size = max(1, int(size))
    for index in range(0, len(values), size):
        yield list(values[index:index + size])


def _rows(response: Any) -> list[dict[str, Any]]:
    return list(getattr(response, "data", None) or [])


def latest_approved_market_date(client: Any) -> str | None:
    response = (
        client.table(DATE_QUALITY_TABLE)
        .select("market_date,status")
        .eq("tcg", "pokemon")
        .in_("status", ["READY", "LEGACY_VERIFIED"])
        .order("market_date", desc=True)
        .limit(1)
        .execute()
    )
    rows = _rows(response)
    return str(rows[0]["market_date"])[:10] if rows else None


def resolve_set_id(client: Any, set_name: str) -> str:
    rows = _rows(
        client.table(SETS_TABLE)
        .select("id,name")
        .eq("name", set_name)
        .limit(2)
        .execute()
    )
    if len(rows) != 1:
        raise RuntimeError(f"Expected exactly one set named {set_name!r}; found {len(rows)}")
    return str(rows[0]["id"])


def market_member_set_ids(client: Any, root_set_id: str) -> list[str]:
    """Root + children that contribute to the root Set Value universe."""
    child_rows = _rows(
        client.table(SETS_TABLE)
        .select("id,parent_opening_set_id,counts_toward_parent_set_value,catalog_only")
        .eq("parent_opening_set_id", root_set_id)
        .eq("counts_toward_parent_set_value", True)
        .eq("catalog_only", False)
        .execute()
    )
    return [root_set_id, *sorted(str(row["id"]) for row in child_rows if row.get("id"))]


def refresh_current_metadata(
    client: Any,
    *,
    set_ids: Sequence[str],
    commit: bool,
) -> dict[str, Any]:
    report: dict[str, Any] = {
        "dry_run": not commit,
        "set_count": len(set_ids),
        "result": None,
        "failure": None,
    }
    if not commit:
        return report
    try:
        response = client.rpc(
            CURRENT_METADATA_REFRESH_RPC,
            {"p_set_ids": list(set_ids)},
        ).execute()
        report["result"] = getattr(response, "data", None)
    except Exception as exc:  # noqa: BLE001 - one authoritative metadata projection
        report["failure"] = str(exc)
    return report


def refresh_interval_authority(
    client: Any,
    *,
    set_ids: Sequence[str],
    commit: bool,
    chunk_size: int,
) -> dict[str, Any]:
    report: dict[str, Any] = {
        "dry_run": not commit,
        "set_count": len(set_ids),
        "chunk_size": int(chunk_size),
        "chunks": 0,
        "refreshed_rows": 0,
        "failures": [],
    }
    if not commit:
        report["chunks"] = sum(1 for _ in _chunks(list(set_ids), chunk_size))
        return report

    for chunk in _chunks(list(set_ids), chunk_size):
        report["chunks"] += 1
        try:
            response = client.rpc(
                INTERVAL_REFRESH_RPC,
                {"p_set_ids": chunk},
            ).execute()
            report["refreshed_rows"] += int(getattr(response, "data", 0) or 0)
        except Exception as exc:  # noqa: BLE001 - bounded chunk is reported, then next chunk continues
            report["failures"].append({"set_ids": chunk, "error": str(exc)})
    return report


def load_readiness_rows(client: Any, *, set_id: str | None = None) -> list[dict[str, Any]]:
    query = client.table(READY_VIEW).select("*")
    if set_id:
        query = query.eq("set_id", set_id)
    return _rows(query.order("set_name").order("market_scope").execute())


def summarize_readiness(rows: Sequence[dict[str, Any]]) -> dict[str, Any]:
    by_scope: dict[str, Counter[str]] = defaultdict(Counter)
    ready = 0
    for row in rows:
        scope = str(row.get("market_scope") or "unknown")
        status = str(row.get("current_certification_status") or "UNKNOWN")
        by_scope[scope][status] += 1
        ready += int(bool(row.get("market_publication_ready")))
    return {
        "scope_rows": len(rows),
        "ready_scope_rows": ready,
        "not_ready_scope_rows": len(rows) - ready,
        "by_scope": {
            scope: dict(sorted(statuses.items()))
            for scope, statuses in sorted(by_scope.items())
        },
    }


def load_blockers(client: Any, set_id: str) -> list[dict[str, Any]]:
    return _rows(client.rpc(BLOCKER_RPC, {"p_root_set_id": set_id}).execute())


def compact_blockers(rows: Sequence[dict[str, Any]], limit: int = 100) -> dict[str, Any]:
    counts = Counter(str(row.get("blocker_code") or "UNKNOWN") for row in rows)
    items = [
        {
            "scope": row.get("market_scope"),
            "card": row.get("card_name"),
            "number": row.get("card_number"),
            "rarity": row.get("rarity"),
            "variant_id": row.get("card_variant_id"),
            "captured_at": row.get("captured_at"),
            "canonical_market_date": row.get("canonical_market_date"),
            "reason": row.get("price_selection_reason"),
            "blocker": row.get("blocker_code"),
        }
        for row in list(rows)[: max(0, int(limit))]
    ]
    return {
        "count": len(rows),
        "by_code": dict(sorted(counts.items())),
        "rows": items,
        "truncated": len(rows) > len(items),
    }


def run(*, commit: bool, set_name: str | None, show_blockers: bool, chunk_size: int) -> dict[str, Any]:
    started = time.monotonic()
    client = create_service_role_client()
    market_date = latest_approved_market_date(client)
    if not market_date:
        raise RuntimeError("No READY/LEGACY_VERIFIED Pokemon market date exists")

    selected_set_id = resolve_set_id(client, set_name) if set_name else None
    # Reuse the accepted Market Explorer market-history cohort globally. A
    # focused root-set run expands to qualifying child subsets because those
    # cards participate in the same parent Set Value / Top-10 universe.
    authority_set_ids = (
        market_member_set_ids(client, selected_set_id)
        if selected_set_id
        else list(resolve_tracked_set_ids(client))
    )

    metadata_report = refresh_current_metadata(
        client,
        set_ids=authority_set_ids,
        commit=commit,
    )
    if metadata_report.get("failure"):
        return {
            "dry_run": not commit,
            "canonical_market_date": market_date,
            "set_name": set_name,
            "metadata_refresh": metadata_report,
            "interval_refresh": None,
            "readiness": None,
            "status": "metadata_refresh_failed",
            "elapsed_seconds": round(time.monotonic() - started, 3),
        }

    interval_report = refresh_interval_authority(
        client,
        set_ids=authority_set_ids,
        commit=commit,
        chunk_size=chunk_size,
    )
    readiness = load_readiness_rows(client, set_id=selected_set_id)
    report: dict[str, Any] = {
        "dry_run": not commit,
        "canonical_market_date": market_date,
        "set_name": set_name,
        "authority_set_count": len(authority_set_ids),
        "metadata_refresh": metadata_report,
        "interval_refresh": interval_report,
        "readiness": summarize_readiness(readiness),
        "status": "ok" if not interval_report.get("failures") else "interval_refresh_failed",
    }

    if show_blockers:
        targets: list[tuple[str, str]] = []
        if selected_set_id:
            targets.append((selected_set_id, str(set_name)))
        else:
            seen: set[str] = set()
            for row in readiness:
                if bool(row.get("market_publication_ready")):
                    continue
                sid = str(row.get("set_id") or "")
                if sid and sid not in seen:
                    seen.add(sid)
                    targets.append((sid, str(row.get("set_name") or sid)))
        report["blockers"] = {
            name: compact_blockers(load_blockers(client, sid))
            for sid, name in targets
        }

    report["elapsed_seconds"] = round(time.monotonic() - started, 3)
    return report


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--commit",
        action="store_true",
        help=(
            "Refresh current variant metadata and interval authority before auditing. "
            "Without this flag the run is read-only."
        ),
    )
    parser.add_argument("--set-name", default=None, help="Audit one exact Pokemon root set name.")
    parser.add_argument("--show-blockers", action="store_true", help="Include card-level blocker diagnostics.")
    parser.add_argument("--chunk-size", type=int, default=DEFAULT_SET_CHUNK_SIZE)
    return parser


def main() -> int:
    args = build_parser().parse_args()
    try:
        report = run(
            commit=bool(args.commit),
            set_name=args.set_name,
            show_blockers=bool(args.show_blockers),
            chunk_size=max(1, int(args.chunk_size)),
        )
    except Exception as exc:  # noqa: BLE001 - CLI boundary
        print(json.dumps({"status": "failed", "error": str(exc)}, indent=2), file=sys.stderr)
        return 2

    print(json.dumps(report, indent=2, sort_keys=True, default=str))
    return 0 if report.get("status") == "ok" else 1


if __name__ == "__main__":
    raise SystemExit(main())
