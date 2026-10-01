import pytest

from backend.db.services.chase_efficiency_query_service import SORT_COLUMNS, _public_row
from backend.rankings.public_relative import absolute_rank_percentile_tier


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
    assert payload["tier"] == absolute_rank_percentile_tier(11, 4_852) == "S"
    assert payload["milestones"]["0.5"]["spend"] == 345


@pytest.mark.parametrize(
    ("rank", "size", "expected"),
    [(1, 100, "S"), (2, 100, "A"), (10, 100, "A"), (11, 100, "B"),
     (25, 100, "B"), (26, 100, "C"), (50, 100, "C"), (51, 100, "D"),
     (75, 100, "D"), (76, 100, "F"), (100, 100, "F"),
     (48, 4_852, "S"), (49, 4_852, "A"), (485, 4_852, "A"), (486, 4_852, "B"),
     (1_213, 4_852, "B"), (1_214, 4_852, "C"), (2_426, 4_852, "C"), (2_427, 4_852, "D"),
     (3_639, 4_852, "D"), (3_640, 4_852, "F"),
     (1, 7, "S"), (2, 7, "C"), (None, 100, None), (1, None, None), (0, 100, None)],
)
def test_card_payload_uses_absolute_rank_percentile_boundaries(rank, size, expected):
    payload = _public_row({"overall_rank": rank, "overall_cohort_size": size})
    assert payload["tier"] == absolute_rank_percentile_tier(rank, size) == expected
