from backend.services.pokemon_tcg_api_set_service import resolve_set_metadata


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
