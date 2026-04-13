"""Low-level Supabase access for the three holdings tables.

All writes are scoped to both `id` AND `user_id` so that the service-role
client cannot mutate a row on behalf of the wrong owner.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, Optional

from backend.db.clients.supabase_client import supabase

logger = logging.getLogger(__name__)

# ─── table + column map ──────────────────────────────────────────────────────

_TABLE: Dict[str, str] = {
    "card": "user_card_holdings",
    "sealed_product": "user_sealed_product_holdings",
    "graded_card": "user_graded_card_holdings",
}

_SELECT_COLS = "id, user_id, quantity"


# ─── public helpers ──────────────────────────────────────────────────────────


def _table_for(holding_type: str) -> str:
    table = _TABLE.get(holding_type)
    if not table:
        raise ValueError(f"Unknown holding_type: {holding_type!r}")
    return table


def _first_row(result: Any) -> Optional[Dict[str, Any]]:
    data = getattr(result, "data", None)
    if isinstance(data, list):
        return data[0] if data else None
    return None


# ─── read ─────────────────────────────────────────────────────────────────────


def get_holding(holding_type: str, holding_id: str, user_id: str) -> Optional[Dict[str, Any]]:
    """Return the holding row if it belongs to *user_id*, else None."""
    table = _table_for(holding_type)
    result = (
        supabase.table(table)
        .select(_SELECT_COLS)
        .eq("id", holding_id)
        .eq("user_id", user_id)
        .limit(1)
        .execute()
    )
    return _first_row(result)


# ─── write ────────────────────────────────────────────────────────────────────


def update_holding_quantity(
    holding_type: str,
    holding_id: str,
    user_id: str,
    new_quantity: int,
) -> Optional[Dict[str, Any]]:
    """Set quantity on a holding.  Ownership is enforced by the WHERE clause."""
    table = _table_for(holding_type)
    result = (
        supabase.table(table)
        .update({"quantity": new_quantity})
        .eq("id", holding_id)
        .eq("user_id", user_id)
        .execute()
    )
    return _first_row(result)


def delete_holding(
    holding_type: str,
    holding_id: str,
    user_id: str,
) -> bool:
    """Delete a holding row.  Returns True if a row was affected."""
    table = _table_for(holding_type)
    result = (
        supabase.table(table)
        .delete()
        .eq("id", holding_id)
        .eq("user_id", user_id)
        .execute()
    )
    data = getattr(result, "data", None)
    return isinstance(data, list) and len(data) > 0
