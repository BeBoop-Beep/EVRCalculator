import pytest

from backend.constants.tcg.pokemon.swordAndShieldEra.astralRadiance import SetAstralRadianceConfig
from backend.constants.tcg.pokemon.swordAndShieldEra.battleStyles import SetBattleStylesConfig
from backend.constants.tcg.pokemon.swordAndShieldEra.brilliantStars import SetBrilliantStarsConfig
from backend.constants.tcg.pokemon.swordAndShieldEra.chillingReign import SetChillingReignConfig
from backend.constants.tcg.pokemon.swordAndShieldEra.darknessAblaze import SetDarknessAblazeConfig
from backend.constants.tcg.pokemon.swordAndShieldEra.evolvingSkies import SetEvolvingSkiesConfig
from backend.constants.tcg.pokemon.swordAndShieldEra.fusionStrike import SetFusionStrikeConfig
from backend.constants.tcg.pokemon.swordAndShieldEra.lostOrigin import SetLostOriginConfig
from backend.constants.tcg.pokemon.swordAndShieldEra.rebelClash import SetRebelClashConfig
from backend.constants.tcg.pokemon.swordAndShieldEra.silverTempest import SetSilverTempestConfig
from backend.constants.tcg.pokemon.swordAndShieldEra.swordAndShield import SetSwordAndShieldConfig
from backend.constants.tcg.pokemon.swordAndShieldEra.vividVoltage import SetVividVoltageConfig


@pytest.mark.parametrize(
    "config_cls,expected_holo",
    [
        (SetSwordAndShieldConfig, 1 / 5.5),
        (SetRebelClashConfig, 1 / 5.7),
        (SetDarknessAblazeConfig, 1 / 5.9),
        (SetVividVoltageConfig, 0.2175),
        (SetBattleStylesConfig, 1 / 5.6),
        (SetChillingReignConfig, 1 / 5.6),
        (SetEvolvingSkiesConfig, 1 / 5.5),
        (SetFusionStrikeConfig, 1 / 5.6),
        (SetBrilliantStarsConfig, 1 / 5.7),
        (SetAstralRadianceConfig, 1 / 5.7),
        (SetLostOriginConfig, 1 / 5.6),
        (SetSilverTempestConfig, 1 / 5.6),
    ],
)
def test_swsh_holo_rare_runtime_is_not_legacy_one_in_three(config_cls, expected_holo):
    table = config_cls.RARE_SLOT_PROBABILITY

    assert table["holo rare"] == pytest.approx(expected_holo, abs=1e-12)
    assert table["holo rare"] != pytest.approx(1 / 3, abs=1e-12)
    assert sum(table.values()) == pytest.approx(1.0, abs=1e-12)


@pytest.mark.parametrize(
    "evidence_rows,source_id,expected_odds",
    [
        (
            SetSwordAndShieldConfig.SWORD_AND_SHIELD_PULL_RATE_REFERENCE_BUCKET_EVIDENCE,
            "swsh1_thepricedex_cross_reference_2026_05",
            "1/5.5",
        ),
        (
            SetRebelClashConfig.REBEL_CLASH_PULL_RATE_REFERENCE_BUCKET_EVIDENCE,
            "swsh2_thepricedex_cross_reference_2026_05",
            "1/5.7",
        ),
        (
            SetDarknessAblazeConfig.DARKNESS_ABLAZE_PULL_RATE_REFERENCE_BUCKET_EVIDENCE,
            "swsh3_thepricedex_cross_reference_2026_05",
            "1/5.9",
        ),
        (
            SetBattleStylesConfig.BATTLE_STYLES_PULL_RATE_REFERENCE_BUCKET_EVIDENCE,
            "battle_styles_thepricedex_cross_reference_2026_05",
            "1/5.6",
        ),
        (
            SetFusionStrikeConfig.FUSION_STRIKE_PULL_RATE_REFERENCE_BUCKET_EVIDENCE,
            "fusion_strike_thepricedex_cross_reference_2026_05",
            "1/5.6",
        ),
        (
            SetBrilliantStarsConfig.BRILLIANT_STARS_PULL_RATE_REFERENCE_BUCKET_EVIDENCE,
            "brilliant_stars_thepricedex_cross_reference_2026_05",
            "1/5.7",
        ),
        (
            SetAstralRadianceConfig.ASTRAL_RADIANCE_PULL_RATE_REFERENCE_BUCKET_EVIDENCE,
            "astral_radiance_thepricedex_cross_reference_2026_05",
            "1/5.7",
        ),
        (
            SetLostOriginConfig.LOST_ORIGIN_PULL_RATE_REFERENCE_BUCKET_EVIDENCE,
            "lost_origin_thepricedex_cross_reference_2026_05",
            "1/5.6",
        ),
        (
            SetSilverTempestConfig.SILVER_TEMPEST_PULL_RATE_REFERENCE_BUCKET_EVIDENCE,
            "silver_tempest_thepricedex_cross_reference_2026_05",
            "1/5.6",
        ),
    ],
)
def test_swsh_holo_rare_reference_rows_are_non_direct_secondary_index(evidence_rows, source_id, expected_odds):
    holo_row = next(row for row in evidence_rows if row.get("normalized_bucket") == "holo rare")

    assert holo_row["odds_display"] == expected_odds
    assert holo_row["source_status"] == "SECONDARY_INDEX_ONLY"
    assert holo_row["source_granularity_status"] == "SECONDARY_INDEX_ONLY"
    assert source_id in (holo_row.get("source_ids") or [])


@pytest.mark.parametrize(
    "draft_audit,expected_odds,expected_source_id",
    [
        (
            SetChillingReignConfig.CHILLING_REIGN_RARE_SLOT_PROBABILITY_DRAFT_AUDIT,
            "1/5.6",
            "swsh6_thepricedex_cross_reference_2026_06_holo",
        ),
        (
            SetEvolvingSkiesConfig.EVOLVING_SKIES_RARE_SLOT_PROBABILITY_DRAFT_AUDIT,
            "1/5.5",
            "swsh7_thepricedex_cross_reference_2026_06_holo",
        ),
    ],
)
def test_swsh6_swsh7_holo_rare_draft_rows_remain_provisional_and_non_direct(draft_audit, expected_odds, expected_source_id):
    provisional_rows = draft_audit["source_rows_used_with_assumptions"]
    holo_row = next(
        payload
        for payload in provisional_rows.values()
        if payload.get("normalized_bucket") == "holo rare"
    )

    assert holo_row["source_odds"] == expected_odds
    assert holo_row["source_granularity_status"] == "PROVISIONAL_DIRECTIONAL"
    assert holo_row.get("source_id") == expected_source_id
    assert "not source_direct" in (holo_row.get("assumption") or "").lower()
