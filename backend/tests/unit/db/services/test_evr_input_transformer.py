from types import MappingProxyType

from backend.db.services.evr_input_transformer import EVRInputTransformer


class MockConfig:
    PULL_RATE_MAPPING = MappingProxyType(
        {
            "common": 40,
            "rare": 16,
            "illustration rare": 42,
            "master ball pattern": 1362,
            "poke ball pattern": 302,
        }
    )

    RARITY_MAPPING = MappingProxyType(
        {
            "common": "common",
            "rare": "rare",
            "illustration rare": "hits",
            "master ball pattern": "hits",
            "poke ball pattern": "hits",
        }
    )


def test_transform_emits_expected_dataframe_shape_and_scalars():
    payload = {
        "cards": [
            {
                "name": "Common A",
                "rarity": "Common",
                "variants": [
                    {
                        "variant_id": 100,
                        "printing": "Normal",
                        "special_type": "",
                        "near_mint_latest": {"market_price": 0.11},
                    }
                ],
            },
            {
                "name": "Rare A",
                "rarity": "Rare",
                "variants": [
                    {
                        "variant_id": 101,
                        "printing": "Holofoil",
                        "special_type": "ex",
                        "near_mint_latest": {"market_price": 1.35},
                    }
                ],
            },
            {
                "name": "No Price Card",
                "rarity": "Rare",
                "variants": [],
            },
            {
                "name": "Unknown Pull Rate",
                "rarity": "Promo Rare",
                "variants": [
                    {
                        "variant_id": 102,
                        "printing": "Normal",
                        "near_mint_latest": {"market_price": 2.5},
                    }
                ],
            },
        ],
        "sealed": {
            "pack": {"latest_price": {"market_price": 6.25}},
            "etb": {"latest_price": {"market_price": 54.99}},
            "promo": {"latest_price": {"market_price": 3.10}},
        },
    }

    transformer = EVRInputTransformer()
    transformed = transformer.transform(payload, MockConfig())

    assert set(transformed.keys()) == {"card_rows", "sealed_prices", "diagnostics"}
    assert transformed["sealed_prices"] == {
        "pack_price": 6.25,
        "etb_price": 54.99,
        "etb_promo_card_price": 3.10,
    }

    card_rows = transformed["card_rows"]
    assert card_rows == [
        {
            "card_name": "Common A",
            "card_number": "",
            "rarity": "common",
            "special_type": "",
            "market_price": 0.11,
            "pull_rate_one_in_x": 40.0,
            "reverse_market_price": 0.11,
        },
        {
            "card_name": "Rare A",
            "card_number": "",
            "rarity": "rare",
            "special_type": "ex",
            "market_price": 1.35,
            "pull_rate_one_in_x": 16.0,
            "reverse_market_price": 1.35,
        },
    ]

    compat = transformer.to_legacy_calculator_payload(transformed)
    df = compat["dataframe"]

    assert list(df.columns) == [
        "Card Name",
        "Card Number",
        "Rarity",
        "Special Type",
        "Price ($)",
        "Pull Rate (1/X)",
        "Reverse Variant Price ($)",
        "Pack Price",
        "ETB Price",
        "ETB Promo Card Price",
    ]

    assert len(df) == 2
    assert df["Card Name"].tolist() == ["Common A", "Rare A"]
    assert df["Rarity"].tolist() == ["common", "rare"]
    assert df["Special Type"].tolist() == ["", "ex"]
    assert df["Pull Rate (1/X)"].tolist() == [40.0, 16.0]
    assert df["Pack Price"].tolist() == [6.25, 6.25]
    assert df["ETB Price"].tolist() == [54.99, 54.99]
    assert df["ETB Promo Card Price"].tolist() == [3.10, 3.10]

    assert compat["pack_price"] == 6.25
    assert compat["etb_price"] == 54.99
    assert compat["etb_promo_card_price"] == 3.10

    diagnostics = transformed["diagnostics"]
    assert diagnostics["source_card_rows"] == 4
    assert diagnostics["rows_emitted"] == 2
    assert diagnostics["rows_dropped"] == 2
    assert diagnostics["missing_price_rows"] == 1
    assert diagnostics["missing_pull_rates"] == 1


def test_transform_uses_deterministic_variant_selection_for_base_and_reverse_price():
    payload = {
        "cards": [
            {
                "name": "Illustration Rare Test",
                "rarity": "Illustration Rare",
                "variants": [
                    {
                        "variant_id": 10,
                        "printing": "Holofoil",
                        "special_type": "",
                        "near_mint_latest": {"market_price": 7.0},
                    },
                    {
                        "variant_id": 11,
                        "printing": "Normal",
                        "special_type": "ex",
                        "near_mint_latest": {"market_price": 8.0},
                    },
                    {
                        "variant_id": 12,
                        "printing": "Reverse Holofoil",
                        "special_type": "",
                        "near_mint_latest": {"market_price": 12.0},
                    },
                ],
            }
        ],
        "sealed": {
            "pack": {"latest_price": {"market_price": 7.15}},
            "etb": None,
            "promo": None,
        },
    }

    transformer = EVRInputTransformer()
    transformed = transformer.transform(payload, MockConfig())
    df = transformer.to_legacy_calculator_payload(transformed)["dataframe"]

    assert len(df) == 1
    assert df.iloc[0]["Price ($)"] == 8.0
    assert df.iloc[0]["Reverse Variant Price ($)"] == 12.0
    assert df.iloc[0]["Special Type"] == "ex"
    assert df.iloc[0]["Pull Rate (1/X)"] == 42.0


def test_transform_supports_special_pull_rate_resolution_from_card_name():
    payload = {
        "cards": [
            {
                "name": "Pikachu Master Ball Pattern",
                "rarity": "Promo",
                "variants": [
                    {
                        "variant_id": 201,
                        "special_type": None,
                        "near_mint_latest": {"market_price": 44.0},
                    }
                ],
            }
        ],
        "sealed": {
            "pack": {"latest_price": {"market_price": 10}},
            "etb": {"latest_price": {"market_price": 60}},
            "promo": {"latest_price": {"market_price": 5}},
        },
    }

    transformer = EVRInputTransformer()
    transformed = transformer.transform(payload, MockConfig())
    df = transformer.to_legacy_calculator_payload(transformed)["dataframe"]

    assert len(df) == 1
    assert df.iloc[0]["Pull Rate (1/X)"] == 1362.0
    assert transformed["diagnostics"]["rows_emitted"] == 1
    assert transformed["diagnostics"]["rows_dropped"] == 0


def test_transform_passes_through_card_number_when_present():
    payload = {
        "cards": [
            {
                "name": "Charizard ex",
                "card_number": "006/165",
                "rarity": "Illustration Rare",
                "variants": [
                    {
                        "variant_id": 300,
                        "printing": "Holofoil",
                        "special_type": "ex",
                        "near_mint_latest": {"market_price": 25.0},
                    }
                ],
            },
            {
                "name": "Charizard ex",
                "card_number": "199/165",
                "rarity": "Master Ball Pattern",
                "variants": [
                    {
                        "variant_id": 301,
                        "printing": "Holofoil",
                        "special_type": "",
                        "near_mint_latest": {"market_price": 120.0},
                    }
                ],
            },
        ],
        "sealed": {
            "pack": {"latest_price": {"market_price": 6.25}},
            "etb": None,
            "promo": None,
        },
    }

    transformer = EVRInputTransformer()
    transformed = transformer.transform(payload, MockConfig())
    card_rows = transformed["card_rows"]

    assert len(card_rows) == 2
    assert card_rows[0]["card_number"] == "006/165"
    assert card_rows[1]["card_number"] == "199/165"
    assert card_rows[0]["special_type"] == "ex"
    assert card_rows[1]["special_type"] == ""

    df = transformer.to_legacy_calculator_payload(transformed)["dataframe"]
    assert df["Card Number"].tolist() == ["006/165", "199/165"]
    assert df["Special Type"].tolist() == ["ex", ""]
