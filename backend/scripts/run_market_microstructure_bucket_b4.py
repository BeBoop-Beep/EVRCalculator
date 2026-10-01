"""Breadth-first Phase 1 sold-history backfill for Core Panel V1.

Phase 1 readiness is deliberately narrower than lifetime archival:
- provider-retained history is exhausted; OR
- oldest persisted sold_at is on/before 2026-04-02, the frozen 180-day
  horizon for reference date 2026-09-29.

This coordinator never starts Phase 2 lifetime archival. It is gated behind a
healthy exact 207-card active-supply observation for the same Phoenix date.
"""
from __future__ import annotations

import argparse
import json
import math
import time
import uuid
from collections import Counter
from datetime import date, datetime, timedelta, timezone
from typing import Any
from zoneinfo import ZoneInfo

from backend.pricing_pipeline.pkmnprices_client import (
    PkmnPricesAPIError,
    PkmnPricesClient,
)
from backend.pricing_pipeline.pkmnprices_credentials import load_pkmnprices_credentials
from backend.pricing_pipeline.pkmnprices_store import PkmnPricesStore
from backend.scripts.run_market_microstructure_bucket_b import (
    COLLECTOR_VERSION,
    PANEL_FINGERPRINT,
    _identity,
    _normalize,
    load_panel,
)

REFERENCE_DATE = date(2026, 9, 29)
HORIZON_DAYS = 180
HORIZON_CUTOFF = REFERENCE_DATE - timedelta(days=HORIZON_DAYS)
SOURCE_PROVIDER = "pkmnprices_tcgplayer"
SELECTOR_VERSION = "market_microstructure_core_panel_phase1_v1"
PAGE_SIZE = 20
MAX_ROWS_PER_CARD_DAY = 80
ACCOUNT_DAILY_CREDIT_LIMIT = 75000
DAILY_B_CREDIT_CAP = 55000
ACCOUNT_RESERVE_CREDITS = ACCOUNT_DAILY_CREDIT_LIMIT - DAILY_B_CREDIT_CAP
IDENTITY_LOOKUP_WORST_CASE = 5
CALIBRATED_MEAN_READY_ROWS = 419.8
EXPECTED_PANEL_COUNT = 207
FIRST_FULL_C_DATE = date(2026, 9, 30)


def phoenix_date() -> str:
    return datetime.now(ZoneInfo("America/Phoenix")).date().isoformat()


def provider_credit_day_utc() -> str:
    # PkmnPrices resets at midnight UTC, so the provider credit day is exactly
    # the current UTC calendar date.
    return datetime.now(timezone.utc).date().isoformat()


def _daily_b4_credits_used(db: Any, credit_day: str) -> int:
    start = datetime.fromisoformat(credit_day + "T00:00:00+00:00")
    end = start + timedelta(days=1)
    rows = (
        db.table("pkmnprices_sold_runs_v1")
        .select("credits_used,metadata,started_at")
        .gte("started_at", start.isoformat())
        .lt("started_at", end.isoformat())
        .execute()
        .data
        or []
    )
    return sum(
        int(row.get("credits_used") or 0)
        for row in rows
        if dict(row.get("metadata") or {}).get("mode")
        == "bucket_b4_phase1_breadth_180d"
    )


def _scrape_batch_state(db: Any, expected_date: str) -> dict[str, Any] | None:
    rows = (
        db.table("pokemon_scrape_batches")
        .select(
            "id,market_date,status,expected_set_count,queued_set_count,"
            "succeeded_set_count,failed_set_count,missing_set_count,"
            "started_at,completed_at,promoted_at"
        )
        .eq("market_date", expected_date)
        .order("created_at", desc=True)
        .limit(1)
        .execute()
        .data
        or []
    )
    return dict(rows[0]) if rows else None


def operational_pause_reason(
    db: Any,
    *,
    now_local: datetime | None = None,
) -> dict[str, Any] | None:
    now_local = now_local or datetime.now(ZoneInfo("America/Phoenix"))
    local_time = now_local.time()
    expected_date = now_local.date().isoformat()

    # Give the C continuity panel an uncontested window around its 21:10
    # primary, 21:40 retry and 22:10 health run.
    if now_local.date() >= FIRST_FULL_C_DATE and (
        (local_time.hour == 20 and local_time.minute >= 55)
        or (21 <= local_time.hour < 22)
        or (local_time.hour == 22 and local_time.minute < 25)
    ):
        return {
            "reason": "C_CONTINUITY_WINDOW",
            "expected_date": expected_date,
        }

    # The daily TCGPlayer scrape owns the machine beginning just before the
    # 01:05 batch creation. Once that window begins, B4 remains paused until
    # the current Phoenix-date batch is authoritatively complete.
    after_scrape_window_start = (
        local_time.hour > 0
        or (local_time.hour == 0 and local_time.minute >= 55)
    )
    if after_scrape_window_start:
        batch = _scrape_batch_state(db, expected_date)
        if not batch:
            return {
                "reason": "SCRAPE_BATCH_NOT_READY",
                "expected_date": expected_date,
            }
        if str(batch.get("status") or "").casefold() != "complete":
            return {
                "reason": "SCRAPE_BATCH_ACTIVE",
                "expected_date": expected_date,
                "batch_id": batch.get("id"),
                "batch_status": batch.get("status"),
            }
    return None


def c_daily_gate(db: Any, expected_date: str) -> dict[str, Any]:
    rows = (
        db.table("market_active_supply_snapshot_runs_v1")
        .select(
            "run_id,status,target_count,observed_target_count,"
            "provider_credits_used,metadata"
        )
        .eq("panel_fingerprint", PANEL_FINGERPRINT)
        .eq("source_provider", SOURCE_PROVIDER)
        .eq("expected_observation_date", expected_date)
        .limit(1)
        .execute()
        .data
        or []
    )
    if not rows:
        return {
            "ready": False,
            "reason": "C_RUN_MISSING",
            "expected_date": expected_date,
        }
    run = dict(rows[0])
    metadata = dict(run.get("metadata") or {})
    ready = bool(
        run.get("status") == "COMPLETE"
        and int(run.get("target_count") or 0) == EXPECTED_PANEL_COUNT
        and int(run.get("observed_target_count") or 0) == EXPECTED_PANEL_COUNT
        and metadata.get("full_panel_daily") is True
    )
    return {
        "ready": ready,
        "reason": "READY" if ready else "C_RUN_NOT_EXACT_COMPLETE",
        "expected_date": expected_date,
        "run_id": run.get("run_id"),
        "status": run.get("status"),
        "target_count": int(run.get("target_count") or 0),
        "observed_target_count": int(run.get("observed_target_count") or 0),
        "provider_credits_used": int(run.get("provider_credits_used") or 0),
        "full_panel_daily": metadata.get("full_panel_daily") is True,
    }


def _evidence_summary(db: Any, provider_card_id: int) -> dict[str, Any]:
    """One-time compatibility path for sync rows created before Phase 1 metadata."""
    rows: list[dict[str, Any]] = []
    start = 0
    while True:
        page = (
            db.table("pkmnprices_ebay_sold_evidence_v1")
            .select("sold_at,graded,attribution")
            .eq("provider_card_id", provider_card_id)
            .order("sold_at")
            .range(start, start + 999)
            .execute()
            .data
            or []
        )
        rows.extend(dict(row) for row in page)
        if len(page) < 1000:
            break
        start += 1000
    sold_dates = sorted(str(row.get("sold_at") or "")[:10] for row in rows if row.get("sold_at"))
    return {
        "transaction_count": len(rows),
        "oldest_sold_at": sold_dates[0] if sold_dates else None,
        "newest_sold_at": sold_dates[-1] if sold_dates else None,
    }


def _horizon_ready(oldest_sold_at: str | None, *, drained: bool) -> tuple[bool, str | None]:
    if drained:
        return True, "PROVIDER_DRAINED"
    if oldest_sold_at and date.fromisoformat(str(oldest_sold_at)[:10]) <= HORIZON_CUTOFF:
        return True, "HORIZON_180D"
    return False, None


def _paged_rows(db: Any, table: str, columns: str) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    start = 0
    while True:
        page = (
            db.table(table)
            .select(columns)
            .range(start, start + 999)
            .execute()
            .data
            or []
        )
        rows.extend(dict(row) for row in page)
        if len(page) < 1000:
            return rows
        start += 1000


def _sync_phase1(
    *,
    db: Any,
    target: dict[str, Any],
    identity: dict[str, Any] | None,
    sync: dict[str, Any] | None,
) -> dict[str, Any]:
    if not identity:
        return {
            "target": target,
            "identity": None,
            "provider_card_id": None,
            "sync": None,
            "sync_meta": {},
            "rows_seen": 0,
            "oldest_sold_at": None,
            "drained": False,
            "phase1_ready": False,
            "phase1_ready_reason": None,
            "needs_metadata_init": False,
        }
    if str(identity.get("tcgplayer_product_id")) != str(target["tcgplayer_product_id"]):
        raise RuntimeError("PHASE1_CACHED_IDENTITY_MISMATCH")

    provider_id = int(identity["provider_card_id"])
    if not sync:
        return {
            "target": target,
            "identity": identity,
            "provider_card_id": provider_id,
            "sync": None,
            "sync_meta": {},
            "rows_seen": 0,
            "oldest_sold_at": None,
            "drained": False,
            "phase1_ready": False,
            "phase1_ready_reason": None,
            "needs_metadata_init": False,
        }

    meta = dict(sync.get("metadata") or {})
    drained = bool(
        sync.get("status") == "CURRENT"
        and meta.get("core_panel_backfill_complete") is True
    )
    rows_seen = int(sync.get("rows_seen") or 0)

    metadata_current = (
        meta.get("phase1_reference_date") == REFERENCE_DATE.isoformat()
        and meta.get("phase1_horizon_cutoff") == HORIZON_CUTOFF.isoformat()
        and "phase1_ready" in meta
    )
    if metadata_current:
        oldest = meta.get("phase1_oldest_sold_at")
        return {
            "target": target,
            "identity": identity,
            "provider_card_id": provider_id,
            "sync": sync,
            "sync_meta": meta,
            "rows_seen": rows_seen,
            "oldest_sold_at": oldest,
            "drained": drained,
            "phase1_ready": bool(meta.get("phase1_ready")),
            "phase1_ready_reason": meta.get("phase1_ready_reason"),
            "needs_metadata_init": False,
        }

    summary = _evidence_summary(db, provider_id)
    oldest = summary["oldest_sold_at"]
    ready, reason = _horizon_ready(oldest, drained=drained)
    return {
        "target": target,
        "identity": identity,
        "provider_card_id": provider_id,
        "sync": sync,
        "sync_meta": meta,
        "rows_seen": max(rows_seen, int(summary["transaction_count"])),
        "oldest_sold_at": oldest,
        "drained": drained,
        "phase1_ready": ready,
        "phase1_ready_reason": reason,
        "needs_metadata_init": True,
    }


def _persist_phase1_summary(
    *,
    store: PkmnPricesStore,
    state: dict[str, Any],
    oldest_sold_at: str | None,
    ready: bool,
    ready_reason: str | None,
    expected_date: str,
) -> None:
    sync = state.get("sync")
    if not sync or state.get("provider_card_id") is None:
        return
    meta = dict(state.get("sync_meta") or {})
    store.upsert_sync_state({
        "provider_card_id": state["provider_card_id"],
        "canonical_card_id": state["target"]["canonical_card_id"],
        "last_ingested_at": sync.get("last_ingested_at"),
        "last_sold_at": sync.get("last_sold_at"),
        "last_attempt_at": sync.get("last_attempt_at"),
        "last_success_at": sync.get("last_success_at"),
        "status": sync.get("status"),
        "consecutive_failures": int(sync.get("consecutive_failures") or 0),
        "rows_seen": int(sync.get("rows_seen") or 0),
        "rows_inserted": int(sync.get("rows_inserted") or 0),
        "last_error_code": sync.get("last_error_code"),
        "metadata": {
            **meta,
            "panel_fingerprint": PANEL_FINGERPRINT,
            "phase1_reference_date": REFERENCE_DATE.isoformat(),
            "phase1_horizon_cutoff": HORIZON_CUTOFF.isoformat(),
            "phase1_oldest_sold_at": oldest_sold_at,
            "phase1_ready": ready,
            "phase1_ready_reason": ready_reason,
            "phase1_summary_updated_for_date": expected_date,
        },
    })


def panel_states(db: Any) -> list[dict[str, Any]]:
    panel = load_panel()
    panel_ids = {str(row["canonical_card_id"]) for row in panel["rows"]}

    identity_rows = _paged_rows(
        db,
        "pkmnprices_card_identity_v1",
        "provider_card_id,canonical_card_id,tcgplayer_product_id,language",
    )
    identity_by_canonical = {
        str(row["canonical_card_id"]): row
        for row in identity_rows
        if str(row.get("canonical_card_id")) in panel_ids
        and str(row.get("language") or "") == "English"
    }

    provider_ids = {
        int(row["provider_card_id"])
        for row in identity_by_canonical.values()
        if row.get("provider_card_id") is not None
    }
    sync_rows = _paged_rows(
        db,
        "pkmnprices_sold_sync_state_v1",
        "provider_card_id,canonical_card_id,last_ingested_at,last_sold_at,"
        "last_attempt_at,last_success_at,status,consecutive_failures,"
        "rows_seen,rows_inserted,last_error_code,metadata",
    )
    sync_by_provider = {
        int(row["provider_card_id"]): row
        for row in sync_rows
        if row.get("provider_card_id") is not None
        and int(row["provider_card_id"]) in provider_ids
    }

    states: list[dict[str, Any]] = []
    for index, target in enumerate(panel["rows"]):
        identity = identity_by_canonical.get(str(target["canonical_card_id"]))
        sync = (
            sync_by_provider.get(int(identity["provider_card_id"]))
            if identity and identity.get("provider_card_id") is not None
            else None
        )
        state = _sync_phase1(
            db=db,
            target=target,
            identity=identity,
            sync=sync,
        )
        state["panel_index"] = index
        states.append(state)
    return states


def _breadth_order(states: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return sorted(
        [row for row in states if not row["phase1_ready"]],
        key=lambda row: (row["rows_seen"], row["panel_index"]),
    )


def preflight(db: Any, *, expected_date: str, credit_cap: int) -> dict[str, Any]:
    if not 1 <= credit_cap <= DAILY_B_CREDIT_CAP:
        raise ValueError("credit_cap must be between 1 and 55000")
    gate = c_daily_gate(db, expected_date)
    credit_day = provider_credit_day_utc()
    prior_b4_credits = _daily_b4_credits_used(db, credit_day)
    remaining_b4_credits = max(0, credit_cap - prior_b4_credits)
    pause = operational_pause_reason(db)
    states = panel_states(db)
    ready = [row for row in states if row["phase1_ready"]]
    pending = [row for row in states if not row["phase1_ready"]]
    ordered = _breadth_order(states)
    return {
        "status": "PREFLIGHT_OK",
        "panel_fingerprint": PANEL_FINGERPRINT,
        "panel_count": len(states),
        "expected_date": expected_date,
        "reference_date": REFERENCE_DATE.isoformat(),
        "horizon_days": HORIZON_DAYS,
        "horizon_cutoff": HORIZON_CUTOFF.isoformat(),
        "c_gate": gate,
        "operational_pause": pause,
        "provider_credit_day_utc": credit_day,
        "account_daily_credit_limit": ACCOUNT_DAILY_CREDIT_LIMIT,
        "account_reserve_credits": ACCOUNT_RESERVE_CREDITS,
        "prior_b4_credits_today": prior_b4_credits,
        "remaining_b4_credits_today": remaining_b4_credits,
        "phase1_ready_count": len(ready),
        "phase1_remaining_count": len(pending),
        "identity_resolved_count": sum(row["identity"] is not None for row in states),
        "identity_unresolved_count": sum(row["identity"] is None for row in states),
        "legacy_summary_init_count": sum(row["needs_metadata_init"] for row in states),
        "next_candidates": [
            {
                "canonical_card_id": row["target"]["canonical_card_id"],
                "tcgplayer_product_id": row["target"]["tcgplayer_product_id"],
                "rows_seen": row["rows_seen"],
                "identity_resolved": row["identity"] is not None,
            }
            for row in ordered[:20]
        ],
        "credit_cap": credit_cap,
        "provider_requests": 0,
        "provider_credits_used": 0,
        "database_writes": 0,
        "phase2_lifetime_archival": False,
    }


def _can_spend(*, local_remaining: int, requested: int) -> bool:
    return requested > 0 and local_remaining >= requested


def _resolve_identity(
    *,
    provider: PkmnPricesClient,
    store: PkmnPricesStore,
    target: dict[str, Any],
) -> dict[str, Any]:
    matches = [
        row
        for row in provider.cards_by_tcgplayer_id(target["tcgplayer_product_id"])
        if str(row.get("tcg_player_id") or "") == str(target["tcgplayer_product_id"])
    ]
    if len(matches) != 1:
        raise RuntimeError(f"PHASE1_PROVIDER_IDENTITY_COUNT_{len(matches)}")
    identity = _identity(target, matches[0])
    store.upsert_identity(identity)
    return identity


def _update_sync_after_page(
    *,
    store: PkmnPricesStore,
    target: dict[str, Any],
    provider_card_id: int,
    previous_sync: dict[str, Any] | None,
    previous_meta: dict[str, Any],
    normalized: list[dict[str, Any]],
    has_more: bool,
    next_cursor: str | None,
    collected_at: str,
    inserted: int,
    oldest_sold_at: str | None,
    expected_date: str,
) -> tuple[bool, str | None]:
    observed_ingested = [
        row["ingested_at"] for row in normalized if row.get("ingested_at")
    ]
    watermark = previous_meta.get("core_panel_incremental_watermark")
    if not watermark and observed_ingested:
        watermark = max(observed_ingested)

    last_ingested = (previous_sync or {}).get("last_ingested_at")
    if not has_more and watermark:
        last_ingested = watermark

    drained = not has_more
    ready, ready_reason = _horizon_ready(oldest_sold_at, drained=drained)
    store.upsert_sync_state({
        "provider_card_id": provider_card_id,
        "canonical_card_id": target["canonical_card_id"],
        "last_ingested_at": last_ingested,
        "last_sold_at": max(
            [
                str(value)
                for value in [
                    (previous_sync or {}).get("last_sold_at"),
                    max(
                        [row.get("sold_at") for row in normalized if row.get("sold_at")],
                        default=None,
                    ),
                ]
                if value
            ],
            default=None,
        ),
        "last_attempt_at": collected_at,
        "last_success_at": collected_at,
        "status": "PARTIAL" if has_more else "CURRENT",
        "consecutive_failures": 0,
        "rows_seen": int((previous_sync or {}).get("rows_seen") or 0) + len(normalized),
        "rows_inserted": int((previous_sync or {}).get("rows_inserted") or 0) + inserted,
        "last_error_code": None,
        "metadata": {
            **previous_meta,
            "panel_fingerprint": PANEL_FINGERPRINT,
            "stream": "combined_raw_graded",
            "core_panel_backfill_in_progress": has_more,
            "core_panel_backfill_complete": not has_more,
            "core_panel_backfill_cursor": next_cursor if has_more else None,
            "core_panel_incremental_watermark": watermark,
            "phase1_reference_date": REFERENCE_DATE.isoformat(),
            "phase1_horizon_cutoff": HORIZON_CUTOFF.isoformat(),
            "phase1_oldest_sold_at": oldest_sold_at,
            "phase1_ready": ready,
            "phase1_ready_reason": ready_reason,
            "phase1_last_breadth_date": expected_date,
        },
    })
    return ready, ready_reason


def run_phase1(
    *,
    db: Any,
    provider: PkmnPricesClient,
    expected_date: str,
    credit_cap: int,
) -> dict[str, Any]:
    if not 1 <= credit_cap <= DAILY_B_CREDIT_CAP:
        raise ValueError("credit_cap must be between 1 and 55000")

    gate = c_daily_gate(db, expected_date)
    credit_day = provider_credit_day_utc()
    prior_b4_credits = _daily_b4_credits_used(db, credit_day)
    invocation_credit_cap = max(0, credit_cap - prior_b4_credits)
    pause = operational_pause_reason(db)
    if pause:
        return {
            "status": "BLOCKED",
            "reason": pause["reason"],
            "operational_pause": pause,
            "c_gate": gate,
            "provider_credit_day_utc": credit_day,
            "prior_b4_credits_today": prior_b4_credits,
            "remaining_b4_credits_today": invocation_credit_cap,
            "provider_credits_used": 0,
            "database_writes": 0,
            "phase2_lifetime_archival": False,
        }
    if invocation_credit_cap <= 0:
        return {
            "status": "COMPLETE",
            "reason": "B4_DAILY_BUDGET_EXHAUSTED",
            "c_gate": gate,
            "provider_credit_day_utc": credit_day,
            "prior_b4_credits_today": prior_b4_credits,
            "remaining_b4_credits_today": 0,
            "provider_credits_used": 0,
            "database_writes": 0,
            "phase2_lifetime_archival": False,
        }

    store = PkmnPricesStore(db)
    states = panel_states(db)

    # Persist one-time phase summary metadata for pre-B4 sync rows. This avoids
    # rescanning their full evidence ledger on every future daily run.
    summary_init_writes = 0
    for state in states:
        if state["needs_metadata_init"] and state["sync"]:
            _persist_phase1_summary(
                store=store,
                state=state,
                oldest_sold_at=state["oldest_sold_at"],
                ready=state["phase1_ready"],
                ready_reason=state["phase1_ready_reason"],
                expected_date=expected_date,
            )
            summary_init_writes += 1

    pending = _breadth_order(states)

    run_id = str(uuid.uuid4())
    started_at = datetime.now(timezone.utc).isoformat()
    store.create_run({
        "run_id": run_id,
        "started_at": started_at,
        "finished_at": None,
        "status": "RUNNING",
        "selector_version": SELECTOR_VERSION,
        "collector_version": COLLECTOR_VERSION,
        "target_count": EXPECTED_PANEL_COUNT,
        "item_credit_cap": invocation_credit_cap,
        "api_request_count": 0,
        "credits_used": 0,
        "provider_card_lookup_count": 0,
        "sold_item_count": 0,
        "exact_attribution_count": 0,
        "fair_value_signal_eligible_count": 0,
        "set_value_nm_eligible_count": 0,
        "manifest_fingerprint": PANEL_FINGERPRINT,
        "metadata": {
            "mode": "bucket_b4_phase1_breadth_180d",
            "panel_fingerprint": PANEL_FINGERPRINT,
            "expected_date": expected_date,
            "reference_date": REFERENCE_DATE.isoformat(),
            "horizon_cutoff": HORIZON_CUTOFF.isoformat(),
            "max_rows_per_card_day": MAX_ROWS_PER_CARD_DAY,
            "page_size": PAGE_SIZE,
            "phase2_lifetime_archival": False,
            "c_gate_run_id": gate.get("run_id"),
            "provider_credit_day_utc": credit_day,
            "account_daily_credit_limit": ACCOUNT_DAILY_CREDIT_LIMIT,
            "account_reserve_credits": ACCOUNT_RESERVE_CREDITS,
            "daily_b4_credit_cap": credit_cap,
            "prior_b4_credits_today": prior_b4_credits,
            "invocation_credit_cap": invocation_credit_cap,
        },
    })

    totals = Counter()
    receipts: list[dict[str, Any]] = []
    failures: list[dict[str, Any]] = []
    write_seconds = 0.0

    for initial in pending:
        if provider.credits_charged >= invocation_credit_cap:
            break

        target = initial["target"]
        identity = initial["identity"]
        identity_lookup_credits = 0
        try:
            if identity is None:
                if not _can_spend(
                    local_remaining=invocation_credit_cap - provider.credits_charged,
                    requested=IDENTITY_LOOKUP_WORST_CASE,
                ):
                    totals["stopped_for_budget_or_reserve"] += 1
                    break
                before = provider.credits_charged
                identity = _resolve_identity(
                    provider=provider,
                    store=store,
                    target=target,
                )
                identity_lookup_credits = provider.credits_charged - before
                if provider.credits_charged > invocation_credit_cap:
                    raise RuntimeError("PHASE1_DAILY_CREDIT_CAP_EXCEEDED")
                totals["provider_card_lookup_count"] += 1

            provider_id = int(identity["provider_card_id"])
            sync = store.get_sync_state(provider_id)
            meta = dict((sync or {}).get("metadata") or {})

            if sync:
                drained = bool(
                    sync.get("status") == "CURRENT"
                    and meta.get("core_panel_backfill_complete") is True
                )
                ready, reason = _horizon_ready(
                    meta.get("phase1_oldest_sold_at"),
                    drained=drained,
                )
                if ready:
                    totals["targets_skipped_ready"] += 1
                    continue
                if not (
                    sync.get("status") == "PARTIAL"
                    and meta.get("core_panel_backfill_in_progress") is True
                    and meta.get("core_panel_backfill_cursor")
                ):
                    raise RuntimeError("PHASE1_EXISTING_CURSOR_NOT_RESUMABLE")
                cursor: str | None = str(meta["core_panel_backfill_cursor"])
                oldest = meta.get("phase1_oldest_sold_at")
            else:
                cursor = None
                oldest = None

            rows_this_card = 0
            pages: list[dict[str, Any]] = []
            ready = False
            ready_reason: str | None = None

            while rows_this_card < MAX_ROWS_PER_CARD_DAY and not ready:
                remaining_local = invocation_credit_cap - provider.credits_charged
                remaining_card = MAX_ROWS_PER_CARD_DAY - rows_this_card
                requested = min(PAGE_SIZE, remaining_local, remaining_card)
                if requested <= 0 or not _can_spend(
                    local_remaining=remaining_local,
                    requested=requested,
                ):
                    totals["stopped_for_budget_or_reserve"] += 1
                    break

                pause = operational_pause_reason(db)
                if pause:
                    totals["paused_for_operational_work"] += 1
                    totals["pause_reason_" + pause["reason"].lower()] += 1
                    break

                before_credits = provider.credits_charged
                payload = provider.ebay_sold_page(
                    provider_id,
                    graded=None,
                    sort="date_desc",
                    limit=requested,
                    cursor=cursor,
                )
                data = payload.get("data") or []
                if not isinstance(data, list):
                    raise PkmnPricesAPIError(
                        200, "invalid_payload", "sold data is not an array"
                    )
                raw_rows = [dict(row) for row in data if isinstance(row, dict)]
                page = payload.get("pagination") or {}
                has_more = bool(page.get("has_more"))
                next_value = page.get("next_cursor")
                next_cursor = str(next_value) if next_value else None
                if has_more and (not next_cursor or next_cursor == cursor):
                    raise PkmnPricesAPIError(
                        200,
                        "invalid_pagination",
                        "sold pagination cursor did not advance",
                    )

                collected_at = datetime.now(timezone.utc).isoformat()
                normalized = [
                    _normalize(
                        raw,
                        target,
                        provider_id,
                        run_id,
                        collected_at,
                    )
                    for raw in raw_rows
                ]
                page_oldest = min(
                    [str(row["sold_at"])[:10] for row in normalized if row.get("sold_at")],
                    default=None,
                )
                if page_oldest and (oldest is None or page_oldest < oldest):
                    oldest = page_oldest

                write_started = time.perf_counter()
                inserted, duplicates, drifts = store.insert_evidence(normalized)
                ready, ready_reason = _update_sync_after_page(
                    store=store,
                    target=target,
                    provider_card_id=provider_id,
                    previous_sync=sync,
                    previous_meta=meta,
                    normalized=normalized,
                    has_more=has_more,
                    next_cursor=next_cursor,
                    collected_at=collected_at,
                    inserted=inserted,
                    oldest_sold_at=oldest,
                    expected_date=expected_date,
                )
                write_seconds += time.perf_counter() - write_started
                rows_this_card += len(normalized)
                totals.update({
                    "sold_item_count": len(normalized),
                    "inserted": inserted,
                    "duplicates": duplicates,
                    "provider_metadata_drifts": drifts,
                    "exact_attribution_count": sum(
                        row["attribution"] == "exact" for row in normalized
                    ),
                    "fair_value_signal_eligible_count": sum(
                        bool(row["fair_value_signal_eligible"]) for row in normalized
                    ),
                })
                pages.append({
                    "rows_seen": len(normalized),
                    "rows_inserted": inserted,
                    "credits": provider.credits_charged - before_credits,
                    "has_more": has_more,
                    "oldest_sold_at": oldest,
                    "phase1_ready": ready,
                    "phase1_ready_reason": ready_reason,
                })

                sync = store.get_sync_state(provider_id)
                meta = dict((sync or {}).get("metadata") or {})
                cursor = meta.get("core_panel_backfill_cursor") if has_more else None

                if not has_more or ready:
                    break

            totals["cards_sliced"] += int(rows_this_card > 0)
            totals["cards_newly_ready"] += int(ready)
            totals["cards_newly_drained"] += int(ready_reason == "PROVIDER_DRAINED")
            receipts.append({
                "canonical_card_id": target["canonical_card_id"],
                "provider_card_id": provider_id,
                "identity_lookup_credits": identity_lookup_credits,
                "newly_purchased_rows": rows_this_card,
                "pages": pages,
                "oldest_sold_at": oldest,
                "phase1_ready": ready,
                "phase1_ready_reason": ready_reason,
            })

            if totals["stopped_for_budget_or_reserve"] or totals["paused_for_operational_work"]:
                break
        except Exception as exc:
            totals["targets_failed"] += 1
            failures.append({
                "canonical_card_id": target["canonical_card_id"],
                "tcgplayer_product_id": target["tcgplayer_product_id"],
                "code": type(exc).__name__,
                "message": str(exc)[:300],
            })
            continue

    # Recompute only from sync metadata/evidence-absent rows; the one-time legacy
    # summaries above have already been persisted.
    final_states = panel_states(db)
    ready_count = sum(row["phase1_ready"] for row in final_states)
    remaining_count = EXPECTED_PANEL_COUNT - ready_count
    estimated_remaining_credits = sum(
        max(0.0, CALIBRATED_MEAN_READY_ROWS - float(row["rows_seen"]))
        + (1.0 if row["identity"] is None else 0.0)
        for row in final_states
        if not row["phase1_ready"]
    )
    projected_days = math.ceil(estimated_remaining_credits / DAILY_B_CREDIT_CAP) if remaining_count else 0
    pause_at_finish = operational_pause_reason(db)

    finished_at = datetime.now(timezone.utc).isoformat()
    status = (
        "PARTIAL"
        if failures or totals["paused_for_operational_work"]
        else "COMPLETE"
    )
    store.update_run(run_id, {
        "finished_at": finished_at,
        "status": status,
        "api_request_count": provider.request_attempt_count,
        "credits_used": provider.credits_charged,
        "provider_card_lookup_count": totals["provider_card_lookup_count"],
        "sold_item_count": totals["sold_item_count"],
        "exact_attribution_count": totals["exact_attribution_count"],
        "fair_value_signal_eligible_count": totals["fair_value_signal_eligible_count"],
        "set_value_nm_eligible_count": 0,
        "error_code": failures[0]["code"] if failures else None,
        "metadata": {
            "mode": "bucket_b4_phase1_breadth_180d",
            "panel_fingerprint": PANEL_FINGERPRINT,
            "expected_date": expected_date,
            "reference_date": REFERENCE_DATE.isoformat(),
            "horizon_cutoff": HORIZON_CUTOFF.isoformat(),
            "c_gate_run_id": gate.get("run_id"),
            "summary_init_writes": summary_init_writes,
            "receipts": receipts,
            "failures": failures,
            "phase1_ready_count": ready_count,
            "phase1_remaining_count": remaining_count,
            "estimated_remaining_credits_mean_calibration": round(
                estimated_remaining_credits, 1
            ),
            "projected_remaining_b_days_mean_calibration": projected_days,
            "provider_rate_remaining_requests": provider.rate_remaining,
            "provider_credits_limit": provider.credits_limit,
            "provider_credit_day_utc": credit_day,
            "prior_b4_credits_today": prior_b4_credits,
            "b4_credits_after_run": prior_b4_credits + provider.credits_charged,
            "b4_credits_remaining_today": max(
                0, credit_cap - prior_b4_credits - provider.credits_charged
            ),
            "account_reserve_credits": ACCOUNT_RESERVE_CREDITS,
            "operational_pause_at_finish": pause_at_finish,
            "phase2_lifetime_archival": False,
            "db_insert_and_state_write_seconds": round(write_seconds, 6),
        },
    })

    return {
        "status": status,
        "run_id": run_id,
        "expected_date": expected_date,
        "c_gate": gate,
        "credits_used": provider.credits_charged,
        "credit_cap": credit_cap,
        "invocation_credit_cap": invocation_credit_cap,
        "provider_credits_limit": provider.credits_limit,
        "provider_rate_remaining_requests": provider.rate_remaining,
        "provider_credit_day_utc": credit_day,
        "prior_b4_credits_today": prior_b4_credits,
        "b4_credits_after_run": prior_b4_credits + provider.credits_charged,
        "b4_credits_remaining_today": max(
            0, credit_cap - prior_b4_credits - provider.credits_charged
        ),
        "account_reserve_credits": ACCOUNT_RESERVE_CREDITS,
        "operational_pause_at_finish": pause_at_finish,
        "summary_init_writes": summary_init_writes,
        **dict(totals),
        "failures": failures,
        "phase1_ready_count": ready_count,
        "phase1_remaining_count": remaining_count,
        "estimated_remaining_credits_mean_calibration": round(
            estimated_remaining_credits, 1
        ),
        "projected_remaining_b_days_mean_calibration": projected_days,
        "db_insert_and_state_write_seconds": round(write_seconds, 6),
        "phase2_lifetime_archival": False,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--expected-date", default=phoenix_date())
    parser.add_argument("--credit-cap", type=int, default=DAILY_B_CREDIT_CAP)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--preflight", action="store_true")
    mode.add_argument("--commit-phase1", action="store_true")
    args = parser.parse_args()

    from backend.db.clients.supabase_client import create_service_role_client

    db = create_service_role_client()
    if args.preflight:
        result = preflight(
            db,
            expected_date=args.expected_date,
            credit_cap=args.credit_cap,
        )
    else:
        credentials = load_pkmnprices_credentials(allow_frontend_fallback=False)
        result = run_phase1(
            db=db,
            provider=PkmnPricesClient(
                credentials.api_key, min_request_interval=0.55
            ),
            expected_date=args.expected_date,
            credit_cap=args.credit_cap,
        )

    print(json.dumps(result, indent=2, sort_keys=True, default=str))
    if result["status"] == "BLOCKED":
        return 3
    return 0 if result["status"] != "FAILED" else 2


if __name__ == "__main__":
    raise SystemExit(main())
