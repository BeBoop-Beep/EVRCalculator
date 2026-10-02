"""FV-S3 append-only forward-outcome collector.

Research-only. No provider calls and no anchor mutation.

For each prospective shadow publication:
1. recover/freeze the exact horizon-0 TCGplayer condition binding only when the
   published H0 price maps to exactly one card_variant_price_observations row;
2. for due horizons +1/+7/+30, read that SAME card_variant_id + condition_id +
   source + USD observation on the exact comparison date;
3. append an immutable outcome through the existing shadow ledger.

Ambiguous or missing H0 bindings fail closed and are reported. Missing future
prices become MARKET_MISSING outcomes; they are never imputed.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import sys
from collections import Counter, defaultdict
from datetime import date, timedelta
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any, Iterable, Mapping
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.scripts import index_fair_value_shadow_evaluation_v1 as evaluation
from backend.scripts import index_fair_value_shadow_ledger_v1 as ledger_mod

BINDING_SCHEMA_VERSION = "fv_shadow_market_binding_v1"
BINDING_METHOD = "UNIQUE_H0_EXACT_PRICE_MATCH_V1"
PRICE_SOURCE = "TCGPlayer"
PHOENIX = ZoneInfo("America/Phoenix")
FORWARD_HORIZONS = (1, 7, 30)


class ForwardOutcomeError(RuntimeError):
    pass


def _chunks(values: list[str], size: int = 50) -> Iterable[list[str]]:
    for i in range(0, len(values), size):
        yield values[i:i + size]


def _fp(value: Mapping[str, Any]) -> str:
    raw = json.dumps(dict(value), sort_keys=True, separators=(",", ":"), ensure_ascii=True, default=str)
    return hashlib.sha256(raw.encode()).hexdigest()


def _positive(value: Any) -> float | None:
    try:
        out = float(value)
    except (TypeError, ValueError):
        return None
    return out if math.isfinite(out) and out > 0 else None


def _money(value: Any) -> Decimal | None:
    try:
        out = Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        return None
    return out if out.is_finite() and out > 0 else None


def fetch_publications(db: Any, today: date) -> list[dict[str, Any]]:
    start = today - timedelta(days=max(FORWARD_HORIZONS))
    rows = (
        db.table("fair_value_shadow_anchor_publications_v1")
        .select("publication_id,canonical_card_id,card_variant_id,evaluation_date,median,status,evidence_status")
        .eq("evidence_status", "PROSPECTIVE_AS_KNOWN_AT_CUTOFF")
        .gte("evaluation_date", start.isoformat())
        .lte("evaluation_date", today.isoformat())
        .order("evaluation_date").order("canonical_card_id")
        .execute().data or []
    )
    return [dict(r) for r in rows]


def fetch_h0(db: Any, publication_ids: list[str]) -> dict[str, dict[str, Any]]:
    out: dict[str, dict[str, Any]] = {}
    for chunk in _chunks(publication_ids):
        rows = (
            db.table("fair_value_shadow_evaluation_outcomes_v1")
            .select("publication_id,horizon_days,comparison_date,comparison_market_price_usd,comparison_price_source,outcome_status")
            .in_("publication_id", chunk).eq("horizon_days", 0).execute().data or []
        )
        for row in rows:
            out[str(row["publication_id"])] = dict(row)
    return out


def fetch_existing_bindings(db: Any, publication_ids: list[str]) -> dict[str, dict[str, Any]]:
    out: dict[str, dict[str, Any]] = {}
    for chunk in _chunks(publication_ids):
        rows = db.table("fair_value_shadow_market_bindings_v1").select("*").in_("publication_id", chunk).execute().data or []
        for row in rows:
            out[str(row["publication_id"])] = dict(row)
    return out


def derive_binding(db: Any, publication: Mapping[str, Any], h0: Mapping[str, Any]) -> dict[str, Any]:
    price = _positive(h0.get("comparison_market_price_usd"))
    if price is None:
        raise ForwardOutcomeError("H0_MARKET_PRICE_MISSING")
    source = str(h0.get("comparison_price_source") or PRICE_SOURCE)
    target_money = _money(h0.get("comparison_market_price_usd"))
    rows = (
        db.table("card_variant_price_observations")
        .select("card_variant_id,condition_id,market_price,captured_at,source,currency")
        .eq("card_variant_id", publication["card_variant_id"])
        .eq("captured_at", publication["evaluation_date"])
        .eq("source", source)
        .eq("currency", "USD")
        .execute().data or []
    )
    unique = {
        (str(r["condition_id"]), str(r["card_variant_id"]), str(r["captured_at"])[:10], str(r["source"]), _money(r.get("market_price")))
        for r in rows if r.get("condition_id") and _money(r.get("market_price")) == target_money
    }
    if len(unique) != 1:
        raise ForwardOutcomeError(f"H0_BINDING_CARDINALITY_{len(unique)}")
    condition_id, variant_id, baseline_date, bound_source, bound_money = next(iter(unique))
    assert bound_money is not None
    bound_price = float(bound_money)
    record = {
        "publication_id": str(publication["publication_id"]),
        "schema_version": BINDING_SCHEMA_VERSION,
        "canonical_card_id": str(publication["canonical_card_id"]),
        "card_variant_id": variant_id,
        "condition_id": condition_id,
        "baseline_date": baseline_date,
        "baseline_market_price_usd": round(bound_price, 2),
        "price_source": bound_source,
        "currency": "USD",
        "binding_method": BINDING_METHOD,
    }
    return record


def read_bound_price(db: Any, binding: Mapping[str, Any], comparison_date: date) -> dict[str, Any] | None:
    rows = (
        db.table("card_variant_price_observations")
        .select("market_price,captured_at,source,currency,condition_id,card_variant_id")
        .eq("card_variant_id", binding["card_variant_id"])
        .eq("condition_id", binding["condition_id"])
        .eq("captured_at", comparison_date.isoformat())
        .eq("source", binding["price_source"])
        .eq("currency", "USD")
        .execute().data or []
    )
    prices = sorted({_positive(r.get("market_price")) for r in rows if _positive(r.get("market_price")) is not None})
    if len(prices) > 1:
        raise ForwardOutcomeError(f"BOUND_PRICE_AMBIGUOUS_{comparison_date.isoformat()}")
    if not prices:
        return None
    return {"market_price_usd": prices[0], "source": binding["price_source"]}


def _bound_price_key(binding: Mapping[str, Any], comparison_date: date) -> tuple[str, str, str, str]:
    return (
        str(binding["card_variant_id"]),
        str(binding["condition_id"]),
        comparison_date.isoformat(),
        str(binding["price_source"]),
    )


def fetch_bound_prices_batch(
    db: Any,
    due: Sequence[tuple[Mapping[str, Any], date]],
    *,
    chunk_size: int = 50,
) -> tuple[dict[tuple[str, str, str, str], float | None], set[tuple[str, str, str, str]], int]:
    """Fetch exact bound prices in date/source batches instead of one query per outcome."""
    requested = {_bound_price_key(binding, comparison_date) for binding, comparison_date in due}
    grouped: dict[tuple[str, str], set[str]] = defaultdict(set)
    for variant_id, _condition_id, day, source in requested:
        grouped[(day, source)].add(variant_id)

    price_sets: dict[tuple[str, str, str, str], set[float]] = defaultdict(set)
    requests = 0
    for (day, source), variant_ids in sorted(grouped.items()):
        ids = sorted(variant_ids)
        for i in range(0, len(ids), chunk_size):
            chunk = ids[i:i + chunk_size]
            rows = (
                db.table("card_variant_price_observations")
                .select("market_price,captured_at,source,currency,condition_id,card_variant_id")
                .in_("card_variant_id", chunk)
                .eq("captured_at", day)
                .eq("source", source)
                .eq("currency", "USD")
                .execute().data or []
            )
            requests += 1
            for row in rows:
                if not row.get("condition_id") or not row.get("card_variant_id"):
                    continue
                key = (
                    str(row["card_variant_id"]),
                    str(row["condition_id"]),
                    str(row.get("captured_at") or "")[:10],
                    str(row.get("source") or ""),
                )
                if key not in requested:
                    continue
                price = _positive(row.get("market_price"))
                if price is not None:
                    price_sets[key].add(price)

    ambiguous = {key for key, values in price_sets.items() if len(values) > 1}
    prices = {
        key: (next(iter(price_sets[key])) if key in price_sets and len(price_sets[key]) == 1 else None)
        for key in requested
    }
    return prices, ambiguous, requests


def fetch_existing_outcomes(db: Any, publication_ids: list[str]) -> set[tuple[str, int]]:
    out: set[tuple[str, int]] = set()
    for chunk in _chunks(publication_ids):
        rows = db.table("fair_value_shadow_evaluation_outcomes_v1").select("publication_id,horizon_days").in_("publication_id", chunk).execute().data or []
        out.update((str(r["publication_id"]), int(r["horizon_days"])) for r in rows)
    return out


def fetch_completed_market_dates(db: Any, *, start: date, end: date) -> set[str]:
    """Dates whose authoritative daily scrape batch is complete.

    Forward outcomes are append-only. A missing price must therefore never be recorded
    while that comparison day's source batch is still incomplete or absent; otherwise a
    scheduling delay would become permanent research evidence.
    """
    rows = (
        db.table("pokemon_scrape_batches")
        .select("market_date,status")
        .gte("market_date", start.isoformat())
        .lte("market_date", end.isoformat())
        .eq("status", "complete")
        .execute().data or []
    )
    return {str(r["market_date"])[:10] for r in rows if r.get("market_date")}


def collect(*, db: Any, ledger: Any, today: date, dry_run: bool = False, bindings_only: bool = False) -> dict[str, Any]:
    publications = fetch_publications(db, today)
    ids = [str(p["publication_id"]) for p in publications]
    h0_by = fetch_h0(db, ids)
    bindings = fetch_existing_bindings(db, ids)
    existing_outcomes = fetch_existing_outcomes(db, ids)
    completed_market_dates = fetch_completed_market_dates(
        db, start=today - timedelta(days=max(FORWARD_HORIZONS)), end=today
    )
    binding_status = Counter()
    outcome_status = Counter()
    binding_failures: list[dict[str, str]] = []
    outcome_failures: list[dict[str, str]] = []

    if dry_run:
        # Dry-run still derives exact bindings/prices, but writes nowhere.
        binding_writer = None
        outcome_ledger = ledger_mod.InMemoryShadowLedger()
        for p in publications:
            outcome_ledger._by_id[str(p["publication_id"])] = dict(p)  # isolated test-only ledger seed
    else:
        binding_writer = ledger
        outcome_ledger = ledger

    bound_publications: list[tuple[dict[str, Any], dict[str, Any]]] = []
    for pub in publications:
        pid = str(pub["publication_id"])
        binding = bindings.get(pid)
        if binding is None:
            h0 = h0_by.get(pid)
            if h0 is None:
                binding_failures.append({"publication_id": pid, "reason": "H0_OUTCOME_MISSING"})
                continue
            try:
                binding = derive_binding(db, pub, h0)
            except ForwardOutcomeError as exc:
                binding_failures.append({"publication_id": pid, "reason": str(exc)})
                continue
            if dry_run:
                binding_status["WOULD_INSERT"] += 1
            else:
                binding_status[binding_writer.append_market_binding(binding)] += 1
            bindings[pid] = binding
        else:
            binding_status["EXISTING"] += 1
        bound_publications.append((pub, binding))

    due_items: list[tuple[dict[str, Any], dict[str, Any], int, date]] = []
    if not bindings_only:
        for pub, binding in bound_publications:
            pid = str(pub["publication_id"])
            for horizon in FORWARD_HORIZONS:
                key = (pid, horizon)
                comparison_date = date.fromisoformat(str(pub["evaluation_date"])[:10]) + timedelta(days=horizon)
                if comparison_date > today or key in existing_outcomes:
                    continue
                if comparison_date.isoformat() not in completed_market_dates:
                    outcome_status["DEFERRED_BATCH_NOT_COMPLETE"] += 1
                    continue
                due_items.append((pub, binding, horizon, comparison_date))

    due_prices, ambiguous_keys, price_select_requests = fetch_bound_prices_batch(
        db, [(binding, comparison_date) for _pub, binding, _horizon, comparison_date in due_items]
    )

    for pub, binding, horizon, comparison_date in due_items:
        pid = str(pub["publication_id"])
        price_key = _bound_price_key(binding, comparison_date)
        if price_key in ambiguous_keys:
            outcome_failures.append({
                "publication_id": pid,
                "horizon": str(horizon),
                "reason": f"ForwardOutcomeError:BOUND_PRICE_AMBIGUOUS_{comparison_date.isoformat()}",
            })
            continue
        baseline = _positive(binding.get("baseline_market_price_usd"))
        market_price = due_prices.get(price_key)
        try:
            outcome = evaluation.build_evaluation_outcome(
                pub,
                {
                    "horizon_days": horizon,
                    "comparison_date": comparison_date.isoformat(),
                    "market_price_usd": market_price,
                    "source": binding["price_source"],
                },
                baseline_market_price_usd=baseline,
                today=today,
            )
            if dry_run:
                outcome_status["WOULD_INSERT_" + outcome["outcome_status"]] += 1
            else:
                outcome_status[outcome_ledger.append_outcome(outcome)] += 1
        except Exception as exc:
            outcome_failures.append({
                "publication_id": pid,
                "horizon": str(horizon),
                "reason": type(exc).__name__ + ":" + str(exc)[:180],
            })

    return {
        "status": "DRY_RUN" if dry_run else "COMPLETE",
        "today": today.isoformat(),
        "bindings_only": bindings_only,
        "publication_count": len(publications),
        "binding_statuses": dict(binding_status),
        "binding_failures": binding_failures,
        "outcome_statuses": dict(outcome_status),
        "outcome_failures": outcome_failures,
        "bound_price_select_requests": price_select_requests,
        "provider_calls": 0,
        "provider_credits_used": 0,
        "anchor_writes": 0,
        "public_price_writes": 0,
    }

def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--dry-run", action="store_true")
    mode.add_argument("--commit", action="store_true")
    parser.add_argument("--today", type=date.fromisoformat, default=None)
    parser.add_argument("--bindings-only", action="store_true")
    args = parser.parse_args(argv)

    from backend.db.clients.supabase_client import create_service_role_client
    db = create_service_role_client()
    ledger = ledger_mod.SupabaseShadowLedger(db)
    today = args.today or __import__("datetime").datetime.now(PHOENIX).date()
    result = collect(
        db=db, ledger=ledger, today=today, dry_run=args.dry_run, bindings_only=args.bindings_only
    )
    print(json.dumps(result, indent=2, sort_keys=True, default=str))
    return 0 if not result["binding_failures"] and not result["outcome_failures"] else 3


if __name__ == "__main__":
    raise SystemExit(main())
