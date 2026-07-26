import httpx
import pytest
from postgrest.exceptions import APIError

from backend.db.services.data_service_health import (
    classify_data_service_error,
    is_transient_data_service_error,
)
from backend.scripts.snapshot_query_retry import run_snapshot_operation_with_retry


def test_transient_classifier_prefers_structured_postgrest_and_http_statuses():
    assert is_transient_data_service_error(
        APIError({"message": "schema cache unavailable", "code": "PGRST002", "hint": None, "details": None})
    )
    request = httpx.Request("GET", "https://example.test/rest/v1/table")
    response = httpx.Response(522, request=request)
    assert is_transient_data_service_error(httpx.HTTPStatusError("gateway", request=request, response=response))
    assert not classify_data_service_error(
        APIError({"message": "missing column", "code": "42703", "hint": None, "details": None})
    ).transient


def test_statement_timeout_is_transient():
    """57014 cancels the statement, not the connection.

    A cold TOAST read can exceed the statement timeout and then succeed on a
    retry once the pages are cached, so classifying it permanent turned a
    recoverable read into an empty published payload.
    """
    assert is_transient_data_service_error(
        APIError(
            {
                "message": "canceling statement due to statement timeout",
                "code": "57014",
                "hint": None,
                "details": None,
            }
        )
    )


def test_http_520_is_transient_like_its_neighbours():
    """520 sat outside the set while 521/522 were inside it."""
    request = httpx.Request("GET", "https://example.test/rest/v1/table")
    for status in (502, 503, 504, 520, 521, 522):
        response = httpx.Response(status, request=request)
        assert is_transient_data_service_error(
            httpx.HTTPStatusError("gateway", request=request, response=response)
        ), f"HTTP {status} must be transient"


def test_offline_snapshot_retry_uses_a_fresh_client_for_pgrst002():
    clients = []
    sleeps = []

    def client_factory():
        client = object()
        clients.append(client)
        return client

    def operation(client):
        if len(clients) < 3:
            raise APIError({"message": "temporarily unavailable", "code": "PGRST002", "hint": None, "details": None})
        return client

    result = run_snapshot_operation_with_retry(
        operation,
        operation_name="fixture",
        set_id="set-1",
        client_factory=client_factory,
        sleep=sleeps.append,
        jitter=lambda _start, _end: 0,
    )

    assert result is clients[-1]
    assert len(clients) == 3
    assert len({id(client) for client in clients}) == 3
    assert sleeps == [0.25, 0.5]


def test_offline_snapshot_retry_does_not_retry_semantic_errors():
    attempts = []

    with pytest.raises(APIError):
        run_snapshot_operation_with_retry(
            lambda client: (attempts.append(client), (_ for _ in ()).throw(
                APIError({"message": "missing column", "code": "42703", "hint": None, "details": None})
            ))[1],
            operation_name="fixture",
            client_factory=object,
            sleep=lambda _delay: None,
        )

    assert len(attempts) == 1
