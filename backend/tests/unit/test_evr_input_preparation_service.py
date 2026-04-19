from unittest.mock import Mock, patch

import pandas as pd
import pytest

from backend.db.services.evr_input_preparation_service import EVRInputPreparationService


class Config:
    SET_ID = "sv1"
    SET_NAME = "Base"


def test_prepare_for_set_emits_required_diagnostics_and_returns_transformed_payload():
    repository = Mock()
    transformer = Mock()

    repository.load_inputs.return_value = {
        "diagnostics": {
            "total_cards_loaded": 151,
            "cards_missing_prices": 7,
            "duplicate_card_mappings": 2,
            "pack_price_resolution_status": "priced",
            "etb_price_resolution_status": "priced",
            "promo_price_resolution_status": "missing_price",
        }
    }
    transformer.transform.return_value = {
        "card_rows": [
            {
                "card_name": "Charizard",
                "rarity": "rare",
                "market_price": 100.0,
                "pull_rate_one_in_x": 16.0,
                "reverse_market_price": 100.0,
            }
        ],
        "sealed_prices": {
            "pack_price": 6.0,
            "etb_price": 55.0,
            "etb_promo_card_price": 3.0,
        },
        "diagnostics": {
            "pack_price_missing": False,
            "etb_price_missing": False,
            "etb_promo_card_price_missing": True,
            "rows_emitted": 1,
            "rows_dropped": 0,
        },
    }
    transformer.to_legacy_calculator_payload.return_value = {
        "dataframe": pd.DataFrame(
            [
                {
                    "Card Name": "Charizard",
                    "Rarity": "rare",
                    "Price ($)": 100.0,
                    "Pull Rate (1/X)": 16.0,
                    "Reverse Variant Price ($)": 100.0,
                    "Pack Price": 6.0,
                    "ETB Price": 55.0,
                    "ETB Promo Card Price": 3.0,
                }
            ]
        ),
        "pack_price": 6.0,
        "etb_price": 55.0,
        "etb_promo_card_price": 3.0,
        "diagnostics": {
            "pack_price_missing": False,
            "etb_price_missing": False,
            "etb_promo_card_price_missing": True,
            "rows_emitted": 1,
            "rows_dropped": 0,
        },
    }

    config = Config()
    service = EVRInputPreparationService(repository=repository, transformer=transformer)

    with patch("builtins.print") as mock_print:
        transformed = service.prepare_for_set(config, "base", "Base")

    repository.load_inputs.assert_called_once_with(
        {
            "canonical_key": "base",
            "set_id": "sv1",
            "set_name": "Base",
        }
    )
    transformer.transform.assert_called_once_with(repository.load_inputs.return_value, config)
    transformer.to_legacy_calculator_payload.assert_called_once_with(transformer.transform.return_value)

    assert transformed["pack_price"] == 6.0
    assert isinstance(transformed["dataframe"], pd.DataFrame)
    assert "Reverse Variant Price ($)" in transformed["dataframe"].columns
    assert transformed["dataframe"]["Reverse Variant Price ($)"].iloc[0] == pytest.approx(100.0)

    diagnostics_lines = [
        call.args[0]
        for call in mock_print.call_args_list
        if call.args and isinstance(call.args[0], str) and call.args[0].startswith("[DB_INPUT_DIAGNOSTICS]")
    ]

    assert len(diagnostics_lines) == 1
    line = diagnostics_lines[0]
    assert '"total_cards_loaded": 151' in line
    assert '"cards_missing_prices": 7' in line
    assert '"duplicate_card_mappings": 2' in line
    assert '"pack_price_resolution"' in line
    assert '"etb_price_resolution"' in line
    assert '"promo_price_resolution"' in line
    assert '"status": "priced"' in line
    assert '"missing": false' in line
    assert '"missing": true' in line


def test_prepare_for_set_raises_when_pack_price_missing():
    repository = Mock()
    transformer = Mock()

    repository.load_inputs.return_value = {
        "diagnostics": {
            "total_cards_loaded": 2,
            "cards_missing_prices": 0,
            "duplicate_card_mappings": 0,
            "pack_price_resolution_status": "missing_price",
            "etb_price_resolution_status": "priced",
            "promo_price_resolution_status": "priced",
        }
    }
    transformer.transform.return_value = {
        "card_rows": [
            {
                "card_name": "Card A",
                "rarity": "rare",
                "market_price": 1.0,
                "pull_rate_one_in_x": 16.0,
                "reverse_market_price": 1.0,
            }
        ],
        "sealed_prices": {
            "pack_price": None,
            "etb_price": 55.0,
            "etb_promo_card_price": 3.0,
        },
        "diagnostics": {
            "pack_price_missing": True,
            "etb_price_missing": False,
            "etb_promo_card_price_missing": False,
            "rows_emitted": 1,
            "rows_dropped": 0,
        },
    }
    transformer.to_legacy_calculator_payload.return_value = {
        "dataframe": pd.DataFrame(
            [
                {
                    "Card Name": "Card A",
                    "Rarity": "rare",
                    "Price ($)": 1.0,
                    "Pull Rate (1/X)": 16.0,
                    "Reverse Variant Price ($)": 1.0,
                    "Pack Price": None,
                    "ETB Price": 55.0,
                    "ETB Promo Card Price": 3.0,
                }
            ]
        ),
        "pack_price": None,
        "etb_price": 55.0,
        "etb_promo_card_price": 3.0,
        "diagnostics": {
            "pack_price_missing": True,
            "etb_price_missing": False,
            "etb_promo_card_price_missing": False,
            "rows_emitted": 1,
            "rows_dropped": 0,
        },
    }

    service = EVRInputPreparationService(repository=repository, transformer=transformer)

    with patch("builtins.print"):
        with pytest.raises(ValueError) as exc_info:
            service.prepare_for_set(Config(), "base", "Base")

    assert "missing pack price" in str(exc_info.value).lower()


def test_prepare_for_set_uses_set_name_argument_when_config_name_missing():
    repository = Mock()
    transformer = Mock()

    repository.load_inputs.return_value = {"diagnostics": {}}
    transformer.transform.return_value = {
        "card_rows": [
            {
                "card_name": "Card A",
                "rarity": "rare",
                "market_price": 1.0,
                "pull_rate_one_in_x": 16.0,
                "reverse_market_price": 1.0,
            }
        ],
        "sealed_prices": {
            "pack_price": 5.0,
            "etb_price": None,
            "etb_promo_card_price": None,
        },
        "diagnostics": {
            "pack_price_missing": False,
            "rows_emitted": 1,
            "rows_dropped": 0,
        },
    }
    transformer.to_legacy_calculator_payload.return_value = {
        "dataframe": pd.DataFrame(
            [
                {
                    "Card Name": "Card A",
                    "Rarity": "rare",
                    "Price ($)": 1.0,
                    "Pull Rate (1/X)": 16.0,
                    "Reverse Variant Price ($)": 1.0,
                    "Pack Price": 5.0,
                    "ETB Price": None,
                    "ETB Promo Card Price": None,
                }
            ]
        ),
        "pack_price": 5.0,
        "etb_price": None,
        "etb_promo_card_price": None,
        "diagnostics": {
            "pack_price_missing": False,
            "rows_emitted": 1,
            "rows_dropped": 0,
        },
    }

    class ConfigWithoutSetName:
        SET_ID = "svX"

    service = EVRInputPreparationService(repository=repository, transformer=transformer)

    with patch("builtins.print"):
        service.prepare_for_set(ConfigWithoutSetName(), "base", "Fallback Set Name")

    repository.load_inputs.assert_called_once_with(
        {
            "canonical_key": "base",
            "set_id": "svX",
            "set_name": "Fallback Set Name",
        }
    )


def test_prepare_for_set_raises_when_reverse_variant_price_column_missing():
    repository = Mock()
    transformer = Mock()

    repository.load_inputs.return_value = {"diagnostics": {}}
    transformer.transform.return_value = {
        "card_rows": [
            {
                "card_name": "Card A",
                "rarity": "rare",
                "market_price": 1.0,
                "pull_rate_one_in_x": 16.0,
                "reverse_market_price": 1.0,
            }
        ],
        "sealed_prices": {
            "pack_price": 5.0,
            "etb_price": None,
            "etb_promo_card_price": None,
        },
        "diagnostics": {
            "pack_price_missing": False,
            "rows_emitted": 1,
            "rows_dropped": 0,
        },
    }
    transformer.to_legacy_calculator_payload.return_value = {
        "dataframe": pd.DataFrame(
            [
                {
                    "Card Name": "Card A",
                    "Rarity": "rare",
                    "Price ($)": 1.0,
                    "Pull Rate (1/X)": 16.0,
                    "Pack Price": 5.0,
                    "ETB Price": None,
                    "ETB Promo Card Price": None,
                }
            ]
        ),
        "pack_price": 5.0,
        "etb_price": None,
        "etb_promo_card_price": None,
        "diagnostics": {
            "pack_price_missing": False,
            "rows_emitted": 1,
            "rows_dropped": 0,
        },
    }

    service = EVRInputPreparationService(repository=repository, transformer=transformer)

    with patch("builtins.print"):
        with pytest.raises(ValueError) as exc_info:
            service.prepare_for_set(Config(), "base", "Base")

    assert "missing required reverse price column" in str(exc_info.value).lower()
