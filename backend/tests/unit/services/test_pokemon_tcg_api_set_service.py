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
    status_code = 200

    def raise_for_status(self):
        return None

    def json(self):
        return {"data": [ROW]}


class _Session:
    def __init__(self):
        self.calls = []

    def get(self, url, params=None, headers=None, timeout=None):
        self.calls.append({
            "url": url,
            "params": dict(params or {}),
            "headers": dict(headers or {}),
            "timeout": timeout,
        })
        return _Response()


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
