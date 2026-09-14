from backend.scripts.research_best_open_price_bucket2 import _cohort_analysis, _status


def test_bucket2_status_taxonomy_preserves_direction():
    assert _status(1, 100, 120) == "current_number_one_with_headroom"
    assert _status(2, 100, 100) == "resolved_at_market"
    assert _status(2, 100, 80) == "resolved_below_market"


def test_bucket2_cohort_analysis_keeps_leader_headroom_out_of_discounts():
    rows = [
        {"status": "current_number_one_with_headroom", "bestOpenPrice": 12,
         "currentBudgetRank": 1, "priceGapPercent": -0.2, "quantityDelta": -1,
         "productFamily": "pack", "setId": "a"},
        {"status": "resolved_below_market", "bestOpenPrice": 8,
         "currentBudgetRank": 2, "priceGapPercent": 0.2, "quantityDelta": 2,
         "productFamily": "box", "setId": "b"},
    ]
    result = _cohort_analysis(rows)
    assert result["resolved"] == 2
    assert result["discountPercentiles"]["p50"] == 0.2
    assert result["discountBands"]["under5Percent"] == 0
    assert result["discountBands"]["under10Percent"] == 0
    assert result["discountBands"]["under20Percent"] == 0
    assert result["discountBands"]["20To40Percent"] == 1


def test_bucket2_discount_threshold_bands_are_cumulative():
    rows = [
        {"status": "resolved_below_market", "bestOpenPrice": 9,
         "currentBudgetRank": rank, "priceGapPercent": gap, "quantityDelta": 1,
         "productFamily": "pack", "setId": "a"}
        for rank, gap in ((2, 0.08), (3, 0.15), (4, 0.30))
    ]
    bands = _cohort_analysis(rows)["discountBands"]
    assert bands["under5Percent"] == 0
    assert bands["under10Percent"] == 1
    assert bands["under20Percent"] == 2
    assert bands["20To40Percent"] == 1
