"""Business logic for mutating collection holdings.

Supported actions:
  • increment — add 1 unit to an existing holding
  • decrement — subtract 1 unit (minimum 1; caller must handle 1→0 confirmation)
  • remove    — delete the holding row entirely

All functions return a tuple: (result_dict | None, error_dict | None).
A non-None error_dict always carries {"message": str, "status": int}.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, Optional, Tuple

from backend.db.repositories.holdings_repository import (
    delete_holding,
    get_holding,
    update_holding_quantity,
)

logger = logging.getLogger(__name__)

_VALID_TYPES = {"card", "sealed_product", "graded_card"}
_VALID_ACTIONS = {"increment", "decrement", "remove"}


def _err(message: str, status: int) -> Tuple[None, Dict[str, Any]]:
    return None, {"message": message, "status": status}


def mutate_holding(
    user_id: str,
    holding_type: str,
    holding_id: str,
    action: str,
) -> Tuple[Optional[Dict[str, Any]], Optional[Dict[str, Any]]]:
    """Apply *action* to a holding owned by *user_id*.

    Returns (result, None) on success or (None, error_dict) on failure.
    """
    # ── input validation ──────────────────────────────────────────────────
    if not user_id:
        return _err("Not authenticated.", 401)
    if holding_type not in _VALID_TYPES:
        return _err(f"Invalid holding_type '{holding_type}'.", 400)
    if action not in _VALID_ACTIONS:
        return _err(f"Invalid action '{action}'.", 400)
    if not holding_id:
        return _err("holding_id is required.", 400)

    # ── ownership check ───────────────────────────────────────────────────
    row = get_holding(holding_type, holding_id, user_id)
    if row is None:
        return _err("Holding not found or access denied.", 404)

    current_qty = int(row.get("quantity") or 0)

    # ── apply action ──────────────────────────────────────────────────────
    if action == "remove":
        deleted = delete_holding(holding_type, holding_id, user_id)
        if not deleted:
            return _err("Failed to remove holding.", 500)
        return {"action": "removed", "holding_id": holding_id}, None

    if action == "increment":
        new_qty = current_qty + 1
        update_holding_quantity(holding_type, holding_id, user_id, new_qty)
        return {"action": "incremented", "holding_id": holding_id, "quantity": new_qty}, None

    if action == "decrement":
        # Safety floor: never go below 1 via decrement (remove must be used for 1→0)
        if current_qty <= 1:
            return _err(
                "Use action='remove' to delete the last unit of a holding.",
                422,
            )
        new_qty = current_qty - 1
        update_holding_quantity(holding_type, holding_id, user_id, new_qty)
        return {"action": "decremented", "holding_id": holding_id, "quantity": new_qty}, None

    # unreachable
    return _err("Unhandled action.", 500)
