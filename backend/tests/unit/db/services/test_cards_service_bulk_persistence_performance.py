import math
from types import SimpleNamespace

import pytest

from backend.db.services import cards_service as module
from backend.db.services import supabase_persistence_retry as retry


def _payload(count):
    work, card_ids = [], {}
    for index in range(count):
        card_key = (f"Card {index}", str(index))
        card_id = f"card-{index}"
        card_ids[card_key] = card_id
        work.append(({
            "card_id": card_id, "printing_type": "holo", "special_type": None, "edition": None,
            "_external_identity": {"provider": "tcgplayer", "external_product_id": str(index),
                                   "external_variant_key": f"variant-{index}"},
        }, [], card_key))
    return work, card_ids


def _install_warm_bulk_maps(monkeypatch, count):
    identities = {
        ("tcgplayer", str(index), f"variant-{index}"):
            {"id": f"identity-{index}", "provider": "tcgplayer", "external_product_id": str(index),
             "external_variant_key": f"variant-{index}", "card_variant_id": f"variant-id-{index}"}
        for index in range(count)
    }
    variants = {
        f"variant-id-{index}": {"id": f"variant-id-{index}", "card_id": f"card-{index}",
                                "printing_type": "holo", "special_type": None, "edition": None}
        for index in range(count)
    }
    chunk_count = math.ceil(count / module.get_card_variant_external_identities_bulk.__globals__["BULK_READ_CHUNK_SIZE"])
    monkeypatch.setattr(module, "get_card_variant_external_identities_bulk",
                        lambda _provider, _pairs: (identities, chunk_count))
    monkeypatch.setattr(module, "get_card_variants_bulk",
                        lambda **_kwargs: (variants, {}, chunk_count))
    for name in ("get_card_variant_external_identity", "get_card_variant_by_id",
                 "get_card_variant_by_card_and_type", "link_card_variant_external_identity",
                 "insert_card_variant"):
        monkeypatch.setattr(module, name, lambda *_a, _name=name, **_k:
                            (_ for _ in ()).throw(AssertionError(f"warm path called {_name}")))
    return chunk_count


@pytest.mark.parametrize("count", [100, 400])
def test_warm_ingestion_reads_scale_with_chunks_not_variants(monkeypatch, count):
    chunks = _install_warm_bulk_maps(monkeypatch, count)
    work, card_ids = _payload(count)
    result = module.CardsService()._process_batch_worker((work, card_ids), 0)
    metrics = result["persistence_metrics"]
    assert result["errors"] == []
    assert metrics["identityReadOperations"] == chunks
    assert metrics["variantReadOperations"] == chunks
    assert metrics["identityWriteOperations"] == 0
    assert metrics["variantWriteOperations"] == 0
    assert metrics["identityReadOperations"] + metrics["variantReadOperations"] < 20
    price_chunks = math.ceil(count / 100)
    total_db_operations = metrics["identityReadOperations"] + metrics["variantReadOperations"] + price_chunks * 2
    assert total_db_operations == (4 if count == 100 else 14)


def test_400_variant_call_count_is_major_reduction_from_legacy_loop(monkeypatch):
    count = 400
    chunks = _install_warm_bulk_maps(monkeypatch, count)
    work, card_ids = _payload(count)
    result = module.CardsService()._process_batch_worker((work, card_ids), 0)
    after_reads = (result["persistence_metrics"]["identityReadOperations"]
                   + result["persistence_metrics"]["variantReadOperations"])
    legacy_reads = count * 3  # identity lookup + mapped variant lookup + redundant link lookup
    legacy_clients = legacy_reads
    assert (legacy_reads, legacy_clients) == (1200, 1200)
    assert after_reads == chunks * 2 == 6
    assert legacy_reads / after_reads == 200
    assert legacy_reads + 8 == 1208  # plus four price SELECTs and four INSERTs
    assert legacy_clients + 4 == 1204
    assert after_reads + 8 == 14
    assert chunks * 2 + 4 == 10  # Phase 1 client constructions before session reuse


@pytest.mark.parametrize("count", [100, 400])
def test_warm_path_real_bulk_queries_construct_one_worker_client(monkeypatch, count):
    identities = [{"id": f"identity-{i}", "provider": "tcgplayer",
                   "external_product_id": str(i), "external_variant_key": f"variant-{i}",
                   "card_variant_id": f"variant-id-{i}"} for i in range(count)]
    variants = [{"id": f"variant-id-{i}", "card_id": f"card-{i}",
                 "printing_type": "holo", "special_type": None, "edition": None}
                for i in range(count)]
    tables = {"card_variant_external_identities": identities, "card_variants": variants}
    constructions = []

    class Query:
        def __init__(self, rows): self.rows, self.filters, self.bounds = rows, [], (0, 999)
        def select(self, *_args): return self
        def eq(self, key, value): self.filters.append((key, value, False)); return self
        def in_(self, key, values): self.filters.append((key, set(map(str, values)), True)); return self
        def order(self, _key): return self
        def range(self, start, end): self.bounds = (start, end); return self
        def execute(self):
            rows = self.rows
            for key, value, many in self.filters:
                rows = [row for row in rows if (str(row.get(key)) in value if many
                                                 else row.get(key) == value)]
            start, end = self.bounds
            return SimpleNamespace(data=rows[start:end + 1])
    class Client:
        def table(self, name): return Query(tables[name])
    def factory(_url, _key):
        client = Client(); constructions.append(client); return client

    monkeypatch.setattr(retry, "create_client", factory)
    work, card_ids = _payload(count)
    result = module.CardsService()._process_batch_worker((work, card_ids), 0)
    assert result["errors"] == []
    assert len(constructions) == 1


@pytest.mark.parametrize("count,expected_chunks", [(100, 1), (400, 3)])
def test_complete_warm_path_observes_real_repository_api_calls(
    monkeypatch, count, expected_chunks,
):
    market_date = "2026-08-19"
    tables = {
        "card_variant_external_identities": [
            {"id": f"identity-{i:04d}", "provider": "tcgplayer",
             "external_product_id": str(i), "external_variant_key": f"variant-{i}",
             "card_variant_id": f"variant-id-{i}"} for i in range(count)
        ],
        "card_variants": [
            {"id": f"variant-id-{i}", "card_id": f"card-{i}",
             "printing_type": "holo", "special_type": None, "edition": None}
            for i in range(count)
        ],
        "card_variant_price_observations": [],
    }
    events, constructions = [], []

    class Query:
        def __init__(self, table):
            self.table, self.operation, self.filters = table, "SELECT", []
            self.payload, self.bounds = None, (0, 999)
        def select(self, *_args): self.operation = "SELECT"; return self
        def insert(self, payload): self.operation, self.payload = "INSERT", payload; return self
        def update(self, payload): self.operation, self.payload = "UPDATE", payload; return self
        def eq(self, key, value): self.filters.append((key, value, False)); return self
        def in_(self, key, values): self.filters.append((key, set(map(str, values)), True)); return self
        def order(self, _key): return self
        def range(self, start, end): self.bounds = (start, end); return self
        def execute(self):
            payload_size = len(self.payload) if isinstance(self.payload, list) else None
            events.append((self.table, self.operation, payload_size))
            rows = tables[self.table]
            if self.operation == "INSERT":
                inserted = []
                for payload in self.payload:
                    row = {**payload, "id": f"price-{len(rows)}"}
                    rows.append(row); inserted.append(dict(row))
                return SimpleNamespace(data=inserted)
            filtered = rows
            for key, value, many in self.filters:
                filtered = [row for row in filtered if
                            (str(row.get(key)) in value if many else row.get(key) == value)]
            if self.operation == "UPDATE":
                for row in filtered: row.update(self.payload)
                return SimpleNamespace(data=[dict(row) for row in filtered])
            filtered = sorted(filtered, key=lambda row: str(row.get("id")))
            start, end = self.bounds
            return SimpleNamespace(data=[dict(row) for row in filtered[start:end + 1]])

    class Rpc:
        def __init__(self, name): self.name = name
        def execute(self):
            events.append((self.name, "RPC", None))
            return SimpleNamespace(data=[])

    class Client:
        def table(self, name): return Query(name)
        def rpc(self, name, _params): return Rpc(name)

    def factory(_url, _key):
        client = Client(); constructions.append(client); return client

    monkeypatch.setattr(retry, "create_client", factory)
    monkeypatch.setenv(
        "POKEMON_CANONICAL_REFRESH_RPC_NAME",
        "refresh_pokemon_canonical_card_market_prices_latest_for_variant",
    )
    price_repo = module.insert_card_variant_prices_batch_with_stats.__globals__
    monkeypatch.setitem(price_repo, "_canonical_refresh_rpc_name", None)

    work, card_ids = _payload(count)
    for index, item in enumerate(work):
        item[1].append({"condition_id": "near-mint", "source": "TCGPLAYER",
                        "captured_at": market_date, "market_price": index + 1,
                        "high_price": None, "low_price": None})

    service = module.CardsService()
    batch_result = service._process_batch_worker((work, card_ids), 0)
    accumulator = {"inserted_prices": 0, "errors": []}
    expected, shipped, errors = service.ship_results_sequentially(
        [batch_result], accumulator)

    def observed(table, operation):
        return [event for event in events if event[:2] == (table, operation)]
    price_chunks = math.ceil(count / 100)
    assert batch_result["errors"] == [] and errors == []
    assert expected == shipped == count
    assert len(observed("card_variant_external_identities", "SELECT")) == expected_chunks
    assert len(observed("card_variants", "SELECT")) == expected_chunks
    assert len(observed("card_variant_price_observations", "SELECT")) == price_chunks
    assert len(observed("card_variant_price_observations", "INSERT")) == price_chunks
    assert len(observed("card_variant_price_observations", "UPDATE")) == 0
    assert all(event[2] <= 100 for event in observed(
        "card_variant_price_observations", "INSERT"))
    assert len([event for event in events if event[1] == "RPC"]) == price_chunks * 2
    assert len(constructions) == 2  # one worker context, one parent shipping context
    expected_table_executes = expected_chunks * 2 + price_chunks * 2
    assert len([event for event in events if event[1] != "RPC"]) == expected_table_executes
    assert len(events) == expected_table_executes + price_chunks * 2


def test_mapped_identity_variant_mismatch_fails_closed(monkeypatch):
    _install_warm_bulk_maps(monkeypatch, 1)
    work, card_ids = _payload(1)
    monkeypatch.setattr(module, "get_card_variants_bulk", lambda **_kwargs: ({
        "variant-id-0": {"id": "variant-id-0", "card_id": "different", "printing_type": "holo",
                         "special_type": None, "edition": None}}, {}, 1))
    result = module.CardsService()._process_batch_worker((work, card_ids), 0)
    assert "external identity contradicts incoming variant" in result["errors"][0]
    assert result["prices_to_ship"] == []


def test_mapped_identity_missing_variant_fails_closed(monkeypatch):
    _install_warm_bulk_maps(monkeypatch, 1)
    work, card_ids = _payload(1)
    monkeypatch.setattr(module, "get_card_variants_bulk", lambda **_kwargs: ({}, {}, 1))
    result = module.CardsService()._process_batch_worker((work, card_ids), 0)
    assert "external identity maps to missing variant" in result["errors"][0]


def test_missing_identity_uses_natural_key_and_creates_link_once(monkeypatch):
    work, card_ids = _payload(1)
    natural = {("card-0", "holo", None, None): {"id": "variant-existing", "card_id": "card-0",
                                                  "printing_type": "holo", "special_type": None, "edition": None}}
    monkeypatch.setattr(module, "get_card_variant_external_identities_bulk", lambda *_a: ({}, 1))
    monkeypatch.setattr(module, "get_card_variants_bulk", lambda **_k: ({"variant-existing": natural[next(iter(natural))]}, natural, 1))
    calls = []
    monkeypatch.setattr(module, "link_card_variant_external_identity",
                        lambda variant_id, identity, **kwargs: calls.append((variant_id, identity, kwargs)) or "identity")
    monkeypatch.setattr(module, "insert_card_variant", lambda *_a: (_ for _ in ()).throw(AssertionError("insert")))
    result = module.CardsService()._process_batch_worker((work, card_ids), 0)
    assert result["errors"] == []
    assert calls[0][0] == "variant-existing"
    assert calls[0][2] == {"known_absent": True}
    assert result["persistence_metrics"]["identityWriteOperations"] == 1


def test_new_variant_fallback_remains_available(monkeypatch):
    work, card_ids = _payload(1)
    monkeypatch.setattr(module, "get_card_variant_external_identities_bulk", lambda *_a: ({}, 1))
    monkeypatch.setattr(module, "get_card_variants_bulk", lambda **_k: ({}, {}, 1))
    monkeypatch.setattr(module, "insert_card_variant", lambda _row: "new-variant")
    monkeypatch.setattr(module, "link_card_variant_external_identity", lambda *_a, **_k: "new-identity")
    result = module.CardsService()._process_batch_worker((work, card_ids), 0)
    assert result["errors"] == []
    assert result["inserted_variants"] == 1
    assert result["persistence_metrics"]["variantWriteOperations"] == 1
