"""Daily target selection: economically meaningful priority, adaptive request planning, deterministic order."""
from __future__ import annotations

import statistics
from datetime import date
from typing import Any, Mapping, Sequence

from backend.pricing_pipeline.contracts import DAILY_REQUEST_LIMIT, DEFAULT_REQUESTS_PER_TARGET, PLANNING_FRACTION, digest
from backend.scripts import p5b_cohort_builder as cb
from backend.scripts.index_fair_value_ebay_evidence_collector import generate_queries

SELECTOR_VERSION = "multi_source_daily_selector_p6_v1"
# Priority tiers (P6I). Lower tier fills first; each tier is capped so no single tier starves the rest, and any
# unused capacity is then spent in priority order.
TIER_NAMES = {1: "MISSING_PRICE_GAP", 2: "ECONOMICALLY_IMPORTANT", 3: "SOURCE_DISAGREEMENT_REFRESH",
              4: "STALE_OR_AGING_HIGH_IMPACT", 5: "MOVER", 6: "ROTATION"}
TIER_CAP_SHARE = {1: 0.35, 2: 0.30, 3: 0.10, 4: 0.10, 5: 0.10, 6: 1.0}
HIGH_VALUE_USD = 50.0
STALE_IMPACT_USD = 20.0
MOVER_MIN_USD, MOVER_MIN_CHANGE = 5.0, 0.20
LOW_RARITY = {"common", "uncommon", "promo", "energy", ""}


def measured_requests_per_target(history: Sequence[Mapping[str, Any]]) -> float:
    """Median Browse requests per target over completed runs (requests_attempted / target_count)."""
    ratios = [r["requests_attempted"] / r["target_count"] for r in history
              if r.get("target_count") and r.get("requests_attempted")]
    return float(statistics.median(ratios)) if ratios else DEFAULT_REQUESTS_PER_TARGET


def plan_capacity(remaining_requests: int, cost_per_target: float, fraction: float = PLANNING_FRACTION) -> int:
    budget = max(0, min(remaining_requests, DAILY_REQUEST_LIMIT))
    return int((budget * fraction) // max(cost_per_target, 1.0))


def _mover_variants(events: Sequence[Mapping[str, Any]]) -> set[str]:
    by: dict[str, list[float]] = {}
    for e in sorted(events, key=lambda x: (str(x["effective_date"]), str(x["id"]))):
        if e.get("market_price") is not None and float(e["market_price"]) > 0:
            by.setdefault(str(e["card_variant_id"]), []).append(float(e["market_price"]))
    return {v for v, p in by.items() if len(p) >= 2 and abs(p[-1] - p[0]) >= MOVER_MIN_USD and abs(p[-1] / p[0] - 1) >= MOVER_MIN_CHANGE}


def classify(row: Mapping[str, Any], resolved: Mapping[str, Any], disagreements: set[str], movers: set[str]) -> tuple[int, str] | None:
    """(tier, reason), or None when the card is not worth an eBay lookup today."""
    rarity = str(row.get("rarity") or "").casefold()
    price = row.get("tcgplayer_market_price")
    chase = row.get("structure") == "hit_special"
    if row["tcg_status"] == "missing":
        if not (resolved.get(row["canonical_card_id"]) or {}).get("variant_id"):
            return None  # identity gap: no source can price it, so never spend requests on it
        if row.get("opening_eligible") or chase:
            return 1, "MISSING_PRICE_OPENING_OR_CHASE"
        return (1, "MISSING_PRICE_RESOLVED_VARIANT") if rarity not in LOW_RARITY else None
    if price is None:
        return None
    if price >= HIGH_VALUE_USD or (chase and price >= 5):
        return 2, "HIGH_VALUE" if price >= HIGH_VALUE_USD else "CHASE_RARITY"
    if row["canonical_card_id"] in disagreements:
        return 3, "PRIOR_SOURCE_DISAGREEMENT"
    if row["tcg_status"] == "stale" and price >= STALE_IMPACT_USD:
        return 4, "STALE_OR_AGING_HIGH_IMPACT"
    if row.get("card_variant_id") in movers and price >= MOVER_MIN_USD:
        return 5, "RECENT_MOVER"
    if row.get("opening_eligible") and rarity not in LOW_RARITY:
        return 6, "ROTATION"
    return None


def _to_target(row: Mapping[str, Any], tier: int, reason: str, variant: str | None) -> dict[str, Any]:
    return {
        "canonical_card_id": row["canonical_card_id"], "card_variant_id": variant or row.get("card_variant_id"),
        "card_name": row["card_name"], "card_number": row["card_number"], "set_id": row["set_id"], "set_name": row["set_name"],
        "era_id": row["era_id"], "rarity": row["rarity"], "priority_tier": tier, "priority_reason": reason,
        "tcgplayer_market_price": row.get("tcgplayer_market_price"), "tcgplayer_captured_at": row.get("tcgplayer_captured_at"),
        "tcg_status": row["tcg_status"],
    }


def plan_targets(universe: Sequence[Mapping[str, Any]], market_date: date, *, remaining_requests: int,
                 cost_per_target: float, resolved_variants: Mapping[str, Any] | None = None,
                 disagreements: set[str] | None = None, events: Sequence[Mapping[str, Any]] = ()) -> dict[str, Any]:
    resolved = resolved_variants or {}
    movers = _mover_variants(events)
    capacity = plan_capacity(remaining_requests, cost_per_target)
    buckets: dict[int, list[tuple]] = {t: [] for t in TIER_NAMES}
    for row in universe:
        if not cb.eligible_for_cohort(row):
            continue
        hit = classify(row, resolved, disagreements or set(), movers)
        if not hit:
            continue
        tier, reason = hit
        variant = (resolved.get(row["canonical_card_id"]) or {}).get("variant_id") if row["tcg_status"] == "missing" else None
        price = row.get("tcgplayer_market_price") or 0
        rotation = digest([SELECTOR_VERSION, market_date.isoformat(), row["canonical_card_id"]])
        # Tier 2 rotates by date so the whole important set is covered over days instead of re-buying the same top cards.
        buckets[tier].append(((-price if tier in (3, 4) else 0, rotation), _to_target(row, tier, reason, variant)))
    chosen: list[dict[str, Any]] = []
    taken: set[str] = set()
    for tier in sorted(TIER_NAMES):
        cap = capacity if tier == 6 else max(1, int(capacity * TIER_CAP_SHARE[tier]))
        for _, target in sorted(buckets[tier], key=lambda x: x[0])[:cap]:
            if len(chosen) < capacity:
                chosen.append(target)
                taken.add(target["canonical_card_id"])
    for tier in sorted(TIER_NAMES):
        for _, target in sorted(buckets[tier], key=lambda x: x[0]):
            if len(chosen) >= capacity:
                break
            if target["canonical_card_id"] not in taken:
                chosen.append(target)
                taken.add(target["canonical_card_id"])
    chosen.sort(key=lambda t: t["priority_tier"])  # stable sort keeps the within-tier order
    manifest = {
        "market_date": market_date.isoformat(), "selector_version": SELECTOR_VERSION, "target_count": len(chosen),
        "remaining_requests_at_plan": remaining_requests, "cost_per_target": round(cost_per_target, 3),
        "planned_capacity": capacity, "planning_fraction": PLANNING_FRACTION,
        "tier_counts": {TIER_NAMES[t]: sum(1 for x in chosen if x["priority_tier"] == t) for t in TIER_NAMES},
        "candidate_counts": {TIER_NAMES[t]: len(buckets[t]) for t in TIER_NAMES}, "cards": chosen,
    }
    manifest["selector_fingerprint"] = digest({k: v for k, v in manifest.items() if k != "selector_fingerprint"})
    return manifest


def verify_manifest(manifest: Mapping[str, Any]) -> bool:
    return digest({k: v for k, v in manifest.items() if k != "selector_fingerprint"}) == manifest.get("selector_fingerprint")


def with_queries(target: Mapping[str, Any]) -> dict[str, Any]:
    enriched = dict(target)
    enriched["planned_queries"] = generate_queries(enriched)
    return enriched
