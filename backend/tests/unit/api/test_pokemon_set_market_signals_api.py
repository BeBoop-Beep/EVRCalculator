import json

import pytest
from fastapi import HTTPException, Request

from backend.api import main
from backend.db.services.pokemon_set_market_service import PokemonSetMarketError


def _request():
    return Request({"type": "http", "method": "GET", "path": "/", "headers": [], "client": ("test", 1)})


def test_basic_is_denied_before_market_signals_database_read(monkeypatch):
    monkeypatch.setattr(main, "_require_authenticated_user_id", lambda **_kwargs: "base-user")
    monkeypatch.setattr(main, "_resolve_index_plan", lambda *_args: None)
    monkeypatch.setattr(main, "get_pokemon_set_market_signals_snapshot_payload", lambda **_kwargs: pytest.fail("DB reader must not run"))
    with pytest.raises(HTTPException) as caught:
        main.get_pokemon_set_market_signals(_request(), "set-id")
    assert caught.value.status_code == 403
    assert caught.value.detail["code"] == "INDEX_PLUS_REQUIRED"


@pytest.mark.parametrize("plan", ["plus", "premium"])
def test_paid_plans_receive_compact_signals(monkeypatch, plan):
    monkeypatch.setattr(main, "_require_authenticated_user_id", lambda **_kwargs: "paid-user")
    payload = {"set": {"id": "set-id"}, "window": "365d", "marketBreadth": {"7D": {"available": True}}}
    monkeypatch.setattr(main, "_resolve_index_plan", lambda *_args: plan)
    monkeypatch.setattr(main, "get_pokemon_set_market_signals_snapshot_payload", lambda **_kwargs: payload)
    response = main.get_pokemon_set_market_signals(_request(), "set-id")
    assert response.status_code == 200
    assert json.loads(response.body) == payload
    assert response.headers["cache-control"] == "no-store"
    assert response.headers["vary"] == "Cookie, Authorization"


def test_incomplete_signals_publication_is_retryable_503(monkeypatch):
    monkeypatch.setattr(main, "_require_authenticated_user_id", lambda **_kwargs: "paid-user")
    monkeypatch.setattr(main, "_resolve_index_plan", lambda *_args: "plus")
    def fail(**_kwargs):
        raise PokemonSetMarketError(503, "incomplete", "POKEMON_SET_MARKET_SIGNALS_SNAPSHOT_INCOMPLETE")
    monkeypatch.setattr(main, "get_pokemon_set_market_signals_snapshot_payload", fail)
    response = main.get_pokemon_set_market_signals(_request(), "set-id")
    body = json.loads(response.body)
    assert response.status_code == 503
    assert body == {"message": "incomplete", "code": "POKEMON_SET_MARKET_SIGNALS_SNAPSHOT_INCOMPLETE", "retryable": True}


def test_route_directory_final_failure_is_retryable_503(monkeypatch):
    monkeypatch.setattr(main, "get_pokemon_set_route_directory_payload", lambda **_kwargs: (_ for _ in ()).throw(RuntimeError("down")))
    response = main.get_pokemon_set_route_directory()
    body = json.loads(response.body)
    assert response.status_code == 503
    assert body["retryable"] is True
