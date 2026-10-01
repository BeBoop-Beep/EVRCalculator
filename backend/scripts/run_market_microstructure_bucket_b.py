"""Backfill the frozen Core Panel V1 raw + graded completed-sale ledger.

Dry-run/preflight performs no provider calls and no database writes. Commit mode
is intentionally bounded; the full 207-card run requires an explicit later
review and is rejected by this entry point's default smoke limits.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import statistics
import uuid
from collections import Counter
from datetime import date, datetime, timezone
from decimal import Decimal
from pathlib import Path
from typing import Any

from backend.pricing_pipeline.pkmnprices_client import PkmnPricesClient
from backend.pricing_pipeline.pkmnprices_credentials import load_pkmnprices_credentials
from backend.pricing_pipeline.pkmnprices_sold import normalize_sold_listing
from backend.pricing_pipeline.pkmnprices_store import PkmnPricesStore

ROOT = Path(__file__).resolve().parents[2]
MANIFEST = ROOT / "docs/research/index_fair_value/core_panel_v1_manifest.json"
PANEL_FINGERPRINT = "9e3068ffb2e644e3dab2f5c237271afa4efe061ed8f3139187dc9e8331bd1d1f"
SELECTOR_VERSION = "market_microstructure_core_panel_v1"
COLLECTOR_VERSION = "pkmnprices_combined_sold_cursor_v1"
SMOKE_CARD_CAP = 10
SMOKE_CREDIT_CAP = 1000


def _fingerprint(value: Any) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"),
                                     ensure_ascii=True).encode()).hexdigest()


def load_panel(path: Path = MANIFEST) -> dict[str, Any]:
    manifest = json.loads(path.read_text(encoding="utf-8"))
    audit = manifest.pop("audit")
    expected = manifest.pop("panel_fingerprint")
    if _fingerprint(manifest) != expected or expected != PANEL_FINGERPRINT:
        raise RuntimeError("CORE_PANEL_FINGERPRINT_DRIFT")
    if len(manifest.get("rows") or []) != 207 or audit.get("row_count") != 207:
        raise RuntimeError("CORE_PANEL_MEMBERSHIP_DRIFT")
    manifest["audit"] = audit
    manifest["panel_fingerprint"] = expected
    return manifest


def ordered_panel_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Return a stable order with a price-band/era-stratified first slice."""
    ordered = sorted(rows, key=lambda row: (
        row["price_band"], row["era"], row["canonical_card_id"], row["card_variant_id"]
    ))
    picked: list[dict[str, Any]] = []
    used_bands: set[str] = set()
    bands = sorted({row["price_band"] for row in ordered})
    eras = sorted({row["era"] for row in ordered})
    for index, band in enumerate(bands):
        band_rows = [row for row in ordered if row["price_band"] == band]
        preferred_era = eras[-1 - (index % len(eras))]
        row = next((item for item in band_rows if item["era"] == preferred_era), band_rows[0])
        if row["price_band"] not in used_bands:
            picked.append(row)
            used_bands.add(row["price_band"])
    for row in ordered:
        if row not in picked:
            picked.append(row)
    return picked


def select_smoke_rows(rows: list[dict[str, Any]], limit: int, offset: int = 0) -> list[dict[str, Any]]:
    return ordered_panel_rows(rows)[offset:offset + limit]


def preflight(*, card_limit: int, credit_cap: int, max_items_per_card: int,
              card_offset: int = 0) -> dict[str, Any]:
    panel = load_panel()
    if not 1 <= card_limit <= SMOKE_CARD_CAP:
        raise ValueError(f"card_limit must be between 1 and {SMOKE_CARD_CAP}")
    if not 1 <= credit_cap <= SMOKE_CREDIT_CAP:
        raise ValueError(f"credit_cap must be between 1 and {SMOKE_CREDIT_CAP}")
    if max_items_per_card < 1:
        raise ValueError("max_items_per_card must be positive")
    if card_offset < 0 or card_offset + card_limit > 207:
        raise ValueError("card_offset/card_limit exceeds the frozen panel")
    rows = select_smoke_rows(panel["rows"], card_limit, card_offset)
    return {
        "status": "PREFLIGHT_OK", "panel_fingerprint": PANEL_FINGERPRINT,
        "panel_card_count": 207, "selected_card_count": len(rows),
        "card_offset": card_offset,
        "credit_cap": credit_cap, "max_items_per_card": max_items_per_card,
        "provider_requests": 0, "provider_credits_used": 0, "database_writes": 0,
        "combined_stream_graded_parameter": None,
        "selected": [{key: row[key] for key in (
            "canonical_card_id", "card_variant_id", "tcgplayer_product_id",
            "card_name", "set_name", "era", "price_band"
        )} for row in rows],
        "research_only": True, "set_value_authority_unchanged": True,
    }


def _identity(row: dict[str, Any], provider_card: dict[str, Any]) -> dict[str, Any]:
    provider_id = provider_card.get("id")
    if provider_id is None:
        raise RuntimeError("provider card row is missing id")
    provider_set = provider_card.get("set") or {}
    return {
        "provider_card_id": int(provider_id), "canonical_card_id": row["canonical_card_id"],
        "tcgplayer_product_id": str(row["tcgplayer_product_id"]), "language": "English",
        "match_basis": "frozen_tcgplayer_product_id_exact",
        "provider_name": provider_card.get("name"),
        "provider_set_id": str(provider_set.get("id")) if provider_set.get("id") is not None else None,
        "metadata": {"provider_set_name": provider_set.get("name"),
                     "panel_fingerprint": PANEL_FINGERPRINT,
                     "card_variant_id": row["card_variant_id"]},
    }


def _normalize(raw: dict[str, Any], row: dict[str, Any], provider_id: int,
               run_id: str, collected_at: str) -> dict[str, Any]:
    normalized = normalize_sold_listing(
        raw, provider_card_id=provider_id, canonical_card_id=row["canonical_card_id"],
        internal_variants=[{"id": row["card_variant_id"], "edition": row.get("edition"),
                            "printing_type": row.get("printing_type")}],
        collected_at=collected_at,
    )
    normalized["run_id"] = run_id
    return normalized


def combined_stream_semantics(provider: PkmnPricesClient, provider_card_id: int,
                              *, per_stream: int = 20) -> dict[str, Any]:
    """Compare one combined page with raw/graded control pages."""
    combined = provider.ebay_sold_collection(provider_card_id, graded=None, max_items=per_stream)["rows"]
    raw = provider.ebay_sold_collection(provider_card_id, graded=False, max_items=per_stream)["rows"]
    graded = provider.ebay_sold_collection(provider_card_id, graded=True, max_items=per_stream)["rows"]
    ids = lambda values: {str(value.get("id")) for value in values}
    raw_ids, graded_ids, combined_ids = ids(raw), ids(graded), ids(combined)
    combined_graded = [x for x in combined if x.get("grader") or x.get("grade") or x.get("grade_qualifier")]
    evidence_complete = all(
        value.get("grader") and value.get("grade")
        for value in combined_graded
    )
    overlap = len((raw_ids | graded_ids) & combined_ids)
    return {
        "combined_count": len(combined), "raw_control_count": len(raw),
        "graded_control_count": len(graded), "combined_graded_count": len(combined_graded),
        "control_union_overlap_count": overlap,
        "grader_grade_evidence_complete": evidence_complete,
        "qualifier_field_preserved": all("grade_qualifier" in x for x in combined_graded),
        "safe_for_single_cursor": bool(combined and raw and graded and combined_graded and evidence_complete),
    }


def summarize(rows: list[dict[str, Any]], *, today: date | None = None) -> dict[str, Any]:
    today = today or datetime.now(timezone.utc).date()
    dates = sorted(date.fromisoformat(str(row["sold_at"])[:10]) for row in rows)
    prices = sorted(Decimal(str(row["price"])) for row in rows)
    median = statistics.median(prices) if prices else None
    deviations = sorted(abs(value - median) for value in prices) if prices else []
    q = statistics.quantiles(prices, n=4, method="inclusive") if len(prices) >= 2 else []
    gaps = [(b - a).days for a, b in zip(sorted(set(dates)), sorted(set(dates))[1:])]
    return {
        "history_start": dates[0].isoformat() if dates else None,
        "history_end": dates[-1].isoformat() if dates else None,
        "transaction_count": len(rows), "transaction_days": len(set(dates)),
        **{f"count_{days}d": sum((today - sold).days <= days for sold in dates)
           for days in (7, 30, 90, 180)},
        "median_days_between_sales": float(statistics.median(gaps)) if gaps else None,
        "recency_days": (today - dates[-1]).days if dates else None,
        "median_price": str(median) if median is not None else None,
        "mad_price": str(statistics.median(deviations)) if deviations else None,
        "iqr_price": str(q[2] - q[0]) if q else None,
        "grader_mix": dict(Counter(str(row.get("grader") or "RAW") for row in rows)),
        "grade_mix": dict(Counter(str(row.get("grade") or "RAW") for row in rows)),
        "qualifier_mix": dict(Counter(str(row.get("grade_qualifier") or "NONE") for row in rows)),
        "raw_count": sum(not bool(row.get("graded")) for row in rows),
        "graded_count": sum(bool(row.get("graded")) for row in rows),
    }


def collect_smoke(*, db: Any, provider: PkmnPricesClient, card_limit: int,
                  credit_cap: int, max_items_per_card: int,
                  card_offset: int = 0) -> dict[str, Any]:
    plan = preflight(card_limit=card_limit, credit_cap=credit_cap,
                     max_items_per_card=max_items_per_card, card_offset=card_offset)
    panel = load_panel()
    targets = select_smoke_rows(panel["rows"], card_limit, card_offset)
    # Exercise combined semantics on the most liquid-looking price stratum first;
    # this maximizes the chance that one bounded page contains both raw and slabs.
    targets.sort(key=lambda row: (row["price_band"] != "250_plus", row["canonical_card_id"]))
    store = PkmnPricesStore(db)
    run_id = str(uuid.uuid4())
    started = datetime.now(timezone.utc).isoformat()
    metadata = {"panel_fingerprint": PANEL_FINGERPRINT, "mode": "bounded_smoke",
                "combined_stream": True, "max_items_per_card": max_items_per_card,
                "research_only": True, "full_panel_backfill": False}
    store.create_run({"run_id": run_id, "started_at": started, "finished_at": None,
        "status": "RUNNING", "selector_version": SELECTOR_VERSION,
        "collector_version": COLLECTOR_VERSION, "target_count": len(targets),
        "item_credit_cap": credit_cap, "api_request_count": 0, "credits_used": 0,
        "provider_card_lookup_count": 0, "sold_item_count": 0,
        "exact_attribution_count": 0, "fair_value_signal_eligible_count": 0,
        "set_value_nm_eligible_count": 0, "manifest_fingerprint": PANEL_FINGERPRINT,
        "metadata": metadata})
    totals = Counter()
    failures: list[dict[str, Any]] = []
    receipts: list[dict[str, Any]] = []
    semantics: dict[str, Any] | None = None
    for target in targets:
        if provider.credits_charged >= credit_cap:
            failures.append({"canonical_card_id": target["canonical_card_id"], "code": "CREDIT_CAP_REACHED"})
            break
        before = provider.credits_charged
        try:
            existing = store.get_identity_by_canonical(target["canonical_card_id"])
            if existing and str(existing["tcgplayer_product_id"]) == str(target["tcgplayer_product_id"]):
                identity = existing
            else:
                matches = [x for x in provider.cards_by_tcgplayer_id(target["tcgplayer_product_id"])
                           if str(x.get("tcg_player_id") or "") == str(target["tcgplayer_product_id"])]
                totals["provider_card_lookup_count"] += 1
                if len(matches) != 1:
                    raise RuntimeError(f"provider identity count={len(matches)}")
                identity = _identity(target, matches[0])
                store.upsert_identity(identity)
            provider_id = int(identity["provider_card_id"])
            if semantics is None:
                semantics = combined_stream_semantics(provider, provider_id)
                if not semantics["safe_for_single_cursor"]:
                    raise RuntimeError("COMBINED_STREAM_SEMANTICS_UNPROVEN")
            sync = store.get_sync_state(provider_id)
            sync_meta = dict((sync or {}).get("metadata") or {})
            cursor = sync_meta.get("core_panel_backfill_cursor") if sync_meta.get("core_panel_backfill_in_progress") else None
            remaining = max(0, credit_cap - provider.credits_charged)
            collection = provider.ebay_sold_collection(
                provider_id, graded=None, max_items=min(max_items_per_card, remaining),
                initial_cursor=str(cursor) if cursor else None)
            collected_at = datetime.now(timezone.utc).isoformat()
            normalized = [_normalize(raw, target, provider_id, run_id, collected_at)
                          for raw in collection["rows"]]
            inserted, duplicates, drifts = store.insert_evidence(normalized)
            totals.update({"sold_item_count": len(normalized), "inserted": inserted,
                           "duplicates": duplicates, "provider_metadata_drifts": drifts,
                           "exact_attribution_count": sum(x["attribution"] == "exact" for x in normalized),
                           "fair_value_signal_eligible_count": sum(bool(x["fair_value_signal_eligible"]) for x in normalized),
                           "targets_completed": 1})
            observed_ingested = [x["ingested_at"] for x in normalized if x.get("ingested_at")]
            historical_more = bool(collection["has_more"])
            prior_watermark = sync_meta.get("core_panel_incremental_watermark")
            watermark = max(observed_ingested) if observed_ingested and not prior_watermark else prior_watermark
            last_ingested = (sync or {}).get("last_ingested_at")
            if not historical_more and watermark:
                last_ingested = watermark
            store.upsert_sync_state({"provider_card_id": provider_id,
                "canonical_card_id": target["canonical_card_id"],
                "last_ingested_at": last_ingested,
                "last_sold_at": max([x["sold_at"] for x in normalized], default=(sync or {}).get("last_sold_at")),
                "last_attempt_at": collected_at, "last_success_at": collected_at,
                "status": "PARTIAL" if historical_more else "CURRENT", "consecutive_failures": 0,
                "rows_seen": int((sync or {}).get("rows_seen") or 0) + len(normalized),
                "rows_inserted": int((sync or {}).get("rows_inserted") or 0) + inserted,
                "last_error_code": None,
                "metadata": {**sync_meta, "panel_fingerprint": PANEL_FINGERPRINT,
                    "stream": "combined_raw_graded", "core_panel_backfill_in_progress": historical_more,
                    "core_panel_backfill_complete": not historical_more,
                    "core_panel_backfill_cursor": collection["next_cursor"] if historical_more else None,
                    "core_panel_incremental_watermark": watermark}})
            receipts.append({"canonical_card_id": target["canonical_card_id"],
                "provider_card_id": provider_id, "credits_used": provider.credits_charged - before,
                "rows_seen": len(normalized), "rows_inserted": inserted,
                "history_drained": not historical_more, "summary": summarize(normalized)})
        except Exception as exc:
            totals["targets_failed"] += 1
            failures.append({"canonical_card_id": target["canonical_card_id"],
                             "code": type(exc).__name__, "message": str(exc)[:300]})
    status = "COMPLETE" if not failures else ("PARTIAL" if totals["targets_completed"] else "FAILED")
    finished = datetime.now(timezone.utc).isoformat()
    final_meta = {**metadata, "preflight": plan, "combined_stream_semantics": semantics,
                  "credit_receipts": receipts, "failures": failures}
    store.update_run(run_id, {"finished_at": finished, "status": status,
        "api_request_count": provider.request_attempt_count,
        "credits_used": min(provider.credits_charged, credit_cap),
        "provider_card_lookup_count": totals["provider_card_lookup_count"],
        "sold_item_count": totals["sold_item_count"],
        "exact_attribution_count": totals["exact_attribution_count"],
        "fair_value_signal_eligible_count": totals["fair_value_signal_eligible_count"],
        "set_value_nm_eligible_count": 0, "error_code": failures[0]["code"] if failures else None,
        "metadata": final_meta})
    return {"run_id": run_id, "status": status, "panel_fingerprint": PANEL_FINGERPRINT,
            "credits_used": provider.credits_charged, "credit_cap": credit_cap,
            **dict(totals), "combined_stream_semantics": semantics,
            "credit_receipts": receipts, "failures": failures,
            "full_panel_backfill_started": False, "set_value_authority_unchanged": True}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--card-limit", type=int, default=10)
    parser.add_argument("--card-offset", type=int, default=0)
    parser.add_argument("--credit-cap", type=int, default=900)
    parser.add_argument("--max-items-per-card", type=int, default=80)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--preflight", action="store_true")
    mode.add_argument("--commit-smoke", action="store_true")
    args = parser.parse_args()
    if args.preflight:
        result = preflight(card_limit=args.card_limit, credit_cap=args.credit_cap,
                           max_items_per_card=args.max_items_per_card,
                           card_offset=args.card_offset)
    else:
        from backend.db.clients.supabase_client import create_service_role_client

        credentials = load_pkmnprices_credentials(allow_frontend_fallback=False)
        result = collect_smoke(db=create_service_role_client(),
            provider=PkmnPricesClient(credentials.api_key, min_request_interval=1.1),
            card_limit=args.card_limit, credit_cap=args.credit_cap,
            max_items_per_card=args.max_items_per_card, card_offset=args.card_offset)
    print(json.dumps(result, indent=2, sort_keys=True, default=str))
    return 0 if result["status"] not in {"FAILED"} else 2


if __name__ == "__main__":
    raise SystemExit(main())
