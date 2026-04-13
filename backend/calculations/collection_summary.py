"""Collection summary calculation entry points.

This module defines the calculation layer contract for collection summary metrics.
Database access and item retrieval are intentionally handled outside this module.
"""

from typing import Any, Dict, List, Optional

from backend.models.collection_summary_models import CollectionSummary


def _to_positive_int(value: object) -> int:
    """Convert value to a non-negative integer quantity."""
    if isinstance(value, bool):
        return 0
    if isinstance(value, (int, float)):
        return int(value) if value > 0 else 0
    return 0


def _to_non_negative_float(value: object) -> float:
    """Convert value to a non-negative float amount."""
    if isinstance(value, bool):
        return 0.0
    if isinstance(value, (int, float)):
        return float(value) if value > 0 else 0.0
    return 0.0


def calculate_portfolio_value(
    user_card_holdings: Optional[List[Dict[str, Any]]] = None,
    user_sealed_product_holdings: Optional[List[Dict[str, Any]]] = None,
    user_graded_card_holdings: Optional[List[Dict[str, Any]]] = None,
) -> float:
    """Return current total portfolio value across collection items."""
    user_card_holdings = user_card_holdings or []
    user_sealed_product_holdings = user_sealed_product_holdings or []
    user_graded_card_holdings = user_graded_card_holdings or []

    total_value = 0.0
    for domain_items in (
        user_card_holdings,
        user_sealed_product_holdings,
        user_graded_card_holdings,
    ):
        for item in domain_items:
            if not isinstance(item, dict):
                continue

            quantity = _to_positive_int(item.get("quantity"))
            market_price = _to_non_negative_float(item.get("market_price"))
            total_value += quantity * market_price

    return total_value


def calculate_cards_count(
    user_card_holdings: Optional[List[Dict[str, Any]]] = None,
) -> int:
    """Return count of card items according to backend domain rules."""
    if not user_card_holdings:
        return 0

    total_count = 0
    for card in user_card_holdings:
        if not isinstance(card, dict):
            continue
        total_count += _to_positive_int(card.get("quantity"))

    return total_count


def calculate_sealed_count(
    user_sealed_product_holdings: Optional[List[Dict[str, Any]]] = None,
) -> int:
    """Return count of sealed items according to backend domain rules."""
    sealed_items = user_sealed_product_holdings

    if not sealed_items:
        return 0

    total_count = 0
    for item in sealed_items:
        if not isinstance(item, dict):
            continue
        total_count += _to_positive_int(item.get("quantity"))

    return total_count


def calculate_graded_count(
    user_graded_card_holdings: Optional[List[Dict[str, Any]]] = None,
) -> int:
    """Return count of graded items according to backend domain rules."""
    graded_items = user_graded_card_holdings

    if not graded_items:
        return 0

    total_count = 0
    for item in graded_items:
        if not isinstance(item, dict):
            continue
        total_count += _to_positive_int(item.get("quantity"))

    return total_count


def calculate_summary(
    portfolio_value: float,
    cards_count: int,
    sealed_count: int,
    graded_count: int,
) -> CollectionSummary:
    """Aggregate precomputed metrics into a single summary domain object."""
    return CollectionSummary(
        portfolio_value=portfolio_value,
        cards_count=cards_count,
        sealed_count=sealed_count,
        graded_count=graded_count,
    )
