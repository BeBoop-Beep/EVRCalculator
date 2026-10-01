from backend.desirability.chase_accessibility_overall_score import chase_accessibility_overall_score
from backend.db.services.product_rankings_v2_service import _apply_exact, _filter_sort, _page


def test_chase_contract_uses_canonical_fixed_transform():
    raw = 0.002
    assert chase_accessibility_overall_score(raw) != raw
    assert 0 < chase_accessibility_overall_score(raw) < 100


def test_filter_and_sort_happen_before_page_and_rank_is_preserved():
    rows = [
        {"sealedProductId": "3", "productName": "Gamma", "familyKey": "pack", "familyName": "Pack", "rank": 87},
        {"sealedProductId": "1", "productName": "Alpha", "familyKey": "pack", "familyName": "Pack", "rank": 1},
        {"sealedProductId": "2", "productName": "Beta", "familyKey": "box", "familyName": "Box", "rank": 2},
    ]
    filtered = _filter_sort(rows, search="a", family="pack", sort="productName", direction="asc")
    page, meta = _page(filtered, 1, 1)
    assert meta == {"page": 1, "pageSize": 1, "total": 2, "totalPages": 2}
    assert page[0]["productName"] == "Alpha"
    assert filtered[1]["rank"] == 87


def test_exact_sku_recovery_overrides_strategy_semantics():
    row = {"chanceToRecoverCost": 0}
    _apply_exact(row, {"product_market_cost": 10, "pack_count": 1, "expected_value": 8,
                       "chance_to_recover_cost": 0.099126, "price_as_of": "2026-09-30"})
    assert row["chanceToRecoverCost"] == 0.099126
    assert row["modeledReturnOnSpend"] == 0.8


def test_missing_exact_sku_stays_unavailable():
    row = {}
    assert "chanceToRecoverCost" not in row
