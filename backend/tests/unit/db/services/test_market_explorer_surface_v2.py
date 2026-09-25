from types import SimpleNamespace

import pytest

from backend.db.services import market_explorer_surface_v2 as v2

GEN = "11111111-1111-1111-1111-111111111111"
OTHER = "22222222-2222-2222-2222-222222222222"


def drow(key, scope, asset="cards", **kw):
    base = dict(generation_id=GEN, market_key=key, asset=asset, scope_kind=scope, label=key,
                base_label=key, source_kind="k", set_id=None, era_id=None, market_scope=None,
                taxonomy_key=None, source_as_of="2026-09-24", current_tracked_value=100.5,
                current_index_value=101.2, history_available=True, history_start_date="2026-01-01",
                history_end_date="2026-09-24", history_point_count=5, constituent_count=3,
                composition_kind="index_only", availability="available", unavailable_reason=None,
                definition_version="d1", metadata={})
    base.update(kw)
    return base


class Resp:
    def __init__(self, data):
        self.data = data

    def execute(self):
        return self


class Q:
    def __init__(self, rows):
        self.rows = rows

    def select(self, *_):
        return self

    def eq(self, k, v):
        self.rows = [r for r in self.rows if r.get(k) == v]
        return self

    def execute(self):
        return SimpleNamespace(data=self.rows)


class Client:
    def __init__(self, directory=None, history=None, aliases=None, fail=None, page=None):
        self.directory, self.history = directory or [], history or []
        self.aliases, self.fail, self.page, self.calls = aliases or [], fail or {}, page, []

    def table(self, name):
        assert name == v2.ALIASES_TABLE_V2
        return Q([dict(a, generation_id=GEN) for a in self.aliases])

    def rpc(self, name, args):
        self.calls.append((name, args))
        if name in self.fail:
            raise self.fail[name]
        data = {v2.DIRECTORY_RPC_V2: self.directory, v2.HISTORY_RPC_V2: self.history,
                v2.CONSTITUENTS_RPC_V2: self.page}.get(name, [])
        return Resp(data)


@pytest.fixture(autouse=True)
def _reset():
    v2._reset_v2_state_cache()


def history(key, values):
    return [dict(generation_id=GEN, market_key=key, market_date=f"2026-09-{20 + i:02}", index_value=v,
                 tracked_value=v * 10, constituent_count=3, chain_segment_id=1)
            for i, v in enumerate(values)]


def test_directory_normalizes_and_maps_fields():
    c = Client(directory=[drow("raw", "parent", composition_kind="index_and_composition"),
                          drow("set:a", "set", set_id="s", era_id="e", market_scope="first_edition"),
                          drow("sealed-set:s", "set", asset="sealed", availability="unavailable",
                               unavailable_reason="x")])
    rows = {r["market_key"]: r for r in v2.read_v2_directory(c)}
    assert rows["raw"]["market_type"] == "parent"
    assert rows["raw"]["composition_kind"] == "index_and_composition"
    s = rows["set:a"]
    assert (s["set_id"], s["parent_era_id"], s["comparison_value"], s["comparison_index_value"]) == ("s", "e", 100.5, 101.2)
    assert s["generation_id"] == GEN and s["metadata"]["marketScope"] == "first_edition"
    assert rows["sealed-set:s"]["available"] is False and rows["sealed-set:s"]["unavailable_reason"] == "x"


def test_v2_absent_when_empty_or_rpc_missing_falls_back_to_v1(monkeypatch):
    assert v2.read_v2_directory(Client(directory=[])) is None
    v2._reset_v2_state_cache()
    err = RuntimeError("Could not find the function public.get_x (PGRST202)")
    assert v2.read_v2_directory(Client(fail={v2.DIRECTORY_RPC_V2: err})) is None
    from backend.db.services import market_explorer_prepared_directory as v1
    monkeypatch.setattr(v1, "read_prepared_directory", lambda c: [{"market_key": "legacy"}])
    v2._reset_v2_state_cache()
    assert v2.read_directory_v2_first(Client(directory=[])) == [{"market_key": "legacy"}]


def test_active_v2_error_is_visible_never_v1(monkeypatch):
    from backend.db.services import market_explorer_prepared_directory as v1
    monkeypatch.setattr(v1, "read_prepared_directory", lambda c: pytest.fail("V1 fallback used"))
    monkeypatch.setattr(v1, "read_prepared_comparison_bundle", lambda *a: pytest.fail("V1 fallback used"))
    with pytest.raises(v2.SurfaceV2Error):
        v2.read_directory_v2_first(Client(fail={v2.DIRECTORY_RPC_V2: RuntimeError("boom")}))
    c = Client(directory=[drow("set:a", "set")], fail={v2.HISTORY_RPC_V2: RuntimeError("history down")})
    with pytest.raises(v2.SurfaceV2Error):
        v2.read_comparison_v2_first(c, ["set:a"])


def test_mixed_generation_directory_rejected():
    with pytest.raises(v2.GenerationMismatch):
        v2.read_v2_directory(Client(directory=[drow("a", "set"), drow("b", "set", generation_id=OTHER)]))


def test_bundle_history_movements_and_single_market_scope():
    c = Client(directory=[drow("set:a", "set"), drow("set:b", "set")],
               history=history("set:a", [100, 101, 102]))
    bundle = v2.read_comparison_v2_first(c, ["set:a"])
    assert [m["market_key"] for m in bundle["markets"]] == ["set:a"]
    hist_call = [x for x in c.calls if x[0] == v2.HISTORY_RPC_V2][0][1]
    assert hist_call["p_market_keys"] == ["set:a"]
    assert bundle["history"][0]["index_value"] == 100 and bundle["history"][0]["chain_segment_id"] == 1
    assert "1D" in bundle["markets"][0]["window_movements"]
    assert bundle["missingKeys"] == [] and bundle["surface"]["generationId"] == GEN


def test_history_generation_mismatch_fails_closed():
    h = history("set:a", [1, 2])
    h[0]["generation_id"] = OTHER
    with pytest.raises(v2.GenerationMismatch):
        v2.read_comparison_v2_first(Client(directory=[drow("set:a", "set")], history=h), ["set:a"])


def test_legacy_alias_resolves_server_side():
    c = Client(directory=[drow("sealed-type:booster_box", "type", asset="sealed")],
               history=history("sealed-type:booster_box", [5, 6]),
               aliases=[{"alias_key": "format:booster-box", "market_key": "sealed-type:booster_box"}])
    bundle = v2.read_comparison_v2_first(c, ["format:booster-box", "nope"])
    assert bundle["markets"][0]["market_key"] == "sealed-type:booster_box"
    assert bundle["markets"][0]["requested_market_key"] == "format:booster-box"
    assert bundle["history"][0]["requested_market_key"] == "format:booster-box"
    assert bundle["missingKeys"] == ["nope"]


def test_constituent_page_normalization_and_cursor():
    page = {"marketKey": "raw", "generationId": GEN, "availability": "available", "reason": None,
            "totalCount": 3, "afterRank": 0, "limit": 2, "rows": [{"name": "a", "imageUrl": "u"}, {"name": "b"}]}
    c = Client(directory=[drow("raw", "parent", composition_kind="index_and_composition")], page=page)
    out = v2.read_v2_constituents(c, v2.read_v2_directory(c), "raw", GEN, 0, 2)
    assert [r["rank"] for r in out["rows"]] == [1, 2] and out["nextCursor"] == 2
    assert out["totalCount"] == 3 and out["asset"] == "cards" and out["rows"][0]["imageUrl"] == "u"
    page["rows"] = [{"rank": 3}]
    out = v2.read_v2_constituents(c, None, "raw", GEN, 2, 2)
    assert out["nextCursor"] is None


def test_constituent_unavailable_composition_is_returned_not_thrown():
    page = {"marketKey": "set:a", "generationId": GEN, "availability": "unavailable",
            "reason": "COMPOSITION_NOT_AVAILABLE", "totalCount": 0, "rows": []}
    out = v2.read_v2_constituents(Client(page=page), None, "set:a", GEN)
    assert out["availability"] == "unavailable" and out["availabilityReason"] == "COMPOSITION_NOT_AVAILABLE"


def test_constituent_generation_mismatch_and_limit_validation():
    c = Client(fail={v2.CONSTITUENTS_RPC_V2: RuntimeError("GENERATION_MISMATCH")})
    assert v2.read_v2_constituents(c, None, "raw", GEN)["code"] == "GENERATION_MISMATCH"
    for bad in (0, 101):
        with pytest.raises(ValueError):
            v2.read_v2_constituents(c, None, "raw", GEN, 0, bad)
    with pytest.raises(ValueError):
        v2.read_v2_constituents(c, None, "raw", GEN, -1, 10)


def test_total_sealed_composition_row_is_inspectable_metadata():
    row = v2.normalize_directory_row(drow("sealedMarket", "parent", asset="sealed",
                                          composition_kind="composition", constituent_count=40))
    assert (row["composition_kind"], row["constituent_count"], row["availability"]) == ("composition", 40, "available")


def test_search_validation_and_passthrough():
    with pytest.raises(ValueError):
        v2.validate_search_request("cards", "g", 10)
    with pytest.raises(ValueError):
        v2.validate_search_request("cards", "gengar", 51)
    with pytest.raises(ValueError):
        v2.validate_search_request("weapons", "gengar", 10)
    assert v2.validate_search_request("Cards", "  Rare   Holo GX ", 20) == ("cards", "Rare Holo GX", 20)

    class C(Client):
        def rpc(self, name, args):
            self.calls.append((name, args))
            return Resp([{"asset": "graded", "result_kind": "graded_instrument",
                          "availability": "INSUFFICIENT_AUTHORITY"}])

    c = C()
    assert v2.search_catalog(c, "graded", "psa", 5)[0]["availability"] == "INSUFFICIENT_AUTHORITY"
    assert c.calls[0][1] == {"p_asset": "graded", "p_query": "psa", "p_limit": 5}


def test_asset_options_missing_authority_is_explicit():
    err = RuntimeError("Could not find the function (PGRST202)")
    with pytest.raises(v2.SurfaceV2Error) as e:
        v2.read_asset_options(Client(fail={v2.ASSET_OPTIONS_RPC_V2: err}), "cards")
    assert e.value.code == "ASSET_OPTIONS_UNAVAILABLE"
