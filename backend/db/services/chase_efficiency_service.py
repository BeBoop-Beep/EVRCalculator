"""Build and atomically publish the canonical Chase Efficiency snapshot."""

from __future__ import annotations

from collections import Counter
from datetime import datetime, timezone
import json
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence, Tuple

from backend.domain.pokemon.chase_efficiency import (
    CHASE_EFFICIENCY_CONTRACT_VERSION,
    CHASE_EFFICIENCY_METHODOLOGY_VERSION,
    CHASE_EFFICIENCY_PRICING_BASIS_VERSION,
    calculate_row,
    fingerprint,
    probability_from_effective_pull_rate,
    rank_rows,
)

PAGE_SIZE = 1000


def _rows(response: Any) -> List[Dict[str, Any]]:
    return list(getattr(response, "data", None) or [])


def _all(query: Any, *, limit: int = 100_000) -> List[Dict[str, Any]]:
    result: List[Dict[str, Any]] = []
    for start in range(0, limit, PAGE_SIZE):
        batch = _rows(query.range(start, start + PAGE_SIZE - 1).execute())
        result.extend(batch)
        if len(batch) < PAGE_SIZE:
            return result
    raise RuntimeError("Chase Efficiency source read exceeded safety limit")


def build_snapshot_from_inputs(
    *, market_date: str, cards: Iterable[Mapping[str, Any]],
    products_by_set: Mapping[str, Sequence[Mapping[str, Any]]],
    authoritative_run_ids: Mapping[str, str], supported_set_count: int,
    built_at: Optional[str] = None,
) -> Dict[str, Any]:
    """Build the complete candidate, retaining every exclusion reason."""
    eligible: List[Dict[str, Any]] = []
    excluded: List[Dict[str, Any]] = []
    source_cards = [dict(card) for card in cards]
    for card in source_cards:
        set_id = str(card.get("set_id") or "")
        run_id = str(card.get("source_calculation_run_id") or "")
        variant_id = card.get("card_variant_id")
        if not set_id or set_id not in authoritative_run_ids:
            reason = "set_not_in_supported_simulation_cohort"
        elif run_id != str(authoritative_run_ids[set_id]):
            reason = "not_authoritative_current_calculation_run"
        elif card.get("effective_pull_rate") is None:
            reason = "effective_pull_rate_unavailable"
        else:
            normalized = {**card, "probability": probability_from_effective_pull_rate(card.get("effective_pull_rate"))}
            row, reason = calculate_row(normalized, products_by_set.get(set_id, ()))
            if row is not None:
                eligible.append(row)
                continue
        excluded.append({
            "card_variant_id": variant_id,
            "set_id": set_id or None,
            "source_calculation_run_id": run_id or None,
            "reason": reason,
            "diagnostics": card.get("identity_diagnostics") or {},
        })

    ranked = rank_rows(eligible)
    now = built_at or datetime.now(timezone.utc).isoformat()
    source_run_fingerprint = fingerprint(sorted(authoritative_run_ids.items()))
    cohort_fingerprint = fingerprint([
        (row["card_variant_id"], row["chase_efficiency"], row["overall_rank"])
        for row in ranked
    ])
    exclusions = dict(sorted(Counter(row["reason"] for row in excluded).items()))
    snapshot = {
        "market_date": market_date,
        "built_at": now,
        "publication_status": "candidate",
        "contract_version": CHASE_EFFICIENCY_CONTRACT_VERSION,
        "calculation_methodology_version": CHASE_EFFICIENCY_METHODOLOGY_VERSION,
        "pricing_basis_version": CHASE_EFFICIENCY_PRICING_BASIS_VERSION,
        "eligible_cohort_count": len(ranked),
        "excluded_cohort_count": len(excluded),
        "supported_set_count": supported_set_count,
        "cohort_fingerprint": cohort_fingerprint,
        "source_run_fingerprint": source_run_fingerprint,
        "diagnostics_json": {
            "excludedCountByReason": exclusions,
            "excludedRows": excluded,
            "authoritativeRunIds": dict(sorted(authoritative_run_ids.items())),
        },
    }
    return {"snapshot": snapshot, "rows": ranked, "excluded": excluded}


def validate_candidate(candidate: Mapping[str, Any]) -> List[str]:
    """Fail-closed candidate audit; empty means PASS."""
    snapshot = candidate.get("snapshot") or {}
    rows = list(candidate.get("rows") or [])
    excluded = list(candidate.get("excluded") or [])
    failures: List[str] = []
    if len(rows) != snapshot.get("eligible_cohort_count"): failures.append("eligible count mismatch")
    if len(excluded) != snapshot.get("excluded_cohort_count"): failures.append("excluded count mismatch")
    try: json.dumps(candidate, allow_nan=False, default=str)
    except (TypeError, ValueError): failures.append("candidate contains NaN or Infinity")
    represented_sets = {str(row.get("set_id")) for row in [*rows, *excluded] if row.get("set_id")}
    if len(represented_sets) != snapshot.get("supported_set_count"): failures.append("supported set count mismatch")
    ids = [str(row.get("card_variant_id")) for row in rows]
    if len(ids) != len(set(ids)): failures.append("duplicate card_variant_id")
    if any(not row.get("reason") for row in excluded): failures.append("excluded row missing reason")
    for row in rows:
        for prefix in ("overall", "era", "set", "rarity"):
            rank, size = row.get(f"{prefix}_rank"), row.get(f"{prefix}_cohort_size")
            if not isinstance(rank, int) or not isinstance(size, int) or not 1 <= rank <= size:
                failures.append(f"{row.get('card_variant_id')}: invalid {prefix} rank")
        milestones = row.get("milestones") or {}
        packs = [milestones.get(q, {}).get("packsNeeded") for q in ("50", "75", "90", "95")]
        spends = [milestones.get(q, {}).get("spend") for q in ("50", "75", "90", "95")]
        if any(value is None for value in packs) or packs != sorted(packs): failures.append(f"{row.get('card_variant_id')}: non-monotonic thresholds")
        if any(value is None for value in spends) or spends != sorted(spends): failures.append(f"{row.get('card_variant_id')}: non-monotonic milestone spends")
        routes = row.get("verified_routes") or []
        if not routes: failures.append(f"{row.get('card_variant_id')}: missing verified routes"); continue
        minimum = min(route["pack_equivalent_cost"] for route in routes)
        if abs(minimum - row["best_verified_pack_equivalent_cost"]) > 1e-10: failures.append(f"{row.get('card_variant_id')}: pack cost is not minimum")
        for q in ("50", "75", "90", "95"):
            expected = min(route["thresholds"][q]["spend"] for route in routes)
            if abs(expected - milestones[q]["spend"]) > 1e-10: failures.append(f"{row.get('card_variant_id')}: {q}% route is not minimum")
        from backend.domain.pokemon.chase_efficiency import chase_efficiency
        reproduced = chase_efficiency(target_value=row["current_market_price"], pack_cost=row["best_verified_pack_equivalent_cost"], probability=row["probability"])
        if reproduced is None or abs(reproduced - row["chase_efficiency"]) > 1e-10: failures.append(f"{row.get('card_variant_id')}: CE reproduction failed")
        base = row["chase_efficiency"]
        if not chase_efficiency(target_value=row["current_market_price"] * 1.01, pack_cost=row["best_verified_pack_equivalent_cost"], probability=row["probability"]) > base:
            failures.append(f"{row.get('card_variant_id')}: target-value monotonicity failed")
        if row["probability"] < 1.0 and not chase_efficiency(target_value=row["current_market_price"], pack_cost=row["best_verified_pack_equivalent_cost"], probability=min(1.0 - 1e-15, row["probability"] * 1.01)) > base:
            failures.append(f"{row.get('card_variant_id')}: probability monotonicity failed")
        if not chase_efficiency(target_value=row["current_market_price"], pack_cost=row["best_verified_pack_equivalent_cost"] * 1.01, probability=row["probability"]) < base:
            failures.append(f"{row.get('card_variant_id')}: pack-cost monotonicity failed")
    for prefix, cohort_fields in (("overall", ()), ("era", ("era_id",)), ("set", ("set_id",)), ("rarity", ("canonical_rarity",))):
        cohorts: Dict[Tuple[str, ...], List[Dict[str, Any]]] = {}
        for row in rows: cohorts.setdefault(tuple(str(row.get(f) or "") for f in cohort_fields), []).append(row)
        for members in cohorts.values():
            if sorted(row[f"{prefix}_rank"] for row in members) != list(range(1, len(members) + 1)):
                failures.append(f"non-contiguous {prefix} ranks")
    return failures


def publish_candidate(client: Any, candidate: Mapping[str, Any]) -> str:
    failures = validate_candidate(candidate)
    if failures:
        raise ValueError("Chase Efficiency audit failed: " + "; ".join(failures))
    response = client.rpc("publish_pokemon_card_chase_efficiency_snapshot", {
        "p_snapshot": candidate["snapshot"], "p_rows": candidate["rows"],
    }).execute()
    data = getattr(response, "data", None)
    if isinstance(data, list): data = data[0] if data else None
    if not data: raise RuntimeError("Chase Efficiency publication RPC returned no snapshot id")
    return str(data)


def load_candidate(client: Any, *, market_date: str) -> Dict[str, Any]:
    """Resolve the promoted-date real-data authority and build one candidate."""
    set_rows = _all(client.table("sets").select("id,name,era_id,supports_opening_simulation").eq("supports_opening_simulation", True))
    supported = {str(row["id"]): row for row in set_rows}
    authority_rows = _all(client.table("explore_rip_statistics_latest").select("set_id,calculation_run_id"))
    authorities = {
        str(row["set_id"]): str(row["calculation_run_id"])
        for row in authority_rows
        if str(row.get("set_id") or "") in supported and row.get("calculation_run_id")
    }
    if set(supported) != set(authorities):
        missing = sorted(set(supported) - set(authorities))
        raise RuntimeError(f"supported sets missing authoritative run: {missing}")

    canonical_rows = _all(client.table("pokemon_canonical_cards").select("id,set_id,name,rarity"))
    # A direct price-projection read supplies the legacy-card bridge shared by
    # all exact variants of that card.
    canonical_prices = _all(client.table("pokemon_canonical_card_market_prices_latest").select("canonical_card_id,legacy_card_id"))
    canonical_by_id = {str(row["id"]): row for row in canonical_rows}
    canonical_by_legacy = {
        str(row["legacy_card_id"]): canonical_by_id.get(str(row["canonical_card_id"]), {})
        for row in canonical_prices if row.get("legacy_card_id")
    }
    variant_ids: set[str] = set()
    raw_cards: List[Dict[str, Any]] = []
    products_by_set: Dict[str, List[Dict[str, Any]]] = {}
    for set_id, run_id in authorities.items():
        source_cards = _all(client.table("simulation_input_cards_with_near_mint_price").select(
            "calculation_run_id,card_id,card_variant_id,card_name,effective_pull_rate,current_near_mint_price,current_near_mint_price_captured_at,current_near_mint_price_source"
        ).eq("calculation_run_id", run_id))
        for row in source_cards:
            variant_ids.add(str(row.get("card_variant_id") or ""))
            canonical = canonical_by_legacy.get(str(row.get("card_id") or ""), {})
            raw_cards.append({
                **row, "set_id": set_id, "source_calculation_run_id": run_id,
                "era_id": supported[set_id].get("era_id"),
                "canonical_card_id": canonical.get("id"),
                "canonical_rarity": canonical.get("rarity") or row.get("rarity_bucket") or "Unknown",
                "card_name": canonical.get("name") or row.get("card_name") or "Unknown",
                "current_market_price": row.get("current_near_mint_price"),
                "card_price_as_of": str(row.get("current_near_mint_price_captured_at") or "")[:10] or None,
                "card_price_source": row.get("current_near_mint_price_source"),
                "price_is_fresh": str(row.get("current_near_mint_price_captured_at") or "")[:10] == market_date,
            })
        source_products = _all(client.table("simulation_sealed_product_results").select(
            "calculation_run_id,set_id,sealed_product_id,product_name,product_family,product_market_cost,pack_count,random_pack_count,guaranteed_component_market_value,composition_id,composition_version,price_as_of,price_source"
        ).eq("calculation_run_id", run_id).eq("price_as_of", market_date))
        normalized_products: List[Dict[str, Any]] = []
        loose_prices: List[float] = []
        for row in source_products:
            random_count = row.get("random_pack_count")
            stage1 = random_count is None and row.get("guaranteed_component_market_value") is None
            count = row.get("pack_count") if stage1 else random_count
            verified = bool(count and float(count) > 0 and (stage1 or row.get("composition_id") or row.get("composition_version")))
            normalized = {
                "sealed_product_id": row.get("sealed_product_id"), "product_name": row.get("product_name"),
                "product_family": row.get("product_family"), "product_price": row.get("product_market_cost"),
                "random_pack_count": count, "composition_verified": verified,
                "price_as_of": row.get("price_as_of"), "price_source": row.get("price_source"),
            }
            normalized_products.append(normalized)
            if str(row.get("product_family") or "") in {"booster_pack", "loose_booster_pack"}:
                try: loose_prices.append(float(row["product_market_cost"]))
                except (TypeError, ValueError): pass
        products_by_set[set_id] = normalized_products
        loose = min((price for price in loose_prices if price > 0), default=None)
        for card in raw_cards:
            if card["set_id"] == set_id: card["loose_booster_pack_price"] = loose

    if variant_ids:
        # A single giant PostgREST `in` filter exceeds httpx's URL limit for
        # the full cohort. The table is small enough for one paged projection.
        variant_rows = _all(client.table("card_variants").select("id,printing_type,special_type,image_large_url,image_small_url"))
        variants = {str(row["id"]): row for row in variant_rows}
        for card in raw_cards:
            variant = variants.get(str(card.get("card_variant_id") or ""), {})
            card.update({"printing_type": variant.get("printing_type"), "special_type": variant.get("special_type"),
                         "artwork": variant.get("image_large_url") or variant.get("image_small_url")})
    return build_snapshot_from_inputs(
        market_date=market_date, cards=raw_cards, products_by_set=products_by_set,
        authoritative_run_ids=authorities, supported_set_count=len(supported),
    )
