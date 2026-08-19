from types import SimpleNamespace

import pytest

from backend.db.repositories import card_variant_repository as repo
from backend.db.services import supabase_persistence_retry as retry


class Backend:
    def __init__(self, rows, errors=None):
        self.rows = rows
        self.errors = list(errors or [])
        self.clients = 0
        self.calls = []
    def client(self, *_): self.clients += 1; return Client(self)


class Client:
    def __init__(self, backend): self.backend = backend
    def table(self, name): return Query(self.backend, name)


class Query:
    def __init__(self, backend, table):
        self.backend, self.table_name, self.filters = backend, table, []
    def select(self, *_): return self
    def eq(self, column, value): self.filters.append((column, value, False)); return self
    def in_(self, column, values): self.filters.append((column, set(values), True)); return self
    def order(self, _column): return self
    def range(self, start, end): self.start, self.end = start, end; return self
    def execute(self):
        self.backend.calls.append((self.table_name, tuple(self.filters)))
        if self.backend.errors:
            error = self.backend.errors.pop(0)
            if error: raise error
        rows = self.backend.rows.get(self.table_name, [])
        for column, value, is_in in self.filters:
            rows = [row for row in rows if (str(row.get(column)) in {str(v) for v in value}
                                             if is_in else row.get(column) == value)]
        return SimpleNamespace(data=rows[getattr(self, "start", 0):getattr(self, "end", len(rows) - 1) + 1])


@pytest.fixture
def fast_retry(monkeypatch):
    monkeypatch.setattr(retry.time, "sleep", lambda _seconds: None)
    monkeypatch.setattr(retry.random, "uniform", lambda *_args: 0.0)
    return lambda backend: monkeypatch.setattr(retry, "create_client", backend.client)


def test_bulk_identity_queries_are_bounded_and_select_requested_keys(fast_retry):
    rows = [{"id": f"i-{i}", "provider": "tcgplayer", "external_product_id": str(i),
             "external_variant_key": f"k-{i}", "card_variant_id": f"v-{i}"} for i in range(400)]
    backend = Backend({"card_variant_external_identities": rows}); fast_retry(backend)
    found, operations = repo.get_card_variant_external_identities_bulk(
        "tcgplayer", [(str(i), f"k-{i}") for i in range(400)])
    assert len(found) == 400
    assert operations == backend.clients == 3


def test_bulk_identity_duplicate_exact_key_fails_closed(fast_retry):
    row = {"provider": "tcgplayer", "external_product_id": "1", "external_variant_key": "k",
           "card_variant_id": "v"}
    backend = Backend({"card_variant_external_identities": [{"id": "a", **row}, {"id": "b", **row}]})
    fast_retry(backend)
    with pytest.raises(repo.AmbiguousExternalVariantIdentity):
        repo.get_card_variant_external_identities_bulk("tcgplayer", [("1", "k")])


def test_transient_bulk_identity_read_retries_with_new_client(fast_retry):
    backend = Backend({"card_variant_external_identities": []}, [ConnectionError("Server disconnected")])
    fast_retry(backend)
    repo.get_card_variant_external_identities_bulk("tcgplayer", [("1", "k")])
    assert backend.clients == 2


def test_transient_bulk_variant_read_retries_with_new_client(fast_retry):
    backend = Backend({"card_variants": [{"id": "v", "card_id": "c", "printing_type": "holo",
                                           "special_type": None, "edition": None}]},
                      [ConnectionError("Server disconnected")])
    fast_retry(backend)
    by_id, by_natural, operations = repo.get_card_variants_bulk(variant_ids=["v"], card_ids=[])
    assert by_id["v"]["card_id"] == "c"
    assert by_natural[("c", "holo", None, None)]["id"] == "v"
    assert operations == 1
    assert backend.clients == 2


def test_bulk_identity_read_pages_past_server_row_limit(fast_retry):
    rows = [{"id": f"i-{i:04d}", "provider": "tcgplayer", "external_product_id": "1",
             "external_variant_key": f"k-{i}", "card_variant_id": f"v-{i}"}
            for i in range(1001)]
    backend = Backend({"card_variant_external_identities": rows}); fast_retry(backend)
    found, operations = repo.get_card_variant_external_identities_bulk(
        "tcgplayer", [("1", f"k-{i}") for i in range(1001)])
    assert len(found) == 1001
    assert operations == 2


def test_bulk_variant_read_pages_past_server_row_limit(fast_retry):
    rows = [{"id": f"v-{i:04d}", "card_id": "card-1",
             "printing_type": f"printing-{i}", "special_type": None, "edition": None}
            for i in range(1001)]
    backend = Backend({"card_variants": rows}); fast_retry(backend)
    by_id, by_natural, operations = repo.get_card_variants_bulk(
        variant_ids=[], card_ids=["card-1"])
    assert len(by_id) == len(by_natural) == 1001
    assert set(by_id) == {row["id"] for row in rows}
    assert operations == 2
