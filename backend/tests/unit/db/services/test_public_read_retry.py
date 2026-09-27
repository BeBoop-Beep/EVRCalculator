import pytest
from postgrest.exceptions import APIError

from backend.db.services import public_read_retry


def _transient_error():
    return APIError(
        {
            "message": "schema cache unavailable",
            "code": "PGRST002",
            "hint": None,
            "details": None,
        }
    )


def _statement_timeout_error():
    return APIError(
        {
            "message": "canceling statement due to statement timeout",
            "code": "57014",
            "hint": None,
            "details": None,
        }
    )


def _permanent_error():
    return APIError(
        {
            "message": "column \"bogus\" does not exist",
            "code": "42703",
            "hint": None,
            "details": None,
        }
    )


@pytest.fixture(autouse=True)
def reset_circuit():
    public_read_retry._reset_public_read_circuit_breaker_for_tests()
    yield
    public_read_retry._reset_public_read_circuit_breaker_for_tests()


def test_live_retry_uses_initial_then_fresh_client():
    initial = object()
    fresh = object()
    seen = []
    sleeps = []

    def operation(client):
        seen.append(client)
        if client is initial:
            raise _transient_error()
        return "ok"

    result = public_read_retry.run_public_read_with_retry(
        operation,
        operation_name="fixture",
        initial_client=initial,
        client_factory=lambda: fresh,
        sleep=sleeps.append,
        jitter=lambda _start, _end: 0.25,
    )

    assert result == "ok"
    assert seen == [initial, fresh]
    assert sleeps == [0.25]


def test_open_circuit_suppresses_duplicate_retries():
    clock = [100.0]
    attempts = []

    def operation(client):
        attempts.append(client)
        raise _transient_error()

    with pytest.raises(APIError):
        public_read_retry.run_public_read_with_retry(
            operation,
            operation_name="fixture",
            initial_client="initial",
            client_factory=lambda: "fresh",
            sleep=lambda delay: clock.__setitem__(0, clock[0] + delay),
            jitter=lambda _start, _end: 0.25,
            monotonic=lambda: clock[0],
        )

    assert attempts == ["initial", "fresh"]

    with pytest.raises(public_read_retry.PublicReadCircuitOpenError):
        public_read_retry.run_public_read_with_retry(
            operation,
            operation_name="fixture",
            initial_client="another-initial",
            client_factory=lambda: "another-fresh",
            monotonic=lambda: clock[0],
        )

    assert attempts == ["initial", "fresh"]


def test_successful_half_open_probe_closes_circuit():
    clock = [100.0]

    with pytest.raises(APIError):
        public_read_retry.run_public_read_with_retry(
            lambda _client: (_ for _ in ()).throw(_transient_error()),
            operation_name="fixture",
            initial_client="initial",
            client_factory=lambda: "fresh",
            sleep=lambda delay: clock.__setitem__(0, clock[0] + delay),
            jitter=lambda _start, _end: 0.25,
            monotonic=lambda: clock[0],
        )

    clock[0] += 4.1
    probe_clients = []
    assert public_read_retry.run_public_read_with_retry(
        lambda client: probe_clients.append(client) or "probe-ok",
        operation_name="fixture",
        initial_client="stale-initial",
        client_factory=lambda: "probe-fresh",
        monotonic=lambda: clock[0],
    ) == "probe-ok"
    assert probe_clients == ["probe-fresh"]


# -- run_bounded_page_read_with_retry: Best-Open source-load 57014 hardening --


def test_bounded_page_retries_once_after_statement_timeout_then_succeeds():
    """One 57014 then success: only the failed page retries, no data lost."""
    attempts = []

    def operation():
        attempts.append(1)
        if len(attempts) == 1:
            raise _statement_timeout_error()
        return "page-data"

    result = public_read_retry.run_bounded_page_read_with_retry(
        operation,
        operation_name="fixture.page",
        page_offset=0,
        page_end=999,
        sleep=lambda _delay: None,
        jitter=lambda _start, _end: 0.0,
    )

    assert result == "page-data"
    assert len(attempts) == 2  # exactly one retry, observable via attempt count


def test_bounded_page_repeated_statement_timeout_fails_bounded_with_page_context():
    """Repeated 57014: bounded failure (no infinite loop); error names the page
    range and the exhausted attempt count."""
    attempts = []

    def operation():
        attempts.append(1)
        raise _statement_timeout_error()

    with pytest.raises(RuntimeError) as excinfo:
        public_read_retry.run_bounded_page_read_with_retry(
            operation,
            operation_name="fixture.page",
            page_offset=2000,
            page_end=2999,
            max_attempts=3,
            sleep=lambda _delay: None,
            jitter=lambda _start, _end: 0.0,
        )

    assert len(attempts) == 3  # bounded: exactly max_attempts, not infinite
    message = str(excinfo.value)
    assert "fixture.page" in message
    assert "[2000, 2999]" in message
    assert "3 attempt" in message


def test_bounded_page_permanent_error_is_not_retried():
    """A deterministic (non-57014) DB error must not be retried, and must
    surface as itself rather than a wrapped RuntimeError."""
    attempts = []

    def operation():
        attempts.append(1)
        raise _permanent_error()

    with pytest.raises(APIError):
        public_read_retry.run_bounded_page_read_with_retry(
            operation,
            operation_name="fixture.page",
            page_offset=0,
            page_end=999,
            sleep=lambda _delay: None,
            jitter=lambda _start, _end: 0.0,
        )

    assert len(attempts) == 1  # not retried at all
