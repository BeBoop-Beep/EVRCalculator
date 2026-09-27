from unittest.mock import MagicMock, patch

from backend.db.repositories import sealed_product_prices_repository as repository
from backend.db.repositories.sealed_product_prices_repository import get_latest_price


@patch("backend.db.repositories.sealed_product_prices_repository.create_client")
def test_get_latest_price_uses_latest_market_view(mock_create_client):
    client = MagicMock()
    query = MagicMock()
    mock_create_client.return_value = client
    client.table.return_value = query
    query.select.return_value = query
    query.eq.return_value = query
    query.maybe_single.return_value = query

    response = MagicMock()
    response.data = {"sealed_product_id": 987, "market_price": 44.5}
    query.execute.return_value = response

    result = get_latest_price(987)

    client.table.assert_called_once_with("sealed_product_market_usd_latest")
    assert result == {"sealed_product_id": 987, "market_price": 44.5}


@patch("backend.db.repositories.sealed_product_prices_repository.create_client")
def test_get_latest_price_returns_none_when_missing(mock_create_client):
    client = MagicMock()
    query = MagicMock()
    mock_create_client.return_value = client
    client.table.return_value = query
    query.select.return_value = query
    query.eq.return_value = query
    query.maybe_single.return_value = query

    response = MagicMock()
    response.data = None
    query.execute.return_value = response

    assert get_latest_price(111) is None


def test_batch_insert_retries_statement_timeout_and_reconciles_landed_rows(monkeypatch):
    fetch_calls = []
    retry_operations = []

    def fake_fetch(rows, *, client=None):
        fetch_calls.append(client)
        if len(fetch_calls) == 1:
            return {}, 1
        identity = repository._identity_key(rows[0])
        return {
            identity: {
                "id": 77,
                "sealed_product_id": rows[0]["sealed_product_id"],
                "source": rows[0]["source"],
                "captured_at": rows[0]["captured_at"],
                "market_price": rows[0]["market_price"],
                "low_price": rows[0].get("low_price"),
            }
        }, 1

    class FailingInsertClient:
        def table(self, _name):
            return self

        def insert(self, _rows):
            return self

        def execute(self):
            raise RuntimeError(
                "canceling statement due to statement timeout code=57014"
            )

    def fake_retry(operation, *, operation_name, **_kwargs):
        retry_operations.append(operation_name)
        if operation_name.endswith("same_day_dedupe_read"):
            return operation(object(), 1)
        try:
            return operation(FailingInsertClient(), 1)
        except RuntimeError as exc:
            assert "57014" in str(exc)
            return operation(object(), 2)

    monkeypatch.setattr(
        repository,
        "_fetch_existing_same_day_observations",
        fake_fetch,
    )
    monkeypatch.setattr(
        repository,
        "run_supabase_with_transient_retry",
        fake_retry,
    )

    stats = repository.insert_sealed_product_prices_batch_with_stats(
        [
            {
                "sealed_product_id": 9,
                "market_price": 12.34,
                "source": "TCGPlayer",
                "captured_at": "2026-09-22",
            }
        ]
    )

    assert stats["attempted_rows"] == 1
    assert stats["inserted_count"] == 1
    assert stats["inserted_ids"] == [77]
    assert stats["skipped_duplicates"] == 0
    assert retry_operations == [
        "sealed_product_price_observations.same_day_dedupe_read",
        "sealed_product_price_observations.batch_insert",
    ]
    assert len(fetch_calls) == 2
