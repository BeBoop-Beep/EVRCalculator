"""Bucket B5 targeted sold-history expansion after Core Panel completion.

Priority:
1. current canonical price gaps with exactly one physical variant + one TCGPlayer product id;
2. current governed 7D Explore movers not already in the completed Core Panel.

This is research evidence only. It never mutates canonical TCGPlayer pricing.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import uuid
from collections import Counter
from datetime import date, datetime, timedelta, timezone
from typing import Any, Iterable

from backend.pricing_pipeline.pkmnprices_client import PkmnPricesClient
from backend.pricing_pipeline.pkmnprices_credentials import load_pkmnprices_credentials
from backend.pricing_pipeline.pkmnprices_store import PkmnPricesStore
from backend.pricing_pipeline.pkmnprices_sold import normalize_sold_listing
from backend.scripts.run_market_microstructure_bucket_b import (
    COLLECTOR_VERSION,
    PANEL_FINGERPRINT,
)
from backend.scripts.run_market_microstructure_bucket_b4 import (
    operational_pause_reason,
    phoenix_date,
)

MODE = "bucket_b5_targeted_sold_history_v1"
SELECTOR_VERSION = "bucket_b5_gap_then_governed_7d_movers_v1"
PAGE_SIZE = 20
MAX_ROWS_PER_TARGET_ROUND = 80
DAILY_B5_CREDIT_CAP = 8000
HORIZON_DAYS = 180
EXPECTED_CORE_PANEL_READY = 207
MOVER_TABLE = "pokemon_explore_card_movers_snapshot_latest"


def _chunks(values: list[Any], size: int = 150) -> Iterable[list[Any]]:
    for start in range(0, len(values), size):
        yield values[start:start + size]


def _paged(db: Any, table: str, columns: str, *, order: str | None = None) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    start = 0
    while True:
        query = db.table(table).select(columns)
        if order:
            query = query.order(order)
        page = query.range(start, start + 999).execute().data or []
        rows.extend(dict(row) for row in page)
        if len(page) < 1000:
            return rows
        start += 1000


def _core_panel_ready_count(db: Any) -> int:
    identities = _paged(
        db,
        "pkmnprices_card_identity_v1",
        "provider_card_id,metadata",
        order="provider_card_id",
    )
    provider_ids = {
        int(row["provider_card_id"])
        for row in identities
        if dict(row.get("metadata") or {}).get("panel_fingerprint") == PANEL_FINGERPRINT
    }
    if not provider_ids:
        return 0
    ready = 0
    for chunk in _chunks(sorted(provider_ids), 150):
        rows = (
            db.table("pkmnprices_sold_sync_state_v1")
            .select("provider_card_id,metadata")
            .in_("provider_card_id", chunk)
            .execute().data or []
        )
        ready += sum(bool(dict(row.get("metadata") or {}).get("phase1_ready")) for row in rows)
    return ready


def _gap_targets(db: Any) -> list[dict[str, Any]]:
    missing = _paged(
        db,
        "pokemon_canonical_card_market_price_missing_cards",
        "canonical_card_id,set_name,name,number,rarity",
        order="canonical_card_id",
    )
    if not missing:
        return []
    missing_by = {str(row["canonical_card_id"]): row for row in missing}
    canonical_by: dict[str, dict[str, Any]] = {}
    missing_ids = list(missing_by)
    for chunk in _chunks(missing_ids, 150):
        rows = (
            db.table("pokemon_canonical_cards")
            .select(
                "id,name,number,printed_number,pokemon_tcg_api_card_id,"
                "source_payload,set_id,rarity"
            )
            .in_("id", chunk)
            .execute().data or []
        )
        for row in rows:
            canonical_by[str(row["id"])] = dict(row)
    links: list[dict[str, Any]] = []
    for chunk in _chunks(list(missing_by), 150):
        links.extend(
            db.table("pokemon_canonical_card_legacy_identity_links")
            .select("canonical_card_id,legacy_card_id")
            .in_("canonical_card_id", chunk)
            .execute().data or []
        )
    legacy_to_canonical = {
        str(row["legacy_card_id"]): str(row["canonical_card_id"])
        for row in links
    }
    variants: list[dict[str, Any]] = []
    for chunk in _chunks(list(legacy_to_canonical), 150):
        variants.extend(
            db.table("card_variants")
            .select("id,card_id,printing_type,special_type,edition")
            .in_("card_id", chunk)
            .execute().data or []
        )
    variant_by_id = {str(row["id"]): dict(row) for row in variants}
    external: list[dict[str, Any]] = []
    for chunk in _chunks(list(variant_by_id), 150):
        external.extend(
            db.table("card_variant_external_identities")
            .select("card_variant_id,external_product_id,provider")
            .in_("card_variant_id", chunk)
            .eq("provider", "tcgplayer")
            .execute().data or []
        )

    pairs: dict[str, list[tuple[dict[str, Any], str]]] = {}
    for ext in external:
        variant = variant_by_id.get(str(ext["card_variant_id"]))
        if not variant:
            continue
        cid = legacy_to_canonical.get(str(variant["card_id"]))
        if not cid:
            continue
        pairs.setdefault(cid, []).append((variant, str(ext["external_product_id"])))

    targets: list[dict[str, Any]] = []
    exact_variant_cids: set[str] = set()
    for cid, rows in sorted(pairs.items()):
        unique = {
            (str(variant["id"]), product_id)
            for variant, product_id in rows
        }
        if len(unique) != 1:
            continue
        variant, product_id = rows[0]
        card = missing_by[cid]
        exact_variant_cids.add(cid)
        targets.append({
            "canonical_card_id": cid,
            "card_variant_id": str(variant["id"]),
            "internal_variants": [{
                "id": str(variant["id"]),
                "edition": variant.get("edition"),
                "printing_type": variant.get("printing_type"),
            }],
            "tcgplayer_product_id": product_id,
            "provider_identity_strategy": "exact_tcgplayer_product_id",
            "provider_search_name": None,
            "provider_search_number": None,
            "provider_search_set_name": None,
            "card_name": card.get("name"),
            "set_name": card.get("set_name"),
            "rarity": card.get("rarity"),
            "edition": variant.get("edition"),
            "printing_type": variant.get("printing_type"),
            "special_type": variant.get("special_type"),
            "priority_tier": 1,
            "priority_reason": "MISSING_PRICE_EXACT_VARIANT",
            "movement_rank": None,
            "change_percent": None,
        })

    # Broader exact provider-search cohort. These cards have native Pokémon TCG
    # source metadata, including exact set/name/number, but our internal variant
    # mapping is incomplete. Evidence collected here stays card-level unless the
    # provider variant string resolves unambiguously to an internal variant.
    for cid, card in sorted(canonical_by.items()):
        if cid in exact_variant_cids:
            continue
        payload = dict(card.get("source_payload") or {})
        source_set = dict(payload.get("set") or {})
        if not isinstance(payload.get("tcgplayer"), dict):
            continue
        name = str(card.get("name") or "").strip()
        number = str(card.get("number") or card.get("printed_number") or "").strip()
        set_name = str(source_set.get("name") or "").strip()
        if not (name and number and set_name):
            continue

        internal_variants = []
        for legacy_id in [
            str(row["legacy_card_id"])
            for row in links
            if str(row["canonical_card_id"]) == cid
        ]:
            for variant in variants:
                if str(variant.get("card_id")) == legacy_id:
                    internal_variants.append({
                        "id": str(variant["id"]),
                        "edition": variant.get("edition"),
                        "printing_type": variant.get("printing_type"),
                    })

        targets.append({
            "canonical_card_id": cid,
            "card_variant_id": None,
            "internal_variants": internal_variants,
            "tcgplayer_product_id": None,
            "provider_identity_strategy": "exact_set_name_card_name_number",
            "provider_search_name": name,
            "provider_search_number": number,
            "provider_search_set_name": set_name,
            "card_name": name,
            "set_name": set_name,
            "rarity": card.get("rarity"),
            "edition": None,
            "printing_type": None,
            "special_type": None,
            "priority_tier": 1,
            "priority_reason": "MISSING_PRICE_EXACT_PROVIDER_SEARCH",
            "movement_rank": None,
            "change_percent": None,
        })
    return targets


eturn targets


def _mover_targets(db: Any, *, exclude: set[str]) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    rows = (
        db.table(MOVER_TABLE)
        .select("payload_json,market_date,updated_at,card_count")
        .eq("tcg", "pokemon")
        .eq("scope", "explore")
        .eq("window_key", "7D")
        .limit(1)
        .execute().data or []
    )
    if not rows:
        return [], {"status": "MOVER_SNAPSHOT_MISSING"}
    snapshot = dict(rows[0])
    payload = dict(snapshot.get("payload_json") or {})
    movements = list((payload.get("marketMovers") or {}).get("all") or [])
    # The published Explore snapshot is already ordered by the governed
    # canonical movement sort. Preserve that authority exactly; do not
    # recompute or reinterpret movement ranking here.
    movements = [dict(row) for row in movements if isinstance(row, dict)]

    variant_ids = [
        str(row.get("cardVariantId") or row.get("card_variant_id"))
        for row in movements
        if row.get("cardVariantId") or row.get("card_variant_id")
    ]
    ext_rows: list[dict[str, Any]] = []
    for chunk in _chunks(variant_ids, 150):
        ext_rows.extend(
            db.table("card_variant_external_identities")
            .select("card_variant_id,external_product_id,provider")
            .in_("card_variant_id", chunk)
            .eq("provider", "tcgplayer")
            .execute().data or []
        )
    ext_by_variant: dict[str, list[str]] = {}
    for row in ext_rows:
        ext_by_variant.setdefault(str(row["card_variant_id"]), []).append(str(row["external_product_id"]))

    targets = []
    for rank, movement in enumerate(movements, start=1):
        cid = str(movement.get("canonicalCardId") or movement.get("canonical_card_id") or "")
        vid = str(movement.get("cardVariantId") or movement.get("card_variant_id") or "")
        if not cid or not vid or cid in exclude:
            continue
        product_ids = sorted(set(ext_by_variant.get(vid) or []))
        if len(product_ids) != 1:
            continue
        targets.append({
            "canonical_card_id": cid,
            "card_variant_id": vid,
            "internal_variants": [{
                "id": vid,
                "edition": movement.get("edition"),
                "printing_type": movement.get("printingType") or movement.get("printing_type"),
            }],
            "tcgplayer_product_id": product_ids[0],
            "provider_identity_strategy": "exact_tcgplayer_product_id",
            "provider_search_name": None,
            "provider_search_number": None,
            "provider_search_set_name": None,
            "card_name": movement.get("name") or movement.get("cardName"),
            "set_name": movement.get("setName"),
            "rarity": movement.get("rarity"),
            "edition": movement.get("edition"),
            "printing_type": movement.get("printingType") or movement.get("printing_type"),
            "special_type": movement.get("specialType") or movement.get("special_type"),
            "priority_tier": 2,
            "priority_reason": "GOVERNED_7D_MOVER",
            "movement_rank": rank,
            "change_percent": movement.get("changePercent") or movement.get("change_percent"),
        })
    meta = {
        "status": "READY",
        "market_date": snapshot.get("market_date"),
        "published_count": len(movements),
        "selected_non_excluded_exact_count": len(targets),
    }
    return targets, meta


def _core_panel_canonical_ids(db: Any) -> set[str]:
    rows = _paged(
        db,
        "pkmnprices_card_identity_v1",
        "canonical_card_id,metadata",
        order="canonical_card_id",
    )
    return {
        str(row["canonical_card_id"])
        for row in rows
        if dict(row.get("metadata") or {}).get("panel_fingerprint") == PANEL_FINGERPRINT
    }


def select_targets(db: Any) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    gaps = _gap_targets(db)
    excluded = _core_panel_canonical_ids(db)
    excluded.update(str(row["canonical_card_id"]) for row in gaps)
    movers, mover_meta = _mover_targets(db, exclude=excluded)
    targets = gaps + movers
    manifest_body = [
        {
            "canonical_card_id": row["canonical_card_id"],
            "card_variant_id": row["card_variant_id"],
            "tcgplayer_product_id": row.get("tcgplayer_product_id"),
            "provider_identity_strategy": row.get("provider_identity_strategy"),
            "priority_tier": row["priority_tier"],
            "priority_reason": row["priority_reason"],
            "movement_rank": row["movement_rank"],
        }
        for row in targets
    ]
    fingerprint = hashlib.sha256(
        json.dumps(manifest_body, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    return targets, {
        "selector_version": SELECTOR_VERSION,
        "selector_fingerprint": fingerprint,
        "gap_target_count": len(gaps),
        "mover_target_count": len(movers),
        "mover_snapshot": mover_meta,
    }


def _daily_credits_used(db: Any, credit_day: str) -> int:
    start = datetime.fromisoformat(credit_day + "T00:00:00+00:00")
    end = start + timedelta(days=1)
    rows = (
        db.table("pkmnprices_sold_runs_v1")
        .select("credits_used,metadata,started_at")
        .gte("started_at", start.isoformat())
        .lt("started_at", end.isoformat())
        .execute().data or []
    )
    return sum(
        int(row.get("credits_used") or 0)
        for row in rows
        if dict(row.get("metadata") or {}).get("mode") == MODE
    )


def _credit_day() -> str:
    return datetime.now(timezone.utc).date().isoformat()


def _horizon() -> tuple[date, date]:
    reference = date.fromisoformat(phoenix_date())
    return reference, reference - timedelta(days=HORIZON_DAYS)


def _evidence_summary(db: Any, provider_card_id: int) -> dict[str, Any]:
    rows = (
        db.table("pkmnprices_ebay_sold_evidence_v1")
        .select("sold_at")
        .eq("provider_card_id", provider_card_id)
        .order("sold_at")
        .range(0, 999)
        .execute().data or []
    )
    if len(rows) == 1000:
        # Oldest only: order ascending means the first row is already sufficient.
        oldest = str(rows[0]["sold_at"])[:10] if rows else None
    else:
        oldest = min((str(row["sold_at"])[:10] for row in rows), default=None)
    return {"oldest_sold_at": oldest, "transaction_count_lower_bound": len(rows)}


def _identity_row(target: dict[str, Any], provider_card: dict[str, Any]) -> dict[str, Any]:
    provider_id = provider_card.get("id")
    if provider_id is None:
        raise RuntimeError("B5_PROVIDER_CARD_ID_MISSING")
    provider_set = provider_card.get("set") or {}
    return {
        "provider_card_id": int(provider_id),
        "canonical_card_id": target["canonical_card_id"],
        "tcgplayer_product_id": str(
            target.get("tcgplayer_product_id")
            or provider_card.get("tcg_player_id")
            or ""
        ),
        "language": "English",
        "match_basis": "b5_" + str(target.get("provider_identity_strategy") or "unknown"),
        "provider_name": provider_card.get("name"),
        "provider_set_id": str(provider_set.get("id")) if provider_set.get("id") is not None else None,
        "metadata": {
            "card_variant_id": target["card_variant_id"],
            "b5_selector_version": SELECTOR_VERSION,
            "b5_priority_tier": target["priority_tier"],
            "b5_priority_reason": target["priority_reason"],
        },
    }


def _ensure_identity(
    store: PkmnPricesStore,
    provider: PkmnPricesClient,
    target: dict[str, Any],
    *,
    set_cache: dict[str, int],
) -> tuple[dict[str, Any], int]:
    cached = store.get_identity_by_canonical(target["canonical_card_id"])
    if cached:
        expected = target.get("tcgplayer_product_id")
        if expected and str(cached.get("tcgplayer_product_id")) != str(expected):
            raise RuntimeError("B5_CACHED_IDENTITY_DRIFT")
        return cached, 0

    before = provider.credits_charged
    strategy = target.get("provider_identity_strategy")
    if strategy == "exact_tcgplayer_product_id":
        rows = provider.cards_by_tcgplayer_id(
            target["tcgplayer_product_id"], language="English", per_page=5
        )
        exact = [
            row for row in rows
            if str(row.get("tcg_player_id") or "") == str(target["tcgplayer_product_id"])
        ]
    elif strategy == "exact_set_name_card_name_number":
        set_name = str(target["provider_search_set_name"])
        cache_key = set_name.casefold()
        provider_set_id = set_cache.get(cache_key)
        if provider_set_id is None:
            set_rows = provider.sets_by_name(
                set_name, language="English", per_page=20
            )
            exact_sets = [
                row for row in set_rows
                if str(row.get("name") or "").strip().casefold() == cache_key
                and str(row.get("language") or "English").casefold() == "english"
            ]
            if len(exact_sets) != 1:
                raise RuntimeError(f"B5_PROVIDER_SET_COUNT_{len(exact_sets)}")
            provider_set_id = int(exact_sets[0]["id"])
            set_cache[cache_key] = provider_set_id

        rows = provider.cards_by_identity(
            name=str(target["provider_search_name"]),
            number=str(target["provider_search_number"]),
            set_id=provider_set_id,
            language="English",
            per_page=20,
        )
        exact = [
            row for row in rows
            if str(row.get("name") or "").strip().casefold()
                == str(target["provider_search_name"]).strip().casefold()
            and str(row.get("number") or "").strip().casefold()
                == str(target["provider_search_number"]).strip().casefold()
            and str((row.get("set") or {}).get("id") or "") == str(provider_set_id)
        ]
    else:
        raise RuntimeError("B5_PROVIDER_IDENTITY_STRATEGY_UNSUPPORTED")

    if len(exact) != 1:
        raise RuntimeError(f"B5_PROVIDER_IDENTITY_COUNT_{len(exact)}")
    identity = _identity_row(target, exact[0])
    store.upsert_identity(identity)
    return identity, provider.credits_charged - before


def _state(
    db: Any,
    store: PkmnPricesStore,
    target: dict[str, Any],
    *,
    reference: date,
    cutoff: date,
) -> dict[str, Any]:
    identity = store.get_identity_by_canonical(target["canonical_card_id"])
    if not identity:
        return {"identity": None, "sync": None, "ready": False, "rows_seen": 0, "oldest": None}
    sync = store.get_sync_state(int(identity["provider_card_id"]))
    if not sync:
        return {"identity": identity, "sync": None, "ready": False, "rows_seen": 0, "oldest": None}
    meta = dict(sync.get("metadata") or {})
    if meta.get("b5_horizon_cutoff") == cutoff.isoformat() and "b5_ready" in meta:
        return {
            "identity": identity,
            "sync": sync,
            "ready": bool(meta.get("b5_ready")),
            "ready_reason": meta.get("b5_ready_reason"),
            "rows_seen": int(sync.get("rows_seen") or 0),
            "oldest": meta.get("b5_oldest_sold_at"),
        }

    # Existing non-B5 evidence is reused, but never rewritten.
    summary = _evidence_summary(db, int(identity["provider_card_id"]))
    oldest = summary["oldest_sold_at"]
    drained = bool(
        sync.get("status") == "CURRENT"
        and (
            meta.get("targeted_backfill_complete") is True
            or meta.get("core_panel_backfill_complete") is True
        )
    )
    ready = drained or bool(oldest and date.fromisoformat(oldest) <= cutoff)
    return {
        "identity": identity,
        "sync": sync,
        "ready": ready,
        "ready_reason": "PROVIDER_DRAINED" if drained else ("HORIZON_180D" if ready else None),
        "rows_seen": int(sync.get("rows_seen") or 0),
        "oldest": oldest,
    }


def _upsert_state(
    store: PkmnPricesStore,
    target: dict[str, Any],
    identity: dict[str, Any],
    previous: dict[str, Any] | None,
    *,
    normalized: list[dict[str, Any]],
    has_more: bool,
    next_cursor: str | None,
    inserted: int,
    collected_at: str,
    oldest: str | None,
    reference: date,
    cutoff: date,
) -> tuple[bool, str | None]:
    meta = dict((previous or {}).get("metadata") or {})
    observed_ingested = [row["ingested_at"] for row in normalized if row.get("ingested_at")]
    watermark = meta.get("targeted_incremental_watermark") or meta.get("core_panel_incremental_watermark")
    if not watermark and observed_ingested:
        watermark = max(observed_ingested)
    drained = not has_more
    ready = drained or bool(oldest and date.fromisoformat(oldest) <= cutoff)
    reason = "PROVIDER_DRAINED" if drained else ("HORIZON_180D" if ready else None)
    last_ingested = (previous or {}).get("last_ingested_at")
    if drained and watermark:
        last_ingested = watermark
    last_sold_at = max(
        [
            str(value)
            for value in [
                (previous or {}).get("last_sold_at"),
                max([row.get("sold_at") for row in normalized if row.get("sold_at")], default=None),
            ]
            if value
        ],
        default=None,
    )
    store.upsert_sync_state({
        "provider_card_id": int(identity["provider_card_id"]),
        "canonical_card_id": target["canonical_card_id"],
        "last_ingested_at": last_ingested,
        "last_sold_at": last_sold_at,
        "last_attempt_at": collected_at,
        "last_success_at": collected_at,
        "status": "PARTIAL" if has_more else "CURRENT",
        "consecutive_failures": 0,
        "rows_seen": int((previous or {}).get("rows_seen") or 0) + len(normalized),
        "rows_inserted": int((previous or {}).get("rows_inserted") or 0) + inserted,
        "last_error_code": None,
        "metadata": {
            **meta,
            "targeted_backfill_in_progress": has_more,
            "targeted_backfill_complete": not has_more,
            "targeted_backfill_cursor": next_cursor if has_more else None,
            "targeted_incremental_watermark": watermark,
            "b5_reference_date": reference.isoformat(),
            "b5_horizon_cutoff": cutoff.isoformat(),
            "b5_oldest_sold_at": oldest,
            "b5_ready": ready,
            "b5_ready_reason": reason,
            "b5_priority_tier": target["priority_tier"],
            "b5_priority_reason": target["priority_reason"],
            "b5_selector_version": SELECTOR_VERSION,
        },
    })
    return ready, reason


def preflight(db: Any) -> dict[str, Any]:
    ready_core = _core_panel_ready_count(db)
    targets, meta = select_targets(db)
    reference, cutoff = _horizon()
    credit_day = _credit_day()
    prior = _daily_credits_used(db, credit_day)
    return {
        "status": "PREFLIGHT_OK",
        "core_panel_ready_count": ready_core,
        "core_panel_gate_ready": ready_core == EXPECTED_CORE_PANEL_READY,
        "target_count": len(targets),
        "gap_target_count": meta["gap_target_count"],
        "mover_target_count": meta["mover_target_count"],
        "selector_fingerprint": meta["selector_fingerprint"],
        "mover_snapshot": meta["mover_snapshot"],
        "reference_date": reference.isoformat(),
        "horizon_cutoff": cutoff.isoformat(),
        "daily_credit_cap": DAILY_B5_CREDIT_CAP,
        "prior_b5_credits_today": prior,
        "remaining_b5_credits_today": max(0, DAILY_B5_CREDIT_CAP - prior),
        "operational_pause": operational_pause_reason(db),
        "targets": [
            {
                "canonical_card_id": row["canonical_card_id"],
                "tcgplayer_product_id": row.get("tcgplayer_product_id"),
                "provider_identity_strategy": row.get("provider_identity_strategy"),
                "priority_tier": row["priority_tier"],
                "priority_reason": row["priority_reason"],
                "movement_rank": row["movement_rank"],
                "change_percent": row["change_percent"],
            }
            for row in targets
        ],
        "provider_requests": 0,
        "provider_credits_used": 0,
        "database_writes": 0,
    }


def run(db: Any, provider: PkmnPricesClient) -> dict[str, Any]:
    plan = preflight(db)
    if not plan["core_panel_gate_ready"]:
        return {**plan, "status": "BLOCKED", "reason": "CORE_PANEL_NOT_COMPLETE"}
    if plan["operational_pause"]:
        return {**plan, "status": "BLOCKED", "reason": plan["operational_pause"]["reason"]}
    invocation_cap = int(plan["remaining_b5_credits_today"])
    if invocation_cap <= 0:
        return {**plan, "status": "COMPLETE", "reason": "B5_DAILY_BUDGET_EXHAUSTED"}

    targets, selector_meta = select_targets(db)
    reference, cutoff = _horizon()
    store = PkmnPricesStore(db)
    run_id = str(uuid.uuid4())
    started_at = datetime.now(timezone.utc).isoformat()
    store.create_run({
        "run_id": run_id,
        "started_at": started_at,
        "finished_at": None,
        "status": "RUNNING",
        "selector_version": SELECTOR_VERSION,
        "collector_version": COLLECTOR_VERSION,
        "target_count": len(targets),
        "item_credit_cap": invocation_cap,
        "api_request_count": 0,
        "credits_used": 0,
        "provider_card_lookup_count": 0,
        "sold_item_count": 0,
        "exact_attribution_count": 0,
        "fair_value_signal_eligible_count": 0,
        "set_value_nm_eligible_count": 0,
        "manifest_fingerprint": selector_meta["selector_fingerprint"],
        "metadata": {
            "mode": MODE,
            "selector_fingerprint": selector_meta["selector_fingerprint"],
            "gap_target_count": selector_meta["gap_target_count"],
            "mover_target_count": selector_meta["mover_target_count"],
            "reference_date": reference.isoformat(),
            "horizon_cutoff": cutoff.isoformat(),
            "daily_credit_cap": DAILY_B5_CREDIT_CAP,
            "prior_b5_credits_today": plan["prior_b5_credits_today"],
            "invocation_credit_cap": invocation_cap,
            "canonical_price_mutation": False,
        },
    })

    by_id = {row["canonical_card_id"]: row for row in targets}
    blocked: set[str] = set()
    set_cache: dict[str, int] = {}
    totals = Counter()
    receipts: dict[str, dict[str, Any]] = {}
    pause = None

    # Repeat breadth rounds within the active priority tier. Tier 1 must be
    # exhausted/ready/blocked before tier 2 is allowed to spend.
    while provider.credits_charged < invocation_cap:
        states = {
            cid: _state(db, store, target, reference=reference, cutoff=cutoff)
            for cid, target in by_id.items()
        }
        unresolved_t1 = [
            by_id[cid] for cid, state in states.items()
            if by_id[cid]["priority_tier"] == 1 and not state["ready"] and cid not in blocked
        ]
        if unresolved_t1:
            pool = sorted(unresolved_t1, key=lambda row: (states[row["canonical_card_id"]]["rows_seen"], row["canonical_card_id"]))
        else:
            unresolved_t2 = [
                by_id[cid] for cid, state in states.items()
                if by_id[cid]["priority_tier"] == 2 and not state["ready"] and cid not in blocked
            ]
            if not unresolved_t2:
                break
            pool = sorted(
                unresolved_t2,
                key=lambda row: (
                    states[row["canonical_card_id"]]["rows_seen"],
                    int(row.get("movement_rank") or 999),
                    row["canonical_card_id"],
                ),
            )

        progress_this_round = False
        for target in pool:
            if provider.credits_charged >= invocation_cap:
                break
            pause = operational_pause_reason(db)
            if pause:
                break
            cid = target["canonical_card_id"]
            try:
                identity, lookup_credits = _ensure_identity(
                    store, provider, target, set_cache=set_cache
                )
                totals["identity_lookup_credits"] += lookup_credits
                if lookup_credits:
                    totals["provider_card_lookup_count"] += 1
                if provider.credits_charged >= invocation_cap:
                    break

                state = _state(db, store, target, reference=reference, cutoff=cutoff)
                if state["ready"]:
                    continue
                sync = state["sync"]
                meta = dict((sync or {}).get("metadata") or {})
                if sync:
                    cursor = meta.get("targeted_backfill_cursor")
                    if cursor is None and meta.get("core_panel_backfill_cursor"):
                        cursor = meta.get("core_panel_backfill_cursor")
                    if sync.get("status") == "PARTIAL" and not cursor:
                        raise RuntimeError("B5_EXISTING_CURSOR_NOT_RESUMABLE")
                else:
                    cursor = None

                oldest = state.get("oldest")
                rows_this_round = 0
                ready = False
                reason = None
                while rows_this_round < MAX_ROWS_PER_TARGET_ROUND and not ready:
                    if provider.credits_charged >= invocation_cap:
                        break
                    pause = operational_pause_reason(db)
                    if pause:
                        break
                    requested = min(
                        PAGE_SIZE,
                        MAX_ROWS_PER_TARGET_ROUND - rows_this_round,
                        invocation_cap - provider.credits_charged,
                    )
                    payload = provider.ebay_sold_page(
                        int(identity["provider_card_id"]),
                        graded=None,
                        sort="date_desc",
                        limit=requested,
                        cursor=str(cursor) if cursor else None,
                    )
                    data = payload.get("data") or []
                    raw_rows = [dict(row) for row in data if isinstance(row, dict)]
                    page = payload.get("pagination") or {}
                    has_more = bool(page.get("has_more"))
                    next_value = page.get("next_cursor")
                    next_cursor = str(next_value) if next_value else None
                    if has_more and (not next_cursor or next_cursor == cursor):
                        raise RuntimeError("B5_CURSOR_DID_NOT_ADVANCE")

                    collected_at = datetime.now(timezone.utc).isoformat()
                    normalized = []
                    for raw in raw_rows:
                        item = normalize_sold_listing(
                            raw,
                            provider_card_id=int(identity["provider_card_id"]),
                            canonical_card_id=target["canonical_card_id"],
                            internal_variants=target.get("internal_variants") or [],
                            collected_at=collected_at,
                        )
                        item["run_id"] = run_id
                        normalized.append(item)
                    page_oldest = min(
                        [str(row["sold_at"])[:10] for row in normalized if row.get("sold_at")],
                        default=None,
                    )
                    if page_oldest and (oldest is None or page_oldest < oldest):
                        oldest = page_oldest
                    inserted, duplicates, drifts = store.insert_evidence(normalized)
                    ready, reason = _upsert_state(
                        store,
                        target,
                        identity,
                        sync,
                        normalized=normalized,
                        has_more=has_more,
                        next_cursor=next_cursor,
                        inserted=inserted,
                        collected_at=collected_at,
                        oldest=oldest,
                        reference=reference,
                        cutoff=cutoff,
                    )
                    sold = len(normalized)
                    rows_this_round += sold
                    totals["sold_item_count"] += sold
                    totals["inserted"] += inserted
                    totals["duplicates"] += duplicates
                    totals["provider_metadata_drifts"] += drifts
                    progress_this_round = progress_this_round or sold > 0
                    cursor = next_cursor if has_more else None
                    sync = store.get_sync_state(int(identity["provider_card_id"]))
                    receipts[cid] = {
                        "canonical_card_id": cid,
                        "provider_card_id": int(identity["provider_card_id"]),
                        "priority_tier": target["priority_tier"],
                        "priority_reason": target["priority_reason"],
                        "movement_rank": target["movement_rank"],
                        "rows_seen": int((sync or {}).get("rows_seen") or 0),
                        "oldest_sold_at": dict((sync or {}).get("metadata") or {}).get("b5_oldest_sold_at"),
                        "ready": ready,
                        "ready_reason": reason,
                    }
                    if not has_more or ready:
                        break

                totals["targets_touched"] += int(rows_this_round > 0)
                totals["targets_newly_ready"] += int(ready)
                if pause:
                    break
            except Exception as exc:
                blocked.add(cid)
                receipts[cid] = {
                    "canonical_card_id": cid,
                    "priority_tier": target["priority_tier"],
                    "priority_reason": target["priority_reason"],
                    "status": "BLOCKED",
                    "error_code": type(exc).__name__,
                    "error": str(exc)[:240],
                }
                totals["targets_blocked"] += 1

        if pause or not progress_this_round:
            break

    final_states = {
        cid: _state(db, store, target, reference=reference, cutoff=cutoff)
        for cid, target in by_id.items()
    }
    tier1_ready = sum(
        state["ready"] for cid, state in final_states.items()
        if by_id[cid]["priority_tier"] == 1
    )
    tier2_ready = sum(
        state["ready"] for cid, state in final_states.items()
        if by_id[cid]["priority_tier"] == 2
    )
    finished_at = datetime.now(timezone.utc).isoformat()
    status = "PARTIAL" if pause or blocked else "COMPLETE"
    store.update_run(run_id, {
        "finished_at": finished_at,
        "status": status,
        "api_request_count": provider.request_attempt_count,
        "credits_used": provider.credits_charged,
        "provider_card_lookup_count": totals["provider_card_lookup_count"],
        "sold_item_count": totals["sold_item_count"],
        "exact_attribution_count": 0,
        "fair_value_signal_eligible_count": 0,
        "set_value_nm_eligible_count": 0,
        "error_code": None,
        "metadata": {
            "mode": MODE,
            "selector_fingerprint": selector_meta["selector_fingerprint"],
            "gap_target_count": selector_meta["gap_target_count"],
            "mover_target_count": selector_meta["mover_target_count"],
            "reference_date": reference.isoformat(),
            "horizon_cutoff": cutoff.isoformat(),
            "daily_credit_cap": DAILY_B5_CREDIT_CAP,
            "prior_b5_credits_today": plan["prior_b5_credits_today"],
            "invocation_credit_cap": invocation_cap,
            "gap_ready_count": tier1_ready,
            "mover_ready_count": tier2_ready,
            "blocked_count": len(blocked),
            "pause": pause,
            "receipts": list(receipts.values()),
            "canonical_price_mutation": False,
        },
    })
    return {
        "status": status,
        "run_id": run_id,
        "credits_used": provider.credits_charged,
        "credit_cap": invocation_cap,
        "gap_target_count": selector_meta["gap_target_count"],
        "gap_ready_count": tier1_ready,
        "mover_target_count": selector_meta["mover_target_count"],
        "mover_ready_count": tier2_ready,
        "blocked_count": len(blocked),
        "pause": pause,
        **dict(totals),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--preflight", action="store_true")
    mode.add_argument("--commit", action="store_true")
    args = parser.parse_args()

    from backend.db.clients.supabase_client import create_service_role_client

    db = create_service_role_client()
    if args.preflight:
        result = preflight(db)
    else:
        credentials = load_pkmnprices_credentials(allow_frontend_fallback=False)
        result = run(
            db,
            PkmnPricesClient(credentials.api_key, min_request_interval=0.55),
        )
    print(json.dumps(result, indent=2, sort_keys=True, default=str))
    return 3 if result["status"] == "BLOCKED" else 0


if __name__ == "__main__":
    raise SystemExit(main())
