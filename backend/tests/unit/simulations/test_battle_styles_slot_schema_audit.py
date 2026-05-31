import pandas as pd
import pytest

from backend.constants.tcg.pokemon.swordAndShieldEra.battleStyles import SetBattleStylesConfig
from backend.simulations.slotSchemaOutcomeResolver import apply_slot_schema_outcome_pool_mapping


class _BattleStylesMapping:
    SLOT_SCHEMA_OUTCOME_POOL_MAPPING = SetBattleStylesConfig.SLOT_SCHEMA_OUTCOME_POOL_MAPPING


def _resolve_row(name: str, rarity: str, card_number: str) -> list[str]:
    df = pd.DataFrame(
        [
            {
                "name": name,
                "rarity": rarity,
                "printing_type": "holo",
                "card_number": card_number,
            }
        ]
    )
    pools = apply_slot_schema_outcome_pool_mapping(
        _BattleStylesMapping,
        df,
        allow_empty_pools=True,
    )
    return [bucket for bucket, pool_df in pools.items() if not pool_df.empty]


def test_battle_styles_reddit_source_url_points_to_exact_thread_not_generic_reddit():
    source_rows = {
        row["source_id"]: row
        for row in SetBattleStylesConfig.BATTLE_STYLES_PULL_RATE_REFERENCE_SOURCES
    }
    reddit_url = source_rows["battle_styles_community_pack_study"]["source_url"]

    assert "/comments/" in reddit_url
    assert "battle_styles_pull_data_after_almost_20000_packs" in reddit_url
    assert reddit_url != "https://www.reddit.com/r/PokemonTCG/"


def test_battle_styles_runtime_keys_include_alternate_art_vmax():
    table = SetBattleStylesConfig.RARE_SLOT_PROBABILITY

    assert "alternate art vmax" in table
    assert table["alternate art vmax"] == pytest.approx(1 / 684, abs=1e-12)
    assert sum(float(value) for value in table.values()) == pytest.approx(1.0, abs=1e-12)


def test_battle_styles_thepricedex_rows_remain_secondary_index_only():
    evidence = SetBattleStylesConfig.BATTLE_STYLES_PULL_RATE_REFERENCE_BUCKET_EVIDENCE

    pricedex_rows = [
        row
        for row in evidence
        if any("thepricedex" in str(source_id).lower() for source_id in (row.get("source_ids") or []))
    ]
    assert pricedex_rows
    assert all(row["source_status"] == "SECONDARY_INDEX_ONLY" for row in pricedex_rows)
    assert all(row["source_status"] != "SOURCE_DIRECT" for row in pricedex_rows)

    secret_rare_rows = [
        row
        for row in pricedex_rows
        if str(row.get("source_bucket_label") or "").lower() == "thepricedex secret rare"
    ]
    assert secret_rare_rows
    assert all(str(row.get("normalized_bucket") or "") != "alternate art vmax" for row in secret_rare_rows)


def test_battle_styles_alt_art_vmax_evidence_row_is_direct_and_runtime_used():
    evidence = SetBattleStylesConfig.BATTLE_STYLES_PULL_RATE_REFERENCE_BUCKET_EVIDENCE
    alt_vmax_row = next(row for row in evidence if row["normalized_bucket"] == "alternate art vmax")

    assert alt_vmax_row["source_bucket_label"] == "Alt VMAX"
    assert alt_vmax_row["source_status"] == "SOURCE_DIRECT"
    assert alt_vmax_row["source_granularity_status"] == "SOURCE_DIRECT"
    assert alt_vmax_row["used_in_runtime"] is True
    assert alt_vmax_row["odds_display"] == "1/684"
    assert "community sample" in (alt_vmax_row.get("caveat") or "").lower()


def test_battle_styles_alt_art_vmax_classification_matches_known_rows():
    # Confirmed alt-art secret cards
    assert _resolve_row(
        "Single Strike Urshifu VMAX (Alternate Art Secret)",
        "Secret Rare",
        "168/163",
    ) == ["alternate art vmax"]
    assert _resolve_row(
        "Rapid Strike Urshifu VMAX (Alternate Art Secret)",
        "Secret Rare",
        "170/163",
    ) == ["alternate art vmax"]

    # Regular VMAX cards stay in regular VMAX
    assert _resolve_row(
        "Single Strike Urshifu VMAX",
        "Ultra Rare",
        "086/163",
    ) == ["regular vmax"]
    assert _resolve_row(
        "Rapid Strike Urshifu VMAX",
        "Ultra Rare",
        "088/163",
    ) == ["regular vmax"]


def test_battle_styles_alt_art_vmax_does_not_overlap_other_hit_buckets():
    buckets = _resolve_row(
        "Single Strike Urshifu VMAX (Alternate Art Secret)",
        "Secret Rare",
        "168/163",
    )

    assert buckets == ["alternate art vmax"]
    assert "regular vmax" not in buckets
    assert "rainbow rare" not in buckets
    assert "gold rare" not in buckets
    assert "alternate art v" not in buckets
    assert "full art" not in buckets
