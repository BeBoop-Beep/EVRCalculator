"""Calibrate the 180-day sold-history horizon for the six high-liquidity B2 tails.

This runner is intentionally narrow:
- exactly the six preregistered B2 provider identities;
- resumes existing combined-stream cursors only;
- buys at most 80 rows/card/pass in 20-row pages;
- stops a card immediately after the first page that reaches the 180-day horizon
  or exhausts provider-retained history;
- never starts the 207-card breadth backfill;
- hard total provider-credit ceiling: 3,000.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import statistics
import time
import uuid
from collections import Counter
from datetime import date, datetime, timedelta, timezone
from typing import Any, Callable

from backend.pricing_pipeline.pkmnprices_client import (
    PkmnPricesAPIError,
    PkmnPricesClient,
)
from backend.pricing_pipeline.pkmnprices_credentials import load_pkmnprices_credentials
from backend.pricing_pipeline.pkmnprices_store import PkmnPricesStore
from backend.scripts.run_market_microstructure_bucket_b import (
    COLLECTOR_VERSION,
    PANEL_FINGERPRINT,
    SELECTOR_VERSION,
    _normalize,
)
from backend.scripts.run_market_microstructure_bucket_b2 import (
    _cumulative,
    _cursor_hash,
    load_smoke_targets,
)

REFERENCE_DATE = date(2026, 9, 29)
HORIZON_DAYS = 180
HORIZON_CUTOFF = REFERENCE_DATE - timedelta(days=HORIZON_DAYS)
EXPECTED_PROVIDER_IDS = {14359, 24546, 24626, 31828, 34083, 114847}
TARGET_COUNT = 6
PAGE_SIZE = 20
MAX_ROWS_PER_CARD_PASS = 80
MAX_PASSES = 5
TOTAL_CREDIT_CAP = 3000


def _days_to_reference(oldest_sold_at: str | None) -> int | None:
    if not oldest_sold_at:
        return None
    return (REFERENCE_DATE - date.fromisoformat(str(oldest_sold_at)[:10])).days


def _is_horizon_ready(*, oldest_sold_at: str | None, drained: bool) -> bool:
    if drained:
        return True
    return bool(oldest_sold_at and date.fromisoformat(str(oldest_sold_at)[:10]) <= HORIZON_CUTOFF)


def _state(db: Any, store: PkmnPricesStore, target: dict[str, Any]) -> dict[str, Any]:
    identity = store.get_identity_by_canonical(target["canonical_card_id"])
    if not identity or str(identity.get("tcgplayer_product_id")) != str(target["tcgplayer_product_id"]):
        raise RuntimeError("BUCKET_B3_PROVIDER_IDENTITY_MISSING")
    provider_id = int(identity["provider_card_id"])
    if provider_id not in EXPECTED_PROVIDER_IDS:
        raise RuntimeError("BUCKET_B3_UNEXPECTED_PROVIDER_ID")
    sync = store.get_sync_state(provider_id)
    if not sync:
        raise RuntimeError("BUCKET_B3_SYNC_STATE_MISSING")
    meta = dict(sync.get("metadata") or {})
    drained = bool(
        sync.get("status") == "CURRENT"
        and meta.get("core_panel_backfill_complete") is True
    )
    if not drained:
        if not (
            sync.get("status") == "PARTIAL"
            and meta.get("core_panel_backfill_in_progress") is True
            and meta.get("core_panel_backfill_cursor")
        ):
            raise RuntimeError("BUCKET_B3_CURSOR_NOT_RESUMABLE")
    cumulative = _cumulative(db, provider_id)
    ready = _is_horizon_ready(
        oldest_sold_at=cumulative.get("oldest_sold_at"),
        drained=drained,
    )
    return {
        "target": target,
        "identity": identity,
        "sync": sync,
        "sync_meta": meta,
        "provider_card_id": provider_id,
        "drained": drained,
        "horizon_ready": ready,
        "history_days_to_reference": _days_to_reference(cumulative.get("oldest_sold_at")),
        **cumulative,
    }


def load_targets(db: Any) -> list[dict[str, Any]]:
    store = PkmnPricesStore(db)
    candidates: list[dict[str, Any]] = []
    for target in load_smoke_targets(db):
        identity = store.get_identity_by_canonical(target["canonical_card_id"])
        if identity and int(identity["provider_card_id"]) in EXPECTED_PROVIDER_IDS:
            candidates.append(target)
    provider_ids = {
        int(store.get_identity_by_canonical(row["canonical_card_id"])["provider_card_id"])
        for row in candidates
    }
    if provider_ids != EXPECTED_PROVIDER_IDS or len(candidates) != TARGET_COUNT:
        raise RuntimeError("BUCKET_B3_TARGET_COHORT_DRIFT")
    return sorted(
        candidates,
        key=lambda row: int(
            store.get_identity_by_canonical(row["canonical_card_id"])["provider_card_id"]
        ),
    )


def preflight(db: Any, *, pass_count: int, total_credit_cap: int) -> dict[str, Any]:
    if not 1 <= pass_count <= MAX_PASSES:
        raise ValueError("pass_count must be between 1 and 5")
    if not 1 <= total_credit_cap <= TOTAL_CREDIT_CAP:
        raise ValueError("total_credit_cap must be between 1 and 3000")
    targets = load_targets(db)
    store = PkmnPricesStore(db)
    states = [_state(db, store, target) for target in targets]
    return {
        "status": "PREFLIGHT_OK",
        "panel_fingerprint": PANEL_FINGERPRINT,
        "reference_date": REFERENCE_DATE.isoformat(),
        "horizon_days": HORIZON_DAYS,
        "horizon_cutoff": HORIZON_CUTOFF.isoformat(),
        "target_count": TARGET_COUNT,
        "expected_provider_ids": sorted(EXPECTED_PROVIDER_IDS),
        "pass_count": pass_count,
        "page_size": PAGE_SIZE,
        "max_rows_per_card_pass": MAX_ROWS_PER_CARD_PASS,
        "total_credit_cap": total_credit_cap,
        "provider_requests": 0,
        "provider_credits_used": 0,
        "database_writes": 0,
        "breadth_backfill_started": False,
        "targets": [
            {
                "provider_card_id": row["provider_card_id"],
                "canonical_card_id": row["target"]["canonical_card_id"],
                "persisted_transaction_count": row["persisted_transaction_count"],
                "oldest_sold_at": row["oldest_sold_at"],
                "history_days_to_reference": row["history_days_to_reference"],
                "drained": row["drained"],
                "horizon_ready": row["horizon_ready"],
                "cursor_hash": _cursor_hash(
                    row["sync_meta"].get("core_panel_backfill_cursor")
                ),
                "last_ingested_at": row["sync"].get("last_ingested_at"),
            }
            for row in states
        ],
    }


def _update_sync_after_page(
    *,
    store: PkmnPricesStore,
    state: dict[str, Any],
    normalized: list[dict[str, Any]],
    has_more: bool,
    next_cursor: str | None,
    collected_at: str,
    inserted: int,
) -> None:
    sync = state["sync"]
    meta = dict(state["sync_meta"])
    observed_ingested = [
        row["ingested_at"] for row in normalized if row.get("ingested_at")
    ]
    watermark = meta.get("core_panel_incremental_watermark")
    if not watermark and observed_ingested:
        watermark = max(observed_ingested)
    last_ingested = sync.get("last_ingested_at")
    if not has_more and watermark:
        last_ingested = watermark
    store.upsert_sync_state({
        "provider_card_id": state["provider_card_id"],
        "canonical_card_id": state["target"]["canonical_card_id"],
        "last_ingested_at": last_ingested,
        "last_sold_at": sync.get("last_sold_at"),
        "last_attempt_at": collected_at,
        "last_success_at": collected_at,
        "status": "PARTIAL" if has_more else "CURRENT",
        "consecutive_failures": 0,
        "rows_seen": int(sync.get("rows_seen") or 0) + len(normalized),
        "rows_inserted": int(sync.get("rows_inserted") or 0) + inserted,
        "last_error_code": None,
        "metadata": {
            **meta,
            "core_panel_backfill_in_progress": has_more,
            "core_panel_backfill_complete": not has_more,
            "core_panel_backfill_cursor": next_cursor if has_more else None,
            "core_panel_incremental_watermark": watermark,
        },
    })


def collect_pass(
    *,
    db: Any,
    provider: PkmnPricesClient,
    pass_number: int,
    total_credit_cap: int,
) -> dict[str, Any]:
    targets = load_targets(db)
    store = PkmnPricesStore(db)
    run_id = str(uuid.uuid4())
    started = datetime.now(timezone.utc).isoformat()
    start_credits = provider.credits_charged
    metadata = {
        "mode": "bucket_b3_180d_horizon_calibration",
        "panel_fingerprint": PANEL_FINGERPRINT,
        "reference_date": REFERENCE_DATE.isoformat(),
        "horizon_days": HORIZON_DAYS,
        "horizon_cutoff": HORIZON_CUTOFF.isoformat(),
        "pass_number": pass_number,
        "page_size": PAGE_SIZE,
        "max_rows_per_card_pass": MAX_ROWS_PER_CARD_PASS,
        "breadth_backfill": False,
    }
    store.create_run({
        "run_id": run_id,
        "started_at": started,
        "finished_at": None,
        "status": "RUNNING",
        "selector_version": SELECTOR_VERSION,
        "collector_version": COLLECTOR_VERSION,
        "target_count": TARGET_COUNT,
        "item_credit_cap": max(0, total_credit_cap - start_credits),
        "api_request_count": 0,
        "credits_used": 0,
        "provider_card_lookup_count": 0,
        "sold_item_count": 0,
        "exact_attribution_count": 0,
        "fair_value_signal_eligible_count": 0,
        "set_value_nm_eligible_count": 0,
        "manifest_fingerprint": PANEL_FINGERPRINT,
        "metadata": metadata,
    })

    totals = Counter()
    receipts: list[dict[str, Any]] = []
    failures: list[dict[str, Any]] = []
    write_seconds = 0.0

    for target in targets:
        state = _state(db, store, target)
        if state["horizon_ready"]:
            totals["targets_skipped_ready"] += 1
            receipts.append({
                "provider_card_id": state["provider_card_id"],
                "canonical_card_id": target["canonical_card_id"],
                "state_before": "DRAINED" if state["drained"] else "HORIZON_READY",
                "newly_purchased_rows": 0,
                "credits": 0,
                "persisted_transaction_count": state["persisted_transaction_count"],
                "oldest_sold_at": state["oldest_sold_at"],
                "history_days_to_reference": state["history_days_to_reference"],
                "drained": state["drained"],
                "horizon_ready": True,
            })
            continue

        rows_this_pass = 0
        page_receipts: list[dict[str, Any]] = []
        while rows_this_pass < MAX_ROWS_PER_CARD_PASS:
            if provider.credits_charged >= total_credit_cap:
                failures.append({
                    "provider_card_id": state["provider_card_id"],
                    "canonical_card_id": target["canonical_card_id"],
                    "code": "TOTAL_CREDIT_CAP_REACHED",
                })
                break

            # Refresh after every persisted page so the next request always starts
            # from the durable cursor we just committed.
            state = _state(db, store, target)
            if state["horizon_ready"]:
                break
            cursor = state["sync_meta"].get("core_panel_backfill_cursor")
            if not cursor:
                failures.append({
                    "provider_card_id": state["provider_card_id"],
                    "canonical_card_id": target["canonical_card_id"],
                    "code": "BUCKET_B3_CURSOR_NOT_RESUMABLE",
                })
                break

            remaining_total = total_credit_cap - provider.credits_charged
            remaining_card = MAX_ROWS_PER_CARD_PASS - rows_this_pass
            limit = min(PAGE_SIZE, remaining_total, remaining_card)
            if limit <= 0:
                break

            before_credits = provider.credits_charged
            before_cursor_hash = _cursor_hash(cursor)
            payload = provider.ebay_sold_page(
                state["provider_card_id"],
                graded=None,
                sort="date_desc",
                limit=limit,
                cursor=str(cursor),
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
            if has_more and (not next_cursor or next_cursor == str(cursor)):
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
                    state["provider_card_id"],
                    run_id,
                    collected_at,
                )
                for raw in raw_rows
            ]
            write_started = time.perf_counter()
            inserted, duplicates, drifts = store.insert_evidence(normalized)
            _update_sync_after_page(
                store=store,
                state=state,
                normalized=normalized,
                has_more=has_more,
                next_cursor=next_cursor,
                collected_at=collected_at,
                inserted=inserted,
            )
            write_seconds += time.perf_counter() - write_started
            rows_this_pass += len(normalized)
            cumulative = _cumulative(db, state["provider_card_id"])
            drained = not has_more
            ready = _is_horizon_ready(
                oldest_sold_at=cumulative.get("oldest_sold_at"),
                drained=drained,
            )
            days = _days_to_reference(cumulative.get("oldest_sold_at"))
            page_receipts.append({
                "input_cursor_hash": before_cursor_hash,
                "output_cursor_hash": _cursor_hash(next_cursor),
                "rows_seen": len(normalized),
                "rows_inserted": inserted,
                "duplicates": duplicates,
                "provider_metadata_drifts": drifts,
                "credits": provider.credits_charged - before_credits,
                "has_more": has_more,
                "drained": drained,
                "oldest_sold_at": cumulative.get("oldest_sold_at"),
                "history_days_to_reference": days,
                "horizon_ready": ready,
            })
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

            # This is the key B3 cost-control rule: stop on the first page that
            # crosses 180 days instead of buying the remainder of the 80-row layer.
            if ready:
                break

        final_state = _state(db, store, target)
        receipts.append({
            "provider_card_id": final_state["provider_card_id"],
            "canonical_card_id": target["canonical_card_id"],
            "newly_purchased_rows": sum(
                int(page.get("rows_seen") or 0) for page in page_receipts
            ),
            "credits": sum(int(page.get("credits") or 0) for page in page_receipts),
            "pages": page_receipts,
            "persisted_transaction_count": final_state["persisted_transaction_count"],
            "oldest_sold_at": final_state["oldest_sold_at"],
            "history_days_to_reference": final_state["history_days_to_reference"],
            "raw_count": final_state["raw_count"],
            "graded_count": final_state["graded_count"],
            "exact_count": final_state["exact_count"],
            "shared_count": final_state["shared_count"],
            "unknown_count": final_state["unknown_count"],
            "drained": final_state["drained"],
            "horizon_ready": final_state["horizon_ready"],
        })
        totals["targets_completed"] += 1

        if provider.credits_charged >= total_credit_cap:
            break

    pass_credits = provider.credits_charged - start_credits
    status = "COMPLETE" if not failures else ("PARTIAL" if receipts else "FAILED")
    finished = datetime.now(timezone.utc).isoformat()
    store.update_run(run_id, {
        "finished_at": finished,
        "status": status,
        "api_request_count": provider.request_attempt_count,
        "credits_used": pass_credits,
        "provider_card_lookup_count": 0,
        "sold_item_count": totals["sold_item_count"],
        "exact_attribution_count": totals["exact_attribution_count"],
        "fair_value_signal_eligible_count": totals["fair_value_signal_eligible_count"],
        "set_value_nm_eligible_count": 0,
        "error_code": failures[0]["code"] if failures else None,
        "metadata": {
            **metadata,
            "receipts": receipts,
            "failures": failures,
            "db_insert_and_state_write_seconds": round(write_seconds, 6),
        },
    })
    return {
        "run_id": run_id,
        "pass_number": pass_number,
        "status": status,
        "credits_used": pass_credits,
        "cumulative_provider_credits": provider.credits_charged,
        "db_insert_and_state_write_seconds": round(write_seconds, 6),
        **dict(totals),
        "receipts": receipts,
        "failures": failures,
        "breadth_backfill_started": False,
    }


def _percentile(values: list[int], p: float) -> float | None:
    if not values:
        return None
    if len(values) == 1:
        return float(values[0])
    ordered = sorted(values)
    position = (len(ordered) - 1) * p
    lower = int(position)
    upper = min(lower + 1, len(ordered) - 1)
    fraction = position - lower
    return ordered[lower] + (ordered[upper] - ordered[lower]) * fraction


def calibrate(
    *,
    db: Any,
    provider_factory: Callable[[], PkmnPricesClient],
    pass_count: int,
    total_credit_cap: int,
) -> dict[str, Any]:
    plan = preflight(
        db, pass_count=pass_count, total_credit_cap=total_credit_cap
    )
    provider = provider_factory()
    passes: list[dict[str, Any]] = []
    for number in range(1, pass_count + 1):
        states = [
            _state(db, PkmnPricesStore(db), target)
            for target in load_targets(db)
        ]
        if all(row["horizon_ready"] for row in states):
            break
        if provider.credits_charged >= total_credit_cap:
            break
        result = collect_pass(
            db=db,
            provider=provider,
            pass_number=number,
            total_credit_cap=total_credit_cap,
        )
        passes.append(result)
        if result["status"] == "FAILED":
            break

    final_store = PkmnPricesStore(db)
    final_states = [
        _state(db, final_store, target) for target in load_targets(db)
    ]
    reached = [
        int(row["persisted_transaction_count"])
        for row in final_states
        if row["horizon_ready"]
    ]
    unresolved = [
        int(row["persisted_transaction_count"])
        for row in final_states
        if not row["horizon_ready"]
    ]
    return {
        "status": "COMPLETE",
        "preflight": plan,
        "passes_executed": len(passes),
        "total_credits_used": provider.credits_charged,
        "total_credit_cap": total_credit_cap,
        "horizon_ready_count": sum(row["horizon_ready"] for row in final_states),
        "drained_count": sum(row["drained"] for row in final_states),
        "still_open_below_horizon_count": sum(
            not row["horizon_ready"] for row in final_states
        ),
        "rows_required_observed": reached,
        "rows_required_median": (
            float(statistics.median(reached)) if reached else None
        ),
        "rows_required_p75": _percentile(reached, 0.75),
        "rows_required_max": max(reached) if reached else None,
        "unresolved_row_lower_bounds": unresolved,
        "final_states": [
            {
                "provider_card_id": row["provider_card_id"],
                "canonical_card_id": row["target"]["canonical_card_id"],
                "persisted_transaction_count": row["persisted_transaction_count"],
                "oldest_sold_at": row["oldest_sold_at"],
                "history_days_to_reference": row["history_days_to_reference"],
                "raw_count": row["raw_count"],
                "graded_count": row["graded_count"],
                "exact_count": row["exact_count"],
                "shared_count": row["shared_count"],
                "unknown_count": row["unknown_count"],
                "drained": row["drained"],
                "horizon_ready": row["horizon_ready"],
            }
            for row in final_states
        ],
        "passes": passes,
        "breadth_backfill_started": False,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pass-count", type=int, default=MAX_PASSES)
    parser.add_argument("--total-credit-cap", type=int, default=TOTAL_CREDIT_CAP)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--preflight", action="store_true")
    mode.add_argument("--commit-calibration", action="store_true")
    args = parser.parse_args()

    from backend.db.clients.supabase_client import create_service_role_client

    db = create_service_role_client()
    if args.preflight:
        result = preflight(
            db,
            pass_count=args.pass_count,
            total_credit_cap=args.total_credit_cap,
        )
    else:
        credentials = load_pkmnprices_credentials(allow_frontend_fallback=False)
        result = calibrate(
            db=db,
            provider_factory=lambda: PkmnPricesClient(
                credentials.api_key, min_request_interval=1.1
            ),
            pass_count=args.pass_count,
            total_credit_cap=args.total_credit_cap,
        )

    print(json.dumps(result, indent=2, sort_keys=True, default=str))
    return 0 if result["status"] != "FAILED" else 2


if __name__ == "__main__":
    raise SystemExit(main())
