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
                composition_kind="index", availability="available", unavailable_reason=None,
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


def test_directory_publishes_legacy_aliases_per_market():
    c = Client(directory=[drow("sealed-type:booster_box", "type", asset="sealed"), drow("set:a", "set")],
               aliases=[{"alias_key": "format:booster-box", "market_key": "sealed-type:booster_box"}])
    rows = {r["market_key"]: r for r in v2.read_directory_v2_first(c)}
    assert rows["sealed-type:booster_box"]["legacy_aliases"] == ["format:booster-box"]
    assert rows["set:a"]["legacy_aliases"] == []


# ---- constituent movement / as-of normalization ----
def test_price_as_of_normalized_only_when_every_row_agrees():
    base = {"marketKey": "set:a", "generationId": GEN, "availability": "available", "totalCount": 2}
    same = v2.normalize_constituent_page({**base, "rows": [{"priceAsOf": "2026-09-24"}, {"priceAsOf": "2026-09-24T00:00:00Z"}]}, after_rank=0, asset="cards")
    assert same["priceAsOf"] == "2026-09-24"
    mixed = v2.normalize_constituent_page({**base, "rows": [{"priceAsOf": "2026-09-24"}, {"priceAsOf": "2026-09-23"}]}, after_rank=0, asset="cards")
    assert mixed["priceAsOf"] is None
    partial = v2.normalize_constituent_page({**base, "rows": [{"priceAsOf": "2026-09-24"}, {}]}, after_rank=0, asset="cards")
    assert partial["priceAsOf"] is None
    junk = v2.normalize_constituent_page({**base, "rows": [{"priceAsOf": "not-a-date"}]}, after_rank=0, asset="cards")
    assert junk["priceAsOf"] is None
    page_level = v2.normalize_constituent_page({**base, "priceAsOf": "2026-09-22", "rows": [{"priceAsOf": "2026-09-24"}]}, after_rank=0, asset="cards")
    assert page_level["priceAsOf"] == "2026-09-22"


def test_v2_card_movement_enrichment_paths(monkeypatch):
    import backend.db.services.market_explorer_constituent_movement as mv
    calls = []

    def ok(client, page):
        calls.append(page["as_of"])
        return {"items": [dict(r, changes={"7D": 2.0}) for r in page["items"]], "movement_windows": {"7D": {"start": "x"}}}
    monkeypatch.setattr(mv, "enrich_card_constituent_page", ok)
    from backend.db.services.market_explorer_prepared_directory import enrich_prepared_constituent_page
    page = v2.normalize_constituent_page({"marketKey": "set:a", "generationId": GEN, "availability": "available", "totalCount": 1,
                                          "rows": [{"cardVariantId": "v", "priceAsOf": "2026-09-24"}]}, after_rank=0, asset="cards")
    out = enrich_prepared_constituent_page(object(), page)
    assert out["movementAvailable"] is True and calls == ["2026-09-24"] and out["rows"][0]["rank"] == 1

    def boom(client, page):
        raise RuntimeError("movement down")
    monkeypatch.setattr(mv, "enrich_card_constituent_page", boom)
    degraded = enrich_prepared_constituent_page(object(), page)
    assert degraded["availability"] == "available" and degraded["rows"] and degraded["movementAvailable"] is False

    calls.clear()
    monkeypatch.setattr(mv, "enrich_card_constituent_page", ok)
    sealed = dict(page, asset="sealed")
    assert enrich_prepared_constituent_page(object(), sealed)["movementAvailable"] is False and calls == []
    # no as-of -> never guessed; the accepted enrichment itself returns unenriched rows
    undated = dict(page, priceAsOf=None)
    enrich_prepared_constituent_page(object(), undated)
    assert calls in ([None], []), "no invented date: the accepted enrichment gets no date and declines"


# ---- alias audit ----
def test_alias_read_is_generation_scoped_and_canonical_wins():
    class Spy(Client):
        def table(self, name):
            self.filters = []
            outer = self
            q = super().table(name)
            orig = q.eq
            q.eq = lambda k, v: (outer.filters.append((k, v)), orig(k, v))[1]
            return q
    c = Spy(directory=[drow("set:a", "set"), drow("format:x", "type", asset="sealed")],
            aliases=[{"alias_key": "format:x", "market_key": "set:a"}, {"alias_key": "old", "market_key": "set:a"}],
            history=history("set:a", [1, 2]))
    aliases = v2.read_aliases(c, GEN)
    assert ("generation_id", GEN) in c.filters
    assert v2.resolve_requested_keys(["format:x", "old", "ghost"], {"set:a", "format:x"}, aliases) == {"format:x": "format:x", "old": "set:a"}
    assert v2.resolve_requested_keys(["ghost"], {"set:a"}, aliases) == {}


def test_constituents_and_comparison_converge_on_the_same_canonical_market():
    page = {"marketKey": "sealed-type:booster_box", "generationId": GEN, "availability": "available", "totalCount": 0, "rows": []}
    c = Client(directory=[drow("sealed-type:booster_box", "type", asset="sealed")], page=page,
               aliases=[{"alias_key": "format:booster-box", "market_key": "sealed-type:booster_box"}],
               history=history("sealed-type:booster_box", [1, 2]))
    d = v2.read_v2_directory(c)
    v2.read_v2_constituents(c, d, "format:booster-box", GEN)
    sent = [a for n, a in c.calls if n == v2.CONSTITUENTS_RPC_V2][0]
    assert sent["p_market_key"] == "sealed-type:booster_box"
    assert v2.read_comparison_v2_bundle_key(c, d, "format:booster-box") == "sealed-type:booster_box"
    # a page for another generation fails closed BEFORE the RPC or alias read
    c2 = Client(directory=[drow("set:a", "set")], page=page)
    out = v2.read_v2_constituents(c2, v2.read_v2_directory(c2), "set:a", OTHER)
    assert out["code"] == "GENERATION_MISMATCH" and not [n for n, _ in c2.calls if n == v2.CONSTITUENTS_RPC_V2]


def test_unknown_alias_is_missing_not_invented():
    c = Client(directory=[drow("set:a", "set")])
    assert v2.read_comparison_v2_first(c, ["nope"])["missingKeys"] == ["nope"]


def test_active_v2_search_and_options_errors_do_not_invent_legacy_results():
    with pytest.raises(v2.SurfaceV2Error):
        v2.search_catalog(Client(fail={v2.SEARCH_RPC_V1: RuntimeError("x")}), "cards", "gengar", 5)
    with pytest.raises(v2.SurfaceV2Error):
        v2.read_asset_options(Client(fail={v2.ASSET_OPTIONS_RPC_V2: RuntimeError("x")}), "sealed")


# ---- Raw: no after-the-fact reconstruction ----
def test_application_never_reconstructs_raw_or_freezes_outside_the_backfill():
    import pathlib
    root = pathlib.Path(__file__).resolve().parents[5] / "backend"
    users = [p for p in root.rglob("*.py") if "tests" not in p.parts
             and "replace_pokemon_market_set_value_constituents_v1" in p.read_text(encoding="utf-8", errors="ignore")]
    assert {p.name for p in users} == {"pokemon_set_value_constituent_freeze.py"}, users
    callers = [p.name for p in root.rglob("*.py") if "tests" not in p.parts
               and "freeze_set_value_constituents" in p.read_text(encoding="utf-8", errors="ignore")]
    assert sorted(set(callers)) == ["pokemon_market_historical_root_value.py", "pokemon_set_value_constituent_freeze.py"]
    adapter = (root / "db/services/market_explorer_surface_v2.py").read_text(encoding="utf-8")
    for forbidden in ("card_variants", "card_variant_prices", "latest", "raw_composition"):
        assert forbidden not in adapter.replace("latest_", ""), forbidden
