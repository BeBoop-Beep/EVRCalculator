"""Canonical exact-printing Chase Efficiency mathematics and ranking.

This module is deliberately pure.  It consumes already-authoritative card and
sealed-product rows; authority resolution and publication live in the service
layer.  The persisted value is the raw economic quantity, never a display
score.
"""

from __future__ import annotations

import hashlib
import json
import math
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence, Tuple

from backend.domain.pokemon.rip_decision_metrics import packs_for_cumulative_probability

CHASE_EFFICIENCY_CONTRACT_VERSION = "pokemon-chase-efficiency-v1"
CHASE_EFFICIENCY_METHODOLOGY_VERSION = "value-times-hit-hazard-over-best-pack-cost-v1"
CHASE_EFFICIENCY_PRICING_BASIS_VERSION = "best-verified-pack-equivalent-cost-v1"
CHASE_EFFICIENCY_THRESHOLDS = (0.50, 0.75, 0.90, 0.95)
PRECISION = 12


def finite_positive(value: Any) -> Optional[float]:
    if value is None or isinstance(value, bool):
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) and number > 0.0 else None


def valid_probability(value: Any) -> Optional[float]:
    number = finite_positive(value)
    return number if number is not None and number <= 1.0 else None


def probability_from_effective_pull_rate(value: Any) -> Optional[float]:
    """Convert the repository's one-in-N denominator into exact-pack p."""
    denominator = finite_positive(value)
    if denominator is None:
        return None
    return valid_probability(1.0 / denominator)


def chase_efficiency(*, target_value: Any, pack_cost: Any, probability: Any) -> Optional[float]:
    value = finite_positive(target_value)
    cost = finite_positive(pack_cost)
    p = valid_probability(probability)
    if value is None or cost is None or p is None:
        return None
    # log1p is stable for very small probabilities. p=1 has infinite hazard
    # and therefore infinite CE, which cannot be persisted; refuse it.
    hazard = -math.log1p(-p) if p < 1.0 else math.inf
    result = (value / cost) * hazard
    return round(result, PRECISION) if math.isfinite(result) else None


def packs_for_threshold(probability: Any, threshold: float) -> Optional[int]:
    return packs_for_cumulative_probability(valid_probability(probability), threshold)


def verified_product_route(product: Mapping[str, Any], probability: Any) -> Optional[Dict[str, Any]]:
    price = finite_positive(product.get("product_price"))
    pack_count_value = finite_positive(product.get("random_pack_count"))
    p = valid_probability(probability)
    if price is None or pack_count_value is None or p is None:
        return None
    pack_count = int(pack_count_value)
    if pack_count <= 0 or float(pack_count) != pack_count_value or not product.get("composition_verified", False):
        return None
    p_product = 1.0 - ((1.0 - p) ** pack_count)
    if not 0.0 < p_product <= 1.0:
        return None
    thresholds: Dict[str, Any] = {}
    for q in CHASE_EFFICIENCY_THRESHOLDS:
        products = packs_for_threshold(p_product, q)
        key = str(int(q * 100))
        thresholds[key] = {
            "productsNeeded": products,
            "spend": None if products is None else round(products * price, PRECISION),
        }
    return {
        **dict(product),
        "product_price": price,
        "random_pack_count": pack_count,
        "pack_equivalent_cost": round(price / pack_count, PRECISION),
        "product_probability": round(p_product, PRECISION),
        "thresholds": thresholds,
    }


def calculate_row(card: Mapping[str, Any], products: Sequence[Mapping[str, Any]]) -> Tuple[Optional[Dict[str, Any]], Optional[str]]:
    variant_id = str(card.get("card_variant_id") or "").strip()
    if not variant_id:
        return None, "insufficient_variant_identity"
    if not card.get("set_id"):
        return None, "missing_set_identity"
    p = valid_probability(card.get("probability"))
    if p is None:
        return None, "invalid_exact_pull_probability"
    value = finite_positive(card.get("current_market_price"))
    if value is None:
        return None, "missing_or_invalid_near_mint_price"
    if not card.get("price_is_fresh", False):
        return None, "stale_near_mint_price"
    if not card.get("canonical_card_id"):
        return None, "unmapped_canonical_card_identity"

    routes = [route for product in products if (route := verified_product_route(product, p))]
    if not routes:
        return None, "no_verified_current_opening_route"
    best = min(routes, key=lambda r: (r["pack_equivalent_cost"], str(r.get("sealed_product_id") or "")))
    ce = chase_efficiency(target_value=value, pack_cost=best["pack_equivalent_cost"], probability=p)
    if ce is None:
        return None, "non_finite_chase_efficiency"

    milestones: Dict[str, Any] = {}
    for q in CHASE_EFFICIENCY_THRESHOLDS:
        key = str(int(q * 100))
        valid = [r for r in routes if r["thresholds"][key]["spend"] is not None]
        cheapest = min(valid, key=lambda r: (r["thresholds"][key]["spend"], str(r.get("sealed_product_id") or "")))
        milestones[key] = {
            "packsNeeded": packs_for_threshold(p, q),
            "sealedProductId": cheapest.get("sealed_product_id"),
            "productName": cheapest.get("product_name"),
            "productFamily": cheapest.get("product_family"),
            **cheapest["thresholds"][key],
        }

    return {
        **dict(card),
        "card_variant_id": variant_id,
        "probability": p,
        "current_market_price": value,
        "chase_efficiency": ce,
        "best_verified_pack_equivalent_cost": best["pack_equivalent_cost"],
        "loose_booster_pack_price": finite_positive(card.get("loose_booster_pack_price")),
        "chosen_sealed_product_id": best.get("sealed_product_id"),
        "chosen_product_family": best.get("product_family"),
        "chosen_product_name": best.get("product_name"),
        "chosen_product_price": best.get("product_price"),
        "chosen_random_pack_count": best.get("random_pack_count"),
        "chosen_product_price_source": best.get("price_source"),
        "chosen_product_price_as_of": best.get("price_as_of"),
        "milestones": milestones,
        "verified_routes": routes,
    }, None


def _rank(rows: List[Dict[str, Any]], key: str, cohort_fields: Sequence[str]) -> None:
    groups: Dict[Tuple[str, ...], List[Dict[str, Any]]] = {}
    for row in rows:
        cohort = tuple(str(row.get(field) or "") for field in cohort_fields)
        groups.setdefault(cohort, []).append(row)
    for members in groups.values():
        members.sort(key=lambda r: (-r["chase_efficiency"], -r["current_market_price"], r["card_variant_id"]))
        size = len(members)
        for index, row in enumerate(members, 1):
            row[f"{key}_rank"] = index
            row[f"{key}_cohort_size"] = size


def rank_rows(rows: Iterable[Mapping[str, Any]]) -> List[Dict[str, Any]]:
    ranked = [dict(row) for row in rows]
    _rank(ranked, "overall", ())
    _rank(ranked, "era", ("era_id",))
    _rank(ranked, "set", ("set_id",))
    _rank(ranked, "rarity", ("canonical_rarity",))
    return sorted(ranked, key=lambda r: r["overall_rank"])


def fingerprint(value: Any) -> str:
    encoded = json.dumps(value, sort_keys=True, separators=(",", ":"), default=str).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()
