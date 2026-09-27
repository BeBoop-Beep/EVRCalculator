"""Bounded same-day sealed-market authority checks for coordinated publication."""
from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass, field
from typing import Any, Iterable, Mapping, Optional, Sequence

DEFERRED_SEALED_MARKET_AUTHORITY_INCOMPLETE = "DEFERRED_SEALED_MARKET_AUTHORITY_INCOMPLETE"
SEALED_RESULT_DATE_MISMATCH = "SEALED_RESULT_DATE_MISMATCH"


@dataclass(frozen=True)
class SealedMarketAuthorityReport:
    ready: bool
    reason_code: str
    target_market_date: str
    expected_product_count: int
    verified_product_count: int
    stale_product_count: int
    missing_product_count: int
    stale_product_ids: list[str] = field(default_factory=list)
    missing_product_ids: list[str] = field(default_factory=list)
    min_price_as_of: Optional[str] = None
    max_price_as_of: Optional[str] = None
    snapshot_authority_ids: list[str] = field(default_factory=list)
    authority_fingerprint: Optional[str] = None
    query_count: int = 1

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def evaluate_snapshot_rows(rows: Iterable[Mapping[str, Any]], target_market_date: str,
                           canonical_set_keys: Optional[Sequence[str]] = None) -> SealedMarketAuthorityReport:
    expected: set[str] = set()
    selected: dict[str, Optional[str]] = {}
    authority_ids: list[str] = []
    coherent = True
    for row in rows:
        payload = row.get("payload_json") or {}
        if canonical_set_keys is not None and (payload.get("set") or {}).get("canonicalKey") not in canonical_set_keys:
            continue
        meta = payload.get("meta") or {}
        manifest = {str(value) for value in (meta.get("eligibleProductIds") or [])}
        products = list(payload.get("products") or [])
        expected.update(manifest)
        if not manifest:
            coherent = False
            expected.update(str(p.get("sealedProductId")) for p in products if p.get("sealedProductId") is not None)
        for product in products:
            selected[str(product.get("sealedProductId"))] = product.get("priceAsOf")
        fingerprint = row.get("source_generation_fingerprint")
        if not fingerprint or row.get("market_date") != payload.get("marketDate"):
            coherent = False
        authority_ids.append(f"{row.get('set_id')}:{fingerprint or 'missing'}")
    missing = sorted(expected - set(selected))
    stale = sorted(product_id for product_id in expected & set(selected) if selected[product_id] != target_market_date)
    dates = sorted(str(selected[p]) for p in expected & set(selected) if selected[p])
    verified = len(expected) - len(missing) - len(stale)
    ready = bool(expected) and coherent and not missing and not stale
    canonical = json.dumps({"date": target_market_date, "authorities": sorted(authority_ids),
                            "expected": sorted(expected), "selected": sorted(selected.items())},
                           sort_keys=True, separators=(",", ":"))
    return SealedMarketAuthorityReport(
        ready=ready, reason_code="READY" if ready else DEFERRED_SEALED_MARKET_AUTHORITY_INCOMPLETE,
        target_market_date=target_market_date, expected_product_count=len(expected),
        verified_product_count=verified, stale_product_count=len(stale), missing_product_count=len(missing),
        stale_product_ids=stale, missing_product_ids=missing,
        min_price_as_of=dates[0] if dates else None, max_price_as_of=dates[-1] if dates else None,
        snapshot_authority_ids=sorted(authority_ids),
        authority_fingerprint=hashlib.sha256(canonical.encode()).hexdigest() if authority_ids else None,
    )


def evaluate_same_day_sealed_market_authority(client: Any, *, target_market_date: str) -> SealedMarketAuthorityReport:
    from backend.db.services.opening_simulation_gate import supported_opening_set_keys
    rows = list(client.table("pokemon_set_sealed_market_snapshot_latest").select(
        "set_id,market_date,payload_json,source_generation_fingerprint"
    ).eq("tcg", "pokemon").execute().data or [])
    return evaluate_snapshot_rows(rows, target_market_date, supported_opening_set_keys())


def verify_simulation_product_dates(client: Any, *, target_market_date: str) -> SealedMarketAuthorityReport:
    runs = list(client.table("calculation_runs").select("id,target_id,created_at")
                .eq("market_date", target_market_date).eq("target_type", "set")
                .order("created_at", desc=True).execute().data or [])
    latest_run_ids = []
    seen_sets = set()
    for run in runs:
        target_id = str(run.get("target_id"))
        if target_id not in seen_sets:
            seen_sets.add(target_id); latest_run_ids.append(str(run.get("id")))
    rows = list(client.table("simulation_sealed_product_results").select(
        "sealed_product_id,price_as_of,calculation_run_id"
    ).in_("calculation_run_id", latest_run_ids).execute().data or []) if latest_run_ids else []
    expected = {str(row.get("sealed_product_id")) for row in rows}
    stale = sorted({str(row.get("sealed_product_id")) for row in rows
                    if str(row.get("price_as_of")) != target_market_date})
    dates = sorted(str(row.get("price_as_of")) for row in rows if row.get("price_as_of"))
    ready = bool(rows) and not stale
    return SealedMarketAuthorityReport(
        ready=ready, reason_code="READY" if ready else SEALED_RESULT_DATE_MISMATCH,
        target_market_date=target_market_date, expected_product_count=len(expected),
        verified_product_count=len(expected) - len(stale), stale_product_count=len(stale),
        missing_product_count=0, stale_product_ids=stale,
        min_price_as_of=dates[0] if dates else None, max_price_as_of=dates[-1] if dates else None,
        query_count=2,
    )
