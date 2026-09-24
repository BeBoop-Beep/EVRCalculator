from backend.scripts.build_pokemon_explore_set_value_snapshot import _expand_market_scope_rows
from backend.db.services.pokemon_explore_set_value_service import build_global_set_value_row


def _root(name="Jungle", profile_ready=True):
    return {
        "id": "11111111-1111-1111-1111-111111111111",
        "canonical_key": "jungle",
        "name": name,
        "era": "Base / WotC",
        "market_scope": "standard",
        "market_publication_ready": profile_ready,
    }


def _history(start, end):
    return [
        {"snapshot_date": "2026-09-21", "set_value": float(start)},
        {"snapshot_date": "2026-09-22", "set_value": float(end)},
    ]


def test_edition_split_root_expands_to_two_explicit_markets_and_no_generic_row():
    root = _root()
    rows = _expand_market_scope_rows(
        [root],
        market_date="2026-09-22",
        profiles={root["id"]: "edition_split"},
    )
    assert [(row["market_scope"], row["name"]) for row in rows] == [
        ("first_edition", "Jungle — 1st Edition"),
        ("unlimited", "Jungle — Unlimited"),
    ]
    assert [row["market_key"] for row in rows] == [
        f"set:{root['id']}:first_edition",
        f"set:{root['id']}:unlimited",
    ]
    assert all(row["market_key"] != f"set:{root['id']}" for row in rows)


def test_base_three_printings_expands_to_three_explicit_markets():
    root = _root(name="Base")
    rows = _expand_market_scope_rows(
        [root],
        market_date="2026-09-22",
        profiles={root["id"]: "base_three_printings"},
    )
    assert [row["market_scope"] for row in rows] == [
        "first_edition", "shadowless", "unlimited",
    ]
    assert [row["name"] for row in rows] == [
        "Base — 1st Edition", "Base — Shadowless", "Base — Unlimited",
    ]


def test_modern_root_keeps_single_standard_market_identity():
    root = _root(name="Obsidian Flames")
    rows = _expand_market_scope_rows(
        [root],
        market_date="2026-09-22",
        profiles={},
    )
    assert len(rows) == 1
    assert rows[0]["market_scope"] == "standard"
    assert rows[0]["market_key"] == f"set:{root['id']}"
    assert rows[0]["name"] == "Obsidian Flames"


def test_market_snapshot_publishes_scoped_rows_as_independent_markets():
    root = _root()
    scoped = _expand_market_scope_rows(
        [root],
        market_date="2026-09-22",
        profiles={root["id"]: "edition_split"},
    )
    histories = {
        f"set:{root['id']}:first_edition": _history(100, 110),
        f"set:{root['id']}:unlimited": _history(50, 60),
    }
    result = build_global_set_value_row(
        scoped, [], histories, target_market_date="2026-09-22",
    )
    markets = result["payload_json"]["sets"]
    assert result["set_count"] == 2
    assert result["_diagnostics"]["eligibleSetCount"] == 2
    assert result["_diagnostics"]["eligibleRootSetCount"] == 1
    assert result["_diagnostics"]["publishedSetCount"] == 2
    assert result["_diagnostics"]["publishedRootSetCount"] == 1
    assert result["payload_json"]["meta"]["source"] == "canonical_scoped_root_set_market_history_v1"

    by_scope = {row["marketScope"]: row for row in markets}
    assert by_scope["first_edition"]["marketKey"].endswith(":first_edition")
    assert by_scope["unlimited"]["marketKey"].endswith(":unlimited")
    assert by_scope["first_edition"]["currentSetValue"] == 110.0
    assert by_scope["unlimited"]["currentSetValue"] == 60.0
    assert round(by_scope["first_edition"]["marketIndex"]["currentValue"], 6) == 110.0
    assert round(by_scope["unlimited"]["marketIndex"]["currentValue"], 6) == 120.0
    assert {row["name"] for row in markets} == {
        "Jungle — 1st Edition", "Jungle — Unlimited",
    }


def test_uncertified_scope_remains_discoverable_but_unavailable():
    root = _root(name="Base")
    scoped = _expand_market_scope_rows(
        [root],
        market_date="2026-09-22",
        profiles={root["id"]: "base_three_printings"},
    )
    result = build_global_set_value_row(
        scoped, [], {}, target_market_date="2026-09-22",
    )
    assert result["set_count"] == 3
    assert all(row["valueStatus"] == "unavailable" for row in result["payload_json"]["sets"])
    assert all(row["currentSetValue"] is None for row in result["payload_json"]["sets"])
