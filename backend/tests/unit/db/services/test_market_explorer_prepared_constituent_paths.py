"""Prepared constituent read path: per-market-type pages, generation safety,
movement honesty and the API contract. In-test fake clients only; no network."""
from pathlib import Path

import pytest

from backend.db.services import market_explorer_prepared_directory as service
from backend.db.services.market_explorer_prepared_directory import (
    enrich_prepared_constituent_page, read_prepared_comparison_bundle, read_prepared_constituents,
)

ROOT = Path(__file__).resolve().parents[5]
SOURCE = (ROOT / "backend" / "api" / "main.py").read_text(encoding="utf-8")


class _Result:
    def __init__(self, data):
        self.data = data


class PageClient:
    """Answers the constituents RPC from a canned per-market table."""

    def __init__(self, pages):
        self.pages = pages
        self.calls = []

    def rpc(self, name, params):
        self.calls.append((name, params))
        page = self.pages[params["p_market_key"]]
        if page.get("availability") == "available" and page.get("generationId") != params["p_generation_id"]:
            page = {"marketKey": params["p_market_key"], "generationId": page["generationId"],
                    "availability": "unavailable", "code": "GENERATION_MISMATCH"}
        return type("Q", (), {"execute": lambda self_: _Result(page)})()


def _cards_page(market_key, total, source_kind, generation="gen-1", count=2):
    rows = [{"rank": i + 1, "cardVariantId": "v%d" % i, "cardName": "Card %d" % i, "marketPrice": 10 - i}
            for i in range(count)]
    return {"marketKey": market_key, "generationId": generation, "sourceKind": source_kind,
            "asset": "cards", "priceAsOf": "2026-09-19", "totalCount": total, "returnedCount": count,
            "hasMore": total > count, "nextCursor": count if total > count else None,
            "availability": "available", "rows": rows}


MARKETS = {}
# Sets (Base / Jungle / Fossil / Team Rocket / a modern set): canonical Set roster reader.
for _key in ("set:base", "set:jungle", "set:fossil", "set:team-rocket", "set:151"):
    MARKETS[_key] = _cards_page(_key, 102, "public_set_snapshot")
# Eras (EX, a WotC era, a modern era) and Quick markets and prepared rarity: maintained query cache.
for _key in ("era:ex", "era:wotc", "era:sv", "curated:premium", "curated:global-top10",
             "rarity:rare-ultra", "rarity:sir"):
    MARKETS[_key] = _cards_page(_key, 900, "maintained_query_cache")
# Sealed formats (Packs deliberately combines loose + sleeved packs upstream).
for _key in ("format:booster-box", "format:packs", "format:etb"):
    MARKETS[_key] = dict(_cards_page(_key, 40, "prepared_sealed_snapshots"), asset="sealed")


@pytest.mark.parametrize("key", sorted(MARKETS))
def test_every_market_type_reads_a_bounded_first_page_pinned_to_its_generation(key):
    client = PageClient(MARKETS)
    page = read_prepared_constituents(client, key, "gen-1", 0, 100)
    assert page["availability"] == "available"
    assert page["marketKey"] == key and page["generationId"] == "gen-1"
    assert len(page["rows"]) <= 100
    ((name, params),) = client.calls
    assert name == "get_pokemon_market_explorer_prepared_constituents_v3"
    assert params == {"p_market_key": key, "p_generation_id": "gen-1", "p_after_rank": 0, "p_limit": 100}


def test_pagination_cursor_is_forwarded_and_exhaustion_is_explicit():
    last = dict(_cards_page("set:base", 2, "public_set_snapshot"), nextCursor=None, hasMore=False)
    client = PageClient({"set:base": last})
    page = read_prepared_constituents(client, "set:base", "gen-1", 100, 50)
    assert client.calls[0][1]["p_after_rank"] == 100 and client.calls[0][1]["p_limit"] == 50
    assert page["nextCursor"] is None and page["hasMore"] is False


def test_generation_mismatch_is_structured_and_returns_no_rows():
    page = read_prepared_constituents(PageClient(MARKETS), "set:jungle", "gen-OLD", 0, 100)
    assert page["code"] == "GENERATION_MISMATCH"
    assert page["generationId"] == "gen-1"
    assert "rows" not in page


def test_no_roster_states_pass_through_untouched():
    for state in ("unavailable", "notApplicable", "empty"):
        client = PageClient({"x": {"availability": state, "generationId": "g", "availabilityReason": "r"}})
        assert read_prepared_constituents(client, "x", "g", 0, 10)["availability"] == state


@pytest.mark.parametrize("market,generation,cursor,limit", [
    ("", "g", 0, 10), ("set:x", "", 0, 10), ("set:x", "g", -1, 10), ("set:x", "g", 0, 0), ("set:x", "g", 0, 101),
])
def test_invalid_requests_never_reach_the_database(market, generation, cursor, limit):
    client = PageClient({})
    with pytest.raises(ValueError):
        read_prepared_constituents(client, market, generation, cursor, limit)
    assert client.calls == []


def test_card_page_gets_movement_from_the_accepted_v2_authority(monkeypatch):
    from backend.db.services import market_explorer_constituent_movement as movement
    seen = {}

    def fake(client, page):
        seen["as_of"] = page["as_of"]
        return {"items": [dict(row, changes={"7D": {"percent": 1.5}}) for row in page["items"]],
                "movement_windows": {"7D": {"startDate": "2026-09-12"}}}

    monkeypatch.setattr(movement, "enrich_card_constituent_page", fake)
    result = enrich_prepared_constituent_page(object(), _cards_page("set:base", 2, "public_set_snapshot"))
    assert seen["as_of"] == "2026-09-19"
    assert result["movementAvailable"] is True
    assert result["rows"][0]["changes"]["7D"]["percent"] == 1.5


def test_sealed_movement_is_honestly_unavailable_not_fabricated():
    page = dict(_cards_page("format:packs", 40, "prepared_sealed_snapshots"), asset="sealed")
    result = enrich_prepared_constituent_page(object(), page)
    assert result["movementAvailable"] is False
    assert all("changes" not in row for row in result["rows"])


def test_movement_failure_never_fails_the_roster(monkeypatch):
    from backend.db.services import market_explorer_constituent_movement as movement

    def boom(client, page):
        raise RuntimeError("db down")

    monkeypatch.setattr(movement, "enrich_card_constituent_page", boom)
    result = enrich_prepared_constituent_page(object(), _cards_page("era:ex", 900, "maintained_query_cache"))
    assert result["movementAvailable"] is False and len(result["rows"]) == 2


def test_unavailable_pages_are_not_enriched():
    page = {"availability": "unavailable", "rows": [{"cardVariantId": "v"}], "asset": "cards"}
    assert enrich_prepared_constituent_page(object(), page)["movementAvailable"] is False


def test_comparison_bundle_reports_keys_with_no_prepared_row():
    class C:
        def rpc(self, name, params):
            rows = ([{"market_key": "set:base", "comparison_as_of": "2026-09-19", "metadata": {}}]
                    if name == service.COMPARISON_RPC else [])
            return type("Q", (), {"execute": lambda s: _Result(rows)})()

    bundle = read_prepared_comparison_bundle(C(), ["set:base", "set:typo"])
    assert bundle["missingKeys"] == ["set:typo"]


def test_directory_row_is_the_prepared_identity_the_constituent_pager_needs():
    migration = (ROOT / "backend" / "db" / "migrations"
                 / "20260911200732_market_explorer_phase5_prepared_directory_serving_contract.sql"
                 ).read_text(encoding="utf-8")
    for column in ("generation_id", "prepared_series_key", "comparison_as_of", "source_kind", "asset", "market_type"):
        assert column in migration


def _function_source(name):
    start = SOURCE.index("def %s(" % name)
    rest = SOURCE[start:]
    index = rest.find("\n@app.", 1)
    return rest[:index] if index != -1 else rest


def test_endpoint_authenticates_then_requires_plus_before_reading():
    source = _function_source("get_market_explorer_prepared_constituents")
    assert (source.index("_require_authenticated_user_id") < source.index("has_index_plus_access")
            < source.index("read_constituents_v2_first("))


def test_endpoint_maps_generation_mismatch_to_409_and_bounds_the_page():
    source = _function_source("get_market_explorer_prepared_constituents")
    assert "GENERATION_MISMATCH" in source and "status_code=409" in source
    assert "le=100" in source and "PREPARED_CONSTITUENTS_TIMEOUT" in source


def test_context_keys_count_toward_the_compare_entitlement_but_are_never_read():
    source = _function_source("post_market_explorer_prepared_comparison")
    assert "contextMarketKeys" in source
    assert "read_comparison_v2_first(\n            service_read_client, keys" in source
    assert "PREPARED_COMPARISON_TIMEOUT" in source
