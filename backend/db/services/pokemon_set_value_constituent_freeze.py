"""Freeze the exact leaf roster that produced a persisted Standard Set Value.

The rows passed in are the in-memory (canonical card -> selected physical
variant -> market price) rows the publication path already resolved. This
module never resolves, refetches or repairs anything: a reconciliation failure
from the database authority propagates (fail closed).
"""

from __future__ import annotations

import logging
from decimal import Decimal, ROUND_HALF_UP
from typing import Any, Iterable, Mapping

from backend.domain.pokemon.market_index import MARKET_INDEX_METHODOLOGY_VERSION

FREEZE_RPC = "replace_pokemon_market_set_value_constituents_v1"
FREEZE_SOURCE = "set_value_publication_frozen_roster_v1"
logger = logging.getLogger(__name__)


class SetValueConstituentFreezeError(RuntimeError):
    """Frozen-roster publication failed; the Raw surface must stay unavailable."""


def _money(value: Any) -> Decimal:
    return Decimal(str(value)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def build_freeze_items(rows: Iterable[Mapping[str, Any]]) -> list[dict[str, Any]]:
    """Shape exact in-memory selection rows into RPC items (no filtering/repair)."""
    items = []
    for row in rows:
        item = {
            "canonicalCardId": str(row["canonical_card_id"]),
            "cardVariantId": str(row["card_variant_id"]),
            "setId": str(row["set_id"]),
            "marketPrice": str(row["market_price"]),
        }
        captured = str(row.get("captured_at") or "")[:10]
        if captured:
            item["capturedAt"] = captured
        for out, key in (("source", "price_source"), ("printingType", "printing_type"),
                         ("priceSelectionReason", "price_selection_reason")):
            if row.get(key) or (key == "price_source" and row.get("source")):
                item[out] = str(row.get(key) or row.get("source"))
        items.append(item)
    return items


def freeze_set_value_constituents(
    client: Any, *, root_set_id: str, market_date: str, set_value: Any,
    items: list[dict[str, Any]], commit: bool,
    source: str = FREEZE_SOURCE,
    methodology_version: str = MARKET_INDEX_METHODOLOGY_VERSION,
) -> dict[str, Any]:
    """Persist the frozen roster via the DB authority. Dry-run performs zero calls."""
    day = str(market_date)[:10]
    if not commit:
        return {"status": "dry_run", "rootSetId": root_set_id, "marketDate": day,
                "itemCount": len(items), "rpcInvoked": False}
    # Local consistency only: never mutate/repair the roster.
    if _money(sum(_money(i["marketPrice"]) for i in items)) != _money(set_value):
        raise SetValueConstituentFreezeError(
            f"SET_VALUE_ROSTER_SUM_MISMATCH root={root_set_id} date={day}")
    args = {
        "p_root_set_id": root_set_id, "p_market_date": day,
        "p_methodology_version": methodology_version,
        "p_expected_set_value": str(_money(set_value)),
        "p_expected_card_count": len(items), "p_source": source, "p_items": items,
    }
    try:
        response = client.rpc(FREEZE_RPC, args).execute()
    except Exception as exc:
        logger.error("set_value_frozen_roster_failed", extra={
            "root_set_id": root_set_id, "market_date": day,
            "expected_card_count": len(items), "error": str(exc)[:300]})
        raise SetValueConstituentFreezeError(
            f"frozen Set Value roster rejected for root={root_set_id} date={day}: {exc}") from exc
    logger.info("set_value_frozen_roster_published", extra={
        "root_set_id": root_set_id, "market_date": day, "card_count": len(items)})
    return {"status": "published", "rootSetId": root_set_id, "marketDate": day,
            "itemCount": len(items), "rpcInvoked": True,
            "receipt": getattr(response, "data", None)}
