from __future__ import annotations

import json
import os
from copy import deepcopy
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

os.environ.setdefault("SUPABASE_URL", "https://example.supabase.co")
os.environ.setdefault("SUPABASE_SERVICE_ROLE_KEY", "test-service-role-key")
os.environ.setdefault("SUPABASE_ANON_KEY", "test-anon-key")

from backend.api import main


ROOT = Path(__file__).resolve().parents[4]
FIXTURES = ROOT / "docs" / "research" / "market_activity_v1" / "fixtures"
MANIFEST = json.loads((FIXTURES / "manifest.json").read_text(encoding="utf-8"))
CLIENT = TestClient(main.app, raise_server_exceptions=False)
AUTH = {"Authorization": "Bearer good"}


def _auth(monkeypatch, plan="plus"):
    monkeypatch.setattr(main, "decode_token", lambda token: ({"id": "user-1"}, None) if token == "good" else (None, ({"message": "Not authenticated"}, 401)))
    monkeypatch.setattr(main, "get_me", lambda token: ({"user": {"id": "user-1", "index_plan": plan}}, 200) if token == "good" else ({}, 401))


def _instrument_fixture():
    return json.loads((FIXTURES / "fma_fixture_01_fresh_complete.json").read_text(encoding="utf-8"))


def test_anonymous_and_basic_are_denied_before_activity_read(monkeypatch):
    fixture = _instrument_fixture()
    calls = []
    monkeypatch.setattr(main, "read_instrument_activity", lambda *_: calls.append(1))
    response = CLIENT.post("/market/explorer/activity/instrument", json=fixture["inputs"]["request"])
    assert response.status_code == 401
    _auth(monkeypatch, None)
    response = CLIENT.post("/market/explorer/activity/instrument", json=fixture["inputs"]["request"], headers=AUTH)
    assert response.status_code == 403
    assert calls == []


@pytest.mark.parametrize("plan", ["plus", "premium"])
def test_paid_prepared_reads_are_allowed_and_private(monkeypatch, plan):
    _auth(monkeypatch, plan)
    fixture = _instrument_fixture()
    monkeypatch.setattr(main, "read_instrument_activity", lambda _client, _request: deepcopy(fixture["expected"]))
    response = CLIENT.post("/market/explorer/activity/instrument", json=fixture["inputs"]["request"], headers=AUTH)
    assert response.status_code == 200
    assert response.headers["cache-control"] == "private, no-store"


def test_custom_requires_premium(monkeypatch):
    fixture = _instrument_fixture()
    fixture["inputs"]["request"]["marketKey"] = "custom:abc"
    _auth(monkeypatch, "plus")
    response = CLIENT.post("/market/explorer/activity/instrument", json=fixture["inputs"]["request"], headers=AUTH)
    assert response.status_code == 403
    _auth(monkeypatch, "premium")
    expected = deepcopy(fixture["expected"])
    expected["request"] = deepcopy(fixture["inputs"]["request"])
    monkeypatch.setattr(main, "read_instrument_activity", lambda *_: expected)
    response = CLIENT.post("/market/explorer/activity/instrument", json=fixture["inputs"]["request"], headers=AUTH)
    assert response.status_code == 200


def test_published_revision_requires_premium_regardless_of_market_key(monkeypatch):
    fixture = _instrument_fixture()
    request = deepcopy(fixture["inputs"]["request"])
    request["marketKey"] = "innocent-looking-market"
    request["rosterRef"] = {
        "kind": "QUERY_CACHE_PUBLISHED_REVISION", "queryFingerprint": "a" * 64,
        "revisionId": "44444444-4444-4444-8444-444444444444",
        "computedThrough": "2026-09-29",
    }
    activity_calls = []
    monkeypatch.setattr(main, "read_instrument_activity", lambda *_: activity_calls.append(1))
    _auth(monkeypatch, "plus")
    denied = CLIENT.post("/market/explorer/activity/instrument", json=request, headers=AUTH)
    assert denied.status_code == 403
    assert activity_calls == []

    _auth(monkeypatch, "premium")
    expected = deepcopy(fixture["expected"])
    expected["request"] = request
    monkeypatch.setattr(main, "read_instrument_activity", lambda *_: expected)
    allowed = CLIENT.post("/market/explorer/activity/instrument", json=request, headers=AUTH)
    assert allowed.status_code == 200


def test_invalid_extra_field_is_400_before_db(monkeypatch):
    _auth(monkeypatch)
    fixture = _instrument_fixture()
    body = {**fixture["inputs"]["request"], "plan": "premium"}
    calls = []
    monkeypatch.setattr(main, "read_instrument_activity", lambda *_: calls.append(1))
    response = CLIENT.post("/market/explorer/activity/instrument", json=body, headers=AUTH)
    assert response.status_code == 400
    assert response.json()["detail"]["code"] == "MARKET_ACTIVITY_REQUEST_INVALID"
    assert calls == []


def test_invalid_reader_response_is_bounded_500(monkeypatch):
    _auth(monkeypatch)
    fixture = _instrument_fixture()
    monkeypatch.setattr(main, "read_instrument_activity", lambda *_: {"rawProviderPayload": {"seller": "secret"}})
    response = CLIENT.post("/market/explorer/activity/instrument", json=fixture["inputs"]["request"], headers=AUTH)
    assert response.status_code == 500
    assert response.json()["code"] == "MARKET_ACTIVITY_CONTRACT_VIOLATION"
    assert "secret" not in response.text


@pytest.mark.parametrize("entry", MANIFEST["fixtures"], ids=lambda item: item["fixtureId"])
def test_all_accepted_fixtures_cross_route_serializer(monkeypatch, entry):
    _auth(monkeypatch, "premium")
    fixture = json.loads((FIXTURES / entry["file"]).read_text(encoding="utf-8"))
    route_and_reader = {
        "instrument_detail": ("/market/explorer/activity/instrument", "read_instrument_activity"),
        "group_activity": ("/market/explorer/activity", "read_group_activity"),
        "constituent_page": ("/market/explorer/activity/constituents", "read_constituent_activity_page"),
    }
    route, reader = route_and_reader[entry["assembler"]]
    monkeypatch.setattr(main, reader, lambda _client, _request: deepcopy(fixture["expected"]))
    response = CLIENT.post(route, json=fixture["inputs"]["request"], headers=AUTH)
    assert response.status_code == 200, response.text
    assert response.json() == fixture["expected"]


def _capability_body(count=1, custom=False):
    markets = []
    for index in range(count):
        market = f"custom:{index}" if custom else f"set:{index}"
        roster = ({"kind": "QUERY_CACHE_PUBLISHED_REVISION", "queryFingerprint": f"fp-{index}",
                   "revisionId": "11111111-1111-4111-8111-111111111111", "computedThrough": "2026-09-29"}
                  if custom else {"kind": "SURFACE_V2_GENERATION",
                                  "generationId": "11111111-1111-4111-8111-111111111111", "marketKey": market})
        markets.append({"focusKey": f"focus-{index}", "marketKey": market, "rosterRef": roster})
    return {"markets": markets, "windowDays": 30}


@pytest.mark.parametrize("field", ["focusKey", "marketKey"])
def test_capability_duplicate_identity_is_invalid(monkeypatch, field):
    _auth(monkeypatch, "premium")
    body = _capability_body(2)
    body["markets"][1][field] = body["markets"][0][field]
    response = CLIENT.post("/market/explorer/activity/capabilities", json=body, headers=AUTH)
    assert response.status_code == 400


def test_capability_plan_bound_and_custom_hierarchy(monkeypatch):
    _auth(monkeypatch, "plus")
    response = CLIENT.post("/market/explorer/activity/capabilities", json=_capability_body(4), headers=AUTH)
    assert response.status_code == 400
    response = CLIENT.post("/market/explorer/activity/capabilities", json=_capability_body(1, custom=True), headers=AUTH)
    assert response.status_code == 403
