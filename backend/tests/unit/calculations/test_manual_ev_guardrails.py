from types import MappingProxyType
from unittest import mock

import pandas as pd
import pytest

from backend.calculations.packCalcsRefractored.packCalculationOrchestrator import (
    PackCalculationOrchestrator,
)


class _GuardrailConfig:
    RARITY_MAPPING = MappingProxyType(
        {
            "common": "common",
            "uncommon": "uncommon",
            "rare": "rare",
            "double rare": "hits",
            "ultra rare": "hits",
            "hyper rare": "hits",
            "illustration rare": "hits",
            "special illustration rare": "hits",
            "ace spec rare": "hits",
            "shiny rare": "hits",
            "shiny ultra rare": "hits",
        }
    )
    PULL_RATE_MAPPING = MappingProxyType(
        {
            "common": 10,
            "uncommon": 10,
            "rare": 20,
        }
    )
    RARE_SLOT_PROBABILITY = {"rare": 1.0}
    REVERSE_SLOT_PROBABILITIES = {
        "slot_1": {"regular reverse": 0.0},
        "slot_2": {"regular reverse": 0.0},
    }
    GOD_PACK_CONFIG = {"enabled": False}
    DEMI_GOD_PACK_CONFIG = {"enabled": False}

    @staticmethod
    def get_rarity_pack_multiplier():
        return {"common": 1, "uncommon": 1}


def _build_raw_df(rows):
    return pd.DataFrame(rows)


def test_active_manual_path_includes_paldean_fates_shiny_rarities_in_dynamic_totals_and_total_manual_ev():
    orchestrator = PackCalculationOrchestrator(_GuardrailConfig())
    raw_df = _build_raw_df(
        [
            {
                "Card Name": "Paldean Student",
                "Card Number": "001/091",
                "Rarity": "common",
                "Price ($)": 1.0,
                "Pull Rate (1/X)": 10.0,
                "Pack Price": 5.0,
            },
            {
                "Card Name": "Wugtrio ex",
                "Card Number": "057/091",
                "Rarity": "shiny rare",
                "Price ($)": 12.0,
                "Pull Rate (1/X)": 24.0,
                "Pack Price": 5.0,
            },
            {
                "Card Name": "Mew ex",
                "Card Number": "232/091",
                "Rarity": "shiny ultra rare",
                "Price ($)": 48.0,
                "Pull Rate (1/X)": 96.0,
                "Pack Price": 5.0,
            },
        ]
    )

    prepared_df, _ = orchestrator.load_and_prepare_data(raw_df)

    with mock.patch.object(orchestrator, "calculate_reverse_ev", return_value=0.0):
        with mock.patch.object(orchestrator, "calculate_hit_probability", return_value=(50.0, 50.0)):
            results = orchestrator.calculate_evr_calculations(prepared_df)

    ev_totals_by_rarity = results["ev_totals_by_rarity"]
    shiny_rare_ev = prepared_df.loc[prepared_df["rarity_key"] == "shiny_rare", "EV"].sum()
    shiny_ultra_rare_ev = prepared_df.loc[
        prepared_df["rarity_key"] == "shiny_ultra_rare", "EV"
    ].sum()

    assert ev_totals_by_rarity["shiny_rare"] == pytest.approx(shiny_rare_ev)
    assert ev_totals_by_rarity["shiny_ultra_rare"] == pytest.approx(shiny_ultra_rare_ev)
    assert results["summary_data_for_manual_calcs"]["ev_totals_by_rarity"] is ev_totals_by_rarity
    assert results["total_manual_ev"] == pytest.approx(sum(ev_totals_by_rarity.values()))
    assert results["total_manual_ev"] == pytest.approx(prepared_df["EV"].sum())


def test_manual_aggregation_reconciles_row_level_ev_sum_with_dynamic_rarity_totals_excluding_reverse():
    orchestrator = PackCalculationOrchestrator(_GuardrailConfig())
    raw_df = _build_raw_df(
        [
            {
                "Card Name": "Common A",
                "Card Number": "001/091",
                "Rarity": "common",
                "Price ($)": 1.0,
                "Pull Rate (1/X)": 10.0,
                "Pack Price": 5.0,
            },
            {
                "Card Name": "Gardevoir ex",
                "Card Number": "029/091",
                "Rarity": "double rare",
                "Price ($)": 8.0,
                "Pull Rate (1/X)": 40.0,
                "Pack Price": 5.0,
            },
            {
                "Card Name": "Mew ex",
                "Card Number": "232/091",
                "Rarity": "shiny ultra rare",
                "Price ($)": 48.0,
                "Pull Rate (1/X)": 96.0,
                "Pack Price": 5.0,
            },
        ]
    )

    prepared_df, _ = orchestrator.load_and_prepare_data(raw_df)

    with mock.patch.object(orchestrator, "calculate_reverse_ev", return_value=0.65):
        with mock.patch.object(orchestrator, "calculate_hit_probability", return_value=(33.0, 67.0)):
            results = orchestrator.calculate_evr_calculations(prepared_df)

    ev_totals_by_rarity = results["ev_totals_by_rarity"]
    row_level_ev_sum = float(prepared_df["EV"].sum())
    dynamic_non_reverse_sum = sum(
        total for rarity_key, total in ev_totals_by_rarity.items() if rarity_key != "reverse"
    )

    assert dynamic_non_reverse_sum == pytest.approx(row_level_ev_sum)
    assert results["ev_reverse_total"] == pytest.approx(0.65)
    assert sum(ev_totals_by_rarity.values()) == pytest.approx(row_level_ev_sum + 0.65)
    assert results["total_manual_ev"] == pytest.approx(row_level_ev_sum + 0.65)


def test_legacy_alias_fields_are_derived_directly_from_ev_totals_by_rarity():
    orchestrator = PackCalculationOrchestrator(_GuardrailConfig())
    ev_totals_by_rarity = {
        "common": 0.25,
        "reverse": 0.5,
        "ace_spec_rare": 0.75,
        "pokeball_pattern": 1.15,
        "poke_ball_pattern": 7.5,
        "master_ball_pattern": 1.45,
        "master_ball": 8.5,
        "illustration_rare": 1.25,
        "special_illustration_rare": 1.75,
        "double_rare": 2.25,
        "hyper_rare": 2.75,
        "ultra_rare": 3.25,
    }

    summary = orchestrator._build_manual_summary_data(
        ev_totals_by_rarity,
        regular_pack_contribution=12.75,
        god_pack_ev_contribution=0.0,
        demi_god_pack_ev_contribution=0.0,
        total_manual_ev=12.75,
    )

    assert summary["ev_totals_by_rarity"] is ev_totals_by_rarity
    assert summary["ev_common_total"] == pytest.approx(ev_totals_by_rarity["common"])
    assert summary["ev_reverse_total"] == pytest.approx(ev_totals_by_rarity["reverse"])
    assert summary["ev_ace_spec_total"] == pytest.approx(ev_totals_by_rarity["ace_spec_rare"])
    assert summary["ev_pokeball_total"] == pytest.approx(ev_totals_by_rarity["pokeball_pattern"])
    assert summary["ev_master_ball_total"] == pytest.approx(ev_totals_by_rarity["master_ball_pattern"])
    assert summary["ev_IR_total"] == pytest.approx(ev_totals_by_rarity["illustration_rare"])
    assert summary["ev_SIR_total"] == pytest.approx(
        ev_totals_by_rarity["special_illustration_rare"]
    )
    assert summary["ev_double_rare_total"] == pytest.approx(ev_totals_by_rarity["double_rare"])
    assert summary["ev_hyper_rare_total"] == pytest.approx(ev_totals_by_rarity["hyper_rare"])
    assert summary["ev_ultra_rare_total"] == pytest.approx(ev_totals_by_rarity["ultra_rare"])
    assert summary["total_manual_ev"] == pytest.approx(sum(ev_totals_by_rarity.values()))


def test_hit_and_non_hit_contribution_output_keeps_card_number_as_primary_identity():
    orchestrator = PackCalculationOrchestrator(_GuardrailConfig())
    df = pd.DataFrame(
        {
            "Card Name": [
                "Charizard ex",
                "Charizard ex",
                "Charmander",
                "Charmander",
            ],
            "Card Number": ["006/165", "199/165", "004/165", "168/165"],
            "Rarity": [
                "double rare",
                "special illustration rare",
                "common",
                "illustration rare",
            ],
            "EV": [0.055, 0.2, 0.0015, 0.043],
        }
    )

    card_ev_split = orchestrator.build_hit_and_non_hit_ev_contributions(df)

    assert set(card_ev_split["hit_ev_contributions"]) == {"006/165", "199/165", "168/165"}
    assert set(card_ev_split["non_hit_ev_contributions"]) == {"004/165"}
    assert "Charizard ex" not in card_ev_split["hit_ev_contributions"]
    assert card_ev_split["card_display_labels"]["199/165"]["card_name"] == "Charizard ex"
    assert card_ev_split["card_display_labels"]["168/165"]["card_number"] == "168/165"


def test_unmapped_rarity_is_warned_and_still_visible_in_dynamic_totals(capsys):
    orchestrator = PackCalculationOrchestrator(_GuardrailConfig())
    raw_df = _build_raw_df(
        [
            {
                "Card Name": "Tera Card",
                "Card Number": "999/999",
                "Rarity": "stellar rare",
                "Price ($)": 20.0,
                "Pull Rate (1/X)": 100.0,
                "Pack Price": 5.0,
            }
        ]
    )

    prepared_df, _ = orchestrator.load_and_prepare_data(raw_df)

    with mock.patch.object(orchestrator, "calculate_reverse_ev", return_value=0.0):
        with mock.patch.object(orchestrator, "calculate_hit_probability", return_value=(0.0, 100.0)):
            results = orchestrator.calculate_evr_calculations(prepared_df)

    output = capsys.readouterr().out

    assert "[RARITY_WARNING]" in output
    assert "stellar rare" in output
    assert prepared_df.iloc[0]["rarity_key"] == "stellar_rare"
    assert pd.isna(prepared_df.iloc[0]["rarity_group"])
    assert results["ev_totals_by_rarity"]["stellar_rare"] == pytest.approx(prepared_df["EV"].sum())
    assert results["total_manual_ev"] == pytest.approx(prepared_df["EV"].sum())