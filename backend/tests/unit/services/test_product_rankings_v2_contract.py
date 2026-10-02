from backend.desirability.chase_accessibility_overall_score import chase_accessibility_overall_score
from backend.db.services.product_rankings_v2_service import _apply_exact, _best_open, _filter_sort, _page, query_product_rankings


class Response:
    def __init__(self, data): self.data = data


class Query:
    def __init__(self, rows): self.rows = list(rows)
    def select(self, *_args): return self
    def limit(self, size): self.rows = self.rows[:size]; return self
    def eq(self, key, value): self.rows = [row for row in self.rows if row.get(key) == value]; return self
    def in_(self, key, values): self.rows = [row for row in self.rows if row.get(key) in values]; return self
    def execute(self): return Response(self.rows)


class Client:
    def __init__(self, tables): self.tables = tables
    def table(self, name): return Query(self.tables.get(name, []))


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


def test_best_open_accepts_older_independently_dated_run_for_exact_product_only():
    client = Client({
        "budget_product_best_open_price_latest": [{"snapshot_id": "best-1", "source_market_date": "2026-09-08"}],
        "budget_product_best_open_price_rows": [
            {"snapshot_id": "best-1", "sealed_product_id": "p1", "source_calculation_run_id": "old-run", "current_market_price": 50, "status": "available", "best_open_price": 42, "price_gap_dollars": 8, "price_gap_percent": .16},
            {"snapshot_id": "best-1", "sealed_product_id": "other", "source_calculation_run_id": "new-run", "best_open_price": 1},
        ],
    })
    result = _best_open(client, [{"sealedProductId": "p1", "sourceCalculationRunId": "new-run"}], "2026-10-01")
    assert list(result) == ["p1"]
    assert result["p1"]["bestOpenPrice"] == 42
    assert result["p1"]["bestOpenSourceMarketDate"] == "2026-09-08"
    assert result["p1"]["bestOpenFreshnessStatus"] == "older"


def test_best_open_sort_enriches_full_cohort_before_paging(monkeypatch):
    authority = {"marketDate": "2026-10-01", "rows": [
        {"sealedProductId": "p1", "productName": "A", "familyKey": "pack", "familyName": "Pack", "rank": 1, "sourceCalculationRunId": "new-1"},
        {"sealedProductId": "p2", "productName": "B", "familyKey": "pack", "familyName": "Pack", "rank": 2, "sourceCalculationRunId": "new-2"},
    ]}
    monkeypatch.setattr("backend.db.services.product_rankings_v2_service._exact_economics", lambda *_: {})
    monkeypatch.setattr("backend.db.services.product_rankings_v2_service._best_open", lambda _c, rows, _d: {row["sealedProductId"]: {"bestOpenPrice": 90 if row["sealedProductId"] == "p1" else 10} for row in rows})
    result = query_product_rankings(object(), authority, view="economics", sort="bestOpenPrice", direction="asc", page=1, page_size=1)
    assert result["rows"][0]["sealedProductId"] == "p2"
    assert result["total"] == 2
