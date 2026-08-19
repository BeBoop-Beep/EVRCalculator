from types import SimpleNamespace

import backend.db.repositories.card_variant_prices_repository as repo
from backend.db.services import supabase_persistence_retry as retry


class _FakeQuery:
    def __init__(self, calls):
        self.calls = calls

    def select(self, _cols):
        return self

    def in_(self, _col, values):
        self.calls.append(("in", list(values)))
        return self

    def eq(self, _col, value):
        self.calls.append(("eq", value))
        return self

    def execute(self):
        last_in_values = []
        for kind, payload in reversed(self.calls):
            if kind == "in":
                last_in_values = payload
                break
        rows = [{"variant_id": variant_id, "condition_id": "cond", "market_price": 1.0} for variant_id in last_in_values]
        return SimpleNamespace(data=rows)


class _FakeClient:
    def __init__(self, calls):
        self.calls = calls

    def table(self, name):
        self.calls.append(("table", name))
        return _FakeQuery(self.calls)


def test_get_latest_prices_for_variants_chunks_large_in_list(monkeypatch):
    calls = []

    def _fake_create_client(_url, _key):
        return _FakeClient(calls)

    monkeypatch.setattr(repo, "create_client", _fake_create_client)

    variant_ids = [f"id-{idx}" for idx in range(1201)]
    rows = repo.get_latest_prices_for_variants(variant_ids, "cond")

    in_lengths = [len(payload) for kind, payload in calls if kind == "in"]
    assert in_lengths == [500, 500, 201]
    assert len(rows) == 1201


def test_get_latest_prices_for_variants_normalizes_and_drops_empty(monkeypatch):
    calls = []

    def _fake_create_client(_url, _key):
        return _FakeClient(calls)

    monkeypatch.setattr(repo, "create_client", _fake_create_client)

    variant_ids = ["id-1", " id-1 ", None, "", "id-2"]
    rows = repo.get_latest_prices_for_variants(variant_ids, " cond ")

    in_payloads = [payload for kind, payload in calls if kind == "in"]
    assert in_payloads == [["id-1", "id-2"]]

    eq_payloads = [payload for kind, payload in calls if kind == "eq"]
    assert eq_payloads == ["cond"]
    assert len(rows) == 2


def test_price_ingest_refreshes_value_history_and_canonical_selection(monkeypatch):
    calls = []

    class _Rpc:
        def execute(self):
            return SimpleNamespace(data=[])

    class _RefreshClient:
        def rpc(self, name, params):
            calls.append((name, params))
            return _Rpc()

    monkeypatch.setattr(repo, "create_client", lambda _url, _key: _RefreshClient())
    monkeypatch.setattr(retry, "create_client", lambda _url, _key: _RefreshClient())
    monkeypatch.setattr(repo, "_canonical_refresh_rpc_name", None)

    repo._refresh_pokemon_set_value_history_for_price_rows(
        [
            {
                "card_variant_id": "variant-1",
                "captured_at": "2026-07-12T12:00:00+00:00",
            }
        ]
    )

    assert calls == [
        (
            "refresh_pokemon_set_value_daily_history_for_variants",
            {"p_card_variant_ids": ["variant-1"], "p_start_date": "2026-07-12"},
        ),
        (
            "refresh_pokemon_canonical_card_market_prices_latest_for_variant",
            {"p_card_variant_ids": ["variant-1"]},
        ),
    ]


def test_canonical_refresh_falls_back_to_plural_once_and_caches(monkeypatch):
    calls = []
    class MissingRpc(Exception):
        code = "PGRST202"
    class Rpc:
        def __init__(self, name): self.name = name
        def execute(self):
            if self.name == repo._CANONICAL_REFRESH_SINGULAR:
                raise MissingRpc("function not found 404")
            return SimpleNamespace(data=[])
    class Client:
        def rpc(self, name, _params):
            calls.append(name)
            return Rpc(name)
    monkeypatch.setattr(repo, "create_client", lambda _url, _key: Client())
    monkeypatch.setattr(retry, "create_client", lambda _url, _key: Client())
    monkeypatch.setattr(repo, "_canonical_refresh_rpc_name", None)

    repo._refresh_canonical_prices(["v1"])
    repo._refresh_canonical_prices(["v2"])

    assert calls == [repo._CANONICAL_REFRESH_SINGULAR,
                     repo._CANONICAL_REFRESH_PLURAL,
                     repo._CANONICAL_REFRESH_PLURAL]


def test_canonical_refresh_env_can_pin_repository_plural_contract(monkeypatch):
    calls = []
    class Rpc:
        def execute(self): return SimpleNamespace(data=[])
    class Client:
        def rpc(self, name, _params): calls.append(name); return Rpc()
    monkeypatch.setenv("POKEMON_CANONICAL_REFRESH_RPC_NAME", repo._CANONICAL_REFRESH_PLURAL)
    monkeypatch.setattr(repo, "create_client", lambda _url, _key: Client())
    monkeypatch.setattr(retry, "create_client", lambda _url, _key: Client())
    monkeypatch.setattr(repo, "_canonical_refresh_rpc_name", None)
    repo._refresh_canonical_prices(["v1"])
    assert calls == [repo._CANONICAL_REFRESH_PLURAL]
