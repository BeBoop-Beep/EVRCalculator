"""Collect bounded PkmnPrices eBay sold evidence for unresolved vintage price gaps.

This is a shadow evidence pipeline. It never writes canonical TCGPlayer prices,
Set Value, or public Market Explorer values.

Primary use cases:
  1. Build transaction evidence for inDex Fair Value research.
  2. Diagnose vintage edition price gaps with exact physical-variant attribution.

PkmnPrices sold rows do not expose raw-card condition, so this collector keeps
set_value_nm_eligible=false for every row by construction.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import uuid
from datetime import datetime, timezone
from typing import Any

from backend.db.clients.supabase_client import create_service_role_client
from backend.pricing_pipeline.pkmnprices_client import PkmnPricesClient
from backend.pricing_pipeline.pkmnprices_credentials import load_pkmnprices_credentials
from backend.pricing_pipeline.pkmnprices_sold import normalize_sold_listing
from backend.pricing_pipeline.pkmnprices_sold_identity import (
    MATCHER_VERSION as SOLD_IDENTITY_MATCHER_VERSION,
    classify_vintage_sold,
)
from backend.pricing_pipeline.pkmnprices_store import PkmnPricesStore
from backend.pricing_pipeline.pkmnprices_targets import (
    discover_vintage_gap_rows,
    latest_approved_market_date,
    resolve_targets,
)

SELECTOR_VERSION = "pkmnprices_vintage_gap_selector_v1"
COLLECTOR_VERSION = "pkmnprices_ebay_sold_collector_v1"


def _fingerprint(value: Any) -> str:
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":"), default=str).encode()
    ).hexdigest()


def _provider_identity_rows(client: PkmnPricesClient, target: dict[str, Any]) -> list[dict[str, Any]]:
    rows = client.cards_by_tcgplayer_id(
        target["tcgplayer_product_id"], language="English", per_page=5
    )
    exact = [
        row for row in rows
        if str(row.get("tcg_player_id") or "") == str(target["tcgplayer_product_id"])
    ]
    return exact


def _identity_row(target: dict[str, Any], provider_card: dict[str, Any]) -> dict[str, Any]:
    provider_id = provider_card.get("id")
    if provider_id is None:
        raise RuntimeError("PkmnPrices card row is missing id")
    provider_set = provider_card.get("set") or {}
    return {
        "provider_card_id": int(provider_id),
        "canonical_card_id": target["canonical_card_id"],
        "tcgplayer_product_id": str(target["tcgplayer_product_id"]),
        "language": "English",
        "match_basis": target["product_identity_basis"],
        "provider_name": provider_card.get("name"),
        "provider_set_id": str(provider_set.get("id")) if provider_set.get("id") is not None else None,
        "metadata": {
            "provider_set_name": provider_set.get("name"),
            "card_number": provider_card.get("number"),
            "target_card_name": target.get("card_name"),
            "target_card_number": target.get("card_number"),
            "gap_variants": target.get("gap_variants") or [],
        },
    }


def _run_metadata(
    targets: list[dict[str, Any]],
    market_date: str,
    item_credit_cap: int,
    max_sold_per_card: int,
    sync_mode: str,
) -> dict[str, Any]:
    return {
        "market_date": market_date,
        "mode": "vintage_gap_shadow",
        "max_sold_per_card": max_sold_per_card,
        "sync_mode": sync_mode,
        "target_canonical_card_ids": [row["canonical_card_id"] for row in targets],
        "target_tcgplayer_product_ids": [row["tcgplayer_product_id"] for row in targets],
        "item_credit_cap": item_credit_cap,
        "set_value_authority_unchanged": True,
        "fair_value_research_only": True,
        "sold_identity_matcher_version": SOLD_IDENTITY_MATCHER_VERSION,
    }


def collect(
    *,
    db: Any,
    provider: PkmnPricesClient,
    market_date: str,
    item_credit_cap: int,
    max_sold_per_card: int,
    target_limit: int | None = None,
    sync_mode: str = "incremental",
) -> dict[str, Any]:
    store = PkmnPricesStore(db)
    gap_rows = discover_vintage_gap_rows(db, market_date)
    targets = resolve_targets(db, gap_rows)
    if target_limit is not None:
        targets = targets[: max(0, int(target_limit))]

    metadata = _run_metadata(
        targets, market_date, item_credit_cap, max_sold_per_card, sync_mode
    )
    manifest_fingerprint = _fingerprint(metadata)
    run_id = str(uuid.uuid4())
    started_at = datetime.now(timezone.utc)
    store.create_run({
        "run_id": run_id,
        "started_at": started_at.isoformat(),
        "finished_at": None,
        "status": "RUNNING",
        "selector_version": SELECTOR_VERSION,
        "collector_version": COLLECTOR_VERSION,
        "target_count": len(targets),
        "item_credit_cap": item_credit_cap,
        "api_request_count": 0,
        "credits_used": 0,
        "provider_card_lookup_count": 0,
        "sold_item_count": 0,
        "exact_attribution_count": 0,
        "fair_value_signal_eligible_count": 0,
        "set_value_nm_eligible_count": 0,
        "manifest_fingerprint": manifest_fingerprint,
        "metadata": metadata,
    })

    totals = {
        "provider_card_lookup_count": 0,
        "sold_item_count": 0,
        "exact_attribution_count": 0,
        "fair_value_signal_eligible_count": 0,
        "inserted": 0,
        "duplicates": 0,
        "targets_completed": 0,
        "targets_failed": 0,
    }
    failures: list[dict[str, Any]] = []

    try:
        for target in targets:
            if provider.credits_charged >= item_credit_cap:
                failures.append({
                    "canonical_card_id": target["canonical_card_id"],
                    "code": "ITEM_CREDIT_CAP_REACHED",
                })
                totals["targets_failed"] += 1
                break

            try:
                matches = _provider_identity_rows(provider, target)
                totals["provider_card_lookup_count"] += 1
                if len(matches) != 1:
                    raise RuntimeError(
                        f"provider identity count={len(matches)} for "
                        f"tcgplayer_product_id={target['tcgplayer_product_id']}"
                    )
                provider_card = matches[0]
                identity = _identity_row(target, provider_card)
                store.upsert_identity(identity)

                provider_card_id = int(identity["provider_card_id"])
                sync = store.get_sync_state(provider_card_id)
                sync_metadata = dict((sync or {}).get("metadata") or {})

                if sync_mode == "historical_backfill":
                    since = None
                    initial_cursor = (
                        str(sync_metadata.get("backfill_cursor"))
                        if sync_metadata.get("backfill_in_progress")
                        and sync_metadata.get("backfill_cursor")
                        else None
                    )
                else:
                    if sync_metadata.get("backfill_in_progress"):
                        raise RuntimeError(
                            "historical backfill is incomplete; incremental sync is blocked"
                        )
                    since = (
                        str(sync.get("last_ingested_at"))
                        if sync and sync.get("last_ingested_at")
                        else None
                    )
                    initial_cursor = None

                remaining_cap = max(0, item_credit_cap - provider.credits_charged)
                max_items = min(max_sold_per_card, remaining_cap)
                collection = provider.ebay_sold_collection(
                    provider_card_id,
                    graded=False,
                    since=since,
                    max_items=max_items,
                    initial_cursor=initial_cursor,
                )
                raw_rows = list(collection["rows"])

                collected_at = datetime.now(timezone.utc).isoformat()
                normalized = []
                for raw_row in raw_rows:
                    row = normalize_sold_listing(
                        raw_row,
                        provider_card_id=provider_card_id,
                        canonical_card_id=target["canonical_card_id"],
                        internal_variants=target["variant_candidates"],
                        collected_at=collected_at,
                    )
                    strict = classify_vintage_sold(target, raw_row)
                    row["card_variant_id"] = strict["card_variant_id"]
                    row["identity_state"] = strict["state"]
                    row["fair_value_signal_eligible"] = bool(
                        strict["state"] == "EXACT"
                        and not row["graded"]
                        and row["currency"] == "USD"
                        and row["attribution"] == "exact"
                    )
                    row["exclusion_reason"] = (
                        None if row["fair_value_signal_eligible"] else strict["reason"]
                    )
                    payload = dict(row["provider_payload"])
                    payload["_index_identity"] = {
                        "matcher_version": strict["matcher_version"],
                        "reason": strict["reason"],
                        "evidence": strict["evidence"],
                    }
                    row["provider_payload"] = payload
                    row["run_id"] = run_id
                    normalized.append(row)

                inserted, duplicates = store.insert_evidence(normalized)
                totals["inserted"] += inserted
                totals["duplicates"] += duplicates
                totals["sold_item_count"] += len(normalized)
                totals["exact_attribution_count"] += sum(
                    row["attribution"] == "exact" for row in normalized
                )
                totals["fair_value_signal_eligible_count"] += sum(
                    bool(row["fair_value_signal_eligible"]) for row in normalized
                )
                totals["targets_completed"] += 1

                old_seen = int((sync or {}).get("rows_seen") or 0)
                old_inserted = int((sync or {}).get("rows_inserted") or 0)
                observed_ingested = [
                    str(row["ingested_at"]) for row in normalized if row.get("ingested_at")
                ]
                observed_sold = [
                    str(row["sold_at"]) for row in normalized if row.get("sold_at")
                ]
                prior_ingested = (
                    str((sync or {}).get("last_ingested_at"))
                    if (sync or {}).get("last_ingested_at")
                    else None
                )
                prior_sold = (
                    str((sync or {}).get("last_sold_at"))
                    if (sync or {}).get("last_sold_at")
                    else None
                )

                if sync_mode == "historical_backfill":
                    watermark = sync_metadata.get("backfill_incremental_watermark")
                    if not watermark and observed_ingested:
                        watermark = max(observed_ingested)
                    watermark_sold = sync_metadata.get("backfill_latest_sold_at")
                    if not watermark_sold and observed_sold:
                        watermark_sold = max(observed_sold)
                    backfill_in_progress = bool(collection.get("has_more"))
                    state_status = "PARTIAL" if backfill_in_progress else "CURRENT"
                    last_ingested = prior_ingested if backfill_in_progress else (
                        str(watermark) if watermark else prior_ingested
                    )
                    last_sold = prior_sold if backfill_in_progress else (
                        str(watermark_sold) if watermark_sold else prior_sold
                    )
                    next_metadata = {
                        "tcgplayer_product_id": target["tcgplayer_product_id"],
                        "gap_variants": target["gap_variants"],
                        "backfill_in_progress": backfill_in_progress,
                        "backfill_complete": not backfill_in_progress,
                        "backfill_cursor": collection.get("next_cursor")
                            if backfill_in_progress else None,
                        "backfill_incremental_watermark": watermark,
                        "backfill_latest_sold_at": watermark_sold,
                    }
                else:
                    last_ingested_candidates = observed_ingested + (
                        [prior_ingested] if prior_ingested else []
                    )
                    last_sold_candidates = observed_sold + (
                        [prior_sold] if prior_sold else []
                    )
                    last_ingested = (
                        max(last_ingested_candidates) if last_ingested_candidates else None
                    )
                    last_sold = max(last_sold_candidates) if last_sold_candidates else None
                    state_status = "CURRENT"
                    next_metadata = {
                        **sync_metadata,
                        "tcgplayer_product_id": target["tcgplayer_product_id"],
                        "gap_variants": target["gap_variants"],
                    }

                store.upsert_sync_state({
                    "provider_card_id": provider_card_id,
                    "canonical_card_id": target["canonical_card_id"],
                    "last_ingested_at": last_ingested,
                    "last_sold_at": last_sold,
                    "last_attempt_at": collected_at,
                    "last_success_at": collected_at,
                    "status": state_status,
                    "consecutive_failures": 0,
                    "rows_seen": old_seen + len(normalized),
                    "rows_inserted": old_inserted + inserted,
                    "last_error_code": None,
                    "metadata": next_metadata,
                })
            except Exception as exc:
                totals["targets_failed"] += 1
                failures.append({
                    "canonical_card_id": target["canonical_card_id"],
                    "tcgplayer_product_id": target["tcgplayer_product_id"],
                    "code": type(exc).__name__,
                    "message": str(exc)[:500],
                })

        status = "COMPLETE" if not failures else ("PARTIAL" if totals["targets_completed"] else "FAILED")
        finished_at = datetime.now(timezone.utc).isoformat()
        store.update_run(run_id, {
            "finished_at": finished_at,
            "status": status,
            "api_request_count": provider.request_attempt_count,
            "credits_used": min(provider.credits_charged, item_credit_cap),
            "provider_card_lookup_count": totals["provider_card_lookup_count"],
            "sold_item_count": totals["sold_item_count"],
            "exact_attribution_count": totals["exact_attribution_count"],
            "fair_value_signal_eligible_count": totals["fair_value_signal_eligible_count"],
            "set_value_nm_eligible_count": 0,
            "error_code": failures[0]["code"] if failures else None,
            "metadata": {
                **metadata,
                "provider_credit_limit": provider.credits_limit,
                "provider_rate_remaining": provider.rate_remaining,
                "targets_completed": totals["targets_completed"],
                "targets_failed": totals["targets_failed"],
                "inserted": totals["inserted"],
                "duplicates": totals["duplicates"],
                "failures": failures,
            },
        })
        return {
            "run_id": run_id,
            "status": status,
            "market_date": market_date,
            "target_count": len(targets),
            "credits_used": provider.credits_charged,
            "credit_limit": provider.credits_limit,
            **totals,
            "failures": failures,
            "set_value_authority_unchanged": True,
        }
    except Exception:
        finished_at = datetime.now(timezone.utc).isoformat()
        try:
            store.update_run(run_id, {
                "finished_at": finished_at,
                "status": "FAILED",
                "api_request_count": provider.request_attempt_count,
                "credits_used": min(provider.credits_charged, item_credit_cap),
                "provider_card_lookup_count": totals["provider_card_lookup_count"],
                "sold_item_count": totals["sold_item_count"],
                "exact_attribution_count": totals["exact_attribution_count"],
                "fair_value_signal_eligible_count": totals["fair_value_signal_eligible_count"],
                "set_value_nm_eligible_count": 0,
                "error_code": "UNEXPECTED_COLLECTOR_FAILURE",
                "metadata": {**metadata, "failures": failures},
            })
        finally:
            raise


def preview(db: Any, market_date: str, target_limit: int | None = None) -> dict[str, Any]:
    gap_rows = discover_vintage_gap_rows(db, market_date)
    targets = resolve_targets(db, gap_rows)
    if target_limit is not None:
        targets = targets[: max(0, int(target_limit))]
    return {
        "market_date": market_date,
        "gap_row_count": len(gap_rows),
        "target_count": len(targets),
        "targets": [
            {
                "canonical_card_id": row["canonical_card_id"],
                "card_name": row["card_name"],
                "card_number": row["card_number"],
                "tcgplayer_product_id": row["tcgplayer_product_id"],
                "gap_variants": row["gap_variants"],
            }
            for row in targets
        ],
        "provider_calls": 0,
        "database_writes": 0,
        "set_value_authority_unchanged": True,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--market-date", default=None)
    parser.add_argument("--item-credit-cap", type=int, default=500)
    parser.add_argument("--max-sold-per-card", type=int, default=40)
    parser.add_argument("--target-limit", type=int, default=None)
    parser.add_argument(
        "--sync-mode",
        choices=("incremental", "historical_backfill"),
        default="incremental",
    )
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--dry-run", action="store_true")
    mode.add_argument("--commit", action="store_true")
    args = parser.parse_args()

    if args.item_credit_cap < 1:
        parser.error("--item-credit-cap must be >= 1")
    if args.max_sold_per_card < 1:
        parser.error("--max-sold-per-card must be >= 1")

    db = create_service_role_client()
    market_date = args.market_date or latest_approved_market_date(db)

    if args.dry_run:
        result = preview(db, market_date, args.target_limit)
    else:
        credentials = load_pkmnprices_credentials(allow_frontend_fallback=False)
        provider = PkmnPricesClient(
            credentials.api_key,
            # Pro allows 60 req/min. 1.1s keeps this worker below that ceiling
            # even during long cursor walks rather than depending on 429 retries.
            min_request_interval=1.1,
        )
        result = collect(
            db=db,
            provider=provider,
            market_date=market_date,
            item_credit_cap=args.item_credit_cap,
            max_sold_per_card=args.max_sold_per_card,
            target_limit=args.target_limit,
            sync_mode=args.sync_mode,
        )

    print(json.dumps(result, indent=2, sort_keys=True, default=str))
    return 0 if result.get("status") not in {"FAILED"} else 2


if __name__ == "__main__":
    raise SystemExit(main())
