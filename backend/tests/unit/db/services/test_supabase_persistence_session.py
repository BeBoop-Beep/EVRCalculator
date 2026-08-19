import pytest

from backend.db.services import supabase_persistence_retry as retry


class Factory:
    def __init__(self):
        self.clients = []

    def __call__(self):
        client = object()
        self.clients.append(client)
        return client


@pytest.fixture(autouse=True)
def _fast_retry(monkeypatch):
    monkeypatch.setattr(retry.time, "sleep", lambda _seconds: None)
    monkeypatch.setattr(retry.random, "uniform", lambda *_args: 0.0)


def test_healthy_operations_reuse_one_context_client():
    factory = Factory()
    seen = []
    with retry.scraper_persistence_session(retry.ScraperPersistenceSession(factory)):
        retry.run_supabase_with_transient_retry(
            lambda client, _attempt: seen.append(client), operation_name="identity")
        retry.run_supabase_with_transient_retry(
            lambda client, _attempt: seen.append(client), operation_name="variant")
        retry.run_supabase_with_transient_retry(
            lambda client, _attempt: seen.append(client), operation_name="price-1")
        retry.run_supabase_with_transient_retry(
            lambda client, _attempt: seen.append(client), operation_name="price-2")
    assert len(factory.clients) == 1
    assert len({id(client) for client in seen}) == 1


def test_transient_failure_discards_client_and_later_operation_reuses_replacement():
    factory = Factory()
    seen = []
    def flaky(client, attempt):
        seen.append(client)
        if attempt == 1:
            raise ConnectionError("Server disconnected")
        return "ok"
    with retry.scraper_persistence_session(retry.ScraperPersistenceSession(factory)):
        assert retry.run_supabase_with_transient_retry(flaky, operation_name="flaky") == "ok"
        retry.run_supabase_with_transient_retry(
            lambda client, _attempt: seen.append(client), operation_name="later")
    assert len(factory.clients) == 2
    assert seen[0] is factory.clients[0]
    assert seen[1] is seen[2] is factory.clients[1]


def test_two_transient_failures_construct_three_clients():
    factory = Factory()
    with retry.scraper_persistence_session(retry.ScraperPersistenceSession(factory)):
        retry.run_supabase_with_transient_retry(
            lambda _client, attempt: (_ for _ in ()).throw(ConnectionError("Server disconnected"))
            if attempt < 3 else "ok",
            operation_name="twice",
        )
    assert len(factory.clients) == 3


def test_deterministic_failure_does_not_retry_or_recreate_client():
    factory = Factory()
    session = retry.ScraperPersistenceSession(factory)
    with retry.scraper_persistence_session(session):
        with pytest.raises(ValueError, match="invalid data"):
            retry.run_supabase_with_transient_retry(
                lambda _client, _attempt: (_ for _ in ()).throw(ValueError("invalid data")),
                operation_name="deterministic",
            )
        retry.run_supabase_with_transient_retry(lambda client, _attempt: client,
                                                operation_name="later")
    assert len(factory.clients) == 1


def test_session_teardown_does_not_reuse_client_in_future_invocation():
    factory = Factory()
    for _ in range(2):
        with retry.scraper_persistence_session(retry.ScraperPersistenceSession(factory)):
            retry.run_supabase_with_transient_retry(lambda client, _attempt: client,
                                                    operation_name="invocation")
    assert len(factory.clients) == 2
