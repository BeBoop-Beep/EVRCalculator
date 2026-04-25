import pandas as pd

from backend.constants.tcg.pokemon.scarletAndVioletEra.prismaticEvolutions import (
    SetPrismaticEvolutionsConfig,
)
from backend.simulations.monteCarloSimV2 import validate_pack_state_model
from backend.simulations.utils.extractScarletAndVioletCardGroups import (
    extract_scarletandviolet_card_groups,
)
from backend.simulations.utils.simulationTokenResolver import get_row_match_keys


class _PrismaticBaselineOnlyConfig(SetPrismaticEvolutionsConfig):
    PACK_STATE_MODEL = {
        "state_probabilities": {"baseline": 1.0},
        "state_outcomes": {
            "baseline": {
                "rare": "rare",
                "reverse_1": "regular reverse",
                "reverse_2": "regular reverse",
            }
        },
    }


def _prepared_like_df_with_rare_aliases() -> pd.DataFrame:
    # Shape mirrors real prepared dataframe columns used by simulation.
    return pd.DataFrame(
        [
            {
                "Card Name": "Common A",
                "Rarity": "Common",
                "rarity_raw": "common",
                "rarity_key": "common",
                "pattern_key": "",
                "aggregation_key": "common",
                "classification_key": "common",
                "Price ($)": 0.2,
                "Reverse Variant Price ($)": 0.15,
            },
            {
                "Card Name": "Uncommon A",
                "Rarity": "Uncommon",
                "rarity_raw": "uncommon",
                "rarity_key": "uncommon",
                "pattern_key": "",
                "aggregation_key": "uncommon",
                "classification_key": "uncommon",
                "Price ($)": 0.35,
                "Reverse Variant Price ($)": 0.22,
            },
            {
                "Card Name": "Ordinary Rare Holo A",
                "Rarity": "Holo Rare",
                "rarity_raw": "holo rare",
                "rarity_key": "holo_rare",
                "pattern_key": "",
                "aggregation_key": "holo_rare",
                "classification_key": "holo_rare",
                "Price ($)": 1.8,
                "Reverse Variant Price ($)": 0.4,
            },
            {
                "Card Name": "Ordinary Rare Holo B",
                "Rarity": "Rare Holo",
                "rarity_raw": "rare holo",
                "rarity_key": "rare_holo",
                "pattern_key": "",
                "aggregation_key": "rare_holo",
                "classification_key": "rare_holo",
                "Price ($)": 1.9,
                "Reverse Variant Price ($)": 0.42,
            },
            {
                "Card Name": "Master Overlay Rare Alias",
                "Rarity": "Holo Rare",
                "rarity_raw": "holo rare",
                "rarity_key": "holo_rare",
                "pattern_key": "master_ball_pattern",
                "aggregation_key": "master_ball_pattern",
                "classification_key": "master_ball_pattern",
                "Price ($)": 4.8,
                "Reverse Variant Price ($)": 1.5,
            },
        ]
    )


def test_prismatic_base_rare_pool_not_empty_with_holo_rare_aliases() -> None:
    df = _prepared_like_df_with_rare_aliases()

    base_keys, source = get_row_match_keys(df, mode="base_rarity")
    assert source == "rarity_key"
    assert int(base_keys.eq("rare").sum()) == 3

    pools = extract_scarletandviolet_card_groups(_PrismaticBaselineOnlyConfig, df)

    assert not pools["rare"].empty
    assert "Ordinary Rare Holo A" in pools["rare"]["Card Name"].tolist()
    assert "Ordinary Rare Holo B" in pools["rare"]["Card Name"].tolist()
    assert "Master Overlay Rare Alias" in pools["rare"]["Card Name"].tolist()
    assert "Master Overlay Rare Alias" in pools["hit"]["Card Name"].tolist()

    # Baseline validation is the regression target: this raised when rare pool was empty.
    validate_pack_state_model(_PrismaticBaselineOnlyConfig, pools)
