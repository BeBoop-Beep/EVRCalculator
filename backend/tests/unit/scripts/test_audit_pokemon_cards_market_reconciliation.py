from backend.scripts.audit_pokemon_cards_market_reconciliation import audit_latest_reconciliation


class _Response:
    def __init__(self, data):
        self.data = data


class _Query:
    def __init__(self, data):
        self.data = data

    def select(self, *_args): return self
    def eq(self, *_args): return self
    def order(self, *_args, **_kwargs): return self
    def execute(self): return _Response(self.data)


class _Client:
    def __init__(self, difference=0):
        self.difference = difference

    def table(self, name):
        assert name == "pokemon_set_value_daily_history"
        return _Query([{"set_id": "set-1", "snapshot_date": "2026-08-28", "set_value": 5036.02}])

    def rpc(self, name, params):
        assert name == "get_pokemon_cards_daily_constituents"
        assert params == {"p_set_ids": ["set-1"], "p_start_date": "2026-08-28", "p_end_date": "2026-08-28", "p_card_ids": None}
        return _Query([{"market_price": 5036.02 + self.difference}])


def test_exhaustive_audit_passes_exact_reconciliation():
    report = audit_latest_reconciliation(_Client())
    assert report["ok"] is True
    assert report["failed_set_count"] == 0


def test_exhaustive_audit_remains_fail_closed_above_one_cent():
    report = audit_latest_reconciliation(_Client(0.02))
    assert report["ok"] is False
    assert report["failed_set_count"] == 1
