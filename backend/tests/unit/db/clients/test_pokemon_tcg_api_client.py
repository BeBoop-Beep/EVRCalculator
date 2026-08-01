"""Unit coverage for the Pokemon TCG API client's retry and pagination resilience.

The provider behind api.pokemontcg.io returns HTTP 500 intermittently (~50% of
identical requests were observed failing for set ``me5``), so a single fatal
request aborted whole set syncs. These tests pin the bounded retry policy and
the bounded pagination fallbacks that make a complete fetch reachable.

All HTTP is faked; nothing here touches the live API.
"""

import json

import pytest
import requests

from backend.db.clients.pokemon_tcg_api_client import (
    DEFAULT_SELECT_FIELDS,
    PokemonTCGAPIClient,
    PokemonTCGAPIError,
)


# ---------------------------------------------------------------------------
# Fakes
# ---------------------------------------------------------------------------


class _FakeResponse:
    """Minimal stand-in for ``requests.Response``."""

    def __init__(self, status_code=200, payload=None, headers=None, text=None, bad_json=False):
        self.status_code = status_code
        self._payload = payload if payload is not None else {}
        self.headers = headers or {}
        self._bad_json = bad_json
        self.text = text if text is not None else json.dumps(self._payload)

    def json(self):
        if self._bad_json:
            raise ValueError("Expecting value: line 1 column 1 (char 0)")
        return self._payload


class _FakeSession:
    """Replays a scripted sequence of responses/exceptions and records calls."""

    def __init__(self, outcomes):
        self._outcomes = list(outcomes)
        self.calls = []

    def get(self, url, params=None, headers=None, timeout=None):
        self.calls.append(
            {"url": url, "params": dict(params or {}), "headers": dict(headers or {}), "timeout": timeout}
        )
        if not self._outcomes:
            raise AssertionError(f"unexpected extra request: {url} {params}")
        outcome = self._outcomes.pop(0)
        if isinstance(outcome, Exception):
            raise outcome
        return outcome


def _card(card_id, number, name="Tropius"):
    return {
        "id": card_id,
        "name": name,
        "number": str(number),
        "images": {
            "small": f"https://images.example/{card_id}/small",
            "large": f"https://images.example/{card_id}/large",
        },
        "set": {"id": "me5", "name": "Pitch Black"},
    }


def _cards_page(ids, total_count=120):
    return _FakeResponse(payload={"data": [_card(f"me5-{i}", i) for i in ids], "totalCount": total_count})


def _server_error(status=500):
    return _FakeResponse(status_code=status, payload={"status": status, "error": "Internal Server Error"})


def _make_client(session, **kwargs):
    """Build a client with zero real delays."""
    sleeps = kwargs.pop("sleeps", None)
    if sleeps is None:
        sleeps = []
    client = PokemonTCGAPIClient(
        api_key="test-secret-key",
        session=session,
        sleep=sleeps.append,
        jitter=lambda _a, _b: 0.0,
        **kwargs,
    )
    client._recorded_sleeps = sleeps
    return client


# ---------------------------------------------------------------------------
# Request-level retries
# ---------------------------------------------------------------------------


def test_retries_two_server_errors_then_succeeds():
    session = _FakeSession([_server_error(), _server_error(), _cards_page([1], total_count=1)])
    sleeps = []
    client = _make_client(session, sleeps=sleeps)

    result = client._request_json("/cards", {"q": "set.id:me5"})

    assert result["totalCount"] == 1
    assert len(session.calls) == 3
    assert sleeps == [1.0, 2.0]


def test_retries_read_timeout_then_succeeds():
    session = _FakeSession([requests.Timeout("read timed out"), _cards_page([1], total_count=1)])
    client = _make_client(session)

    assert client._request_json("/cards", {})["totalCount"] == 1
    assert len(session.calls) == 2


def test_retries_connection_error_then_succeeds():
    session = _FakeSession([requests.ConnectionError("conn reset"), _cards_page([1], total_count=1)])
    client = _make_client(session)

    assert client._request_json("/cards", {})["totalCount"] == 1
    assert len(session.calls) == 2


@pytest.mark.parametrize("status", [401, 403])
def test_auth_errors_fail_immediately_without_retry(status):
    session = _FakeSession([_FakeResponse(status_code=status, payload={"error": "nope"})])
    sleeps = []
    client = _make_client(session, sleeps=sleeps)

    with pytest.raises(PokemonTCGAPIError) as excinfo:
        client._request_json("/cards", {})

    assert excinfo.value.status_code == status
    assert excinfo.value.retryable is False
    assert excinfo.value.attempts == 1
    assert len(session.calls) == 1
    assert sleeps == []


def test_rate_limit_honors_numeric_retry_after_within_bound():
    session = _FakeSession(
        [
            _FakeResponse(status_code=429, headers={"Retry-After": "3"}, payload={}),
            _cards_page([1], total_count=1),
        ]
    )
    sleeps = []
    client = _make_client(session, sleeps=sleeps)

    assert client._request_json("/cards", {})["totalCount"] == 1
    assert sleeps == [3.0]


def test_rate_limit_caps_absurd_retry_after_and_ignores_garbage():
    session = _FakeSession(
        [
            _FakeResponse(status_code=429, headers={"Retry-After": "99999"}, payload={}),
            _FakeResponse(status_code=429, headers={"Retry-After": "soon"}, payload={}),
            _cards_page([1], total_count=1),
        ]
    )
    sleeps = []
    client = _make_client(session, sleeps=sleeps, max_retry_after_seconds=30.0)

    assert client._request_json("/cards", {})["totalCount"] == 1
    # first sleep clamped to the bound, second falls back to exponential backoff
    assert sleeps == [30.0, 2.0]


def test_persistent_503_stops_after_max_attempts_with_structured_error():
    session = _FakeSession([_server_error(503) for _ in range(4)])
    sleeps = []
    client = _make_client(session, sleeps=sleeps)

    with pytest.raises(PokemonTCGAPIError) as excinfo:
        client._request_json("/cards", {"q": "set.id:me5", "page": 2, "pageSize": 100})

    err = excinfo.value
    assert err.status_code == 503
    assert err.retryable is True
    assert err.attempts == 4
    assert err.path == "/cards"
    assert err.params["page"] == 2
    assert len(session.calls) == 4
    assert sleeps == [1.0, 2.0, 4.0]


def test_invalid_json_raises_clear_api_error():
    session = _FakeSession([_FakeResponse(bad_json=True)])
    client = _make_client(session)

    with pytest.raises(PokemonTCGAPIError) as excinfo:
        client._request_json("/cards", {})

    message = str(excinfo.value)
    assert "invalid JSON" in message
    assert isinstance(excinfo.value.original, ValueError)


def test_non_retryable_client_error_fails_immediately():
    session = _FakeSession([_FakeResponse(status_code=422, payload={"error": "bad"})])
    client = _make_client(session)

    with pytest.raises(PokemonTCGAPIError) as excinfo:
        client._request_json("/cards", {})

    assert excinfo.value.status_code == 422
    assert excinfo.value.retryable is False
    assert len(session.calls) == 1


def test_explicit_connect_and_read_timeouts_are_sent():
    session = _FakeSession([_cards_page([1], total_count=1)])
    client = _make_client(session, connect_timeout=7.5, read_timeout=42.0)

    client._request_json("/cards", {})

    assert session.calls[0]["timeout"] == (7.5, 42.0)


# ---------------------------------------------------------------------------
# Payload control and secret hygiene
# ---------------------------------------------------------------------------


def test_card_request_includes_select_fields():
    session = _FakeSession([_cards_page(range(1, 4), total_count=3)])
    client = _make_client(session)

    list(client.iter_cards_for_set("me5", rate_limit_delay=0))

    assert session.calls[0]["params"]["select"] == DEFAULT_SELECT_FIELDS


def test_select_fields_cover_everything_normalize_card_needs():
    """The select list must actually carry images and set through normalization."""
    session = _FakeSession([_cards_page([1], total_count=1)])
    client = _make_client(session)

    selected = set(DEFAULT_SELECT_FIELDS.split(","))
    assert selected == {"id", "name", "number", "images", "set"}

    normalized = list(client.iter_cards_for_set("me5", rate_limit_delay=0))[0]
    assert normalized == {
        "pokemon_tcg_api_id": "me5-1",
        "set_id": "me5",
        "set_name": "Pitch Black",
        "number": "1",
        "name": "Tropius",
        "image_small_url": "https://images.example/me5-1/small",
        "image_large_url": "https://images.example/me5-1/large",
    }


def test_api_key_is_sent_but_never_leaked_into_errors(caplog):
    session = _FakeSession([_server_error() for _ in range(4)])
    client = _make_client(session)

    with caplog.at_level("WARNING"):
        with pytest.raises(PokemonTCGAPIError) as excinfo:
            client._request_json("/cards", {"q": "set.id:me5"})

    assert session.calls[0]["headers"]["X-Api-Key"] == "test-secret-key"

    err = excinfo.value
    leaked_surfaces = [str(err), repr(err), json.dumps(err.params), caplog.text]
    for surface in leaked_surfaces:
        assert "test-secret-key" not in surface
    assert "X-Api-Key" not in json.dumps(err.params)


# ---------------------------------------------------------------------------
# Pagination and fallback strategies
# ---------------------------------------------------------------------------


def test_full_fetch_over_two_pages_sleeps_once_between_pages():
    session = _FakeSession(
        [
            _cards_page(range(1, 101)),
            _cards_page(range(101, 121)),
        ]
    )
    sleeps = []
    client = _make_client(session, sleeps=sleeps)

    cards = list(client.iter_cards_for_set("me5", rate_limit_delay=0.1))

    assert len(cards) == 120
    # exactly one inter-page delay, not the duplicated pair the old loop emitted
    assert sleeps == [0.1]


def test_falls_back_to_smaller_page_size_and_still_returns_all_120_unique_cards():
    """Page 2 keeps failing at pageSize=100; strategy 2 restarts at 50 and completes."""
    outcomes = [_cards_page(range(1, 101))]
    outcomes += [_server_error() for _ in range(4)]  # page 2 @100 exhausts retries
    outcomes += [
        _cards_page(range(1, 51)),      # strategy 2 restarts at page 1
        _cards_page(range(51, 101)),
        _cards_page(range(101, 121)),
    ]
    session = _FakeSession(outcomes)
    client = _make_client(session)

    cards = list(client.iter_cards_for_set("me5", rate_limit_delay=0))

    ids = [card["pokemon_tcg_api_id"] for card in cards]
    assert len(ids) == 120
    assert len(set(ids)) == 120, "no API card may be emitted twice"
    assert set(ids) == {f"me5-{i}" for i in range(1, 121)}


def test_fallback_restart_suppresses_duplicates_and_keeps_page_size_stable():
    outcomes = [_cards_page(range(1, 101))]
    outcomes += [_server_error() for _ in range(4)]
    outcomes += [
        _cards_page(range(1, 51)),
        _cards_page(range(51, 101)),
        _cards_page(range(101, 121)),
    ]
    session = _FakeSession(outcomes)
    client = _make_client(session)

    list(client.iter_cards_for_set("me5", rate_limit_delay=0))

    fallback_calls = session.calls[5:]
    assert [call["params"]["page"] for call in fallback_calls] == [1, 2, 3], "must restart from page one"
    assert {call["params"]["pageSize"] for call in fallback_calls} == {50}, "page size must stay stable"


def test_third_strategy_drops_order_by():
    outcomes = [_server_error() for _ in range(4)]          # strategy 1 dies on page 1
    outcomes += [_server_error() for _ in range(4)]         # strategy 2 dies on page 1
    outcomes += [_cards_page(range(1, 51)), _cards_page(range(51, 101)), _cards_page(range(101, 121))]
    session = _FakeSession(outcomes)
    client = _make_client(session)

    cards = list(client.iter_cards_for_set("me5", rate_limit_delay=0))

    assert len(cards) == 120
    final_calls = session.calls[8:]
    assert all("orderBy" not in call["params"] for call in final_calls)
    assert {call["params"]["pageSize"] for call in final_calls} == {50}


def test_raises_rather_than_returning_partial_results_when_all_strategies_fail():
    outcomes = [_cards_page(range(1, 101))]
    outcomes += [_server_error() for _ in range(4)]   # strategy 1, page 2
    outcomes += [_server_error() for _ in range(4)]   # strategy 2, page 1
    outcomes += [_server_error() for _ in range(4)]   # strategy 3, page 1
    session = _FakeSession(outcomes)
    client = _make_client(session)

    collected = []
    with pytest.raises(PokemonTCGAPIError) as excinfo:
        for card in client.iter_cards_for_set("me5", rate_limit_delay=0):
            collected.append(card)

    message = str(excinfo.value)
    assert "me5" in message
    assert "100/120" in message
    assert "pageSize=100,orderBy=id" in message
    assert "pageSize=50,orderBy=id" in message
    assert "pageSize=50,orderBy=none" in message
    assert len(collected) == 100, "partial results must not be presented as success"


def test_incomplete_strategy_without_error_still_falls_back():
    """A strategy that runs out of pages below totalCount is incomplete, not done."""
    outcomes = [
        _cards_page(range(1, 101)),
        _FakeResponse(payload={"data": [], "totalCount": 120}),  # provider truncates
        _cards_page(range(1, 51)),
        _cards_page(range(51, 101)),
        _cards_page(range(101, 121)),
    ]
    session = _FakeSession(outcomes)
    client = _make_client(session)

    cards = list(client.iter_cards_for_set("me5", rate_limit_delay=0))
    assert len({card["pokemon_tcg_api_id"] for card in cards}) == 120


def test_empty_set_completes_without_error():
    session = _FakeSession([_FakeResponse(payload={"data": [], "totalCount": 0})])
    client = _make_client(session)

    assert list(client.iter_cards_for_set("me5", rate_limit_delay=0)) == []


def test_completion_summary_reports_totals(caplog):
    session = _FakeSession([_cards_page(range(1, 101)), _cards_page(range(101, 121))])
    client = _make_client(session)

    with caplog.at_level("INFO"):
        list(client.iter_cards_for_set("me5", rate_limit_delay=0))

    assert "completed set='me5'" in caplog.text
    assert "unique_cards=120" in caplog.text
    assert "reported_total=120" in caplog.text
    assert "pages_requested=2" in caplog.text
