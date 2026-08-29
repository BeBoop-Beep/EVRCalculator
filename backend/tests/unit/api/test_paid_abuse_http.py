from fastapi.testclient import TestClient
import pytest

from backend.api import main


@pytest.fixture(autouse=True)
def _reset_limiter():
    main.paid_analytics_limiter.clear()
    main._market_explorer_query_cache.clear()
    yield
    main.paid_analytics_limiter.clear()
    main._market_explorer_query_cache.clear()


def _install_auth(monkeypatch):
    plans = {"plus": "plus", "premium": "premium", "premium-two": "premium"}
    monkeypatch.setattr(main, "decode_token", lambda token: (
        ({"id": f"user-{token}"}, None) if token in plans
        else (None, ({"message": "Not authenticated"}, 401))
    ))
    monkeypatch.setattr(main, "get_me", lambda token: (
        ({"user": {"id": f"user-{token}", "index_plan": plans[token]}}, 200)
        if token in plans else ({"message": "Not authenticated"}, 401)
    ))


def _auth(token):
    return {"authorization": f"Bearer {token}"}


def test_premium_sequential_pages_eventually_return_429_with_retry_after(monkeypatch):
    _install_auth(monkeypatch)
    monkeypatch.setattr(main, "query_chase_efficiency", lambda *args, **kwargs: {"rows": []})
    client = TestClient(main.app)
    responses = [client.get(
        f"/explore/card-chase-efficiency?page={page}&sort=rank&search=q{page}",
        headers=_auth("premium"),
    ) for page in range(1, 14)]
    assert all(response.status_code == 200 for response in responses[:12])
    assert responses[12].status_code == 429
    assert int(responses[12].headers["retry-after"]) > 0
    assert responses[12].json()["detail"]["code"] == "PAID_ANALYTICS_RATE_LIMITED"


def test_custom_query_variation_cannot_bypass_and_users_are_isolated(monkeypatch):
    _install_auth(monkeypatch)
    monkeypatch.setattr(main, "normalize_query_spec", lambda **kwargs: kwargs)
    monkeypatch.setattr(main, "query_fingerprint", lambda spec: str(spec))
    monkeypatch.setattr(main, "run_market_explorer_query", lambda *args, **kwargs: {"rows": []})
    client = TestClient(main.app)
    responses = [client.post(
        "/market/explorer/query", json={"asset": "cards", "setIds": [f"set-{i}"]},
        headers=_auth("premium"),
    ) for i in range(6)]
    assert all(response.status_code == 200 for response in responses[:5])
    assert responses[5].status_code == 429
    assert client.post("/market/explorer/query", json={"asset": "cards"},
                       headers=_auth("premium-two")).status_code == 200
    assert client.post("/market/explorer/query", json={"asset": "cards"},
                       headers=_auth("plus")).status_code == 403


def test_hard_pagination_and_topn_caps_are_enforced_before_readers(monkeypatch):
    _install_auth(monkeypatch)
    client = TestClient(main.app)
    assert client.get("/explore/card-chase-efficiency?page_size=101",
                      headers=_auth("premium")).status_code == 422
    assert client.get("/tcgs/pokemon/sets/set/cards/validation?max_cards=301",
                      headers=_auth("plus")).status_code == 422
    assert client.post("/market/explorer/query", json={"asset": "cards", "topN": 101},
                       headers=_auth("premium")).status_code == 422
