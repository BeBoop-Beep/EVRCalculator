from backend.db.services.chase_efficiency_query_service import SORT_COLUMNS


def test_cards_ui_sort_options_are_all_server_authoritative():
    assert SORT_COLUMNS == {
        "chase_efficiency": "chase_efficiency", "rank": "overall_rank",
        "price": "current_near_mint_market_price", "name": "card_name",
        "pull_probability": "exact_pull_probability", "chase_spend_50": "chase_spend_50",
        "cost_multiple_50": "cost_multiple_50",
    }
