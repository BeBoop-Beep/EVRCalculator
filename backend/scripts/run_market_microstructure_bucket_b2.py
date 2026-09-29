"""Resume the ten Bucket B smoke cursors to calibrate sold-history tail depth."""
from __future__ import annotations

import argparse
import hashlib
import json
import time
import uuid
from collections import Counter
from datetime import datetime, timezone
from typing import Any, Callable

from backend.pricing_pipeline.pkmnprices_client import PkmnPricesClient
from backend.pricing_pipeline.pkmnprices_credentials import load_pkmnprices_credentials
from backend.pricing_pipeline.pkmnprices_store import PkmnPricesStore
from backend.scripts.run_market_microstructure_bucket_b import (
    COLLECTOR_VERSION, PANEL_FINGERPRINT, SELECTOR_VERSION, _normalize, load_panel,
)

SMOKE_RUN_ID = "5c951f67-135d-4665-bd5a-e8b733480aea"
CARD_COUNT = 10
ITEMS_PER_CARD = 80
SUBRUN_CREDIT_CAP = 1000
TOTAL_CREDIT_CAP = 3000
MAX_SLICES = 3
STOP_DRAINED = 3


def _cursor_hash(value: Any) -> str | None:
    return hashlib.sha256(str(value).encode()).hexdigest() if value else None


def validate_limits(*, slice_count: int, subrun_credit_cap: int,
                    items_per_card: int) -> None:
    if not 1 <= slice_count <= MAX_SLICES:
        raise ValueError("slice_count must be between 1 and 3")
    if not 1 <= subrun_credit_cap <= SUBRUN_CREDIT_CAP:
        raise ValueError("subrun_credit_cap must be between 1 and 1000")
    if not 1 <= items_per_card <= ITEMS_PER_CARD:
        raise ValueError("items_per_card must be between 1 and 80")
    if slice_count * subrun_credit_cap > TOTAL_CREDIT_CAP:
        raise ValueError("requested calibration exceeds 3000 credits")


def load_smoke_targets(db: Any) -> list[dict[str, Any]]:
    source = (db.table("pkmnprices_sold_runs_v1").select("run_id,status,manifest_fingerprint,metadata")
              .eq("run_id", SMOKE_RUN_ID).single().execute().data)
    if not source or source.get("status") != "COMPLETE":
        raise RuntimeError("BUCKET_B_SMOKE_RUN_NOT_COMPLETE")
    if source.get("manifest_fingerprint") != PANEL_FINGERPRINT:
        raise RuntimeError("BUCKET_B_SMOKE_FINGERPRINT_DRIFT")
    selected = list((source.get("metadata") or {}).get("preflight", {}).get("selected") or [])
    ids = [str(row.get("canonical_card_id")) for row in selected]
    if len(ids) != CARD_COUNT or len(set(ids)) != CARD_COUNT:
        raise RuntimeError("BUCKET_B_SMOKE_COHORT_INVALID")
    panel = {str(row["canonical_card_id"]): row for row in load_panel()["rows"]}
    if any(card_id not in panel for card_id in ids):
        raise RuntimeError("BUCKET_B_SMOKE_COHORT_NOT_IN_PANEL")
    return [panel[card_id] for card_id in ids]


def preflight(db: Any, *, slice_count: int, subrun_credit_cap: int,
              items_per_card: int) -> dict[str, Any]:
    validate_limits(slice_count=slice_count, subrun_credit_cap=subrun_credit_cap,
                    items_per_card=items_per_card)
    targets = load_smoke_targets(db)
    store = PkmnPricesStore(db)
    rows = []
    for target in targets:
        identity = store.get_identity_by_canonical(target["canonical_card_id"])
        if not identity or str(identity.get("tcgplayer_product_id")) != str(target["tcgplayer_product_id"]):
            raise RuntimeError("CALIBRATION_PROVIDER_IDENTITY_MISSING")
        sync = store.get_sync_state(int(identity["provider_card_id"]))
        metadata = dict((sync or {}).get("metadata") or {})
        in_progress = metadata.get("core_panel_backfill_in_progress") is True
        cursor = metadata.get("core_panel_backfill_cursor")
        if sync and sync.get("status") == "CURRENT" and metadata.get("core_panel_backfill_complete") is True:
            state = "DRAINED"
        elif sync and sync.get("status") == "PARTIAL" and in_progress and cursor:
            state = "RESUMABLE"
        else:
            raise RuntimeError("CALIBRATION_CURSOR_NOT_RESUMABLE")
        rows.append({"canonical_card_id": target["canonical_card_id"],
                     "provider_card_id": int(identity["provider_card_id"]),
                     "state": state, "cursor_hash": _cursor_hash(cursor),
                     "rows_seen": int((sync or {}).get("rows_seen") or 0),
                     "last_ingested_at": (sync or {}).get("last_ingested_at")})
    return {"status": "PREFLIGHT_OK", "source_run_id": SMOKE_RUN_ID,
            "panel_fingerprint": PANEL_FINGERPRINT, "target_count": len(rows),
            "resumable_count": sum(row["state"] == "RESUMABLE" for row in rows),
            "already_drained_count": sum(row["state"] == "DRAINED" for row in rows),
            "slice_count": slice_count, "subrun_credit_cap": subrun_credit_cap,
            "total_credit_cap": slice_count * subrun_credit_cap,
            "items_per_card": items_per_card, "targets": rows,
            "provider_requests": 0, "provider_credits_used": 0,
            "database_writes": 0, "breadth_backfill_started": False}


def _evidence_rows(db: Any, provider_card_id: int) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    start = 0
    while True:
        page = (db.table("pkmnprices_ebay_sold_evidence_v1")
                .select("provider_card_id,sold_at,graded,attribution")
                .eq("provider_card_id", provider_card_id)
                .order("sold_at").range(start, start + 999).execute().data or [])
        result.extend(dict(row) for row in page)
        if len(page) < 1000:
            return result
        start += 1000


def _cumulative(db: Any, provider_card_id: int) -> dict[str, Any]:
    rows = _evidence_rows(db, provider_card_id)
    dates = sorted(str(row["sold_at"])[:10] for row in rows)
    attributions = Counter(str(row.get("attribution") or "unknown") for row in rows)
    return {"persisted_transaction_count": len(rows),
            "history_start": dates[0] if dates else None,
            "history_end": dates[-1] if dates else None,
            "oldest_sold_at": dates[0] if dates else None,
            "raw_count": sum(not bool(row.get("graded")) for row in rows),
            "graded_count": sum(bool(row.get("graded")) for row in rows),
            "exact_count": attributions["exact"],
            "shared_count": attributions["shared"],
            "unknown_count": attributions["unknown"]}


def collect_slice(*, db: Any, provider: PkmnPricesClient,
                  subrun_credit_cap: int = SUBRUN_CREDIT_CAP,
                  items_per_card: int = ITEMS_PER_CARD,
                  slice_number: int = 1) -> dict[str, Any]:
    validate_limits(slice_count=1, subrun_credit_cap=subrun_credit_cap,
                    items_per_card=items_per_card)
    targets = load_smoke_targets(db)
    store = PkmnPricesStore(db)
    run_id = str(uuid.uuid4())
    started_at = datetime.now(timezone.utc).isoformat()
    metadata = {"mode": "bucket_b2_tail_calibration", "source_run_id": SMOKE_RUN_ID,
                "panel_fingerprint": PANEL_FINGERPRINT, "slice_number": slice_number,
                "items_per_card": items_per_card, "breadth_backfill": False}
    store.create_run({"run_id": run_id, "started_at": started_at, "finished_at": None,
        "status": "RUNNING", "selector_version": SELECTOR_VERSION,
        "collector_version": COLLECTOR_VERSION, "target_count": CARD_COUNT,
        "item_credit_cap": subrun_credit_cap, "api_request_count": 0, "credits_used": 0,
        "provider_card_lookup_count": 0, "sold_item_count": 0,
        "exact_attribution_count": 0, "fair_value_signal_eligible_count": 0,
        "set_value_nm_eligible_count": 0, "manifest_fingerprint": PANEL_FINGERPRINT,
        "metadata": metadata})
    totals = Counter()
    receipts: list[dict[str, Any]] = []
    failures: list[dict[str, Any]] = []
    write_seconds = 0.0
    for target in targets:
        identity = store.get_identity_by_canonical(target["canonical_card_id"])
        provider_id = int(identity["provider_card_id"]) if identity else 0
        sync = store.get_sync_state(provider_id) if provider_id else None
        sync_meta = dict((sync or {}).get("metadata") or {})
        if sync_meta.get("core_panel_backfill_complete") is True:
            totals["targets_skipped_drained"] += 1
            continue
        cursor = sync_meta.get("core_panel_backfill_cursor")
        if not (sync and sync.get("status") == "PARTIAL"
                and sync_meta.get("core_panel_backfill_in_progress") is True and cursor):
            failures.append({"canonical_card_id": target["canonical_card_id"],
                             "code": "CALIBRATION_CURSOR_NOT_RESUMABLE"})
            break
        remaining = subrun_credit_cap - provider.credits_charged
        if remaining <= 0:
            failures.append({"canonical_card_id": target["canonical_card_id"],
                             "code": "SUBRUN_CREDIT_CAP_REACHED"})
            break
        before_credits = provider.credits_charged
        before_cursor_hash = _cursor_hash(cursor)
        collection = provider.ebay_sold_collection(
            provider_id, graded=None, max_items=min(items_per_card, remaining),
            initial_cursor=str(cursor))
        collected_at = datetime.now(timezone.utc).isoformat()
        normalized = [_normalize(raw, target, provider_id, run_id, collected_at)
                      for raw in collection["rows"]]
        write_started = time.perf_counter()
        inserted, duplicates, drifts = store.insert_evidence(normalized)
        has_more = bool(collection["has_more"])
        observed_ingested = [row["ingested_at"] for row in normalized if row.get("ingested_at")]
        watermark = sync_meta.get("core_panel_incremental_watermark")
        if not watermark and observed_ingested:
            watermark = max(observed_ingested)
        last_ingested = sync.get("last_ingested_at")
        if not has_more and watermark:
            last_ingested = watermark
        old_rows_seen = int(sync.get("rows_seen") or 0)
        old_rows_inserted = int(sync.get("rows_inserted") or 0)
        store.upsert_sync_state({"provider_card_id": provider_id,
            "canonical_card_id": target["canonical_card_id"],
            "last_ingested_at": last_ingested,
            "last_sold_at": sync.get("last_sold_at"),
            "last_attempt_at": collected_at, "last_success_at": collected_at,
            "status": "PARTIAL" if has_more else "CURRENT", "consecutive_failures": 0,
            "rows_seen": old_rows_seen + len(normalized),
            "rows_inserted": old_rows_inserted + inserted, "last_error_code": None,
            "metadata": {**sync_meta, "core_panel_backfill_in_progress": has_more,
                "core_panel_backfill_complete": not has_more,
                "core_panel_backfill_cursor": collection["next_cursor"] if has_more else None,
                "core_panel_incremental_watermark": watermark}})
        write_seconds += time.perf_counter() - write_started
        cumulative = _cumulative(db, provider_id)
        receipt = {"canonical_card_id": target["canonical_card_id"],
            "provider_card_id": provider_id,
            "input_cursor_hash": before_cursor_hash,
            "output_cursor_hash": _cursor_hash(collection["next_cursor"]),
            "cursor_continuation_proven": before_cursor_hash is not None,
            "newly_purchased_rows": len(normalized), "newly_inserted_rows": inserted,
            "duplicates": duplicates, "provider_metadata_drifts": drifts,
            "has_more": has_more, "drained": not has_more,
            "credits": provider.credits_charged - before_credits, **cumulative}
        receipts.append(receipt)
        totals.update({"targets_completed": 1, "sold_item_count": len(normalized),
            "inserted": inserted, "duplicates": duplicates,
            "provider_metadata_drifts": drifts,
            "exact_attribution_count": sum(row["attribution"] == "exact" for row in normalized),
            "fair_value_signal_eligible_count": sum(bool(row["fair_value_signal_eligible"]) for row in normalized),
            "drained_this_slice": int(not has_more)})
    status = "COMPLETE" if not failures else ("PARTIAL" if receipts else "FAILED")
    finished_at = datetime.now(timezone.utc).isoformat()
    final_metadata = {**metadata, "receipts": receipts, "failures": failures,
                      "db_insert_and_state_write_seconds": round(write_seconds, 6)}
    store.update_run(run_id, {"finished_at": finished_at, "status": status,
        "api_request_count": provider.request_attempt_count,
        "credits_used": min(provider.credits_charged, subrun_credit_cap),
        "provider_card_lookup_count": 0, "sold_item_count": totals["sold_item_count"],
        "exact_attribution_count": totals["exact_attribution_count"],
        "fair_value_signal_eligible_count": totals["fair_value_signal_eligible_count"],
        "set_value_nm_eligible_count": 0,
        "error_code": failures[0]["code"] if failures else None,
        "metadata": final_metadata})
    return {"run_id": run_id, "slice_number": slice_number, "status": status,
            "credits_used": provider.credits_charged, "credit_cap": subrun_credit_cap,
            "db_insert_and_state_write_seconds": round(write_seconds, 6),
            **dict(totals), "receipts": receipts, "failures": failures,
            "breadth_backfill_started": False}


def calibrate(*, db: Any, provider_factory: Callable[[], PkmnPricesClient],
              slice_count: int, subrun_credit_cap: int,
              items_per_card: int) -> dict[str, Any]:
    plan = preflight(db, slice_count=slice_count,
                     subrun_credit_cap=subrun_credit_cap,
                     items_per_card=items_per_card)
    slices = []
    total_credits = 0
    drained = plan["already_drained_count"]
    for number in range(1, slice_count + 1):
        if drained >= STOP_DRAINED:
            break
        result = collect_slice(db=db, provider=provider_factory(),
                               subrun_credit_cap=subrun_credit_cap,
                               items_per_card=items_per_card, slice_number=number)
        slices.append(result)
        total_credits += int(result["credits_used"])
        drained += int(result.get("drained_this_slice") or 0)
        if total_credits > TOTAL_CREDIT_CAP:
            raise RuntimeError("CALIBRATION_TOTAL_CREDIT_CAP_EXCEEDED")
        if result["status"] == "FAILED":
            break
    return {"status": "COMPLETE" if slices and all(x["status"] == "COMPLETE" for x in slices) else "PARTIAL",
            "preflight": plan, "slices_executed": len(slices),
            "total_credits_used": total_credits, "total_credit_cap": TOTAL_CREDIT_CAP,
            "drained_count": drained, "stopped_for_drain_threshold": drained >= STOP_DRAINED,
            "slices": slices, "breadth_backfill_started": False}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--slice-count", type=int, default=3)
    parser.add_argument("--subrun-credit-cap", type=int, default=1000)
    parser.add_argument("--items-per-card", type=int, default=80)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--preflight", action="store_true")
    mode.add_argument("--commit-calibration", action="store_true")
    args = parser.parse_args()
    from backend.db.clients.supabase_client import create_service_role_client
    db = create_service_role_client()
    if args.preflight:
        result = preflight(db, slice_count=args.slice_count,
                           subrun_credit_cap=args.subrun_credit_cap,
                           items_per_card=args.items_per_card)
    else:
        credentials = load_pkmnprices_credentials(allow_frontend_fallback=False)
        result = calibrate(db=db,
            provider_factory=lambda: PkmnPricesClient(credentials.api_key, min_request_interval=1.1),
            slice_count=args.slice_count, subrun_credit_cap=args.subrun_credit_cap,
            items_per_card=args.items_per_card)
    print(json.dumps(result, indent=2, sort_keys=True, default=str))
    return 0 if result["status"] != "FAILED" else 2


if __name__ == "__main__":
    raise SystemExit(main())
