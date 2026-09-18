from backend.domain.access.index_plan_access import (
    FEATURE_BEST_OPEN_PRICE,
    has_index_feature_access,
    project_product_family_rankings_response,
    project_product_rankings_response,
)


ROW = {
    "sealedProductId": "p1",
    "productName": "Alpha Booster Pack",
    "unitPrice": 14.57,
    "budgetRank": 2,
    "overallRipLeaderScore": 91,
    "bestOpenPrice": 13.23,
    "bestOpenPriceStatus": "resolved_below_market",
    "bestOpenPriceGapDollars": 1.34,
    "bestOpenPriceGapPercent": 0.0919,
}
META = {
    "available": True,
    "reason": None,
    "snapshotId": "bop-1",
    "methodVersion": "best-open-v1",
    "sourceMarketDate": "2026-09-08",
    "sourceBudgetSnapshotId": "budget-1",
    "privateFutureField": "must-not-cross-boundary",
}


def test_best_open_price_is_plus_and_premium_not_basic():
    assert has_index_feature_access(None, FEATURE_BEST_OPEN_PRICE) is False
    assert has_index_feature_access("plus", FEATURE_BEST_OPEN_PRICE) is True
    assert has_index_feature_access("premium", FEATURE_BEST_OPEN_PRICE) is True


def test_basic_product_projection_never_receives_best_open_values():
    payload = {
        "available": True,
        "cohortSize": 1,
        "rows": [ROW],
        "bestOpenPrice": META,
    }
    result = project_product_rankings_response(payload, None)
    assert "bestOpenPrice" not in result
    assert "bestOpenPrice" not in result["rows"][0]
    assert "bestOpenPriceStatus" not in result["rows"][0]
    assert result["rows"][0]["unitPrice"] == 14.57


def test_plus_product_projection_gets_only_narrow_best_open_contract():
    payload = {
        "available": True,
        "cohortSize": 1,
        "rows": [ROW],
        "bestOpenPrice": META,
        "authority": {"snapshotId": "budget-1"},
    }
    result = project_product_rankings_response(payload, "plus")
    row = result["rows"][0]
    assert row["bestOpenPrice"] == 13.23
    assert row["bestOpenPriceStatus"] == "resolved_below_market"
    assert row["bestOpenPriceGapDollars"] == 1.34
    assert row["bestOpenPriceGapPercent"] == 0.0919
    assert result["bestOpenPrice"]["sourceMarketDate"] == "2026-09-08"
    assert "privateFutureField" not in result["bestOpenPrice"]


def test_family_rankings_do_not_receive_cross_format_best_open_even_for_plus():
    payload = {
        "families": {
            "loose_booster_pack": {
                "label": "Loose Booster Pack",
                "count": 1,
                "products": [ROW],
            },
        },
    }
    result = project_product_family_rankings_response(payload, "plus")
    row = result["families"]["loose_booster_pack"]["products"][0]
    assert "bestOpenPrice" not in row
    assert "bestOpenPriceGapPercent" not in row
