"""Regression tests for the Profile/Portfolio public-exposure hard-stop.

Profile and Portfolio are not production-ready. `/collection/items/public/{username}`,
`/public/profiles/{username}`, and `/profile/public/{username}` must all short-circuit
to a disabled response BEFORE calling into any DB/service loader — this proves the
short-circuit happens by monkeypatching the underlying loaders to raise, and asserting
the request still returns the disabled response rather than propagating the failure.

`/profile/me` is a separate, unrelated identity/account-settings endpoint and must
keep working exactly as before.
"""

from fastapi.testclient import TestClient

from backend.api import main

client = TestClient(main.app)


def _fail(*args, **kwargs):
    raise AssertionError("underlying Profile/Portfolio loader must not be called while the feature is disabled")


def test_public_collection_items_short_circuits_before_service_call(monkeypatch):
    monkeypatch.setattr(main, "get_public_collection_data_by_username", _fail)

    response = client.get("/collection/items/public/someuser")

    assert response.status_code == 503
    assert response.json() == {
        "message": "This feature is temporarily unavailable.",
        "code": "FEATURE_TEMPORARILY_DISABLED",
    }


def test_public_profile_page_short_circuits_before_service_call(monkeypatch):
    monkeypatch.setattr(main, "get_public_profile_page_payload", _fail)

    response = client.get("/public/profiles/someuser")

    assert response.status_code == 503
    assert response.json() == {
        "message": "This feature is temporarily unavailable.",
        "code": "FEATURE_TEMPORARILY_DISABLED",
    }


def test_profile_public_short_circuits_before_service_call(monkeypatch):
    monkeypatch.setattr(main, "get_public_profile", _fail)

    response = client.get("/profile/public/someuser")

    assert response.status_code == 503
    assert response.json() == {
        "message": "This feature is temporarily unavailable.",
        "code": "FEATURE_TEMPORARILY_DISABLED",
    }


def test_public_endpoints_disabled_regardless_of_query_params_or_auth():
    response = client.get(
        "/collection/items/public/someuser",
        params={"include_collection_items": "1"},
        headers={"authorization": "Bearer whatever"},
    )
    assert response.status_code == 503

    response = client.get(
        "/public/profiles/someuser",
        params={"include_collection_items": "1"},
    )
    assert response.status_code == 503


def test_profile_me_get_is_unaffected_by_the_public_profile_disable(monkeypatch):
    monkeypatch.setattr(main, "get_current_profile", lambda token: ({"profile": {"id": "user-1"}}, 200))

    response = client.get("/profile/me", headers={"authorization": "Bearer good"})

    assert response.status_code == 200
    assert response.json() == {"profile": {"id": "user-1"}}


def test_profile_me_put_is_unaffected_by_the_public_profile_disable(monkeypatch):
    monkeypatch.setattr(main, "update_profile", lambda token, payload: ({"profile": {"id": "user-1", **payload}}, 200))

    response = client.put(
        "/profile/me",
        json={"display_name": "New Name"},
        headers={"authorization": "Bearer good"},
    )

    assert response.status_code == 200
    assert response.json() == {"profile": {"id": "user-1", "display_name": "New Name"}}
