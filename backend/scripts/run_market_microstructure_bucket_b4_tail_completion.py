"""Finish the single remaining Core Panel Phase-1 tail safely.

This is a one-card, one-time continuation of Bucket B4. It resumes the exact
stored cursor for the frozen outlier and stops immediately on:
- provider exhaustion, or
- the frozen 180-day horizon, or
- the 3,000-credit hard ceiling, or
- any operational pause (scraper/C/publication safety remains authoritative).
"""
from __future__ import annotations

import argparse
import json
import uuid
from datetime import datetime, timezone
from typing import Any

from backend.pricing_pipeline.pkmnprices_client import PkmnPricesClient
from backend.pricing_pipeline.pkmnprices_credentials import load_pkmnprices_credentials
from backend.pricing_pipeline.pkmnprices_store import PkmnPricesStore
from backend.scripts.run_market_microstructure_bucket_b import (
    COLLECTOR_VERSION,
    PANEL_FINGERPRINT,
    _normalize,
    load_panel,
)
from backend.scripts.run_market_microstructure_bucket_b4 import (
    HORIZON_CUTOFF,
    PAGE_SIZE,
    REFERENCE_DATE,
    _horizon_ready,
    _update_sync_after_page,
    operational_pause_reason,
    phoenix_date,
)

CANONICAL_CARD_ID = "ad79530b-263d-45bd-be6a-6c0dc17e682d"
PROVIDER_CARD_ID = 76774
TCGPLAYER_PRODUCT_ID = "693517"
CREDIT_CAP = 3000
MODE = "bucket_b4_tail_completion_180d"
SELECTOR_VERSION = "market_microstructure_core_panel_tail_completion_v1"


def _target() -> dict[str, Any]:
    matches = [
        row for row in load_panel()["rows"]
        if str(row["canonical_card_id"]) == CANONICAL_CARD_ID
    ]
    if len(matches) != 1:
        raise RuntimeError("TAIL_TARGET_NOT_EXACTLY_ONE")
    target = matches[0]
    if str(target["tcgplayer_product_id"]) != TCGPLAYER_PRODUCT_ID:
        raise RuntimeError("TAIL_TARGET_TCGPLAYER_ID_DRIFT")
    return target


def preflight(db: Any) -> dict[str, Any]:
    store = PkmnPricesStore(db)
    target = _target()
    identity = store.get_identity_by_canonical(CANONICAL_CARD_ID)
    if not identity or int(identity["provider_card_id"]) != PROVIDER_CARD_ID:
        raise RuntimeError("TAIL_PROVIDER_IDENTITY_DRIFT")
    sync = store.get_sync_state(PROVIDER_CARD_ID)
    if not sync:
        raise RuntimeError("TAIL_SYNC_STATE_MISSING")
    meta = dict(sync.get("metadata") or {})
    ready = bool(meta.get("phase1_ready"))
    cursor = meta.get("core_panel_backfill_cursor")
    if not ready and not (
        sync.get("status") == "PARTIAL"
        and meta.get("core_panel_backfill_in_progress") is True
        and cursor
    ):
        raise RuntimeError("TAIL_CURSOR_NOT_RESUMABLE")
    return {
        "status": "PREFLIGHT_OK",
        "panel_fingerprint": PANEL_FINGERPRINT,
        "canonical_card_id": CANONICAL_CARD_ID,
        "provider_card_id": PROVIDER_CARD_ID,
        "tcgplayer_product_id": TCGPLAYER_PRODUCT_ID,
        "rows_seen": int(sync.get("rows_seen") or 0),
        "oldest_sold_at": meta.get("phase1_oldest_sold_at"),
        "phase1_ready": ready,
        "phase1_ready_reason": meta.get("phase1_ready_reason"),
        "cursor_present": bool(cursor),
        "reference_date": REFERENCE_DATE.isoformat(),
        "horizon_cutoff": HORIZON_CUTOFF.isoformat(),
        "credit_cap": CREDIT_CAP,
        "operational_pause": operational_pause_reason(db),
        "provider_requests": 0,
        "provider_credits_used": 0,
        "database_writes": 0,
    }


def run(db: Any, provider: PkmnPricesClient) -> dict[str, Any]:
    plan = preflight(db)
    if plan["phase1_ready"]:
        return {**plan, "status": "ALREADY_READY"}
    if plan["operational_pause"]:
        return {
            **plan,
            "status": "BLOCKED",
            "reason": plan["operational_pause"]["reason"],
        }

    store = PkmnPricesStore(db)
    target = _target()
    run_id = str(uuid.uuid4())
    started_at = datetime.now(timezone.utc).isoformat()
    store.create_run({
        "run_id": run_id,
        "started_at": started_at,
        "finished_at": None,
        "status": "RUNNING",
        "selector_version": SELECTOR_VERSION,
        "collector_version": COLLECTOR_VERSION,
        "target_count": 1,
        "item_credit_cap": CREDIT_CAP,
        "api_request_count": 0,
        "credits_used": 0,
        "provider_card_lookup_count": 0,
        "sold_item_count": 0,
        "exact_attribution_count": 0,
        "fair_value_signal_eligible_count": 0,
        "set_value_nm_eligible_count": 0,
        "manifest_fingerprint": PANEL_FINGERPRINT,
        "metadata": {
            "mode": MODE,
            "panel_fingerprint": PANEL_FINGERPRINT,
            "canonical_card_id": CANONICAL_CARD_ID,
            "provider_card_id": PROVIDER_CARD_ID,
            "reference_date": REFERENCE_DATE.isoformat(),
            "horizon_cutoff": HORIZON_CUTOFF.isoformat(),
            "page_size": PAGE_SIZE,
            "phase2_lifetime_archival": False,
        },
    })

    sold_rows = inserted_total = duplicates_total = drifts_total = 0
    pages = 0
    ready = False
    ready_reason = None
    pause = None

    while provider.credits_charged < CREDIT_CAP and not ready:
        pause = operational_pause_reason(db)
        if pause:
            break

        sync = store.get_sync_state(PROVIDER_CARD_ID)
        if not sync:
            raise RuntimeError("TAIL_SYNC_STATE_DISAPPEARED")
        meta = dict(sync.get("metadata") or {})
        if bool(meta.get("phase1_ready")):
            ready = True
            ready_reason = meta.get("phase1_ready_reason")
            break
        cursor = meta.get("core_panel_backfill_cursor")
        if not cursor:
            raise RuntimeError("TAIL_CURSOR_DISAPPEARED")

        requested = min(PAGE_SIZE, CREDIT_CAP - provider.credits_charged)
        payload = provider.ebay_sold_page(
            PROVIDER_CARD_ID,
            graded=None,
            sort="date_desc",
            limit=requested,
            cursor=str(cursor),
        )
        data = payload.get("data") or []
        raw_rows = [dict(row) for row in data if isinstance(row, dict)]
        page = payload.get("pagination") or {}
        has_more = bool(page.get("has_more"))
        next_value = page.get("next_cursor")
        next_cursor = str(next_value) if next_value else None
        if has_more and (not next_cursor or next_cursor == str(cursor)):
            raise RuntimeError("TAIL_PAGINATION_CURSOR_DID_NOT_ADVANCE")

        collected_at = datetime.now(timezone.utc).isoformat()
        normalized = [
            _normalize(raw, target, PROVIDER_CARD_ID, run_id, collected_at)
            for raw in raw_rows
        ]
        page_oldest = min(
            [str(row["sold_at"])[:10] for row in normalized if row.get("sold_at")],
            default=None,
        )
        oldest = meta.get("phase1_oldest_sold_at")
        if page_oldest and (oldest is None or page_oldest < oldest):
            oldest = page_oldest

        inserted, duplicates, drifts = store.insert_evidence(normalized)
        ready, ready_reason = _update_sync_after_page(
            store=store,
            target=target,
            provider_card_id=PROVIDER_CARD_ID,
            previous_sync=sync,
            previous_meta=meta,
            normalized=normalized,
            has_more=has_more,
            next_cursor=next_cursor,
            collected_at=collected_at,
            inserted=inserted,
            oldest_sold_at=oldest,
            expected_date=phoenix_date(),
        )
        sold_rows += len(normalized)
        inserted_total += inserted
        duplicates_total += duplicates
        drifts_total += drifts
        pages += 1
        if not has_more:
            ready, ready_reason = _horizon_ready(oldest, drained=True)

    final_sync = store.get_sync_state(PROVIDER_CARD_ID)
    final_meta = dict((final_sync or {}).get("metadata") or {})
    final_ready = bool(final_meta.get("phase1_ready"))
    final_reason = final_meta.get("phase1_ready_reason")
    status = "COMPLETE" if final_ready else ("PAUSED" if pause else "CAP_REACHED")
    finished_at = datetime.now(timezone.utc).isoformat()

    store.update_run(run_id, {
        "finished_at": finished_at,
        "status": "COMPLETE" if final_ready else "PARTIAL",
        "api_request_count": provider.request_attempt_count,
        "credits_used": provider.credits_charged,
        "provider_card_lookup_count": 0,
        "sold_item_count": sold_rows,
        "exact_attribution_count": 0,
        "fair_value_signal_eligible_count": 0,
        "set_value_nm_eligible_count": 0,
        "error_code": None,
        "metadata": {
            "mode": MODE,
            "panel_fingerprint": PANEL_FINGERPRINT,
            "canonical_card_id": CANONICAL_CARD_ID,
            "provider_card_id": PROVIDER_CARD_ID,
            "reference_date": REFERENCE_DATE.isoformat(),
            "horizon_cutoff": HORIZON_CUTOFF.isoformat(),
            "page_size": PAGE_SIZE,
            "phase2_lifetime_archival": False,
            "pages": pages,
            "inserted": inserted_total,
            "duplicates": duplicates_total,
            "provider_metadata_drifts": drifts_total,
            "phase1_ready": final_ready,
            "phase1_ready_reason": final_reason,
            "rows_seen": int((final_sync or {}).get("rows_seen") or 0),
            "oldest_sold_at": final_meta.get("phase1_oldest_sold_at"),
            "pause": pause,
        },
    })

    return {
        "status": status,
        "run_id": run_id,
        "credits_used": provider.credits_charged,
        "credit_cap": CREDIT_CAP,
        "pages": pages,
        "sold_rows": sold_rows,
        "inserted": inserted_total,
        "duplicates": duplicates_total,
        "provider_metadata_drifts": drifts_total,
        "rows_seen": int((final_sync or {}).get("rows_seen") or 0),
        "oldest_sold_at": final_meta.get("phase1_oldest_sold_at"),
        "phase1_ready": final_ready,
        "phase1_ready_reason": final_reason,
        "pause": pause,
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
    return 0 if result["status"] not in {"BLOCKED"} else 3


if __name__ == "__main__":
    raise SystemExit(main())
