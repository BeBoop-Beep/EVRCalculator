import requests

from backend.services.pokemon_tcg_api_set_service import fetch_targeted_sets, resolve_set_metadata


ROW = {
    "id": "me5", "name": "Future Set", "series": "Mega Evolution",
    "releaseDate": "2026/08/01", "printedTotal": 100, "total": 120,
    "ptcgoCode": "FUT", "images": {"symbol": "https://api/symbol", "logo": "https://api/logo"},
}


def test_exact_metadata_resolution_returns_authoritative_fields():
    result = resolve_set_metadata("Fúture Set", [ROW])
    assert result.status == "resolved"
    assert result.set_data == ROW


def test_missing_and_ambiguous_metadata_are_not_guessed():
    assert resolve_set_metadata("Missing", [ROW]).status == "not_found"
    duplicate = {**ROW, "id": "me6"}
    assert resolve_set_metadata("Future Set", [ROW, duplicate]).status == "ambiguous"


def test_expected_api_identity_conflict_is_explicit():
    result = resolve_set_metadata("Future Set", [ROW], expected_api_id="different")
    assert result.status == "identity_conflict"


class _Response:
    def __init__(self, status_code=200, payload=None, headers=None):
        self.status_code = status_code
        self._payload = payload if payload is not None else {"data": [ROW]}
        self.headers = headers or {}

    def raise_for_status(self):
        if self.status_code >= 400:
            raise requests.HTTPError(f"HTTP {self.status_code}")

    def json(self):
        return self._payload


class _Session:
    def __init__(self, outcomes=None):
        self.calls = []
        self.outcomes = list(outcomes or [_Response()])

    def get(self, url, params=None, headers=None, timeout=None):
        self.calls.append({
            "url": url,
            "params": dict(params or {}),
            "headers": dict(headers or {}),
            "timeout": timeout,
        })
        if not self.outcomes:
            raise AssertionError("unexpected extra request")
        outcome = self.outcomes.pop(0)
        if isinstance(outcome, Exception):
            raise outcome
        return outcome


def test_fetch_targeted_sets_keyless_omits_api_header():
    session = _Session()

    rows = fetch_targeted_sets("Future Set", "", session=session)

    assert len(rows) == 1
    assert rows[0]["id"] == "me5"
    assert "X-Api-Key" not in session.calls[0]["headers"]
    assert session.calls[0]["headers"]["Accept"] == "application/json"


def test_fetch_targeted_sets_uses_api_key_when_available():
    session = _Session()

    fetch_targeted_sets("Future Set", "secret-key", session=session)

    assert session.calls[0]["headers"]["X-Api-Key"] == "secret-key"



def test_fetch_targeted_sets_retries_transient_500_then_succeeds():
    session = _Session([
        _Response(status_code=500, payload={"error": "temporary"}),
        _Response(status_code=500, payload={"error": "temporary"}),
        _Response(),
    ])
    sleeps = []

    rows = fetch_targeted_sets(
        "Future Set",
        "secret-key",
        session=session,
        max_attempts=3,
        sleep=sleeps.append,
    )

    assert rows[0]["id"] == "me5"
    assert len(session.calls) == 3
    assert sleeps == [1.0, 2.0]


def test_keyless_transient_retry_respects_unauthenticated_rate_floor():
    session = _Session([
        _Response(status_code=500, payload={"error": "temporary"}),
        _Response(),
    ])
    sleeps = []

    fetch_targeted_sets(
        "Future Set",
        "",
        session=session,
        max_attempts=2,
        sleep=sleeps.append,
    )

    assert sleeps == [2.1]


def test_rate_limit_honors_bounded_retry_after():
    session = _Session([
        _Response(status_code=429, payload={}, headers={"Retry-After": "999"}),
        _Response(),
    ])
    sleeps = []

    fetch_targeted_sets(
        "Future Set",
        "secret-key",
        session=session,
        max_attempts=2,
        sleep=sleeps.append,
    )

    assert sleeps == [30.0]


def test_non_retryable_error_fails_without_extra_request():
    session = _Session([_Response(status_code=422, payload={"error": "bad"})])
    sleeps = []

    try:
        fetch_targeted_sets(
            "Future Set",
            "",
            session=session,
            max_attempts=3,
            sleep=sleeps.append,
        )
    except requests.HTTPError:
        pass
    else:
        raise AssertionError("expected HTTPError")

    assert len(session.calls) == 1
    assert sleeps == []


def test_connection_error_retries_then_succeeds_keyless():
    session = _Session([
        requests.ConnectionError("reset"),
        _Response(),
    ])
    sleeps = []

    rows = fetch_targeted_sets(
        "Future Set",
        "",
        session=session,
        max_attempts=2,
        sleep=sleeps.append,
    )

    assert rows[0]["id"] == "me5"
    assert sleeps == [2.1]



class _ScrydexMetadata:
    def resolve_set(self, name):
        assert name == "30th Celebration"
        return {
            "id": "me55",
            "name": "30th Celebration",
            "series": "Mega Evolution",
            "releaseDate": "2026-09-16",
            "printedTotal": 128,
            "total": 161,
            "ptcgoCode": "M3",
            "images": {
                "symbol": "https://images.scrydex.com/pokemon/me55-symbol/symbol",
                "logo": "https://images.scrydex.com/pokemon/me55-logo/logo",
            },
        }


def test_fetch_targeted_sets_uses_scrydex_when_legacy_returns_no_match():
    session = _Session([_Response(payload={"data": []})])

    rows = fetch_targeted_sets(
        "30th Celebration",
        "",
        session=session,
        scrydex_client=_ScrydexMetadata(),
    )

    assert rows == [{
        "id": "me55",
        "name": "30th Celebration",
        "series": "Mega Evolution",
        "releaseDate": "2026-09-16",
        "printedTotal": 128,
        "total": 161,
        "ptcgoCode": "M3",
        "images": {
            "symbol": "https://images.scrydex.com/pokemon/me55-symbol/symbol",
            "logo": "https://images.scrydex.com/pokemon/me55-logo/logo",
        },
    }]
