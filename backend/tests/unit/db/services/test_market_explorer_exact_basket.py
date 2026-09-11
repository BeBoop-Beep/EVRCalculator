from backend.db.services.market_explorer_exact_basket import run_exact_basket_v2


class Response:
    def __init__(self, data): self.data = data
    def execute(self): return self


class Client:
    def __init__(self, rows): self.rows = rows; self.calls = []
    def rpc(self, name, args): self.calls.append((name, args)); return Response(self.rows)


def test_exact_basket_uses_common_cohort_values_not_raw_basket_jump():
    rows = [
        {"market_date": "2026-09-07", "selected_instrument_count": 2, "priced_instrument_count": 1, "basket_value": 10, "common_instrument_count": 0, "common_current_value": 0, "common_previous_value": 0, "basket_as_of": "2026-09-08", "comparison_as_of": "2026-09-08", "status": "ready"},
        {"market_date": "2026-09-08", "selected_instrument_count": 2, "priced_instrument_count": 2, "basket_value": 1010, "common_instrument_count": 1, "common_current_value": 9, "common_previous_value": 10, "basket_as_of": "2026-09-08", "comparison_as_of": "2026-09-08", "status": "ready", "current_constituents": [{"asset": "cards", "instrumentId": "a", "marketPrice": 9, "quantity": 1}, {"asset": "sealed", "instrumentId": "b", "marketPrice": 1001, "quantity": 1}]},
    ]
    result = run_exact_basket_v2(Client(rows), instruments=[{"asset": "cards", "instrumentId": "a"}, {"asset": "sealed", "instrumentId": "b"}])
    assert result["trackedValue"] == 1010
    assert result["trend"][-1][1] == 90
    assert result["metadata"]["oneUnitPerLeaf"] is True
    assert result["basketAsOf"] == "2026-09-08"
    assert len(result["currentConstituents"]) == 2

