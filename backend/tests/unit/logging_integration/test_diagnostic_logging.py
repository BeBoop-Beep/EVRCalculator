import logging
import re

import pandas as pd
import pytest

from backend.calculations.packCalcsRefractored.evrCalculator import PackEVCalculator
from backend.constants.tcg.pokemon.scarletAndVioletEra.obsidianFlames import SetObsidianFlamesConfig
from backend.constants.tcg.pokemon.scarletAndVioletEra.prismaticEvolutions import SetPrismaticEvolutionsConfig
from backend.simulations.evrSimulator import PackEVRSimulator
from backend.simulations.utils.extractScarletAndVioletCardGroups import extract_scarletandviolet_card_groups


class _PrismaticV1Config(SetPrismaticEvolutionsConfig):
    USE_MONTE_CARLO_V2 = False


def _build_prismatic_like_df() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "Card Name": [
                "Common A",
                "Common B",
                "Uncommon A",
                "Rare A",
                "Poke Ball Pattern A",
                "Master Ball Pattern A",
                "Illustration Rare A",
            ],
            "Rarity": [
                "common",
                "common",
                "uncommon",
                "rare",
                "rare",
                "rare",
                "illustration rare",
            ],
            "rarity_group": ["common", "common", "uncommon", "rare", "rare", "rare", "hits"],
            "rarity_key": ["common", "common", "uncommon", "rare", "rare", "rare", "illustration_rare"],
            "aggregation_key": [
                "common",
                "common",
                "uncommon",
                "rare",
                "pokeball_pattern",
                "master_ball_pattern",
                "illustration_rare",
            ],
            "Special Type": ["", "", "", "", "poke ball", "master ball", ""],
            "Price ($)": [0.11, 0.13, 0.24, 1.0, 2.1, 5.2, 9.5],
            "Reverse Variant Price ($)": [0.21, 0.22, 0.33, 0.51, 2.5, 5.8, None],
            "EV": [0.10, 0.20, 0.30, 0.40, 1.03, 1.69, 2.50],
        }
    )


def _build_obsidian_like_df() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "Card Name": ["Common A", "Common B", "Uncommon A", "Rare A", "Illustration Rare A"],
            "Rarity": ["common", "common", "uncommon", "rare", "illustration rare"],
            "rarity_group": ["common", "common", "uncommon", "rare", "hits"],
            "rarity_key": ["common", "common", "uncommon", "rare", "illustration_rare"],
            "aggregation_key": ["common", "common", "uncommon", "rare", "illustration_rare"],
            "Special Type": ["", "", "", "", ""],
            "Price ($)": [0.10, 0.10, 0.20, 0.90, 4.50],
            "Reverse Variant Price ($)": [0.15, 0.16, 0.25, 0.45, None],
            "EV": [0.10, 0.10, 0.20, 0.90, 1.20],
        }
    )


def _pool_log_lines(caplog: pytest.LogCaptureFixture) -> list[str]:
    return [record.message for record in caplog.records if "[POOL_COMPOSITION]" in record.message]


def _manual_ev_log_lines(caplog: pytest.LogCaptureFixture) -> list[str]:
    return [record.message for record in caplog.records if "[MANUAL_EV_COMPOSITION]" in record.message]


def _cross_check_log_lines(caplog: pytest.LogCaptureFixture) -> list[str]:
    return [record.message for record in caplog.records if "[POOL_CROSS_CHECK]" in record.message]


def _pool_input_profile_lines(caplog: pytest.LogCaptureFixture) -> list[str]:
    return [record.message for record in caplog.records if "[POOL_INPUT_PROFILE]" in record.message]


def _extract_metric(messages: list[str], key: str) -> str:
    pattern = re.compile(rf"{re.escape(key)}=([^\s]+)")
    for message in messages:
        match = pattern.search(message)
        if match:
            return match.group(1)
    raise AssertionError(f"Metric '{key}' not found in logs: {messages}")


def test_pool_composition_logging_present(caplog: pytest.LogCaptureFixture) -> None:
    caplog.set_level(logging.INFO)
    df = _build_prismatic_like_df()

    extract_scarletandviolet_card_groups(SetPrismaticEvolutionsConfig, df)

    messages = _pool_log_lines(caplog)
    expected_metrics = [
        "total_rows_in_source",
        "common_pool_size",
        "pattern_rows_in_common",
        "uncommon_pool_size",
        "pattern_rows_in_uncommon",
        "rare_pool_size",
        "pattern_rows_in_rare",
        "hit_pool_size",
        "reverse_pool_size",
        "pokeball_pattern_count",
        "master_ball_pattern_count",
        "pattern_overlap_with_base_pools",
    ]
    for metric in expected_metrics:
        assert any(f"{metric}=" in message for message in messages), f"Missing metric: {metric}"


def test_pool_composition_logging_correct(caplog: pytest.LogCaptureFixture) -> None:
    caplog.set_level(logging.INFO)
    df = _build_prismatic_like_df()

    extract_scarletandviolet_card_groups(SetPrismaticEvolutionsConfig, df)

    messages = _pool_log_lines(caplog)

    assert int(_extract_metric(messages, "common_pool_size")) == 2
    assert int(_extract_metric(messages, "pokeball_pattern_count")) == 1
    assert int(_extract_metric(messages, "master_ball_pattern_count")) == 1


def test_pool_input_profile_logging_includes_base_rarity_source_and_counts(caplog: pytest.LogCaptureFixture) -> None:
    caplog.set_level(logging.WARNING)
    df = _build_prismatic_like_df()

    extract_scarletandviolet_card_groups(SetPrismaticEvolutionsConfig, df)

    messages = _pool_input_profile_lines(caplog)
    assert any("base_rarity_key_source=rarity_key" in message for message in messages)
    assert any("base_rarity_key value=rare count=3" in message for message in messages)
    assert any("base_rarity_key_counts common=2 uncommon=1 rare=3" in message for message in messages)


def test_pattern_overlap_logging_reports_expected_overlap(caplog: pytest.LogCaptureFixture) -> None:
    caplog.set_level(logging.INFO)
    df = _build_prismatic_like_df()

    extract_scarletandviolet_card_groups(SetPrismaticEvolutionsConfig, df)

    messages = _pool_log_lines(caplog)
    assert int(_extract_metric(messages, "pattern_overlap_with_base_pools")) == 2


def test_manual_ev_logging_present(caplog: pytest.LogCaptureFixture) -> None:
    caplog.set_level(logging.INFO)
    calculator = PackEVCalculator(SetPrismaticEvolutionsConfig)
    df = _build_prismatic_like_df()

    calculator.calculate_rarity_ev_totals(df, ev_reverse_total=0.75)

    messages = _manual_ev_log_lines(caplog)
    expected_metrics = [
        "total_ev_across_all_buckets",
        "base_rarity_ev_total",
        "pattern_ev_total",
        "other_special_ev_total",
        "pokeball_pattern_ev",
        "master_ball_pattern_ev",
    ]
    for metric in expected_metrics:
        assert any(f"{metric}=" in message for message in messages), f"Missing metric: {metric}"


def test_manual_ev_logging_values_reasonable(caplog: pytest.LogCaptureFixture) -> None:
    caplog.set_level(logging.INFO)
    calculator = PackEVCalculator(SetPrismaticEvolutionsConfig)
    df = _build_prismatic_like_df()

    calculator.calculate_rarity_ev_totals(df, ev_reverse_total=0.75)

    messages = _manual_ev_log_lines(caplog)

    pokeball_ev = float(_extract_metric(messages, "pokeball_pattern_ev"))
    master_ball_ev = float(_extract_metric(messages, "master_ball_pattern_ev"))
    pattern_ev_total = float(_extract_metric(messages, "pattern_ev_total"))

    assert pokeball_ev > 0
    assert master_ball_ev > 0
    assert pattern_ev_total == pytest.approx(pokeball_ev + master_ball_ev, rel=1e-2, abs=1e-2)


def test_cross_check_logging_verifies_no_leakage(
    caplog: pytest.LogCaptureFixture,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    caplog.set_level(logging.INFO)
    df = _build_prismatic_like_df()

    # Keep this test focused on cross-check logging by bypassing heavy simulation work.
    import backend.simulations.evrSimulator as evr_simulator_module

    monkeypatch.setattr(evr_simulator_module, "make_simulate_pack_fn", lambda **kwargs: (lambda: 0.0))
    monkeypatch.setattr(
        evr_simulator_module,
        "run_simulation",
        lambda simulate_one_pack, rarity_pull_counts, rarity_value_totals, n: {"mean": 0.0, "values": [0.0]},
    )
    monkeypatch.setattr(evr_simulator_module, "print_simulation_summary", lambda sim_results: None)
    monkeypatch.setattr(evr_simulator_module, "validate_and_debug_slot", lambda **kwargs: None)
    monkeypatch.setattr(
        evr_simulator_module,
        "validate_full_pack_logic",
        lambda slot_logs, simulate_one_pack, rare_slot_config, reverse_slot_config, n: None,
    )

    simulator = PackEVRSimulator(_PrismaticV1Config)
    simulator.calculate_evr_simulations(df)

    messages = _cross_check_log_lines(caplog)
    assert any("Verifying pool composition for simulation" in m for m in messages)
    assert int(_extract_metric(messages, "base_pools_pattern_overlap_count")) >= 0
    assert _extract_metric(messages, "all_rows_accounted_for") == "True"
    assert _extract_metric(messages, "patterns_in_hit_pool") == "2_rows"


def test_logging_on_non_pattern_set_minimal(caplog: pytest.LogCaptureFixture) -> None:
    caplog.set_level(logging.INFO)
    df = _build_obsidian_like_df()

    extract_scarletandviolet_card_groups(SetObsidianFlamesConfig, df)

    messages = _pool_log_lines(caplog)
    assert any("[POOL_COMPOSITION]" in message for message in messages)
    assert int(_extract_metric(messages, "pokeball_pattern_count")) == 0
    assert int(_extract_metric(messages, "master_ball_pattern_count")) == 0
