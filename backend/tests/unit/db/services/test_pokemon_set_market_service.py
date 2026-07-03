from backend.db.services import pokemon_set_market_service


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
        self.order_fields = []
        self.limit_value = None

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

    def order(self, field, desc=False):
        self.order_fields.append((field, desc))
        return self

    def limit(self, value):
        self.limit_value = value
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
    monkeypatch.setattr(pokemon_set_market_service, "public_read_client", client)

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
    monkeypatch.setattr(pokemon_set_market_service, "public_read_client", client)

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
    monkeypatch.setattr(pokemon_set_market_service, "public_read_client", client)

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
        monkeypatch.setattr(pokemon_set_market_service, "public_read_client", client)
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
    monkeypatch.setattr(pokemon_set_market_service, "public_read_client", client)

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
    monkeypatch.setattr(pokemon_set_market_service, "public_read_client", client)

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
    monkeypatch.setattr(pokemon_set_market_service, "public_read_client", client)

    payload = pokemon_set_market_service.build_pokemon_set_card_movement_payload(set_id="set-1", window_days=1)

    movers = _movers_by_card_id(payload)
    assert "card-5" not in movers, "a 26-day-old single observation must still be excluded from a 1D window"
    assert payload["movements"] == []
