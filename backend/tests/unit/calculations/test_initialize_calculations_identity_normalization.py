from types import MappingProxyType

import pandas as pd
import pytest

from backend.calculations.packCalcsRefractored.initializeCalculations import PackEVInitializer
from backend.calculations.packCalcsRefractored.packCalculationOrchestrator import PackCalculationOrchestrator
from backend.calculations.utils.rarity_classification import filter_card_ev_by_hits
from backend.configured_special_pack_resolver import resolve_configured_god_pack_rows
from backend.constants.tcg.pokemon.scarletAndVioletEra.scarletAndViolet151 import Set151Config


class _ConfigStub:
    PULL_RATE_MAPPING = MappingProxyType({})
    RARITY_MAPPING = MappingProxyType({
        "common": "common",
        "uncommon": "uncommon",
        "rare": "rare",
        "double rare": "hits",
        "illustration rare": "hits",
        "special illustration rare": "hits",
    })
    RARE_SLOT_PROBABILITY = {"rare": 1.0}
    REVERSE_SLOT_PROBABILITIES = {
        "slot_1": {"regular reverse": 0.0},
        "slot_2": {"regular reverse": 0.0},
    }

    @staticmethod
    def get_rarity_pack_multiplier():
        return {"common": 1, "uncommon": 1}


class _InitializerUnderTest(PackEVInitializer):
    def calculate_effective_pull_rate(self, rarity_group, base_pull_rate, pattern_key=None):
        return base_pull_rate


def _base_row(**overrides):
    row = {
        "Card Name": "Bulbasaur",
        "Card Number": "",
        "Rarity": "common",
        "Special Type": "",
        "Price ($)": 1.0,
        "Pull Rate (1/X)": 10.0,
        "Pack Price": 5.0,
    }
    row.update(overrides)
    return row


def test_splits_combined_card_name_into_card_number_when_number_blank():
    initializer = _InitializerUnderTest(_ConfigStub())
    df = pd.DataFrame([
        _base_row(
            **{
                "Card Name": "Charmander - 168/165",
                "Card Number": "",
                "Rarity": "illustration rare",
                "Special Type": "regular",
            }
        )
    ])

    prepared_df, _ = initializer.load_and_prepare_data(df)

    assert prepared_df.iloc[0]["Card Name"] == "Charmander"
    assert prepared_df.iloc[0]["Card Number"] == "168/165"
    assert prepared_df.iloc[0]["Rarity"] == "illustration rare"
    assert prepared_df.iloc[0]["Special Type"] == "regular"
    assert prepared_df.iloc[0]["rarity_raw"] == "illustration rare"
    assert prepared_df.iloc[0]["rarity_group"] == "hits"
    assert prepared_df.iloc[0]["rarity_key"] == "illustration_rare"
    assert prepared_df.iloc[0]["special_type_raw"] == "regular"
    assert prepared_df.iloc[0]["special_type_key"] == "regular"
    assert prepared_df.iloc[0]["pattern_key"] == ""
    assert prepared_df.iloc[0]["base_rarity_key"] == "illustration_rare"
    assert prepared_df.iloc[0]["aggregation_key"] == "illustration_rare"
    assert prepared_df.iloc[0]["classification_key"] == "illustration_rare"


def test_cleans_combined_card_name_when_card_number_already_present():
    initializer = _InitializerUnderTest(_ConfigStub())
    df = pd.DataFrame([
        _base_row(
            **{
                "Card Name": "Charizard ex - 199/165",
                "Card Number": "199/165",
                "Rarity": "special illustration rare",
                "Special Type": "god_pack",
            }
        )
    ])

    prepared_df, _ = initializer.load_and_prepare_data(df)

    assert prepared_df.iloc[0]["Card Name"] == "Charizard ex"
    assert prepared_df.iloc[0]["Card Number"] == "199/165"
    assert prepared_df.iloc[0]["Rarity"] == "special illustration rare"
    assert prepared_df.iloc[0]["Special Type"] == "god_pack"


def test_already_normalized_rows_remain_unchanged():
    initializer = _InitializerUnderTest(_ConfigStub())
    df = pd.DataFrame([
        _base_row(
            **{
                "Card Name": "Pikachu",
                "Card Number": "025/165",
                "Rarity": "rare",
                "Special Type": "",
            }
        )
    ])

    prepared_df, _ = initializer.load_and_prepare_data(df)

    assert prepared_df.iloc[0]["Card Name"] == "Pikachu"
    assert prepared_df.iloc[0]["Card Number"] == "025/165"
    assert prepared_df.iloc[0]["Rarity"] == "rare"
    assert prepared_df.iloc[0]["rarity_raw"] == "rare"
    assert prepared_df.iloc[0]["rarity_group"] == "rare"
    assert prepared_df.iloc[0]["rarity_key"] == "rare"
    assert prepared_df.iloc[0]["special_type_raw"] == ""
    assert prepared_df.iloc[0]["special_type_key"] == ""
    assert prepared_df.iloc[0]["pattern_key"] == ""
    assert prepared_df.iloc[0]["base_rarity_key"] == "rare"
    assert prepared_df.iloc[0]["aggregation_key"] == "rare"
    assert prepared_df.iloc[0]["classification_key"] == "rare"


def test_rarity_key_normalizes_spaces_and_hyphens_without_changing_group_mapping():
    initializer = _InitializerUnderTest(_ConfigStub())
    df = pd.DataFrame([
        _base_row(
            **{
                "Rarity": "  Double   Rare  ",
            }
        )
    ])

    prepared_df, _ = initializer.load_and_prepare_data(df)

    assert prepared_df.iloc[0]["rarity_raw"] == "double   rare"
    assert prepared_df.iloc[0]["rarity_group"] is None or pd.isna(prepared_df.iloc[0]["rarity_group"])
    assert prepared_df.iloc[0]["rarity_key"] == "double_rare"
    assert prepared_df.iloc[0]["pattern_key"] == ""
    assert prepared_df.iloc[0]["base_rarity_key"] == "double_rare"
    assert prepared_df.iloc[0]["aggregation_key"] == "double_rare"
    assert prepared_df.iloc[0]["classification_key"] == "double_rare"


def test_pattern_overlay_preserves_base_classification_and_uses_pattern_aggregation():
    initializer = _InitializerUnderTest(_ConfigStub())
    df = pd.DataFrame([
        _base_row(
            **{
                "Rarity": "common",
                "Special Type": "poke ball",
            }
        )
    ])

    prepared_df, _ = initializer.load_and_prepare_data(df)

    assert prepared_df.iloc[0]["Rarity"] == "common"
    assert prepared_df.iloc[0]["rarity_key"] == "common"
    assert prepared_df.iloc[0]["special_type_raw"] == "poke ball"
    assert prepared_df.iloc[0]["special_type_key"] == "pokeball_pattern"
    assert prepared_df.iloc[0]["pattern_key"] == "pokeball_pattern"
    assert prepared_df.iloc[0]["base_rarity_key"] == "common"
    assert prepared_df.iloc[0]["aggregation_key"] == "pokeball_pattern"
    assert prepared_df.iloc[0]["classification_key"] == "common"


def test_raw_rarity_remains_intact_after_preparation():
    initializer = _InitializerUnderTest(_ConfigStub())
    df = pd.DataFrame([
        _base_row(
            **{
                "Rarity": "special illustration rare",
                "Special Type": "master ball pattern",
            }
        )
    ])

    prepared_df, _ = initializer.load_and_prepare_data(df)

    assert prepared_df.iloc[0]["Rarity"] == "special illustration rare"
    assert prepared_df.iloc[0]["rarity_raw"] == "special illustration rare"
    assert prepared_df.iloc[0]["special_type_key"] == "master_ball_pattern"
    assert prepared_df.iloc[0]["pattern_key"] == "master_ball_pattern"
    assert prepared_df.iloc[0]["base_rarity_key"] == "special_illustration_rare"
    assert prepared_df.iloc[0]["aggregation_key"] == "master_ball_pattern"
    assert prepared_df.iloc[0]["classification_key"] == "special_illustration_rare"


def test_master_ball_overlay_keeps_base_rarity_key_as_rare_while_aggregation_uses_pattern():
    initializer = _InitializerUnderTest(_ConfigStub())
    df = pd.DataFrame([
        _base_row(
            **{
                "Rarity": "rare",
                "Special Type": "master ball",
            }
        )
    ])

    prepared_df, _ = initializer.load_and_prepare_data(df)

    assert prepared_df.iloc[0]["rarity_key"] == "rare"
    assert prepared_df.iloc[0]["special_type_key"] == "master_ball_pattern"
    assert prepared_df.iloc[0]["pattern_key"] == "master_ball_pattern"
    assert prepared_df.iloc[0]["base_rarity_key"] == "rare"
    assert prepared_df.iloc[0]["aggregation_key"] == "master_ball_pattern"
    assert prepared_df.iloc[0]["classification_key"] == "rare"


def test_unknown_special_types_emit_diagnostic_and_fall_back_to_rarity_key(capsys):
    initializer = _InitializerUnderTest(_ConfigStub())
    df = pd.DataFrame([
        _base_row(
            **{
                "Rarity": "rare",
                "Special Type": "Galaxy Foil",
            }
        )
    ])

    prepared_df, _ = initializer.load_and_prepare_data(df)
    output = capsys.readouterr().out

    assert prepared_df.iloc[0]["special_type_raw"] == "galaxy foil"
    assert prepared_df.iloc[0]["special_type_key"] == "galaxy_foil"
    assert prepared_df.iloc[0]["pattern_key"] == ""
    assert prepared_df.iloc[0]["aggregation_key"] == "rare"
    assert prepared_df.iloc[0]["classification_key"] == "rare"
    assert "[SPECIAL_TYPE_WARNING]" in output
    assert "galaxy foil" in output
    assert "galaxy_foil" in output
    assert "pattern_key remains empty" in output
    assert "fall back to rarity_key" in output


def test_unmapped_rarity_emits_warning_and_keeps_group_missing(capsys):
    initializer = _InitializerUnderTest(_ConfigStub())
    df = pd.DataFrame([
        _base_row(
            **{
                "Rarity": "  Shiny-Ultra Rare  ",
            }
        )
    ])

    prepared_df, _ = initializer.load_and_prepare_data(df)
    output = capsys.readouterr().out

    assert prepared_df.iloc[0]["rarity_raw"] == "shiny-ultra rare"
    assert prepared_df.iloc[0]["rarity_key"] == "shiny_ultra_rare"
    assert pd.isna(prepared_df.iloc[0]["rarity_group"])
    assert "[RARITY_WARNING]" in output
    assert "shiny-ultra rare" in output
    assert "no fallback rarity_group was applied" in output


def test_active_runtime_rejects_file_path_input():
    initializer = _InitializerUnderTest(_ConfigStub())

    with pytest.raises(TypeError, match="only support pandas DataFrame input"):
        initializer.load_and_prepare_data("d:/EVRCalculator/data/excelDocs/Dummy/pokemon_data.xlsx")


def test_live_run_shape_with_blank_card_numbers_normalizes_to_plain_names_and_numbers():
    initializer = _InitializerUnderTest(_ConfigStub())
    df = pd.DataFrame(
        [
            _base_row(
                **{
                    "Card Name": "Charmander - 168/165",
                    "Card Number": "",
                    "Rarity": "illustration rare",
                }
            ),
            _base_row(
                **{
                    "Card Name": "Charizard ex - 199/165",
                    "Card Number": " ",
                    "Rarity": "special illustration rare",
                }
            ),
        ]
    )

    prepared_df, _ = initializer.load_and_prepare_data(df)

    assert prepared_df["Card Name"].tolist() == ["Charmander", "Charizard ex"]
    assert prepared_df["Card Number"].tolist() == ["168/165", "199/165"]


def test_normalized_runtime_path_enables_151_resolution_and_avoids_name_fallback_warning(capsys):
    initializer = _InitializerUnderTest(_ConfigStub())
    df = pd.DataFrame(
        [
            _base_row(
                **{
                    "Card Name": "Charmander - 168/165",
                    "Card Number": "",
                    "Rarity": "illustration rare",
                    "Price ($)": 8.0,
                }
            ),
            _base_row(
                **{
                    "Card Name": "Charmeleon - 169/165",
                    "Card Number": "",
                    "Rarity": "illustration rare",
                    "Price ($)": 6.0,
                }
            ),
            _base_row(
                **{
                    "Card Name": "Charizard ex - 199/165",
                    "Card Number": "",
                    "Rarity": "special illustration rare",
                    "Price ($)": 45.0,
                }
            ),
            _base_row(
                **{
                    "Card Name": "Charmander - 004/165",
                    "Card Number": "",
                    "Rarity": "common",
                    "Price ($)": 0.10,
                }
            ),
        ]
    )

    prepared_df, _ = initializer.load_and_prepare_data(df)
    cards = Set151Config.GOD_PACK_CONFIG["strategy"]["packs"][0]["cards"]

    resolved = resolve_configured_god_pack_rows(
        cards,
        prepared_df,
        context_label="test.runtime_normalized_151",
    )
    assert len(resolved) == 3
    assert set(resolved["Card Number"].tolist()) == {"168/165", "169/165", "199/165"}
    assert " - " not in " ".join(prepared_df["Card Name"].tolist())

    contributions, _ = PackCalculationOrchestrator.build_card_ev_contributions(prepared_df)
    assert "168/165" in contributions
    assert "169/165" in contributions
    assert "199/165" in contributions
    assert "004/165" in contributions

    hit, non_hit = filter_card_ev_by_hits(contributions, prepared_df, _ConfigStub())
    output = capsys.readouterr().out

    assert "card-name-based hit classification fallback" not in output
    assert "168/165" in hit
    assert "169/165" in hit
    assert "199/165" in hit
    assert "004/165" in non_hit
