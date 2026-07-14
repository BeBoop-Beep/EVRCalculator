"""Canonical Market Movers contract tests.

Market Movers is a filtered/sorted view of the complete Cards dataset
(pokemon_set_cards_snapshot_latest.cards_json), never a separate
reliability-qualified subset. Membership is hasValidMovement + nonzero
movement; ranking is absolute dollar move desc, then absolute percent desc,
then canonical card id. Reliability stays metadata only. The Overview banner
(/market/movers) is the exact first-N slim projection of the same query.
"""

import pytest

from backend.db.services import pokemon_public_snapshot_service, public_read_retry


class _Result:
    def __init__(self, data):
        self.data = data


class _Query:
    def __init__(self, table_name, handlers):
        self.table_name = table_name
        self.handlers = handlers
        self.eq_filters = []
        self.limit_value = None

    def select(self, _fields):
        self.select_fields = _fields
        return self

    def eq(self, _field, _value):
        self.eq_filters.append((_field, _value))
        return self

    def limit(self, _value):
        self.limit_value = _value
        return self

    def order(self, _field, desc=False):
        return self

    def execute(self):
        return _Result(self.handlers[self.table_name](self))


class _Client:
    def __init__(self, handlers):
        self.handlers = handlers

    def table(self, table_name):
        return _Query(table_name, self.handlers)


@pytest.fixture(autouse=True)
def reset_public_read_circuit():
    public_read_retry._reset_public_read_circuit_breaker_for_tests()
    yield
    public_read_retry._reset_public_read_circuit_breaker_for_tests()


_TEST_UUID = "75cd439d-aaa2-41cb-86f3-2fefa5b26e29"

_CARDS_MOVEMENT_METADATA = {
    "movementContractVersion": "pokemon_card_movement_v1",
    "windowConvention": "inclusive_calendar_dates_v1",
    "movementAsOfDate": "2026-07-13",
    "marketAsOfDate": "2026-07-13",
    "generationId": "gen-cards-1",
    "builtAt": "2026-07-13T23:59:00+00:00",
}


def _movement_card(
    card_id,
    *,
    amount=None,
    percent=None,
    reliable=True,
    full_window=True,
    partial=False,
    history_points=5,
    price=10.0,
):
    movement = {
        "window": "7D",
        "windowDays": 7,
        "changeAmount": amount,
        "changePercent": percent,
        "reliable": reliable,
        "reliability": "high" if reliable else "low",
        "fullWindowCoverage": full_window,
        "isPartialWindow": partial,
        "windowCoverageDays": 3 if partial else 7,
        "requestedWindowDays": 7,
        "historyPointCount": history_points,
        "startDate": "2026-07-07",
        "endDate": "2026-07-13",
        "cardVariantId": f"variant-{card_id}",
        "conditionId": "condition-nm",
    }
    return {
        "id": card_id,
        "canonicalCardId": card_id,
        "cardVariantId": f"variant-{card_id}",
        "conditionId": "condition-nm",
        "name": f"Card {card_id}",
        "cardNumber": "1",
        "rarity": "Rare",
        "marketPrice": price,
        "currentPrice": price,
        "change7dAmount": amount,
        "change7dPercent": percent,
        "movement7dReliable": reliable,
        "movement7d": movement,
        "movementMetadata": dict(_CARDS_MOVEMENT_METADATA),
    }


def _cards_snapshot_client(cards, extra_handlers=None):
    handlers = {
        "pokemon_set_cards_snapshot_latest": lambda _q: [
            {
                "set_id": _TEST_UUID,
                "cards_json": cards,
                "card_count": len(cards),
                "updated_at": "2026-07-14T02:00:00+00:00",
            }
        ],
    }
    handlers.update(extra_handlers or {})
    return _Client(handlers)


def _movers_membership_fixture():
    return [
        _movement_card("neg-12", amount=-12.0, percent=-6.0),
        _movement_card("pos-8", amount=8.0, percent=4.0),
        _movement_card("neg-3", amount=-3.0, percent=-2.0),
        _movement_card("tiny-spike", amount=0.30, percent=100.0),
        _movement_card("big-25", amount=20.0, percent=25.0),
        _movement_card("unreliable", amount=15.0, percent=10.0, reliable=False),
        _movement_card("partial", amount=5.0, percent=3.0, full_window=False, partial=True),
        # Exactly zero movement: stays in All Cards, never in Market Movers.
        _movement_card("zero", amount=0.0, percent=0.0),
        # No calculable movement: All Cards only.
        _movement_card("no-movement", amount=None, percent=None, history_points=None),
    ]


def test_cards_page_market_movers_membership_uses_valid_nonzero_movement_not_reliability(monkeypatch):
    monkeypatch.setattr(
        pokemon_public_snapshot_service, "public_read_client", _cards_snapshot_client(_movers_membership_fixture())
    )

    movers = pokemon_public_snapshot_service.get_pokemon_set_cards_page_snapshot_payload(
        _TEST_UUID, sort="7d-movers", movement_sort="7d-movers", section="market-movers", page_size=60
    )
    mover_ids = [card["id"] for card in movers["cards"]]

    assert "unreliable" in mover_ids, "an explicitly unreliable but valid nonzero movement must appear"
    assert "partial" in mover_ids, "a valid partial-window movement must appear"
    assert "zero" not in mover_ids, "zero-movement cards stay out of Market Movers"
    assert "no-movement" not in mover_ids, "cards without calculable movement stay out of Market Movers"
    assert movers["pagination"]["totalCards"] == 7

    # Reliability metadata is retained on the served records.
    unreliable = next(card for card in movers["cards"] if card["id"] == "unreliable")
    assert unreliable["movement7d"]["reliable"] is False
    partial = next(card for card in movers["cards"] if card["id"] == "partial")
    assert partial["movement7d"]["isPartialWindow"] is True


def test_cards_page_all_cards_keeps_zero_and_no_movement_rows(monkeypatch):
    monkeypatch.setattr(
        pokemon_public_snapshot_service, "public_read_client", _cards_snapshot_client(_movers_membership_fixture())
    )

    all_cards = pokemon_public_snapshot_service.get_pokemon_set_cards_page_snapshot_payload(
        _TEST_UUID, sort="7d-movers", movement_sort="7d-movers", section="all-cards", page_size=60
    )
    all_ids = [card["id"] for card in all_cards["cards"]]

    assert "zero" in all_ids
    assert "no-movement" in all_ids
    assert all_cards["pagination"]["totalCards"] == 9


def test_cards_page_market_movers_sorts_by_absolute_dollar_then_percent_then_id(monkeypatch):
    monkeypatch.setattr(
        pokemon_public_snapshot_service, "public_read_client", _cards_snapshot_client(_movers_membership_fixture())
    )

    movers = pokemon_public_snapshot_service.get_pokemon_set_cards_page_snapshot_payload(
        _TEST_UUID, sort="7d-movers", movement_sort="7d-movers", section="market-movers", page_size=60
    )
    mover_ids = [card["id"] for card in movers["cards"]]

    # Absolute dollar move ranks first: a +100% $0.30 spike never outranks a
    # $20 +25% move; -$12 outranks +$8; +$8 outranks -$3.
    assert mover_ids == ["big-25", "unreliable", "neg-12", "pos-8", "partial", "neg-3", "tiny-spike"]


def test_cards_page_market_movers_percent_tiebreak_and_canonical_id_determinism(monkeypatch):
    cards = [
        _movement_card("b-card", amount=5.0, percent=10.0),
        _movement_card("a-card", amount=5.0, percent=10.0),
        _movement_card("z-higher-percent", amount=5.0, percent=12.0),
    ]
    monkeypatch.setattr(pokemon_public_snapshot_service, "public_read_client", _cards_snapshot_client(cards))

    movers = pokemon_public_snapshot_service.get_pokemon_set_cards_page_snapshot_payload(
        _TEST_UUID, sort="7d-movers", movement_sort="7d-movers", section="market-movers"
    )

    assert [card["id"] for card in movers["cards"]] == ["z-higher-percent", "a-card", "b-card"]


def test_cards_page_heating_and_cooling_filter_by_direction_only(monkeypatch):
    monkeypatch.setattr(
        pokemon_public_snapshot_service, "public_read_client", _cards_snapshot_client(_movers_membership_fixture())
    )

    heating = pokemon_public_snapshot_service.get_pokemon_set_cards_page_snapshot_payload(
        _TEST_UUID, sort="7d-movers", movement_sort="7d-movers", section="market-movers", movement_filter="heating"
    )
    cooling = pokemon_public_snapshot_service.get_pokemon_set_cards_page_snapshot_payload(
        _TEST_UUID, sort="7d-movers", movement_sort="7d-movers", section="market-movers", movement_filter="cooling"
    )

    heating_ids = [card["id"] for card in heating["cards"]]
    cooling_ids = [card["id"] for card in cooling["cards"]]

    assert heating_ids == ["big-25", "unreliable", "pos-8", "partial", "tiny-spike"]
    assert cooling_ids == ["neg-12", "neg-3"]
    assert heating["pagination"]["totalCards"] == 5
    assert cooling["pagination"]["totalCards"] == 2


def test_cards_page_market_movers_pagination_traverses_complete_filtered_list(monkeypatch):
    cards = [_movement_card(f"card-{index:03d}", amount=float(200 - index), percent=5.0) for index in range(160)]
    cards.extend(_movement_card(f"flat-{index}", amount=0.0, percent=0.0) for index in range(30))
    monkeypatch.setattr(pokemon_public_snapshot_service, "public_read_client", _cards_snapshot_client(cards))

    page1 = pokemon_public_snapshot_service.get_pokemon_set_cards_page_snapshot_payload(
        _TEST_UUID, sort="7d-movers", movement_sort="7d-movers", section="market-movers", page=1, page_size=60
    )
    page3 = pokemon_public_snapshot_service.get_pokemon_set_cards_page_snapshot_payload(
        _TEST_UUID, sort="7d-movers", movement_sort="7d-movers", section="market-movers", page=3, page_size=60
    )

    assert page1["pagination"]["totalCards"] == 160
    assert page1["pagination"]["totalPages"] == 3
    assert page1["pagination"]["hasNextPage"] is True
    assert len(page3["cards"]) == 40
    assert page3["pagination"]["hasNextPage"] is False
    totals = page1["meta"]["movementTotals"]
    assert totals["checklistCardCount"] == 190
    assert totals["cardsWithCalculableMovement"] == 190
    assert totals["nonzeroMovementCount"] == 160
    assert totals["filteredTotal"] == 160
    assert totals["pageCount"] == 60


def test_cards_page_meta_exposes_market_as_of_date_from_generation(monkeypatch):
    monkeypatch.setattr(
        pokemon_public_snapshot_service, "public_read_client", _cards_snapshot_client(_movers_membership_fixture())
    )

    payload = pokemon_public_snapshot_service.get_pokemon_set_cards_page_snapshot_payload(_TEST_UUID)

    assert payload["meta"]["snapshot"]["marketAsOfDate"] == "2026-07-13"
    assert payload["meta"]["snapshot"]["generationId"] == "gen-cards-1"


def _legacy_dashboard_handler(rows_by_window_key):
    def handler(query):
        requested_window_key = None
        for field, value in query.eq_filters:
            if field == "window_key":
                requested_window_key = value
        row = rows_by_window_key.get(requested_window_key)
        if not row:
            return []
        mover_window = None
        for candidate in ("1D", "7D", "30D"):
            if f"marketMoversByWindow->{candidate}->" in query.select_fields:
                mover_window = candidate
                break
        movers_by_window = row.get("_market_movers_by_window") or {}
        entry = movers_by_window.get(mover_window)
        result_row = {key: value for key, value in row.items() if not key.startswith("_")}
        result_row["heating"] = (entry or {}).get("heatingUp") if entry is not None else None
        result_row["cooling"] = (entry or {}).get("coolingOff") if entry is not None else None
        result_row["all_items"] = (entry or {}).get("all") if entry is not None else None
        result_row["heating_snake"] = None
        result_row["cooling_snake"] = None
        result_row["all_items_snake"] = None
        return [result_row]

    return handler


def _legacy_mover_card(card_id):
    return {"cardId": card_id, "name": card_id, "currentPrice": 1.0, "changeAmount": 1.0, "changePercent": 1.0}


def _legacy_dashboard_row():
    return {
        "set_id": _TEST_UUID,
        "window_key": "365d",
        "latest_market_date": "2026-07-14",
        "updated_at": "2026-07-14T00:00:00+00:00",
        "_market_movers_by_window": {
            "7D": {
                "heatingUp": [_legacy_mover_card("legacy-h1")],
                "coolingOff": [_legacy_mover_card("legacy-c1")],
                "all": [_legacy_mover_card("legacy-h1"), _legacy_mover_card("legacy-c1")],
            }
        },
    }


def test_market_movers_endpoint_is_first_n_of_canonical_cards_query(monkeypatch):
    cards = _movers_membership_fixture()
    # A legacy dashboard row with a differently-ranked mover list must NOT be
    # consulted when the canonical cards snapshot exists.
    client = _cards_snapshot_client(
        cards,
        extra_handlers={
            "pokemon_set_market_dashboard_snapshot_latest": _legacy_dashboard_handler({"365d": _legacy_dashboard_row()})
        },
    )
    monkeypatch.setattr(pokemon_public_snapshot_service, "public_read_client", client)

    movers = pokemon_public_snapshot_service.get_pokemon_set_market_movers_snapshot_payload(
        _TEST_UUID, window="7D", limit=10
    )
    cards_page = pokemon_public_snapshot_service.get_pokemon_set_cards_page_snapshot_payload(
        _TEST_UUID, sort="7d-movers", movement_sort="7d-movers", section="market-movers", page=1, page_size=60
    )

    banner = movers["marketMovers"]["all"]
    cards_first = cards_page["cards"][: len(banner)]

    assert [card["canonicalCardId"] for card in banner] == [card["canonicalCardId"] for card in cards_first]
    assert not any(card["canonicalCardId"].startswith("legacy-") for card in banner)
    for banner_card, cards_card in zip(banner, cards_first):
        assert banner_card["cardVariantId"] == cards_card["cardVariantId"]
        assert banner_card["conditionId"] == cards_card["conditionId"]
        assert banner_card["currentPrice"] == cards_card["currentPrice"]
        assert banner_card["changeAmount"] == cards_card["change7dAmount"]
        assert banner_card["changePercent"] == cards_card["change7dPercent"]
        assert banner_card["startDate"] == cards_card["movement7d"]["startDate"]
        assert banner_card["endDate"] == cards_card["movement7d"]["endDate"]

    assert movers["meta"]["snapshot"]["source"] == "canonical_cards_filter"
    assert movers["meta"]["snapshot"]["usedLegacyMoverList"] is False
    assert movers["meta"]["snapshot"]["marketAsOfDate"] == "2026-07-13"
    assert movers["meta"]["query"] == {
        "section": "market-movers",
        "window": "7D",
        "movement": "all",
        "sort": "largest-dollar-move",
        "limit": 10,
    }
    # Slim projection: no heavy checklist fields ride along.
    assert "priceHistory" not in banner[0]
    assert "movementMetadata" not in banner[0]


def test_market_movers_endpoint_banner_can_be_ten_negatives_and_is_not_five_five_capped(monkeypatch):
    cards = [
        _movement_card(f"drop-{index:02d}", amount=-float(50 - index), percent=-10.0) for index in range(12)
    ]
    cards.append(_movement_card("small-gain", amount=0.5, percent=1.0))
    monkeypatch.setattr(pokemon_public_snapshot_service, "public_read_client", _cards_snapshot_client(cards))

    movers = pokemon_public_snapshot_service.get_pokemon_set_market_movers_snapshot_payload(
        _TEST_UUID, window="7D", limit=10
    )

    banner = movers["marketMovers"]["all"]
    assert len(banner) == 10
    assert all(card["changeAmount"] < 0 for card in banner), "ten negatives must be allowed when they are the largest moves"
    # Directional arrays are derived views of the same canonical list.
    assert [card["id"] for card in movers["marketMovers"]["coolingOff"]] == [card["id"] for card in banner]
    assert movers["marketMovers"]["heatingUp"] == []


def test_market_movers_endpoint_serves_fewer_than_ten_only_when_fewer_valid_movers_exist(monkeypatch):
    cards = [
        _movement_card("only-mover-1", amount=4.0, percent=2.0),
        _movement_card("only-mover-2", amount=-1.5, percent=-1.0),
        _movement_card("zero", amount=0.0, percent=0.0),
        _movement_card("no-movement", amount=None, percent=None),
    ]
    monkeypatch.setattr(pokemon_public_snapshot_service, "public_read_client", _cards_snapshot_client(cards))

    movers = pokemon_public_snapshot_service.get_pokemon_set_market_movers_snapshot_payload(
        _TEST_UUID, window="7D", limit=10
    )

    assert [card["id"] for card in movers["marketMovers"]["all"]] == ["only-mover-1", "only-mover-2"]
    assert movers["meta"]["movementTotals"]["nonzeroMovementCount"] == 2
    assert movers["meta"]["movementTotals"]["filteredTotal"] == 2


def test_market_movers_endpoint_heating_and_cooling_movement_filters(monkeypatch):
    monkeypatch.setattr(
        pokemon_public_snapshot_service, "public_read_client", _cards_snapshot_client(_movers_membership_fixture())
    )

    heating = pokemon_public_snapshot_service.get_pokemon_set_market_movers_snapshot_payload(
        _TEST_UUID, window="7D", limit=10, movement="heating"
    )
    cooling = pokemon_public_snapshot_service.get_pokemon_set_market_movers_snapshot_payload(
        _TEST_UUID, window="7D", limit=10, movement="cooling"
    )

    assert all(card["changeAmount"] > 0 for card in heating["marketMovers"]["all"])
    assert all(card["changeAmount"] < 0 for card in cooling["marketMovers"]["all"])
    assert heating["meta"]["movementTotals"]["filteredTotal"] == 5
    assert cooling["meta"]["movementTotals"]["filteredTotal"] == 2


def test_market_movers_endpoint_falls_back_to_diagnosed_legacy_list_when_cards_snapshot_missing(monkeypatch):
    client = _Client(
        {
            "pokemon_set_cards_snapshot_latest": lambda _q: [],
            "pokemon_set_market_dashboard_snapshot_latest": _legacy_dashboard_handler({"365d": _legacy_dashboard_row()}),
        }
    )
    monkeypatch.setattr(pokemon_public_snapshot_service, "public_read_client", client)

    movers = pokemon_public_snapshot_service.get_pokemon_set_market_movers_snapshot_payload(
        _TEST_UUID, window="7D", limit=10
    )

    assert movers["meta"]["snapshot"]["usedLegacyMoverList"] is True
    assert movers["meta"]["snapshot"]["source"] == "pokemon_set_market_dashboard_snapshot_latest"
    assert any("legacy" in warning.lower() for warning in movers["meta"]["warnings"])
    assert [card["cardId"] for card in movers["marketMovers"]["all"]] == ["legacy-h1", "legacy-c1"]
