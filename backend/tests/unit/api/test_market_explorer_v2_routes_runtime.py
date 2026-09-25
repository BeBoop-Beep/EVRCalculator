"""Runtime (TestClient) tests for the V2 Explorer routes.

Requires the project's declared environment (backend/requirements.txt). Skipped
where FastAPI is not installed.
"""
from types import SimpleNamespace

import pytest

pytest.importorskip("fastapi")
pytest.importorskip("httpx")
from fastapi import HTTPException  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from backend.api import main  # noqa: E402
from backend.db.services import market_explorer_surface_v2 as v2  # noqa: E402
from backend.db.services import market_explorer_prepared_directory as v1  # noqa: E402

GEN = "11111111-1111-1111-1111-111111111111"
OTHER = "22222222-2222-2222-2222-222222222222"


def drow(key, scope="set", asset="cards", **kw):
    base = dict(generation_id=GEN, market_key=key, asset=asset, scope_kind=scope, label=key, base_label=key,
                source_kind="k", set_id=None, era_id=None, market_scope=None, taxonomy_key=None,
                source_as_of="2026-09-24", current_tracked_value=1.0, current_index_value=100.0,
                history_available=True, history_start_date="2026-09-01", history_end_date="2026-09-24",
                history_point_count=3, constituent_count=2, composition_kind="composition",
                availability="available", unavailable_reason=None, definition_version="d", metadata={})
    base.update(kw)
    return base


class Resp:
    def __init__(self, data):
        self.data = data

    def execute(self):
        return self


class AliasQ:
    def __init__(self, rows):
        self.rows = rows

    def select(self, *_):
        return self

    def eq(self, k, v):
        self.rows = [r for r in self.rows if r.get(k) == v]
        return self

    def execute(self):
        return SimpleNamespace(data=self.rows)


class Fake:
    def __init__(self, directory=None, history=None, page=None, fail=None, search=None, options=None, aliases=None):
        self.directory, self.history, self.page = directory or [], history or [], page
        self.fail, self.search, self.options, self.aliases, self.calls = fail or {}, search, options, aliases or [], []

    def table(self, name):
        return AliasQ([dict(a, generation_id=GEN) for a in self.aliases])

    def rpc(self, name, args):
        self.calls.append(name)
        if name in self.fail:
            raise self.fail[name]
        data = {v2.DIRECTORY_RPC_V2: self.directory, v2.HISTORY_RPC_V2: self.history,
                v2.CONSTITUENTS_RPC_V2: self.page, v2.SEARCH_RPC_V1: self.search,
                v2.ASSET_OPTIONS_RPC_V2: self.options}.get(name)
        return Resp(data)


@pytest.fixture
def api(monkeypatch):
    v2._reset_v2_state_cache()
    monkeypatch.setattr(main, "_require_authenticated_user_id", lambda **kw: "user-1")
    monkeypatch.setattr(main, "_resolve_index_plan", lambda a, t: "premium")
    monkeypatch.setattr(main, "_enforce_paid_abuse", lambda *a, **k: None)
    # V1 must never be touched once V2 is active.
    monkeypatch.setattr(v1, "read_prepared_comparison_bundle", lambda *a, **k: pytest.fail("V1 used"))
    monkeypatch.setattr(v1, "read_prepared_constituents", lambda *a, **k: pytest.fail("V1 used"))
    monkeypatch.setattr(v1, "read_prepared_directory", lambda *a, **k: pytest.fail("V1 used"))

    def install(fake):
        monkeypatch.setattr(main, "service_read_client", fake)
        return TestClient(main.app, raise_server_exceptions=False)
    return install


def test_catalog_search_validation_and_structured_errors(api):
    client = api(Fake(search=[{"asset": "cards", "result_kind": "set", "label": "Fossil"}]))
    assert client.get("/market/explorer/catalog/search", params={"asset": "cards", "q": "g"}).status_code in (400, 422)
    assert client.get("/market/explorer/catalog/search", params={"asset": "cards", "q": "gengar", "limit": 51}).status_code in (400, 422)
    assert client.get("/market/explorer/catalog/search", params={"asset": "weapons", "q": "gengar"}).status_code == 400
    ok = client.get("/market/explorer/catalog/search", params={"asset": "cards", "q": "fossil", "limit": 5})
    assert ok.status_code == 200 and ok.json()["results"][0]["label"] == "Fossil"
    assert ok.headers["cache-control"] == "no-store"


def test_catalog_search_is_not_plan_gated_and_uses_abuse_control(monkeypatch, api):
    calls = []
    client = api(Fake(search=[]))
    monkeypatch.setattr(main, "_enforce_paid_abuse", lambda *a, **k: calls.append(k["route"]))
    monkeypatch.setattr(main, "_resolve_index_plan", lambda a, t: pytest.fail("search must not consult plan"))
    monkeypatch.setattr(main, "_require_authenticated_user_id", lambda **kw: pytest.fail("search must not require auth"))
    assert client.get("/market/explorer/catalog/search", params={"asset": "sealed", "q": "case"}).status_code == 200
    assert calls == ["/market/explorer/catalog/search"]


def test_catalog_search_failure_is_browser_safe_no_invented_results(api):
    client = api(Fake(fail={v2.SEARCH_RPC_V1: RuntimeError('PostgREST relation "x" does not exist secret')}))
    r = client.get("/market/explorer/catalog/search", params={"asset": "cards", "q": "gengar"})
    assert r.status_code == 503
    assert "secret" not in r.text and "PostgREST" not in r.text
    assert r.json()["code"] == "CATALOG_SEARCH_FAILED"


def test_asset_options_ok_invalid_and_failure(api):
    client = api(Fake(options={"asset": "sealed", "types": []}))
    assert client.get("/market/explorer/asset-options", params={"asset": "sealed"}).json() == {"asset": "sealed", "types": []}
    assert client.get("/market/explorer/asset-options", params={"asset": "nope"}).status_code == 400
    bad = api(Fake(fail={v2.ASSET_OPTIONS_RPC_V2: RuntimeError("boom internal")}))
    r = bad.get("/market/explorer/asset-options", params={"asset": "cards"})
    assert r.status_code == 503 and "boom" not in r.text


def test_comparison_v2_single_market_and_no_cross_market(api):
    fake = Fake(directory=[drow("set:a"), drow("set:b")],
                history=[{"generation_id": GEN, "market_key": "set:a", "market_date": f"2026-09-{20+i}", "index_value": 100 + i,
                          "tracked_value": 1, "constituent_count": 2, "chain_segment_id": 1} for i in range(3)])
    r = api(fake).post("/market/explorer/prepared-comparison", json={"marketKeys": ["set:a"]})
    assert r.status_code == 200
    body = r.json()
    assert [m["market_key"] for m in body["markets"]] == ["set:a"] and body["surface"]["version"] == "v2"
    assert all(h["market_key"] == "set:a" for h in body["history"])


def test_comparison_compare_requires_auth_and_plus(monkeypatch, api):
    client = api(Fake(directory=[drow("set:a"), drow("set:b")]))

    def deny(**kw):
        raise HTTPException(status_code=401, detail="auth")
    monkeypatch.setattr(main, "_require_authenticated_user_id", deny)
    r = client.post("/market/explorer/prepared-comparison", json={"marketKeys": ["set:a"], "contextMarketKeys": ["set:b"]})
    assert r.status_code == 401
    monkeypatch.setattr(main, "_require_authenticated_user_id", lambda **kw: "u")
    monkeypatch.setattr(main, "_resolve_index_plan", lambda a, t: "basic")
    r = client.post("/market/explorer/prepared-comparison", json={"marketKeys": ["set:a"], "contextMarketKeys": ["set:b"]})
    assert r.status_code == 403


def test_comparison_active_v2_failure_is_visible_503_no_v1(api):
    fake = Fake(directory=[drow("set:a")], fail={v2.HISTORY_RPC_V2: RuntimeError("history exploded")})
    r = api(fake).post("/market/explorer/prepared-comparison", json={"marketKeys": ["set:a"]})
    assert r.status_code == 503 and "exploded" not in r.text


def test_directory_active_v2_error_503_no_v1(api):
    r = api(Fake(fail={v2.DIRECTORY_RPC_V2: RuntimeError("down")})).get("/market/explorer/prepared-directory")
    assert r.status_code == 503


def test_constituents_v2_requires_plus_validates_and_maps_409(monkeypatch, api):
    page = {"marketKey": "set:a", "generationId": GEN, "availability": "available", "totalCount": 1, "rows": [{"name": "x"}]}
    client = api(Fake(directory=[drow("set:a")], page=page))
    params = {"marketKey": "set:a", "generationId": GEN, "limit": 100}
    assert client.get("/market/explorer/prepared-constituents", params={**params, "limit": 101}).status_code == 422
    assert client.get("/market/explorer/prepared-constituents", params=params).status_code == 200
    mismatch = client.get("/market/explorer/prepared-constituents", params={**params, "generationId": OTHER})
    assert mismatch.status_code == 409 and mismatch.json()["code"] == "GENERATION_MISMATCH"
    monkeypatch.setattr(main, "_resolve_index_plan", lambda a, t: "basic")
    assert client.get("/market/explorer/prepared-constituents", params=params).status_code == 403


def test_constituents_rpc_generation_mismatch_is_409_before_movement(monkeypatch, api):
    monkeypatch.setattr(main, "enrich_prepared_constituent_page", lambda *a, **k: pytest.fail("movement work before 409"))
    fake = Fake(directory=[drow("set:a")], fail={v2.CONSTITUENTS_RPC_V2: RuntimeError("GENERATION_MISMATCH")})
    r = api(fake).get("/market/explorer/prepared-constituents", params={"marketKey": "set:a", "generationId": GEN})
    assert r.status_code == 409


def test_constituents_active_v2_error_503_no_v1(api):
    fake = Fake(directory=[drow("set:a")], fail={v2.CONSTITUENTS_RPC_V2: RuntimeError("db exploded")})
    r = api(fake).get("/market/explorer/prepared-constituents", params={"marketKey": "set:a", "generationId": GEN})
    assert r.status_code == 503 and "exploded" not in r.text


def test_v2_card_page_gets_accepted_movement_and_sealed_never_calls_it(monkeypatch, api):
    seen = []
    import backend.db.services.market_explorer_constituent_movement as mv

    def fake_enrich(client, page):
        seen.append(page["as_of"])
        return {"items": [{**r, "changes": {"7D": 1.5}} for r in page["items"]], "movement_windows": {"7D": {}}}
    monkeypatch.setattr(mv, "enrich_card_constituent_page", fake_enrich)
    card = {"marketKey": "set:a", "generationId": GEN, "availability": "available", "totalCount": 1,
            "rows": [{"cardVariantId": "v1", "marketPrice": 2, "priceAsOf": "2026-09-24"}]}
    r = api(Fake(directory=[drow("set:a")], page=card)).get("/market/explorer/prepared-constituents", params={"marketKey": "set:a", "generationId": GEN})
    assert r.status_code == 200 and r.json()["movementAvailable"] is True and seen == ["2026-09-24"]
    assert r.json()["rows"][0]["changes"] == {"7D": 1.5}
    seen.clear()
    sealed = {"marketKey": "sealed-type:x", "generationId": GEN, "availability": "available", "totalCount": 1,
              "rows": [{"sealedProductId": "p", "marketPrice": 2, "priceAsOf": "2026-09-24"}]}
    r = api(Fake(directory=[drow("sealed-type:x", "type", "sealed")], page=sealed)).get(
        "/market/explorer/prepared-constituents", params={"marketKey": "sealed-type:x", "generationId": GEN})
    assert r.status_code == 200 and r.json()["movementAvailable"] is False and seen == []


def test_v2_absent_falls_back_to_v1_only_then(monkeypatch):
    v2._reset_v2_state_cache()
    monkeypatch.setattr(main, "_enforce_paid_abuse", lambda *a, **k: None)
    monkeypatch.setattr(v1, "read_prepared_directory", lambda c: [{"market_key": "legacy"}])
    for fake in (Fake(fail={v2.DIRECTORY_RPC_V2: RuntimeError("Could not find the function (PGRST202)")}), Fake(directory=[])):
        v2._reset_v2_state_cache()
        monkeypatch.setattr(main, "service_read_client", fake)
        r = TestClient(main.app).get("/market/explorer/prepared-directory")
        assert r.json() == {"markets": [{"market_key": "legacy"}]}


@pytest.mark.parametrize("label,key", [("Fossil", "set:fossil"), ("HeartGold & SoulSilver", "set:hgss"),
                                       ("Base Set 2", "set:base2"), ("Rare Ultra", "rarity:rareUltra"),
                                       ("Rare Secret", "rarity:rareSecret")])
def test_image_fields_survive_v2_rpc_to_api_payload(monkeypatch, api, label, key):
    import backend.db.services.market_explorer_constituent_movement as mv
    monkeypatch.setattr(mv, "enrich_card_constituent_page", lambda c, p: {"items": p["items"], "movement_windows": {}})
    rows = [{"cardVariantId": "v1", "name": f"{label} card", "marketPrice": 3, "priceAsOf": "2026-09-24",
             "imageUrl": "https://i/std.png", "imageSmallUrl": "https://i/s.png", "imageLargeUrl": "https://i/l.png"},
            {"cardVariantId": "v2", "name": "no art", "marketPrice": 1, "priceAsOf": "2026-09-24",
             "imageUrl": None, "imageSmallUrl": None, "imageLargeUrl": None}]
    page = {"marketKey": key, "generationId": GEN, "availability": "available", "totalCount": 2, "rows": rows}
    r = api(Fake(directory=[drow(key)], page=page)).get("/market/explorer/prepared-constituents", params={"marketKey": key, "generationId": GEN})
    out = r.json()["rows"]
    assert (out[0]["imageUrl"], out[0]["imageSmallUrl"], out[0]["imageLargeUrl"]) == ("https://i/std.png", "https://i/s.png", "https://i/l.png")
    assert out[1]["imageSmallUrl"] is None and out[1]["imageUrl"] is None
