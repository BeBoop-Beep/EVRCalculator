from types import MappingProxyType

import pandas as pd
import pytest

from backend.calculations.packCalcsRefractored.evrCalculator import PackEVCalculator


class _ConfigStub:
    PULL_RATE_MAPPING = MappingProxyType({})
    RARITY_MAPPING = MappingProxyType(
        {
            "common": "common",
            "uncommon": "uncommon",
            "rare": "rare",
            "double rare": "hits",
            "illustration rare": "hits",
            "special illustration rare": "hits",
            "hyper rare": "hits",
            "ultra rare": "hits",
            "ace spec rare": "hits",
            "poke ball pattern": "hits",
            "master ball pattern": "hits",
        }
    )
    RARE_SLOT_PROBABILITY = {"double rare": 0.2, "rare": 0.8}
    REVERSE_SLOT_PROBABILITIES = {
        "slot_1": {"regular reverse": 1.0},
        "slot_2": {"regular reverse": 1.0},
    }
    GOD_PACK_CONFIG = {"enabled": False}
    DEMI_GOD_PACK_CONFIG = {"enabled": False}

    @staticmethod
    def get_rarity_pack_multiplier():
        return {"common": 4, "uncommon": 3}


@pytest.fixture
def calculator() -> PackEVCalculator:
    return PackEVCalculator(_ConfigStub())


def _prepared_single_row(
    calculator: PackEVCalculator,
    *,
    card_name: str,
    rarity: str,
    pull_rate: float,
    special_type: str,
    price: float = 10.0,
) -> pd.Series:
    raw_df = pd.DataFrame(
        [
            {
                "Card Name": card_name,
                "Rarity": rarity,
                "Price ($)": price,
                "Pull Rate (1/X)": pull_rate,
                "Pack Price": 5.0,
                "Special Type": special_type,
                "Reverse Variant Price ($)": 0.5,
            }
        ]
    )
    prepared, _ = calculator.load_and_prepare_data(raw_df)
    return prepared.iloc[0]


def test_pattern_detection_uses_structured_field_not_card_name(calculator: PackEVCalculator) -> None:
    row = _prepared_single_row(
        calculator,
        card_name="Master Ball Token",
        rarity="common",
        pull_rate=20.0,
        special_type="",
    )

    expected = 20.0 / 4.0
    assert row["pattern_key"] == "", "Row should not be marked as pattern when Special Type is blank"
    assert row["Effective_Pull_Rate"] == pytest.approx(expected), (
        "Misleading card name must not trigger pattern logic; common rows should use guaranteed-slot rate"
    )


def test_pattern_detection_ignores_card_name_variations(calculator: PackEVCalculator) -> None:
    for card_name in ["MASTER BALL", "master_ball", "Master-Ball"]:
        row = _prepared_single_row(
            calculator,
            card_name=card_name,
            rarity="common",
            pull_rate=20.0,
            special_type="",
        )
        assert row["pattern_key"] == "", f"Card name '{card_name}' must not create a pattern_key"
        assert row["Effective_Pull_Rate"] == pytest.approx(5.0), (
            f"Card name variation '{card_name}' must still use common guaranteed-slot rate"
        )


def test_pattern_key_overrides_card_name(calculator: PackEVCalculator) -> None:
    row = _prepared_single_row(
        calculator,
        card_name="Regular Common",
        rarity="rare",
        pull_rate=40.0,
        special_type="master_ball",
    )

    assert row["pattern_key"] == "master_ball_pattern", "Structured Special Type should map to master_ball_pattern"
    assert row["Effective_Pull_Rate"] == pytest.approx(40.0), (
        "Pattern rows must use exact configured pull rate rather than rarity-based adjustments"
    )


def test_non_pattern_common_works_correctly(calculator: PackEVCalculator) -> None:
    row = _prepared_single_row(
        calculator,
        card_name="Regular Common",
        rarity="common",
        pull_rate=20.0,
        special_type="",
    )

    assert row["pattern_key"] == "", "Non-pattern common row must have empty pattern_key"
    assert row["Effective_Pull_Rate"] == pytest.approx(5.0), "Common rows should divide base pull rate by four slots"
    assert row["Effective_Pull_Rate"] != pytest.approx(20.0), "Non-pattern common row must not use exact pull rate"


def test_non_pattern_rare_works_correctly(calculator: PackEVCalculator) -> None:
    row = _prepared_single_row(
        calculator,
        card_name="Regular Rare",
        rarity="rare",
        pull_rate=40.0,
        special_type="",
    )

    expected_probability = 0.8 * (1.0 / 40.0)
    expected_rate = 1.0 / expected_probability
    assert row["pattern_key"] == "", "Non-pattern rare row must have empty pattern_key"
    assert row["Effective_Pull_Rate"] == pytest.approx(expected_rate), "Rare rows must use probability-based rare-slot adjustment"
    assert row["Effective_Pull_Rate"] != pytest.approx(40.0), "Non-pattern rare row must not use exact pull rate"
