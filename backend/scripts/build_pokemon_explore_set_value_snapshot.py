from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys
from collections import defaultdict
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from backend.db.services.pokemon_explore_set_value_service import (
    ExploreSetValueUnavailable,
    build_global_set_value_row,
    read_initial_selected_set_movers,
    upsert_explore_set_value_snapshot,
)
from backend.db.services.market_publication_gate import (
    MarketForcePublishRejected,
    enforce_market_publication_gate,
)
from backend.db.services.publication_gate import add_publication_gate_args
from backend.db.services.pokemon_market_index_service import read_index_history
from backend.db.services.canonical_market_overview import (
    build_canonical_market_overview,
    resolve_canonical_overview_sets,
)
from backend.db.services.pokemon_market_rollout_cohort import (
    MARKET_ROOT_AUTHORITY_CUTOVER_DATE,
    MARKET_ROOT_AUTHORITY_TABLE_CUTOVER_DATE,
    resolve_market_root_cohort,
    resolve_market_root_ids,
)
from backend.scripts.pokemon_snapshot_builders import get_client

MARKET_READY_VIEW = "pokemon_market_set_value_publication_cohort_v1"
CANONICAL_HISTORY_RPC = "get_pokemon_market_root_set_value_daily_history_bulk_v1"
CANONICAL_HISTORY_START = "1999-01-01"
CANONICAL_HISTORY_SET_BATCH = 4
ROLLOUT_STANDARD_SOURCE = "canonical_root_set_rollout_v1"


def _attach_initial_selected_set_movers(client, row: dict) -> None:
    """Publish the #1 Set Value target's canonical 7D movers, never full Cards."""
    payload = row.get("payload_json") or {}
    published_sets = payload.get("sets") or []
    if not published_sets:
        return
    # The existing movers publication is keyed only by set_id and therefore
    # cannot distinguish Unlimited / 1st Edition / Shadowless. Never attach a
    # generic mover list to an explicit edition market.
    if str(published_sets[0].get("marketScope") or "standard") != "standard":
        return
    contract = read_initial_selected_set_movers(client, published_sets[0])
    payload["initialSelectedSetMovers"] = contract
    items = contract.get("items") or []
    encoded = json.dumps(payload, separators=(",", ":")).encode()
    row["payload_size_bytes"] = len(encoded)
    mover_identity = "\n".join(
        f"{card.get('canonicalCardId')}|{card.get('cardVariantId')}|{card.get('conditionId')}"
        for card in items
    )
    row["source_generation_fingerprint"] = hashlib.sha256(
        f"{row.get('source_generation_fingerprint')}\n{mover_identity}".encode()
    ).hexdigest()


def publisher_build_sha() -> str:
    configured = (os.getenv("PUBLICATION_BUILD_SHA") or os.getenv("GIT_SHA") or "").strip()
    if configured:
        return configured[:40]
    try:
        return subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=REPO_ROOT, text=True, timeout=5
        ).strip()[:40]
    except (OSError, subprocess.SubprocessError):
        return "unknown"


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(description="Build the compact global Market Set Value snapshot")
    mode = result.add_mutually_exclusive_group(required=True)
    mode.add_argument("--dry-run", action="store_true")
    mode.add_argument("--commit", action="store_true")
    add_publication_gate_args(result)
    return result


def _legacy_load_sets(client, *, market_date: str):
    """Historical Set Market cohort exactly as it was published pre-cutover."""
    rows = list((
        client.table(MARKET_READY_VIEW)
        .select(
            "set_id,set_name,canonical_key,era_name,release_date,logo_image_url,"
            "symbol_image_url,market_scope,canonical_market_date,market_publication_ready,"
            "current_certification_status"
        )
        .eq("market_scope", "standard")
        .eq("market_publication_ready", True)
        .eq("canonical_market_date", str(market_date)[:10])
        .order("release_date")
        .execute()
    ).data or [])
    return [
        {
            "id": row.get("set_id"),
            "name": row.get("set_name"),
            "canonical_key": row.get("canonical_key"),
            "era": row.get("era_name"),
            "release_date": row.get("release_date"),
            "logo_image_url": row.get("logo_image_url"),
            "symbol_image_url": row.get("symbol_image_url"),
            "market_scope": row.get("market_scope"),
            "market_publication_ready": bool(row.get("market_publication_ready")),
            "current_certification_status": row.get("current_certification_status"),
        }
        for row in rows
        if row.get("set_id")
    ]


def _load_sets(client, *, market_date: str):
    """Set Market roots aligned with the global Market authority.

    Sep 8 and earlier retain the already-published Set Market cohort verbatim.
    Sep 9 preserves the canonical transition resolver exactly as published.
    Sep 10+ membership comes from the frozen authority table via the lightweight
    membership-only resolver. Display metadata is then read directly from
    sets/eras; the heavyweight annotation view is deliberately avoided because
    certification is annotation, not membership, and that view is a known
    statement-timeout risk for broad 155-set publication builds.
    """
    day = str(market_date)[:10]
    if day < MARKET_ROOT_AUTHORITY_CUTOVER_DATE:
        return _legacy_load_sets(client, market_date=day)

    if day >= MARKET_ROOT_AUTHORITY_TABLE_CUTOVER_DATE:
        set_ids = resolve_market_root_ids(client, market_date=day)
        if not set_ids:
            raise RuntimeError(f"pokemon_market_root_authority has no active members for {day}")

        set_rows = []
        for offset in range(0, len(set_ids), 100):
            set_rows.extend(
                dict(row)
                for row in (
                    client.table("sets")
                    .select(
                        "id,name,canonical_key,era_id,release_date,logo_image_url,"
                        "symbol_image_url,catalog_only,parent_opening_set_id"
                    )
                    .in_("id", set_ids[offset:offset + 100])
                    .execute().data or []
                )
            )

        by_id = {str(row.get("id")): row for row in set_rows if row.get("id")}
        era_ids = sorted({str(row.get("era_id")) for row in set_rows if row.get("era_id")})
        era_names = {
            str(row.get("id")): str(row.get("name") or "")
            for row in (
                client.table("eras").select("id,name").in_("id", era_ids).execute().data or []
            )
        } if era_ids else {}

        return [
            {
                "id": set_id,
                "name": (by_id.get(set_id) or {}).get("name"),
                "canonical_key": (by_id.get(set_id) or {}).get("canonical_key"),
                "era": era_names.get(str((by_id.get(set_id) or {}).get("era_id"))),
                "release_date": (by_id.get(set_id) or {}).get("release_date"),
                "logo_image_url": (by_id.get(set_id) or {}).get("logo_image_url"),
                "symbol_image_url": (by_id.get(set_id) or {}).get("symbol_image_url"),
                "market_scope": "standard",
                "market_publication_ready": True,
                "market_current_certification_status": None,
            }
            for set_id in set_ids
        ]

    return [
        {
            "id": row.get("id"),
            "name": row.get("name"),
            "canonical_key": row.get("canonical_key"),
            "era": row.get("era"),
            "release_date": row.get("release_date"),
            "logo_image_url": row.get("logo_image_url"),
            "symbol_image_url": row.get("symbol_image_url"),
            "market_scope": "standard",
            "market_publication_ready": True,
            "market_current_certification_status": row.get("market_current_certification_status"),
        }
        for row in resolve_market_root_cohort(client, market_date=day)
    ]

def _scope_label(scope: str) -> str:
    return {
        "standard": "",
        "unlimited": "Unlimited",
        "first_edition": "1st Edition",
        "shadowless": "Shadowless",
    }.get(str(scope or "standard"), str(scope or "").replace("_", " ").title())


def _market_key(set_id: str, scope: str) -> str:
    scope = str(scope or "standard")
    return f"set:{set_id}" if scope == "standard" else f"set:{set_id}:{scope}"


def _expand_market_scope_rows(client, sets):
    """Expand root Sets into explicit market identities.

    Standard roots publish one Standard market. Edition-split roots publish
    each real edition scope separately and deliberately do NOT publish a
    generic blended Set market. Incomplete scopes remain in membership so the
    Market page can render them honestly as unavailable.
    """
    base_rows = [dict(row) for row in sets]
    ids = [str(row.get("id") or "") for row in base_rows if row.get("id")]
    if not ids:
        return []

    scoped_rows = []
    for offset in range(0, len(ids), 100):
        scoped_rows.extend(list(
            client.table("pokemon_market_root_set_value_latest_v1")
            .select("set_id,market_scope,coverage_pct,publishable_100pct")
            .in_("set_id", ids[offset:offset + 100])
            .execute().data or []
        ))

    scopes_by_set = defaultdict(list)
    for row in scoped_rows:
        set_id = str(row.get("set_id") or "")
        scope = str(row.get("market_scope") or "")
        if set_id and scope:
            scopes_by_set[set_id].append(dict(row))

    expanded = []
    for row in base_rows:
        set_id = str(row.get("id") or "")
        candidates = scopes_by_set.get(set_id) or [{"market_scope": "standard", "publishable_100pct": True}]
        nonstandard = [item for item in candidates if str(item.get("market_scope")) != "standard"]
        selected = nonstandard if nonstandard else [item for item in candidates if str(item.get("market_scope")) == "standard"]
        if not selected:
            selected = [{"market_scope": "standard", "publishable_100pct": True}]

        for authority in selected:
            scope = str(authority.get("market_scope") or "standard")
            suffix = _scope_label(scope)
            base_name = row.get("name") or row.get("set_name")
            next_row = dict(row)
            next_row.update({
                "market_scope": scope,
                "market_key": _market_key(set_id, scope),
                "base_set_name": base_name,
                "name": f"{base_name} - {suffix}" if suffix else base_name,
                "market_publication_ready": True,
                "market_current_certification_status": (
                    "CERTIFIED" if authority.get("publishable_100pct") is True else "SCOPED_MARKET_INCOMPLETE"
                ),
            })
            expanded.append(next_row)
    return expanded


def _load_scoped_certified_histories(client, market_rows, *, through_date):
    """Load certified root history keyed by explicit market identity."""
    grouped = defaultdict(list)
    limit_date = str(through_date)[:10]
    scope_by_set = defaultdict(set)
    for market in market_rows:
        set_id = str(market.get("id") or market.get("set_id") or "")
        scope = str(market.get("market_scope") or "standard")
        if set_id and scope != "standard":
            scope_by_set[set_id].add(scope)
    set_ids = sorted(scope_by_set)
    for offset in range(0, len(set_ids), CANONICAL_HISTORY_SET_BATCH):
        batch = set_ids[offset:offset + CANONICAL_HISTORY_SET_BATCH]
        response = client.rpc(
            CANONICAL_HISTORY_RPC,
            {
                "p_root_set_ids": batch,
                "p_start_date": CANONICAL_HISTORY_START,
                "p_end_date": limit_date,
            },
        ).execute()
        for row in list(response.data or []):
            set_id = str(row.get("set_id") or "")
            scope = str(row.get("market_scope") or "")
            if scope not in scope_by_set.get(set_id, set()):
                continue
            if row.get("certified_on_date") is not True:
                continue
            grouped[_market_key(set_id, scope)].append({
                "set_id": row.get("set_id"),
                "snapshot_date": row.get("market_date"),
                "set_value": row.get("set_value"),
            })
    for rows in grouped.values():
        rows.sort(key=lambda row: str(row.get("snapshot_date") or ""))
    return grouped

def _load_canonical_histories(client, market_rows, *, through_date: str):
    """Load the Set Value history that the Market page actually displays.

    PRE-CUTOVER keeps the historical certified-root contract plus the explicitly
    activated rollout row for the current day.

    POST-CUTOVER standard roots continue to use
    pokemon_set_value_daily_history Standard rows. Explicit vintage edition
    profiles may supply a scoped override for the one-row Set Market view.
    Scoped rows come only from certified canonical root history; incomplete
    scoped markets therefore become stale/unavailable rather than falling back
    to a blended Standard basket.

    Reads are explicitly paged with a deterministic (snapshot_date, set_id)
    order so PostgREST row caps cannot silently truncate broad Market cohorts.
    """
    grouped = defaultdict(list)
    limit_date = str(through_date)[:10]
    post_cutover = limit_date >= MARKET_ROOT_AUTHORITY_CUTOVER_DATE
    set_ids = sorted({str(row.get("id") or row.get("set_id") or "") for row in market_rows if row.get("id") or row.get("set_id")})
    standard_ids = {
        str(row.get("id") or row.get("set_id") or "")
        for row in market_rows
        if str(row.get("market_scope") or "standard") == "standard"
    }

    if post_cutover:
        page_size = 1000
        for offset in range(0, len(set_ids), 100):
            batch = set_ids[offset:offset + 100]
            start = 0
            while True:
                response = (
                    client.table("pokemon_set_value_daily_history")
                    .select("set_id,snapshot_date,set_value,source")
                    .in_("set_id", batch)
                    .eq("value_scope", "standard")
                    .lte("snapshot_date", limit_date)
                    .order("snapshot_date", desc=False)
                    .order("set_id", desc=False)
                    .range(start, start + page_size - 1)
                    .execute()
                )
                rows = list(response.data or [])
                for row in rows:
                    set_id = str(row.get("set_id") or "")
                    if set_id not in standard_ids:
                        continue
                    grouped[_market_key(set_id, "standard")].append({
                        "set_id": row.get("set_id"),
                        "snapshot_date": row.get("snapshot_date"),
                        "set_value": row.get("set_value"),
                    })
                if len(rows) < page_size:
                    break
                start += page_size

        scoped = _load_scoped_certified_histories(client, market_rows, through_date=limit_date)
        for market_key, rows in scoped.items():
            grouped[market_key] = list(rows)

        for rows in grouped.values():
            rows.sort(key=lambda row: str(row.get("snapshot_date") or ""))
        return grouped

    for offset in range(0, len(set_ids), CANONICAL_HISTORY_SET_BATCH):
        batch = set_ids[offset:offset + CANONICAL_HISTORY_SET_BATCH]
        response = client.rpc(
            CANONICAL_HISTORY_RPC,
            {
                "p_root_set_ids": batch,
                "p_start_date": CANONICAL_HISTORY_START,
                "p_end_date": limit_date,
            },
        ).execute()
        for row in list(response.data or []):
            if str(row.get("market_scope") or "") != "standard":
                continue
            if row.get("certified_on_date") is not True:
                continue
            set_id = str(row.get("set_id") or "")
            grouped[_market_key(set_id, "standard")].append({
                "set_id": row.get("set_id"),
                "snapshot_date": row.get("market_date"),
                "set_value": row.get("set_value"),
            })

    for offset in range(0, len(set_ids), 100):
        batch = set_ids[offset:offset + 100]
        rows = list((
            client.table("pokemon_set_value_daily_history")
            .select("set_id,snapshot_date,set_value,source")
            .in_("set_id", batch)
            .eq("snapshot_date", limit_date)
            .eq("value_scope", "standard")
            .eq("source", ROLLOUT_STANDARD_SOURCE)
            .execute()
        ).data or [])
        for row in rows:
            set_id = str(row.get("set_id"))
            market_key = _market_key(set_id, "standard")
            grouped[market_key] = [
                point
                for point in grouped.get(market_key, [])
                if str(point.get("snapshot_date"))[:10] != limit_date
            ]
            grouped[market_key].append({
                "set_id": row.get("set_id"),
                "snapshot_date": row.get("snapshot_date"),
                "set_value": row.get("set_value"),
            })

    for rows in grouped.values():
        rows.sort(key=lambda row: str(row.get("snapshot_date") or ""))
    return grouped

def build(*, client, market_date: str, commit: bool, market_index_history=None, market_overview=None) -> dict:
    root_sets = _load_sets(client, market_date=market_date)
    # Explicit edition markets exist only under the canonical root authority.
    # Pre-cutover historical builds keep the legacy one-Standard-row contract.
    if str(market_date)[:10] >= MARKET_ROOT_AUTHORITY_CUTOVER_DATE:
        sets = _expand_market_scope_rows(client, root_sets)
    else:
        sets = [
            {**dict(row), "market_scope": "standard", "market_key": _market_key(str(row.get("id")), "standard")}
            for row in root_sets
        ]
    set_ids = sorted({str(row["id"]) for row in sets})
    if not set_ids:
        raise ExploreSetValueUnavailable(
            "no staged Market Set Value scopes are available",
            diagnostics={"marketDate": str(market_date)[:10]},
        )

    dashboards = []
    post_cutover = str(market_date)[:10] >= MARKET_ROOT_AUTHORITY_TABLE_CUTOVER_DATE
    if not post_cutover:
        dashboard_fields = (
            "set_id,window_key,set_value_histories_json,latest_market_date,updated_at,"
            "cardsMarket:payload_json->cardsMarket"
        )
        for offset in range(0, len(set_ids), 20):
            result = (client.table("pokemon_set_market_dashboard_snapshot_latest")
                .select(dashboard_fields)
                .eq("window_key", "365d").in_("set_id", set_ids[offset:offset + 20]).execute())
            dashboards.extend(result.data or [])

    histories = _load_canonical_histories(
        client,
        sets,
        through_date=market_date,
    )

    overview = market_overview
    if overview is None:
        history = market_index_history
        if history is None:
            history = read_index_history(client, through_date=market_date)
        overview_sets = resolve_canonical_overview_sets(client, market_date=market_date)
        overview_set_ids = [str(row["id"]) for row in overview_sets]
        overview = build_canonical_market_overview(
            client,
            market_date=market_date,
            history=history,
            set_ids=overview_set_ids,
        )

    row = build_global_set_value_row(
        sets,
        dashboards,
        histories,
        target_market_date=market_date,
        market_overview=overview,
        publisher_build_sha=publisher_build_sha(),
    )
    _attach_initial_selected_set_movers(client, row)
    if commit:
        upsert_explore_set_value_snapshot(row, client=client)
    return row


def main() -> None:
    args = parser().parse_args()
    client = get_client()
    try:
        gate = enforce_market_publication_gate(
            client,
            commit=bool(args.commit),
            market_date=args.market_date,
            force_publish=bool(args.force_publish),
            entry_point="Global Market Set Value snapshot",
        )
    except MarketForcePublishRejected as exc:
        print(str(exc))
        raise SystemExit(2) from exc
    if not gate.proceed:
        raise SystemExit(gate.exit_code)
    market_date = args.market_date or gate.decision.market_date
    if not market_date:
        raise SystemExit("A promoted --market-date is required")
    try:
        row = build(client=client, market_date=str(market_date)[:10], commit=bool(args.commit))
    except ExploreSetValueUnavailable as exc:
        print(json.dumps({"status": "blocked", "reason": str(exc), **exc.diagnostics}, indent=2, sort_keys=True))
        raise SystemExit(1) from exc
    print(json.dumps({
        "status": "validated",
        **row["_diagnostics"],
        "payloadSizeBytes": row["payload_size_bytes"],
        "sourceGenerationFingerprint": row["source_generation_fingerprint"],
    }, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
