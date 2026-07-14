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

    assert public_read_retry.run_public_read_with_retry(
        lambda client: client,
        operation_name="fixture",
        initial_client="normal-initial",
        client_factory=lambda: "unused",
        monotonic=lambda: clock[0],
    ) == "normal-initial"
