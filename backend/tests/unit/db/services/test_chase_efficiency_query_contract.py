import pytest

from backend.db.services.chase_efficiency_query_service import SORT_COLUMNS, _public_row


def test_cards_ui_sort_options_are_all_server_authoritative():
    assert SORT_COLUMNS == {
        "chase_efficiency": "chase_efficiency", "rank": "overall_rank",
        "price": "current_near_mint_market_price", "name": "card_name",
        "pull_probability": "exact_pull_probability", "chase_spend_50": "chase_spend_50",
        "cost_multiple_50": "cost_multiple_50",
    }


def test_card_payload_derives_buy_price_probability_and_percentile_server_side():
    payload = _public_row({
        "exact_pull_probability": 0.01,
        "current_near_mint_market_price": 100,
        "best_verified_pack_equivalent_cost": 5,
        "overall_rank": 11,
        "overall_cohort_size": 4_852,
        "milestones_json": {"0.5": {"packs": 69, "spend": 345}},
    })

    assert payload["packsAtBuyPrice"] == 20
    assert payload["chanceAtBuyPrice"] == pytest.approx(1 - 0.99**20)
    assert payload["topPercent"] == pytest.approx(100 * 11 / 4_852)
    assert payload["milestones"]["0.5"]["spend"] == 345
