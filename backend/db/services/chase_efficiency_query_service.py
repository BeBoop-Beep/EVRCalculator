"""Premium read projection for the published Chase Efficiency snapshot."""
from __future__ import annotations

import math
import time
from typing import Any, Dict, Optional
from uuid import UUID

from backend.rankings.public_relative import public_rank_tier

SORT_COLUMNS = {
    "chase_efficiency": "chase_efficiency", "rank": "overall_rank",
    "price": "current_near_mint_market_price", "name": "card_name",
    "pull_probability": "exact_pull_probability",
    "chase_spend_50": "chase_spend_50", "cost_multiple_50": "cost_multiple_50",
}
_LATEST_POINTER_TTL_SECONDS = 30.0
_LATEST_POINTER_CACHE: Dict[int, tuple[float, Dict[str, Any]]] = {}


def _latest_snapshot(client: Any) -> Optional[Dict[str, Any]]:
    cache_key = id(client)
    cached = _LATEST_POINTER_CACHE.get(cache_key)
    now = time.monotonic()
    if cached and cached[0] > now:
        return dict(cached[1])
    response = (client.table("pokemon_card_chase_efficiency_latest")
                .select("snapshot_id,market_date").order("market_date", desc=True).limit(1).execute())
    rows = list(response.data or [])
    latest = rows[0] if rows else None
    if latest:
        _LATEST_POINTER_CACHE[cache_key] = (now + _LATEST_POINTER_TTL_SECONDS, dict(latest))
    return latest


def _public_row(row: Dict[str, Any]) -> Dict[str, Any]:
    probability = float(row["exact_pull_probability"]) if row.get("exact_pull_probability") is not None else None
    market_price = float(row["current_near_mint_market_price"]) if row.get("current_near_mint_market_price") is not None else None
    pack_cost = float(row["best_verified_pack_equivalent_cost"]) if row.get("best_verified_pack_equivalent_cost") is not None else None
    packs_at_buy_price = math.floor(market_price / pack_cost) if market_price and pack_cost else None
    chance_at_buy_price = (1.0 - ((1.0 - probability) ** packs_at_buy_price)) if probability and packs_at_buy_price is not None else None
    overall_rank = row.get("overall_rank"); overall_size = row.get("overall_cohort_size")
    return {
        "cardVariantId": row.get("card_variant_id"), "canonicalCardId": row.get("canonical_card_id"),
        "setId": row.get("set_id"), "eraId": row.get("era_id"), "cardName": row.get("card_name"),
        "rarity": row.get("canonical_rarity"), "printingType": row.get("printing_type"),
        "specialType": row.get("special_type"), "artwork": row.get("artwork"),
        "exactPullProbability": row.get("exact_pull_probability"),
        "currentNearMintMarketPrice": row.get("current_near_mint_market_price"),
        "cardPriceAsOf": row.get("card_price_as_of"), "chaseEfficiency": row.get("chase_efficiency"),
        "bestVerifiedPackEquivalentCost": row.get("best_verified_pack_equivalent_cost"),
        "looseBoosterPackPrice": row.get("loose_booster_pack_price"),
        "chosenProduct": {"sealedProductId": row.get("chosen_sealed_product_id"), "family": row.get("chosen_product_family"),
                          "name": row.get("chosen_product_name"), "price": row.get("chosen_product_price"),
                          "randomPackCount": row.get("chosen_random_pack_count"), "priceAsOf": row.get("chosen_product_price_as_of"),
                          "priceSource": row.get("chosen_product_price_source")},
        "milestones": row.get("milestones_json"),
        "chaseSpend50": row.get("chase_spend_50"), "costMultiple50": row.get("cost_multiple_50"),
        "packsAtBuyPrice": packs_at_buy_price, "chanceAtBuyPrice": chance_at_buy_price,
        "topPercent": (100.0 * int(overall_rank) / int(overall_size)) if overall_rank and overall_size else None,
        "tier": public_rank_tier(overall_rank, overall_size),
        "ranks": {scope: {"rank": row.get(f"{scope}_rank"), "cohortSize": row.get(f"{scope}_cohort_size")}
                  for scope in ("overall", "era", "set", "rarity")},
    }


def query_chase_efficiency(client: Any, *, page: int = 1, page_size: int = 50, search: Optional[str] = None,
                           era: Optional[str] = None, set_id: Optional[str] = None, rarity: Optional[str] = None,
                           min_price: Optional[float] = None, max_price: Optional[float] = None,
                           sort: str = "rank", direction: str = "asc") -> Dict[str, Any]:
    page = max(1, int(page)); page_size = min(100, max(1, int(page_size)))
    sort_column = SORT_COLUMNS.get(str(sort).lower())
    if not sort_column: raise ValueError("unsupported sort")
    direction = str(direction).lower()
    if direction not in {"asc", "desc"}: raise ValueError("direction must be asc or desc")
    latest = _latest_snapshot(client)
    if not latest: return {"available": False, "reason": "no_published_snapshot", "rows": []}
    query = client.table("pokemon_card_chase_efficiency_rows").select("*", count="exact").eq("snapshot_id", latest["snapshot_id"])
    if search: query = query.ilike("card_name", f"%{str(search).strip()[:100]}%")
    if era:
        try: era_id = str(UUID(str(era)))
        except ValueError:
            era_rows = list(client.table("eras").select("id").eq("canonical_key", str(era)).limit(1).execute().data or [])
            if not era_rows:
                era_rows = list(client.table("eras").select("id").eq("name", str(era)).limit(1).execute().data or [])
            era_id = str(era_rows[0]["id"]) if era_rows else "00000000-0000-0000-0000-000000000000"
        query = query.eq("era_id", era_id)
    if set_id: query = query.eq("set_id", set_id)
    if rarity: query = query.eq("canonical_rarity", rarity)
    if min_price is not None:
        if not math.isfinite(float(min_price)) or float(min_price) < 0: raise ValueError("invalid minimum price")
        query = query.gte("current_near_mint_market_price", float(min_price))
    if max_price is not None:
        if not math.isfinite(float(max_price)) or float(max_price) < 0: raise ValueError("invalid maximum price")
        query = query.lte("current_near_mint_market_price", float(max_price))
    if min_price is not None and max_price is not None and float(min_price) > float(max_price): raise ValueError("minimum price exceeds maximum")
    start = (page - 1) * page_size
    response = query.order(sort_column, desc=direction == "desc").order("card_variant_id").range(start, start + page_size - 1).execute()
    total = int(getattr(response, "count", None) or 0)
    return {"available": True, "marketDate": latest["market_date"], "page": page, "pageSize": page_size,
            "total": total, "totalPages": math.ceil(total / page_size) if total else 0,
            "rows": [_public_row(row) for row in (response.data or [])]}


def get_card_chase_efficiency(client: Any, *, set_id: str, card_id: str, variant_id: Optional[str]) -> Dict[str, Any]:
    latest = _latest_snapshot(client)
    if not latest: return {"available": False, "reason": "no_published_snapshot"}
    query = (client.table("pokemon_card_chase_efficiency_rows").select("*")
             .eq("snapshot_id", latest["snapshot_id"]).eq("set_id", set_id).eq("canonical_card_id", card_id))
    if variant_id: query = query.eq("card_variant_id", variant_id)
    response = query.order("overall_rank").limit(1).execute(); rows = list(response.data or [])
    if not rows: return {"available": False, "reason": "card_or_variant_not_ranked"}
    return {"available": True, "marketDate": latest["market_date"], "row": _public_row(rows[0])}
