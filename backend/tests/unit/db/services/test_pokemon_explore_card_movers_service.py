import pytest

from backend.db.services.pokemon_explore_card_movers_service import (
    ExploreCardMoversUnavailable,
    build_global_card_movers_row,
    read_explore_card_movers_snapshot,
)
from backend.db.services.pokemon_card_market_delta_contract import WINDOW_CONVENTION


def movement(card_id, percent, amount, **extra):
    return {"canonicalCardId": card_id, "cardVariantId": "v", "conditionId": "nm",
            "name": card_id, "changePercent": percent, "changeAmount": amount, **extra}


def snapshot(set_id, rows, date="2026-08-01", version="pokemon_card_movement_v1"):
    return {"set_id": set_id, "latest_market_date": date, "updated_at": f"{date}T12:00:00Z",
            "payload_json": {"marketMoversByWindow": {"7D": {"all": rows}}, "meta": {
                "movementContractVersion": version, "windowConvention": WINDOW_CONVENTION,
                "movementGenerationId": f"generation-{set_id}"}}}


def test_aggregates_deduplicates_sorts_and_adds_cross_set_identity():
    sets = [{"id": "a", "name": "Alpha", "canonical_key": "alpha"},
            {"id": "b", "name": "Beta", "canonical_key": "beta"}]
    row = build_global_card_movers_row(
        sets, [snapshot("a", [movement("positive", 10, 50), movement("duplicate", -20, -1)]),
               snapshot("b", [movement("negative", -30, -2), movement("duplicate", -20, -1)])],
        target_market_date="2026-08-01",
    )
    cards = row["payload_json"]["marketMovers"]["all"]
    assert [card["canonicalCardId"] for card in cards] == ["negative", "duplicate", "positive"]
    assert cards[0]["setName"] == "Beta"
    assert "setSlug" not in cards[0]
    assert len([card for card in cards if card["canonicalCardId"] == "duplicate"]) == 1
    assert row["payload_json"]["meta"]["coverage"]["candidateCardCount"] == 4


def test_excludes_non_public_sets_and_applies_limit_after_global_sort():
    sets = [{"id": "a", "name": "Alpha"}, {"id": "hidden", "name": "Sword and Shield",
             "era": "Sword and Shield"}]
    rows = [movement(f"c{i:02}", i, i) for i in range(40)]
    row = build_global_card_movers_row(sets, [snapshot("a", rows)], target_market_date="2026-08-01")
    assert row["eligible_set_count"] == 1
    assert row["card_count"] == 30
    assert row["payload_json"]["marketMovers"]["all"][0]["canonicalCardId"] == "c39"


@pytest.mark.parametrize("sources", [[], [snapshot("a", [], date="2026-07-31")],
                                        [snapshot("a", [], version="wrong")]])
def test_incoherent_source_blocks_publication(sources):
    with pytest.raises(ExploreCardMoversUnavailable):
        build_global_card_movers_row([{"id": "a", "name": "Alpha"}], sources,
                                     target_market_date="2026-08-01")


def test_valid_empty_all_array_is_included_not_malformed():
    row = build_global_card_movers_row(
        [{"id": "a", "name": "Alpha", "canonical_key": "alpha"}],
        [snapshot("a", [])],
        target_market_date="2026-08-01",
    )
    assert row["eligible_set_count"] == 1
    assert row["card_count"] == 0
    assert row["_diagnostics"]["includedSetCount"] == 1


class _Result:
    def __init__(self, data):
        self.data = data


class _Query:
    def __init__(self, rows):
        self.rows = rows
    def select(self, *_args): return self
    def eq(self, *_args): return self
    def limit(self, *_args): return self
    def execute(self): return _Result(self.rows)


class _Client:
    def __init__(self, rows):
        self.rows = rows
    def table(self, _name): return _Query(self.rows)


def test_read_service_serves_only_prepared_snapshot_and_caps_limit():
    payload = {"marketMovers": {"window": "7D", "all": [movement(str(i), i, i) for i in range(35)]},
               "meta": {"snapshot": {"marketDate": "2026-08-01"}}}
    result = read_explore_card_movers_snapshot(client=_Client([{"payload_json": payload}]), limit=99)
    assert result["marketMovers"]["window"] == "7D"
    assert len(result["marketMovers"]["all"]) == 30
