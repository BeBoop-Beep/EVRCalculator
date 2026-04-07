"""Service layer orchestration for collection summary metrics."""

import logging
from uuid import UUID

from backend.calculations.collection_summary import (
    calculate_cards_count,
    calculate_graded_count,
    calculate_portfolio_value,
    calculate_sealed_count,
    calculate_summary,
)
from backend.db.repositories.user_collection_summary_repository import (
    load_user_collection_for_summary,
)
from backend.models.collection_summary_models import CollectionSummary


logger = logging.getLogger(__name__)


def get_user_collection_summary(user_id: UUID) -> CollectionSummary:
    """Load holdings payloads, compute metrics, and return CollectionSummary."""
    payload = load_user_collection_for_summary(user_id)

    user_card_holdings = payload.get("user_card_holdings", [])
    user_sealed_product_holdings = payload.get("user_sealed_product_holdings", [])
    user_graded_card_holdings = payload.get("user_graded_card_holdings", [])

    portfolio_value = calculate_portfolio_value(
        user_card_holdings=user_card_holdings,
        user_sealed_product_holdings=user_sealed_product_holdings,
        user_graded_card_holdings=user_graded_card_holdings,
    )
    cards_count = calculate_cards_count(user_card_holdings=user_card_holdings)
    sealed_count = calculate_sealed_count(user_sealed_product_holdings=user_sealed_product_holdings)
    graded_count = calculate_graded_count(user_graded_card_holdings=user_graded_card_holdings)

    logger.warning(
        "[portfolio-debug] summary totals user_id=%s raw_card_rows=%s sealed_rows=%s graded_rows=%s portfolio_value=%s cards_count=%s sealed_count=%s graded_count=%s",
        user_id,
        len(user_card_holdings),
        len(user_sealed_product_holdings),
        len(user_graded_card_holdings),
        portfolio_value,
        cards_count,
        sealed_count,
        graded_count,
    )

    return calculate_summary(
        portfolio_value=portfolio_value,
        cards_count=cards_count,
        sealed_count=sealed_count,
        graded_count=graded_count,
    )
