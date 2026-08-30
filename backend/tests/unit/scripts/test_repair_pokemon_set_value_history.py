from backend.scripts.repair_pokemon_set_value_history import repair_history


class Result:
    def __init__(self, data, count=None): self.data, self.count = data, count


class Query:
    def __init__(self, client, table, rows): self.client, self.name, self.rows = client, table, list(rows)
    def select(self, *a, **k): self.count_mode = k.get("count"); return self
    def eq(self, key, value): self.rows = [r for r in self.rows if r.get(key) == value]; return self
    def gte(self, key, value): self.rows = [r for r in self.rows if str(r.get(key)) >= value]; return self
    def lte(self, key, value): self.rows = [r for r in self.rows if str(r.get(key)) <= value]; return self
    def order(self, key): self.rows.sort(key=lambda r: str(r.get(key))); return self
    def execute(self): return Result(self.rows, len(self.rows))


class Client:
    def __init__(self, drift=0):
        self.drift, self.refresh_calls = drift, []
        self.tables = {
            "sets": [{"id": "s1", "canonical_key": "perfectOrder", "name": "Perfect Order", "ready_for_daily_scrape": True}],
            "pokemon_set_value_daily_history": [{"set_id": "s1", "snapshot_date": "2026-08-28", "value_scope": "standard", "set_value": 100}],
        }
    def table(self, name): return Query(self, name, self.tables[name])
    def rpc(self, name, params):
        if name == "refresh_pokemon_set_value_daily_history":
            self.refresh_calls.append(dict(params))
            class Scalar:
                def execute(self): return Result(1)
            return Scalar()
        assert name == "get_pokemon_cards_daily_constituents"
        return Query(self, name, [{"market_date": "2026-08-28", "market_price": 100 + self.drift}])


def test_dry_run_is_bounded_and_never_refreshes():
    client = Client()
    report = repair_history(client, start="2026-08-28", end="2026-08-28",
                            selector="perfectOrder", all_sets=False, commit=False)
    assert report["mode"] == "dry_run" and report["target_set_count"] == 1
    assert client.refresh_calls == []


def test_commit_calls_only_canonical_refresh_and_reconciles():
    client = Client()
    report = repair_history(client, start="2026-08-28", end="2026-08-28",
                            selector=None, all_sets=True, commit=True)
    assert report["ok"] is True
    assert client.refresh_calls == [{"p_set_id": "s1", "p_start_date": "2026-08-28", "p_end_date": "2026-08-28"}]


def test_idempotent_rerun_uses_same_bounded_upsert_authority():
    client = Client()
    first = repair_history(client, start="2026-08-28", end="2026-08-28", selector=None, all_sets=True, commit=True)
    second = repair_history(client, start="2026-08-28", end="2026-08-28", selector=None, all_sets=True, commit=True)
    assert first["reconciliation_after"] == second["reconciliation_after"]
    assert client.refresh_calls[0] == client.refresh_calls[1]


def test_reconciliation_above_one_cent_fails_closed():
    report = repair_history(Client(drift=0.02), start="2026-08-28", end="2026-08-28",
                            selector=None, all_sets=True, commit=True)
    assert report["ok"] is False and report["reconciliation_after"]["failure_count"] == 1


def test_prismatic_promo_exclusion_and_legacy_identity_are_owned_by_database_rpcs():
    import inspect
    from backend.scripts import repair_pokemon_set_value_history as module
    source = inspect.getsource(module)
    assert "set_value_eligible" not in source
    assert "promo_variant" not in source
    assert "legacy_identity" not in source
    assert module.REFRESH_RPC == "refresh_pokemon_set_value_daily_history"
    assert module.CONSTITUENT_RPC == "get_pokemon_cards_daily_constituents"
