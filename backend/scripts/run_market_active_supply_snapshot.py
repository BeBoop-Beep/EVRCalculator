"""Collect one bounded Core Panel V1 PkmnPrices active-supply snapshot.

The launch build intentionally rejects more than ten live targets. It does not
schedule or enable the recurring 207-card panel.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import uuid
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

from backend.pricing_pipeline.active_supply import normalize_listing, summarize
from backend.pricing_pipeline.active_supply_store import ActiveSupplyStore
from backend.pricing_pipeline.pkmnprices_client import PkmnPricesClient
from backend.pricing_pipeline.pkmnprices_credentials import load_pkmnprices_credentials
from backend.pricing_pipeline.pkmnprices_sold import parse_provider_variant

ROOT = Path(__file__).resolve().parents[2]
MANIFEST_PATH = ROOT / "docs/research/index_fair_value/core_panel_v1_manifest.json"
SOURCE = "pkmnprices_tcgplayer"
MAX_LIVE_TARGETS = 10
MAX_OFFERS = 19  # issue launch smoke requires strictly fewer than 20/card
MAX_CREDITS = 300
PRINTINGS = {"holo": "Holofoil", "reverse-holo": "Reverse Holofoil", "non-holo": "Normal"}


def load_manifest(path: Path = MANIFEST_PATH) -> dict[str, Any]:
    manifest = json.loads(path.read_text(encoding="utf-8"))
    if manifest.get("version") != "market_microstructure_core_panel_v1":
        raise RuntimeError("unexpected panel version")
    if len(manifest.get("rows") or []) != 207:
        raise RuntimeError("Core Panel V1 must contain exactly 207 targets")
    return manifest


def preflight(*, target_limit: int, offer_limit: int, credit_cap: int) -> dict[str, Any]:
    manifest = load_manifest()
    if not 1 <= target_limit <= MAX_LIVE_TARGETS:
        raise ValueError(f"target_limit must be 1..{MAX_LIVE_TARGETS}")
    if not 1 <= offer_limit <= MAX_OFFERS:
        raise ValueError(f"offer_limit must be 1..{MAX_OFFERS}")
    if not 1 <= credit_cap <= MAX_CREDITS:
        raise ValueError(f"credit_cap must be 1..{MAX_CREDITS}")
    # Conservative provider model: one identity lookup plus up to one credit per
    # returned listing. Runtime accounting headers remain authoritative.
    projected_max = target_limit * (1 + offer_limit)
    if projected_max > credit_cap:
        raise ValueError("configured smoke could exceed its provider credit cap")
    targets = manifest["rows"][:target_limit]
    return {
        "mode": "dry_run",
        "panel_version": manifest["version"],
        "panel_fingerprint": manifest["panel_fingerprint"],
        "full_panel_target_count": len(manifest["rows"]),
        "target_count": len(targets),
        "offer_limit": offer_limit,
        "credit_cap": credit_cap,
        "projected_max_credits": projected_max,
        "provider_requests": 0,
        "provider_credits_used": 0,
        "database_writes": 0,
        "recurring_full_panel_enabled": False,
        "targets": [{k: row.get(k) for k in (
            "canonical_card_id", "card_variant_id", "tcgplayer_product_id",
            "printing_type", "edition", "card_name", "set_name"
        )} for row in targets],
    }


def _provider_card(provider: PkmnPricesClient, target: dict[str, Any]) -> dict[str, Any]:
    rows = provider.cards_by_tcgplayer_id(target["tcgplayer_product_id"], language="English", per_page=5)
    exact = [row for row in rows if str(row.get("tcg_player_id") or "") == str(target["tcgplayer_product_id"])]
    if len(exact) != 1:
        raise RuntimeError(f"provider identity count={len(exact)}")
    if exact[0].get("id") is None:
        raise RuntimeError("provider card id missing")
    return exact[0]


def _printing_matches(row: dict[str, Any], target: dict[str, Any]) -> bool:
    parsed = parse_provider_variant(row.get("printing"))
    if parsed["printing_type"] != target.get("printing_type"):
        return False
    edition = str(target.get("edition") or "").strip().casefold().replace("_", "-")
    return not edition or parsed["edition"] == edition


def collect(
    *, db: Any, provider: PkmnPricesClient, seller_hash_key: str,
    target_limit: int, offer_limit: int, credit_cap: int,
    observation_date: str,
) -> dict[str, Any]:
    plan = preflight(target_limit=target_limit, offer_limit=offer_limit, credit_cap=credit_cap)
    manifest = load_manifest()
    targets = manifest["rows"][:target_limit]
    store = ActiveSupplyStore(db)
    run_id = str(uuid.uuid4())
    started = datetime.now(timezone.utc)
    store.create_run({
        "run_id": run_id, "panel_version": manifest["version"],
        "panel_fingerprint": manifest["panel_fingerprint"], "source_provider": SOURCE,
        "expected_observation_date": observation_date, "started_at": started.isoformat(),
        "status": "RUNNING", "target_count": len(targets),
        "metadata": {"launch_smoke": True, "offer_limit": offer_limit,
                     "credit_cap": credit_cap, "recurring_full_panel_enabled": False},
    })
    observed = failed = listing_count = 0
    failures: list[dict[str, str]] = []
    try:
        for target in targets:
            source_card_id = f"tcgplayer:{target['tcgplayer_product_id']}"
            try:
                if provider.credits_charged >= credit_cap:
                    raise RuntimeError("provider credit cap reached")
                card = _provider_card(provider, target)
                source_card_id = str(card["id"])
                printing = PRINTINGS.get(str(target.get("printing_type")))
                if not printing:
                    raise RuntimeError("unsupported exact printing")
                page = provider.tcgplayer_listings_page(
                    source_card_id, condition="Near Mint", printing=printing,
                    language="English", sort="total_asc", limit=offer_limit,
                )
                if provider.credits_charged > credit_cap:
                    raise RuntimeError("provider credit cap exceeded")
                raw = [dict(row) for row in (page.get("data") or []) if isinstance(row, dict)]
                mismatches = [row for row in raw if not _printing_matches(row, target)]
                if mismatches:
                    raise RuntimeError("provider returned non-exact printing")
                listings = [normalize_listing(row, rank=i, seller_hash_key=seller_hash_key)
                            for i, row in enumerate(raw, 1)]
                stats = summarize(listings)
                pagination = page.get("pagination") if isinstance(page.get("pagination"), dict) else {}
                has_more = bool(pagination.get("has_more"))
                observed_at = datetime.now(timezone.utc).isoformat()
                snapshot = {
                    "run_id": run_id, "canonical_card_id": target["canonical_card_id"],
                    "card_variant_id": target["card_variant_id"], "source_provider": SOURCE,
                    "source_card_id": source_card_id, "observed_at": observed_at,
                    "observation_state": "OBSERVED", "language": "English",
                    "condition_label": "Near Mint", "printing_label": printing,
                    "requested_depth": offer_limit, "has_more": has_more,
                    "next_cursor_present": bool(pagination.get("next_cursor")),
                    "continuity_eligible": False,
                    "source_payload": {"sort": "total_asc", "bounded_depth": True,
                                       "truncated": has_more, "inventory_semantics": "captured_depth_only"},
                    **stats,
                }
                store.insert_snapshot(snapshot, listings)
                observed += 1
                listing_count += len(listings)
            except Exception as exc:
                code = type(exc).__name__.upper()
                failures.append({"card_variant_id": target["card_variant_id"], "code": code})
                store.insert_snapshot({
                    "run_id": run_id, "canonical_card_id": target["canonical_card_id"],
                    "card_variant_id": target["card_variant_id"], "source_provider": SOURCE,
                    "source_card_id": source_card_id, "observed_at": None,
                    "observation_state": "TARGET_FAILED", "language": "English",
                    "condition_label": "Near Mint", "printing_label": PRINTINGS.get(str(target.get("printing_type"))),
                    "requested_depth": offer_limit, "has_more": None, "next_cursor_present": None,
                    "continuity_eligible": False, "error_code": code,
                    "source_payload": {"bounded_depth": True, "raw_error_omitted": True},
                }, [])
                failed += 1
        status = "COMPLETE" if failed == 0 else "PARTIAL"
    except BaseException:
        status = "FAILED"
        raise
    finally:
        finished = datetime.now(timezone.utc)
        store.finish_run(run_id, {
            "finished_at": finished.isoformat(), "status": status,
            "observed_target_count": observed,
            "provider_request_count": provider.successful_request_count,
            "provider_credits_used": provider.credits_charged,
            "metadata": {"launch_smoke": True, "offer_limit": offer_limit,
                         "credit_cap": credit_cap, "target_failures": failed,
                         "recurring_full_panel_enabled": False},
        })
    elapsed = max((finished - started).total_seconds(), 0.001)
    return {
        **{k: v for k, v in plan.items() if k not in {"mode", "targets"}},
        "mode": "live_smoke", "run_id": run_id, "status": status,
        "observed_target_count": observed, "failed_target_count": failed,
        "captured_listing_count": listing_count,
        "provider_requests": provider.successful_request_count,
        "provider_credits_used": provider.credits_charged,
        "actual_credits_per_card": provider.credits_charged / len(targets),
        "projected_full_panel_daily_credits": provider.credits_charged / len(targets) * 207,
        "elapsed_seconds": elapsed, "failures": failures,
        "database_writes": 1 + len(targets) + listing_count + 1,
        "recurring_full_panel_enabled": False,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--live-smoke", action="store_true")
    parser.add_argument("--target-limit", type=int, default=10)
    parser.add_argument("--offer-limit", type=int, default=19)
    parser.add_argument("--credit-cap", type=int, default=300)
    parser.add_argument("--observation-date", default=date.today().isoformat())
    args = parser.parse_args()
    if not args.live_smoke:
        result = preflight(target_limit=args.target_limit, offer_limit=args.offer_limit, credit_cap=args.credit_cap)
    else:
        from backend.db.clients.supabase_client import create_service_role_client

        credentials = load_pkmnprices_credentials(allow_frontend_fallback=False)
        key = os.environ.get("ACTIVE_SUPPLY_SELLER_HASH_KEY", "")
        result = collect(
            db=create_service_role_client(), provider=PkmnPricesClient(credentials.api_key),
            seller_hash_key=key, target_limit=args.target_limit, offer_limit=args.offer_limit,
            credit_cap=args.credit_cap, observation_date=args.observation_date,
        )
    print(json.dumps(result, indent=2, sort_keys=True, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
