import os

from backend.scripts import ingest_pokemon_canonical_cards as ingest


def test_keyless_headers_omit_api_key(monkeypatch):
    monkeypatch.delenv("POKEMON_TCG_API_KEY", raising=False)

    headers = ingest.build_headers()

    assert headers["Accept"] == "application/json"
    assert headers["User-Agent"] == "EVRCalculator/1.0"
    assert "X-Api-Key" not in headers
    assert ingest.request_delay_seconds() >= 2.1


def test_configured_headers_include_api_key(monkeypatch):
    monkeypatch.setenv("POKEMON_TCG_API_KEY", "test-key")

    headers = ingest.build_headers()

    assert headers["X-Api-Key"] == "test-key"
    assert ingest.request_delay_seconds() == ingest.REQUEST_DELAY_SECONDS


def test_require_env_does_not_require_pokemon_api_key(monkeypatch):
    monkeypatch.setenv("SUPABASE_URL", "https://example.supabase.co")
    monkeypatch.setenv("SUPABASE_SERVICE_ROLE_KEY", "ci-placeholder-service-role-key")
    monkeypatch.delenv("POKEMON_TCG_API_KEY", raising=False)

    ingest.require_env()
