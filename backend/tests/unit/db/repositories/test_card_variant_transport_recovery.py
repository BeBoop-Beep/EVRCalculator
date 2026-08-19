import ssl
from types import SimpleNamespace

import pytest

from backend.db.repositories import card_variant_prices_repository as prices
from backend.db.services import supabase_persistence_retry as retry


class TransportStatus(Exception):
    def __init__(self, status):
        super().__init__(f"HTTP {status}")
        self.status_code = status


class Backend:
    def __init__(self, errors=None, commit_on_error=False):
        self.rows = []
        self.errors = list(errors or [])
        self.commit_on_error = commit_on_error
        self.insert_payloads = []
        self.client_count = 0

    def client(self, *_):
        self.client_count += 1
        return Client(self)


class Client:
    def __init__(self, backend): self.backend = backend
    def table(self, _name): return Query(self.backend)


class Query:
    def __init__(self, backend):
        self.backend = backend
        self.mode = "select"
        self.payload = None
        self.filters = []
    def select(self, *_): self.mode = "select"; return self
    def in_(self, column, values): self.filters.append((column, set(values), "in")); return self
    def eq(self, column, value): self.filters.append((column, value, "eq")); return self
    def insert(self, payload): self.mode = "insert"; self.payload = [dict(row) for row in payload]; return self
    def update(self, payload): self.mode = "update"; self.payload = dict(payload); return self
    def execute(self):
        if self.mode == "select":
            rows = list(self.backend.rows)
            for column, value, kind in self.filters:
                rows = [row for row in rows if (row.get(column) in value if kind == "in" else row.get(column) == value)]
            return SimpleNamespace(data=[dict(row) for row in rows])
        if self.mode == "update":
            for row in self.backend.rows:
                if all(row.get(column) == value for column, value, _ in self.filters):
                    row.update(self.payload)
            return SimpleNamespace(data=[])
        self.backend.insert_payloads.append(self.payload)
        error = self.backend.errors.pop(0) if self.backend.errors else None
        if error and self.backend.commit_on_error:
            self._commit()
        if error:
            raise error
        return SimpleNamespace(data=self._commit())
    def _commit(self):
        committed = []
        for payload in self.payload:
            row = {**payload, "id": len(self.backend.rows) + 1}
            self.backend.rows.append(row)
            committed.append(row)
        return committed


def make_rows(count):
    return [{"card_variant_id": f"v-{i}", "condition_id": "nm", "source": "TCGPLAYER",
             "captured_at": "2026-08-19", "market_price": i + 1} for i in range(count)]


@pytest.fixture
def recovery(monkeypatch):
    monkeypatch.setattr(prices, "_refresh_pokemon_set_value_history_for_price_rows", lambda _rows: None)
    monkeypatch.setattr(retry.time, "sleep", lambda _seconds: None)
    monkeypatch.setattr(retry.random, "uniform", lambda _a, _b: 0.0)
    def install(backend):
        monkeypatch.setattr(retry, "create_client", backend.client)
        return backend
    return install


def test_server_disconnected_then_succeeds(recovery):
    backend = recovery(Backend([ConnectionError("Server disconnected")]))
    result = prices.insert_card_variant_prices_batch_with_stats(make_rows(2))
    assert result["inserted_count"] == 2
    assert len(backend.rows) == 2
    assert backend.client_count == 2


def test_ssl_error_then_succeeds(recovery):
    backend = recovery(Backend([ssl.SSLError("SSLV3_ALERT_BAD_RECORD_MAC")]))
    assert prices.insert_card_variant_prices_batch_with_stats(make_rows(1))["inserted_count"] == 1
    assert backend.client_count == 2


@pytest.mark.parametrize("status", [502, 503, 504])
def test_gateway_statuses_retry(recovery, status):
    backend = recovery(Backend([TransportStatus(status)]))
    assert prices.insert_card_variant_prices_batch_with_stats(make_rows(1))["inserted_count"] == 1
    assert backend.client_count == 2


def test_deterministic_400_does_not_retry(recovery):
    backend = recovery(Backend([TransportStatus(400)]))
    with pytest.raises(TransportStatus):
        prices.insert_card_variant_prices_batch_with_stats(make_rows(1))
    assert backend.client_count == 1


def test_lost_insert_response_reconciles_without_duplicate(recovery):
    backend = recovery(Backend([ConnectionError("Server disconnected")], commit_on_error=True))
    result = prices.insert_card_variant_prices_batch_with_stats(make_rows(3))
    assert result["inserted_count"] == 3
    assert len(backend.rows) == 3
    assert len(backend.insert_payloads) == 1


def test_742_rows_are_chunked_to_at_most_100(recovery):
    backend = recovery(Backend())
    result = prices.insert_card_variant_prices_batch_with_stats(make_rows(742))
    assert result["attempted_rows"] == 742
    assert [len(payload) for payload in backend.insert_payloads] == [100] * 7 + [42]


def test_middle_chunk_retry_does_not_resend_completed_chunks(recovery):
    backend = recovery(Backend([None, ConnectionError("Server disconnected")]))
    result = prices.insert_card_variant_prices_batch_with_stats(make_rows(250))
    assert result["inserted_count"] == 250
    assert [len(payload) for payload in backend.insert_payloads] == [100, 100, 100, 50]
    assert len({row["card_variant_id"] for row in backend.rows}) == 250


def test_exhausted_transport_retries_fail_closed(recovery):
    backend = recovery(Backend([ConnectionError("Server disconnected")] * 3))
    with pytest.raises(ConnectionError, match="Server disconnected"):
        prices.insert_card_variant_prices_batch_with_stats(make_rows(1))
    assert backend.client_count == 3


def test_small_success_behavior_and_attempt_count_are_unchanged(recovery):
    backend = recovery(Backend())
    result = prices.insert_card_variant_prices_batch_with_stats(make_rows(4))
    assert result["attempted_rows"] == result["inserted_count"] == 4
    assert len(backend.insert_payloads) == 1


def test_set_session_reuses_one_client_across_all_price_chunks(recovery):
    backend = recovery(Backend())
    with retry.scraper_persistence_session():
        result = prices.insert_card_variant_prices_batch_with_stats(make_rows(742))
    assert result["inserted_count"] == 742
    assert backend.client_count == 1


def test_middle_chunk_transient_replaces_client_for_remaining_chunks(recovery):
    backend = recovery(Backend([None, ConnectionError("Server disconnected")]))
    with retry.scraper_persistence_session():
        result = prices.insert_card_variant_prices_batch_with_stats(make_rows(250))
    assert result["inserted_count"] == 250
    assert backend.client_count == 2
    assert len({row["card_variant_id"] for row in backend.rows}) == 250
