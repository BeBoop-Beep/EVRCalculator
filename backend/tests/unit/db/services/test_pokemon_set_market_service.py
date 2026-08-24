import httpcore
import pytest

from backend.db.services import pokemon_set_market_service
from backend.db.services import public_read_retry


class _ImmediateSleepTime:
    """Drop-in for the retry module's `time`, so bounded backoff costs no wall clock."""

    @staticmethod
    def sleep(_seconds):
        return None

    @staticmethod
    def monotonic():
        return 0.0


def test_market_movers_all_ranks_signed_moves_by_absolute_percent_then_amount():
    movements = [
        {"canonicalCardId": "positive", "changePercent": 9.0, "changeAmount": 9.0, "moverEligible": True},
        {"canonicalCardId": "negative-largest", "changePercent": -30.0, "changeAmount": -1.0, "moverEligible": True},
        {"canonicalCardId": "negative-middle", "changePercent": -15.0, "changeAmount": -8.0, "moverEligible": True},
        {"canonicalCardId": "unreliable", "changePercent": -99.0, "changeAmount": -99.0, "moverEligible": False},
    ]

    payload = pokemon_set_market_service._movement_payload_for_window(
        context={"set": {"id": "set-1"}},
        movements=movements,
        window_days=7,
        limit=5,
        warnings=[],
        sources={},
        diagnostics={},
    )

    assert [row["canonicalCardId"] for row in payload["marketMovers"]["all"]] == [
        "negative-largest",
        "negative-middle",
        "positive",
    ]


class _Result:
    def __init__(self, data):
        self.data = data


class _Query:
    def __init__(self, table_name, handlers):
        self.table_name = table_name
        self.handlers = handlers
        self.select_fields = None
        self.eq_filters = []
        self.in_filters = []
        self.gte_filters = []
        self.gt_filters = []
        self.lt_filters = []
        self.order_fields = []
        self.limit_value = None
        self.range_value = None

    def select(self, fields):
        self.select_fields = fields
        return self

    def eq(self, field, value):
        self.eq_filters.append((field, value))
        return self

    def in_(self, field, values):
        self.in_filters.append((field, list(values)))
        return self

    def gte(self, field, value):
        self.gte_filters.append((field, value))
        return self

    def gt(self, field, value):
        self.gt_filters.append((field, value))
        return self

    def lt(self, field, value):
        self.lt_filters.append((field, value))
        return self

    def order(self, field, desc=False):
        self.order_fields.append((field, desc))
        return self

    def limit(self, value):
        self.limit_value = value
        return self

    def range(self, start, end):
        self.range_value = (start, end)
        return self

    def execute(self):
        return _Result(self.handlers[self.table_name](self))


class _Client:
    def __init__(self, handlers):
        self.handlers = handlers

    def table(self, table_name):
        if table_name not in self.handlers:
            raise AssertionError(f"Unexpected table requested: {table_name}")
        return _Query(table_name, self.handlers)


def test_top_chase_window_observations_paginate_past_postgrest_cap_and_keep_newest_rows():
    observations = [
        {
            "id": index + 1,
            "card_variant_id": "variant-1",
            "condition_id": "condition-nm",
            "market_price": 10.0 + index / 100,
            "source": "tcgplayer",
            "captured_at": (
                "2026-07-26T12:00:00+00:00"
                if index == 1000
                else "2026-07-27T12:00:00+00:00"
                if index == 1001
                else "2026-07-22T12:00:00+00:00"
            ),
        }
        for index in range(1002)
    ]
    queries = []

    def read_observations(query):
        queries.append(query)
        start, end = query.range_value
        return observations[start : end + 1]

    sources = {}
    rows = pokemon_set_market_service._load_price_observation_rows_for_window(
        variant_ids=["variant-1"],
        condition_id="condition-nm",
        start_date=pokemon_set_market_service.date(2026, 6, 28),
        end_date=pokemon_set_market_service.date(2026, 7, 28),
        sources=sources,
        source_key="top_chase_test",
        client=_Client({"card_variant_price_observations": read_observations}),
    )

    assert len(rows) == 1002
    assert [row["captured_at"][:10] for row in rows[-2:]] == ["2026-07-26", "2026-07-27"]
    assert [query.range_value for query in queries] == [(0, 999), (1000, 1999)]
    assert all(
        query.select_fields == "id,card_variant_id,condition_id,market_price,source,captured_at"
        for query in queries
    )
    assert all(query.order_fields == [("captured_at", False), ("id", False)] for query in queries)
    assert all(query.eq_filters == [("condition_id", "condition-nm")] for query in queries)
    assert all(query.gt_filters == [("market_price", 0)] for query in queries)
    assert all(query.gte_filters == [("captured_at", "2026-06-28")] for query in queries)
    assert all(query.lt_filters == [("captured_at", "2026-07-28")] for query in queries)
    assert sources["top_chase_test"] == "OK"


def test_canonical_top_chase_history_uses_paginated_newest_market_date():
    observations = [
        {
            "id": index + 1,
            "card_variant_id": "canonical-variant",
            "condition_id": "condition-nm",
            "market_price": 100.0 + index / 100,
            "source": "tcgplayer",
            "captured_at": (
                "2026-07-26T12:00:00+00:00"
                if index == 1000
                else "2026-07-27T12:00:00+00:00"
                if index == 1001
                else "2026-07-22T12:00:00+00:00"
            ),
        }
        for index in range(1002)
    ]
    queries = []

    def read_observations(query):
        queries.append(query)
        start, end = query.range_value
        return observations[start : end + 1]

    client = _Client({"card_variant_price_observations": read_observations})
    history_by_variant, diagnostics, meta = (
        pokemon_set_market_service._load_canonical_top_chase_price_history(
            [
                {
                    "card_id": "legacy-card",
                    "card_variant_id": "display-variant",
                    "condition_id": "condition-nm",
                    "card_name": "Ascended Hero ex",
                    "price_used": 110.01,
                    "captured_at": "2026-07-27T18:00:00+00:00",
                }
            ],
            30,
            {
                "set": {"id": "ascended-heroes"},
                "condition_id": "condition-nm",
                "legacy_card_to_canonical_id": {"legacy-card": "canonical-card"},
                "variant_to_canonical_id": {
                    "display-variant": "canonical-card",
                    "canonical-variant": "canonical-card",
                },
            },
            {},
            [],
            client=client,
        )
    )

    assert len(queries) == 2
    assert meta["asOfDate"] == meta["windowEnd"] == "2026-07-27"
    assert history_by_variant["display-variant"][-1]["date"] == "2026-07-27"
    assert diagnostics["display-variant"]["latestHistoryDate"] == "2026-07-27"
    assert diagnostics["display-variant"]["matchingConditionObservationCount"] == 1002


_CONDITION_ID = "condition-nm"


def _canonical_card(card_id, *, name, api_id, number="1"):
    return {
        "id": card_id,
        "set_id": "set-1",
        "pokemon_tcg_api_card_id": api_id,
        "name": name,
        "rarity": "Rare",
        "number": number,
        "printed_number": number,
        "image_small_url": None,
        "image_large_url": None,
    }


def _legacy_card(card_id, *, name, api_id, number="1"):
    return {
        "id": card_id,
        "set_id": "set-1",
        "name": name,
        "rarity": "Rare",
        "card_number": number,
        "pokemon_tcg_api_id": api_id,
        "image_small_url": None,
        "image_large_url": None,
    }


def _variant(variant_id, *, legacy_card_id, api_id):
    return {
        "id": variant_id,
        "card_id": legacy_card_id,
        "pokemon_tcg_api_id": api_id,
        "image_small_url": None,
        "image_large_url": None,
    }


def _build_movement_client(*, canonical_cards, legacy_cards, variants, latest_rows, observation_rows):
    return _Client(
        {
            "sets": lambda _q: [
                {"id": "set-1", "name": "Test Set", "canonical_key": "testSet", "pokemon_api_set_id": "sv-test"}
            ],
            "pokemon_canonical_cards": lambda _q: canonical_cards,
            "cards": lambda _q: legacy_cards,
            "card_variants": lambda _q: variants,
            "conditions": lambda _q: [{"id": _CONDITION_ID, "name": "Near Mint"}],
            "card_market_usd_latest_by_condition": lambda _q: latest_rows,
            "card_variant_price_observations": lambda _q: observation_rows,
        }
    )


def _movers_by_card_id(payload):
    return {
        movement.get("cardId"): movement
        for movement in (payload.get("marketMovers") or {}).get("all") or []
    }


def test_1d_mover_with_26_day_old_baseline_is_excluded(monkeypatch):
    """A card whose only available baseline is 26 days old must not appear as a 1D mover."""
    canonical_cards = [_canonical_card("card-1", name="Sylveon", api_id="api-1")]
    legacy_cards = [_legacy_card("legacy-1", name="Sylveon", api_id="api-1")]
    variants = [_variant("variant-1", legacy_card_id="legacy-1", api_id="api-1")]
    latest_rows = [
        {
            "variant_id": "variant-1",
            "condition_id": _CONDITION_ID,
            "market_price": 130.0,
            "source": "TCGPLAYER",
            "captured_at": "2026-07-02T12:00:00+00:00",
        }
    ]
    observation_rows = [
        {
            "card_variant_id": "variant-1",
            "condition_id": _CONDITION_ID,
            "market_price": 100.0,
            "source": "TCGPLAYER",
            "captured_at": "2026-06-06T12:00:00+00:00",
        },
        {
            "card_variant_id": "variant-1",
            "condition_id": _CONDITION_ID,
            "market_price": 130.0,
            "source": "TCGPLAYER",
            "captured_at": "2026-07-02T12:00:00+00:00",
        },
    ]
    client = _build_movement_client(
        canonical_cards=canonical_cards,
        legacy_cards=legacy_cards,
        variants=variants,
        latest_rows=latest_rows,
        observation_rows=observation_rows,
    )
    monkeypatch.setattr(pokemon_set_market_service, "service_read_client", client)

    payload = pokemon_set_market_service.build_pokemon_set_card_movement_payload(set_id="set-1", window_days=1)

    movers = _movers_by_card_id(payload)
    assert "card-1" not in movers, "a 26-day-old baseline must not be presented as a 1D movement"
    assert payload["movements"] == []


def test_7d_mover_with_26_day_old_baseline_is_excluded(monkeypatch):
    """A card whose only available baseline is 26 days old must not appear as a 7D mover."""
    canonical_cards = [_canonical_card("card-1", name="Sylveon", api_id="api-1")]
    legacy_cards = [_legacy_card("legacy-1", name="Sylveon", api_id="api-1")]
    variants = [_variant("variant-1", legacy_card_id="legacy-1", api_id="api-1")]
    latest_rows = [
        {
            "variant_id": "variant-1",
            "condition_id": _CONDITION_ID,
            "market_price": 130.0,
            "source": "TCGPLAYER",
            "captured_at": "2026-07-02T12:00:00+00:00",
        }
    ]
    observation_rows = [
        {
            "card_variant_id": "variant-1",
            "condition_id": _CONDITION_ID,
            "market_price": 100.0,
            "source": "TCGPLAYER",
            "captured_at": "2026-06-06T12:00:00+00:00",
        },
        {
            "card_variant_id": "variant-1",
            "condition_id": _CONDITION_ID,
            "market_price": 130.0,
            "source": "TCGPLAYER",
            "captured_at": "2026-07-02T12:00:00+00:00",
        },
    ]
    client = _build_movement_client(
        canonical_cards=canonical_cards,
        legacy_cards=legacy_cards,
        variants=variants,
        latest_rows=latest_rows,
        observation_rows=observation_rows,
    )
    monkeypatch.setattr(pokemon_set_market_service, "service_read_client", client)

    payload = pokemon_set_market_service.build_pokemon_set_card_movement_payload(set_id="set-1", window_days=7)

    movers = _movers_by_card_id(payload)
    assert "card-1" not in movers, "a 26-day-old baseline must not be presented as a 7D movement"
    assert payload["movements"] == []


def test_30d_mover_with_26_day_old_baseline_is_included(monkeypatch):
    """The same 26-day-old baseline is valid for a 30D window (min 14, max 45 days)."""
    canonical_cards = [_canonical_card("card-1", name="Sylveon", api_id="api-1")]
    legacy_cards = [_legacy_card("legacy-1", name="Sylveon", api_id="api-1")]
    variants = [_variant("variant-1", legacy_card_id="legacy-1", api_id="api-1")]
    latest_rows = [
        {
            "variant_id": "variant-1",
            "condition_id": _CONDITION_ID,
            "market_price": 130.0,
            "source": "TCGPLAYER",
            "captured_at": "2026-07-02T12:00:00+00:00",
        }
    ]
    observation_rows = [
        {
            "card_variant_id": "variant-1",
            "condition_id": _CONDITION_ID,
            "market_price": 100.0,
            "source": "TCGPLAYER",
            "captured_at": "2026-06-06T12:00:00+00:00",
        },
        {
            "card_variant_id": "variant-1",
            "condition_id": _CONDITION_ID,
            "market_price": 130.0,
            "source": "TCGPLAYER",
            "captured_at": "2026-07-02T12:00:00+00:00",
        },
    ]
    client = _build_movement_client(
        canonical_cards=canonical_cards,
        legacy_cards=legacy_cards,
        variants=variants,
        latest_rows=latest_rows,
        observation_rows=observation_rows,
    )
    monkeypatch.setattr(pokemon_set_market_service, "service_read_client", client)

    payload = pokemon_set_market_service.build_pokemon_set_card_movement_payload(set_id="set-1", window_days=30)

    movers = _movers_by_card_id(payload)
    assert "card-1" in movers
    movement = movers["card-1"]
    assert movement["historyStartDate"] == "2026-06-06"
    assert movement["historyEndDate"] == "2026-07-02"
    assert movement["change30dAmount"] == 30.0


def test_1d_7d_30d_produce_distinct_deltas_when_valid_baselines_exist(monkeypatch):
    """With observations positioned inside each window's tolerance, the three windows must diverge."""
    canonical_cards = [_canonical_card("card-2", name="Card Two", api_id="api-2")]
    legacy_cards = [_legacy_card("legacy-2", name="Card Two", api_id="api-2")]
    variants = [_variant("variant-2", legacy_card_id="legacy-2", api_id="api-2")]
    latest_rows = [
        {
            "variant_id": "variant-2",
            "condition_id": _CONDITION_ID,
            "market_price": 60.0,
            "source": "TCGPLAYER",
            "captured_at": "2026-07-02T12:00:00+00:00",
        }
    ]
    observation_rows = [
        {
            "card_variant_id": "variant-2",
            "condition_id": _CONDITION_ID,
            "market_price": 40.0,
            "source": "TCGPLAYER",
            "captured_at": "2026-06-05T12:00:00+00:00",
        },
        {
            "card_variant_id": "variant-2",
            "condition_id": _CONDITION_ID,
            "market_price": 50.0,
            "source": "TCGPLAYER",
            "captured_at": "2026-06-27T12:00:00+00:00",
        },
        {
            "card_variant_id": "variant-2",
            "condition_id": _CONDITION_ID,
            "market_price": 55.0,
            "source": "TCGPLAYER",
            "captured_at": "2026-07-01T12:00:00+00:00",
        },
        {
            "card_variant_id": "variant-2",
            "condition_id": _CONDITION_ID,
            "market_price": 60.0,
            "source": "TCGPLAYER",
            "captured_at": "2026-07-02T12:00:00+00:00",
        },
    ]

    results = {}
    for window_days in (1, 7, 30):
        client = _build_movement_client(
            canonical_cards=canonical_cards,
            legacy_cards=legacy_cards,
            variants=variants,
            latest_rows=latest_rows,
            observation_rows=observation_rows,
        )
        monkeypatch.setattr(pokemon_set_market_service, "service_read_client", client)
        payload = pokemon_set_market_service.build_pokemon_set_card_movement_payload(
            set_id="set-1", window_days=window_days
        )
        movers = _movers_by_card_id(payload)
        assert "card-2" in movers, f"card must be a valid mover for window_days={window_days}"
        results[window_days] = movers["card-2"]

    assert results[1]["change30dAmount"] == 5.0
    assert results[1]["historyStartDate"] == "2026-07-01"
    assert results[7]["change30dAmount"] == 10.0
    assert results[7]["historyStartDate"] == "2026-06-27"
    assert results[30]["change30dAmount"] == 20.0
    assert results[30]["historyStartDate"] == "2026-06-05"

    # The three windows must not collapse to the same amount/baseline.
    amounts = {results[1]["change30dAmount"], results[7]["change30dAmount"], results[30]["change30dAmount"]}
    assert len(amounts) == 3


def test_single_raw_observation_at_t_minus_1_day_plus_latest_row_is_a_valid_1d_mover(monkeypatch):
    """A variant with exactly one raw observation (T-1) plus a current price row (T) must not be discarded."""
    canonical_cards = [_canonical_card("card-3", name="Card Three", api_id="api-3")]
    legacy_cards = [_legacy_card("legacy-3", name="Card Three", api_id="api-3")]
    variants = [_variant("variant-3", legacy_card_id="legacy-3", api_id="api-3")]
    latest_rows = [
        {
            "variant_id": "variant-3",
            "condition_id": _CONDITION_ID,
            "market_price": 60.0,
            "source": "TCGPLAYER",
            "captured_at": "2026-07-02T12:00:00+00:00",
        }
    ]
    # Only ONE raw observation row exists for this variant — this is the shape the
    # old `if len(observations) < 2: continue` guard discarded before ever reaching
    # the current-price row appended below.
    observation_rows = [
        {
            "card_variant_id": "variant-3",
            "condition_id": _CONDITION_ID,
            "market_price": 55.0,
            "source": "TCGPLAYER",
            "captured_at": "2026-07-01T12:00:00+00:00",
        }
    ]
    client = _build_movement_client(
        canonical_cards=canonical_cards,
        legacy_cards=legacy_cards,
        variants=variants,
        latest_rows=latest_rows,
        observation_rows=observation_rows,
    )
    monkeypatch.setattr(pokemon_set_market_service, "service_read_client", client)

    payload = pokemon_set_market_service.build_pokemon_set_card_movement_payload(set_id="set-1", window_days=1)

    movers = _movers_by_card_id(payload)
    assert "card-3" in movers, "a single T-1 observation plus a live price must produce a valid 1D mover"
    movement = movers["card-3"]
    assert movement["change30dAmount"] == 5.0
    assert movement["historyStartDate"] == "2026-07-01"
    assert movement["historyEndDate"] == "2026-07-02"


def test_single_raw_observation_around_t_minus_5_days_plus_latest_row_is_a_valid_7d_mover(monkeypatch):
    """A variant with exactly one raw observation (~T-5) plus a current price row (T) must not be discarded."""
    canonical_cards = [_canonical_card("card-4", name="Card Four", api_id="api-4")]
    legacy_cards = [_legacy_card("legacy-4", name="Card Four", api_id="api-4")]
    variants = [_variant("variant-4", legacy_card_id="legacy-4", api_id="api-4")]
    latest_rows = [
        {
            "variant_id": "variant-4",
            "condition_id": _CONDITION_ID,
            "market_price": 60.0,
            "source": "TCGPLAYER",
            "captured_at": "2026-07-02T12:00:00+00:00",
        }
    ]
    observation_rows = [
        {
            "card_variant_id": "variant-4",
            "condition_id": _CONDITION_ID,
            "market_price": 50.0,
            "source": "TCGPLAYER",
            "captured_at": "2026-06-27T12:00:00+00:00",
        }
    ]
    client = _build_movement_client(
        canonical_cards=canonical_cards,
        legacy_cards=legacy_cards,
        variants=variants,
        latest_rows=latest_rows,
        observation_rows=observation_rows,
    )
    monkeypatch.setattr(pokemon_set_market_service, "service_read_client", client)

    payload = pokemon_set_market_service.build_pokemon_set_card_movement_payload(set_id="set-1", window_days=7)

    movers = _movers_by_card_id(payload)
    assert "card-4" in movers, "a single ~T-5 observation plus a live price must produce a valid 7D mover"
    movement = movers["card-4"]
    assert movement["change30dAmount"] == 10.0
    assert movement["historyStartDate"] == "2026-06-27"
    assert movement["historyEndDate"] == "2026-07-02"


def test_single_stale_observation_at_t_minus_26_days_is_still_excluded_from_1d(monkeypatch):
    """The relaxed single-observation path must not bypass the max-span guardrail."""
    canonical_cards = [_canonical_card("card-5", name="Card Five", api_id="api-5")]
    legacy_cards = [_legacy_card("legacy-5", name="Card Five", api_id="api-5")]
    variants = [_variant("variant-5", legacy_card_id="legacy-5", api_id="api-5")]
    latest_rows = [
        {
            "variant_id": "variant-5",
            "condition_id": _CONDITION_ID,
            "market_price": 130.0,
            "source": "TCGPLAYER",
            "captured_at": "2026-07-02T12:00:00+00:00",
        }
    ]
    observation_rows = [
        {
            "card_variant_id": "variant-5",
            "condition_id": _CONDITION_ID,
            "market_price": 100.0,
            "source": "TCGPLAYER",
            "captured_at": "2026-06-06T12:00:00+00:00",
        }
    ]
    client = _build_movement_client(
        canonical_cards=canonical_cards,
        legacy_cards=legacy_cards,
        variants=variants,
        latest_rows=latest_rows,
        observation_rows=observation_rows,
    )
    monkeypatch.setattr(pokemon_set_market_service, "service_read_client", client)

    payload = pokemon_set_market_service.build_pokemon_set_card_movement_payload(set_id="set-1", window_days=1)

    movers = _movers_by_card_id(payload)
    assert "card-5" not in movers, "a 26-day-old single observation must still be excluded from a 1D window"


# ---------------------------------------------------------------------------
# resolve_pokemon_set_identifier — shared resolver
# ---------------------------------------------------------------------------


class _RecordingSetsHandler:
    """A `sets` table handler that actually filters by eq(), and records every
    query issued so tests can assert which lookup strategy was used (unlike
    the fixed-row lambdas above, which ignore filters entirely)."""

    def __init__(self, rows):
        self.rows = rows
        self.calls = []

    def __call__(self, query):
        self.calls.append(query)
        if query.eq_filters:
            field, value = query.eq_filters[-1]
            matches = [row for row in self.rows if row.get(field) == value]
            return matches[: query.limit_value] if query.limit_value else matches
        return self.rows


def _set_row(set_id, name, canonical_key, api_id):
    return {"id": set_id, "name": name, "canonical_key": canonical_key, "pokemon_api_set_id": api_id}


_PRISMATIC_EVOLUTIONS_UUID = "11111111-1111-1111-1111-111111111111"


def test_resolve_pokemon_set_identifier_resolves_by_uuid(monkeypatch):
    rows = [_set_row(_PRISMATIC_EVOLUTIONS_UUID, "Prismatic Evolutions", "prismaticEvolutions", "sv8pt5")]
    sets_handler = _RecordingSetsHandler(rows)
    monkeypatch.setattr(pokemon_set_market_service, "service_read_client", _Client({"sets": sets_handler}))

    row = pokemon_set_market_service.resolve_pokemon_set_identifier(_PRISMATIC_EVOLUTIONS_UUID)

    assert row["id"] == _PRISMATIC_EVOLUTIONS_UUID
    assert len(sets_handler.calls) == 1, "UUID fast path must issue exactly one indexed lookup"
    assert sets_handler.calls[0].eq_filters == [("id", _PRISMATIC_EVOLUTIONS_UUID)]


def test_resolve_pokemon_set_identifier_uuid_fast_path_skips_normalized_scan(monkeypatch):
    rows = [_set_row(_PRISMATIC_EVOLUTIONS_UUID, "Prismatic Evolutions", "prismaticEvolutions", "sv8pt5")]
    sets_handler = _RecordingSetsHandler(rows)
    monkeypatch.setattr(pokemon_set_market_service, "service_read_client", _Client({"sets": sets_handler}))

    pokemon_set_market_service.resolve_pokemon_set_identifier(_PRISMATIC_EVOLUTIONS_UUID)

    assert all(call.eq_filters for call in sets_handler.calls), (
        "UUID fast path must never fall back to a full-table scan"
    )


def test_resolve_pokemon_set_identifier_resolves_by_canonical_key(monkeypatch):
    rows = [_set_row("set-uuid-1", "Prismatic Evolutions", "prismaticEvolutions", "sv8pt5")]
    sets_handler = _RecordingSetsHandler(rows)
    monkeypatch.setattr(pokemon_set_market_service, "service_read_client", _Client({"sets": sets_handler}))

    row = pokemon_set_market_service.resolve_pokemon_set_identifier("prismaticEvolutions")

    assert row["id"] == "set-uuid-1"


def test_resolve_pokemon_set_identifier_resolves_by_pokemon_api_set_id(monkeypatch):
    rows = [_set_row("set-uuid-1", "Prismatic Evolutions", "prismaticEvolutions", "sv8pt5")]
    sets_handler = _RecordingSetsHandler(rows)
    monkeypatch.setattr(pokemon_set_market_service, "service_read_client", _Client({"sets": sets_handler}))

    row = pokemon_set_market_service.resolve_pokemon_set_identifier("sv8pt5")

    assert row["id"] == "set-uuid-1"


def test_resolve_pokemon_set_identifier_resolves_hyphenated_slug_via_normalized_fallback(monkeypatch):
    rows = [_set_row("set-uuid-1", "Prismatic Evolutions", "prismaticEvolutions", "sv8pt5")]
    sets_handler = _RecordingSetsHandler(rows)
    monkeypatch.setattr(pokemon_set_market_service, "service_read_client", _Client({"sets": sets_handler}))

    row = pokemon_set_market_service.resolve_pokemon_set_identifier("prismatic-evolutions")

    assert row["id"] == "set-uuid-1"
    # id/canonical_key/pokemon_api_set_id eq attempts all miss, then a
    # full-table scan (no eq_filters) normalizes and matches by name.
    full_scan_calls = [call for call in sets_handler.calls if not call.eq_filters]
    assert len(full_scan_calls) == 1


def test_resolve_pokemon_set_identifier_raises_not_found_for_unknown_slug(monkeypatch):
    rows = [_set_row("set-uuid-1", "Prismatic Evolutions", "prismaticEvolutions", "sv8pt5")]
    sets_handler = _RecordingSetsHandler(rows)
    monkeypatch.setattr(pokemon_set_market_service, "service_read_client", _Client({"sets": sets_handler}))

    with pytest.raises(pokemon_set_market_service.PokemonSetMarketError) as exc_info:
        pokemon_set_market_service.resolve_pokemon_set_identifier("totally-unknown-set")

    assert exc_info.value.status_code == 404
    assert exc_info.value.code == "POKEMON_SET_NOT_FOUND"


def test_get_pokemon_set_value_history_payload_resolves_hyphenated_slug(monkeypatch):
    """Regression test: get_pokemon_set_value_history_payload previously 404'd
    on hyphen slugs like prismatic-evolutions because it used a weaker
    resolver with no normalized-slug fallback."""
    rows = [_set_row("set-uuid-1", "Prismatic Evolutions", "prismaticEvolutions", "sv8pt5")]
    sets_handler = _RecordingSetsHandler(rows)
    client = _Client(
        {
            "sets": sets_handler,
            "pokemon_set_value_daily_history": lambda _q: [],
        }
    )
    monkeypatch.setattr(pokemon_set_market_service, "service_read_client", client)

    payload = pokemon_set_market_service.get_pokemon_set_value_history_payload("prismatic-evolutions")

    assert payload["set"]["id"] == "set-uuid-1"
    assert payload["history"] == []


def test_build_pokemon_set_card_movement_payload_resolves_hyphenated_slug(monkeypatch):
    """Regression test: the live movers builder previously 404'd on hyphen
    slugs for the same reason as value-history."""
    canonical_cards = [_canonical_card("card-1", name="Sylveon", api_id="api-1")]
    legacy_cards = [_legacy_card("legacy-1", name="Sylveon", api_id="api-1")]
    variants = [_variant("variant-1", legacy_card_id="legacy-1", api_id="api-1")]
    sets_handler = _RecordingSetsHandler(
        [_set_row("set-1", "Prismatic Evolutions", "prismaticEvolutions", "sv8pt5")]
    )
    client = _Client(
        {
            "sets": sets_handler,
            "pokemon_canonical_cards": lambda _q: canonical_cards,
            "cards": lambda _q: legacy_cards,
            "card_variants": lambda _q: variants,
            "conditions": lambda _q: [{"id": _CONDITION_ID, "name": "Near Mint"}],
            "card_market_usd_latest_by_condition": lambda _q: [],
            "card_variant_price_observations": lambda _q: [],
        }
    )
    monkeypatch.setattr(pokemon_set_market_service, "service_read_client", client)

    payload = pokemon_set_market_service.build_pokemon_set_card_movement_payload(set_id="prismatic-evolutions")

    assert payload["set"]["id"] == "set-1"
    assert payload["movements"] == []


# ---------------------------------------------------------------------------
# resolve_pokemon_set_identifier — shared resolver
# ---------------------------------------------------------------------------


class _RecordingSetsHandler:
    """A `sets` table handler that actually filters by eq(), and records every
    query issued so tests can assert which lookup strategy was used (unlike
    the fixed-row lambdas above, which ignore filters entirely)."""

    def __init__(self, rows):
        self.rows = rows
        self.calls = []

    def __call__(self, query):
        self.calls.append(query)
        if query.eq_filters:
            field, value = query.eq_filters[-1]
            matches = [row for row in self.rows if row.get(field) == value]
            return matches[: query.limit_value] if query.limit_value else matches
        return self.rows


def _set_row(set_id, name, canonical_key, api_id):
    return {"id": set_id, "name": name, "canonical_key": canonical_key, "pokemon_api_set_id": api_id}


_PRISMATIC_EVOLUTIONS_UUID = "11111111-1111-1111-1111-111111111111"


def test_resolve_pokemon_set_identifier_resolves_by_uuid(monkeypatch):
    rows = [_set_row(_PRISMATIC_EVOLUTIONS_UUID, "Prismatic Evolutions", "prismaticEvolutions", "sv8pt5")]
    sets_handler = _RecordingSetsHandler(rows)
    monkeypatch.setattr(pokemon_set_market_service, "service_read_client", _Client({"sets": sets_handler}))

    row = pokemon_set_market_service.resolve_pokemon_set_identifier(_PRISMATIC_EVOLUTIONS_UUID)

    assert row["id"] == _PRISMATIC_EVOLUTIONS_UUID
    assert len(sets_handler.calls) == 1, "UUID fast path must issue exactly one indexed lookup"
    assert sets_handler.calls[0].eq_filters == [("id", _PRISMATIC_EVOLUTIONS_UUID)]


def test_resolve_pokemon_set_identifier_uuid_fast_path_skips_normalized_scan(monkeypatch):
    rows = [_set_row(_PRISMATIC_EVOLUTIONS_UUID, "Prismatic Evolutions", "prismaticEvolutions", "sv8pt5")]
    sets_handler = _RecordingSetsHandler(rows)
    monkeypatch.setattr(pokemon_set_market_service, "service_read_client", _Client({"sets": sets_handler}))

    pokemon_set_market_service.resolve_pokemon_set_identifier(_PRISMATIC_EVOLUTIONS_UUID)

    assert all(call.eq_filters for call in sets_handler.calls), (
        "UUID fast path must never fall back to a full-table scan"
    )


def test_resolve_pokemon_set_identifier_resolves_by_canonical_key(monkeypatch):
    rows = [_set_row("set-uuid-1", "Prismatic Evolutions", "prismaticEvolutions", "sv8pt5")]
    sets_handler = _RecordingSetsHandler(rows)
    monkeypatch.setattr(pokemon_set_market_service, "service_read_client", _Client({"sets": sets_handler}))

    row = pokemon_set_market_service.resolve_pokemon_set_identifier("prismaticEvolutions")

    assert row["id"] == "set-uuid-1"


def test_resolve_pokemon_set_identifier_resolves_by_pokemon_api_set_id(monkeypatch):
    rows = [_set_row("set-uuid-1", "Prismatic Evolutions", "prismaticEvolutions", "sv8pt5")]
    sets_handler = _RecordingSetsHandler(rows)
    monkeypatch.setattr(pokemon_set_market_service, "service_read_client", _Client({"sets": sets_handler}))

    row = pokemon_set_market_service.resolve_pokemon_set_identifier("sv8pt5")

    assert row["id"] == "set-uuid-1"


def test_resolve_pokemon_set_identifier_resolves_hyphenated_slug_via_normalized_fallback(monkeypatch):
    rows = [_set_row("set-uuid-1", "Prismatic Evolutions", "prismaticEvolutions", "sv8pt5")]
    sets_handler = _RecordingSetsHandler(rows)
    monkeypatch.setattr(pokemon_set_market_service, "service_read_client", _Client({"sets": sets_handler}))

    row = pokemon_set_market_service.resolve_pokemon_set_identifier("prismatic-evolutions")

    assert row["id"] == "set-uuid-1"
    # id/canonical_key/pokemon_api_set_id eq attempts all miss, then a
    # full-table scan (no eq_filters) normalizes and matches by name.
    full_scan_calls = [call for call in sets_handler.calls if not call.eq_filters]
    assert len(full_scan_calls) == 1


def test_resolve_pokemon_set_identifier_raises_not_found_for_unknown_slug(monkeypatch):
    rows = [_set_row("set-uuid-1", "Prismatic Evolutions", "prismaticEvolutions", "sv8pt5")]
    sets_handler = _RecordingSetsHandler(rows)
    monkeypatch.setattr(pokemon_set_market_service, "service_read_client", _Client({"sets": sets_handler}))

    with pytest.raises(pokemon_set_market_service.PokemonSetMarketError) as exc_info:
        pokemon_set_market_service.resolve_pokemon_set_identifier("totally-unknown-set")

    assert exc_info.value.status_code == 404
    assert exc_info.value.code == "POKEMON_SET_NOT_FOUND"


def test_get_pokemon_set_value_history_payload_resolves_hyphenated_slug(monkeypatch):
    """Regression test: get_pokemon_set_value_history_payload previously 404'd
    on hyphen slugs like prismatic-evolutions because it used a weaker
    resolver with no normalized-slug fallback."""
    rows = [_set_row("set-uuid-1", "Prismatic Evolutions", "prismaticEvolutions", "sv8pt5")]
    sets_handler = _RecordingSetsHandler(rows)
    client = _Client(
        {
            "sets": sets_handler,
            "pokemon_set_value_daily_history": lambda _q: [],
        }
    )
    monkeypatch.setattr(pokemon_set_market_service, "service_read_client", client)

    payload = pokemon_set_market_service.get_pokemon_set_value_history_payload("prismatic-evolutions")

    assert payload["set"]["id"] == "set-uuid-1"
    assert payload["history"] == []


def test_build_pokemon_set_card_movement_payload_resolves_hyphenated_slug(monkeypatch):
    """Regression test: the live movers builder previously 404'd on hyphen
    slugs for the same reason as value-history."""
    canonical_cards = [_canonical_card("card-1", name="Sylveon", api_id="api-1")]
    legacy_cards = [_legacy_card("legacy-1", name="Sylveon", api_id="api-1")]
    variants = [_variant("variant-1", legacy_card_id="legacy-1", api_id="api-1")]
    sets_handler = _RecordingSetsHandler(
        [_set_row("set-1", "Prismatic Evolutions", "prismaticEvolutions", "sv8pt5")]
    )
    client = _Client(
        {
            "sets": sets_handler,
            "pokemon_canonical_cards": lambda _q: canonical_cards,
            "cards": lambda _q: legacy_cards,
            "card_variants": lambda _q: variants,
            "conditions": lambda _q: [{"id": _CONDITION_ID, "name": "Near Mint"}],
            "card_market_usd_latest_by_condition": lambda _q: [],
            "card_variant_price_observations": lambda _q: [],
        }
    )
    monkeypatch.setattr(pokemon_set_market_service, "service_read_client", client)

    payload = pokemon_set_market_service.build_pokemon_set_card_movement_payload(set_id="prismatic-evolutions")

    assert payload["set"]["id"] == "set-1"


# ---------------------------------------------------------------------------
# get_pokemon_set_market_movers_payload — slim single-window movers endpoint
# ---------------------------------------------------------------------------


def _distinct_window_movement_fixture():
    """Same fixture as test_1d_7d_30d_produce_distinct_deltas_when_valid_baselines_exist
    — one card with observations positioned so 1D/7D/30D windows diverge."""
    canonical_cards = [_canonical_card("card-2", name="Card Two", api_id="api-2")]
    legacy_cards = [_legacy_card("legacy-2", name="Card Two", api_id="api-2")]
    variants = [_variant("variant-2", legacy_card_id="legacy-2", api_id="api-2")]
    latest_rows = [
        {
            "variant_id": "variant-2",
            "condition_id": _CONDITION_ID,
            "market_price": 60.0,
            "source": "TCGPLAYER",
            "captured_at": "2026-07-02T12:00:00+00:00",
        }
    ]
    observation_rows = [
        {
            "card_variant_id": "variant-2",
            "condition_id": _CONDITION_ID,
            "market_price": 40.0,
            "source": "TCGPLAYER",
            "captured_at": "2026-06-05T12:00:00+00:00",
        },
        {
            "card_variant_id": "variant-2",
            "condition_id": _CONDITION_ID,
            "market_price": 50.0,
            "source": "TCGPLAYER",
            "captured_at": "2026-06-27T12:00:00+00:00",
        },
        {
            "card_variant_id": "variant-2",
            "condition_id": _CONDITION_ID,
            "market_price": 55.0,
            "source": "TCGPLAYER",
            "captured_at": "2026-07-01T12:00:00+00:00",
        },
        {
            "card_variant_id": "variant-2",
            "condition_id": _CONDITION_ID,
            "market_price": 60.0,
            "source": "TCGPLAYER",
            "captured_at": "2026-07-02T12:00:00+00:00",
        },
    ]
    return canonical_cards, legacy_cards, variants, latest_rows, observation_rows


def test_market_movers_payload_returns_only_requested_window(monkeypatch):
    canonical_cards, legacy_cards, variants, latest_rows, observation_rows = _distinct_window_movement_fixture()

    results = {}
    for window in ("1D", "7D", "30D"):
        client = _build_movement_client(
            canonical_cards=canonical_cards,
            legacy_cards=legacy_cards,
            variants=variants,
            latest_rows=latest_rows,
            observation_rows=observation_rows,
        )
        monkeypatch.setattr(pokemon_set_market_service, "service_read_client", client)
        payload = pokemon_set_market_service.get_pokemon_set_market_movers_payload("set-1", window=window)

        assert payload["window"] == window
        assert payload["marketMovers"]["window"] == window
        # Only the requested window is present — no marketMoversByWindow key at all.
        assert "marketMoversByWindow" not in payload
        assert "market_movers_by_window" not in payload
        results[window] = payload

    amounts = {
        entry["marketMovers"]["heatingUp"][0]["change30dAmount"]
        for entry in results.values()
        if entry["marketMovers"]["heatingUp"]
    }
    assert len(amounts) == 3, "1D/7D/30D movers must not collapse to the same amount"
    assert results["1D"]["windowDays"] == 1
    assert results["7D"]["windowDays"] == 7
    assert results["30D"]["windowDays"] == 30


def test_market_movers_payload_excludes_top_chase_and_set_value_fields(monkeypatch):
    canonical_cards, legacy_cards, variants, latest_rows, observation_rows = _distinct_window_movement_fixture()
    client = _build_movement_client(
        canonical_cards=canonical_cards,
        legacy_cards=legacy_cards,
        variants=variants,
        latest_rows=latest_rows,
        observation_rows=observation_rows,
    )
    monkeypatch.setattr(pokemon_set_market_service, "service_read_client", client)

    payload = pokemon_set_market_service.get_pokemon_set_market_movers_payload("set-1")

    assert set(payload.keys()) == {"set", "window", "windowDays", "marketMovers", "meta"}
    assert "topChaseCardHistories" not in payload
    assert "setValueHistoriesByScope" not in payload


def test_market_movers_payload_resolves_prismatic_evolutions(monkeypatch):
    canonical_cards = [_canonical_card("card-1", name="Sylveon", api_id="api-1")]
    legacy_cards = [_legacy_card("legacy-1", name="Sylveon", api_id="api-1")]
    variants = [_variant("variant-1", legacy_card_id="legacy-1", api_id="api-1")]
    sets_handler = _RecordingSetsHandler(
        [_set_row("set-1", "Prismatic Evolutions", "prismaticEvolutions", "sv8pt5")]
    )
    client = _Client(
        {
            "sets": sets_handler,
            "pokemon_canonical_cards": lambda _q: canonical_cards,
            "cards": lambda _q: legacy_cards,
            "card_variants": lambda _q: variants,
            "conditions": lambda _q: [{"id": _CONDITION_ID, "name": "Near Mint"}],
            "card_market_usd_latest_by_condition": lambda _q: [],
            "card_variant_price_observations": lambda _q: [],
        }
    )
    monkeypatch.setattr(pokemon_set_market_service, "service_read_client", client)

    payload = pokemon_set_market_service.get_pokemon_set_market_movers_payload("prismatic-evolutions")

    assert payload["set"]["id"] == "set-1"


def test_market_movers_payload_invalid_window_normalizes_to_default(monkeypatch):
    canonical_cards, legacy_cards, variants, latest_rows, observation_rows = _distinct_window_movement_fixture()
    client = _build_movement_client(
        canonical_cards=canonical_cards,
        legacy_cards=legacy_cards,
        variants=variants,
        latest_rows=latest_rows,
        observation_rows=observation_rows,
    )
    monkeypatch.setattr(pokemon_set_market_service, "service_read_client", client)

    payload = pokemon_set_market_service.get_pokemon_set_market_movers_payload("set-1", window="90D")

    assert payload["window"] == "30D", "an unsupported window must normalize predictably to the 30D default"
    assert payload["windowDays"] == 30


def test_market_movers_payload_has_no_duplicate_snake_case_aliases(monkeypatch):
    """The /market/movers contract is a new slim v2 payload — camelCase
    only, no legacy snake_case alias duplicates (unlike the legacy
    /market/dashboard contract, which is left alone in this phase)."""
    canonical_cards, legacy_cards, variants, latest_rows, observation_rows = _distinct_window_movement_fixture()
    client = _build_movement_client(
        canonical_cards=canonical_cards,
        legacy_cards=legacy_cards,
        variants=variants,
        latest_rows=latest_rows,
        observation_rows=observation_rows,
    )
    monkeypatch.setattr(pokemon_set_market_service, "service_read_client", client)

    payload = pokemon_set_market_service.get_pokemon_set_market_movers_payload("set-1")

    for snake_key in (
        "market_movers",
        "market_movers_by_window",
        "window_days",
        "top_chase_cards",
        "top_chase_card_histories",
        "set_value_histories_by_scope",
    ):
        assert snake_key not in payload, f"{snake_key} must not appear in the camelCase-only movers payload"

    inner = payload["marketMovers"]
    for snake_key in ("window_days", "heating_up", "cooling_off"):
        assert snake_key not in inner, f"{snake_key} must not appear in the nested camelCase-only marketMovers object"


def _movers_fixture_for_n_cards(count):
    """Build a movement fixture for `count` distinct cards, each with a
    valid ~27-day-old baseline observation plus a live latest price row —
    the same recipe test_1d_7d_30d_produce_distinct_deltas_when_valid_baselines_exist
    uses for a single card, generalized to N cards for a payload-size test."""
    canonical_cards = []
    legacy_cards = []
    variants = []
    latest_rows = []
    observation_rows = []
    for index in range(count):
        card_id = f"card-{index}"
        legacy_id = f"legacy-{index}"
        variant_id = f"variant-{index}"
        api_id = f"api-{index}"
        canonical_cards.append(_canonical_card(card_id, name=f"Chase Card {index}", api_id=api_id))
        legacy_cards.append(_legacy_card(legacy_id, name=f"Chase Card {index}", api_id=api_id))
        variants.append(_variant(variant_id, legacy_card_id=legacy_id, api_id=api_id))
        latest_rows.append(
            {
                "variant_id": variant_id,
                "condition_id": _CONDITION_ID,
                "market_price": 60.0 + index,
                "source": "TCGPLAYER",
                "captured_at": "2026-07-02T12:00:00+00:00",
            }
        )
        observation_rows.append(
            {
                "card_variant_id": variant_id,
                "condition_id": _CONDITION_ID,
                "market_price": 40.0 + index,
                "source": "TCGPLAYER",
                "captured_at": "2026-06-05T12:00:00+00:00",
            }
        )
    return canonical_cards, legacy_cards, variants, latest_rows, observation_rows


def test_market_movers_payload_serialized_size_is_under_150kb(monkeypatch):
    """Payload budget: a representative fixture with 25 valid movers (well
    above the default limit=5) must serialize under 150KB, since movers
    carries no top-chase histories or set-value histories."""
    import json

    canonical_cards, legacy_cards, variants, latest_rows, observation_rows = _movers_fixture_for_n_cards(25)
    client = _build_movement_client(
        canonical_cards=canonical_cards,
        legacy_cards=legacy_cards,
        variants=variants,
        latest_rows=latest_rows,
        observation_rows=observation_rows,
    )
    monkeypatch.setattr(pokemon_set_market_service, "service_read_client", client)

    payload = pokemon_set_market_service.get_pokemon_set_market_movers_payload("set-1", limit=25)

    serialized_bytes = len(json.dumps(payload, default=str).encode("utf-8"))
    assert serialized_bytes < 150_000, f"movers payload was {serialized_bytes} bytes, over the 150KB budget"


# ---------------------------------------------------------------------------
# resolve_pokemon_set_identifier — stale pooled connection recovery
# ---------------------------------------------------------------------------
#
# OBSERVED FAILURE (2026-08-12, isolated production build): 84 generic 500s
# across 8 set-detail endpoints, every one of them an
# `httpcore.RemoteProtocolError: Server disconnected` raised out of the shared
# HTTP/2 connection pool on the FIRST database call of the request. The
# dominant frame was this resolver. It fails in ~40-230ms, far too fast to be
# query latency: an idle keep-alive connection is closed by PostgREST, the
# pooled client hands that dead connection to the next request, and the read
# dies immediately. Direct repeated calls never reproduce it because the
# connection stays hot; a tab navigation leaves exactly the idle gap required.
#
# The classifier already calls RemoteProtocolError transient, and this resolver
# already re-raised it deliberately — there was simply no retry, so a dead
# socket became a user-visible 500. The retry must use a FRESH client, since
# retrying on the same pool can hand back the same dead connection.


class _DisconnectingSetsHandler:
    """Raises a stale-connection error on the first N calls, then succeeds."""

    def __init__(self, rows, failures=1):
        self.rows = rows
        self.remaining_failures = failures
        self.calls = 0

    def __call__(self, query):
        self.calls += 1
        if self.remaining_failures > 0:
            self.remaining_failures -= 1
            raise httpcore.RemoteProtocolError("Server disconnected")
        if query.eq_filters:
            field, value = query.eq_filters[-1]
            matches = [row for row in self.rows if row.get(field) == value]
            return matches[: query.limit_value] if query.limit_value else matches
        return self.rows


def test_resolve_pokemon_set_identifier_recovers_from_stale_pooled_connection(monkeypatch):
    """A dead keep-alive connection must not surface as a 500."""
    rows = [_set_row(_PRISMATIC_EVOLUTIONS_UUID, "Prismatic Evolutions", "prismaticEvolutions", "sv8pt5")]
    handler = _DisconnectingSetsHandler(rows, failures=1)
    fresh_clients = []

    def _client_factory():
        client = _Client({"sets": handler})
        fresh_clients.append(client)
        return client

    monkeypatch.setattr(pokemon_set_market_service, "service_read_client", _Client({"sets": handler}))
    monkeypatch.setattr(pokemon_set_market_service, "create_short_timeout_service_client", _client_factory)
    monkeypatch.setattr(public_read_retry, "time", _ImmediateSleepTime())
    public_read_retry._reset_public_read_circuit_breaker_for_tests()

    row = pokemon_set_market_service.resolve_pokemon_set_identifier(_PRISMATIC_EVOLUTIONS_UUID)

    assert row["id"] == _PRISMATIC_EVOLUTIONS_UUID, "the retry must return the resolved set"
    assert handler.calls == 2, "exactly one retry — not zero, and not a retry storm"
    assert fresh_clients, "the retry must use a FRESH client, not the pool that just died"


# ---------------------------------------------------------------------------
# value-history — stale pooled connection recovery at the LATER read sites
# ---------------------------------------------------------------------------
#
# OBSERVED FAILURE (2026-08-12, isolated production build): after the resolver
# was hardened, backend 500s fell 84 -> 12 and every one of the 12 survivors
# came from `market/value-history` with the identical
# `httpcore.RemoteProtocolError: Server disconnected` signature. The resolver
# retry cannot cover these: they are the reads that run AFTER the resolver has
# already succeeded, so they can still be handed a different idle-killed socket
# out of the shared pool. Each was classified transient and re-raised with no
# retry, so the dead socket became a generic 500.


class _DisconnectingValueHistoryHandler:
    """Raises a stale-connection error on the first N calls, then returns rows."""

    def __init__(self, rows, failures=1):
        self.rows = rows
        self.remaining_failures = failures
        self.calls = 0

    def __call__(self, query):
        self.calls += 1
        if self.remaining_failures > 0:
            self.remaining_failures -= 1
            raise httpcore.RemoteProtocolError("Server disconnected")
        if query.limit_value:
            return self.rows[: query.limit_value]
        return self.rows


def _value_history_row(date_key, value):
    return {
        "snapshot_date": date_key,
        "value_scope": "market",
        "set_value": value,
        "priced_card_count": 10,
        "total_card_count": 10,
        "source": "test",
        "created_at": f"{date_key}T00:00:00+00:00",
        "updated_at": f"{date_key}T00:00:00+00:00",
    }


def _patch_value_history_retry(monkeypatch, sets_handler, history_handler):
    fresh_clients = []

    def _client_factory():
        client = _Client({"sets": sets_handler, "pokemon_set_value_daily_history": history_handler})
        fresh_clients.append(client)
        return client

    monkeypatch.setattr(
        pokemon_set_market_service,
        "service_read_client",
        _Client({"sets": sets_handler, "pokemon_set_value_daily_history": history_handler}),
    )
    monkeypatch.setattr(pokemon_set_market_service, "create_short_timeout_service_client", _client_factory)
    monkeypatch.setattr(public_read_retry, "time", _ImmediateSleepTime())
    public_read_retry._reset_public_read_circuit_breaker_for_tests()
    return fresh_clients


def test_value_history_recovers_from_stale_pooled_connection(monkeypatch):
    """The proven 12 remaining 500s must not survive as user-visible failures."""
    sets_handler = _RecordingSetsHandler(
        [_set_row("set-uuid-1", "Prismatic Evolutions", "prismaticEvolutions", "sv8pt5")]
    )
    history_handler = _DisconnectingValueHistoryHandler(
        [_value_history_row("2026-08-11", 100.0), _value_history_row("2026-08-12", 110.0)],
        failures=1,
    )
    fresh_clients = _patch_value_history_retry(monkeypatch, sets_handler, history_handler)

    payload = pokemon_set_market_service.get_pokemon_set_value_history_payload("prismatic-evolutions")

    assert payload["set"]["id"] == "set-uuid-1"
    assert payload["history"], "the retry must recover real history, not an empty degraded payload"
    assert fresh_clients, "the retry must use a FRESH client, not the pool that just died"


def test_value_history_retry_is_bounded_per_read(monkeypatch):
    """Persistent disconnects must still surface — no retry storm."""
    sets_handler = _RecordingSetsHandler(
        [_set_row("set-uuid-1", "Prismatic Evolutions", "prismaticEvolutions", "sv8pt5")]
    )
    history_handler = _DisconnectingValueHistoryHandler([], failures=99)
    _patch_value_history_retry(monkeypatch, sets_handler, history_handler)

    with pytest.raises(Exception):
        pokemon_set_market_service.get_pokemon_set_value_history_payload("prismatic-evolutions")

    assert history_handler.calls <= 2, "the live request path retries each read at most once"


def test_value_history_does_not_retry_a_deterministic_empty_result(monkeypatch):
    """No rows is a real answer, not a transient fault — retrying cannot help."""
    sets_handler = _RecordingSetsHandler(
        [_set_row("set-uuid-1", "Prismatic Evolutions", "prismaticEvolutions", "sv8pt5")]
    )
    calls = {"count": 0}

    def _history_handler(_query):
        calls["count"] += 1
        return []

    _patch_value_history_retry(monkeypatch, sets_handler, _history_handler)

    payload = pokemon_set_market_service.get_pokemon_set_value_history_payload("prismatic-evolutions")

    assert payload["history"] == []
    assert calls["count"] <= 2, "an empty result must not be retried per read"


def test_resolve_pokemon_set_identifier_does_not_retry_a_genuine_miss(monkeypatch):
    """A set that does not exist is deterministic — retrying cannot help."""
    handler = _RecordingSetsHandler([])
    monkeypatch.setattr(pokemon_set_market_service, "service_read_client", _Client({"sets": handler}))
    public_read_retry._reset_public_read_circuit_breaker_for_tests()

    with pytest.raises(pokemon_set_market_service.PokemonSetMarketError) as excinfo:
        pokemon_set_market_service.resolve_pokemon_set_identifier(_PRISMATIC_EVOLUTIONS_UUID)

    assert excinfo.value.status_code == 404
    assert len(handler.calls) == 1, "a 404 must not be retried"


def test_resolve_pokemon_set_identifier_gives_up_after_the_bounded_retry(monkeypatch):
    """Persistent disconnects must still fail — no unbounded retry loop."""
    handler = _DisconnectingSetsHandler([], failures=99)
    monkeypatch.setattr(pokemon_set_market_service, "service_read_client", _Client({"sets": handler}))
    monkeypatch.setattr(pokemon_set_market_service, "create_short_timeout_service_client",
                        lambda: _Client({"sets": handler}))
    monkeypatch.setattr(public_read_retry, "time", _ImmediateSleepTime())
    public_read_retry._reset_public_read_circuit_breaker_for_tests()

    with pytest.raises(Exception) as excinfo:
        pokemon_set_market_service.resolve_pokemon_set_identifier(_PRISMATIC_EVOLUTIONS_UUID)

    assert not isinstance(excinfo.value, pokemon_set_market_service.PokemonSetMarketError) or \
        excinfo.value.status_code >= 500
    assert handler.calls <= 2, "the live request path retries at most once"
