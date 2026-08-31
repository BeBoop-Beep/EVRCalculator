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
    def __init__(self, drift=0, history=True, constituents=True, refresh_result=1):
        self.drift, self.constituents, self.refresh_result = drift, constituents, refresh_result
        self.refresh_calls = []
        self.tables = {
            "sets": [{"id": "s1", "canonical_key": "perfectOrder", "name": "Perfect Order", "ready_for_daily_scrape": True}],
            "pokemon_set_value_daily_history": ([{"set_id": "s1", "snapshot_date": "2026-08-28", "value_scope": "standard", "set_value": 100}] if history else []),
        }
    def table(self, name): return Query(self, name, self.tables[name])
    def rpc(self, name, params):
        if name == "refresh_pokemon_set_value_daily_history":
            self.refresh_calls.append(dict(params))
            client = self
            class Scalar:
                def execute(self): return Result(client.refresh_result)
            return Scalar()
        assert name == "get_pokemon_cards_daily_constituents"
        rows = [{"market_date": "2026-08-28", "market_price": 100 + self.drift}] if self.constituents else []
        return Query(self, name, rows)


def run(client, *, commit=True):
    return repair_history(client, start="2026-08-28", end="2026-08-28",
                          selector=None, all_sets=True, commit=commit)


def test_dry_run_is_bounded_and_never_refreshes():
    client = Client()
    report = repair_history(client, start="2026-08-28", end="2026-08-28",
                            selector="perfectOrder", all_sets=False, commit=False)
    assert report["mode"] == "dry_run" and report["target_set_count"] == 1
    assert client.refresh_calls == []


def test_commit_calls_only_canonical_refresh_and_exact_reconciliation_passes():
    client = Client()
    report = run(client)
    assert report["ok"] is True
    assert report["reconciliation_after"]["expected_set_date_count"] == 1
    assert report["reconciliation_after"]["reconciled_set_date_count"] == 1
    assert client.refresh_calls == [{"p_set_id": "s1", "p_start_date": "2026-08-28", "p_end_date": "2026-08-28"}]


def test_idempotent_rerun_uses_same_bounded_upsert_authority():
    client = Client()
    first, second = run(client), run(client)
    assert first["reconciliation_after"] == second["reconciliation_after"]
    assert client.refresh_calls[0] == client.refresh_calls[1]


def test_reconciliation_above_one_cent_fails_closed():
    report = run(Client(drift=0.02))
    assert report["ok"] is False
    assert len(report["reconciliation_after"]["numeric_drift_failures"]) == 1


def test_history_only_date_fails():
    report = run(Client(constituents=False))
    assert report["ok"] is False
    assert len(report["reconciliation_after"]["missing_constituent_totals"]) == 1


def test_constituents_only_date_fails():
    report = run(Client(history=False))
    assert report["ok"] is False
    assert len(report["reconciliation_after"]["missing_history_rows"]) == 1


def test_expected_date_absent_from_both_sides_fails():
    report = run(Client(history=False, constituents=False))
    after = report["reconciliation_after"]
    assert report["ok"] is False and after["expected_set_date_count"] == 1
    assert after["missing_history_rows"][0]["reason"] == "both_expected_inputs_absent"
    assert after["missing_constituent_totals"][0]["reason"] == "both_expected_inputs_absent"


def test_zero_row_refresh_cannot_be_green():
    report = run(Client(refresh_result=0))
    assert report["ok"] is False
    assert report["refresh_coverage_failures"][0]["reason"] == "refresh_rpc_returned_zero"


def test_expected_drift_dry_run_is_non_mutating_and_operator_safe():
    client = Client(drift=0.02)
    report = run(client, commit=False)
    assert report["ok"] is True and report["repair_needed"] is True
    assert report["reconciliation_before"]["failure_count"] == 1
    assert client.refresh_calls == []


def test_cli_preview_drift_exits_zero_but_commit_failure_exits_nonzero(monkeypatch, capsys):
    from backend.scripts import repair_pokemon_set_value_history as module
    preview_client = Client(drift=0.02)
    monkeypatch.setattr(module, "supabase", preview_client)
    args = ["--start-date", "2026-08-28", "--end-date", "2026-08-28", "--all"]
    assert module.main(args) == 0
    assert '"repair_needed": true' in capsys.readouterr().out

    commit_client = Client(drift=0.02)
    monkeypatch.setattr(module, "supabase", commit_client)
    assert module.main([*args, "--commit"]) == 1
    assert commit_client.refresh_calls


def test_prismatic_promo_exclusion_and_legacy_identity_are_owned_by_database_rpcs():
    import inspect
    from backend.scripts import repair_pokemon_set_value_history as module
    source = inspect.getsource(module)
    assert "set_value_eligible" not in source
    assert "promo_variant" not in source
    assert "legacy_identity" not in source
    assert module.REFRESH_RPC == "refresh_pokemon_set_value_daily_history"
    assert module.CONSTITUENT_RPC == "get_pokemon_cards_daily_constituents"
